"""Public compiler API: parse, check, then generate a JavaScript ES module."""
from .syntax import CompileError, Node, Parser, parse_code, decode_string
from .checker import Checker
from .emitter import Emitter

__all__ = ['CompileError', 'Compiler', 'compile_source', 'parse_code']


class Compiler:
    def compile(self, program, format='mjs'):
        if format not in ('js', 'mjs', 'ts'):
            raise CompileError(f'unsupported output format: {format}')
        for node in program.children:
            if node.kind == 'import' and decode_string(node.value[1]).endswith(('.gs', '.gos')):
                raise CompileError('local GS imports require Project or build_project with a source path', node.line)
        try:
            checker = Checker()
            checker.run(program)
            return Emitter(format, checker).compile(program)
        except RecursionError as error:
            raise CompileError('source nesting exceeds compiler capacity') from error


def compile_source(source, format='mjs'):
    return Compiler().compile(parse_code(source), format)
