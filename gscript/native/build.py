"""Compile checked GS to C, then a native executable/object/shared library."""
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
from parser.syntax import CompileError
from .checker import NativeProject
from .emitter import CEmitter


def build_native(entry,root=None,output=None,emit='exe',cc=None,target=None,links=(),header=None,check_only=False,out_dir=None,library_dirs=(),objects=()):
    if emit not in ('exe','object','shared','static','c'):raise CompileError('native --emit must be exe, object, shared, static or c')
    if target=='native':target=None
    entry=Path(entry).resolve();root=Path(root or entry.parent).resolve()
    windows=target is not None and 'windows' in target or target is None and os.name=='nt'
    bits=32 if target and target.split('-')[0] in ('x86','i386','i486','i586','i686','arm','thumb') else 64 if target else __import__('struct').calcsize('P')*8
    import re
    if any(not re.fullmatch(r'[A-Za-z0-9_.+-]+',name) for name in links):raise CompileError('invalid native link library name')
    try:project=NativeProject(entry,root,bits,library=emit in ('shared','object','static')).check()
    except RecursionError as error:raise CompileError('native module/type nesting exceeds compiler capacity') from error
    code,definitions=CEmitter(project).emit()
    if check_only:return project,None
    suffix={'exe':'.exe' if windows else '', 'object':'.obj' if windows else '.o','shared':'.dll' if windows else '.dylib' if (target and ('macos' in target or 'darwin' in target) or not target and platform.system()=='Darwin') else '.so','static':'.lib' if windows else '.a','c':'.c'}[emit]
    output=Path(output or Path(out_dir or root/'dist/native')/(entry.stem+suffix)).resolve()
    selected_compiler=cc or shutil.which('clang') or shutil.which('cc') or shutil.which('gcc')
    msvc_link=bool(windows and selected_compiler and 'clang' in Path(selected_compiler).stem and (target is None or 'msvc' in target))
    objects=[Path(p).resolve() for p in objects]
    if any(not p.is_file() for p in objects):raise CompileError('native link object does not exist')
    import_library=output.with_suffix('.lib' if msvc_link else '.dll.a') if windows and emit=='shared' else None
    destinations=[output,*([Path(header).resolve()] if header else []),*([import_library] if import_library else [])]
    if len(set(destinations))!=len(destinations):raise CompileError('native output/header/import-library paths must differ')
    if any(p.is_dir() for p in destinations):raise CompileError('native output path is a directory')
    protected=set(project.modules)|set(objects)
    for destination in destinations:
        if destination in protected:raise CompileError('native output must not overwrite GS source')
    if header and Path(header).resolve()==output:raise CompileError('native header and binary paths must differ')
    if emit=='c':
        output.parent.mkdir(parents=True,exist_ok=True);output.write_text(code,encoding='utf-8')
    else:
        compiler=selected_compiler
        if not compiler:raise CompileError('native compilation requires a GCC-compatible C11 driver (Clang, GCC or Zig); use --cc /path/to/zig')
        compiler=str(compiler)
        driver=[compiler,'cc'] if Path(compiler).stem=='zig' else [compiler]
        if target:
            if Path(compiler).stem=='zig':driver+=['-target',target]
            elif 'clang' in Path(compiler).stem:driver+=['--target='+target]
            else:raise CompileError('--target requires Clang or Zig plus the target libraries')
        # The compiler/linker writes only a staging output. Existing artifacts survive errors.
        output.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.gs-native-',dir=output.parent) as directory:
            temp=Path(directory);source=temp/'program.c';binary=temp/('program'+suffix)
            source.write_text(code,encoding='utf-8')
            args=[*driver,'-std=c11','-O2','-fno-strict-aliasing',str(source),'-o',str(binary)]
            if emit in ('object','static'):args+=['-c']
            elif emit=='shared':args+=['-shared']+([] if windows else ['-fPIC'])
            if emit not in ('object','static'):args+=[str(p) for p in objects]+['-L'+str(Path(p).resolve()) for p in library_dirs]+['-l'+name for name in dict.fromkeys([*project.links,*links])]+([] if windows else ['-lm'])
            staged_import=temp/'import.dll.a'
            if import_library:
                args+=['-Xlinker','/IMPLIB:'+str(staged_import)] if msvc_link else ['-Xlinker','--out-implib','-Xlinker',str(staged_import)]
            try:result=subprocess.run(args,capture_output=True,text=True,timeout=180)
            except (OSError,subprocess.TimeoutExpired) as error:raise CompileError('native C toolchain failed: '+str(error)) from error
            if result.returncode:raise CompileError('native C compilation/linking failed:\n'+result.stdout+result.stderr)
            if emit=='static':
                archive=temp/('archive'+suffix)
                archiver=[compiler,'ar'] if Path(compiler).stem=='zig' else [shutil.which('llvm-ar') or shutil.which('ar') or 'ar']
                archive_args=[*archiver,'rcs',str(archive),str(binary)]
                if msvc_link:
                    librarian=shutil.which('llvm-lib') or shutil.which('lib.exe')
                    if not librarian:raise CompileError('MSVC static libraries require llvm-lib or lib.exe')
                    archive_args=[librarian,'/OUT:'+str(archive),str(binary)]
                try:packed=subprocess.run(archive_args,capture_output=True,text=True,timeout=180)
                except (OSError,subprocess.TimeoutExpired) as error:raise CompileError('native archiver failed: '+str(error)) from error
                if packed.returncode:raise CompileError('native archiver failed: '+packed.stderr)
                binary=archive
            if import_library:
                if not staged_import.is_file():raise CompileError('native linker did not produce the Windows import library')
                os.replace(staged_import,import_library)
            os.replace(binary,output)
    if header:
        destination=Path(header).resolve();destination.parent.mkdir(parents=True,exist_ok=True);destination.write_text(definitions,encoding='utf-8')
    return project,output
