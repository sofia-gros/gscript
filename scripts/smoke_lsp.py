"""Verify the exact distributed LSP executable over framed stdio."""
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gscript.lsp import read_message


def main():
    executable=Path(sys.argv[1]).resolve()
    command=([sys.executable] if executable.suffix=='.pyz' else [])+[str(executable),'--stdio']
    with tempfile.TemporaryDirectory() as directory:
        directory=str(Path(directory).resolve())
        uri=(Path(directory)/'main.gs').as_uri()
        messages=[{'id':1,'method':'initialize','params':{'rootUri':Path(directory).as_uri()}},
                  {'method':'textDocument/didOpen','params':{'textDocument':{'uri':uri,'version':1,'text':'var value int = "wrong"'}}},
                  {'method':'textDocument/didChange','params':{'textDocument':{'uri':uri,'version':2},'contentChanges':[{'text':'var value int = 3\nconsole.log(value)'}]}},
                  {'id':2,'method':'textDocument/hover','params':{'textDocument':{'uri':uri},'position':{'line':1,'character':13}}},
                  {'id':3,'method':'shutdown'}, {'method':'exit'}]
        def frame(message):
            body=json.dumps(dict(jsonrpc='2.0',**message)).encode()
            return f'Content-Length: {len(body)}\r\n\r\n'.encode()+body
        p=subprocess.run(command,input=b''.join(map(frame,messages)),capture_output=True,timeout=60)
        if p.returncode:raise RuntimeError(p.stderr.decode(errors='replace'))
        stream=io.BytesIO(p.stdout);responses=[]
        while (response:=read_message(stream)) is not None:responses.append(response)
        assert responses[0]['result']['serverInfo']['version']=='0.4.0',responses
        assert 'type mismatch' in responses[1]['params']['diagnostics'][0]['message'],responses
        assert responses[2]['params']['diagnostics']==[],responses
        assert responses[3]['result']['contents']['value']=='value: number',responses
        print('Distributed GS LSP: framed stdio, native diagnostics, unsaved edits and hover passed')


if __name__=='__main__':main()
