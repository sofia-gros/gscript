"""External TypeScript, JSDoc, package resolution, invalidation and runtime tests."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from gscript import CompileError
from gscript.project import Project, build_project

ROOT = Path(__file__).resolve().parents[1]
TS = ROOT / 'node_modules/typescript/lib/typescript.js'


class InteropTests(unittest.TestCase):
    def build(self, entry, out, format='mjs', **options):
        return build_project(entry, out, format=format, typescript=TS, **options)

    def check(self, entry, **options):
        return Project(entry, typescript=TS, **options).check()

    def execute(self, entry):
        result = subprocess.run(['node', str(entry)], text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def transpile_ts(self, entry, output):
        result = subprocess.run(['node', str(TS.parent / 'tsc.js'), str(entry), '--strict',
                                 '--target', 'ES2022', '--module', 'NodeNext', '--moduleResolution',
                                 'NodeNext', '--typeRoots', str(ROOT / 'node_modules/@types'),
                                 '--outDir', str(output)], text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # tsc does not copy existing JavaScript dependencies.
        import shutil
        for source in entry.parent.rglob('*'):
            if source.suffix in ('.js', '.cjs', '.mjs'):
                target = output / source.relative_to(entry.parent)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        (output / 'package.json').write_text('{"type":"module"}')
        return output / entry.with_suffix('.js').name

    def package(self, root):
        package = root / 'node_modules' / '@fixture' / 'math'
        package.mkdir(parents=True)
        (package / 'package.json').write_text(json.dumps({'name': '@fixture/math', 'type': 'module',
            'exports': {'.': {'types': './index.d.ts', 'import': './index.js'}}}))
        (package / 'index.d.ts').write_text('''export function twice(value: number): number;
export function identity<T>(value: T): T;
export class Box { constructor(value: number); value: number; scale(n: number): number; }
''')
        (package / 'index.js').write_text('''export function twice(n) { return n * 2; }
export function identity(value) { return value; }
export class Box { constructor(value) { this.value = value; } scale(n) { return this.value * n; } }
''')
        return package

    def test_local_ts_transitive_graph_and_type_only_exports_in_all_formats(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'helper.ts').write_text('export const factor: number = 2;')
            (root / 'math.ts').write_text('''import { factor } from "./helper.js";
export interface Point { x: number; y: number }
export function twice(n: number): number { return n * factor; }
''')
            (root / 'main.gs').write_text('''import { twice, Point } from "./math.ts"
var p Point = {x: 2, y: 3}
console.log(twice(p.x))
''')
            for format in ('js', 'mjs', 'ts'):
                with self.subTest(format=format):
                    output = self.build(root / 'main.gs', root / format, format)
                    if format == 'ts':
                        output = self.transpile_ts(output, root / 'ts-js')
                    else:
                        self.assertNotIn('Point', output.read_text())
                    self.assertEqual(self.execute(output), '4\n')

    def test_jsdoc_javascript_is_checked_and_copied(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'lib.js').write_text('/** @param {number} n @returns {number} */\nexport function twice(n) { return n * 2; }')
            entry = root / 'main.gs'
            entry.write_text('import { twice } from "./lib.js"\nconsole.log(twice(3))')
            output = self.build(entry, root / 'out')
            self.assertEqual(self.execute(output), '6\n')
            self.assertTrue((root / 'out/lib.mjs').exists())
            entry.write_text('import { twice } from "./lib.js"\ntwice("bad")')
            with self.assertRaisesRegex(CompileError, 'TS2345') as failure:
                self.build(entry, root / 'bad')
            self.assertEqual(Path(failure.exception.filename), entry)
            self.assertEqual(failure.exception.line, 2)
            self.assertFalse((root / 'bad').exists())

    def test_existing_node_modules_types_overloads_generics_and_constructors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.package(root)
            entry = root / 'main.gs'
            entry.write_text('''import { twice, Box, identity } from "@fixture/math"
var box Box = new Box(3)
console.log(twice(box.value), box.scale(2), identity("typed"))
''')
            output = self.build(entry, root / 'out')
            self.assertEqual(self.execute(output), '6 6 typed\n')
            bad = [
                'twice("bad")', 'new Box("bad")', 'identity(2).toUpperCase()',
                'new Box(1).scale("bad")', 'new Box(1).missing()',
                'var n int = identity("bad")',
                'var values []int = []int{identity("bad")}',
                'if identity("bad") { console.log("bad") }',
                'console.log(identity("bad") + 1)',
                'console.log(identity("bad") < 1)',
            ]
            for code in bad:
                with self.subTest(code=code):
                    entry.write_text('import { twice, Box, identity } from "@fixture/math"\n' + code)
                    with self.assertRaises(CompileError):
                        self.build(entry, root / 'bad')
                    self.assertFalse((root / 'bad').exists())

    def test_content_cache_detects_same_size_same_mtime_declaration_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = self.package(root)
            entry = root / 'main.gs'
            entry.write_text('import { twice } from "@fixture/math"\ntwice(1)')
            first = self.check(entry)
            second = self.check(entry)
            self.assertFalse(first.interop_stats['cache_hit'])
            self.assertTrue(second.interop_stats['cache_hit'])
            declaration = package / 'index.d.ts'
            state = declaration.stat()
            declaration.write_text(declaration.read_text().replace('twice(value: number)', 'twice(value: string)'))
            os.utime(declaration, ns=(state.st_atime_ns, state.st_mtime_ns))
            with self.assertRaisesRegex(CompileError, 'TS2345'):
                self.check(entry)

    def test_cache_invalidation_when_missing_module_types_are_added(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'lib.js').write_text('export function f(value) { return value; }')
            entry = root / 'main.gs'
            entry.write_text('import { f } from "./lib.js"\nf(1)')
            self.check(entry)
            self.assertTrue(self.check(entry).interop_stats['cache_hit'])
            (root / 'lib.d.ts').write_text('export function f(value: string): string;')
            with self.assertRaisesRegex(CompileError, 'TS2345'):
                self.check(entry)

    def test_no_cache_and_corrupted_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.package(root)
            entry = root / 'main.gs'
            entry.write_text('import { twice } from "@fixture/math"\ntwice(1)')
            self.assertFalse(self.check(entry, cache=False).interop_stats['cache_hit'])
            self.assertFalse((root / '.gs-cache').exists())
            self.check(entry)
            cache = next((root / '.gs-cache').rglob('*.json'))
            cache.write_text('{broken')
            self.assertFalse(self.check(entry).interop_stats['cache_hit'])

    def test_commonjs_jsdoc_import_keeps_runtime_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'lib.cjs').write_text('/** @param {number} n */\nexports.twice = function(n) { return n * 2; };')
            entry = root / 'main.gs'
            entry.write_text('import lib from "./lib.cjs"\nconsole.log(lib.twice(3))')
            for format in ('mjs', 'ts'):
                output = self.build(entry, root / format, format)
                if format == 'ts':
                    output = self.transpile_ts(output, root / 'ts-js')
                self.assertEqual(self.execute(output), '6\n')

    def test_js_with_declaration_sidecar_compiles_to_typescript(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'lib.js').write_text('export function f(n) { return n * 2; }')
            (root / 'lib.d.ts').write_text('export function f(n: number): number;')
            entry = root / 'main.gs'
            entry.write_text('import { f } from "./lib.js"\nconsole.log(f(2))')
            output = self.build(entry, root / 'out', 'ts')
            self.assertTrue((root / 'out/lib.d.ts').exists())
            self.assertEqual(self.execute(self.transpile_ts(output, root / 'js')), '4\n')

    def test_external_types_flow_through_gs_modules_and_errors_preserve_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.package(root)
            (root / 'lib.gs').write_text('import { Box } from "@fixture/math"\nexport var box Box = new Box(3)')
            entry = root / 'main.gs'
            entry.write_text('import { box } from "./lib.gs"\nconsole.log(box.scale(2))')
            output = self.build(entry, root / 'out')
            self.assertEqual(self.execute(output), '6\n')
            before = output.read_text()
            entry.write_text('import { box } from "./lib.gs"\nbox.scale("bad")')
            with self.assertRaises(CompileError):
                self.build(entry, root / 'out')
            self.assertEqual(output.read_text(), before)

    def test_tsconfig_paths_aliases_are_rewritten_for_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'tsconfig.json').write_text('{"compilerOptions":{"baseUrl":".","paths":{"@local/*":["lib/*.ts"]}}}')
            (root / 'lib').mkdir()
            (root / 'lib/math.ts').write_text('export function f(n: number) { return n * 2; }')
            entry = root / 'main.gs'
            entry.write_text('import { f } from "@local/math"\nconsole.log(f(2))')
            self.assertEqual(self.execute(self.build(entry, root / 'out')), '4\n')

    def test_external_outputs_and_declarations_cannot_overwrite_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'lib.ts').write_text('export function f(n: number) { return n; }')
            entry = root / 'main.gs'
            entry.write_text('import { f } from "./lib.ts"\nf(1)')
            before = (root / 'lib.ts').read_text()
            with self.assertRaisesRegex(CompileError, 'overwrite'):
                self.build(entry, root, 'ts')
            self.assertEqual((root / 'lib.ts').read_text(), before)

    def test_read_only_or_malformed_cache_does_not_break_compilation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.package(root)
            entry = root / 'main.gs'
            entry.write_text('import { twice } from "@fixture/math"\ntwice(1)')
            blocked = root / 'not-a-directory'
            blocked.write_text('preserve')
            self.check(entry, cache_dir=blocked)
            self.assertEqual(blocked.read_text(), 'preserve')
            self.check(entry)
            cache = next((root / '.gs-cache').rglob('*.json'))
            data = json.loads(cache.read_text())
            data['result'] = 3
            cache.write_text(json.dumps(data))
            self.assertFalse(self.check(entry).interop_stats['cache_hit'])

    def test_large_module_chain_does_not_use_python_recursion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(1200):
                (root / f'm{index}.gs').write_text((f'import "./m{index+1}.gs"\n' if index < 1199 else '') + 'const n = 1')
            project = Project(root / 'm0.gs').check()
            self.assertEqual(len(project.modules), 1200)
            self.assertFalse(project.has_external)

    def test_phaser_real_declarations_accept_valid_config_and_reject_wrong_types(self):
        project = Project(ROOT / 'tests/fixtures/interop/phaser.gs').check()
        self.assertTrue(project.has_external)
        with tempfile.TemporaryDirectory(dir=ROOT / 'tests') as directory:
            root = Path(directory)
            source = root / 'bad.gs'
            for code in ('new Phaser.Math.Vector2("bad", 0)',
                         'new Phaser.Game({width: true})',
                         'new Phaser.Scene().missingMethod()',
                         'var config Phaser.Types.Core.GameConfig = {width: true}'):
                with self.subTest(code=code):
                    source.write_text('import Phaser from "phaser"\n' + code)
                    with self.assertRaises(CompileError):
                        Project(source).check()


if __name__ == '__main__':
    unittest.main()
