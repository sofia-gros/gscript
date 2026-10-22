# v0.4からv0.5へ

1. コンパイラとプラグインを両方0.5.0へ更新します。
2. intとfloatは別型です。var x float = 1 は1.0またはfloat(1)へ変えます。float64はfloatの別名です。
3. JSのnumberはint/floatの上位型です。外部numberをintへ使う場合はint(value)、floatへはfloat(value)が必要です。
4. int/intの除算結果はJSの動作に合わせfloatです。整数にする場合はint(a / b)を明示します。
5. printfの先頭引数は文字列です。値をそのまま表示する場合はprintln(value)を使います。
6. pop/shift/findはundefinedを返し得ます。--strict-nullでチェックし、分岐で絞り込んで使います。
7. CLIの既定出力はmjsからjsへ、標準出力からdistへのファイル出力へ変更しました。gs main.gsの後はnode dist/main.jsで実行できます。
8. gs .は既定でminifyします。可読出力は--no-minify、従来のmjsは--format mjsを指定します。
9. gsconfig.jsonを使う場合、エディターも同じstrictNull/lib設定を読みます。VSCodeのgscript.strictNullはnullが設定追従です。

公開済みv0.4のタグ・配布物は変更しません。新しい配布物はv0.5.0とplugin-v0.5.0です。
