#![cfg_attr(
    all(target_os = "windows", not(debug_assertions)),
    windows_subsystem = "windows"
)]
#[cfg(feature = "gui")]
mod ui;
fn main() -> anyhow::Result<()> {
    let args: Vec<_> = std::env::args().collect();
    if args.iter().any(|a| a == "--self-check") {
        let pages = gscript_manager::docs::chapters();
        anyhow::ensure!(pages.len() == 26, "embedded guide is incomplete");
        println!(
            "GScript Manager {}: {} embedded Markdown pages; native service ready",
            env!("CARGO_PKG_VERSION"),
            pages.len()
        );
        return Ok(());
    }
    if args.iter().any(|a| a == "--version") {
        println!("GScript Manager {}", env!("CARGO_PKG_VERSION"));
        return Ok(());
    }
    if args.iter().any(|a| a == "--check-updates") {
        let r = gscript_manager::service::Service::new()?.check_updates()?;
        println!(
            "Compiler {} / Plugin {}",
            r.compiler.version, r.plugins.version
        );
        return Ok(());
    }
    if args.iter().any(|a| a == "--toolchains") {
        let settings = gscript_manager::service::Settings::load()?;
        let tools = gscript_manager::service::Service::new()?.detect_toolchains(&settings);
        println!("{}", serde_json::to_string_pretty(&tools)?);
        return Ok(());
    }
    if let Some(index) = args.iter().position(|a| a == "--download-toolchain") {
        let name = args
            .get(index + 1)
            .ok_or_else(|| anyhow::anyhow!("ツール名が必要です"))?;
        let directory = args
            .iter()
            .position(|a| a == "--download-dir")
            .and_then(|i| args.get(i + 1))
            .ok_or_else(|| anyhow::anyhow!("--download-dir ABSOLUTE_PATH が必要です"))?;
        let result = gscript_manager::service::Service::new()?.download_toolchain(
            name,
            std::path::Path::new(directory),
            &|p| eprintln!("{:.0}% {}", p.percent, p.message),
        )?;
        println!("SHA256 verified: {}", result.display());
        return Ok(());
    }
    if let Some(index) = args.iter().position(|a| a == "--install-toolchain") {
        let name = args
            .get(index + 1)
            .ok_or_else(|| anyhow::anyhow!("--install-toolchain NAME が必要です"))?;
        let directory = args
            .iter()
            .position(|a| a == "--install-dir")
            .and_then(|i| args.get(i + 1))
            .ok_or_else(|| anyhow::anyhow!("--install-dir ABSOLUTE_PATH が必要です"))?;
        anyhow::ensure!(
            args.iter().any(|a| a == "--no-path"),
            "CLIインストールでは--no-pathを明示してください。PATH設定はGUIから操作できます"
        );
        let mut settings = gscript_manager::service::Settings::load()?;
        settings.toolchains_dir = std::path::PathBuf::from(directory);
        settings.path_scope = gscript_manager::service::PathScope::None;
        let result =
            gscript_manager::service::Service::new()?.install_toolchain(name, &settings, &|p| {
                eprintln!("{:.0}% {}", p.percent, p.message)
            })?;
        println!("{result}");
        return Ok(());
    }
    #[cfg(feature = "gui")]
    ui::run();
    #[cfg(not(feature = "gui"))]
    anyhow::bail!("Build with the default gui feature to open the desktop app");
    #[allow(unreachable_code)]
    Ok(())
}
