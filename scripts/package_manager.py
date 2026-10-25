"""Package an already built GPUI manager; never launches its window."""
import argparse
from pathlib import Path
import plistlib
import shutil
import subprocess
import tarfile
import tempfile
import tomllib
import zipfile
ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--target', choices=['windows-x86_64', 'linux-x86_64', 'macos-arm64'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tag')
    args = parser.parse_args()
    version = tomllib.loads((ROOT/'apps/manager/native/Cargo.toml').read_text())['package']['version']
    if args.tag and args.tag != 'manager-v'+version:
        parser.error('manager release tag must match Cargo.toml')
    binary = args.binary.resolve()
    result = subprocess.run([str(binary), '--self-check'], capture_output=True, text=True, timeout=30, check=True)
    if f'GScript Manager {version}:' not in result.stdout:
        raise RuntimeError('unexpected manager self-check result: '+result.stdout+result.stderr)
    args.output.mkdir(parents=True, exist_ok=True)
    stem = f'gscript-manager-v{version}-{args.target}'
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)/stem
        folder.mkdir()
        if args.target.startswith('macos'):
            app = folder/'GScript Manager.app'/'Contents'
            (app/'MacOS').mkdir(parents=True)
            target = app/'MacOS'/'gscript-manager'
            shutil.copy2(binary, target)
            with (app/'Info.plist').open('wb') as stream:
                plistlib.dump({'CFBundleIdentifier':'dev.gscript.manager', 'CFBundleName':'GScript Manager',
                              'CFBundleDisplayName':'GScript Manager', 'CFBundleExecutable':'gscript-manager',
                              'CFBundleVersion':version, 'CFBundleShortVersionString':version,
                              'CFBundlePackageType':'APPL', 'LSMinimumSystemVersion':'11.0',
                              'NSHighResolutionCapable':True}, stream)
        else:
            shutil.copy2(binary, folder/binary.name)
        shutil.copy2(ROOT/'apps/manager/native/README.md', folder/'README.md')
        if args.target.startswith('windows'):
            with zipfile.ZipFile(args.output/(stem+'.zip'), 'w', zipfile.ZIP_DEFLATED) as archive:
                for path in folder.rglob('*'):
                    if path.is_file():
                        archive.write(path, (Path(stem)/path.relative_to(folder)).as_posix())
        else:
            with tarfile.open(args.output/(stem+'.tar.gz'), 'w:gz') as archive:
                archive.add(folder, arcname=stem)
    print('Packaged:', stem)


if __name__ == '__main__':
    main()
