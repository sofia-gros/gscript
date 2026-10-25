# GScript Manager

## ネイティブアプリ（GPUI + gpui-component）

リポジトリのルートから起動します。

```sh
cargo run --locked --manifest-path apps/manager/native/Cargo.toml
```

ビルド環境・導入先・PATH・実装範囲は[native/README.md](native/README.md)を参照してください。画面と実機の最終動作確認は未実施です。このアプリ用のGitHub Actionsは追加していません。

## HTMLデザイン試作

左サイドバーから「コンパイラ」「エディター拡張」「ツールチェーン」「ドキュメント」を選ぶ管理GUIの試作です。各ページには選んだ機能だけを表示します。

## 開く

リポジトリのルートから:

```sh
python -m http.server 8080 --directory apps/manager
```

http://localhost:8080 を開きます。外部CDN・フォントを必要としません。

## 導入・更新

- コンパイラ、VSCode拡張、Zed拡張の導入状態と配布バージョン
- 更新確認の操作、GitHubリンク、各配布物のリリースノート
- Clang / GCC / Zigの検出と不足時の導入
- WindowsのPATH追加先（ユーザー／システム／追加なし）

現在の検出・導入はデモです。GitHubの最新状態を取得したり、PCを検査・変更したりしません。更新確認ボタンはこの状態を明示します。状態は再読み込みでリセットします。

## 言語ドキュメント

`docs/guide/navigation.json`に定義した25ページを同梱します。言語の実行モデル、基本、文と式、型、ライブラリ連携、ネイティブ仕様、Go・JS・GS比較を扱います。運用記録・開発計画・ベンチマーク・配布操作は文書一覧に含めません。

Vue公式ガイドの段階的な導入・章構成・ページ内目次を参考にしています。左にカテゴリ別の章一覧、右にページ内目次、本文の下に前後ページへのリンクを表示します。Go・JavaScript・GScriptの比較例はタブで切り替えられます。コードにシンタックスハイライトとコピーボタンがあります。

本文はGitHubでも読む同じMarkdownが唯一の原稿です。Markdownから生成するHTML・検索データはアプリへ同梱するため、表示にネットワークや外部CDNは不要です。

全文検索と内部リンクはネット接続なしで動作します。GitHub等への外部リンクには接続が必要です。

文書の更新後は次で再生成します。生成後の閲覧にNode.jsは不要です。

```sh
cd apps/manager
npm ci
npm run docs:bundle
```

## アプリ化

GPUI + gpui-componentの実装は`native/`にあります。`tokens.css`はshadcn/uiに合わせた色の役割・余白・角丸の定義です。HTML自体をGPUIへ読み込む構成ではありません。言語文書も同梱し、Markdownビューへ渡します。

アプリ側に実環境の検査、Release情報の取得、公式配布物のSHA256検証、導入・更新、PATH変更とバックアップを実装しています。OSとSDK、既存ツールチェーン、Zedの開発拡張とVSCodeのVSIXの違いに合わせた導入が必要です。
