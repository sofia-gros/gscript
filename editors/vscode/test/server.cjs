const {test} = require('node:test');
const assert = require('node:assert/strict');
const {resolveServer} = require('../server');
const path = require('path');
const root = path.resolve(__dirname,'..');
const config = values=>({get:(key, fallback)=>key in values?values[key]:fallback});
test('explicit executable and arguments survive spaces',()=>{
  assert.deepEqual(resolveServer(config({'server.path':'/with space/python','server.args':['/server with space.pyz','--stdio']}), root, (command,args)=>{assert.equal(command,'/with space/python');assert.deepEqual(args,['/server with space.pyz','--version']);return 'gs-lsp 0.6.1\n';}), {command:'/with space/python',args:['/server with space.pyz','--stdio']});
});
test('PATH native server version is checked',()=>{
  assert.equal(resolveServer(config({}),root,()=> 'gs-lsp 0.6.1\n').command,'gs-lsp');
});
test('missing native server uses bundled Python with separate argv',()=>{
  const calls=[];
  const server=resolveServer(config({}),root,(cmd,args)=>{calls.push([cmd,args]);if(cmd==='gs-lsp')throw Error('ENOENT');return '';},'linux');
  assert.equal(server.command,'python3');assert(server.args[0].endsWith('.pyz'));assert.equal(calls.length,2);
});
test('Windows launcher selects Python 3 and the separate probe enforces 3.12+',()=>{
 const server=resolveServer(config({}),root,(cmd)=>{if(cmd==='gs-lsp')throw Error('missing');return '';},'win32');
 assert.equal(server.command,'py');assert.equal(server.args[0],'-3');
});
test('missing Python returns an actionable installation message',()=>{
 assert.throws(()=>resolveServer(config({}),root,()=>{throw Error('missing');}),/Python 3.12\+/);
});

test('broken explicit native executable fails before starting a crashing LSP client',()=>{
 const error=new Error('process exited');error.stderr=Buffer.from('[PYI-12:ERROR] Failed to extract VCRUNTIME140.dll');
 assert.throws(()=>resolveServer(config({'server.path':'A:/Download/gs-lsp.exe'}),root,()=>{throw error;}),e=>/VCRUNTIME140.dll/.test(e.message)&&/gscript.server.path/.test(e.message)&&/Python 3.12/.test(e.message));
});
test('explicit server version mismatch is actionable',()=>{
 assert.throws(()=>resolveServer(config({'server.path':'/old/gs-lsp'}),root,()=> 'gs-lsp 0.5.0'),/Expected gs-lsp 0.6.1/);
});
