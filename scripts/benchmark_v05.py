"""Reproducible cold/warm/incremental builds; memory measured in a separate pass."""
import argparse
import json
from pathlib import Path
import platform
import statistics
import sys
import tempfile
import time
import tracemalloc
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from gscript.build import build,configure
from gscript.cache import BuildSession
from gscript.project import Project


def measure(root,count,external=False):
    for i in range(count):
        prefix='import Phaser from "phaser"\n' if external else ''
        (root/f'm{i}.gs').write_text(prefix+f'export func f{i}(n int) int {{ return n+1 }}\n'+('scene := new Phaser.Scene("test")\n' if external else ''))
    entry=root/'main.gs';entry.write_text('\n'.join(f'import {{ f{i} }} from "./m{i}.gs"' for i in range(count))+'\nprintln(f0(1))')
    settings=configure(entry,cache_dir=root/'cache');session=BuildSession()
    start=time.perf_counter();project,_=build(settings,session=session);cold=time.perf_counter()-start
    warm=[]
    for _ in range(3):
        start=time.perf_counter();build(settings,session=session);warm.append(time.perf_counter()-start)
    changed=root/'m0.gs';changed.write_text(changed.read_text().replace('n+1','n+2'))
    old=(session.parse_cache.parsed,session.emitted)
    start=time.perf_counter();build(settings,session=session);incremental=time.perf_counter()-start
    delta=[session.parse_cache.parsed-old[0],session.emitted-old[1]]
    tracemalloc.start();memory_session=BuildSession();build(settings,session=memory_session);_,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    return dict(modules=count,cold_seconds=cold,warm_median_seconds=statistics.median(warm),incremental_seconds=incremental,incremental_parsed=delta[0],incremental_emitted=delta[1],python_peak_bytes=peak,output_bytes=sum(p.stat().st_size for p in settings.out_dir.rglob('*') if p.is_file()))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result={'python':platform.python_version(),'platform':platform.platform(),'memory_scope':'tracemalloc Python allocations; excludes Node child process RSS','cases':[]}
    with tempfile.TemporaryDirectory(prefix='.gs-bench-',dir=ROOT) as temporary:
        root=Path(temporary)
        for count,foreign in [(1,False),(100,False),(1000,False),(1,True),(100,True)]:
            case=root/(str(count)+('-phaser' if foreign else '-gs'));case.mkdir()
            measured=measure(case,count,foreign);measured['external_phaser']=foreign;result['cases'].append(measured)
        samples=[]
        case=root/'1000-gs'
        for _ in range(3):
            start=time.perf_counter();Project(case/'main.gs',prepare_output=False).check();samples.append(time.perf_counter()-start)
        result['gs_1000_check_median_seconds']=statistics.median(samples)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
