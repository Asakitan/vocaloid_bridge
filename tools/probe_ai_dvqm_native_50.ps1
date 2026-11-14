param(
    [Parameter(Mandatory=$true)][string]$Root,
    [Parameter(Mandatory=$true)][string]$Baseline,
    [Parameter(Mandatory=$true)][string]$Conflict,
    [Parameter(Mandatory=$true)][string]$Install,
    [Parameter(Mandatory=$true)][string]$Product,
    [Parameter(Mandatory=$true)][string]$HostPath,
    [Parameter(Mandatory=$true)][int]$DbId,
    [Parameter(Mandatory=$true)][int]$NameId
)
$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$rootPath = (Resolve-Path -LiteralPath $Root).Path
if (-not $rootPath.StartsWith((Join-Path $workspace 'artifacts') + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Owned artifact root required'
}
foreach ($candidate in @($Baseline, $Conflict)) {
    $resolved = (Resolve-Path -LiteralPath $candidate).Path
    if (-not $resolved.StartsWith($rootPath + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Owned artifact input required'
    }
}
$installPath = (Resolve-Path -LiteralPath $Install).Path
$hostPath = (Resolve-Path -LiteralPath $HostPath).Path
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class Dvqm50DllPaths {
 [DllImport("kernel32", SetLastError=true)] public static extern bool SetDefaultDllDirectories(uint flags);
 [DllImport("kernel32", CharSet=CharSet.Unicode, SetLastError=true)] public static extern IntPtr AddDllDirectory(string path);
}
'@
if (-not [Dvqm50DllPaths]::SetDefaultDllDirectories(0xc00) -or
    [Dvqm50DllPaths]::AddDllDirectory($installPath) -eq [IntPtr]::Zero) { throw 'DLL setup failed' }
$core = [Reflection.Assembly]::LoadFrom((Join-Path $installPath ($Product + '.dll')))
if ($core.GetName().Name -ne $Product) { throw 'Native core product mismatch' }
$assembly = [Reflection.Assembly]::LoadFrom($hostPath)
$desktop = $assembly.GetType('Program', $true).GetMethod('DesktopName', [Reflection.BindingFlags]'Static,NonPublic').Invoke($null, @())
if ($desktop -in @('Default', 'Winlogon', 'Disconnect')) { throw 'Private desktop required' }
$flags = [Reflection.BindingFlags]'Instance,NonPublic'
$hostType = $assembly.GetType('EngineHost', $true)
$engine = $hostType.GetConstructor($flags, $null, [Type[]]@([string], [string]), $null).Invoke(@($rootPath, $installPath))
try {
    $null = $hostType.GetMethod('EnsureVoiceServices', $flags).Invoke($engine, @())
    $manager = $hostType.GetProperty('SequenceManager', $flags).GetValue($engine)
    $rate = [Enum]::Parse($core.GetType('Yamaha.VOCALOID.VSM.VSMSamplingRate', $true), '_44100')
    $settings = $hostType.GetMethod('SequenceSettings', [Reflection.BindingFlags]'Static,NonPublic').Invoke($null, @($rate))
    function ReadNoteState($sequence) {
        $track = $sequence.GetTrack([ulong]0)
        $part = $track.GetPart([ulong]0)
        $note = $part.GetNote([ulong]0)
        $dvqm = $note.GetDvqm($true)
        $voiceId = if ($Product -eq 'VOCALOID7') { $track.VoiceBankID } else { $part.AiVoiceBankID }
        return [ordered]@{
            voice_id = $voiceId
            note_is_ai = $note.IsAi
            duration_tick = $note.HmmWeightDuration
            pre_weight = $note.PreHmmWeight
            post_weight = $note.PostHmmWeight
            attack_empty = $dvqm.IsEmpty
            attack_db_id = $dvqm.DBID
            attack_name_id = $dvqm.NameID
        }
    }
    function InspectFixture([string]$path, [string]$label) {
        $extracted = Join-Path $rootPath $label
        [IO.Compression.ZipFile]::ExtractToDirectory($path, $extracted)
        $jsonPath = Join-Path $extracted 'Project\sequence.json'
        $sequence = $manager.OpenSequence($jsonPath, $installPath, $settings)
        if ($null -eq $sequence) { throw "Native $label open failed: $($manager.LastError)" }
        try {
            $state = ReadNoteState $sequence
            $destination = Join-Path $rootPath ($label + '-saved')
            [IO.Directory]::CreateDirectory($destination) | Out-Null
            if (-not $sequence.Save($destination, $false)) { throw "Native $label save failed: $($sequence.LastError)" }
            $saved = Get-Content -Raw -LiteralPath (Join-Path $destination 'Project\sequence.json') | ConvertFrom-Json -Depth 100
            $savedNote = $saved.tracks[0].parts[0].notes[0]
            return @{ state = $state; saved_singing_skill = $savedNote.singingSkill; saved_dvqm = $savedNote.dvqm }
        } finally {
            if (-not $sequence.Close()) { throw "Native $label close failed: $($sequence.LastError)" }
        }
    }
    function ProbeSetterOrder([string]$label, [bool]$dvqmFirst) {
        $source = Join-Path $rootPath 'baseline\Project\sequence.json'
        $sequence = $manager.OpenSequence($source, $installPath, $settings)
        if ($null -eq $sequence) { throw "Native $label open failed: $($manager.LastError)" }
        try {
            $before = ReadNoteState $sequence
            $note = $sequence.GetTrack([ulong]0).GetPart([ulong]0).GetNote([ulong]0)
            $duration = [Activator]::CreateInstance($core.GetType('Yamaha.VOCALOID.VSM.VSMRelTick', $true), [object[]]@([long]73))
            if ($dvqmFirst) { $dvqmResult = $note.GetDvqm($true).Set($DbId, $NameId, $true) }
            $weightResult = $note.SetHmmWeight(37, 91)
            $durationResult = $note.SetHmmWeightDuration($duration)
            if (-not $dvqmFirst) { $dvqmResult = $note.GetDvqm($true).Set($DbId, $NameId, $true) }
            $staged = $sequence.IsStaged
            $commit = if ($staged) { $sequence.Commit($true) } else { $null }
            $after = ReadNoteState $sequence
            $undoResult = $sequence.Undo()
            $undo = ReadNoteState $sequence
            $redoResult = $sequence.Redo()
            $redo = ReadNoteState $sequence
            $destination = Join-Path $rootPath ($label + '-saved')
            [IO.Directory]::CreateDirectory($destination) | Out-Null
            if (-not $sequence.Save($destination, $false)) { throw "Native $label save failed: $($sequence.LastError)" }
            $saved = Get-Content -Raw -LiteralPath (Join-Path $destination 'Project\sequence.json') | ConvertFrom-Json -Depth 100
            $savedNote = $saved.tracks[0].parts[0].notes[0]
            $reopened = $manager.OpenSequence((Join-Path $destination 'Project\sequence.json'), $installPath, $settings)
            if ($null -eq $reopened) { throw "Native $label reopen failed: $($manager.LastError)" }
            try { $reopenedState = ReadNoteState $reopened }
            finally { if (-not $reopened.Close()) { throw "Native $label reopen close failed" } }
            return @{ before = $before; dvqm_result = $dvqmResult; weight_result = $weightResult;
                      duration_result = $durationResult; staged = $staged; commit = $commit; after = $after;
                      undo_result = $undoResult; undo = $undo; redo_result = $redoResult; redo = $redo;
                      saved_singing_skill = $savedNote.singingSkill; saved_dvqm = $savedNote.dvqm; reopened = $reopenedState }
        } finally {
            if (-not $sequence.Close()) { throw "Native $label close failed: $($sequence.LastError)" }
        }
    }
    $baselineResult = InspectFixture $Baseline 'baseline'
    $conflictResult = InspectFixture $Conflict 'conflict'
    $dvqmFirst = ProbeSetterOrder 'dvqm-then-hmm' $true
    $hmmFirst = ProbeSetterOrder 'hmm-then-dvqm' $false
    @{ product = $Product; core_assembly = $core.GetName().Name; desktop = $desktop; host_path = $hostPath;
       baseline = $baselineResult; conflict = $conflictResult; dvqm_then_hmm = $dvqmFirst;
       hmm_then_dvqm = $hmmFirst } | ConvertTo-Json -Depth 100 -Compress
} finally { $engine.Dispose() }