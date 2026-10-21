# gscript

Go の宣言・関数・制御構文と、JavaScript のオブジェクト・配列 API・非同期処理を組み合わせる言語です。構文解析 → 型検査 → JavaScript ES2022 Modules の生成を行います。現在のバージョンは **0.2.0** です。

## クイックスタート

Python 3.12 以上と、出力を実行する Node.js 22 以上を用意します。コンパイラの実行時依存パッケージはありません。ローカル検証環境は Python 3.12 / Node.js 24、CI は Python 3.12・3.13 / Node.js 22・24 の組み合わせです。

```bash
# チェックアウトから使う（インストール不要）
python -m gscript examples/main.gos -o build/main.mjs
node build/main.mjs

# コマンドとしてインストール
python -m pip install .
gscript examples/hello.gos -o build/hello.mjs
node build/hello.mjs

# 型検査だけ
python -m gscript examples/main.gos --check

# テスト（Node.js も必要）
python -m unittest discover -s tests -v
```

従来の `python main.py` も利用できます。引数省略時は `examples/main.gos` をコンパイルして標準出力に表示します。`gscript` と `python -m gscript` は入力ファイルを指定します。ブラウザーでは生成物を module として読み込めますが、Node.js 固有のモジュールは使えません。

## Go に近い構文

```go
var count int
const limit int = 3
name := "Sofia"

func greet(name string) string {
  return "Hello, " + name
}

console.log(greet(name))
for i := 0; i < limit; i++ {
  count += i
}
```

`package` や `main()` は不要です。トップレベルで処理を実行できます。`let` による変数宣言と、`printf(...)`（書式処理のない `console.log` の別名）も利用できます。

`+ - * / %`、比較、`&& || !`、`if / else if / else`、3節の for、`for condition {}`、無限ループ、`break / continue` を実装しています。優先順位を考慮して JavaScript を生成します。

### struct とメソッド

```go
type Person struct {
  Name string
  Age int
}

func (p Person) Greet() string {
  return "Hello, " + p.Name
}

p := Person{Name: "Sofia"}
console.log(p.Greet())
```

struct は JavaScript の class に変換します。省略フィールドは数値が `0`、文字列が `""`、真偽値が `false`、その他が `null` です。`Age int = 18` のような初期値にも対応します。レシーバーに `*` は付けません。struct と名前付き関数の宣言は同じモジュール内で前方参照できます。

### 関数を値として使う

```go
func apply(n int, callback func(int) int) int {
  return callback(n)
}

double := func(n int) int { return n * 2 }
console.log(apply(3, double))
```

`func add(a, b int) int` のグループ化した引数宣言、クロージャー、ネストした関数、相互再帰にも対応します。戻り値注釈を省略した関数は `void` です。値を返す関数には型を指定してください。

## JavaScript の使いやすさ

```go
user := {name: "Sofia", age: 28}
updated := {...user, age: 29}

numbers := []int{1, 2, 3}
doubled := numbers.map(func(n int) int {
  return n * 2
})

for i, n := range doubled {
  console.log(i, n)
}
```

オブジェクトの短縮プロパティ、spread、添字アクセス、任意の JavaScript API の呼び出しを利用できます。`range` は配列専用で、1変数ならインデックス、2変数ならインデックスと値を取得します。

`map / filter / find / forEach / some / every / push / unshift` は引数や結果の型を検査します。配列 API 全体の型定義を提供しているわけではなく、一部メソッドは `any` で扱います。

### 非同期処理

```go
async func loadText(url string) string {
  res := await fetch(url)
  return await res.text()
}

try {
  text := await loadText("data:text/plain,Hello")
  console.log(text)
} catch err {
  console.log(err.message)
}
```

`async func` の戻り値注釈は await 後の値の型です。呼び出すと Promise が返ります。トップレベルの await、非同期コールバック、`throw`、JavaScript コンストラクターの `new Error(...)` も利用できます。

## モジュールのビルド

import は名前付き（`as` 別名も可）、デフォルト、名前空間、副作用のみの4形式です。`export` は変数・関数・struct の宣言に付けられます。

```go
// lib/math.gos
export func twice(n int) int {
  return n * 2
}
```

