// npm run docs:bundle — generated assets have no browser-time dependencies.
import {readFile,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {marked} from 'marked';
import hljs from 'highlight.js';
const root=fileURLToPath(new URL('../../..',import.meta.url));
const folder=path.join(root,'docs','guide');
const navigation=JSON.parse(await readFile(path.join(folder,'navigation.json'),'utf8'));
const escape=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
marked.use({renderer:{code({text,lang}){const language=(lang||'text').split(' ')[0];const mapped={gs:'go',js:'javascript',sh:'bash',text:'plaintext'}[language]||language;const html=hljs.getLanguage(mapped)?hljs.highlight(text,{language:mapped}).value:escape(text);return `<pre data-language="${escape(language)}"><code>${html}</code></pre>\n`;}}});
const documents=[];
for(const entry of navigation){const source=await readFile(path.join(folder,entry.id),'utf8');documents.push({...entry,source,html:marked.parse(source),sha256:createHash('sha256').update(source).digest('hex')});}
await writeFile(new URL('../docs-bundle.js',import.meta.url),'// Generated from docs/guide/navigation.json. Do not edit.\nwindow.GSCRIPT_DOCS = '+JSON.stringify({version:'0.6.1',documents}).replaceAll('<','\\u003c')+';\n');
console.log(`Bundled ${documents.length} offline guide pages`);
