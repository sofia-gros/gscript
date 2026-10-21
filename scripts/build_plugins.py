"""Build version-aligned editor plugins and the standalone language server."""
import argparse
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipapp
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from gscript import __version__


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native',action='store_true')
    parser.add_argument('--portable',action='store_true')
    parser.add_argument('--editors',action='store_true')
    parser.add_argument('--output',type=Path,default=ROOT/'dist/plugins')
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    if not any((args.native,args.portable,args.editors)):parser.error('select a build target')
    if args.portable:
        with tempfile.TemporaryDirectory() as directory:
            staging=Path(directory)
            for name in ('gscript','parser'):
                shutil.copytree(ROOT/name,staging/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            shutil.copy2(ROOT/'scripts/lsp_entry.py',staging/'__main__.py')
            target=output/f'gs-lsp-v{__version__}.pyz'
            zipapp.create_archive(staging,target,interpreter='/usr/bin/env python3',compressed=True)
        subprocess.run([sys.executable,str(ROOT/'scripts/smoke_lsp.py'),str(target)],check=True)
    if args.native:
        build=ROOT/'build/lsp'
        subprocess.run([sys.executable,'-m','PyInstaller','--clean','--noconfirm','--onefile','--name','gs-lsp','--paths',str(ROOT),
                        '--add-data',str(ROOT/'gscript/declarations.cjs')+__import__('os').pathsep+'gscript',
                        '--distpath',str(build/'bin'),'--workpath',str(build/'work'),'--specpath',str(build),str(ROOT/'scripts/lsp_entry.py')],check=True)
        executable=build/'bin'/('gs-lsp.exe' if sys.platform=='win32' else 'gs-lsp')
        subprocess.run([sys.executable,str(ROOT/'scripts/smoke_lsp.py'),str(executable)],check=True)
        system={'Linux':'linux','Darwin':'macos','Windows':'windows'}[platform.system()]
        arch={'AMD64':'x86_64','aarch64':'arm64'}.get(platform.machine(),platform.machine())
        name=f'gs-lsp-v{__version__}-{system}-{arch}'
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)/name;folder.mkdir()
            shutil.copy2(executable,folder/executable.name)
            shutil.copy2(ROOT/'docs/editors.md',folder/'README.md')
            if system=='windows':
                with zipfile.ZipFile(output/(name+'.zip'),'w',zipfile.ZIP_DEFLATED) as archive:
                    for p in folder.iterdir():archive.write(p,name+'/'+p.name)
            else:
                with tarfile.open(output/(name+'.tar.gz'),'w:gz') as archive:archive.add(folder,arcname=name)
    if args.editors:
        extension=(ROOT/'editors/zed/extension.wasm').read_bytes()
        grammar=(ROOT/'editors/zed/grammars/gs.wasm').read_bytes()
        assert extension[:8]==b'\x00asm\x0d\x00\x01\x00', 'Zed extension must be a WebAssembly component'
        assert b'zed:api-version' in extension, 'missing Zed API version'
        assert grammar[:8]==b'\x00asm\x01\x00\x00\x00', 'invalid grammar WASM'
        shutil.copy2(ROOT/f'editors/vscode/gscript-{__version__}.vsix',output/f'gscript-v{__version__}.vsix')
        with zipfile.ZipFile(output/f'gscript-zed-v{__version__}.zip','w',zipfile.ZIP_DEFLATED) as archive:
            base=ROOT/'editors/zed'
            for p in base.rglob('*'):
                relative=p.relative_to(base)
                if p.is_file() and not set(relative.parts)&{'target','.git'}:
                    archive.write(p,'gscript-zed/'+str(relative))
        with zipfile.ZipFile(output/f'gs-plugin-sources-v{__version__}.zip','w',zipfile.ZIP_DEFLATED) as archive:
            for p in (ROOT/'editors').rglob('*'):
                if p.is_file() and not set(p.relative_to(ROOT).parts)&{'target','node_modules','dist','.vscode-test'} and p.suffix!='.vsix':
                    archive.write(p,str(p.relative_to(ROOT)))
            archive.write(ROOT/'docs/editors.md','README.md')


if __name__=='__main__':main()
