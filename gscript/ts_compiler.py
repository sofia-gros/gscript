"""Official TS 5.9/6.0 API and TS 7.0 native CLI adapters, after GS checking."""
from importlib.resources import files
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile

from parser.compiler import CompileError
from .project import plan_outputs


def run_compiler(*args,**kwargs):
    try:return subprocess.run(*args,**kwargs)
    except subprocess.TimeoutExpired as error:raise CompileError('official TypeScript compiler exceeded the 120 second timeout') from error
    except OSError as error:raise CompileError('could not start official TypeScript compiler: '+str(error)) from error


def package_for(entry,override=None):
    if override:
        candidate=Path(override).resolve()
        if candidate.is_file():candidate=candidate.parent.parent
        choices=[candidate]
    else:choices=[parent/'node_modules/typescript' for parent in dict.fromkeys([entry.parent,*entry.parent.parents,Path(__file__).resolve().parent.parent])]
    for candidate in choices:
        metadata=candidate/'package.json'
        if not metadata.is_file():continue
        package=json.loads(metadata.read_text(encoding='utf-8'));version=package.get('version','')
        if not re.fullmatch(r'(5\.9|6\.0|7\.0)\.\d+',version):raise CompileError('supported official TypeScript releases are 5.9.x, 6.0.x and 7.0.x; got '+version)
        return candidate,version
    raise CompileError('--ts-compiler ts requires a local TypeScript 5.9, 6.0 or 7.0 release; run npm install --save-dev typescript')


def native_command(package):
    system={'linux':'linux','darwin':'darwin','win32':'win32'}.get(__import__('sys').platform)
    arch={'x86_64':'x64','AMD64':'x64','aarch64':'arm64','arm64':'arm64'}.get(platform.machine(),platform.machine())
    executable=package.parent/'@typescript'/f'typescript-{system}-{arch}'/'lib'/('tsc.exe' if system=='win32' else 'tsc')
    if executable.is_file():return [str(executable)]
    node=shutil.which('node')
    if node and (package/'bin/tsc').is_file():return [node,str(package/'bin/tsc')]
    raise CompileError('TypeScript 7 native binary for this OS/CPU is missing; reinstall typescript with optional dependencies enabled')


def compile_typescript(project,previous,settings):
    package,version=package_for(project.entry,settings.typescript)
    with tempfile.TemporaryDirectory(prefix='.gs-ts-',dir=project.root) as directory:
        temporary=Path(directory);input_dir=temporary/'input';output_dir=temporary/'output'
        input_dir.mkdir();output_dir.mkdir()
        staged=plan_outputs(project,input_dir,'ts')
        source_files={}
        for target,code in staged.items():
            target.parent.mkdir(parents=True,exist_ok=True);target.write_text(code,encoding='utf-8')
        for module in project.modules.values():source_files[str(input_dir/module.source.relative_to(project.root).with_suffix('.ts'))]=module.source
        options={'strict':True,'target':'ES2022','module':'NodeNext','moduleResolution':'NodeNext','allowJs':True,'checkJs':False,'skipLibCheck':True,'noEmitOnError':True,'rootDir':'input','outDir':'output','sourceMap':settings.sourcemap,'inlineSources':settings.sourcemap}
        config=temporary/'tsconfig.json'
        config.write_text(json.dumps({'compilerOptions':options,'include':['input/**/*']}),encoding='utf-8')
        if version.startswith('7.'):
            result=run_compiler([*native_command(package),'--project',str(config),'--pretty','false'],capture_output=True,text=True,timeout=120)
            if result.returncode:raise CompileError('TypeScript '+version+' compilation failed:\n'+result.stdout+result.stderr)
        else:
            node=shutil.which('node')
            if not node:raise CompileError('TypeScript 5.9/6.0 compilation requires Node.js')
            script=temporary/'compile.cjs';script.write_text(files('gscript').joinpath('compile_ts.cjs').read_text(encoding='utf-8'),encoding='utf-8')
            result=run_compiler([node,str(script)],input=json.dumps({'api':str(package/'lib/typescript.js'),'config':str(config)}),capture_output=True,text=True,timeout=120)
            if result.returncode:raise CompileError('TypeScript compiler API failed: '+result.stderr)
            diagnostics=json.loads(result.stdout)['diagnostics']
            if diagnostics:
                d=diagnostics[0];failure=CompileError('TS'+str(d['code'])+': '+d['message'],d.get('line'),d.get('column'));failure.filename=str(source_files.get(d.get('file'),d.get('file') or project.entry));raise failure
        compiled={path.relative_to(output_dir):path.read_text(encoding='utf-8') for path in output_dir.rglob('*') if path.is_file()}
        results={}
        for relative,code in compiled.items():
            if relative.suffix=='.map':continue # Composed by the GS Source Map phase.
            destination=relative.with_suffix('.mjs') if settings.format=='mjs' and relative.suffix=='.js' else relative
            if settings.format=='mjs':
                from .import_rewrite import rewrite_imports
                def rewrite(spec):
                    target=Path(os.path.normpath(str(relative.parent/spec)))
                    return spec[:-3]+'.mjs' if spec.startswith('.') and spec.endswith('.js') and target in compiled else spec
                code=rewrite_imports(code,rewrite)
            code=re.sub(r'(?m)^//# sourceMappingURL=[^\n]*(?:\n|$)','',code)
            target=settings.out_dir/destination
            if settings.output and relative==project.entry.relative_to(project.root).with_suffix('.js'):target=Path(settings.output).resolve()
            results[target]=code
        # Retain ESM marker and external declarations planned by GS.
        results.update({p:c for p,c in previous.items() if p.name=='package.json' or p.name.endswith(('.d.ts','.d.mts','.d.cts'))})
        return results
