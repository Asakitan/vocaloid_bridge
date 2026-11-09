param([Parameter(Mandatory=$true)][string]$Root,[Parameter(Mandatory=$true)][string]$ClipId,[ValidateSet('stage','live')][string]$Mode)
$ErrorActionPreference='Stop'
$workspace=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path; $rootPath=(Resolve-Path $Root).Path; $artifacts=(Resolve-Path (Join-Path $workspace 'artifacts')).Path
if (-not $rootPath.StartsWith($artifacts + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase) -or (Split-Path $rootPath -Leaf) -notin @('media20-private','media20-stage') -or $ClipId -notmatch '^[0-9a-f-]{36}$') { throw 'Synthetic fixture root required' }
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class Media20DllPaths {
 [DllImport("kernel32",SetLastError=true)] public static extern bool SetDefaultDllDirectories(uint flags);
 [DllImport("kernel32",CharSet=CharSet.Unicode,SetLastError=true)] public static extern IntPtr AddDllDirectory(string path);
}
"@
$install='C:\Program Files\VOCALOID6\Editor'; if (-not [Media20DllPaths]::SetDefaultDllDirectories(0xc00) -or [Media20DllPaths]::AddDllDirectory($install) -eq [IntPtr]::Zero) { throw 'DLL setup failed' }
[Reflection.Assembly]::LoadFrom((Join-Path $install 'VOCALOID6.dll')) | Out-Null
$asm=[Reflection.Assembly]::LoadFrom((Join-Path $workspace 'native\bin\Release\net8.0-windows\VocaloidBridge.Host.dll'))
$desktop=$asm.GetType('Program',$true).GetMethod('DesktopName',[Reflection.BindingFlags]'Static,NonPublic').Invoke($null,@()); if ($desktop -in @('Default','Winlogon','Disconnect')) { throw 'Private desktop required' }
$empty=Join-Path (Split-Path $rootPath) ('empty20-'+[guid]::NewGuid().ToString('N')); New-Item -ItemType Directory $empty | Out-Null
$e=[Yamaha.VOCALOID.VMM.VMMError]::None
$manager=[Yamaha.VOCALOID.VMM.MediaManagerIF]::CreateMediaManager('VOCALOID6',$empty,$rootPath,[string[]]@(),[string[]]@(),[ref]$e)
if ($null -eq $manager -or $e -ne [Yamaha.VOCALOID.VMM.VMMError]::None -or $manager.ReadAllClipFiles() -ne [Yamaha.VOCALOID.VMM.VMMError]::None) { throw 'Manager failed' }
try {
 $clip=@($manager.AllClipEnumerator() | Where-Object ID -eq $ClipId)[0]
 if ($null -eq $clip -or [IO.Path]::GetFullPath($clip.ClipPath) -ne [IO.Path]::GetFullPath((Join-Path (Join-Path $rootPath $ClipId) ($ClipId+'.vsclip')))) { throw 'Wrong manager root' }
 if ($Mode -eq 'stage') {
  $editor=$clip.CreatePropertyEditor(); try { if (-not $editor.SetClipName('Media20 staged') -or -not $editor.SetPartTempo(12345) -or -not $editor.SetPartKey($clip.PartKey) -or -not $editor.Save($true)) { throw 'Stage save failed' } } finally { $clip.DestroyPropertyEditor() }
  @{mode=$Mode;desktop=$desktop;path=$clip.ClipPath;name=$clip.Name} | ConvertTo-Json -Compress
 } else {
  @{mode=$Mode;desktop=$desktop;path=$clip.ClipPath;name=$clip.Name} | ConvertTo-Json -Compress
  while (($command=[Console]::ReadLine()) -ne $null) {
   if ($command -eq 'read') { @{name=$clip.Name;tempo=$clip.PartTempo} | ConvertTo-Json -Compress }
   elseif ($command -eq 'refresh') { $result=$manager.ReadAllClipFiles(); $found=@($manager.AllClipEnumerator() | Where-Object ID -eq $ClipId)[0]; @{status=[string]$result;name=$found.Name;tempo=$found.PartTempo;old_name=$clip.Name} | ConvertTo-Json -Compress }
   else { break }
  }
 }
} finally { $manager.Dispose() }
