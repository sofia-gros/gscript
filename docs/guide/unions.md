# UnionとNullable

値が複数の型を取り得る場合はUnionを使います。値を確認して型を絞り込む方法と、nilを含む値へ安全にアクセスする方法を説明します。

## Nullableとnilによる絞り込み

T?はT | nilです。比較で絞り込んでからアクセスします。?.と??はJSの短絡評価を保持します。

```gs
type Item struct { Value int }
func read(x Item?) int {
 if x != nil { return x.Value }
 return 0
}
func optional(x Item?) int { return x?.Value ?? 8 }
console.log(read(nil), optional(nil), optional(Item{Value: 3}))
```

出力:

```text
0 8 3
```


## オプショナルアクセス・呼び出し

?.name、?.[index]、?.(args)を使えます。??はnil / undefinedの場合に右辺へ進み、0やfalseを置換しません。

```gs
type Item struct { get func() int }
func read(x []int?) int { return x?.[0] ?? 7 }
var call func() int = func() int { return 4 }
console.log(read(nil), call?.() ?? 0, 0 ?? 9)
```

出力:

```text
7 4 0
```


## 型エイリアス・Union・リテラル型・typeof

Unionは文字列・数値・真偽値のリテラル型も含められます。nil比較、typeof、instanceofによる絞り込みを利用できます。

```gs
type Direction = "up" | "down"
type Value = string | number
func read(x Value) string {
 if typeof x == "string" { return x.toUpperCase() }
 return "number"
}
func move(d Direction) { console.log(d) }
move("up")
console.log(read("gs"), read(3))
```

出力:

```text
up
GS number
```
