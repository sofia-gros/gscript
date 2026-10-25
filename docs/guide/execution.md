# コンパイルと実行

GScript（GS）は、Go風の宣言構文とJavaScriptのAPI・モジュールを組み合わせた静的型付き言語です。ソースは`.gs`（旧`.gos`も利用可能）に記述します。Goの別実装ではなく、独立した言語です。

## 2つの実行モデル

| | JavaScript / TypeScript出力 | ネイティブ出力 |
| --- | --- | --- |
| 変換 | GS → GS型検査 → JS / MJS / TS | GS → GS型検査 → C11 → Cコンパイラ → 機械語 |
| 実行 | Node.js、またはブラウザー等のJS環境 | 対象OSの実行ファイル |
| ライブラリ | JS / TS、npm、Node.js・ブラウザーのAPI | C ABI / Windows system ABI |
| メモリ | JSのガベージコレクション | 値とポインター。外部メモリの寿命は利用側で管理 |
| 対応構文 | [文と式](control-flow.md)・[型とオブジェクト](structs.md) | [ネイティブ言語仕様](native-types.md)の静的な部分集合 |

ネイティブ実行にJSエンジンは使いません。npmやDOMがネイティブでそのまま動くわけではありません。ネイティブ用ライブラリはC ABIを使って実装します。ネイティブバックエンドはv0.6.0では実験的です。

## 実行開始とモジュール

```gs
func greet(name string) string {
  return "Hello, " + name
}
println(greet("GScript"))
```

トップレベルの文が実行されます。Goの`package main`や暗黙の`main`呼び出しはありません。

```gs
func main() { println("Hello") }
main()
```

関数を`main`と名付けても、呼び出す文が必要です。これは両バックエンドで共通です。

JS経路では1ファイルが1つのES Moduleです。GSモジュール間で型を共有して検査し、トップレベルの副作用の順序を保持します。関数を前方参照できても、未初期化の変数を読む関数を早く呼び出すと実行時エラーになります。

## 何をコンパイラが検査するか

GSコンパイラ自身が構文、名前、スコープ、代入、引数、戻り値、メンバーアクセス等を検査します。外部JS / TSの型定義はTypeScript APIで読み取りますが、GSコードの型検査をTypeScriptへ委譲しません。

```gs
var count int = "three" // コンパイルエラー
```

型検査は外部ライブラリの実装が宣言どおり動くことや、任意の`any`の安全性まで保証しません。JS経路では生成後のAPIの存在や実行時環境も必要です。

## JSとしての意味

GSの型注釈はJSで消去します。structはJS class、配列はJS Array、数値はJS Numberです。Node.jsのAPIを使うコードにはNode.jsが、DOMを使うコードにはブラウザー等が必要です。TS出力は実行環境ではなく、さらにJSへ変換して利用するソースです。

次は[基本・数値・演算](variables.md)、GoやJSとの違いは[比較](comparison.md)を参照してください。
