use std::{env, fs, path::PathBuf};
fn main() {
    let root = PathBuf::from(env::var("CARGO_MANIFEST_DIR").unwrap()).join("../../../docs/guide");
    let navigation = root.join("navigation.json");
    println!("cargo:rerun-if-changed={}", navigation.display());
    let mut pages: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(navigation).unwrap()).unwrap();
    for page in pages.as_array_mut().unwrap() {
        let path = root.join(page["id"].as_str().unwrap());
        println!("cargo:rerun-if-changed={}", path.display());
        page["source"] = fs::read_to_string(path).unwrap().into();
    }
    fs::write(
        PathBuf::from(env::var("OUT_DIR").unwrap()).join("guide.json"),
        serde_json::to_string(&pages).unwrap(),
    )
    .unwrap();
}
