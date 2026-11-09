param([Parameter(Mandatory=$true)][string]$ClipId, [Parameter(Mandatory=$true)][string]$Candidate,
      [Parameter(Mandatory=$true)][ValidateSet('prepared','detached','published','committed')][string]$PauseAt)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
[Console]::InputEncoding=[Text.UTF8Encoding]::new($false)
$workspace=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if ($ClipId -notmatch '^[0-9a-f-]{36}$') { throw 'Invalid synthetic clip ID' }
$inputPath=(Resolve-Path $Candidate).Path
if (-not $inputPath.StartsWith((Join-Path $workspace 'artifacts')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Candidate must be a test artifact' }
$property=Join-Path $workspace ".runtime/library/media/$ClipId/property.json"
if ((Get-Content -Raw -Encoding UTF8 $property | ConvertFrom-Json).name -notlike 'Recovery32-*') { throw 'Synthetic recovery fixture required' }
$assembly=[Reflection.Assembly]::LoadFrom((Join-Path $workspace 'native/bin/Release/net8.0-windows/VocaloidBridge.Host.dll'))
$flags=[Reflection.BindingFlags]'Instance,NonPublic'
$desktop=$assembly.GetType('Program').GetMethod('DesktopName',[Reflection.BindingFlags]'Static,NonPublic').Invoke($null,@())
if ($desktop -in @('Default','Winlogon','Disconnect')) { throw 'Private desktop required' }
$type=$assembly.GetType('MediaPropertyJournal',$true)
$stage=Join-Path $workspace ('.runtime/media-property/'+[guid]::NewGuid().ToString('N'))
$null=New-Item -ItemType Directory -Path $stage
$transaction=$null
try {
    $arguments=[string[]]@($workspace,$ClipId,$stage)
    $transaction=$type.GetConstructor($flags,$null,[Type[]]@([string],[string],[string]),$null).Invoke($arguments)
    $type.GetProperty('Checkpoint',$flags).SetValue($transaction,[Action[string]]{
        param($phase)
        if ($phase -eq $PauseAt) {
            [Console]::WriteLine((@{phase=$phase;stage=$stage;desktop=$desktop}|ConvertTo-Json -Compress))
            if ([Console]::ReadLine() -eq 'fail') { throw 'injected publication failure' }
        }
    })
    $parameters=[object[]]::new(1)
    $parameters[0]=[IO.File]::ReadAllBytes($inputPath)
    $null=$type.GetMethod('Publish',$flags).Invoke($transaction,$parameters)
    $null=$type.GetMethod('Complete',$flags).Invoke($transaction,@())
    [Console]::WriteLine((@{ok=$true;stage=$stage}|ConvertTo-Json -Compress))
} catch {
    $failure=$_.ToString(); $pending=$false
    if ($null -ne $transaction) {
        try { $null=$type.GetMethod('Rollback',$flags).Invoke($transaction,@()) }
        catch { $pending=$true; $failure+='; '+$_.ToString() }
    }
    [Console]::WriteLine((@{ok=$false;recovery_pending=$pending;error=$failure;stage=$stage}|ConvertTo-Json -Compress))
} finally {
    if ($null -ne $transaction) { $transaction.Dispose() }
    elseif ((Test-Path -LiteralPath $stage) -and @(Get-ChildItem -LiteralPath $stage -Force).Count -eq 0) { [IO.Directory]::Delete($stage) }
}
