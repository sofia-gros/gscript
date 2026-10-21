"""gscript parser and ES module compiler. No runtime or third-party dependency."""
from dataclasses import dataclass, field
import json
import re


class CompileError(ValueError):
    def __init__(self, message, line=None, column=None):
        self.message, self.line, self.column = message, line, column
        location = f'line {line}' + (f':{column}' if column else '') if line else ''
        super().__init__(f'{location}: {message}' if location else message)



@dataclass
class Node:
    kind: str
    value: object = None
    children: list = field(default_factory=list)
    line: int = 1


@dataclass
class Token:
    text: str
    line: int
    kind: str
    column: int = 1


TOKEN = re.compile(r'(?P<space>[^\S\n]+)|(?P<comment>//[^\n]*|/\*[\s\S]*?\*/)|(?P<nl>\n)|(?P<string>"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\')|(?P<number>\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)|(?P<op>\.\.\.|:=|==|!=|<=|>=|&&|\|\||\+\+|--|\+=|-=|[{}()\[\].,:;=+*/%!<>?-])')


def decode_string(text):
    """Decode the supported JavaScript string escapes, without Python semantics."""
    result, i = [], 1
    simple = {'n': '\n', 'r': '\r', 't': '\t', 'b': '\b', 'f': '\f', 'v': '\v',
              '0': '\0', "'": "'", '"': '"', '\\': '\\', '/': '/'}
    while i < len(text) - 1:
        char = text[i]
        i += 1
        if char != '\\':
            result.append(char)
            continue
        escaped = text[i]
        i += 1
        if escaped in simple:
            if escaped == '0' and i < len(text) - 1 and text[i].isdigit():
                raise ValueError('octal escapes are not supported')
            result.append(simple[escaped])
        elif escaped in ('x', 'u'):
            if escaped == 'u' and i < len(text) - 1 and text[i] == '{':
                end = text.find('}', i + 1)
                digits = text[i + 1:end] if end != -1 else ''
                i = end + 1
                valid = 1 <= len(digits) <= 6
            else:
                size = 2 if escaped == 'x' else 4
                digits = text[i:i + size]
                i += size
                valid = len(digits) == size
            if not valid or not re.fullmatch('[0-9a-fA-F]+', digits) or int(digits, 16) > 0x10ffff:
                raise ValueError('invalid Unicode or hexadecimal escape')
            result.append(chr(int(digits, 16)))
        else:
            raise ValueError(f'unsupported string escape: {escaped}')
    # Combine surrogate pairs so equivalent escaped property names compare equally.
    return ''.join(result).encode('utf-16-le', 'surrogatepass').decode('utf-16-le', 'surrogatepass')


def tokenize(source):
    tokens, pos, line, line_start = [], 0, 1, 0
    delimiters = []
    can_end = False
    while pos < len(source):
        match = TOKEN.match(source, pos)
        if not match:
            raise CompileError(f'unexpected character {source[pos]!r}', line, pos - line_start + 1)
        text, kind = match.group(), match.lastgroup
        if kind == 'string':
            try:
                decode_string(text)
            except ValueError as error:
                raise CompileError(str(error), line, pos - line_start + 1) from error
        if kind == 'nl' or kind == 'comment' and '\n' in text:
            if can_end and (not delimiters or delimiters[-1] == '{'):
                tokens.append(Token(';', line, 'separator', pos - line_start + 1))
                can_end = False
        elif kind not in ('space', 'comment'):
            tokens.append(Token(text, line, kind, pos - line_start + 1))
            if text in ('(', '[', '{'):
                delimiters.append(text)
            elif text in (')', ']', '}'):
                if delimiters:
                    delimiters.pop()
            can_end = kind in ('name', 'number', 'string') or text in (')', ']', '}', '++', '--')
        if '\n' in text:
            line += text.count('\n')
            line_start = pos + text.rfind('\n') + 1
        pos = match.end()
    tokens.append(Token('<eof>', line, 'eof', pos - line_start + 1))
    return tokens


