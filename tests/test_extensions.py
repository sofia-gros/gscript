"""Native GS checks and executable output for the v0.4 language proposal."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from gscript import compile_source, CompileError
from gscript.project import Project, build_project

ROOT=Path(__file__).resolve().parents[1]

CASES={
'inheritance':('''type Child struct extends Parent { Extra int = 2 }
type Parent struct { Value int }
func (p Parent) constructor(n int) { p.Value = n }
func (p Parent) get() int { return p.Value }
func (c Child) constructor(n int) { super(n); c.Extra = 4 }
override func (c Child) get() int { return super.get() + c.Extra }
x := new Child(3)
var parent Parent = x
console.log(parent.get(), x instanceof Parent)
''','7 true\n'),
'interface':('''type Named interface { Name string }
type Entity interface extends Named { get() int }
type Player struct implements Entity { Name string; HP int }
func (p Player) get() int { return p.HP }
func read(e Entity) int { return e.get() }
console.log(read(Player{Name: "GS", HP: 5}))
''','5\n'),
'nullable':('''type Item struct { Value int }
func read(x Item?) int {
 if x != nil { return x.Value }
 return 0
}
func optional(x Item?) int { return x?.Value ?? 8 }
console.log(read(nil), optional(nil), optional(Item{Value: 3}))
''','0 8 3\n'),
'optional':('''type Item struct { get func() int }
func read(x []int?) int { return x?.[0] ?? 7 }
var call func() int = func() int { return 4 }
console.log(read(nil), call?.() ?? 0, 0 ?? 9)
''','7 4 0\n'),
'union':('''type Direction = "up" | "down"
type Value = string | number
func read(x Value) string {
 if typeof x == "string" { return x.toUpperCase() }
 return "number"
}
func move(d Direction) { console.log(d) }
move("up")
console.log(read("gs"), read(3))
''','up\nGS number\n'),
'generics':('''type Container<T> struct { Value T }
func (c Container<T>) get() T { return c.Value }
type Pair<K, V> struct { Key K; Value V }
type Has<T> interface { Value T }
type Result<T> = T | nil
func identity<T>(value T) T { return value }
func max<T extends number>(a T, b T) T { if a > b { return a }; return b }
x := Container<int>{Value: 100}
var item Has<int> = x
pair := Pair<string, int>{Key: "gs", Value: 3}
var result Result<int> = nil
console.log(x.get(), item.Value, pair.Key, identity("ok"), max<int>(3, 4))
''','100 100 gs ok 4\n'),
'switch':('''type State = "idle" | "walk" | "run"
func read(state State) int {
 switch state {
 case "idle": return 0
 case "walk", "run": return 1
 }
}
console.log(read("walk"))
''','1\n'),
'static':('''type MathHelper struct { static Count int = 1 }
static func (m MathHelper) square(n int) int { m.Count += 1; return n * n }
type Derived struct extends MathHelper {}
console.log(Derived.square(5), MathHelper.Count)
''','25 1\n'),
'access':('''type Parent struct { private HP int; protected Speed int = 3; readonly ID string }
func (p Parent) constructor(id string) { p.ID = id; p.HP = 2 }
func (p Parent) get() int { return p.HP }
type Child struct extends Parent {}
func (c Child) speed() int { return c.Speed }
x := new Child("gs")
console.log(x.ID, x.get(), x.speed())
''','gs 2 3\n'),
'aliases':('''type UserID = string
type Position = {x: number, y: number}
type Callback = func(number) number
func apply(cb Callback, n int) int { return cb(n) }
var p Position = {x: 2, y: 3}
var id UserID = "gs"
console.log(id, p.x, apply(func(n int) int { return n * 2 }, 3))
''','gs 2 6\n'),
'enum':('''type State enum { Idle; Walk; Attack }
type Direction enum { Up = "up"; Down = "down" }
func read(state State) int {
 switch state { case State.Idle: return 1; case State.Walk, State.Attack: return 2 }
}
var d Direction = Direction.Up
console.log(read(State.Walk), d, Object.isFrozen(State))
''','2 up true\n'),
}

CASES['optional-method']=('type A struct {}\nfunc (a A) get() int { return 3 }\nfunc read(a A?) int { return a?.get() ?? 7 }\nconsole.log(read(nil), read(A{}))','7 3\n')
CASES['recursive-alias']=('type Link = {value: int; next: Link?}\nvar x Link = {value: 3, next: nil}\nconsole.log(x.value)','3\n')
CASES['nullable-and']=('type A struct { Value int }\nfunc read(a A?) bool { return a != nil && a.Value > 0 }\nconsole.log(read(nil),read(A{Value: 3}))','false true\n')
CASES['enum-keys']=('type Object struct {}\ntype Weird enum { __proto__; constructor }\nconsole.log(Weird.__proto__,Weird.constructor)','0 1\n')
CASES['static-order']=('var count int = 3\ntype A struct { static Value int = count }\nconsole.log(A.Value)','3\n')
CASES['short-circuit']=('type A struct { Value int }\nvar calls int = 0\nfunc get() A? { calls += 1; return nil }\nconsole.log(get()?.Value ?? 4,calls)','4 1\n')
CASES['alias-zero']=('type Count = int\nvar count Count\nconsole.log(count)','0\n')
CASES['optional-field']=('type Options = {value?: int}\nvar options Options = {}\nconsole.log(options.value ?? 3)','3\n')
CASES['instanceof']=('type A struct { X int }\ntype B struct { Y int }\nfunc read(v A | B) int { if v instanceof A { return v.X }; return v.Y }\nconsole.log(read(A{X: 4}),read(B{Y: 5}))','4 5\n')

BAD=[
 'type A struct extends B {}\ntype B struct extends A {}',
 'type A struct {}\nfunc (a A) constructor() int { return 1 }',
 'type A struct {}\nfunc (a A) constructor() {}\nfunc (a A) constructor() {}',
 'type A struct {}\ntype B struct extends A {}\nfunc (b B) constructor() { b.x = 1; super() }',
 'type A struct {}\ntype B struct extends A {}\nfunc (b B) constructor() { super(); super() }',
 'type A struct {}\nfunc (a A) constructor(n int) {}\nnew A("bad")',
 'type A struct {}\nfunc (a A) constructor() {}\nA{}',
 'type E interface { get() int }\ntype A struct implements E {}',
 'type A struct {}\noverride func (a A) missing() {}',
 'type A struct {}\nfunc (a A) f(n int) int { return n }\ntype B struct extends A {}\noverride func (b B) f(n string) int { return 1 }',
 'type A struct { X int }\nfunc f(a A?) int { return a.X }',
 'type D = "up" | "down"\nvar d D = "bad"',
 'type V = string | number\nfunc f(v V) { console.log(v.toUpperCase()) }',
 'func f<T extends number>(x T) T { return x }\nf("bad")',
 'type C<T> struct { Value T }\nC<int>{Value: "bad"}',
 'type D = "up" | "down"\nfunc f(d D) { switch d { case "up": console.log(d) } }',
 'type A struct { private HP int }\nconsole.log(A{}.HP)',
 'type A struct { readonly ID int }\na := A{}\na.ID = 2',
 'type A struct { static X int }\nconsole.log(A{}.X)',
 'type A = B\ntype B = A',
 'type E interface extends F {}\ntype F interface extends E {}',
 'type A struct {}\nvar a any = A{} ?? true || false',
 'type E interface {}\nconsole.log(E)',
 'type A struct {}\nfunc (a A) f() int { return 1 }\nfunc read(a A?) { (a?.f)() }',
 'type A struct { X int }\nfunc read(a A?) { if a != nil { a = nil; console.log(a.X) } }',
 'type Empty = []void',
 'func invalid<T>(n void) {}',
 'type S enum { A; A }',
 'type S enum { A = "a"; B }',
 'type S enum { A; B }\nvar s S = 9',
]


class ExtensionTests(unittest.TestCase):
    def test_external_classes_are_checked_by_gs_before_output_bridge(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'parent.ts').write_text('export class Parent { readonly id: string; constructor(id: string) { this.id=id; } get(n: number): number { return n * 2; } }')
            entry=root/'main.gs'
            source='import { Parent } from "./parent.ts"\n'+'type Child struct extends Parent {}\nfunc (c Child) constructor(id string) { super(id) }\noverride func (c Child) get(n int) int { return super.get(n) + 1 }\nconsole.log(new Child("gs").get(3))'
            entry.write_text(source)
            for format in ('js','mjs','ts'):
                output=build_project(entry,root/format,format=format,typescript=ROOT/'node_modules/typescript/lib/typescript.js')
                if format=='ts':continue
                result=subprocess.run(['node',str(output)],capture_output=True,text=True,timeout=15)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(result.stdout,'7\n')
            bad=[source.replace('super(id)','super(1)'), source.replace('get(n int) int','get(n string) int'), source.replace('console.log(new Child("gs").get(3))','new Child("gs").missing()')]
            for code in bad:
                entry.write_text(code)
                with patch('gscript.interop.ExternalChecker.run',side_effect=AssertionError('GS must reject this before output processing')):
                    with self.assertRaises(CompileError):Project(entry,typescript=ROOT/'node_modules/typescript/lib/typescript.js').check()

    def test_external_generic_classes_and_factory_return_types(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'lib.ts').write_text('export class Cell<T> { constructor(public value:T) {} }\nexport function create<T>(value:T):Cell<T> { return new Cell(value); }')
            entry=root/'main.gs'
            entry.write_text('import { Cell, create } from "./lib.ts"\nvar c Cell<int> = new Cell<int>(3)\nvar n int = create(3).value\nconsole.log(c.value, n)')
            output=build_project(entry,root/'out',typescript=ROOT/'node_modules/typescript/lib/typescript.js')
            result=subprocess.run(['node',str(output)],capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout,'3 3\n')
            entry.write_text('import { create } from "./lib.ts"\nvar n int = create("bad").value')
            with self.assertRaises(CompileError):Project(entry,typescript=ROOT/'node_modules/typescript/lib/typescript.js').check()

    def test_external_metadata_cache_skips_node_but_still_checks_gs(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'lib.ts').write_text('export function twice(n:number):number { return n*2; }')
            entry=root/'main.gs'
            entry.write_text('import { twice } from "./lib.ts"\ntwice(1)')
            options={'typescript':ROOT/'node_modules/typescript/lib/typescript.js'}
            Project(entry,**options).check()
            with patch('subprocess.Popen',side_effect=AssertionError('warm declaration metadata must not start Node')):
                Project(entry,**options).check()
                entry.write_text('import { twice } from "./lib.ts"\ntwice("bad")')
                with self.assertRaises(CompileError):Project(entry,**options).check()

    def test_phaser_scene_inheritance_checks(self):
        Project(ROOT/'tests/fixtures/interop/phaser-scene.gs').check()

    def test_native_checks_do_not_invoke_typescript(self):
        with patch('subprocess.run',side_effect=AssertionError('GS checking must not invoke TypeScript')), patch('subprocess.Popen',side_effect=AssertionError('GS checking must not invoke TypeScript')):
            for name,(source,_) in CASES.items():
                with self.subTest(name=name):compile_source(source)
            for source in BAD:
                with self.subTest(source=source):
                    with self.assertRaises(CompileError):compile_source(source)

    def test_all_features_execute_in_js_mjs_and_strict_ts(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'package.json').write_text('{"type":"module"}')
            for name,(source,expected) in CASES.items():
                for format in ('js','mjs','ts'):
                    with self.subTest(name=name,format=format):
                        entry=root/(name+'.'+format)
                        entry.write_text(compile_source(source,format),encoding='utf-8')
                        if format=='ts':
                            out=root/(name+'-compiled')
                            result=subprocess.run(['node',str(ROOT/'node_modules/typescript/bin/tsc'),str(entry),'--strict','--target','ES2022','--module','NodeNext','--moduleResolution','NodeNext','--outDir',str(out)],capture_output=True,text=True,timeout=30)
                            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                            entry=out/(name+'.js')
                        result=subprocess.run(['node',str(entry)],capture_output=True,text=True,timeout=15)
                        self.assertEqual(result.returncode,0,result.stderr)
                        self.assertEqual(result.stdout,expected)

    def test_strict_null_and_failure_preserves_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            entry=root/'main.gs'
            entry.write_text('type A struct {}\nvar a A = nil')
            Project(entry).check()
            target=root/'out/main.mjs'
            target.parent.mkdir();target.write_text('preserve')
            with self.assertRaises(CompileError):build_project(entry,target.parent,strict_null=True)
            self.assertEqual(target.read_text(),'preserve')

    def test_cross_module_interfaces_aliases_and_inheritance(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'lib.gs').write_text('export type E interface { get() int }\nexport type A struct { X int }\nfunc (a A) get() int { return a.X }')
            entry=root/'main.gs'
            entry.write_text('import { E, A } from "./lib.gs"\ntype B struct extends A {}\nvar e E = new B({X: 3})\nconsole.log(e.get())')
            output=build_project(entry,root/'out')
            result=subprocess.run(['node',str(output)],capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout,'3\n')


if __name__=='__main__':unittest.main()
