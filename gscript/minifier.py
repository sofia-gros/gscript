"""Linear lexical minifier for compiler-generated ES2022 (no external process)."""
import re

TOKEN=re.compile(r'(?P<comment>//[^\n]*|/\*[\s\S]*?\*/)|(?P<string>"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`)|(?P<word>[A-Za-z_$][\w$]*)|(?P<number>\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|(?P<operator>===|!==|=>|\?\.|\?\?|==|!=|<=|>=|&&|\|\||\+\+|--|\+=|-=|\.\.\.)|(?P<space>\s+)|(?P<other>.)')


def minify(code, track=False):
    parts=[];positions=[];last='';last_kind=None;out_line=out_col=in_line=in_col=0
    for match in TOKEN.finditer(code):
        text,kind=match.group(),match.lastgroup
        line,column=in_line,in_col
        count=text.count('\n')
        if count:in_line+=count;in_col=len(text.rsplit('\n',1)[1])
        else:in_col+=len(text)
        if kind in ('space','comment'):continue
        space=last_kind in ('word','number') and kind in ('word','number') or last.endswith(('+','-','/')) and text[0]==last[-1] or last.endswith('/') and text.startswith('*') or last_kind=='number' and text.startswith('.')
        if space:parts.append(' ');out_col+=1
        if track:positions.append((out_line,out_col,line,column))
        parts.append(text)
        if '\n' in text:out_line+=text.count('\n');out_col=len(text.rsplit('\n',1)[1])
        else:out_col+=len(text)
        last,last_kind=text,kind
    result=''.join(parts)+'\n'
    return (result,positions) if track else result
