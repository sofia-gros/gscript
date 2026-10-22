# コンパイラ出力

js/mjsはES2022 Modules、tsは型注釈付き中間TypeScriptです。JS/TS出力では必要に応じてpackage.jsonのtype:moduleを作成します。既存CommonJS設定との衝突はエラーです。

可読出力は2スペース、元の識別子とコメントを維持し、演算子の優先順位に必要な括弧だけを使います。スコープ衝突を回避する場合は内部名を生成します。--minifyはGSが生成したJSの空白・コメントを削減し、コピーした外部JSは変更しません。バンドルやnpm依存の内包は行いません。

int/floatの型検査はコンパイル時だけです。生成物には数値型タグ、判定ヘルパー、BigInt変換を追加しません。明示的int変換はMath.trunc、float変換はNumberを使います。structコンストラクター等の言語動作に必要なコードは出力します。

[Source Map](source-maps.md)と[宣言ファイル](declarations.md)は独立したオプションです。コンパイルエラー時は既存成果物を更新しません。
