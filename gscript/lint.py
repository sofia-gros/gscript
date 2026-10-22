"""Additional, non-fatal GS diagnostics separate from compiler type errors."""
from dataclasses import dataclass,asdict
import re
from parser.checker import unwrap
from .analysis import walk


@dataclass(frozen=True)
class Diagnostic:
    file: str
    line: int
    column: int
    severity: str
    code: str
    message: str

    def to_dict(self):return asdict(self)


def lint_module(module):
    result=[];checker=module.checker
    def warn(node,code,message,span=None):
        span=span or getattr(node,'name_span',getattr(node,'span',(node.line,1)))
        result.append(Diagnostic(str(module.source),span[0],span[1],'warning',code,message))
    for symbol in checker.symbols:
        name=symbol.original_name
        if name.startswith('_') or name in module.exports or symbol.category in ('struct','function'):continue
        references=[n for n in symbol.references.values() if not getattr(n,'write_only',False)]
        if not references and not getattr(symbol,'type_used',False):
            warn(symbol.node,'GS1002' if symbol.category in ('import','external') else 'GS1001',('Unused import: ' if symbol.category in ('import','external') else 'Unused variable: ')+name,symbol.definition_span)
        node=symbol.node
        scopes=getattr(node,'lexical_scopes',())
        if symbol.scope_depth and any(name in scope and scope[name] is not symbol for scope in scopes[:-1]):warn(node,'GS1007','Shadowed binding: '+name,symbol.definition_span)
    def sequence(nodes):
        terminal=False
        for original in nodes:
            node=unwrap(original)
            if terminal:warn(node,'GS1003','Unreachable statement')
            if checker.terminates([node]):terminal=True
    sequence(module.program.children)
    for node in walk(module.program):
        if node.kind in ('func','lambda','case'):sequence(node.children)
        elif node.kind=='if':
            sequence(node.children[1])
            if node.children[2] is not None:sequence(node.children[2])
            condition=node.children[0]
            if condition.kind=='name' and condition.value in ('true','false'):warn(condition,'GS1004','Condition is always '+condition.value)
            elif condition.kind=='binary' and condition.children[0].kind in ('number','string') and condition.children[1].kind==condition.children[0].kind and condition.children[0].value==condition.children[1].value and condition.value in ('==','!=','<=','>=','<','>'):warn(condition,'GS1004','Condition has a constant result')
        elif node.kind=='for':sequence(node.children[3])
        elif node.kind=='range':sequence(node.children[1])
        if node.kind=='call' and getattr(node,'builtin_call',None) in ('int','float','float64','number','string'):
            target={'float64':'float'}.get(node.builtin_call,node.builtin_call)
            actual=checker.types.get(id(node.children[1]))
            if actual and (actual.args[0].kind if actual.kind=='literal' else actual.kind)==target:warn(node,'GS1005','Unnecessary '+target+' conversion')
        if node.kind=='decl' and node.value[2]=='any' and node.children[0]:
            actual=checker.types.get(id(node.children[0]))
            if actual and actual.kind not in ('any','external','unknown'):warn(node,'GS1006','Explicit any hides the inferred '+str(actual)+' type')
        if node.kind=='binary' and node.value in ('/','%') and node.children[1].kind=='number':
            try:zero=float(node.children[1].value)==0
            except ValueError:zero=False
            if zero:warn(node,'GS1009','Division or remainder by zero produces a non-finite numeric result')
        if getattr(node,'deprecated',False):warn(node,'GS1008','Deprecated API: '+str(node.value))
    for i,line in enumerate(module.source_text.splitlines(),1):
        match=re.search(r'[ \t]+$',line)
        if match:result.append(Diagnostic(str(module.source),i,match.start()+1,'warning','GS1012','Trailing whitespace (safe to fix)'))
    return sorted(set(result),key=lambda d:(d.line,d.column,d.code))


def lint_project(project):return [d for module in project.modules.values() for d in lint_module(module)]
