"""gscript parser and ES module compiler. No runtime or third-party dependency."""
from dataclasses import dataclass, field
import json
import re
from typing import NamedTuple


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


class Token(NamedTuple):
    text: str
    line: int
    kind: str
    column: int = 1


TOKEN = re.compile(r'(?P<space>[^\S\n]+)|(?P<comment>//[^\n]*|/\*[\s\S]*?\*/)|(?P<nl>\n)|(?P<string>"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\')|(?P<number>\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)|(?P<op>\.\.\.|\?\.|\?\?|:=|==|!=|<=|>=|&&|\|\||\+\+|--|\+=|-=|[{}()\[\].,:;=+*/%!<>?|&-])')


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


class Tokens(list):
    def __init__(self):super().__init__();self.comments=[];self.identifiers=set()


def tokenize(source):
    tokens, pos, line, line_start = Tokens(), 0, 1, 0
    delimiters = []
    can_end = False
    while pos < len(source):
        match = TOKEN.match(source, pos)
        if not match:
            raise CompileError(f'unexpected character {source[pos]!r}', line, pos - line_start + 1)
        text, kind = match.group(), match.lastgroup
        if kind=='comment':tokens.comments.append((text,line,pos-line_start+1))
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
            if kind=='name':tokens.identifiers.add(text)
            tokens.append(Token(text, line, kind, pos - line_start + 1))
            if text in ('(', '[', '{'):
                delimiters.append(text)
            elif text in (')', ']', '}'):
                if delimiters:
                    delimiters.pop()
            can_end = kind in ('name', 'number', 'string') or text in (')', ']', '}', '++', '--', '?')
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
        while self.accept('.'):
            result += '.' + self.name()
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
            if not self.at(end) and not self.at(';') and not (self.i and self.tokens[self.i-1].line < self.token.line):
                # Block declarations delimit themselves; expressions do not.
                if (nodes[-1].children[0].kind if nodes[-1].kind == 'export' else nodes[-1].kind) not in ('func', 'struct', 'interface', 'enum', 'switch', 'if', 'for', 'range', 'try'):
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
        spans = {}
        self.separators()
        while not self.at(')'):
            token=self.token
            name = self.name()
            spans[name]=(token.line,token.column,token.line,token.column+len(name))
            typ = self.type_name() if not self.at(',') and not self.at(')') else None
            params.append((name, typ))
            if not self.accept(','):
                break
            self.separators()
        self.take(')')
        for index in range(len(params) - 2, -1, -1):
            if params[index][1] is None and params[index + 1][1] is not None:
                params[index] = (params[index][0], params[index + 1][1])
        self.parameter_spans=spans
        return [(name, typ or 'any') for name, typ in params]

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
        token=self.token
        name = self.name()
        typ = None if self.at('=') else self.type_name()
        expr = self.expression() if self.accept('=') else None
        if kind == 'const' and expr is None:
            self.fail('const requires an initializer')
        node=Node('decl', (kind, name, typ), [expr], line)
        node.binding_spans={name:(token.line,token.column,token.line,token.column+len(name))}
        return node

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
            if self.accept('default'):
                return Node('default', children=[self.expression()], line=line)
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
                    node=Node('range', names, [expr, self.block()], line)
                    node.binding_spans={t.text:(t.line,t.column,t.line,t.column+len(t.text)) for t in self.tokens[checkpoint:self.i] if t.text in names and t.kind=='name'}
                    # Select the declarations in the loop header, before any body references.
                    for t in reversed(self.tokens[checkpoint:self.i]):
                        if t.text in names:node.binding_spans[t.text]=(t.line,t.column,t.line,t.column+len(t.text))
                    return node
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
            error_token=self.token
            error = self.name()
            if paren:
                self.take(')')
            node=Node('try', error, [body, self.block()], line)
            node.binding_spans={error:(error_token.line,error_token.column,error_token.line,error_token.column+len(error))}
            return node
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
        if word in ('!', '-', '+', 'await', 'typeof'):
            if word == 'typeof': self.extended = True
            self.take()
            left = Node('unary', word, [self.expression(7, composite)], line)
        elif word == 'func':
            left = self.function(anonymous=True)
        elif word == 'async':
            self.take()
            left = self.function(True, True)
        elif word == 'new':
            self.take()
            constructor_token=self.token
            name = self.name()
            while self.accept('.'):
                name += '.' + self.name()
            type_args = []
            if self.accept('<'):
                self.extended = True
                type_args.append(self.type_name())
                while self.accept(','): type_args.append(self.type_name())
                self.take('>')
            self.take('(')
            left = Node('new', name, self.list_values(')'), line)
            left.type_args = type_args
            left.constructor_name_span=(constructor_token.line,constructor_token.column,constructor_token.line,constructor_token.column+len(name.split('.')[0]))
        elif self.accept('('):
            self.separators()
            left = self.expression()
            self.separators()
            self.take(')')
            left.parenthesized = True
            left.optional_chain = False
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
            token=self.token
            left = Node('name', self.take(), line=line)
            left.name_span=(token.line,token.column,token.line,token.column+len(token.text))
        else:
            self.fail('expected expression')
        while True:
            if hasattr(self, 'postfix_binary'):
                updated = self.postfix_binary(left, minimum, composite)
                if updated is not left:
                    left = updated
                    continue
            if self.accept('.'):
                previous=left
                token=self.token
                left = Node('member', self.name(), [left], token.line)
                left.name_span=(token.line,token.column,token.line,token.column+len(token.text))
                left.optional_chain=not getattr(previous,'parenthesized',False) and (previous.kind.startswith('optional_') or getattr(previous,'optional_chain',False))
            elif self.accept('('):
                previous=left
                left = Node('call', children=[left, *self.list_values(')')], line=line)
                left.optional_chain=not getattr(previous,'parenthesized',False) and (previous.kind.startswith('optional_') or getattr(previous,'optional_chain',False))
            elif self.accept('['):
                index = self.expression()
                self.take(']')
                previous=left
                left = Node('index', children=[left, index], line=line)
                left.optional_chain=not getattr(previous,'parenthesized',False) and (previous.kind.startswith('optional_') or getattr(previous,'optional_chain',False))
            elif composite and left.kind in ('name', 'type_apply') and self.accept('{'):
                applied = left if left.kind == 'type_apply' else None
                constructor_node=applied.children[0] if applied else left
                left = Node('composite', applied.children[0].value if applied else left.value, self.properties(), line)
                left.type_args = applied.value if applied else []
                left.constructor_name_span=getattr(constructor_node,'name_span',None)
            elif self.token.text in self.PRECEDENCE and self.PRECEDENCE[self.token.text] >= minimum:
                op = self.take()
                if op in ('??', 'instanceof'): self.extended = True
                right = self.expression(self.PRECEDENCE[op] + 1, composite)
                if op in ('??','&&','||'):
                    for operand in (left,right):
                        if operand.kind=='binary' and not getattr(operand,'parenthesized',False) and ((op=='??' and operand.value in ('&&','||')) or (op in ('&&','||') and operand.value=='??')):
                            self.fail('parentheses are required when mixing ?? with && or ||')
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
                key_token=self.token
                key_line = self.token.line
                key = self.take()
                explicit=self.accept(':')
                value = self.expression() if explicit else Node('name', key, line=key_line)
                if not explicit:value.name_span=(key_token.line,key_token.column,key_token.line,key_token.column+len(key))
                item=Node('property', key, [value], key_line)
                item.key_span=(key_token.line,key_token.column,key_token.line,key_token.column+len(key))
                item.shorthand=not explicit
                values.append(item)
            self.separators()
            if not self.accept(','):
                break
            self.separators()
        self.take('}')
        return values


