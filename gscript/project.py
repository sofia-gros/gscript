"""Parse, link and type-check an entire GS module graph before writing output."""
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import tempfile

from parser.compiler import CompileError, parse_code
from parser.checker import Checker, Symbol, Type, ANY, import_names, unwrap
from parser.emitter import Emitter
from parser.syntax import decode_string

SOURCE_SUFFIXES = {'.gs', '.gos'}
FORMATS = ('js', 'mjs', 'ts')


def write_output(path, contents):
    """Replace one output atomically, without truncating an existing file on error."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n',
                                         dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(contents)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@dataclass
class Module:
    source: Path
    program: object
    exports: dict = field(default_factory=dict)
    imports: dict = field(default_factory=dict)
    checker: object = None


class Project:
    def __init__(self, entry, root=None):
        self.entry = Path(entry).resolve()
        self.root = Path(root).resolve() if root else self.entry.parent
        self.modules = {}
        self.order = []
        self._load(self.entry)

    def _located(self, source, action):
        try:
            return action()
        except RecursionError as error:
            failure = CompileError('source or module nesting exceeds compiler capacity')
            failure.filename = str(source)
            raise failure from error
        except (CompileError, OSError, UnicodeError) as error:
            if not getattr(error, 'filename', None):
                error.filename = str(source)
            raise

    def _load(self, source):
        if not source.is_relative_to(self.root):
            raise CompileError(f'module is outside project root {self.root}: {source}')
        if source in self.modules:
            return

        def load():
            program = parse_code(source.read_text(encoding='utf-8'))
            module = Module(source, program)
            self.modules[source] = module
            for original in program.children:
                node = unwrap(original)
                if original.kind == 'export':
                    name = node.value[1] if node.kind == 'decl' else node.value[0]
                    if name in module.exports:
                        raise CompileError(f'duplicate export: {name}', node.line)
                    module.exports[name] = Symbol(Type('pending'), category='export', initialized=False)
                elif node.kind == 'default':
                    if 'default' in module.exports:
                        raise CompileError('duplicate default export', node.line)
                    module.exports['default'] = Symbol(Type('pending'), True, 'export', initialized=False)
                if node.kind != 'import':
                    continue
                path = decode_string(node.value[1])
                if Path(path).suffix not in SOURCE_SUFFIXES:
                    continue
                if not path.startswith(('./', '../')):
                    raise CompileError('GS imports must be relative paths', node.line)
                dependency = (source.parent / path).resolve()
                if not dependency.is_file():
                    raise CompileError(f'module not found: {path}', node.line)
                module.imports[id(node)] = dependency
                self._load(dependency)
            self.order.append(module)
        self._located(source, load)

    def check(self):
        structs = {}
        exports = {str(path): module.exports for path, module in self.modules.items()}
        # Declare nominal struct identities first, so signatures can reference
        # local/imported types even through a cyclic import graph.
        for module in self.modules.values():
            checker = module.checker = Checker(str(module.source), structs, module.exports, exports)
            self._located(module.source, lambda: checker.declare_structs(module.program.children, module=True))
        for module in self.modules.values():
            for node in module.program.children:
                if node.kind == 'default' and node.children[0].kind == 'name':
                    symbol = module.checker.scopes[0].get(node.children[0].value)
                    if symbol is not None and symbol.typ.kind == 'constructor':
                        module.exports['default'].typ = symbol.typ
        for module in self.modules.values():
            self._located(module.source, lambda: self._link(module))
        for module in self.modules.values():
            checker = module.checker
            # Explicit exported variable types are available across value cycles.
            for original in module.program.children:
                node = unwrap(original)
                if original.kind == 'export' and node.kind == 'decl' and node.value[2]:
                    self._located(module.source, lambda: setattr(module.exports[node.value[1]], 'typ', checker.declared_type(node, node.value[2])))
            self._located(module.source, lambda: checker.declare_signatures(module.program.children, module=True))
            checker.prepared.add('module')
        # Top-level values are inferred in dependency order; bodies are checked
        # after all inferred export types are known, including recursive functions.
        for module in self.order:
            checker = module.checker
            checker.defer_functions = True
            self._located(module.source, lambda: checker.run(module.program))
        for module in self.order:
            checker = module.checker
            checker.defer_functions = False
            for node, scopes in checker.deferred_functions:
                old_scopes = checker.scopes
                checker.scopes = scopes
                try:
                    self._located(module.source, lambda: checker.check_function(node))
                finally:
                    checker.scopes = old_scopes
        return self

    def _link(self, module):
        checker = module.checker
        for node in module.program.children:
            if node.kind != 'import':
                continue
            dependency = module.imports.get(id(node))
            node.gs_module = dependency is not None
            if dependency is None:
                continue
            checker.prepared.add(id(node))
            binding = node.value[0]
            if binding is None:
                continue
            target = self.modules[dependency].exports
            if binding.startswith('* as '):
                name = binding.split()[-1]
                checker.bind(node, name, Type('namespace', str(dependency)), True, 'import')
                for exported, symbol in target.items():
                    if symbol.typ.kind == 'constructor':
                        checker.type_names[name + '.' + exported] = symbol.typ.name
                continue
            if binding.startswith('{'):
                pairs = [tuple(part.strip().split(' as ')) for part in binding[1:-1].split(',') if part.strip()]
                pairs = [(parts[0], parts[-1]) for parts in pairs]
            else:
                pairs = [('default', binding)]
            for exported, local in pairs:
                if exported not in target:
                    checker.fail(node, f'module {dependency.name} has no export: {exported}')
                checker.bind(node, local, target[exported].typ, True, 'import')
                checker.scopes[0][local].target = target[exported]
                if target[exported].typ.kind == 'constructor':
                    if local in {'int', 'float', 'float64', 'number', 'string', 'bool', 'boolean', 'any', 'object', 'void', 'Promise'}:
                        checker.fail(node, f'reserved type name: {local}')
                    checker.type_names[local] = target[exported].typ.name

    def emit(self, module, format='mjs', out_dir=None):
        # Each invocation restores source specifiers before rewriting; a Project
        # can safely emit multiple output formats without accumulating changes.
        original_values = []
        try:
            for node in module.program.children:
                dependency = module.imports.get(id(node))
                if dependency is None:
                    continue
                binding, literal = node.value
                original_values.append((node, node.value))
                relative = os.path.relpath(dependency, module.source.parent)
                # TypeScript NodeNext resolves .js imports to .ts source files.
                extension = 'js' if format == 'ts' else format
                specifier = str(Path(relative).with_suffix('.' + extension)).replace(os.sep, '/')
                node.value = (binding, json.dumps(specifier if specifier.startswith('.') else './' + specifier))
            return Emitter(format=format, checker=module.checker).compile(module.program)
        finally:
            for node, value in original_values:
                node.value = value


def module_marker(directory):
    """Plan an ESM marker without overwriting a user's package settings."""
    marker = directory / 'package.json'
    if marker.exists():
        try:
            package = json.loads(marker.read_text(encoding='utf-8'))
        except (ValueError, UnicodeError) as error:
            raise CompileError(f'invalid package.json: {marker}') from error
        if not isinstance(package, dict) or package.get('type') != 'module':
            raise CompileError(f'ES module output requires type=module in {marker}; use a new output directory or --format mjs')
        return None
    return marker


def build_project(entry, out_dir, root=None, format='mjs', check_only=False):
    if format not in FORMATS:
        raise CompileError(f'unsupported output format: {format}')
    project = Project(entry, root).check()
    if check_only:
        return None
    out_dir = Path(out_dir).resolve()
    outputs = {}
    for module in project.modules.values():
        output = out_dir / module.source.relative_to(project.root).with_suffix('.' + format)
        if output.resolve() in project.modules:
            raise CompileError('build output must not overwrite a source file')
        if output in outputs:
            raise CompileError(f'output path collision: {output}')
        outputs[output] = project.emit(module, format)
    if format in ('js', 'ts'):
        marker = module_marker(out_dir)
        if marker:
            outputs[marker] = '{"type":"module"}\n'
    for output, contents in outputs.items():
        write_output(output, contents)
    return out_dir / project.entry.relative_to(project.root).with_suffix('.' + format)
