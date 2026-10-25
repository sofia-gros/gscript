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
    parser.add_argument('--backend',choices=('js','native'))
    parser.add_argument('--emit',choices=('exe','object','shared','static','c'))
    parser.add_argument('--cc',type=Path)
    parser.add_argument('--target')
    parser.add_argument('--link',action='append',default=[])
    parser.add_argument('--header',type=Path)
    parser.add_argument('--library-dir',action='append',type=Path,default=[])
    parser.add_argument('--link-object',action='append',type=Path,default=[])
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
        selected=configure(args.source)
        if (args.backend or selected.backend)=='native':
            if args.format or args.ts_compiler or args.sourcemap or args.declaration or args.minify is not None:raise CompileError('JS/TS output options are not applicable to the native backend')
            from .native.build import build_native
            settings=configure(args.source,root=args.root,out_dir=args.out_dir,library_dirs=args.library_dir,objects=args.link_object)
            build_native(settings.entry,root=settings.root,output=args.output,emit=args.emit or 'exe',cc=args.cc,target=args.target or settings.native_target,links=args.link,header=args.header,check_only=args.check,out_dir=args.out_dir,library_dirs=args.library_dir,objects=args.link_object)
            return 0
        if args.emit or args.cc or args.target or args.link or args.header or args.library_dir or args.link_object:raise CompileError('native toolchain options require --backend native')
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
