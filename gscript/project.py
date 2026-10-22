"""Parse, link and type-check an entire GS module graph before writing output."""
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import tempfile

from parser.compiler import CompileError, parse_code
from parser.checker import Checker, Symbol, Type, ANY, EXTERNAL, import_names, unwrap
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
    source_text: str = ''


class Project:
    def __init__(self, entry, root=None, format='mjs', cache=True, cache_dir=None, typescript=None, strict_null=False, sources=None, libraries=None, prepare_output=True, parse_cache=None, positions=False, analysis_info=False):
        self.libraries=libraries or []
        self.prepare_output=prepare_output
        self.parse_cache=parse_cache
        self.positions=positions
        self.analysis_info=analysis_info or positions
        self.sources = {Path(path).resolve(): text for path, text in (sources or {}).items()}
        self.strict_null = strict_null
        self.format = format
        self.interop_options = {'cache': cache, 'cache_dir': cache_dir, 'typescript': typescript}
        self.has_external = False
        self.external_results = {}
        self.interop_stats = {}
        self.entry = Path(entry).resolve()
        self.root = Path(root).resolve() if root else self.entry.parent
        self.modules = {}
        self.order = []
        self._load(self.entry)
        self.extended = strict_null or bool(self.libraries) or self.has_external or any(getattr(m.program, "extended", False) for m in self.modules.values())

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
        # Explicit DFS avoids Python recursion limits on long module chains.
        stack = [(source, False)]
        while stack:
            current, exiting = stack.pop()
            if exiting:
                self.order.append(self.modules[current])
                continue
            if not current.is_relative_to(self.root):
                raise CompileError(f'module is outside project root {self.root}: {current}')
            if current in self.modules:
                continue
            def load():
                text = self.sources[current] if current in self.sources else current.read_text(encoding='utf-8')
                program = self.parse_cache.parse(current,text,positions=self.positions) if self.parse_cache else parse_code(text,positions=self.positions)
                module = Module(current, program, source_text=text)
                self.modules[current] = module
                dependencies = []
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
                        self.has_external = True
                        continue
                    if not path.startswith(('./', '../')):
                        raise CompileError('GS imports must be relative paths', node.line)
                    dependency = (current.parent / path).resolve()
                    if dependency not in self.sources and not dependency.is_file():
                        raise CompileError(f'module not found: {path}', node.line)
                    module.imports[id(node)] = dependency
                    dependencies.append(dependency)
                return dependencies
            dependencies = self._located(current, load)
            stack.append((current, True))
            stack.extend((dependency, False) for dependency in reversed(dependencies))

    def check(self):
        try:
            return self._check()
        finally:
            if getattr(self,"declarations",None): self.declarations.close()

    def _check(self):
        if self.extended and (self.has_external or self.libraries):
            from .declarations import Declarations
            self.declarations = Declarations(self)
        structs = {}
        exports = {str(path): module.exports for path, module in self.modules.items()}
        # Declare nominal struct identities first, so signatures can reference
        # local/imported types even through a cyclic import graph.
        for module in self.modules.values():
            if self.extended:
                from parser.extended_checker import ExtendedChecker
                checker = module.checker = ExtendedChecker(str(module.source), structs, module.exports, exports, strict_null=self.strict_null)
            else:
                checker = module.checker = Checker(str(module.source), structs, module.exports, exports)
            checker.capture_info=self.analysis_info
            if self.extended:
                checker.declarations = getattr(self,"declarations",None)
                checker.defer_validation = True
            self._located(module.source, lambda: checker.declare_structs(module.program.children, module=True))
        if self.extended:
            definitions = {k:v for m in self.modules.values() for k,v in m.checker.type_defs.items()}
            for m in self.modules.values(): m.checker.type_defs = definitions
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
        if self.extended:
            for module in self.modules.values():
                checker=module.checker
                checker.prepare_static_order()
                for original in module.program.children:
                    node=unwrap(original)
                    if node.kind=='struct':self._located(module.source,lambda:checker.validate_inheritance(node))
                    elif node.kind=='interface':self._located(module.source,lambda:checker.members(Type('interface',checker.type_names[node.value[0]])))
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
        if self.has_external and self.prepare_output:
            self._external_result(self.format)
        elif getattr(self,'declarations',None):
            self.interop_stats={'cache_hit':self.declarations.process is None}
        return self

    def _external_result(self, format):
        if format not in self.external_results:
            from .interop import ExternalChecker
            checker = ExternalChecker(self, format, **self.interop_options)
            self.external_results[format] = checker.run()
            self.interop_stats = checker.stats
        return self.external_results[format]

    def _link(self, module):
        checker = module.checker
        for node in module.program.children:
            if node.kind != 'import':
                continue
            dependency = module.imports.get(id(node))
            node.gs_module = dependency is not None
            if dependency is None:
                node.external_typed = True
                checker.prepared.add(id(node))
                for local in import_names(node.value[0]):
                    typ = self.declarations.resolve(module.source,local)[0] if self.extended else EXTERNAL
                    if self.extended:
                        value_type,declared_type=self.declarations.resolve(module.source,local)
                        if value_type==ANY and declared_type!=ANY:
                            if not hasattr(checker,'type_only_names'):checker.type_only_names=set()
                            checker.type_only_names.add(local)
                    checker.bind(node, local, typ, True, 'external')
                    info=self.declarations.query(action='resolve',file=str(module.source)+'.declarations.mts',name=local)
                    checker.scopes[0][local].external_definition=info.get('definition',[])
                    checker.scopes[0][local].deprecated=info.get('deprecated',False)
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
                    if symbol.typ.kind in ('constructor','type','enum'):
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
                if target[exported].typ.kind in ('constructor', 'type', 'enum'):
                    if local in {'int', 'float', 'float64', 'number', 'string', 'bool', 'boolean', 'any', 'object', 'void', 'Promise'}:
                        checker.fail(node, f'reserved type name: {local}')
                    checker.type_names[local] = target[exported].typ.name

    def emit(self, module, format='mjs', out_dir=None, checking=False, runtime_format=None, mapping=False):
        if self.has_external and not checking and runtime_format is None:
            result = self._external_result(format)
            generated = result.get('gsFiles', {}).get(str(module.source))
            if generated is not None:
                return generated
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
                extension = 'mjs' if checking else ('js' if runtime_format == 'ts' else runtime_format) if runtime_format else 'js' if format == 'ts' else format
                target = Path(relative) if checking else Path(relative).with_suffix('')
                specifier = str(target) + '.' + extension
                specifier = specifier.replace(os.sep, '/')
                node.value = (binding, json.dumps(specifier if specifier.startswith('.') else './' + specifier))
            if self.extended:
                from parser.extended_emitter import ExtendedEmitter
                return ExtendedEmitter(format=format, checker=module.checker, checking=checking, mapping=mapping).compile(module.program)
            return Emitter(format=format, checker=module.checker, checking=checking, mapping=mapping).compile(module.program)
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


