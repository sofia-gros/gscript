//! OS operations live outside GPUI. No shell interpolation, no background privilege escalation.
use crate::toolchains::{self, ToolchainRelease};
use anyhow::{Context, Result, bail, ensure};
use directories::ProjectDirs;
use reqwest::blocking::Client;
use semver::Version;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::{Read, Write},
    path::{Component, Path, PathBuf},
    process::{Command, Stdio},
    time::Duration,
};
use wait_timeout::ChildExt;
const REPO: &str = "https://github.com/sofia-gros/gscript";
const API: &str = "https://api.github.com/repos/sofia-gros/gscript";
const MAX_DOWNLOAD: u64 = 2 * 1024 * 1024 * 1024;
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Settings {
    pub compiler_dir: PathBuf,
    pub extensions_dir: PathBuf,
    pub toolchains_dir: PathBuf,
    pub docs_dir: PathBuf,
    pub path_scope: PathScope,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize, Default)]
pub enum PathScope {
    None,
    #[default]
    User,
    System,
}
impl Settings {
    pub fn load() -> Result<Self> {
        let root = data_dir()?;
        let path = root.join("settings.json");
        if path.exists() {
            Ok(serde_json::from_slice(&fs::read(path)?)?)
        } else {
            Ok(Self {
                compiler_dir: root.join("compiler"),
                extensions_dir: root.join("extensions"),
                toolchains_dir: root.join("toolchains"),
                docs_dir: root.join("docs"),
                path_scope: PathScope::User,
            })
        }
    }
    pub fn save(&self) -> Result<()> {
        let root = data_dir()?;
        fs::create_dir_all(&root)?;
        atomic_json(&root.join("settings.json"), self)
    }
}
pub fn data_dir() -> Result<PathBuf> {
    Ok(ProjectDirs::from("dev", "GScript", "GScript Manager")
        .context("ユーザーデータディレクトリを取得できません")?
        .data_local_dir()
        .to_path_buf())
}
fn atomic_json<T: Serialize>(path: &Path, value: &T) -> Result<()> {
    let mut temp =
        tempfile::NamedTempFile::new_in(path.parent().context("保存先の親がありません")?)?;
    serde_json::to_writer_pretty(&mut temp, value)?;
    temp.flush()?;
    temp.persist(path).map_err(|e| e.error)?;
    Ok(())
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Release {
    pub version: String,
    pub tag: String,
    pub notes: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Releases {
    pub compiler: Release,
    pub plugins: Release,
}
impl Default for Releases {
    fn default() -> Self {
        Self {
            compiler: Release {
                version: "0.6.1".into(),
                tag: "v0.6.1".into(),
                notes: include_str!("../../../../docs/releases/v0.6.1.md").into(),
            },
            plugins: Release {
                version: "0.6.1".into(),
                tag: "plugin-v0.6.1".into(),
                notes: include_str!("../../../../docs/releases/plugin-v0.6.1.md").into(),
            },
        }
    }
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Installed {
    pub product: String,
    pub version: String,
    pub location: PathBuf,
    pub executable: Option<PathBuf>,
    pub prepared: bool,
}
#[derive(Clone, Debug, Serialize)]
pub struct Toolchain {
    pub name: String,
    pub executable: Option<PathBuf>,
    pub version: String,
    pub usable: bool,
    pub latest_version: Option<String>,
    pub download_version: Option<String>,
    pub provider: Option<String>,
    pub update_available: Option<bool>,
    pub lookup_error: Option<String>,
}
#[derive(Clone, Debug)]
pub struct Progress {
    pub message: String,
    pub percent: f32,
}
impl From<&str> for Progress {
    fn from(message: &str) -> Self {
        let percent = if message.starts_with("検証した") {
            85.0
        } else if message.starts_with("VSCode") {
            90.0
        } else {
            0.0
        };
        Self {
            message: message.into(),
            percent,
        }
    }
}
#[derive(Clone)]
pub struct Service {
    client: Client,
}
impl Service {
    pub fn new() -> Result<Self> {
        Ok(Self {
            client: Client::builder()
                .user_agent(concat!("GScript-Manager/", env!("CARGO_PKG_VERSION")))
                .connect_timeout(Duration::from_secs(15))
                .timeout(Duration::from_secs(15 * 60))
                .build()?,
        })
    }
    pub fn cached_releases(&self) -> Releases {
        data_dir()
            .ok()
            .and_then(|r| fs::read(r.join("releases.json")).ok())
            .and_then(|b| serde_json::from_slice(&b).ok())
            .unwrap_or_default()
    }
    pub fn check_updates(&self) -> Result<Releases> {
        let mut releases = self.api_releases().or_else(|_| self.feed_releases())?;
        for release in [&mut releases.compiler, &mut releases.plugins] {
            if release.notes.is_empty() {
                let name = if release.tag.starts_with("plugin-") {
                    format!("plugin-v{}.md", release.version)
                } else {
                    format!("v{}.md", release.version)
                };
                let url = format!(
                    "https://raw.githubusercontent.com/sofia-gros/gscript/{}/docs/releases/{}",
                    release.tag, name
                );
                release.notes=self.text(&url,1024*1024).unwrap_or_else(|_|format!("# {}\n\nリリースノートを取得できませんでした。[GitHubで確認]({}/releases/tag/{})してください。",release.tag,REPO,release.tag));
            }
        }
        let root = data_dir()?;
        fs::create_dir_all(&root)?;
        atomic_json(&root.join("releases.json"), &releases)?;
        Ok(releases)
    }
    fn api_releases(&self) -> Result<Releases> {
        let json: serde_json::Value = serde_json::from_str(
            &self.text(&format!("{API}/releases?per_page=100"), 8 * 1024 * 1024)?,
        )?;
        let list = json.as_array().context("Release一覧の形式が不正です")?;
        let mut compiler = None;
        let mut plugins = None;
        for item in list {
            if item["draft"].as_bool() == Some(true) || item["prerelease"].as_bool() == Some(true) {
                continue;
            }
            if let Some(tag) = item["tag_name"].as_str() {
                insert_release(
                    tag,
                    item["body"].as_str().unwrap_or(""),
                    &mut compiler,
                    &mut plugins,
                );
            }
        }
        Ok(Releases {
            compiler: compiler.context("コンパイラReleaseがありません")?,
            plugins: plugins.context("Plugin Releaseがありません")?,
        })
    }
    fn feed_releases(&self) -> Result<Releases> {
        let xml = self.text(&format!("{REPO}/releases.atom"), 4 * 1024 * 1024)?;
        parse_feed(&xml)
    }
    fn text(&self, url: &str, limit: u64) -> Result<String> {
        let response = self
            .client
            .get(url)
            .timeout(Duration::from_secs(30))
            .send()
            .with_context(|| format!("配布情報への接続に失敗しました: {url}"))?
            .error_for_status()
            .with_context(|| format!("配布情報を取得できません: {url}"))?;
        let mut text = String::new();
        response.take(limit + 1).read_to_string(&mut text)?;
        ensure!(text.len() as u64 <= limit, "応答が大きすぎます");
        Ok(text)
    }
    fn download(
        &self,
        url: &str,
        destination: &Path,
        expected: &str,
        progress: &impl Fn(Progress),
    ) -> Result<()> {
        for attempt in 0..3 {
            match self.download_once(url, destination, expected, progress) {
                Ok(()) => return Ok(()),
                Err(error) => {
                    let transient = error.chain().any(|cause| {
                        cause.downcast_ref::<reqwest::Error>().is_some_and(|e| {
                            e.is_timeout()
                                || e.is_connect()
                                || e.status()
                                    .is_some_and(|s| s.is_server_error() || s.as_u16() == 429)
                        }) || cause.downcast_ref::<std::io::Error>().is_some_and(|e| {
                            matches!(
                                e.kind(),
                                std::io::ErrorKind::TimedOut
                                    | std::io::ErrorKind::ConnectionReset
                                    | std::io::ErrorKind::UnexpectedEof
                                    | std::io::ErrorKind::ConnectionAborted
                            )
                        })
                    });
                    if !transient || attempt == 2 {
                        let _ = fs::remove_file(destination);
                        return Err(error);
                    }
                    progress(Progress {
                        message: format!(
                            "通信が中断したため再取得します（{}/3）: {url}",
                            attempt + 2
                        ),
                        percent: 0.0,
                    });
                    std::thread::sleep(Duration::from_secs(attempt + 1));
                }
            }
        }
        unreachable!()
    }
    fn download_once(
        &self,
        url: &str,
        destination: &Path,
        expected: &str,
        progress: &impl Fn(Progress),
    ) -> Result<()> {
        ensure!(
            expected.len() == 64 && expected.bytes().all(|b| b.is_ascii_hexdigit()),
            "SHA256が不正です"
        );
        let mut response = self
            .client
            .get(url)
            .send()
            .with_context(|| format!("ダウンロード先へ接続できません: {url}"))?
            .error_for_status()
            .with_context(|| format!("ダウンロード先がエラーを返しました: {url}"))?;
        if let Some(size) = response.content_length() {
            ensure!(size <= MAX_DOWNLOAD, "配布物が大きすぎます");
        }
        let expected_size = response.content_length();
        let mut last_report = std::time::Instant::now();
        let mut file = fs::File::create(destination)?;
        let mut digest = Sha256::new();
        let mut buffer = [0u8; 64 * 1024];
        let mut total = 0;
        loop {
            let n = response.read(&mut buffer).with_context(|| {
                format!("ダウンロード受信が中断しました: {url}（受信済み {total} bytes）")
            })?;
            if n == 0 {
                break;
            }
            total += n as u64;
            ensure!(total <= MAX_DOWNLOAD, "配布物が大きすぎます");
            digest.update(&buffer[..n]);
            file.write_all(&buffer[..n])?;
            if last_report.elapsed() > Duration::from_millis(100) {
                let fraction = expected_size
                    .filter(|s| *s > 0)
                    .map(|size| total as f32 / size as f32)
                    .unwrap_or(0.0);
                progress(Progress {
                    message: format!(
                        "ダウンロード中: {:.1} MB{}",
                        total as f64 / 1048576.0,
                        expected_size
                            .map(|size| format!(" / {:.1} MB", size as f64 / 1048576.0))
                            .unwrap_or_default()
                    ),
                    percent: (fraction * 75.0).min(75.0),
                });
                last_report = std::time::Instant::now();
            }
        }
        file.sync_all()?;
        progress(Progress {
            message: "SHA256を検証しています…".into(),
            percent: 76.0,
        });
        ensure!(
            format!("{:x}", digest.finalize()).eq_ignore_ascii_case(expected),
            "SHA256が一致しません。導入を中止しました"
        );
        Ok(())
    }
    pub fn records(&self, settings: &Settings) -> Vec<Installed> {
        [
            &settings.compiler_dir,
            &settings.extensions_dir,
            &settings.toolchains_dir,
        ]
        .into_iter()
        .flat_map(|root| {
            fs::read_dir(root)
                .into_iter()
                .flatten()
                .filter_map(|e| e.ok())
                .filter_map(|e| fs::read(e.path().join("gscript-install.json")).ok())
                .filter_map(|data| serde_json::from_slice::<Installed>(&data).ok())
        })
        .filter(|record| {
            record.location.is_dir() && record.executable.as_ref().is_none_or(|path| path.is_file())
        })
        .collect()
    }
    pub fn install(
        &self,
        product: &str,
        release: &Release,
        settings: &Settings,
        progress: &impl Fn(Progress),
    ) -> Result<Installed> {
        let version = Version::parse(&release.version)?;
        ensure!(version.pre.is_empty(), "安定版のみ導入できます");
        ensure!(
            release.tag
                == if product == "compiler" {
                    format!("v{version}")
                } else {
                    format!("plugin-v{version}")
                },
            "Releaseタグが不正です"
        );
        ensure!(
            ["compiler", "vscode", "zed"].contains(&product),
            "不明な製品です"
        );
        let platform = platform()?;
        let name = match product {
            "compiler" => format!("gs-v{version}-{platform}.{}", archive_extension()),
            "vscode" => format!("gscript-v{version}.vsix"),
            _ => format!("gscript-zed-v{version}.zip"),
        };
        let root = if product == "compiler" {
            &settings.compiler_dir
        } else {
            &settings.extensions_dir
        };
        validate_destination(root)?;
        fs::create_dir_all(root)?;
        let destination = root.join(format!("{product}-{version}"));
        ensure!(
            !destination.exists(),
            "同じバージョンが既にあります。既存の導入先は変更しません: {}",
            destination.display()
        );
        let stage = tempfile::Builder::new()
            .prefix(".gscript-download-")
            .tempdir_in(root)?;
        progress(Progress {
            message: format!("{name}を取得しています…"),
            percent: 0.0,
        });
        let base = format!("{REPO}/releases/download/{}", release.tag);
        let sums = self.text(&format!("{base}/SHA256SUMS"), 1024 * 1024)?;
        let hash = checksum_for(&sums, &name)?;
        let archive = stage.path().join(&name);
        self.download(&format!("{base}/{name}"), &archive, &hash, progress)?;
        let content = stage.path().join("content");
        fs::create_dir(&content)?;
        let mut executable = None;
        if product == "vscode" {
            fs::rename(&archive, content.join(&name))?;
        } else {
            extract(&archive, &content)?;
            if product == "compiler" {
                let exe = content
                    .join(format!("gs-v{version}-{platform}"))
                    .join(exe_name("gs"));
                ensure!(exe.is_file(), "配布物にコンパイラがありません");
                set_executable(&exe)?;
                let output = run(&exe, ["--version"], Duration::from_secs(20))?;
                ensure!(
                    output.contains(&version.to_string()),
                    "コンパイラのバージョンを確認できません"
                );
                executable = Some(exe.strip_prefix(&content)?.to_path_buf());
            }
        }
        progress("検証したファイルを配置しています…".into());
        fs::rename(&content, &destination)?;
        let result = (|| {
            let exe = executable.map(|p| destination.join(p));
            let record = Installed {
                product: product.into(),
                version: version.to_string(),
                location: destination.clone(),
                executable: exe.clone(),
                prepared: product == "zed",
            };
            if product == "vscode" {
                let code=find_executable("code").context("VSCodeのcodeコマンドがありません。先にVSCodeを導入し、codeコマンドを有効にしてください")?;
                let dir = settings.extensions_dir.join("vscode-extensions");
                let package = destination.join(&name);
                progress("VSCodeへ拡張を導入しています…".into());
                run(
                    &code,
                    [
                        "--extensions-dir".as_ref(),
                        dir.as_os_str(),
                        "--install-extension".as_ref(),
                        package.as_os_str(),
                        "--force".as_ref(),
                    ],
                    Duration::from_secs(180),
                )?;
            }
            atomic_json(&destination.join("gscript-install.json"), &record)?;
            if let Some(exe) = exe {
                let bin = root.join("bin");
                fs::create_dir_all(&bin)?;
                configure_path(&bin, settings.path_scope)?;
                create_launcher(&bin, "gs", &exe)?;
            }
            Ok(record)
        })();
        // Remove only the newly created, manager-owned candidate on failure; previous versions remain intact.
        if result.is_err() {
            let _ = fs::remove_dir_all(&destination);
        }
        result
    }
    pub fn export_docs(&self, settings: &Settings) -> Result<PathBuf> {
        validate_destination(&settings.docs_dir)?;
        fs::create_dir_all(&settings.docs_dir)?;
        for doc in crate::docs::chapters() {
            fs::write(settings.docs_dir.join(doc.id), doc.source)?;
        }
        Ok(settings.docs_dir.clone())
    }
    fn inspect_toolchain(&self, name: &str, settings: &Settings) -> Toolchain {
        let managed = settings.toolchains_dir.join(name);
        let candidates = [
            managed.join(exe_name(name)),
            managed.join("bin").join(exe_name(name)),
            managed.join("mingw64/bin").join(exe_name(name)),
            managed.join("mingw32/bin").join(exe_name(name)),
        ];
        let executable = candidates
            .into_iter()
            .find(|p| p.is_file())
            .or_else(|| find_executable(name));
        let mut version = "未検出".to_string();
        let mut usable = false;
        if let Some(exe) = &executable {
            match run(
                exe,
                [if name == "zig" {
                    "version"
                } else {
                    "--version"
                }],
                Duration::from_secs(10),
            ) {
                Ok(text) => {
                    version = text.lines().next().unwrap_or("検出済み").into();
                    usable = probe_compiler(exe, name).is_ok();
                }
                Err(error) => version = format!("起動失敗: {error:#}"),
            }
        }
        Toolchain {
            name: name.into(),
            executable,
            version,
            usable,
            latest_version: None,
            download_version: None,
            provider: None,
            update_available: None,
            lookup_error: None,
        }
    }
    pub fn latest_toolchain(&self, name: &str) -> Result<ToolchainRelease> {
        if name == "zig" {
            let json = self.text("https://ziglang.org/download/index.json", 8 * 1024 * 1024)?;
            return toolchains::zig_release(
                &json,
                zig_target(std::env::consts::ARCH, std::env::consts::OS)?,
            );
        }
        ensure!(["clang", "gcc"].contains(&name), "不明なツールチェーンです");
        #[cfg(windows)]
        {
            let path = toolchains::manifest_path(name)?;
            let version=self.text(&format!("https://api.github.com/repos/microsoft/winget-pkgs/contents/manifests/{path}"),4*1024*1024)
                .and_then(|body|toolchains::github_catalog_versions(&body))
                .or_else(|_|self.text(&format!("https://github.com/microsoft/winget-pkgs/tree/master/manifests/{path}"),4*1024*1024).and_then(|body|toolchains::github_catalog_versions(&body)))?;
            let id = toolchains::package_id(name)?;
            let manifest=self.text(&format!("https://raw.githubusercontent.com/microsoft/winget-pkgs/master/manifests/{path}/{version}/{id}.installer.yaml"),2*1024*1024)?;
            let release = toolchains::windows_manifest(&manifest, name, std::env::consts::ARCH)?;
            ensure!(
                release.version == version,
                "カタログとマニフェストの版が一致しません"
            );
            return Ok(release);
        }
        #[cfg(target_os = "macos")]
        {
            let brew =
                find_executable("brew").context("最新版の配布情報確認にはHomebrewが必要です")?;
            let formula = if name == "clang" { "llvm" } else { "gcc" };
            return toolchains::brew_release(
                &run(
                    &brew,
                    ["info", "--json=v2", formula],
                    Duration::from_secs(120),
                )?,
                name,
            );
        }
        #[cfg(target_os = "linux")]
        {
            let apt =
                find_executable("apt-cache").context("このOSのAPTカタログを取得できません")?;
            return toolchains::apt_release(
                &run(&apt, ["madison", name], Duration::from_secs(30))?,
                name,
            );
        }
        #[allow(unreachable_code)]
        Err(anyhow::anyhow!("このOSの配布元を確認できません"))
    }
    pub fn detect_toolchains(&self, settings: &Settings) -> Vec<Toolchain> {
        std::thread::scope(|scope| {
            let handles: Vec<_> = ["clang", "gcc", "zig"]
                .into_iter()
                .map(|name| {
                    scope.spawn(move || {
                        let mut tool = self.inspect_toolchain(name, settings);
                        match self.latest_toolchain(name) {
                            Ok(release) => {
                                let available = release.tool_version();
                                tool.update_available =
                                    toolchains::installed_version(name, &tool.version)
                                        .and_then(|v| toolchains::newer_version(&v, &available));
                                tool.latest_version = Some(available);
                                tool.download_version = Some(release.version);
                                tool.provider = Some(release.source);
                            }
                            Err(error) => tool.lookup_error = Some(format!("{error:#}")),
                        }
                        tool
                    })
                })
                .collect();
            handles
                .into_iter()
                .map(|h| h.join().expect("toolchain inspection worker"))
                .collect()
        })
    }
    pub fn install_toolchain(
        &self,
        name: &str,
        settings: &Settings,
        progress: &impl Fn(Progress),
    ) -> Result<String> {
        if name == "zig" {
            return self.install_zig(settings, progress);
        }
        ensure!(["clang", "gcc"].contains(&name), "不明なツールチェーンです");
        let release = self
            .latest_toolchain(name)
            .context("インストール対象の最新版を確認できませんでした")?;
        let current = self.inspect_toolchain(name, settings);
        let managed = current
            .executable
            .as_ref()
            .is_some_and(|p| p.starts_with(settings.toolchains_dir.join(name)));
        if current.usable
            && (!cfg!(windows) || managed)
            && toolchains::installed_version(name, &current.version)
                .and_then(|v| toolchains::newer_version(&v, &release.tool_version()))
                == Some(false)
        {
            return Ok(format!(
                "{name}は使用可能な版です。{} / 配布元: {}",
                current.version, release.source
            ));
        }
        progress(Progress {
            message: format!(
                "{} v{}を取得・導入します（{}）",
                name, release.version, release.source
            ),
            percent: 0.0,
        });
        #[cfg(windows)]
        {
            return self.install_windows_toolchain(name, &release, settings, progress);
        }
        #[cfg(not(windows))]
        {
            progress(
                "OSのパッケージ管理ツールを起動しています。認証画面が表示される場合があります。"
                    .into(),
            );
            let installed = install_system_compiler(name, &release);
            installed.with_context(|| format!("{name}の導入処理に失敗しました"))?;
            let inspected = self.inspect_toolchain(name, settings);
            let tool = inspected.executable.is_some().then_some(inspected);
            if let Some(tool) = tool {
                if tool.usable {
                    let actual = toolchains::installed_version(name, &tool.version)
                        .context("導入後のコンパイラのバージョンを確認できません")?;
                    ensure!(
                        toolchains::newer_version(&actual, &release.tool_version()) == Some(false),
                        "導入後の版が取得対象より古いままです: {actual} / 対象 {}",
                        release.version
                    );
                    return Ok(format!(
                        "{name}を導入し、Cプログラムのビルド・実行を確認しました。{}",
                        tool.version
                    ));
                }
                return Ok(format!(
                    "{name}の導入は完了しましたが、SDK / ライブラリを含むビルド検証は未完了です。{}\n実行ファイル: {}",
                    tool.version,
                    tool.executable.unwrap().display()
                ));
            }
            bail!(
                "導入処理は終了しましたが{name}を検出できません。パッケージ管理ツールの出力とインストール先を確認してください。"
            )
        }
    }
    #[cfg(windows)]
    fn install_windows_toolchain(
        &self,
        name: &str,
        release: &ToolchainRelease,
        settings: &Settings,
        progress: &impl Fn(Progress),
    ) -> Result<String> {
        validate_destination(&settings.toolchains_dir)?;
        fs::create_dir_all(&settings.toolchains_dir)?;
        let stage = tempfile::Builder::new()
            .prefix(".gscript-tool-")
            .tempdir_in(&settings.toolchains_dir)?;
        let url = release
            .url
            .as_deref()
            .context("配布マニフェストにURLがありません")?;
        let hash = release
            .sha256
            .as_deref()
            .context("配布マニフェストにSHA256がありません")?;
        let parsed = reqwest::Url::parse(url)?;
        let filename = parsed
            .path_segments()
            .and_then(|p| p.last())
            .filter(|p| !p.is_empty())
            .context("取得ファイル名が不明です")?;
        ensure!(safe_entry(Path::new(filename)), "取得ファイル名が不正です");
        let archive = stage.path().join(filename);
        self.download(url, &archive, hash, progress)?;
        let destination = settings.toolchains_dir.join(name);
        let executable = if release.installer_type.as_deref() == Some("zip") {
            progress(Progress {
                message: format!("{name}を展開しています…"),
                percent: 80.0,
            });
            let content = stage.path().join("content");
            fs::create_dir(&content)?;
            extract(&archive, &content)?;
            let relative = release
                .executable
                .as_deref()
                .context("配布マニフェストにコンパイラの保存場所がありません")?;
            ensure!(
                safe_entry(Path::new(relative)),
                "配布マニフェストの保存場所が不正です"
            );
            let candidate = content.join(relative);
            ensure!(candidate.is_file(), "展開したコンパイラがありません");
            probe_compiler(&candidate, name)
                .context("取得したコンパイラのCビルド確認に失敗しました")?;
            promote_toolchain_named(&content, &destination, name)?;
            destination.join(relative)
        } else {
            progress(Progress {
                message: "検証済みインストーラーを実行します。WindowsのUACで許可してください。"
                    .into(),
                percent: 85.0,
            });
            install_windows_package(&archive, &destination, release)?;
            let exe = destination.join("bin").join(exe_name(name));
            ensure!(
                exe.is_file(),
                "インストーラー完了後の実行ファイルが見つかりません"
            );
            exe
        };
        let output = run(&executable, ["--version"], Duration::from_secs(15))?;
        let actual = toolchains::installed_version(name, &output)
            .context("導入したコンパイラの版を確認できません")?;
        ensure!(
            actual == release.tool_version(),
            "導入されたバージョンが配布情報と一致しません"
        );
        let bin = executable
            .parent()
            .context("コンパイラの保存先が不明です")?;
        configure_path(bin, settings.path_scope).with_context(|| {
            format!(
                "導入は完了しましたがPATH設定に失敗しました: {}",
                bin.display()
            )
        })?;
        let usable = probe_compiler(&executable, name).is_ok();
        Ok(format!(
            "{name} v{actual}の導入が完了しました。\n保存先: {}\nCビルド確認: {}",
            executable.display(),
            if usable {
                "成功"
            } else {
                "SDK / ライブラリを確認してください（導入済み）"
            }
        ))
    }
    pub fn download_toolchain(
        &self,
        name: &str,
        directory: &Path,
        progress: &impl Fn(Progress),
    ) -> Result<PathBuf> {
        validate_destination(directory)?;
        fs::create_dir_all(directory)?;
        let release = self.latest_toolchain(name)?;
        let url = release
            .url
            .as_deref()
            .context("この取得元はOSのパッケージ管理を使用します")?;
        let hash = release
            .sha256
            .as_deref()
            .context("配布情報にSHA256がありません")?;
        let parsed = reqwest::Url::parse(url)?;
        let filename = parsed
            .path_segments()
            .and_then(|s| s.last())
            .filter(|s| !s.is_empty())
            .context("配布ファイル名がありません")?;
        ensure!(safe_entry(Path::new(filename)), "配布ファイル名が不正です");
        let destination = directory.join(filename);
        ensure!(
            !destination.exists(),
            "同名ファイルが既にあります: {}",
            destination.display()
        );
        progress(Progress {
            message: format!("{} v{} / {}", name, release.version, release.source),
            percent: 0.0,
        });
        self.download(url, &destination, hash, progress)?;
        Ok(destination)
    }
    fn install_zig(&self, settings: &Settings, progress: &impl Fn(Progress)) -> Result<String> {
        progress("Zig公式の最新版を確認しています…".into());
        let release = self
            .latest_toolchain("zig")
            .context("Zig公式から最新版を確認できませんでした")?;
        let version = release.version.as_str();
        let url = release
            .url
            .as_deref()
            .context("Zig最新版の取得先がありません")?;
        let hash = release
            .sha256
            .as_deref()
            .context("Zig最新版にSHA256がありません")?;
        progress(Progress {
            message: format!("Zig v{version}を取得します（{}）", release.source),
            percent: 0.0,
        });
        validate_destination(&settings.toolchains_dir)?;
        fs::create_dir_all(&settings.toolchains_dir)?;
        let destination = settings.toolchains_dir.join("zig");
        let mut previous_version = None;
        if destination.exists() {
            let exe = destination.join(exe_name("zig"));
            let current = run(&exe, ["version"], Duration::from_secs(15)).context(
                "Zigの保存先が存在しますが起動できません。既存フォルダーは自動削除しません",
            )?;
            let current = current.trim();
            Version::parse(current).context("配置済みZigのバージョンを確認できません")?;
            if toolchains::newer_version(current, &release.version) == Some(false) {
                probe_compiler(&exe, "zig").context("配置済みZigのCビルド確認に失敗しました")?;
                configure_path(&destination, settings.path_scope).with_context(|| {
                    format!(
                        "Zigは配置済みですがPATH設定に失敗しました: {}",
                        destination.display()
                    )
                })?;
                return Ok(format!(
                    "Zig v{current}は利用可能な最新版以上です。保存先: {}",
                    destination.display()
                ));
            }
            previous_version = Some(current.to_string());
        }
        let stage = tempfile::Builder::new()
            .prefix(".gscript-zig-")
            .tempdir_in(&settings.toolchains_dir)?;
        let archive = stage.path().join(
            url.rsplit('/')
                .next()
                .context("Zigのファイル名がありません")?,
        );
        progress("Zigを取得しています…".into());
        self.download(url, &archive, hash, progress)?;
        progress(Progress {
            message: "Zigを展開しています…".into(),
            percent: 80.0,
        });
        let out = stage.path().join("content");
        fs::create_dir(&out)?;
        extract(&archive, &out).context("Zigのアーカイブを展開できませんでした")?;
        let folder = fs::read_dir(&out)?
            .filter_map(|e| e.ok())
            .find(|e| e.path().join(exe_name("zig")).is_file())
            .context("Zigの実行ファイルがありません")?
            .path();
        let exe = folder.join(exe_name("zig"));
        set_executable(&exe)?;
        progress(Progress {
            message: "ZigでCプログラムをビルド・実行しています…".into(),
            percent: 90.0,
        });
        probe_compiler(&exe, "zig").context("Zigの受信・展開後のCビルド確認に失敗しました")?;
        let actual = run(&exe, ["version"], Duration::from_secs(15))?;
        ensure!(
            actual.trim() == release.version,
            "取得したZigのバージョンが配布情報と一致しません"
        );
        promote_toolchain(&folder, &destination, previous_version.as_deref())?;
        // A PATH failure must not discard a successfully downloaded and verified compiler.
        configure_path(&destination,settings.path_scope).with_context(||format!("Zigの配置は完了しましたがPATHの設定に失敗しました。保存先: {}。PATH追加を外して再実行するか手動で設定してください",destination.display()))?;
        Ok(format!(
            "Zig v{}を導入しました: {}",
            release.version,
            destination.display()
        ))
    }
}
#[cfg(windows)]
fn promote_toolchain_named(staged: &Path, destination: &Path, name: &str) -> Result<()> {
    let backup = if destination.exists() {
        let stamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)?
            .as_nanos();
        let backup = destination.with_file_name(format!("{name}-backup-{stamp}"));
        fs::rename(destination, &backup)?;
        Some(backup)
    } else {
        None
    };
    if let Err(error) = fs::rename(staged, destination) {
        if let Some(backup) = backup {
            fs::rename(backup, destination)?;
        }
        return Err(error.into());
    }
    Ok(())
}
#[cfg(windows)]
fn install_windows_package(
    package: &Path,
    destination: &Path,
    release: &ToolchainRelease,
) -> Result<()> {
    let path = package.to_string_lossy();
    let root = destination.to_string_lossy();
    ensure!(
        !path.contains('"') && !root.contains('"'),
        "保存先に引用符は使えません"
    );
    let (program, parameters) = if package
        .extension()
        .is_some_and(|s| s.to_string_lossy().eq_ignore_ascii_case("msi"))
    {
        let template = release
            .install_location
            .as_deref()
            .context("MSIの保存先プロパティが取得できません")?;
        let property = template
            .split('=')
            .next()
            .context("MSIの保存先指定が不正です")?;
        ensure!(
            !property.is_empty()
                && property
                    .bytes()
                    .all(|c| c.is_ascii_alphanumeric() || c == b'_'),
            "MSIの保存先プロパティが不正です"
        );
        (
            "msiexec.exe".to_string(),
            format!("/i \"{path}\" /qn /norestart \"{property}={root}\""),
        )
    } else if release.installer_type.as_deref() == Some("nullsoft") {
        (path.to_string(), format!("/S /D={root}"))
    } else {
        bail!("このインストーラー形式は未対応です。導入は行いません")
    };
    run_elevated(&program, &parameters)
}
#[cfg(windows)]
fn run_elevated(program: &str, parameters: &str) -> Result<()> {
    use windows_sys::Win32::{
        Foundation::*,
        System::Threading::*,
        UI::{Shell::*, WindowsAndMessaging::SW_HIDE},
    };
    let wide = |s: &str| s.encode_utf16().chain(Some(0)).collect::<Vec<u16>>();
    let file = wide(program);
    let args = wide(parameters);
    let verb = wide("runas");
    unsafe {
        let mut info: SHELLEXECUTEINFOW = std::mem::zeroed();
        info.cbSize = std::mem::size_of::<SHELLEXECUTEINFOW>() as u32;
        info.fMask = SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NOASYNC;
        info.lpVerb = verb.as_ptr();
        info.lpFile = file.as_ptr();
        info.lpParameters = args.as_ptr();
        info.nShow = SW_HIDE;
        ensure!(
            ShellExecuteExW(&mut info) != 0,
            "インストーラーを開始できませんでした（UACキャンセル等）: {}",
            std::io::Error::last_os_error()
        );
        let status = WaitForSingleObject(info.hProcess, 1800 * 1000);
        let mut code = 0;
        let success = GetExitCodeProcess(info.hProcess, &mut code);
        CloseHandle(info.hProcess);
        ensure!(
            status == WAIT_OBJECT_0 && success != 0,
            "インストーラーの完了を確認できません。進行中の場合は終了後に再検出してください"
        );
        ensure!(
            code == 0 || code == 3010,
            "インストーラーが終了コード{code}で失敗しました"
        );
    }
    Ok(())
}
fn promote_toolchain(
    staged: &Path,
    destination: &Path,
    previous_version: Option<&str>,
) -> Result<()> {
    let backup = if let Some(version) = previous_version {
        let version = Version::parse(version)?;
        let stamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)?
            .as_nanos();
        let backup = destination.with_file_name(format!("zig-backup-{version}-{stamp}"));
        fs::rename(destination, &backup)
            .context("旧版Zigの退避に失敗しました。実行中のZigがあれば終了してください")?;
        Some(backup)
    } else {
        None
    };
    if let Err(error) = fs::rename(staged, destination) {
        if let Some(backup) = backup {
            fs::rename(&backup, destination).context(
                "配置に失敗し、旧版の復元も失敗しました。zig-backupフォルダーを確認してください",
            )?;
        }
        return Err(error).context("新しいZigの配置に失敗しました。旧版は復元しました");
    }
    Ok(())
}
fn insert_release(
    tag: &str,
    notes: &str,
    compiler: &mut Option<Release>,
    plugins: &mut Option<Release>,
) {
    let (is_plugin, raw) = if let Some(v) = tag.strip_prefix("plugin-v") {
        (true, v)
    } else if let Some(v) = tag.strip_prefix('v') {
        (false, v)
    } else {
        return;
    };
    let Ok(version) = Version::parse(raw) else {
        return;
    };
    if !version.pre.is_empty() {
        return;
    }
    let slot = if is_plugin { plugins } else { compiler };
    if slot
        .as_ref()
        .and_then(|r| Version::parse(&r.version).ok())
        .is_none_or(|current| version > current)
    {
        *slot = Some(Release {
            version: version.to_string(),
            tag: tag.into(),
            notes: notes.into(),
        });
    }
}
pub fn parse_feed(xml: &str) -> Result<Releases> {
    let doc = roxmltree::Document::parse(xml)?;
    let mut compiler = None;
    let mut plugins = None;
    for node in doc.descendants().filter(|n| n.has_tag_name("link")) {
        if let Some(url) = node.attribute("href") {
            if let Some(tag) = url.strip_prefix(&format!("{REPO}/releases/tag/")) {
                insert_release(tag, "", &mut compiler, &mut plugins);
            }
        }
    }
    Ok(Releases {
        compiler: compiler.context("コンパイラReleaseがありません")?,
        plugins: plugins.context("Plugin Releaseがありません")?,
    })
}
pub fn checksum_for(sums: &str, name: &str) -> Result<String> {
    let matches: Vec<_> = sums
        .lines()
        .filter_map(|l| {
            let mut parts = l.split_whitespace();
            let hash = parts.next()?;
            let file = parts.next()?.trim_start_matches('*');
            (file == name
                && parts.next().is_none()
                && hash.len() == 64
                && hash.bytes().all(|c| c.is_ascii_hexdigit()))
            .then_some(hash.to_owned())
        })
        .collect();
    ensure!(
        matches.len() == 1,
        "配布物のSHA256を一意に確認できません: {name}"
    );
    Ok(matches[0].clone())
}
fn platform() -> Result<&'static str> {
    match (std::env::consts::OS, std::env::consts::ARCH) {
        ("windows", "x86_64") => Ok("windows-x86_64"),
        ("linux", "x86_64") => Ok("linux-x86_64"),
        ("macos", "aarch64") => Ok("macos-arm64"),
        _ => bail!("このOS / CPUのスタンドアロン配布物はありません"),
    }
}
fn archive_extension() -> &'static str {
    if cfg!(windows) { "zip" } else { "tar.gz" }
}
fn exe_name(name: &str) -> String {
    format!("{name}{}", if cfg!(windows) { ".exe" } else { "" })
}
pub fn validate_destination(path: &Path) -> Result<()> {
    ensure!(path.is_absolute(), "保存先には絶対パスを指定してください");
    ensure!(
        !path.components().any(|c| matches!(c, Component::ParentDir)),
        "保存先に..は使えません"
    );
    ensure!(
        path.parent().is_some(),
        "ファイルシステムのルートは保存先にできません"
    );
    Ok(())
}
fn safe_entry(path: &Path) -> bool {
    !path.as_os_str().is_empty()
        && path
            .components()
            .all(|c| matches!(c, Component::Normal(_) | Component::CurDir))
}
pub fn extract(archive: &Path, destination: &Path) -> Result<()> {
    let name = archive.file_name().unwrap_or_default().to_string_lossy();
    let mut total = 0u64;
    if name.ends_with(".zip") {
        let mut zip = zip::ZipArchive::new(fs::File::open(archive)?)?;
        for index in 0..zip.len() {
            let mut entry = zip.by_index(index)?;
            let path = entry
                .enclosed_name()
                .context("ZIPに危険なパスがあります")?
                .to_path_buf();
            ensure!(safe_entry(&path), "ZIPのパスが不正です");
            ensure!(
                entry.unix_mode().is_none_or(|m| m & 0o170000 != 0o120000),
                "ZIPのシンボリックリンクは展開しません"
            );
            total = total.saturating_add(entry.size());
            ensure!(total < 3 * 1024 * 1024 * 1024, "展開サイズが大きすぎます");
            let target = destination.join(path);
            if entry.is_dir() {
                fs::create_dir_all(target)?;
            } else {
                fs::create_dir_all(target.parent().unwrap())?;
                let mut out = fs::File::create(&target)?;
                std::io::copy(&mut entry, &mut out)?;
                #[cfg(unix)]
                if let Some(mode) = entry.unix_mode() {
                    use std::os::unix::fs::PermissionsExt;
                    fs::set_permissions(&target, fs::Permissions::from_mode(mode & 0o777))?;
                }
            }
        }
    } else {
        let file = fs::File::open(archive)?;
        let reader: Box<dyn Read> = if name.ends_with(".tar.gz") {
            Box::new(flate2::read::GzDecoder::new(file))
        } else if name.ends_with(".tar.xz") {
            Box::new(xz2::read::XzDecoder::new(file))
        } else {
            bail!("未対応のアーカイブ形式です")
        };
        for entry in tar::Archive::new(reader).entries()? {
            let mut entry = entry?;
            let path = entry.path()?.into_owned();
            ensure!(safe_entry(&path), "TARに危険なパスがあります");
            let kind = entry.header().entry_type();
            ensure!(
                kind.is_file() || kind.is_dir(),
                "TARのリンクや特殊ファイルは展開しません"
            );
            total = total.saturating_add(entry.size());
            ensure!(total < 3 * 1024 * 1024 * 1024, "展開サイズが大きすぎます");
            ensure!(
                entry.unpack_in(destination)?,
                "アーカイブが保存先を逸脱しました"
            );
        }
    }
    Ok(())
}
#[cfg(unix)]
fn set_executable(path: &Path) -> Result<()> {
    use std::os::unix::fs::PermissionsExt;
    fs::set_permissions(path, fs::Permissions::from_mode(0o755))?;
    Ok(())
}
#[cfg(not(unix))]
fn set_executable(_path: &Path) -> Result<()> {
    // Windows executability is determined by the file type, not Unix mode bits.
    Ok(())
}
fn executable_dirs() -> Vec<PathBuf> {
    let mut paths: Vec<PathBuf> = std::env::var_os("PATH")
        .map(|p| std::env::split_paths(&p).collect())
        .unwrap_or_default();
    #[cfg(windows)]
    {
        use winreg::{RegKey, enums::*};
        for (hive, key) in [
            (HKEY_CURRENT_USER, "Environment"),
            (
                HKEY_LOCAL_MACHINE,
                "SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Environment",
            ),
        ] {
            if let Ok(key) = RegKey::predef(hive).open_subkey(key) {
                if let Ok(value) = key.get_value::<String, _>("Path") {
                    paths.extend(std::env::split_paths(&expand_windows_environment(&value)));
                }
            }
        }
        if let Some(local) = std::env::var_os("LOCALAPPDATA") {
            paths.push(PathBuf::from(&local).join("Microsoft/WindowsApps"));
            paths.push(PathBuf::from(local).join("Microsoft/WinGet/Links"));
        }
        if let Some(program) = std::env::var_os("ProgramFiles") {
            paths.push(PathBuf::from(&program).join("LLVM/bin"));
            paths.push(PathBuf::from(program).join("WinGet/Links"));
        }
    }
    paths.dedup();
    paths
}
#[cfg(windows)]
fn expand_windows_environment(value: &str) -> std::ffi::OsString {
    use std::os::windows::ffi::OsStringExt;
    let input: Vec<u16> = value.encode_utf16().chain(Some(0)).collect();
    unsafe {
        let size = windows_sys::Win32::System::Environment::ExpandEnvironmentStringsW(
            input.as_ptr(),
            std::ptr::null_mut(),
            0,
        );
        if size == 0 {
            return value.into();
        }
        let mut buffer = vec![0u16; size as usize];
        let written = windows_sys::Win32::System::Environment::ExpandEnvironmentStringsW(
            input.as_ptr(),
            buffer.as_mut_ptr(),
            size,
        );
        if written == 0 || written > size {
            return value.into();
        }
        std::ffi::OsString::from_wide(&buffer[..written as usize - 1])
    }
}
pub fn find_executable(name: &str) -> Option<PathBuf> {
    #[cfg(target_os = "macos")]
    if ["clang", "gcc"].contains(&name) {
        // Homebrew llvm is keg-only; GCC uses a major-version suffix.
        if let Some(brew) = find_in_dirs("brew", &executable_dirs()) {
            let formula = if name == "clang" { "llvm" } else { "gcc" };
            if let Ok(prefix) = run(&brew, ["--prefix", formula], Duration::from_secs(15)) {
                let bin = Path::new(prefix.trim()).join("bin");
                if let Some(exe) = find_in_dirs(name, &[bin.clone()]) {
                    return Some(exe);
                }
                if name == "gcc" {
                    let mut candidates: Vec<_> = fs::read_dir(&bin)
                        .into_iter()
                        .flatten()
                        .filter_map(|entry| entry.ok())
                        .filter_map(|entry| {
                            let filename = entry.file_name().to_string_lossy().into_owned();
                            let major: u32 = filename.strip_prefix("gcc-")?.parse().ok()?;
                            entry.path().is_file().then_some((major, entry.path()))
                        })
                        .collect();
                    candidates.sort_by_key(|(major, _)| *major);
                    if let Some((_, exe)) = candidates.pop() {
                        return Some(exe);
                    }
                }
            }
        }
    }
    find_in_dirs(name, &executable_dirs())
}
fn find_in_dirs(name: &str, dirs: &[PathBuf]) -> Option<PathBuf> {
    for dir in dirs {
        for suffix in if cfg!(windows) {
            vec![".exe", ".cmd", ""]
        } else {
            vec![""]
        } {
            let exe = dir.join(format!("{name}{suffix}"));
            // App Execution Aliases (including winget.exe) can be reparse points.
            if fs::symlink_metadata(&exe).is_ok_and(|m| !m.is_dir()) {
                return Some(exe);
            }
        }
    }
    None
}
pub fn zig_target(arch: &str, os: &str) -> Result<&'static str> {
    match (arch, os) {
        ("x86_64", "windows") => Ok("x86_64-windows"),
        ("aarch64", "windows") => Ok("aarch64-windows"),
        ("x86_64", "linux") => Ok("x86_64-linux"),
        ("aarch64", "linux") => Ok("aarch64-linux"),
        ("x86_64", "macos") => Ok("x86_64-macos"),
        ("aarch64", "macos") => Ok("aarch64-macos"),
        _ => bail!("この環境のZig導入は未対応です"),
    }
}

