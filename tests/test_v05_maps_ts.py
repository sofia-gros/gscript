import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from gscript.build import configure,build

ROOT=Path(__file__).resolve().parents[1]
VERSIONS=ROOT/'node_modules'


class SourceMapAndCompilerTests(unittest.TestCase):
    def test_runtime_stack_points_to_original_gs_with_and_without_minify(self):
        for mini in (False,True):
            with self.subTest(minify=mini),tempfile.TemporaryDirectory() as d:
                root=Path(d)
                (root/'lib.gs').write_text('export func fail() {\n  // source map must account for comments\n  throw new Error("gs-boom")\n}\n')
                entry=root/'main.gs';entry.write_text('import { fail } from "./lib.gs"\nfail()\n')
                _,target=build(configure(entry,sourcemap=True,minify=mini))
                result=subprocess.run(['node','--enable-source-maps',str(target)],capture_output=True,text=True)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('lib.gs:3:',result.stderr)
                self.assertIn('main.gs:2:',result.stderr)
                mapping=json.loads((root/'dist/lib.js.map').read_text())
                self.assertEqual(mapping['version'],3)
                self.assertIn('throw new Error',mapping['sourcesContent'][0])

    def test_official_59_60_70_adapters_and_composed_maps(self):
        paths=[VERSIONS/'typescript',VERSIONS/'typescript60',VERSIONS/'typescript70']
        if not all(p.exists() for p in paths):self.skipTest('official version matrix is installed by release CI')
        for package in paths:
            with self.subTest(package=package.name),tempfile.TemporaryDirectory() as d:
                root=Path(d);entry=root/'main.gs'
                entry.write_text('func fail() {\n  throw new Error("official-ts")\n}\nfail()\n')
                _,target=build(configure(entry,ts_compiler='ts',typescript=package,sourcemap=True,minify=True,format='mjs'))
                result=subprocess.run(['node','--enable-source-maps',str(target)],capture_output=True,text=True)
                self.assertIn('main.gs:2:',result.stderr)
                self.assertIn('main.gs:4:',result.stderr)

    def test_mjs_import_rewrite_does_not_modify_ordinary_strings(self):
        package=VERSIONS/'typescript70'
        if not package.exists():self.skipTest('TS 7 release matrix')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);entry=root/'main.gs'
            entry.write_text('import { f } from "./lib.gs"\nprintln("./lib.js", f(2))')
            (root/'lib.gs').write_text('export func f(n int) int { return n+1 }')
            _,target=build(configure(entry,ts_compiler='ts',typescript=package,format='mjs'))
            self.assertEqual(subprocess.check_output(['node',str(target)],text=True),'./lib.js 3\n')
