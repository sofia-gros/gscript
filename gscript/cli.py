"""Build gscript files into JavaScript ES modules."""
import argparse
from pathlib import Path
import sys

from parser.compiler import CompileError, Compiler, parse_code
from parser.checker import unwrap
from parser.syntax import decode_string
from . import __version__
from .project import build_project, write_output


def main(argv=None, default_source=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', nargs='?', type=Path, default=default_source)
    output = parser.add_mutually_exclusive_group()
    output.add_argument('-o', '--output', type=Path, help='write one ES module (use .mjs)')
    output.add_argument('--out-dir', type=Path, help='build entry and relative .gos imports')
    output.add_argument('--check', action='store_true', help='parse and type-check without output')
    parser.add_argument('--root', type=Path, help='project root for --out-dir (default: entry directory)')
    parser.add_argument('--version', action='version', version=f'gscript {__version__}')
    args = parser.parse_args(argv)
    if args.source is None:
        parser.error('source is required')
    if args.root and not args.out_dir:
        parser.error('--root requires --out-dir')
    try:
        if args.out_dir:
            build_project(args.source, args.out_dir, args.root)
            return 0
        source = args.source.read_text(encoding='utf-8')
        program = parse_code(source)
        for original in program.children:
            node = unwrap(original)
            if node.kind == 'import' and decode_string(node.value[1]).endswith('.gos'):
                raise CompileError('use --out-dir to build .gos module imports', node.line)
        javascript = Compiler().compile(program)
        if args.check:
            return 0
        if args.output:
            if args.source.resolve() == args.output.resolve():
                raise CompileError('output must not overwrite the source file')
            write_output(args.output, javascript)
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
