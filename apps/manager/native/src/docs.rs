use serde::Deserialize;
#[derive(Clone, Debug, Deserialize)]
pub struct Chapter {
    pub id: String,
    pub title: String,
    pub group: String,
    pub source: String,
}
pub fn chapters() -> Vec<Chapter> {
    serde_json::from_str(include_str!(concat!(env!("OUT_DIR"), "/guide.json")))
        .expect("embedded guide")
}
pub fn search(query: &str) -> Vec<Chapter> {
    let q = query.to_lowercase();
    chapters()
        .into_iter()
        .filter(|d| {
            format!("{} {}", d.title, d.source)
                .to_lowercase()
                .contains(&q)
        })
        .collect()
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn embedded_offline_guide() {
        let docs = chapters();
        assert_eq!(docs.len(), 26);
        assert!(
            docs.iter()
                .any(|d| d.id == "comparison.md" && d.source.contains("JavaScript"))
        );
        assert!(!search("range").is_empty());
    }
}
