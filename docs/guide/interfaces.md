# interface

interfaceは、値が提供するフィールドやメソッドを宣言します。特定のstructそのものではなく、必要な形に依存した関数を書くために使います。

## interfaceとimplements

interfaceは構造的な型です。interfaceは複数extends、structは複数implementsを指定できます。関数引数は反変、戻り値は共変で検査します。interface自体は実行時の値にはなりません。

```gs
type Named interface { Name string }
type Entity interface extends Named { get() int }
type Player struct implements Entity { Name string; HP int }
func (p Player) get() int { return p.HP }
func read(e Entity) int { return e.get() }
console.log(read(Player{Name: "GS", HP: 5}))
```

出力:

```text
5
```
