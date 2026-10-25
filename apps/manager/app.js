'use strict';
// Presentation adapter. Installation and update discovery are simulated in this HTML prototype.
const documents=window.GSCRIPT_DOCS.documents;
const catalog=[
 {id:'compiler',name:'GScript Compiler',icon:'gs',description:'JavaScript / TypeScript変換とネイティブAOT',release:'v0.6.0',method:'スタンドアロンCLI'},
 {id:'vscode',name:'Visual Studio Code',icon:'⋈',description:'補完・型診断・ハイライト・定義ジャンプ',release:'plugin-v0.6.0',method:'VSIXパッケージ'},
 {id:'zed',name:'Zed',icon:'Z',description:'補完・型診断・ハイライト・定義ジャンプ',release:'plugin-v0.6.0',method:'開発拡張 + GS言語サーバー'}
];
const toolchains=[{id:'clang',name:'Clang',description:'対象OSのSDK・リンカーも確認します。'},{id:'gcc',name:'GCC',description:'WindowsではMinGW等の対象環境を確認します。'},{id:'zig',name:'Zig',description:'Cコンパイラとして使用できます。検証版は0.15.2です。'}];
const installed=new Set();const dialog=document.querySelector('#install-dialog');
let currentDoc='introduction.md',selected=null,busy=false,toastTimer,tocObserver;
const routeFor=(id,section='')=>'#documents/'+id+(section?'?section='+encodeURIComponent(section):'');
function toast(message){const el=document.querySelector('#toast');el.textContent=message;el.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.hidden=true,4000);}
function renderProducts(){
 const card=t=>`<article class="product-panel"><div class="product-top"><div class="product-icon" aria-hidden="true">${t.icon}</div><div><h2>${t.name}</h2><p>${t.description}</p></div><span class="badge">${installed.has(t.id)?'導入済み · デモ':'未インストール · デモ'}</span></div><dl class="product-details"><div><dt>配布バージョン</dt><dd>v0.6.0</dd></div><div><dt>導入形式</dt><dd>${t.method}</dd></div>${t.id==='compiler'?'<div><dt>対応環境</dt><dd>Windows / macOS / Linux</dd></div>':''}</dl><div class="product-actions"><a href="https://github.com/sofia-gros/gscript/releases/tag/${t.release}" target="_blank" rel="noreferrer">リリースノート ↗</a><button class="button ${installed.has(t.id)?'':'primary'}" data-install="${t.id}">${installed.has(t.id)?'再セットアップ':'インストール'}</button></div></article>`;
 document.querySelector('#compiler-list').innerHTML=card(catalog[0]);
 document.querySelector('#editor-list').innerHTML=catalog.slice(1).map(card).join('');
 document.querySelector('#toolchain-list').innerHTML=toolchains.map(t=>`<div class="toolchain-row"><div class="toolchain-name"><strong>${t.name}</strong><p>${t.description}</p></div><span class="toolchain-state" data-detection="${t.id}">${installed.has(t.id)?'導入済み（デモ）':'未確認'}</span><button class="button" data-install="${t.id}">${installed.has(t.id)?'再セットアップ':'インストール'}</button></div>`).join('');
}
function closeMenu(){document.querySelector('.sidebar').classList.remove('open');document.querySelector('#menu-toggle').setAttribute('aria-expanded','false');}
function navigate(){
 const [path,query='']=location.hash.slice(1).split('?');const [requested,id]=path.split('/');const page=['compiler','editors','toolchains','documents'].includes(requested)?requested:'compiler';
 document.querySelectorAll('.page').forEach(el=>el.hidden=el.id!==page);
 document.querySelectorAll('[data-page]').forEach(el=>{if(el.dataset.page===page)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');});
 document.querySelector('#docs-navigation').hidden=page!=='documents';
 document.querySelector('#breadcrumb').textContent={compiler:'コンパイラ',editors:'エディター拡張',toolchains:'ツールチェーン',documents:'ドキュメント'}[page];
 if(page==='documents'){const target=documents.some(d=>d.id===id)?id:'introduction.md';openDocument(target,new URLSearchParams(query).get('section')||'');}
 else window.scrollTo(0,0);
 closeMenu();
}
function renderDocList(query=''){
 const list=document.querySelector('#docs-list');list.replaceChildren();let group='';
 for(const doc of documents.filter(d=>(d.title+' '+d.source).toLocaleLowerCase().includes(query.toLocaleLowerCase()))){
  if(group!==doc.group){group=doc.group;const label=document.createElement('div');label.className='doc-nav-group';label.textContent=group;list.append(label);}
  const link=document.createElement('a');link.className='doc-link';link.href=routeFor(doc.id);link.textContent=doc.title;if(doc.id===currentDoc)link.setAttribute('aria-current','page');list.append(link);
 }
 if(!list.children.length){const empty=document.createElement('p');empty.className='help';empty.textContent='一致するページがありません。';list.append(empty);}
}
function decorateCode(content){
 content.querySelectorAll('pre').forEach(pre=>{const block=document.createElement('div');block.className='code-block';pre.before(block);const header=document.createElement('div');header.className='code-header';const label=document.createElement('span');label.textContent=({gs:'GScript',go:'Go',js:'JavaScript',sh:'Shell',text:'出力'})[pre.dataset.language]||pre.dataset.language||'コード';const copy=document.createElement('button');copy.className='copy-code';copy.type='button';copy.textContent='コピー';copy.setAttribute('aria-label',label.textContent+'のコードをコピー');copy.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(pre.textContent);copy.textContent='コピー済み';setTimeout(()=>copy.textContent='コピー',1500);}catch{toast('このブラウザーではコピーできません。コードを選択してコピーしてください。');}});header.append(label,copy);block.append(header,pre);});
 // Compare the same example in three languages without tripling the reader's scroll.
 content.querySelectorAll('h3').forEach(heading=>{
  if(heading.textContent!=='Go')return;
  const headings=[heading];let next=heading.nextElementSibling;
  while(next&&next.tagName!=='H2'){if(next.tagName==='H3')headings.push(next);next=next.nextElementSibling;}
  if(headings.length!==3||headings[1].textContent!=='JavaScript'||headings[2].textContent!=='GScript'||headings.some(h=>!h.nextElementSibling?.classList.contains('code-block')))return;
  const wrap=document.createElement('div');wrap.className='comparison-example';heading.before(wrap);const tabs=document.createElement('div');tabs.className='code-tabs';tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','コード例の言語');wrap.append(tabs);
  const tabButtons=[];const panels=[];
  headings.forEach((h,i)=>{const panel=h.nextElementSibling;const label=h.textContent;h.remove();const tab=document.createElement('button');tab.textContent=label;tab.setAttribute('role','tab');const unique='example-'+content.querySelectorAll('.comparison-example').length+'-'+i;tab.id=unique+'-tab';panel.id=unique+'-panel';tab.setAttribute('aria-controls',panel.id);panel.setAttribute('role','tabpanel');panel.setAttribute('aria-labelledby',tab.id);tabs.append(tab);wrap.append(panel);tabButtons.push(tab);panels.push(panel);});
  function select(index){tabButtons.forEach((tab,i)=>{tab.setAttribute('aria-selected',String(i===index));tab.tabIndex=i===index?0:-1;panels[i].hidden=i!==index;});}
  tabButtons.forEach((tab,i)=>{tab.addEventListener('click',()=>select(i));tab.addEventListener('keydown',event=>{let target;if(event.key==='ArrowRight')target=(i+1)%3;else if(event.key==='ArrowLeft')target=(i+2)%3;else if(event.key==='Home')target=0;else if(event.key==='End')target=2;else return;event.preventDefault();select(target);tabButtons[target].focus();});});select(2);
 });
}
function openDocument(id,fragment=''){
 const doc=documents.find(d=>d.id===id);if(!doc)return;currentDoc=id;const content=document.querySelector('#docs-content');content.innerHTML=doc.html;
 const slugCounts=new Map();content.querySelectorAll('h1,h2,h3').forEach(h=>{const base=h.textContent.toLowerCase().replace(/[^\p{L}\p{N}_\- ]/gu,'').replaceAll(' ','-');const count=slugCounts.get(base)||0;slugCounts.set(base,count+1);h.id=base+(count?'-'+count:'');});
 content.querySelectorAll('a[href]').forEach(link=>{const url=new URL(link.getAttribute('href'),'https://offline.invalid/docs/guide/'+id);const local=decodeURIComponent(url.pathname.replace(/^\/docs\/guide\//,''));if(url.origin==='https://offline.invalid'&&documents.some(d=>d.id===local))link.href=routeFor(local,decodeURIComponent(url.hash.slice(1)));else if(!['https:','http:','mailto:'].includes(url.protocol))link.removeAttribute('href');else{if(url.origin==='https://offline.invalid')link.href='https://github.com/sofia-gros/gscript/blob/main'+url.pathname+url.hash;link.target='_blank';link.rel='noreferrer noopener';link.title='外部リンク（オンライン接続が必要）';}});
 decorateCode(content);renderDocList(document.querySelector('#docs-search').value);document.querySelector('#doc-group').textContent=doc.group;document.querySelector('#source-link').href='https://github.com/sofia-gros/gscript/blob/main/docs/guide/'+id;
 const toc=document.querySelector('#doc-toc');toc.replaceChildren();content.querySelectorAll('h2').forEach(h=>{const a=document.createElement('a');a.href=routeFor(id,h.id);a.textContent=h.textContent;toc.append(a);});
 tocObserver?.disconnect();tocObserver=new IntersectionObserver(entries=>{for(const entry of entries){if(entry.isIntersecting)toc.querySelectorAll('a').forEach(a=>{if(a.hash===routeFor(id,entry.target.id))a.setAttribute('aria-current','location');else a.removeAttribute('aria-current');});}},{rootMargin:'-80px 0px -60% 0px'});content.querySelectorAll('h2').forEach(h=>tocObserver.observe(h));
 const index=documents.findIndex(d=>d.id===id);const pagination=document.querySelector('#doc-pagination');pagination.replaceChildren();for(const [offset,label,cls] of [[-1,'前のページ','previous'],[1,'次のページ','next']]){const d=documents[index+offset];if(!d)continue;const a=document.createElement('a');a.href=routeFor(d.id);a.className=cls;const small=document.createElement('small');small.textContent=label;const title=document.createElement('span');title.textContent=(offset===-1?'← ':'')+d.title+(offset===1?' →':'');a.append(small,title);pagination.append(a);}
 if(fragment)requestAnimationFrame(()=>document.getElementById(fragment)?.scrollIntoView({block:'start'}));else window.scrollTo(0,0);
}
function syncPlatform(){document.querySelector('#windows-options').hidden=!document.querySelector('#platform').value.startsWith('Windows');}
function openInstall(id){if(busy)return;selected=id;const tool=[...catalog,...toolchains].find(t=>t.id===id);document.querySelector('#install-product').textContent=tool.name+(catalog.includes(tool)?' · v0.6.0':'');document.querySelector('#install-help').textContent=id==='zed'?'Zedは開発拡張として導入します。アプリ版ではRust・Git等を確認し、Zed内の操作を案内します。':toolchains.includes(tool)?'対象OSとSDKを確認し、公式配布物またはOSのパッケージ管理を使って導入する予定です。':'';document.querySelector('#install-status').textContent='';syncPlatform();dialog.showModal();}
document.addEventListener('click',event=>{const install=event.target.closest('[data-install]');if(install)openInstall(install.dataset.install);const check=event.target.closest('[data-check]');if(check){document.querySelector('#'+check.dataset.check+'-update-status').textContent='試作：最新情報は未取得';toast('実際の更新状況はリリースノートから確認できます。');}if(event.target.closest('.sidebar a'))closeMenu();});
document.querySelector('#platform').addEventListener('change',syncPlatform);
document.querySelector('#path-scope').addEventListener('change',event=>{document.querySelector('#path-help').textContent={user:'新しく開いたターミナルでコマンドを利用できます。',none:'コマンドの絶対パスを指定して実行します。',system:'全ユーザーに影響します。アプリ版では管理者権限が必要です。'}[event.target.value];});
document.querySelector('#detect').addEventListener('click',()=>{document.querySelectorAll('[data-detection]').forEach(el=>el.textContent=installed.has(el.dataset.detection)?'導入済み（デモ）':'未検出（デモ）');toast('HTML試作の検出表示です。実際のPCは検査していません。');});
dialog.addEventListener('cancel',event=>{if(busy)event.preventDefault();});
document.querySelector('#confirm-install').addEventListener('click',async()=>{busy=true;dialog.querySelectorAll('button,select').forEach(el=>el.disabled=true);document.querySelector('#install-status').textContent='デモ：導入処理を再現しています…';await new Promise(resolve=>setTimeout(resolve,800));installed.add(selected);renderProducts();busy=false;dialog.querySelectorAll('button,select').forEach(el=>el.disabled=false);dialog.close();toast('デモ完了。PCへの変更はありません。');});
document.querySelector('#docs-search').addEventListener('input',event=>renderDocList(event.target.value));
document.querySelector('#menu-toggle').addEventListener('click',()=>{const open=document.querySelector('.sidebar').classList.toggle('open');document.querySelector('#menu-toggle').setAttribute('aria-expanded',String(open));});
document.querySelector('#theme-toggle').addEventListener('click',()=>document.body.classList.toggle('light'));
window.addEventListener('hashchange',navigate);renderProducts();navigate();
