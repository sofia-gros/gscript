# Source Map

```sh
gs main.gs --sourcemap
node --enable-source-maps dist/main.js
gs . --sourcemap --format mjs --ts-compiler ts
```

GSモジュールごとにmain.js.map/main.mjs.mapとsourceMappingURLを出力します。v3のsources/sourcesContent/mappingsを持ち、元GSのファイル名・行・UTF-16列へ対応させます。可読・minify出力、公式TS 5.9/6.0/7.0経由、モジュール間、関数・メソッド・asyncに対応します。エディターやブラウザーのデバッガーは標準Source Mapとして読み取れます。

通常ビルドでは詳細位置追跡を起動しません。マップはGSコード用です。コピーした外部JS/TSの独自マップは外部のビルド設定で管理してください。
