# Parse and bind the complete native source without emitting an assembly.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$dotnetRoot = Split-Path (Get-Command dotnet).Source -Parent
foreach ($assembly in @('Microsoft.CodeAnalysis.dll', 'Microsoft.CodeAnalysis.CSharp.dll')) {
    Add-Type -Path (Join-Path $PSHOME $assembly)
}
$references = [System.Collections.Generic.List[Microsoft.CodeAnalysis.MetadataReference]]::new()
foreach ($pack in @('Microsoft.NETCore.App.Ref', 'Microsoft.WindowsDesktop.App.Ref')) {
    $version = Get-ChildItem -LiteralPath (Join-Path $dotnetRoot "packs/$pack") -Directory |
        Where-Object { Test-Path (Join-Path $_.FullName 'ref/net8.0') } |
        Sort-Object { [version]$_.Name } -Descending | Select-Object -First 1
    if (-not $version) { throw "Missing net8.0 reference pack: $pack" }
    foreach ($file in Get-ChildItem -LiteralPath (Join-Path $version.FullName 'ref/net8.0') -Filter '*.dll') {
        $references.Add([Microsoft.CodeAnalysis.MetadataReference]::CreateFromFile($file.FullName))
    }
}
$install = if ($env:VOCALOID_INSTALL) { $env:VOCALOID_INSTALL } else { 'C:\Program Files\VOCALOID6\Editor' }
$references.Add([Microsoft.CodeAnalysis.MetadataReference]::CreateFromFile((Join-Path $install 'VOCALOID6.dll')))
$trees = [System.Collections.Generic.List[Microsoft.CodeAnalysis.SyntaxTree]]::new()
$parse = [Microsoft.CodeAnalysis.CSharp.CSharpParseOptions]::Default.WithLanguageVersion(
    [Microsoft.CodeAnalysis.CSharp.LanguageVersion]::CSharp12)
foreach ($file in Get-ChildItem -LiteralPath (Join-Path $root 'native') -Filter '*.cs' -File) {
    $trees.Add([Microsoft.CodeAnalysis.CSharp.CSharpSyntaxTree]::ParseText(
        [IO.File]::ReadAllText($file.FullName), $parse, $file.FullName))
}
$globalsPath = Join-Path $root 'native/obj/Release/net8.0-windows/VocaloidBridge.Host.GlobalUsings.g.cs'
if (-not (Test-Path -LiteralPath $globalsPath)) { throw 'Generate the project global usings before semantic preflight.' }
$trees.Add([Microsoft.CodeAnalysis.CSharp.CSharpSyntaxTree]::ParseText([IO.File]::ReadAllText($globalsPath), $parse, $globalsPath))
$options = [Microsoft.CodeAnalysis.CSharp.CSharpCompilationOptions]::new([Microsoft.CodeAnalysis.OutputKind]::ConsoleApplication).
    WithPlatform([Microsoft.CodeAnalysis.Platform]::X64).
    WithNullableContextOptions([Microsoft.CodeAnalysis.NullableContextOptions]::Enable)
$compilation = [Microsoft.CodeAnalysis.CSharp.CSharpCompilation]::Create('VocaloidBridge.Preflight', $trees, $references, $options)
$errors = @($compilation.GetDiagnostics() | Where-Object { $_.Severity -eq [Microsoft.CodeAnalysis.DiagnosticSeverity]::Error })
$errors | ForEach-Object { $_.ToString() }
Write-Output "Native semantic preflight: $($trees.Count) files, $($references.Count) references, $($errors.Count) errors"
if ($errors.Count) { exit 1 }
exit 0