```go
// main.gos
import { twice } from "./lib/math.gos"
import { basename } from "node:path"
console.log(twice(21), basename("/tmp/main.gos"))
```

```bash
python -m gscript examples/modules/main.gos --out-dir build/modules
node build/modules/main.mjs
```

`--out-dir` は相対 `.gos` import を再帰的にビルドし、出力の import を `.mjs` に書き換えます。レイアウトは保持されます。デフォルトのプロジェクトルートはエントリーファイルのディレクトリです。親ディレクトリの共有モジュールも含める場合は `--root` を指定してください。

```bash
python -m gscript src/main.gos --root . --out-dir build
node build/src/main.mjs
```

循環 import にも対応しますが、初期化順序は ES Modules と同じです。全モジュールの構文・型検査が成功してから出力し、1ファイルごとの書き込みは原子的に置き換えます。ファイルシステム障害時のビルド全体のロールバックは行いません。

npm や既存 `.js` / `.mjs` の import は保持します。パッケージのインストール、バンドル、Node.js 以外への polyfill は行いません。`-o` と `--check` は単一ファイル用で、`.gos` import がある場合は `--out-dir` を使います。

## 型検査と JS との境界

- 変数の型推論、代入、関数・レシーバーメソッドの引数と戻り値、関数値、struct フィールド、配列要素、オブジェクトのプロパティを検査します。
- 未定義名、重複宣言、const の再代入、既知の値への不正な演算、戻り値の漏れ、await や break の不正な場所を検出します。
- `any` は JavaScript との接続用です。import の値と JS のグローバル API は原則として `any` です。`any` のプロパティや呼び出しは実行時に検証されます。名前そのものの未定義は `any` にしません。
- import 境界では `.gos` 同士でも型情報を共有しません。import した値の型、export 名の存在、外部パッケージの存在は静的に検証しません。import した struct は JS class として `new Person({...})` で使います。
- オブジェクトリテラルの既知のプロパティは検査します。動的なキーを使う場合は `var data object = {...}` または `any` を指定します。
- JS グローバル名は一般的な Node.js・ブラウザー API を登録しています。独自のグローバルは `globalThis.myAPI` 経由で使えます。登録済みでも実行環境が API を提供する保証はありません。

## Go との違い・現在の制約

**Go 互換コンパイラではありません。** 実行時の振る舞いは JavaScript に合わせています。

- 型注釈は出力から削除します。`int / float / float64 / number` はすべて JS の Number です。整数の強制、整数除算、オーバーフロー検査はありません。
- struct・配列・オブジェクトの代入は参照の共有です。Go の構造体コピーやスライスの容量管理は再現しません。
- const は再代入禁止で、内容の変更は可能です。メソッドを取り出した場合の `this` も JS と同じです。
- `nil` は `null`、`== / !=` は `=== / !==` に変換します。配列などの参照型には nil を代入できますが、数値・文字列・真偽値にはできません。
- 改行時に文の終わりを認識し、演算子の後や引数の途中の改行に対応します。ただし Go の字句仕様全体には準拠していません。識別子は ASCII の英数字・`_`・`$`、数値は十進数、文字列は引用符付きの JS 形式の基本エスケープです。
- 型検査は健全性を保証する完全な検査器ではありません。`any`、外部 API、配列の範囲外アクセス、null の経路、関数呼び出し前の変数初期化など、実行時エラーになる場合があります。
- goroutine、channel、ポインター、map 型、interface、ジェネリクス、複数戻り値、可変長引数、Go 標準ライブラリは未実装です。

## 実装と比較資料

- `parser/syntax.py`: 字句解析・構文解析・AST・位置付き構文エラー
- `parser/checker.py`: スコープ・型検査・制御フロー
- `parser/emitter.py`: JavaScript 生成
- `parser/compiler.py`: コンパイラ API
- `gscript/`: 公開 API・CLI・モジュールのビルド
- `examples/` / `tests/`: サンプルと、生成 JS の実行を含むテスト

[Go / gscript / 生成 JS の比較](docs/comparison.md)・[言語仕様と開発方針](docs/language.md)
