# 関数

関数は処理に名前を付け、引数を受け取り、結果を返します。GSでは関数の入口と出口の型を宣言し、その呼び出しをコンパイル時に検査します。

## 関数・引数・戻り値

```gs
func add(a, b int) int { return a + b }
func show(value string) { println(value) }
var twice func(int) int = func(n int) int { return n * 2 }
println(add(2, 3), twice(4))
```

型を後ろに書きます。`a, b int`は両方がintです。型を完全に省略した引数はany、戻り値型を省略するとvoidです。戻り値型の推論は行いません。戻り値ありの関数は終了経路を検査します。無名関数は外側の変数を捕捉できます。
