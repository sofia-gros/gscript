"""Validate native GS records/callbacks against the real Win32 SDK, without a GUI."""
import argparse
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from gscript.native.build import build_native
from gscript.native.emitter import CEmitter

SOURCE='''link "kernel32"
extern "system" func GetCurrentProcessId() u32
extern "system" func GetLastError() u32
extern "system" func SetLastError(value u32)
type WindowClass struct {
  style u32
  callback winfunc(ptr<void>,u32,usize,isize)isize
  classExtra i32
  windowExtra i32
  instance ptr<void>
  icon ptr<void>
  cursor ptr<void>
  background ptr<void>
  menu cptr<u16>
  name cptr<u16>
}
system func WindowProc(window ptr<void>,message u32,wparam usize,lparam isize) isize {
  return lparam+isize(1)
}
export func callbackAddress() winfunc(ptr<void>,u32,usize,isize)isize {return WindowProc}
export func processId() u32 {return GetCurrentProcessId()}
export func errorRoundTrip(value u32) u32 {SetLastError(value);return GetLastError()}
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--cc',required=True);args=parser.parse_args()
    cc=Path(args.cc).resolve()
    if cc.stem!='zig':parser.error('this SDK cross-validation uses the Zig distribution and its MinGW headers')
    for target,machine in [('x86_64-windows-gnu',0x8664),('x86-windows-gnu',0x14c)]:
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);entry=root/'api.gs';entry.write_text(SOURCE)
            project,obj=build_native(entry,emit='object',cc=cc,target=target,header=root/'api.h')
            record=project.modules[entry.resolve()].types['WindowClass'].name
            fields={'style':'style','callback':'lpfnWndProc','classExtra':'cbClsExtra','windowExtra':'cbWndExtra','instance':'hInstance','icon':'hIcon','cursor':'hCursor','background':'hbrBackground','menu':'lpszMenuName','name':'lpszClassName'}
            assertions=['_Static_assert(sizeof('+record+')==sizeof(WNDCLASSW),"record size");','_Static_assert(_Alignof('+record+')==_Alignof(WNDCLASSW),"record alignment");']
            for gs,c in fields.items():assertions.append('_Static_assert(offsetof('+record+','+CEmitter(project).field(gs)+')==offsetof(WNDCLASSW,'+c+'),"field offset");')
            driver=root/'driver.c';driver.write_text('#include <windows.h>\n#include "api.h"\n'+'\n'.join(assertions)+'''\nint main(void) {
  if (processId()!=GetCurrentProcessId()) return 1;
  if (errorRoundTrip(123)!=123) return 2;
  WNDPROC callback=(WNDPROC)callbackAddress();
  if (callback(NULL,0,0,41)!=42) return 3;
  return 0;
}\n''')
            exe=root/'probe.exe'
            subprocess.run([str(cc),'cc','-target',target,'-std=c11',str(driver),str(obj),'-lkernel32','-o',str(exe)],check=True,timeout=180)
            data=exe.read_bytes();pe=struct.unpack_from('<I',data,0x3c)[0]
            assert data[:2]==b'MZ' and data[pe:pe+4]==b'PE\0\0'
            assert struct.unpack_from('<H',data,pe+4)[0]==machine
            if os.name=='nt':subprocess.run([str(exe)],check=True,timeout=20)
            print(target+': SDK size/alignment/offsets, system callbacks, kernel32 linkage and PE format verified'+('; execution passed' if os.name=='nt' else '; execution requires Windows'),flush=True)

if __name__=='__main__':main()
