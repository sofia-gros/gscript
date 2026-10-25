#[cfg(feature = "gui")]
mod ui;
fn main() -> anyhow::Result<()> {
    let args: Vec<_> = std::env::args().collect();
    if args.iter().any(|a| a == "--self-check") {
        let pages = gscript_manager::docs::chapters();
        anyhow::ensure!(pages.len() == 25, "embedded guide is incomplete");
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
    #[cfg(feature = "gui")]
    ui::run();
    #[cfg(not(feature = "gui"))]
    anyhow::bail!("Build with the default gui feature to open the desktop app");
    #[allow(unreachable_code)]
    Ok(())
}
