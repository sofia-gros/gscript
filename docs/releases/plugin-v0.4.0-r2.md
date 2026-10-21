# Plugin v0.4.0 — 修正版r2

GSコンパイラ・言語仕様v0.4.0を対象とした導入・起動処理の修正版です。初版Releaseは履歴として維持し、タグ`plugin-v0.4.0-r2`から新しい配布物を取得してください。

- VSCodeに言語サーバーを同梱。Python 3.12以降で起動でき、別途gs-lspを用意する必要がなくなりました。ネイティブ版の指定も可能です。
- サーバー・Pythonがない場合に導入方法を表示し、GS専用の出力ログを提供。
- Zedは対応OSのgs-lsp 0.4.0を自動取得。Extension APIを0.6へ変更し、公式互換表に沿って対応範囲を広げました。
- コンパイラの固定Releaseリンク、OS別導入、ZedのRust/Git・ビルド前提、更新・動作確認・エラー対処を記載。
- VSCodeのテストは配布VSIXから同梱サーバーを起動し、チェックアウトへのPython依存なしで診断・ホバー・補完を確認する方式へ変更。

[実際のインストール手順](https://github.com/sofia-gros/gscript/blob/main/docs/editors.md)

言語バージョンを維持しているため、初版のVSCode拡張は`code --install-extension ./gscript-v0.4.0.vsix --force`で入れ直してください。Zedでは古い開発拡張を削除し、修正版ZIPを展開して`Install Dev Extension`で選び直します。Zed開発拡張にはRustとGitが必要です。

配布物の整合性は同じReleaseのSHA256SUMSで確認できます。
