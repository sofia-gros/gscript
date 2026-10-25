extern "C" func puts(text cptr<cchar>) i32

export func greeting() {
  puts(cstr("GScript calls a C ABI library"))
}
