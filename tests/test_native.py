import ctypes
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from gscript import CompileError
from gscript.native.build import build_native
from gscript.native.checker import NativeProject

ROOT=Path(__file__).resolve().parents[1]
CC=os.environ.get('GS_NATIVE_CC') or shutil.which('clang') or shutil.which('cc') or shutil.which('gcc')
DRIVER=[CC,'cc'] if CC and Path(CC).stem=='zig' else [CC]


class NativeTypeTests(unittest.TestCase):
    def test_native_errors_are_checked_without_invoking_c(self):
        invalid=[
            'var x int = 1.5', 'var x i32 = 1',
            'func f(n i32) {}\nf(1)', 'func f() i32 {return 1}',
            'func f() int {if true {return 1}}',
            'extern "C" func bad(value string)',
            'type A struct { Self A }', 'type Empty struct {}',
            'type A struct { Value int }\na:=A{Value:2.5}',
            'var data [3]u8\ndata[3]=u8(2)',
            'type H struct { cb winfunc(i32)i32 }\nfunc f(n i32) i32{return n}\nh:=H{cb:f}',
            'extern "Rust" func bad()', 'import x from "phaser"',
            'const x int=1\np:=address(x)',
            'store(cstr("constant"),u8(2))',
            'var p ptr<i32>\np=cast<ptr<i32>>(i32(1))' if struct.calcsize('P')==8 else 'var p ptr<i32>\np=cast<ptr<i32>>(i64(1))',
            'var data [2]u8\ncopy:=data', 'u8(256)',
            'type A struct { readonly X i32 }',
        ]
        for source in invalid:
            with self.subTest(source=source),tempfile.TemporaryDirectory() as d:
                path=Path(d)/'main.gs';path.write_text(source);out=Path(d)/'saved';out.write_text('preserved')
                with patch('subprocess.run',side_effect=AssertionError('GS must reject this before the C compiler')):
                    with self.assertRaises(CompileError):build_native(path,output=out)
                self.assertEqual(out.read_text(),'preserved')

    def test_check_only_and_c_emission_need_no_c_toolchain(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);entry=root/'main.gs';entry.write_text('println(42)')
            with patch('subprocess.run',side_effect=AssertionError('check/C output must not run a toolchain')):
                build_native(entry,check_only=True)
                _,out=build_native(entry,emit='c')
            self.assertIn('int main(void)',out.read_text())
            self.assertFalse((root/'dist/native/main').exists())

    def test_library_rejects_executable_initialization_and_protects_sources(self):
        with tempfile.TemporaryDirectory() as d:
            entry=Path(d)/'main.gs';entry.write_text('println(1)')
            with self.assertRaises(CompileError):build_native(entry,emit='shared')
            entry.write_text('var x int=1\nx=2')
            with self.assertRaises(CompileError):build_native(entry,emit='object')
            entry.write_text('println(1)')
            with self.assertRaises(CompileError):build_native(entry,emit='c',output=entry)
            self.assertEqual(entry.read_text(),'println(1)')


