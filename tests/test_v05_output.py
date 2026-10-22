import subprocess
import unittest
from gscript import compile_source


class ReadableOutputTests(unittest.TestCase):
    def test_names_precedence_and_comments(self):
        source='''// greeting
func greet(name string) string {
  // body
  return "Hello, " + name
}
name := "Sofia"
println(greet(name))
println(1 - (2 - 3), (1 + 2) * 3, -(-3), 1 + (2 + 3))
// end'''
        js=compile_source(source)
        self.assertIn('function greet(name)',js)
        self.assertIn('return "Hello, " + name;',js)
        self.assertIn('console.log(greet(name));',js)
        self.assertIn('1 - (2 - 3)',js)
        for comment in ('// greeting','// body','// end'):self.assertEqual(js.count(comment),1)
        result=subprocess.run(['node','--input-type=module'],input=js,capture_output=True,text=True,check=True)
        self.assertEqual(result.stdout,'Hello, Sofia\n2 9 3 6\n')

    def test_pretty_output_preserves_shadow_initializer_semantics(self):
        js=compile_source('n := 3\nif true { n := n + 1; println(n) }\nprintln(n)')
        result=subprocess.run(['node','--input-type=module'],input=js,capture_output=True,text=True,check=True)
        self.assertEqual(result.stdout,'4\n3\n')

    def test_erased_export_comment_does_not_leave_orphan_export(self):
        js=compile_source('export /* erased type */ type X = int\nprintln(3)')
        result=subprocess.run(['node','--input-type=module'],input=js,capture_output=True,text=True,check=True)
        self.assertEqual(result.stdout,'3\n')
        self.assertIn('/* erased type */',js)