pub fn run<I, S>(program: &Path, args: I, timeout: Duration) -> Result<String>
where
    I: IntoIterator<Item = S>,
    S: AsRef<std::ffi::OsStr>,
{
    let stdout = tempfile::tempfile()?;
    let stderr = tempfile::tempfile()?;
    let mut command = Command::new(program);
    let mut paths = executable_dirs();
    if let Some(parent) = program.parent().filter(|p| !p.as_os_str().is_empty()) {
        paths.insert(0, parent.to_path_buf());
    }
    if let Ok(path) = std::env::join_paths(paths) {
        command.env("PATH", path);
    }
    command
        .args(args)
        .stdin(Stdio::null())
        .stdout(stdout.try_clone()?)
        .stderr(stderr.try_clone()?);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    let mut child = command
        .spawn()
        .with_context(|| format!("{}を起動できません", program.display()))?;
    let status = match child.wait_timeout(timeout)? {
        Some(status) => status,
        None => {
            let _ = child.kill();
            let _ = child.wait();
            bail!("処理がタイムアウトしました: {}", program.display())
        }
    };
    use std::io::{Seek, SeekFrom};
    let mut out = stdout;
    let mut err = stderr;
    out.seek(SeekFrom::Start(0))?;
    err.seek(SeekFrom::Start(0))?;
    let mut text = String::new();
    out.take(24 * 1024).read_to_string(&mut text)?;
    err.take(24 * 1024).read_to_string(&mut text)?;
    ensure!(
        status.success(),
        "{}が失敗しました: {}",
        program.display(),
        text.trim()
    );
    Ok(text)
}
fn probe_compiler(executable: &Path, name: &str) -> Result<()> {
    let temp = tempfile::tempdir()?;
    let source = temp.path().join("probe.c");
    let output = temp.path().join(exe_name("probe"));
    fs::write(&source, "int main(void){return 0;}\n")?;
    let mut args = vec![];
    if name == "zig" {
        args.push("cc".as_ref())
    }
    args.extend([source.as_os_str(), "-o".as_ref(), output.as_os_str()]);
    run(executable, args, Duration::from_secs(90))?;
    run(&output, [] as [&str; 0], Duration::from_secs(10))?;
    Ok(())
}
fn create_launcher(bin: &Path, name: &str, target: &Path) -> Result<()> {
    fs::create_dir_all(bin)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::symlink;
        let temp = bin.join(format!(".{name}-new"));
        if temp.exists() {
            fs::remove_file(&temp)?;
        }
        symlink(target, &temp)?;
        fs::rename(temp, bin.join(name))?;
    }
    #[cfg(windows)]
    {
        let text = target.to_string_lossy();
        ensure!(
            !text.contains(['"', '%', '\n', '\r']),
            "この保存先はWindowsランチャーに使えません"
        );
        let content = format!("@echo off\r\n\"{text}\" %*\r\n");
        fs::write(bin.join(format!("{name}.cmd")), content)?;
    }
    Ok(())
}
#[cfg(not(windows))]
pub fn configure_path(bin: &Path, scope: PathScope) -> Result<()> {
    match scope {
        PathScope::None => Ok(()),
        PathScope::System => bail!("システムPATH変更はWindowsのみ対応です"),
        PathScope::User => {
            let home = directories::BaseDirs::new().context("ホームディレクトリがありません")?;
            let shell = std::env::var("SHELL").unwrap_or_default();
            let filename = if shell.ends_with("zsh") {
                ".zshrc"
            } else if shell.ends_with("bash") {
                ".bashrc"
            } else {
                bail!(
                    "このシェルへのPATH自動追加は未対応です。{}を手動でPATHへ追加してください",
                    bin.display()
                )
            };
            let file = home.home_dir().join(filename);
            let existing = fs::read_to_string(&file).unwrap_or_default();
            let raw = bin.to_string_lossy();
            ensure!(!raw.contains(['\n', '\r']), "PATHに改行は使えません");
            let quoted = raw.replace('\'', "'\\''");
            let line = format!("export PATH='{quoted}':\"$PATH\"");
            if !existing.lines().any(|l| l == line) {
                let backup = file.with_extension(format!(
                    "gscript-backup-{}",
                    std::time::SystemTime::now()
                        .duration_since(std::time::UNIX_EPOCH)?
                        .as_secs()
                ));
                if file.exists() {
                    fs::copy(&file, backup)?;
                }
                let mut out = fs::OpenOptions::new()
                    .create(true)
                    .append(true)
                    .open(file)?;
                write!(out, "\n# GScript Manager\n{line}\n")?;
            }
            Ok(())
        }
    }
}
#[cfg(windows)]
pub fn configure_path(bin: &Path, scope: PathScope) -> Result<()> {
    use winreg::{RegKey, enums::*};
    if scope == PathScope::None {
        return Ok(());
    }
    let key = if scope == PathScope::User {
        RegKey::predef(HKEY_CURRENT_USER)
            .open_subkey_with_flags("Environment", KEY_READ | KEY_WRITE)?
    } else {
        RegKey::predef(HKEY_LOCAL_MACHINE).open_subkey_with_flags("SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Environment",KEY_READ|KEY_WRITE).context("システムPATHには管理者権限が必要です。ユーザーPATHを選ぶか管理者として起動してください")?
    };
    let old: String = key.get_value("Path").unwrap_or_default();
    let raw = bin.to_string_lossy();
    ensure!(
        !raw.contains([';', '\r', '\n']),
        "PATHとして使えない保存先です"
    );
    if !old.split(';').any(|p| {
        p.trim_end_matches('\\')
            .eq_ignore_ascii_case(raw.trim_end_matches('\\'))
    }) {
        let backup = data_dir()?.join("path-backup.json");
        fs::create_dir_all(backup.parent().unwrap())?;
        atomic_json(
            &backup,
            &serde_json::json!({"scope":format!("{scope:?}"),"Path":old}),
        )?;
        let combined = if old.is_empty() {
            raw.to_string()
        } else {
            format!("{old};{raw}")
        };
        use std::os::windows::ffi::OsStrExt;
        let bytes: Vec<u8> = std::ffi::OsStr::new(&combined)
            .encode_wide()
            .chain(Some(0))
            .flat_map(u16::to_le_bytes)
            .collect();
        key.set_raw_value(
            "Path",
            &winreg::RegValue {
                vtype: REG_EXPAND_SZ,
                bytes,
            },
        )?;
        let env: Vec<u16> = "Environment\0".encode_utf16().collect();
        unsafe {
            windows_sys::Win32::UI::WindowsAndMessaging::SendMessageTimeoutW(
                windows_sys::Win32::UI::WindowsAndMessaging::HWND_BROADCAST,
                windows_sys::Win32::UI::WindowsAndMessaging::WM_SETTINGCHANGE,
                0,
                env.as_ptr() as isize,
                windows_sys::Win32::UI::WindowsAndMessaging::SMTO_ABORTIFHUNG,
                2000,
                std::ptr::null_mut(),
            );
        }
    }
    Ok(())
}
#[cfg(not(windows))]
fn install_system_compiler(name: &str, release: &ToolchainRelease) -> Result<()> {
    let _ = name;
    #[cfg(target_os = "linux")]
    {
        if let Some(pkexec) = find_executable("pkexec") {
            let apt = find_executable("apt-get")
                .context("apt-getがありません。OSのパッケージ管理で導入してください")?;
            run(
                &pkexec,
                [
                    apt.as_os_str(),
                    "install".as_ref(),
                    "-y".as_ref(),
                    format!("{}={}", release.package, release.version).as_ref(),
                ],
                Duration::from_secs(1800),
            )?;
        } else {
            bail!(
                "認証付きインストーラーpkexecがありません。端末で sudo apt-get install {name} を実行するか、Zigを選んでください"
            )
        }
    }
    #[cfg(target_os = "macos")]
    {
        let brew = find_executable("brew").context("Clang / GCCの導入にはHomebrewが必要です")?;
        let installed = run(
            &brew,
            ["list", "--versions", release.package.as_str()],
            Duration::from_secs(30),
        )
        .is_ok_and(|output| !output.trim().is_empty());
        run(
            &brew,
            [
                if installed { "upgrade" } else { "install" },
                release.package.as_str(),
            ],
            Duration::from_secs(1800),
        )?;
    }
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn feed_versions_are_distinct() {
        let xml = r#"<feed><entry><link href="https://github.com/sofia-gros/gscript/releases/tag/plugin-v0.6.0"/></entry><entry><link href="https://github.com/sofia-gros/gscript/releases/tag/v0.6.1"/></entry><entry><link href="https://github.com/sofia-gros/gscript/releases/tag/v0.7.0-beta.1"/></entry></feed>"#;
        let r = parse_feed(xml).unwrap();
        assert_eq!(r.compiler.version, "0.6.1");
        assert_eq!(r.plugins.version, "0.6.0");
    }
    #[test]
    fn exact_checksum_required() {
        let hash = "a".repeat(64);
        assert_eq!(
            checksum_for(&format!("{hash}  a.zip\n"), "a.zip").unwrap(),
            hash
        );
        assert!(checksum_for(&format!("{hash} a.zip\n{hash} a.zip"), "a.zip").is_err());
        assert!(checksum_for("bad a.zip", "a.zip").is_err());
    }
    #[test]
    fn paths_and_archive_links_rejected() {
        assert!(validate_destination(Path::new("relative")).is_err());
        assert!(!safe_entry(Path::new("../escape")));
        let root = tempfile::tempdir().unwrap();
        let archive = root.path().join("bad.zip");
        let mut zip = zip::ZipWriter::new(fs::File::create(&archive).unwrap());
        zip.start_file("../escape", zip::write::SimpleFileOptions::default())
            .unwrap();
        zip.write_all(b"bad").unwrap();
        zip.finish().unwrap();
        let out = root.path().join("out");
        fs::create_dir(&out).unwrap();
        assert!(extract(&archive, &out).is_err());
        assert!(!root.path().join("escape").exists());
    }
    #[test]
    fn valid_archive_extracts() {
        let root = tempfile::tempdir().unwrap();
        let archive = root.path().join("ok.zip");
        let mut zip = zip::ZipWriter::new(fs::File::create(&archive).unwrap());
        zip.start_file("folder/hello", zip::write::SimpleFileOptions::default())
            .unwrap();
        zip.write_all(b"hello").unwrap();
        zip.finish().unwrap();
        let out = root.path().join("out");
        fs::create_dir(&out).unwrap();
        extract(&archive, &out).unwrap();
        assert_eq!(fs::read(out.join("folder/hello")).unwrap(), b"hello");
    }
    #[test]
    fn custom_absolute_paths_persist() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config.json");
        let s = Settings {
            compiler_dir: dir.path().join("my compiler"),
            extensions_dir: dir.path().join("my extensions"),
            toolchains_dir: dir.path().join("toolchains"),
            docs_dir: dir.path().join("offline docs"),
            path_scope: PathScope::User,
        };
        atomic_json(&path, &s).unwrap();
        let restored: Settings = serde_json::from_slice(&fs::read(path).unwrap()).unwrap();
        assert_eq!(restored.compiler_dir, s.compiler_dir);
        assert_eq!(restored.path_scope, PathScope::User);
    }
}

