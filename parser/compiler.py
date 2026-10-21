"""Public compiler API: parse, check, then generate a JavaScript ES module."""
from .syntax import CompileError, Node, Parser, parse_code
from .checker import Checker
from .emitter import Emitter

__all__ = ['CompileError', 'Compiler', 'compile_source', 'parse_code']


class Compiler:
    def compile(self, program, format='mjs'):
        if format not in ('js', 'mjs', 'ts'):
            raise CompileError(f'unsupported output format: {format}')
        checker = Checker()
        checker.run(program)
        return Emitter(format, checker).compile(program)


def compile_source(source, format='mjs'):
    return Compiler().compile(parse_code(source), format)
