"""Public parsing entry point for gscript."""
from .compiler import CompileError, parse_code

__all__ = ['CompileError', 'parse_code']
