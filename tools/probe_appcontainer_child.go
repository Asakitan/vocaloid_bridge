// Native synthetic named-pipe child for probe_appcontainer_pipe.cs.
package main

import (
    "fmt"
    "os"
    "syscall"
    "unsafe"
)

func main() {
    if len(os.Args) != 3 || os.Args[1] != "child" { os.Exit(239) }
    fmt.Println("stage=native_main")
    adv := syscall.NewLazyDLL("advapi32.dll")
    open := adv.NewProc("OpenProcessToken")
    info := adv.NewProc("GetTokenInformation")
    var token syscall.Handle
    ok, _, _ := open.Call(^uintptr(0), 8, uintptr(unsafe.Pointer(&token)))
    if ok == 0 { os.Exit(240) }
    var value, returned uint32
    ok, _, _ = info.Call(uintptr(token), 29, uintptr(unsafe.Pointer(&value)), 4, uintptr(unsafe.Pointer(&returned)))
    syscall.CloseHandle(token)
    if ok == 0 { os.Exit(241) }
    fmt.Printf("stage=token token_is_appcontainer=%d\n", value)
    name, err := syscall.UTF16PtrFromString(os.Args[2])
    if err != nil { os.Exit(243) }
    h, err := syscall.CreateFile(name, syscall.GENERIC_READ|syscall.GENERIC_WRITE, 0, nil, syscall.OPEN_EXISTING, 0, 0)
    code := 0
    if err != nil { if e, ok := err.(syscall.Errno); ok { code=int(e) } else { code=999 } } else { syscall.CloseHandle(h) }
    fmt.Printf("stage=create_file error=%d\n", code)
    if code>999 { code=999 }
    if value!=0 { code+=1000 }
    os.Exit(code)
}
