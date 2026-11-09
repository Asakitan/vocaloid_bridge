param([Parameter(Mandatory=$true)][string]$Fixture)
$ErrorActionPreference = 'Stop'
$install = 'C:\Program Files\VOCALOID6\Editor'; $workspace = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class PitchItemDllPaths {
 [DllImport("kernel32", SetLastError=true)] public static extern bool SetDefaultDllDirectories(uint flags);
 [DllImport("kernel32", CharSet=CharSet.Unicode, SetLastError=true)] public static extern IntPtr AddDllDirectory(string path);
}
'@
if (-not [PitchItemDllPaths]::SetDefaultDllDirectories(0xc00) -or [PitchItemDllPaths]::AddDllDirectory($install) -eq [IntPtr]::Zero) { throw 'DLL setup failed' }
[Reflection.Assembly]::LoadFrom((Join-Path $install 'VOCALOID6.dll')) | Out-Null
$asm = [Reflection.Assembly]::LoadFrom((Join-Path $workspace 'native\bin\Release\net8.0-windows\VocaloidBridge.Host.dll'))
$desktop = $asm.GetType('Program', $true).GetMethod('DesktopName', [Reflection.BindingFlags]'Static,NonPublic').Invoke($null, @())
if ($desktop -in @('Default', 'Winlogon', 'Disconnect')) { throw 'Private desktop required' }
$flags = [Reflection.BindingFlags]'Instance,NonPublic,Public'; $type = $asm.GetType('EngineHost', $true)
$engine = [Activator]::CreateInstance($type, $flags, $null, @($workspace), $null)
function Pointer($o) {
 $p = $o.GetType().GetProperty('CppObjPtr', $flags)
 if ($null -eq $p) { return $null }
 $value=$p.GetValue($o); if ($value -is [IntPtr]) { return ('0x{0:X}' -f $value.ToInt64()) }
 return [string]$value
}
function Snapshot($seq) {
 $track=$seq.GetTrack(0)
 $parts=@(for ($k=0; $k -lt $track.NumParts; $k++) {
  $part=$track.GetPart([ulong]$k)
  $notes=@(for ($i=0; $i -lt $part.NumNotes; $i++) {
   $n=$part.GetNote([ulong]$i)
   $items=@(for ($j=0; $j -lt $n.NumDirectPitches; $j++) {
    $p=$n.DirectPitchData([ulong]$j)
    @{type=$p.GetType().FullName; pointer=(Pointer $p); tick=$p.Tick; value=$p.Value}
   })
   @{pointer=(Pointer $n); pos=$n.RelPosTick.Value; items=$items}
  })
  @{pointer=(Pointer $part); pos=$part.AbsPosTick.Value; notes=$notes}
 })
 return ,$parts
}
try {
 $results=@{}
 foreach ($op in @('duplicate','part_duplicate')) {
  $a=[object[]]::new(1); $a[0]=$Fixture
  $session=$type.GetMethod('Open',$flags).Invoke($engine,$a)
  $seq=$session.GetType().GetProperty('Sequence',$flags).GetValue($session)
  $part=$seq.GetTrack(0).GetPart(0); $note=$part.GetNote(0)
  if ($op -eq 'join') {
   if ($null -eq $part.DivideNote($note,[Yamaha.VOCALOID.VSM.VSMRelTick]::new(480)) -or -not $seq.Commit($true)) { throw 'Join setup failed' }
  }
  $events=[System.Collections.Generic.List[object]]::new(); $phase='setup'
  $observer=[Yamaha.VOCALOID.VSM.WIVSMUpdateObserver]::new()
  $handler=[Yamaha.VOCALOID.VSM.UpdateObserverNotifyEventHandler]{param($e)
   $objects=@($e.Objects | ForEach-Object { @{type=$_.GetType().FullName; pointer=(Pointer $_)} })
   $events.Add(@{phase=$phase; notify=[string]$e.NotifyType; objects=$objects})
  }
  $observer.add_Notified($handler); if (-not $seq.AddUpdateObserver($observer)) { throw 'Observer registration failed' }
  $before=Snapshot $seq; $phase='edit'
  switch ($op) {
   'set' { $ok=$note.SetDirectPitch([Yamaha.VOCALOID.VSM.VSMRelTick]::new(100),[single]-800) }
   'clear' { $ok=$note.ClearDirectPitches([Yamaha.VOCALOID.VSM.VSMRelTick]::new(90),[Yamaha.VOCALOID.VSM.VSMRelTick]::new(110)) }
   'part_duplicate' { $ok=$null -ne $seq.GetTrack(0).DuplicatePart([Yamaha.VOCALOID.VSM.VSMAbsTick]::new(4000),$part) }
   'duplicate' { $ok=$null -ne $part.DuplicateNote([Yamaha.VOCALOID.VSM.VSMRelTick]::new(1200),$note) }
   'split' { $ok=$null -ne $part.DivideNote($note,[Yamaha.VOCALOID.VSM.VSMRelTick]::new(480)) }
   'join' { $selected=[System.Collections.Generic.List[Yamaha.VOCALOID.VSM.WIVSMNote]]::new(); $selected.Add($part.GetNote(0)); $selected.Add($part.GetNote(1)); $ok=$part.JoinNotes($selected) }
  }
  if (-not $ok) { throw "$op failed" }
  $pending=Snapshot $seq; $phase='commit'; if (-not $seq.Commit($true)) { throw "$op commit failed" }
  $after=Snapshot $seq; $phase='undo'; $seq.Undo() | Out-Null; $undo=Snapshot $seq
  $phase='redo'; $seq.Redo() | Out-Null; $redo=Snapshot $seq
  $seq.RemoveUpdateObserver($observer) | Out-Null; $observer.remove_Notified($handler); $observer.Dispose()
  $results[$op]=@{before=$before; pending=$pending; after=$after; undo=$undo; redo=$redo; events=@($events)}
 }
 @{desktop=$desktop; fixture=$Fixture; cases=$results} | ConvertTo-Json -Depth 30 -Compress
} finally { $engine.Dispose() }
