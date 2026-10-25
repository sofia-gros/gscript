# structとメソッド

同じ形のデータと振る舞いを何度も使うときはstructを定義します。まずフィールドを持つ型を作り、その型にメソッドを追加してみましょう。

## structとレシーバーメソッド

```gs
type Person struct { Name string }
func (p Person) greet() string { return "Hello, " + p.Name }
p := Person{Name: "GS"}
println(p.greet())
```

JSではclassのインスタンスです。代入は参照共有であり、GoやネイティブGSのstructのような値コピーではありません。独自constructorのない基本structでは`new Person({Name: "GS"})`も使えます。レシーバー名はthisのローカル別名となり、内側の関数からも参照できます。
