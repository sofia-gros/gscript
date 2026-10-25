"""LSP operations over the checked native AST; never invokes a C compiler."""
from pathlib import Path
import re
from parser.syntax import tokenize,decode_string
from gscript.analysis import walk
from gscript.lsp_features import range_for,codepoint_position,text_offset
from .checker import NativeProject,BUILTINS,SCALARS

KEYWORDS='extern system link func type struct union var const return if else for break continue export import ptr cptr winfunc'.split()+sorted(SCALARS)


def detect(options,text):
    if options.backend=='native':return True
    try:tokens=tokenize(text)
    except ValueError:return False
    return any(t.text=='extern' and i+1<len(tokens) and tokens[i+1].kind=='string' and decode_string(tokens[i+1].text) in ('C','system') for i,t in enumerate(tokens))


def check(entry,options,sources):
    target=options.native_target or '';bits=32 if target.split('-')[0] in ('x86','i386','i486','i586','i686','arm','thumb') else __import__('struct').calcsize('P')*8
    return NativeProject(entry,options.root,bits=bits,sources=sources,positions=True)


def span(binding):
    n=binding.node
    if getattr(binding,'depth',0)==0 and n.kind in ('func','extern'):return getattr(n,'declaration_span',None)
    return getattr(n,'binding_spans',{}).get(binding.name) or (getattr(n,'declaration_span',None) if n.kind in ('func','extern') else getattr(n.children[0],'name_span',None) if n.kind=='assign' else None)


def identity(binding):
    if binding.module and binding.name in binding.module.bindings:
        original=binding.module.bindings[binding.name]
        if original.c_name==binding.c_name:return original
    if binding.module:
        return next((b for b in binding.module.bindings.values() if b.c_name==binding.c_name),binding)
    return binding


def occurrences(project):
    for module in project.modules.values():
        for node in walk(module.program):
            b=getattr(node,'binding',None)
            if node.kind=='name' and b and getattr(node,'name_span',None):yield module,node.name_span,identity(b),False,node
        for b in project.bindings:
            if b.module is module and span(b):yield module,span(b),identity(b),True,b.node
        for n in module.program.children:
            if n.kind!='import' or not n.value[0] or not n.value[0].startswith('{'):continue
            dep=module.imports.get(id(n))
            if not dep:continue
            for part in n.value[0][1:-1].split(','):
                names=part.strip().split(' as ');remote,local=names[0],names[-1]
                b=dep.bindings.get(remote)
                if not b:continue
                matches=[t for t in module.program.tokens if t.kind=='name' and t.text==remote and getattr(n,'span',(n.line,1,n.line,10000))[:2]<=(t.line,t.column)<=getattr(n,'span',(n.line,1,n.line,10000))[2:]]
                if matches:
                    t=matches[0];yield module,(t.line,t.column,t.line,t.column+len(t.text)),identity(b),False,n


