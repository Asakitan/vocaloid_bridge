package main
import ("fmt"; "os"; "syscall"; "unsafe")
func main() {
 if len(os.Args)!=3 || os.Args[1]!="child" {os.Exit(239)}
 adv:=syscall.NewLazyDLL("advapi32.dll"); var token syscall.Handle; var isAC, n uint32
 ok,_,_:=adv.NewProc("OpenProcessToken").Call(^uintptr(0),8,uintptr(unsafe.Pointer(&token))); if ok==0 {os.Exit(240)}
 ok,_,_ = adv.NewProc("GetTokenInformation").Call(uintptr(token),29,uintptr(unsafe.Pointer(&isAC)),4,uintptr(unsafe.Pointer(&n))); syscall.CloseHandle(token); if ok==0 {os.Exit(241)}
 fmt.Printf("token_is_appcontainer=%d\n",isAC)
 name,_:=syscall.UTF16PtrFromString(os.Args[2]); p:=syscall.NewLazyDLL("kernel32.dll").NewProc("CreateNamedPipeW")
 h,_,err:=p.Call(uintptr(unsafe.Pointer(name)),3|0x80000,0,1,256,256,0,0); code:=0
 if h==^uintptr(0) {code=int(err.(syscall.Errno))} else {syscall.CloseHandle(syscall.Handle(h))}
 fmt.Printf("create_named_pipe_error=%d\n",code); os.Exit(0)
}
