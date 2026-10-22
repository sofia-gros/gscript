# GS / gscript for VSCode

[Plugin v0.5.0](https://github.com/sofia-gros/gscript/releases/tag/plugin-v0.5.0)のgscript-v0.5.0.vsixを取得し、VSCode 1.85以降で「VSIXからのインストール」を選びます。

```sh
code --install-extension ./gscript-v0.5.0.vsix
```

Python 3.12以降で同梱LSPを起動します。PATHにネイティブgs-lsp 0.5.0があればPythonは不要です。設定で実行ファイルの絶対パスも指定できます。

診断・ホバー・定義・参照・リネーム・補完・Signature Help・整形に対応します。gscript.strictNullはnullでgsconfig.jsonへ追従します。

起動エラーは「出力」→「GS Language Server」で確認してください。[OS別導入・設定・対処](https://github.com/sofia-gros/gscript/blob/main/docs/editors.md)。
