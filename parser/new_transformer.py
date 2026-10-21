"""Compatibility entry point for the original compiler API."""
from .compiler import Compiler


class MyLangTransformer:
    def transform(self, tree):
        return Compiler().compile(tree)
