//! OS operations live outside GPUI. No shell interpolation, no background privilege escalation.
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
const MAX_DOWNLOAD: u64 = 700 * 1024 * 1024;
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
                version: "0.6.0".into(),
                tag: "v0.6.0".into(),
                notes: include_str!("../../../../docs/releases/v0.6.0.md").into(),
            },
            plugins: Release {
                version: "0.6.0".into(),
                tag: "plugin-v0.6.0".into(),
                notes: include_str!("../../../../docs/releases/plugin-v0.6.0.md").into(),
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
#[derive(Clone, Debug)]
pub struct Toolchain {
    pub name: String,
    pub executable: Option<PathBuf>,
    pub version: String,
    pub usable: bool,
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
                .timeout(Duration::from_secs(180))
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
        let response = self.client.get(url).send()?.error_for_status()?;
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
        ensure!(
            expected.len() == 64 && expected.bytes().all(|b| b.is_ascii_hexdigit()),
            "SHA256が不正です"
        );
        let mut response = self.client.get(url).send()?.error_for_status()?;
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
            let n = response.read(&mut buffer)?;
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
    pub fn detect_toolchains(&self, settings: &Settings) -> Vec<Toolchain> {
        ["clang", "gcc", "zig"]
            .into_iter()
            .map(|name| {
                let executable = find_executable(name).or_else(|| {
                    let path = settings.toolchains_dir.join("zig").join(exe_name("zig"));
                    (name == "zig" && path.is_file()).then_some(path)
                });
                let mut version = String::from("未検出");
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
                            if !usable {
                                version.push_str("（SDK / リンクの確認に失敗）");
                            }
                        }
                        Err(error) => version = format!("起動失敗: {error}"),
                    }
                }
                Toolchain {
                    name: name.into(),
                    executable,
                    version,
                    usable,
                }
            })
            .collect()
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
        progress(
            "OSのパッケージ管理ツールを起動しています。認証画面が表示される場合があります。".into(),
        );
        install_system_compiler(name)?;
        let found = self
            .detect_toolchains(settings)
            .into_iter()
            .find(|t| t.name == name && t.usable);
        ensure!(
            found.is_some(),
            "導入処理は終了しましたが、コンパイラとSDKの実行確認は完了していません。新しいセッションで再検出してください。"
        );
        Ok(format!("{name}を検出・実行確認しました"))
    }
    fn install_zig(&self, settings: &Settings, progress: &impl Fn(Progress)) -> Result<String> {
        progress("Zig公式の配布情報を確認しています…".into());
        let json: serde_json::Value = serde_json::from_str(
            &self.text("https://ziglang.org/download/index.json", 8 * 1024 * 1024)?,
        )?;
        let target = match (std::env::consts::ARCH, std::env::consts::OS) {
            ("x86_64", "windows") => "x86_64-windows",
            ("x86_64", "linux") => "x86_64-linux",
            ("aarch64", "macos") => "aarch64-macos",
            ("x86_64", "macos") => "x86_64-macos",
            ("aarch64", "linux") => "aarch64-linux",
            _ => bail!("この環境のZig導入は未対応です"),
        };
        let entry = &json["0.15.2"][target];
        let url = entry["tarball"]
            .as_str()
            .context("Zigの配布物がありません")?;
        ensure!(
            url.starts_with("https://ziglang.org/download/0.15.2/"),
            "Zigの取得先が不正です"
        );
        let hash = entry["shasum"]
            .as_str()
            .context("ZigのSHA256がありません")?;
        validate_destination(&settings.toolchains_dir)?;
        fs::create_dir_all(&settings.toolchains_dir)?;
        let destination = settings.toolchains_dir.join("zig");
        ensure!(
            !destination.exists(),
            "Zigの保存先が既に存在します: {}",
            destination.display()
        );
        let stage = tempfile::tempdir_in(&settings.toolchains_dir)?;
        let name = url
            .rsplit('/')
            .next()
            .context("Zigのファイル名がありません")?;
        let archive = stage.path().join(name);
        progress("Zigを取得しSHA256を検証しています…".into());
        self.download(url, &archive, hash, progress)?;
        let out = stage.path().join("content");
        fs::create_dir(&out)?;
        extract(&archive, &out)?;
        let folder = fs::read_dir(&out)?
            .filter_map(|e| e.ok())
            .find(|e| e.path().join(exe_name("zig")).is_file())
            .context("Zigの実行ファイルがありません")?
            .path();
        let exe = folder.join(exe_name("zig"));
        set_executable(&exe)?;
        probe_compiler(&exe, "zig")?;
        fs::rename(folder, &destination)?;
        if let Err(e) = configure_path(&destination, settings.path_scope) {
            let _ = fs::remove_dir_all(&destination);
            return Err(e);
        };
        Ok(format!(
            "Zig 0.15.2を導入しました: {}",
            destination.display()
        ))
    }
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
fn set_executable(path: &Path) -> Result<()> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(path, fs::Permissions::from_mode(0o755))?;
    }
    Ok(())
}
pub fn find_executable(name: &str) -> Option<PathBuf> {
    let path = std::env::var_os("PATH")?;
    for dir in std::env::split_paths(&path) {
        for suffix in if cfg!(windows) {
            vec![".exe", ".cmd", ""]
        } else {
            vec![""]
        } {
            let exe = dir.join(format!("{name}{suffix}"));
            if exe.is_file() {
                return Some(exe);
            }
        }
    }
    None
}
pub fn run<I, S>(program: &Path, args: I, timeout: Duration) -> Result<String>
where
    I: IntoIterator<Item = S>,
    S: AsRef<std::ffi::OsStr>,
{
    let stdout = tempfile::tempfile()?;
    let stderr = tempfile::tempfile()?;
    let mut command = Command::new(program);
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
fn install_system_compiler(name: &str) -> Result<()> {
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
                    name.as_ref(),
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
        if name == "clang" {
            run(
                Path::new("/usr/bin/xcode-select"),
                ["--install"],
                Duration::from_secs(60),
            )?;
        } else {
            let brew = find_executable("brew")
                .context("GCCの導入にはHomebrewが必要です。Zigも利用できます")?;
            run(&brew, ["install", "gcc"], Duration::from_secs(1800))?;
        }
    }
    #[cfg(windows)]
    {
        let winget = find_executable("winget")
            .context("wingetがありません。アプリインストーラーを導入するかZigを選んでください")?;
        let package = if name == "clang" {
            "LLVM.LLVM"
        } else {
            "BrechtSanders.WinLibs.POSIX.UCRT"
        };
        run(
            &winget,
            [
                "install",
                "--exact",
                "--id",
                package,
                "--source",
                "winget",
                "--accept-source-agreements",
                "--accept-package-agreements",
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
