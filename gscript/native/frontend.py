"""Native-only syntax on top of GS's existing lexer and expression parser."""
from parser.extended_parser import ExtendedParser
from parser.syntax import Node,Token,CompileError,decode_string


class NativeParser(ExtendedParser):
    def type_name(self,union=True):
        if self.at('[') and self.tokens[self.i+1].kind=='number':
            self.take('[');count=self.take();self.take(']')
            if not count.isdigit() or int(count)<1:self.fail('fixed array size must be a positive integer')
            return '['+count+']'+self.type_name(False)
        if self.accept('winfunc'):
            self.take('(');args=[]
            while not self.at(')'):
                args.append(self.type_name())
                if not self.accept(','):break
            self.take(')');result=self.type_name(False) if self.token.kind=='name' else 'void'
            return 'winfunc('+','.join(args)+')'+result
        return super().type_name(union)

    def statement(self):
        line=self.token.line
        if self.accept('link'):
            if self.token.kind!='string':self.fail('link requires a library name string')
            return Node('link',decode_string(self.take()),line=line)
        if self.accept('extern'):
            if self.token.kind!='string':self.fail('extern requires "C" or "system"')
            abi=decode_string(self.take())
            if abi not in ('C','system'):self.fail('unsupported external calling convention: '+abi)
            self.take('func');name=self.name();params=self.params()
            result=self.type_name() if self.token.kind=='name' or self.at('[') else 'void'
            node=Node('extern',(name,params,result,False,None),line=line);node.abi=abi
            return node
        if self.accept('system'):
            if not self.at('func'):self.fail('system must precede a function')
            node=self.function();node.abi='system';return node
        if self.at('type') and self.tokens[self.i+2].text=='union':
            token=self.tokens[self.i+2]
            self.tokens[self.i+2]=Token('struct',token.line,token.kind,token.column)
            node=super().statement();node.kind='native_union';return node
        return super().statement()


def parse(source):
    try:
        parser=NativeParser(source)
        return Node('program',children=parser.program())
    except RecursionError as error:raise CompileError('source nesting exceeds native compiler capacity') from error
