# 組み込み関数

GSには表示・長さ・変換・例外送出のための少数の組み込みがあります。このページはJS経路の動作を説明します。

## 組み込み関数

| 記法 | JS経路の動作 |
| --- | --- |
| `print(...)`, `println(...)` | 両方ともconsole.log。改行あり |
| `printf(format, ...args)` | console.log(format, ...args)。Go fmtの書式仕様ではない |
| `len(x)` | 配列・文字列のlength、外部Map/Setのsize |
| `int`, `float`, `float64`, `number`, `string` | 明示変換 |
| `panic(x)` | Errorをthrow |

文字列の`len`はUTF-16コード単位数です。同名のユーザー宣言は組み込みを隠します。
