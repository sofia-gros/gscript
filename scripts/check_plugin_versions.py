"""Keep the compiler, language server and both editor plugins version-aligned."""
import json
from pathlib import Path
import sys
import tomllib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from gscript import __version__


def main():
    for file in ('editors/zed/extension.toml','editors/zed/Cargo.toml','pyproject.toml'):
        data=tomllib.loads((ROOT/file).read_text())
        actual=data.get('version') or data.get('package',data.get('project',{})).get('version')
        assert actual==__version__,(file,actual,__version__)
    assert json.loads((ROOT/'editors/vscode/package.json').read_text())['version']==__version__
    assert json.loads((ROOT/'editors/tree-sitter-gs/tree-sitter.json').read_text())['metadata']['version']==__version__
    if len(sys.argv)>1:assert sys.argv[1] in ('plugin-v'+__version__, 'plugin-v'+__version__+'-r2'),sys.argv[1]
    print('Compiler, language server, VSCode, Zed and grammar versions verified:',__version__)


if __name__=='__main__':main()
