import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import test_v05_cli
from gscript.project import Project
from gscript.lint import lint_project
from gscript.tools import initialize

ROOT=Path(__file__).resolve().parents[1]


class ToolTests(unittest.TestCase):
    run_cli=test_v05_cli.SimpleCLITests.run_cli
    def test_formatter_check_and_safe_lint_fix(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);entry=root/'main.gs';entry.write_text('var unused int = 3  \nif true{println(1)}\n')
            self.assertEqual(self.run_cli(root,'fmt','--check').returncode,1)
            self.assertEqual(self.run_cli(root,'fmt').returncode,0)
            self.assertEqual(self.run_cli(root,'fmt','--check').returncode,0)
            entry.write_text('var unused int = 3  \nif true { println(1) }\n')
            diagnostics=json.loads(self.run_cli(root,'lint','--json').stdout)
            self.assertTrue({'GS1001','GS1004','GS1012'} <= {d['code'] for d in diagnostics})
            self.assertEqual(self.run_cli(root,'lint','--fix').returncode,0)
            self.assertNotIn('  \n',entry.read_text())
            entry.write_text('var n int = 3.5')
            result=self.run_cli(root,'lint','--json')
            self.assertEqual(result.returncode,1)
            self.assertEqual(json.loads(result.stdout)[0]['severity'],'error')

    def test_init_templates_and_no_overwrite(self):
        with tempfile.TemporaryDirectory(prefix='.gs-template-',dir=ROOT) as d:
            root=Path(d)
            for template in ('node','browser','phaser'):
                folder=root/template;initialize(folder,template)
                for file in ('main.gs','package.json','gsconfig.json','.gitignore'):self.assertTrue((folder/file).is_file())
                Project(folder/'main.gs',typescript=ROOT/'node_modules/typescript',prepare_output=False).check()
            before=(root/'node/main.gs').read_text()
            self.assertEqual(self.run_cli(root/'node','init').returncode,1)
            self.assertEqual((root/'node/main.gs').read_text(),before)

    def test_unreachable_shadowing_and_redundant_conversion(self):
        with tempfile.TemporaryDirectory() as d:
            entry=Path(d)/'main.gs'
            entry.write_text('n := 3\nif true { n := 4; println(n) }\nfunc f() int { return int(3); println("unreachable") }\nprintln(n,f())')
            codes={d.code for d in lint_project(Project(entry,analysis_info=True).check())}
            self.assertTrue({'GS1003','GS1005','GS1007'}<=codes,codes)

    def test_typed_standard_apis_and_native_gs_rejection(self):
        with tempfile.TemporaryDirectory() as d:
            entry=Path(d)/'main.gs'
            entry.write_text('body := document.querySelector("body")\nbody?.appendChild(document.createElement("p"))')
            Project(entry,libraries=['es2022','dom'],typescript=ROOT/'node_modules/typescript',prepare_output=False).check()
            entry.write_text('document.querySelector(3)')
            from gscript import CompileError
            with self.assertRaisesRegex(CompileError,'type mismatch'):Project(entry,libraries=['es2022','dom'],typescript=ROOT/'node_modules/typescript',prepare_output=False).check()

    def test_typed_collections_node_worker_and_deprecated(self):
        from gscript import CompileError
        with tempfile.TemporaryDirectory(prefix='.gs-api-',dir=ROOT) as d:
            root=Path(d);entry=root/'main.gs'
            def check(source,libraries):
                entry.write_text(source)
                return Project(entry,libraries=libraries,typescript=ROOT/'node_modules/typescript',prepare_output=False,analysis_info=True).check()
            check('values := new Map<string,int>()\nvalues.set("a",1)\nprintln(values.get("a"),len(values))',['es2022'])
            with self.assertRaises(CompileError):check('values := new Map<string,int>()\nvalues.set("a",1.5)',['es2022'])
            check('println(process.cwd())',['node'])
            check('postMessage("ready")',['webworker'])
            (root/'old.ts').write_text('/** @deprecated use replacement */\nexport function old(value:number):number{return value}')
            project=check('import { old } from "./old.ts"\nprintln(old(1))',[])
            self.assertIn('GS1008',{d.code for d in lint_project(project)})
