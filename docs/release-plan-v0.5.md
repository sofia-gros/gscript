# GScript v0.5.0 開発計画書

**Repository:** https://github.com/sofia-gros/gscript  
**Previous Version:** v0.4.0  
**Target Version:** v0.5.0  
**Status:** 開発計画・仕様策定

---

## 1. 基本開発方針

GScriptはGo風の構文と独自の静的型検査を備え、JavaScript / TypeScriptへコンパイルするプログラミング言語である。

v0.5.0では、言語としての完成度、実行性能、コンパイル性能、開発体験を改善する。

### 基本原則

1. 型の整合性はGSコンパイラがコンパイル時に検証する。
2. 出力JavaScriptには型検査用の追加処理を挿入しない。
3. JSの標準APIやnpmエコシステムとの互換性を維持する。
4. Go風の関数名は実用上のエイリアスとして提供する。
5. 生成されるJSは可読性と実行性能を重視する。
6. CLIは短く、基本操作にオプション指定を要求しない。
7. TypeScriptのコンパイル処理はGSとTS本家から選択できる。
8. VSCodeとZedの既存拡張を改善する。
9. コンパイル時の無駄な処理を削減し、高速化する。
10. 新機能はそれぞれ独立した回帰テストを持つ。

## 2. F01 — 厳密な数値型検査

**Priority: P0**

### 2.1 型の定義

GScriptコンパイラ内部では、次の型を区別する。

| 型 | 内容 |
|---|---|
| int | 整数 |
| float | 浮動小数点数 |
| float64 | 浮動小数点型。floatとの関係を仕様上定義する |
| number | JavaScript相互運用用の数値型 |

`int` と `float` は同じ型ではない。

現在の `int` / `float` / `float64` / `number` をすべて同一の型として解析する処理を変更する。

### 2.2 コンパイル時の検証

```go
a := 10       // int
b := 10.5     // float
c := 10.0     // float

var x int = 10
var y float = 10.5
```

以下はコンパイルエラーとする。

```go
var a int = 10.5
var b float = 10

var x int = 10
var y float = 2.5

z := x + y
```

型検査の対象は以下。

- 変数宣言と代入
- リテラル
- 算術演算
- 比較演算
- 関数引数と戻り値
- 配列の要素型
- structのフィールド
- GenericsとUnion
- 外部JS / TSとの型境界

暗黙の数値型変換は禁止する。

必要な場合は明示的に変換する。

```go
a := 10
b := float(a)
```

### 2.3 JavaScript生成

型検査が成功したコードは、余計な型情報を持たない通常のJavaScriptに変換する。

GS:

```go
a := 10
b := 20
c := a + b
```

JS:

```javascript
let a = 10;
let b = 20;
let c = a + b;
```

**型検査はコンパイラのみが担当する。**

生成JSに追加しないもの：

- BigIntへの強制変換
- ランタイム型チェック
- 数値型のタグ付きオブジェクト
- int / floatの判定ヘルパー
- 数値型を維持するためのラッパークラス

数値表現は通常のJavaScript Numberを利用する。

ただし、JavaScript Number自体の精度限界や、実行時に外部APIが返す値はコンパイル時検査だけでは保証できない。これはGSの型チェックとJSの実行時仕様を分離した制約として文書化する。

### 2.4 受け入れ条件

- int / floatの混在をコンパイル時に拒否する。
- 正しい明示的型変換を許可する。
- 数値型の検査が配列や関数にも適用される。
- 生成JSに数値型専用のランタイム処理がない。
- 数値演算の実行性能が不要な変換によって低下しない。

## 3. F02 — Go風関数名の追加

**Priority: P0**

### 3.1 基本方針

完全なGo互換ランタイムは実装しない。

Go風の関数名を使用できるようにし、コンパイラが適切なJavaScript APIへ変換する。

目的は構文・API上の親しみやすさであり、Go標準ライブラリの完全な再現ではない。

### 3.2 関数変換

対象：

- `print`
- `println`
- `printf`

```go
print("Hello")
println("World")
printf("Hello %s", "Sofia")

console.log("JavaScript API")
```

