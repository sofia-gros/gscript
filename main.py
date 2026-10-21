"""Compatibility launcher; installed users can invoke `gscript` or `python -m gscript`."""
from pathlib import Path
from gscript.cli import main

if __name__ == '__main__':
    raise SystemExit(main(default_source=Path(__file__).parent / 'examples/main.gos'))
