#include <windows.h>
#include <stdio.h>
#include <string.h>
static int hits;
static HANDLE WINAPI create_hook(LPCSTR n,DWORD a,DWORD b,DWORD c,DWORD d,DWORD e,DWORD f,LPSECURITY_ATTRIBUTES g) {
    (void)n;(void)a;(void)b;(void)c;(void)d;(void)e;(void)f;(void)g; hits++; SetLastError(ERROR_INVALID_NAME); return INVALID_HANDLE_VALUE;
}
static HANDLE WINAPI open_hook(LPCSTR n,DWORD a,DWORD b,LPSECURITY_ATTRIBUTES c,DWORD d,DWORD e,HANDLE f) {
    (void)n;(void)a;(void)b;(void)c;(void)d;(void)e;(void)f; hits++; SetLastError(ERROR_INVALID_NAME); return INVALID_HANDLE_VALUE;
}
static int patch(HMODULE m) {
    BYTE *b=(BYTE*)m; IMAGE_DOS_HEADER *d=(IMAGE_DOS_HEADER*)b;
    IMAGE_NT_HEADERS *nt=(IMAGE_NT_HEADERS*)(b+d->e_lfanew);
    IMAGE_IMPORT_DESCRIPTOR *x=(IMAGE_IMPORT_DESCRIPTOR*)(b+nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT].VirtualAddress);
    int found=0;
    for (; x->Name; x++) { IMAGE_THUNK_DATA *o,*i; if(!x->OriginalFirstThunk) continue;
        o=(IMAGE_THUNK_DATA*)(b+x->OriginalFirstThunk); i=(IMAGE_THUNK_DATA*)(b+x->FirstThunk);
        for (;o->u1.AddressOfData;o++,i++) { IMAGE_IMPORT_BY_NAME *n; void *p=NULL; DWORD old,tmp;
            if(IMAGE_SNAP_BY_ORDINAL(o->u1.Ordinal)) continue;
            n=(IMAGE_IMPORT_BY_NAME*)(b+o->u1.AddressOfData);
            if(!strcmp((char*)n->Name,"CreateNamedPipeA")) p=(void*)create_hook;
            if(!strcmp((char*)n->Name,"CreateFileA")) p=(void*)open_hook;
            if(p) { if(!VirtualProtect(&i->u1.Function,sizeof(void*),PAGE_READWRITE,&old)) return -1;
                i->u1.Function=(ULONGLONG)p; if(!VirtualProtect(&i->u1.Function,sizeof(void*),old,&tmp)) return -2; found++; }
        }
    } return found;
}
int main(int argc,char **argv) {
    typedef HANDLE (*Call)(const char*); typedef DWORD (*Init)(void);
    HMODULE a,b; HANDLE h; char name[256]; DWORD initA,initB; int p;
    if(argc!=3 || strlen(argv[1])>80) return 10;
    if(strncmp(argv[1],"CodexSynthetic",14)) return 11;
    snprintf(name,sizeof(name),"\\\\.\\pipe\\%s",argv[1]); SetEnvironmentVariableA("CODEX_SYNTHETIC_PIPE",name);
    a=LoadLibraryA(argv[2]); if(!a) {printf("load_error=%lu\n",GetLastError());return 12;}
    initA=((Init)GetProcAddress(a,"InitResult"))();
    p=patch(a); printf("init_before_patch=%lu patched_slots=%d\n",initA,p); if(initA || p!=2) return 13;
    h=((Call)GetProcAddress(a,"StaticCreate"))(name); printf("static_create_hook_hits=%d error=%lu\n",hits,GetLastError()); if(h!=INVALID_HANDLE_VALUE || hits!=1) return 14;
    h=((Call)GetProcAddress(a,"StaticOpen"))(name); printf("static_open_hook_hits=%d error=%lu\n",hits,GetLastError()); if(h!=INVALID_HANDLE_VALUE || hits!=2) return 15;
    h=((Call)GetProcAddress(a,"DynamicCreate"))(name); printf("dynamic_create_hook_hits=%d success=%d\n",hits,h!=INVALID_HANDLE_VALUE); if(h==INVALID_HANDLE_VALUE || hits!=2) return 16; CloseHandle(h);
    b=LoadLibraryA("probe_iat_ansi_fixture2.dll"); if(!b) {printf("load_second_error=%lu\n",GetLastError());return 17;}
    initB=((Init)GetProcAddress(b,"InitResult"))(); h=((Call)GetProcAddress(b,"StaticCreate"))(name);
    printf("second_init=%lu second_static_hook_hits=%d success=%d\n",initB,hits,h!=INVALID_HANDLE_VALUE);
    if(h==INVALID_HANDLE_VALUE || hits!=2 || initB) return 18; CloseHandle(h); FreeLibrary(b); FreeLibrary(a); return 0;
}
