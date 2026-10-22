"""Emit ambient public APIs from GS's checked AST, with distinct numeric brands."""
from contextlib import nullcontext
import json
from pathlib import Path
import re

from parser.checker import Type, unwrap
from parser.extended_emitter import ExtendedEmitter
from .import_rewrite import rewrite_imports


class DeclarationEmitter(ExtendedEmitter):
    def __init__(self,module):
        super().__init__('ts',module.checker)
        self.module=module
        identifiers=module.program.identifiers
        self.int_name='GSInt'
        while self.int_name in identifiers:self.int_name='_'+self.int_name
        self.float_name='GSFloat'
        while self.float_name in identifiers:self.float_name='_'+self.float_name
        for original in module.program.children:
            node=unwrap(original)
            if node.kind=='func' and node.value[4]:self.methods.setdefault(node.value[4][1].split('<')[0],[]).append(node)

    def context(self,node,receiver=None):
        return self.checker.parameters(node,receiver) if hasattr(self.checker,'parameters') else nullcontext()

    def annotation(self,node,text):
        if text is None:return 'void'
        names={'int':self.int_name,'float':self.float_name,'float64':self.float_name}
        text=re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[A-Za-z_$][\w$]*',lambda m:names.get(m.group(),m.group()),text)
        return super().annotation(node,text)

    def ts_type(self,typ):
        if typ.kind=='int':return self.int_name
        if typ.kind=='float':return self.float_name
        if typ.kind=='literal' and typ.args[0].kind in ('int','float'):return '('+self.ts_type(typ.args[0])+' & '+typ.name+')'
        if typ.kind=='undefined':return 'undefined'
        if typ.kind=='tuple':return '['+', '.join(self.ts_type(a) for a in typ.args)+']'
        if typ.kind=='iterator':return 'IterableIterator<'+self.ts_type(typ.args[0])+'>'
        if typ.kind=='foreign':
            existing=self.checker.foreign_names.get(typ)
            if existing:return self.annotation(self.module.program,existing)
            reader=self.checker.declarations
            text=reader.query(action='type_text',id=int(typ.name),file=str(self.module.source)+'.declarations.mts')
            if typ.args:
                params=reader.describe(typ).get('parameters',[])
                names={reader.typ(p).name.split('@')[0]:self.ts_type(t) for p,t in zip(params,typ.args)}
                text=re.sub(r'\b[A-Za-z_$][\w$]*\b',lambda m:names.get(m.group(),m.group()),text)
            return text
        return super().ts_type(typ)

    def signature(self,node,method=False):
        name,params,result,async_,receiver=node.value
        with self.context(node,receiver[1] if receiver else None):
            generic=self.generic(node)
            args=', '.join(n+': '+self.annotation(node,t) for n,t in params)
            if name=='constructor':return 'constructor('+args+');'
            returns=self.annotation(node,result)
            if async_:returns='Promise<'+returns+'>'
            mods=' '.join(m for m in getattr(node,'modifiers',[]) if m!='override')
            return (mods+' ' if mods else '')+('' if method else 'declare function ')+name+generic+'('+args+'): '+returns+';'

    def struct_declaration(self,node):
        name,fields=node.value
        with self.context(node):
            header='declare class '+name+self.generic(node)
            base=getattr(node,'base',None)
            if base:header+=' extends '+self.annotation(node,base)
            interfaces=getattr(node,'implements',[])
            if interfaces:header+=' implements '+', '.join(self.annotation(node,t) for t in interfaces)
            lines=[];mods=getattr(node,'field_mods',{})
            for field,typ,default in fields:
                prefix=' '.join(mods.get(field,[]))
                lines.append((prefix+' ' if prefix else '')+json.dumps(field)+': '+self.annotation(node,typ)+';')
            methods=self.methods.get(name,[])
            custom=next((m for m in methods if m.value[0]=='constructor'),None)
            if not custom and not base:
                own=[(f,t) for f,t,_ in fields if 'static' not in mods.get(f,[])]
                required=[]
                for field,typ,default in fields:
                    if 'static' in mods.get(field,[]):continue
                    resolved=self.checker.declared_type(node,typ)
                    if default is None and (resolved.kind=='param' or getattr(self.checker,'strict_null',False) and resolved.kind not in ('int','float','number','string','bool','any','unknown') and not self.checker.compatible(resolved,Type('null'))):required.append(field)
                shape='{ '+ '; '.join(json.dumps(f)+('' if f in required else '?')+': '+self.annotation(node,t) for f,t in own)+' }'
                lines.append('constructor(values'+('' if required else '?')+': '+shape+');')
            lines.extend(self.signature(method,True) for method in methods)
            return header+' {\n'+ '\n'.join('  '+line for line in lines)+'\n}'

    def emit(self,format):
        parts=[f'export type {self.int_name} = number & {{ readonly __gscriptNumeric__: "int" }};',f'export type {self.float_name} = number & {{ readonly __gscriptNumeric__: "float" }};']
        for original in self.module.program.children:
            node=unwrap(original);exported=original.kind=='export';prefix='export ' if exported else ''
            if node.kind=='import':
                code=super().statement_code(node)
                code=rewrite_imports(code,lambda s:s[:-3]+('.mjs' if format=='mjs' else '.js') if s.endswith('.gs') else s[:-4]+('.mjs' if format=='mjs' else '.js') if s.endswith('.gos') else s)
            elif node.kind=='func':
                if node.value[4]:continue
                code=prefix+self.signature(node)
            elif node.kind=='struct':code=prefix+self.struct_declaration(node)
            elif node.kind in ('interface','alias'):code=prefix+super().statement_code(node)
            elif node.kind=='enum':
                name=node.value[0]
                fields=[]
                for key,value in node.enum_values:
                    typ=json.dumps(value,ensure_ascii=False)
                    if isinstance(value,int):typ=self.int_name+' & '+typ
                    fields.append('readonly '+json.dumps(key)+': '+typ+';')
                code=prefix+'declare const '+name+': { '+' '.join(fields)+' };\n'+prefix+'type '+name+' = typeof '+name+'[keyof typeof '+name+'];'
            elif node.kind=='decl':
                name=node.value[1];symbol=self.checker.scopes[0][name]
                typ=self.annotation(node,node.value[2]) if node.value[2] else self.ts_type(symbol.typ)
                code=prefix+'declare '+('const' if node.value[0]=='const' else 'let')+' '+name+': '+typ+';'
            elif node.kind=='assign' and node.value==':=':
                name=node.children[0].value
                code='declare let '+name+': '+self.ts_type(self.checker.scopes[0][name].typ)+';'
            elif node.kind=='default':
                typ=self.checker.types[id(node.children[0])]
                code='declare const __default: '+self.ts_type(typ)+';\nexport default __default;'
            else:continue
            parts.append(code)
        parts.append('export {};')
        return '\n\n'.join(parts)+'\n'


def declarations(project,settings):
    result={}
    try:
        for module in project.modules.values():
            target=settings.out_dir/module.source.relative_to(project.root).with_suffix('.d.mts' if settings.format=='mjs' else '.d.ts')
            if settings.output and module.source==project.entry:target=Path(settings.output).resolve().with_suffix('.d.mts' if settings.format=='mjs' else '.d.ts')
            result[target]=DeclarationEmitter(module).emit(settings.format)
        return result
    finally:
        if getattr(project,'declarations',None):project.declarations.close()
