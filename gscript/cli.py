"""Compile GS to checked JavaScript or TypeScript ES modules."""
import argparse
from pathlib import Path
import sys

from parser.compiler import CompileError
from . import __version__
from .project import FORMATS, SOURCE_SUFFIXES, Project, build_project, module_marker, write_output


def main(argv=None, default_source=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', nargs='?', type=Path, default=default_source)
    parser.add_argument('--format', choices=FORMATS, help='output format (default: inferred from -o, otherwise mjs)')
    output = parser.add_mutually_exclusive_group()
    output.add_argument('-o', '--output', type=Path, help='write a single module; extension must match --format')
    output.add_argument('--out-dir', type=Path, help='build the complete local GS module graph')
    output.add_argument('--check', action='store_true', help='check the module graph without writing output')
    parser.add_argument('--root', type=Path, help='source root (default: entry directory)')
    parser.add_argument('--strict-null', action='store_true', help='reject nil for non-nullable types')
    parser.add_argument('--typescript', type=Path, help='TypeScript compiler package or lib/typescript.js')
    parser.add_argument('--no-cache', action='store_true', help='disable the external type-checking cache')
    parser.add_argument('--cache-dir', type=Path, help='external type-checking cache directory')
    parser.add_argument('--version', action='version', version=f'gscript {__version__}')
    args = parser.parse_args(argv)
    if args.source is None:
        parser.error('source is required')
    if args.source.suffix not in SOURCE_SUFFIXES:
        parser.error('source extension must be .gs or .gos')
    if args.output and args.source.resolve() == args.output.resolve():
        print(f'{args.source}: output must not overwrite the source file', file=sys.stderr)
        return 1
    inferred = args.output.suffix[1:] if args.output else None
    format = args.format or inferred or 'mjs'
    if format not in FORMATS:
        parser.error('output extension must be .js, .mjs or .ts')
    if inferred and inferred != format:
        parser.error('output extension must match --format')
    try:
        if args.out_dir:
            build_project(args.source, args.out_dir, args.root, format, cache=not args.no_cache, cache_dir=args.cache_dir, typescript=args.typescript, strict_null=args.strict_null)
            return 0
        project = Project(args.source, args.root, format, cache=not args.no_cache, cache_dir=args.cache_dir, typescript=args.typescript, strict_null=args.strict_null).check()
        if args.check:
            return 0
        if len(project.modules) > 1 or (project.has_external and project._external_result(format).get('files')):
            raise CompileError('use --out-dir to build local module dependencies')
        javascript = project.emit(project.modules[project.entry], format)
        if args.output:
            if args.source.resolve() == args.output.resolve():
                raise CompileError('output must not overwrite the source file')
            marker = module_marker(args.output.resolve().parent) if format in ('js', 'ts') else None
            write_output(args.output, javascript)
            if marker:
                write_output(marker, '{"type":"module"}\n')
        else:
            print(javascript, end='')
    except (CompileError, OSError, UnicodeError) as error:
        filename = getattr(error, 'filename', None) or args.source
        print(f'{filename}: {error}', file=sys.stderr)
        if isinstance(error, CompileError) and error.line:
            try:
                lines = Path(filename).read_text(encoding='utf-8').splitlines()
                if error.line <= len(lines):
                    print('  ' + lines[error.line - 1], file=sys.stderr)
                    if error.column:
                        print('  ' + ' ' * (error.column - 1) + '^', file=sys.stderr)
            except (OSError, UnicodeError):
                pass
        return 1
    return 0
