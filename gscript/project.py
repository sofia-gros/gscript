"""Compile a local .gos module graph before writing any build output."""
import json
import os
from pathlib import Path
import tempfile

from parser.compiler import Compiler, CompileError, parse_code
from parser.checker import unwrap
from parser.syntax import decode_string


def write_output(path, contents):
    """Replace an output atomically, without truncating existing files on error."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n',
                                         dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(contents)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def build_project(entry, out_dir, root=None):
    entry, out_dir = Path(entry).resolve(), Path(out_dir).resolve()
    root = Path(root).resolve() if root else entry.parent
    outputs, visited = {}, set()

    def visit(source):
        if not source.is_relative_to(root):
            raise CompileError(f'module is outside project root {root}: {source}')
        if source in visited:
            return
        visited.add(source)
        try:
            program = parse_code(source.read_text(encoding='utf-8'))
            for original in program.children:
                node = unwrap(original)
                if node.kind != 'import':
                    continue
                binding, literal = node.value
                try:
                    module = decode_string(literal)
                except (ValueError, SyntaxError) as error:
                    raise CompileError('invalid module string', node.line) from error
                if not module.endswith('.gos'):
                    continue
                if not module.startswith(('./', '../')):
                    raise CompileError('.gos imports must be relative paths', node.line)
                dependency = (source.parent / module).resolve()
                if not dependency.is_file():
                    raise CompileError(f'module not found: {module}', node.line)
                visit(dependency)
                # Keep output layout aligned with the resolved dependency even for symlinks.
                source_output = out_dir / source.relative_to(root).with_suffix('.mjs')
                dependency_output = out_dir / dependency.relative_to(root).with_suffix('.mjs')
                relative = os.path.relpath(dependency_output, source_output.parent).replace(os.sep, '/')
                node.value = (binding, json.dumps(relative if relative.startswith('.') else './' + relative))
            javascript = Compiler().compile(program)
            output = out_dir / source.relative_to(root).with_suffix('.mjs')
            if output.resolve() in visited:
                raise CompileError('build output must not overwrite a source file')
            outputs[output] = javascript
        except (CompileError, OSError, UnicodeError) as error:
            if not hasattr(error, 'filename') or not error.filename:
                error.filename = str(source)
            raise

    visit(entry)
    # All modules must parse and type-check before any output is changed.
    for output, javascript in outputs.items():
        write_output(output, javascript)
    return out_dir / entry.relative_to(root).with_suffix('.mjs')
