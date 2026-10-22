"""GS compiler and project tools."""
import argparse
from pathlib import Path
import sys

from parser.compiler import CompileError
from . import __version__


def main(argv=None, default_source=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    commands={'init','fmt','lint','watch'}
    if argv and argv[0] in commands:
        from .tools import command
        return command(argv)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',nargs='?',type=Path,default=default_source or Path('.'))
    parser.add_argument('--format',choices=('js','mjs','ts'))
    output=parser.add_mutually_exclusive_group()
    output.add_argument('-o','--output',type=Path)
    output.add_argument('--out-dir',type=Path)
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--root',type=Path)
    parser.add_argument('--strict-null',action='store_true',default=None)
    parser.add_argument('--typescript',type=Path)
    parser.add_argument('--no-cache',action='store_true')
    parser.add_argument('--cache-dir',type=Path)
    mini=parser.add_mutually_exclusive_group()
    mini.add_argument('--minify',action='store_true',default=None)
    mini.add_argument('--no-minify',dest='minify',action='store_false')
    parser.add_argument('--ts-compiler',choices=('gs','ts'))
    parser.add_argument('--sourcemap',action='store_true',default=None)
    parser.add_argument('--declaration',action='store_true',default=None)
    parser.add_argument('--version',action='version',version=f'gscript {__version__}')
    args=parser.parse_args(argv)
    try:
        from .build import configure,build
        if args.output and args.source.is_file() and args.output.resolve()==args.source.resolve():raise CompileError('output must not overwrite the source file')
        inferred=args.output.suffix[1:] if args.output else None
        if inferred and inferred not in ('js','mjs','ts'):parser.error('output extension must be .js, .mjs or .ts')
        if inferred and args.format and inferred!=args.format:parser.error('output extension must match --format')
        settings=configure(args.source,format=args.format or inferred,out_dir=args.out_dir or (args.output.resolve().parent if args.output else None),
                           root=args.root,strict_null=args.strict_null,typescript=args.typescript,
                           cache=not args.no_cache,cache_dir=args.cache_dir,minify=args.minify,
                           ts_compiler=args.ts_compiler,sourcemap=args.sourcemap,declaration=args.declaration,output=args.output)
        build(settings,args.check)
        return 0
    except (CompileError,OSError,UnicodeError,ValueError) as error:
        filename=getattr(error,'filename',None) or args.source
        print(f'{filename}: {error}',file=sys.stderr)
        if isinstance(error,CompileError) and error.line:
            try:
                lines=Path(filename).read_text(encoding='utf-8').splitlines()
                if error.line<=len(lines):
                    print('  '+lines[error.line-1],file=sys.stderr)
                    if error.column:print('  '+' '*(error.column-1)+'^',file=sys.stderr)
            except (OSError,UnicodeError):pass
        return 1
