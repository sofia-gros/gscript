# v0.5 組み込み関数

組み込みはASTの名前解決によって認識します。同名のユーザー定義関数・変数は組み込みを隠します。

| 関数 | 変換・意味 |
| --- | --- |
| print / println | console.log。どちらもconsoleの改行動作に従う |
| printf(format, ...args) | console.log(format, ...args)。formatはstring。書式は実行環境のconsoleに従う |
| int(value) | 数値をMath.truncで切り捨て |
| float / float64 / number(value) | 数値をNumberへ明示変換 |
| string(value) | String(value) |
| len(value) | 配列・文字列のlength、外部Map/Setのsize。戻り値はint |
| panic(value) | Errorをthrow |

Go fmtのバイト数・errorの戻り値や、printの改行なし動作は再現しません。文字列のlenはJSのUTF-16コード単位数です。
