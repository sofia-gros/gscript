# GScript Manager v0.6.2 Preview

GPUI + gpui-componentによるネイティブGUIの初回配布です。画面の最終操作確認は利用者の実機で行うプレビュー版として公開します。

- コンパイラ・VSCode拡張・Zed拡張・ツールチェーンを別画面で管理。
- 各ツールのインストール済みバージョン、取得元で利用可能な安定版、ダウンロード版、取得元、更新有無を表示。
- Zigは公式インデックス、WindowsのGCC / ClangはMicrosoftのWinGetカタログから、版・URL・SHA256を実行時に解決。アーカイブURL・バージョンの固定指定はしません。
- WindowsのGCCは検証済みZIPを指定先へ展開。Clangは検証済みMSI等の公式インストーラーから指定先へ導入します。ClangはUAC許可とWindows SDKが必要です。WinGetコマンドの導入は不要です。
- 通信のタイムアウト延長・一時障害時の再取得・SHA256確認・旧版退避と配置失敗時の復元。
- WindowsのPATH更新を子プロセスへ反映し、導入後に自動再検出。PATH設定の失敗時も配置済みのツールを削除しません。
- 同じMarkdownの言語ガイドをアプリに埋め込み、オフライン閲覧・検索・Go / JS / GS比較に対応。

Windows x86_64、macOS arm64、Linux x86_64を配布します。WindowsはZIPを展開してgscript-manager.exeを起動します。macOSはtar.gzを展開してGScript Manager.appを開き、Linuxは同梱バイナリを起動します。配布物は署名・公証をしていないプレビューです。

macOSのGCC / ClangはHomebrew、LinuxはAPTの提供版を使用するため、上流の最新版と提供版が異なる場合があります。取得元を画面に明記し、取得失敗時は「最新版未確認」と表示します。

[起動環境・導入先・PATH・配布元と補助コマンド](https://github.com/sofia-gros/gscript/blob/main/apps/manager/native/README.md)
