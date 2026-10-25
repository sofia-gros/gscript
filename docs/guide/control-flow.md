# 条件分岐とループ

条件で処理を分けたり、同じ処理を繰り返したりする構文を説明します。if・forはGoに近い見た目ですが、rangeの1変数形式には意味の違いがあります。

## 条件分岐

```gs
n := 3
if n > 0 {
  println("positive")
} else if n == 0 {
  println("zero")
} else {
  println("negative")
}
```


## ループの全形式

```gs
for i := 0; i < 3; i++ { println(i) }
var n int = 0
for n < 3 { n++ }
for { break }
values := []int{10, 20}
for index, value := range values { println(index, value) }
for value := range values { println(value) }
```

GSのrangeは1変数なら**値**、2変数なら添字と値です。Goの1変数range（添字）とは異なります。`break`でループを抜け、`continue`で次へ進みます。Goのラベル付き制御はありません。


## switch

```gs
type State = "idle" | "walk" | "run"
func speed(state State) int {
  switch state {
  case "idle": return 0
  case "walk", "run": return 1
  }
}
println(speed("walk"))
```

値は一度評価され、caseは厳密等価で比較します。暗黙のfallthroughはありません。`default:`も使えます。defaultなしで有限Unionやenumを扱う場合は網羅性を検査します。
