"""TypeScript-backed external-module checking with content-validated caching."""
import hashlib
from importlib.resources import files
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from parser.syntax import CompileError


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fingerprint(path, kind):
    path = Path(path)
    try:
        if kind == 'directory':
            return [path.is_dir(), str(path.resolve())]
        if not path.is_file():
            return None
        return [str(path.resolve()), _digest(path)]
    except OSError:
        return None


def find_typescript(entry, override=None):
    if override:
        candidate = Path(override).resolve()
        if candidate.is_dir():
            candidate = candidate / 'lib/typescript.js'
        if candidate.is_file():
            return candidate
        raise CompileError(f'TypeScript compiler not found: {candidate}')
    for parent in dict.fromkeys([entry.parent, *entry.parent.parents, Path(__file__).resolve().parent.parent]):
        candidate = parent / 'node_modules/typescript/lib/typescript.js'
        if candidate.is_file():
            return candidate.resolve()
    raise CompileError('external module checking requires TypeScript; run npm install --save-dev typescript@5.9.3 in your project or use --typescript PATH')


class ExternalChecker:
    def __init__(self, project, format='mjs', cache=True, cache_dir=None, typescript=None):
        self.project, self.format = project, format
        self.cache_dir = Path(cache_dir) if cache_dir else project.root / '.gs-cache'
        self.use_cache, self.override = cache, typescript
        self.stats = {'cache_hit': False, 'seconds': 0.0}

    def run(self):
        start = time.perf_counter()
        ts = find_typescript(self.project.entry, self.override)
        node = shutil.which('node')
        if not node:
            raise CompileError('external module checking requires Node.js 22 or newer')
        bridge = files('gscript').joinpath('typescript_bridge.cjs').read_text(encoding='utf-8')
        sources = []
        for module in self.project.modules.values():
            sources.append({'fileName': str(module.source) + '.mts', 'sourcePath': str(module.source),
                            'sourceText': module.source_text,
                            'text': self.project.emit(module, 'ts', checking=True),
                            'runtimeText': self.project.emit(module, 'ts', runtime_format=self.format)})
        request = {'typescript': str(ts), 'entry': str(self.project.entry),
                   'root': str(self.project.root), 'sources': sources, 'format': self.format}
        identity = json.dumps(request, sort_keys=True, ensure_ascii=True) + bridge + _digest(ts)
        key = hashlib.sha256(identity.encode()).hexdigest()
        cache_file = self.cache_dir / 'v0.4' / (key + '.json')
        result = self._read_cache(cache_file) if self.use_cache else None
        if result is not None:
            self.stats['cache_hit'] = True
        else:
            # A real file works with normal installs, zipapps and PyInstaller;
            # the bridge is package data, not a path into the user's checkout.
            with tempfile.TemporaryDirectory(prefix='gs-types-') as directory:
                script = Path(directory) / 'bridge.cjs'
                script.write_text(bridge, encoding='utf-8')
                try:
                    process = subprocess.run([node, str(script)], input=json.dumps(request),
                                             text=True, capture_output=True, timeout=60)
                except (OSError, subprocess.TimeoutExpired) as error:
                    raise CompileError(f'external type checker could not complete: {error}') from error
                if process.returncode:
                    raise CompileError('external type checker failed: ' + process.stderr.strip()[:3000])
                try:
                    result = json.loads(process.stdout)
                except ValueError as error:
                    raise CompileError('external type checker returned an invalid response') from error
            if not self._valid_result(result):
                raise CompileError('external type checker returned an invalid response')
            if not result.get('diagnostics') and self.use_cache:
                self._write_cache(cache_file, result)
        self.stats['seconds'] = time.perf_counter() - start
        diagnostics = result.get('diagnostics', [])
        if diagnostics:
            first = diagnostics[0]
            message = f'TS{first["code"]}: {first["message"]}'
            if len(diagnostics) > 1:
                message += f' ({len(diagnostics) - 1} further diagnostics)'
            error = CompileError(message, first.get('line'), first.get('column'))
            error.filename = first.get('file', str(self.project.entry))
            error.diagnostics = diagnostics
            raise error
        return result

    def _valid_result(self, result):
        if not isinstance(result, dict) or not isinstance(result.get('diagnostics'), list):
            return False
        if result['diagnostics']:
            return all(isinstance(d, dict) and isinstance(d.get('message'), str) and isinstance(d.get('code'), int)
                       for d in result['diagnostics'])
        if not isinstance(result.get('gsFiles'), dict) or set(result['gsFiles']) != {str(p) for p in self.project.modules}:
            return False
        if not all(isinstance(code, str) for code in result['gsFiles'].values()) or not isinstance(result.get('files'), list):
            return False
        for item in result['files']:
            if not isinstance(item, dict) or not isinstance(item.get('source'), str) or not isinstance(item.get('code'), str):
                return False
            if item.get('extension') not in ('js', 'mjs', 'cjs', 'ts', 'tsx', 'mts', 'cts'):
                return False
            if item.get('declaration'):
                declaration = item['declaration']
                if not isinstance(declaration, dict) or declaration.get('extension') not in ('d.ts', 'd.mts', 'd.cts') or not isinstance(declaration.get('code'), str):
                    return False
        return True

    def _read_cache(self, path):
        try:
            cache = json.loads(path.read_text(encoding='utf-8'))
            if cache.get('schema') != 1:
                return None
            for dependency in cache['dependencies']:
                if _fingerprint(dependency['file'], dependency['kind']) != dependency['fingerprint']:
                    return None
            result = cache['result']
            if not self._valid_result(result) or result['diagnostics']:
                return None
            return result
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return None

    def _write_cache(self, path, result):
        dependencies = []
        for dependency in result.get('dependencies', []):
            fingerprint = _fingerprint(dependency['file'], dependency['kind'])
            if dependency.get('readHash') and (fingerprint is None or fingerprint[1] != dependency['readHash']):
                return  # A dependency changed while TypeScript was reading it.
            dependencies.append({**dependency, 'fingerprint': fingerprint})
        try:
            from .project import write_output
            write_output(path, json.dumps({'schema': 1, 'dependencies': dependencies, 'result': result}))
        except OSError:
            # Caching is optional. A read-only source tree still type-checks.
            pass
