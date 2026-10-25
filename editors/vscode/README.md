# GS / gscript for VSCode

[Plugin v0.6.1](https://github.com/sofia-gros/gscript/releases/tag/plugin-v0.6.1)のgscript-v0.6.1.vsixを取得し、VSCode 1.85以降で「VSIXからのインストール」を選びます。

```sh
code --install-extension ./gscript-v0.6.1.vsix
```

Python 3.12以降で同梱LSPを起動します。PATHにネイティブgs-lsp 0.6.1があればPythonは不要です。設定で実行ファイルの絶対パスも指定できます。

診断・ホバー・定義・参照・リネーム・補完・Signature Help・整形に対応します。gscript.strictNullはnullでgsconfig.jsonへ追従します。

起動エラーは「出力」→「GS Language Server」で確認してください。[OS別導入・設定・対処](https://github.com/sofia-gros/gscript/blob/main/docs/editors.md)。

## WindowsでVCRUNTIME140.dllの展開に失敗する場合

`[PYI-...:ERROR] Failed to extract VCRUNTIME140.dll`は、ネイティブEXEがLSP起動前に終了しているエラーです。`write EPIPE`はその後続エラーです。

Python 3.12以降を導入済みの場合は、VSCodeのSettings JSONで古いEXEの指定を外し、同梱Python版へ切り替えられます。

```json
{
  "gscript.server.path": "",
  "gscript.server.args": ["--stdio"]
}
```

**Developer: Reload Window**で再起動します。ワークスペース設定に古いEXEが残っていないかも確認してください。修正VSIXではWindowsの`py -3`でPython 3を探し、実際のバージョンが3.12以上か確認します。

[コンパイラの復旧・Python版LSPの明示指定・Windows修正版ビルド](https://github.com/sofia-gros/gscript/blob/main/docs/windows-startup.md)も参照してください。公開済みの旧EXEは、VSIXを更新するだけでは置き換わりません。Windowsの修正版はEXEと`_internal`を含むフォルダー全体で配置します。
