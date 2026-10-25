"""C11 lowering with explicit left-to-right evaluation and a small scalar runtime."""
import json
import hashlib
from parser.syntax import decode_string
from parser.checker import unwrap
from .checker import VOID,BOOL,STRING,INT,FLOAT,NIL,SCALARS,pointer

PRELUDE=r'''#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#if defined(_WIN32) && !defined(_WIN64)
# if defined(_MSC_VER)
#  define GS_SYSTEM __stdcall
# else
#  define GS_SYSTEM __attribute__((stdcall))
# endif
#else
# define GS_SYSTEM
#endif
#if defined(_WIN32)
# define GS_EXPORT __declspec(dllexport)
#else
# define GS_EXPORT __attribute__((visibility("default")))
#endif
#ifndef GS_NATIVE_TYPES_V1
#define GS_NATIVE_TYPES_V1
typedef struct { const uint8_t *data; size_t len; } GSString;
#endif
'''
RUNTIME=r'''
_Noreturn static void gs_fail(const char *message) { fputs(message, stderr); fputc('\n',stderr); exit(1); }
static bool gs_string_equal(GSString a, GSString b) { return a.len==b.len && (!a.len || memcmp(a.data,b.data,a.len)==0); }
static GSString gs_string_view(const char *value) {
  if (!value) gs_fail("string: null C pointer");
  return (GSString){(const uint8_t *)value,strlen(value)};
}
static const char *gs_cstr(GSString value) {
  if (value.len && memchr(value.data,0,value.len)) gs_fail("cstr: embedded NUL");
  return (const char *)value.data;
}
'''


def c_bytes(text):
    data=text.encode('utf-8')
    return '"'+''.join('\\%03o'%b for b in data)+'"'


