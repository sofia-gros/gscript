const assert = require('assert');
const vscode = require('vscode');
exports.run = async function () {
  const folder = vscode.workspace.workspaceFolders[0].uri;
  const uri = vscode.Uri.joinPath(folder, 'editor-test.gs');
  await vscode.workspace.fs.writeFile(uri, Buffer.from('var value int = "wrong"\nconsole.log(value)'));
  const doc = await vscode.workspace.openTextDocument(uri);
  await vscode.window.showTextDocument(doc);
  assert.strictEqual(doc.languageId, 'gscript');
  await vscode.extensions.getExtension('sofia-gros.gscript').activate();
  async function waitFor(check) {
    const end = Date.now()+30000;
    while(Date.now()<end) {if(check()) return;await new Promise(r=>setTimeout(r,100));}
    throw new Error('Timed out waiting for GS diagnostics');
  }
  await waitFor(()=>vscode.languages.getDiagnostics(uri).some(d=>d.source==='gs' && d.message.includes('type mismatch')));
  const edit = new vscode.WorkspaceEdit();
  edit.replace(uri, new vscode.Range(0,0,doc.lineCount,0), 'var value int = 3\nconsole.log(value)');
  await vscode.workspace.applyEdit(edit);
  await waitFor(()=>vscode.languages.getDiagnostics(uri).length===0);
  const hovers = await vscode.commands.executeCommand('vscode.executeHoverProvider', uri, new vscode.Position(1,13));
  assert(hovers.some(h=>h.contents.some(c=>(c.value || '').includes('value: number'))));
  const completions = await vscode.commands.executeCommand('vscode.executeCompletionItemProvider',uri,new vscode.Position(1,0));
  assert(completions.items.some(i=>i.label==='value'));
  console.log('VSCode real extension host: diagnostics, unsaved edits, hover and completion passed');
};
