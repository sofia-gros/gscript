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

出力は`apps/manager/native/target/release/gscript-manager`（Windowsは`.exe`）です。[Manager v0.6.2 Preview](https://github.com/sofia-gros/gscript/releases/tag/manager-v0.6.2)でActionsビルド済みの配布物を公開します。画面の最終操作テストは利用者の実機で行います。

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
- Zig: 選択先の`zig`へ公式の最新安定版を導入し、チェックサム検証後にCプログラムをビルド・実行して確認します。
- WindowsのGCC: 公式WinGetカタログの最新版ZIPをSHA256検証し、選択先の`gcc`へ展開します。
- WindowsのClang: 同カタログの最新版MSI / NSISインストーラーを検証して、選択先の`clang`へ導入します。UACの許可が必要です。WinGetコマンド自体は不要です。Windows SDK / MSVCランタイムの開発用ライブラリは別途必要です。
- macOSのGCC / Clang: Homebrewのgcc / llvm提供版を使用します。LinuxはAPTカタログの候補版を使用します。これらの保存先はOS側の規則に従います。
- ドキュメント: アプリ本体にMarkdownを埋め込みます。別の場所にも保存したい場合は、ドキュメント画面の「保存先を選んで書き出す」を使います。

### PATH

既定の追加先はユーザーPATHです。WindowsはレジストリのユーザーPATHへ追記し、変更を通知します。システムPATHは別チェックで選択でき、事前に管理者権限でアプリを起動する必要があります。既存の値はユーザーデータ内の`path-backup.json`へ保存します。

Linux/macOSはbashの`.bashrc`、zshの`.zshrc`へ追記します。既存ファイルの横へバックアップを保存し、同じ行の重複追加を避けます。他のシェルは手動設定が必要です。新しいターミナルで反映を確認してください。

### 更新・取得

コンパイラとプラグインのReleaseを区別して取得します。GitHub REST APIが使えない場合は公開Atomフィードへフォールバックします。失敗時はエラーと保存済み情報を表示し、「最新」とは判断しません。配布物は公式ReleaseのSHA256SUMSで検証し、既存バージョンを保持したまま新しいバージョンを配置します。

管理対象コンパイラの配布物は現在Linux x86_64、macOS arm64、Windows x86_64です。ほかのOS/CPUでは対応配布物がない旨を表示します。Clang / GCCはLinuxのpkexec + apt-get、macOSのHomebrew、WindowsではMicrosoft WinGetカタログから取得した配布物を使用します。認証やSDKが必要になる場合があります。

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

`.github/workflows/manager.yml`で3OSのGUIビルド・同梱文書確認・実ダウンロードの確認・配布物作成を行います。画面は開かず、最終の画面操作は利用者の実機で確認します。

## 導入したツールでGSを動かす

インストール後のコマンドは[ネイティブコンパイルと実行](../../../docs/guide/native-build.md)にあります。アプリ内でも「ドキュメント → ネイティブ → ネイティブコンパイルと実行」から同じ内容を参照できます。

## ZedのRuffエラーについて

RuffはPython用の言語サーバーで、GS拡張の依存ではありません。`ruff is not recognized`が出る場合のPythonへの導入・Zedの実行パス設定、使わない場合の無効化は[エディターのトラブルシューティング](../../../docs/editors.md#zedでruffが見つからないと出る場合)を参照してください。VSCode拡張はReleaseのVSIXを取得してインストールします。

## 最新版とダウンロードURL

固定しているのは配布元の情報APIとパッケージ識別子です。個別アーカイブの版・ファイル名・URLは固定しません。

| ツール / OS | バージョン・取得先の情報源 |
| --- | --- |
| Zig | Zig公式download/index.jsonの安定版一覧。master / 開発版を除き、利用環境の最新版のURL・SHA256を読む |
| Windows Clang / GCC | Microsoft winget-pkgs公式カタログのバージョン一覧とinstaller.yaml。CPU・InstallerUrl・InstallerSha256・保存場所を読む |
| macOS Clang / GCC | brew info --json=v2 llvm / gcc。Homebrewが管理する提供版・URLで導入 |
| Linux Clang / GCC | apt-cache madison。OSカタログの候補版を明示して導入。カタログ更新はOSのapt updateを使用 |

画面ではインストール済みと取得可能な最新版を別々に表示します。版を比較できない場合や取得に失敗した場合は「未確認」とし、「最新」とは判定しません。インストール直前に配布情報を再取得し、実際の取得版を進捗に表示します。配布情報の取得にはネットワーク接続が必要です。

Zigの更新時は旧版をzig-backupフォルダーへ退避し、新版の配置失敗時は元へ戻します。GCCの旧版も退避します。LLVMの更新・修復は取得した公式インストーラーが管理します。

GUIを開かずに検出・最新版を確認する場合:

```sh
cargo run --locked --manifest-path apps/manager/native/Cargo.toml -- --toolchains
```

取得・インストールの確認用CLI（PATHは変更しません）:

```sh
gscript-manager --install-toolchain zig --install-dir /absolute/path/to/tools --no-path
```

WindowsではGCCにも使用できます。ClangのMSI等はGUIからUAC許可を含めて導入するか、ダウンロードだけを行えます。

```powershell
.\gscript-manager.exe --download-toolchain clang --download-dir C:\Downloads\gs-tools
```
