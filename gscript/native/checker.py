"""Native GS type checking. C compilation never substitutes for GS checking."""
from dataclasses import dataclass,field
import hashlib
import math
import re
from pathlib import Path
from parser.syntax import CompileError,decode_string
from parser.checker import Type,unwrap,Checker
from .frontend import parse

VOID=Type('void');BOOL=Type('bool');STRING=Type('string');NIL=Type('nil')
INT=Type('integer','int');FLOAT=Type('float');USIZE=Type('integer','usize')
WIDTHS={'i8':8,'u8':8,'i16':16,'u16':16,'i32':32,'u32':32,'i64':64,'u64':64,'int':64}
SCALARS={n:Type('integer',n) for n in (*WIDTHS,'isize','usize')}
SCALARS.update({'cchar':Type('cchar'),'f32':Type('float','f32'),'f64':FLOAT,'bool':BOOL,'string':STRING,'void':VOID,'float':FLOAT,'float64':FLOAT,'number':FLOAT})
BUILTINS={'print','println','len','panic','address','load','store','offset','sizeof','alignof','offsetof','cast','utf16','cstr','bitOr','bitAnd','bitXor','bitNot','shl','shr','idiv'}|set(SCALARS)


def pointer(typ):return Type('pointer',args=(typ,))
def callback(args,result,abi='C'):return Type('callback',abi,(*args,result))
def split_types(text):
    depth=0;start=0;result=[]
    for i,char in enumerate(text):
        if char in '<([':depth+=1
        elif char in '>)]':depth-=1
        elif char==',' and depth==0:result.append(text[start:i]);start=i+1
    if text[start:]:result.append(text[start:])
    return result


@dataclass(eq=False)
class Binding:
    name:str
    typ:Type
    c_name:str
    constant:bool=False
    node:object=None
    module:object=None
    external:bool=False
    initialized:bool=True

@dataclass
class Module:
    source:Path
    program:object
    prefix:str
    bindings:dict=field(default_factory=dict)
    types:dict=field(default_factory=dict)
    imports:dict=field(default_factory=dict)
    exports:dict=field(default_factory=dict)

@dataclass
class Record:
    typ:Type
    node:object
    module:Module
    fields:dict=field(default_factory=dict)


