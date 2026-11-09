$ErrorActionPreference = 'Stop'
$install = 'C:\Program Files\VOCALOID6\Editor'; $workspace = 'E:\VC\vocaloid_bridge'
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class DirectProbeDllPaths {
 [DllImport("kernel32", SetLastError=true)] public static extern bool SetDefaultDllDirectories(uint flags);
 [DllImport("kernel32", CharSet=CharSet.Unicode, SetLastError=true)] public static extern IntPtr AddDllDirectory(string path);
}
'@
if (-not [DirectProbeDllPaths]::SetDefaultDllDirectories(0xc00) -or [DirectProbeDllPaths]::AddDllDirectory($install) -eq [IntPtr]::Zero) { throw 'DLL setup failed' }
[Reflection.Assembly]::LoadFrom((Join-Path $install 'VOCALOID6.dll')) | Out-Null
$asm = [Reflection.Assembly]::LoadFrom((Join-Path $workspace 'native\bin\Release\net8.0-windows\VocaloidBridge.Host.dll'))
$desktop = $asm.GetType('Program', $true).GetMethod('DesktopName', [Reflection.BindingFlags]'Static,NonPublic').Invoke($null, @())
if ($desktop -in @('Default', 'Winlogon', 'Disconnect')) { throw 'This probe requires a private Windows desktop.' }
$flags = [Reflection.BindingFlags]'Instance,NonPublic,Public'; $type = $asm.GetType('EngineHost', $true)
$engine = [Activator]::CreateInstance($type, $flags, $null, @($workspace), $null)
$a = [object[]]::new(1); $a[0] = [string](Join-Path $workspace 'output\clipboard_probe_synthetic_20261110.vpr')
$src=$type.GetMethod('Open',$flags).Invoke($engine,$a); $dst=$type.GetMethod('Open',$flags).Invoke($engine,$a)
$ss=$src.GetType().GetProperty('Sequence',$flags).GetValue($src); $ds=$dst.GetType().GetProperty('Sequence',$flags).GetValue($dst)
$st=$ss.GetTrack(0); $sp=$st.GetPart(0); $sn=$sp.GetNote(0); $dt=$ds.GetTrack(0); $dp=$dt.GetPart(1)
$out=@{}
try {
 [Console]::Error.WriteLine('stage: direct note')
 $newNote=$dp.DuplicateNote([Yamaha.VOCALOID.VSM.VSMRelTick]::new(1100),$sn)
 if ($null -eq $newNote) { throw 'direct note duplicate failed' }
 $out.note=@{source_pointer=('0x{0:X}' -f $sn.CppObjPtr.ToInt64()); target_pointer=('0x{0:X}' -f $newNote.CppObjPtr.ToInt64()); position=$newNote.RelPosTick.Value; lyric=$newNote.Lyric; number=$newNote.NoteNumber}
 if (-not $ds.Commit($true)) { throw 'note commit failed' }
 [Console]::Error.WriteLine('stage: direct part')
 $newPart=$dt.DuplicatePart([Yamaha.VOCALOID.VSM.VSMAbsTick]::new(10000),$sp)
 if ($null -eq $newPart) { throw 'direct part duplicate failed' }
 $out.part=@{source_pointer=('0x{0:X}' -f ([Yamaha.VOCALOID.VSM.WIVSMPart]::op_Explicit($sp)).ToInt64()); target_pointer=('0x{0:X}' -f ([Yamaha.VOCALOID.VSM.WIVSMPart]::op_Explicit($newPart)).ToInt64()); position=$newPart.AbsPosTick.Value; name=$newPart.Name; note_count=$newPart.NumNotes}
 if (-not $ds.Commit($true)) { throw 'part commit failed' }
 [Console]::Error.WriteLine('stage: direct track')
 $errorMessage=''; $newTrack=$ds.DuplicateTrack($ds.NumTrack,$st,[ref]$errorMessage)
 if ($null -eq $newTrack) { throw "direct track duplicate failed: $errorMessage" }
 $out.track=@{source_pointer=('0x{0:X}' -f ([Yamaha.VOCALOID.VSM.WIVSMTrack]::op_Explicit($st)).ToInt64()); target_pointer=('0x{0:X}' -f ([Yamaha.VOCALOID.VSM.WIVSMTrack]::op_Explicit($newTrack)).ToInt64()); name=$newTrack.Name; part_count=$newTrack.NumParts}
 if (-not $ds.Commit($true)) { throw 'track commit failed' }
 $out.done=$true; $out | ConvertTo-Json -Depth 10 -Compress
} finally { $engine.Dispose() }
