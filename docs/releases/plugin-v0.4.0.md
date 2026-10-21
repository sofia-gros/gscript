# Plugin v0.4.0

GSコンパイラv0.4.0と同じバージョンの、VSCode・Zed拡張と言語サーバーです。

- 両エディターでシンタックスハイライト、括弧対応、GS自身による構文・型・import診断。
- 未保存ファイルとGSモジュール間の変更を検査。
- 式の型ホバー、キーワード・トップレベルシンボル補完、アウトライン。
- VSCodeのインストール可能なVSIX、Zedの開発拡張ZIP（WASM同梱）、Linux・macOS・Windows用の言語サーバー、Python zipapp、拡張ソースを配布。

言語サーバーをPATHに配置してから拡張をインストールしてください。VSCodeはVSIX、ZedはZIPを展開して`zed: install dev extension`から導入します。Zed開発拡張の導入にはRustが必要です。Marketplace・Zed拡張レジストリーへの登録は含みません。

[インストール手順・設定・提供機能](https://github.com/sofia-gros/gscript/blob/main/docs/editors.md)

配布物はSHA256SUMSで検証できます。Gitタグは空白を使えないため`plugin-v0.4.0`、Releaseタイトルは`Plugin v0.4.0`です。