#[cfg(test)]
mod toolchain_tests {
    use super::*;
    use std::net::TcpListener;
    #[test]
    fn retries_transient_http_failure_and_validates_download() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let server = std::thread::spawn(move || {
            for attempt in 0..2 {
                let (mut stream, _) = listener.accept().unwrap();
                let mut request = [0u8; 4096];
                let _ = stream.read(&mut request).unwrap();
                if attempt == 0 {
                    stream.write_all(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n").unwrap();
                } else {
                    stream.write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\nConnection: close\r\n\r\nhello").unwrap();
                }
            }
        });
        let root = tempfile::tempdir().unwrap();
        let output = root.path().join("download.zip");
        let service = Service {
            client: Client::builder()
                .no_proxy()
                .timeout(Duration::from_secs(3))
                .build()
                .unwrap(),
        };
        service
            .download(
                &format!("http://{address}/download"),
                &output,
                &format!("{:x}", Sha256::digest(b"hello")),
                &|_| {},
            )
            .unwrap();
        assert_eq!(fs::read(output).unwrap(), b"hello");
        server.join().unwrap();
    }
    #[test]
    fn bad_checksum_is_not_installed_or_retried() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let server = std::thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            let mut request = [0u8; 4096];
            let _ = stream.read(&mut request).unwrap();
            stream
                .write_all(
                    b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\nConnection: close\r\n\r\nhello",
                )
                .unwrap();
        });
        let root = tempfile::tempdir().unwrap();
        let output = root.path().join("download.zip");
        let service = Service {
            client: Client::builder()
                .no_proxy()
                .timeout(Duration::from_secs(3))
                .build()
                .unwrap(),
        };
        let error = service
            .download(
                &format!("http://{address}/download"),
                &output,
                &"a".repeat(64),
                &|_| {},
            )
            .unwrap_err();
        assert!(error.to_string().contains("SHA256"));
        assert!(!output.exists());
        server.join().unwrap();
    }
    #[test]
    fn finds_tools_in_newly_supplied_directories() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join(exe_name("clang"));
        fs::write(&path, b"fixture").unwrap();
        assert_eq!(
            find_in_dirs("clang", &[dir.path().to_path_buf()]).unwrap(),
            path
        );
    }
}

