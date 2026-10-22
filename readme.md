<div align="center">

# GS / gscript

**Go風の構文。GS自身の型検査。JavaScriptの実行環境。**

[![Tests](https://github.com/sofia-gros/gscript/actions/workflows/test.yml/badge.svg)](https://github.com/sofia-gros/gscript/actions/workflows/test.yml)

[コンパイラ v0.5.0](https://github.com/sofia-gros/gscript/releases/tag/v0.5.0) · [エディター拡張](https://github.com/sofia-gros/gscript/releases/tag/plugin-v0.5.0) · [インストール](docs/installation.md) · [ドキュメント](docs/language-v0.5.md)

</div>

GSはGo風の構文を使い、JavaScript ES2022 ModulesまたはTypeScriptへコンパイルする言語です。`func`、`:=`、struct、レシーバーを使いつつ、JSのオブジェクト・配列・npm・async/awaitを扱います。構文・型・スコープ・モジュールはGSコンパイラが検査します。

```go
func greet(name string) string {
  return "Hello, " + name
}
println(greet("GS"))
```

## はじめる

[Release](https://github.com/sofia-gros/gscript/releases/tag/v0.5.0)からOS・CPUに合うネイティブ版を展開し、`gs`をPATHへ追加します。Python版・wheelもあります。[OS別インストール手順](docs/installation.md)を参照してください。

上のコードを`main.gs`へ保存します。

```sh
gs main.gs
node dist/main.js
# Hello, GS
```

GSのみのコンパイルにNode.js・TypeScriptは不要です。生成JSの検証対象はNode.js 22/24です。外部JS/TSの型読み取りにはNode.jsとTypeScript Compiler APIが必要です。

```sh
gs init demo --template node
cd demo
gs .
node dist/main.js
```

## ビルドとツール

| コマンド | 動作 |
| --- | --- |
| `gs .` | main.gs/main.gosから依存もビルド、既定はminify JS |
| `gs main.gs` | dist/main.jsへ可読JS |
| `gs . --no-minify` | コメント・名前を維持した可読出力 |
| `gs . --format mjs` | Nodeで直接実行できるES Modules |
| `gs . --format ts` | 型注釈付きTypeScript |
| `gs . --ts-compiler ts` | GS検査後に公式TypeScriptでJS生成 |
| `gs . --sourcemap --declaration` | Source Mapと公開APIの型宣言も生成 |
| `gs . --check` | 型検査のみ |
| `gs lint` / `gs fmt` | 追加診断 / ソース整形 |
| `gs watch` | 差分ビルド、失敗時は既存出力を維持 |

設定ファイルは不要です。`gsconfig.json`でentry/outDir/format/minify/strictNull/lib等を指定できます。JS/TS出力には必要なESM設定を作成します。npm依存のバンドルは行いません。[CLI仕様](docs/cli.md)

## 言語と型

intとfloatをコンパイル時に区別し、数値型専用のランタイム処理を生成しません。float64はfloatの別名、numberはJSとの共通数値型です。

```go
a := 10
b := 2.5
// a + b は型エラー
println(float(a) + b)
```

struct継承、constructor/super、interface、implements、制約付きgenerics、union・リテラル型、nullable、optional chaining、nullish coalescing、enum、switch、static、アクセス制御、readonly、GSモジュール間の型共有に対応します。`--strict-null`で厳密なnil検査を選べます。

[数値型](docs/numeric-types.md) · [組み込み関数](docs/builtins.md) · [配列](docs/arrays.md) · [v0.4からの移行](docs/migration-v0.4-to-v0.5.md)

## JavaScript・TypeScriptとの連携

```sh
npm install --save-dev typescript@5.9.3
gs . --check
```

外部JS/TS、JSDoc、.d.ts、node_modulesの型情報を読み、呼び出しの適否をGSが検査します。最終JS生成は既定のGSまたは公式TS 5.9/6.0/7.0から選べます。TS7のネイティブCLIと外部型用APIの併用方法、DOM・Node・Workerの設定は[相互運用ガイド](docs/typescript-interop.md)を参照してください。

## エディター

[Plugin v0.5.0](https://github.com/sofia-gros/gscript/releases/tag/plugin-v0.5.0)から導入します。コンパイラとプラグインは別Releaseです。

- **VSCode:** VSIXにLSPを同梱。Python 3.12以降、またはネイティブgs-lspで起動します。
- **Zed:** ZIPを展開し、Rust・Gitを準備してInstall Dev Extensionを使います。Tree-sitterのハイライトとLSPを提供します。

診断、ホバー、定義ジャンプ、参照検索、リネーム、ローカル・プロパティ補完、Signature Help、自動import候補、Lint、整形に対応します。[正確な導入・更新・エラー対処](docs/editors.md)

## ドキュメント・開発

[出力](docs/compiler-output.md) · [Source Map](docs/source-maps.md) · [型宣言](docs/declarations.md) · [Lint](docs/lint.md) · [Formatter](docs/formatter.md) · [性能](docs/performance.md)

Python 3.12以降を使います。

```sh
git clone https://github.com/sofia-gros/gscript.git
cd gscript
python -m gscript examples/hello.gs
node examples/dist/hello.js
npm ci --ignore-scripts
python -m unittest discover -s tests -v
```

公開ワークフローは3OSのネイティブ配布、生成物の実行、公式TS各版、Phaser、VSIX実接続、Zed用WASM・文法を検証してからReleaseを公開します。
