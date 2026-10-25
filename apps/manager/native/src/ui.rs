use gpui::{prelude::*, *};
use gpui_component::{
    button::{Button, ButtonVariants},
    checkbox::Checkbox,
    input::{Input, InputEvent, InputState},
    progress::Progress as ProgressBar,
    scroll::ScrollableElement,
    text::TextView,
    *,
};
use gscript_manager::{
    docs::{self, Chapter},
    service::{self, Installed, PathScope, Progress, Releases, Service, Settings, Toolchain},
};
use regex::Regex;
use std::{
    path::PathBuf,
    sync::mpsc::{self, Receiver, Sender},
    time::{Duration, Instant},
};

#[derive(Clone, Copy, PartialEq)]
enum Page {
    Compiler,
    Editors,
    Toolchains,
    Docs,
    Notes,
}
enum Event {
    Updates(Result<Releases, String>),
    Detected(Vec<Toolchain>),
    Installed,
    Message(String),
}
struct Manager {
    page: Page,
    settings: Settings,
    service: Service,
    releases: Releases,
    records: Vec<Installed>,
    toolchains: Vec<Toolchain>,
    status: String,
    updating: bool,
    detecting: bool,
    chapters: Vec<Chapter>,
    chapter: usize,
    section: usize,
    language: usize,
    scroll: ScrollHandle,
    search: Entity<InputState>,
    _subscriptions: Vec<Subscription>,
    tx: Sender<Event>,
    rx: Receiver<Event>,
    notes: String,
    notes_title: String,
}
impl Manager {
    fn new(window: &mut Window, cx: &mut Context<Self>) -> Self {
        let service = Service::new().expect("HTTPS client");
        let settings = Settings::load().unwrap_or_else(|_| {
            let root = service::data_dir().unwrap_or_else(|_| PathBuf::from("."));
            Settings {
                compiler_dir: root.join("compiler"),
                extensions_dir: root.join("extensions"),
                toolchains_dir: root.join("toolchains"),
                docs_dir: root.join("docs"),
                path_scope: PathScope::User,
            }
        });
        let search = cx.new(|cx| InputState::new(window, cx).placeholder("ガイドを検索…"));
        let subscriptions = vec![cx.subscribe(&search, |_, _, _: &InputEvent, cx| cx.notify())];
        let (tx, rx) = mpsc::channel();
        cx.spawn(async move |weak, cx| {
            loop {
                Timer::after(Duration::from_millis(150)).await;
                if weak.update(cx, |this, cx| this.poll(cx)).is_err() {
                    break;
                }
            }
        })
        .detach();
        Self {
            page: Page::Compiler,
            records: service.records(&settings),
            releases: service.cached_releases(),
            settings,
            service,
            toolchains: vec![],
            status: "更新はまだ確認していません".into(),
            updating: false,
            detecting: false,
            chapters: docs::chapters(),
            chapter: 0,
            section: 0,
            language: 2,
            scroll: ScrollHandle::new(),
            search,
            _subscriptions: subscriptions,
            tx,
            rx,
            notes: String::new(),
            notes_title: String::new(),
        }
    }
    fn poll(&mut self, cx: &mut Context<Self>) {
        let mut changed = false;
        while let Ok(event) = self.rx.try_recv() {
            changed = true;
            match event {
                Event::Updates(result) => {
                    self.updating = false;
                    match result {
                        Ok(releases) => {
                            self.releases = releases;
                            self.status = "GitHubの最新の安定版を確認しました".into()
                        }
                        Err(e) => {
                            self.status = format!(
                                "更新確認に失敗しました。保存済みの配布情報を表示しています。\n{e}"
                            )
                        }
                    }
                }
                Event::Detected(tools) => {
                    self.toolchains = tools;
                    self.detecting = false;
                    self.status = "検出とCプログラムのビルド・実行確認が完了しました".into()
                }
                Event::Installed => {
                    if let Ok(settings) = Settings::load() {
                        self.settings = settings
                    }
                    self.records = self.service.records(&self.settings);
                    self.status =
                        "導入先を更新しました。PATH追加後は新しいターミナルを開いてください".into()
                }
                Event::Message(text) => self.status = text,
            }
        }
        if changed {
            cx.notify();
        }
    }
    fn update_releases(&mut self, cx: &mut Context<Self>) {
        if self.updating {
            return;
        }
        self.updating = true;
        self.status = "GitHubのRelease情報を取得しています…".into();
        let tx = self.tx.clone();
        let service = self.service.clone();
        std::thread::spawn(move || {
            let _ = tx.send(Event::Updates(
                service.check_updates().map_err(|e| format!("{e:#}")),
            ));
        });
        cx.notify();
    }
    fn detect(&mut self, cx: &mut Context<Self>) {
        if self.detecting {
            return;
        }
        self.detecting = true;
        let service = self.service.clone();
        let settings = self.settings.clone();
        let tx = self.tx.clone();
        std::thread::spawn(move || {
            let tools = service.detect_toolchains(&settings);
            let _ = tx.send(Event::Detected(tools));
        });
        cx.notify();
    }
    fn open_install(&mut self, product: &str, window: &mut Window, cx: &mut Context<Self>) {
        let product = product.to_string();
        let settings = self.settings.clone();
        let service = self.service.clone();
        let release = if product == "compiler" {
            self.releases.compiler.clone()
        } else {
            self.releases.plugins.clone()
        };
        let tx = self.tx.clone();
        let view = cx.new(|cx| Installer::new(product, settings, service, release, tx, window, cx));
        window.open_dialog(cx, move |dialog, _, _| {
            dialog
                .title("インストール")
                .w(px(580.))
                .close_button(false)
                .keyboard(false)
                .overlay_closable(false)
                .child(view.clone())
        });
    }
    fn sidebar(&self, window: &mut Window, cx: &mut Context<Self>) -> AnyElement {
        let mut sidebar = v_flex()
            .w(px(242.))
            .h_full()
            .flex_shrink_0()
            .bg(cx.theme().sidebar)
            .border_r_1()
            .border_color(cx.theme().border)
            .p_4()
            .gap_2()
            .child(
                h_flex()
                    .gap_3()
                    .px_2()
                    .py_4()
                    .child(
                        div()
                            .rounded_md()
                            .bg(cx.theme().primary)
                            .text_color(cx.theme().primary_foreground)
                            .px_2()
                            .text_lg()
                            .child("gs"),
                    )
                    .child(
                        v_flex()
                            .child(div().font_weight(FontWeight::SEMIBOLD).child("GScript"))
                            .child(
                                div()
                                    .text_xs()
                                    .text_color(cx.theme().muted_foreground)
                                    .child("Manager"),
                            ),
                    ),
            );
        for (page, label, icon) in [
            (Page::Compiler, "コンパイラ", IconName::SquareTerminal),
            (Page::Editors, "エディター拡張", IconName::Frame),
            (Page::Toolchains, "ツールチェーン", IconName::Settings2),
            (Page::Docs, "ドキュメント", IconName::BookOpen),
        ] {
            sidebar = sidebar.child(
                Button::new(SharedString::from(label))
                    .ghost()
                    .w_full()
                    .justify_start()
                    .icon(icon)
                    .label(label)
                    .selected(self.page == page)
                    .on_click(cx.listener(move |this, _, _, cx| {
                        this.page = page;
                        this.section = 0;
                        this.scroll.set_offset(point(px(0.), px(0.)));
                        cx.notify();
                    })),
            );
        }
        if self.page == Page::Docs {
            sidebar = sidebar.child(Input::new(&self.search).prefix(IconName::Search).small());
            let query = self.search.read(cx).value().to_lowercase();
            let mut nav = v_flex().gap_1();
            let mut group = "";
            for (index, chapter) in self.chapters.iter().enumerate().filter(|(_, d)| {
                format!("{} {}", d.title, d.source)
                    .to_lowercase()
                    .contains(&query)
            }) {
                if group != chapter.group {
                    group = &chapter.group;
                    nav = nav.child(
                        div()
                            .mt_4()
                            .px_2()
                            .text_xs()
                            .font_weight(FontWeight::SEMIBOLD)
                            .child(chapter.group.clone()),
                    );
                }
                nav = nav.child(
                    Button::new(("chapter", index))
                        .ghost()
                        .small()
                        .w_full()
                        .justify_start()
                        .label(chapter.title.clone())
                        .selected(index == self.chapter)
                        .on_click(cx.listener(move |this, _, _, cx| {
                            this.chapter = index;
                            this.section = 0;
                            this.scroll.set_offset(point(px(0.), px(0.)));
                            cx.notify();
                        })),
                );
            }
            sidebar = sidebar.child(div().flex_1().min_h_0().child(nav.overflow_y_scrollbar()));
        } else {
            sidebar = sidebar.child(div().flex_1());
        }
        sidebar = sidebar
            .child(
                Button::new("github")
                    .ghost()
                    .small()
                    .icon(IconName::GitHub)
                    .label("GitHub")
                    .on_click(|_, _, cx| cx.open_url("https://github.com/sofia-gros/gscript")),
            )
            .child(
                div()
                    .px_2()
                    .text_xs()
                    .text_color(cx.theme().muted_foreground)
                    .child(format!("Manager {}", env!("CARGO_PKG_VERSION"))),
            );
        let _ = window;
        sidebar.into_any_element()
    }
    fn product(
        &self,
        id: &'static str,
        name: &str,
        description: &str,
        cx: &mut Context<Self>,
    ) -> AnyElement {
        let release = if id == "compiler" {
            &self.releases.compiler
        } else {
            &self.releases.plugins
        };
        let record = self
            .records
            .iter()
            .filter(|r| r.product == id)
            .max_by_key(|r| semver::Version::parse(&r.version).ok());
        let installed = record
            .map(|r| {
                format!(
                    "{} · {}",
                    if r.prepared {
                        "配置済み / Zedで有効化が必要"
                    } else {
                        "導入済み"
                    },
                    r.version
                )
            })
            .unwrap_or_else(|| "未インストール".into());
        let location = record
            .map(|r| r.location.display().to_string())
            .unwrap_or_else(|| "保存先はインストール時に指定します".into());
        let current = record.is_some_and(|r| r.version == release.version);
        let tag = release.tag.clone();
        let notes = release.notes.clone();
        let path = record.map(|r| r.location.clone());
        let mut buttons = h_flex().justify_between().gap_3().child(
            Button::new(SharedString::from(format!("notes-{id}")))
                .ghost()
                .icon(IconName::File)
                .label("リリースノート")
                .on_click(cx.listener(move |this, _, _, cx| {
                    this.notes = notes.clone();
                    this.notes_title = tag.clone();
                    this.page = Page::Notes;
                    cx.notify();
                })),
        );
        if current {
            buttons = buttons.child(
                Button::new(SharedString::from(format!("open-{id}")))
                    .icon(IconName::FolderOpen)
                    .label("導入先を開く")
                    .on_click(move |_, _, cx| {
                        if let Some(path) = &path {
                            cx.reveal_path(path)
                        }
                    }),
            );
        } else {
            buttons = buttons.child(
                Button::new(SharedString::from(format!("install-{id}")))
                    .primary()
                    .icon(IconName::ArrowDown)
                    .label(if id == "vscode" {
                        if record.is_some() {
                            "VSIXで更新"
                        } else {
                            "VSIXをインストール"
                        }
                    } else if record.is_some() {
                        "更新"
                    } else {
                        "インストール"
                    })
                    .on_click(
                        cx.listener(move |this, _, window, cx| this.open_install(id, window, cx)),
                    ),
            );
        }
        v_flex().gap_4().p_6().border_1().border_color(cx.theme().border).rounded_lg().bg(cx.theme().popover).child(h_flex().gap_3().child(Icon::new(if id=="compiler"{IconName::SquareTerminal}else{IconName::Frame}).size_6()).child(div().text_lg().font_weight(FontWeight::SEMIBOLD).child(name.to_string()))).child(div().text_sm().text_color(cx.theme().muted_foreground).child(description.to_string())).child(h_flex().gap_6().child(v_flex().child(div().text_xs().text_color(cx.theme().muted_foreground).child("配布版")).child(format!("v{}",release.version))).child(v_flex().child(div().text_xs().text_color(cx.theme().muted_foreground).child("状態")).child(installed))).child(div().text_xs().text_color(cx.theme().muted_foreground).child(location)).when(id=="zed",|d|d.child(div().text_xs().child("Zed → Extensions → Install Dev Extensionで、導入先内のgscript-zedを選択してください。Rust・Gitが必要です。"))).when(id=="vscode",|d|d.child(div().text_xs().child("ReleaseのVSIXを取得・検証し、code --install-extensionで指定先のvscode-extensionsへ導入します。起動時も code --extensions-dir <同じパス> を指定してください。"))).child(buttons).into_any_element()
    }
    fn docs_view(&self, window: &mut Window, cx: &mut Context<Self>) -> AnyElement {
        let chapter = &self.chapters[self.chapter];
        let sections = doc_sections(&chapter.source);
        let anchors: Vec<_> = sections
            .iter()
            .map(|_| ScrollAnchor::for_handle(self.scroll.clone()))
            .collect();
        let mut links = vec![];
        let mut reader = v_flex().gap_5().flex_1().min_w_0().child(
            div()
                .text_xs()
                .text_color(cx.theme().muted_foreground)
                .child(format!(
                    "{} / {} · v0.6.0 · オフライン",
                    chapter.group, chapter.title
                )),
        );
        if chapter.id == "comparison.md" {
            let mut tabs = h_flex().gap_2();
            for (i, label) in ["Go", "JavaScript", "GScript"].into_iter().enumerate() {
                tabs = tabs.child(
                    Button::new(("language", i))
                        .ghost()
                        .label(label)
                        .selected(self.language == i)
                        .on_click(cx.listener(move |this, _, _, cx| {
                            this.language = i;
                            cx.notify();
                        })),
                );
            }
            reader = reader.child(tabs);
        }
        let regex = Regex::new(r"\[([^\]]+)\]\(([^)]+)\)").unwrap();
        for (index, (_, source)) in sections.iter().enumerate() {
            let raw = if chapter.id == "comparison.md" {
                filter_comparison(source, self.language)
            } else {
                source.clone()
            };
            let markdown = regex
                .replace_all(&raw, |captures: &regex::Captures| {
                    let target = captures[2].split('#').next().unwrap_or("");
                    if let Some(index) = self.chapters.iter().position(|d| d.id == target) {
                        links.push(index);
                        captures[1].to_string()
                    } else {
                        captures[0].to_string()
                    }
                })
                .replace("```gs\n", "```go\n");
            reader = reader.child(
                div()
                    .id(("doc-section", index))
                    .anchor_scroll(Some(anchors[index].clone()))
                    .child(
                        TextView::markdown(
                            SharedString::from(format!(
                                "markdown-{}-{index}-{}",
                                chapter.id, self.language
                            )),
                            markdown.to_string(),
                            window,
                            cx,
                        )
                        .selectable(true),
                    ),
            );
        }
        links.sort_unstable();
        links.dedup();
        if !links.is_empty() {
            reader = reader.child(
                div()
                    .mt_4()
                    .text_xs()
                    .text_color(cx.theme().muted_foreground)
                    .child("関連するページ"),
            );
            for index in links {
                reader = reader.child(
                    Button::new(("related", index))
                        .ghost()
                        .justify_start()
                        .icon(IconName::ArrowRight)
                        .label(self.chapters[index].title.clone())
                        .on_click(cx.listener(move |this, _, _, cx| {
                            this.chapter = index;
                            this.section = 0;
                            this.scroll.set_offset(point(px(0.), px(0.)));
                            cx.notify();
                        })),
                );
            }
        }
        let mut pagination = h_flex().justify_between().gap_4().mt_6();
        if self.chapter > 0 {
            pagination = pagination.child(
                Button::new("previous-page")
                    .icon(IconName::ArrowLeft)
                    .label(self.chapters[self.chapter - 1].title.clone())
                    .on_click(cx.listener(|this, _, _, cx| {
                        this.chapter -= 1;
                        this.section = 0;
                        this.scroll.set_offset(point(px(0.), px(0.)));
                        cx.notify();
                    })),
            );
        }
        if self.chapter + 1 < self.chapters.len() {
            pagination = pagination.child(
                Button::new("next-page")
                    .icon(IconName::ArrowRight)
                    .label(self.chapters[self.chapter + 1].title.clone())
                    .on_click(cx.listener(|this, _, _, cx| {
                        this.chapter += 1;
                        this.section = 0;
                        this.scroll.set_offset(point(px(0.), px(0.)));
                        cx.notify();
                    })),
            );
        }
        let url = format!(
            "https://github.com/sofia-gros/gscript/blob/main/docs/guide/{}",
            chapter.id
        );
        reader = reader
            .child(pagination)
            .child(
                Button::new("source-markdown")
                    .ghost()
                    .icon(IconName::GitHub)
                    .label("同じMarkdownをGitHubで読む")
                    .on_click(move |_, _, cx| cx.open_url(&url)),
            )
            .child(
                Button::new("export-docs")
                    .ghost()
                    .icon(IconName::FolderOpen)
                    .label("Markdownの保存先を選んで書き出す")
                    .on_click(cx.listener(|this, _, window, cx| this.open_export(window, cx))),
            );
        let mut toc = v_flex()
            .w(px(185.))
            .flex_shrink_0()
            .gap_1()
            .border_l_1()
            .border_color(cx.theme().border)
            .pl_4()
            .child(div().text_xs().mb_3().child("このページの内容"));
        for (index, (title, _)) in sections.iter().enumerate() {
            let anchor = anchors[index].clone();
            toc = toc.child(
                Button::new(("toc", index))
                    .ghost()
                    .small()
                    .justify_start()
                    .w_full()
                    .selected(index == self.section)
                    .label(title.clone())
                    .on_click(cx.listener(move |this, _, window, cx| {
                        this.section = index;
                        anchor.scroll_to(window, cx);
                        cx.notify();
                    })),
            );
        }
        h_flex()
            .items_start()
            .gap_8()
            .child(reader)
            .child(toc)
            .into_any_element()
    }
    fn open_export(&mut self, window: &mut Window, cx: &mut Context<Self>) {
        let picker = cx.prompt_for_paths(PathPromptOptions {
            files: false,
            directories: true,
            multiple: false,
            prompt: Some("ドキュメントの保存先".into()),
        });
        let _ = window;
        cx.spawn(async move |weak, cx| {
            if let Ok(Ok(Some(paths))) = picker.await {
                if let Some(path) = paths.first() {
                    let path = path.clone();
                    let _ = weak.update(cx, |this, cx| {
                        this.settings.docs_dir = path;
                        let service = this.service.clone();
                        let settings = this.settings.clone();
                        let tx = this.tx.clone();
                        std::thread::spawn(move || {
                            let result =
                                settings.save().and_then(|_| service.export_docs(&settings));
                            let _ = tx.send(Event::Message(match result {
                                Ok(p) => format!("Markdownを書き出しました: {}", p.display()),
                                Err(e) => format!("書き出しに失敗しました: {e:#}"),
                            }));
                        });
                        cx.notify();
                    });
                }
            }
        })
        .detach();
    }
}
impl Render for Manager {
    fn render(&mut self, window: &mut Window, cx: &mut Context<Self>) -> impl IntoElement {
        let title = match self.page {
            Page::Compiler => "コンパイラ",
            Page::Editors => "エディター拡張",
            Page::Toolchains => "ツールチェーン",
            Page::Docs => "ドキュメント",
            Page::Notes => "リリースノート",
        };
        let mut body = v_flex().gap_5().w_full().max_w(px(1160.)).mx_auto().p_8();
        if self.page == Page::Docs {
            body = body.child(self.docs_view(window, cx));
        } else if self.page == Page::Notes {
            body = body
                .child(div().text_2xl().child(self.notes_title.clone()))
                .child(
                    TextView::markdown("release-notes", self.notes.clone(), window, cx)
                        .selectable(true),
                );
        } else {
            body = body.child(
                div()
                    .text_2xl()
                    .font_weight(FontWeight::SEMIBOLD)
                    .child(title),
            );
            if self.page != Page::Toolchains {
                body = body.child(
                    h_flex()
                        .gap_4()
                        .justify_between()
                        .child(
                            div()
                                .text_sm()
                                .text_color(cx.theme().muted_foreground)
                                .child(self.status.clone()),
                        )
                        .child(
                            Button::new("check-updates")
                                .icon(IconName::Redo2)
                                .label(if self.updating {
                                    "確認中…"
                                } else {
                                    "更新を確認"
                                })
                                .disabled(self.updating)
                                .on_click(cx.listener(|this, _, _, cx| this.update_releases(cx))),
                        ),
                );
            }
            match self.page {
                Page::Compiler => {
                    body = body
                        .child(self.product(
                            "compiler",
                            "GScript Compiler",
                            "GSをJS / TSまたはネイティブへコンパイルします。",
                            cx,
                        ))
                        .child(
                            Button::new("native-tools")
                                .ghost()
                                .icon(IconName::Settings2)
                                .label("ネイティブ用ツールチェーンを管理")
                                .on_click(cx.listener(|this, _, _, cx| {
                                    this.page = Page::Toolchains;
                                    cx.notify();
                                })),
                        );
                }
                Page::Editors => {
                    body = body
                        .child(self.product(
                            "vscode",
                            "Visual Studio Code",
                            "VSIXと同梱のGS言語サーバーを導入します。",
                            cx,
                        ))
                        .child(self.product(
                            "zed",
                            "Zed",
                            "開発拡張のファイルを配置し、Zed内の有効化手順を案内します。",
                            cx,
                        ));
                }
                Page::Toolchains => {
                    body=body.child(div().text_sm().text_color(cx.theme().muted_foreground).child("Clang・GCC・Zigのいずれか1つが必要です。検出時にはCプログラムのビルドと実行も確認します。JS / TS出力だけなら不要です。")).child(Button::new("detect-toolchains").icon(IconName::Search).label(if self.detecting{"検査中…"}else{"検出する"}).disabled(self.detecting).on_click(cx.listener(|this,_,_,cx|this.detect(cx))));
                    body = body.child(
                        Button::new("native-build-guide")
                            .ghost()
                            .icon(IconName::BookOpen)
                            .label("GSをコンパイルして実行する方法")
                            .on_click(cx.listener(|this, _, _, cx| {
                                if let Some(index) =
                                    this.chapters.iter().position(|d| d.id == "native-build.md")
                                {
                                    this.chapter = index;
                                    this.section = 0;
                                    this.page = Page::Docs;
                                    this.scroll.set_offset(point(px(0.), px(0.)));
                                    cx.notify();
                                }
                            })),
                    );
                    for (name, label) in [("clang", "Clang"), ("gcc", "GCC"), ("zig", "Zig")] {
                        let tool = self.toolchains.iter().find(|t| t.name == name);
                        let status = tool
                            .map(|t| {
                                format!(
                                    "{}\n{}",
                                    t.version,
                                    t.executable
                                        .as_ref()
                                        .map(|p| p.display().to_string())
                                        .unwrap_or_default()
                                )
                            })
                            .unwrap_or_else(|| "未確認".into());
                        body = body.child(
                            h_flex()
                                .gap_4()
                                .items_center()
                                .p_5()
                                .border_1()
                                .border_color(cx.theme().border)
                                .rounded_lg()
                                .child(Icon::new(IconName::Settings2))
                                .child(
                                    v_flex().flex_1().child(label).child(
                                        div()
                                            .text_xs()
                                            .text_color(cx.theme().muted_foreground)
                                            .child(status),
                                    ),
                                )
                                .child(
                                    Button::new(SharedString::from(format!("install-{name}")))
                                        .icon(IconName::ArrowDown)
                                        .label("インストール")
                                        .on_click(cx.listener(move |this, _, window, cx| {
                                            this.open_install(name, window, cx)
                                        })),
                                ),
                        );
                    }
                    body = body.child(
                        div()
                            .text_xs()
                            .text_color(cx.theme().muted_foreground)
                            .child(self.status.clone()),
                    );
                }
                _ => {}
            }
        }
        h_flex()
            .relative()
            .size_full()
            .bg(cx.theme().background)
            .text_color(cx.theme().foreground)
            .child(self.sidebar(window, cx))
            .child(
                v_flex()
                    .flex_1()
                    .min_w_0()
                    .h_full()
                    .child(
                        h_flex()
                            .h(px(56.))
                            .flex_shrink_0()
                            .px_8()
                            .items_center()
                            .justify_between()
                            .border_b_1()
                            .border_color(cx.theme().border)
                            .child(format!("GScript / {title}"))
                            .child(
                                Button::new("appearance")
                                    .ghost()
                                    .icon(IconName::Sun)
                                    .on_click(|_, window, cx| {
                                        let mode = if cx.theme().mode.is_dark() {
                                            ThemeMode::Light
                                        } else {
                                            ThemeMode::Dark
                                        };
                                        Theme::change(mode, Some(window), cx);
                                        apply_palette(cx)
                                    }),
                            ),
                    )
                    .child(
                        div()
                            .id("main-content")
                            .flex_1()
                            .min_h_0()
                            .overflow_y_scroll()
                            .track_scroll(&self.scroll)
                            .vertical_scrollbar(&self.scroll)
                            .child(body),
                    ),
            )
            // Root stores overlay state, but its child view must draw these layers.
            // Otherwise open_dialog captures focus without displaying the installer.
            .children(Root::render_sheet_layer(window, cx))
            .children(Root::render_dialog_layer(window, cx))
            .children(Root::render_notification_layer(window, cx))
    }
}
fn doc_sections(source: &str) -> Vec<(String, String)> {
    let mut sections = vec![];
    let mut title = "概要".to_string();
    let mut text = String::new();
    let mut code = false;
    for line in source.lines() {
        if line.starts_with("```") {
            code = !code
        }
        if !code && line.starts_with("## ") {
            if !text.trim().is_empty() {
                sections.push((title, text));
            }
            title = line.trim_start_matches("## ").into();
            text = String::new();
        }
        text.push_str(line);
        text.push('\n');
    }
    if !text.trim().is_empty() {
        sections.push((title, text));
    }
    sections
}
fn filter_comparison(source: &str, language: usize) -> String {
    let names = ["Go", "JavaScript", "GScript"];
    let regex = Regex::new(r"(?m)^### (Go|JavaScript|GScript)\n+```[^\n]*\n(?s:.*?)\n```").unwrap();
    regex
        .replace_all(source, |captures: &regex::Captures| {
            if captures[1] == *names[language] {
                captures[0].to_string()
            } else {
                String::new()
            }
        })
        .to_string()
}

