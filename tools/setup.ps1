param([string]$Python = 'E:\Py\python.exe')

$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$EnvironmentPython = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $EnvironmentPython)) {
    & $Python -m venv (Join-Path $Root '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed.' }
}
& $EnvironmentPython -m pip install --disable-pip-version-check -e $Root
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
& dotnet build (Join-Path $Root 'native\VocaloidBridge.Host.csproj') -c Release --configfile (Join-Path $Root '.tools\NuGet.Config') --nologo
if ($LASTEXITCODE -ne 0) { throw 'Native host build failed.' }
Write-Output 'VOCALOID6 MCP setup complete.'