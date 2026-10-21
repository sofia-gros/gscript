"""Compile the real Phaser fixture and boot it in a headless Chromium browser."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import signal
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gscript.project import build_project


def main():
    browser = next((shutil.which(name) for name in ('chromium', 'chromium-browser', 'google-chrome', 'google-chrome-stable') if shutil.which(name)), None)
    if not browser:
        raise SystemExit('Chromium or Google Chrome is required for the Phaser browser release gate')
    version = json.loads((ROOT / 'node_modules/phaser/package.json').read_text())['version']
    with tempfile.TemporaryDirectory() as directory:
        output = build_project(ROOT / 'tests/fixtures/interop/phaser-scene.gs', Path(directory))
        ready=threading.Event()
        reports=[]
        observer=b'''<script>
function report(){if(document.body.dataset.result){fetch('/__result?value='+encodeURIComponent(document.body.dataset.result));return true;}return false;}
new MutationObserver(report).observe(document.body,{attributes:true});
addEventListener('error',e=>{if(e.message)fetch('/__error?value='+encodeURIComponent(e.message));});
addEventListener('unhandledrejection',e=>fetch('/__error?value='+encodeURIComponent(String(e.reason))));
</script>'''
        routes = {
            '/': ('text/html', b'<!doctype html><html><body>'+observer+b'<script type="importmap">{"imports":{"phaser":"/phaser.mjs"}}</script><script type="module" src="/app.mjs"></script></body></html>'),
            '/app.mjs': ('text/javascript', output.read_bytes()),
            '/phaser.mjs': ('text/javascript', b'import * as Phaser from "/engine.js"; export default Phaser;'),
            '/engine.js': ('text/javascript', (ROOT / 'node_modules/phaser/dist/phaser.esm.js').read_bytes()),
        }
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                parsed=urlparse(self.path)
                if parsed.path in ('/__result','/__error'):
                    reports.append((parsed.path,parse_qs(parsed.query).get('value',[''])[0]))
                    self.send_response(204)
                    self.end_headers()
                    ready.set()
                    return
                route = routes.get(self.path.split('?')[0])
                if route is None:
                    self.send_error(404)
                    return
                content_type, contents = route
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(contents)))
                self.end_headers()
                self.wfile.write(contents)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with (Path(directory)/'browser.log').open('w+',encoding='utf-8') as log:
                process=subprocess.Popen([browser,'--headless','--no-sandbox','--disable-gpu',
                    '--user-data-dir='+str(Path(directory)/'browser-profile'),
                    '--disable-dev-shm-usage','--disable-background-networking',
                    '--no-first-run','--no-default-browser-check',
                    f'http://127.0.0.1:{server.server_port}/'],
                    stdout=subprocess.DEVNULL,stderr=log,start_new_session=True,
                    env={**os.environ,'XDG_CACHE_HOME':str(Path(directory)/'cache'),
                         'XDG_CONFIG_HOME':str(Path(directory)/'config')})
                try:
                    deadline=time.monotonic()+40
                    while not ready.wait(0.1) and time.monotonic()<deadline:
                        if process.poll() is not None:break
                finally:
                    try:os.killpg(process.pid,signal.SIGTERM)
                    except ProcessLookupError:pass
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
                if not reports or reports[0]!=('/__result',f'phaser:{version}'):
                    log.seek(0)
                    raise RuntimeError('Phaser scene did not report successful startup: '+repr(reports)+'\n'+log.read()[-6000:])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
    print(f'Phaser {version}: GS compile, real type declarations and Chromium scene startup passed')


if __name__ == '__main__':
    main()
