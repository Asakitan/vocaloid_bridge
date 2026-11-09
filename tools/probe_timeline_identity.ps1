param([Parameter(Mandatory=$true)][string]$Fixture)
$ErrorActionPreference = 'Stop'
$install = 'C:\Program Files\VOCALOID6\Editor'; $workspace = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class TimelineProbeDllPaths {
 [DllImport("kernel32", SetLastError=true)] public static extern bool SetDefaultDllDirectories(uint flags);
 [DllImport("kernel32", CharSet=CharSet.Unicode, SetLastError=true)] public static extern IntPtr AddDllDirectory(string path);
}
"@
if (-not [TimelineProbeDllPaths]::SetDefaultDllDirectories(0xc00) -or [TimelineProbeDllPaths]::AddDllDirectory($install) -eq [IntPtr]::Zero) { throw 'DLL setup failed' }
[Reflection.Assembly]::LoadFrom((Join-Path $install 'VOCALOID6.dll')) | Out-Null
$asm = [Reflection.Assembly]::LoadFrom((Join-Path $workspace 'native\bin\Release\net8.0-windows\VocaloidBridge.Host.dll'))
$desktop = $asm.GetType('Program', $true).GetMethod('DesktopName', [Reflection.BindingFlags]'Static,NonPublic').Invoke($null, @())
if ($desktop -in @('Default', 'Winlogon', 'Disconnect')) { throw 'This probe requires a private Windows desktop.' }
$flags = [Reflection.BindingFlags]'Instance,NonPublic,Public'; $type = $asm.GetType('EngineHost', $true)
$engine = [Activator]::CreateInstance($type, $flags, $null, @($workspace), $null)
function Pointer($o) {
 $p = $o.GetType().GetProperty('CppObjPtr', $flags)
 if ($null -eq $p) { throw ('Missing pointer on ' + $o.GetType().FullName) }
 return ('0x{0:X}' -f $p.GetValue($o).ToInt64())
}
function Snapshot($sequence) {
 $tempos = @($sequence.Tempos | ForEach-Object { @{ ptr=(Pointer $_); tick=$_.RelPosTick.Value; value=$_.Value } })
 $meters = @($sequence.TimeSigs | ForEach-Object { @{ ptr=(Pointer $_); bar=$_.PosBar; numer=$_.Value.Numer; denom=$_.Value.Denom } })
 $track = $sequence.GetTrack(0); $part = $track.GetPart(0)
 $notes = @(for ($i=0; $i -lt $part.NumNotes; $i++) { $n=$part.GetNote([ulong]$i); @{ptr=(Pointer $n); tick=$n.RelPosTick.Value; number=$n.NoteNumber} })
 $kind=[Yamaha.VOCALOID.VSM.VSMControllerType]::Dynamics
 $controllers = @(for ($i=0; $i -lt $part.GetNumController($kind); $i++) { $c=$part.GetController($kind,[ulong]$i); @{ptr=(Pointer $c); tick=$c.RelPosTick.Value; value=$c.Value} })
 return @{tempos=$tempos; meters=$meters; part=@{ptr=(Pointer $part); tick=$part.AbsPosTick.Value}; notes=$notes; controllers=$controllers}
}
try {
 $result=@{}
 foreach ($include in @($false,$true)) { foreach ($op in @('insert','delete')) {
  $a=[object[]]::new(1); $a[0]=$Fixture
  $session=$type.GetMethod('Open',$flags).Invoke($engine,$a)
  $seq=$session.GetType().GetProperty('Sequence',$flags).GetValue($session)
  $before=Snapshot $seq
  $range=[Yamaha.VOCALOID.VSM.VSMTickRange]::new(1000,1500)
  $ok=if ($op -eq 'insert') {[Yamaha.VOCALOID.WIVSMSequenceExtension]::InsertSilence($seq,$range,$include)} else {[Yamaha.VOCALOID.WIVSMSequenceExtension]::DeleteTime($seq,$range,$include)}
  if (-not $ok) { throw "Native $op failed" }
  $pending=Snapshot $seq
  if (-not $seq.Rollback()) { throw 'Rollback failed' }
  $rolled=Snapshot $seq
  $ok=if ($op -eq 'insert') {[Yamaha.VOCALOID.WIVSMSequenceExtension]::InsertSilence($seq,$range,$include)} else {[Yamaha.VOCALOID.WIVSMSequenceExtension]::DeleteTime($seq,$range,$include)}
  if (-not $ok -or -not $seq.Commit($true)) { throw 'Second edit or commit failed' }
  $committed=Snapshot $seq; $seq.Undo(); $undo=Snapshot $seq; $seq.Redo(); $redo=Snapshot $seq
  $result["${op}_${include}"]=@{before=$before; pending=$pending; rollback=$rolled; committed=$committed; undo=$undo; redo=$redo}
 }}
 $result | ConvertTo-Json -Depth 20 -Compress
} finally { $engine.Dispose() }
