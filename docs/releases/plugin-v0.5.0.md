# Plugin v0.5.0

GSコンパイラv0.5.0と同じ型検査を使う言語サーバー、VSCode VSIX、Zed開発拡張を配布します。

定義ジャンプ、参照検索、スコープを区別するリネーム、ローカル・プロパティ補完、Signature Help、GSの自動import候補、未使用変数等のLint診断、フォーマットを追加しました。gsconfig.jsonのstrictNull/libをエディターとCLIで共用し、構文木・型情報キャッシュで再解析を削減します。v0.5構文のハイライトも更新しました。

- VSCode: gscript-v0.5.0.vsix。Python 3.12以降で同梱LSPを実行、またはネイティブgs-lspを指定。
- Zed: gscript-zed-v0.5.0.zip。Rust・Gitを準備しInstall Dev Extensionで導入。WASI2コンポーネントと文法WASMを同梱しますが、公式の開発拡張導入ではローカル再ビルドが必要です。
- ネイティブLSP: Linux x86_64、macOS arm64、Windows x86_64。
- Python版: gs-lsp-v0.5.0.pyz。Python 3.12以降。

[正確なインストール・設定・トラブル対処](https://github.com/sofia-gros/gscript/blob/plugin-v0.5.0/docs/editors.md)

CIは配布VSIXを実際のExtension Hostに読み込んでLSP接続と編集操作を検査します。ZedはRust/WASI2・文法・クエリー・WASMをビルド検査し、LSPは3OSで実行します。Zed GUI導入の自動試験とは区別しています。
