use zed_extension_api::{self as zed, settings::LspSettings, LanguageServerId, Result};

struct Gscript;
impl zed::Extension for Gscript {
    fn new() -> Self { Self }
    fn language_server_command(&mut self, id: &LanguageServerId, worktree: &zed::Worktree) -> Result<zed::Command> {
        let settings = LspSettings::for_worktree(id.as_ref(), worktree).ok();
        let binary = settings.and_then(|s| s.binary);
        let command = binary.as_ref().and_then(|b| b.path.clone())
            .or_else(|| worktree.which("gs-lsp"))
            .ok_or("Install GS Language Server v0.4.0 and add gs-lsp to PATH, or set lsp.gs-lsp.binary.path")?;
        let args = binary.and_then(|b| b.arguments).unwrap_or_else(|| vec!["--stdio".into()]);
        Ok(zed::Command { command, args, env: worktree.shell_env() })
    }
    fn language_server_initialization_options(&mut self, id: &LanguageServerId, worktree: &zed::Worktree) -> Result<Option<zed::serde_json::Value>> {
        Ok(LspSettings::for_worktree(id.as_ref(), worktree).ok().and_then(|s| s.initialization_options))
    }
}
zed::register_extension!(Gscript);
