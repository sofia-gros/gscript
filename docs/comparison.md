# Go / gscript / JavaScript

この比較の gscript は実装済みの構文です。JavaScript のレイアウトは説明用に整えています。

## 関数と変数

### Go

```go
package main

import "fmt"

func greet(name string) string {
    return "Hello, " + name
}

func main() {
    name := "Sofia"
    fmt.Println(greet(name))
}
```

### gscript

```go
func greet(name string) string {
  return "Hello, " + name
}
name := "Sofia"
console.log(greet(name))
```

### 生成 JavaScript

```javascript
function greet(name) {
  return ("Hello, " + name);
}

let name = "Sofia";

((console).log)((greet)(name));
```

## struct とメソッド

### Go

```go
type Person struct {
    Name string
}
func (p Person) Greet() string {
    return "Hello, " + p.Name
}
// main 内
p := Person{Name: "Sofia"}
fmt.Println(p.Greet())
```

### gscript

```go
type Person struct {
  Name string
}
func (p Person) Greet() string {
  return "Hello, " + p.Name
}
p := Person{Name: "Sofia"}
console.log(p.Greet())
```

### 生成 JavaScript

```javascript
class Person {
  ["Name"];
  constructor({"Name": __gscript0 = ""} = {}) {
    this["Name"] = __gscript0;
  }
  Greet() {
    const p = this;
    return ("Hello, " + (p).Name);
  }
}

let p = new Person({["Name"]: "Sofia"});

((console).log)(((p).Greet)());
```

レシーバーのローカル名は、メソッド内の通常の関数からも参照できるよう保持しています。Go と異なり、`other := p` はコピーではなく同じインスタンスへの参照です。

## 配列とコールバック

### Go

```go
numbers := []int{1, 2, 3}
doubled := make([]int, 0, len(numbers))
for _, n := range numbers {
    doubled = append(doubled, n*2)
}
for i, n := range doubled {
    fmt.Println(i, n)
}
```

### gscript

```go
numbers := []int{1, 2, 3}
doubled := numbers.map(func(n int) int { return n * 2 })
for i, n := range doubled {
  console.log(i, n)
}
```

### 生成 JavaScript

```javascript
let numbers = [1, 2, 3];

let doubled = ((numbers).map)(((n) => {
  return (n * 2);
}));

for (let [i, n] of (doubled).entries()) {
  ((console).log)(i, n);
}
```

## 非同期処理

### Go

```go
func loadText(url string) (string, error) {
    res, err := http.Get(url)
    if err != nil { return "", err }
    defer res.Body.Close()
    body, err := io.ReadAll(res.Body)
    return string(body), err
}
```

### gscript

```go
async func loadText(url string) string {
  res := await fetch(url)
  return await res.text()
}
text := await loadText("data:text/plain,Hello")
console.log(text)
```

### 生成 JavaScript

```javascript
async function loadText(url) {
  let res = (await (fetch)(url));
  return (await ((res).text)());
}

let text = (await (loadText)("data:text/plain,Hello"));

((console).log)(text);
```

Go の同期的な関数とエラー値に対し、gscript は Promise と例外を使います。失敗は `try` / `catch` で処理できます。両方とも HTTP ステータスがエラーかどうかの判定は別途必要です。
