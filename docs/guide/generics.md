# Generics

同じ処理を型ごとに書き直したくないときは型パラメーターを使います。関数だけでなく、struct・interface・型エイリアスにも宣言できます。

## Generics・制約・型引数推論

function・struct・interface・型エイリアスで<T, U extends Constraint>を使えます。JSでは型情報を消去し、型ごとの特殊化コードは生成しません。

```gs
type Container<T> struct { Value T }
func (c Container<T>) get() T { return c.Value }
type Pair<K, V> struct { Key K; Value V }
type Has<T> interface { Value T }
type Result<T> = T | nil
func identity<T>(value T) T { return value }
func max<T extends number>(a T, b T) T { if a > b { return a }; return b }
x := Container<int>{Value: 100}
var item Has<int> = x
pair := Pair<string, int>{Key: "gs", Value: 3}
var result Result<int> = nil
console.log(x.get(), item.Value, pair.Key, identity("ok"), max<int>(3, 4))
```

出力:

```text
100 100 gs ok 4
```
