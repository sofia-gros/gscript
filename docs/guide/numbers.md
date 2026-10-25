# 数値と演算

GSは整数・浮動小数点・外部JSの数値を静的に区別します。まず数値の推論規則を確認してから、変換と演算の意味を見ていきます。

## 数値の推論・変換

```gs
integer := 10
fraction := 10.0
exponent := 1e2
var external number = integer
var narrowed int = int(external)
println(integer / 4, int(integer / 4), float(integer))
```

`10`はint、`10.0`・`1e2`はfloatです。intとfloat間の暗黙変換はありません。両方をnumberへ渡せますが、numberから狭める場合は明示変換します。int同士の`/`の結果もfloatです。

`int(x)`は`Math.trunc(x)`、`float(x)`・`float64(x)`・`number(x)`は`Number(x)`です。整数専用の実行時表現やBigIntには変換しません。精度限界、NaN、InfinityはJSの規則です。


## 演算と代入

| 分類 | 記法 |
| --- | --- |
| 四則・余り | `+ - * / %` |
| 比較 | `== != < > <= >=` |
| 論理・否定 | `&& || !` |
| 符号 | `+x`, `-x` |
| 代入 | `=`, `+=`, `-=` |
| 更新 | `i++`, `i--`（文として使用） |
| メンバー・添字 | `value.name`, `values[index]` |
| 呼び出し・生成 | `f(args)`, `new T(args)` |
| 型判別 | `typeof value`, `value instanceof T` |
| null対応 | `value?.name`, `value?.[i]`, `f?.()`, `value ?? fallback` |

優先順位は低い方から`||`と`??`（同順位）、`&&`、等値比較、大小比較・instanceof、加減算、乗除算・余り、単項演算です。`??`の混在には後述の括弧規則が適用されます。括弧で評価順を明示できます。論理演算と`??`は短絡評価します。`??`と`&&` / `||`を混ぜる場合は括弧が必要です。switchと等値比較はJSの厳密な比較を使用します。
