$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$artifact = Join-Path $root 'artifacts'
$hostDll = Join-Path $root 'native\bin\Release\net8.0-windows\VocaloidBridge.Host.dll'
$assembly = [Reflection.Assembly]::LoadFrom($hostDll)
$method = $assembly.GetType('EngineHost', $true).GetMethod('ValidateArchiveExport', [Reflection.BindingFlags]'Static,NonPublic')
if (-not $method) { throw 'Archive export validator not found' }
$run = [Guid]::NewGuid().ToString('N').Substring(0, 12)

function New-ProbeArchive([string] $suffix, [System.Collections.IDictionary] $entries) {
    $path = Join-Path $artifact "archive-export-$run-$suffix.zip"
    $stream = [IO.File]::Open($path, [IO.FileMode]::CreateNew)
    try {
        $archive = [IO.Compression.ZipArchive]::new($stream, [IO.Compression.ZipArchiveMode]::Create, $true)
        try {
            foreach ($name in $entries.Keys) {
                $entry = $archive.CreateEntry($name)
                $output = $entry.Open()
                try {
                    $bytes = [Text.Encoding]::UTF8.GetBytes([string]$entries[$name])
                    $output.Write($bytes, 0, $bytes.Length)
                } finally { $output.Dispose() }
            }
        } finally { $archive.Dispose() }
    } finally { $stream.Dispose() }
    return $path
}

function Test-Rejection([string] $path, [int] $entries, [long] $bytes, [string] $expected) {
    try { $method.Invoke($null, @([string]$path, [string]$artifact, [int]$entries, [long]$bytes)); throw 'Expected a validation error' }
    catch {
        $error = $_.Exception
        while ($error.InnerException) { $error = $error.InnerException }
        if ($error.Message -notmatch $expected) { throw }
    }
}

$normal = New-ProbeArchive 'normal' @{ 'Project/a.txt' = '1234'; 'Project/inner/b.txt' = '12345' }
$method.Invoke($null, @([string]$normal, [string]$artifact, [int]2, [long]9))
Test-Rejection $normal 1 9 'entry limit'
Test-Rejection $normal 2 8 'size limit'
$caseEntries = [Collections.Generic.Dictionary[string, string]]::new([StringComparer]::Ordinal)
$caseEntries.Add('Project/A.txt', '1')
$caseEntries.Add('Project/a.TXT', '2')
$duplicate = New-ProbeArchive 'case' $caseEntries
Test-Rejection $duplicate 10 100 'duplicate case-insensitive'
$prefix = New-ProbeArchive 'prefix' @{ 'Project/node' = '1'; 'Project/node/child' = '2' }
Test-Rejection $prefix 10 100 'file/directory path conflict'
$result = @{ status = 'passed'; entry_limit = $true; size_limit = $true; case_conflict = $true; prefix_conflict = $true }
$receipt = Join-Path $artifact "archive-export-$run.json"
[IO.File]::WriteAllText($receipt, ($result | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
Write-Output "Receipt: $receipt"
