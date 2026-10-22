from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from parser.compiler import CompileError, compile_source
from parser.parser import parse_code
from parser.new_transformer import MyLangTransformer

ROOT = Path(__file__).resolve().parents[1]


class CompilerTests(unittest.TestCase):
    def run_js(self, source, expected):
        js = compile_source(source)
        result = subprocess.run(['node', '--input-type=module'], input=js,
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr + '\n' + js)
        self.assertEqual(result.stdout, expected)
        return js

    def test_functions_precedence_and_legacy_api(self):
        source = '''func add(a int, b int) int { return a + b }
var n int = 2 + 3 * 4
println(add(n, 1), 10.0 - 6.0 / 2.0, 9 % 4)
console.log((2 + 3) * 4, -2 * 3, 2 <= 3 && 3 != 4)'''
        js = self.run_js(source, '15 7 1\n20 -6 true\n')
        self.assertEqual(MyLangTransformer().transform(parse_code(source)), js)

    def test_struct_receiver_defaults_and_reference_semantics(self):
        self.run_js('''type Person struct {
Name string
Age int
Active bool
}
func (p Person) Greet(prefix string) string { return prefix + p.Name }
p := Person{Name: "Sofia"}
copy := p
copy.Age = 29
console.log(p.Greet("Hi "), p.Age, p.Active)
''', 'Hi Sofia 29 false\n')

    def test_objects_spread_arrays_and_callbacks(self):
        self.run_js('''user := {name: "Sofia", age: 28}
updated := {...user, age: 29}
values := []int{1, 2, 3}
doubled := values.map(func(n int) int { return n * 2 })
for i, n := range doubled { console.log(i, n) }
console.log(updated.name, updated["age"], values[0])
''', '0 2\n1 4\n2 6\nSofia 29 1\n')

    def test_loop_forms_and_control(self):
        self.run_js('''for i := 0; i < 4; i++ {
if i == 1 { continue }
if i == 3 { break }
console.log(i)
}
var j int = 0
for (let k int = 0; k < 2; k = k + 1) { j += k }
for (j < 3) { j++ }
for { break }
for i := range []string{"x", "y"} { console.log(i) }
console.log(j)
''', '0\n2\n0\n1\n3\n')

    def test_async_and_error_handling(self):
        self.run_js('''async func load(url string) string {
r := await fetch(url)
return await r.text()
}
console.log(await load("data:text/plain,hello"))
try { throw new Error("oops") } catch (err) { console.log(err.message) }
''', 'hello\noops\n')

    def test_import_forms(self):
        self.run_js('''import path from "node:path"
import { basename as base, extname } from "node:path"
import * as paths from "node:path"
import "node:fs"
console.log(base("/tmp/a.gos"), extname("a.gos"), path.sep == paths.sep)
''', 'a.gos .gos true\n')

    def test_multiline_and_comments(self):
        self.run_js('''// comments and trailing commas
values := []int{
1,
2,
}
/* comment */
obj := {
values,
"label": "ok",
}
if false { console.log("bad") }
else if true { console.log(obj.label, obj.values.length) }
''', 'ok 2\n')

    def test_scopes(self):
        self.run_js('''n := 1
if true { n := "local"; console.log(n) }
console.log(n)
''', 'local\n1\n')

    def test_zero_values_and_const_members(self):
        self.run_js('''var s string
var n int
var b bool
const o = {n: 1}
o.n = 2
console.log(s == "", n, b, o.n)
''', 'true 0 false 2\n')

    def test_condition_loop_and_immediate_callback(self):
        self.run_js("""ready := true
for ready { ready = false }
console.log(func(n int) int { return n * 2 }(3))
""", '6\n')

    def test_receiver_capture(self):
        self.run_js('''type P struct { Name string }
func (p P) Greet() string {
func inner() string { return p.Name }
return inner()
}
p := P{Name: "Sofia"}
console.log(p.Greet())
''', 'Sofia\n')

    def test_diagnostics(self):
        cases = [
            ('var n int = "bad"', 'type mismatch'),
            ('func f(n int) { n := 1 }', 'duplicate'),
            ('import path from "node:path"\npath := 1', 'duplicate'),
            ('n := 1\nn = "bad"', 'type mismatch'),
            ('const n = 1\nn++', 'constant'),
            ('const n = 1\nn = 2', 'constant'),
            ('n := 1\nn := 2', 'duplicate'),
            ('var n Mystery = 1', 'unknown type'),
            ('func f(n int) int { return n }\nf("bad")', 'type mismatch'),
            ('func f(n int) int { return n }\nf()', 'arguments'),
            ('func f() string { return 1 }', 'type mismatch'),
            ('func f() int { return }', 'type mismatch'),
            ('func f() { await f() }', 'async'),
            ('return 1', 'outside function'),
            ('break', 'outside loop'),
            ('continue', 'outside loop'),
            ('type P struct { Name string }\np := P{Name: 1}', 'type mismatch'),
            ('type P struct { Name string }\np := P{Age: 1}', 'unknown field'),
            ('p := Missing{}', 'unknown struct'),
            ('for i := range 42 {}', 'arrays only'),
            ('if 1 {}', 'type mismatch'),
            ('n := []int{1, "bad"}', 'type mismatch'),
            ('a := "x" - "y"', 'operator'),
            ('a := 1 @ 2', 'unexpected character'),
            ('func f() {', 'expected'),
            ('go f()', 'not supported'),
        ]
        for source, message in cases:
            with self.subTest(source=source), self.assertRaisesRegex(CompileError, message):
                compile_source(source)

    def test_examples(self):
        expected = {
            'main.gos': 'Hello, Sofia\nHello, Sofia\n0 2\n1 4\n2 6\nSofia 29\n',
            'hello.gos': 'Hello, World\n',
            'vars.gos': 'Sofia 3\n',
            'import.gos': 'main.gos .gos\n',
            'async.gos': 'Hello async\n',
        }
        for path in sorted((ROOT / 'examples').glob('*.gos')):
            with self.subTest(path=path.name):
                self.run_js(path.read_text(), expected[path.name])

    def test_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'nested' / 'main.mjs'
            result = subprocess.run([sys.executable, str(ROOT / 'main.py'),
                                     str(ROOT / 'examples/hello.gos'), '-o', str(output)],
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run(['node', str(output)], text=True, capture_output=True)
            self.assertEqual(result.stdout, 'Hello, World\n')
            self.assertEqual(result.returncode, 0, result.stderr)
            source = Path(directory) / 'bad.gos'
            source.write_text('var n int = "bad"')
            output.unlink()
            result = subprocess.run([sys.executable, str(ROOT / 'main.py'), str(source), '-o', str(output)],
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('line 1: type mismatch', result.stderr)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
