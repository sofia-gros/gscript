const vscode = require('vscode');
const { LanguageClient } = require('vscode-languageclient/node');
const {resolveServer} = require('./server');
let client;
async function activate(context) {
  const output = vscode.window.createOutputChannel('GS Language Server');
  context.subscriptions.push(output);
  try {
    const config = vscode.workspace.getConfiguration('gscript');
    const server = resolveServer(config, context.extensionPath);
    output.appendLine(`Starting ${server.command} ${server.args.join(' ')}`);
    const watcher = vscode.workspace.createFileSystemWatcher('**/*.{gs,gos,js,mjs,cjs,ts,json}');
    context.subscriptions.push(watcher);
    client = new LanguageClient('gscript', 'GS Language Server', {
      ...server, options: {env:process.env}
    }, {
      documentSelector:[{scheme:'file',language:'gscript'}],
      synchronize:{fileEvents:watcher}, outputChannel:output,
      initializationOptions:{strictNull:config.get('strictNull',null)}
    });
    await client.start();
  } catch (error) {
    output.appendLine(String(error.stack || error));
    const action = await vscode.window.showErrorMessage(`GS language server could not start: ${error.message}`, 'Show GS log', 'Open GS settings');
    if (action === 'Show GS log') output.show();
    if (action === 'Open GS settings') await vscode.commands.executeCommand('workbench.action.openSettings', 'gscript.server');
  }
}
function deactivate() { return client && client.isRunning() ? client.stop() : undefined; }
module.exports = {activate, deactivate};
