# GScript Manager

GPUI 0.2.2 + gpui-component 0.5.1を使うRust製デスクトップアプリです。HTMLやWebViewを表示する構成ではありません。アイコンはgpui-component-assetsに同梱されるLucide SVGを使用します。

## 起動

リポジトリのルートで実行します。初回はRust依存のビルドに時間がかかります。

```sh
cargo run --locked --manifest-path apps/manager/native/Cargo.toml
```

リリースビルド:

```sh
cargo build --locked --release --manifest-path apps/manager/native/Cargo.toml
```

出力は`apps/manager/native/target/release/gscript-manager`（Windowsは`.exe`）です。現時点で管理アプリ自体のGitHub Releaseや自動配布は行いません。

### ビルド環境

- Rust stable、C/C++ビルドツール、Git、依存取得用のネットワーク。
- Windows: MSVC版RustとVisual Studio Build Toolsの「C++によるデスクトップ開発」、Windows SDK。
- macOS: Xcode Command Line Tools。
- Linux: C/C++ツール、pkg-config、Fontconfig / FreeType / xkbcommonの開発用ライブラリ、X11またはWayland、Vulkan対応ドライバー。Debian/Ubuntuの例:

```sh
sudo apt-get install build-essential pkg-config libfontconfig1-dev libfreetype-dev libxkbcommon-dev libxkbcommon-x11-dev libwayland-dev libxcb1-dev libx11-xcb-dev libvulkan-dev fonts-noto-cjk
```

LinuxでGPUを利用できない環境では、対応するMesaのソフトウェアVulkanドライバーが必要です。サーバー向けのGUIなし環境では通常の画面は開けません。実機のウィンドウ・入力・描画はユーザー側で最終確認してください。

## 画面と導入フロー

左サイドバーからコンパイラ・エディター拡張・ツールチェーン・ドキュメントを個別に開きます。

「インストール」→保存先を入力またはフォルダー選択→PATHの追加を設定→「次へ」→ダウンロード・検証・配置→完了です。PATH追加は初期状態でチェック済み。拡張機能にはPATH追加が不要なため表示しません。

処理中は経過時間、受信量、全体の進捗バーと0〜100%を表示します。ダウンロードの受信量は実測し、サイズが取得できない場合は割合を推定しません。ダウンロードが全体の0〜75%、検証・配置等が残りの工程です。100%は処理が成功したときだけ表示します。認証待ちやOSのパッケージ管理による作業中は、外部処理が返るまで進捗が止まる場合があります。

### 保存先

標準はOSのユーザーデータディレクトリ配下です。各ポップアップで変更でき、次回用に保存します。

- コンパイラ: 選択先にバージョン別ディレクトリを作成し、`bin/gs`（Windowsは`bin/gs.cmd`）から起動します。アプリ内ランタイム資源も同じ配布物に含まれます。
- VSCode: 選択先の`vscode-extensions`へ、code CLIでVSIXを導入します。通常のVSCodeの保存先とは別なので、利用時も`code --extensions-dir <選択先>/vscode-extensions`で起動してください。code CLIが必要です。
- Zed: 選択先に開発拡張を配置します。ZedのExtensions → Install Dev Extensionで、配置先内の`gscript-zed`を選択してください。Rust・Git等が必要です。有効化前は「配置済み」と表示し、インストール済みとは扱いません。
- Zig: 選択先の`zig`へ公式0.15.2を導入し、チェックサム検証後にCプログラムをビルド・実行して確認します。
- Clang / GCC: OSのパッケージ管理を使用するため、実体の保存先はOSの規則に従います。任意ディレクトリへの本体配置はZigを選んでください。
- ドキュメント: アプリ本体にMarkdownを埋め込みます。別の場所にも保存したい場合は、ドキュメント画面の「保存先を選んで書き出す」を使います。

### PATH

既定の追加先はユーザーPATHです。WindowsはレジストリのユーザーPATHへ追記し、変更を通知します。システムPATHは別チェックで選択でき、事前に管理者権限でアプリを起動する必要があります。既存の値はユーザーデータ内の`path-backup.json`へ保存します。

Linux/macOSはbashの`.bashrc`、zshの`.zshrc`へ追記します。既存ファイルの横へバックアップを保存し、同じ行の重複追加を避けます。他のシェルは手動設定が必要です。新しいターミナルで反映を確認してください。

### 更新・取得

コンパイラとプラグインのReleaseを区別して取得します。GitHub REST APIが使えない場合は公開Atomフィードへフォールバックします。失敗時はエラーと保存済み情報を表示し、「最新」とは判断しません。配布物は公式ReleaseのSHA256SUMSで検証し、既存バージョンを保持したまま新しいバージョンを配置します。

管理対象コンパイラの配布物は現在Linux x86_64、macOS arm64、Windows x86_64です。ほかのOS/CPUでは対応配布物がない旨を表示します。Clang / GCCはLinuxのpkexec + apt-get、macOSのXcode CLT / Homebrew、Windowsのwingetを使用し、認証やSDKが必要になる場合があります。

## 同梱ドキュメント

`docs/guide/navigation.json`とMarkdownから、Cargoのビルド時に26ページを直接埋め込みます。HTML試作で生成するJSファイルは使用しません。GitHubとアプリで同じ原稿を使用し、ネット接続なしで検索・閲覧できます。章一覧、ページ内目次、前後移動、Go / JS / GS比較の切り替えに対応します。文書内のローカルリンクはアプリの「関連するページ」ボタンとして表示します。

## 補助コマンド

```sh
cargo run --locked --manifest-path apps/manager/native/Cargo.toml -- --self-check
cargo run --locked --manifest-path apps/manager/native/Cargo.toml -- --check-updates
```

`--self-check`は埋め込み文書の存在確認、`--check-updates`は実際の更新確認です。画面を開きません。ネットワーク不要のサービス層テストは次で実行できます。

```sh
cargo test --locked --manifest-path apps/manager/native/Cargo.toml --no-default-features --lib
```

このアプリ用のGitHub Actionsワークフローは追加していません。画面・実機での導入と更新の最終検証は未実施です。

## 導入したツールでGSを動かす

インストール後のコマンドは[ネイティブコンパイルと実行](../../../docs/guide/native-build.md)にあります。アプリ内でも「ドキュメント → ネイティブ → ネイティブコンパイルと実行」から同じ内容を参照できます。
