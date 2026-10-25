"""Dependency-free LSP 3.17 server using the GS compiler, over stdio."""
import argparse
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlparse,unquote
from urllib.request import url2pathname

from . import __version__
from .project import Project
from parser.compiler import CompileError, parse_code
from parser.checker import unwrap
from parser.syntax import tokenize

KEYWORDS = 'func type struct interface enum extends implements constructor super override static public private protected readonly var const return if else for range switch case default break continue async await new export import true false nil undefined int float float64 number string bool any unknown never void try catch throw typeof instanceof'.split()


class UnknownMethod(LookupError):
    pass


def file_uri_path(uri,windows=False):
    parsed=urlparse(uri)
    if parsed.scheme!='file' or parsed.netloc not in ('','localhost') or parsed.query or parsed.fragment:
        raise ValueError('GS language server requires local file URIs')
    # Decode exactly once, before recognizing a Windows drive. Zed may encode ':' as %3A.
    decoded=unquote(parsed.path,errors='strict')
    if windows:
        import ntpath
        if re.match(r'^/[A-Za-z]:',decoded):decoded=decoded[1:]
        decoded=decoded.replace('/','\\')
        drive,tail=ntpath.splitdrive(decoded)
        if not drive or not tail.startswith('\\'):raise ValueError('Windows file URI must contain an absolute drive path')
        return ntpath.normpath(decoded)
    if not decoded.startswith('/'):raise ValueError('file URI must be absolute')
    return decoded


def path_from_uri(uri):
    return Path(file_uri_path(uri,windows=sys.platform=='win32')).resolve()


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
        from .cache import CheckSession
        self.session=CheckSession(positions=True)
        self.parse_cache=self.session.parse_cache
        self.send = send
        self.documents = {}
        self.projects = {}
        self.partial_projects = {}
        self.native_projects = {}
        self.published = set()
        self.roots = []
        self.strict_null = None
        self.stopped = False

    def notify(self, method, params):
        self.send({'jsonrpc':'2.0','method':method,'params':params})

    def root_for(self, path):
        return max((r for r in self.roots if path.is_relative_to(r)), key=lambda r:len(r.parts), default=path.parent)

    def validate(self):
        diagnostics = {uri:[] for uri in self.documents}
        sources = {path_from_uri(uri):doc['text'] for uri,doc in self.documents.items()}
        self.projects = {}
        self.partial_projects = {}
        self.native_projects = {}
        for uri in self.documents:
            path = path_from_uri(uri)
            project=None
            try:
                from .build import configure
                options=configure(path,root=self.root_for(path),strict_null=self.strict_null)
                from .native import lsp as native_lsp
                if native_lsp.detect(options,sources[path]):
                    project=native_lsp.check(path,options,sources);self.native_projects[uri]=project
                    project.check();continue
                project=self.session.check(path,options.root,sources=sources,strict_null=options.strict_null,libraries=options.libraries,positions=True)
                self.projects[uri] = project
                from .lint import lint_project
                for warning in lint_project(project):
                    filename=Path(warning.file).resolve()
                    target=next((u for u in self.documents if path_from_uri(u)==filename),filename.as_uri())
                    text=sources.get(filename)
                    if text is None:
                        warning_module=project.modules.get(filename)
                        text=warning_module.source_text if warning_module else ''
                    start=position(text,warning.line,warning.column)
                    item={'range':{'start':start,'end':dict(start,character=start['character']+1)},'severity':2,'source':'gs-lint','code':warning.code,'message':warning.message}
                    if item not in diagnostics.setdefault(target,[]):diagnostics[target].append(item)
            except (CompileError, OSError, UnicodeError, ValueError) as error:
                project=project or self.session.last_project
                if project and uri not in self.native_projects and path in project.modules and project.modules[path].checker:self.partial_projects[uri]=project
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
            self.strict_null = (params.get('initializationOptions') or {}).get('strictNull')
            return {'capabilities':{'positionEncoding':'utf-16','textDocumentSync':{'openClose':True,'change':1,'save':{'includeText':True}},'hoverProvider':True,'completionProvider':{'resolveProvider':False,'triggerCharacters':['.']},'documentSymbolProvider':True,'definitionProvider':True,'referencesProvider':True,'renameProvider':{'prepareProvider':True},'signatureHelpProvider':{'triggerCharacters':['(',',']},'documentFormattingProvider':True},'serverInfo':{'name':'gs-lsp','version':__version__}}
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
        elif method in ('textDocument/hover','textDocument/completion','textDocument/documentSymbol','textDocument/definition','textDocument/references','textDocument/prepareRename','textDocument/rename','textDocument/signatureHelp','textDocument/formatting'):
            if params['textDocument']['uri'] in self.native_projects:
                from .native.lsp import handle
                return handle(self,method,params,self.native_projects[params['textDocument']['uri']])
            from .lsp_features import handle_feature
            return handle_feature(self,method,params)
        elif method in ('initialized','$/cancelRequest','$/setTrace'):return None
        elif not method.startswith('$/'):raise UnknownMethod(method)
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
            if is_request:send({'jsonrpc':'2.0','id':request_id,'error':{'code':-32601 if isinstance(error,UnknownMethod) else -32603,'message':str(error)}})
            else:server.notify('window/logMessage',{'type':1,'message':str(error)})


if __name__=='__main__':sys.exit(main())
