const {test} = require('node:test');
const assert = require('node:assert/strict');
const {resolveServer} = require('../server');
const path = require('path');
const root = path.resolve(__dirname,'..');
const config = values=>({get:(key, fallback)=>key in values?values[key]:fallback});
test('explicit executable and arguments survive spaces',()=>{
  assert.deepEqual(resolveServer(config({'server.path':'/with space/python','server.args':['/server with space.pyz','--stdio']}), root), {command:'/with space/python',args:['/server with space.pyz','--stdio']});
});
test('PATH native server version is checked',()=>{
  assert.equal(resolveServer(config({}),root,()=> 'gs-lsp 0.4.0\n').command,'gs-lsp');
});
test('missing native server uses bundled Python with separate argv',()=>{
  const calls=[];
  const server=resolveServer(config({}),root,(cmd,args)=>{calls.push([cmd,args]);if(cmd==='gs-lsp')throw Error('ENOENT');return '';},'linux');
  assert.equal(server.command,'python3');assert(server.args[0].endsWith('.pyz'));assert.equal(calls.length,2);
});
test('Windows launcher uses an explicit Python version',()=>{
 const server=resolveServer(config({}),root,(cmd)=>{if(cmd==='gs-lsp')throw Error('missing');return '';},'win32');
 assert.equal(server.command,'py');assert.equal(server.args[0],'-3.12');
});
test('missing Python returns an actionable installation message',()=>{
 assert.throws(()=>resolveServer(config({}),root,()=>{throw Error('missing');}),/Python 3.12\+/);
});
