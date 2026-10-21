"""Write SHA-256 checksums for all release assets, in stable name order."""
import hashlib
from pathlib import Path
import sys

root = Path(sys.argv[1])
lines = []
for path in sorted(root.iterdir()):
    if path.is_file() and path.name != 'SHA256SUMS':
        lines.append(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.name)
(root / 'SHA256SUMS').write_text('\n'.join(lines) + '\n', encoding='utf-8')
