"""Test a built compiler outside its checkout, including its output and errors."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(command, **kwargs):
    result = subprocess.run(command, text=True, capture_output=True, timeout=60, **kwargs)
    if result.returncode:
        raise RuntimeError(f'{command!r}\n{result.stdout}\n{result.stderr}')
    return result


def main():
    artifact = Path(sys.argv[1]).resolve()
    compiler = [sys.executable, str(artifact)] if artifact.suffix == '.pyz' else [str(artifact)]
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        environment = dict(os.environ)
        environment.pop('PYTHONPATH', None)
        # Installed packages must not accidentally satisfy imports from the source tree.
        run([*compiler, '--version'], cwd=root, env=environment)
        expected = 'Hello, Sofia Hello, GS answer 42 4\n'
        for format in ('js', 'mjs', 'ts'):
            output = root / format
            run([*compiler, str(ROOT / 'tests/fixtures/modules/main.gs'), '--format', format,
                 '--out-dir', str(output)], cwd=root, env=environment)
            entry = output / ('main.' + format)
            if format == 'ts':
                run(['node', str(ROOT / 'node_modules/typescript/bin/tsc'), str(entry),
                     '--strict', '--target', 'ES2022', '--module', 'NodeNext',
                     '--moduleResolution', 'NodeNext', '--typeRoots', str(ROOT / 'node_modules/@types'),
                     '--outDir', str(root / 'ts-js')], cwd=root)
                (root / 'ts-js/package.json').write_text('{"type":"module"}')
                entry = root / 'ts-js/main.js'
            result = run(['node', str(entry)], cwd=root)
            if result.stdout != expected:
                raise AssertionError(result.stdout)
        advanced = ROOT / 'examples/advanced/main.gs'
        for format in ('js', 'mjs', 'ts'):
            output = root / ('advanced-' + format)
            run([*compiler, str(advanced), '--format', format, '--out-dir', str(output)], cwd=root, env=environment)
            entry = output / ('main.' + format)
            if format == 'ts':
                run(['node', str(ROOT / 'node_modules/typescript/bin/tsc'), str(entry),
                     '--strict', '--target', 'ES2022', '--module', 'NodeNext',
                     '--moduleResolution', 'NodeNext', '--outDir', str(root / 'advanced-js')], cwd=root)
                (root / 'advanced-js/package.json').write_text('{"type":"module"}')
                entry = root / 'advanced-js/main.js'
            if run(['node', str(entry)], cwd=root).stdout != '42\n':
                raise AssertionError('native GS language extension output failed')
        # Verify bundled bridge resources and existing project node_modules.
        run([*compiler, str(ROOT / 'tests/fixtures/interop/phaser.gs'), '--check', '--no-cache'], cwd=root, env=environment)
        for format in ('js', 'mjs', 'ts'):
            external_output = root / ('external-' + format)
            run([*compiler, str(ROOT / 'tests/fixtures/interop/external-main.gs'), '--format', format,
                 '--out-dir', str(external_output)], cwd=root, env=environment)
            external_entry = external_output / ('external-main.' + format)
            if format == 'ts':
                run(['node', str(ROOT / 'node_modules/typescript/bin/tsc'), str(external_entry),
                     '--strict', '--target', 'ES2022', '--module', 'NodeNext',
                     '--moduleResolution', 'NodeNext', '--outDir', str(root / 'external-js')], cwd=root)
                (root / 'external-js/package.json').write_text('{"type":"module"}')
                external_entry = root / 'external-js/external-main.js'
            result = run(['node', str(external_entry)], cwd=root)
            if result.stdout != '7\n':
                raise AssertionError(result.stdout)
        bad = root / 'bad.gs'
        target = root / 'existing.mjs'
        target.write_text('unchanged')
        for source in ('var n int = "bad"', 'func broken( {'):
            bad.write_text(source)
            result = subprocess.run([*compiler, str(bad), '-o', str(target)], cwd=root,
                                    text=True, capture_output=True, timeout=30)
            if result.returncode != 1 or 'Traceback' in result.stderr or target.read_text() != 'unchanged':
                raise AssertionError(f'bad input was not safely rejected: {result.stderr}')
    print(f'Artifact and JS/MJS/TS output checks passed: {artifact.name}')


if __name__ == '__main__':
    main()
