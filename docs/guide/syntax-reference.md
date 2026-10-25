# 構文リファレンス

使いたい構文を探すための索引です。各リンク先で書き方と意味を説明します。ネイティブ専用の構文は別の表に分けています。

## JS / TS経路

| 分類 | 構文 | 説明 |
| --- | --- | --- |
| コメント | `//`、`/* ... */` | [変数と値](variables.md) |
| 宣言 | `var`、`let`、`const`、`:=` | [変数と値](variables.md) |
| リテラル | 文字列・数値・bool・nil・undefined | [変数と値](variables.md) |
| 数値・代入 | `+ - * / %`、`= += -=`、`++ --` | [数値と演算](numbers.md) |
| 比較・論理 | `== != < > <= >=`、`&& || !` | [数値と演算](numbers.md) |
| 関数 | 名前付きfunc、無名func、関数型、return | [関数](functions.md) |
| 制御 | if / else、3節for、条件for、無限for、range、break / continue、switch | [条件分岐とループ](control-flow.md) |
| コレクション | `[]T{...}`、`{key: value}`、省略プロパティ、spread、添字 | [配列とオブジェクト](collections.md) |
| 非同期・例外 | async / await、try / catch、throw | [非同期処理と例外](async-errors.md) |
| 型 | 基本型、Union、Nullable、関数型、オブジェクト型 | [型の基本](type-system.md) |
| オブジェクト | struct、レシーバーメソッド、new | [structとメソッド](structs.md) |
| 継承 | extends、constructor、super、override | [継承と初期化](inheritance.md) |
| 契約 | interface、implements | [interface](interfaces.md) |
| 型の判別 | typeof、instanceof、nil比較 | [UnionとNullable](unions.md) |
| null対応 | `?.`、`?.[]`、`?.()`、`??` | [UnionとNullable](unions.md) |
| 型引数 | `<T>`、`extends`制約 | [Generics](generics.md) |
| メンバー | public / private / protected / readonly / static | [アクセス制御とstatic](members.md) |
| 型宣言 | type alias、enum、再帰型、省略可能プロパティ | [型エイリアスとenum](aliases-enums.md) |
| モジュール | named / default / namespace / side-effect import、export | [モジュール](modules.md) |

## ネイティブ専用

| 分類 | 構文・型 | 説明 |
| --- | --- | --- |
| 型 | 固定幅整数、isize / usize、f32 / f64、cchar | [型とメモリ](native-types.md) |
| 保存領域 | `[N]T`、C-layout struct / union | [型とメモリ](native-types.md) |
| ポインター | ptr / cptr、address / load / store / offset / cast | [型とメモリ](native-types.md) |
| レイアウト | sizeof / alignof / offsetof | [型とメモリ](native-types.md) |
| FFI | extern C / system、link、system func、winfunc | [C ABIとWin32](native-ffi.md) |
| 文字列境界 | cstr、utf16、Cポインターからstring | [C ABIとWin32](native-ffi.md) |

## この版にない構文

Goのpackage、go、defer、channel、map型、複数戻り値、ポインター記法`*T`はJS経路にありません。JSのclass宣言・アロー関数・三項演算子・分割代入・テンプレートリテラル・finallyもGSの構文ではありません。

class相当はstruct、アロー関数相当は無名funcを使います。ネイティブのポインターは`ptr<T>`です。JS構文をGSへそのまま貼り付ける代わりに、[Go・JavaScriptとの比較](comparison.md)で対応する記法を確認してください。
