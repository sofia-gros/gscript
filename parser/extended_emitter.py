"""Direct JS/MJS/TS emission after the native GS checker succeeds."""
import json
import re
from .emitter import Emitter, indent
from .checker import Type, ANY, NULL, VOID, unwrap
from .extended_checker import UNDEFINED, split_type
from .syntax import decode_string


class ExtendedEmitter(Emitter):
    def annotation(self,node,text):
        if text is None:return 'void'
        text=text.strip()
        if text.startswith('[]'):return 'globalThis.Array<'+self.annotation(node,text[2:])+'>'
        if text.startswith('func('):
            depth,end=1,5
            while depth:
                if text[end]=='(':depth+=1
                elif text[end]==')':depth-=1
                end+=1
            args=split_type(text[5:end-1]) if text[5:end-1] else []
            return '('+', '.join('arg'+str(i)+': '+self.annotation(node,a) for i,a in enumerate(args))+') => '+self.annotation(node,text[end:])
        if text.startswith('{'):
            fields=[]
            for part in split_type(text[1:-1],';'):
                if part:
                    key,value=part.split(':',1);fields.append(key+': '+self.annotation(node,value))
            return '{'+'; '.join(fields)+'}'
        aliases={'int':'number','float':'number','float64':'number','bool':'boolean','nil':'null'}
        # Tokenize quoted literals separately so names inside them stay unchanged.
        return re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[A-Za-z_$][\w$]*',lambda m:aliases.get(m.group(),m.group()),text)

    def ts_type(self,typ):
        if typ.kind=='foreign':return self.checker.foreign_names.get(typ,'unknown')
        if typ.kind == 'union': return '(' + ' | '.join(self.ts_type(t) for t in typ.args) + ')'
        if typ.kind == 'literal': return typ.name
        if typ.kind == 'param': return typ.name
        if typ.kind in ('never','unknown','undefined'): return typ.kind
        if typ == NULL: return 'null'
        if typ.kind in ('struct','interface','recursive'):
            name = next((n for n,k in self.checker.type_names.items() if k==typ.name), typ.name.rsplit('::',1)[-1])
            return name + ('<' + ', '.join(self.ts_type(a) for a in typ.args) + '>' if typ.args else '')
        return super().ts_type(typ)

    def default(self,typ):
        if isinstance(typ,Type):
            if typ.kind in ('int','float','number'):return '0'
            if typ.kind=='bool':return 'false'
            if typ.kind=='string':return '\"\"'
            return 'null'+('!' if self.format=='ts' else '')
        return super().default(typ)

    def compile(self,program):
        self.used_names = set(program.identifiers)
        nodes = list(program.children)
        for original in nodes:
            n = unwrap(original)
            if n.kind == 'func' and n.value[4]: self.methods.setdefault(n.value[4][1].split('<')[0],[]).append(n)
        # JavaScript class declarations must follow their local base declaration.
        structs = {unwrap(n).value[0]:n for n in nodes if unwrap(n).kind=='struct'}
        ordered,visiting,done = [],set(),set()
        def add(n):
            key=unwrap(n).value[0]
            if key in done:return
            if key in visiting:self.checker.fail(unwrap(n),'cyclic inheritance')
            visiting.add(key)
            base=getattr(unwrap(n),'base',None)
            root=base.split('<')[0] if base else None
            if root in structs:add(structs[root])
            visiting.remove(key);done.add(key);ordered.append(n)
        for n in structs.values():
            if not getattr(unwrap(n),'deferred_class',False):add(n)
        before=[n for n in nodes if unwrap(n).kind in ('import','interface','alias','enum')]
        functions=[n for n in nodes if unwrap(n).kind=='func']
        rest=[n for n in nodes if unwrap(n).kind not in ('import','interface','alias','enum','struct','func') or unwrap(n).kind=='struct' and getattr(unwrap(n),'deferred_class',False)]
        code='\n\n'.join(filter(None,(self.statement(n) for n in before+ordered+functions+rest)))+'\n'
        return code+'\n'.join(getattr(program,'trailing_comments',[]))+('\n' if getattr(program,'trailing_comments',[]) else '')

    def generic(self,node):
        if self.format!='ts' or not getattr(node,'type_params',[]):return ''
        return '<'+', '.join(name+(' extends '+self.annotation(node,c) if c else '') for name,c in node.type_params)+'>'

    def function(self,node,anonymous=False,method=False):
        name,params,result,asynchronous,receiver=node.value
        with self.checker.parameters(node,receiver[1] if receiver else None):
            parameters=', '.join(self.binding(node,n)+(': '+self.annotation(node,t) if self.format=='ts' else '') for n,t in params)
            generic=self.generic(node)
            ret=self.annotation(node,result) if self.format=='ts' else ''
            if asynchronous and ret:ret='globalThis.Promise<'+ret+'>'
            returns=': '+ret if ret and name!='constructor' else ''
            mods=getattr(node,'modifiers',[])
            prefix=(' '.join(m for m in mods if m!='readonly')+' ' if self.format=='ts' and mods else 'static ' if 'static' in mods else '')
            prefix+= 'async ' if asynchronous else ''
            if receiver:
                alias='const '+self.binding(node,receiver[0])+' = this;'
                previous=getattr(self,'constructor_receiver',None)
                if name=='constructor':self.constructor_receiver=receiver[0]
                if name=='constructor' and node.children and self.checker.is_super_call(node.children[0]):
                    body='{\n'+indent(self.statement(node.children[0])+'\n'+alias+'\n'+'\n'.join(self.statement(n) for n in node.children[1:]))+'\n}'
                else:body=self.block(node.children,alias)
                self.constructor_receiver=previous
            else:body=self.block(node.children)
            if anonymous:return '('+prefix+'('+parameters+')'+returns+' => '+body+')'
            return prefix+('' if method else 'function ')+name+generic+'('+parameters+')'+returns+' '+body

    def expr(self,node):
        if node.kind=='name' and node.value=='super':return 'super'
        code=super().expr(node)
        return '('+code+')' if getattr(node,'parenthesized',False) and node.kind.startswith('optional_') else code

    def expression(self,node):
        k,v,c=node.kind,node.value,node.children
        if k=='name' and v==getattr(self,'constructor_receiver',None):return 'this'
        if k=='binary' and v in ('==','!=') and any(a.kind=='name' and a.value in ('nil','null') for a in c):
            operands=['null' if a.kind=='name' and a.value in ('nil','null') else self.expr(a) for a in c]
            return '('+operands[0]+(' === ' if v=='==' else ' !== ')+operands[1]+')'
        if k=='binary' and v=='??':
            typ=self.checker.types.get(id(c[0]))
            if typ and typ.kind not in ('union','any','external','unknown','null','undefined','param','foreign'):return self.expr(c[0])
        if k=='name' and v in ('nil','null'):
            return 'null' + ('!' if self.format=='ts' and not self.checker.strict_null else '')
        if k=='name' and v=='super':return 'super'
        if k=='optional_member':return self.expr(c[0])+'?.'+v
        if k=='optional_index':return self.expr(c[0])+'?.['+self.expr(c[1])+']'
        if k=='optional_call':return self.expr(c[0])+'?.('+', '.join(self.expr(a) for a in c[1:])+')'
        if k=='call' and c[0].kind=='name' and c[0].value=='super':return 'super('+', '.join(self.expr(a) for a in c[1:])+')'
        if k=='member' and c[0].kind=='name' and c[0].value==getattr(self,'constructor_receiver',None):return 'this.'+v
        if k=='member' and c[0].kind=='name' and c[0].value=='super':return 'super.'+v
        if k=='type_apply':return self.expr(c[0])+('<'+', '.join(self.annotation(node,t) for t in v)+'>' if self.format=='ts' else '')
        if k=='call' and getattr(node,'optional_chain',False):return self.expr(c[0])+'('+', '.join(self.expr(a) for a in c[1:])+')'
        if k=='member' and getattr(node,'optional_chain',False):return self.expr(c[0])+'.'+v
        if k=='index' and getattr(node,'optional_chain',False):return self.expr(c[0])+'['+self.expr(c[1])+']'
        if k=='new':
            types=getattr(node,'type_args',[])
            constructor=getattr(node,'constructor_name',v)
            if self.format=='ts' and self.checker.types.get(id(node))==ANY:constructor='('+constructor+' as any)'
            return 'new '+constructor+('<'+', '.join(self.annotation(node,t) for t in types)+'>' if self.format=='ts' and types else '')+'('+', '.join(self.expr(a) for a in c)+')'
        if k=='composite':
            typ=getattr(node,'instance_type',None)
            args='<'+', '.join(self.ts_type(t) for t in typ.args)+'>' if self.format=='ts' and typ and typ.args else ''
            props=[]
            for item in c:
                props.append('...'+self.expr(item.children[0]) if item.kind=='spread' else '['+json.dumps(decode_string(item.value) if item.value.startswith(('"',"'")) else item.value)+']: '+self.expr(item.children[0]))
            constructor=getattr(node,'constructor_name',v)
            if self.format=='ts' and self.checker.types.get(id(node))==ANY:constructor='('+constructor+' as any)'
            return 'new '+constructor+args+'({'+', '.join(props)+'})'
        if k=='unary' and v=='typeof':return '(typeof '+self.expr(c[0])+')'
        return super().expression(node)

    def simple(self,node):
        if node.kind=='decl' and node.children[0] is None:
            kind,name,typ=node.value
            value=self.default(self.checker.declared_type(node,typ))
            return ('const' if kind=='const' else 'let')+' '+self.binding(node,name)+(': '+self.annotation(node,typ) if self.format=='ts' else '')+' = '+value
        return super().simple(node)

    def statement_code(self,node):
        k,v,c=node.kind,node.value,node.children
        if k=='export':
            if self.format!='ts' and c[0].kind in ('alias','interface'):return '\n'.join(getattr(c[0],'leading_comments',[]))
            code=self.statement(c[0])
            if not code:return ''
            return 'export '+code.replace('\ntype ','\nexport type ') if c[0].kind=='enum' else 'export '+code
        if k=='import' and self.format!='ts' and v[0] and v[0].startswith('{'):
            from .checker import import_names
            parts=[]
            for part in v[0][1:-1].split(','):
                local=part.strip().split(' as ')[-1]
                symbol=self.checker.scopes[0].get(local)
                if symbol and symbol.typ.kind=='type':continue
                if local in getattr(self.checker,'type_only_names',set()):continue
                parts.append(part.strip())
            if not parts:return 'import '+v[1]+';'
            return 'import { '+', '.join(parts)+' } from '+v[1]+';'
        if k=='alias':
            if self.format!='ts':return ''
            with self.checker.parameters(node):return 'type '+v[0]+self.generic(node)+' = '+self.annotation(node,v[1])+';'
        if k=='interface':
            if self.format!='ts':return ''
            with self.checker.parameters(node):
                header='interface '+v[0]+self.generic(node)+(' extends '+', '.join(self.annotation(node,t) for t in v[1]) if v[1] else '')
                parts=[]
                for member in c:
                    if member.kind=='signature':
                        name,params,result=member.value
                        parts.append(name+': ('+', '.join(n+': '+self.annotation(member,t) for n,t in params)+') => '+self.annotation(member,result)+';')
                    else:parts.append(member.value[0]+': '+self.annotation(member,member.value[1])+';')
                return header+' {\n'+indent('\n'.join(parts))+'\n}'
        if k=='enum':
            name=v[0]
            fields=', '.join('['+json.dumps(n)+']: '+json.dumps(value) for n,value in node.enum_values)
            result='const '+name+' = globalThis.Object.freeze({'+fields+'}'+(' as const' if self.format=='ts' else '')+');'
            if self.format=='ts':result+='\ntype '+name+' = typeof '+name+'[keyof typeof '+name+'];'
            return result
        if k=='struct':return self.struct(node)
        if k=='switch':
            parts=[]
            for case in c[1:]:
                labels='\n'.join('case '+self.expr(x)+':' for x in case.value) if case.value else 'default:'
                parts.append(labels+' {\n'+indent('\n'.join(self.statement(n) for n in case.children)+'\nbreak;')+'\n}')
            return 'switch ('+self.expr(c[0])+') {\n'+indent('\n'.join(parts))+'\n}'
        return super().statement_code(node)

    def struct(self,node):
        name,fields=node.value
        target=self.checker.structs[self.checker.type_names[name]]
        with self.checker.parameters(node):
            generic=self.generic(node)
            header='class '+name+generic
            if node.base:header+=' extends '+(self.annotation(node,node.base) if self.format=='ts' else node.base.split('<')[0])
            if self.format=='ts' and node.implements:header+=' implements '+', '.join(self.annotation(node,t) for t in node.implements)
            methods=self.methods.get(name,[])
            custom=next((m for m in methods if m.value[0]=='constructor'),None)
            lines=[]
            for field,typ,default in fields:
                mods=node.field_mods.get(field,[])
                prefix=(' '.join(mods)+' ' if mods else '') if self.format=='ts' else 'static ' if 'static' in mods else ''
                value=self.expr(default) if default else self.default(self.checker.declared_type(node,typ))
                initialize=bool(custom or node.base or 'static' in mods)
                lines.append(prefix+'['+json.dumps(field)+']'+(': '+self.annotation(node,typ) if self.format=='ts' else '')+(' = '+value if initialize else '')+';')
            methods=self.methods.get(name,[])
            custom=next((m for m in methods if m.value[0]=='constructor'),None)
            if not custom and not node.base:
                own=[(f,t,d) for f,t,d in fields if 'static' not in node.field_mods.get(f,[])]
                locals=[self.fresh() for _ in own]
                params=', '.join(json.dumps(f)+': '+local+' = '+(self.expr(d) if d else self.default(self.checker.declared_type(node,t))) for (f,t,d),local in zip(own,locals))
                shape='{'+ '; '.join(json.dumps(f)+'?: '+self.annotation(node,t) for f,t,_ in own)+'}' if self.format=='ts' else ''
                lines.append('constructor({'+params+'}'+(': '+shape if shape else '')+' = {}) {\n'+indent('\n'.join('this['+json.dumps(f)+'] = '+local+';' for (f,_,_),local in zip(own,locals)))+'\n}')
            lines.extend(self.function(m,method=True) for m in methods)
            return header+' {\n'+indent('\n'.join(lines))+'\n}'
