# C ABIとWin32

C ABIを持つライブラリやWindows APIの関数をGSから呼び出します。外部の宣言に記した型と呼び出し規約が、実際のAPIに一致している必要があります。

## Cライブラリと文字列

```go
extern "C" func puts(text cptr<cchar>) i32
puts(cstr("Hello, native"))
```

`string(cPointer)`はNUL終端のC文字列を、コピーしないGS文字列ビューとして読み取ります。元のバッファの寿命は呼び出し側で管理します。`cstr`はGS文字列をNUL終端C文字列として渡します。埋め込みNULは拒否します。`utf16("literal")`はNUL終端UTF-16の読み取り用バッファを生成し、`cptr<u16>`を返します。動的UTF-16変換や書き込み用バッファはライブラリ側で実装します。外部宣言へGSのstringをそのまま渡すことを拒否し、ABIの取り違えを防ぎます。

```sh
python -m gscript app.gs --backend native --link example --library-dir /path/to/libs
python -m gscript app.gs --backend native --link-object /path/to/fixture.o
```


## Windows APIとコールバック

```go
link "kernel32"
extern "system" func GetCurrentProcessId() u32
println(GetCurrentProcessId())
```

```go
type CallbackHolder struct {
  callback winfunc(ptr<void>, u32, usize, isize)isize
}
system func WindowProc(window ptr<void>, message u32, wparam usize, lparam isize) isize {
  return isize(0)
}
value := CallbackHolder{callback: WindowProc}
```

`system`関数と`winfunc`は32bit Windowsではstdcallを使い、64bit Windowsではターゲットの標準Windows ABIを使います。C規約の関数をsystemコールバックへ暗黙に渡すことを拒否します。こうした宣言をGSモジュールへまとめ、ウィンドウ構築・描画用ライブラリを実装できます。今回、ウィンドウ構築・レンダラー自体は作成していません。

```sh
python -m gscript examples/native/win32-probe.gs --backend native \
  --cc /absolute/path/to/zig --target x86_64-windows-gnu -o dist/probe.exe
```

クロスコンパイルには対象のヘッダー／ランタイム／リンクライブラリを備えたツールチェーンが必要です。Zig 0.15.2のWin32 SDKを使う検証では、Windows x64/x86のPE生成、WNDCLASSWとのサイズ・アラインメント・全フィールドoffsetの一致、kernel32連携、systemコールバックを確認します。生成Windowsプログラムの実行はWindows環境で検証します。


## GSからライブラリを公開する

```go
export func add(left, right i32) i32 {
  return left + right
}
```

`--emit object|static|shared --header api.h`でC ABIの公開関数とヘッダーを生成します。Windowsのshared出力では、DLLに加え、同じ名前のインポートライブラリ（Zig/MinGWは`.dll.a`、MSVCリンカーを使うClangは`.lib`）を作成します。利用側では`--link-object /path/to/api.dll.a`等でリンクできます。C、Rustのextern C、C++のC ABI部分等から利用できます。依存GSモジュール内の関数は内部シンボルとして保持し、入口モジュールの公開関数をABIとしてexportします。
