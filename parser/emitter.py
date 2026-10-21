"""ES2022 module generation from a checked syntax tree."""
import json
import re

from .checker import unwrap, Type, Checker, ANY, EXTERNAL, is_external
from .syntax import decode_string


def indent(code):
    return '\n'.join('  ' + line if line else '' for line in code.splitlines())


def zero(typ):
    if typ in ('int', 'float', 'float64', 'number'):
        return '0'
    if typ in ('bool', 'boolean'):
        return 'false'
    if typ == 'string':
        return '""'
    return 'null'


class Emitter:
    def __init__(self, format='mjs', checker=None, checking=False):
        self.checking = checking
        self.helpers = []
        self.format = format
        self.checker = checker
        self.methods = {}
        self.used_names = set()
        self.counter = 0

    def compile(self, program):
        names = getattr(program, 'identifiers', None)
        self.used_names = set(names if names is not None else re.findall(r'[A-Za-z_$][\w$]*', repr(program)))
        for original in program.children:
            node = unwrap(original)
            if node.kind == 'func' and node.value[4]:
                self.methods.setdefault(node.value[4][1], []).append(node)
        # Type and function declarations are hoisted, as in the source language.
        order = {'import': 0, 'struct': 1, 'func': 2}
        nodes = sorted(program.children, key=lambda n: order.get(unwrap(n).kind, 3))
        body = '\n\n'.join(filter(None, (self.statement(node) for node in nodes))) + '\n'
        return '\n'.join(self.helpers) + '\n' + body if self.helpers else body

    def ts_type(self, typ):
        if typ.kind == 'external_type':
            return typ.name
        if typ.kind in ('any', 'pending', 'namespace', 'external'):
            return 'any'
        if typ.kind == 'bool':
            return 'boolean'
        if typ.kind in ('number', 'string', 'void', 'null'):
            return typ.kind
        if typ.kind == 'array':
            return 'globalThis.Array<' + self.ts_type(typ.args[0]) + '>'
        if typ.kind == 'promise':
            return 'globalThis.Promise<' + self.ts_type(typ.args[0]) + '>'
        if typ.kind in ('struct', 'constructor'):
            names = [name for name, key in self.checker.type_names.items() if key == typ.name]
            if not names:
                # A non-exported nominal type may appear in an imported function's
                # result; inline its public field shape instead of inventing a name.
                fields = self.checker.structs[typ.name].fields
                return '{' + '; '.join(json.dumps(k) + ': ' + self.ts_type(t) for k, t in fields.items()) + '}'
            return ('typeof ' if typ.kind == 'constructor' else '') + names[0]
        if typ.kind == 'function':
            params = ', '.join(f'arg{i}: {self.ts_type(t)}' for i, t in enumerate(typ.args[:-1]))
            return '(' + params + ') => ' + self.ts_type(typ.args[-1])
        if typ.kind == 'record':
            return '{' + '; '.join(json.dumps(k) + ': ' + self.ts_type(t) for k, t in typ.fields) + '}'
        if typ.kind == 'object':
            return '{[key: string]: any}'
        return 'any'

    def binding(self, node, name):
        return getattr(node, 'bindings', {}).get(name, name)

    def annotation(self, node, type_name):
        return self.ts_type(self.checker.declared_type(node, type_name))

    def default(self, typ):
        value = zero(typ)
        return value + '!' if value == 'null' and self.format == 'ts' else value

    def fresh(self):
        while True:
            name = f'__gscript{self.counter}'
            self.counter += 1
            if name not in self.used_names:
                self.used_names.add(name)
                return name

    def block(self, nodes, prefix=''):
        body = '\n'.join(filter(None, [prefix, *(self.statement(node) for node in nodes)]))
        return '{\n' + indent(body) + '\n}'

    def function(self, node, anonymous=False, method=False):
        name, params, result, asynchronous, receiver = node.value
        prefix = 'async ' if asynchronous else ''
        names = ', '.join(self.binding(node, name) + (': ' + self.annotation(node, typ) if self.format == 'ts' else '') for name, typ in params)
        returns = ''
        if self.format == 'ts':
            result_type = self.annotation(node, result)
            returns = ': ' + (f'globalThis.Promise<{result_type}>' if asynchronous else result_type)
        body = self.block(node.children, f'const {self.binding(node, receiver[0])} = this;' if receiver else '')
        if anonymous:
            return f'({prefix}({names}){returns} => {body})'
        emitted_name = name if method else getattr(node, 'declaration_name', name)
        return f'{prefix}{"" if method else "function "}{emitted_name}({names}){returns} {body}'

    def expr(self, node):
        code = self.expression(node)
        if self.format == 'ts' and node.kind in ('name', 'member', 'index') and self.checker.types.get(id(node)) == ANY:
            return '(' + code + ' as any)'
        if self.checking and node.kind != 'spread':
            return f'(/*__GS_LINE_{node.line}__*/ {code})'
        return code

    def expression(self, node):
        k, v, c = node.kind, node.value, node.children
        if k == 'string':
            return json.dumps(decode_string(v))
        if k == 'number':
            return re.sub(r'^0+(?=\d)', '', v)
        if k == 'name':
            if self.format == 'ts' and v in ('nil', 'null'):
                return 'null!'
            return 'console.log' if getattr(node, 'builtin', False) else {'nil': 'null'}.get(v, getattr(node, 'resolved_name', v))
        if k == 'array':
            code = '[' + ', '.join(self.expr(child) for child in c) + ']'
            if self.format == 'ts':
                code = '(' + code + ' satisfies globalThis.Array<' + self.annotation(node, v) + '>)'
            return code
        if k in ('object', 'composite'):
            parts = []
            for item in c:
                if item.kind == 'spread':
                    parts.append('...' + self.expr(item.children[0]))
                else:
                    key = json.dumps(decode_string(item.value) if item.value.startswith(('"', "'")) else item.value)
                    # A computed key preserves __proto__ as an ordinary own property.
                    parts.append(f'[{key}]: {self.expr(item.children[0])}')
            obj = '{' + ', '.join(parts) + '}'
            return f'new {getattr(node, "constructor_name", v)}({obj})' if k == 'composite' else '(' + obj + ')'
        if k == 'member':
            return f'({self.expr(c[0])}).{v}'
        if k == 'index':
            return f'({self.expr(c[0])})[{self.expr(c[1])}]'
        if k == 'binary':
            op = {'==': '===', '!=': '!=='}.get(v, v)
            left, right = self.expr(c[0]), self.expr(c[1])
            lt, rt = [self.checker.types.get(id(child)) for child in c]
            if self.checking and (is_external(lt) or is_external(rt)):
                if v == '+' and ANY not in (lt, rt):
                    helper = self.fresh()
                    self.helpers += [f'declare function {helper}(a: number, b: number): number;',
                                     f'declare function {helper}(a: string, b: string): string;']
                    return f'{helper}({left}, {right})'
                if v in ('<', '>', '<=', '>=') and ANY not in (lt, rt):
                    helper = self.fresh()
                    self.helpers += [f'declare function {helper}(a: number, b: number): boolean;',
                                     f'declare function {helper}(a: string, b: string): boolean;']
                    return f'{helper}({left}, {right})'
                if v in ('&&', '||', '-', '*', '/', '%'):
                    required = 'boolean' if v in ('&&', '||') else 'number'
                    if is_external(lt): left = f'({left} satisfies {required})'
                    if is_external(rt): right = f'({right} satisfies {required})'
            return f'({left} {op} {right})'
        if k == 'unary':
            child = self.expr(c[0])
            if self.checking and v != 'await' and is_external(self.checker.types.get(id(c[0]))):
                child = f'({child} satisfies {"boolean" if v == "!" else "number"})'
            return f'({v}{" " if v == "await" else ""}{child})'
        if k == 'call':
            return f'({self.expr(c[0])})({", ".join(self.expr(arg) for arg in c[1:])})'
        if k == 'new':
            v = getattr(node, 'constructor_name', v)
            if self.format == 'ts' and self.checker.types.get(id(node)) == ANY:
                v = '(' + v + ' as any)'
            return f'new {v}({", ".join(self.expr(arg) for arg in c)})'
        if k == 'lambda':
            return self.function(node, anonymous=True)
        if k == 'spread':
            return '...' + self.expr(c[0])
        raise AssertionError(f'unhandled checked expression: {k}')

    def simple(self, node):
        k, v, c = node.kind, node.value, node.children
        if k == 'decl':
            kind, name, typ = v
            value = self.expr(c[0]) if c[0] else self.default(typ)
            annotation = ': ' + self.annotation(node, typ) if self.format == 'ts' and typ else ''
            return f'{"const" if kind == "const" else "let"} {self.binding(node, name)}{annotation} = {value}'
        if k == 'assign':
            if v == ':=':
                return f'let {self.binding(node, c[0].value)} = {self.expr(c[1])}'
            return f'{self.expr(c[0])} {v} {self.expr(c[1])}'
        if k == 'update':
            return self.expr(c[0]) + v
        return self.expr(c[0])

    def statement(self, node):
        code = self.statement_code(node)
        return f'/*__GS_LINE_{node.line}__*/\n' + code if self.checking and code else code

    def statement_code(self, node):
        k, v, c = node.kind, node.value, node.children
        if k == 'default':
            return 'export default ' + self.expr(c[0]) + ';'
        if k == 'export':
            if c[0].kind == 'decl':
                source_name = c[0].value[1]
                emitted = self.binding(c[0], source_name)
                if emitted != source_name:
                    return self.statement(c[0]) + f'\nexport {{ {emitted} as {source_name} }};'
            return 'export ' + self.statement(c[0])
        if k in ('decl', 'assign', 'update', 'expr'):
            return self.simple(node) + ';'
        if k == 'import':
            binding, path = v
            path = json.dumps(decode_string(path))
            code = f'import {path};' if binding is None else f'import {binding} from {path};'
            if self.format == 'ts' and not getattr(node, 'gs_module', False) and not getattr(node, 'external_typed', False):
                code = '// @ts-ignore -- external JavaScript is a GS any boundary.\n' + code
            return code
        if k == 'func':
            return '' if v[4] else self.function(node)
        if k == 'struct':
            name, fields = v
            # Unnamed destructuring avoids collision between a source field or method
            # and compiler-generated constructor parameters or local bindings.
            local_names = [self.fresh() for _ in fields]
            params = ', '.join(f'{json.dumps(name)}: {local_names[i]} = {self.expr(default) if default else self.default(typ)}'
                               for i, (name, typ, default) in enumerate(fields))
            annotation = f': globalThis.Partial<{name}>' if self.format == 'ts' else ''
            lines = [f'constructor({{{params}}}{annotation} = {{}}) {{']
            for i, (field_name, _, _) in enumerate(fields):
                key = json.dumps(field_name)
                # Class field declarations safely define __proto__ and shadow inherited accessors.
                lines.append(f'  this[{key}] = {local_names[i]};')
            lines.append('}')
            # Own class fields ensure assignment cannot invoke __proto__'s setter.
            declarations = [f'[{json.dumps(field_name)}]' + (': ' + self.annotation(node, typ) if self.format == 'ts' else '') + ';' for field_name, typ, _ in fields]
            methods = [self.function(method, method=True) for method in self.methods.get(name, [])]
            return f'class {name} {{\n' + indent('\n'.join([*declarations, '\n'.join(lines), *methods])) + '\n}'
        if k == 'return':
            return 'return' + (' ' + self.expr(c[0]) if c else '') + ';'
        if k == 'throw':
            return 'throw ' + self.expr(c[0]) + ';'
        if k in ('break', 'continue'):
            return k + ';'
        if k == 'if':
            condition = self.expr(c[0])
            if self.checking and is_external(self.checker.types.get(id(c[0]))):
                condition = f'({condition} satisfies boolean)'
            result = f'if ({condition}) {self.block(c[1])}'
            return result + (' else ' + self.block(c[2]) if c[2] is not None else '')
        if k == 'range':
            expr = self.expr(c[0])
            if self.checking and is_external(self.checker.types.get(id(c[0]))):
                expr = f'({expr} satisfies globalThis.ReadonlyArray<unknown>)'
            if len(v) == 2:
                header = f'let [{self.binding(node, v[0])}, {self.binding(node, v[1])}] of ({expr}).entries()'
            else:
                header = f'let {self.binding(node, v[0])} of ({expr}).keys()'
            return f'for ({header}) {self.block(c[1])}'
        if k == 'for':
            init = self.simple(c[0]) if c[0] else ''
            cond = self.expr(c[1]) if c[1] else 'true'
            if self.checking and c[1] and is_external(self.checker.types.get(id(c[1]))):
                cond = f'({cond} satisfies boolean)'
            step = self.simple(c[2]) if c[2] else ''
            return f'for ({init}; {cond}; {step}) {self.block(c[3])}'
        if k == 'try':
            return f'try {self.block(c[0])} catch ({self.binding(node, v)}{": any" if self.format == "ts" else ""}) {self.block(c[1])}'
        raise AssertionError(f'unhandled checked statement: {k}')
