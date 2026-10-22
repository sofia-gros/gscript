from pathlib import Path
import subprocess
import tempfile
import unittest

from gscript.build import configure,build

ROOT=Path(__file__).resolve().parents[1]
TSC=ROOT/'node_modules/typescript/bin/tsc'


class DeclarationTests(unittest.TestCase):
    def test_public_api_numeric_brands_and_cross_module_identity(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'lib.gs').write_text('export func twice(n int) int { return n*2 }')
            entry=root/'main.gs';entry.write_text('''import { twice } from "./lib.gs"
export type Box<T> struct { Value T }
func (b Box<T>) get() T { return b.Value }
export type Has<T> interface { Value T }
export type Scalar = int | float | nil
export type State enum { Idle; Running }
export func integer(n int) int { return twice(n) }
export func fractional(n float) float { return n }
export func read(box Has<int>) int { return box.Value }
''')
            build(configure(entry,declaration=True,strict_null=True))
            definition=(root/'dist/main.d.ts').read_text()
            self.assertIn('GSInt',definition);self.assertIn('GSFloat',definition)
            self.assertNotIn('function integer(n: number)',definition)
            consumer=root/'dist/consumer.ts'
            consumer.write_text('''import { integer, fractional, Box, State, type GSInt, type GSFloat } from "./main.js";
import { twice } from "./lib.js";
const i = 3 as GSInt;
const f = 3.5 as GSFloat;
integer(twice(i));
fractional(f);
new Box<GSInt>({Value:i}).get();
const state: typeof State.Idle = State.Idle;
// @ts-expect-error floating values do not satisfy the integer brand
integer(f);
// @ts-expect-error integer values do not satisfy the float brand
fractional(i);
''')
            p=subprocess.run(['node',str(TSC),'--noEmit','--strict','--target','ES2022','--module','NodeNext','--moduleResolution','NodeNext',str(consumer)],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)

    def test_all_v04_feature_declarations_remain_valid_typescript(self):
        import sys
        sys.path.insert(0,str(ROOT/'tests'))
        from test_extensions import CASES
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);files=[]
            for name,(source,_) in CASES.items():
                entry=root/(name+'.gs');entry.write_text(source)
                build(configure(entry,declaration=True,out_dir=root/'out'))
                files.append(str(root/'out'/(name+'.d.ts')))
            p=subprocess.run(['node',str(TSC),'--noEmit','--strict','--target','ES2022','--module','NodeNext','--moduleResolution','NodeNext',*files],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
