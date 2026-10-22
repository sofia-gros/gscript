# 型宣言の生成

```sh
gs . --declaration
```

js出力には.d.ts、mjs出力には.d.mtsを生成します。公開関数・変数・struct/class・interface・enum・型エイリアス・generics・union・nullable・継承・メソッド・constructorを宣言します。モジュール間importも対応するJS拡張子へ変換します。

int/floatはnumberを基底とするGSInt/GSFloatブランド型です。numberへは代入できますが、TSの通常numberをGSIntへ渡すには境界で明示的に扱う必要があります。ブランドはモジュール間で互換です。ブランドは型レベルのみで、JSにタグやラッパーはありません。

生成宣言の消費はstrict TypeScriptで検証します。外部型は元ライブラリーの型を参照するため、利用者にもその依存パッケージが必要です。
