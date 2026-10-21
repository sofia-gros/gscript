<div align="center">

# GS / gscript

**Go の書き心地で、JavaScript の世界へ。**

構文と型を検査し、JavaScript・ES Modules・TypeScript にコンパイルする言語。

[![Compiler tests](https://github.com/sofia-gros/gscript/actions/workflows/test.yml/badge.svg)](https://github.com/sofia-gros/gscript/actions/workflows/test.yml)
[![Release compiler](https://github.com/sofia-gros/gscript/actions/workflows/release.yml/badge.svg)](https://github.com/sofia-gros/gscript/actions/workflows/release.yml)
[![GitHub Release](https://img.shields.io/github/v/release/sofia-gros/gscript)](https://github.com/sofia-gros/gscript/releases/latest)

[はじめる](#はじめる) · [言語仕様](docs/language.md) · [Go / GS / JS の比較](docs/comparison.md) · [ダウンロード](https://github.com/sofia-gros/gscript/releases)

</div>

```go
func greet(name string) string {
  return "Hello, " + name
}

console.log(greet("GS"))
```

```sh
gs hello.gs --format mjs -o dist/hello.mjs
node dist/hello.mjs
# Hello, GS
```

## GS が大切にしていること

| Go に近い構文 | JavaScript と自然につながる | 実行前に間違いを見つける |
| --- | --- | --- |
| `:=`、`func`、struct、レシーバーメソッド、`range` | オブジェクト、配列 API、npm、`async / await` | 構文・型・スコープ・モジュールの検査 |

GS は独自の言語です。Go のランタイムを移植するものではなく、実行時の数値・参照・非同期処理は JavaScript のモデルに従います。[確定仕様と公開条件](docs/release-plan.md)を実装前に定義し、公開時にも検証しています。

## はじめる

### コンパイラをダウンロード

[GitHub Releases](https://github.com/sofia-gros/gscript/releases/latest) から、OS と CPU に合うアーカイブを選んで展開してください。

- Linux / macOS：展開した `gs` を実行。必要なら `chmod +x gs`。
- Windows：展開した `gs.exe` を実行。
- Python 版：Python 3.12 以上で `python gs-v0.4.0.pyz --version`。
- Python パッケージ：wheel をダウンロードし、`python -m pip install ./gscript_lang-0.4.0-py3-none-any.whl`。

単体実行ファイルには Python を同梱しているため、Python の別途インストールは不要です。各配布物の SHA-256 は Release の `SHA256SUMS` で確認できます。ネイティブ版の実行基盤は、Linux が Ubuntu 22.04 以降、macOS が 14 以降、Windows が Windows Server 2022 / Windows 11 系です。CPU はファイル名に記載します。別の基盤では Python 版を利用してください。

生成した JavaScript の実行には Node.js 22 / 24、または ES2022 Modules を提供する実行環境が必要です。リリースの実行検証対象は Node.js 22 / 24 です。ブラウザーへ組み込む場合は `<script type="module">` や既存のバンドラーを使い、実行環境の API を選んでください。

### チェックアウトから使う

```sh
# Python 3.12 以上。GS 単独のコンパイルには Node / TypeScript は不要です。
python -m pip install .
gs examples/hello.gs --format mjs -o build/hello.mjs
node build/hello.mjs
```

インストールせずに `python -m gscript` でも実行できます。`gscript` コマンドと従来の `.gos` も引き続き使えます。

## 出力形式を選ぶ

```sh
gs hello.gs --format js  -o dist/hello.js
gs hello.gs --format mjs -o dist/hello.mjs
gs hello.gs --format ts  -o dist/hello.ts
```

| `--format` | 生成物 | 実行方法 |
| --- | --- | --- |
| `js` | `.js` の ES2022 Modules | Node.js。出力先に `type: module` を設定 |
| `mjs` | `.mjs` の ES2022 Modules | Node.js が拡張子で module と判断 |
| `ts` | 型注釈付き TypeScript | TypeScript 5.9 で JS に変換して実行 |

`-o` の拡張子からも推論できます。指定がなければ `mjs` です。形式と拡張子が矛盾する引数はエラーになります。

JS / TS のファイル出力では、必要な `package.json` を出力先に作成します。既存の CommonJS 設定は上書きせずエラーにするので、専用の出力ディレクトリか `mjs` を選んでください。標準出力を使う場合のモジュール設定は、保存先のプロジェクト側で管理します。

TS を使う場合の例：

```sh
npm install --save-dev typescript@5.9.3
gs hello.gs --format ts -o dist/hello.ts
npx tsc dist/hello.ts --strict --target ES2022 --module NodeNext --moduleResolution NodeNext --outDir dist/js
node dist/js/hello.js
```

形式の違いは API の違いを埋めません。たとえば `node:fs` はブラウザーでは動作しません。GS は言語の型を検査し、外部の JavaScript API はその API の実行環境に従って扱います。

## 型を検査する

```go
func double(n int) int {
  return n * 2
}

double("wrong") // コンパイルエラー：数値の引数に文字列
```

```sh
gs hello.gs --check
```

構文エラー、未定義名、重複宣言、型の不一致、引数の個数、存在しないプロパティ・export、const の再代入、戻り値の漏れなどを検査します。失敗時はファイル・位置・ソース行を表示し、終了コード `1` を返します。引数の誤りは `2` です。型エラーがある場合、生成物を書き換えません。

GS 同士のモジュールでは型情報を共有します。外部 JS / TS と node_modules は TypeScript の型情報・JSDoc・推論を使って検査します。明示的な `any` は動的な値として扱います。`any` を使っても未定義名の検査は無効になりません。

## モジュールを分ける

```go
// lib/math.gs
export func twice(n int) int {
  return n * 2
}
```

```go
// main.gs
import { twice } from "./lib/math.gs"
console.log(twice(21))
```

```sh
gs main.gs --format mjs --out-dir dist
node dist/main.mjs
```

相対 GS import をたどり、全ファイルを検査してから出力します。import は選んだ形式に合わせて書き換えます。TS の import は、TypeScript の NodeNext が解決できる `.js` 指定になります。

共有モジュールが入口の親ディレクトリにある場合は `--root .` を指定します。ローカル JS / TS の依存も変換・配置します。npm import は保持され、依存パッケージのインストールやバンドルは利用側で行います。

## 外部 JS / TS と node_modules

```sh
npm install --save-dev typescript@5.9.3
npm install phaser@3.90.0
gs game.gs --check
gs game.gs --format mjs --out-dir dist
```

Phaser などの `.d.ts`、ローカル TypeScript、JavaScript の JSDoc を使い、引数・プロパティ・戻り値をコンパイル時に検査します。外部連携には Node.js 22 / 24 と TypeScript 5.9.3 が必要です。型検査キャッシュで再コンパイルを高速化します。

[連携の具体例・出力配置・キャッシュ](docs/interop.md) · [v0.4 公開条件](docs/release-plan-v0.4.md)

## struct・配列・非同期処理

```go
type Person struct {
  Name string
}

func (p Person) Greet() string {
  return "Hello, " + p.Name
}

p := Person{Name: "Sofia"}
console.log(p.Greet())

values := []int{1, 2, 3}
doubled := values.map(func(n int) int { return n * 2 })
for i, n := range doubled {
  console.log(i, n)
}

async func loadText(url string) string {
  response := await fetch(url)
  return await response.text()
}

console.log(await loadText("data:text/plain,Hello"))
```

詳しい構文・型・ゼロ値・参照の意味は [言語仕様](docs/language.md) にまとめています。

## 開発とリリース

```sh
npm ci --ignore-scripts
python -m pip install -r requirements-build.txt
python -m unittest discover -s tests -v

# 単体実行ファイルと Python zipapp。ビルドした実行ファイルも検証します。
python scripts/build_release.py --native --zipapp
python scripts/smoke_compiler.py dist/release/gs-v0.4.0.pyz
```

テストはコンパイラだけでなく、生成した JS / MJS の実行、TS の厳格な型チェックと JS への変換後の実行、インストールしたコンパイラの実行まで確認します。

Release ワークフローは Python 3.12 / 3.13、Node.js 22 / 24、Linux / macOS / Windows で検証します。必須ジョブのどれかが失敗すれば公開しません。コンパイラ、パッケージ、Git タグのバージョンも照合します。

[公開条件](docs/release-plan.md) · [リリースノート](docs/releases/v0.4.0.md) · [ソースコード](https://github.com/sofia-gros/gscript)
