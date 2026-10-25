# ネイティブ実行とFFI

ソース版で利用できる実験的なAOTバックエンドです。公開済みコンパイラv0.5.0のバイナリには未収録です。

```text
GS → ネイティブ型検査 → C11 + GSランタイム → Clang / GCC / Zig → 機械語
```

生成アプリケーションはNode.js・Python・JSエンジンを使わず動作します。OSのCランタイムと、アプリケーションがリンクした外部ライブラリは必要です。Windows向けの生成物はPE実行ファイルです。

## 導入と実行

Python 3.12以降を使い、リポジトリーで実行します。

```sh
git clone https://github.com/sofia-gros/gscript.git
cd gscript
python -m gscript examples/native/hello.gs --backend native
./examples/native/dist/native/hello
```

Linux/macOSではPATH上のClang・cc・gccを順に検出します。GCC互換のC11ドライバーを使います。MSVCの`cl.exe`形式のオプションには対応していません。

Zigは[公式配布](https://ziglang.org/download/)のアーカイブを展開し、実際の実行ファイルのパスを指定できます。検証版は0.15.2です。

```sh
python -m gscript examples/native/hello.gs --backend native --cc /absolute/path/to/zig
```

Windows PowerShell:

```powershell
python -m gscript examples/native/hello.gs --backend native --cc C:\Tools\zig\zig.exe
.\examples\native\dist\native\hello.exe
```

`gs`コマンドとして使う場合は仮想環境へ`python -m pip install -e .`でソース版を導入します。公開済みv0.5.0の`gs`と混同しないよう、使用中の実行ファイルを確認してください。

## 出力

```sh
python -m gscript main.gs --backend native -o dist/app
python -m gscript main.gs --backend native --out-dir build
python -m gscript main.gs --backend native --check
python -m gscript main.gs --backend native --emit c -o build/main.c
python -m gscript api.gs --backend native --emit object -o build/api.o
python -m gscript api.gs --backend native --emit static -o build/libapi.a
python -m gscript api.gs --backend native --emit shared -o build/libapi.so --header build/api.h
```

既定は`dist/native/<入力名>`です。Windowsの既定実行ファイルには`.exe`、オブジェクトには`.obj`、共有ライブラリには`.dll`、静的ライブラリには`.lib`を使います。macOSの共有ライブラリの既定は`.dylib`です。`-o`は明示した名前を使います。

`--check`と`--emit c`にはCコンパイラが不要です。Cのコンパイル・リンクには180秒のタイムアウトを設けます。コンパイル・リンクが失敗した場合、既存のバイナリは更新しません。JS / TS用の`--format`、minify、Source Map、TSコンパイラ選択とは分離しています。

GSのトップレベル文をモジュール依存順に実行します。`main`というGS関数は通常の関数です。`func main() { ... }`を使う場合はGS側で`main()`を呼び出します。ライブラリ出力ではトップレベルの実行文を拒否し、グローバルは定数で初期化できる値に限定します。

## 型とメモリの規則

ネイティブ経路はC ABIに接続するため、型の表現を明確に分けます。

| 型 | ネイティブ表現 |
| --- | --- |
| int | 符号付き64bit整数 |
| float / float64 / number / f64 | IEEEのdouble |
| f32 | Cのfloat |
| i8/u8/i16/u16/i32/u32/i64/u64 | 対応する固定幅整数 |
| isize / usize | ターゲットのポインター幅の整数 |
| bool | Cのbool |
| cchar | Cのchar。主にC文字列のポインターで使用 |
| ptr<T> / cptr<T> | 可変／読み取り用のCポインター |
| func(...)Result | C呼び出し規約の関数ポインター |
| winfunc(...)Result | Windows system呼び出し規約の関数ポインター |
| struct / union | Cレイアウトの値型 |
| [N]T | インラインの固定長配列 |
| string | UTF-8の読み取り用データとバイト長 |

ネイティブのstructは値としてコピーされます。参照共有が必要なら`ptr<T>`を明示します。JS経路のstructの参照意味論とは異なります。ネイティブの`len(string)`はUTF-8のバイト数、JS経路はUTF-16コード単位数です。ネイティブ文字列は現在、リテラルとC文字列からの読み取り用ビューを扱い、動的な連結は未対応です。

数値幅の暗黙変換を拒否します。`i32(value)`、`u64(value)`、`f32(value)`等を明示します。整数の定数範囲をコンパイル時に検査し、実行時の符号付き加減乗算オーバーフロー、整数除算、変換範囲、固定長配列の添字をチェックします。符号なし演算はその幅で周回します。整数同士の`/`はfloatを返し、整数除算には`idiv`を使います。

ポインターは低レベルのFFI機能です。有効なアドレス、所有権、アラインメント、配列境界、コールバックの署名・寿命を呼び出し側が守る必要があります。Rustの借用検査やGCを実装したという意味ではありません。メモリの確保・解放はC ABIのallocator等を使うライブラリで管理できます。

## ポインター・レイアウト

```go
type Point struct { X i32; Y i32 }
p := Point{X: i32(2), Y: i32(3)}
q := address(p)
q.X = i32(4)
println(p.X, sizeof<Point>(), alignof<Point>(), offsetof<Point>("Y"))

var buffer [16]u8
buffer[0] = u8(42)
println(buffer[0], len(buffer))
```

`address`、`load`、`store`、`offset`、`cast<T>`を使用できます。`cptr<T>`への書き込みを拒否します。`cast`によるポインター・関数ポインター変換は明示的な低レベル操作で、実際のABIとの一致は利用側の責任です。

固定長配列はゼロ初期化した保存領域として宣言します。全体の代入・コピー・値渡しは現在未対応です。structのフィールド名、レイアウト、パディングはターゲットのCコンパイラで確定し、生成ヘッダーにはGSのフィールド名をコメントで対応付けます。

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

`--emit object|static|shared --header api.h`でC ABIの公開関数とヘッダーを生成します。Windowsのshared出力では、DLLに加え、同じ名前の`.dll.a`インポートライブラリを作成します。利用側では`--link-object /path/to/api.dll.a`等でリンクできます。C、Rustのextern C、C++のC ABI部分等から利用できます。依存GSモジュール内の関数は内部シンボルとして保持し、入口モジュールの公開関数をABIとしてexportします。

## 現在の対応範囲

静的な関数・再帰、変数・定数、if、for、break/continue、基本数値・bool・文字列、C-layout struct/union、型エイリアス、固定長配列、ポインター、関数ポインター、名前付きGS import/export、C/system FFIを対象とします。

async、クロージャ、generics、継承、interface、動的配列、JSの動的オブジェクト、例外、ネイティブ用のエディター統合は今後の対象です。未対応コードはGSコンパイラがエラーにし、JS経路へ自動で切り替えることはありません。npm・Node・DOMを使うコードは[JS / TS経路](typescript-interop.md)で利用できます。
