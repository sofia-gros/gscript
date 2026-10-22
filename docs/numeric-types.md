# v0.5 数値型

`int`と`float`は異なる静的型です。`float64`は`float`の別名です。`10`はint、`10.0`・`10.5`・`1e2`はfloatと推論します。int/float間の暗黙変換は行いません。配列、フィールド、関数、Generics、Unionでも同じ規則を適用します。

`number`はJavaScriptの数値を扱う上位型です。int/floatをnumberへ渡すことは、値を変換しない型の拡大として許可します。numberからint/floatへ狭める場合は明示変換が必要です。外部JS/TSのnumberは、整数と静的に証明できないためGSでもnumberとして読み込みます。

`int(value)`は`Math.trunc(value)`、`float(value)`・`float64(value)`・`number(value)`は`Number(value)`に変換します。型変換は明示された場所でのみ実行します。通常の数値演算に型タグ、BigInt、実行時型判定、ラッパークラスを挿入しません。

実行時の表現はJavaScript Numberです。Numberの精度限界、Infinity/NaN、外部APIの実際の戻り値、明示変換の結果を実行時に追加監視しません。int同士の除算`a / b`の静的な結果型はfloatです。Goの整数除算のように丸めたい場合は`int(a / b)`を明示します。
