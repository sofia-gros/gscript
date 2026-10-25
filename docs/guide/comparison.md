# Go・JavaScriptとの比較

GScriptはGo風の宣言構文を使いますが、JS経路ではJavaScriptの実行モデルを使います。ここでのJavaScript例は同等の処理を人が書いた例で、生成コードそのものではありません。ネイティブの違いは末尾の表を参照してください。

## 書き方の対応表

Goの文は、特記のない限り関数内の断片です。

| 機能 | Go | JavaScript | GScript（JS経路） |
| --- | --- | --- | --- |
| 推論する変数 | `n := 3` | `let n = 3` | `n := 3` |
| 型付き変数 | `var n int = 3` | 型注釈なし | `var n int = 3` |
| 定数 | `const n = 3` | `const n = 3` | `const n = 3`（束縛の再代入禁止） |
| 関数 | `func add(a, b int) int` | `function add(a, b)` | `func add(a, b int) int` |
| 無名関数 | `func(n int) int { return n*2 }` | `(n) => n*2` | `func(n int) int { return n*2 }` |
| 条件 | `if n > 0 { ... }` | `if (n > 0) { ... }` | `if n > 0 { ... }` |
| ループ | `for i := 0; i < 3; i++` | `for (let i=0; i<3; i++)` | `for i := 0; i < 3; i++` |
| 条件ループ | `for n < 3` | `while (n < 3)` | `for n < 3` |
| 無限ループ | `for { ... }` | `for (;;) { ... }` | `for { ... }` |
| 値を反復 | `for _, v := range xs` | `for (const v of xs)` | `for v := range xs` |
| 添字と値 | `for i, v := range xs` | `for (const [i,v] of xs.entries())` | `for i, v := range xs` |
| 配列に追加 | `xs = append(xs, 4)` | `xs.push(4)` | `xs.push(4)` |
| 配列の長さ | `len(xs)` | `xs.length` | `len(xs)` または `xs.length` |
| オブジェクト | structやmapを使う | `{name: "GS"}` | `{name: "GS"}` |
| コピーと上書き | 型ごとに記述 | `{...x, age: 3}` | `{...x, age: 3}` |
| null値 | `nil`（使える型に制約） | `null` | `nil` → JS null |
| null対応 | 明示的なif | `x?.name ?? ""` | `x?.Name ?? ""` |
| 型の和 | 直接のUnion構文なし | 動的な値として扱う | `type Value = string \| number` |
| Generics | `func id[T any](x T) T` | 動的に扱う | `func id<T>(x T) T` |
| 非同期 | goroutine / channel等 | `async function` / `await` | `async func` / `await` |
| エラー | error値、panic/recover | throw / try / catch | throw / try / catch、panic |
| import | `import "example/pkg"` | `import {x} from "pkg"` | `import {x} from "pkg"` |
| 公開 | 名前の先頭を大文字に | `export` | `export` |
| エントリー | package mainのmain | モジュールのトップレベル | モジュールのトップレベル |

## 同じ挨拶を書く

### Go

```go
package main
import "fmt"
func greet(name string) string { return "Hello, " + name }
func main() {
  name := "GS"
  fmt.Println(greet(name))
}
```

### JavaScript

```js
function greet(name) { return "Hello, " + name; }
let name = "GS";
console.log(greet(name));
```

### GScript

```gs
func greet(name string) string { return "Hello, " + name }
name := "GS"
println(greet(name))
```

Goはmainを自動実行します。GSはトップレベル文を実行し、型注釈を検査してから消去します。

## 配列の変換と反復

### Go

```go
values := []int{1, 2, 3}
next := make([]int, len(values))
for i, n := range values { next[i] = n * 2 }
for _, n := range next { fmt.Println(n) }
```

### JavaScript

```js
const values = [1, 2, 3];
const next = values.map(n => n * 2);
for (const n of next) console.log(n);
```

### GScript

```gs
values := []int{1, 2, 3}
next := values.map(func(n int) int { return n * 2 })
for n := range next { println(n) }
```

GSはGo風の配列記法にJSの配列メソッドを組み合わせます。GSの1変数rangeはGoと違って値を返します。

## structとメソッド

### Go

```go
type Person struct { Name string }
func (p Person) Greet() string { return "Hello, " + p.Name }
p := Person{Name: "GS"}
q := p
q.Name = "Changed" // p.NameはGSのまま（値コピー）
```

### JavaScript

```js
class Person {
  constructor({Name = ""} = {}) { this.Name = Name; }
  Greet() { return "Hello, " + this.Name; }
}
const p = new Person({Name: "GS"});
const q = p;
q.Name = "Changed"; // p.Nameも変化（参照共有）
```

### GScript

```gs
type Person struct { Name string }
func (p Person) Greet() string { return "Hello, " + p.Name }
p := Person{Name: "GS"}
q := p
q.Name = "Changed" // JS経路ではp.Nameも変化
println(p.Greet())
```

レシーバーの見た目がGoでも、JS経路でのstructはclassインスタンスです。ネイティブGSのstructは値コピーになります。

## 整数の除算

| | 式 | 結果 |
| --- | --- | --- |
| Go | `5 / 2`（整数） | `2` |
| JavaScript | `5 / 2` | `2.5` |
| GScript JS | `5 / 2` | `2.5`（float） |
| GScript JS | `int(5 / 2)` | `2` |
| GScript Native | `idiv(5, 2)` | `2` |

GS JSのintは実行時にJS Numberです。Goのint幅や任意精度の定数を再現しません。

## 非同期と例外

### Go

```go
// 同期的なerror値の処理。goroutineを使うかどうかは呼び出し側の設計。
text, err := loadText(url)
if err != nil { return err }
fmt.Println(text)
```

### JavaScript

```js
try {
  const text = await loadText(url);
  console.log(text);
} catch (err) { console.log(err.message); }
```

### GScript

```gs
try {
  text := await loadText(url)
  println(text)
} catch err { println(err.message) }
```

この例は各言語のエラー処理の断片です。loadTextは別途定義します。GSはJSのPromiseを使い、goroutineやchannelへ変換しません。

## JS出力とネイティブで変わる意味

| 項目 | GS JS / TS | GS Native |
| --- | --- | --- |
| int | JS Number（静的な整数型） | 符号付き64bit |
| struct代入 | 参照共有 | C-layoutの値コピー |
| stringの長さ | UTF-16コード単位 | UTF-8バイト数 |
| 配列 | 可変JS Array | 固定長[N]Tの保存領域 |
| ポインター | 言語のCポインターなし | ptr / cptr、寿命は利用側で管理 |
| Generics・async・継承 | 対応 | v0.6.1未対応 |
| 外部ライブラリ | JS / TS / npm | C / system ABI |

[型とオブジェクト](structs.md)に継承・interface・Generics・enum等の例、[文と式](control-flow.md)に制御文・例外・モジュール構文の一覧があります。
