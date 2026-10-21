/* External declaration reader. Never receives or type-checks a GS expression. */
'use strict';
const readline = require('node:readline');
const path = require('node:path');
const crypto=require('node:crypto');
const fs=require('node:fs');
const dependencies=new Map();
function track(p,kind,contents){
 const key=path.resolve(p)+'|'+kind;
 const item={file:path.resolve(p),kind};
 if(contents!==undefined){try{item.readHash=crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');}catch{}}
 if(!dependencies.has(key)||contents!==undefined)dependencies.set(key,item);
}
let ts, checker, program, request;
const objects = [], ids = new Map();
function id(t) { if (!ids.has(t)) { ids.set(t, objects.length); objects.push(t); } return ids.get(t); }
function signature(s) {
  return {params: s.getParameters().map((p,i) => {
    const d = p.valueDeclaration ?? p.declarations?.[0];
    return {type: id(checker.getTypeOfSymbolAtLocation(p,d)), optional: i >= s.minArgumentCount,
            rest: !!d?.dotDotDotToken};
  }), result: id(checker.getReturnTypeOfSignature(s)),
  parameters: (s.typeParameters ?? []).map(p => ({name:p.symbol.name, type:id(p), constraint:checker.getBaseConstraintOfType(p) ? id(checker.getBaseConstraintOfType(p)) : null}))};
}
function describe(t) {
  const f=t.flags, F=ts.TypeFlags;
  if (f&F.Any) return {kind:'any'};
  if (f&F.Unknown) return {kind:'unknown'};
  if (f&F.Never) return {kind:'never'};
  if (f&F.Null) return {kind:'null'};
  if (f&F.Undefined) return {kind:'undefined'};
  if (f&F.Void) return {kind:'void'};
  if (f&F.StringLiteral) return {kind:'literal',value:t.value,base:'string'};
  if (f&F.NumberLiteral) return {kind:'literal',value:t.value,base:'number'};
  if (f&F.BooleanLiteral) return {kind:'literal',value:t.intrinsicName==='true',base:'bool'};
  if (f&F.String) return {kind:'string'};
  if (f&F.Number) return {kind:'number'};
  if (f&F.Boolean) return {kind:'bool'};
  if (t.isUnion()) return {kind:'union',args:t.types.map(id)};
  if (f&F.TypeParameter) return {kind:'param',name:t.symbol.name,constraint:checker.getBaseConstraintOfType(t) ? id(checker.getBaseConstraintOfType(t)) : null};
  if (checker.isArrayType(t) || checker.isTupleType(t)) return {kind:'array',args:[id(checker.getIndexTypeOfType(t,ts.IndexKind.Number))]};
  const promised=checker.getPromisedTypeOfPromise(t);
  if (promised) return {kind:'promise',args:[id(promised)]};
  if(f & (F.Conditional|F.IndexedAccess|F.TemplateLiteral|F.StringMapping))throw Error('unsupported external type operator: '+checker.typeToString(t));
  return {kind:'foreign', isFunctionObject:t.symbol?.name==='Function', isClass:!!t.isClass?.(), bases:t.isClassOrInterface?.() ? (checker.getBaseTypes(t)??[]).map(id) : [], parameters:(t.target?.typeParameters ?? t.typeParameters ?? []).map(id), arguments:((t.objectFlags & ts.ObjectFlags.Reference) ? checker.getTypeArguments(t) : []).map(id), calls:t.getCallSignatures().map(signature), constructors:t.getConstructSignatures().map(signature)};
}
function property(t,name) {
  const p=checker.getPropertyOfType(t,name);
  return p ? symbolProperty(p) : null;
}
function symbolProperty(p) {
  const d=p.valueDeclaration ?? p.declarations?.[0];
  const flags=d ? ts.getCombinedModifierFlags(d) : 0;
  return {type:id(checker.getTypeOfSymbolAtLocation(p,d)),optional:!!(p.flags&ts.SymbolFlags.Optional),
          readonly:!!(flags&ts.ModifierFlags.Readonly),owner:d?.parent?.symbol && ts.isClassLike(d.parent) ? id(checker.getDeclaredTypeOfSymbol(d.parent.symbol)) : null,access:flags&ts.ModifierFlags.Private?'private':flags&ts.ModifierFlags.Protected?'protected':'public'};
}
function init(r) {
  request=r;ts=require(r.typescript);
  const virtual=new Map(r.sources.map(s=>[path.resolve(s.fileName),s.text]));
  let options={};
  const system={...ts.sys,
    readFile(p){const text=ts.sys.readFile(p);track(p,'file',text);return text;},
    fileExists(p){track(p,'file');return ts.sys.fileExists(p);},
    directoryExists(p){track(p,'directory');return ts.sys.directoryExists(p);}};
  const config=ts.findConfigFile(path.dirname(r.sources[0].fileName),system.fileExists);
  if (config) {
    const json=ts.readConfigFile(config,system.readFile);
    if (json.error) throw Error(ts.flattenDiagnosticMessageText(json.error.messageText,'\n'));
    options=ts.parseJsonConfigFileContent(json.config,{...system,readDirectory:()=>[]},path.dirname(config)).options;
  }
  options={...options,target:ts.ScriptTarget.ES2022,module:options.module ?? ts.ModuleKind.NodeNext,
    moduleResolution:options.moduleResolution ?? ts.ModuleResolutionKind.NodeNext,
    allowJs:true,checkJs:true,strict:true,noEmit:true,skipLibCheck:true,maxNodeModuleJsDepth:2,
    noUncheckedSideEffectImports:true,allowSyntheticDefaultImports:true,esModuleInterop:true,
    allowImportingTsExtensions:true};
  if (!options.typeRoots) {
    const roots=ts.getEffectiveTypeRoots(options,{getCurrentDirectory:()=>path.dirname(r.sources[0].fileName),directoryExists:ts.sys.directoryExists}) ?? [];
    roots.push(path.resolve(path.dirname(r.typescript),'../../@types')); options.typeRoots=[...new Set(roots)];
  }
  const host=ts.createCompilerHost(options);
  const read=system.readFile,exists=system.fileExists;
  host.directoryExists=system.directoryExists;
  host.readFile=p=>virtual.get(path.resolve(p)) ?? read(p);
  host.fileExists=p=>virtual.has(path.resolve(p)) || exists(p);
  host.getSourceFile=(p,v)=>{const text=host.readFile(p);if(text===undefined)return undefined;return ts.createSourceFile(p,text,v,true);};
  program=ts.createProgram([...virtual.keys()],options,host);checker=program.getTypeChecker();
  // Probe files contain import declarations only. Diagnostics here concern resolution,
  // never GS bodies, assignments, inheritance or calls.
  const diagnostics=[];
  const implicitJs=new Set([7005,7006,7010,7019,7031,7034,7044]);
  for (const d of ts.getPreEmitDiagnostics(program)) {
    const probe=d.file && virtual.has(path.resolve(d.file.fileName));
    if(probe && ![2307,2305,2614,1192,7016].includes(d.code))continue;
    if(d.file && /\.[cm]?jsx?$/.test(d.file.fileName) && implicitJs.has(d.code))continue;
    diagnostics.push((d.file&&!probe ? d.file.fileName+': '+(d.file.getLineAndCharacterOfPosition(d.start??0).line+1)+': ' : '')+ts.flattenDiagnosticMessageText(d.messageText,'\n'));
  }
  return {ready:true,diagnostics};
}
function run(r) {
  if (r.action==='init')return init(r);
  if (r.action==='resolve') {
    const sf=program.getSourceFile(r.file);
    const symbols=checker.getSymbolsInScope(sf,ts.SymbolFlags.Alias|ts.SymbolFlags.Value|ts.SymbolFlags.Type);
    let s=symbols.find(s=>s.name===r.name);
    if(!s)throw Error('external binding not found: '+r.name);
    if(s.flags&ts.SymbolFlags.Alias)s=checker.getAliasedSymbol(s);
    const location=s.valueDeclaration ?? s.declarations?.[0] ?? sf;
    return {value:id(checker.getTypeOfSymbolAtLocation(s,location)),type:id(checker.getDeclaredTypeOfSymbol(s))};
  }
  if (r.action==='named_type') {
    const sf=program.getSourceFile(r.file);
    const parts=r.name.split('.');
    const rootName=parts.shift();
    let symbol=checker.getSymbolsInScope(sf,ts.SymbolFlags.Alias|ts.SymbolFlags.Value|ts.SymbolFlags.Type).find(s=>s.name===rootName);
    if(symbol?.flags&ts.SymbolFlags.Alias)symbol=checker.getAliasedSymbol(symbol);
    for(const name of parts){
      let next;
      try {next=checker.getExportsOfModule(symbol).find(s=>s.name===name);}catch{}
      if(!next)next=checker.getPropertyOfType(checker.getTypeOfSymbolAtLocation(symbol,symbol.valueDeclaration ?? symbol.declarations?.[0] ?? sf),name);
      symbol=next;
      if(!symbol)throw Error('unknown external type: '+r.name);
      if(symbol.flags&ts.SymbolFlags.Alias)symbol=checker.getAliasedSymbol(symbol);
    }
    if(!symbol)throw Error('unknown external type: '+r.name);
    return {type:id(checker.getDeclaredTypeOfSymbol(symbol))};
  }
  if (r.action==='dependencies')return [...dependencies.values()];
  const t=objects[r.id];
  if (!t) throw Error('invalid external type reference');
  if (r.action==='describe')return describe(t);
  if (r.action==='property')return property(t,r.name);
  if (r.action==='fields')return checker.getPropertiesOfType(t).map(s=>({name:s.name,...symbolProperty(s)}));
  throw Error('unknown declaration query');
}
const rl=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
rl.on('line',line=>{try{process.stdout.write(JSON.stringify({result:run(JSON.parse(line))})+'\n');}catch(e){process.stdout.write(JSON.stringify({error:e.stack})+'\n');}});
