# Plugin v0.6.1

コンパイラv0.6.1に合わせたVSCode・Zed・GS言語サーバーの修正版です。

- Windowsのgs-lspをフォルダー形式（onedir）へ変更し、起動時のVCRUNTIME140.dll自己展開をなくします。EXEと`_internal`を含むフォルダー全体で配置してください。
- VSCodeは指定されたLSPを起動前に確認し、失敗した場合はstderrとPython版への切り替え方法を表示します。EXEの起動失敗をLSP接続切断のログだけで報告しないようにします。
- WindowsのPython自動検出は`py -3`で候補を探し、実際にPython 3.12以上か確認。3.12だけを固定指定しません。
- VSIXをローカルで再ビルドした際、旧版の同梱LSPを含めないよう整理。
- Zedはgs-lsp 0.6.1を使用し、新しいダウンロード先・キャッシュへ切り替えます。

VSCodeで`gscript.server.path`、Zedで`lsp.gs-lsp.binary.path`に古いEXEを明示している場合は、新しい保存先へ変更してください。VSIX更新だけでは別途指定したEXEは置き換わりません。

[エディター導入](https://github.com/sofia-gros/gscript/blob/plugin-v0.6.1/docs/editors.md) / [Windows起動エラーと復旧](https://github.com/sofia-gros/gscript/blob/plugin-v0.6.1/docs/windows-startup.md)

VSCode用VSIX、Zed開発拡張、3OSのLSP、Python zipapp、拡張のソースとSHA256SUMSを配布します。Zedの開発拡張はZed内で有効化し、画面の最終操作確認は利用者の実機で行います。

## 配布物の確認

[配布ワークフロー](https://github.com/sofia-gros/gscript/actions/runs/40213131299)が成功し、Windows上での起動を含む配布前確認を完了しました。公開ファイルのダウンロード後にもSHA256とWindows ZIP内の`_internal/VCRUNTIME140.dll`を含む構成を確認しています。実機の画面操作は別途利用環境で確認してください。
