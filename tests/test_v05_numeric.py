import subprocess
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from gscript import compile_source, CompileError


class NumericAndBuiltinTests(unittest.TestCase):
    def test_strict_numeric_rules_everywhere(self):
        invalid=[
            'var x int = 1.5', 'var x float = 1', 'var x float64 = 2',
            'a := 1\nb := 2.0\nprintln(a+b)', 'println(1 < 1.0)',
            'func f(n int) {}\nf(1.1)', 'func f() int { return 1.1 }',
            'a := []int{1,2.0}', 'a := []float{1.0}\na.push(2)',
            'type A struct { X int }\na := A{X:1.5}',
            'func f<T>(x T) T { return x }\nvar x int = f<float>(1.5)',
            'var x int = 3 / 2', 'var x int|string = 1.5', 'a := []int{1}\nprintln(a[0.0])',
        ]
        for source in invalid:
            with self.subTest(source=source),self.assertRaises(CompileError):compile_source(source)

    def test_explicit_conversions_and_no_numeric_runtime_wrappers(self):
        source='a := 10\nb := float(a)\nvar c float64 = 10.0\nprintln(a, b+c, int(3.9), len([]int{1,2}), len("abc"))'
        with patch('subprocess.Popen',side_effect=AssertionError('GS must check natively')):
            js=compile_source(source)
        self.assertNotIn('BigInt',js)
        self.assertNotIn('typeof',js)
        self.assertNotIn('class ',js)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'main.mjs';p.write_text(js)
            result=subprocess.run(['node',str(p)],capture_output=True,text=True,check=True)
        self.assertEqual(result.stdout,'10 20 3 2 3\n')

    def test_builtin_shadowing_and_formatting(self):
        js=compile_source('func println(x int) int { return x+1 }\nconsole.log(println(2))\nprintf("%s %d", "hello", 3)')
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'main.mjs';p.write_text(js)
            result=subprocess.run(['node',str(p)],capture_output=True,text=True,check=True)
        self.assertEqual(result.stdout,'3\nhello 3\n')
        for source in ('len(2)','printf(2)','int("3")','float()'):
            with self.subTest(source=source),self.assertRaises(CompileError):compile_source(source)

    def test_number_boundary_does_not_narrow_implicitly(self):
        compile_source('var n number = 1\nvar f number = 1.5')
        for source in ('var n number = 1\nvar i int = n','var n number = 1.0\nvar f float = n'):
            with self.assertRaises(CompileError):compile_source(source)