enum InstallEvent {
    Progress(Progress),
    Done(Result<String, String>),
}
#[derive(PartialEq)]
enum InstallStep {
    Configure,
    Running,
    Done,
    Failed,
}
struct Installer {
    product: String,
    settings: Settings,
    service: Service,
    release: service::Release,
    parent: Sender<Event>,
    path: Entity<InputState>,
    add_path: bool,
    system_path: bool,
    step: InstallStep,
    started: Option<Instant>,
    finished: Option<Duration>,
    percent: f32,
    message: String,
    rx: Receiver<InstallEvent>,
    tx: Sender<InstallEvent>,
}
impl Installer {
    fn new(
        product: String,
        settings: Settings,
        service: Service,
        release: service::Release,
        parent: Sender<Event>,
        window: &mut Window,
        cx: &mut Context<Self>,
    ) -> Self {
        let root = if product == "compiler" {
            &settings.compiler_dir
        } else if ["vscode", "zed"].contains(&product.as_str()) {
            &settings.extensions_dir
        } else {
            &settings.toolchains_dir
        };
        let path = cx.new(|cx| {
            let mut state = InputState::new(window, cx);
            state.set_value(root.display().to_string(), window, cx);
            state
        });
        let (tx, rx) = mpsc::channel();
        cx.spawn(async move |weak, cx| {
            loop {
                Timer::after(Duration::from_millis(100)).await;
                if weak
                    .update(cx, |this, cx| {
                        let mut changed = this.step == InstallStep::Running;
                        while let Ok(event) = this.rx.try_recv() {
                            changed = true;
                            match event {
                                InstallEvent::Progress(p) => {
                                    this.percent = this.percent.max(p.percent).min(99.0);
                                    this.message = p.message
                                }
                                InstallEvent::Done(result) => {
                                    this.finished = this.started.map(|start| start.elapsed());
                                    match result {
                                        Ok(text) => {
                                            this.step = InstallStep::Done;
                                            this.percent = 100.0;
                                            this.message = text;
                                            let _ = this.parent.send(Event::Installed);
                                        }
                                        Err(error) => {
                                            this.step = InstallStep::Failed;
                                            this.message = error
                                        }
                                    }
                                }
                            }
                        }
                        if changed {
                            cx.notify();
                        }
                    })
                    .is_err()
                {
                    break;
                }
            }
        })
        .detach();
        Self {
            product,
            settings,
            service,
            release,
            parent,
            path,
            add_path: true,
            system_path: false,
            step: InstallStep::Configure,
            started: None,
            finished: None,
            percent: 0.0,
            message: String::new(),
            rx,
            tx,
        }
    }
    fn choose_path(&mut self, window: &mut Window, cx: &mut Context<Self>) {
        let picker = cx.prompt_for_paths(PathPromptOptions {
            files: false,
            directories: true,
            multiple: false,
            prompt: Some("インストール先を選択".into()),
        });
        cx.spawn_in(window, async move |weak, cx| match picker.await {
            Ok(Ok(Some(paths))) => {
                if let Some(path) = paths.first() {
                    let value = path.display().to_string();
                    let _ = weak.update_in(cx, |this, window, cx| {
                        this.path
                            .update(cx, |input, cx| input.set_value(value, window, cx));
                        cx.notify();
                    });
                }
            }
            Ok(Err(error)) => {
                let _ = weak.update_in(cx, |this, _, cx| {
                    this.message = format!(
                        "フォルダー選択に失敗しました。入力欄へ絶対パスを指定できます。{error}"
                    );
                    cx.notify();
                });
            }
            _ => {}
        })
        .detach();
    }
    fn start(&mut self, cx: &mut Context<Self>) {
        let root = PathBuf::from(self.path.read(cx).value().as_str());
        if let Err(error) = service::validate_destination(&root) {
            self.message = error.to_string();
            cx.notify();
            return;
        }
        self.settings.path_scope = if !self.add_path {
            PathScope::None
        } else if self.system_path {
            PathScope::System
        } else {
            PathScope::User
        };
        match self.product.as_str() {
            "compiler" => self.settings.compiler_dir = root,
            "vscode" | "zed" => self.settings.extensions_dir = root,
            _ => self.settings.toolchains_dir = root,
        };
        self.step = InstallStep::Running;
        self.started = Some(Instant::now());
        self.finished = None;
        self.percent = 0.0;
        self.message = "開始しています…".into();
        let service = self.service.clone();
        let settings = self.settings.clone();
        let product = self.product.clone();
        let release = self.release.clone();
        let tx = self.tx.clone();
        std::thread::spawn(move || {
            let report = |p| {
                let _ = tx.send(InstallEvent::Progress(p));
            };
            let result = (|| -> anyhow::Result<String> {
                settings.save()?;
                if ["compiler", "vscode", "zed"].contains(&product.as_str()) {
                    let record = service.install(&product, &release, &settings, &report)?;
                    if record.prepared {
                        Ok(format!(
                            "配置が完了しました。ZedのExtensions → Install Dev Extensionで、{} 内のgscript-zedを選択してください。",
                            record.location.display()
                        ))
                    } else {
                        Ok(format!(
                            "インストールが完了しました。\n保存先: {}\nPATHを追加した場合は新しいターミナルを開いてください。",
                            record.location.display()
                        ))
                    }
                } else {
                    service.install_toolchain(&product, &settings, &report)
                }
            })();
            let _ = tx.send(InstallEvent::Done(result.map_err(|e| format!("{e:#}"))));
        });
        cx.notify();
    }
}
impl Render for Installer {
    fn render(&mut self, _window: &mut Window, cx: &mut Context<Self>) -> impl IntoElement {
        let mut content = v_flex().gap_4().w_full();
        let is_plugin = ["vscode", "zed"].contains(&self.product.as_str());
        if self.step == InstallStep::Configure {
            content = content
                .child(div().text_sm().child(format!(
                    "{}{}",
                    self.product,
                    if ["compiler", "vscode", "zed"].contains(&self.product.as_str()) {
                        format!(" v{}", self.release.version)
                    } else {
                        String::new()
                    }
                )))
                .child(
                    div()
                        .text_xs()
                        .text_color(cx.theme().muted_foreground)
                        .child("インストール先"),
                )
                .child(
                    h_flex()
                        .gap_2()
                        .child(div().flex_1().min_w_0().child(Input::new(&self.path)))
                        .child(
                            Button::new("choose-install-directory")
                                .icon(IconName::FolderOpen)
                                .label("選択")
                                .on_click(
                                    cx.listener(|this, _, window, cx| this.choose_path(window, cx)),
                                ),
                        ),
                );
            if !is_plugin {
                content=content.child(Checkbox::new("add-path").checked(self.add_path).label("PATHへ追加する").on_click(cx.listener(|this,checked,_,cx|{this.add_path=*checked;cx.notify();}))).child(div().text_xs().text_color(cx.theme().muted_foreground).child(if cfg!(windows){"既定はユーザーPATHです。新しいターミナルで有効になります。"}else{"ユーザーのbash / zsh設定へ追加します。既存設定のバックアップを保存します。"}));
                if cfg!(windows) {
                    content = content.child(
                        Checkbox::new("system-path")
                            .checked(self.system_path)
                            .disabled(!self.add_path)
                            .label("システムPATHへ追加（管理者権限が必要）")
                            .on_click(cx.listener(|this, checked, _, cx| {
                                this.system_path = *checked;
                                cx.notify();
                            })),
                    );
                }
            } else {
                content=content.child(div().text_xs().text_color(cx.theme().muted_foreground).child("拡張機能にPATH追加は不要です。VSCodeは選択先のvscode-extensionsを使用し、Zedは選択先を開発拡張として参照します。"));
            }
            if ["clang", "gcc"].contains(&self.product.as_str()) {
                content=content.child(div().text_xs().text_color(cx.theme().muted_foreground).child("Clang / GCCはOSのパッケージ管理から導入します。ツール本体の保存先はOS側の規則に従い、認証が必要な場合があります。任意フォルダーへ配置する場合はZigを選べます。"));
            }
            if !self.message.is_empty() {
                content = content.child(
                    div()
                        .text_sm()
                        .text_color(cx.theme().danger)
                        .child(self.message.clone()),
                );
            }
            content = content.child(
                h_flex()
                    .justify_end()
                    .gap_2()
                    .child(
                        Button::new("cancel-install")
                            .label("キャンセル")
                            .on_click(|_, window, cx| window.close_dialog(cx)),
                    )
                    .child(
                        Button::new("next-install")
                            .primary()
                            .icon(IconName::ArrowRight)
                            .label("次へ")
                            .on_click(cx.listener(|this, _, _, cx| this.start(cx))),
                    ),
            );
        } else {
            let elapsed = self
                .finished
                .unwrap_or_else(|| self.started.map(|s| s.elapsed()).unwrap_or_default());
            let secs = elapsed.as_secs();
            content = content
                .child(
                    h_flex()
                        .gap_3()
                        .items_center()
                        .child(Icon::new(match self.step {
                            InstallStep::Done => IconName::CircleCheck,
                            InstallStep::Failed => IconName::TriangleAlert,
                            _ => IconName::ArrowDown,
                        }))
                        .child(div().text_sm().child(match self.step {
                            InstallStep::Done => "完了",
                            InstallStep::Failed => "インストールに失敗しました",
                            _ => "ダウンロード・インストール中",
                        })),
                )
                .child(
                    h_flex()
                        .justify_between()
                        .text_sm()
                        .child(format!("経過時間 {:02}:{:02}", secs / 60, secs % 60))
                        .child(format!("{:.0}%", self.percent)),
                )
                .child(ProgressBar::new().value(self.percent))
                .child(div().text_sm().child(self.message.clone()));
            if self.step != InstallStep::Running {
                content = content.child(
                    h_flex()
                        .justify_end()
                        .gap_2()
                        .when(self.step == InstallStep::Failed, |row| {
                            row.child(Button::new("retry-settings").label("設定へ戻る").on_click(
                                cx.listener(|this, _, _, cx| {
                                    this.step = InstallStep::Configure;
                                    this.message.clear();
                                    cx.notify();
                                }),
                            ))
                        })
                        .child(
                            Button::new("finish-install")
                                .primary()
                                .label("閉じる")
                                .on_click(|_, window, cx| window.close_dialog(cx)),
                        ),
                );
            }
        }
        content
    }
}
pub fn run() {
    Application::new()
        .with_assets(gpui_component_assets::Assets)
        .run(|cx| {
            gpui_component::init(cx);
            Theme::change(ThemeMode::Dark, None, cx);
            apply_palette(cx);
            let theme = Theme::global_mut(cx);
            theme.font_size = px(14.);
            theme.font_family = if cfg!(windows) {
                "Yu Gothic UI".into()
            } else if cfg!(target_os = "macos") {
                "Hiragino Sans".into()
            } else {
                "Noto Sans CJK JP".into()
            };
            cx.on_window_closed(|cx| {
                if cx.windows().is_empty() {
                    cx.quit();
                }
            })
            .detach();
            let options = WindowOptions {
                window_bounds: Some(WindowBounds::Windowed(Bounds::centered(
                    None,
                    size(px(1320.), px(900.)),
                    cx,
                ))),
                window_min_size: Some(size(px(900.), px(640.))),
                titlebar: Some(TitlebarOptions {
                    title: Some("GScript Manager".into()),
                    ..Default::default()
                }),
                ..Default::default()
            };
            cx.open_window(options, |window, cx| {
                let manager = cx.new(|cx| Manager::new(window, cx));
                cx.new(|cx| Root::new(manager, window, cx))
            })
            .expect("open GScript Manager window");
            cx.activate(true);
        });
}

