import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from gscript.lsp import Server,file_uri_path,path_from_uri,UnknownMethod


class URIRegressionTests(unittest.TestCase):
    def test_zed_windows_encoded_drive_and_percent_are_decoded_once(self):
        self.assertEqual(file_uri_path('file:///a%3A/Project/gscript/hello.gos',True),'a:\\Project\\gscript\\hello.gos')
        self.assertEqual(file_uri_path('file:///a:/Project/gscript/hello.gos',True),'a:\\Project\\gscript\\hello.gos')
        self.assertEqual(file_uri_path('file:///a%3A/Project/name%2520literal.gos',True),'a:\\Project\\name%20literal.gos')
        with self.assertRaises(ValueError):file_uri_path('file:///a:Project/gscript/hello.gos',True)

    @unittest.skipUnless(os.name=='nt','actual WindowsPath resolution')
    def test_real_windows_document_symbols_with_zed_uri(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'hello.gos';text='func greet() string { return "hello" }\nprintln(greet())';path.write_text(text)
            uri=path.as_uri()
            drive=path.drive
            uri=uri.replace('/'+drive,'/'+drive.lower().replace(':','%3A'))
            self.assertEqual(path_from_uri(uri),path.resolve())
            events=[];server=Server(events.append);server.handle('initialize',{'rootUri':Path(d).as_uri()})
            server.handle('textDocument/didOpen',{'textDocument':{'uri':uri,'version':1,'text':text}})
            result=server.handle('textDocument/documentSymbol',{'textDocument':{'uri':uri}})
            self.assertIn('greet',[item['name'] for item in result])
            self.assertFalse(any(x.get('severity')==1 for e in events for x in e.get('params',{}).get('diagnostics',[])))

    def test_only_unsupported_methods_are_lookup_errors(self):
        with self.assertRaises(UnknownMethod):Server(lambda _:None).handle('not/a/method',{})
        self.assertFalse(isinstance(KeyError('module'),UnknownMethod))


class NativeLSPTests(unittest.TestCase):
    def test_native_unsaved_diagnostics_hover_definition_and_format(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'gsconfig.json').write_text('{"backend":"native"}')
            uri=(root/'main.gs').as_uri();events=[];server=Server(events.append)
            server.handle('initialize',{'rootUri':root.as_uri()})
            text='extern "C" func puts(text cptr<cchar>) i32\nvalue:=i32(42)\nprintln(value)'
            with patch('subprocess.run',side_effect=AssertionError('LSP must not run a C compiler')):
                server.handle('textDocument/didOpen',{'textDocument':{'uri':uri,'version':1,'text':text}})
            self.assertEqual(events[-1]['params']['diagnostics'],[])
            params={'textDocument':{'uri':uri},'position':{'line':2,'character':9}}
            self.assertIn('value: i32',server.handle('textDocument/hover',params)['contents']['value'])
            self.assertEqual(server.handle('textDocument/definition',params)[0]['range']['start']['line'],1)
            self.assertIn('value',[s['name'] for s in server.handle('textDocument/documentSymbol',params)])
            self.assertTrue(server.handle('textDocument/formatting',params))
            rename=server.handle('textDocument/rename',{**params,'newName':'total'})
            self.assertEqual(len(rename['documentChanges'][0]['edits']),2)
            server.handle('textDocument/didChange',{'textDocument':{'uri':uri,'version':2},'contentChanges':[{'text':'var value i32 = "bad"'}]})
            self.assertIn('native type mismatch',events[-1]['params']['diagnostics'][0]['message'])

    def test_native_ffi_auto_detection_does_not_require_config(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);uri=(root/'main.gs').as_uri();events=[];server=Server(events.append)
            server.handle('initialize',{'rootUri':root.as_uri()})
            server.handle('textDocument/didOpen',{'textDocument':{'uri':uri,'version':1,'text':'extern "C" func puts(text cptr<cchar>) i32\nputs(cstr("ok"))'}})
            self.assertEqual(events[-1]['params']['diagnostics'],[])
