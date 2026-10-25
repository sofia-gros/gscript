# 配列とオブジェクト

複数の値を扱うときは配列を、名前付きの値をまとめるときはオブジェクトを使います。JS経路ではどちらも参照を共有する値です。

## 配列

```gs
values := []int{1, 2, 3}
values.push(4)
next := values.map(func(n int) int { return n + 1 })
println(next.join(","), values[0], len(values))
```

配列は可変の参照です。`map/filter/find/forEach/some/every`、`push/pop/shift/unshift`、`slice/concat/includes/indexOf`、`join/reverse/sort`、`entries/keys/values`を認識し、要素・コールバックを検査します。`pop/shift/find`はundefinedを含む結果を返します。添字・length・検索位置はint。lengthへの直接代入は不可です。

境界外アクセスはJSに従ってundefinedとなり、境界検査は追加しません。Goのsliceの容量・append・makeの仕様とは異なります。


## オブジェクトとspread

```gs
user := {name: "GS", age: 2}
updated := {...user, age: 3}
println(updated.name)
```

プロパティごとの型を推論し、spreadは左から右へ適用します。any / objectのspreadでは静的なプロパティ集合を確定できずobjectになります。


## 配列・呼び出しのspread

```gs
values := []int{1, 2}
copy := []int{...values, 3}
console.log(...values)
println(copy[2])
```

呼び出しのspreadは動的なJS呼び出しで利用します。静的なGS関数には引数を個別に渡します。

オブジェクトでは`{name}`というプロパティ省略記法も使えます。spreadを受ける関数を定義するJS風のrest引数宣言とは別です。
