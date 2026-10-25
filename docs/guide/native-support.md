# ネイティブの対応範囲

ネイティブはJS経路のすべての構文を実装しているわけではありません。v0.6.1で利用できる機能と、コンパイル時に拒否される機能をまとめます。

## 現在の対応範囲

静的な関数・再帰、変数・定数、if、for、break/continue、基本数値・bool・文字列、C-layout struct/union、型エイリアス、固定長配列、ポインター、関数ポインター、名前付きGS import/export、C/system FFIを対象とします。

async、クロージャ、generics、継承、interface、動的配列、JSの動的オブジェクト、例外は今後の対象です。未対応コードはGSコンパイラがエラーにし、JS経路へ自動で切り替えることはありません。npm・Node・DOMを使うコードは[JS / TS経路](javascript.md)で利用できます。
