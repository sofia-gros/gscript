# コンパイラv0.6.0のインストール

> このページはJS / TS経路のガイドです。言語全体は[実行モデル](execution-models.md)、ソース版のネイティブ機能は[Native](native.md)を参照してください。

コンパイラは[GS v0.6.0](https://github.com/sofia-gros/gscript/releases/tag/v0.6.0)から取得します。`releases/latest`はエディター拡張を指す場合があるため、コンパイラの導入には使いません。エディター拡張の導入は[別の手順](editors.md)です。

## 配布物を選ぶ

| 環境 | ファイル |
| --- | --- |
| Linux x86_64 | `gs-v0.6.0-linux-x86_64.tar.gz` |
| macOS Apple Silicon | `gs-v0.6.0-macos-arm64.tar.gz` |
| Windows x86_64 | `gs-v0.6.0-windows-x86_64.zip` |
| Python 3.12以降がある環境 | `gs-v0.6.0.pyz` |
| Python仮想環境へインストール | `gscript_lang-0.6.0-py3-none-any.whl` |

ネイティブ版はPython不要です。ビルド・実行検証環境はUbuntu 22.04 x86_64、macOS 14 arm64、Windows Server 2022 x86_64です。他のOS・CPUへのネイティブ対応を確認したという意味ではありません。Intel Mac・Linux ARM等ではPython版を選べます。

## Linux x86_64

ダウンロード用の空の作業ディレクトリーで実行します。

```sh
curl -fL -O https://github.com/sofia-gros/gscript/releases/download/v0.6.0/gs-v0.6.0-linux-x86_64.tar.gz
tar -xzf gs-v0.6.0-linux-x86_64.tar.gz
mkdir -p "$HOME/.local/bin"
install -m 755 gs-v0.6.0-linux-x86_64/gs "$HOME/.local/bin/gs"
export PATH="$HOME/.local/bin:$PATH"
gs --version
```

`gscript 0.6.0`が表示されます。`export PATH=...`は現在のシェルにだけ有効です。以後も使う場合は、使用するシェルの設定（bashの`~/.bashrc`等）へ同じ行を追加します。

## macOS Apple Silicon

```sh
curl -fL -O https://github.com/sofia-gros/gscript/releases/download/v0.6.0/gs-v0.6.0-macos-arm64.tar.gz
tar -xzf gs-v0.6.0-macos-arm64.tar.gz
mkdir -p "$HOME/.local/bin"
install -m 755 gs-v0.6.0-macos-arm64/gs "$HOME/.local/bin/gs"
export PATH="$HOME/.local/bin:$PATH"
gs --version
```

継続してPATHに追加する場合、zshでは`~/.zshrc`に`export PATH="$HOME/.local/bin:$PATH"`を追加します。OSが実行をブロックする場合は、取得元とSHA-256を確認したうえでmacOSの「プライバシーとセキュリティ」の表示に従ってください。

## Windows x86_64（PowerShell）

```powershell
Invoke-WebRequest -Uri "https://github.com/sofia-gros/gscript/releases/download/v0.6.0/gs-v0.6.0-windows-x86_64.zip" -OutFile "gs-v0.6.0-windows-x86_64.zip"
Expand-Archive -Path ".\gs-v0.6.0-windows-x86_64.zip" -DestinationPath ".\gs-compiler"
& ".\gs-compiler\gs-v0.6.0-windows-x86_64\gs.exe" --version
```

そのまま絶対パス・相対パスで実行できます。`gs`だけで起動したい場合は、`gs.exe`を削除しない場所へ移し、その**フォルダー**をWindowsのユーザー環境変数`Path`へ追加してターミナルを開き直します。PowerShellでは現在のフォルダーの実行ファイルにも`./`または`.\`が必要です。

## Python版

[Python 3.12以降](https://www.python.org/downloads/)を導入し、Releaseから`gs-v0.6.0.pyz`をダウンロードします。ダウンロードしたフォルダーで実行します。

```sh
python --version
python gs-v0.6.0.pyz --version
python gs-v0.6.0.pyz hello.gs --format mjs -o dist/hello.mjs
```

Linux/macOSでコマンド名が`python3`なら、上記の`python`を`python3`へ置き換えます。zipapp自体を直接起動する必要はありません。

wheelを使う場合は、ダウンロードしたファイルをPython仮想環境へインストールします。PyPIへ公開済みとは案内していません。

Linux / macOS:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install ./gscript_lang-0.6.0-py3-none-any.whl
.venv/bin/gs --version
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install .\gscript_lang-0.6.0-py3-none-any.whl
.\.venv\Scripts\gs.exe --version
```

## 最初のコンパイル

次を`hello.gs`として保存します。

```go
func greet(name string) string {
  return "Hello, " + name
}
console.log(greet("GS"))
```

```sh
gs hello.gs --format mjs -o dist/hello.mjs
node dist/hello.mjs
```

`Hello, GS`が表示されます。Python版なら`gs`を`python /path/to/gs-v0.6.0.pyz`へ置き換えます。JSの実行にはNode.js 22/24等の対応実行環境が必要です。

外部JS/TSの型情報を使うプロジェクトでは、そのプロジェクトのディレクトリーで次を実行します。

```sh
npm install --save-dev typescript@5.9.3
```

GSだけのコンパイルでは不要です。外部型の読み取り時はNode.jsがPATHから実行できる必要があります。

## 配布物の整合性

同じReleaseの`SHA256SUMS`を取得し、対象ファイルのハッシュと比較します。

- Linux: `sha256sum ファイル名`
- macOS: `shasum -a 256 ファイル名`
- PowerShell: `Get-FileHash .\ファイル名 -Algorithm SHA256`

SHA256SUMSには複数の配布物が載っています。ダウンロードしていないファイルを含む一覧全体を一括検証すると、未取得ファイルについてエラーが出ます。自分が取得したファイル名の行と比較してください。