概念的なJS変換：

```javascript
console.log("Hello");
console.log("World");
console.log("Hello %s", "Sofia");

console.log("JavaScript API");
```

`println` および `printf` の改行は、原則として `console.log` 自身の改行動作を利用する。

`printf` は必要な引数展開や基本的な書式処理だけを行う。`console.log` が利用可能な書式指定を使い、Goの `fmt.Printf` と完全に一致させる必要はない。

不要な改行文字を追加して二重改行になることは避ける。

### 3.3 実装方針

- 組み込み関数として名前を登録する。
- ASTで呼び出し先を解決する。
- 文字列による単純置換は使用しない。
- ユーザー定義の同名関数と区別する。
- 必要以上のランタイムヘルパーを追加しない。
- 通常の `console.log` 呼び出しは変更しない。

Go風APIは見せかけの互換性を提供するものであり、バイト数・エラーの複数戻り値などは実装しない。

## 4. F03 — JavaScript出力の可読性改善

**Priority: P0**

### 4.1 目標

GS:

```go
func greet(name string) string {
  return "Hello, " + name
}

name := "Sofia"
console.log(greet(name))
```

出力JS:

```javascript
function greet(name) {
  return "Hello, " + name;
}

let name = "Sofia";
console.log(greet(name));
```

### 4.2 実装内容

- 元の変数名を可能な限り維持する。
- 不要な括弧を削減する。
- JSの演算子優先順位に従って括弧を出力する。
- 不必要な内部一時変数を生成しない。
- 衝突する識別子だけを必要に応じて変更する。
- GSのコメントを保持する。
- インデントを2スペースに統一する。
- 読みやすい空行・関数配置にする。
- `new`、optional chaining、nullish coalescing等の意味を維持する。

内部の型検証用コードと最終出力コードを分離する。

## 5. F04 — CLIの簡略化

**Priority: P0**

### 5.1 最小コマンド

以下の2つだけでコンパイルできることを必須とする。

```bash
gs .
gs main.gs
```

オプション指定は必須にしない。

### 5.2 コマンド仕様

| コマンド | 処理 |
|---|---|
| `gs .` | プロジェクトをJSとしてminifyビルド |
| `gs main.gs` | 指定ファイルを可読JSへコンパイル |
| `gs --ts-compiler ts` | 現在のプロジェクトをTSコンパイラ経由でビルド |
| `gs . --format ts` | TSファイルを生成 |
| `gs main.gs --minify` | 指定ファイルをminify |
| `gs . --no-minify` | 可読JSを生成 |
| `gs main.gs -o output.js` | 出力先を指定 |
| `gs . --check` | 型検査のみ |
| `gs lint` | 現在のプロジェクトをLint |
| `gs fmt` | 現在のプロジェクトを整形 |
| `gs watch` | 自動再コンパイル |
| `gs init` | プロジェクト初期化 |

### 5.3 デフォルト動作

`gs .` は原則として以下と同等。

```bash
gs main.gs --format js --minify --out-dir dist
```

エントリーポイントはプロジェクト設定、`main.gs`、`main.gos` の順に解決する。

`gs main.gs` はデフォルトの出力先を自動決定する。

```text
project/
├── main.gs
└── dist/
    └── main.js
```

複数の依存モジュールがある場合も自動処理する。

入力ファイルを上書きしない。

既存のCLIとの違いについては移行手順を用意する。

### 5.4 オプション

すべてのオプションは必要な場合のみ指定する。

- `--format js|mjs|ts`
- `--minify`
- `--no-minify`
- `--ts-compiler gs|ts`
- `--check`
- `--sourcemap`
- `--declaration`
- `--strict-null`
- `-o` / `--out-dir`
- `--no-cache`

基本的なビルドには設定ファイルも必須にしない。

## 6. F05 — TypeScriptコンパイラ選択

**Priority: P0**

### 6.1 新オプション

```bash
gs . --ts-compiler gs
gs . --ts-compiler ts
```

省略時は `gs` を選択する。

### 6.2 GSコンパイラモード

```bash
gs . --ts-compiler gs
```

