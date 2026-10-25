# GS v0.5

> このページはJS / TS経路のガイドです。言語全体は[実行モデル](execution-models.md)、ソース版のネイティブ機能は[Native](native.md)を参照してください。

GSはGo風構文をJavaScript ES2022へ変換する静的型付き言語です。GSの構文、スコープ、型、モジュールはGSコンパイラが検査します。外部の型定義はTypeScript APIで読み取ります。

```go
func greet(name string) string {
  return "Hello, " + name
}
println(greet("GS"))
```

v0.4の[言語拡張](language-v0.4-extensions.md)（継承、interface、generics、union、nullable、enum、アクセス制御、async）を維持し、[数値型](numeric-types.md)、[組み込み](builtins.md)、[配列](arrays.md)を厳密化しました。[移行手順](migration-v0.4-to-v0.5.md)を参照してください。

`float64`は`float`の別名です。`number`はJSとの共通数値型で、int/floatを受け取れますが、逆方向には明示変換が必要です。数値表現はすべてJS Numberです。既定の参照型nil互換を維持し、`--strict-null`でnullableを厳密に検査します。
