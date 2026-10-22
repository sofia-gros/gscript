const cp = require('child_process');
const path = require('path');
const fs = require('fs');

function resolveServer(config, extensionPath, run = cp.execFileSync, platform = process.platform) {
  const configured = config.get('server.path', '').trim();
  const args = config.get('server.args', ['--stdio']);
  if (configured) return {command: configured, args};
  try {
    const version = String(run('gs-lsp', ['--version'], {timeout:5000, windowsHide:true})).trim();
    if (version !== 'gs-lsp 0.5.0') throw new Error(`Expected gs-lsp 0.5.0, got ${version}`);
    return {command:'gs-lsp', args:['--stdio']};
  } catch (_) { /* Fall back to the compiler bundled in the VSIX. */ }
  const server = path.join(extensionPath, 'server', 'gs-lsp-v0.5.0.pyz');
  if (!fs.existsSync(server)) throw new Error('The GS extension is incomplete: bundled language server is missing. Reinstall the VSIX.');
  const candidates = platform === 'win32' ? [['py',['-3.12']], ['python',[]], ['python3',[]]] : [['python3',[]], ['python',[]]];
  for (const [command, prefix] of candidates) {
    try {
      run(command, [...prefix, '-c', 'import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)'], {timeout:5000, windowsHide:true});
      return {command, args:[...prefix, server, '--stdio']};
    } catch (_) { /* Try the next interpreter without opening a shell. */ }
  }
  throw new Error('GS needs Python 3.12+ for its bundled language server, or the native gs-lsp 0.5.0. Install either, or set gscript.server.path to its absolute path, then run Developer: Reload Window. See the GS extension README for installation instructions.');
}
module.exports = {resolveServer};
