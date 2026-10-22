import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class SimpleCLITests(unittest.TestCase):
    def run_cli(self,root,*args):
        return subprocess.run([sys.executable,'-m','gscript',*args],cwd=root,env={**os.environ,'PYTHONPATH':str(ROOT)},capture_output=True,text=True,timeout=30)

    def test_file_and_project_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'main.gs'
            source.write_text('func f(n int) int { return n+1 }\nprintln(f(2))')
            result=self.run_cli(root,'main.gs')
            self.assertEqual(result.returncode,0,result.stderr)
            output=root/'dist/main.js'
            self.assertIn('return n + 1;',output.read_text())
            result=self.run_cli(root,'.')
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('return n+1;',output.read_text())
            self.assertEqual(subprocess.check_output(['node',str(output)],text=True),'3\n')
            result=self.run_cli(root,'.','--no-minify')
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('return n + 1;',output.read_text())

    def test_configuration_entry_and_auto_dependencies(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'gsconfig.json').write_text(json.dumps({'entry':'start.gs','outDir':'output','format':'mjs'}))
            (root/'start.gs').write_text('import { f } from "./lib.gs"\nprintln(f(3))')
            (root/'lib.gs').write_text('export func f(n int) int { return n*2 }')
            result=self.run_cli(root,'.')
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(subprocess.check_output(['node',str(root/'output/start.mjs')],text=True),'6\n')
            (root/'lib.gs').write_text('export func f(n int) int { return "bad" }')
            before=(root/'output/start.mjs').read_bytes()
            self.assertNotEqual(self.run_cli(root,'.').returncode,0)
            self.assertEqual((root/'output/start.mjs').read_bytes(),before)

    def test_check_and_overwrite_protection(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);entry=root/'main.gs';entry.write_text('println(3)')
            self.assertEqual(self.run_cli(root,'.','--check').returncode,0)
            self.assertFalse((root/'dist').exists())
            result=self.run_cli(root,'main.gs','-o','main.gs')
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(entry.read_text(),'println(3)')

    def test_minify_preserves_strings_comments_and_operator_boundaries(self):
        from gscript import compile_source
        from gscript.minifier import minify
        code=minify(compile_source('println("http://test/* keep */", 1 + +2, 3 - -2) // remove'))
        self.assertIn('http://test/* keep */',code)
        self.assertNotIn('// remove',code)
        result=subprocess.run(['node','--input-type=module'],input=code,text=True,capture_output=True,check=True)
        self.assertEqual(result.stdout,'http://test/* keep */ 3 5\n')