def handle(server,method,params,project):
    from gscript.lsp import path_from_uri
    uri=params['textDocument']['uri'];path=path_from_uri(uri);doc=server.documents[uri];text=doc['text'];module=project.modules.get(path)
    position=params.get('position',{'line':0,'character':0});point=codepoint_position(text,position)
    all_occ=list(occurrences(project))
    selected=next((o for o in all_occ if o[0].source==path and o[1][:2]<=point<o[1][2:]),None)
    if method=='textDocument/formatting':
        from gscript.formatter import format_source
        from .frontend import parse
        updated=format_source(text,parse=parse)
        return [] if updated==text else [{'range':{'start':{'line':0,'character':0},'end':{'line':text.count('\n'),'character':len(text.rsplit('\n',1)[-1].encode('utf-16-le'))//2}},'newText':updated}]
    if method=='textDocument/hover':
        if not selected:return None
        return {'contents':{'kind':'plaintext','value':selected[2].name+': '+project.describe(selected[2].typ)},'range':range_for(text,selected[1])}
    if method=='textDocument/completion':
        items={name:{'label':name,'kind':14} for name in KEYWORDS}
        items.update({name:{'label':name,'kind':3} for name in BUILTINS})
        if module:
            for b in project.bindings:
                owner=getattr(b.node,'span',None)
                if b.module is module and (not b.depth or owner and owner[:2]<=point<=owner[2:]):items[b.name]={'label':b.name,'kind':3 if b.typ.kind=='callback' else 6,'detail':project.describe(b.typ)}
            prefix=text[:text_offset(text,*point)]
            match=re.search(r'([A-Za-z_$][\w$]*)\.\w*$',prefix)
            if match:
                binding=module.bindings.get(match[1]) or next((b for b in reversed(project.bindings) if b.module is module and b.name==match[1]),None)
                if binding:
                    typ=binding.typ.args[0] if binding.typ.kind=='pointer' else binding.typ
                    if typ.kind=='record':items={name:{'label':name,'kind':10,'detail':project.describe(t)} for name,t in project.records[typ.name].fields.items()}
        return {'isIncomplete':False,'items':list(items.values())}
    if method=='textDocument/documentSymbol':
        result=[]
        for b in project.bindings:
            if b.module is module and not b.depth and span(b):
                r=range_for(text,span(b));result.append({'name':b.name,'kind':12 if b.typ.kind=='callback' else 13,'range':r,'selectionRange':r})
        return result
    if method=='textDocument/signatureHelp':
        if not module:return None
        calls=[n for n in walk(module.program) if n.kind=='call' and getattr(n,'span',None) and n.span[:2]<=point<=n.span[2:]]
        if not calls:return None
        call=max(calls,key=lambda n:n.span[:2]);typ=getattr(call.children[0],'native_type',None)
        if not typ or typ.kind!='callback':return None
        labels=['arg'+str(i)+': '+project.describe(t) for i,t in enumerate(typ.args[:-1])]
        return {'signatures':[{'label':project.describe(typ),'parameters':[{'label':p} for p in labels]}],'activeSignature':0,'activeParameter':0}
    if not selected:return [] if method in ('textDocument/definition','textDocument/references') else None
    binding=selected[2]
    if method=='textDocument/definition':
        target=span(binding)
        if not target:return []
        return [{'uri':binding.module.source.as_uri(),'range':range_for(binding.module.program.source_text,target)}]
    if method=='textDocument/references':
        include=params.get('context',{}).get('includeDeclaration',False);result={}
        for m,s,b,decl,_ in all_occ:
            if b is binding and (include or not decl):result[(m.source,s)]={'uri':m.source.as_uri(),'range':range_for(m.program.source_text,s)}
        return list(result.values())
    if method=='textDocument/prepareRename':
        if binding.external:return None
        return {'range':range_for(text,selected[1]),'placeholder':binding.name}
    if method=='textDocument/rename':
        if binding.external:raise ValueError('external C ABI symbols cannot be renamed')
        name=params['newName']
        if not re.fullmatch(r'[A-Za-z_$][\w$]*',name) or name in KEYWORDS:raise ValueError('invalid native identifier')
        edits={};sources={m.source:m.program.source_text for m in project.modules.values()}
        for m,s,b,_,_ in all_occ:
            if b is binding:edits.setdefault(m.source,{})[s]=name
        for p,replacements in edits.items():
            source=sources[p]
            for s,new in sorted(replacements.items(),reverse=True):source=source[:text_offset(source,*s[:2])]+new+source[text_offset(source,*s[2:]):]
            sources[p]=source
        NativeProject(project.entry,project.root,project.bits,sources=sources,positions=True).check()
        return {'documentChanges':[{'textDocument':{'uri':p.as_uri(),'version':next((d['version'] for u,d in server.documents.items() if path_from_uri(u)==p),None)},'edits':[{'range':range_for(project.modules[p].program.source_text,s),'newText':new} for s,new in sorted(replacements.items())]} for p,replacements in edits.items()]}
    return None
