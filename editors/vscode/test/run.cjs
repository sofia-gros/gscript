const {runTests} = require('@vscode/test-electron');
const fs = require('fs');
const os = require('os');
const path = require('path');
const cp = require('child_process');
const packaged = fs.mkdtempSync(path.join(os.tmpdir(), 'gs packaged extension '));
cp.execFileSync(process.env.GS_PYTHON || 'python', ['-c', 'import sys,zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])', path.resolve(__dirname,'../gscript-0.6.1.vsix'), packaged]);
const workspace = fs.mkdtempSync(path.join(os.tmpdir(), 'gs vscode '));
fs.mkdirSync(path.join(workspace, '.vscode'));
fs.writeFileSync(path.join(workspace, '.vscode/settings.json'), JSON.stringify({
  'gscript.server.path': ''
}));
runTests({
  version: '1.96.4',
  extensionDevelopmentPath: path.join(packaged, 'extension'),
  extensionTestsPath: path.join(__dirname, 'suite.cjs'),
  extensionTestsEnv: {PYTHONPATH: ''},
  launchArgs: [workspace, '--no-sandbox', '--disable-gpu', '--disable-workspace-trust', '--skip-welcome', '--skip-release-notes']
}).then(() => fs.rmSync(workspace, {recursive:true, force:true})).catch(error => {console.error(error);process.exitCode=1;});
