"""Language contracts: generated modules must execute, invalid programs must fail."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from gscript import CompileError, compile_source
from gscript.project import build_project

ROOT = Path(__file__).resolve().parents[1]


class LanguageTests(unittest.TestCase):
    def run_js(self, source, expected):
        javascript = compile_source(source)
        result = subprocess.run(['node', '--input-type=module'], input=javascript,
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr + '\n' + javascript)
        self.assertEqual(result.stdout, expected)

    def test_default_import_named_side(self):
        self.run_js('''import side from "node:path"
console.log(side.basename("/tmp/main.gos"))
''', 'main.gos\n')

    def test_function_aliases_and_shadowing(self):
        self.run_js('''func f(n int) int { return n + 1 }
first := f
if true {
  f := func(s string) string { return s.toUpperCase() }
  console.log(f("local"))
}
console.log(first(2))
''', 'LOCAL\n3\n')

    def test_nested_hoisting_and_mutual_recursion(self):
        self.run_js('''func test() bool {
  func even(n int) bool {
    if n == 0 { return true }
    return odd(n - 1)
  }
  func odd(n int) bool {
    if n == 0 { return false }
    return even(n - 1)
  }
  return even(6)
}
console.log(test())
''', 'true\n')

    def test_grouped_params_and_function_types(self):
        self.run_js('''func add(a, b int) int { return a + b }
func apply(n int, f func(int) int) int { return f(n) }
var double func(int) int = func(n int) int { return n * 2 }
console.log(add(2, 3), apply(4, double))
''', '5 8\n')

    def test_receiver_binding_and_shadowing(self):
        self.run_js('''type P struct { Name string }
func (p P) Test() string {
  if true { p := {Name: "local"}; console.log(p.Name) }
  func inner() string { return p.Name }
  return inner()
}
p := P{Name: "outer"}
console.log(p.Test())
''', 'local\nouter\n')

    def test_method_alias_signature(self):
        self.run_js('''type P struct { Name string }
func (p P) Add(a int, b int) int { return a + b }
p := P{}
add := p.Add
console.log(add(2, 3))
''', '5\n')

    def test_struct_hoisting_and_generated_names(self):
        self.run_js('''p := P{Name: "Sofia"}
type P struct { Name string }
console.log(p.Name)
var __gscript0 string = "safe"
type Other struct { Value string = __gscript0 }
x := Other{}
console.log(x.Value)
''', 'Sofia\nsafe\n')

    def test_prototype_keys(self):
        self.run_js('''o := {__proto__: "ordinary"}
type S struct { __proto__ string }
s := S{__proto__: "field"}
console.log(o.__proto__, s.__proto__)
''', 'ordinary field\n')

    def test_builtin_alias_can_be_shadowed(self):
        self.run_js('''func printf(s string) string { return "custom " + s }
console.log(printf("value"))
''', 'custom value\n')

    def test_object_shapes_and_spreads(self):
        self.run_js('''one := {name: "Sofia", count: 1}
two := {...one, count: 2}
two.count += 1
var dynamic object = two
key := "name"
console.log(two.count, dynamic[key])
''', '3 Sofia\n')

    def test_array_method_results(self):
        self.run_js('''values := []int{1, 2, 3}
selected := values.filter(func(n int) bool { return n > 1 })
values.push(4)
console.log(selected.join(","), values.length)
console.log(values.some(func(n int) bool { return n == 4 }))
''', '2,3 4\ntrue\n')

    def test_multiline_expressions_and_callback_bodies(self):
        self.run_js('''values := []int{1, 2}
result := values.map(func(n int) int {
  doubled := n *
    2
  return doubled
})
console.log(
  result[0],
  result[1],
)
''', '2 4\n')

    def test_comment_newlines_separate_statements(self):
        self.run_js('''a := 1 /* a comment
with a newline */ b := 2
console.log(a, b)
''', '1 2\n')

    def test_escapes_and_numeric_normalization(self):
        self.run_js(r'''o := {"\u{1f600}": "\x41"}
console.log(o["\ud83d\ude00"], 00012, 001.5)
''', 'A 12 1.5\n')

    def test_exhaustive_return_paths(self):
        self.run_js('''func choose(n int) string {
if n > 0 { return "positive" } else { return "other" }
}
func viaLoop() int { for { return 4 } }
func viaCatch() string {
try { throw new Error("x") } catch err { return "caught" }
}
console.log(choose(1), viaLoop(), viaCatch())
''', 'positive 4 caught\n')

    def test_dynamic_js_boundary(self):
        self.run_js('''var dynamic any = {answer: 42}
console.log(dynamic.answer)
console.log(globalThis.JSON.stringify({ok: true}))
''', '42\n{"ok":true}\n')

    def test_type_and_scope_errors(self):
        cases = [
            ('console.log(missing)', 'undefined name'),
            ('missing = 1', 'undefined name'),
            ('console.log(later)\nlater := 1', 'undefined name'),
            ('func f() int { if true { return 1 } }', 'missing return'),
            ('func f() int { for { break } }', 'missing return'),
            ('func f() { return 1 }', 'type mismatch'),
            ('func f(n int) int { return n }\nalias := f\nalias("bad")', 'type mismatch'),
            ('func f(n int) int { return n }\nif true { f := 1; f(2) }', 'not callable'),
            ('type P struct {}\nfunc (p P) F(n int) int { return n }\np := P{}\np.F("bad")', 'type mismatch'),
            ('type P struct {}\np := P{}\np.Unknown()', 'unknown field or method'),
            ('o := {age: 1}\no.age = "bad"', 'type mismatch'),
            ('o := {age: 1}\nconsole.log(o.agge)', 'unknown property'),
            ('o := {age: 1}\nconsole.log(o["agge"])', 'unknown property'),
            ('a := []int{1}\na[0] = "bad"', 'type mismatch'),
            ('a := []int{1}\na["x"]', 'type mismatch'),
            ('a := []int{1}\na.length = 0', 'read-only'),
            ('s := "hello"\ns[0] = "x"', 'read-only'),
            ('a := []int{1}\na.map(func(n string) int { return 1 })', 'type mismatch'),
            ('a := []int{1}\nb := a.map(func(n int) int { return n })\nb[0] = "bad"', 'type mismatch'),
            ('a := []int{1}\na.filter(func(n int) int { return n })', 'type mismatch'),
            ('a := []int{1}\na.push("bad")', 'type mismatch'),
            ('a := []int{1}\na.map(3)', 'callback'),
            ('a := []int{1}\na.map(func(n int) {})', 'return a value'),
            ('a := []int{..."bad"}', 'spread'),
            ('a := {...1}', 'spread'),
            ('console.log(...1)', 'iterable'),
            ('a := []int{1}\na.push(...1)', 'iterable'),
            ('console.log(true + false)', 'operator'),
            ('console.log(!1)', 'type mismatch'),
            ('console.log(1 && true)', 'type mismatch'),
            ('console.log("x" < 1)', 'type mismatch'),
            ('console.log(1 == "1")', 'cannot compare'),
            ('var n int = nil', 'type mismatch'),
            ('var n void', 'void'),
            ('func f(n void) {}', 'void'),
            ('type P struct { N void }', 'void'),
            ('func f() {}\nx := f()', 'void'),
            ('var callback func(int) int = func(n string) int { return 1 }', 'type mismatch'),
            ('if true { export var n int = 1 }', 'module scope'),
            ('if true { import "node:fs" }', 'module scope'),
            ('if true { type P struct {} }', 'module scope'),
            ('type P struct { X string = await fetch("data:,x") }', 'async'),
            ('type P struct {}\np := new P(1)', 'field object'),
            ('new NotDefined()', 'undefined name'),
            ('var eval int = 1', 'reserved'),
            (r'console.log("\01")', 'octal'),
            (r'console.log("\u{110000}")', 'invalid Unicode'),
        ]
        for source, message in cases:
            with self.subTest(source=source), self.assertRaisesRegex(CompileError, message):
                compile_source(source)

    def test_compiler_instances_do_not_share_state(self):
        from gscript import Compiler, parse_code
        compiler = Compiler()
        self.assertEqual(compiler.compile(parse_code('n := 1')), compile_source('n := 1'))
        self.assertEqual(compiler.compile(parse_code('n := 2')), compile_source('n := 2'))


class ProjectTests(unittest.TestCase):
    def cli(self, *args):
        return subprocess.run([sys.executable, '-m', 'gscript', *map(str, args)],
                              cwd=ROOT, text=True, capture_output=True, timeout=10)

    def test_documented_module_example(self):
        with tempfile.TemporaryDirectory() as directory:
            output = build_project(ROOT / 'examples/modules/main.gos', directory)
            result = subprocess.run(['node', str(output)], text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, 'Hello, Sofia 42\n')

    def test_export_and_local_module_graph(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'lib').mkdir()
            (root / 'lib/math.gos').write_text('export func twice(n int) int { return n * 2 }')
            (root / 'lib/message.gos').write_text('export const label string = "answer"')
            (root / 'lib/person.gos').write_text('export type P struct { Name string }\nfunc (p P) Greet() string { return p.Name }')
            entry = root / 'app.gos'
            entry.write_text('''import { twice } from "./lib/math.gos"
import { label } from "./lib/message.gos"
import { P } from "./lib/person.gos"
p := new P({Name: "Sofia"})
console.log(label, twice(21), p.Greet())
''')
            output = root / 'build'
            result = self.cli(entry, '--out-dir', output)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(list(output.rglob('*.mjs'))), 4)
            result = subprocess.run(['node', str(output / 'app.mjs')], text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, 'answer 42 Sofia\n')
            original = (output / 'app.mjs').read_text()
            self.assertEqual(self.cli(entry, '--out-dir', output).returncode, 0)
            self.assertEqual((output / 'app.mjs').read_text(), original)

    def test_cyclic_imports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a.gos').write_text('import { b } from "./b.gos"\nexport func a() int { return 1 }\nconsole.log(b())')
            (root / 'b.gos').write_text('import { a } from "./a.gos"\nexport func b() int { return a() + 1 }')
            output = build_project(root / 'a.gos', root / 'build')
            result = subprocess.run(['node', str(output)], text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, '2\n')

    def test_failed_graph_preserves_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entry = root / 'main.gos'
            entry.write_text('import { f } from "./lib.gos"\nconsole.log(f())')
            (root / 'lib.gos').write_text('export func f() int { return "wrong" }')
            output = root / 'build'
            output.mkdir()
            target = output / 'main.mjs'
            target.write_text('existing output')
            result = self.cli(entry, '--out-dir', output)
            self.assertEqual(result.returncode, 1)
            self.assertIn('lib.gos: line 1', result.stderr)
            self.assertEqual(target.read_text(), 'existing output')
            self.assertFalse((output / 'lib.mjs').exists())

    def test_root_and_missing_modules(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'src').mkdir()
            (root / 'lib.gos').write_text('export const n = 1')
            entry = root / 'src/main.gos'
            entry.write_text('import { n } from "../lib.gos"\nconsole.log(n)')
            result = self.cli(entry, '--out-dir', root / 'build')
            self.assertEqual(result.returncode, 1)
            self.assertIn('outside project root', result.stderr)
            result = self.cli(entry, '--out-dir', root / 'build', '--root', root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((root / 'build/src/main.mjs').exists())
            entry.write_text('import "./missing.gos"')
            self.assertIn('module not found', self.cli(entry, '--out-dir', root / 'build').stderr)

    def test_check_and_source_protection(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'input.gos'
            source.write_text('n := 1')
            result = self.cli(source, '--check')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, '')
            result = self.cli(source, '-o', source)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(source.read_text(), 'n := 1')
            alias = Path(directory) / 'alias.mjs'
            alias.symlink_to(source)
            self.assertEqual(self.cli(source, '-o', alias).returncode, 1)
            self.assertEqual(source.read_text(), 'n := 1')

    def test_cli_error_location_and_version(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'input.gos'
            source.write_text('n := 1\nconsole.log(@)')
            result = self.cli(source)
            self.assertEqual(result.returncode, 1)
            self.assertIn('line 2:13', result.stderr)
            self.assertIn('console.log(@)', result.stderr)
            self.assertIn('^', result.stderr)
        self.assertEqual(self.cli('--version').stdout, 'gscript 0.4.0\n')


if __name__ == '__main__':
    unittest.main()
