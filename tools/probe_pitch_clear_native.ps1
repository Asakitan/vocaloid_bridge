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
$cases=@(@{name='exact';begin=100;end=400},@{name='interior';begin=90;end=399},@{name='single';begin=100;end=100},@{name='edge_before';begin=99;end=100},@{name='edge_after';begin=400;end=401},@{name='all';all=$true})
$result=@(); try {
 foreach ($case in $cases) {
  $args1=[object[]]::new(1); $args1[0]=[string]$Fixture
  $session=$type.GetMethod('Open',$flags).Invoke($engine,$args1)
  $seq=$session.GetType().GetProperty('Sequence',$flags).GetValue($session)
  $note=$seq.GetTrack(0).GetPart(0).GetNote(0)
  $before=Points $seq
  if ($case.all) { $begin=[Yamaha.VOCALOID.VSM.WIVSMNote]::DirectPitchClearingBeginTick; $end=[Yamaha.VOCALOID.VSM.WIVSMNote]::DirectPitchClearingEndTick }
  else { $begin=[Yamaha.VOCALOID.VSM.VSMRelTick]::new($case.begin); $end=[Yamaha.VOCALOID.VSM.VSMRelTick]::new($case.end) }
  $ok=$note.ClearDirectPitches($begin,$end); $precommit=Points $seq; $committed=$seq.Commit($true); $after=Points $seq
  $seq.Undo(); $undo=Points $seq; $seq.Redo(); $redo=Points $seq
  $id=$session.GetType().GetProperty('Id',$flags).GetValue($session)
  $name='pitch-clear-native-'+$case.name+'-'+[guid]::NewGuid().ToString('N')+'.vpr'
  $saved=$type.GetMethod('Save',$flags).Invoke($engine,@([string]$id,[string]$name,$false))
  $result+=@{case=$case.name;begin=$case.begin;end=$case.end;before=$before;returned=$ok;precommit=$precommit;commit=$committed;after=$after;undo=$undo;redo=$redo;save=$saved}
 }
 @{desktop=$desktop;fixture=$Fixture;cases=$result} | ConvertTo-Json -Depth 20 -Compress
} finally { $engine.Dispose() }
