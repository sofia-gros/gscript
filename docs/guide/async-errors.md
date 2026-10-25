# 非同期処理と例外

JSの非同期APIを使う処理はasync / awaitで記述します。このページではPromiseを返す関数の書き方と、処理が失敗したときの例外処理を説明します。

## 非同期処理と例外

```gs
async func loadText(url string) string {
  response := await fetch(url)
  return await response.text()
}
try {
  text := await loadText("data:text/plain,Hello")
  println(text)
} catch err {
  println(err.message)
}
```

`async func f() T`の呼び出し結果はPromise<T>です。awaitはPromiseの中の型を取り出します。トップレベルawaitもJSモジュールで使用できます。fetchの存在は実行環境に依存します。`throw expression`で例外を送出し、`try { ... } catch name { ... }`で受け取ります。Goのgoroutineやerror値による処理とは別です。finally、defer、channel、go文は未対応です。
