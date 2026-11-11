param(
    [string]$Python = 'E:\Py\python.exe',
    [string]$Install,
    [ValidateSet('VOCALOID6', 'VOCALOID7')][string]$Product
)

$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$EnvironmentPython = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $EnvironmentPython)) {
    & $Python -m venv (Join-Path $Root '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed.' }
}
& $EnvironmentPython -m pip install --disable-pip-version-check -e $Root
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
$selectionArguments = @((Join-Path $Root 'vocaloid_bridge\install.py'))
if ($Install) { $selectionArguments += @('--install', $Install) }
if ($Product) { $selectionArguments += @('--product', $Product) }
$selectionJson = & $EnvironmentPython @selectionArguments
if ($LASTEXITCODE -ne 0) { throw 'VOCALOID installation discovery failed.' }
$selection = $selectionJson | ConvertFrom-Json
Write-Output "Selected $($selection.product) $($selection.version) at $($selection.path)"
& dotnet build (Join-Path $Root 'native\VocaloidBridge.Host.csproj') -c Release --configfile (Join-Path $Root '.tools\NuGet.Config') --nologo "-p:VocaloidInstall=$($selection.path)" "-p:VocaloidProduct=$($selection.product)" "-p:VocaloidPython=$EnvironmentPython"
if ($LASTEXITCODE -ne 0) { throw 'Native host build failed.' }
Write-Output "$($selection.product) MCP setup complete."