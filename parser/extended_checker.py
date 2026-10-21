"""Native GS type rules for inheritance, structural types, unions and generics."""
from contextlib import contextmanager, ExitStack
import json
import math
import re
from .checker import (Checker, Type, Struct, Symbol, ANY, NUMBER, STRING, BOOL, VOID, NULL,
                      OBJECT, EXTERNAL, function, array, promise, unwrap, import_names, is_external)
from .syntax import decode_string, CompileError, Node

UNDEFINED = Type('undefined')
NEVER = Type('never')
UNKNOWN = Type('unknown')


def split_type(text, separator=','):
    parts, start, stack, quote = [], 0, [], None
    for i, char in enumerate(text):
        if quote:
            if char == quote and (i == 0 or text[i-1] != '\\'): quote = None
        elif char in '\"\'': quote = char
        elif char in '(<[{': stack.append(char)
        elif char in ')>]}':
            if stack: stack.pop()
        elif char == separator and not stack:
            parts.append(text[start:i].strip()); start = i+1
    parts.append(text[start:].strip())
    return parts


def union(*types):
    args = []
    for typ in types:
        for item in typ.args if typ.kind == 'union' else (typ,):
            if item != NEVER and item not in args: args.append(item)
    if not args: return NEVER
    if ANY in args: return ANY
    return args[0] if len(args) == 1 else Type('union', args=tuple(args))


def widen(typ):
    if typ.kind == 'literal': return typ.args[0]
    return typ


def substitute(typ, mapping):
    if typ.kind == 'param': return mapping.get(typ.name, typ)
    return Type(typ.kind, typ.name, tuple(substitute(t, mapping) for t in typ.args),
                tuple((n, substitute(t, mapping)) for n, t in typ.fields))


