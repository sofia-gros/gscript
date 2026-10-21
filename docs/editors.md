# GS editor plugins · v0.4.0

VSCodeとZedは同じGS言語サーバーを使います。診断はGSコンパイラ自身が行い、未保存のGSファイルと、そのファイルがimportするGSモジュールも検査します。ファイルは書き換えず、コンパイル出力も生成しません。

## ダウンロード

[Plugin v0.4.0](https://github.com/sofia-gros/gscript/releases/tag/plugin-v0.4.0)から、エディターの拡張とOSに合う言語サーバーを取得します。コンパイラv0.4.0のReleaseはそのまま維持します。

| 配布物 | 用途 |
| --- | --- |
| `gscript-v0.4.0.vsix` | VSCode用拡張 |
| `gscript-zed-v0.4.0.zip` | Zed用拡張。Rustソース・拡張WASM・文法WASMを同梱 |
| `gs-lsp-v0.4.0-linux-x86_64.tar.gz` | Linux用言語サーバー |
| `gs-lsp-v0.4.0-macos-arm64.tar.gz` | Apple Silicon用言語サーバー |
| `gs-lsp-v0.4.0-windows-x86_64.zip` | Windows用言語サーバー |
| `gs-lsp-v0.4.0.pyz` | Python 3.12以降で動く言語サーバー |
| `gs-plugin-sources-v0.4.0.zip` | エディター拡張と文法のソース |

展開した`gs-lsp`（Windowsでは`gs-lsp.exe`）をPATHに配置するか、エディター設定で絶対パスを指定してください。`gs-lsp --version`は`gs-lsp 0.4.0`を表示します。ネイティブ版にPythonのインストールは不要です。

外部JS/TS・node_modulesの型情報を読む場合は、コンパイラと同様、Node.js 22/24とプロジェクト内のTypeScript 5.9.3が必要です。GSだけの検査には不要です。外部型の読み取りにTypeScriptを利用し、GSコードの型判定はGSが行います。

## VSCode

```sh
code --install-extension gscript-v0.4.0.vsix
```

`.gs`と`.gos`を開くと起動します。パスを指定する場合:

```json
{
  "gscript.server.path": "/absolute/path/to/gs-lsp",
  "gscript.strictNull": false
}
```

Python版の場合は`gscript.server.path`にPython実行ファイル、`gscript.server.args`に`["/absolute/path/to/gs-lsp-v0.4.0.pyz", "--stdio"]`を指定します。サーバー設定変更後はウィンドウを再読み込みしてください。

## Zed

ZIPを展開し、コマンドパレットの`zed: install dev extension`で`extension.toml`がある`gscript-zed`ディレクトリーを選びます。これはGitHubから配布する拡張で、Zed拡張レジストリーへの登録は含みません。Zedの開発拡張インストールにはRust toolchainと、文法取得・ビルド用のネットワーク接続が必要です。ビルド済みWASMも配布に同梱しています。

GS専用Tree-sitter文法で、キーワード・文字列・コメント・数値・演算子・括弧をハイライトします。文法は編集中の不完全なコードを受け入れる字句ベースの文法です。構文・型の正しさは言語サーバーが検査します。

PATHから見つからない場合はZedの設定に追加します。

```json
{
  "lsp": {
    "gs-lsp": {
      "binary": {"path": "/absolute/path/to/gs-lsp", "arguments": ["--stdio"]},
      "initialization_options": {"strictNull": false}
    }
  }
}
```

## 言語サーバーの機能

- 構文・型・importエラーの診断。未保存ファイルの変更時に再検査し、修正・閉鎖時に診断を更新。
- GSコンパイラが型を確定できた式の型ホバー。
- キーワードと型検査済みのトップレベルシンボルの補完。
- トップレベル宣言のアウトライン。
- LSP 3.17、stdio、UTF-16位置、全文同期、複数のworkspace folderに対応。

コンパイラは最初のエラーで停止するため、各エントリーファイルにつき最初のエラーを表示します。エラーを含む文書では型情報が確定しないため、ホバーとシンボル補完を返しません。ローカル変数・メンバーの補完、定義ジャンプ、リネーム、整形は今回の提供機能に含みません。エディターのフォルダーはGS import先も含む共通の親を開いてください。

診断チェックは逐次実行です。大きなプロジェクトや初回の外部型読み込みでは結果を待つ場合があります。外部型の内容キャッシュはコンパイラと共有します。

## 開発・検証

```sh
python -m unittest discover -s tests -v
npm ci --prefix editors/vscode
npm run package --prefix editors/vscode
# Linux + Xvfbで本物のVSCode extension hostを検証
xvfb-run -a node editors/vscode/test/run.cjs
cargo build --release --target wasm32-wasip1 --manifest-path editors/zed/Cargo.toml
```

GitHub ActionsはVSCode実接続、Tree-sitterクエリー、Rust/WASMビルド、3OSの配布サーバーのstdio通信を検証した後にReleaseを作成します。
