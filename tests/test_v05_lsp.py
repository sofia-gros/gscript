from pathlib import Path
import tempfile
import unittest

from gscript.lsp import Server
from gscript.lsp_features import text_offset,codepoint_position


class EnhancedLSPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.events=[];self.server=Server(self.events.append)
        self.server.handle('initialize',{'rootUri':self.root.as_uri()})

    def open(self,name,text):
        path=self.root/name;path.write_text(text,encoding='utf-8');uri=path.as_uri()
        self.server.handle('textDocument/didOpen',{'textDocument':{'uri':uri,'version':1,'text':text}})
        return uri

    def request(self,method,uri,line,character,**extra):
        return self.server.handle('textDocument/'+method,{'textDocument':{'uri':uri},'position':{'line':line,'character':character},**extra})

    def changed(self,uri,text):
        version=self.server.documents[uri]['version']+1
        self.server.handle('textDocument/didChange',{'textDocument':{'uri':uri,'version':version},'contentChanges':[{'text':text}]})

    def apply(self,result):
        for change in result['documentChanges']:
            uri=change['textDocument']['uri'];text=self.server.documents.get(uri,{}).get('text')
            if text is None:text=Path(uri.removeprefix('file://')).read_text()
            replacements=[]
            for edit in change['edits']:
                start=codepoint_position(text,edit['range']['start']);end=codepoint_position(text,edit['range']['end'])
                replacements.append((text_offset(text,*start),text_offset(text,*end),edit['newText']))
            for start,end,new in sorted(replacements,reverse=True):text=text[:start]+new+text[end:]
            if uri in self.server.documents:self.changed(uri,text)
            else:Path(uri.removeprefix('file://')).write_text(text)

    def test_definition_references_and_rename_respect_shadowing(self):
        source='value := 1\nfunc run(value int) int { return value+1 }\nprintln(value,run(2))'
        uri=self.open('main.gs',source)
        target=self.request('definition',uri,1,34)
        self.assertEqual(target[0]['range']['start'],{'line':1,'character':9})
        refs=self.request('references',uri,0,2,context={'includeDeclaration':True})
        self.assertEqual(len(refs),2)
        result=self.request('rename',uri,0,2,newName='total')
        self.apply(result)
        updated=self.server.documents[uri]['text']
        self.assertIn('total := 1',updated)
        self.assertIn('run(value int) int { return value+1 }',updated)
        self.assertIn('println(total,run(2))',updated)

    def test_cross_module_alias_definition_and_export_rename(self):
        lib=self.open('lib.gs','export func twice(n int) int { return n*2 }')
        main=self.open('main.gs','import { twice as double } from "./lib.gs"\nprintln(double(3))')
        target=self.request('definition',main,1,9)
        self.assertEqual(target[0]['uri'],lib)
        result=self.request('rename',lib,0,14,newName='multiply')
        self.apply(result)
        self.assertIn('multiply as double',self.server.documents[main]['text'])
        self.assertIn('println(double(3))',self.server.documents[main]['text'])
        self.assertIn('func multiply',self.server.documents[lib]['text'])

    def test_local_property_completion_signature_and_format(self):
        uri=self.open('main.gs','func add(n int,s string) int {\n  local := n+1\n  println(local)\n  return local\n}\nprintln(add(1,"a"))')
        items=self.request('completion',uri,2,3)['items']
        self.assertIn('local',[i['label'] for i in items]);self.assertIn('s',[i['label'] for i in items])
        signature=self.request('signatureHelp',uri,5,15)
        self.assertIn('n: int',signature['signatures'][0]['label'])
        self.assertEqual(signature['activeParameter'],1)
        edits=self.server.handle('textDocument/formatting',{'textDocument':{'uri':uri}})
        self.assertTrue(edits)
        self.changed(uri,'type Item struct { Value int }\nx := Item{Value:3}\nx.')
        items=self.request('completion',uri,2,2)['items']
        self.assertIn('Value',[i['label'] for i in items])

    def test_shorthand_rename_preserves_property_name(self):
        uri=self.open('main.gs','Value := 3\nobj := {Value}\nprintln(obj.Value)')
        self.apply(self.request('rename',uri,0,2,newName='amount'))
        self.assertIn('{Value: amount}',self.server.documents[uri]['text'])

    def test_lint_and_auto_import(self):
        (self.root/'lib.gs').write_text('export func helper() int { return 3 }')
        uri=self.open('main.gs','var unused int = 3\nprintln("hello")')
        self.assertTrue(any(d.get('code')=='GS1001' for e in self.events for d in e.get('params',{}).get('diagnostics',[])))
        items=self.request('completion',uri,1,0)['items']
        helper=next(i for i in items if i['label']=='helper')
        self.assertIn('import { helper }',helper['additionalTextEdits'][0]['newText'])

    def test_rename_rejects_capture(self):
        uri=self.open('main.gs','x := 1\ny := 2\nprintln(x,y)')
        with self.assertRaisesRegex(ValueError,'capture|invalid'):self.request('rename',uri,0,0,newName='y')

    def test_range_catch_bindings_and_constructor_signature(self):
        uri=self.open('main.gs','for i,v := range []int{1,2} { println(i,v) }\ntry { throw "x" } catch err { println(err) }')
        self.assertEqual(self.request('definition',uri,0,38)[0]['range']['start']['character'],4)
        self.assertEqual(self.request('definition',uri,1,38)[0]['range']['start']['character'],24)
        self.changed(uri,'type Item struct { Value int }\nfunc (x Item) constructor(n int) { x.Value=n }\nx := new Item(3)\nprintln(x.Value)')
        signature=self.request('signatureHelp',uri,2,15)
        self.assertIn('n: int',signature['signatures'][0]['label'])
