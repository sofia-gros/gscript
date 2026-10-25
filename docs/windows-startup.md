# WindowsでEXEのDLL展開に失敗する場合

対象のログ:

```text
[PYI-...:ERROR] Failed to extract VCRUNTIME140.dll: decompression resulted in return code -1!
[PYI-...:ERROR] Failed to extract entry: VCRUNTIME140.dll.
```

これはPyInstaller製EXEの起動処理が、内蔵DLLを展開できず終了したエラーです。GSコンパイラや言語サーバーのPythonコードより前に発生しています。VSCodeの`write EPIPE`、`connection got disposed`、再起動回数超過は、そのプロセス終了に伴う後続エラーです。

GSコンパイラが起動していないため、GSファイルの検査、Zig / GCC / Clangの起動、buildフォルダーと実行ファイルの作成は行われません。このログだけでは、元の配布物・取得後の破損・展開時の環境などのどれが失敗を引き起こしたかまでは判定できません。

## 今すぐコンパイルする：ソースをPythonで起動

このリポジトリを取得済みなら、Python 3.12以降からソースを起動でき、問題の自己展開EXEを通りません。PowerShellでリポジトリのルートを開きます。

```powershell
cd A:\Project\gscript
py -3 --version
py -3 -m gscript --version
py -3 -m gscript hello.gs --backend native --cc zig -o .\build\hello-zig.exe
if ($LASTEXITCODE -eq 0) { & .\build\hello-zig.exe }
```

`A:\Project\gscript`は実際の取得先へ置き換えてください。Pythonが3.12未満なら先に対応版を導入します。`py`がない場合は対応するPython実行ファイルの絶対パスを指定します。

この方法では、PATH上の古い`gs.exe`は使用しません。作成したアプリは通常のネイティブ実行ファイルで、実行にPythonは必要ありません。Zigは別途必要です。Clang / GCCを使う場合は`--cc clang` / `--cc gcc`へ変更します。

リポジトリの外からも実行したい場合は、ソースをPython環境へインストールできます。

```powershell
py -3 -m pip install --user .
```

ただし、PATHの先に古い`gs.exe`が残っていると、`gs`はそちらを起動します。`Get-Command gs -All`で確認するか、`py -3 -m gscript`を明示して呼び出してください。

## VSCode：Python版LSPへ切り替える

まず、リポジトリのルートでPython版LSPを作成します。PyInstallerやNode.jsは不要です。

```powershell
py -3 scripts/build_plugins.py --portable --output dist/windows-repair
```

VSCodeのSettings JSONで、古い`gs-lsp.exe`の指定を次へ変更します。既存の設定へ統合してください。

```json
{
  "gscript.server.path": "py",
  "gscript.server.args": [
    "-3",
    "A:\\Project\\gscript\\dist\\windows-repair\\gs-lsp-v0.6.1.pyz",
    "--stdio"
  ]
}
```

上のファイルは実際のリポジトリの場所に合わせて指定します。設定後は**Developer: Reload Window**を実行します。ワークスペース側に古い設定があるとユーザー設定を上書きするため、両方を確認してください。

すでにPython 3.12以降をZed/VSCodeから起動できる環境なら、VSCodeの`gscript.server.path`を空にし、`gscript.server.args`を`["--stdio"]`へ戻して、VSIXに同梱されたPython版へ自動で切り替えることもできます。旧v0.6.0 VSIXの自動検出は`py -3.12`を最初に試すため、Python 3.13以降だけを使っている場合は上の`py -3`設定を使うと明示的に指定できます。

## Zedで同じEXEを使用している場合

同じPython版LSPを、ZedのSettings JSONで指定できます。

```json
{
  "lsp": {
    "gs-lsp": {
      "binary": {
        "path": "py",
        "arguments": [
          "-3",
          "A:\\Project\\gscript\\dist\\windows-repair\\gs-lsp-v0.6.1.pyz",
          "--stdio"
        ]
      }
    }
  }
}
```

パスを合わせてZedを再起動してください。Ruffのエラーとは別の問題です。

## 修正版Windows EXEをローカルで作る

Windows配布スクリプトを`onefile`から`onedir`へ変更しました。DLLを`_internal`へ同梱し、起動時の一時フォルダーへの自己展開をなくします。**EXEだけを取り出さず、フォルダー全体を移動・配置してください。**

v0.6.1はこのフォルダー形式で配布します。公開済みv0.6.0のEXEや、ユーザーが手動指定した古い保存先は自動では書き換わらないため、新しい配布物へ置き換えてください。[コンパイラ v0.6.1](https://github.com/sofia-gros/gscript/releases/tag/v0.6.1)と[Plugin v0.6.1](https://github.com/sofia-gros/gscript/releases/tag/plugin-v0.6.1)を使用します。

Windowsで必要なPythonビルドツールを導入して作成する場合:

```powershell
py -3 -m venv .venv-windows-build
& .\.venv-windows-build\Scripts\python.exe -m pip install -r requirements-build.txt
npm ci --ignore-scripts
$env:GS_NATIVE_CC = (Get-Command zig.exe -ErrorAction Stop).Source
& .\.venv-windows-build\Scripts\python.exe scripts/build_release.py --native --output dist/windows-repair
& .\.venv-windows-build\Scripts\python.exe scripts/build_plugins.py --native --output dist/windows-repair
```

コンパイラの配布確認にはNode.jsとTypeScriptの依存、ネイティブ出力の確認にはZig等が必要です。上のコマンドはPATH上のZigを使用します。配布時の従来の検証版はZig 0.15.2です。

作成したZIPを**全体として**展開し、`gs.exe`または`gs-lsp.exe`と、隣の`_internal`を一緒に配置します。VSCodeのネイティブ設定へ戻す場合は、新しい`gs-lsp.exe`の絶対パスと`["--stdio"]`を指定します。

修正VSIXをソースから作る場合は、リポジトリのルートで次を実行し、生成したVSIXをVSCodeのInstall from VSIXで選びます。

```powershell
npm ci --prefix editors/vscode
npm run package --prefix editors/vscode
```

出力は`editors/vscode/gscript-0.6.1.vsix`です。この修正では、指定されたネイティブLSPを起動前に確認し、起動できない場合に展開エラーとPython版への切り替え手順を表示します。VSIX単体で、ユーザーが別途指定した旧EXEを書き換えることはありません。
