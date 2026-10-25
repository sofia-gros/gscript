//! Provider metadata, separate from machine detection and installation.
use anyhow::{Context, Result, bail, ensure};
use regex::Regex;
use semver::Version;
#[derive(Clone, Debug)]
pub struct ToolchainRelease {
    pub version: String,
    pub source: String,
    pub url: Option<String>,
    pub sha256: Option<String>,
    pub package: String,
    pub installer_type: Option<String>,
    pub executable: Option<String>,
    pub install_location: Option<String>,
}
impl ToolchainRelease {
    pub fn tool_version(&self) -> String {
        let value = self.version.rsplit(':').next().unwrap_or(&self.version);
        Regex::new(r"[0-9]+(?:\.[0-9]+)+")
            .unwrap()
            .find(value)
            .map(|m| m.as_str().to_string())
            .unwrap_or_else(|| self.version.clone())
    }
}
pub fn zig_release(source: &str, target: &str) -> Result<ToolchainRelease> {
    let data: serde_json::Value = serde_json::from_str(source)?;
    let (version, release) = data
        .as_object()
        .context("Zig配布情報の形式が不正です")?
        .iter()
        .filter_map(|(key, value)| {
            Version::parse(key)
                .ok()
                .filter(|v| v.pre.is_empty())
                .map(|v| (v, value))
        })
        .max_by(|a, b| a.0.cmp(&b.0))
        .context("Zigの安定版がありません")?;
    let entry = &release[target];
    let url = entry["tarball"]
        .as_str()
        .context("このOS / CPU向けのZig最新版がありません")?;
    let parsed = reqwest::Url::parse(url)?;
    ensure!(
        parsed.scheme() == "https" && parsed.host_str().is_some(),
        "Zig公式の配布情報にHTTPSの取得先がありません"
    );
    let hash = entry["shasum"]
        .as_str()
        .context("Zig最新版にSHA256がありません")?;
    ensure!(
        hash.len() == 64 && hash.bytes().all(|b| b.is_ascii_hexdigit()),
        "Zig配布情報のSHA256が不正です"
    );
    Ok(ToolchainRelease {
        version: version.to_string(),
        source: "Zig公式 / 安定版".into(),
        url: Some(parsed.to_string()),
        sha256: Some(hash.into()),
        package: String::new(),
        installer_type: None,
        executable: None,
        install_location: None,
    })
}
pub fn winget_version(output: &str) -> Result<String> {
    let pattern = Regex::new(r"^[0-9]+(?:\.[0-9]+)+(?:[-+][0-9A-Za-z.-]+)?$").unwrap();
    let mut versions: Vec<_> = output
        .lines()
        .map(str::trim)
        .filter(|s| pattern.is_match(s) && !is_prerelease(s))
        .collect();
    versions.sort_by_key(|s| numeric_parts(s));
    versions
        .last()
        .map(|v| v.to_string())
        .context("WinGetのバージョン一覧を読み取れませんでした")
}
fn is_prerelease(v: &str) -> bool {
    let lower = v.to_ascii_lowercase();
    ["alpha", "beta", "nightly", "snapshot", "dev", "rc"]
        .iter()
        .any(|s| lower.contains(s))
}
fn numeric_parts(value: &str) -> Vec<u64> {
    value
        .split(|c: char| !c.is_ascii_digit())
        .filter_map(|n| n.parse().ok())
        .collect()
}
pub fn installed_version(name: &str, output: &str) -> Option<String> {
    let first = output.lines().next()?.trim();
    if name == "zig" {
        return Version::parse(first).ok().map(|v| v.to_string());
    }
    if name == "clang" {
        return Regex::new(r"clang version\s+([0-9]+(?:\.[0-9]+)+)")
            .unwrap()
            .captures(first)
            .map(|c| c[1].into());
    }
    // macOS ships a gcc command that is actually Apple Clang.
    if name == "gcc" && first.to_ascii_lowercase().contains("clang") {
        return None;
    }
    Regex::new(r"[0-9]+(?:\.[0-9]+)+")
        .unwrap()
        .find_iter(first)
        .last()
        .map(|m| m.as_str().into())
}
pub fn newer_version(installed: &str, available: &str) -> Option<bool> {
    fn parse(v: &str) -> Option<Version> {
        Version::parse(v)
            .ok()
            .or_else(|| Version::parse(&format!("{v}.0")).ok())
    }
    Some(parse(available)? > parse(installed)?)
}
pub fn brew_release(output: &str, name: &str) -> Result<ToolchainRelease> {
    let value: serde_json::Value = serde_json::from_str(output)?;
    let formula = if name == "clang" { "llvm" } else { "gcc" };
    let item = value["formulae"]
        .as_array()
        .context("Homebrewの応答が不正です")?
        .iter()
        .find(|v| v["name"] == formula)
        .context("Homebrewの配布情報がありません")?;
    let version = item["versions"]["stable"]
        .as_str()
        .context("Homebrew安定版がありません")?;
    Ok(ToolchainRelease {
        version: version.into(),
        source: format!("Homebrew / {formula}"),
        url: None,
        sha256: None,
        package: formula.into(),
        installer_type: None,
        executable: None,
        install_location: None,
    })
}
pub fn apt_release(output: &str, name: &str) -> Result<ToolchainRelease> {
    let version = output
        .lines()
        .filter_map(|line| line.split('|').nth(1))
        .map(str::trim)
        .filter(|v| !v.is_empty())
        .max_by_key(|v| numeric_parts(v))
        .context("APTカタログに利用可能な版がありません。apt updateでカタログを更新してください")?;
    Ok(ToolchainRelease {
        version: version.into(),
        source: format!("APTカタログ / {name}"),
        url: None,
        sha256: None,
        package: name.into(),
        installer_type: None,
        executable: None,
        install_location: None,
    })
}
pub fn package_id(name: &str) -> Result<&'static str> {
    match name {
        "clang" => Ok("LLVM.LLVM"),
        "gcc" => Ok("BrechtSanders.WinLibs.POSIX.UCRT"),
        _ => bail!("不明なWinGetパッケージです"),
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn zig_uses_latest_stable_and_url_from_response() {
        let hash = "a".repeat(64);
        let json = serde_json::json!({"master":{},"1.0.0":{"x86_64-windows":{"tarball":"https://ziglang.org/download/first.zip","shasum":hash}},"1.1.0":{"x86_64-windows":{"tarball":"https://ziglang.org/download/changed-location.zip","shasum":hash}},"2.0.0-beta.1":{"x86_64-windows":{}}});
        let release = zig_release(&json.to_string(), "x86_64-windows").unwrap();
        assert_eq!(release.version, "1.1.0");
        assert!(release.url.unwrap().ends_with("changed-location.zip"));
    }
    #[test]
    fn rejects_insecure_download_url() {
        let json = serde_json::json!({"1.0.0":{"x86_64-windows":{"tarball":"http://example.org/payload.zip","shasum":"a".repeat(64)}}});
        assert!(zig_release(&json.to_string(), "x86_64-windows").is_err());
    }
    #[test]
    fn parses_localized_winget_versions() {
        assert_eq!(
            winget_version("バージョン\n-----\n18.1.8\n19.1.1\n20.0.0-rc1\n").unwrap(),
            "19.1.1"
        );
        assert_eq!(
            winget_version("Version\n15.2.0-13.0.0-r3\n14.2.0-12.0.0-r2").unwrap(),
            "15.2.0-13.0.0-r3"
        );
    }
    #[test]
    fn compares_compiler_versions_without_downgrading() {
        assert_eq!(
            installed_version("clang", "Apple clang version 16.0.0 (clang-1600.0.1)"),
            Some("16.0.0".into())
        );
        assert_eq!(
            installed_version("gcc", "gcc.exe (Rev5, Built by MSYS2 project) 15.2.0"),
            Some("15.2.0".into())
        );
        assert_eq!(
            installed_version("gcc", "Apple clang version 16.0.0 (clang-1600.0.1)"),
            None
        );
        assert_eq!(newer_version("0.16.0", "0.15.2"), Some(false));
        assert_eq!(newer_version("14.0.0", "15.2.0"), Some(true));
    }
}

