# GS / gscript

Go風の構文からJavaScriptを生成するGSのVSCode拡張です。

- `.gs` / `.gos`のシンタックスハイライトと括弧対応
- GSコンパイラ自身による構文・型・import診断（未保存ファイルも対象）
- 式の型ホバー、キーワード・トップレベルシンボル補完、アウトライン

[Plugin v0.4.0](https://github.com/sofia-gros/gscript/releases/tag/plugin-v0.4.0)からOSに合う`gs-lsp`を展開し、PATHに配置してください。あるいは`gscript.server.path`で実行ファイルを指定します。コンパイラ・言語サーバー・拡張のバージョンはv0.4.0に合わせます。

外部JS/TSの型読み込みにはNode.js 22/24とプロジェクト内のTypeScript 5.9.3を利用します。GSの型検査はGS自身が行います。

[インストール・機能・設定](https://github.com/sofia-gros/gscript/blob/main/docs/editors.md)
