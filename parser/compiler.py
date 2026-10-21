"""Public compiler API: parse, check, then generate a JavaScript ES module."""
from .syntax import CompileError, Node, Parser, parse_code
from .checker import Checker
from .emitter import Emitter

__all__ = ['CompileError', 'Compiler', 'compile_source', 'parse_code']


class Compiler:
    def compile(self, program):
        Checker().run(program)
        return Emitter().compile(program)


def compile_source(source):
    return Compiler().compile(parse_code(source))
