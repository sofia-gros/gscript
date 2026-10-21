"""gscript: Go-inspired syntax, JavaScript execution semantics."""
from parser.compiler import CompileError, Compiler, compile_source, parse_code

__version__ = '0.4.0'
__all__ = ['CompileError', 'Compiler', 'compile_source', 'parse_code']
