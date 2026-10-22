"""Bounded in-process caches; source contents and dependency fingerprints are checked."""
from collections import OrderedDict
import hashlib
from pathlib import Path

from parser.syntax import Node,Token,parse_code


def digest(text):return hashlib.sha256(text.encode('utf-8')).hexdigest()


def clone_syntax(value):
    if isinstance(value,Token):return value
    if isinstance(value,Node):
        result=Node(value.kind,clone_syntax(value.value),clone_syntax(value.children),value.line)
        for key,item in value.__dict__.items():
            if key not in ('kind','value','children','line'):setattr(result,key,clone_syntax(item))
        return result
    if isinstance(value,list):return [clone_syntax(v) for v in value]
    if isinstance(value,tuple):return tuple(clone_syntax(v) for v in value)
    if isinstance(value,dict):return {k:clone_syntax(v) for k,v in value.items()}
    return value


class ParseCache:
    def __init__(self,positions=False,limit=2048):
        self.positions=positions;self.limit=limit;self.entries=OrderedDict();self.parsed=0;self.hits=0

    def parse(self,path,text,positions=None):
        positions=self.positions if positions is None else positions
        key=(digest(text),positions)
        prototype=self.entries.get(key)
        if prototype is None:
            self.parsed+=1;prototype=parse_code(text,positions=positions)
            self.entries[key]=prototype
            while len(self.entries)>self.limit:self.entries.popitem(last=False)
        else:self.hits+=1;self.entries.move_to_end(key)
        # The checker mutates AST nodes. Never share checked nodes or scope objects.
        return clone_syntax(prototype)


class CheckSession:
    def __init__(self,positions=False,limit=32):
        self.parse_cache=ParseCache(positions);self.positions=positions
        self.entries=OrderedDict();self.limit=limit;self.checks=0;self.hits=0;self.last_project=None

    def valid(self,project,sources):
        for module in project.modules.values():
            try:text=sources.get(module.source) if module.source in sources else module.source.read_text(encoding='utf-8')
            except (OSError,UnicodeError):return False
            if text!=module.source_text:return False
        from .interop import _fingerprint
        reader=getattr(project,'declarations',None)
        if reader:
            try:
                if hashlib.sha256(Path(reader.init_request['typescript']).read_bytes()).hexdigest()!=reader.compiler_hash:return False
            except OSError:return False
        for dependency in reader.dependencies if reader else ():
            if 'fingerprint' in dependency:
                if _fingerprint(dependency['file'],dependency['kind'])!=dependency['fingerprint']:return False
            else:
                # A cold reader records content hashes; missing probes must stay missing.
                now=_fingerprint(dependency['file'],dependency['kind'])
                if dependency.get('readHash'):
                    if now is None or now[1]!=dependency['readHash']:return False
                elif dependency['kind']=='file' and now is not None:return False
        return True

    def check(self,entry,root,*,sources=None,strict_null=False,libraries=None,typescript=None,cache=True,cache_dir=None,analysis_info=False,positions=None):
        from .project import Project
        entry=Path(entry).resolve();root=Path(root).resolve();sources={Path(p).resolve():text for p,text in (sources or {}).items()}
        positions=self.positions if positions is None else positions
        key=(entry,root,strict_null,tuple(libraries or []),str(typescript),cache,str(cache_dir),analysis_info,positions)
        self.last_project=None
        project=self.entries.get(key)
        if project and self.valid(project,sources):
            self.hits+=1;self.entries.move_to_end(key);self.last_project=project;return project
        self.checks+=1
        project=Project(entry,root,sources=sources,strict_null=strict_null,libraries=libraries,typescript=typescript,cache=cache,cache_dir=cache_dir,prepare_output=False,parse_cache=self.parse_cache,positions=positions,analysis_info=analysis_info)
        self.last_project=project
        project.check()
        self.entries[key]=project
        while len(self.entries)>self.limit:self.entries.popitem(last=False)
        return project


def type_shape(typ,structs,seen=None):
    seen=set() if seen is None else set(seen)
    result=(typ.kind,typ.name,tuple(type_shape(t,structs,seen) for t in typ.args),tuple((n,type_shape(t,structs,seen)) for n,t in typ.fields))
    if typ.name in structs and typ.name not in seen:
        seen.add(typ.name);target=structs[typ.name]
        shape=tuple((name,type_shape(t,structs,seen)) for name,t in sorted({**target.fields,**target.methods,**getattr(target,'statics',{})}.items()))
        base=getattr(target,'base',None)
        constructor=getattr(target,'constructor',None)
        result+=(shape,type_shape(base,structs,seen) if base else None,type_shape(constructor,structs,seen) if constructor else None,tuple(getattr(target,'parameters',[])),str(getattr(target,'access',{})),tuple(sorted(getattr(target,'readonly',set()))))
    return result


class BuildSession(CheckSession):
    def __init__(self):
        super().__init__();self.emissions={};self.emitted=0;self.emission_hits=0

    def plan(self,project,out_dir,format):
        # External emission already uses its content-validated persistent cache.
        from .project import plan_outputs
        if project.has_external:return plan_outputs(project,out_dir,format)
        shapes={path:digest(repr(tuple((name,type_shape(symbol.typ,module.checker.structs)) for name,symbol in sorted(module.exports.items())))) for path,module in project.modules.items()}
        outputs={};out_dir=Path(out_dir).resolve()
        for module in project.modules.values():
            dependencies=set();queue=list(module.imports.values())
            while queue:
                path=queue.pop()
                if path in dependencies:continue
                dependencies.add(path);queue.extend(project.modules[path].imports.values())
            key=(module.source,digest(module.source_text),format,tuple((str(path),shapes[path]) for path in sorted(dependencies)),project.strict_null)
            if key in self.emissions:code=self.emissions[key];self.emission_hits+=1
            else:
                code=project.emit(module,format);self.emissions[key]=code;self.emitted+=1
                if len(self.emissions)>4096:self.emissions.pop(next(iter(self.emissions)))
            outputs[out_dir/module.source.relative_to(project.root).with_suffix('.'+format)]=code
        if format in ('js','ts'):
            from .project import module_marker
            marker=module_marker(out_dir)
            if marker:outputs[marker]='{"type":"module"}\n'
        return outputs
