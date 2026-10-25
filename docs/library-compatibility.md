# ライブラリ互換性

ライブラリは実行対象に合う経路で利用します。

| ライブラリ | 使用経路 | 型と連携 |
| --- | --- | --- |
| Node.js標準API | JS / TS | `node:` import、任意のNode標準型定義 |
| npmのJS / TSパッケージ | JS / TS | 既存node_modules、.d.ts、JSDocを読み、GSが呼び出しを検査 |
| Phaser等のブラウザーライブラリ | JS / TS | 型検査後、ブラウザー・バンドラー等で依存解決 |
| GSの共通静的コード | 両方 | 両経路の対応構文・型の範囲に収まるモジュールを利用 |
| C ABIの既存ライブラリ | Native | `extern "C"`、リンク対象と検索ディレクトリーを指定 |
| Win32 API | Native | `extern "system"`、`winfunc`、固定幅型・ポインター・C互換レコード |
| GSから作成したライブラリ | Native | 公開関数をC ABIでexport、ヘッダーを生成 |
| Rust / C++のライブラリ | Native | ライブラリ側のC ABIエクスポート／ラッパーを使用 |

## Node.js・TypeScript・npm

既存のJS / TS経路を維持します。GS自身の型検査器が外部型のメタデータを使用し、GSの構文・型の適否を判断します。

```sh
npm install --save-dev typescript@5.9.3 @types/node
npm install phaser@3.90.0
gs game.gs --check
gs game.gs --format mjs --out-dir dist
```

Node標準型を厳密に使う場合はgsconfig.jsonの`lib`を`["es2022","node"]`にします。ブラウザーでは`["es2022","dom"]`等を指定します。公式TS 5.9/6.0/7.0の最終JS生成と、TS7でのメタデータAPI併用方法は[相互運用ガイド](typescript-interop.md)を参照してください。

Node/npmパッケージのコードはJSの実行環境で動きます。ネイティブへ接続する場合には、そのパッケージ／基底ライブラリが提供するC ABIを利用するか、GSのネイティブ対応範囲に合わせた実装が必要です。Node用`.node`アドオンも、Node ABIを使用する場合はJS / TS経路で利用します。

## ネイティブライブラリ

```go
extern "C" func puts(text cptr<cchar>) i32
puts(cstr("Hello, C ABI"))
```

```sh
python -m gscript app.gs --backend native --link example --library-dir /path/to/libs
python -m gscript app.gs --backend native --link-object /path/to/example.o
```

OS・CPU・ABIが一致するオブジェクト／ライブラリを使用します。動的ライブラリの実行時検索はOSのローダー設定に従います。C++クラスのABI、Rust固有のABI、JSオブジェクトのレイアウトを推測して接続する機能ではありません。

Win32では`link "kernel32"`等をGSモジュールに記述できるため、利用者のアプリケーションからimportするGSライブラリへOS固有宣言をまとめられます。ウィンドウ構築・描画ライブラリ自体は今回の実装に含めていません。[宣言・コールバック・型の具体例](native.md)
