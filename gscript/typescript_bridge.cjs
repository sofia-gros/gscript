/* GS compiler bridge. Uses TypeScript's public compiler API, never executes imports. */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const request = JSON.parse(fs.readFileSync(0, 'utf8'));
const ts = require(request.typescript);
const sensitive = ts.sys.useCaseSensitiveFileNames;
const key = p => sensitive ? path.resolve(p) : path.resolve(p).toLowerCase();
const virtual = new Map(request.sources.map(s => [key(s.fileName), s]));
const dependencies = new Map();
function track(p, kind) {
  if (!virtual.has(key(p)) && !dependencies.has(path.resolve(p))) dependencies.set(path.resolve(p), {file: path.resolve(p), kind});
}
const originalRead = ts.sys.readFile;
const originalExists = ts.sys.fileExists;
const originalDirectory = ts.sys.directoryExists;
const system = {
  ...ts.sys,
  readFile(p) {
    if (virtual.has(key(p))) return virtual.get(key(p)).text;
    track(p, 'file');
    try {
      const bytes = fs.readFileSync(p);
      dependencies.get(path.resolve(p)).readHash = crypto.createHash('sha256').update(bytes).digest('hex');
      if (bytes.length >= 2 && bytes[0] === 0xff && bytes[1] === 0xfe) return bytes.subarray(2).toString('utf16le');
      if (bytes.length >= 2 && bytes[0] === 0xfe && bytes[1] === 0xff) return Buffer.from(bytes.subarray(2)).swap16().toString('utf16le');
      return bytes.toString('utf8').replace(/^\uFEFF/, '');
    } catch { return undefined; }
  },
  fileExists(p) { if (virtual.has(key(p))) return true; track(p, 'file'); return originalExists(p); },
  directoryExists(p) { track(p, 'directory'); return originalDirectory(p); }
};
let configOptions = {};
const configPath = ts.findConfigFile(path.dirname(request.entry), system.fileExists);
let configErrors = [];
if (configPath) {
  const config = ts.readConfigFile(configPath, system.readFile);
  if (config.error) configErrors.push(config.error);
  else {
    const parsed = ts.parseJsonConfigFileContent(config.config, {...system, readDirectory() { return []; }}, path.dirname(configPath), undefined, configPath);
    configOptions = parsed.options;
    // GS entry points, not tsconfig's include list, determine the source graph.
    configErrors.push(...parsed.errors.filter(d => d.code !== 18003 && d.code !== 18002));
  }
}
const options = {
  ...configOptions,
  target: ts.ScriptTarget.ES2022,
  module: configOptions.module ?? ts.ModuleKind.NodeNext,
  moduleResolution: configOptions.moduleResolution ?? ts.ModuleResolutionKind.NodeNext,
  jsx: configOptions.jsx ?? ts.JsxEmit.ReactJSX,
  allowJs: true, checkJs: true, strict: true, noImplicitAny: true,
  noUncheckedSideEffectImports: true,
  allowSyntheticDefaultImports: true, esModuleInterop: true,
  allowImportingTsExtensions: true, skipLibCheck: true,
  maxNodeModuleJsDepth: 2,
  noEmit: false, declaration: true, emitDeclarationOnly: true,
  noUnusedLocals: false, noUnusedParameters: false,
  rootDir: undefined, outDir: undefined, declarationDir: undefined,
  incremental: false, composite: false, tsBuildInfoFile: undefined,
};
if (!options.typeRoots) {
  const roots = ts.getEffectiveTypeRoots(options, {getCurrentDirectory: () => path.dirname(request.entry), directoryExists: system.directoryExists}) ?? [];
  const toolTypes = path.resolve(path.dirname(request.typescript), '../../@types');
  if (system.directoryExists(toolTypes)) roots.push(toolTypes);
  options.typeRoots = [...new Set(roots)];
}
const host = ts.createCompilerHost(options, true);
host.readFile = system.readFile;
host.fileExists = system.fileExists;
host.directoryExists = system.directoryExists;
host.getSourceFile = (p, languageVersion, onError) => {
  const text = system.readFile(p);
  if (text === undefined) return undefined;
  const sf = ts.createSourceFile(p, text, languageVersion, true);
  sf.impliedNodeFormat = virtual.has(key(p)) ? ts.ModuleKind.ESNext : ts.getImpliedNodeFormatForFile(p, undefined, host, options);
  return sf;
};
// Discover local runtime dependencies separately from declaration resolution:
// an adjacent .d.ts must not make its .js implementation disappear from output.
const runtime = new Map();
function runtimeTarget(specifier, importer) {
  const resolved = ts.resolveModuleName(specifier, importer, options, host).resolvedModule;
  const explicit = path.resolve(path.dirname(importer), specifier);
  let target = resolved?.resolvedFileName;
  if (!target || /\.d\.[cm]?ts$/.test(target)) {
    if (/\.[cm]?[jt]sx?$/.test(explicit) && system.fileExists(explicit)) target = explicit;
    else if (target) {
      const sibling = target.replace(/\.d\.mts$/, '.mjs').replace(/\.d\.cts$/, '.cjs').replace(/\.d\.ts$/, '.js');
      target = system.fileExists(sibling) ? sibling : null;
    }
  }
  if (!target || virtual.has(key(target)) || /\.d\.[cm]?ts$/.test(target) || path.resolve(target).split(path.sep).includes('node_modules')) return null;
  return path.resolve(target);
}
const queue = [];
for (const source of request.sources) {
  for (const item of ts.preProcessFile(source.text, true, true).importedFiles) {
    const target = runtimeTarget(item.fileName, source.fileName);
    if (target) queue.push(target);
  }
}
while (queue.length) {
  const file = queue.pop();
  if (runtime.has(key(file))) continue;
  const text = system.readFile(file);
  if (text === undefined) continue;
  runtime.set(key(file), {file, text});
  for (const item of ts.preProcessFile(text, true, true).importedFiles) {
    const target = runtimeTarget(item.fileName, file);
    if (target) queue.push(target);
  }
}
const program = ts.createProgram(request.sources.map(s => s.fileName), options, host);
const implicitJs = new Set([7005, 7006, 7010, 7019, 7031, 7034, 7044]);
const diagnostics = [...configErrors, ...ts.getPreEmitDiagnostics(program)]
  .filter(d => !(d.file && /\.[cm]?jsx?$/.test(d.file.fileName) && implicitJs.has(d.code)));
