param([Parameter(Mandatory=$true)][string]$Root,[Parameter(Mandatory=$true)][string]$ClipId)
$ErrorActionPreference='Stop'
$workspace=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path; $rootPath=(Resolve-Path $Root).Path; $artifacts=(Resolve-Path (Join-Path $workspace 'artifacts')).Path
if (-not $rootPath.StartsWith($artifacts + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase) -or (Split-Path $rootPath -Leaf) -ne 'media20-private' -or $ClipId -notmatch '^[0-9a-f-]{36}$') { throw 'Synthetic fixture root required' }
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
$stage=Join-Path (Split-Path $rootPath) 'stage20'; $empty=Join-Path (Split-Path $rootPath) 'empty20'; New-Item -ItemType Directory $stage,$empty | Out-Null
Copy-Item -Recurse (Join-Path $rootPath $ClipId) (Join-Path $stage $ClipId)
function New-Manager($dir) { $e=[Yamaha.VOCALOID.VMM.VMMError]::None; $m=[Yamaha.VOCALOID.VMM.MediaManagerIF]::CreateMediaManager('VOCALOID6',$empty,$dir,[string[]]@(),[string[]]@(),[ref]$e); if ($null -eq $m -or $e -ne [Yamaha.VOCALOID.VMM.VMMError]::None -or $m.ReadAllClipFiles() -ne [Yamaha.VOCALOID.VMM.VMMError]::None) { throw 'Manager failed' }; return $m }
$live=New-Manager $rootPath; $staged=New-Manager $stage
try {
 $lc=@($live.AllClipEnumerator() | Where-Object ID -eq $ClipId)[0]; $sc=@($staged.AllClipEnumerator() | Where-Object ID -eq $ClipId)[0]
 $prop=Join-Path (Join-Path $rootPath $ClipId) 'property.json'; $sp=Join-Path (Join-Path $stage $ClipId) 'property.json'; $original=[IO.File]::ReadAllText($prop); $editor=$sc.CreatePropertyEditor()
 try { if (-not $editor.SetClipName('Media20 staged') -or -not $editor.SetPartTempo(12345) -or -not $editor.SetPartKey($sc.PartKey) -or -not $editor.Save($true)) { throw 'Stage edit failed' } } finally { $sc.DestroyPropertyEditor() }
 $stagedJson=[IO.File]::ReadAllText($sp) | ConvertFrom-Json; $oldJson=$original | ConvertFrom-Json; $stagedJson | Add-Member -NotePropertyName x_media19_property -NotePropertyValue $oldJson.x_media19_property -Force
 $temp=$prop+'.tmp'; [IO.File]::WriteAllText($temp,($stagedJson | ConvertTo-Json -Depth 100 -Compress),[Text.UTF8Encoding]::new($false));
 $lock=[IO.File]::Open($prop,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
 try { try { [IO.File]::Move($temp,$prop,$true); $locked='unexpected success' } catch { $locked=$_.Exception.GetType().FullName } } finally { $lock.Dispose() }
 $unchanged=([IO.File]::ReadAllText($prop) -eq $original); $lockCache=$lc.Name
 [IO.File]::Move($temp,$prop,$true); $beforeRefresh=$lc.Name; $refresh=[string]$live.ReadAllClipFiles(); $afterClip=@($live.AllClipEnumerator() | Where-Object ID -eq $ClipId)[0]
 @{desktop=$desktop; staged_name=$sc.Name; locked_result=$locked; locked_file_unchanged=$unchanged; locked_cache=$lockCache; cache_before_refresh=$beforeRefresh; refresh=$refresh; cache_after_refresh=$afterClip.Name; old_object_after_refresh=$lc.Name; committed_name=(([IO.File]::ReadAllText($prop) | ConvertFrom-Json).name); unknown_preserved=(([IO.File]::ReadAllText($prop) | ConvertFrom-Json).x_media19_property.nested[2].value -eq 'synthetic')} | ConvertTo-Json -Compress
} finally { $staged.Dispose(); $live.Dispose() }
