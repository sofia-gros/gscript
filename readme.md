# gscript

この言語はGo言語風であり、javascriptにコンパイルされます。

開発状況は、やりたいことが見つかれば追記していきます。

## 開発状況
- [x] 変数宣言
- [x] 関数宣言
- [x] 関数呼び出し
- [x] Class
- [x] クラス呼び出し (new)
- [x] 非同期処理 (async, await)
- [x] 計算 & 比較 (+ - / * > < >= <= == !=)
- [x] for
- [x] printf
- [x] セミコロン任意化
- [ ] 型の評価
- [ ] struct構文

```go
import path from "pathlib"

let a string = "a"
let b number = 0.2

func main() bool {
  return true
}

class Person {
  prop object = {}
  method(name string) string {}
}

for(let i number = 0; i < 10; i = i + 1) {}
```
