# GS 0.4 言語仕様

## コンパイル単位

1つの `.gs`（従来の `.gos` も可）は1つの ES Module です。名前付き関数・struct・import はモジュール内で前方参照可能です。変数の直接参照は宣言後に限ります。関数の本体は周囲の宣言を収集した後に検査するため、クロージャーから後続の変数を参照できます。ただし、その変数の初期化前に関数を呼び出した場合は JavaScript の実行時エラーになります。

import と export と struct とレシーバーメソッドはモジュール直下に置きます。`export default expression` によるデフォルト値の公開も可能です。import と struct と関数の生成コードを先に配置し、その他のトップレベルの文は元の順序で配置します。変数宣言の副作用の順序は保持されます。

モジュールのビルドでは、入口から到達する GS モジュールと外部 JS / TS を検査します。GS モジュール間では型情報を共有し、外部モジュールには TypeScript の解決と型検査を使います。プロジェクトルート外の共有ソースには `--root` を指定します。npm import は保持し、ローカル JS / TS は選択した形式で配置します。動的な値から組み立てる import の実行先は静的には決定しません。

## 型

| 記述 | 意味 |
|---|---|
| `int`, `float`, `float64`, `number` | JS Number |
| `string` | JS string |
| `bool`, `boolean` | JS boolean |
| `[]T` | T の配列。JS Array |
| struct 名 | 宣言された class のインスタンス |
| `func(T, U) R` | 引数・戻り値の型を持つ関数 |
| `Promise<T>` | T に解決する Promise |
| `object` | プロパティを静的に限定しないオブジェクト |
| `any` | 動的な JS 値 |
| `void` | 戻り値なし。変数・フィールド・引数の型としては不可 |

組み込み型の名前は型宣言・型 import の別名として再定義できません。

関数・パラメーター・プロパティの型は単純な構造として保持します。struct の型は名前で区別します。オブジェクトリテラルはプロパティごとの型を推論します。関数を変数に代入してもシグネチャを保持します。

引数の型を完全に省略したものは any です。`func f(a, b int)` のようなグループ記法では、直前の型なし引数も後続の型を使います。関数の戻り値型を省略すると void で、戻り値の型推論は行いません。

`async func f() string` は文字列を返す async 関数で、呼び出し結果の型は `Promise<string>` です。await は Promise の型を取り出し、Promise 以外への await は元の型になります。

戻り値を持つ関数では、if/else・try/catch・ループの終了経路を検査します。値の真偽を一般に証明するわけではないため、複雑な条件で必ず return していても、静的に確認できなければ missing return になる場合があります。

## オブジェクトと struct

struct は own property を持つ class です。コンストラクターにはプロパティのオブジェクトを渡します。コンパイラは内部の一時変数名がソース中の名前と衝突しないように生成します。`__proto__` も通常のフィールドとして保持します。

型が分かる struct には `Person{Name: "Sofia"}` と `new Person({Name: "Sofia"})` の両方を利用できます。import の別名でも型を検査します。

メソッドではレシーバー名を this のローカル別名にします。これにより、内部の関数やクロージャーからレシーバーを参照できます。別のスコープで同名の変数を宣言した場合は、そのローカル変数を参照します。

オブジェクトリテラルの spread は左から右へ適用されます。動的な object/any を spread した結果は静的なプロパティ集合を確定できないため object になります。

配列の `length` と文字列の添字は gscript では書き換え不可です。配列の長さを変えるには push/unshift などを使います。

## エラーと出力

公開 API:

```python
from gscript import CompileError, compile_source

try:
    javascript = compile_source('var n int = "bad"')
except CompileError as error:
    print(error.line, error.message)
```

CLI は構文エラーに行・列、意味エラーに行番号を表示します。ソース行も表示し、終了コード 1 を返します。コンパイル成功は Node.js での実行成功を保証するものではありません。

出力先はコンパイル完了まで変更しません。単一ファイルは同一ディレクトリ内の一時ファイルから置換します。モジュール群は全ソースの検査が終わってから書き込みます。既存出力の消去や、不要になった生成ファイルの削除は行いません。

## 開発時の検証

```bash
npm ci --ignore-scripts
python -m unittest discover -s tests -v
python -m gscript examples/main.gos -o build/main.mjs
node build/main.mjs
python -m gscript examples/modules/main.gos --out-dir build/modules
node build/modules/main.mjs
```

テストは文字列の出力比較だけでなく、Node.js で生成したコードを実行し、型・構文・スコープの不正なプログラムを拒否することを検査します。CLI、複数モジュール、循環 import、失敗時の出力保持も検査します。

GS はここに記載した言語構文と JavaScript の実行モデルを仕様とします。Go の goroutine・channel・ポインター・標準ライブラリは GS 0.4 の構文・ランタイムには含まれません。これは Go 互換という約束ではなく、Go の構文を参考にした独立した言語です。

## 出力形式

`--format js|mjs|ts` はファイル拡張子だけでなく、ローカル import の指定と TS の型注釈を制御します。JS と MJS は ES2022 Modules です。JS 出力は type=module の設定を出力先に用意します。既存の CommonJS package 設定は自動変更しません。TS は TypeScript 5.9 の strict / ES2022 / NodeNext で検査します。TS の import は変換後の JS ファイルを指します。

GS の nil は参照型の null です。TS 出力での null の非 null 表明は型消去後も実行時の null を保持し、GS にない null フロー解析を追加するものではありません。範囲外アクセス、外部 API、明示的な any は実行時の JS の振る舞いに従います。

## 対応環境と仕様上の境界

公開時の実行検証対象は Node.js 22 / 24、TypeScript 5.9.3、Python 3.12 / 3.13 です。ネイティブコンパイラは Release に記載した OS・CPU の組み合わせで配布します。生成物は JS の API を移植したり polyfill を挿入したりしません。npm の導入やブラウザー固有 API の用意は実行プロジェクトの役割です。

すべての参照型が常に非 null であることや配列の範囲内アクセスは、GS の型の保証には含めません。関数の実行による初期化順序まで一般に証明することもしません。直接の循環したモジュール値初期化はエラーにします。これらの動作は実装後に残した未実装ではなく、公開前に定義した JavaScript ベースの言語の意味です。

## GS 0.4 の外部型連携

外部 import は型定義を読み込み、GS自身がプロジェクトのコンパイル時に検査します。外部型名・名前空間を GS の型注釈として使えます。詳細は [外部連携仕様](interop.md) を参照してください。従来の外部 import を一律 any とする記述は、ファイルを持たない compile_source API に限ります。

継承・interface・Genericsなどの追加構文と型規則は [v0.4拡張仕様](language-v0.4-extensions.md) を参照してください。
