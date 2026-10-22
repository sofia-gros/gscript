"""GS built-in registry. Resolution is lexical, never source-text replacement."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Builtin:
    name: str
    javascript: str
    minimum: int = 1
    maximum: int | None = 1
    result: str = 'void'


REGISTRY = {b.name:b for b in (
    Builtin('print','console.log',0,None),
    Builtin('println','console.log',0,None),
    Builtin('printf','console.log',1,None),
    Builtin('int','Math.trunc',result='int'),
    Builtin('float','Number',result='float'),
    Builtin('float64','Number',result='float'),
    Builtin('number','Number',result='number'),
    Builtin('string','String',result='string'),
    Builtin('len','((value) => value.length ?? value.size)',result='int'),
    Builtin('panic','((message) => { throw new globalThis.Error(globalThis.String(message)); })'),
)}


def check_call(checker, node, name, args):
    from .checker import INT, FLOAT, NUMBER, STRING, VOID, numeric, is_dynamic
    spec=REGISTRY[name]
    if len(args)<spec.minimum or spec.maximum is not None and len(args)>spec.maximum:
        checker.fail(node,f'{name} expects '+(str(spec.minimum) if spec.minimum==spec.maximum else f'at least {spec.minimum}')+' arguments')
    node.builtin_call=name
    if name in ('int','float','float64','number') and not (numeric(args[0]) or is_dynamic(args[0])):
        checker.fail(node,f'{name} conversion requires a numeric argument')
    if name=='printf':checker.check(node,STRING,args[0])
    if name=='len':
        typ=args[0]
        if typ.kind=='literal':typ=typ.args[0]
        if typ.kind=='array' or typ==STRING:node.length_property='length'
        elif typ.kind=='foreign':
            try:checker.property(node,typ,'size');node.length_property='size'
            except ValueError:checker.fail(node,'len requires an array, string, Map or Set')
        else:checker.fail(node,'len requires an array, string, Map or Set')
    return {'int':INT,'float':FLOAT,'number':NUMBER,'string':STRING,'void':VOID}[spec.result]