処理：

1. GSソースを解析する。
2. GSコンパイラが型検査を実行する。
3. GSコンパイラがJSまたはTSを生成する。
4. 必要に応じてMinifyする。
5. 出力する。

GSのみのソースではTypeScriptを起動しない。

ただし、外部TS型定義が必要な場合は既存の外部型解析機能を利用する。

### 6.3 TSコンパイラモード

```bash
gs . --ts-compiler ts
```

処理：

1. GSソースを解析する。
2. GSコンパイラがGS自身の型検査を実行する。
3. GSから中間TypeScriptコードを生成する。
4. 本家TypeScriptコンパイラで検証・JS生成する。
5. 必要に応じてMinifyする。
6. 出力する。

GSの構文解析とGS固有の型検査をTypeScriptへ委譲するわけではない。

### 6.4 TypeScriptバージョン

対応対象：

- TypeScript 5.9
- TypeScript 6.0
- TypeScript 7.0

正式版のみ対応する。

TypeScript 7.0のネイティブCLIと、5.9 / 6.0のJavaScript Compiler APIの違いを吸収するアダプターを用意する。

`--format ts` はTSソースの出力指定であり、`--ts-compiler` は最終JS生成を担当するコンパイラの選択として分離する。

## 7. F06 — Source Map

**Priority: P0**

生成されたJSと元のGSソース位置を対応付ける。

```text
main.gs
dist/
├── main.js
└── main.js.map
```

対応内容：

- JS / MJS出力
- Minify済みJS
- TSコンパイラ経由のJS
- モジュール間の対応
- 関数・クラス・非同期関数
- 元のGSファイル名と行・列情報

`--sourcemap` を指定できるようにする。

Source Mapを生成する場合も、通常のコンパイル性能への影響を最小化する。

## 8. F07 — `.d.ts` の自動生成

**Priority: P0**

GSの公開APIからTypeScript型定義を生成する。

```bash
gs . --declaration
```

対応対象：

- function
- struct / class
- interface
- Generics
- enum
- Union
- Nullable
- 型エイリアス
- 継承
- メソッドとコンストラクター

GSの `int` と `float` は型情報として区別する。

生成JSに実行時型チェックは追加しない。

必要な場合は `.d.ts` の型レベルだけで区別できるブランド型等を使用する。

## 9. F08 — Zed / VSCode拡張

**Priority: P0**

### Zed

既存のRust製拡張とGitHub Actionsを改善する。

- RustコードをGitHub Actionsでビルドする。
- `wasm32-wasip2` を対象とする。
- WASMをRelease成果物に含める。
- Tree-sitter grammarを更新する。
- 対応OSのLSP実行ファイルを生成する。
- 拡張のバージョンをv0.5.0に統一する。
- 生成した配布物の動作を確認する。
- ローカル導入時のビルドや外部依存を可能な限り減らす。

Zedが開発拡張を再ビルドする場合があるため、GitHub Actionsで生成したWASMをそのまま利用できるか、実際の導入経路で確認する。

### VSCode

- VSIXの自動生成
- LSPの同梱
- v0.5.0の構文へ更新
- CLI設定との連携
- インストールテスト
- Releaseからの導入手順を整備

## 10. F09 — LSP機能強化

**Priority: P0 / P1**

追加する機能：

- Go to Definition
- Rename Symbol
- Find References
- ローカル変数の補完
- 型に応じたプロパティ補完
- Signature Help
- 未使用変数の診断
- 自動import候補
- `gs fmt` との連携
- `gs lint` の診断表示

LSPはコンパイラのAST・シンボル情報を再利用する。

不要な全ファイル再解析を減らし、編集時の応答速度を重視する。

## 11. F10 — `gs lint`

**Priority: P1**

静的解析専用コマンドを追加する。

```bash
gs lint
gs lint main.gs
gs lint .
```

解析内容：

- 未使用変数
- 未使用import
- 到達不能コード
- 不要な条件分岐
- 常に同じ値になる条件
- 不要な型変換
- 不必要なany型
- シャドーイングに関する警告
- 型宣言の不整合
- 非推奨API
- 不審な数値演算