pub fn manifest_path(name: &str) -> Result<&'static str> {
    match name {
        "clang" => Ok("l/LLVM/LLVM"),
        "gcc" => Ok("b/BrechtSanders/WinLibs/POSIX/UCRT"),
        _ => bail!("不明なWindowsツールです"),
    }
}
pub fn github_catalog_versions(body: &str) -> Result<String> {
    if let Ok(data) = serde_json::from_str::<serde_json::Value>(body) {
        if let Some(items) = data.as_array() {
            let versions = items
                .iter()
                .filter_map(|i| i["name"].as_str())
                .collect::<Vec<_>>()
                .join("\n");
            return winget_version(&versions);
        }
    }

    let pattern =
        Regex::new(r#"(?s)<script[^>]*type="application/json"[^>]*>(.*?)</script>"#).unwrap();
    for captures in pattern.captures_iter(body) {
        if let Ok(data) = serde_json::from_str::<serde_json::Value>(&captures[1]) {
            let route = &data["payload"]["codeViewTreeRoute"];
            let tree = if route.is_object() {
                &route["tree"]
            } else {
                &data["payload"]["tree"]
            };
            if let Some(items) = tree["items"].as_array() {
                let versions = items
                    .iter()
                    .filter_map(|i| i["name"].as_str())
                    .collect::<Vec<_>>()
                    .join("\n");
                if let Ok(version) = winget_version(&versions) {
                    return Ok(version);
                }
            }
        }
    }
    bail!("公式カタログのバージョン一覧を読み取れません")
}
pub fn windows_manifest(source: &str, name: &str, arch: &str) -> Result<ToolchainRelease> {
    let data: serde_yaml::Value = serde_yaml::from_str(source)?;
    let id = package_id(name)?;
    ensure!(
        data["PackageIdentifier"].as_str() == Some(id),
        "取得したパッケージIDが一致しません"
    );
    let expected = match arch {
        "x86_64" => "x64",
        "aarch64" => "arm64",
        _ => bail!("このCPUのWindows配布物は未対応です"),
    };
    let installer = data["Installers"]
        .as_sequence()
        .context("インストーラー情報がありません")?
        .iter()
        .find(|i| i["Architecture"].as_str() == Some(expected))
        .context("このCPU向けのインストーラーがありません")?;
    let url = installer["InstallerUrl"]
        .as_str()
        .context("インストーラーのURLがありません")?;
    let parsed = reqwest::Url::parse(url)?;
    ensure!(
        parsed.scheme() == "https",
        "インストーラーのURLがHTTPSではありません"
    );
    let sha = installer["InstallerSha256"]
        .as_str()
        .context("インストーラーのSHA256がありません")?;
    ensure!(
        sha.len() == 64 && sha.bytes().all(|b| b.is_ascii_hexdigit()),
        "インストーラーのSHA256が不正です"
    );
    let version = data["PackageVersion"]
        .as_str()
        .context("配布バージョンがありません")?;
    let executable = installer["NestedInstallerFiles"]
        .as_sequence()
        .and_then(|items| {
            items
                .iter()
                .filter_map(|i| i["RelativeFilePath"].as_str())
                .find(|p| p.replace('\\', "/").ends_with(&format!("/bin/{name}.exe")))
        })
        .map(|s| s.replace('\\', "/"));
    Ok(ToolchainRelease {
        version: version.into(),
        source: format!("Microsoft WinGetカタログ / {id}"),
        url: Some(parsed.to_string()),
        sha256: Some(sha.into()),
        package: id.into(),
        installer_type: installer["InstallerType"]
            .as_str()
            .or(data["InstallerType"].as_str())
            .map(str::to_string),
        executable,
        install_location: installer["InstallerSwitches"]["InstallLocation"]
            .as_str()
            .or(data["InstallerSwitches"]["InstallLocation"].as_str())
            .map(str::to_string),
    })
}

#[cfg(test)]
mod windows_provider_tests {
    use super::*;
    #[test]
    fn reads_latest_catalog_and_installer_url_without_a_fixed_version() {
        assert_eq!(
            github_catalog_versions(r#"[{"name":"21.1.0"},{"name":"23.1.4"}]"#).unwrap(),
            "23.1.4"
        );
        let yaml = format!(
            "PackageIdentifier: LLVM.LLVM\nPackageVersion: 99.1.2\nInstallerType: wix\nInstallerSwitches:\n  InstallLocation: 'INSTALL_ROOT=\"<INSTALLPATH>\"'\nInstallers:\n- Architecture: x64\n  InstallerUrl: https://github.com/llvm/llvm-project/releases/download/new-location/changed.msi\n  InstallerSha256: {}\n",
            "a".repeat(64)
        );
        let release = windows_manifest(&yaml, "clang", "x86_64").unwrap();
        assert_eq!(release.version, "99.1.2");
        assert!(release.url.unwrap().ends_with("changed.msi"));
        assert_eq!(release.installer_type.as_deref(), Some("wix"));
    }
    #[test]
    fn selects_gcc_archive_path_for_cpu() {
        let yaml = format!(
            "PackageIdentifier: BrechtSanders.WinLibs.POSIX.UCRT\nPackageVersion: 16.2.0-14.0.0-r3\nInstallerType: zip\nInstallers:\n- Architecture: x64\n  InstallerUrl: https://github.com/brechtsanders/winlibs_mingw/releases/download/future/gcc.zip\n  InstallerSha256: {}\n  NestedInstallerFiles:\n  - RelativeFilePath: mingw64\\bin\\gcc.exe\n",
            "b".repeat(64)
        );
        let release = windows_manifest(&yaml, "gcc", "x86_64").unwrap();
        assert_eq!(release.executable.as_deref(), Some("mingw64/bin/gcc.exe"));
        assert_eq!(release.tool_version(), "16.2.0");
    }
}
