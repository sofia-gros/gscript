"""Lexical scopes and static checks for the supported gscript language subset.

`any` is an explicit boundary to JavaScript APIs. It does not disable name lookup.
"""
from contextlib import contextmanager
from dataclasses import dataclass, field
import re

from .syntax import CompileError, decode_string


@dataclass(frozen=True)
class Type:
    kind: str
    name: str = ''
    args: tuple = ()
    fields: tuple = ()

    def __str__(self):
        if self.kind=='foreign':return 'external type'
        if self.kind=='union':return ' | '.join(map(str,self.args))
        if self.kind=='literal':return self.name
        if self.kind == 'array':
            return '[]' + str(self.args[0])
        if self.kind == 'promise':
            return f'Promise<{self.args[0]}>'
        if self.kind == 'function':
            return 'func(' + ', '.join(map(str, self.args[:-1])) + ') ' + str(self.args[-1])
        return self.name.rsplit('::', 1)[-1] or self.kind


ANY = Type('any')
EXTERNAL = Type('external')

def is_external(typ):
    return typ is not None and typ.kind in ('external', 'external_type')

def is_dynamic(typ):
    return typ == ANY or is_external(typ)
NUMBER = Type('number')
STRING = Type('string')
BOOL = Type('bool')
VOID = Type('void')
NULL = Type('null')
OBJECT = Type('object')


def array(element):
    return Type('array', args=(element,))


def function(params, result):
    return Type('function', args=(*params, result))


def promise(result):
    return Type('promise', args=(result,))


class Symbol:
    def __init__(self, typ, constant=False, category='variable', target=None, initialized=True):
        self.js_name = None
        self._initialized = initialized
        self._typ, self.constant, self.category, self.target = typ, constant, category, target

    @property
    def initialized(self):
        return self.target.initialized if self.target is not None else self._initialized

    @initialized.setter
    def initialized(self, value):
        self._initialized = value

    @property
    def typ(self):
        return self.target.typ if self.target is not None else self._typ

    @typ.setter
    def typ(self, value):
        self._typ = value


@dataclass
class Struct:
    fields: dict = field(default_factory=dict)
    methods: dict = field(default_factory=dict)


RESERVED = set('await break case catch class const continue debugger default delete do else enum export extends false finally for function if implements import in instanceof interface let new null package private protected public return static super switch this throw true try typeof var void while with yield eval arguments async func type struct range go defer nil'.split())
GLOBALS = set('console globalThis window document navigator location fetch Request Response Headers URL URLSearchParams FormData Blob File AbortController AbortSignal TextEncoder TextDecoder ReadableStream WritableStream TransformStream Buffer process Deno Bun JSON Math Object Array Number String Boolean BigInt Symbol Date RegExp Map Set WeakMap WeakSet Promise Error TypeError RangeError SyntaxError ReferenceError URIError AggregateError Reflect Proxy Intl NaN Infinity undefined setTimeout clearTimeout setInterval clearInterval queueMicrotask structuredClone atob btoa parseInt parseFloat isNaN isFinite encodeURI decodeURI encodeURIComponent decodeURIComponent performance crypto WebSocket'.split())
GLOBALS.update('self alert confirm prompt localStorage sessionStorage indexedDB history screen customElements Event CustomEvent HTMLElement EventTarget MessageChannel MessagePort Worker SharedWorker MutationObserver IntersectionObserver ResizeObserver FileReader Image Audio Notification requestAnimationFrame cancelAnimationFrame setImmediate clearImmediate WebAssembly Atomics SharedArrayBuffer ArrayBuffer DataView Int8Array Uint8Array Uint8ClampedArray Int16Array Uint16Array Int32Array Uint32Array Float32Array Float64Array BigInt64Array BigUint64Array WeakRef FinalizationRegistry BroadcastChannel CompressionStream DecompressionStream EventSource'.split())


def import_names(binding):
    if binding is None:
        return []
    if binding.startswith('{'):
        return [part.strip().split(' as ')[-1] for part in binding[1:-1].split(',') if part.strip()]
    return [binding.split()[-1]]


def unwrap(node):
    return node.children[0] if node.kind == 'export' else node


