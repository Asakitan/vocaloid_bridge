#include <windows.h>
#include <wchar.h>

/* Only the two known imports in our own synthetic DLL are patched. */
typedef HANDLE (WINAPI *CreatePipeFn)(LPCWSTR,DWORD,DWORD,DWORD,DWORD,DWORD,DWORD,LPSECURITY_ATTRIBUTES);
typedef HANDLE (WINAPI *OpenFn)(LPCWSTR,DWORD,DWORD,LPSECURITY_ATTRIBUTES,DWORD,DWORD,HANDLE);
static CreatePipeFn originalCreate;
static OpenFn originalOpen;
static int translate(LPCWSTR source, wchar_t *out, size_t capacity) {
    static const wchar_t prefix[]=L"\\\\.\\pipe\\CodexSynthetic";
    static const wchar_t dest[]=L"\\\\.\\pipe\\LOCAL\\CodexSynthetic";
    size_t n=wcslen(prefix), d=wcslen(dest), tail;
    if (!source || wcsncmp(source,prefix,n)!=0) return 0;
    tail=wcslen(source+n);
    if (d+tail+1>capacity) return 0;
    memcpy(out,dest,d*sizeof(wchar_t));
    memcpy(out+d,source+n,(tail+1)*sizeof(wchar_t));
    return 1;
}
static HANDLE WINAPI mappedCreate(LPCWSTR n,DWORD a,DWORD b,DWORD c,DWORD d,DWORD e,DWORD f,LPSECURITY_ATTRIBUTES g) {
    wchar_t out[512]; if(!translate(n,out,512)){SetLastError(ERROR_INVALID_NAME);return INVALID_HANDLE_VALUE;}
    return originalCreate(out,a,b,c,d,e,f,g);
}
static HANDLE WINAPI mappedOpen(LPCWSTR n,DWORD a,DWORD b,LPSECURITY_ATTRIBUTES c,DWORD d,DWORD e,HANDLE f) {
    wchar_t out[512]; if(!translate(n,out,512)){SetLastError(ERROR_INVALID_NAME);return INVALID_HANDLE_VALUE;}
    return originalOpen(out,a,b,c,d,e,f);
}
__declspec(dllexport) int PatchSyntheticImports(HMODULE module) {
    BYTE *base=(BYTE *)module; IMAGE_DOS_HEADER *dos=(IMAGE_DOS_HEADER *)base;
    IMAGE_NT_HEADERS *nt=(IMAGE_NT_HEADERS *)(base+dos->e_lfanew);
    IMAGE_IMPORT_DESCRIPTOR *desc=(IMAGE_IMPORT_DESCRIPTOR *)(base+nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT].VirtualAddress);
    void **slots[2]={0}; void *replacement[2]={(void *)mappedCreate,(void *)mappedOpen};
    const char *names[2]={"CreateNamedPipeW","CreateFileW"}; int i;
    for(;desc->Name;desc++) {
        IMAGE_THUNK_DATA *orig=(IMAGE_THUNK_DATA *)(base+desc->OriginalFirstThunk);
        IMAGE_THUNK_DATA *iat=(IMAGE_THUNK_DATA *)(base+desc->FirstThunk);
        if(!desc->OriginalFirstThunk) continue;
        for(;orig->u1.AddressOfData;orig++,iat++) {
            if(IMAGE_SNAP_BY_ORDINAL(orig->u1.Ordinal)) continue;
            IMAGE_IMPORT_BY_NAME *entry=(IMAGE_IMPORT_BY_NAME *)(base+orig->u1.AddressOfData);
            for(i=0;i<2;i++) if(lstrcmpA((char *)entry->Name,names[i])==0) slots[i]=(void **)&iat->u1.Function;
        }
    }
    if(!slots[0] || !slots[1]) return 1;
    originalCreate=(CreatePipeFn)*slots[0]; originalOpen=(OpenFn)*slots[1];
    for(i=0;i<2;i++) { DWORD old,ignore; if(!VirtualProtect(slots[i],sizeof(void *),PAGE_READWRITE,&old)) return 2+i;
        *slots[i]=replacement[i]; if(!VirtualProtect(slots[i],sizeof(void *),old,&ignore)) return 4+i; }
    return 0;
}