class Parser:
    def __init__(self, source):
        self.tokens = tokenize(source)
        self.i = 0

    @property
    def token(self):
        return self.tokens[self.i]

    def at(self, text):
        return self.token.text == text

    def take(self, text=None):
        token = self.token
        if text is not None and token.text != text:
            self.fail(f'expected {text!r}, got {token.text!r}')
        self.i += 1
        return token.text

    def accept(self, text):
        if self.at(text):
            self.take()
            return True
        return False

    def fail(self, message):
        raise CompileError(message, self.token.line, self.token.column)

    def name(self):
        if self.token.kind != 'name':
            self.fail('expected identifier')
        return self.take()

    def separators(self):
        while self.accept(';'):
            pass

    def type_name(self):
        if self.accept('func'):
            self.take('(')
            args = []
            while not self.at(')'):
                args.append(self.type_name())
                if not self.accept(','):
                    break
            self.take(')')
            result = self.type_name() if self.token.kind == 'name' or self.at('[') else 'void'
            return 'func(' + ','.join(args) + ')' + result
        if self.accept('['):
            self.take(']')
            return '[]' + self.type_name()
        result = self.name()
        if self.accept('<'):
            result += '<' + self.type_name()
            self.take('>')
            result += '>'
        return result

    def program(self, end='<eof>'):
        nodes = []
        self.separators()
        while not self.at(end):
            if self.at('<eof>'):
                self.fail(f'expected {end!r}')
            nodes.append(self.statement())
            if not self.at(end) and not self.at(';'):
                # Block declarations delimit themselves; expressions do not.
                if (nodes[-1].children[0].kind if nodes[-1].kind == 'export' else nodes[-1].kind) not in ('func', 'struct', 'if', 'for', 'range', 'try'):
                    self.fail('expected newline or semicolon')
            self.separators()
        return nodes

    def block(self):
        self.take('{')
        result = self.program('}')
        self.take('}')
        return result

    def params(self):
        self.take('(')
        params = []
        self.separators()
        while not self.at(')'):
            name = self.name()
            typ = self.type_name() if not self.at(',') and not self.at(')') else 'any'
            params.append((name, typ))
            if not self.accept(','):
                break
            self.separators()
        self.take(')')
        for index in range(len(params) - 2, -1, -1):
            if params[index][1] == 'any' and params[index + 1][1] != 'any':
                params[index] = (params[index][0], params[index + 1][1])
        return params

    def function(self, asynchronous=False, anonymous=False):
        line = self.token.line
        self.take('func')
        receiver = None
        if not anonymous and self.accept('('):
            receiver = (self.name(), self.type_name())
            self.take(')')
        name = None if anonymous else self.name()
        params = self.params()
        typ = self.type_name() if not self.at('{') else None
        body = self.block()
        return Node('lambda' if anonymous else 'func', (name, params, typ, asynchronous, receiver), body, line)

    def declaration(self):
        line = self.token.line
        kind = self.take()
        name = self.name()
        typ = None if self.at('=') else self.type_name()
        expr = self.expression() if self.accept('=') else None
        if kind == 'const' and expr is None:
            self.fail('const requires an initializer')
        return Node('decl', (kind, name, typ), [expr], line)

    def simple(self, composite=True):
        line = self.token.line
        if self.token.text in ('var', 'let', 'const'):
            return self.declaration()
        left = self.expression(composite=composite)
        if self.token.text in (':=', '=', '+=', '-='):
            op = self.take()
            if op == ':=' and left.kind != 'name':
                self.fail('short declaration requires an identifier')
            if left.kind not in ('name', 'member', 'index'):
                self.fail('invalid assignment target')
            return Node('assign', op, [left, self.expression()], line)
        if self.token.text in ('++', '--'):
            if left.kind not in ('name', 'member', 'index'):
                self.fail('invalid update target')
            return Node('update', self.take(), [left], line)
        return Node('expr', children=[left], line=line)

    def statement(self):
        line = self.token.line
        word = self.token.text
        if word == 'export':
            self.take()
            declaration = self.statement()
            if declaration.kind not in ('decl', 'func', 'struct'):
                self.fail('export requires a variable, function or struct declaration')
            if declaration.kind == 'func' and declaration.value[4]:
                self.fail('export the struct instead of its receiver methods')
            return Node('export', children=[declaration], line=line)
        if word == 'import':
            self.take()
            if self.token.kind == 'string':
                return Node('import', (None, self.take()), line=line)
            if self.accept('{'):
                names = []
                self.separators()
                while not self.at('}'):
                    name = self.name()
                    if self.accept('as'):
                        name += ' as ' + self.name()
                    names.append(name)
                    if not self.accept(','):
                        break
                    self.separators()
                self.take('}')
                binding = '{ ' + ', '.join(names) + ' }'
            elif self.accept('*'):
                self.take('as')
                binding = '* as ' + self.name()
            else:
                binding = self.name()
            self.take('from')
            if self.token.kind != 'string':
                self.fail('expected module string')
            return Node('import', (binding, self.take()), line=line)
        if word == 'type':
            self.take()
            name = self.name()
            self.take('struct')
            self.take('{')
            fields = []
            self.separators()
            while not self.at('}'):
                field_name, typ = self.name(), self.type_name()
                default = self.expression() if self.accept('=') else None
                fields.append((field_name, typ, default))
                if not self.at('}'):
                    if not self.accept(';'):
                        self.fail('expected field separator')
                    self.separators()
            self.take('}')
            return Node('struct', (name, fields), line=line)
        if word == 'func':
            return self.function()
        if word == 'async':
            self.take()
            return self.function(True)
        if word == 'return':
            self.take()
            values = [] if self.token.text in (';', '}', '<eof>') else [self.expression()]
            return Node('return', children=values, line=line)
        if word == 'if':
            self.take()
            condition = self.expression(composite=False)
            body = self.block()
            checkpoint = self.i
            self.separators()
            otherwise = None
            if self.accept('else'):
                otherwise = [self.statement()] if self.at('if') else self.block()
            else:
                self.i = checkpoint
            return Node('if', children=[condition, body, otherwise], line=line)
        if word == 'for':
            self.take()
            if self.at('{'):
                return Node('for', children=[None, None, None, self.block()], line=line)
            parenthesized = self.accept('(')
            # range has one value binding or index,value bindings.
            checkpoint = self.i
            if self.token.kind == 'name':
                names = [self.take()]
                if self.accept(','):
                    names.append(self.name())
                if self.accept(':=') and self.accept('range'):
                    expr = self.expression(composite=False)
                    if parenthesized:
                        self.take(')')
                    return Node('range', names, [expr, self.block()], line)
            self.i = checkpoint
            init = self.simple(composite=False)
            if self.accept(';'):
                condition = self.expression()
                self.take(';')
                step = self.simple()
            else:
                if init.kind != 'expr':
                    self.fail('expected three-clause for or range')
                condition, init, step = init.children[0], None, None
            if parenthesized:
                self.take(')')
            return Node('for', children=[init, condition, step, self.block()], line=line)
        if word == 'try':
            self.take()
            body = self.block()
            self.separators()
            self.take('catch')
            paren = self.accept('(')
            error = self.name()
            if paren:
                self.take(')')
            return Node('try', error, [body, self.block()], line)
        if word == 'throw':
            self.take()
            return Node('throw', children=[self.expression()], line=line)
        if word in ('break', 'continue'):
            return Node(self.take(), line=line)
        if word in ('go', 'defer', 'package', 'class'):
            self.fail(f'{word!r} is not supported; use gscript ES module syntax')
        return self.simple()

    PRECEDENCE = {'||': 1, '&&': 2, '==': 3, '!=': 3, '<': 4, '>': 4, '<=': 4, '>=': 4, '+': 5, '-': 5, '*': 6, '/': 6, '%': 6}

    def expression(self, minimum=0, composite=True):
        line = self.token.line
        word = self.token.text
        if word in ('!', '-', '+', 'await'):
            self.take()
            left = Node('unary', word, [self.expression(7, composite)], line)
        elif word == 'func':
            left = self.function(anonymous=True)
        elif word == 'async':
            self.take()
            left = self.function(True, True)
        elif word == 'new':
            self.take()
            name = self.name()
            self.take('(')
            left = Node('new', name, self.list_values(')'), line)
        elif self.accept('('):
            self.separators()
            left = self.expression()
            self.separators()
            self.take(')')
        elif self.accept('['):
            self.take(']')
            typ = self.type_name()
            self.take('{')
            left = Node('array', typ, self.list_values('}'), line)
        elif self.accept('{'):
            left = Node('object', children=self.properties(), line=line)
        elif self.token.kind in ('string', 'number'):
            kind = self.token.kind
            left = Node(kind, self.take(), line=line)
        elif self.token.kind == 'name':
            left = Node('name', self.take(), line=line)
        else:
            self.fail('expected expression')
        while True:
            if self.accept('.'):
                left = Node('member', self.name(), [left], line)
            elif self.accept('('):
                left = Node('call', children=[left, *self.list_values(')')], line=line)
            elif self.accept('['):
                index = self.expression()
                self.take(']')
                left = Node('index', children=[left, index], line=line)
            elif composite and left.kind == 'name' and self.accept('{'):
                left = Node('composite', left.value, self.properties(), line)
            elif self.token.text in self.PRECEDENCE and self.PRECEDENCE[self.token.text] >= minimum:
                op = self.take()
                right = self.expression(self.PRECEDENCE[op] + 1, composite)
                left = Node('binary', op, [left, right], line)
            else:
                break
        return left

    def list_values(self, end):
        values = []
        self.separators()
        while not self.at(end):
            if self.accept('...'):
                values.append(Node('spread', children=[self.expression()]))
            else:
                values.append(self.expression())
            self.separators()
            if not self.accept(','):
                break
            self.separators()
        self.take(end)
        return values

    def properties(self):
        values = []
        self.separators()
        while not self.at('}'):
            if self.accept('...'):
                values.append(Node('spread', children=[self.expression()]))
            else:
                if self.token.kind not in ('name', 'string'):
                    self.fail('expected property name')
                key_line = self.token.line
                key = self.take()
                value = self.expression() if self.accept(':') else Node('name', key, line=key_line)
                values.append(Node('property', key, [value], key_line))
            self.separators()
            if not self.accept(','):
                break
            self.separators()
        self.take('}')
        return values


def parse_code(source):
    parser = Parser(source)
    return Node('program', children=parser.program())