class NativeProject:
    def __init__(self,entry,root=None,bits=64,library=False):
        self.entry=Path(entry).resolve();self.root=Path(root or self.entry.parent).resolve()
        self.bits=bits;self.library=library;self.modules={};self.order=[];self.records={};self.links=[]
        self.current=None;self.scopes=[];self.result=VOID;self.loop=0;self.counter=0;self.in_function=False

    def fail(self,node,message):
        e=CompileError(message,getattr(node,'line',1));e.filename=str(self.current.source if self.current else self.entry);raise e

    def width(self,t):return self.bits if t.name in ('usize','isize') else WIDTHS[t.name]
    def signed(self,t):return not t.name.startswith('u')
    def limits(self,t):
        bits=self.width(t);return (-(1<<(bits-1)),(1<<(bits-1))-1) if self.signed(t) else (0,(1<<bits)-1)

    def load_modules(self,path,visiting=None):
        path=path.resolve();visiting=set() if visiting is None else visiting
        if path in visiting:raise CompileError('native imports must not form an initialization cycle')
        if path in self.modules:return
        if not path.is_relative_to(self.root):raise CompileError('native module is outside project root: '+str(path))
        if path.suffix not in ('.gs','.gos'):raise CompileError('native target only imports GS modules; use extern for C APIs')
        try:program=parse(path.read_text(encoding='utf-8'))
        except CompileError as e:e.filename=str(path);raise
        m=Module(path,program,'gs_'+hashlib.sha256(str(path).encode()).hexdigest()[:12]+'_')
        self.modules[path]=m;visiting.add(path)
        for original in program.children:
            n=unwrap(original)
            if n.kind=='import':
                spec=decode_string(n.value[1])
                if not spec.startswith(('./','../')):self.current=m;self.fail(n,'native imports must be relative GS paths; npm requires the JS target')
                target=(path.parent/spec).resolve();self.load_modules(target,visiting);m.imports[id(n)]=self.modules[target]
        visiting.remove(path);self.order.append(m)

    def declared(self,node,text,module=None,seen=None):
        m=module or self.current;text=(text or 'void').replace(' ','');seen=set() if seen is None else seen
        if text in SCALARS:return SCALARS[text]
        if (text.startswith('ptr<') or text.startswith('cptr<')) and text.endswith('>'):
            const=text.startswith('cptr<');inner=self.declared(node,text[5 if const else 4:-1],m,seen)
            if inner.kind=='fixed_array':self.fail(node,'pointer-to-array types are not supported; point to the element type')
            return Type('pointer','const' if const else '',(inner,))
        if text.startswith('['):
            found=re.fullmatch(r'\[(\d+)\](.+)',text)
            if not found:self.fail(node,'native arrays require a fixed size, for example [16]u8')
            typ=self.declared(node,found[2],m,seen)
            if typ==VOID:self.fail(node,'array elements cannot be void')
            return Type('fixed_array',found[1],(typ,))
        for prefix,abi in [('winfunc(','system'),('func(','C')]:
            if text.startswith(prefix):
                depth=1;end=len(prefix)
                while end<len(text) and depth:
                    if text[end]=='(':depth+=1
                    elif text[end]==')':depth-=1
                    end+=1
                if depth:self.fail(node,'invalid function pointer type')
                args=[self.declared(node,t,m,seen) for t in split_types(text[len(prefix):end-1])]
                result=self.declared(node,text[end:] or 'void',m,seen)
                if any(t==VOID or t.kind=='fixed_array' for t in args) or result.kind=='fixed_array':self.fail(node,'function ABI cannot pass void or bare arrays by value')
                return callback(args,result,abi)
        if text in m.types:
            value=m.types[text]
            if isinstance(value,Type):return value
            if text in seen:self.fail(node,'cyclic native type alias: '+text)
            return self.declared(value,value.value[1],m,seen|{text})
        self.fail(node,'unsupported or unknown native type: '+text)

    def bind(self,n,name,t,constant=False,external=False,c_name=None):
        if not re.fullmatch(r'[A-Za-z_$][\w$]*',name) or name in ('true','false','nil','null','undefined'):self.fail(n,'invalid native binding: '+name)
        scope=self.scopes[-1]
        if name in scope:self.fail(n,'duplicate declaration: '+name)
        if t.kind=='fixed_array' and (node_init:=getattr(n,'children',[])) and any(x is not None for x in node_init):self.fail(n,'fixed arrays require declared zero-initialized storage; copy through indexed access')
        if t in (VOID,NIL):self.fail(n,'binding requires a concrete non-void type')
        self.counter+=1
        b=Binding(name,t,c_name or self.current.prefix+'v'+str(self.counter),constant,n,self.current,external)
        scope[name]=b;return b

    def lookup(self,n,name):
        for scope in reversed(self.scopes):
            if name in scope:
                b=scope[name]
                if not b.initialized:self.fail(n,'value used before initialization: '+name)
                return b
        self.fail(n,'unknown native identifier: '+name)

    def compatible(self,expected,actual):return expected==actual or actual==NIL and expected.kind in ('pointer','callback') or expected.kind==actual.kind=='pointer' and expected.name=='const' and expected.args==actual.args
    def describe(self,t):
        if t.kind=='pointer':return ('cptr' if t.name=='const' else 'ptr')+'<'+self.describe(t.args[0])+'>'
        if t.kind=='fixed_array':return '['+t.name+']'+self.describe(t.args[0])
        if t.kind=='callback':return ('winfunc' if t.name=='system' else 'func')+'('+','.join(self.describe(a) for a in t.args[:-1])+')'+self.describe(t.args[-1])
        if t.kind=='record':return self.records[t.name].node.value[0]
        return t.name or t.kind

    def expect(self,n,expected,actual):
        if not self.compatible(expected,actual):self.fail(n,f'native type mismatch: expected {self.describe(expected)}, got {self.describe(actual)}; use an explicit conversion')

    def check(self):
        self.load_modules(self.entry)
        for m in self.order:
            self.current=m
            for original in m.program.children:
                n=unwrap(original)
                if n.kind in ('struct','native_union'):
                    if getattr(n,'base',None) or getattr(n,'type_params',[]) or getattr(n,'implements',[]) or any(getattr(n,'field_mods',{}).values()):self.fail(n,'native C-layout records do not support inheritance or generics')
                    name=n.value[0]
                    if name in m.types:self.fail(n,'duplicate type: '+name)
                    t=Type('record',m.prefix+'type_'+name.encode().hex());m.types[name]=t;self.records[t.name]=Record(t,n,m)
                elif n.kind=='alias':
                    if n.value[0] in m.types:self.fail(n,'duplicate type: '+n.value[0])
                    m.types[n.value[0]]=n
            for n in m.program.children:
                if n.kind=='export':
                    node=unwrap(n);name=node.value[1] if node.kind=='decl' else node.value[0]
                    if name in m.exports:self.fail(node,'duplicate export: '+name)
                    m.exports[name]=node
            for original in m.program.children:
                n=unwrap(original)
                if n.kind!='import':continue
                dep=m.imports[id(n)];binding=n.value[0]
                if not binding:continue
                if not binding.startswith('{'):self.fail(n,'native imports currently use named bindings: import { name } from "./module.gs"')
                for part in binding[1:-1].split(','):
                    names=part.strip().split(' as ');remote,local=names[0],names[-1]
                    if remote not in dep.exports:self.fail(n,'module has no native export: '+remote)
                    if remote in dep.types:
                        if local in m.types:self.fail(n,'duplicate imported type: '+local)
                        m.types[local]=self.declared(dep.exports[remote],remote,dep)
                    else:
                        if local in m.bindings:self.fail(n,'duplicate import: '+local)
                        original=dep.bindings[remote]
                        m.bindings[local]=Binding(local,original.typ,original.c_name,True,n,dep,original.external)
            for t in list(m.types):self.declared(NodeProxy(),t,m)
            for record in [r for r in self.records.values() if r.module is m]:
                for field_name,text,default in record.node.value[1]:
                    if field_name in record.fields:self.fail(record.node,'duplicate native field: '+field_name)
                    if default is not None:self.fail(record.node,'native record defaults use zero initialization; put values in a constructor function')
                    typ=self.declared(record.node,text)
                    if typ==VOID:self.fail(record.node,'record fields cannot be void')
                    record.fields[field_name]=typ
                if not record.fields:self.fail(record.node,'native C-layout records must have at least one field; use ptr<void> for opaque handles')
            self.scopes=[m.bindings]
            for original in m.program.children:
                n=unwrap(original)
                if n.kind in ('func','extern'):
                    name,params,result,async_,receiver=n.value
                    if async_ or receiver or getattr(n,'type_params',[]):self.fail(n,'native functions currently require static signatures without async, receivers or generics')
                    abi=getattr(n,'abi','C');typ=callback([self.declared(n,t) for _,t in params],self.declared(n,result),abi)
                    if any(t==VOID or t.kind=='fixed_array' for t in typ.args[:-1]) or typ.args[-1].kind=='fixed_array':self.fail(n,'native functions cannot pass void or bare arrays by value')
                    external=n.kind=='extern'
                    if external and any(self.contains_string(t) for t in typ.args):self.fail(n,'extern signatures cannot use GS string; use ptr<u8> or ptr<u16>')
                    public=original.kind=='export' and m.source==self.entry
                    if public and (not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',name) or name=='main'):self.fail(n,'public native ABI requires a C identifier other than main')
                    if (external or public) and not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',name):self.fail(n,'C ABI symbol requires a C identifier')
                    if (external or public) and name in 'auto break case char const continue default do double else enum extern float for goto if inline int long register restrict return short signed sizeof static struct switch typedef union unsigned void volatile while'.split():self.fail(n,'C ABI symbol is a reserved C keyword')
                    c_name=name if external or public else m.prefix+'fn_'+name.encode().hex()
                    n.binding=self.bind(n,name,typ,True,external,c_name)
                elif n.kind=='link':
                    if not re.fullmatch(r'[A-Za-z0-9_.+-]+',n.value):self.fail(n,'invalid link library name')
                    if n.value not in self.links:self.links.append(n.value)
            for original in m.program.children:
                n=unwrap(original)
                if n.kind in ('decl','assign'):
                    if self.library and n.kind=='assign' and n.value!=':=':self.fail(n,'native libraries cannot execute top-level assignments')
                    self.statement(n,global_=True)
                    if original.kind=='export' and n.kind=='assign':self.fail(n,'export requires an explicit declaration')
            for original in m.program.children:
                n=unwrap(original)
                if n.kind=='func':self.check_function(n)
                elif n.kind not in ('extern','link','import','struct','native_union','alias','decl','assign'):
                    if self.library:self.fail(n,'native libraries cannot execute top-level statements')
                    self.statement(n)
        self.check_records()
        self.check_c_symbols()
        return self

    def contains_string(self,t,seen=None):
        seen=set() if seen is None else seen
        if t in seen:return False
        seen=seen|{t}
        if t==STRING:return True
        if t.kind=='record':return any(self.contains_string(v,seen) for v in self.records[t.name].fields.values())
        return any(self.contains_string(a,seen) for a in t.args) if t.kind=='callback' else False

    def check_records(self):
        def visit(t,seen):
            if t.kind=='fixed_array':return visit(t.args[0],seen)
            if t.kind!='record':return
            if t.name in seen:self.fail(self.records[t.name].node,'recursive records need a ptr<T> field')
            for field in self.records[t.name].fields.values():visit(field,seen|{t.name})
        for r in self.records.values():visit(r.typ,set())

    def check_c_symbols(self):
        names={}
        for m in self.order:
            self.current=m
            for b in m.bindings.values():
                if b.module is not m:continue
                old=names.get(b.c_name)
                if old and old is not b and (not old.external or not b.external or old.typ!=b.typ):self.fail(b.node,'incompatible C symbol declarations: '+b.c_name)
                names[b.c_name]=b

    def check_function(self,n):
        self.scopes.append({});old=self.result;self.in_function=True;self.result=n.binding.typ.args[-1]
        n.parameters=[]
        for (name,_),t in zip(n.value[1],n.binding.typ.args[:-1]):n.parameters.append(self.bind(n,name,t))
        for child in n.children:self.statement(child)
        if self.result!=VOID and not self.terminates(n.children):self.fail(n,'missing return on some native function paths')
        self.result=old;self.in_function=False;self.scopes.pop()

    def exits(self,nodes):return Checker.exits(self,nodes)

    def terminates(self,nodes):return 'normal' not in self.exits(nodes)

    def block(self,nodes):
        self.scopes.append({})
        for n in nodes:self.statement(n)
        self.scopes.pop()

    def statement(self,n,global_=False):
        k,v,c=n.kind,n.value,n.children
        if k=='decl':
            initial=self.expr(c[0]) if c[0] else None;t=self.declared(n,v[2]) if v[2] else initial
            if initial:self.expect(n,t,initial)
            if t is None:self.fail(n,'native declaration needs a type or initializer')
            n.binding=self.bind(n,v[1],t,v[0]=='const')
        elif k=='assign':
            actual=self.expr(c[1])
            if v==':=':n.binding=self.bind(n,c[0].value,actual);c[0].binding=n.binding;c[0].native_type=actual
            else:
                target=self.lvalue(c[0]);self.expect(n,target,actual)
                if v not in ('=','+=','-='):self.fail(n,'unsupported native assignment')
                if v!='=' and target.kind not in ('integer','float'):self.fail(n,'compound assignment requires a number')
        elif k=='expr':self.expr(c[0])
        elif k=='return':
            if not self.in_function:self.fail(n,'native return must be inside a function')
            self.expect(n,self.result,self.expr(c[0]) if c else VOID)
        elif k=='update':
            if self.lvalue(c[0]).kind not in ('integer','float'):self.fail(n,'update requires a number')
        elif k=='if':
            self.expect(n,BOOL,self.expr(c[0]));self.block(c[1])
            if c[2] is not None:self.block(c[2])
        elif k=='for':
            self.scopes.append({});self.loop+=1
            if c[0]:self.statement(c[0])
            if c[1]:self.expect(n,BOOL,self.expr(c[1]))
            if c[2]:self.statement(c[2])
            self.block(c[3]);self.loop-=1;self.scopes.pop()
        elif k in ('break','continue'):
            if not self.loop:self.fail(n,k+' is only allowed inside a native loop')
        else:self.fail(n,'unsupported native statement: '+k)
        if global_ and self.library and c and any(x is not None for x in c):
            init=c[-1] if k=='assign' else c[0]
            if init is not None and not self.constant_expr(init):self.fail(n,'native library globals require constant initializers')

    def constant_expr(self,n):return n.kind in ('number','string') or n.kind=='name' and n.value in ('true','false','nil') or n.kind=='unary' and n.value in ('-','+') and self.constant_expr(n.children[0]) or n.kind=='call' and getattr(n,'native_builtin',None)=='cast' and self.constant_expr(n.children[1])

    def lvalue(self,n):
        t=self.expr(n)
        if n.kind not in ('name','member','index'):self.fail(n,'native pointer access requires an addressable value')
        base=n;indirect=False
        while base.kind in ('member','index'):
            if base.children[0].native_type.kind=='pointer' and base.children[0].native_type.name=='const':self.fail(n,'cannot modify storage through a const pointer')
            if base.children[0].native_type.kind=='pointer':indirect=True
            base=base.children[0]
        if base.kind not in ('name','member','index') and getattr(base,'native_type',VOID).kind!='pointer':self.fail(n,'native record temporaries are not addressable')
        if base.kind=='name' and getattr(base,'binding',None) and base.binding.constant and not indirect:self.fail(n,'cannot modify or take a mutable pointer to a constant')
        if n.kind in ('member','index') and n.children[0].native_type.kind=='pointer' and n.children[0].native_type.name=='const':self.fail(n,'cannot modify storage through a const pointer')
        return t

    def expr(self,n):
        k,v,c=n.kind,n.value,n.children
        if k=='number':
            t=FLOAT if any(ch in v for ch in '.eE') else INT
            if t==FLOAT and not math.isfinite(float(v)):self.fail(n,'native floating literal is out of range')
            if t==INT and not self.limits(INT)[0]<=int(v)<=self.limits(INT)[1]:self.fail(n,'integer literal exceeds int64; use an explicit fixed-width conversion')
        elif k=='string':t=STRING
        elif k=='name':
            if v in ('true','false'):t=BOOL
            elif v=='nil':t=NIL
            else:n.binding=self.lookup(n,v);t=n.binding.typ
        elif k=='unary':
            if v=='-' and c[0].kind=='number' and c[0].value==str(1<<63):c[0].native_type=INT;t=INT
            else:
                t=self.expr(c[0])
                if v=='!':self.expect(n,BOOL,t);t=BOOL
                elif v not in ('-','+') or t.kind not in ('integer','float'):self.fail(n,'unsupported native unary operator: '+v)
        elif k=='binary':
            left,right=self.expr(c[0]),self.expr(c[1])
            if v in ('&&','||'):self.expect(n,BOOL,left);self.expect(n,BOOL,right);t=BOOL
            else:
                if not self.compatible(left,right) and not self.compatible(right,left):self.fail(n,'native operands must have matching types')
                if v in ('==','!='):
                    if left.kind in ('record','fixed_array') or left==VOID:self.fail(n,'records and arrays do not have implicit native equality')
                    t=BOOL
                elif v in ('<','<=','>','>='):
                    if left.kind not in ('integer','float'):self.fail(n,'native ordering requires numbers')
                    t=BOOL
                else:
                    if left.kind not in ('integer','float') or v not in ('+','-','*','/','%'):self.fail(n,'unsupported native arithmetic')
                    if v=='%' and left.kind!='integer':self.fail(n,'native remainder requires integers')
                    t=FLOAT if v=='/' and left.kind=='integer' else left
        elif k=='member':
            base=self.expr(c[0]);record=base.args[0] if base.kind=='pointer' else base
            if record.kind!='record' or v not in self.records[record.name].fields:self.fail(n,'unknown native record field: '+v)
            t=self.records[record.name].fields[v]
        elif k=='index':
            base=self.expr(c[0]);index=self.expr(c[1])
            if base.kind not in ('fixed_array','pointer') or base.args[0]==VOID or index.kind!='integer':self.fail(n,'native indexing requires an integer and an array or typed pointer')
            if base.kind=='fixed_array' and c[1].kind=='number' and not 0<=int(c[1].value)<int(base.name):self.fail(n,'fixed array index out of bounds')
            t=base.args[0]
        elif k=='composite':
            t=self.declared(n,v)
            if t.kind!='record':self.fail(n,'native composite requires a C-layout record')
            fields=self.records[t.name].fields;seen=set()
            for item in c:
                if item.kind!='property' or item.value not in fields or item.value in seen:self.fail(item,'invalid or duplicate native record field')
                if fields[item.value].kind=='fixed_array':self.fail(item,'initialize native fixed-array fields through indexed access')
                seen.add(item.value);self.expect(item,fields[item.value],self.expr(item.children[0]))
        elif k=='call':
            callee=c[0];applied=callee.value if callee.kind=='type_apply' else []
            root=callee.children[0] if applied else callee
            if root.kind=='name' and root.value in BUILTINS and not any(root.value in s for s in self.scopes):t=self.builtin(n,root.value,c[1:],applied)
            else:
                if applied:self.fail(n,'native generic calls are reserved for cast/sizeof/alignof/offsetof')
                fn=self.expr(callee)
                if fn.kind!='callback':self.fail(n,'native value is not callable')
                if len(c)-1!=len(fn.args)-1:self.fail(n,'incorrect native argument count')
                for node,expected in zip(c[1:],fn.args[:-1]):self.expect(node,expected,self.expr(node))
                t=fn.args[-1]
        else:self.fail(n,'unsupported native expression: '+k)
        n.native_type=t;return t

    def builtin(self,n,name,args,types):
        n.native_builtin=name
        if name=='panic':n.builtin_call='panic'
        counts={'len':1,'panic':1,'address':1,'load':1,'store':2,'offset':2,'sizeof':0,'alignof':0,'offsetof':1,'cast':1,'utf16':1,'cstr':1,'bitOr':2,'bitAnd':2,'bitXor':2,'bitNot':1,'shl':2,'shr':2,'idiv':2}
        if name in SCALARS:counts[name]=1
        if name not in ('print','println') and len(args)!=counts[name]:self.fail(n,'incorrect argument count for '+name)
        if name in ('sizeof','alignof','offsetof','cast'):
            if len(types)!=1:self.fail(n,name+' requires one type argument')
            target=self.declared(n,types[0]);n.native_target=target
            if target in (VOID,NIL):self.fail(n,'invalid native type argument')
            if name in ('sizeof','alignof'):return USIZE
            if name=='offsetof':
                if target.kind!='record' or args[0].kind!='string' or decode_string(args[0].value) not in self.records[target.name].fields:self.fail(n,'offsetof requires a record and a literal field name')
                n.native_field=decode_string(args[0].value);return USIZE
        elif types:self.fail(n,name+' does not accept type arguments')
        if name=='string':
            actual=self.expr(args[0])
            if actual!=STRING and not (actual.kind=='pointer' and actual.args[0] in (SCALARS['cchar'],SCALARS['u8'])):self.fail(n,'native string conversion requires a C string pointer or string')
            n.native_builtin='string_view';return STRING
        if name in SCALARS or name=='cast':
            target=SCALARS[name] if name in SCALARS else n.native_target
            if target.kind=='integer' and args[0].kind=='number' and args[0].value.isdigit():
                if not self.limits(target)[0]<=int(args[0].value)<=self.limits(target)[1]:self.fail(n,'constant conversion is out of range')
                args[0].native_type=target;actual=target
            else:actual=self.expr(args[0])
            if target.kind in ('integer','float') and actual.kind in ('integer','float'):pass
            elif target.kind in ('pointer','callback') and actual.kind in ('pointer','callback','nil'):pass
            elif target.kind=='pointer' and actual.kind=='integer':
                if self.width(actual)!=self.bits:self.fail(n,'address conversion requires a pointer-sized integer')
            elif target.kind=='integer' and actual.kind=='pointer':
                if self.width(target)!=self.bits:self.fail(n,'pointer conversion requires a pointer-sized integer')
            else:self.fail(n,'invalid native conversion')
            n.native_builtin='cast';n.native_target=target;return target
        if name=='address':return pointer(self.lvalue(args[0]))
        values=[self.expr(a) for a in args]
        if name in ('print','println'):
            if any(t.kind not in ('integer','float','bool','string','pointer') for t in values):self.fail(n,'native print accepts scalar values and strings')
            return VOID
        if name=='panic':self.expect(n,STRING,values[0]);return VOID
        if name=='len':
            if values[0].kind not in ('string','fixed_array'):self.fail(n,'native len requires a string or fixed array')
            return INT
        if name in ('utf16','cstr'):
            self.expect(n,STRING,values[0])
            if name=='utf16' and args[0].kind!='string':self.fail(n,'utf16 currently requires a literal; dynamic buffers belong in a library')
            return Type('pointer','const',(SCALARS['u16' if name=='utf16' else 'cchar'],))
        if name in ('load','store','offset'):
            t=values[0]
            if t.kind!='pointer' or t.args[0]==VOID:self.fail(n,name+' requires a typed non-void pointer')
            if name=='store':
                if t.name=='const':self.fail(n,'cannot store through a const pointer')
                if t.args[0].kind=='fixed_array':self.fail(n,'store does not copy fixed arrays')
                self.expect(n,t.args[0],values[1]);return VOID
            if name=='offset':
                if values[1].kind!='integer':self.fail(n,'pointer offset requires an integer')
                return t
            return t.args[0]
        if name in ('bitOr','bitAnd','bitXor','bitNot','shl','shr','idiv'):
            if values[0].kind!='integer':self.fail(n,name+' requires integers')
            if len(values)>1:
                if name in ('shl','shr'):
                    if values[1].kind!='integer':self.fail(n,'shift count requires an integer')
                else:self.expect(n,values[0],values[1])
            return values[0]
        self.fail(n,'unknown native builtin: '+name)


class NodeProxy:
    line=1
