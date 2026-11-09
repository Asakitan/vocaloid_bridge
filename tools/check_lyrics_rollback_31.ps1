param([Parameter(Mandatory=$true)][string]$Root, [Parameter(Mandatory=$true)][string]$Source)
$ErrorActionPreference='Stop'
$workspace=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$rootPath=(Resolve-Path $Root).Path
if (-not $rootPath.StartsWith((Join-Path $workspace 'artifacts')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Owned artifact root required' }
$install='C:\Program Files\VOCALOID6\Editor'
Add-Type @'
using System; using System.Runtime.InteropServices;
public static class Lyric31DllPaths {
 [DllImport("kernel32",SetLastError=true)] public static extern bool SetDefaultDllDirectories(uint flags);
 [DllImport("kernel32",CharSet=CharSet.Unicode,SetLastError=true)] public static extern IntPtr AddDllDirectory(string path);
}
'@
if (-not [Lyric31DllPaths]::SetDefaultDllDirectories(0xc00) -or [Lyric31DllPaths]::AddDllDirectory($install) -eq [IntPtr]::Zero) { throw 'DLL setup failed' }
[Reflection.Assembly]::LoadFrom((Join-Path $install 'VOCALOID6.dll')) | Out-Null
$assembly=[Reflection.Assembly]::LoadFrom((Join-Path $workspace 'native/bin/Release/net8.0-windows/VocaloidBridge.Host.dll'))
$desktop=$assembly.GetType('Program').GetMethod('DesktopName',[Reflection.BindingFlags]'Static,NonPublic').Invoke($null,@())
if ($desktop -in @('Default','Winlogon','Disconnect')) { throw 'Private desktop required' }
$flags=[Reflection.BindingFlags]'Instance,NonPublic'
$hostType=$assembly.GetType('EngineHost',$true)
$engine=$hostType.GetConstructor($flags,$null,[Type[]]@([string]),$null).Invoke(@($rootPath))
function InvokeEngine([string]$name,[object[]]$arguments) { $hostType.GetMethod($name,$flags).Invoke($engine,$arguments) }
function Options([string]$json) { $doc=[System.Text.Json.JsonDocument]::Parse($json); try {$doc.RootElement.Clone()} finally {$doc.Dispose()} }
function ReadState {
    [ordered]@{notes=(InvokeEngine 'EditScore' @($script:id,'note.list',(Options '{"track_index":0,"part_index":0}')));
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
    @{staged_change_observed=$stagedSeen; lyric_change_observed=$changedSeen; restored=($before -eq $after); desktop=$desktop} | ConvertTo-Json -Compress
} finally { $engine.Dispose() }
