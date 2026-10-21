"""Build a Python zipapp and/or the native compiler for the current machine."""
import argparse
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipapp
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gscript import __version__


def build_zipapp(output):
    with tempfile.TemporaryDirectory() as directory:
        staging = Path(directory)
        for package in ('gscript', 'parser'):
            shutil.copytree(ROOT / package, staging / package,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        shutil.copy2(ROOT / 'scripts/compiler_entry.py', staging / '__main__.py')
        zipapp.create_archive(staging, output / f'gs-v{__version__}.pyz',
                              interpreter='/usr/bin/env python3', compressed=True)


def build_native(output):
    build = ROOT / 'build/native'
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm',
                    '--onefile', '--name', 'gs', '--paths', str(ROOT),
                    '--add-data', str(ROOT / 'gscript/typescript_bridge.cjs') + os.pathsep + 'gscript',
                    '--add-data', str(ROOT / 'gscript/declarations.cjs') + os.pathsep + 'gscript',
                    '--distpath', str(build / 'bin'), '--workpath', str(build / 'work'),
                    '--specpath', str(build), str(ROOT / 'scripts/compiler_entry.py')], check=True)
    executable = build / 'bin' / ('gs.exe' if sys.platform == 'win32' else 'gs')
    # Exercise the exact standalone executable before packaging it.
    subprocess.run([sys.executable, str(ROOT / 'scripts/smoke_compiler.py'), str(executable)], check=True)
    system = {'Darwin': 'macos', 'Windows': 'windows', 'Linux': 'linux'}[platform.system()]
    arch = {'AMD64': 'x86_64', 'aarch64': 'arm64'}.get(platform.machine(), platform.machine())
    base = f'gs-v{__version__}-{system}-{arch}'
    with tempfile.TemporaryDirectory() as directory:
        staging = Path(directory) / base
        staging.mkdir()
        shutil.copy2(executable, staging / executable.name)
        shutil.copy2(ROOT / 'readme.md', staging / 'README.md')
        shutil.copy2(ROOT / 'docs/language.md', staging / 'LANGUAGE.md')
        if system == 'windows':
            with zipfile.ZipFile(output / (base + '.zip'), 'w', zipfile.ZIP_DEFLATED) as archive:
                for path in staging.iterdir():
                    archive.write(path, str(Path(base) / path.name))
        else:
            with tarfile.open(output / (base + '.tar.gz'), 'w:gz') as archive:
                archive.add(staging, arcname=base)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', action='store_true')
    parser.add_argument('--zipapp', action='store_true')
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/release')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.zipapp:
        build_zipapp(args.output)
    if args.native:
        build_native(args.output)
    if not (args.native or args.zipapp):
        parser.error('choose --native and/or --zipapp')


if __name__ == '__main__':
    main()
