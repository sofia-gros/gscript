# VSCode・Zedへの導入

対象はGSコンパイラ・言語サーバーv0.5.0です。

[v0.5.0版のダウンロード](https://github.com/sofia-gros/gscript/releases/tag/plugin-v0.5.0)

## VSCode

### インストール

1. VSCode 1.85以降を使用します。
2. [Python公式サイト](https://www.python.org/downloads/)からPython 3.12以降をインストールします。VSCodeを終了し、起動し直してください。既にネイティブ版`gs-lsp 0.5.0`を使っている場合、Pythonは不要です。
3. v0.5.0版Releaseの`gscript-v0.5.0.vsix`をダウンロードします。
4. VSCodeの拡張機能ビューを開き、右上の「…」→「VSIXからのインストール…」で選択します。
5. 「Developer: Reload Window」で再読み込みし、プロジェクトのフォルダーを開きます。

`code`コマンドが利用できる環境では、ダウンロードしたディレクトリーで次も使えます。既存拡張から更新する場合も同じ手順です。

```sh
code --install-extension ./gscript-v0.5.0.vsix --force
```

VSIXには言語サーバーのPython zipappを同梱しています。起動順は、ユーザー指定の実行ファイル → PATH上の`gs-lsp 0.5.0` → Python 3.12以降による同梱サーバーです。ソースリポジトリーやコンパイラの別途インストールは不要です。

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
  "gscript.server.args": ["/absolute/path/to/gs-lsp-v0.5.0.pyz", "--stdio"]
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

1. v0.5.0版Releaseから`gscript-zed-v0.5.0.zip`を取得して展開します。
2. 展開した`gscript-zed`フォルダーを、削除しない場所へ移動します。開発拡張はこのフォルダーを参照し続けます。
3. Zedのコマンドパレットで`zed: extensions`を開き、**Install Dev Extension**を選びます。
4. `extension.toml`と`Cargo.toml`がある`gscript-zed`フォルダーを選択します。ZIP自体や、その1つ上のフォルダーは選びません。
5. ビルド完了後、GSプロジェクトのフォルダーを開き、`hello.gs`を開きます。言語表示が`GS`になり、キーワード等が色分けされます。

初版を導入済みの場合は、Extensionsから古い開発拡張を削除してからv0.5.0版のフォルダーを選び直してください。v0.5.0版はZed Extension API 0.6を使います。APIの対応範囲は[Zed公式互換表](https://github.com/zed-industries/zed/tree/main/crates/extension_api#compatible-zed-versions)を参照してください。

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

Windowsでは`"path": "C:\\Users\\Alice\\Tools\\gs-lsp.exe"`のように指定します。Intel Mac・Linux ARM等では、Python 3.12以降の実行ファイルを`path`に、`["/absolute/path/to/gs-lsp-v0.5.0.pyz", "--stdio"]`を`arguments`に指定してください。

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

GSの診断、ホバー、アウトライン、ローカル・プロパティ補完、定義ジャンプ、参照検索、リネーム、Signature Help、GSモジュールの自動import候補、Lint警告、ドキュメント整形を提供します。コンパイラのAST・シンボル・スコープを再利用し、未保存ファイルも検査します。リネームは編集後の型検査が成功した場合に編集案を返します。外部ライブラリーの定義は参照できますが書き換えません。ワークスペース内に型エラーがある場合は参照検索・リネーム前に修正してください。

gsconfig.jsonのstrictNull/libを共用します。VSCodeのgscript.strictNullは既定nullで設定へ追従し、true/falseで上書きできます。初回の外部型読み取りには時間がかかります。外部型キャッシュを.gs-cacheへ保存する場合があります。

CIは実際のVSIXをExtension Hostへインストールし、同梱サーバーとの接続を検査します。Zed用Rust/WASI2コンポーネント、Tree-sitterの生成・解析・クエリー・WASM、3OSのLSP実行も検査します。Zedの開発拡張導入は上記公式手順でローカル再ビルドされます。同梱WASMをZIPから直接インストールする機能ではありません。GUIによるZed導入の自動試験とは区別します。
