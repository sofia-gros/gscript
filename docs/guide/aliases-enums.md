# 型エイリアスとenum

既存の型に意味のある名前を付けるには型エイリアス、選択肢の集合を宣言するにはenumを使います。どちらもGoの同名機能と意味が完全には一致しません。

## オブジェクト型・関数型・型エイリアス

型エイリアスはJSで消去します。無条件の循環aliasは拒否しますが、objectやarrayを介する再帰型は許可します。

```gs
type UserID = string
type Position = {x: number, y: number}
type Callback = func(int) int
func apply(cb Callback, n int) int { return cb(n) }
var p Position = {x: 2, y: 3}
var id UserID = "gs"
console.log(id, p.x, apply(func(n int) int { return n * 2 }, 3))
```

出力:

```text
gs 2 6
```


## 数値enum・文字列enum

数値enumは0から自動増分します。文字列enumでは全メンバーに値が必要です。数値と文字列は混在させません。実行時は凍結オブジェクト、型は値のUnionです。別enumでも同じ値集合なら構造的に互換です。

```gs
type State enum { Idle; Walk; Attack }
type Direction enum { Up = "up"; Down = "down" }
func read(state State) int {
 switch state { case State.Idle: return 1; case State.Walk, State.Attack: return 2 }
}
var d Direction = Direction.Up
console.log(read(State.Walk), d, Object.isFrozen(State))
```

出力:

```text
2 up true
```


## 再帰型と省略可能プロパティ

```gs
type Link = {value: int; next: Link?}
type Options = {value?: int}
var options Options = {}
println(options.value ?? 3)
```

省略可能プロパティにはundefinedが含まれます。型宣言は型検査後に消去されます。
