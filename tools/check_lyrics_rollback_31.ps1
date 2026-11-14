param([Parameter(Mandatory=$true)][string]$Root, [Parameter(Mandatory=$true)][string]$Source,
    [Parameter(Mandatory=$true)][string]$Install, [Parameter(Mandatory=$true)][string]$Product,
    [Parameter(Mandatory=$true)][string]$HostPath)
$ErrorActionPreference='Stop'
$workspace=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$rootPath=(Resolve-Path $Root).Path
if (-not $rootPath.StartsWith((Join-Path $workspace 'artifacts')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Owned artifact root required' }
$install=(Resolve-Path -LiteralPath $Install).Path
$hostPath=(Resolve-Path -LiteralPath $HostPath).Path
Add-Type @'
using System; using System.Runtime.InteropServices;
public static class Lyric31DllPaths {
 [DllImport("kernel32",SetLastError=true)] public static extern bool SetDefaultDllDirectories(uint flags);
 [DllImport("kernel32",CharSet=CharSet.Unicode,SetLastError=true)] public static extern IntPtr AddDllDirectory(string path);
}
'@
if (-not [Lyric31DllPaths]::SetDefaultDllDirectories(0xc00) -or [Lyric31DllPaths]::AddDllDirectory($install) -eq [IntPtr]::Zero) { throw 'DLL setup failed' }
$core=[Reflection.Assembly]::LoadFrom((Join-Path $install ($Product+'.dll')))
if ($core.GetName().Name -ne $Product) { throw 'Native core product mismatch' }
$assembly=[Reflection.Assembly]::LoadFrom($hostPath)
$desktop=$assembly.GetType('Program').GetMethod('DesktopName',[Reflection.BindingFlags]'Static,NonPublic').Invoke($null,@())
if ($desktop -in @('Default','Winlogon','Disconnect')) { throw 'Private desktop required' }
$flags=[Reflection.BindingFlags]'Instance,NonPublic'
$hostType=$assembly.GetType('EngineHost',$true)
$engine=$hostType.GetConstructor($flags,$null,[Type[]]@([string],[string]),$null).Invoke(@($rootPath,$install))
function InvokeEngine([string]$name,[object[]]$arguments) { $hostType.GetMethod($name,$flags).Invoke($engine,$arguments) }
function Options([string]$json) { $doc=[System.Text.Json.JsonDocument]::Parse($json); try {$doc.RootElement.Clone()} finally {$doc.Dispose()} }
function ReadState {
    [ordered]@{notes=(InvokeEngine 'EditScore' @($script:id,'note.list',(Options '{"track_index":0,"part_index":0}')));
        tracks=(InvokeEngine 'EditScore' @($script:id,'track.list',(Options '{}')));
        history=(InvokeEngine 'EditScore' @($script:id,'history.status',(Options '{}')));
        dirty=$script:session.GetType().GetProperty('Dirty',$flags).GetValue($script:session)} | ConvertTo-Json -Depth 100 -Compress
}
try {
    $script:session=InvokeEngine 'Open' @((Resolve-Path $Source).Path)
    $script:id=$session.GetType().GetProperty('Id',$flags).GetValue($session)
    $null=InvokeEngine 'EditScore' @($id,'note.update',(Options '{"track_index":0,"part_index":0,"note_index":0,"velocity":73}'))
    $null=InvokeEngine 'Save' @($id,'before-failure.vpr',$false)
    $before=ReadState
    $sequence=$session.GetType().GetProperty('Sequence',$flags).GetValue($session)
    $property=$session.GetType().GetProperty('ArchiveValidate',$flags)
    $original=$property.GetValue($session)
    $script:stagedSeen=$false; $script:changedSeen=$false
    $property.SetValue($session,[Action]{
        $script:stagedSeen=$sequence.IsStaged
        $script:changedSeen=($sequence.GetTrack([ulong]0).GetPart([ulong]0).GetNote([ulong]0).Lyric -eq 'い')
        throw 'injected lyric transaction validation failure'
    })
    try {
        $null=InvokeEngine 'LibraryOperation' @($id,'lyrics_apply',(Options '{"track_index":0,"part_index":0,"note_index":0,"language_id":0,"lyrics":"い"}'))
        throw 'Injected transaction unexpectedly succeeded'
    } catch {
        if ($_.ToString() -notmatch 'injected lyric transaction validation failure') { throw }
    } finally { $property.SetValue($session,$original) }
    $after=ReadState
    if (-not $stagedSeen -or -not $changedSeen -or $before -ne $after) { throw 'Rollback did not restore notes, dirty state and prior history' }
    $trackBefore=ReadState
    $initialTrack=(InvokeEngine 'EditScore' @($script:id,'track.list',(Options '{}'))).result.tracks[0]
    if ($initialTrack.mute -or $initialTrack.midi_recording -or
        $(if ($Product -eq 'VOCALOID7') { $initialTrack.solo_state -ne 'Off' } else { $initialTrack.solo })) {
        throw 'Track rollback fixture must start with mute, solo and recording disabled'
    }
    $script:trackChangedSeen=$false
    $property.SetValue($session,[Action]{
        $snapshot=InvokeEngine 'EditScore' @($script:id,'track.list',(Options '{}'))
        $track=$snapshot.result.tracks[0]
        $script:trackChangedSeen=$track.mute -and $track.midi_recording -and
            $(if ($Product -eq 'VOCALOID7') { $track.solo_state -eq 'Defeat' } else { $track.solo })
        throw 'injected track transaction validation failure'
    })
    try {
        $trackOptions=if ($Product -eq 'VOCALOID7') {
            '{"track_index":0,"mute":true,"solo_state":"Defeat","midi_recording":true}'
        } else {
            '{"track_index":0,"mute":true,"solo":true,"midi_recording":true}'
        }
        $null=InvokeEngine 'EditScore' @($id,'track.update',(Options $trackOptions))
        throw 'Injected track transaction unexpectedly succeeded'
    } catch {
        if ($_.ToString() -notmatch 'injected track transaction validation failure') { throw }
    } finally { $property.SetValue($session,$original) }
    $trackAfter=ReadState
    if (-not $trackChangedSeen -or $trackBefore -ne $trackAfter) { throw 'Track rollback did not restore state and history' }
        @{staged_change_observed=$stagedSeen; lyric_change_observed=$changedSeen; restored=($before -eq $after);
      track_change_observed=$trackChangedSeen; track_restored=($trackBefore -eq $trackAfter);
      desktop=$desktop; product=$Product; core_assembly=$core.GetName().Name; host_path=$hostPath} | ConvertTo-Json -Compress
} finally { $engine.Dispose() }
