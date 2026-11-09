#include <windows.h>
static DWORD init_result;
BOOL WINAPI DllMain(HINSTANCE m, DWORD reason, LPVOID reserved) {
    char name[256]; DWORD n; HANDLE h;
    (void)m; (void)reserved;
    if (reason != DLL_PROCESS_ATTACH) return TRUE;
    n = GetEnvironmentVariableA("CODEX_SYNTHETIC_PIPE", name, sizeof(name));
    if (!n || n >= sizeof(name)) { init_result = 9999; return TRUE; }
    h = CreateNamedPipeA(name, PIPE_ACCESS_DUPLEX | FILE_FLAG_FIRST_PIPE_INSTANCE,
                         PIPE_TYPE_BYTE, 1, 256, 256, 0, NULL);
    init_result = h == INVALID_HANDLE_VALUE ? GetLastError() : 0;
    if (h != INVALID_HANDLE_VALUE) CloseHandle(h);
    return TRUE;
}
__declspec(dllexport) DWORD InitResult(void) { return init_result; }
__declspec(dllexport) HANDLE StaticCreate(const char *n) {
    return CreateNamedPipeA(n, PIPE_ACCESS_DUPLEX | FILE_FLAG_FIRST_PIPE_INSTANCE,
                            PIPE_TYPE_BYTE, 1, 256, 256, 0, NULL);
}
__declspec(dllexport) HANDLE StaticOpen(const char *n) {
    return CreateFileA(n, GENERIC_WRITE, 0, NULL, OPEN_EXISTING, 0, NULL);
}
__declspec(dllexport) HANDLE DynamicCreate(const char *n) {
    typedef HANDLE (WINAPI *Fn)(LPCSTR,DWORD,DWORD,DWORD,DWORD,DWORD,DWORD,LPSECURITY_ATTRIBUTES);
    Fn f = (Fn)GetProcAddress(GetModuleHandleA("kernel32.dll"), "CreateNamedPipeA");
    return f(n, PIPE_ACCESS_DUPLEX | FILE_FLAG_FIRST_PIPE_INSTANCE, PIPE_TYPE_BYTE, 1, 256, 256, 0, NULL);
}