class ExtendedChecker(Checker):
    def __init__(self, *args, strict_null=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.strict_null = strict_null
        self.type_defs = {}
        self.generic_context = {}
        self.resolving = set()
        self.current_class = None
        self.in_constructor = False
        self.switch_depth = 0
        self.static_context = False
        self.compatibility_stack = set()
        self.declarations = None
        self.foreign_names = {}
        self.structural_depth = 0
        self.alias_depth = {}

    def bind(self,node,name,typ,constant=False,category='variable'):
        super().bind(node,name,typ,constant,category)
        self.scopes[-1][name].declared_type=typ

    def lookup(self,node,name):
        symbol=super().lookup(node,name)
        if symbol.typ.kind=='type' or name in getattr(self,'type_only_names',set()):self.fail(node,'type cannot be used as a value: '+name)
        return symbol

    def declared_type(self, node, name):
        if name is None: return VOID
        name = name.strip()
        if name.startswith('(') and name.endswith(')') and len(split_type(name[1:-1], '|')) >= 1:
            # Remove only an enclosing pair, not a function's parameter list.
            depth, enclosing = 0, True
            for i,ch in enumerate(name):
                if ch == '(': depth += 1
                elif ch == ')': depth -= 1
                if depth == 0 and i < len(name)-1: enclosing = False; break
            if enclosing: return self.declared_type(node, name[1:-1])
        parts = split_type(name, '|')
        if len(parts) > 1: return union(*(self.declared_type(node, p) for p in parts))
        if name in ('nil', 'null'): return NULL
        if name == 'undefined': return UNDEFINED
        if name == 'never': return NEVER
        if name == 'unknown': return UNKNOWN
        if name in ('true', 'false'): return Type('literal', name, (BOOL,))
        if name.startswith(('"', "'")): return Type('literal', json.dumps(decode_string(name),ensure_ascii=False), (STRING,))
        if re.fullmatch(r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?', name): return Type('literal', str(int(float(name))) if math.isfinite(float(name)) and float(name).is_integer() else str(float(name)), (NUMBER,))
        if name.startswith('func('):
            depth,end,quote=1,5,None
            while end<len(name) and depth:
                char=name[end]
                if quote:
                    if char==quote and name[end-1]!='\\':quote=None
                elif char in ('"',"'"):quote=char
                elif char=='(':depth+=1
                elif char==')':depth-=1
                end+=1
            if depth:self.fail(node,'invalid function type')
            self.structural_depth+=1
            try:
                args=split_type(name[5:end-1]) if name[5:end-1] else []
                params=[self.declared_type(node,p) for p in args]
                if VOID in params:self.fail(node,'parameters cannot be void')
                return function(params,self.declared_type(node,name[end:]))
            finally:self.structural_depth-=1
        if name.startswith('[]'):
            self.structural_depth+=1
            try:
                element=self.declared_type(node,name[2:])
                if element==VOID:self.fail(node,'array element cannot be void')
                return array(element)
            finally:self.structural_depth-=1
        if name.startswith('{'):
            self.structural_depth+=1
            fields = []
            for part in split_type(name[1:-1], ';'):
                if not part: continue
                field, typ = part.split(':', 1)
                fields.append((field.strip(), self.declared_type(node, typ)))
            self.structural_depth-=1
            return Type('record', fields=tuple(fields))
        if name in self.generic_context: return self.generic_context[name]
        root, args = name, []
        if '<' in name and name.endswith('>') and not name.startswith(('[]', 'func(')):
            root, body = name.split('<', 1)
            args = [self.declared_type(node, p) for p in split_type(body[:-1])]
        key = self.type_names.get(root)
        if key and key in self.type_defs:
            definition = self.type_defs[key]
            parameters = getattr(definition, 'type_params', [])
            if len(args) != len(parameters): self.fail(node, f'{root} expects {len(parameters)} type arguments, got {len(args)}')
            mapping = dict(self.generic_context)
            for (parameter, constraint), argument in zip(parameters, args):
                if constraint: self.check(node, self.with_context(node, constraint, mapping), argument)
                mapping[parameter] = argument
            if definition.kind == 'alias':
                if key in self.resolving:
                    if self.structural_depth>self.alias_depth[key]:return Type('recursive',key,tuple(args))
                    self.fail(node,f'cyclic type alias: {root}')
                self.resolving.add(key)
                self.alias_depth[key]=self.structural_depth
                try:
                    owner=self.structs[key].checker
                    return owner.with_context(node,definition.value[1],mapping)
                finally: self.resolving.remove(key)
            if definition.kind == 'enum': return self.structs[key].enum_type
            return Type('interface' if definition.kind == 'interface' else 'struct', key, tuple(args))
        if self.declarations:
            root_name=root.split('.')[0]
            if any(root_name in scope and scope[root_name].category=='external' for scope in self.scopes):
                data=self.declarations.query(action='named_type',file=self.module_id+'.declarations.mts',name=root)
                typ=self.declarations.typ(data['type'])
                if typ==ANY:self.fail(node,'external name is not a type: '+root)
                if args:
                    description=self.declarations.describe(typ) if typ.kind=='foreign' else {}
                    parameters=[self.declarations.typ(p) for p in description.get('parameters',[])]
                    if len(args)!=len(parameters):self.fail(node,'incorrect external type arguments')
                    for p,arg in zip(parameters,args):self.check(node,p.args[0],arg)
                    typ=Type('foreign',typ.name,tuple(args))
                self.foreign_names[typ]=name
                return typ
        return super().declared_type(node, name)

    def with_context(self, node, text, context):
        old = self.generic_context
        self.generic_context = context
        try: return self.declared_type(node, text)
        finally: self.generic_context = old

    @contextmanager
    def parameters(self, node, receiver=None):
        old = self.generic_context
        context = dict(old)
        if receiver and 'static' in getattr(node,'modifiers',[]):
            target=self.structs[self.type_names[receiver.split('<')[0]]]
            for parameter,_ in target.parameters:context.pop(parameter,None)
        if receiver and 'static' not in getattr(node,'modifiers',[]):
            target = self.structs[self.type_names[receiver.split('<')[0]]]
            for name, constraint in target.parameters:
                context[name] = Type('param', name, (self.with_context(node, constraint, context) if constraint else UNKNOWN,))
        for name, constraint in getattr(node, 'type_params', []):
            if name in context: self.fail(node, f'duplicate type parameter: {name}')
            context[name] = Type('param', name, (self.with_context(node, constraint, context) if constraint else UNKNOWN,))
        self.generic_context = context
        try: yield
        finally: self.generic_context = old

    def declare_structs(self, nodes, module=False):
        for original in nodes:
            n = unwrap(original)
            if n.kind not in ('alias', 'interface', 'struct', 'enum'): continue
            if not module: self.fail(n, 'type declarations must be at module scope')
            name = n.value[0]
            if name in ('int','number','string','bool','boolean','any','void','object','Promise','never','unknown','undefined'):
                self.fail(n, f'reserved type name: {name}')
            key = f'{self.module_id}::{name}' if self.module_id else name
            if key in self.structs: self.fail(n, f'duplicate type: {name}')
            self.type_names[name] = key
            self.type_defs[key] = n
            target = self.structs[key] = Struct()
            target.parameters = getattr(n, 'type_params', [])
            target.base = None
            target.statics, target.access, target.readonly, target.method_nodes = {}, {}, set(), {}
            target.constructor = None
            target.kind, target.node, target.checker = n.kind, n, self
            self.bind(n, name, Type('constructor' if n.kind == 'struct' else 'enum' if n.kind == 'enum' else 'type', key), True, 'struct')

    def contains_parameter(self,typ,names):
        return typ.kind=='param' and typ.name in names or any(self.contains_parameter(t,names) for t in typ.args) or any(self.contains_parameter(t,names) for _,t in typ.fields)

    def signature(self, node):
        receiver = node.value[4]
        with self.parameters(node, receiver[1] if receiver else None):
            sig = super().signature(node)
            params = getattr(node, 'type_params', [])
            if params:
                return Type('generic_function', args=(sig, *(self.generic_context[p] for p,_ in params)))
            return sig

    def declare_signatures(self, nodes, module=False):
        # Types are resolved before method bodies, including forward references.
        for original in nodes:
            n = unwrap(original)
            if n.kind == 'import' and id(n) not in self.prepared:
                for name in import_names(n.value[0]): self.bind(n, name, EXTERNAL, True, 'external')
        for original in nodes:
            n = unwrap(original)
            if n.kind not in ('struct', 'interface', 'enum', 'alias'): continue
            target = self.structs[self.type_names[n.value[0]]]
            with self.parameters(n):
                if n.kind == 'alias':
                    # Resolve non-recursive aliases even when unused.
                    self.declared_type(n, n.value[0] + ('<' + ','.join(p for p,_ in n.type_params) + '>' if n.type_params else ''))
                elif n.kind == 'enum':
                    value, flavor, names = 0, None, set()
                    n.enum_values = []
                    for name, expr in n.value[1]:
                        if name in names: self.fail(n, 'duplicate enum member: ' + name)
                        names.add(name)
                        if expr:
                            if expr.kind == 'string': value = decode_string(expr.value)
                            elif expr.kind == 'number' and float(expr.value).is_integer(): value = int(expr.value)
                            elif expr.kind == 'unary' and expr.value == '-' and expr.children[0].kind == 'number' and float(expr.children[0].value).is_integer(): value = -int(expr.children[0].value)
                            else: self.fail(expr, 'enum value must be an integer or string constant')
                        elif flavor == 'string': self.fail(n, 'string enum members need explicit values')
                        current = 'string' if isinstance(value,str) else 'number'
                        if flavor and flavor != current: self.fail(n, 'enum cannot mix strings and numbers')
                        flavor = current
                        typ = Type('literal', json.dumps(value,ensure_ascii=False), (STRING if current == 'string' else NUMBER,))
                        target.statics[name] = typ
                        n.enum_values.append((name,value))
                        if current == 'number': value += 1
                    target.enum_type = union(*target.statics.values())
                elif n.kind == 'interface':
                    for member in n.children:
                        name = member.value[0]
                        if name in target.fields or name in target.methods: self.fail(member, 'duplicate interface member: ' + name)
                        if member.kind == 'signature':
                            target.methods[name] = function([self.declared_type(member,t) for _,t in member.value[1]], self.declared_type(member,member.value[2]))
                        else: target.fields[name] = self.declared_type(member,member.value[1])
                    target.bases = [self.declared_type(n,t) for t in n.value[1]]
                else:
                    target.base = self.declared_type(n,n.base) if getattr(n,'base',None) else None
                    if getattr(n,'base',None):
                        root=n.base.split('<')[0].split('.')[0]
                        self.lookup(n,root)
                    if target.base and target.base.kind not in ('struct', 'foreign'): self.fail(n,'extends requires a class')
                    if target.base and target.base.kind=='foreign' and not self.declarations.describe(target.base)['isClass']:self.fail(n,'extends requires an external class')
                    for name, typ, default in n.value[1]:
                        mods = n.field_mods.get(name, [])
                        if 'override' in mods: self.fail(n, 'override applies to methods')
                        dest = target.statics if 'static' in mods else target.fields
                        if name in dest: self.fail(n, 'duplicate field: ' + name)
                        dest[name] = self.declared_type(n,typ)
                        if 'static' in mods and self.contains_parameter(dest[name],{p for p,_ in target.parameters}):self.fail(n,'static members cannot use instance type parameters')
                        if dest[name] == VOID: self.fail(n,'struct fields cannot be void')
                        target.access[('static' in mods,name)] = next((m for m in mods if m in ('private','protected')), 'public')
                        if 'readonly' in mods: target.readonly.add(('static' in mods,name))
        for original in nodes:
            n = unwrap(original)
            if n.kind != 'func': continue
            name, _, result, asynchronous, receiver = n.value
            sig = self.signature(n)
            if not receiver:
                self.bind(n,name,sig,True,'function'); continue
            root = receiver[1].split('<')[0]
            key = self.type_names.get(root)
            target = self.structs.get(key)
            if not target or target.checker is not self or target.kind != 'struct': self.fail(n,'unknown receiver type: '+receiver[1])
            mods = getattr(n,'modifiers',[])
            static = 'static' in mods
            if name == 'constructor':
                if target.constructor is not None: self.fail(n, 'duplicate constructor')
                if result or asynchronous or mods or n.type_params: self.fail(n, 'constructor cannot have result type, modifiers, async or type parameters')
                target.constructor = sig
                target.constructor_node = n
            else:
                dest = target.statics if static else target.methods
                if name in dest or not static and name in target.fields: self.fail(n,'duplicate member: '+name)
                dest[name] = sig
                target.method_nodes[name] = n
                target.access[(static,name)] = next((m for m in mods if m in ('private','protected')), 'public')
        if module:self.prepare_static_order()
        for original in nodes:
            n = unwrap(original)
            if n.kind == 'struct' and not getattr(self,'defer_validation',False): self.validate_inheritance(n)
            if n.kind == 'interface' and not getattr(self,'defer_validation',False):
                target=self.structs[self.type_names[n.value[0]]]
                if any(t.kind not in ('interface','foreign') for t in target.bases):self.fail(n,'interface extends requires interface types')
                self.members(Type('interface',self.type_names[n.value[0]]))

    def prepare_static_order(self):
        changed=True
        while changed:
            changed=False
            for key,target in self.structs.items():
                if getattr(target,'kind',None)!='struct':continue
                deferred=any('static' in mods for mods in target.node.field_mods.values())
                if target.base and target.base.kind=='struct':deferred=deferred or getattr(self.structs[target.base.name].node,'deferred_class',False)
                if deferred and not getattr(target.node,'deferred_class',False):target.node.deferred_class=True;changed=True
        for name,symbol in self.scopes[0].items():
            if symbol.typ.kind=='constructor' and symbol.category=='struct' and getattr(self.structs[symbol.typ.name].node,'deferred_class',False):symbol.initialized=False

    def mapping(self, typ):
        target = self.structs[typ.name]
        return dict(zip((p for p,_ in target.parameters), typ.args or (Type('param',p,(UNKNOWN,)) for p,_ in target.parameters)))

    def members(self, typ, static=False, visited=None):
        if typ.kind=='foreign':return {p['name']:self.declarations.typ(p['type']) for p in self.declarations.fields(typ) if p['access']=='public'}
        if typ.kind not in ('struct','interface','constructor'): return {}
        visited = set() if visited is None else set(visited)
        if typ.name in visited: raise CompileError('cyclic inheritance: '+typ.name.rsplit('::',1)[-1])
        visited.add(typ.name)
        target = self.structs[typ.name]
        mapping = {} if static else self.mapping(typ)
        result = {}
        bases = getattr(target,'bases',[]) if target.kind == 'interface' else [target.base] if target.base else []
        for base in bases:
            result.update(self.members(substitute(base,mapping),static,visited))
        for name, item in (target.statics if static else {**target.fields,**target.methods}).items(): result[name] = substitute(item,mapping)
        return result

    def struct_fields(self,typ):
        target=self.structs[typ.name]
        mapping=self.mapping(typ)
        result=self.struct_fields(substitute(target.base,mapping)) if target.base and target.base.kind=='struct' else {}
        result.update({name:substitute(t,mapping) for name,t in target.fields.items()})
        return result

    def validate_inheritance(self, n):
        typ = Type('struct', self.type_names[n.value[0]])
        target = self.structs[typ.name]
        self.members(typ)
        parent=target.base
        while parent and parent.kind=='struct':
            inherited=self.structs[parent.name]
            for static,name in inherited.access:
                own=target.statics if static else {**target.fields,**target.methods}
                if name not in own:continue
                if inherited.access[(static,name)]=='private':self.fail(n,'cannot redeclare inherited private member: '+name)
                if (static,name) in inherited.readonly and (static,name) not in target.readonly:self.fail(n,'cannot remove readonly: '+name)
            parent=inherited.base
        for name,typ in target.fields.items():
            if target.base:
                parent=self.members(target.base) if target.base.kind=='struct' else {}
                if name in parent:self.check(n,parent[name],typ)
        for static in (False,True):
            parent = self.members(target.base,static) if target.base else {}
            for name,method in target.method_nodes.items():
                mods = getattr(method,'modifiers',[])
                if ('static' in mods) != static: continue
                sig = target.statics[name] if static else target.methods[name]
                if 'override' in mods and name not in parent and not is_external(target.base) and (not target.base or target.base.kind!='foreign'): self.fail(method, 'override has no parent method: '+name)
                if target.base and target.base.kind=='foreign':
                    entry=self.declarations.property(target.base,name)
                    if 'override' in mods and not entry:self.fail(method,'override has no parent method: '+name)
                    if entry:self.check(method,self.declarations.typ(entry['type']),sig)
                if name in parent: self.check(method,parent[name],sig)
        with self.parameters(n):
            instance = self.declared_type(n,n.value[0]+('<'+','.join(p for p,_ in n.type_params)+'>' if n.type_params else ''))
            for interface in n.implements: self.check(n,self.declared_type(n,interface),instance)

    def compatible(self, expected, actual):
        pair = (expected,actual)
        if pair in self.compatibility_stack: return True
        self.compatibility_stack.add(pair)
        try: return self._compatible(expected,actual)
        finally: self.compatibility_stack.remove(pair)

    def expand(self,typ):
        if typ.kind!='recursive':return typ
        target=self.structs[typ.name]
        context=dict(zip((n for n,_ in target.parameters),typ.args))
        return target.checker.with_context(target.node,target.node.value[1],context)

    def _compatible(self, expected, actual):
        if expected.kind=='recursive' or actual.kind=='recursive':return self.compatible(self.expand(expected),self.expand(actual))
        if expected.kind=='foreign' or actual.kind=='foreign':
            return self.foreign_compatible(expected,actual)
        if actual == NEVER or expected in (ANY,UNKNOWN) or actual == ANY or expected == actual: return True
        if expected.kind == 'param': return actual == expected
        if actual.kind == 'param': return self.compatible(expected,actual.args[0])
        if actual.kind == 'union': return all(self.compatible(expected,t) for t in actual.args)
        if expected.kind == 'union': return any(self.compatible(t,actual) for t in expected.args)
        if expected.kind == 'literal': return False
        if actual.kind == 'literal': return self.compatible(expected,actual.args[0])
        if actual == NULL and self.strict_null: return False
        if expected.kind == 'interface':
            supplied = self.members(actual) if actual.kind in ('struct','interface') else dict(actual.fields) if actual.kind == 'record' else {}
            optional=self.optional_members(expected)
            return all((name not in supplied and name in optional) or name in supplied and self.compatible(typ,supplied[name]) for name,typ in self.members(expected).items())
        if expected.kind == actual.kind == 'struct':
            current = actual
            seen = set()
            while current and current.kind == 'struct' and current.name not in seen:
                if current.name == expected.name:
                    return len(current.args) == len(expected.args) and all(self.compatible(e,a) and self.compatible(a,e) for e,a in zip(expected.args,current.args))
                seen.add(current.name)
                target = self.structs[current.name]
                current = substitute(target.base,self.mapping(current)) if target.base else None
            return False
        if expected.kind==actual.kind=='record':
            supplied=dict(actual.fields)
            for key,t in expected.fields:
                optional=key.endswith('?');name=key[:-1] if optional else key
                if name not in supplied:
                    if optional:continue
                    return False
                if not self.compatible(t,supplied[name]):return False
            return True
        if expected.kind == actual.kind == 'function':
            return len(actual.args) <= len(expected.args) and self.compatible(expected.args[-1],actual.args[-1]) and all(self.compatible(a,e) for e,a in zip(expected.args[:-1],actual.args[:-1]))
        return super().compatible(expected,actual)

    def statements(self, nodes, module=False):
        self.predeclare(nodes,module)
        deferred=[]
        with ExitStack() as guards:
            for original in nodes:
                n=unwrap(original)
                if n.kind=='func': deferred.append(n)
                elif n.kind=='struct':
                    if getattr(n,'deferred_class',False) and n.base:
                        names=n.base.split('<')[0].split('.')
                        base=Node('name',names[0],line=n.line)
                        for part in names[1:]:base=Node('member',part,[base],n.line)
                        self.expr(base)
                    self.scopes[0][n.value[0]].initialized=True
                    with self.parameters(n):
                        for _,typ,default in n.value[1]:
                            if default:self.check(default,self.declared_type(n,typ),self.expr(default))
                elif n.kind not in ('alias','interface','enum'):
                    self.statement(n)
                    if n.kind=='if':
                        if self.terminates(n.children[1]):guards.enter_context(self.narrowing(n.children[0],False))
                        elif n.children[2] is not None and self.terminates(n.children[2]):guards.enter_context(self.narrowing(n.children[0],True))
            for n in deferred:
                if self.defer_functions:self.deferred_functions.append((n,list(self.scopes)))
                else:self.check_function(n)

    def check_function(self, node):
        if id(node) in self.seen_functions: return self.signature(node)
        name, params, result, asynchronous, receiver = node.value
        old = self.current_class,self.in_constructor,self.return_type,self.async_context,self.loop_depth,self.switch_depth,self.static_context
        self.current_class = self.type_names.get(receiver[1].split('<')[0]) if receiver else None
        self.in_constructor = name == 'constructor' and receiver is not None
        self.static_context = 'static' in getattr(node,'modifiers',[])
        self.return_type, self.async_context,self.loop_depth,self.switch_depth = VOID,asynchronous,0,0
        try:
            with self.parameters(node,receiver[1] if receiver else None):
                self.return_type = self.declared_type(node,result)
                with self.scope():
                    if receiver:
                        cls = self.structs[self.current_class]
                        static = 'static' in getattr(node,'modifiers',[])
                        arguments = () if static else tuple(self.generic_context[p] for p,_ in cls.parameters)
                        self.bind(node,receiver[0],Type('constructor' if static else 'struct', self.current_class,arguments),True)
                        if self.in_constructor and cls.base:
                            if not node.children or not self.is_super_call(node.children[0]): self.fail(node, 'derived constructor must start with super()')
                            if self.contains_receiver(node.children[0],receiver[0]): self.fail(node,'receiver cannot be used before super()')
                            if sum(self.count_super(n) for n in node.children) != 1: self.fail(node,'super() must be called exactly once')
                    for param,typ in params:
                        declared=self.declared_type(node,typ)
                        if declared==VOID:self.fail(node,'parameters cannot be void')
                        self.bind(node,param,declared)
                    self.statements(node.children)
                    if self.in_constructor and self.strict_null:self.validate_initialization(node,receiver[0])
                    if self.return_type != VOID and not self.terminates(node.children): self.fail(node,'missing return on some paths')
            self.seen_functions.add(id(node))
        finally:
            self.current_class,self.in_constructor,self.return_type,self.async_context,self.loop_depth,self.switch_depth,self.static_context = old
        return self.signature(node)

    def required_fields(self,typ):
        target=self.structs[typ.name]
        fields=self.struct_fields(typ)
        defaults={name for name,_,value in target.node.value[1] if value is not None}
        return {name for name,t in target.fields.items() if name not in defaults and not self.compatible(fields[name],self.zero_type(fields[name]))}

    def validate_initialization(self,node,receiver):
        target=self.structs[self.current_class]
        arguments=tuple(self.generic_context[p] for p,_ in target.parameters)
        required=self.required_fields(Type('struct',self.current_class,arguments))
        def reads(n,initialized):
            if n.kind in ('lambda','func'):return
            if n.kind=='member' and n.children[0].kind=='name' and n.children[0].value==receiver and n.value in required-initialized:self.fail(n,'field used before initialization: '+n.value)
            for child in n.children:
                if hasattr(child,'kind'):reads(child,initialized)
        def block(nodes,initialized):
            initialized=set(initialized)
            for n in nodes:
                if n.kind=='assign' and n.children[0].kind=='member' and n.children[0].children[0].kind=='name' and n.children[0].children[0].value==receiver:
                    reads(n.children[1],initialized)
                    if n.value!='=':reads(n.children[0],initialized)
                    initialized.add(n.children[0].value)
                elif n.kind=='if':
                    reads(n.children[0],initialized)
                    left=block(n.children[1],initialized)
                    right=block(n.children[2],initialized) if n.children[2] is not None else initialized
                    initialized=left & right
                elif n.kind in ('for','range'):
                    body=n.children[3] if n.kind=='for' else n.children[1]
                    for child in n.children[:-1]:
                        if hasattr(child,'kind'):reads(child,initialized)
                    block(body,initialized)
                elif n.kind=='try':initialized=block(n.children[0],initialized)&block(n.children[1],initialized)
                elif n.kind=='switch':
                    reads(n.children[0],initialized)
                    branches=[block(case.children,initialized) for case in n.children[1:]]
                    if not getattr(n,'exhaustive',False):branches.append(initialized)
                    if branches:initialized=set.intersection(*branches)
                elif n.kind=='throw':return required
                elif n.kind=='return':
                    if required-initialized:self.fail(n,'constructor leaves fields uninitialized: '+', '.join(sorted(required-initialized)))
                else:reads(n,initialized)
            return initialized
        missing=required-block(node.children,set())
        if missing:self.fail(node,'constructor leaves fields uninitialized: '+', '.join(sorted(missing)))

    def is_super_call(self,n):
        return n.kind == 'expr' and n.children[0].kind == 'call' and n.children[0].children[0].kind == 'name' and n.children[0].children[0].value == 'super'

    def walk(self,n):
        yield n
        for c in n.children:
            if hasattr(c,'kind'): yield from self.walk(c)
            elif isinstance(c,list):
                for item in c:
                    if hasattr(item,'kind'): yield from self.walk(item)

    def count_super(self,n):
        return sum(item.kind == 'call' and item.children[0].kind == 'name' and item.children[0].value == 'super' for item in self.walk(n))

    def contains_receiver(self,n,name):
        return any(item.kind == 'name' and item.value in (name,'this') for item in self.walk(n))

    def access_member(self,n,base,key):
        current = base
        static = base.kind == 'constructor'
        while current and current.kind in ('struct','constructor'):
            target = self.structs[current.name]
            if (static,key) in target.access:
                access = target.access[(static,key)]
                if access == 'private' and self.current_class != current.name: self.fail(n,'private member: '+key)
                if access == 'protected':
                    cls = Type('struct',self.current_class) if self.current_class else None
                    if not cls or not self.is_subclass(cls.name,current.name): self.fail(n,'protected member: '+key)
                return target
            current = target.base
        return None

    def is_subclass(self,child,parent):
        seen = set()
        while child and child not in seen:
            if child == parent: return True
            seen.add(child)
            base = self.structs[child].base
            child = base.name if base and base.kind == 'struct' else None
        return False

    def property(self,n,base,key):
        base=self.expand(base)
        if base.kind=='record' and key not in dict(base.fields) and key+'?' in dict(base.fields):return union(dict(base.fields)[key+'?'],UNDEFINED)
        if base.kind == 'union':
            if NULL in base.args or UNDEFINED in base.args: self.fail(n,'nullable value requires a nil check or optional chaining')
            return union(*(self.property(n,t,key) for t in base.args))
        if base.kind == 'literal': base = base.args[0]
        if base.kind == 'param': base = base.args[0]
        if base.kind=='foreign':
            entry=self.declarations.property(base,key)
            if not entry:self.fail(n,'unknown external member: '+key)
            if entry['access']=='private':self.fail(n,'private external member: '+key)
            if entry['access']=='protected':
                current=self.current_class
                allowed=False
                while current:
                    parent=self.structs[current].base
                    if parent and parent.kind=='foreign':
                        allowed=entry.get('owner') is not None and self.foreign_subclass(parent,str(entry['owner']))
                        break
                    current=parent.name if parent and parent.kind=='struct' else None
                if not allowed:self.fail(n,'protected external member: '+key)
            result=self.declarations.typ(entry['type'])
            result=substitute(result,self.foreign_mapping(base))
            return union(result,UNDEFINED) if entry['optional'] else result
        if base.kind in ('struct','interface','constructor','enum'):
            static = base.kind in ('constructor','enum')
            self.access_member(n,base,key)
            members = self.structs[base.name].statics if base.kind == 'enum' else self.members(base,static)
            if key in members: return members[key]
            target = self.structs[base.name]
            if target.base and (is_external(target.base) or target.base.kind=='foreign'): return self.property(n,target.base,key)
            self.fail(n,'unknown '+('static ' if static else '')+'member: '+key)
        return super().property(n,base,key)

    def infer(self,formal,actual,mapping):
        if formal.kind == 'param':
            actual = widen(actual)
            if formal.name in mapping: mapping[formal.name] = union(mapping[formal.name],actual)
            else: mapping[formal.name] = actual
        elif formal.kind == actual.kind:
            for a,b in zip(formal.args,actual.args): self.infer(a,b,mapping)

    def call_signature(self,n,sig,args,type_args=None):
        sig=self.expand(sig)
        if sig.kind == 'generic_function':
            template, parameters = sig.args[0],sig.args[1:]
            mapping = {}
            if type_args is not None:
                if len(type_args) != len(parameters): self.fail(n,'incorrect number of type arguments')
                mapping.update(zip((p.name for p in parameters),type_args))
            else:
                for formal,actual in zip(template.args[:-1],args): self.infer(formal,actual,mapping)
            for p in parameters:
                if p.name not in mapping: self.fail(n,'cannot infer type argument: '+p.name)
                self.check(n,substitute(p.args[0],mapping),mapping[p.name])
            sig = substitute(template,mapping)
        if sig.kind=='foreign_constructor':return self.foreign_call(n,Type('foreign',sig.name),args,construct=True,type_args=type_args)
        if sig.kind=='foreign':return self.foreign_call(n,sig,args,type_args=type_args)
        if sig.kind != 'function': self.fail(n,'value is not callable')
        if len(args) != len(sig.args)-1: self.fail(n,f'expected {len(sig.args)-1} arguments, got {len(args)}')
        for expected,actual in zip(sig.args[:-1],args): self.check(n,expected,actual)
        return sig.args[-1]

    def constructor_signature(self,typ):
        target = self.structs[typ.name]
        if target.constructor: return substitute(target.constructor,self.mapping(typ))
        if target.base and target.base.kind == 'struct':
            base=substitute(target.base,self.mapping(typ))
            sig=self.constructor_signature(base)
            return sig if sig is not None else Type('default_constructor',base.name,base.args)
        if target.base and target.base.kind=='foreign':
            ctor=self.foreign_constructor(target.base)
            return Type('foreign_constructor',ctor.name)
        return None

    def expression(self,n):
        k,v,c = n.kind,n.value,n.children
        if k in ('string','number'):
            return Type('literal',json.dumps(decode_string(v),ensure_ascii=False) if k == 'string' else (str(int(float(v))) if math.isfinite(float(v)) and float(v).is_integer() else str(float(v))),(STRING if k == 'string' else NUMBER,))
        if k == 'name':
            if v in ('true','false'): return Type('literal',v,(BOOL,))
            if v == 'undefined': return UNDEFINED
            if v == 'super':
                if not self.current_class or not self.structs[self.current_class].base: self.fail(n,'super requires a derived class')
                base=self.structs[self.current_class].base
                if self.static_context:
                    return Type('constructor',base.name,base.args) if base.kind=='struct' else self.foreign_constructor(base)
                return base
            return super().expression(n)
        if k in ('optional_member','optional_index','optional_call'):
            base = self.expr(c[0])
            remaining = union(*(t for t in base.args if t not in (NULL,UNDEFINED))) if base.kind == 'union' else base
            if k == 'optional_member': result = self.property(n,remaining,v)
            elif k == 'optional_index':
                index = self.expr(c[1])
                if remaining.kind == 'array': self.check(n,NUMBER,index); result = remaining.args[0]
                elif remaining == STRING: self.check(n,NUMBER,index); result = STRING
                elif remaining == ANY: result = ANY
                else: self.fail(n,'optional index requires an array or string')
            else: result = self.call_signature(n,remaining,[self.expr(a) for a in c[1:]]) if remaining != ANY else ANY
            n.chain_value_type=result
            return union(result,UNDEFINED)
        if k in ('member','index','call') and getattr(n,'optional_chain',False):
            self.expr(c[0])
            base=c[0].chain_value_type
            if k=='member':result=self.property(n,base,v)
            elif k=='index':
                self.check(n,NUMBER,self.expr(c[1]))
                if base.kind!='array' and base!=STRING:self.fail(n,'cannot index optional chain value')
                result=base.args[0] if base.kind=='array' else STRING
            else:result=self.call_signature(n,base,[self.expr(a) for a in c[1:]])
            n.chain_value_type=result
            return union(result,UNDEFINED)
        if k == 'type_apply':
            callee = self.expr(c[0])
            arguments = [self.declared_type(n,t) for t in v]
            if callee.kind == 'constructor':
                typ = self.declared_type(n,c[0].value+'<'+','.join(v)+'>')
                return Type('constructor',typ.name,typ.args)
            if callee.kind != 'generic_function': self.fail(n,'type arguments require a generic function or struct')
            parameters = callee.args[1:]
            if len(arguments) != len(parameters): self.fail(n,'incorrect number of type arguments')
            mapping = dict(zip((p.name for p in parameters),arguments))
            for p in parameters: self.check(n,substitute(p.args[0],mapping),mapping[p.name])
            return substitute(callee.args[0],mapping)
        if k=='unary' and v in ('+','-') and c[0].kind=='number':
            value=float(c[0].value)*(1 if v=='+' else -1)
            return Type('literal',str(int(value)) if math.isfinite(value) and value.is_integer() else str(value),(NUMBER,))
        if k == 'unary' and v == 'typeof': self.expr(c[0]); return STRING
        if k == 'binary' and v == '??':
            left,right = self.expr(c[0]),self.expr(c[1])
            return union(*(t for t in left.args if t not in (NULL,UNDEFINED)),right) if left.kind == 'union' else right if left in (NULL,UNDEFINED) else union(left,right)
        if k == 'binary' and v == 'instanceof':
            self.expr(c[0]); target = self.expr(c[1])
            if target.kind != 'constructor' and not is_external(target) and target != ANY: self.fail(n,'instanceof requires a constructor')
            return BOOL
        if k == 'call':
            if c[0].kind == 'name' and c[0].value == 'super':
                self.expr(c[0])
                if not self.in_constructor: self.fail(n,'super() is only valid in a derived constructor')
                base = self.structs[self.current_class].base
                sig = self.constructor_signature(base) if base.kind == 'struct' else None
                args = [self.expr(a) for a in c[1:]]
                if sig and sig.kind!='default_constructor': self.call_signature(n,sig,args)
                elif base.kind=='foreign':
                    value=self.foreign_constructor(base)
                    self.foreign_call(n,value,args,construct=True)
                elif base.kind == 'struct':
                    if len(args)>1 or args and args[0].kind != 'record': self.fail(n,'parent constructor expects a field object')
                    if args:
                        for name,t in args[0].fields:
                            fields = self.members(base)
                            if name not in fields: self.fail(n,'unknown parent field: '+name)
                            self.check(n,fields[name],t)
                return VOID
            callee = self.expand(self.expr(c[0]))
            if callee.kind=='foreign':return self.foreign_call(n,callee,[self.expr(a) for a in c[1:]])
            if callee.kind in ('generic_function','function'):
                return self.call_signature(n,callee,[self.expr(a) for a in c[1:]])
        if k in ('new','composite'):
            names = v.split('.')
            constructor = self.lookup(n,names[0]).typ
            for name in names[1:]: constructor = self.property(n,constructor,name)
            if constructor.kind=='foreign' and k=='new':
                return self.foreign_call(n,constructor,[self.expr(a) for a in c],construct=True,type_args=[self.declared_type(n,t) for t in getattr(n,'type_args',[])])
            if constructor.kind == 'constructor':
                target = self.structs[constructor.name]
                type_args = getattr(n,'type_args',[])
                if type_args:
                    typ = self.declared_type(n,v+'<'+','.join(type_args)+'>')
                elif target.parameters:
                    mapping = {}
                    if k == 'composite':
                        for item in c:
                            if item.kind == 'property' and item.value in target.fields: self.infer(target.fields[item.value],self.expr(item.children[0]),mapping)
                    else:
                        sig = target.constructor
                        if sig:
                            for formal,arg in zip(sig.args[:-1],c): self.infer(formal,self.expr(arg),mapping)
                    if any(p not in mapping for p,_ in target.parameters): self.fail(n,'cannot infer struct type arguments')
                    typ = Type('struct',constructor.name,tuple(mapping[p] for p,_ in target.parameters))
                    for p,constraint in target.parameters:
                        if constraint: self.check(n,self.with_context(n,constraint,mapping),mapping[p])
                else: typ = Type('struct',constructor.name)
                n.constructor_name = v
                sig = self.constructor_signature(typ)
                if k == 'composite' and sig is not None and sig.kind!='default_constructor': self.fail(n,'struct literal is not allowed with a custom constructor; use new')
                if k == 'new' and sig and sig.kind!='default_constructor':
                    self.call_signature(n,sig,[self.expr(a) for a in c])
                else:
                    supplied = self.expr(c[0]) if k == 'new' and c else self.expr(Node('object',children=c,line=n.line)) if k == 'composite' else Type('record')
                    if k == 'new' and len(c)>1 or supplied.kind != 'record': self.fail(n,'struct constructor requires one field object')
                    fields = self.struct_fields(Type('struct',sig.name,sig.args)) if sig and sig.kind=='default_constructor' else self.struct_fields(typ)
                    raw_fields=self.structs[sig.name].fields if sig and sig.kind=='default_constructor' else target.fields
                    if self.strict_null:
                        for field in self.required_fields(typ):
                            if target.base or field not in dict(supplied.fields):self.fail(n,'field requires an initializer or constructor: '+field)
                    for field,raw in raw_fields.items():
                        if raw.kind=='param' and field not in dict(supplied.fields) and not self.compatible(fields[field],NULL):self.fail(n,'generic field requires an initializer: '+field)
                    if k=='composite':
                        keys=[decode_string(i.value) if i.value.startswith(('"',"'")) else i.value for i in c if i.kind=='property']
                        if len(keys)!=len(set(keys)):self.fail(n,'duplicate struct field')
                    for name,t in supplied.fields:
                        self.access_member(n,typ,name)
                        if name not in fields: self.fail(n,'unknown field: '+name)
                        self.check(n,fields[name],t)
                n.instance_type = typ
                return typ
        if k=='index':
            base=self.expand(self.expr(c[0]))
            if base.kind=='array':self.check(n,NUMBER,self.expr(c[1]));return base.args[0]
        if k=='binary' and v in ('&&','||'):
            left=self.expr(c[0])
            with self.narrowing(c[0],v=='&&'):right=self.expr(c[1])
            self.check(n,BOOL,left);self.check(n,BOOL,right);return BOOL
        if k == 'binary':
            # Preserve literals for assignments but use their primitive types for operators.
            left,right = self.expr(c[0]),self.expr(c[1])
            if left.kind == 'param': left = left.args[0]
            if right.kind == 'param': right = right.args[0]
            left,right = widen(left),widen(right)
            if v in ('==','!=') and (left in (NULL,UNDEFINED) or right in (NULL,UNDEFINED)): return BOOL
            if v in ('&&','||'): self.check(n,BOOL,left); self.check(n,BOOL,right); return BOOL
            if v in ('==','!='):
                if not self.compatible(left,right) and not self.compatible(right,left): self.fail(n,'incompatible comparison')
                return BOOL
            if v in ('<','>','<=','>='):
                if left not in (NUMBER,STRING,ANY) or right not in (NUMBER,STRING,ANY): self.fail(n,'comparison requires matching numbers or strings')
                self.check(n,left,right); return BOOL
            if v == '+' and left == right == STRING: return STRING
            self.check(n,NUMBER,left); self.check(n,NUMBER,right); return NUMBER
        return super().expression(n)

    def foreign_constructor(self,typ):
        entry=self.declarations.property(typ,'constructor')
        # Instance metadata's symbol can be resolved back to its value by name.
        for name,key in self.type_names.items():
            if key in self.structs and self.structs[key].base==typ:
                base=self.structs[key].node.base
                parts=base.split('<')[0].split('.')
                value=self.lookup(self.structs[key].node,parts[0]).typ
                for part in parts[1:]:value=self.property(self.structs[key].node,value,part)
                return value
        self.fail(self.structs[self.current_class].node,'cannot resolve parent constructor')

    def foreign_subclass(self,typ,owner):
        queue,seen=[typ],set()
        while queue:
            current=queue.pop()
            if current.name==owner:return True
            if current.name in seen:continue
            seen.add(current.name)
            queue.extend(self.declarations.typ(t) for t in self.declarations.describe(current).get('bases',[]))
        return False

    def optional_members(self,typ):
        if typ.kind=='foreign':return {p['name'] for p in self.declarations.fields(typ) if p['optional']}
        if typ.kind=='interface':
            target=self.structs[typ.name]
            result=set()
            for parent in target.bases:result.update(self.optional_members(parent))
            return result-set(target.fields)-set(target.methods)
        return set()

    def foreign_mapping(self,typ):
        description=self.declarations.describe(typ)
        mapping=dict(zip((self.declarations.typ(p).name for p in description.get('parameters',[])),typ.args))
        for argument,actual in zip(description.get('arguments',[]),typ.args):
            self.infer(self.declarations.typ(argument),actual,mapping)
        return mapping

    def foreign_signature(self,description,mapping=None):
        mapping={} if mapping is None else dict(mapping)
        params=[substitute(self.declarations.typ(p['type']),mapping) for p in description['params']]
        result=substitute(self.declarations.typ(description['result']),mapping)
        return params,result

    def foreign_call(self,n,callee,args,construct=False,type_args=None):
        signatures=self.declarations.describe(callee).get('constructors' if construct else 'calls',[])
        errors=[]
        for sig in signatures:
            try:
                parameters=sig.get('parameters',[])
                mapping={}
                if type_args:
                    if len(type_args)!=len(parameters):self.fail(n,'incorrect external type arguments')
                    mapping={self.declarations.typ(p['type']).name:t for p,t in zip(parameters,type_args)}
                raw,_=self.foreign_signature(sig)
                if not mapping:
                    for formal,actual in zip(raw,args):self.infer(formal,actual,mapping)
                for p in parameters:
                    typ=self.declarations.typ(p['type'])
                    if typ.name not in mapping:mapping[typ.name]=typ.args[0]
                    self.check(n,substitute(typ.args[0],mapping),mapping[typ.name])
                params,result=self.foreign_signature(sig,mapping)
                required=sum(not p['optional'] and not p['rest'] for p in sig['params'])
                rest=bool(sig['params'] and sig['params'][-1]['rest'])
                if len(args)<required or not rest and len(args)>len(params):self.fail(n,'external argument count mismatch')
                for i,actual in enumerate(args):
                    expected=params[min(i,len(params)-1)]
                    if rest and i>=len(params)-1 and expected.kind=='array':expected=expected.args[0]
                    self.check(n,expected,actual)
                if result.kind=='foreign' and mapping:
                    description=self.declarations.describe(result)
                    formal=description.get('parameters',[])
                    if formal:
                        arguments=description.get('arguments',[]) or formal
                        result=Type('foreign',result.name,tuple(substitute(self.declarations.typ(p),mapping) for p in arguments))
                return result
            except CompileError as e:errors.append(str(e))
        self.fail(n,'external '+('constructor' if construct else 'call')+' type mismatch'+(': '+errors[0] if errors else ': value is not callable'))

    def foreign_compatible(self,expected,actual):
        if expected==actual or expected in (ANY,UNKNOWN) or actual in (ANY,NEVER):return True
        if actual.kind=='union':return all(self.compatible(expected,t) for t in actual.args)
        if expected.kind=='union':return any(self.compatible(t,actual) for t in expected.args)
        if expected.kind=='param':return expected==actual
        if actual.kind=='param':return self.compatible(expected,actual.args[0])
        if expected.kind=='foreign':
            description=self.declarations.describe(expected)
            if description.get('isFunctionObject') and actual.kind in ('constructor','function','generic_function'):return True
            if description['constructors'] and actual.kind=='constructor':
                instance=Type('struct',actual.name,actual.args)
                signature=self.constructor_signature(instance)
                for external in description['constructors']:
                    params,result=self.foreign_signature(external)
                    if not self.compatible(result,instance):continue
                    if signature is None:return True
                    if signature.kind=='function' and self.compatible(function(params,VOID),signature):return True
                return False
            if description['calls']:
                if actual.kind=='function':
                    for sig in description['calls']:
                        params,result=self.foreign_signature(sig)
                        if self.compatible(function(params,result),actual):return True
                    return False
                if actual.kind=='foreign':
                    right=self.declarations.describe(actual)
                    return all(any(self.compatible(function(*self.foreign_signature(left)),function(*self.foreign_signature(r))) for r in right['calls']) for left in description['calls'])
                return False
            if actual.kind=='struct':
                current=self.structs[actual.name].base
                while current:
                    if current==expected:return True
                    current=self.structs[current.name].base if current.kind=='struct' else None
                supplied=self.members(actual)
            elif actual.kind=='record':supplied=dict(actual.fields)
            elif actual.kind=='foreign':
                actual_description=self.declarations.describe(actual)
                actual_mapping=self.foreign_mapping(actual)
                supplied={p['name']:substitute(self.declarations.typ(p['type']),actual_mapping) for p in self.declarations.fields(actual)}
            else:return False
            fields=self.declarations.fields(expected)
            known={p['name']:p for p in fields}
            mapping=self.foreign_mapping(expected)
            for p in fields:
                if p['access']!='public':continue
                if p['name'] not in supplied:
                    if not p['optional']:return False
                elif not self.compatible(substitute(self.declarations.typ(p['type']),mapping),supplied[p['name']]):return False
            if actual.kind=='record' and any(n not in known for n in supplied):return False
            return True
        if actual.kind=='foreign' and expected.kind in ('interface','record'):
            members=self.members(expected) if expected.kind=='interface' else dict(expected.fields)
            for name,typ in members.items():
                p=self.declarations.property(actual,name)
                if not p or not self.compatible(typ,self.declarations.typ(p['type'])):return False
            return True
        return False

    def assignable(self,node):
        if node.kind == 'member':
            base = self.expr(node.children[0])
            if base.kind=='foreign':
                entry=self.declarations.property(base,node.value)
                if entry and entry['readonly']:self.fail(node,'readonly external member: '+node.value)
            if base.kind in ('struct','constructor'):
                target = self.access_member(node,base,node.value)
                if target and (base.kind=='constructor',node.value) in target.readonly:
                    if not self.in_constructor or self.current_class != self.find_owner(base,node.value): self.fail(node,'readonly member: '+node.value)
        typ=super().assignable(node)
        if node.kind=='name' and getattr(self,'assignment_operator',None)=='=':
            return getattr(self.lookup(node,node.value),'declared_type',typ)
        return typ

    def find_owner(self,typ,name):
        if name in self.structs[typ.name].fields: return typ.name
        base = self.structs[typ.name].base
        return self.find_owner(base,name) if base and base.kind == 'struct' else None

    @contextmanager
    def narrowing(self,condition,truth=True):
        if condition.kind=='unary' and condition.value=='!':
            with self.narrowing(condition.children[0],not truth):yield
            return
        if condition.kind=='binary' and ((condition.value=='&&' and truth) or (condition.value=='||' and not truth)):
            with self.narrowing(condition.children[0],truth),self.narrowing(condition.children[1],truth):yield
            return
        changes = []
        if condition.kind == 'binary' and condition.value in ('==','!='):
            left,right = condition.children
            if right.kind == 'name' and right.value in ('nil','null','undefined') and left.kind == 'name':
                symbol = self.lookup(left,left.value); original = symbol.typ
                candidates = original.args if original.kind == 'union' else (original,)
                null = UNDEFINED if right.value == 'undefined' else NULL
                equal = (condition.value == '==') == truth
                symbol.typ = union(*(t for t in candidates if (t == null) == equal))
                changes.append((symbol,original))
            elif left.kind == 'unary' and left.value == 'typeof' and left.children[0].kind == 'name' and right.kind == 'string':
                symbol = self.lookup(left.children[0],left.children[0].value); original = symbol.typ
                desired = {'string':STRING,'number':NUMBER,'boolean':BOOL,'undefined':UNDEFINED}.get(decode_string(right.value))
                equal = (condition.value == '==') == truth
                candidates = original.args if original.kind == 'union' else (original,)
                symbol.typ = union(*(t for t in candidates if (widen(t)==desired) == equal));changes.append((symbol,original))
        if condition.kind=='binary' and condition.value=='instanceof' and condition.children[0].kind=='name':
            left,right=condition.children
            symbol=self.lookup(left,left.value);original=symbol.typ
            ctor=self.expr(right)
            target=Type('struct',ctor.name,ctor.args) if ctor.kind=='constructor' else None
            if target:
                candidates=original.args if original.kind=='union' else (original,)
                symbol.typ=union(*(t for t in candidates if self.compatible(target,t)==truth));changes.append((symbol,original))
        try: yield
        finally:
            for symbol,original in changes: symbol.typ = original

    def zero_type(self,typ):
        primitive=widen(typ)
        if primitive==NUMBER:return Type('literal','0',(NUMBER,))
        if primitive==BOOL:return Type('literal','false',(BOOL,))
        if primitive==STRING:return Type('literal','""',(STRING,))
        if typ.kind=='union':
            if NULL in typ.args:return NULL
            bases={widen(t) for t in typ.args}
            if len(bases)==1:return self.zero_type(next(iter(bases)))
        return NULL

    def statement(self,n):
        k,v,c = n.kind,n.value,n.children
        if k in ('alias','interface','enum'): return
        if k=='decl' and c[0] is None:
            expected=self.declared_type(n,v[2])
            self.check(n,expected,self.zero_type(expected))
        if k == 'if':
            self.check(n,BOOL,self.expr(c[0]))
            with self.narrowing(c[0]),self.scope(): self.statements(c[1])
            if c[2] is not None:
                with self.narrowing(c[0],False),self.scope(): self.statements(c[2])
            return
        if k == 'switch':
            subject = self.expr(c[0]); candidates = subject.args if subject.kind == 'union' else (subject,)
            covered,defaults = set(),0
            for case in c[1:]:
                defaults += not bool(case.value)
                for value in case.value:
                    typ = self.expr(value)
                    if not self.compatible(subject,typ) and not self.compatible(typ,subject): self.fail(value,'case type does not match switch')
                    if typ in covered: self.fail(value,'duplicate case')
                    covered.add(typ)
                self.switch_depth += 1
                try:
                    with self.scope():
                        if c[0].kind == 'name' and case.value:
                            original = self.lookup(c[0],c[0].value)
                            self.scopes[-1][c[0].value] = Symbol(union(*(self.types[id(x)] for x in case.value)),original.constant)
                        self.statements(case.children)
                finally: self.switch_depth -= 1
            if defaults>1: self.fail(n,'duplicate default')
            if not defaults and all(t.kind == 'literal' for t in candidates) and any(t not in covered for t in candidates): self.fail(n,'non-exhaustive switch')
            n.exhaustive = defaults>0 or all(t.kind=='literal' and t in covered for t in candidates)
            return
        if k == 'break' and self.switch_depth: return
        previous=getattr(self,'assignment_operator',None)
        self.assignment_operator=v if k=='assign' else None
        try:super().statement(n)
        finally:self.assignment_operator=previous
        if k=='assign' and v=='=' and c[0].kind=='name':
            symbol=self.lookup(c[0],c[0].value)
            if getattr(symbol,'declared_type',symbol.typ).kind=='union':symbol.typ=self.types[id(c[1])]
        if k == 'decl' and not v[2] or k == 'assign' and v == ':=':
            name = v[1] if k == 'decl' else c[0].value
            symbol = self.scopes[-1][name]
            if not (k == 'decl' and v[0] == 'const'): symbol.typ = widen(symbol.typ)
            self.types[id(n)] = symbol.typ
            symbol.declared_type=symbol.typ

    def exits(self,nodes):
        if nodes and nodes[-1].kind == 'switch' and getattr(nodes[-1],'exhaustive',False):
            result = set()
            for case in nodes[-1].children[1:]:
                outcome = self.exits(case.children)
                result |= (outcome-{'break'}) | ({'normal'} if 'break' in outcome else set())
            prefix = super().exits(nodes[:-1])
            return (prefix-{'normal'}) | result if 'normal' in prefix else prefix
        return super().exits(nodes)
