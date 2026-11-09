// Synthetic named-pipe isolation probe. Never uses vendor IPC names.
using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;

class Probe {
    const uint DUPLEX = 3, FIRST = 0x00080000, OPEN_EXISTING = 3;
    const uint EXTENDED = 0x00080000, TOKEN_QUERY = 8;
    static readonly IntPtr INVALID = new IntPtr(-1);
    [StructLayout(LayoutKind.Sequential)] struct SecurityCaps { public IntPtr Sid, Caps; public uint Count, Reserved; }
    [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] struct Startup { public int cb; public string reserved, desktop, title; public int x,y,xs,ys,xc,yc,fill,flags; public short show, reserved2; public IntPtr ptr, input, output, error; }
    [StructLayout(LayoutKind.Sequential)] struct StartupEx { public Startup startup; public IntPtr attrs; }
    [StructLayout(LayoutKind.Sequential)] struct ProcInfo { public IntPtr process, thread; public uint pid, tid; }
    [DllImport("userenv.dll", CharSet=CharSet.Unicode)] static extern int CreateAppContainerProfile(string name, string display, string description, IntPtr caps, uint count, out IntPtr sid);
    [DllImport("userenv.dll", CharSet=CharSet.Unicode)] static extern int DeleteAppContainerProfile(string name);
    [DllImport("advapi32.dll")] static extern IntPtr FreeSid(IntPtr sid);
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool InitializeProcThreadAttributeList(IntPtr list,int count,int flags,ref IntPtr size);
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool UpdateProcThreadAttribute(IntPtr list,uint flags,IntPtr attr,IntPtr value,IntPtr size,IntPtr prev,IntPtr ret);
    [DllImport("kernel32.dll")] static extern void DeleteProcThreadAttributeList(IntPtr list);
    [DllImport("kernel32.dll", SetLastError=true,CharSet=CharSet.Unicode)] static extern bool CreateProcessW(string app, string cmd,IntPtr pa,IntPtr ta,bool inherit,uint flags,IntPtr env,string cwd,ref StartupEx si,out ProcInfo pi);
    [DllImport("kernel32.dll",SetLastError=true,CharSet=CharSet.Unicode)] static extern IntPtr CreateNamedPipeW(string name,uint mode,uint pipeMode,uint max,uint outSize,uint inSize,uint timeout,IntPtr sa);
    [DllImport("kernel32.dll",SetLastError=true,CharSet=CharSet.Unicode)] static extern IntPtr CreateFileW(string name,uint access,uint share,IntPtr sa,uint disposition,uint flags,IntPtr template);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
    [DllImport("kernel32.dll")] static extern uint WaitForSingleObject(IntPtr h,uint ms);
    [DllImport("kernel32.dll")] static extern bool GetExitCodeProcess(IntPtr h,out uint code);
    [DllImport("kernel32.dll")] static extern bool TerminateProcess(IntPtr h,uint code);
    [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();
    [DllImport("user32.dll",SetLastError=true,CharSet=CharSet.Unicode)] static extern IntPtr CreateDesktopW(string name,IntPtr device,IntPtr devmode,uint flags,uint access,IntPtr sa);
    [DllImport("user32.dll",SetLastError=true)] static extern bool CloseDesktop(IntPtr desktop);
    [StructLayout(LayoutKind.Sequential)] struct SecurityAttributes { public int length; public IntPtr descriptor; public int inherit; }
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool CreatePipe(out IntPtr read,out IntPtr write,ref SecurityAttributes sa,uint size);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool SetHandleInformation(IntPtr h,uint mask,uint flags);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool PeekNamedPipe(IntPtr h,IntPtr buffer,uint size,IntPtr read,out uint available,IntPtr left);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool ReadFile(IntPtr h,byte[] buffer,uint count,out uint read,IntPtr overlapped);
    [DllImport("advapi32.dll",SetLastError=true)] static extern bool OpenProcessToken(IntPtr process,uint access,out IntPtr token);
    [DllImport("advapi32.dll",SetLastError=true)] static extern bool GetTokenInformation(IntPtr token,int type,out int value,int size,out int returned);
    static void Check(bool ok,string where) { if (!ok) throw new Win32Exception(Marshal.GetLastWin32Error(),where); }
    static int Child(string pipe) {
        Console.WriteLine("stage=managed_main"); Console.Out.Flush();
        IntPtr token; int isAC,n;
        if (!OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,out token)) return 240;
        bool ok=GetTokenInformation(token,29,out isAC,4,out n); CloseHandle(token);
        if (!ok) return 241;
        Console.WriteLine("stage=token token_is_appcontainer="+isAC); Console.Out.Flush();
        IntPtr h=CreateFileW(pipe,0xC0000000,0,IntPtr.Zero,OPEN_EXISTING,0,IntPtr.Zero);
        int err = h==INVALID ? Marshal.GetLastWin32Error() : 0;
        Console.WriteLine("stage=create_file error="+err); Console.Out.Flush();
        if(h!=INVALID) CloseHandle(h);
        // Exit code encodes token and Win32 error; error 0 is success.
        return (isAC != 0 ? 1000 : 0) + Math.Min(err,999);
    }
    static uint Launch(string exe,string pipe,IntPtr sid,bool restricted,string desktop,string role) {
        StartupEx si=new StartupEx(); si.startup.cb=Marshal.SizeOf(typeof(StartupEx)); si.startup.desktop=desktop; IntPtr mem=IntPtr.Zero,capsMem=IntPtr.Zero,read=IntPtr.Zero,write=IntPtr.Zero; ProcInfo pi;
        try {
            SecurityAttributes sa=new SecurityAttributes(); sa.length=Marshal.SizeOf(typeof(SecurityAttributes)); sa.inherit=1;
            Check(CreatePipe(out read,out write,ref sa,0),"CreatePipe"); Check(SetHandleInformation(read,1,0),"SetHandleInformation");
            si.startup.flags=0x100; si.startup.output=write; si.startup.error=write; si.startup.input=IntPtr.Zero;
            if(restricted) {
                IntPtr size=IntPtr.Zero; InitializeProcThreadAttributeList(IntPtr.Zero,1,0,ref size);
                mem=Marshal.AllocHGlobal(size); Check(InitializeProcThreadAttributeList(mem,1,0,ref size),"Initialize attributes"); si.attrs=mem;
                SecurityCaps caps=new SecurityCaps(); caps.Sid=sid; capsMem=Marshal.AllocHGlobal(Marshal.SizeOf(typeof(SecurityCaps))); Marshal.StructureToPtr(caps,capsMem,false);
                Check(UpdateProcThreadAttribute(mem,0,new IntPtr(0x00020009),capsMem,new IntPtr(Marshal.SizeOf(typeof(SecurityCaps))),IntPtr.Zero,IntPtr.Zero),"Update security capabilities");
            }
            Check(CreateProcessW(exe,"\""+exe+"\" "+role+" \""+pipe+"\" x",IntPtr.Zero,IntPtr.Zero,true,(restricted?EXTENDED:0)|0x08000000,IntPtr.Zero,null,ref si,out pi),"CreateProcess");
            CloseHandle(write); write=IntPtr.Zero;
            try { bool ended=false; for(int step=0;step<100;step++) { uint available; if(PeekNamedPipe(read,IntPtr.Zero,0,IntPtr.Zero,out available,IntPtr.Zero) && available>0) { byte[] bytes=new byte[Math.Min(available,4096)]; uint got; if(ReadFile(read,bytes,(uint)bytes.Length,out got,IntPtr.Zero)) Console.Write(System.Text.Encoding.UTF8.GetString(bytes,0,(int)got)); } if(WaitForSingleObject(pi.process,100)==0) { ended=true; uint remain; while(PeekNamedPipe(read,IntPtr.Zero,0,IntPtr.Zero,out remain,IntPtr.Zero) && remain>0) { byte[] bytes=new byte[Math.Min(remain,4096)]; uint got; if(!ReadFile(read,bytes,(uint)bytes.Length,out got,IntPtr.Zero) || got==0) break; Console.Write(System.Text.Encoding.UTF8.GetString(bytes,0,(int)got)); } break; } } if(!ended) { bool terminated=TerminateProcess(pi.process,242); uint waited=WaitForSingleObject(pi.process,5000); Console.WriteLine("role="+role+" terminate="+terminated+" wait_result="+waited); throw new Exception("child timed out"); } uint code; Check(GetExitCodeProcess(pi.process,out code),"GetExitCodeProcess"); return code; }
            finally { CloseHandle(pi.thread); CloseHandle(pi.process); }
        } finally { if(read!=IntPtr.Zero) CloseHandle(read); if(write!=IntPtr.Zero) CloseHandle(write); if(mem!=IntPtr.Zero) { if(si.attrs!=IntPtr.Zero) DeleteProcThreadAttributeList(mem); Marshal.FreeHGlobal(mem); } if(capsMem!=IntPtr.Zero) Marshal.FreeHGlobal(capsMem); }
    }
    static void RunCase(string exe,string pipe,IntPtr serverSid,IntPtr clientSid,bool clientRestricted,string desktop,string label) { uint server=999,client=999; var thread=new System.Threading.Thread(delegate(){ try { server=Launch(exe,pipe,serverSid,true,desktop,"server"); } catch(Exception e) { Console.WriteLine(label+" server_exception="+e.Message); } }); thread.Start(); System.Threading.Thread.Sleep(500); try { client=Launch(exe,pipe,clientSid,clientRestricted,desktop,"client"); } catch(Exception e) { Console.WriteLine(label+" client_exception="+e.Message); } thread.Join(); Console.WriteLine(label+" server_exit="+server+" client_exit="+client); }
    static int Main(string[] args) {
        if(args.Length==2 && args[0]=="child") return Child(args[1]);
        string id=Guid.NewGuid().ToString("N"), profile="CodexProbe"+id, pipe=@"\\.\pipe\CodexSynthetic"+id, desktop="CodexProbeDesktop"+id; IntPtr sid=IntPtr.Zero,h=INVALID,desk=IntPtr.Zero; bool created=false; int exit=1; IntPtr sid2=IntPtr.Zero; bool created2=false; string profile2=profile+"Other";
        Console.WriteLine("profile="+profile); Console.WriteLine("synthetic_pipe="+pipe);
        try {
            desk=CreateDesktopW(desktop,IntPtr.Zero,IntPtr.Zero,0,0x01ff,IntPtr.Zero); Check(desk!=IntPtr.Zero,"CreateDesktop");
            int hr=CreateAppContainerProfile(profile,profile,"Transient synthetic pipe test",IntPtr.Zero,0,out sid); Console.WriteLine("create_profile_hresult=0x"+hr.ToString("X8")); if(hr!=0) return 1; created=true;

            string exe=args.Length==1 ? System.IO.Path.GetFullPath(args[0]) : Process.GetCurrentProcess().MainModule.FileName;
            int hr2=CreateAppContainerProfile(profile2,profile2,"Transient comparison",IntPtr.Zero,0,out sid2); Console.WriteLine("create_second_profile_hresult=0x"+hr2.ToString("X8")); if(hr2!=0) return 1; created2=true;
            RunCase(exe,@"\\.\pipe\LOCAL\CodexSynthetic"+id+"a",sid,sid,true,desktop,"same_sid");
            RunCase(exe,@"\\.\pipe\LOCAL\CodexSynthetic"+id+"b",sid,sid2,true,desktop,"different_sid");
            RunCase(exe,@"\\.\pipe\LOCAL\CodexSynthetic"+id+"c",sid,sid,false,desktop,"full_trust");
            exit=0;
        } catch(Exception e) { Console.WriteLine("exception="+e.GetType().Name+": "+e.Message); }
        finally { if(sid2!=IntPtr.Zero) FreeSid(sid2); if(created2) { int hr2=DeleteAppContainerProfile(profile2); Console.WriteLine("delete_second_profile_hresult=0x"+hr2.ToString("X8")); if(hr2!=0) exit=3; } if(h!=INVALID) CloseHandle(h); if(sid!=IntPtr.Zero) FreeSid(sid); if(created) { int hr=DeleteAppContainerProfile(profile); Console.WriteLine("delete_profile_hresult=0x"+hr.ToString("X8")); if(hr!=0) exit=3; } if(desk!=IntPtr.Zero) Console.WriteLine("close_desktop="+CloseDesktop(desk)); }
        return exit;
    }
}
