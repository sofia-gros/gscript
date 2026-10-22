"""Rewrite module literals, never matching ordinary string contents."""
from .minifier import TOKEN
from parser.syntax import decode_string
import json


def rewrite_imports(code, rewrite):
    tokens=[m for m in TOKEN.finditer(code) if m.lastgroup not in ('space','comment')]
    replacements=[]
    for i,token in enumerate(tokens):
        if token.lastgroup!='string' or token.group().startswith('`'):continue
        previous=tokens[i-1].group() if i else ''
        dynamic=previous=='(' and i>1 and tokens[i-2].group()=='import'
        if previous not in ('from','import') and not dynamic:continue
        specifier=decode_string(token.group())
        updated=rewrite(specifier)
        if updated!=specifier:replacements.append((token.start(),token.end(),json.dumps(updated,ensure_ascii=False)))
    for start,end,value in reversed(replacements):code=code[:start]+value+code[end:]
    return code
