# CLI

> このページはJS / TS経路のガイドです。言語全体は[実行モデル](execution-models.md)、ソース版のネイティブ機能は[Native](native.md)を参照してください。

```sh
gs .                         # main.gs/main.gosをdistへ、既定はminify JS
gs main.gs                   # dist/main.jsへ可読JS、依存も出力
gs . --no-minify
gs . --format mjs
gs . --format ts
gs . --ts-compiler ts
gs . --sourcemap --declaration
gs . --check
gs main.gs -o output.js
gs src/main.gs --root . --out-dir dist
```

出力形式の既定はjsです。-oの拡張子も形式を決めます。複数モジュールには--out-dirを使います。--checkは出力しません。エラー時は終了値1、引数エラーは2です。型検査と全出力の計画が成功してからファイルを書きます。

```sh
gs init demo --template node   # browser / phaserも選択可能
gs fmt . --check
gs fmt main.gs
gs lint . --json
gs lint --fix
gs watch                      # Ctrl+Cで停止
```

設定ファイルは必須ではありません。入力から最も近い親のgsconfig.jsonを読みます。明示したCLIオプションが設定を優先します。

```json
{
  "entry": "main.gs",
  "outDir": "dist",
  "format": "js",
  "minify": true,
  "tsCompiler": "gs",
  "sourcemap": true,
  "declaration": true,
  "strictNull": true,
  "lib": ["es2022", "dom"]
}
```

--no-cacheは外部型キャッシュの永続保存を止めます。--cache-dirで場所を指定できます。--typescriptはTypeScriptパッケージのディレクトリーを指定します。--rootはGS/外部ローカルモジュールを含む共通ルートです。

watchはソース・依存・設定の内容変更を監視し、変更のない構文木と生成コードを再利用します。失敗時には既存出力を維持し、修正後に再ビルドします。initは既存ファイルを上書きしません。browserテンプレートのビルド後はHTTPサーバーでindex.htmlを開きます。phaserテンプレートはnpm install後にnpm run devを使い、GS編集の継続ビルドには別ターミナルでgs watchを実行します。
