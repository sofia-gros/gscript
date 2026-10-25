"""Windows archives must contain the onedir runtime, including nested DLLs."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WindowsBundlesTests(unittest.TestCase):
    def package(self, script, name):
        module = load(script)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'docs').mkdir()
            (root / 'docs/editors.md').write_text('Editor installation')
            (root / 'readme.md').write_text('Compiler installation')
            output = root / 'artifacts'
            output.mkdir()
            builds = []

            def command(args, **kwargs):
                if 'PyInstaller' in args:
                    self.assertIn('--onedir', args)
                    self.assertNotIn('--onefile', args)
                    self.assertIn('--noupx', args)
                    folder = Path(args[args.index('--distpath') + 1]) / name
                    (folder / '_internal/nested').mkdir(parents=True)
                    (folder / (name + '.exe')).write_bytes(b'fake executable')
                    (folder / '_internal/VCRUNTIME140.dll').write_bytes(b'runtime DLL')
                    (folder / '_internal/nested/python312.dll').write_bytes(b'Python DLL')
                    builds.append(folder)
                else:
                    executable = Path(args[-1])
                    self.assertEqual(executable.name, name + '.exe')
                    self.assertTrue(executable.is_file())
                    self.assertTrue((executable.parent / '_internal/VCRUNTIME140.dll').is_file())
                return subprocess.CompletedProcess(args, 0)

            with patch.object(module, 'ROOT', root), patch.object(sys, 'platform', 'win32'), \
                 patch.object(module.platform, 'system', return_value='Windows'), \
                 patch.object(module.platform, 'machine', return_value='AMD64'), \
                 patch.object(module.subprocess, 'run', side_effect=command):
                if script == 'build_release':
                    module.build_native(output)
                else:
                    with patch.object(sys, 'argv', ['build_plugins.py', '--native', '--output', str(output)]):
                        module.main()
            self.assertEqual(len(builds), 1)
            archive_path = next(output.glob('*.zip'))
            with zipfile.ZipFile(archive_path) as archive:
                prefix = archive_path.stem + '/'
                self.assertEqual(archive.read(prefix + name + '.exe'), b'fake executable')
                self.assertEqual(archive.read(prefix + '_internal/VCRUNTIME140.dll'), b'runtime DLL')
                self.assertEqual(archive.read(prefix + '_internal/nested/python312.dll'), b'Python DLL')

    def test_compiler_archive_keeps_entire_runtime_folder(self):
        self.package('build_release', 'gs')

    def test_lsp_archive_keeps_entire_runtime_folder(self):
        self.package('build_plugins', 'gs-lsp')


if __name__ == '__main__':
    unittest.main()
