import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from gscript.build import configure,build
from gscript.cache import BuildSession,CheckSession,ParseCache
from gscript import CompileError
from gscript.lsp import Server

ROOT=Path(__file__).resolve().parents[1]


class IncrementalTests(unittest.TestCase):
    def test_unchanged_modules_are_not_reparsed_or_reemitted(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);entry=root/'main.gs';library=root/'lib.gs'
            entry.write_text('import { f } from "./lib.gs"\nprintln(f(1))')
            library.write_text('export func f(n int) int { return n+1 }')
            settings=configure(entry);session=BuildSession()
            with patch('subprocess.Popen',side_effect=AssertionError('pure GS build must not spawn external processes')):
                build(settings,session=session)
                parsed,emitted=session.parse_cache.parsed,session.emitted
                first=(root/'dist/main.js').stat().st_mtime_ns
                build(settings,session=session)
                self.assertEqual((session.parse_cache.parsed,session.emitted),(parsed,emitted))
                library.write_text('export func f(n int) int { return n+2 }')
                build(settings,session=session)
                self.assertEqual(session.parse_cache.parsed,parsed+1)
                self.assertEqual(session.emitted,emitted+1)
                self.assertEqual((root/'dist/main.js').stat().st_mtime_ns,first)
                before=(root/'dist/lib.js').read_text()
                library.write_text('export func f(n int) int { return "bad" }')
                with self.assertRaises(CompileError):build(settings,session=session)
                self.assertEqual((root/'dist/lib.js').read_text(),before)

    def test_cached_syntax_never_shares_checked_scopes(self):
        cache=ParseCache(positions=True)
        a=cache.parse('a.gs','x := 3\nprintln(x)');b=cache.parse('b.gs','x := 3\nprintln(x)')
        a.children[0].children[0].value='changed'
        self.assertEqual(b.children[0].children[0].value,'x')
        self.assertEqual(cache.parsed,1)
        self.assertTrue(hasattr(b.tokens[0],'kind'))

    def test_unrelated_open_document_reuses_checked_project(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);server=Server(lambda x:None);server.handle('initialize',{'rootUri':root.as_uri()})
            for name in ('one','two'):
                server.handle('textDocument/didOpen',{'textDocument':{'uri':(root/(name+'.gs')).as_uri(),'version':1,'text':'println("'+name+'")'}})
            before=server.session.checks
            server.handle('textDocument/didChange',{'textDocument':{'uri':(root/'one.gs').as_uri(),'version':2},'contentChanges':[{'text':'println("changed")'}]})
            self.assertEqual(server.session.checks,before+1)

    @unittest.skipIf(sys.platform=='win32','POSIX SIGINT process control; Windows uses console Ctrl+C')
    def test_watch_rebuild_and_stop(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);entry=root/'main.gs';entry.write_text('println(1)')
            process=subprocess.Popen([sys.executable,'-m','gscript','watch','--interval','0.05'],cwd=root,env={**os.environ,'PYTHONPATH':str(ROOT)},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            self.addCleanup(lambda:process.kill() if process.poll() is None else None)
            output=queue.Queue()
            threading.Thread(target=lambda:[output.put(line) for line in process.stdout],daemon=True).start()
            self.assertIn('Built',output.get(timeout=15))
            entry.write_text('println(2)')
            self.assertIn('Built',output.get(timeout=15))
            self.assertEqual(subprocess.check_output(['node',str(root/'dist/main.js')],text=True),'2\n')
            process.send_signal(signal.SIGINT);process.wait(timeout=10)
            self.assertEqual(process.returncode,0)
            process.stdout.close();process.stderr.close()

    def test_external_project_reuses_unchanged_gs_emissions(self):
        with tempfile.TemporaryDirectory(prefix='.gs-incremental-',dir=ROOT) as d:
            root=Path(d);entry=root/'main.gs';library=root/'lib.gs'
            (root/'foreign.ts').write_text('export const external:number=2')
            library.write_text('export func f(n int) int { return n+1 }')
            entry.write_text('import { external } from "./foreign.ts"\nimport { f } from "./lib.gs"\nprintln(external,f(1))')
            session=BuildSession();settings=configure(entry)
            build(settings,session=session);before=session.emitted
            library.write_text('export func f(n int) int { return n+2 }')
            build(settings,session=session)
            self.assertEqual(session.emitted,before+1)
            self.assertEqual(subprocess.check_output(['node',str(root/'dist/main.js')],text=True),'2 3\n')