// Same semantic palette as ../tokens.css, applied to native component themes.
fn apply_palette(cx: &mut App) {
    let dark = cx.theme().mode.is_dark();
    let theme = Theme::global_mut(cx);
    let c = &mut theme.colors;
    c.background = rgb(if dark { 0x101212 } else { 0xf3f4ef }).into();
    c.foreground = rgb(if dark { 0xedf0eb } else { 0x252d20 }).into();
    c.popover = rgb(if dark { 0x191c1b } else { 0xffffff }).into();
    c.popover_foreground = c.foreground;
    c.sidebar = rgb(if dark { 0x141616 } else { 0xf9faf6 }).into();
    c.sidebar_foreground = c.foreground;
    c.border = rgb(if dark { 0x2c302e } else { 0xdfe4d8 }).into();
    c.sidebar_border = c.border;
    c.muted = rgb(if dark { 0x222624 } else { 0xe9ece4 }).into();
    c.muted_foreground = rgb(if dark { 0x8b948d } else { 0x727e69 }).into();
    c.primary = rgb(if dark { 0xd3ef8e } else { 0xb9d879 }).into();
    c.primary_hover = rgb(if dark { 0xe1ff9b } else { 0xabc96c }).into();
    c.primary_active = c.primary_hover;
    c.primary_foreground = rgb(0x182014).into();
    c.secondary = rgb(if dark { 0x252d20 } else { 0xe9efdf }).into();
    c.secondary_foreground = c.foreground;
    c.secondary_hover = c.muted;
    c.secondary_active = c.secondary;
    c.accent = c.secondary;
    c.accent_foreground = c.foreground;
    c.sidebar_accent = c.secondary;
    c.sidebar_accent_foreground = c.foreground;
    c.ring = c.primary;
}
