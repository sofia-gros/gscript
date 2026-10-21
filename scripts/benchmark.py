"""Measure GS-only module checks and cold/warm external checks on this machine."""
import argparse
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gscript.project import Project


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--modules', type=int, default=100)
    parser.add_argument('--runs', type=int, default=7)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.modules < 1 or args.runs < 1:
        parser.error('modules and runs must be positive')
    result = {'modules': args.modules, 'runs': args.runs}
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for i in range(args.modules):
            code = (f'import {{ f as next }} from "./m{i+1}.gs"\n' if i < args.modules - 1 else '') + 'export func f(n int) int { return n + 1 }'
            (root / f'm{i}.gs').write_text(code)
        samples = []
        for _ in range(args.runs):
            start = time.perf_counter()
            Project(root / 'm0.gs').check()
            samples.append(time.perf_counter() - start)
        result['gs_only_median_seconds'] = statistics.median(samples)
        source = ROOT / 'tests/fixtures/interop/phaser.gs'
        start = time.perf_counter()
        first = Project(source, cache_dir=root / 'cache').check()
        result['external_cold_seconds'] = time.perf_counter() - start
        assert not first.interop_stats['cache_hit']
        samples = []
        for _ in range(args.runs):
            start = time.perf_counter()
            project = Project(source, cache_dir=root / 'cache').check()
            samples.append(time.perf_counter() - start)
            assert project.interop_stats['cache_hit']
        result['external_warm_median_seconds'] = statistics.median(samples)
        result['external_cache_speedup'] = result['external_cold_seconds'] / result['external_warm_median_seconds']
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(text + '\n')
    print(text)


if __name__ == '__main__':
    main()
