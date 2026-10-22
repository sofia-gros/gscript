"""Shared checked-AST traversal and symbol identities for lint and LSP."""
from parser.syntax import Node


def walk(value):
    if isinstance(value,Node):
        yield value
        yield from walk(value.value)
        yield from walk(value.children)
    elif isinstance(value,(tuple,list)):
        for item in value:yield from walk(item)
    elif isinstance(value,dict):
        for item in value.values():yield from walk(item)


def root_symbol(symbol):
    seen=set()
    while (getattr(symbol,'semantic_target',None) or getattr(symbol,'target',None)) is not None and id(symbol) not in seen:
        seen.add(id(symbol));symbol=getattr(symbol,'semantic_target',None) or symbol.target
    return symbol
