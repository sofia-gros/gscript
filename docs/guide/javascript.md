# JavaScript・TypeScript・npm

GSから既存のJS / TSファイルやnpmパッケージを利用できます。APIをGS向けに書き直す前に、外部の型情報を使ったimportを試してみましょう。

## JS / TS / npm

```gs
import { value } from "./library.ts"
import Phaser from "phaser"
var config Phaser.Types.Core.GameConfig = {
  type: Phaser.AUTO,
  width: 800,
  height: 600,
}
game := new Phaser.Game(config)
```

最初のimportは独立した形式例です。利用する実ファイルとそのexportが必要です。npm依存は通常のnode_modulesへ導入します。

外部の`.d.ts`、TSソース、JSのJSDocや推論型から型情報を読み取り、GS自身が代入・引数・メンバーを検査します。外部JSのnumberは整数と確定できないためGSでもnumberです。intが必要なら`int(value)`を明示します。

ローカルJS / TSは出力へ配置します。npmのbare importは保持するため、実行先でも依存を解決できる必要があります。コンパイラはnpm installやバンドルを自動実行しません。ブラウザーではバンドラーやimport map等で依存を解決します。Node.jsやDOMのAPIをGSが別環境向けに自動移植することもありません。


## 型情報と実行の境界

GSの型検査は外部ファイルを実行せずに行います。明示的なanyや型情報のない値は動的な意味になります。宣言と実装が食い違う外部ライブラリの動作までは保証しません。

npm・Node.js・DOMを使うコードはJS / TS経路で扱います。ネイティブから同じライブラリを呼ぶには、そのライブラリが公開するC ABI等の別の接続方法が必要です。
