# Parse and bind the complete native source without emitting an assembly.
param(
    [string]$Install = $env:VOCALOID_INSTALL,
    [string]$Framework = 'net10.0',
    [ValidateSet('VOCALOID6', 'VOCALOID7')][string]$Product
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$python = Join-Path $root '.venv/Scripts/python.exe'
$selectionArguments = @((Join-Path $root 'vocaloid_bridge/install.py'))
if ($Install) { $selectionArguments += @('--install', $Install) }
if ($Product) { $selectionArguments += @('--product', $Product) }
$selectionJson = & $python @selectionArguments
if ($LASTEXITCODE -ne 0) { throw 'VOCALOID installation discovery failed.' }
$selection = $selectionJson | ConvertFrom-Json
$Install = $selection.path
$product = $selection.product
$core = Get-Item -LiteralPath $selection.core_path
$dotnetRoot = Split-Path (Get-Command dotnet).Source -Parent
foreach ($assembly in @('Microsoft.CodeAnalysis.dll', 'Microsoft.CodeAnalysis.CSharp.dll')) {
    Add-Type -Path (Join-Path $PSHOME $assembly)
}
$references = [System.Collections.Generic.List[Microsoft.CodeAnalysis.MetadataReference]]::new()
foreach ($pack in @('Microsoft.NETCore.App.Ref', 'Microsoft.WindowsDesktop.App.Ref')) {
    $version = Get-ChildItem -LiteralPath (Join-Path $dotnetRoot "packs/$pack") -Directory |
        Where-Object { Test-Path (Join-Path $_.FullName "ref/$Framework") } |
        Sort-Object { [version]$_.Name } -Descending | Select-Object -First 1
    if (-not $version) { throw "Missing $Framework reference pack: $pack" }
    foreach ($file in Get-ChildItem -LiteralPath (Join-Path $version.FullName "ref/$Framework") -Filter '*.dll') {
        $references.Add([Microsoft.CodeAnalysis.MetadataReference]::CreateFromFile($file.FullName))
    }
}
$references.Add([Microsoft.CodeAnalysis.MetadataReference]::CreateFromFile($core.FullName))
$trees = [System.Collections.Generic.List[Microsoft.CodeAnalysis.SyntaxTree]]::new()
$parse = [Microsoft.CodeAnalysis.CSharp.CSharpParseOptions]::Default.WithLanguageVersion(
    [Microsoft.CodeAnalysis.CSharp.LanguageVersion]::Preview).WithPreprocessorSymbols([string[]]@($product))
foreach ($file in Get-ChildItem -LiteralPath (Join-Path $root 'native') -Filter '*.cs' -File) {
    $trees.Add([Microsoft.CodeAnalysis.CSharp.CSharpSyntaxTree]::ParseText(
        [IO.File]::ReadAllText($file.FullName), $parse, $file.FullName))
}
$globals = 'global using System; global using System.Collections.Generic; global using System.Linq; global using System.Threading; global using System.Threading.Tasks;'
$globalsPath = Join-Path $root "native/obj/$product/Release/$Framework-windows/VocaloidBridge.Host.GlobalUsings.g.cs"
$trees.Add([Microsoft.CodeAnalysis.CSharp.CSharpSyntaxTree]::ParseText($globals, $parse, $globalsPath))
$options = [Microsoft.CodeAnalysis.CSharp.CSharpCompilationOptions]::new([Microsoft.CodeAnalysis.OutputKind]::ConsoleApplication).
    WithPlatform([Microsoft.CodeAnalysis.Platform]::X64).
    WithNullableContextOptions([Microsoft.CodeAnalysis.NullableContextOptions]::Enable)
$compilation = [Microsoft.CodeAnalysis.CSharp.CSharpCompilation]::Create('VocaloidBridge.Preflight', $trees, $references, $options)
$errors = @($compilation.GetDiagnostics() | Where-Object { $_.Severity -eq [Microsoft.CodeAnalysis.DiagnosticSeverity]::Error })
$errors | ForEach-Object { $_.ToString() }
Write-Output "Native semantic preflight: $product / $Framework, $($trees.Count) files, $($references.Count) references, $($errors.Count) errors"
if ($errors.Count) { exit 1 }
exit 0
