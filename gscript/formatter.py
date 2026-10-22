"""Token-aware GS formatting, accepted only when the parsed AST is unchanged."""
from parser.syntax import Node, tokenize, parse_code, CompileError


def semantic(value):
    if isinstance(value,Node):
        attributes=tuple((name,semantic(getattr(value,name))) for name in ('type_params','type_args','base','implements','field_mods','modifiers','parenthesized','optional_chain') if hasattr(value,name))
        return value.kind,semantic(value.value),semantic(value.children),attributes
    if isinstance(value,(tuple,list)):return tuple(map(semantic,value))
    if isinstance(value,dict):return tuple((k,semantic(v)) for k,v in value.items())
    return value


def format_source(source):
    original=parse_code(source)
    scanned=tokenize(source)
    events=[(t.line,t.column,t.text,t.kind) for t in scanned if t.text!='<eof>']
    events.extend((line,col,text,'comment') for text,line,col in scanned.comments)
    events.sort(key=lambda e:(e[0],e[1],e[3]!='comment'))
    lines=[];current='';depth=0;delimiters=[];for_header=False;previous=''
    def write(text,space=False):
        nonlocal current
        if not current:current='  '*depth+text
        else:current+=(' ' if space and not current.endswith(' ') else '')+text
    def newline():
        nonlocal current
        if current.strip():lines.append(current.rstrip())
        current=''
    operators={'=',':=','+','-','*','/','%','==','!=','<=','>=','<','>','&&','||','??','|','&','+=','-='}
    for i,(_,_,text,kind) in enumerate(events):
        following=events[i+1][2] if i+1<len(events) else ''
        if kind=='comment':
            if '\n' in text:
                newline()
                for line in text.splitlines():write(line);newline()
            else:
                write(text,bool(current.strip()))
                if text.startswith('//'):newline()
            continue
        if text==';':
            if for_header:write(';');write(' ')
            else:newline()
            previous=';';continue
        if text=='{':
            write('{',bool(current.strip()) and previous not in ('(','[','.','?.'))
            delimiters.append('{');depth+=1;newline();for_header=False
        elif text=='}':
            newline();depth=max(0,depth-1);write('}')
            if delimiters and delimiters[-1]=='{':delimiters.pop()
            if following not in (')',']',',',';','.', '?.','(', '[','else',*operators):newline()
        elif text=='(':
            write('(',previous in ('if','for','switch','catch'));delimiters.append('(')
        elif text==')':
            current=current.rstrip();write(')')
            if delimiters and delimiters[-1]=='(':delimiters.pop()
        elif text=='[':
            write('[',bool(current.strip()) and following==']' and previous not in ('(','[',':=' ,'='));delimiters.append('[')
        elif text==']':
            current=current.rstrip();write(']')
            if delimiters and delimiters[-1]=='[':delimiters.pop()
        elif text==',':
            current=current.rstrip();write(',')
            if delimiters and delimiters[-1]=='{':newline()
            else:write(' ')
        elif text==':':current=current.rstrip();write(':');write(' ')
        elif text in ('.','?.'):current=current.rstrip();write(text)
        elif text in ('++','--'):current=current.rstrip();write(text)
        elif text in operators:
            write(text,True);write(' ')
        else:
            if text=='for':for_header=True
            space=bool(current.strip()) and previous not in ('(','[','.','?.','...') and not current.endswith((' ','\t'))
            # []T and type applications may contain whitespace without changing GS.
            if previous==']':space=False
            write(text,space)
        previous=text
    newline()
    formatted='\n'.join(lines)+'\n'
    if semantic(original)!=semantic(parse_code(formatted)):raise CompileError('formatter could not preserve the AST; source was not changed')
    return formatted
