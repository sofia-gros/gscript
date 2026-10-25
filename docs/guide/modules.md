# モジュール

プログラムをファイルに分割し、exportした宣言を別のファイルからimportします。GSでは1つのファイルをモジュールとして扱います。

## importとexport

```gs
import { add, subtract as sub } from "./math.gs"
import * as math from "./math.gs"
import DefaultValue from "./library.js"
import "./setup.js"
```

上記はimport形式の一覧で、同じモジュールを重複して取り込むことを推奨する例ではありません。

```gs
export func add(a, b int) int { return a + b }
export const name = "GS"
export type Point struct { X int; Y int }
```

`export default expression`も利用できます。外部の型も通常のimportで取り込み、型のみの利用はJS出力から取り除きます。`import type`という独立したGS構文はありません。モジュール宣言はトップレベルに記述します。詳しいライブラリ連携は[モジュールと外部ライブラリ](javascript.md)を参照してください。


## GSモジュール

`math.gs`:

```gs
export func add(a, b int) int { return a + b }
```

`main.gs`:

```gs
import { add } from "./math.gs"
println(add(2, 3))
```

入口から到達するモジュールを検査します。import先の引数や戻り値もGSで検査します。JS出力時はimportの拡張子を生成先に合わせます。GSのファイルはGoのpackage単位ではなくモジュール単位です。
