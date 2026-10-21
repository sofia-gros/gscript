"""Read external declaration metadata; all GS compatibility rules live in Python."""
import hashlib
import json
from importlib.resources import files
from pathlib import Path
import queue
import shutil
import subprocess
import tempfile
import threading
from parser.syntax import CompileError
from parser.checker import Type, ANY, NUMBER, STRING, BOOL, VOID, NULL
from parser.extended_checker import UNDEFINED, UNKNOWN, NEVER, union
from .interop import find_typescript, _fingerprint, _digest


class Declarations:
    def __init__(self, project):
        self.project,self.cache,self.type_cache=project,{},{}
        self.process=None
        self.closed=False
        sources=[]
        for module in project.modules.values():
            imports=[]
            for n in module.program.children:
                if n.kind!='import' or id(n) in module.imports:continue
                binding,literal=n.value
                imports.append('import '+(binding+' from ' if binding else '')+literal+';')
            sources.append({'fileName':str(module.source)+'.declarations.mts','text':'\n'.join(imports)})
        self.script=files('gscript').joinpath('declarations.cjs').read_text(encoding='utf-8')
        self.init_request={'action':'init','typescript':str(find_typescript(project.entry,project.interop_options['typescript'])),'sources':sources}
        identity=json.dumps(self.init_request,sort_keys=True)+self.script+_digest(Path(self.init_request['typescript']))
        key=hashlib.sha256(identity.encode()).hexdigest()
        directory=project.interop_options['cache_dir'] or project.root/'.gs-cache'
        self.cache_file=Path(directory)/'v0.4-native'/(key+'.json')
        self.use_cache=project.interop_options['cache']
        if self.use_cache:
            try:
                data=json.loads(self.cache_file.read_text(encoding='utf-8'))
                if data['schema']==1 and all(_fingerprint(p['file'],p['kind'])==p['fingerprint'] for p in data['dependencies']):
                    entries=data['queries']
                    if self._valid_queries(entries):self.cache=dict(entries)
            except (OSError,ValueError,KeyError,TypeError,AttributeError):pass
        try:
            result=self.query(**self.init_request)
            if result['diagnostics']:raise CompileError('external declaration resolution: '+result['diagnostics'][0])
        except Exception:
            self.close();raise

    def _valid_queries(self,entries):
        try:
            if not isinstance(entries,list) or not entries:return False
            if json.loads(entries[0][0])!=self.init_request:return False
            for key,result in entries:
                q=json.loads(key)
                action=q['action']
                if action=='init':
                    if not isinstance(result,dict) or result.get('ready') is not True or not isinstance(result.get('diagnostics'),list):return False
                elif action in ('resolve','named_type'):
                    if not isinstance(result,dict) or not isinstance(result.get('type'),int):return False
                    if action=='resolve' and not isinstance(result.get('value'),int):return False
                elif action=='describe':
                    if not isinstance(result,dict) or result.get('kind') not in ('any','unknown','never','number','string','bool','void','null','undefined','foreign','literal','param','union','array','promise'):return False
                    if result['kind'] in ('union','array','promise') and not all(isinstance(x,int) for x in result['args']):return False
                    if result['kind']=='foreign':
                        if not isinstance(result.get('calls'),list) or not isinstance(result.get('constructors'),list):return False
                        for sig in result['calls']+result['constructors']:
                            if not isinstance(sig,dict) or not isinstance(sig.get('result'),int) or not isinstance(sig.get('params'),list) or not isinstance(sig.get('parameters'),list):return False
                            if not all(isinstance(p,dict) and isinstance(p.get('type'),int) and isinstance(p.get('optional'),bool) and isinstance(p.get('rest'),bool) for p in sig['params']):return False
                            if not all(isinstance(p,dict) and isinstance(p.get('name'),str) and isinstance(p.get('type'),int) for p in sig['parameters']):return False
                    if result['kind']=='param' and (not isinstance(result.get('name'),str) or result.get('constraint') is not None and not isinstance(result.get('constraint'),int)):return False
                    if result['kind']=='literal' and result.get('base') not in ('number','string','bool'):return False
                elif action=='property':
                    if result is not None and (not isinstance(result,dict) or not isinstance(result.get('type'),int) or not isinstance(result.get('optional'),bool) or not isinstance(result.get('readonly'),bool) or result.get('access') not in ('public','private','protected')):return False
                elif action=='fields':
                    if not isinstance(result,list) or not all(isinstance(p,dict) and isinstance(p.get('name'),str) and isinstance(p.get('type'),int) and isinstance(p.get('optional'),bool) for p in result):return False
                else:return False
            return True
        except (ValueError,TypeError,KeyError,IndexError):return False

    def _start(self):
        node=shutil.which('node')
        if not node:raise CompileError('reading external declarations requires Node.js')
        self.temporary=tempfile.TemporaryDirectory(prefix='gs-declarations-')
        script=Path(self.temporary.name)/'declarations.cjs'
        script.write_text(self.script,encoding='utf-8')
        self.process=subprocess.Popen([node,str(script)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL,text=True,encoding='utf-8',bufsize=1)
        self.responses=queue.Queue()
        def reader():
            for line in self.process.stdout:self.responses.put(line)
            self.responses.put(None)
        self.thread=threading.Thread(target=reader,daemon=True);self.thread.start()
        # Replay queries in order to preserve opaque declaration IDs.
        for key,expected in self.cache.items():
            actual=self._exchange(json.loads(key))
            if actual!=expected:raise CompileError('external declarations changed during compilation; retry')

    def _exchange(self,query):
        try:
            self.process.stdin.write(json.dumps(query)+'\n');self.process.stdin.flush()
            line=self.responses.get(timeout=60)
            response=json.loads(line) if line else {}
        except (OSError,ValueError,queue.Empty) as error:raise CompileError('external declaration reader failed or timed out') from error
        if 'error' in response:raise CompileError('external declaration reader: '+response['error'].split('\n')[0])
        if 'result' not in response:raise CompileError('external declaration reader exited unexpectedly')
        return response['result']

    def query(self,**query):
        key=json.dumps(query,sort_keys=True)
        if key in self.cache:return self.cache[key]
        if self.closed:raise CompileError('declaration metadata was not prepared during GS checking')
        if self.process is None:self._start()
        result=self._exchange(query)
        self.cache[key]=result
        return result

    def resolve(self,module,name):
        result=self.query(action='resolve',file=str(module)+'.declarations.mts',name=name)
        return self.typ(result['value']),self.typ(result['type'])

    def typ(self,id):
        if id in self.type_cache:return self.type_cache[id]
        d=self.query(action='describe',id=id)
        kind=d['kind']
        primitives={'any':ANY,'unknown':UNKNOWN,'never':NEVER,'number':NUMBER,'string':STRING,'bool':BOOL,'void':VOID,'null':NULL,'undefined':UNDEFINED}
        if kind in primitives:typ=primitives[kind]
        elif kind=='foreign':typ=Type('foreign',str(id))
        elif kind=='literal':typ=Type('literal',json.dumps(d['value'],ensure_ascii=False,separators=(',',':')),(primitives[d['base']],))
        elif kind=='param':typ=Type('param',d['name']+'@'+str(id),(self.typ(d['constraint']) if d['constraint'] is not None else UNKNOWN,))
        elif kind=='union':typ=union(*(self.typ(t) for t in d['args']))
        else:typ=Type(kind,args=tuple(self.typ(t) for t in d['args']))
        self.type_cache[id]=typ
        return typ

    def describe(self,typ):return self.query(action='describe',id=int(typ.name))
    def property(self,typ,name):return self.query(action='property',id=int(typ.name),name=name)
    def fields(self,typ):return self.query(action='fields',id=int(typ.name))

    def close(self):
        if self.closed:return
        self.closed=True
        if self.process is not None:
            try:
                dependencies=self._exchange({'action':'dependencies'})
                fingerprints=[{**p,'fingerprint':_fingerprint(p['file'],p['kind'])} for p in dependencies]
                if self.use_cache and all(not p.get('readHash') or p['fingerprint'] is not None and p['fingerprint'][1]==p['readHash'] for p in fingerprints):
                    from .project import write_output
                    write_output(self.cache_file,json.dumps({'schema':1,'queries':list(self.cache.items()),'dependencies':fingerprints}))
            except (OSError,CompileError):pass
            finally:
                self.process.stdin.close()
                try:self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
                self.thread.join(timeout=5)
                self.process.stdout.close()
                self.temporary.cleanup()
