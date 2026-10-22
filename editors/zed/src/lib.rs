use zed_extension_api::{self as zed, settings::LspSettings, LanguageServerId, Result};

struct Gscript;
impl zed::Extension for Gscript {
    fn new() -> Self { Self }
    fn language_server_command(&mut self, id: &LanguageServerId, worktree: &zed::Worktree) -> Result<zed::Command> {
        let settings = LspSettings::for_worktree(id.as_ref(), worktree).ok();
        let binary = settings.and_then(|s| s.binary);
        let args = binary.as_ref().and_then(|b| b.arguments.clone()).unwrap_or_else(|| vec!["--stdio".into()]);
        let configured = binary.and_then(|b| b.path).or_else(|| worktree.which("gs-lsp"));
        let command = match configured {
            Some(command) => command,
            None => {
                let (os, arch) = match zed::current_platform() {
                    (zed::Os::Linux, zed::Architecture::X8664) => ("linux", "x86_64"),
                    (zed::Os::Mac, zed::Architecture::Aarch64) => ("macos", "arm64"),
                    (zed::Os::Windows, zed::Architecture::X8664) => ("windows", "x86_64"),
                    _ => return Err("No native GS server for this CPU/OS. Set lsp.gs-lsp.binary.path to Python 3.12+ and binary.arguments to the GS server .pyz path followed by --stdio. See docs/editors.md.".into()),
                };
                let stem = format!("gs-lsp-v0.5.0-{os}-{arch}");
                let directory = "gs-lsp-0.5.0";
                let executable = if os == "windows" { "gs-lsp.exe" } else { "gs-lsp" };
                let path = format!("{directory}/{stem}/{executable}");
                if !std::fs::metadata(&path).is_ok_and(|s| s.is_file()) {
                    zed::set_language_server_installation_status(id, &zed::LanguageServerInstallationStatus::Downloading);
                    let suffix = if os == "windows" { "zip" } else { "tar.gz" };
                    let url = format!("https://github.com/sofia-gros/gscript/releases/download/plugin-v0.5.0/{stem}.{suffix}");
                    zed::download_file(&url, directory, if os == "windows" { zed::DownloadedFileType::Zip } else { zed::DownloadedFileType::GzipTar })
                        .map_err(|e| format!("GS server download failed: {e}. Install gs-lsp 0.5.0 manually and set lsp.gs-lsp.binary.path to its absolute path."))?;
                    zed::make_file_executable(&path)?;
                }
                path
            }
        };
        Ok(zed::Command { command, args, env: worktree.shell_env() })
    }
    fn language_server_initialization_options(&mut self, id: &LanguageServerId, worktree: &zed::Worktree) -> Result<Option<zed::serde_json::Value>> {
        Ok(LspSettings::for_worktree(id.as_ref(), worktree).ok().and_then(|s| s.initialization_options))
    }
}
zed::register_extension!(Gscript);