def parse_code(source, positions=False):
    try:
        from .extended_parser import ExtendedParser
        parser = ExtendedParser(source)
        # Capture source spans once for diagnostics, maps and editor operations.
        if positions:
            for method_name in ('statement','expression','function','declaration'):
                original=getattr(parser,method_name)
                def located(*args,_original=original,**kwargs):
                    start=parser.i
                    node=_original(*args,**kwargs)
                    if isinstance(node,Node):
                        first,last=parser.tokens[start],parser.tokens[max(start,parser.i-1)]
                        node.span=(first.line,first.column,last.line,last.column+len(last.text))
                    return node
                setattr(parser,method_name,located)
        program = Node('program', children=parser.program())
        if positions or parser.tokens.comments:
            statements=[]
            def collect(value):
                if isinstance(value,Node):
                    collect(value.value)
                    for child in value.children:collect(child)
                    if positions and not hasattr(value,'span'):
                        spans=[getattr(value,'name_span',None),getattr(value,'key_span',None)]
                        spans.extend(getattr(child,'span',None) for child in value.children if isinstance(child,Node))
                        spans=[s for s in spans if s]
                        if spans:value.span=(*min(s[:2] for s in spans),*max(s[2:] for s in spans))
                    if value.kind in ('func','struct','interface','alias','enum','decl','assign','expr','return','if','for','range','switch','throw','try','break','continue','default','import','export'):
                        if not hasattr(value,'span'):value.span=(value.line,1,value.line,1)
                        statements.append(value)
                elif isinstance(value,(list,tuple)):
                    for child in value:collect(child)
            collect(program)
            statements.sort(key=lambda n:n.span[:2])
            program.trailing_comments=[]
            from bisect import bisect_left
            statement_lines=[n.span[0] for n in statements]
            for comment,line,column in parser.tokens.comments:
                index=bisect_left(statement_lines,line)
                if index<len(statements):
                    node=statements[index]
                    if not hasattr(node,'leading_comments'):node.leading_comments=[]
                    node.leading_comments.append(comment)
                else:program.trailing_comments.append(comment)
            if positions:
                from .checker import import_names
                for node in statements:
                    if node.kind=='import':
                        candidates=[t for t in parser.tokens if t.kind=='name' and node.span[:2]<=(t.line,t.column)<=node.span[2:]]
                        node.binding_spans={}
                        for name in import_names(node.value[0]):
                            matching=[t for t in candidates if t.text==name]
                            if matching:
                                token=matching[-1];node.binding_spans[name]=(token.line,token.column,token.line,token.column+len(name))
            program.tokens=tuple(parser.tokens)
            program.source_text=source
        program.position_info=positions
        program.extended = parser.extended
        program.identifiers = frozenset(parser.tokens.identifiers)
        return program
    except RecursionError as error:
        raise CompileError('source nesting exceeds compiler capacity') from error