class Checker:
    def __init__(self, module_id='', structs=None, exports=None, module_exports=None):
        self.module_id = module_id
        self.structs = structs if structs is not None else {}
        self.type_names = {}
        self.exports = exports if exports is not None else {}
        self.module_exports = module_exports if module_exports is not None else {}
        self.prepared = set()
        self.scopes = [{}]
        self.return_type = None
        self.async_context = True
        self.loop_depth = 0
        self.types = {}
        self.seen_functions = set()
        self.defer_functions = False
        self.deferred_functions = []
        self.used_names = set()
        self.name_counter = 0

    def fail(self, node, message):
        raise CompileError(message, node.line)

    @contextmanager
    def scope(self):
        self.scopes.append({})
        try:
            yield
        finally:
            self.scopes.pop()

    def bind(self, node, name, typ, constant=False, category='variable'):
        if name in RESERVED:
            self.fail(node, f'reserved identifier: {name}')
        if name in self.scopes[-1]:
            self.fail(node, f'duplicate declaration: {name}')
        symbol = self.exports.get(name) if len(self.scopes) == 1 else None
        if symbol is None:
            symbol = Symbol(typ, constant, category)
        else:
            symbol.typ, symbol.constant, symbol.category = typ, constant, category
            symbol.initialized = True
        # JS puts let bindings in a temporal dead zone throughout their block;
        # GS resolves an initializer before binding the new name. Give shadowed
        # lexical bindings a distinct JS name so those semantics remain intact.
        emitted = name
        shadowed = any(name in scope for scope in self.scopes[:-1]) or name in GLOBALS or name == 'printf'
        if category == 'variable' and shadowed:
            while True:
                emitted = f'__gs_local{self.name_counter}'
                self.name_counter += 1
                if emitted not in self.used_names:
                    self.used_names.add(emitted)
                    break
        symbol.js_name = emitted
        if not hasattr(node, 'bindings'):
            node.bindings = {}
        node.bindings[name] = emitted
        if category in ('function', 'struct'):
            node.declaration_name = emitted
        self.scopes[-1][name] = symbol

    def lookup(self, node, name):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        if name in GLOBALS or name == 'printf':
            return Symbol(ANY, True, 'global')
        self.fail(node, f'undefined name: {name}')

    def declared_type(self, node, name):
        if name is None:
            return VOID
        if name.startswith('func('):
            depth, end = 1, 5
            while depth:
                if name[end] == '(':
                    depth += 1
                elif name[end] == ')':
                    depth -= 1
                end += 1
            body, result = name[5:end - 1], name[end:]
            parts, start, depth = [], 0, 0
            for i, char in enumerate(body):
                if char in '(<[':
                    depth += 1
                elif char in ')>]':
                    depth -= 1
                elif char == ',' and depth == 0:
                    parts.append(body[start:i])
                    start = i + 1
            if body:
                parts.append(body[start:])
            params = [self.declared_type(node, part) for part in parts]
            if VOID in params:
                self.fail(node, 'parameters cannot be void')
            return function(params, self.declared_type(node, result))
        if name.startswith('[]'):
            item = self.declared_type(node, name[2:])
            if item == VOID:
                self.fail(node, 'array element cannot be void')
            return array(item)
        if name.startswith('Promise<') and name.endswith('>'):
            return promise(self.declared_type(node, name[8:-1]))
        if name in ('int', 'float', 'float64', 'number'):
            return NUMBER
        if name in ('bool', 'boolean'):
            return BOOL
        primitive = {'string': STRING, 'any': ANY, 'object': OBJECT, 'void': VOID, 'Promise': promise(ANY)}
        if name in primitive:
            return primitive[name]
        if name in self.type_names:
            return Type('struct', self.type_names[name])
        root = name.split('.')[0]
        for scope in reversed(self.scopes):
            if root in scope:
                if is_external(scope[root].typ):
                    return Type('external_type', name)
                break
        self.fail(node, f'unknown type: {name}')

    def compatible(self, expected, actual):
        if is_dynamic(expected) or is_dynamic(actual) or expected == actual:
            return True
        if actual == NULL:
            return expected.kind in ('object', 'record', 'array', 'struct', 'function', 'promise')
        if expected == OBJECT:
            return actual.kind in ('record', 'object', 'array', 'struct')
        if expected.kind == actual.kind == 'record':
            actual_fields = dict(actual.fields)
            return all(key in actual_fields and self.compatible(typ, actual_fields[key]) for key, typ in expected.fields)
        if expected.kind == actual.kind and expected.kind in ('array', 'promise'):
            return self.compatible(expected.args[0], actual.args[0])
        if expected.kind == actual.kind == 'function':
            return len(expected.args) == len(actual.args) and all(self.compatible(e, a) for e, a in zip(expected.args, actual.args))
        return False

    def check(self, node, expected, actual):
        if actual.kind == 'pending':
            self.fail(node, 'cyclic value initialization requires a declared type')
        if not self.compatible(expected, actual):
            self.fail(node, f'type mismatch: expected {expected}, got {actual}')

    def signature(self, node):
        _, params, result, asynchronous, _ = node.value
        ret = self.declared_type(node, result)
        if asynchronous:
            ret = promise(ret)
        return function([self.declared_type(node, t) for _, t in params], ret)

    def declare_structs(self, nodes, module=False):
        for original in nodes:
            n = unwrap(original)
            if n.kind == 'default' and 'default' not in self.exports:
                self.exports['default'] = Symbol(ANY, True)
            if original.kind in ('export', 'default') and not module:
                self.fail(original, 'exports must be at module scope')
            if n.kind == 'struct':
                if not module:
                    self.fail(n, 'struct declarations must be at module scope')
                name, _ = n.value
                if name in {'int', 'float', 'float64', 'number', 'string', 'bool', 'boolean', 'any', 'object', 'void', 'Promise'}:
                    self.fail(n, f'reserved type name: {name}')
                key = f'{self.module_id}::{name}' if self.module_id else name
                if key in self.structs:
                    self.fail(n, f'duplicate struct: {name}')
                self.structs[key] = Struct()
                self.type_names[name] = key
                self.bind(n, name, Type('constructor', key), True, 'struct')

    def declare_signatures(self, nodes, module=False):
        for original in nodes:
            n = unwrap(original)
            if n.kind == 'func':
                name, _, _, _, receiver = n.value
                sig = self.signature(n)
                if receiver:
                    if not module:
                        self.fail(n, 'receiver methods must be at module scope')
                    key = self.type_names.get(receiver[1])
                    target = self.structs.get(key)
                    # Methods may only be attached to a struct defined here.
                    if target is None or key != (f'{self.module_id}::{receiver[1]}' if self.module_id else receiver[1]):
                        self.fail(n, f'unknown receiver type: {receiver[1]}')
                    if name in target.methods or name == 'constructor':
                        self.fail(n, f'duplicate or reserved method: {name}')
                    target.methods[name] = sig
                else:
                    self.bind(n, name, sig, True, 'function')
            elif n.kind == 'import':
                if not module:
                    self.fail(n, 'imports must be at module scope')
                if id(n) not in self.prepared:
                    for name in import_names(n.value[0]):
                        self.bind(n, name, ANY, True, 'import')
        for original in nodes:
            n = unwrap(original)
            if n.kind == 'struct':
                name, fields = n.value
                target = self.structs[self.type_names[name]]
                for field_name, typ, _ in fields:
                    if field_name in target.fields or field_name in target.methods:
                        self.fail(n, f'duplicate struct field: {field_name}')
                    target.fields[field_name] = self.declared_type(n, typ)
                    if target.fields[field_name] == VOID:
                        self.fail(n, 'struct fields cannot be void')

    def predeclare(self, nodes, module=False):
        if module and self.prepared:
            return
        self.declare_structs(nodes, module)
        self.declare_signatures(nodes, module)

    def run(self, program):
        names = getattr(program, 'identifiers', None)
        if names is None:
            names = re.findall(r'[A-Za-z_$][A-Za-z0-9_$]*', repr(program))
        self.used_names.update(names)
        self.statements(program.children, module=True)
        return self.types

    def statements(self, nodes, module=False):
        self.predeclare(nodes, module)
        deferred = []
        for original in nodes:
            n = unwrap(original)
            if n.kind == 'func':
                deferred.append(n)
            elif n.kind == 'struct':
                for _, typ, default in n.value[1]:
                    if default:
                        old_async = self.async_context
                        self.async_context = False
                        try:
                            self.check(default, self.declared_type(n, typ), self.expr(default))
                        finally:
                            self.async_context = old_async
            else:
                self.statement(n)
        # Check bodies after surrounding declarations: closures see their lexical scope.
        for node in deferred:
            if self.defer_functions:
                self.deferred_functions.append((node, list(self.scopes)))
            else:
                self.check_function(node)

    def check_function(self, node):
        if id(node) in self.seen_functions:
            return self.signature(node)
        self.seen_functions.add(id(node))
        _, params, result, asynchronous, receiver = node.value
        old = (self.return_type, self.async_context, self.loop_depth)
        self.return_type = self.declared_type(node, result)
        self.async_context, self.loop_depth = asynchronous, 0
        try:
            with self.scope():
                if receiver:
                    self.bind(node, receiver[0], Type('struct', self.type_names[receiver[1]]), True)
                for name, typ in params:
                    param_type = self.declared_type(node, typ)
                    if param_type == VOID:
                        self.fail(node, 'parameters cannot be void')
                    self.bind(node, name, param_type)
                self.statements(node.children)
                if self.return_type != VOID and not self.terminates(node.children):
                    self.fail(node, 'missing return on some paths')
        finally:
            self.return_type, self.async_context, self.loop_depth = old
        return self.signature(node)

    def exits(self, nodes):
        outcomes = {'normal'}
        for node in nodes:
            if 'normal' not in outcomes:
                break
            outcomes.remove('normal')
            k, c = node.kind, node.children
            if k in ('return', 'throw', 'break', 'continue'):
                exits = {k}
            elif k == 'if':
                exits = self.exits(c[1]) | (self.exits(c[2]) if c[2] is not None else {'normal'})
            elif k == 'try':
                exits = (self.exits(c[0]) - {'throw'}) | self.exits(c[1])
            elif k in ('for', 'range'):
                body = c[3] if k == 'for' else c[1]
                inner = self.exits(body)
                exits = inner & {'return', 'throw'}
                infinite = k == 'for' and (c[1] is None or c[1].kind == 'name' and c[1].value == 'true')
                if not infinite or 'break' in inner:
                    exits.add('normal')
            else:
                exits = {'normal'}
            outcomes |= exits
        return outcomes

    def terminates(self, nodes):
        return 'normal' not in self.exits(nodes)

    def expr(self, n):
        typ = self.expression(n)
        self.types[id(n)] = typ
        return typ

    def property(self, n, base, key):
        if is_external(base):
            return EXTERNAL
        if base.kind == 'namespace':
            exports = self.module_exports[base.name]
            if key not in exports:
                self.fail(n, f'module has no export: {key}')
            if not exports[key].initialized:
                self.fail(n, f'module value used before initialization: {key}')
            return exports[key].typ
        if base in (ANY, OBJECT):
            return ANY
        if base.kind == 'record':
            fields = dict(base.fields)
            if key not in fields:
                self.fail(n, f'unknown property: {key}')
            return fields[key]
        if base.kind == 'struct':
            struct = self.structs[base.name]
            if key in struct.fields:
                return struct.fields[key]
            if key in struct.methods:
                return struct.methods[key]
            self.fail(n, f'unknown field or method {key} on {base.name}')
        if base.kind == 'array':
            element = base.args[0]
            if key == 'length':
                return NUMBER
            if key in ('map', 'filter', 'find', 'forEach', 'some', 'every'):
                return Type('array_method', key, (element,))
            if key in ('push', 'unshift'):
                return Type('array_method', key, (element,))
            if key in ('pop', 'shift'):
                # JS may return undefined, deliberately represented as any.
                return function([], ANY)
            if key == 'join':
                return function([STRING], STRING)
            if key in ('slice', 'concat', 'includes', 'indexOf', 'entries', 'keys', 'values', 'reverse', 'sort'):
                return ANY
            self.fail(n, f'unknown array property: {key}')
        if base == STRING:
            if key == 'length':
                return NUMBER
            if key in ('toUpperCase', 'toLowerCase', 'trim', 'trimStart', 'trimEnd'):
                return function([], STRING)
            if key in ('slice', 'substring', 'split', 'replace', 'includes', 'startsWith', 'endsWith', 'charAt', 'indexOf', 'repeat', 'padStart', 'padEnd', 'match', 'replaceAll'):
                return ANY
            self.fail(n, f'unknown string property: {key}')
        if base.kind == 'promise' and key in ('then', 'catch', 'finally'):
            return ANY
        if base == NUMBER and key in ('toFixed', 'toString', 'toPrecision'):
            return ANY
        self.fail(n, f'{base} has no property {key}')

    def expression(self, n):
        k, v, c = n.kind, n.value, n.children
        if k == 'number':
            return NUMBER
        if k == 'string':
            return STRING
        if k == 'name':
            if v in ('true', 'false'):
                return BOOL
            if v in ('nil', 'null'):
                return NULL
            symbol = self.lookup(n, v)
            if not symbol.initialized:
                self.fail(n, f'module value used before initialization: {v}')
            n.resolved_name = symbol.js_name or v
            n.builtin = v == 'printf' and symbol.category == 'global'
            return symbol.typ
        if k == 'array':
            element = self.declared_type(n, v)
            if element == VOID:
                self.fail(n, 'array element cannot be void')
            for item in c:
                typ = self.expr(item)
                if item.kind == 'spread':
                    if not is_dynamic(typ) and typ.kind != 'array':
                        self.fail(item, 'array spread requires an array')
                    typ = typ.args[0] if typ.kind == 'array' else typ
                self.check(item, element, typ)
            return array(element)
        if k in ('object', 'composite'):
            fields, seen, dynamic = {}, set(), False
            external_spread = False
            target = None
            if k == 'composite':
                try:
                    symbol = self.lookup(n, v)
                except CompileError:
                    self.fail(n, f'unknown struct: {v}')
                if symbol.typ.kind != 'constructor':
                    self.fail(n, f'unknown struct: {v}')
                n.constructor_name = symbol.js_name or v
                struct_key = symbol.typ.name
                target = self.structs[struct_key].fields
            for item in c:
                typ = self.expr(item.children[0])
                if item.kind == 'spread':
                    if is_external(typ):
                        external_spread = True
                    elif typ == ANY or typ == OBJECT:
                        dynamic = True
                    elif typ.kind == 'record':
                        fields.update(dict(typ.fields))
                    elif typ.kind == 'struct':
                        fields.update(self.structs[typ.name].fields)
                    else:
                        self.fail(item, 'object spread requires an object')
                else:
                    key = item.value
                    if key.startswith(('"', "'")):
                        key = decode_string(key)
                    if target is not None and key in seen:
                        self.fail(item, f'duplicate field: {key}')
                    fields[key] = typ
                    seen.add(key)
            if target is not None:
                for key, typ in fields.items():
                    if key not in target:
                        self.fail(n, f'unknown field {key} on {v}')
                    self.check(n, target[key], typ)
                return Type('struct', struct_key)
            return OBJECT if dynamic else EXTERNAL if external_spread else Type('record', fields=tuple(fields.items()))
        if k == 'spread':
            return self.expr(c[0])
        if k == 'member':
            return self.property(n, self.expr(c[0]), v)
        if k == 'index':
            base, index = self.expr(c[0]), self.expr(c[1])
            if base.kind == 'array' or base == STRING:
                self.check(n, NUMBER, index)
                return base.args[0] if base.kind == 'array' else STRING
            if is_external(base):
                return EXTERNAL
            if base in (ANY, OBJECT):
                return ANY
            if base.kind == 'record':
                if c[1].kind == 'string':
                    return self.property(n, base, decode_string(c[1].value))
                self.fail(n, 'dynamic object indexing requires an object or any annotation')
            self.fail(n, f'cannot index {base}')
        if k == 'binary':
            lt, rt = self.expr(c[0]), self.expr(c[1])
            if v in ('&&', '||'):
                self.check(n, BOOL, lt)
                self.check(n, BOOL, rt)
                return BOOL
            if v in ('==', '!='):
                if not self.compatible(lt, rt) and not self.compatible(rt, lt):
                    self.fail(n, f'cannot compare {lt} and {rt}')
                return BOOL
            if v in ('<', '>', '<=', '>='):
                if (not is_dynamic(lt) and lt not in (NUMBER, STRING)) or (not is_dynamic(rt) and rt not in (NUMBER, STRING)):
                    self.fail(n, f'operator {v} requires numbers or strings')
                self.check(n, lt, rt)
                return BOOL
            if v == '+' and lt == rt == STRING:
                return STRING
            if v == '+' and (is_external(lt) or is_external(rt)) and (is_dynamic(lt) or lt in (STRING, NUMBER)) and (is_dynamic(rt) or rt in (STRING, NUMBER)):
                return EXTERNAL
            if (not is_dynamic(lt) and lt != NUMBER) or (not is_dynamic(rt) and rt != NUMBER):
                self.fail(n, f'operator {v} requires matching numeric operands (or strings for +)')
            return EXTERNAL if is_external(lt) or is_external(rt) else ANY if ANY in (lt, rt) else NUMBER
        if k == 'unary':
            typ = self.expr(c[0])
            if v == 'await':
                if not self.async_context:
                    self.fail(n, 'await requires an async function')
                return typ.args[0] if typ.kind == 'promise' else typ
            self.check(n, BOOL if v == '!' else NUMBER, typ)
            return BOOL if v == '!' else NUMBER
        if k == 'lambda':
            if self.defer_functions:
                self.deferred_functions.append((n, list(self.scopes)))
                return self.signature(n)
            return self.check_function(n)
        if k == 'new':
            names = v.split('.')
            constructor_symbol = self.lookup(n, names[0])
            n.constructor_name = '.'.join([constructor_symbol.js_name or names[0], *names[1:]])
            constructor = constructor_symbol.typ
            for name in names[1:]:
                constructor = self.property(n, constructor, name)
            args = [self.expr(arg) for arg in c]
            if constructor.kind == 'constructor':
                if len(args) > 1:
                    self.fail(n, 'struct constructor accepts one field object')
                if args:
                    supplied = args[0]
                    if supplied.kind != 'record':
                        self.fail(n, 'struct constructor requires a statically known field object')
                    fields = self.structs[constructor.name].fields
                    for key, typ in supplied.fields:
                        if key not in fields:
                            self.fail(n, f'unknown field {key} on {constructor.name.rsplit("::", 1)[-1]}')
                        self.check(n, fields[key], typ)
                return Type('struct', constructor.name)
            if not is_dynamic(constructor):
                self.fail(n, f'{v} is not a JavaScript constructor')
            return EXTERNAL if is_external(constructor) else ANY
        if k == 'call':
            callee = self.expr(c[0])
            args = [self.expr(arg) for arg in c[1:]]
            for arg, typ in zip(c[1:], args):
                if arg.kind == 'spread' and not is_dynamic(typ) and typ != STRING and typ.kind != 'array':
                    self.fail(arg, 'spread argument must be iterable')
            if is_dynamic(callee):
                return EXTERNAL if is_external(callee) else ANY
            if callee.kind == 'array_method':
                return self.array_call(n, callee, args)
            if callee.kind != 'function':
                self.fail(n, f'{callee} is not callable')
            if any(arg.kind == 'spread' for arg in c[1:]):
                self.fail(n, 'spread arguments require a dynamic JavaScript callable')
            params, result = callee.args[:-1], callee.args[-1]
            if len(args) != len(params):
                self.fail(n, f'expected {len(params)} arguments, got {len(args)}')
            for arg, expected, actual in zip(c[1:], params, args):
                self.check(arg, expected, actual)
            return result
        self.fail(n, f'unsupported expression: {k}')

    def array_call(self, node, method, args):
        element = method.args[0]
        if method.name in ('push', 'unshift'):
            for arg, actual in zip(node.children[1:], args):
                self.check(arg, element, actual.args[0] if arg.kind == 'spread' and actual.kind == 'array' else actual)
            return NUMBER
        if len(args) != 1:
            self.fail(node, 'array callback method requires one callback')
        callback = args[0]
        if is_dynamic(callback):
            dynamic_type = EXTERNAL if is_external(callback) else ANY
            return array(dynamic_type) if method.name == 'map' else dynamic_type
        if callback.kind != 'function':
            self.fail(node, 'array callback must be a function')
        params, result = callback.args[:-1], callback.args[-1]
        if len(params) > 3:
            self.fail(node, 'array callback accepts at most value, index and array')
        for param, supplied in zip(params, (element, NUMBER, array(element))):
            self.check(node, param, supplied)
        if method.name == 'map':
            if result == VOID:
                self.fail(node, 'map callback must return a value')
            return array(result)
        if method.name in ('filter', 'find', 'some', 'every'):
            self.check(node, BOOL, result)
        return {'filter': array(element), 'find': ANY, 'some': BOOL, 'every': BOOL, 'forEach': VOID}[method.name]

    def assignable(self, node):
        if node.kind == 'name':
            symbol = self.lookup(node, node.value)
            if symbol.constant:
                self.fail(node, f'cannot assign to constant {node.value}')
        elif node.kind == 'member':
            base = self.expr(node.children[0])
            if base == STRING or base.kind == 'array' and node.value == 'length':
                self.fail(node, 'property is read-only in gscript')
            if base.kind == 'struct' and node.value in self.structs[base.name].methods:
                self.fail(node, 'cannot assign to a method')
        elif node.kind == 'index':
            if self.expr(node.children[0]) == STRING:
                self.fail(node, 'string indices are read-only')
        else:
            self.fail(node, 'invalid assignment target')
        return self.expr(node)

    def statement(self, n):
        k, v, c = n.kind, n.value, n.children
        if k == 'default':
            self.exports['default'].typ = self.expr(c[0])
            self.exports['default'].initialized = True
        elif k == 'decl':
            kind, name, annotation = v
            expected = self.declared_type(n, annotation) if annotation else None
            actual = self.expr(c[0]) if c[0] else expected
            if actual == VOID or expected == VOID:
                self.fail(n, 'cannot declare a void variable')
            if expected:
                self.check(n, expected, actual)
            self.bind(n, name, expected or actual, kind == 'const')
            self.types[id(n)] = expected or actual
        elif k == 'assign':
            actual = self.expr(c[1])
            if v == ':=':
                if actual == VOID:
                    self.fail(n, 'cannot declare a void variable')
                self.bind(n, c[0].value, actual)
                self.types[id(n)] = actual
            else:
                expected = self.assignable(c[0])
                self.check(n, expected, actual)
                if v in ('+=', '-=') and not is_dynamic(expected) and expected != NUMBER and not (v == '+=' and expected == STRING):
                    self.fail(n, f'operator {v} cannot be used with {expected}')
        elif k == 'update':
            self.check(n, NUMBER, self.assignable(c[0]))
        elif k == 'expr':
            self.expr(c[0])
        elif k == 'return':
            if self.return_type is None:
                self.fail(n, 'return outside function')
            actual = self.expr(c[0]) if c else VOID
            self.check(n, self.return_type, actual)
        elif k == 'throw':
            self.expr(c[0])
        elif k in ('break', 'continue'):
            if not self.loop_depth:
                self.fail(n, f'{k} outside loop')
        elif k == 'if':
            self.check(n, BOOL, self.expr(c[0]))
            with self.scope():
                self.statements(c[1])
            if c[2] is not None:
                with self.scope():
                    self.statements(c[2])
        elif k in ('for', 'range'):
            with self.scope():
                self.loop_depth += 1
                try:
                    if k == 'range':
                        collection = self.expr(c[0])
                        if not is_dynamic(collection) and collection.kind != 'array':
                            self.fail(n, 'range currently supports arrays only')
                        self.bind(n, v[0], NUMBER)
                        if len(v) == 2:
                            self.bind(n, v[1], collection.args[0] if collection.kind == 'array' else collection)
                        body = c[1]
                    else:
                        if c[0]:
                            if c[0].kind not in ('decl', 'assign', 'expr'):
                                self.fail(n, 'invalid loop initializer')
                            self.statement(c[0])
                        if c[1]:
                            self.check(n, BOOL, self.expr(c[1]))
                        if c[2]:
                            if c[2].kind not in ('assign', 'update', 'expr') or c[2].value == ':=':
                                self.fail(n, 'loop step cannot declare a variable')
                            self.statement(c[2])
                        body = c[3]
                    with self.scope():
                        self.statements(body)
                finally:
                    self.loop_depth -= 1
        elif k == 'try':
            with self.scope():
                self.statements(c[0])
            with self.scope():
                self.bind(n, v, ANY)
                self.statements(c[1])
        elif k == 'import':
            pass  # Module-scope validation and bindings are handled by predeclare.
        else:
            self.fail(n, f'unsupported statement: {k}')
