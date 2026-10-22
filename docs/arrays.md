# 配列

```go
values := []int{1, 2, 3}
values.push(4)
next := values.map(func(n int) int { return n + 1 })
println(next.join(","), len(values))
```

配列の要素型は宣言・push/unshift・concat・検索・コールバックの引数と戻り値で検査します。int配列にfloatは追加できません。添字、length、検索位置はintです。pop/shift/findの戻り値にはundefinedを含みます。厳密に扱うには`--strict-null`を使います。

map/filter/find/forEach/some/every、push/pop/shift/unshift、slice/concat/includes/indexOf、join/reverse/sort、entries/keys/valuesを認識します。配列はJSの可変参照です。境界外アクセスはJSに従いundefinedとなり、実行時の境界検査は追加しません。