@unittest.skipUnless(CC,'native execution tests require Clang, GCC or Zig')
class NativeExecutionTests(unittest.TestCase):
    def compile_run(self,source,expected=None):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);entry=root/'main.gs';entry.write_text(source)
            _,out=build_native(entry,cc=CC)
            result=subprocess.run([str(out)],capture_output=True,text=True,env={**os.environ,'PATH':''})
            if expected is not None:self.assertEqual((result.returncode,result.stdout),(0,expected),result.stderr)
            return result

    def test_standalone_execution_evaluation_order_and_loop_control(self):
        self.compile_run('''counter:=0
func next() int { counter++; return counter }
func encode(a,b int) int { return a*10+b }
println(encode(next(),next()),next()+next())
if false && next()>0 { println("wrong") }
total:=0
for i:=0; i<5; i++ { if i==2 { continue }; total+=i }
println(total,counter)
''','12 7\n8 4\n')

    def test_record_array_pointer_string_and_numeric_support(self):
        self.compile_run('''type Point struct { X i32; Y i32 }
p:=Point{X:i32(2),Y:i32(3)}
q:=address(p)
q.X=i32(4)
var data [4]u8
data[2]=u8(7)
println(p.X,p.Y,sizeof<Point>(),offsetof<Point>("Y"),data[2],len(data))
println("GS Native", len("日本"), "a"=="a",f32(1.5)+f32(2.5),int(3.9),bitOr(u32(1),u32(2)))
''','4 3 8 4 7 4\nGS Native 6 true 4 3 3\n')

    def test_checked_integer_overflow_conversion_and_bounds(self):
        for source,message in [
            ('x:=i64(9223372036854775807)\nprintln(x+i64(1))','overflow'),
            ('x:=300\nprintln(u8(x))','conversion out of range'),
            ('var data [2]u8\ni:=-1\nprintln(data[i])','out of bounds'),
            ('println(idiv(1,0))','division by zero'),
        ]:
            with self.subTest(source=source):
                result=self.compile_run(source)
                self.assertEqual(result.returncode,1);self.assertIn(message,result.stderr)

    def test_imports_and_source_link_directives(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'lib.gs').write_text('export type Point struct { X i32; Y i32 }\nexport func twice(n int) int {return n*2}')
            entry=root/'main.gs';entry.write_text('import { Point, twice as double } from "./lib.gs"\np:=Point{X:i32(2)}\nprintln(double(21),p.X)')
            _,out=build_native(entry,cc=CC);self.assertEqual(subprocess.check_output([str(out)],text=True),'42 2\n')

    def test_bidirectional_c_abi_layout_pointer_and_callback(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);fixture=root/'fixture.c';obj=root/'fixture.o'
            fixture.write_text('''#include <stdint.h>
#include <stddef.h>
typedef struct { int32_t X,Y; } Point;
int32_t fixture_apply(Point *p,int32_t (*cb)(int32_t)) { p->X=cb(p->Y); return (int32_t)offsetof(Point,Y); }
''')
            subprocess.run([*DRIVER,'-c',str(fixture),'-o',str(obj)],check=True)
            entry=root/'main.gs';entry.write_text('''type Point struct { X i32; Y i32 }
extern "C" func fixture_apply(p ptr<Point>, cb func(i32)i32) i32
func increment(n i32) i32 {return n+i32(1)}
p:=Point{Y:i32(41)}
println(fixture_apply(address(p),increment),p.X)
''')
            _,out=build_native(entry,cc=CC,objects=[obj]);self.assertEqual(subprocess.check_output([str(out)],text=True),'4 42\n')

    def test_object_static_and_shared_library_consumers(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);entry=root/'api.gs';entry.write_text('export func add(a,b i32) i32 {return a+b}')
            for emit in ('object','static','shared'):
                with self.subTest(emit=emit):
                    _,out=build_native(entry,cc=CC,emit=emit,header=root/'api.h')
                    if emit=='shared':
                        lib=ctypes.CDLL(str(out));lib.add.argtypes=[ctypes.c_int32]*2;lib.add.restype=ctypes.c_int32
                        self.assertEqual(lib.add(20,22),42)
                        if os.name=='nt':
                            import _ctypes
                            _ctypes.FreeLibrary(lib._handle)
                    else:
                        driver=root/'driver.c';driver.write_text('#include "api.h"\nint main(void){return add(20,22)==42?0:1;}')
                        exe=root/('driver.exe' if os.name=='nt' else 'driver')
                        subprocess.run([*DRIVER,str(driver),str(out),'-o',str(exe)],check=True)
                        self.assertEqual(subprocess.run([str(exe)]).returncode,0)

    def test_cli_native_output_and_failed_link_preserve_binary(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);entry=root/'main.gs';entry.write_text('println(42)')
            output=root/('app.exe' if os.name=='nt' else 'app')
            result=subprocess.run([sys.executable,'-m','gscript',str(entry),'--backend','native','--cc',CC,'-o',str(output)],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            before=output.read_bytes()
            entry.write_text('extern "C" func gs_missing_symbol()\ngs_missing_symbol()')
            with self.assertRaises(CompileError):build_native(entry,cc=CC,output=output)
            self.assertEqual(output.read_bytes(),before)

    def test_foreign_c_string_views_and_example_entry_points(self):
        with patch.dict(os.environ,{'GS_NATIVE_TEXT':'native library text'}):
            self.compile_run('extern "C" func getenv(name cptr<cchar>) ptr<cchar>\np:=getenv(cstr("GS_NATIVE_TEXT"))\nif p!=nil { println(string(p)) }','native library text\n')
        for name,expected in [('hello.gs','GScript Native 144\n'),('ffi/main.gs','GScript calls a C ABI library\n')]:
            with tempfile.TemporaryDirectory() as d:
                entry=ROOT/'examples/native'/name
                _,out=build_native(entry,cc=CC,output=Path(d)/('app.exe' if os.name=='nt' else 'app'))
                self.assertEqual(subprocess.check_output([str(out)],text=True),expected)
