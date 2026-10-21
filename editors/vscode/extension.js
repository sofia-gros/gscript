const vscode = require('vscode');
const { LanguageClient } = require('vscode-languageclient/node');
let client;
function activate(context) {
  const config = vscode.workspace.getConfiguration('gscript');
  const watcher = vscode.workspace.createFileSystemWatcher('**/*.{gs,gos,js,mjs,cjs,ts,json}');
  context.subscriptions.push(watcher);
  client = new LanguageClient('gscript', 'GS Language Server', {
    command: config.get('server.path', 'gs-lsp'),
    args: config.get('server.args', ['--stdio']),
    options: {env: process.env}
  }, {
    documentSelector: [{scheme: 'file', language: 'gscript'}],
    synchronize: {fileEvents: watcher},
    initializationOptions: {strictNull: config.get('strictNull', false)}
  });
  return client.start();
}
function deactivate() { return client ? client.stop() : undefined; }
module.exports = {activate, deactivate};
