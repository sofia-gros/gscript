const {runTests} = require('@vscode/test-electron');
const fs = require('fs');
const os = require('os');
const path = require('path');
const root = path.resolve(__dirname, '../../..');
const workspace = fs.mkdtempSync(path.join(os.tmpdir(), 'gs-vscode-'));
fs.mkdirSync(path.join(workspace, '.vscode'));
fs.writeFileSync(path.join(workspace, '.vscode/settings.json'), JSON.stringify({
  'gscript.server.path': process.env.GS_PYTHON || 'python3',
  'gscript.server.args': ['-m', 'gscript.lsp', '--stdio']
}));
runTests({
  version: '1.96.4',
  extensionDevelopmentPath: path.resolve(__dirname, '..'),
  extensionTestsPath: path.join(__dirname, 'suite.cjs'),
  extensionTestsEnv: {PYTHONPATH: root},
  launchArgs: [workspace, '--no-sandbox', '--disable-gpu', '--disable-workspace-trust', '--skip-welcome', '--skip-release-notes']
}).then(() => fs.rmSync(workspace, {recursive:true, force:true})).catch(error => {console.error(error);process.exitCode=1;});