エラーと警告を区別する。

```text
main.gs:12:5 warning GS1002
Unused variable: result
```

追加オプション：

```bash
gs lint --fix
gs lint --json
```

`--fix` は動作を変えないことが確認できる修正のみを行う。

基本的なコンパイル時型チェックとLint専用の追加診断は分離する。

## 12. F11 — `gs watch`

**Priority: P1**

```bash
gs watch
```

現在のプロジェクトを監視し、変更が発生した場合に自動コンパイルする。

対応内容：

- ファイル変更検出
- 依存モジュールの変更検出
- 増分コンパイル
- キャッシュ再利用
- 不要な連続ビルドの抑制
- コンパイル失敗時の既存成果物保護
- 正常な停止処理

## 13. F12 — `gs fmt`

**Priority: P1**

```bash
gs fmt
gs fmt main.gs
gs fmt . --check
```

GSのソースコードを整形する。

仕様：

- 2スペースインデント
- コメント維持
- 不必要な空白の削除
- 宣言・関数・構造体の統一整形
- 繰り返し整形しても出力が変わらない
- ASTの意味が変化しない
- LSP経由でエディターから利用できる

## 14. F13 — `gs init`

**Priority: P1**

```bash
gs init
```

GScriptプロジェクトを作成する。

追加テンプレート：

```bash
gs init --template node
gs init --template browser
gs init --template phaser
```

生成内容：

```text
project/
├── main.gs
├── package.json
├── gsconfig.json
└── .gitignore
```

`gsconfig.json` は省略可能とする。

プロジェクトに設定ファイルが存在しない場合は、標準設定で動作する。

## 15. F14 — JavaScript標準API認識

**Priority: P1**

JavaScriptの標準APIをGSから利用できるようにする。

対象：

- ECMAScript標準API
- DOM
- Node.js
- Web Worker
- JavaScript実行環境固有のAPI
- 型定義を持つ外部ライブラリ

TypeScriptの型定義を読み取る仕組みを拡張する。

TSが導入されていない場合も、GSが標準で認識できるJS APIは従来どおり利用可能とする。

新しいAPIの型情報が利用できる場合は、コンパイル時の診断精度を向上させる。

## 16. F15 — 組み込み関数レジストリ

**Priority: P1**

Go風関数とGS組み込み関数を管理する。

対象：

- print
- println
- printf
- len
- int / float変換
- string変換
- panic

それぞれに以下を定義する。

- 関数名
- 引数型
- 戻り値型
- 型検査ルール
- JSへの変換ルール
- 必要なランタイム依存

原則として直接的なJS変換を優先する。

`len` は対象型に応じた `.length` や `.size` 等への変換を基本とし、Goの文字列バイト長まで完全互換にすることは要求しない。

## 17. F17 — コンパイル性能の最適化

**Priority: P0**

v0.5.0全体の必須要件とする。

### 17.1 最適化対象

- Lexer / Parser
- AST生成
- シンボル解決
- 型検査
- モジュール依存解析
- TypeScript型情報の読み取り
- JavaScriptコード生成
- Minify
- Source Map生成
- キャッシュ
- CLI起動処理
- LSP再解析

### 17.2 最適化方針

1. 同じソースを何度も解析しない。
2. AST・型情報を再利用する。
3. 依存関係が変化していないモジュールを再コンパイルしない。
4. 変更の影響を受けるモジュールだけを処理する。
5. 不要なTypeScriptプロセスを起動しない。
6. 文字列連結や不要なオブジェクト生成を削減する。
7. キャッシュの妥当性を内容ベースで判定する。
8. コンパイル処理を独立したフェーズに整理する。
9. 並列化の効果がある処理だけを並列化する。
10. 性能改善によって型検査や言語仕様を省略しない。

### 18.3 ベンチマーク

- 単一ファイル
- 100モジュール
- 1,000モジュール
- 外部型定義を利用したプロジェクト
- 大規模Phaserプロジェクト
- 初回ビルド
- キャッシュ有効ビルド
- 1ファイルのみ変更した増分ビルド

