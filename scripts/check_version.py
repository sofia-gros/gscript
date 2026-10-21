"""Refuse a release whose tag, distribution and compiler versions disagree."""
from pathlib import Path
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gscript import __version__

version = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version']
if not (__version__ == version and sys.argv[1] == 'v' + version):
    raise SystemExit(f'version mismatch: compiler={__version__}, package={version}, tag={sys.argv[1]}')
if not (ROOT / 'docs/releases' / (sys.argv[1] + '.md')).is_file():
    raise SystemExit('release notes are required')
print(f'Release version verified: {version}')
