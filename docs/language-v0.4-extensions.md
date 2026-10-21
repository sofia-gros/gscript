# GS v0.4 言語拡張仕様

提案書 F01–F13 の未確定点を、実装前に以下のように定める。

- struct は単一継承、interface は複数継承。implements は複数指定できる。interface は構造的な型であり、関数メンバーは引数の反変・戻り値の共変を検査する。
- 明示的 constructor は通常の位置引数を使う。その struct で従来の `T{...}` を使うことは禁止し、`new T(...)` を使う。constructor のない既存 struct は従来のオブジェクト引数・リテラルを維持する。
- 派生 struct に constructor がなければ親の引数を転送する。初期化は親の constructor、派生フィールド、派生 constructor 本体の順。派生 constructor の super は最初の実行文として必須、一度だけとする。super 前の引数評価でもレシーバーを使用できない。`super.method()` はインスタンスメソッド内で利用できる。
- constructor の戻り値型・値を返す return は禁止。明示的 override は親のメソッドと適合する必要がある。override の省略は互換性のため許すが、上書きの型は常に検査する。
- `T?` は `T | nil`。既存の参照型の nil の動作は維持し、`--strict-null` で非 Nullable への nil を禁止する。明示的な Nullable のアクセスはどちらのモードでも検査する。null と undefined は区別し、`undefined` 型・値も利用できる。
- Optional Chaining と Nullish Coalescing はそのまま JS に出力する。`??` と `&&` / `||` の括弧なし混在は禁止。評価は一度で、JS の短絡評価を使う。
- Union は構造的互換性を使う。文字列・数値・真偽値リテラル型を含められ、nil 比較・typeof・instanceof による絞り込みを利用できる。
- 型パラメーターは `<T, U extends Constraint>`。struct/interface/alias/function で使用でき、関数呼び出しでは型引数を推論する。型情報は JS で消去し、特殊化用コードを生成しない。
- switch は式を一度だけ評価し、strict equality で比較する。複数 case は `case a, b:`、暗黙の fallthrough はなく、break は switch を抜ける。default のない switch は入力が有限 Union/enum の場合に網羅性を検査する。
- public が既定。private/protected/readonly はコンパイル時の制約で、JS のフィールドは通常の own property。readonly は浅い制約で constructor 内の初期化だけを許す。static フィールドとメソッドは JS の static として出力する。static メソッドのレシーバーはクラス自身を指す。
- enum は省略時 0 からの数値、自動増分。明示値は整数定数または文字列。同一 enum は数値・文字列を混在させない。文字列 enum では全メンバーに値が必要。実行時は凍結オブジェクト、型はその値の Union とする。enum は値集合として検査し、別 enum と同じ値は構造的に互換。
- primitive/object/function/Union/generic alias は型検査後に消去する。直接または相互の無条件循環 alias は拒否し、object/array 等を介する再帰型は許す。

GS 自身のパーサー・型検査器が全機能を検査する。外部型定義の読み取りと出力 TS の検証は、その GS 型検査の代用にしない。

## 利用例と検証

実行可能な機能別の例は `tests/test_extensions.py`、実際のPhaser.Sceneの継承は `tests/fixtures/interop/phaser-scene.gs` にあります。Phaser 3.90の型定義ではcreateは親クラスのメソッドとして宣言されていないため、そのフックはoverrideを付けずに追加します。親にないメソッドへoverrideを付けた場合はエラーです。

外部型の読み取りにはNode / TypeScriptが必要ですが、GSのみの継承・型・Generics等の検査には不要です。`compile_source(source, strict_null=True)` と CLIの `--strict-null` で厳密なnil代入検査を選べます。

派生クラスの自動constructorは親の引数のみを受け取り、派生フィールドへのオブジェクト引数の割り当てを追加しません。独自の初期化が必要ならconstructorを定義してください。型パラメーターそのものを型とするフィールドでは、型引数の型がnilを受け入れない場合、structリテラル・既定constructorにそのフィールドの値が必要です。

staticフィールドを持つclassとその派生classは、元の宣言位置で評価します。static初期化はその位置までに初期化済みのトップレベル値を参照できます。これらのclassを初期化前に値として使用する場合はコンパイルエラーです。従来のstaticフィールドを持たないstructの前方参照は維持します。