class CEmitter:
    def __init__(self,project):
        self.p=project;self.callbacks={};self.helpers={};self.lines=[];self.depth=0;self.counter=0;self.loops=[]

    def line(self,text=''):self.lines.append('  '*self.depth+text)
    def fresh(self):self.counter+=1;return 'gs_tmp_'+str(self.counter)

    def ctype(self,t):
        if t==VOID:return 'void'
        if t==BOOL:return 'bool'
        if t.kind=='float':return 'float' if t.name=='f32' else 'double'
        if t.kind=='cchar':return 'char'
        if t==STRING:return 'GSString'
        if t==NIL:return 'void *'
        if t.kind=='integer':return {'int':'int64_t','usize':'uintptr_t','isize':'intptr_t'}.get(t.name,('uint' if t.name[0]=='u' else 'int')+t.name[1:]+'_t')
        if t.kind=='record':return t.name
        if t.kind=='pointer':
            inner=self.ctype(t.args[0])
            return (inner+' const *' if t.args[0].kind in ('pointer','callback') else 'const '+inner+' *') if t.name=='const' else inner+' *'
        if t.kind=='fixed_array':return self.ctype(t.args[0])+'['+t.name+']'
        if t.kind=='callback':
            if t not in self.callbacks:
                name='gs_callback_'+hashlib.sha256(repr(t).encode()).hexdigest()[:16]
                params=', '.join(self.ctype(a) for a in t.args[:-1]) or 'void'
                code='typedef '+self.ctype(t.args[-1])+' ('+('GS_SYSTEM ' if t.name=='system' else '')+'*'+name+')('+params+');'
                self.callbacks[t]=(name,code)
            return self.callbacks[t][0]
        raise ValueError('unlowered native type: '+str(t))

    def declaration(self,t,name):
        suffix=''
        while t.kind=='fixed_array':suffix+='['+t.name+']';t=t.args[0]
        return self.ctype(t)+' '+name+suffix

    def literal(self,n):
        if n.kind=='string':
            text=decode_string(n.value);return '(GSString){(const uint8_t *)'+c_bytes(text)+','+str(len(text.encode('utf-8')))+'}'
        if n.kind=='number':
            if n.native_type==FLOAT:return n.value
            return ('UINT64_C' if not self.p.signed(n.native_type) else 'INT64_C')+'('+n.value+')'
        if n.kind=='name':return {'true':'true','false':'false','nil':'NULL'}.get(n.value,getattr(getattr(n,'binding',None),'c_name',n.value))
        if n.kind=='unary':
            if n.value=='-' and n.children[0].kind=='number' and n.children[0].value==str(1<<63):return '(-INT64_C(9223372036854775807)-1)'
            return '('+n.value+self.literal(n.children[0])+')'
        if n.kind=='call' and getattr(n,'native_builtin',None)=='cast':return '(('+self.ctype(n.native_target)+')'+self.literal(n.children[1])+')'
        raise ValueError('not a native constant initializer')

    def value(self,n):
        expression=self.expr(n);t=n.native_type
        if t==VOID:return expression
        if t.kind=='fixed_array':return expression
        name=self.fresh();self.line(self.declaration(t,name)+' = '+expression+';');return name

    def lvalue(self,n):
        if n.kind=='name':return n.binding.c_name
        if n.kind=='member':
            base=n.children[0]
            if base.native_type.kind=='pointer':return '('+self.value(base)+')->'+self.field(n.value)
            return '('+self.lvalue(base)+').'+self.field(n.value)
        if n.kind=='index':
            base,index=n.children
            array=self.value(base) if base.native_type.kind=='pointer' else self.lvalue(base)
            position=self.value(index)
            if base.native_type.kind=='fixed_array':self.line('if ((uintmax_t)'+position+' >= '+base.native_type.name+') gs_fail("array index out of bounds");')
            return '('+array+')['+position+']'
        raise ValueError('non-addressable native value')

    def field(self,name):return 'field_'+name.encode().hex()

    def arithmetic(self,op,t,a,b):
        if t.kind=='float':return '('+a+' '+op+' '+b+')'
        name='gs_'+{'+':'add','-':'sub','*':'mul','%':'rem','idiv':'div'}[op]+'_'+t.name
        if name not in self.helpers:
            c=self.ctype(t);body=''
            if op in ('+','-','*') and self.p.signed(t):
                builtin={'+':'add','-':'sub','*':'mul'}[op]
                body=c+' out; if (__builtin_'+builtin+'_overflow(a,b,&out)) gs_fail("signed integer overflow"); return out;'
            elif op in ('%','idiv'):
                body='if (!b) gs_fail("integer division by zero"); '
                if self.p.signed(t):
                    minimum=self.integer_constant(self.p.limits(t)[0],True)
                    body+='if (a == '+minimum+' && b == -1) gs_fail("signed integer overflow"); '
                body+='return a '+('%' if op=='%' else '/')+' b;'
            else:
                # Widen small unsigned operands before multiplication to avoid int-promotion UB.
                body='return ('+c+')((uint64_t)a '+op+' (uint64_t)b);'
            self.helpers[name]='static '+c+' '+name+'('+c+' a, '+c+' b) { '+body+' }'
        return name+'('+a+','+b+')'

    def integer_constant(self,value,signed=False):
        if value<0:return '(-INT64_C('+str(-value-1)+')-1)'
        return ('INT64_C' if signed else 'UINT64_C')+'('+str(value)+')'

    def convert(self,n,source):
        target=n.native_target;actual=n.children[1].native_type
        if target.kind=='integer' and actual.kind=='float':
            low,high=self.p.limits(target)
            self.line('if (!isfinite('+source+') || (long double)'+source+' < '+str(low)+'.0L || (long double)'+source+' >= '+str(high+1)+'.0L) gs_fail("numeric conversion out of range");')
        elif target.kind==actual.kind=='integer':
            low,high=self.p.limits(target);source_low,source_high=self.p.limits(actual)
            if source_low<low:
                self.line('if ('+source+' < '+self.integer_constant(low,True)+') gs_fail("numeric conversion out of range");')
            if source_high>high:
                if self.p.signed(actual):condition='('+source+' >= 0 && (uintmax_t)'+source+' > '+self.integer_constant(high)+')'
                else:condition='((uintmax_t)'+source+' > '+self.integer_constant(high)+')'
                self.line('if '+condition+' gs_fail("numeric conversion out of range");')
        intermediary='(uintptr_t)' if actual.kind=='pointer' and target.kind=='integer' or actual.kind=='integer' and target.kind=='pointer' else ''
        return '(('+self.ctype(target)+')'+intermediary+'('+source+'))'

    def expr(self,n):
        k,v,c=n.kind,n.value,n.children
        if k in ('number','string','name'):return self.literal(n)
        if k=='unary':
            if v=='-' and c[0].kind=='number' and c[0].value==str(1<<63):return '(-INT64_C(9223372036854775807)-1)'
            a=self.value(c[0])
            return self.arithmetic('-',n.native_type,'0',a) if v=='-' and n.native_type.kind=='integer' else '('+v+a+')'
        if k=='binary':
            a=self.value(c[0])
            if v in ('&&','||'):
                result=self.fresh();self.line('bool '+result+' = '+a+';');self.line('if ('+('!' if v=='||' else '')+result+') {');self.depth+=1
                b=self.value(c[1]);self.line(result+' = '+b+';');self.depth-=1;self.line('}');return result
            b=self.value(c[1])
            if v in ('==','!=') and c[0].native_type==STRING:return ('!' if v=='!=' else '')+'gs_string_equal('+a+','+b+')'
            if v=='/':return '((double)'+a+' / (double)'+b+')'
            if v in ('+','-','*','%'):return self.arithmetic(v,n.native_type,a,b)
            return '('+a+' '+v+' '+b+')'
        if k in ('member','index'):
            if k=='member' and c[0].native_type.kind=='record' and c[0].kind not in ('name','member','index'):return '('+self.value(c[0])+').'+self.field(v)
            return self.lvalue(n)
        if k=='composite':
            name=self.fresh();self.line(self.declaration(n.native_type,name)+' = {0};')
            for item in c:
                value=self.value(item.children[0]);self.line(name+'.'+self.field(item.value)+' = '+value+';')
            return name
        if k=='call':
            builtin=getattr(n,'native_builtin',None)
            if builtin:return self.builtin(n,builtin,c[1:])
            callee=self.value(c[0]);args=[self.value(x) for x in c[1:]]
            return callee+'('+','.join(args)+')'
        raise ValueError('unlowered native expression: '+k)

    def builtin(self,n,name,args):
        if name in ('sizeof','alignof'):return '(uintptr_t)'+('sizeof' if name=='sizeof' else '_Alignof')+'('+self.ctype(n.native_target)+')'
        if name=='offsetof':return '(uintptr_t)offsetof('+self.ctype(n.native_target)+','+self.field(n.native_field)+')'
        if name=='address':return '&('+self.lvalue(args[0])+')'
        if name=='utf16':
            data=decode_string(args[0].value).encode('utf-16-le');units=[int.from_bytes(data[i:i+2],'little') for i in range(0,len(data),2)]+[0]
            symbol=self.fresh();self.line('static const uint16_t '+symbol+'[] = {'+','.join(map(str,units))+'};');return symbol
        values=[self.value(x) for x in args]
        if name=='string_view':return values[0] if args[0].native_type==STRING else 'gs_string_view((const char *)'+values[0]+')'
        if name=='cast':return self.convert(n,values[0])
        if name in ('print','println'):
            for i,(value,arg) in enumerate(zip(values,args)):
                if i:self.line('fputc(\' \',stdout);')
                typ=arg.native_type
                if typ==STRING:self.line('(void)fwrite('+value+'.data,1,'+value+'.len,stdout);')
                elif typ==BOOL:self.line('fputs('+value+' ? "true" : "false",stdout);')
                elif typ.kind=='float':self.line('printf("%.17g",'+value+');')
                elif typ.kind=='pointer':self.line('printf("%p",(void *)'+value+');')
                else:self.line('printf("%" '+('PRId64' if self.p.signed(typ) else 'PRIu64')+',('+('int64_t' if self.p.signed(typ) else 'uint64_t')+')'+value+');')
            if name=='println':self.line('fputc(\'\\n\',stdout);')
            return '(void)0'
        if name=='panic':self.line('(void)fwrite('+values[0]+'.data,1,'+values[0]+'.len,stderr);');return 'gs_fail("")'
        if name=='len':return '(int64_t)'+(values[0]+'.len' if args[0].native_type==STRING else args[0].native_type.name)
        if name=='cstr':return 'gs_cstr('+values[0]+')'
        if name=='load':return '*('+values[0]+')'
        if name=='store':return '(*('+values[0]+') = '+values[1]+')'
        if name=='offset':return '('+values[0]+' + '+values[1]+')'
        if name=='idiv':return self.arithmetic('idiv',n.native_type,*values)
        if name in ('bitOr','bitAnd','bitXor','bitNot'):
            op={'bitOr':'|','bitAnd':'&','bitXor':'^','bitNot':'~'}[name]
            return '(('+self.ctype(n.native_type)+')('+ (op+values[0] if len(values)==1 else op.join(values)) +'))'
        if name in ('shl','shr'):
            bits=self.p.width(n.native_type);self.line('if ((uintmax_t)'+values[1]+' >= '+str(bits)+') gs_fail("shift count out of range");')
            unsigned='uint'+str(bits)+'_t';return '(('+self.ctype(n.native_type)+')(('+unsigned+')'+values[0]+(' << ' if name=='shl' else ' >> ')+values[1]+'))'
        raise ValueError('unlowered native builtin: '+name)

    def statement(self,n,global_=False):
        k,v,c=n.kind,n.value,n.children
        if k=='decl' or k=='assign' and v==':=':
            value_node=c[0] if k=='decl' else c[1]
            value=self.value(value_node) if value_node else '{0}'
            if global_:
                if value_node:self.line(n.binding.c_name+' = '+value+';')
            else:self.line(self.declaration(n.binding.typ,n.binding.c_name)+' = '+value+';')
        elif k=='assign' or k=='update':
            left=c[0];location=self.fresh();self.line(self.ctype(pointer(left.native_type))+' '+location+' = &('+self.lvalue(left)+');')
            old=None
            if k=='update' or v!='=':old=self.fresh();self.line(self.declaration(left.native_type,old)+' = *'+location+';')
            right=self.value(c[1]) if k=='assign' else '1'
            expression=right if v=='=' else self.arithmetic('+' if v in ('+=','++') else '-',left.native_type,old,right)
            self.line('*'+location+' = '+expression+';')
        elif k=='expr':self.line(self.expr(c[0])+';')
        elif k=='return':self.line('return'+(' '+self.value(c[0]) if c else '')+';')
        elif k=='if':
            test=self.value(c[0]);self.line('if ('+test+') {');self.depth+=1
            for child in c[1]:self.statement(child)
            self.depth-=1;self.line('}')
            if c[2] is not None:
                self.line('else {');self.depth+=1
                for child in c[2]:self.statement(child)
                self.depth-=1;self.line('}')
        elif k=='for':
            self.line('{');self.depth+=1
            if c[0]:self.statement(c[0])
            self.line('for (;;) {');self.depth+=1
            if c[1]:self.line('if (!('+self.value(c[1])+')) break;')
            label=self.fresh();self.loops.append(label);self.line('{');self.depth+=1
            for child in c[3]:self.statement(child)
            self.depth-=1;self.line('}');self.line(label+':;');self.loops.pop()
            if c[2]:self.statement(c[2])
            self.depth-=1;self.line('}');self.depth-=1;self.line('}')
        elif k=='continue':self.line('goto '+self.loops[-1]+';')
        elif k=='break':self.line('break;')
        else:raise ValueError('unlowered native statement: '+k)

    def signature(self,n,public=False,internal=False):
        b=n.binding;t=b.typ
        params=', '.join(self.declaration(a,p.c_name) for a,p in zip(t.args[:-1],getattr(n,'parameters',[])))
        if not getattr(n,'parameters',None):params=', '.join(self.ctype(a) for a in t.args[:-1])
        return ('GS_EXPORT ' if public else 'static ' if internal else '')+self.ctype(t.args[-1])+' '+('GS_SYSTEM ' if t.name=='system' else '')+b.c_name+'('+(params or 'void')+')'

    def type_declarations(self):
        forwards=[];definitions=[];done=set()
        for r in self.p.records.values():
            tag='union' if r.node.kind=='native_union' else 'struct'
            forwards.append('typedef '+tag+' '+r.typ.name+' '+r.typ.name+';')
        def record_definition(r):
            if r.typ.name in done:return
            done.add(r.typ.name)
            for t in r.fields.values():
                while t.kind=='fixed_array':t=t.args[0]
                if t.kind=='record':record_definition(self.p.records[t.name])
            fields='\n'.join('  /* '+name+' */ '+self.declaration(t,self.field(name))+';' for name,t in r.fields.items())
            # Empty C records have no standard C11 ABI; native checker rejects them.
            definitions.append(('union' if r.node.kind=='native_union' else 'struct')+' '+r.typ.name+' {\n'+fields+'\n};')
        for r in self.p.records.values():record_definition(r)
        return '\n'.join(forwards)+'\n'+'\n'.join(code for _,code in self.callbacks.values() if code)+'\n'+'\n'.join(definitions)

    def emit(self):
        functions=[];globals_=[];public=[]
        for m in self.p.order:
            for original in m.program.children:
                n=unwrap(original)
                if n.kind in ('func','extern'):
                    exported=original.kind=='export' and m.source==self.p.entry and n.kind=='func'
                    self.ctype(n.binding.typ)
                    functions.append(self.signature(n,exported,not exported and n.kind=='func')+';')
                    if exported:public.append(self.signature(n)+';')
                elif n.kind=='decl' or n.kind=='assign' and n.value==':=':
                    initializer=self.literal(n.children[0] if n.kind=='decl' else n.children[1]) if self.p.library and (n.children[0] if n.kind=='decl' else n.children[1]) else '{0}'
                    globals_.append('static '+self.declaration(n.binding.typ,n.binding.c_name)+' = '+initializer+';')
        for m in self.p.order:
            for original in m.program.children:
                n=unwrap(original)
                if n.kind!='func':continue
                self.line(self.signature(n,original.kind=='export' and m.source==self.p.entry,not(original.kind=='export' and m.source==self.p.entry))+' {');self.depth+=1
                for child in n.children:self.statement(child)
                self.depth-=1;self.line('}')
        if not self.p.library:
            self.line('int main(void) {');self.depth+=1
            for m in self.p.order:
                for original in m.program.children:
                    n=unwrap(original)
                    if n.kind not in ('func','extern','struct','native_union','alias','link','import'):self.statement(n,global_=True)
            self.line('return 0;');self.depth-=1;self.line('}')
        types=self.type_declarations()
        header='#pragma once\n'+PRELUDE+types+'\n#ifdef __cplusplus\nextern "C" {\n#endif\n'+'\n'.join(public)+'\n#ifdef __cplusplus\n}\n#endif\n'
        return PRELUDE+types+'\n'+RUNTIME+'\n'+'\n'.join(self.helpers.values())+'\n'+'\n'.join(globals_+functions+self.lines)+'\n',header
