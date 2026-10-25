# アクセス制御とstatic

structのメンバーについて、どこから読み書きできるか、インスタンスとクラスのどちらに属するかを指定できます。

## private・protected・readonly

publicが既定です。private / protected / readonlyはコンパイル時の制約です。JSの#privateや深い凍結には変換しません。readonlyの初期化はconstructorで許されます。

```gs
type Parent struct { private HP int; protected Speed int = 3; readonly ID string }
func (p Parent) constructor(id string) { p.ID = id; p.HP = 2 }
func (p Parent) get() int { return p.HP }
type Child struct extends Parent {}
func (c Child) speed() int { return c.Speed }
x := new Child("gs")
console.log(x.ID, x.get(), x.speed())
```

出力:

```text
gs 2 3
```


## staticフィールド・メソッド

staticメンバーはクラス自身に属します。staticフィールドを持つclassとその派生classは宣言位置で評価します。staticメンバーからインスタンスの型パラメーターは参照できません。

```gs
type MathHelper struct { static Count int = 1 }
static func (m MathHelper) square(n int) int { m.Count += 1; return n * n }
type Derived struct extends MathHelper {}
console.log(Derived.square(5), MathHelper.Count)
```

出力:

```text
25 1
```
