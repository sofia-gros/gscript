# GS / gscript for VSCode

Go風の構文からJavaScriptを生成するGSの言語サポートです。

## インストール（修正版r2）

1. [Python 3.12以降](https://www.python.org/downloads/)をインストールし、VSCodeを再起動します。
2. [Plugin v0.4.0 修正版r2](https://github.com/sofia-gros/gscript/releases/tag/plugin-v0.4.0-r2)から`gscript-v0.4.0.vsix`を取得します。
3. 拡張機能ビューの「…」→「VSIXからのインストール…」で選び、「Developer: Reload Window」を実行します。
4. プロジェクトのフォルダーを開き、`.gs`または`.gos`を開きます。

言語サーバーはVSIXに同梱しています。PATHに`gs-lsp 0.4.0`がある場合はネイティブ版を使い、なければPython 3.12以降で同梱サーバーを起動します。ネイティブ版があればPythonは不要です。

初版からの更新は同じ言語バージョンのため、CLIでは`code --install-extension ./gscript-v0.4.0.vsix --force`を使います。

## 動作確認

```go
var value int = "wrong"
console.log(value)
```

型不一致が表示され、`"wrong"`を`3`へ修正すると未保存でも診断が消えます。2行目の`value`へマウスを重ねると型が表示されます。

## 起動に失敗した場合

「表示」→「出力」→`GS Language Server`で詳細を確認します。Pythonが見つからない場合は、Python 3.12以降を導入してVSCodeを再起動してください。独自の実行ファイルは`gscript.server.path`で指定できます。パスは絶対パスを使い、設定変更後は再読み込みします。

GSの構文・型検査はGSコンパイラ自身が行います。外部JS/TSの型情報にはNode.js 22/24とプロジェクト内のTypeScript 5.9.3を使います。

シンタックスハイライト、診断、型ホバー、キーワード・トップレベルシンボル補完、アウトラインに対応します。ローカル変数・メンバー補完、定義ジャンプ、リネーム、整形は未提供です。

[OS別設定・詳しいエラー対処](https://github.com/sofia-gros/gscript/blob/main/docs/editors.md)
