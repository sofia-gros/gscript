# ネイティブコンパイルと実行

GSコードをClang・GCC・Zigのいずれかで機械語にコンパイルし、生成した実行ファイルを動かします。このページは実験的なネイティブ経路の手順です。JS / TS出力にはこれらのCコンパイラは不要です。

## どのコマンドを使うか

GSファイルをコンパイルする入口は、どのツールでも`gs`です。`--backend native`でネイティブ出力を選び、`--cc`で使うCコンパイラを指定します。

```text
hello.gs → GSの構文・型検査 → C11 → 指定したCコンパイラ → 実行ファイル
```

| ツール | 指定例 | GSが内部で起動するもの |
| --- | --- | --- |
| Clang | `--cc clang` | `clang` |
| GCC | `--cc gcc` | `gcc` |
| Zig | `--cc zig` | `zig cc` |

`--cc`へ渡すのは**実行ファイル1つの名前またはパス**です。`--cc "zig cc"`とは書きません。`clang hello.gs`や`zig cc hello.gs`のようにGSファイルを直接渡すこともできません。

`--cc`を省略するとPATH上の`clang`、`cc`、`gcc`の順に探します。Zigは自動選択しないため、Zigを使う場合は必ず`--cc zig`または実際のパスを指定してください。

## 最初のGSファイル

作業フォルダーに`hello.gs`を作成します。

```gs
func twice(value int) int {
  return value * 2
}
println("Hello, native", twice(21))
```

実行時の出力:

```text
Hello, native 42
```

以下のコマンドは、このファイルのあるフォルダーで実行します。どのCコンパイラを選んでも、同じGSコードを使用します。

## Windows：Zigでコンパイルする

PowerShellで確認します。管理アプリでPATHへ追加した場合は、先に**新しいターミナルを開いてください**。

```powershell
gs --version
zig version
gs hello.gs --backend native --cc zig -o .\build\hello-zig.exe
.\build\hello-zig.exe
```

`build`フォルダーはGSが作成します。コンパイル成功後に、生成した`.exe`を実行します。生成アプリの実行にNode.js・Python・Zigは不要ですが、OSのランタイムやリンクした外部DLLは必要です。

PATHへ追加していない場合は、それぞれの実際の保存先を指定します。次の`D:\GS Tools`は例なので、自分で選んだ保存先に置き換えてください。

```powershell
& "D:\GS Tools\compiler\bin\gs.cmd" hello.gs --backend native --cc "D:\GS Tools\toolchains\zig\zig.exe" -o .\build\hello-zig.exe
.\build\hello-zig.exe
```

PowerShellでは、空白を含むコマンドのパスを`& "..."`で呼び出します。

## Windows：Clangでコンパイルする

LLVMのClangに加え、Windows SDKとC/C++ランタイムのヘッダー・ライブラリが必要です。Visual Studio Build Toolsで「C++によるデスクトップ開発」を導入し、**Developer PowerShell for VS**等のSDKを認識するターミナルで実行します。

```powershell
gs --version
clang --version
gs hello.gs --backend native --cc clang -o .\build\hello-clang.exe
.\build\hello-clang.exe
```

ClangがPATHにない場合は、`--cc "C:\Program Files\LLVM\bin\clang.exe"`のように実行ファイルを指定します。`clang-cl.exe`やMSVCの`cl.exe`ではなく、GCC互換のオプションを受け付ける`clang.exe`を使ってください。

## Windows：GCCでコンパイルする

Windows向けMinGW-w64 / UCRT等のGCCを使用します。GCC本体に加え、対応するリンカー・ヘッダー・ライブラリが必要です。

```powershell
gs --version
gcc --version
gs hello.gs --backend native --cc gcc -o .\build\hello-gcc.exe
.\build\hello-gcc.exe
```

MSYS2 UCRT64へ導入している場合のパス指定例:

```powershell
gs hello.gs --backend native --cc "C:\msys64\ucrt64\bin\gcc.exe" -o .\build\hello-gcc.exe
.\build\hello-gcc.exe
```

このパスはMSYS2の既定配置の例です。実際の導入先が異なる場合は置き換えてください。実行時にDLL不足が出る場合は、そのGCC環境のbinをPATHで参照できるか、依存DLLを実行環境へ配置しているか確認します。

## Linux / macOS：コンパイルする

以下の3つから、導入したツールの例を1つ選んで実行します。`gs`が見つからない場合は、管理アプリで選択したコンパイラ保存先の`bin/gs`を絶対パスで呼び出してください。

Clang:

```sh
clang --version
gs hello.gs --backend native --cc clang -o build/hello-clang
./build/hello-clang
```

GCC:

```sh
gcc --version
gs hello.gs --backend native --cc gcc -o build/hello-gcc
./build/hello-gcc
```

Zig:

```sh
zig version
gs hello.gs --backend native --cc zig -o build/hello-zig
./build/hello-zig
```

macOSの`gcc`コマンドが実際にはApple Clangである場合があります。GCCを使いたい場合は`gcc --version`で確認し、Homebrew等で導入した`gcc-15`のような実際のコマンド名を`--cc`に指定します。バージョン付きの名前は導入した版に合わせてください。

```sh
gs hello.gs --backend native --cc /absolute/path/to/zig -o build/hello
./build/hello
```

macOSのClangはXcode Command Line Tools、LinuxのClang / GCCは対象OSのC開発用ヘッダー・リンカー・ライブラリを必要とします。

## 確認だけする・Cコードを見る

GSの構文・型検査だけなら、Cコンパイラは不要です。実行ファイルは作成しません。

```sh
gs hello.gs --backend native --check
```

生成するC11コードを見る場合:

```sh
gs hello.gs --backend native --emit c -o build/hello.c
```

`--format js|mjs|ts`はJS / TS経路の指定です。ネイティブ実行ファイルの作成には`--backend native`と`-o`を使います。

## 別のOS向けに生成する

ZigでWindows x64向けに生成する例です。

```sh
gs hello.gs --backend native --cc zig --target x86_64-windows-gnu -o build/hello.exe
```

Linux / macOSで作成した場合も、この`.exe`を通常実行する場所はWindowsです。対象のランタイム・外部ライブラリを持つツールチェーンが必要です。GCCではGSの`--target`指定を受け付けません。Clangのクロス生成も、対応するSDKやリンカー・ライブラリを別途用意する必要があります。

## 動かないときの確認

| 症状 | 確認すること |
| --- | --- |
| `gs`が見つからない | 新しいターミナルを開く。管理アプリの導入先にあるbin/gsまたはbin/gs.cmdを絶対パスで実行 |
| `zig`が見つからない | Zigの保存先をPATHへ追加するか、--ccにzig / zig.exeの絶対パスを指定 |
| Zigは入れたのにCコンパイラがないと言われる | --cc zigを明示する。Zigは自動選択されない |
| Clang / GCCのバージョンは出るがビルド失敗 | ヘッダー・リンカー・SDK・Cランタイムの有無を確認。管理アプリのツール検出でもビルド・実行確認を行える |
| Windowsでヘッダーやライブラリが見つからない | Windows SDKとC++ Build Toolsを確認し、Developer PowerShell等から実行 |
| PowerShellで生成ファイルが実行できない | `hello.exe`だけでなく`./build/hello.exe`または`.\build\hello.exe`のようにパスを指定 |
| 対応していないGS構文のエラー | [ネイティブの対応範囲](native-support.md)を確認。JS経路への自動切り替えは行わない |

型やメモリの意味は[ネイティブの型とメモリ](native-types.md)、Cライブラリ・Windows APIの呼び出しは[C ABIとWin32](native-ffi.md)で説明します。
