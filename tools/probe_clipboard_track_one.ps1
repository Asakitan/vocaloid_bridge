$ErrorActionPreference = 'Stop'
$install='C:\Program Files\VOCALOID6\Editor'; $workspace='E:\VC\vocaloid_bridge'
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class OneProbeDllPaths {
 [DllImport("kernel32", SetLastError=true)] public static extern bool SetDefaultDllDirectories(uint flags);
 [DllImport("kernel32", CharSet=CharSet.Unicode, SetLastError=true)] public static extern IntPtr AddDllDirectory(string path);
}
'@
if (-not [OneProbeDllPaths]::SetDefaultDllDirectories(0xc00) -or [OneProbeDllPaths]::AddDllDirectory($install) -eq [IntPtr]::Zero) { throw 'DLL setup failed' }
[Reflection.Assembly]::LoadFrom((Join-Path $install 'VOCALOID6.dll')) | Out-Null
$asm=[Reflection.Assembly]::LoadFrom((Join-Path $workspace 'native\bin\Release\net8.0-windows\VocaloidBridge.Host.dll'))
$desktop=$asm.GetType('Program',$true).GetMethod('DesktopName',[Reflection.BindingFlags]'Static,NonPublic').Invoke($null,@())
if ($desktop -in @('Default','Winlogon','Disconnect')) { throw 'This probe requires a private Windows desktop.' }
$flags=[Reflection.BindingFlags]'Instance,NonPublic,Public'; $type=$asm.GetType('EngineHost',$true)
$engine=[Activator]::CreateInstance($type,$flags,$null,@($workspace),$null)
$a=[object[]]::new(1); $a[0]=[string](Join-Path $workspace 'output\clipboard_probe_synthetic_20261110.vpr')
$s=$type.GetMethod('Open',$flags).Invoke($engine,$a); $seq=$s.GetType().GetProperty('Sequence',$flags).GetValue($s)
$manager=$type.GetField('manager',$flags).GetValue($engine); $t=$seq.GetTrack(0)
function Ptr($x) { '0x{0:X}' -f ([Yamaha.VOCALOID.VSM.WIVSMTrack]::op_Explicit($x)).ToInt64() }
$clip=$manager.CreateClipboard($seq)
try {
 [Console]::Error.WriteLine('stage: source before PushTrack')
 $source=@{pointer=(Ptr $t); name=$t.Name}
 [Console]::Error.WriteLine('stage: PushTrack return pointer only')
 $p=$clip.PushTrack($t); if ($null -eq $p) { throw 'PushTrack failed' }; $returnPtr=Ptr $p
 [Console]::Error.WriteLine('stage: GetTrack pointer and name')
 $g=$clip.GetTrack(0); $got=@{pointer=(Ptr $g);name=$g.Name}
 [Console]::Error.WriteLine('stage: source after PushTrack')
 $after=@{pointer=(Ptr $t);name=$t.Name}
 @{source=$source;return_pointer=$returnPtr;get=$got;source_after=$after;done=$true} | ConvertTo-Json -Depth 10 -Compress
} finally { $clip.Destroy() | Out-Null; $clip.Dispose(); $engine.Dispose() }
