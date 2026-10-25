# Plugin v0.6.0

GS v0.6.0とバージョンを合わせたVSCode・Zed・LSPです。

Zed / Windowsが送る`file:///a%3A/Project/...`形式を、ドライブを保持する絶対パスへ正規化します。documentSymbolの内部パスエラーを誤って-32601とする分類も修正しました。

ZedはPATHのgs-lspのバージョンを検証し、古ければv0.6.0を取得します。取得したサーバーを絶対パスで起動し、実行権限を確認します。明示したbinary.pathは利用者の設定を尊重するため、古い実行ファイルを指定している場合は更新してください。

ネイティブ専用構文のハイライト、GS自身による診断、基本的なホバー・補完・関数/変数の定義/参照/リネーム・整形を追加しました。gsconfig.jsonのbackend/nativeTargetを共用します。編集時にCツールチェーンは起動しません。

[導入・設定・対処](https://github.com/sofia-gros/gscript/blob/plugin-v0.6.0/docs/editors.md)

VSCodeは同梱Pythonサーバー（Python 3.12+）またはネイティブLSPを使用します。Zedは公式のInstall Dev Extension方式で、Rust・Gitによるローカル再ビルドが必要です。WASI2・文法WASMを同梱します。GUI上のZedインストール自動試験とは区別し、WASMビルドと配布LSPの実行・Windows URI回帰を検証します。
