// OS API probe only. This example does not create a window.
link "kernel32"
extern "system" func GetCurrentProcessId() u32
extern "system" func GetLastError() u32
extern "system" func SetLastError(code u32)

SetLastError(u32(123))
println("Process", GetCurrentProcessId(), "Error", GetLastError())
