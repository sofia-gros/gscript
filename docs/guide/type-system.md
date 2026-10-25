# 型の基本

型は、値にどの操作ができるかを表します。GSが基本として扱う型と、nil・undefinedを含む値の規則を確認します。

## 基本型

| 記法 | 意味 |
| --- | --- |
| `int` | 静的に整数として扱うJS Number |
| `float`, `float64` | 浮動小数点として扱うJS Number。両者は別名 |
| `number` | JS Numberを受ける共通の数値型 |
| `string` | JS文字列（UTF-16） |
| `bool`, `boolean` | 真偽値 |
| `[]T` | JS配列 |
| `func(T) R` | 関数型 |
| `Promise<T>` | 非同期処理の結果 |
| `object` | プロパティ集合を限定しないオブジェクト |
| `any` | 動的な値。検査を弱める |
| `unknown` | 型を絞り込んで扱う未知の値 |
| `never` | 値を持たない型 |
| `void` | 戻り値なし。変数や引数の型には使わない |
| `undefined` | JSのundefined型・値 |
| `T?` | `T \| nil` |
| `A \| B` | Union型 |

型名は型エイリアスや外部型の名前でも記述できます。組み込み型の名前は型宣言で再定義できません。


## nilとundefined

`nil`はJSの`null`へ変換されます。`undefined`とは別の値です。既定モードには参照型へのnil代入を許す互換動作があります。`--strict-null`では非Nullableへのnil代入を拒否します。明示的な`T?`の値には、どちらのモードでもnil確認等が必要です。
