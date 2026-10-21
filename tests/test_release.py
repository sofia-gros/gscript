"""Release gates: link errors and real JS/MJS/TypeScript execution."""
import json
import random
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from gscript import CompileError, compile_source
from gscript.project import Project, build_project

ROOT = Path(__file__).resolve().parents[1]
TSC = ROOT / 'node_modules/typescript/bin/tsc'


class ReleaseTests(unittest.TestCase):
    def cli(self, *args):
        return subprocess.run([sys.executable, '-m', 'gscript', *map(str, args)],
                              cwd=ROOT, text=True, capture_output=True, timeout=15)

    def node(self, path):
        result = subprocess.run(['node', str(path)], text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def typescript(self, entry, out_dir):
        self.assertTrue(TSC.is_file(), 'npm ci is required: TypeScript output tests must not be skipped')
        result = subprocess.run(['node', str(TSC), str(entry), '--strict', '--target', 'ES2022',
                                 '--module', 'NodeNext', '--moduleResolution', 'NodeNext',
                                 '--typeRoots', str(ROOT / 'node_modules/@types'),
                                 '--outDir', str(out_dir)], text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        (Path(out_dir) / 'package.json').write_text('{"type":"module"}')
        return Path(out_dir) / entry.with_suffix('.js').name

    def test_all_output_formats_execute_the_same_module_graph(self):
        fixture = ROOT / 'tests/fixtures/modules/main.gs'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for format in ('js', 'mjs', 'ts'):
                with self.subTest(format=format):
                    output = build_project(fixture, root / format, format=format)
                    if format == 'ts':
                        self.assertIn('Name', output.read_text())
                        output = self.typescript(output, root / 'typescript-js')
                    self.assertEqual(self.node(output), 'Hello, Sofia Hello, GS answer 42 4\n')

    def test_typescript_preserves_dynamic_js_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'main.gs'
            source.write_text('''import { basename } from "node:path"
console.log(Math.max("2", "3"), new Error(42).message, basename("/tmp/file"))
''')
            output = build_project(source, root / 'out', format='ts')
            js = self.typescript(output, root / 'js')
            self.assertEqual(self.node(js), '3 42 file\n')

    def test_all_examples_in_every_format(self):
        expected = {'hello.gs': 'Hello, GS\n', 'main.gos': 'Hello, Sofia\nHello, Sofia\n0 2\n1 4\n2 6\nSofia 29\n',
                    'hello.gos': 'Hello, World\n', 'vars.gos': 'Sofia 3\n',
                    'import.gos': 'main.gos .gos\n', 'async.gos': 'Hello async\n'}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for fixture in sorted(p for p in (ROOT / 'examples').iterdir() if p.suffix in ('.gs', '.gos')):
                for format in ('js', 'mjs', 'ts'):
                    with self.subTest(source=fixture.name, format=format):
                        output = build_project(fixture, root / fixture.stem / format, format=format)
                        if format == 'ts':
                            output = self.typescript(output, root / fixture.stem / 'ts-js')
                        self.assertEqual(self.node(output), expected[fixture.name])

    def test_block_scoped_closures_are_checked_in_their_own_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'main.gs'
            source.write_text('''if true {
  local := "captured"
  callback := func() string { return local }
  console.log(callback())
}
''')
            self.assertEqual(self.node(build_project(source, root / 'out')), 'captured\n')

    def test_default_exported_class_is_a_type(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'model.gs').write_text('type P struct { Name string }\nexport default P')
            (root / 'main.gs').write_text('import User from "./model.gs"\nfunc name(p User) string { return p.Name }\nconsole.log(name(User{Name: "Sofia"}))')
            self.assertEqual(self.node(build_project(root / 'main.gs', root / 'out')), 'Sofia\n')

    def test_fileless_api_does_not_silently_skip_local_module_checks(self):
        with self.assertRaisesRegex(CompileError, 'source path'):
            compile_source('import { f } from "./model.gs"\nf("bad")')

    def test_explicit_any_is_not_overwritten_by_grouped_parameter_types(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'main.gs'
            source.write_text('func echo(value any, n int) string { return value }\nconsole.log(echo("ok", 1))')
            output = build_project(source, root / 'out', format='ts')
            js = self.typescript(output, root / 'js')
            self.assertEqual(self.node(js), 'ok\n')

    def test_excessive_nesting_is_a_compile_error_not_a_traceback(self):
        with self.assertRaisesRegex(CompileError, 'capacity'):
            compile_source('(' * 5000 + '1' + ')' * 5000)

    def test_malformed_input_does_not_crash_the_compiler(self):
        rng = random.Random(20261021)
        tokens = ['func', 'var', 'const', 'type', 'struct', 'export', 'default', 'import',
                  'if', 'else', 'for', 'return', 'async', 'await', 'new', 'catch', 'try',
                  'n', 'int', 'string', 'any', '1', '"x"', '{', '}', '(', ')', '[', ']',
                  ':=', '=', ',', ';', '\n', '+', '*', '.', '...']
        for _ in range(5000):
            source = ' '.join(rng.choices(tokens, k=rng.randrange(1, 45)))
            try:
                compile_source(source)
            except CompileError:
                pass

    def test_module_type_errors_do_not_become_any(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / 'model.gs'
            model.write_text('export func f(n int) int { return n }\nexport type P struct { Name string }\nfunc (p P) F(n int) int { return n }\nexport const n int = 1')
            cases = [
                ('import { f } from "./model.gs"\nf("bad")', 'type mismatch'),
                ('import { missing } from "./model.gs"', 'has no export'),
                ('import missing from "./model.gs"', 'has no export'),
                ('import * as m from "./model.gs"\nm.missing()', 'has no export'),
                ('import { P as User } from "./model.gs"\np := User{Name: 1}', 'type mismatch'),
                ('import { P } from "./model.gs"\np := P{Name: "Sofia"}\np.F("bad")', 'type mismatch'),
                ('import * as m from "./model.gs"\np := new m.P({Name: 1})', 'type mismatch'),
                ('import { n } from "./model.gs"\nn = 2', 'constant'),
                ('import { n } from "./model.gs"\nvar s string = n', 'type mismatch'),
            ]
            for source, message in cases:
                with self.subTest(source=source):
                    entry = root / 'main.gs'
                    entry.write_text(source)
                    with self.assertRaisesRegex(CompileError, message):
                        build_project(entry, root / 'out')
                    self.assertFalse((root / 'out').exists())
                    check = self.cli(entry, '--check')
                    self.assertEqual(check.returncode, 1)
                    self.assertIn(message, check.stderr)

    def test_nominal_structs_from_different_modules_are_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a.gs').write_text('export type P struct { Name string }\nexport func f(p P) string { return p.Name }')
            (root / 'b.gs').write_text('export type P struct { Name string }')
            (root / 'main.gs').write_text('import { P, f } from "./a.gs"\nimport { P as Other } from "./b.gs"\nf(Other{Name: "bad"})')
            with self.assertRaisesRegex(CompileError, 'type mismatch'):
                build_project(root / 'main.gs', root / 'out')

    def test_cyclic_top_level_value_initialization_is_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a.gs').write_text('import { b } from "./b.gs"\nexport const a int = b')
            (root / 'b.gs').write_text('import { a } from "./a.gs"\nexport const b int = a')
            with self.assertRaisesRegex(CompileError, 'before initialization'):
                build_project(root / 'a.gs', root / 'out')
            self.assertFalse((root / 'out').exists())

    def test_colliding_source_extensions_fail_before_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a.gs').write_text('import "./a.gos"')
            (root / 'a.gos').write_text('console.log("legacy")')
            with self.assertRaisesRegex(CompileError, 'collision'):
                build_project(root / 'a.gs', root / 'out')
            self.assertFalse((root / 'out').exists())

    def test_cross_module_closure_and_cycle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a.gs').write_text('import { f } from "./b.gs"\nexport const n int = 2\nconsole.log(f())')
            (root / 'b.gs').write_text('import { n } from "./a.gs"\nexport func f() int { return n + 1 }')
            output = build_project(root / 'a.gs', root / 'out')
            self.assertEqual(self.node(output), '3\n')

    def test_cli_format_selection_and_conflicts(self):
        fixture = ROOT / 'examples/hello.gos'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for format in ('js', 'mjs', 'ts'):
                output = root / format / ('hello.' + format)
                result = self.cli(fixture, '--format', format, '-o', output)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(output.exists())
            self.assertEqual(self.cli(fixture, '--format', 'bad').returncode, 2)
            self.assertEqual(self.cli(fixture, '--format', 'js', '-o', root / 'wrong.ts').returncode, 2)
            self.assertFalse((root / 'wrong.ts').exists())
            result = self.cli(fixture, '-o', root / 'auto.js')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.node(root / 'auto.js'), 'Hello, World\n')

    def test_commonjs_package_is_not_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / 'package.json'
            marker.write_text('{"type":"commonjs","name":"keep-me"}')
            target = root / 'hello.js'
            target.write_text('existing')
            result = self.cli(ROOT / 'examples/hello.gos', '--format', 'js', '-o', target)
            self.assertEqual(result.returncode, 1)
            self.assertIn('ES module output', result.stderr)
            self.assertEqual(target.read_text(), 'existing')
            self.assertEqual(json.loads(marker.read_text())['type'], 'commonjs')

    def test_project_can_emit_multiple_formats_repeatably(self):
        project = Project(ROOT / 'tests/fixtures/modules/main.gs').check()
        module = project.modules[project.entry]
        before = project.emit(module, 'mjs')
        ts = project.emit(module, 'ts')
        self.assertIn('model.js', ts)
        self.assertEqual(project.emit(module, 'mjs'), before)

    def test_default_export_and_anonymous_callback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'f.gs').write_text('export default func(n int) int { return n + 1 }')
            (root / 'main.gs').write_text('import f from "./f.gs"\nconsole.log(f(2))')
            output = build_project(root / 'main.gs', root / 'out')
            self.assertEqual(self.node(output), '3\n')
            (root / 'main.gs').write_text('import f from "./f.gs"\nf("bad")')
            with self.assertRaisesRegex(CompileError, 'type mismatch'):
                build_project(root / 'main.gs', root / 'out')


if __name__ == '__main__':
    unittest.main()