function diagnostic(d) {
  const message = ts.flattenDiagnosticMessageText(d.messageText, '\n');
  if (!d.file) return { message, code: d.code, file: request.entry };
  const source = virtual.get(key(d.file.fileName));
  const position = d.start ?? 0;
  const lc = d.file.getLineAndCharacterOfPosition(position);
  if (!source) return { message, code: d.code, file: d.file.fileName, line: lc.line + 1, column: lc.character + 1 };
  const prefix = source.text.slice(0, position);
  const markers = [...prefix.matchAll(/\/\*__GS_LINE_(\d+)__\*\//g)];
  const line = markers.length ? Number(markers.at(-1)[1]) : 1;
  const token = source.text.slice(position, position + (d.length ?? 0));
  const originalLine = source.sourceText.split(/\r?\n/)[line - 1] ?? '';
  const column = token && !token.includes('\n') ? originalLine.indexOf(token) : -1;
  return { message, code: d.code, file: source.sourcePath, line, column: column >= 0 ? column + 1 : undefined };
}
if (diagnostics.length) {
  process.stdout.write(JSON.stringify({ diagnostics: diagnostics.map(diagnostic), dependencies: [] }));
  process.exit(0);
}
const root = path.resolve(request.root);
const localFiles = [...runtime.values()].map(({file, text}) => {
  const sf = program.getSourceFile(file) ?? ts.createSourceFile(file, text, ts.ScriptTarget.ES2022, true);
  // Bind a standalone runtime file when declaration resolution hid its source.
  if (!program.getSourceFile(file)) {
    sf.commonJsModuleIndicator = /\bmodule\.exports\b|\bexports\.[A-Za-z_$]/.test(text) ? true : undefined;
  }
  return sf;
});
const sourceMap = new Map(localFiles.map(sf => [key(sf.fileName), sf]));
function flavor(sf) {
  const cjs = /\.(cjs|cts)$/.test(sf.fileName) || Boolean(sf.commonJsModuleIndicator);
  if (cjs) return { cjs, extension: 'cjs', declaration: 'd.cts' };
  if (request.format === 'ts') {
    if (/\.[cm]?tsx?$/.test(sf.fileName)) return { cjs, extension: sf.fileName.endsWith('.tsx') ? 'tsx' : 'ts', declaration: null };
    return { cjs, extension: 'js', declaration: 'd.ts' };
  }
  return { cjs, extension: request.format, declaration: null };
}
function outputName(sf) { return path.resolve(sf.fileName).replace(/\.[^.]+$/, '.' + flavor(sf).extension); }
function rewriteSpecifier(literal, importer) {
  const runtimeFile = runtimeTarget(literal.text, importer);
  const target = runtimeFile && sourceMap.get(key(runtimeFile));
  if (!target) return literal;
  let relative = path.relative(path.dirname(importer), outputName(target)).split(path.sep).join('/');
  if (!relative.startsWith('.')) relative = './' + relative;
  // TS source points to its emitted JavaScript sibling, using NodeNext conventions.
  if (request.format === 'ts' && /\.(ts|tsx)$/.test(relative)) relative = relative.replace(/\.(ts|tsx)$/, '.js');
  return ts.factory.createStringLiteral(relative);
}
function transformer(importer) {
  return context => {
    const visit = node => {
      if (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) {
        if (node.moduleSpecifier && ts.isStringLiteral(node.moduleSpecifier)) {
          const next = rewriteSpecifier(node.moduleSpecifier, importer);
          return ts.isImportDeclaration(node)
            ? ts.factory.updateImportDeclaration(node, node.modifiers, node.importClause, next, node.attributes)
            : ts.factory.updateExportDeclaration(node, node.modifiers, node.isTypeOnly, node.exportClause, next, node.attributes);
        }
      }
      if (ts.isCallExpression(node) && node.arguments.length === 1 && ts.isStringLiteral(node.arguments[0])
          && (node.expression.kind === ts.SyntaxKind.ImportKeyword || ts.isIdentifier(node.expression) && node.expression.text === 'require')) {
        return ts.factory.updateCallExpression(node, node.expression, node.typeArguments, [rewriteSpecifier(node.arguments[0], importer)]);
      }
      return ts.visitEachChild(node, visit, context);
    };
    return sf => ts.visitNode(sf, visit);
  };
}
const files = [];
for (const sf of localFiles) {
  const relative = path.relative(root, path.resolve(sf.fileName));
  if (relative.startsWith('..' + path.sep) || path.isAbsolute(relative)) {
    process.stdout.write(JSON.stringify({ diagnostics: [{file: sf.fileName, message: 'external source is outside the project root; set --root', code: 0}], dependencies: [] }));
    process.exit(0);
  }
  const type = flavor(sf);
  const transformed = ts.transform(sf, [transformer(sf.fileName)]);
  const rewritten = ts.createPrinter().printFile(transformed.transformed[0]);
  transformed.dispose();
  const code = request.format === 'ts' && !type.cjs ? rewritten : ts.transpileModule(rewritten, {
    fileName: sf.fileName,
    compilerOptions: { ...options, noEmit: false, declaration: false, emitDeclarationOnly: false,
      allowImportingTsExtensions: false, module: type.cjs ? ts.ModuleKind.CommonJS : ts.ModuleKind.ESNext }
  }).outputText;
  const output = { source: path.resolve(sf.fileName), extension: type.extension, code };
  if (request.format === 'ts' && type.declaration && !program.getSourceFile(sf.fileName)) {
    const declaration = ts.resolveModuleName('./' + path.basename(sf.fileName), sf.fileName, options, host).resolvedModule;
    const declaredFile = declaration && program.getSourceFile(declaration.resolvedFileName);
    if (declaredFile?.isDeclarationFile) output.declaration = {extension: type.declaration, code: declaredFile.text};
  }
  if (request.format === 'ts' && type.declaration && program.getSourceFile(sf.fileName)) {
    const emitted = program.emit(sf, (p, text) => {
      if (/\.d\.[cm]?ts$/.test(p)) output.declaration = { extension: type.declaration, code: text };
    }, undefined, true, { afterDeclarations: [transformer(sf.fileName)] });
    if (emitted.diagnostics.length) {
      process.stdout.write(JSON.stringify({diagnostics: emitted.diagnostics.map(diagnostic), dependencies: []}));
      process.exit(0);
    }
  }
  files.push(output);
}
const gsFiles = {};
for (const source of request.sources) {
  const sf = ts.createSourceFile(source.fileName, source.runtimeText, ts.ScriptTarget.ES2022, true, ts.ScriptKind.TS);
  const transformed = ts.transform(sf, [transformer(source.fileName)]);
  const rewritten = ts.createPrinter().printFile(transformed.transformed[0]);
  transformed.dispose();
  gsFiles[source.sourcePath] = request.format === 'ts' ? rewritten : ts.transpileModule(rewritten, {
    fileName: source.fileName,
    compilerOptions: { ...options, module: ts.ModuleKind.ESNext, noEmit: false,
      declaration: false, emitDeclarationOnly: false, allowImportingTsExtensions: false,
      verbatimModuleSyntax: false }
  }).outputText;
}
// Include all probed paths, including missing candidates. Installing a higher-
// priority declaration or changing package resolution must invalidate the cache.
process.stdout.write(JSON.stringify({ diagnostics: [], files, gsFiles, dependencies: [...dependencies.values()], typescriptVersion: ts.version }));
