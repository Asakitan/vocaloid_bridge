param([Parameter(Mandatory=$true)][string]$Token, [Parameter(Mandatory=$true)][string]$Revision)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$workspace=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$assembly=[Reflection.Assembly]::LoadFrom((Join-Path $workspace 'native/bin/Release/net8.0-windows/VocaloidBridge.Host.dll'))
$flags=[Reflection.BindingFlags]'Static,NonPublic'
$desktop=$assembly.GetType('Program').GetMethod('DesktopName',$flags).Invoke($null,@())
if ($desktop -in @('Default','Winlogon','Disconnect')) { throw 'Private desktop required' }
$checkpoint=[Action[string]]{
    param($phase)
    [Console]::WriteLine((@{phase=$phase;desktop=$desktop}|ConvertTo-Json -Compress))
    $null=[Console]::ReadLine()
}
$parameters=[object[]]@($workspace,$Token,'restore_original',$Revision,$checkpoint)
$result=$assembly.GetType('MediaPropertyJournal').GetMethod('Resolve',$flags).Invoke($null,$parameters)
[Console]::WriteLine(($result|ConvertTo-Json -Compress))
