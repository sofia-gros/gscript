"""gs init / fmt / lint / watch command implementations."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import time

from parser.compiler import CompileError
from .build import configure,build
from .project import Project,write_output


IGNORED={'node_modules','.git','.gs-cache','.venv','venv','dist','build','target','__pycache__'}


def source_files(source):
    source=Path(source)
    if source.is_file():return [source.resolve()]
    if not source.is_dir():raise CompileError('source does not exist: '+str(source))
    result=[]
    for directory,subdirs,files in os.walk(source):
        subdirs[:]=[name for name in subdirs if name not in IGNORED and not name.startswith('.gs-ts-')]
        result.extend((Path(directory)/name).resolve() for name in files if Path(name).suffix in ('.gs','.gos'))
    return sorted(result)



def initialize(directory,template):
    root=Path(directory).resolve();root.mkdir(parents=True,exist_ok=True)
    config={'entry':'main.gs','outDir':'dist','format':'js'}
    package={'name':root.name or 'gs-project','private':True,'type':'module','scripts':{'build':'gs .','check':'gs . --check','dev':'gs watch'}}
    files={'.gitignore':'dist/\nnode_modules/\n.gs-cache/\n','gsconfig.json':json.dumps(config,indent=2)+'\n'}
    if template=='node':files['main.gs']='println("Hello, GS")\n'
    elif template=='browser':
        files['main.gs']='document.body.textContent = "Hello, GS"\n'
        files['index.html']='<!doctype html>\n<html lang="en"><meta charset="utf-8"><title>GS</title><body><script type="module" src="./dist/main.js"></script></body></html>\n'
    else:
        package['devDependencies']={'typescript':'5.9.3','vite':'6.4.1'}
        package['dependencies']={'phaser':'3.90.0'}
        package['scripts']['dev']='gs . && vite'
        files['main.gs']='''import Phaser from "phaser"
type Scene struct extends Phaser.Scene {}
func (s Scene) constructor() { super("main") }
func (s Scene) create() { s.add.text(20, 20, "Hello, GS") }
var config Phaser.Types.Core.GameConfig = { type: Phaser.AUTO, width: 800, height: 600, scene: Scene }
game := new Phaser.Game(config)
'''
        files['index.html']='<!doctype html>\n<html lang="en"><meta charset="utf-8"><title>GS + Phaser</title><body><script type="module" src="./dist/main.js"></script></body></html>\n'
    files['package.json']=json.dumps(package,indent=2)+'\n'
    collisions=[name for name in files if (root/name).exists()]
    if collisions:raise CompileError('init will not overwrite existing files: '+', '.join(collisions))
    for name,text in files.items():write_output(root/name,text)
    print('Initialized '+template+' GS project in '+str(root))


def command(argv):
    operation=argv[0];parser=argparse.ArgumentParser(prog='gs '+operation)
    parser.add_argument('source',nargs='?',type=Path,default=Path('.'))
    if operation=='init':parser.add_argument('--template',choices=('node','browser','phaser'),default='node')
    elif operation=='fmt':parser.add_argument('--check',action='store_true')
    elif operation=='lint':parser.add_argument('--json',action='store_true');parser.add_argument('--fix',action='store_true')
    elif operation=='watch':parser.add_argument('--interval',type=float,default=0.25)
    args=parser.parse_args(argv[1:])
    try:
        if operation=='init':initialize(args.source,args.template);return 0
        if operation=='fmt':
            from .formatter import format_source
            changes={p:format_source(p.read_text(encoding='utf-8')) for p in source_files(args.source)}
            changed=[p for p,text in changes.items() if p.read_text(encoding='utf-8')!=text]
            if not args.check:
                for p in changed:write_output(p,changes[p])
            for p in changed:print(p)
            return int(bool(changed) and args.check)
        if operation=='lint':
            from .lint import lint_project
            if args.fix:
                for path in source_files(args.source):
                    text=path.read_text(encoding='utf-8');updated=re.sub(r'(?m)[ \t]+$','',text)
                    if updated!=text:write_output(path,updated)
            settings=configure(args.source)
            try:project,_=build(settings,True,analysis_info=True);diagnostics=[d.to_dict() for d in lint_project(project)]
            except CompileError as error:diagnostics=[{'file':str(getattr(error,'filename',None) or settings.entry),'line':error.line or 1,'column':error.column or 1,'severity':'error','code':'GS0001','message':error.message}]
            if args.json:print(json.dumps(diagnostics,ensure_ascii=False))
            else:
                for d in diagnostics:print(f'{d["file"]}:{d["line"]}:{d["column"]} {d["severity"]} {d["code"]}\n{d["message"]}')
            return int(any(d['severity']=='error' for d in diagnostics))
        if args.interval<=0:raise CompileError('watch interval must be positive')
        return watch(args.source,args.interval)
    except (CompileError,OSError,UnicodeError,ValueError) as error:
        print(str(error),file=sys.stderr);return 1


def watch(source,interval):
    from .cache import BuildSession
    session=BuildSession()
    settings=configure(source);previous=None;project=None
    def snapshot():
        from hashlib import sha256
        paths=set(source_files(settings.root))|{settings.root/'gsconfig.json',settings.root/'package.json',settings.root/'package-lock.json',settings.root/'tsconfig.json'}
        tracked=project or session.last_project
        if tracked:
            reader=getattr(tracked,'declarations',None)
            paths.update(Path(d['file']) for d in getattr(reader,'dependencies',()) if d.get('kind')=='file')
            for result in tracked.external_results.values():
                paths.update(Path(d['file']) for d in result.get('dependencies',[]) if d.get('kind')=='file')
        # Track creation/repair of local foreign modules even after a failed first build.
        for directory,subdirs,files in os.walk(settings.root):
            subdirs[:]=[n for n in subdirs if n not in IGNORED and not n.startswith('.gs-ts-') and (Path(directory)/n).resolve()!=settings.out_dir]
            paths.update(Path(directory)/n for n in files if Path(n).suffix in ('.js','.mjs','.cjs','.ts','.mts','.cts','.json'))
        values=[]
        for p in sorted(paths):
            try:values.append((str(p),sha256(p.read_bytes()).hexdigest()))
            except FileNotFoundError:values.append((str(p),None))
        return tuple(values)
    try:
        while True:
            current=snapshot()
            if current!=previous:
                # A second stable snapshot coalesces bursts of saves.
                if previous is not None:
                    time.sleep(min(interval,0.5));stable=snapshot()
                    if stable!=current:continue
                previous=current
                try:
                    settings=configure(source);project,target=build(settings,session=session)
                    print('Built '+str(target),flush=True)
                except (CompileError,OSError,ValueError) as error:print('Build failed: '+str(error),file=sys.stderr,flush=True)
            time.sleep(interval)
    except KeyboardInterrupt:
        print('Stopped GS watch',flush=True);return 0
