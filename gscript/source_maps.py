"""Source Map v3 with GS AST positions, composed after TS emission and minification."""
from bisect import bisect_right
from difflib import SequenceMatcher
import json
import os
import re

from .minifier import TOKEN, minify

BASE64='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
MARKER=re.compile(r'/\*__GS_POS_(\d+)_(\d+)__\*/')


def vlq(value):
    value=(-value<<1)|1 if value<0 else value<<1
    result=''
    while True:
        digit=value&31;value>>=5
        result+=BASE64[digit|(32 if value else 0)]
        if not value:return result


def tokens(code):
    return [m for m in TOKEN.finditer(code) if m.lastgroup not in ('space','comment')]


def remove_markers(code):
    parts=[];positions=[];offset=0;end=0
    for match in MARKER.finditer(code):
        part=code[end:match.start()];parts.append(part);offset+=len(part)
        positions.append((offset,int(match[1])-1,int(match[2])-1));end=match.end()
    parts.append(code[end:])
    return ''.join(parts),positions


def line_starts(code):
    return [0]+[m.end() for m in re.finditer('\n',code)]


def utf16_column(text):return len(text.encode('utf-16-le'))//2


def map_code(marked,generated,source,source_name,filename):
    plain,anchors=remove_markers(marked)
    old,new=tokens(plain),tokens(generated)
    if not anchors:anchors=[(0,0,0)]
    offsets=[p[0] for p in anchors]
    old_positions=[anchors[max(0,bisect_right(offsets,m.start())-1)][1:] for m in old]
    assigned={}
    matcher=SequenceMatcher(None,[m.group() for m in old],[m.group() for m in new],autojunk=False)
    for block in matcher.get_matching_blocks():
        for i in range(block.size):assigned[block.b+i]=old_positions[block.a+i]
    generated_lines=line_starts(generated);source_lines=source.splitlines()
    rows={};last_original=(0,0)
    for i,token in enumerate(new):
        original=assigned.get(i,last_original);last_original=original
        line,col=original
        line=min(max(line,0),max(0,len(source_lines)-1))
        col=utf16_column(source_lines[line][:col]) if source_lines else 0
        row=bisect_right(generated_lines,token.start())-1
        column=utf16_column(generated[generated_lines[row]:token.start()])
        rows.setdefault(row,[]).append((column,line,col))
    mappings=[];previous_source_line=previous_source_col=0
    for row in range(generated.count('\n')+1):
        segments=[];previous_generated=0
        for column,line,col in rows.get(row,[]):
            segments.append(vlq(column-previous_generated)+vlq(0)+vlq(line-previous_source_line)+vlq(col-previous_source_col))
            previous_generated=column;previous_source_line=line;previous_source_col=col
        mappings.append(','.join(segments))
    return {'version':3,'file':filename,'sourceRoot':'','sources':[source_name],'sourcesContent':[source],'names':[],'mappings':';'.join(mappings)}


def source_maps(project,outputs,settings):
    results=dict(outputs)
    for module in project.modules.values():
        target=settings.out_dir/module.source.relative_to(project.root).with_suffix('.'+settings.format)
        if settings.output and module.source==project.entry:target=settings.output.resolve()
        if target not in results:continue
        code=results[target]
        if settings.minify and settings.format!='ts':code=minify(code)
        marked=project.emit(module,settings.format,runtime_format=settings.format,mapping=True)
        source_name=os.path.relpath(module.source,target.parent).replace(os.sep,'/')
        mapping=map_code(marked,code,module.source_text,source_name,target.name)
        map_path=target.with_name(target.name+'.map')
        results[map_path]=json.dumps(mapping,ensure_ascii=False,separators=(',',':'))+'\n'
        results[target]=code.rstrip()+'\n//# sourceMappingURL='+map_path.name+'\n'
    return results
