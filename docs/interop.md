# JavaScript / TypeScript 連携（GS 0.4）

GS の構文を増やさず、既存の import と型注釈を外部モジュールにも利用できます。
CLI と `gscript.project.Project` / `build_project` は、外部 import がある場合に 外部の型定義を読み込み、GS自身の型検査器でGSコードを検査します。TypeScript APIは外部のJS/TS・型定義の読み取りと変換に利用し、GSの型検査を委譲しません。ファイルを持たない `compile_source` は GS 単体の変換 API です。外部モジュールの解決にはプロジェクト API を使ってください。

```sh
npm install --save-dev typescript@5.9.3
npm install phaser@3.90.0
gs game.gs --check
gs game.gs --format mjs --out-dir dist
```

```go
import Phaser from "phaser"
var config Phaser.Types.Core.GameConfig = {
  type: Phaser.AUTO,
  width: 800,
  height: 600,
}
game := new Phaser.Game(config)
```

`width: "800"`、存在しないプロパティ、引数や戻り値の型の不一致はコンパイルエラーです。パッケージの `.d.ts`、TypeScript ソース、JavaScript の JSDoc と推論型を利用します。型情報のない JavaScript の値や明示的な `any` は JavaScript の動的な意味を持ちます。型宣言が実装と一致していることや外部コードの実行結果までは静的に保証しません。

## 解決と出力

- 既存の `node_modules` と最寄りの `tsconfig.json` の解決設定（`paths` など）を利用します。GS の入口から参照するファイルだけを検査し、tsconfig の include は入口に追加しません。
- NodeNext が既定です。パス別名にはその解決方式で有効な指定が必要です。たとえば `"paths": {"@local/*": ["lib/*.ts"]}`。
- `./library.ts` / `./library.js` とそのローカル依存は `--out-dir` に変換・配置します。プロジェクト外の共有ソースには `--root` を指定してください。
- `js` / `mjs` は型を消去し、型だけの import を除去します。`ts` は型を保持します。JavaScript の型宣言も必要に応じて出力します。CommonJS のローカル実装は `.cjs` として保持します。
- npm の bare import は保持します。出力先から実行時の `node_modules` を参照できる配置にしてください。依存のインストールやバンドルは自動実行しません。
- ブラウザーではバンドラー、または import map で依存を解決します。Phaser のブラウザー用 ESM を直接使う場合、その named exports を namespace として default export するアダプターが必要です。検証用の構成は `scripts/test_phaser_browser.py` にあります。
- 外部ソースを実行して型を調べることはありません。診断は元の GS または外部ソースのファイル位置に対応します。型チェックが失敗した場合は生成物を書き換えません。

## 必要なツールとキャッシュ

外部 import の検査には Node.js 22 / 24 と TypeScript 5.9.3 が必要です。TypeScript は入力プロジェクトの `node_modules` を親方向に探索します。`--typescript PATH` でパッケージディレクトリまたは `lib/typescript.js` を明示できます。GS だけのプロジェクトは Node / TypeScript を起動しません。

外部型のメタデータは `.gs-cache/v0.4-native`、変換結果は `.gs-cache/v0.4` に保存します。GS自身の型検査は毎回実行します。GS、外部ソース、型定義、設定、パッケージ解決結果、TypeScript とブリッジの内容を検証して再利用します。探索時に存在しなかった型定義が追加された場合も無効化します。時刻だけの比較はしません。キャッシュ破損や書き込み不可では再検査します。

```sh
gs game.gs --check --no-cache
gs game.gs --check --cache-dir .cache/gs
```

速度は `python scripts/benchmark.py --modules 100 --runs 7` で測定できます。測定結果は環境や依存により変わります。外部型メタデータのキャッシュ利用時は型定義読み込み用のNodeプロセスを省略し、GSの検査は省略しません。
