#include <windows.h>

/* Synthetic DLL: its imports remain ordinary Win32 named-pipe calls. */
__declspec(dllexport) HANDLE SyntheticCreate(const wchar_t *name) {
    return CreateNamedPipeW(name, PIPE_ACCESS_DUPLEX | FILE_FLAG_FIRST_PIPE_INSTANCE,
                            PIPE_TYPE_BYTE, 1, 256, 256, 0, NULL);
}
__declspec(dllexport) HANDLE SyntheticOpen(const wchar_t *name) {
    return CreateFileW(name, GENERIC_READ | GENERIC_WRITE, 0, NULL,
                       OPEN_EXISTING, 0, NULL);
}
