"""Symbol-based LSP operations over the native compiler's AST and scopes."""
from dataclasses import dataclass
from pathlib import Path
import json
import os
import re

from parser.syntax import decode_string,Node
from parser.checker import RESERVED,REGISTRY,unwrap,Type,STRING,INT,ANY
from .analysis import walk,root_symbol


def point(text,line,column):
    lines=text.split('\n');row=max(0,min(line-1,len(lines)-1))
    return {'line':row,'character':len(lines[row][:max(0,column-1)].encode('utf-16-le'))//2}


def range_for(text,span):return {'start':point(text,span[0],span[1]),'end':point(text,span[2],span[3])}


def inside(span,row,column):return span[:2]<=(row,column)<=span[2:]


def codepoint_position(text,position):
    lines=text.split('\n');row=min(position['line'],len(lines)-1);units=position['character']
    prefix=lines[row].encode('utf-16-le')[:units*2].decode('utf-16-le',errors='ignore')
    return row+1,len(prefix)+1


def symbol_key(symbol,alias=True):
    if alias and getattr(symbol,'target',None) is not None and getattr(symbol,'original_name','')!=getattr(root_symbol(symbol),'original_name',''):
        target=symbol
    else:target=root_symbol(symbol)
    span=getattr(target,'definition_span',None)
    if not span:return None
    return ('symbol',target.module_id,span,target.original_name)


def text_offset(text,line,column):
    lines=text.splitlines(keepends=True)
    return sum(map(len,lines[:line-1]))+column-1


@dataclass
class Occurrence:
    key: tuple
    uri: str
    span: tuple
    name: str
    declaration: bool=False
    symbol: object=None
    node: object=None
    destination: object=None
    shorthand: str | None=None
    quoted: bool=False


class Index:
    def __init__(self,project):
        self.project=project;self.occurrences=[];self.definitions={};self.parents={}
        self.text={m.source.as_uri():m.source_text for m in project.modules.values()}
        self.structs=next(iter(project.modules.values())).checker.structs
        self.member_families()
        for module in project.modules.values():self.module_index(module)
        for occurrence in self.occurrences:
            if occurrence.declaration:self.definitions.setdefault(occurrence.key,[]).append(occurrence)

    def canonical(self,key):
        parent=self.parents.get(key,key)
        if parent!=key:self.parents[key]=self.canonical(parent)
        return self.parents.get(key,key)

    def join(self,left,right):
        left,right=self.canonical(left),self.canonical(right)
        if left!=right:self.parents[max(left,right)]=min(left,right)

    def own_members(self,target,static=False):
        return target.statics if static and hasattr(target,'statics') else {} if static else {**target.fields,**target.methods}

    def member_keys(self,typ,static=False,seen=None):
        if typ.kind not in ('struct','interface','constructor','enum'):return {}
        seen=set() if seen is None else set(seen)
        if typ.name in seen:return {}
        seen.add(typ.name);target=self.structs[typ.name];result={}
        bases=getattr(target,'bases',[]) or ([target.base] if getattr(target,'base',None) else [])
        for base in bases:result.update(self.member_keys(base,static,seen))
        result.update({name:('member',typ.name,static,name) for name in self.own_members(target,static)})
        return result

    def member_families(self):
        for name,target in self.structs.items():
            if not getattr(target,'node',None):continue
            bases=list(getattr(target,'bases',[])) or ([target.base] if getattr(target,'base',None) else [])
            for text in getattr(target.node,'implements',[]):
                root=text.split('<')[0]
                key=target.checker.type_names.get(root)
                if key:bases.append(Type('interface',key))
            for static in (False,True):
                own=self.member_keys(Type('struct',name),static)
                inherited={}
                for base in bases:
                    for member,key in self.member_keys(base,static).items():
                        if member in inherited:self.join(key,inherited[member])
                        inherited[member]=key
                        if member in own:self.join(own[member],key)

    def add(self,occurrence):
        if occurrence.key and occurrence.span:self.occurrences.append(occurrence)

    def module_index(self,module):
        uri=module.source.as_uri();checker=module.checker;occupied=set()
        for symbol in checker.symbols:
            key=symbol_key(symbol)
            span=getattr(symbol,'definition_span',None)
            if span:
                occupied.add(span)
                self.add(Occurrence(key,uri,span,symbol.original_name,True,symbol))
        for key,target in checker.structs.items():
            if getattr(target,'checker',None) is not checker:continue
            for field,span in getattr(target.node,'field_spans',{}).items():
                static=field in getattr(target,'statics',{})
                member=self.canonical(('member',key,static,field));occupied.add(span)
                self.add(Occurrence(member,uri,span,field,True,destination=(uri,span)))
            for name,node in getattr(target,'method_nodes',{}).items():
                span=getattr(node,'declaration_span',None)
                if span:
                    member=self.canonical(('member',key,'static' in getattr(node,'modifiers',[]),name));occupied.add(span)
                    self.add(Occurrence(member,uri,span,name,True,node=node,destination=(uri,span)))
        shorthand_values={id(n.children[0]):n.value for n in walk(module.program) if n.kind=='property' and getattr(n,'shorthand',False)}
        for node in walk(module.program):
            if node.kind=='property' and hasattr(node,'key_span'):occupied.add(node.key_span)
            if node.kind=='name' and hasattr(node,'symbol') and hasattr(node,'name_span'):
                occupied.add(node.name_span)
                self.add(Occurrence(symbol_key(node.symbol),uri,node.name_span,node.value,symbol=node.symbol,node=node,shorthand=shorthand_values.get(id(node))))
            if getattr(node,'constructor_symbol',None) and getattr(node,'constructor_name_span',None):
                span=node.constructor_name_span;occupied.add(span)
                self.add(Occurrence(symbol_key(node.constructor_symbol),uri,span,node.value.split('.')[0],symbol=node.constructor_symbol,node=node))
            if getattr(node,'external_definition',None) and hasattr(node,'name_span'):
                definition=node.external_definition[0]
                self.add(Occurrence(('external',definition['file'],definition['line'],definition['column']),uri,node.name_span,str(node.value),node=node))
            if getattr(node,'member_key',None) and hasattr(node,'name_span'):
                dest=getattr(node,'member_definition',None)
                destination=(Path(dest[0]).as_uri(),dest[1]) if dest and dest[0] and dest[1] else None
                occupied.add(node.name_span)
                self.add(Occurrence(self.canonical(('member',*node.member_key)),uri,node.name_span,node.value,node=node,destination=destination))
            if node.kind=='composite':
                typ=checker.types.get(id(node))
                if typ and typ.kind=='struct':
                    members=self.member_keys(typ)
                    for item in node.children:
                        if item.kind!='property' or not hasattr(item,'key_span'):continue
                        field=decode_string(item.value) if item.value.startswith(('"',"'")) else item.value
                        if field in members:
                            self.add(Occurrence(self.canonical(members[field]),uri,item.key_span,field,node=item,shorthand='field:'+field if getattr(item,'shorthand',False) else None,quoted=item.value.startswith(('"',"'"))))
        # Imported names before `as` refer to the original export, not its local alias.
        for node in module.program.children:
            if node.kind!='import' or id(node) not in module.imports:continue
            binding=node.value[0]
            if not binding or not binding.startswith('{'):continue
            imported=self.project.modules[module.imports[id(node)]]
            candidates=[t for t in module.program.tokens if t.kind=='name' and node.span[:2]<=(t.line,t.column)<=node.span[2:]]
            for part in binding[1:-1].split(','):
                names=part.strip().split(' as ');exported,local=names[0],names[-1]
                if exported not in imported.exports:continue
                matches=[t for t in candidates if t.text==exported]
                if matches:
                    token=matches[0];span=(token.line,token.column,token.line,token.column+len(exported))
                    # With no alias the same token is both local declaration and import reference.
                    if exported!=local:self.add(Occurrence(symbol_key(imported.exports[exported],False),uri,span,exported))
        generic_scopes=[(getattr(n,'span',None),{p[0] for p in n.type_params}) for n in walk(module.program) if getattr(n,'type_params',None)]
        # Type annotations use the same nominal definitions as expressions.
        for token in module.program.tokens:
            if token.kind!='name':continue
            span=(token.line,token.column,token.line,token.column+len(token.text))
            if span in occupied or any(owner and inside(owner,token.line,token.column) and token.text in names for owner,names in generic_scopes):continue
            key=checker.type_names.get(token.text)
            target=checker.structs.get(key)
            if target:
                declaration=target.checker.scopes[0].get(target.node.value[0])
                if declaration:self.add(Occurrence(symbol_key(declaration,False),uri,span,token.text,symbol=declaration))

    def at(self,uri,position):
        text=self.text.get(uri,'');row,column=codepoint_position(text,position)
        candidates=[o for o in self.occurrences if o.uri==uri and o.span[:2]<=(row,column)<o.span[2:]]
        return sorted(candidates,key=lambda o:(o.shorthand is not None and o.shorthand.startswith('field:'),not o.declaration))[0] if candidates else None

    def location(self,uri,span):return {'uri':uri,'range':range_for(self.text.get(uri,''),span)}

    def definition(self,uri,position):
        selected=self.at(uri,position)
        if not selected:return []
        external=getattr(selected.symbol,'external_definition',None) or getattr(selected.node,'external_definition',None)
        if external:
            return [{'uri':Path(d['file']).resolve().as_uri(),'range':{'start':{'line':d['line']-1,'character':d['column']-1},'end':{'line':d['endLine']-1,'character':d['endColumn']-1}}} for d in external]
        if selected.destination:return [self.location(*selected.destination)]
        key=symbol_key(selected.symbol,False) if selected.symbol else selected.key
        return [self.location(o.uri,o.span) for o in self.definitions.get(key,[])]

    def references(self,uri,position,include_declaration=False):
        selected=self.at(uri,position)
        if not selected:return []
        locations={}
        for o in self.occurrences:
            if o.key==selected.key and (include_declaration or not o.declaration):locations[(o.uri,o.span)]=self.location(o.uri,o.span)
        return list(locations.values())

    def rename(self,uri,position,name,documents):
        if not re.fullmatch(r'[A-Za-z_$][\w$]*',name) or name in RESERVED:raise ValueError('new name must be a valid GS identifier')
        selected=self.at(uri,position)
        if not selected:return {'documentChanges':[]}
        if getattr(selected.symbol,'category',None)=='external' or getattr(selected.node,'external_definition',None):raise ValueError('external library symbols cannot be renamed by GS')
        edits={};sources={m.source:m.source_text for m in self.project.modules.values()}
        for occurrence in self.occurrences:
            if occurrence.key!=selected.key:continue
            symbol=occurrence.symbol
            if symbol:
                scopes=getattr(occurrence.node,'lexical_scopes',())
                own=getattr(symbol,'definition_scope',{})
                for scope in (*scopes,own):
                    conflicting=scope.get(name)
                    if conflicting and symbol_key(conflicting)!=selected.key:raise ValueError('rename would capture an existing binding: '+name)
            replacement=json.dumps(name) if occurrence.quoted else name
            if occurrence.shorthand:
                replacement=name+': '+occurrence.name if occurrence.shorthand.startswith('field:') else occurrence.shorthand+': '+name
            edits.setdefault(occurrence.uri,{})[occurrence.span]=replacement
        for file_uri,replacements in edits.items():
            path=next(p for p in sources if p.as_uri()==file_uri);text=sources[path]
            for span,replacement in sorted(replacements.items(),reverse=True):
                text=text[:text_offset(text,span[0],span[1])]+replacement+text[text_offset(text,span[2],span[3]):]
            sources[path]=text
        from .project import Project
        try:Project(self.project.entry,self.project.root,sources=sources,libraries=self.project.libraries,prepare_output=False,positions=True,strict_null=self.project.strict_null,typescript=self.project.interop_options['typescript']).check()
        except Exception as error:raise ValueError('rename would make the project invalid: '+str(error)) from error
        return {'documentChanges':[{'textDocument':{'uri':file_uri,'version':documents.get(file_uri,{}).get('version')},'edits':[{'range':range_for(self.text[file_uri],span),'newText':replacement} for span,replacement in sorted(replacements.items())]} for file_uri,replacements in edits.items()]}


def brace_ranges(program):
    stack=[];result=[]
    for token in program.tokens:
        if token.text=='{':stack.append(token)
        elif token.text=='}' and stack:
            opening=stack.pop();result.append((opening.line,opening.column,token.line,token.column+1))
    return result


def completions(module,position,text):
    row,column=codepoint_position(text,position);scopes=brace_ranges(module.program);items={}
    for symbol in module.checker.symbols:
        span=symbol.definition_span
        if not span:continue
        if symbol.scope_depth:
            if symbol.node.kind in ('func','lambda','for','range'):owner=getattr(symbol.node,'span',None)
            else:
                candidates=[r for r in scopes if inside(r,span[0],span[1])]
                owner=max(candidates,key=lambda r:r[:2]) if candidates else None
            if owner and not inside(owner,row,column):continue
            if not owner:continue
            if symbol.node.kind not in ('func','lambda') and span[:2]>(row,column):continue
        current=items.get(symbol.original_name)
        if not current or symbol.scope_depth>=current[0]:items[symbol.original_name]=(symbol.scope_depth,symbol)
    return [{'label':name,'kind':3 if s.typ.kind in ('function','generic_function') else 6,'detail':str(s.typ)} for name,(_,s) in items.items()]


def properties(module,typ,node):
    checker=module.checker
    if typ.kind=='union':
        from parser.extended_checker import union
        values=[t for t in typ.args if t.kind not in ('null','undefined')]
        if not values:return {}
        groups=[properties(module,t,node) for t in values];keys=set(groups[0]).intersection(*(set(g) for g in groups[1:]))
        return {key:union(*(g[key] for g in groups)) for key in keys}
    if typ.kind=='literal':return properties(module,typ.args[0],node)
    if typ.kind=='record':return dict(typ.fields)
    if typ.kind in ('struct','interface','constructor','enum'):
        if hasattr(checker,'members'):
            result=checker.members(typ,typ.kind in ('constructor','enum')) if typ.kind!='enum' else checker.structs[typ.name].statics
            visible={};previous=checker.current_class
            checker.current_class=getattr(node,'owner_class',None)
            try:
                for name,t in result.items():
                    try:checker.access_member(node,typ,name);visible[name]=t
                    except ValueError:pass
            finally:checker.current_class=previous
            return visible
        target=checker.structs[typ.name];return {**target.fields,**target.methods}
    if typ.kind=='foreign':
        reader=checker.declarations
        try:return {p['name']:reader.typ(p['type']) for p in reader.fields(typ) if p['access']=='public' and not p['name'].startswith('__@')}
        finally:reader.close()
    names=('length','map','filter','find','forEach','some','every','push','pop','shift','unshift','slice','concat','includes','indexOf','entries','keys','values','reverse','sort','join') if typ.kind=='array' else ('length','slice','split','trim','toUpperCase','toLowerCase','includes','startsWith','endsWith','charAt','indexOf') if typ==STRING else ('toFixed','toString','toPrecision') if typ.kind in ('int','float','number') else ()
    return {name:checker.property(node,typ,name) for name in names}


def signature_help(module,position,text):
    row,column=codepoint_position(text,position)
    calls=[n for n in walk(module.program) if n.kind in ('call','optional_call','new') and hasattr(n,'span') and inside(n.span,row,column)]
    if not calls:return None
    node=max(calls,key=lambda n:n.span[:2])
    constructor=node.kind=='new'
    typ=module.checker.types.get(id(node)) if constructor else module.checker.types.get(id(node.children[0]))
    constructor_node=None
    if constructor and typ and typ.kind=='struct':
        target=module.checker.structs[typ.name]
        constructor_node=getattr(target,'constructor_node',None)
        typ=module.checker.constructor_signature(typ) if hasattr(module.checker,'constructor_signature') else None
    elif constructor and getattr(node,'constructor_symbol',None):typ=node.constructor_symbol.typ
    if not typ:return None
    if typ.kind=='generic_function':typ=typ.args[0]
    signatures=[]
    if typ.kind=='function':
        symbol=getattr(node.children[0],'symbol',None) if node.children else None;source=constructor_node or (getattr(root_symbol(symbol),'node',None) if symbol else None)
        names=[p[0] for p in source.value[1]] if source and source.kind in ('func','lambda') else []
        labels=[(names[i] if i<len(names) else 'arg'+str(i))+': '+str(t) for i,t in enumerate(typ.args[:-1])]
        signatures=[{'label':'('+', '.join(labels)+') '+str(typ.args[-1]),'parameters':[{'label':x} for x in labels]}]
    elif typ.kind=='foreign':
        reader=module.checker.declarations
        try:
            for signature in reader.describe(typ).get('constructs' if constructor else 'calls',[]):
                params,result=module.checker.foreign_signature(signature,dict(typ.fields))
                labels=['arg'+str(i)+': '+str(t) for i,t in enumerate(params)]
                signatures.append({'label':'('+', '.join(labels)+') '+str(result),'parameters':[{'label':x} for x in labels]})
        finally:reader.close()
    elif typ.kind=='builtin':
        label=typ.name+'(value)' if REGISTRY[typ.name].maximum==1 else typ.name+'(...values)'
        signatures=[{'label':label,'parameters':[{'label':'value'}]}]
    if not signatures:return None
    tokens=[t for t in module.program.tokens if node.span[:2]<=(t.line,t.column)<(row,column)]
    depth=0;argument=0
    for token in tokens:
        if token.text in ('(','[','{'):depth+=1
        elif token.text in (')',']','}'):depth-=1
        elif token.text==',' and depth==1:argument+=1
    return {'signatures':signatures,'activeSignature':0,'activeParameter':min(argument,max(0,len(signatures[0]['parameters'])-1))}


def module_for(server,uri,position=None):
    from .lsp import path_from_uri
    path=path_from_uri(uri)
    project=server.projects.get(uri) or server.partial_projects.get(uri)
    if project and path in project.modules and project.modules[path].checker:return project,project.modules[path]
    if position is not None:
        doc=server.documents.get(uri)
        if not doc:return None,None
        text=doc['text'];row,column=codepoint_position(text,position);offset=text_offset(text,row,column)
        prefix=text[:offset]
        patched=prefix+('__gs_completion__' if prefix.rstrip().endswith('.') else '')+text[offset:]
        # Balance incomplete editor input without changing its prefix positions.
        try:
            from parser.syntax import tokenize
            scanned=tokenize(patched)
            stack=[];pairs={')':'(',']':'[','}':'{'}
            for token in scanned:
                if token.text in ('(','[','{'):stack.append(token.text)
                elif token.text in pairs and stack and stack[-1]==pairs[token.text]:stack.pop()
            patched+=''.join({'(':')','[':']','{':'}'}[x] for x in reversed(stack))
            from .project import Project
            from .build import configure
            options=configure(path,root=server.root_for(path),strict_null=server.strict_null)
            overlays={path_from_uri(u):d['text'] for u,d in server.documents.items()};overlays[path]=patched
            project=Project(path,options.root,sources=overlays,libraries=options.libraries,strict_null=options.strict_null,prepare_output=False,parse_cache=getattr(server,'parse_cache',None),positions=True)
            try:project.check()
            except ValueError:pass
            module=project.modules.get(path)
            if module and module.checker:return project,module
        except (ValueError,OSError):pass
    return None,None


def workspace_project(server,uri):
    from .lsp import path_from_uri
    from .tools import source_files
    from .project import Project
    from .build import configure
    root=server.root_for(path_from_uri(uri));files=set(source_files(root))
    overlays={path_from_uri(u):d['text'] for u,d in server.documents.items() if path_from_uri(u).is_relative_to(root)}
    files.update(overlays)
    sources={p:overlays[p] if p in overlays else p.read_text(encoding='utf-8') for p in files}
    collector=root/'.gs-workspace-index.gs'
    sources[collector]='\n'.join('import '+json.dumps('./'+os.path.relpath(p,root).replace(os.sep,'/')) for p in sorted(files))
    options=configure(path_from_uri(uri),root=root,strict_null=server.strict_null)
    fingerprint=(tuple((str(p),text) for p,text in sorted(sources.items())),options.strict_null,tuple(options.libraries or []))
    if getattr(server,'workspace_cache',None) and server.workspace_cache[0]==fingerprint and server.session.valid(server.workspace_cache[1],sources):return server.workspace_cache[1]
    project=Project(collector,root,sources=sources,libraries=options.libraries,strict_null=options.strict_null,prepare_output=False,parse_cache=getattr(server,'parse_cache',None),positions=True).check()
    server.workspace_cache=(fingerprint,project)
    return project


def auto_imports(server,module,existing):
    from .tools import source_files
    from parser.syntax import parse_code
    items=[]
    for path in source_files(server.root_for(module.source)):
        if path==module.source:continue
        try:
            source=server.documents.get(path.as_uri(),{}).get('text')
            source=path.read_text(encoding='utf-8') if source is None else source
            program=server.parse_cache.parse(path,source) if getattr(server,'parse_cache',None) else parse_code(source)
        except (OSError,ValueError):continue
        for original in program.children:
            if original.kind!='export':continue
            node=unwrap(original)
            name=node.value[1] if node.kind=='decl' else node.value[0] if node.kind in ('func','struct','interface','alias','enum') else None
            if not name or name in existing:continue
            relative=os.path.relpath(path,module.source.parent).replace(os.sep,'/')
            if not relative.startswith('.'):relative='./'+relative
            items.append({'label':name,'kind':3 if node.kind=='func' else 6,'detail':'Import from '+relative,'additionalTextEdits':[{'range':{'start':{'line':0,'character':0},'end':{'line':0,'character':0}},'newText':'import { '+name+' } from '+json.dumps(relative)+'\n'}]})
    return items


def handle_feature(server,method,params):
    from .lsp import path_from_uri,KEYWORDS,declarations
    uri=params['textDocument']['uri'];canonical_uri=path_from_uri(uri).as_uri();doc=server.documents.get(uri)
    if not doc:return None
    position=params.get('position',{'line':0,'character':0})
    if method=='textDocument/formatting':
        from .formatter import format_source
        updated=format_source(doc['text'])
        end={'line':doc['text'].count('\n'),'character':len(doc['text'].rsplit('\n',1)[-1].encode('utf-16-le'))//2}
        return [] if updated==doc['text'] else [{'range':{'start':{'line':0,'character':0},'end':end},'newText':updated}]
    project,module=module_for(server,uri,position)
    if not module:return {'items':[{'label':w,'kind':14} for w in KEYWORDS],'isIncomplete':True} if method=='textDocument/completion' else None
    if method=='textDocument/documentSymbol':return declarations(module.program,doc['text'])
    if method=='textDocument/signatureHelp':return signature_help(module,position,doc['text'])
    if method=='textDocument/completion':
        row,column=codepoint_position(doc['text'],position);prefix=doc['text'][:text_offset(doc['text'],row,column)]
        member_prefix=re.search(r'(?:\?\.|\.)[A-Za-z_$\w]*$',prefix)
        if member_prefix:
            candidates=[n for n in walk(module.program) if n.kind in ('member','optional_member') and n.children and hasattr(n.children[0],'span') and n.children[0].span[2:]<=(row,column)]
            if candidates:
                member=max(candidates,key=lambda n:n.children[0].span[2:]);base=member.children[0];typ=module.checker.types.get(id(base))
                if typ:return {'isIncomplete':False,'items':[{'label':name,'kind':2 if t.kind in ('function','array_method','foreign','generic_function') else 10,'detail':str(t)} for name,t in properties(module,typ,member).items()]}
        items=[{'label':w,'kind':14} for w in KEYWORDS]+completions(module,position,doc['text'])
        items+=auto_imports(server,module,{item['label'] for item in items})
        return {'items':items,'isIncomplete':False}
    if method=='textDocument/hover':
        row,column=codepoint_position(doc['text'],position)
        candidates=[n for n in walk(module.program) if getattr(n,'name_span',None) and n.name_span[:2]<=(row,column)<n.name_span[2:]]
        if not candidates:return None
        node=candidates[0];typ=module.checker.types.get(id(node))
        return {'contents':{'kind':'plaintext','value':str(node.value)+': '+str(typ)},'range':range_for(doc['text'],node.name_span)} if typ else None
    if method in ('textDocument/references','textDocument/rename'):project=workspace_project(server,uri)
    index=Index(project)
    if method=='textDocument/definition':return index.definition(canonical_uri,position)
    if method=='textDocument/references':return index.references(canonical_uri,position,params.get('context',{}).get('includeDeclaration',False))
    if method=='textDocument/prepareRename':
        occurrence=index.at(canonical_uri,position)
        return {'range':range_for(doc['text'],occurrence.span),'placeholder':occurrence.name} if occurrence else None
    if method=='textDocument/rename':
        canonical_documents={path_from_uri(u).as_uri():d for u,d in server.documents.items()}
        result=index.rename(canonical_uri,position,params['newName'],canonical_documents)
        for change in result['documentChanges']:
            target=change['textDocument']['uri']
            change['textDocument']['uri']=next((u for u in server.documents if path_from_uri(u).as_uri()==target),target)
        return result
    return None
