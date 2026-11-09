$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
$install = 'C:\Program Files\VOCALOID6\Editor'
[Reflection.Assembly]::LoadFrom((Join-Path $install 'VOCALOID6.dll')) | Out-Null
$assembly = [Reflection.Assembly]::LoadFrom((Join-Path $workspace 'native\bin\Release\net8.0-windows\VocaloidBridge.Host.dll'))
$hostType = $assembly.GetType('EngineHost', $true)
$flags = [Reflection.BindingFlags]'Instance,Static,NonPublic,Public'
$recordType = $hostType.GetNestedType('MidiRecording', $flags)
$handler = $hostType.GetMethod('MidiInputMessage', $flags)
$events = $hostType.GetMethod('MidiInputEventsForCommit', $flags)
$status = $hostType.GetMethod('MidiRecordingStatus', $flags)
if ($null -eq $recordType -or $null -eq $handler -or $null -eq $events -or $null -eq $status) {
    throw 'Built host does not contain the MIDI callback validation methods.'
}
function New-Recording {
    $record = [Activator]::CreateInstance($recordType, $true)
    $recordType.GetField('Active', $flags).SetValue($record, $true)
    return $record
}
function Send-Message($record, [uint32]$message, [uint32]$packed) {
    $args = [object[]]::new(3)
    $args[0] = $record; $args[1] = $message; $args[2] = $packed
    [void]$handler.Invoke($null, $args)
}
function Assert-Rejected($record, [string]$pattern) {
    try {
        $args = [object[]]::new(1); $args[0] = $record
        [void]$events.Invoke($null, $args)
        throw 'Expected callback-state validation to reject the recording.'
    }
    catch {
        $error = $_.Exception
        while ($null -ne $error.InnerException) { $error = $error.InnerException }
        if ($error.Message -notmatch $pattern) { throw }
    }
}
$healthy = New-Recording
Send-Message $healthy 0x3c3 0x005a3c90
Send-Message $healthy 0x3cc 0x00003c80
Send-Message $healthy 0x3c3 0x000140b0
$args = [object[]]::new(1); $args[0] = $healthy
$healthyStatus = $status.Invoke($null, $args)
$healthyEvents = $events.Invoke($null, $args)
if ($healthyStatus.event_count -ne 2 -or $healthyStatus.backlog_notifications -ne 1 -or
    $healthyStatus.ignored_non_note -ne 1 -or $healthyEvents.Length -ne 2) {
    throw 'Valid DATA/MOREDATA or non-note classification was incorrect.'
}
$damaged = New-Recording
Send-Message $damaged 0x3c3 0x005a3c90
Send-Message $damaged 0x3c5 0x00003c90
$recordType.GetField('Active', $flags).SetValue($damaged, $false)
Send-Message $damaged 0x3c6 0
$args[0] = $damaged
$damagedStatus = $status.Invoke($null, $args)
if ($damagedStatus.invalid_input_messages -ne 2 -or $damagedStatus.event_count -ne 1) {
    throw 'Input error notifications were not retained through stop.'
}
Assert-Rejected $damaged '2 invalid message'
$faulted = New-Recording
$recordType.GetField('CallbackFault', $flags).SetValue($faulted, $true)
Assert-Rejected $faulted 'callback failed'
$overflowed = New-Recording
$recordType.GetField('Overflow', $flags).SetValue($overflowed, $true)
Assert-Rejected $overflowed 'capacity exceeded'
$receipt = [ordered]@{
    status = 'passed'; method = 'reflection against built callback code'; opened_midi_device = $false
    healthy = $healthyStatus; errors_during_stop = $damagedStatus
    invalid_input_rejected = $true; callback_fault_rejected = $true; overflow_rejected = $true
}
$name = 'midi-callback-' + [Guid]::NewGuid().ToString('N').Substring(0, 12) + '.json'
$path = Join-Path (Join-Path $workspace 'artifacts') $name
$receipt['receipt'] = $path
$receipt | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $path -Encoding utf8
Write-Output ($receipt | ConvertTo-Json -Depth 10 -Compress)
