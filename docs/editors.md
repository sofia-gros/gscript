# VSCode・Zedへの導入

対象はGSコンパイラv0.4.0用プラグインの**修正版r2**です。拡張・言語サーバーの言語バージョンは0.4.0のまま、配布を`plugin-v0.4.0-r2`で区別します。

[修正版のダウンロード](https://github.com/sofia-gros/gscript/releases/tag/plugin-v0.4.0-r2)

## VSCode

### インストール

1. VSCode 1.85以降を使用します。
2. [Python公式サイト](https://www.python.org/downloads/)からPython 3.12以降をインストールします。VSCodeを終了し、起動し直してください。既にネイティブ版`gs-lsp 0.4.0`を使っている場合、Pythonは不要です。
3. 修正版Releaseの`gscript-v0.4.0.vsix`をダウンロードします。
4. VSCodeの拡張機能ビューを開き、右上の「…」→「VSIXからのインストール…」で選択します。
5. 「Developer: Reload Window」で再読み込みし、プロジェクトのフォルダーを開きます。

`code`コマンドが利用できる環境では、ダウンロードしたディレクトリーで次も使えます。初版からの更新は同じバージョンのため`--force`を指定します。

```sh
code --install-extension ./gscript-v0.4.0.vsix --force
```

VSIXには言語サーバーのPython zipappを同梱しています。起動順は、ユーザー指定の実行ファイル → PATH上の`gs-lsp 0.4.0` → Python 3.12以降による同梱サーバーです。ソースリポジトリーやコンパイラの別途インストールは不要です。

### 動作確認

フォルダー内に`hello.gs`を保存し、次を入力します。

```go
var count int = "wrong"
console.log(count)
```

「問題」ビューにGSの型不一致が表示されます。`"wrong"`を`3`に変えると、保存前でも診断が消えます。2行目の`count`にマウスを重ねると型が表示されます。

### 実行ファイルを明示する場合

「Preferences: Open User Settings (JSON)」から設定します。パスは実際の絶対パスへ置き換えます。`~`や`$HOME`は展開しません。

Linux / macOSのネイティブ版:

```json
{
  "gscript.server.path": "/home/alice/.local/bin/gs-lsp",
  "gscript.server.args": ["--stdio"]
}
```

Windowsのネイティブ版:

```json
{
  "gscript.server.path": "C:\\Users\\Alice\\Tools\\gs-lsp.exe",
  "gscript.server.args": ["--stdio"]
}
```

独自のPython実行ファイルとダウンロードしたzipappを使う場合:

```json
{
  "gscript.server.path": "/absolute/path/to/python3",
  "gscript.server.args": ["/absolute/path/to/gs-lsp-v0.4.0.pyz", "--stdio"]
}
```

設定後はウィンドウを再読み込みします。自動検出へ戻す場合は`gscript.server.path`を空文字列にしてください。

## Zed

### 前提条件

最新版のZed、Git、**rustup経由でインストールしたRust**を使います。Zed公式の[開発拡張の手順](https://zed.dev/docs/extensions/developing-extensions)に従う方式です。GitHub配布のZIPを、Zedの拡張検索へ直接入力する方式ではありません。

Rust未導入の場合は[rustup公式サイト](https://rustup.rs/)から導入し、ターミナルとZedを再起動してください。

```sh
rustup update stable
rustup target add wasm32-wasip2
cargo --version
git --version
```

開発拡張はローカルで再ビルドされます。Rust依存、GS文法のGit取得、必要な文法ビルド用ツールの取得にネットワーク接続が必要です。ビルド済みWASMを同梱していても、これらの前提を省略できるインストーラーではありません。Zedの最新版は文法ビルド用wasi-sdkを自動取得します。詳細は上記公式手順を参照してください。

### インストール

1. 修正版Releaseから`gscript-zed-v0.4.0.zip`を取得して展開します。
2. 展開した`gscript-zed`フォルダーを、削除しない場所へ移動します。開発拡張はこのフォルダーを参照し続けます。
3. Zedのコマンドパレットで`zed: extensions`を開き、**Install Dev Extension**を選びます。
4. `extension.toml`と`Cargo.toml`がある`gscript-zed`フォルダーを選択します。ZIP自体や、その1つ上のフォルダーは選びません。
5. ビルド完了後、GSプロジェクトのフォルダーを開き、`hello.gs`を開きます。言語表示が`GS`になり、キーワード等が色分けされます。

初版を導入済みの場合は、Extensionsから古い開発拡張を削除してから修正版のフォルダーを選び直してください。修正版はZed Extension API 0.6を使います。APIの対応範囲は[Zed公式互換表](https://github.com/zed-industries/zed/tree/main/crates/extension_api#compatible-zed-versions)を参照してください。

### 言語サーバー

指定済みの`lsp.gs-lsp.binary.path`、PATHの`gs-lsp`、自動ダウンロードの順で選びます。自動取得の対象はLinux x86_64、macOS Apple Silicon、Windows x86_64です。初回はGitHub Releasesへの接続が必要です。

オフライン環境では、事前に対応するネイティブ版を取得・展開し、Zedの設定へ実際の絶対パスを指定します。

```json
{
  "lsp": {
    "gs-lsp": {
      "binary": {
        "path": "/home/alice/.local/bin/gs-lsp",
        "arguments": ["--stdio"]
      },
      "initialization_options": {"strictNull": false}
    }
  }
}
```

Windowsでは`"path": "C:\\Users\\Alice\\Tools\\gs-lsp.exe"`のように指定します。Intel Mac・Linux ARM等では、Python 3.12以降の実行ファイルを`path`に、`["/absolute/path/to/gs-lsp-v0.4.0.pyz", "--stdio"]`を`arguments`に指定してください。

## エラーの確認方法

| 症状 | 確認・対処 |
| --- | --- |
| VSCodeでPythonまたはgs-lspが見つからない | Python 3.12以降を導入してVSCodeを再起動するか、実行ファイルの絶対パスを指定。WindowsではPythonのインストール先・実行エイリアスも確認 |
| VSCodeでサーバーが起動しない | 「表示」→「出力」→`GS Language Server`を選び、起動コマンドとエラーを確認 |
| Zedの拡張インストールに失敗 | `cargo --version`、Git、Rustターゲット、ネットワークを確認。`zed: open log`でビルド失敗箇所を確認 |
| Zedでサーバーダウンロードに失敗 | プロキシ・GitHub接続を確認。手動で展開したサーバーを`binary.path`へ指定 |
| `Permission denied` | Linux/macOSでサーバーに実行権限があるか確認。信頼できるReleaseから取得したファイルに対して`chmod +x /absolute/path/to/gs-lsp`を実行 |
| `.gs`が通常のテキストになる | 拡張の有効化、言語モードを確認。対象は`.gs`と`.gos` |
| importがプロジェクト外と判定される | import先を含む共通の親フォルダーをエディターで開く |
| 外部JS/TSだけ検査に失敗 | Node.js 22/24とプロジェクト内のTypeScript 5.9.3を確認。プロジェクトで`npm install --save-dev typescript@5.9.3`を実行 |

## 機能と検証範囲

GSコンパイラ自身による構文・型・import診断、未保存GSモジュールの検査、型を確定した式のホバー、キーワード・トップレベルシンボルの補完、アウトラインを提供します。VSCodeはTextMate、ZedはGS専用の字句ベースTree-sitter文法で色分けします。

各入口についてコンパイラが最初に報告するエラーを表示します。型検査に失敗した文書では型ホバーを返しません。ローカル変数・メンバーの補完、定義ジャンプ、リネーム、整形は未提供です。検査は逐次実行で、外部型の初回読み込みには時間がかかります。ソースやJS出力は書き換えませんが、外部型のキャッシュを`.gs-cache`に作成する場合があります。

CIでは配布VSIXの実際のVSCode Extension Host接続、同梱サーバー、Rust/WASMビルド、Tree-sitter文法・クエリー、3OSのサーバー実行を確認します。Zed GUI上の開発拡張インストールを自動試験したという意味ではありません。
