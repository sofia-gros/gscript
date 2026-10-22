"""GS v0.4 syntax additions. The original AST shape remains valid."""
from .syntax import Parser, Node

MODIFIERS = {'override', 'static', 'public', 'private', 'protected', 'readonly'}


class ExtendedParser(Parser):
    def __init__(self, source):
        super().__init__(source)
        self.extended = False

    def type_params(self):
        params = []
        if self.accept('<'):
            self.extended = True
            self.separators()
            while True:
                name = self.name()
                constraint = self.type_name() if self.accept('extends') else None
                params.append((name, constraint))
                if not self.accept(','):
                    break
                self.separators()
            self.separators()
            self.take('>')
        return params

    def type_name(self, union=True):
        if self.accept('func'):
            self.take('(')
            args = []
            while not self.at(')'):
                args.append(self.type_name())
                if not self.accept(','): break
            self.take(')')
            result = self.type_name(False) if self.token.kind in ('name', 'string', 'number') or self.at('[') else 'void'
            result = 'func(' + ','.join(args) + ')' + result
        elif self.accept('['):
            self.take(']')
            result = '[]' + self.type_name(False)
        elif self.accept('{'):
            self.extended = True
            parts = []
            self.separators()
            while not self.at('}'):
                name = self.name()
                optional = self.accept('?')
                self.take(':')
                parts.append(name + ('?' if optional else '') + ': ' + self.type_name())
                if not self.accept(',') and not self.accept(';') and not self.at('}'):
                    self.fail('expected object type separator')
                self.separators()
            self.take('}')
            result = '{' + '; '.join(parts) + '}'
        elif self.accept('('):
            self.extended = True
            result = '(' + self.type_name() + ')'
            self.take(')')
        elif self.token.kind in ('string', 'number') or self.at('-'):
            self.extended = True
            sign = '-' if self.accept('-') else ''
            if self.token.kind not in ('string', 'number'): self.fail('expected literal type')
            result = sign + self.take()
        else:
            result = self.name()
            if result in ('nil', 'undefined', 'true', 'false', 'unknown', 'never'): self.extended = True
            while self.accept('.'):
                result += '.' + self.name()
            if self.accept('<'):
                args = [self.type_name()]
                while self.accept(','): args.append(self.type_name())
                self.take('>')
                if result != 'Promise' or len(args) != 1: self.extended = True
                result += '<' + ','.join(args) + '>'
        if self.accept('?'):
            self.extended = True
            result = '(' + result + '|nil)'
        if union and self.accept('|'):
            self.extended = True
            result += '|' + self.type_name()
        return result

    def function(self, asynchronous=False, anonymous=False):
        line = self.token.line
        self.take('func')
        receiver = None
        binding_spans={}
        if not anonymous and self.accept('('):
            token=self.token
            receiver = (self.name(), self.type_name())
            binding_spans[receiver[0]]=(token.line,token.column,token.line,token.column+len(receiver[0]))
            self.take(')')
        token=self.token
        name = None if anonymous else self.name()
        declaration_span=(token.line,token.column,token.line,token.column+len(name)) if name else None
        if name == 'constructor': self.extended = True
        generic = self.type_params()
        params = self.params()
        binding_spans.update(self.parameter_spans)
        typ = self.type_name() if not self.at('{') else None
        node = Node('lambda' if anonymous else 'func', (name, params, typ, asynchronous, receiver), self.block(), line)
        node.type_params = generic
        node.binding_spans=binding_spans
        node.declaration_span=declaration_span
        return node

    def statement(self):
        line = self.token.line
        if self.token.text in MODIFIERS:
            self.extended = True
            mods = []
            while self.token.text in MODIFIERS: mods.append(self.take())
            self.validate_modifiers(mods)
            node = self.statement()
            if node.kind != 'func' or not node.value[4]: self.fail('method modifiers require a receiver method')
            if 'readonly' in mods:self.fail('readonly applies to fields')
            node.modifiers = mods
            return node
        if self.at('type'):
            self.take()
            definition_token=self.token
            name = self.name()
            field_spans={}
            generic = self.type_params()
            if self.accept('='):
                self.extended = True
                node = Node('alias', (name, self.type_name()), line=line)
            elif self.accept('enum'):
                self.extended = True
                self.take('{')
                members = []
                self.separators()
                while not self.at('}'):
                    token=self.token
                    member = self.name()
                    field_spans[member]=(token.line,token.column,token.line,token.column+len(member))
                    value = self.expression() if self.accept('=') else None
                    members.append((member, value))
                    if not self.at('}') and not self.accept(',') and not self.accept(';'): self.fail('expected enum member separator')
                    self.separators()
                self.take('}')
                node = Node('enum', (name, members), line=line)
            elif self.accept('interface'):
                self.extended = True
                bases = []
                if self.accept('extends'):
                    bases.append(self.type_name())
                    while self.accept(','): bases.append(self.type_name())
                self.take('{')
                members = []
                self.separators()
                while not self.at('}'):
                    token=self.token
                    member = self.name()
                    field_spans[member]=(token.line,token.column,token.line,token.column+len(member))
                    if self.at('('):
                        params = self.params()
                        typ = self.type_name() if not self.at(';') and not self.at('}') else 'void'
                        members.append(Node('signature', (member, params, typ), line=self.token.line))
                    else:
                        members.append(Node('field', (member, self.type_name()), line=self.token.line))
                    if not self.at('}') and not self.accept(';'): self.fail('expected interface member separator')
                    self.separators()
                self.take('}')
                node = Node('interface', (name, bases), members, line)
            else:
                self.take('struct')
                base, interfaces = None, []
                if self.accept('extends'):
                    self.extended = True
                    base = self.type_name()
                if self.accept('implements'):
                    self.extended = True
                    interfaces.append(self.type_name())
                    while self.accept(','): interfaces.append(self.type_name())
                self.take('{')
                fields, field_mods = [], {}
                self.separators()
                while not self.at('}'):
                    mods = []
                    while self.token.text in MODIFIERS and self.tokens[self.i+1].kind == 'name':
                        self.extended = True
                        mods.append(self.take())
                    self.validate_modifiers(mods)
                    token=self.token
                    field = self.name()
                    field_spans[field]=(token.line,token.column,token.line,token.column+len(field))
                    typ = self.type_name()
                    default = self.expression() if self.accept('=') else None
                    if field in field_mods: self.fail('duplicate field: ' + field)
                    fields.append((field, typ, default))
                    field_mods[field] = mods
                    if not self.at('}') and not self.accept(';') and self.tokens[self.i-1].line==self.token.line: self.fail('expected field separator')
                    self.separators()
                self.take('}')
                node = Node('struct', (name, fields), line=line)
                node.base, node.implements, node.field_mods = base, interfaces, field_mods
            node.type_params = generic
            node.field_spans=field_spans
            node.binding_spans={name:(definition_token.line,definition_token.column,definition_token.line,definition_token.column+len(name))}
            node.declaration_span=node.binding_spans[name]
            return node
        if self.accept('switch'):
            self.extended = True
            expr = self.expression(composite=False)
            self.take('{')
            cases = []
            self.separators()
            while not self.at('}'):
                line = self.token.line
                values = []
                if self.accept('case'):
                    values.append(self.expression())
                    while self.accept(','): values.append(self.expression())
                else: self.take('default')
                self.take(':')
                body = []
                self.separators()
                while self.token.text not in ('case', 'default', '}'):
                    body.append(self.statement())
                    self.separators()
                cases.append(Node('case', values, body, line))
            self.take('}')
            return Node('switch', children=[expr, *cases], line=expr.line)
        # Original export branch only recognizes the old declaration kinds.
        if self.accept('export'):
            if self.accept('default'):
                return Node('default', children=[self.expression()], line=line)
            node = self.statement()
            if node.kind not in ('decl', 'func', 'struct', 'interface', 'alias', 'enum'):
                self.fail('export requires a declaration')
            if node.kind == 'func' and node.value[4]: self.fail('export the struct instead of its methods')
            return Node('export', children=[node], line=line)
        return super().statement()

    def validate_modifiers(self, mods):
        if len(mods) != len(set(mods)) or len(set(mods) & {'public', 'private', 'protected'}) > 1:
            self.fail('duplicate or conflicting modifiers')

    PRECEDENCE = {**Parser.PRECEDENCE, '??': 1, 'instanceof': 4}

    def postfix_binary(self, left, minimum, composite):
        # This hook is shared with the base parser's ordinary expressions.
        while True:
            line = left.line
            if self.accept('?.'):
                self.extended = True
                if self.accept('('): left = Node('optional_call', children=[left, *self.list_values(')')], line=line)
                elif self.accept('['):
                    index = self.expression(); self.take(']')
                    left = Node('optional_index', children=[left, index], line=line)
                else:
                    token=self.token
                    left = Node('optional_member', self.name(), [left], token.line)
                    left.name_span=(token.line,token.column,token.line,token.column+len(token.text))
            elif self.at('<'):
                checkpoint, was_extended = self.i, self.extended
                try:
                    self.take('<')
                    args = [self.type_name()]
                    while self.accept(','): args.append(self.type_name())
                    self.take('>')
                    if not (self.at('(') or composite and self.at('{')): raise ValueError()
                    self.extended = True
                    left = Node('type_apply', args, [left], line)
                except (ValueError, IndexError):
                    self.i, self.extended = checkpoint, was_extended
                    break
            else: break
        return left
