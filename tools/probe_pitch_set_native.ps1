param([Parameter(Mandatory=$true)][string]$Fixture)
$ErrorActionPreference = 'Stop'
$install = 'C:\Program Files\VOCALOID6\Editor'; $workspace = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class PitchProbeDllPaths {
 [DllImport("kernel32", SetLastError=true)] public static extern bool SetDefaultDllDirectories(uint flags);
 [DllImport("kernel32", CharSet=CharSet.Unicode, SetLastError=true)] public static extern IntPtr AddDllDirectory(string path);
}
'@
if (-not [PitchProbeDllPaths]::SetDefaultDllDirectories(0xc00) -or [PitchProbeDllPaths]::AddDllDirectory($install) -eq [IntPtr]::Zero) { throw 'DLL setup failed' }
[Reflection.Assembly]::LoadFrom((Join-Path $install 'VOCALOID6.dll')) | Out-Null
$asm = [Reflection.Assembly]::LoadFrom((Join-Path $workspace 'native\bin\Release\net8.0-windows\VocaloidBridge.Host.dll'))
$desktop = $asm.GetType('Program', $true).GetMethod('DesktopName', [Reflection.BindingFlags]'Static,NonPublic').Invoke($null, @())
if ($desktop -in @('Default', 'Winlogon', 'Disconnect')) { throw 'Private Windows desktop required' }
$flags = [Reflection.BindingFlags]'Instance,NonPublic,Public'; $type = $asm.GetType('EngineHost', $true)
$engine = [Activator]::CreateInstance($type, $flags, $null, @($workspace), $null)
function Points($seq) {
 $note=$seq.GetTrack(0).GetPart(0).GetNote(0)
 $result=@(); for ($i=0; $i -lt $note.NumDirectPitches; $i++) { $p=$note.DirectPitchData([ulong]$i); $result+=@{pos=$p.Tick; value=$p.Value} }
 return ,$result
}

$cases=@(@{name='replace';replace=$true;points=@(@{tick=0;value=60},@{tick=959;value=61})},@{name='merge';replace=$false;points=@(@{tick=100;value=65})},@{name='rollback_injected';replace=$false;fail=$true;points=@(@{tick=100;value=62})})
$result=@(); try { foreach ($case in $cases) {
 $a=[object[]]::new(1); $a[0]=[string]$Fixture; $session=$type.GetMethod('Open',$flags).Invoke($engine,$a); $seq=$session.GetType().GetProperty('Sequence',$flags).GetValue($session); $note=$seq.GetTrack(0).GetPart(0).GetNote(0); $before=Points $seq; $steps=@(); $err=$null
 try { if ($case.replace) { $ok=$note.ClearDirectPitches([Yamaha.VOCALOID.VSM.WIVSMNote]::DirectPitchClearingBeginTick,[Yamaha.VOCALOID.VSM.WIVSMNote]::DirectPitchClearingEndTick); $steps+=@{clear=$ok;points=(Points $seq)} }
 foreach ($pt in $case.points) { $val=[Yamaha.VOCALOID.VSM.VSMScore]::GetPitchFromRawNoteNumber([float]$pt.value); $ok=$note.SetDirectPitch([Yamaha.VOCALOID.VSM.VSMRelTick]::new($pt.tick),$val); $steps+=@{tick=$pt.tick;returned=$ok;points=(Points $seq)}; if (-not $ok) {throw 'set returned false'}; if ($case.fail) {throw 'injected staged validation error'} } } catch {$err=$_.Exception.Message}
 $pending=Points $seq; $staged=$seq.IsStaged; if ($staged) {$finish=if ($err) {$seq.Rollback()} else {$seq.Commit($true)}} else {$finish=$null}; $after=Points $seq; $u=$seq.Undo(); $undo=Points $seq; $r=$seq.Redo(); $redo=Points $seq
 $id=$session.GetType().GetProperty('Id',$flags).GetValue($session); $name='pitch-set-probe-'+[guid]::NewGuid().ToString('N')+'.vpr'; $saved=$type.GetMethod('Save',$flags).Invoke($engine,@([string]$id,[string]$name,$false)); $b=[object[]]::new(1); $b[0]=[string]$saved.path; $opened=$type.GetMethod('Open',$flags).Invoke($engine,$b); $reopened=Points ($opened.GetType().GetProperty('Sequence',$flags).GetValue($opened));
 $result+=@{saved=$saved.path;reopen=$reopened;case=$case.name;before=$before;steps=$steps;error=$err;pending=$pending;staged=$staged;finish=$finish;after=$after;undo_result=$u;undo=$undo;redo_result=$r;redo=$redo}
 }; @{desktop=$desktop;cases=$result} | ConvertTo-Json -Depth 20 -Compress } finally {$engine.Dispose()}
