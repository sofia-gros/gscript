"""Project configuration and phased compilation. Output is committed after validation."""
from dataclasses import dataclass
import json
from pathlib import Path

from parser.compiler import CompileError
from .project import Project, plan_outputs, write_output
from .minifier import minify


@dataclass
class Settings:
    entry: Path
    root: Path
    out_dir: Path
    format: str = 'js'
    minify: bool = False
    ts_compiler: str = 'gs'
    sourcemap: bool = False
    declaration: bool = False
    strict_null: bool = False
    cache: bool = True
    cache_dir: Path | None = None
    typescript: Path | None = None
    output: Path | None = None
    libraries: list | None = None
    backend: str = 'js'
    native_target: str | None = None


def configure(source=None, **overrides):
    source=Path(source or '.')
    directory=source.resolve() if source.is_dir() else source.resolve().parent
    config_file=next((parent/'gsconfig.json' for parent in [directory,*directory.parents] if (parent/'gsconfig.json').is_file()),directory/'gsconfig.json')
    directory=config_file.parent
    config={}
    if config_file.exists():
        try:config=json.loads(config_file.read_text(encoding='utf-8'))
        except (ValueError,UnicodeError) as e:raise CompileError(f'invalid gsconfig.json: {e}') from e
        if not isinstance(config,dict):raise CompileError('gsconfig.json must contain an object')
        allowed={'entry','outDir','format','minify','tsCompiler','sourcemap','declaration','strictNull','lib','backend','nativeTarget'}
        unknown=set(config)-allowed
        if unknown:raise CompileError('unknown gsconfig.json option: '+sorted(unknown)[0])
        for name in ('entry','outDir','format','tsCompiler','backend','nativeTarget'):
            if name in config and not isinstance(config[name],str):raise CompileError(name+' must be a string')
        for name in ('minify','sourcemap','declaration','strictNull'):
            if name in config and not isinstance(config[name],bool):raise CompileError(name+' must be boolean')
    if 'lib' in config and (not isinstance(config['lib'],list) or not all(isinstance(x,str) for x in config['lib'])):raise CompileError('lib must be an array of library names')
    project=source.is_dir()
    if project:
        if 'entry' in config:entry=directory/config['entry']
        else:entry=next((directory/name for name in ('main.gs','main.gos') if (directory/name).is_file()),None)
        if entry is None:raise CompileError('project entry not found; create main.gs or set entry in gsconfig.json')
    else:entry=source.resolve()
    if entry.suffix not in ('.gs','.gos'):raise CompileError('source extension must be .gs or .gos')
    settings=Settings(entry.resolve(),directory,directory/config.get('outDir','dist'),
                      format=config.get('format','js'),minify=config.get('minify',project),
                      ts_compiler=config.get('tsCompiler','gs'),sourcemap=config.get('sourcemap',False),
                      declaration=config.get('declaration',False),strict_null=config.get('strictNull',False),libraries=config.get('lib'),backend=config.get('backend','js'),native_target=config.get('nativeTarget'))
    for key,value in overrides.items():
        if value is not None:setattr(settings,key,value)
    if settings.backend not in ('js','native'):raise CompileError('backend must be js or native')
    if settings.format not in ('js','mjs','ts'):raise CompileError('format must be js, mjs or ts')
    if settings.ts_compiler not in ('gs','ts'):raise CompileError('tsCompiler must be gs or ts')
    settings.root=Path(settings.root).resolve();settings.out_dir=Path(settings.out_dir).resolve()
    return settings


def build(settings, check_only=False, analysis_info=False, session=None):
    options=dict(cache=settings.cache,cache_dir=settings.cache_dir,typescript=settings.typescript,strict_null=settings.strict_null,libraries=settings.libraries,analysis_info=analysis_info,positions=settings.sourcemap)
    project=session.check(settings.entry,settings.root,**options) if session else Project(settings.entry,settings.root,settings.format,prepare_output=False,**options).check()
    if check_only:return project,None
    outputs=session.plan(project,settings.out_dir,settings.format) if session else plan_outputs(project,settings.out_dir,settings.format)
    entry_output=settings.out_dir/project.entry.relative_to(project.root).with_suffix('.'+settings.format)
    if settings.output:
        if len(project.modules)>1 or project.has_external and project._external_result(settings.format).get('files'):raise CompileError('use --out-dir to build local module dependencies')
        target=Path(settings.output).resolve()
        if target in project.modules:raise CompileError('output must not overwrite the source file')
        outputs[target]=outputs.pop(entry_output);entry_output=target
    if settings.ts_compiler=='ts' and settings.format!='ts':
        from .ts_compiler import compile_typescript
        outputs=compile_typescript(project,outputs,settings)
    if settings.declaration:
        from .declarations_output import declarations
        outputs.update(declarations(project,settings))
    if settings.sourcemap:
        from .source_maps import source_maps
        outputs=source_maps(project,outputs,settings)
    if settings.minify and settings.format!='ts' and not settings.sourcemap:
        generated={settings.out_dir/m.source.relative_to(project.root).with_suffix('.'+settings.format) for m in project.modules.values()}
        if settings.output:generated.add(entry_output)
        for path in generated:
            if path in outputs:outputs[path]=minify(outputs[path])
    protected=set(project.modules)
    for external in project.external_results.values():
        protected.update(Path(d['file']).resolve() for d in external.get('dependencies',[]) if d.get('readHash'))
        protected.update(Path(d['source']).resolve() for d in external.get('files',[]))
    for output,contents in outputs.items():
        if output.resolve() in protected:raise CompileError('output must not overwrite a source or declaration file')
    for output,contents in outputs.items():
        if not output.is_file() or output.read_text(encoding='utf-8')!=contents:write_output(output,contents)
    return project,entry_output