def build_project(entry, out_dir, root=None, format='mjs', check_only=False, cache=True, cache_dir=None, typescript=None, strict_null=False):
    if format not in FORMATS:
        raise CompileError(f'unsupported output format: {format}')
    project = Project(entry, root, format, cache, cache_dir, typescript, strict_null).check()
    if check_only:
        return None
    outputs = plan_outputs(project, out_dir, format)
    for output, contents in outputs.items():
        write_output(output, contents)
    return Path(out_dir).resolve() / project.entry.relative_to(project.root).with_suffix('.' + format)


def plan_outputs(project, out_dir, format='mjs'):
    """Plan every file and validate collisions before committing any build output."""
    out_dir = Path(out_dir).resolve()
    outputs = {}
    for module in project.modules.values():
        output = out_dir / module.source.relative_to(project.root).with_suffix('.' + format)
        if output.resolve() in project.modules:
            raise CompileError('build output must not overwrite a source file')
        if output in outputs:
            raise CompileError(f'output path collision: {output}')
        outputs[output] = project.emit(module, format)
    if project.has_external:
        external = project._external_result(format)
        protected = {Path(item['file']).resolve() for item in external.get('dependencies', []) if item.get('readHash')}
        protected.update(Path(item['source']).resolve() for item in external.get('files', []))
        protected.update(project.modules)
        if any(target.resolve() in protected for target in outputs):
            raise CompileError('build output must not overwrite a source or declaration file')
        for item in external.get('files', []):
            source = Path(item['source']).resolve()
            if not source.is_relative_to(project.root):
                raise CompileError(f'external source is outside project root: {source}')
            target = out_dir / source.relative_to(project.root).with_suffix('.' + item['extension'])
            if target.resolve() in protected:
                raise CompileError('build output must not overwrite a source file')
            if target in outputs:
                raise CompileError(f'output path collision: {target}')
            outputs[target] = item['code']
            if item.get('declaration'):
                declaration = item['declaration']
                declaration_target = target.with_suffix('.' + declaration['extension'])
                if declaration_target.resolve() in protected:
                    raise CompileError('build output must not overwrite a source or declaration file')
                if declaration_target in outputs:
                    raise CompileError(f'output path collision: {declaration_target}')
                outputs[declaration_target] = declaration['code']
    if format in ('js', 'ts'):
        marker = module_marker(out_dir)
        if marker:
            outputs[marker] = '{"type":"module"}\n'
    return outputs
