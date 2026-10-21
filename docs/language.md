# gscript 0.2 言語仕様

## コンパイル単位

1つの `.gos` は1つの ES Module です。名前付き関数・struct・import はモジュール内で前方参照可能です。変数の直接参照は宣言後に限ります。関数の本体は周囲の宣言を収集した後に検査するため、クロージャーから後続の変数を参照できます。ただし、その変数の初期化前に関数を呼び出した場合は JavaScript の実行時エラーになります。

import と export と struct とレシーバーメソッドはモジュール直下に置きます。import と struct と関数の生成コードを先に配置し、その他のトップレベルの文は元の順序で配置します。変数宣言の副作用の順序は保持されます。

モジュールのビルドでは、入口から到達できる相対 `.gos` import のみを処理します。外部パッケージ、JS ファイル、動的 import はコンパイラで解決しません。プロジェクトルート外を参照する場合は、明示的に `--root` を広げてください。型情報のモジュール間共有は今後の課題です。

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

関数・パラメーター・プロパティの型は単純な構造として保持します。struct の型は名前で区別します。オブジェクトリテラルはプロパティごとの型を推論します。関数を変数に代入してもシグネチャを保持します。

引数の型を完全に省略したものは any です。`func f(a, b int)` のようなグループ記法では、直前の型なし引数も後続の型を使います。関数の戻り値型を省略すると void で、戻り値の型推論は行いません。

`async func f() string` は文字列を返す async 関数で、呼び出し結果の型は `Promise<string>` です。await は Promise の型を取り出し、Promise 以外への await は元の型になります。

戻り値を持つ関数では、if/else・try/catch・ループの終了経路を検査します。値の真偽を一般に証明するわけではないため、複雑な条件で必ず return していても、静的に確認できなければ missing return になる場合があります。

## オブジェクトと struct

struct は own property を持つ class です。コンストラクターにはプロパティのオブジェクトを渡します。コンパイラは内部の一時変数名がソース中の名前と衝突しないように生成します。`__proto__` も通常のフィールドとして保持します。

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
python -m unittest discover -s tests -v
python -m gscript examples/main.gos -o build/main.mjs
node build/main.mjs
python -m gscript examples/modules/main.gos --out-dir build/modules
node build/modules/main.mjs
```

テストは文字列の出力比較だけでなく、Node.js で生成したコードを実行し、型・構文・スコープの不正なプログラムを拒否することを検査します。CLI、複数モジュール、循環 import、失敗時の出力保持も検査します。

今後の課題は、モジュール間の型共有、JS 型定義との相互運用、ソースマップ、型の拡充です。Go の完全互換や goroutine の実行基盤は、この実装には含めていません。
