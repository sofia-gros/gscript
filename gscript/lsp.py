"""Dependency-free LSP 3.17 server using the GS compiler, over stdio."""
import argparse
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlparse
from urllib.request import url2pathname

from . import __version__
from .project import Project
from parser.compiler import CompileError, parse_code
from parser.checker import unwrap
from parser.syntax import tokenize

KEYWORDS = 'func type struct interface enum extends implements constructor super override static public private protected readonly var const return if else for range switch case default break continue async await new export import true false nil undefined int float number string bool any void'.split()


def path_from_uri(uri):
    parsed = urlparse(uri)
    if parsed.scheme != 'file' or parsed.netloc not in ('', 'localhost'):
        raise ValueError('GS language server requires local file URIs')
    return Path(url2pathname(parsed.path)).resolve()


def position(text, line, column):
    lines = text.splitlines()
    row = min(max((line or 1)-1, 0), max(len(lines)-1, 0))
    content = lines[row] if lines else ''
    col = min(max((column or 1)-1, 0), len(content))
    return {'line': row, 'character': len(content[:col].encode('utf-16-le'))//2}


def declarations(program, text):
    result = []
    for original in program.children:
        node = unwrap(original)
        if node.kind == 'func':
            name, kind = node.value[0], 6 if node.value[4] else 12
        elif node.kind in ('struct', 'interface', 'alias', 'enum'):
            name, kind = node.value[0], {'struct':23, 'interface':11, 'alias':26, 'enum':10}[node.kind]
        elif node.kind == 'decl':
            name, kind = node.value[1], 13
        else:
            continue
        if not isinstance(name, str):
            continue
        lines = text.splitlines()
        line = lines[node.line-1] if node.line <= len(lines) else ''
        match = re.search(r'\b'+re.escape(name)+r'\b', line)
        start = position(text, node.line, match.start()+1 if match else 1)
        end = dict(start, character=start['character']+len(name))
        result.append({'name':name, 'kind':kind, 'range':{'start':start,'end':end}, 'selectionRange':{'start':start,'end':end}})
    return result


class Server:
    def __init__(self, send):
        self.send = send
        self.documents = {}
        self.projects = {}
        self.published = set()
        self.roots = []
        self.strict_null = False
        self.stopped = False

    def notify(self, method, params):
        self.send({'jsonrpc':'2.0','method':method,'params':params})

    def root_for(self, path):
        return max((r for r in self.roots if path.is_relative_to(r)), key=lambda r:len(r.parts), default=path.parent)

    def validate(self):
        diagnostics = {uri:[] for uri in self.documents}
        sources = {path_from_uri(uri):doc['text'] for uri,doc in self.documents.items()}
        self.projects = {}
        for uri in self.documents:
            path = path_from_uri(uri)
            try:
                project = Project(path, self.root_for(path), sources=sources, strict_null=self.strict_null).check()
                self.projects[uri] = project
            except (CompileError, OSError, UnicodeError, ValueError) as error:
                filename = Path(getattr(error,'filename',None) or path).resolve()
                target = next((open_uri for open_uri in self.documents if path_from_uri(open_uri)==filename),filename.as_uri())
                text = sources.get(filename, '')
                if not text:
                    try:text = filename.read_text(encoding='utf-8')
                    except (OSError,UnicodeError):pass
                start = position(text, getattr(error,'line',1), getattr(error,'column',1))
                lines = text.splitlines()
                line = lines[start['line']] if lines else ''
                end = dict(start,character=max(start['character']+1,len(line.encode('utf-16-le'))//2))
                diagnostic = {'range':{'start':start,'end':end},'severity':1,'source':'gs','message':getattr(error,'message',str(error))}
                items = diagnostics.setdefault(target,[])
                if diagnostic not in items:items.append(diagnostic)
        for uri in self.published | diagnostics.keys():
            params = {'uri':uri,'diagnostics':diagnostics.get(uri,[])}
            if uri in self.documents:params['version']=self.documents[uri]['version']
            self.notify('textDocument/publishDiagnostics',params)
        self.published = set(diagnostics)

    def handle(self, method, params):
        if method == 'initialize':
            folders = params.get('workspaceFolders') or []
            if not folders and params.get('rootUri'):folders=[{'uri':params['rootUri']}]
            self.roots = [path_from_uri(f['uri']) for f in folders]
            self.strict_null = bool((params.get('initializationOptions') or {}).get('strictNull',False))
            return {'capabilities':{'positionEncoding':'utf-16','textDocumentSync':{'openClose':True,'change':1,'save':{'includeText':True}},'hoverProvider':True,'completionProvider':{'resolveProvider':False},'documentSymbolProvider':True},'serverInfo':{'name':'gs-lsp','version':__version__}}
        if method == 'shutdown':
            self.stopped = True
            return None
        if self.stopped:
            raise ValueError('server has shut down')
        if method == 'textDocument/didOpen':
            doc = params['textDocument'];path_from_uri(doc['uri'])
            self.documents[doc['uri']] = dict(doc)
            self.validate()
        elif method == 'textDocument/didChange':
            doc = params['textDocument'];current = self.documents[doc['uri']]
            if doc['version'] <= current['version']:return None
            changes = params['contentChanges']
            if any('range' in change for change in changes):raise ValueError('full document synchronization required')
            if changes:current.update(text=changes[-1]['text'],version=doc['version']);self.validate()
        elif method == 'textDocument/didSave':
            uri = params['textDocument']['uri']
            if uri in self.documents and 'text' in params:self.documents[uri]['text']=params['text']
            self.validate()
        elif method == 'textDocument/didClose':
            uri = params['textDocument']['uri'];self.documents.pop(uri,None);self.validate()
        elif method == 'workspace/didChangeWatchedFiles':self.validate()
        elif method in ('textDocument/hover','textDocument/completion','textDocument/documentSymbol'):
            uri = params['textDocument']['uri'];doc = self.documents.get(uri)
            if not doc:return [] if method != 'textDocument/hover' else None
            project = self.projects.get(uri)
            module = project.modules[path_from_uri(uri)] if project else None
            if method == 'textDocument/completion':
                items = [{'label':word,'kind':14} for word in KEYWORDS]
                if module:
                    items += [{'label':name,'kind':6 if symbol.typ.kind=='function' else 6 if symbol.category=='function' else 5,'detail':str(symbol.typ)} for name,symbol in module.checker.scopes[0].items() if name not in KEYWORDS]
                return {'isIncomplete':False,'items':items}
            if method == 'textDocument/documentSymbol':
                try:return declarations(module.program if module else parse_code(doc['text']),doc['text'])
                except CompileError:return []
            if not module:return None
            cursor=params['position'];row=cursor['line']+1
            tokens=[t for t in tokenize(doc['text']) if t.line==row and t.kind=='name']
            for token in tokens:
                start=position(doc['text'],row,token.column)
                if start['character'] <= cursor['character'] < start['character']+len(token.text):
                    # Use the checked expression at this source line, preserving local shadowing.
                    matches=[]
                    def visit(node):
                        if node.kind=='name' and node.value==token.text and node.line==row:
                            typ=module.checker.types.get(id(node))
                            if typ is not None:matches.append(typ)
                        for child in node.children:visit(child)
                    visit(module.program)
                    if matches and all(t==matches[0] for t in matches):
                        return {'contents':{'kind':'plaintext','value':token.text+': '+str(matches[0])},'range':{'start':start,'end':dict(start,character=start['character']+len(token.text))}}
            return None
        elif method in ('initialized','$/cancelRequest','$/setTrace'):return None
        elif not method.startswith('$/'):raise LookupError(method)
        return None


def read_message(stream):
    headers = {}
    while True:
        line=stream.readline()
        if not line:return None
        if line in (b'\r\n',b'\n'):break
        key,value=line.decode('ascii').split(':',1);headers[key.lower()]=value.strip()
    length=int(headers.get('content-length','0'))
    if length<=0 or length>16*1024*1024:raise ValueError('invalid Content-Length')
    body=bytearray()
    while len(body)<length:
        chunk=stream.read(length-len(body))
        if not chunk:raise ValueError('truncated JSON-RPC message')
        body.extend(chunk)
    return json.loads(body)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stdio',action='store_true',help='use standard input/output (default)')
    parser.add_argument('--version',action='version',version=f'gs-lsp {__version__}')
    parser.parse_args(argv)
    def send(message):
        body=json.dumps(message,ensure_ascii=False).encode('utf-8')
        sys.stdout.buffer.write(f'Content-Length: {len(body)}\r\n\r\n'.encode('ascii')+body);sys.stdout.buffer.flush()
    server=Server(send)
    while True:
        try:message=read_message(sys.stdin.buffer)
        except (ValueError,UnicodeError) as error:
            print(str(error),file=sys.stderr);return 1
        if message is None:return 0 if server.stopped else 1
        if message.get('method')=='exit':return 0 if server.stopped else 1
        request_id=message.get('id');is_request='id' in message
        try:
            result=server.handle(message.get('method',''),message.get('params') or {})
            if is_request:send({'jsonrpc':'2.0','id':request_id,'result':result})
        except Exception as error:
            if is_request:send({'jsonrpc':'2.0','id':request_id,'error':{'code':-32601 if isinstance(error,LookupError) else -32603,'message':str(error)}})
            else:server.notify('window/logMessage',{'type':1,'message':str(error)})


if __name__=='__main__':sys.exit(main())
