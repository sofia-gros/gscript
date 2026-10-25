# 継承と初期化

既存のstructを拡張する場合はextendsを使います。ここでは親と子の初期化順序、constructorの引数、メソッドの上書きを1つの例で確認します。

## 継承・constructor・super・override

structは単一継承です。独自constructorは位置引数を受け、この場合T{...}は使えません。派生constructorは最初の実行文としてsuperを一度呼びます。親constructor→派生フィールド→派生constructor本体の順に初期化します。constructorを省略した派生structは親の引数を転送します。overrideを省略しても上書きの型は検査します。

```gs
type Child struct extends Parent { Extra int = 2 }
type Parent struct { Value int }
func (p Parent) constructor(n int) { p.Value = n }
func (p Parent) get() int { return p.Value }
func (c Child) constructor(n int) { super(n); c.Extra = 4 }
override func (c Child) get() int { return super.get() + c.Extra }
x := new Child(3)
var parent Parent = x
console.log(parent.get(), x instanceof Parent)
```

出力:

```text
7 true
```