#[cfg(test)]
mod upgrade_tests {
    use super::*;
    #[test]
    fn upgrade_preserves_previous_toolchain() {
        let root = tempfile::tempdir().unwrap();
        let old = root.path().join("zig");
        let staged = root.path().join("new");
        fs::create_dir(&old).unwrap();
        fs::write(old.join("version"), "1.0.0").unwrap();
        fs::create_dir(&staged).unwrap();
        fs::write(staged.join("version"), "1.1.0").unwrap();
        promote_toolchain(&staged, &old, Some("1.0.0")).unwrap();
        assert_eq!(fs::read_to_string(old.join("version")).unwrap(), "1.1.0");
        let backup = fs::read_dir(root.path())
            .unwrap()
            .filter_map(|e| e.ok())
            .find(|e| e.file_name().to_string_lossy().starts_with("zig-backup-"))
            .unwrap();
        assert_eq!(
            fs::read_to_string(backup.path().join("version")).unwrap(),
            "1.0.0"
        );
    }
    #[test]
    fn failed_promotion_restores_previous_toolchain() {
        let root = tempfile::tempdir().unwrap();
        let old = root.path().join("zig");
        fs::create_dir(&old).unwrap();
        fs::write(old.join("version"), "1.0.0").unwrap();
        assert!(promote_toolchain(&root.path().join("missing"), &old, Some("1.0.0")).is_err());
        assert_eq!(fs::read_to_string(old.join("version")).unwrap(), "1.0.0");
    }
}
