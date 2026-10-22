# TypeScript・JavaScript連携

GS自身の型検査は常にGSコンパイラが行います。外部JS/TS、JSDoc、.d.ts、node_modulesの型情報読み取りにはNode.js 22/24とTypeScript Compiler APIを使います。

```sh
npm install --save-dev typescript@5.9.3
gs . --check
```

本家TSによる最終JS生成も選べます。

```sh
gs . --ts-compiler gs
gs . --ts-compiler ts
```

正式版5.9.x/6.0.xはJavaScript API、7.0.xはネイティブCLIで検証・emitします。nightly/RCは受け付けません。--format tsはTSソースの出力なので、最終JS生成の選択とは独立です。GSのみの既定ビルドではTSプロセスを起動しません。

TS7には従来のCompiler APIがありません。外部型も使う場合は別名でAPI版を追加します。

```sh
npm install --save-dev typescript@7.0.2 typescript-api@npm:typescript@5.9.3
```

--typescript /absolute/path/to/packageで使用パッケージを選べます。外部型のメタデータと出力は内容ハッシュ・依存ファイルでキャッシュを検証します。外部ファイルの型不一致もエラーです。npmライブラリーの実装をバンドルする機能はなく、実行環境側にも依存が必要です。

標準APIを厳密に検査するにはgsconfig.jsonでlibを指定します。例: ["es2022","dom"]、["es2022","webworker"]、["es2022","node"]。Node型にはnpm install --save-dev @types/nodeも必要です。lib未指定・TS未導入では従来の標準グローバル認識を維持します。DOMやNodeの実行環境を生成する機能ではありません。

外部型の範囲と型表現は[従来の相互運用仕様](interop.md)も参照してください。
