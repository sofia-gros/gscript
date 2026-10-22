import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from gscript.lsp import Server, path_from_uri, position, read_message


class LanguageServerTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name).resolve()
        self.uri=(self.root/'main.gs').as_uri()
        self.events=[]
        self.server=Server(self.events.append)
        self.server.handle('initialize',{'rootUri':self.root.as_uri()})

    def open(self,text,uri=None):
        self.server.handle('textDocument/didOpen',{'textDocument':{'uri':uri or self.uri,'languageId':'gscript','version':1,'text':text}})

    def errors(self,uri=None):
        return [d for d in next(e['params']['diagnostics'] for e in reversed(self.events) if e['params'].get('uri')==(uri or self.uri)) if d['severity']==1]

    def test_native_diagnostics_unsaved_changes_clear_and_do_not_write(self):
        self.open('var n int = "bad"')
        self.assertIn('type mismatch',self.errors()[0]['message'])
        self.assertEqual(self.errors()[0]['source'],'gs')
        self.server.handle('textDocument/didChange',{'textDocument':{'uri':self.uri,'version':2},'contentChanges':[{'text':'var n int = 3'}]})
        self.assertEqual(self.errors(),[])
        self.server.handle('textDocument/didChange',{'textDocument':{'uri':self.uri,'version':1},'contentChanges':[{'text':'@'}]})
        self.assertEqual(self.errors(),[])
        self.assertEqual(list(self.root.iterdir()),[])

    def test_unsaved_module_graph_and_close(self):
        lib=self.root/'lib.gs';lib.write_text('export var n int = 1',encoding='utf-8')
        self.open('import { n } from "./lib.gs"\nvar x int = n')
        self.assertEqual(self.errors(),[])
        self.open('export var n string = "changed"',lib.as_uri())
        self.assertIn('type mismatch',self.errors()[0]['message'])
        self.assertEqual(lib.read_text(),'export var n int = 1')
        self.server.handle('textDocument/didClose',{'textDocument':{'uri':lib.as_uri()}})
        self.assertEqual(self.errors(),[])
        self.server.handle('textDocument/didClose',{'textDocument':{'uri':self.uri}})
        self.assertEqual(self.errors(),[])

    def test_hover_completion_symbols_and_shadowing(self):
        self.open('var value int = 3\nconsole.log(value)\nfunc other() { var value string = "local"; console.log(value) }')
        hover=self.server.handle('textDocument/hover',{'textDocument':{'uri':self.uri},'position':{'line':1,'character':13}})
        self.assertEqual(hover['contents']['value'],'value: int')
        hover=self.server.handle('textDocument/hover',{'textDocument':{'uri':self.uri},'position':{'line':2,'character':56}})
        self.assertEqual(hover['contents']['value'],'value: string')
        items=self.server.handle('textDocument/completion',{'textDocument':{'uri':self.uri},'position':{'line':1,'character':0}})['items']
        self.assertIn('value',[i['label'] for i in items])
        self.assertIn('extends',[i['label'] for i in items])
        symbols=self.server.handle('textDocument/documentSymbol',{'textDocument':{'uri':self.uri}})
        self.assertEqual([s['name'] for s in symbols],['value','other'])

    def test_strict_null_and_utf16(self):
        self.server.handle('initialize',{'initializationOptions':{'strictNull':True}})
        self.open('type A struct {}\nvar a A = nil')
        self.assertTrue(self.errors())
        self.assertEqual(position('"😀"; value',1,6),{'line':0,'character':6})
        uri=(self.root/'space 日本.gs').as_uri()
        self.assertEqual(path_from_uri(uri),self.root/'space 日本.gs')
        with self.assertRaises(ValueError):path_from_uri('https://example.com/test.gs')

    def test_syntax_error_and_missing_import_are_diagnostics(self):
        self.open('var n = @')
        self.assertTrue(self.errors())
        self.server.handle('textDocument/didChange',{'textDocument':{'uri':self.uri,'version':2},'contentChanges':[{'text':'import { n } from "./missing.gs"'}]})
        self.assertIn('module not found',self.errors()[0]['message'])

    def test_diagnostics_preserve_client_uri_spelling(self):
        uri=self.uri.replace('file://','file://localhost')
        self.open('var n int = "bad"',uri)
        self.assertIn('type mismatch',self.errors(uri)[0]['message'])
        self.assertFalse(any(e['params'].get('uri')==self.uri for e in self.events))

    def test_stdio_protocol_lifecycle_and_unicode_byte_lengths(self):
        messages=[{'id':1,'method':'initialize','params':{'rootUri':self.root.as_uri()}},
                  {'method':'textDocument/didOpen','params':{'textDocument':{'uri':self.uri,'version':1,'text':'var message string = "日本😀"'}}},
                  {'id':2,'method':'unknown/method'}, {'id':3,'method':'shutdown'}, {'method':'exit'}]
        def frame(m):
            body=json.dumps(dict(jsonrpc='2.0',**m),ensure_ascii=False).encode()
            return f'Content-Length: {len(body)}\r\n\r\n'.encode()+body
        result=subprocess.run([sys.executable,'-m','gscript.lsp','--stdio'],input=b''.join(map(frame,messages)),capture_output=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        stream=io.BytesIO(result.stdout);responses=[]
        while (message:=read_message(stream)) is not None:responses.append(message)
        self.assertEqual(responses[0]['result']['serverInfo']['version'],'0.5.0')
        self.assertFalse(any(d['severity']==1 for d in responses[1]['params']['diagnostics']))
        self.assertEqual(responses[2]['error']['code'],-32601)
        self.assertIsNone(responses[3]['result'])
        with self.assertRaises(ValueError):read_message(io.BytesIO(b'Content-Length: 5\r\n\r\n{}'))