コンパイル時間、ピークメモリ、生成物サイズを測定する。

v0.4.0を比較基準とし、速度低下が発生した場合は原因を特定する。

特に通常のGSコンパイルは軽量であることを優先し、追加機能によって不要な処理が常時起動する構造を禁止する。

## 19. 実装ロードマップ

| Phase | 内容 | 優先度 |
|---|---|---|
| M00 | v0.4.0基準テスト・性能計測・配列再現テスト | P0 |
| M01 | 数値型の厳密化・配列型の修正 | P0 |
| M02 | 組み込み関数レジストリ・Go風関数 | P0 |
| M03 | JS/TS生成の可読性改善 | P0 |
| M04 | CLI簡略化・Minify | P0 |
| M05 | TypeScriptコンパイラ選択 | P0 |
| M06 | Source Map・`.d.ts`生成 | P0 |
| M07 | Lint・Formatter | P1 |
| M08 | Watch・Init | P1 |
| M09 | JS標準API型解析 | P1 |
| M10 | LSP機能強化 | P0/P1 |
| M11 | VSCode・Zed拡張・GitHub Actions | P0 |
| M12 | コンパイル性能最適化・総合検証 | P0 |
| M13 | v0.5.0 Release | P0 |

性能改善はM12だけで行うのではなく、すべてのフェーズを通じて測定・改善する。

各フェーズの完了条件は以下。

- 対象機能の仕様を満たす。
- 対象機能の正常系・異常系テストが通る。
- 既存機能に意図しない回帰がない。
- 性能上の明確な問題が残っていない。
- 必要なドキュメントを更新している。

## 20. リリース受け入れ条件

### 型検査

- int / floatをコンパイル時に厳密に区別する。
- 配列の型検査が正確に動作する。
- JSへ不要な実行時型チェックを追加しない。

### コード生成

- GSの変数名を維持する。
- 読みやすいJSを生成できる。
- Minify出力が正常に実行できる。
- Source Mapと型宣言が正しく生成される。

### CLI

- `gs .` が動く。
- `gs main.gs` が動く。
- オプションの必須指定がない。
- `--ts-compiler gs|ts` が機能する。
- `gs lint` / `gs fmt` / `gs watch` / `gs init` が動く。

### 開発環境

- VSCodeの拡張が動く。
- Zedの拡張が動く。
- GitHub Actionsで配布物を生成できる。
- LSPの診断・補完・定義ジャンプが機能する。

### 性能

- 通常のGSコンパイルに不要な外部プロセスを起動しない。
- キャッシュが正しく動作する。
- 増分ビルドが変更範囲を限定できる。
- 大規模プロジェクトでのコンパイル時間を計測する。
- 生成JSに不要なランタイム負荷を加えない。
- 既存の正常なビルド成果物をエラー時に破損させない。

## 21. ドキュメント

v0.5.0で更新・追加するドキュメント。

```text
docs/
├── release-plan-v0.5.md
├── language-v0.5.md
├── numeric-types.md
├── builtins.md
├── arrays.md
├── cli.md
├── compiler-output.md
├── typescript-interop.md
├── source-maps.md
├── declarations.md
├── lint.md
├── formatter.md
├── performance.md
├── editors.md
├── migration-v0.4-to-v0.5.md
└── releases/
    └── v0.5.0.md
```

## 22. v0.5.0 最終目標

GScript v0.5.0は、以下を満たすコンパイラ・開発ツールとして完成させる。

1. 独立した厳密な静的型システム
2. 高速なGSコンパイル
3. 余計な実行時処理を持たないJavaScript
4. Go風の簡潔な構文と標準関数
5. JavaScript / TypeScriptとの柔軟な連携
6. 読みやすいJavaScript出力
7. `gs .` で完結するビルド
8. 型宣言・Source Map・Lint・Formatter
9. 増分ビルドとキャッシュ
10. VSCode・Zedとの統合

**基本方針：型はコンパイラが責任を持って検査し、JavaScript実行時には不要な負荷を持ち込まない。開発者は最小限のコマンドで高速にビルドできる。**