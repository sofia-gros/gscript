<div align="center">

# GS / gscript

**Go風の構文を、JavaScriptの実行環境へ。**

[![Tests](https://github.com/sofia-gros/gscript/actions/workflows/test.yml/badge.svg)](https://github.com/sofia-gros/gscript/actions/workflows/test.yml)

[コンパイラ v0.4.0](https://github.com/sofia-gros/gscript/releases/tag/v0.4.0) · [エディター拡張](https://github.com/sofia-gros/gscript/releases/tag/plugin-v0.4.0-r2) · [インストール](docs/installation.md) · [言語仕様](docs/language.md)

</div>

GSは構文・型・スコープ・モジュールを検査し、JavaScript ES ModulesまたはTypeScriptを生成する言語です。`func`、`:=`、struct、レシーバー構文を使いつつ、JavaScriptのオブジェクト・配列・npm・`async / await`を扱います。実行時の数値・参照・非同期処理はJavaScriptに従います。

```go
func greet(name string) string {
    return "Hello, " + name
}

console.log(greet("GS"))
```

## はじめる

[コンパイラRelease](https://github.com/sofia-gros/gscript/releases/tag/v0.4.0)からOS・CPUに合うネイティブ版を展開し、`gs`（Windowsは`gs.exe`）を実行します。Python版・wheelもあります。OS別のコマンドとPATH設定は[インストール手順](docs/installation.md)を参照してください。

上のコードを`hello.gs`に保存します。

```sh
gs hello.gs --format mjs -o dist/hello.mjs
node dist/hello.mjs
# Hello, GS
```

GSのみのコンパイルにNode.jsやTypeScriptは不要です。生成JSの検証対象はNode.js 22/24です。外部JS/TSの型を読む場合はNode.js 22/24とプロジェクト内のTypeScript 5.9.3が必要です。

## 出力形式

| 指定 | 出力 | 実行 |
| --- | --- | --- |
| `--format mjs` | ES2022 Modules `.mjs` | Node.jsで直接実行 |
| `--format js` | ES2022 Modules `.js` | 出力先の`package.json`に`type: module`が必要 |
| `--format ts` | 型注釈付き`.ts` | TypeScriptでJSへ変換して実行 |

```sh
gs hello.gs --check
gs hello.gs --format js -o dist/hello.js
gs hello.gs --format ts -o dist/hello.ts
# GSモジュール・外部ローカルファイルをまとめて出力
gs src/main.gs --out-dir dist --format mjs
```

既定は`mjs`です。`-o`の拡張子からも推論します。複数モジュールは`--out-dir`を使います。JS/TSファイル出力時は必要なmodule設定を作成し、既存のCommonJS設定と矛盾する場合はエラーを返します。

## 言語・型検査

- struct継承、constructor / super、レシーバーメソッド、override
- 構造的interface、implements、制約付きGenerics
- Nullable、Union・リテラル型、Optional Chaining、Nullish Coalescing
- switch・網羅性検査、static、アクセス制御、readonly、型エイリアス、enum
- GSモジュール間の型共有、外部`.d.ts`・JSDoc・node_modulesの型情報

**GSコードの型検査はGSコンパイラ自身が行います。** TypeScript APIは外部JS/TSの型情報読み取りと変換に利用します。既定モードでは従来の参照型のnil規則を維持し、`--strict-null`で厳密なnil検査を選べます。

[基本仕様](docs/language.md) · [v0.4拡張仕様](docs/language-v0.4-extensions.md) · [外部JS/TS連携](docs/interop.md) · [Go / GS / JS比較](docs/comparison.md)

## VSCode・Zed

両方のエディターでシンタックスハイライト、GSの診断、型ホバー、補完、アウトラインを使えます。

- **VSCode:** 修正版VSIXをインストール。Python 3.12以降があれば同梱言語サーバーが起動します。ネイティブサーバーの指定も可能です。
- **Zed:** Rust・Gitを準備し、ZIPを展開して`Install Dev Extension`から導入します。対応OSの言語サーバーは自動取得します。

**[エディター別の導入・更新・エラー対処](docs/editors.md)**

コンパイラとプラグインは別のReleaseです。コンパイラのダウンロードには`v0.4.0`、プラグイン修正版には`plugin-v0.4.0-r2`を使います。Marketplace・Zed拡張レジストリーでの配布は行っていません。

## ソースから実行する

Python 3.12以降を使用します。

```sh
git clone https://github.com/sofia-gros/gscript.git
cd gscript
python -m gscript examples/hello.gs --out-dir build/hello
node build/hello/hello.mjs
```

`gs`コマンドとして導入する場合は[仮想環境へのインストール](docs/installation.md)を参照してください。

## 開発・テスト

```sh
npm ci --ignore-scripts
python -m unittest discover -s tests -v
```

コンパイラ本体、生成JS/MJS/TSの実行、外部型連携を検証します。エディター拡張の配布テストは[公開ワークフロー](.github/workflows/plugins.yml)を参照してください。
