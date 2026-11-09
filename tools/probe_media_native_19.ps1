param([Parameter(Mandatory=$true)][string]$Root,[Parameter(Mandatory=$true)][string]$ClipId)
$ErrorActionPreference='Stop'
$install='C:\Program Files\VOCALOID6\Editor'; $workspace=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$rootPath=(Resolve-Path $Root).Path; $artifacts=(Resolve-Path (Join-Path $workspace 'artifacts')).Path
if (-not $rootPath.StartsWith($artifacts + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase) -or (Split-Path $rootPath -Leaf) -ne 'media19-private' -or $ClipId -notmatch '^[0-9a-f-]{36}$') { throw 'Synthetic fixture root required' }
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class Media19DllPaths {
 [DllImport("kernel32",SetLastError=true)] public static extern bool SetDefaultDllDirectories(uint flags);
 [DllImport("kernel32",CharSet=CharSet.Unicode,SetLastError=true)] public static extern IntPtr AddDllDirectory(string path);
}
"@
if (-not [Media19DllPaths]::SetDefaultDllDirectories(0xc00) -or [Media19DllPaths]::AddDllDirectory($install) -eq [IntPtr]::Zero) { throw 'DLL setup failed' }
[Reflection.Assembly]::LoadFrom((Join-Path $install 'VOCALOID6.dll')) | Out-Null
$asm=[Reflection.Assembly]::LoadFrom((Join-Path $workspace 'native\bin\Release\net8.0-windows\VocaloidBridge.Host.dll'))
$desktop=$asm.GetType('Program',$true).GetMethod('DesktopName',[Reflection.BindingFlags]'Static,NonPublic').Invoke($null,@())
if ($desktop -in @('Default','Winlogon','Disconnect')) { throw 'Private desktop required' }
$empty=Join-Path $rootPath 'empty'; New-Item -ItemType Directory $empty | Out-Null
$errorCode=[Yamaha.VOCALOID.VMM.VMMError]::None
$manager=[Yamaha.VOCALOID.VMM.MediaManagerIF]::CreateMediaManager('VOCALOID6',$empty,$rootPath,[string[]]@(),[string[]]@(),[ref]$errorCode)
if ($null -eq $manager -or $errorCode -ne [Yamaha.VOCALOID.VMM.VMMError]::None) { throw "Manager create failed: $errorCode" }
try {
 $err=$manager.ReadAllClipFiles(); if ($err -ne [Yamaha.VOCALOID.VMM.VMMError]::None) { throw "Read failed: $err" }
 $clip=@($manager.AllClipEnumerator() | Where-Object { $_.ID -eq $ClipId }); if ($clip.Count -ne 1 -or $clip[0] -isnot [Yamaha.VOCALOID.VMM.UserClip]) { throw 'Synthetic clip not found as user clip' }; $clip=$clip[0]
 $clipPath=Join-Path (Join-Path $rootPath $ClipId) ($ClipId+'.vsclip'); $prop=Join-Path (Split-Path $clipPath) 'property.json'
 if ([IO.Path]::GetFullPath($clip.ClipPath) -ne [IO.Path]::GetFullPath($clipPath)) { throw 'Wrong clip path' }
 $oldClip=[IO.File]::ReadAllBytes($clipPath); $oldProp=[IO.File]::ReadAllBytes($prop); $oldMeta=([Text.Encoding]::UTF8.GetString($oldClip) | ConvertFrom-Json).vocaloid_bridge_archive_entities_v1 | ConvertTo-Json -Depth 100 -Compress
 $key=$clip.PartKey; $genres=@($clip.Filter.GenreEnumerator()); $types=@($clip.Filter.TypeEnumerator())
 $editor=$clip.CreatePropertyEditor(); if ($null -eq $editor) { throw 'Editor unavailable' }
 try {
  foreach ($ok in @($editor.SetClipName('Media19 changed'),$editor.SetPartTempo(12345),$editor.SetPartKey($key))) { if (-not $ok) { throw 'Editor seed failed' } }
  foreach ($g in $genres) { if (-not $editor.AddFilterGenre($g)) { throw 'Genre seed failed' } }; foreach ($t in $types) { if (-not $editor.AddFilterType($t)) { throw 'Type seed failed' } }
  if (-not $editor.AddFilterGenre('Media19') -or -not $editor.AddFilterType('Media19')) { throw 'Tag set failed' }
  $saved=$editor.Save($true)
 } finally { $clip.DestroyPropertyEditor() }
 $newClip=[IO.File]::ReadAllBytes($clipPath); $newProp=[IO.File]::ReadAllBytes($prop)
 $newMeta=([Text.Encoding]::UTF8.GetString($newClip) | ConvertFrom-Json).vocaloid_bridge_archive_entities_v1 | ConvertTo-Json -Depth 100 -Compress
 $sameClip=[Convert]::ToBase64String($oldClip) -eq [Convert]::ToBase64String($newClip); $changedProp=[Convert]::ToBase64String($oldProp) -ne [Convert]::ToBase64String($newProp)
 $beforeName=$clip.Name; $beforeTempo=$clip.PartTempo
 $lock=[IO.File]::Open($prop,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
 try {
  $editor=$clip.CreatePropertyEditor(); try {
   $null=$editor.SetClipName('Media19 locked'); $null=$editor.SetPartTempo(13579); $null=$editor.SetPartKey($key)
   foreach ($g in @($clip.Filter.GenreEnumerator())) { $null=$editor.AddFilterGenre($g) }; foreach ($t in @($clip.Filter.TypeEnumerator())) { $null=$editor.AddFilterType($t) }
   $lockResult=$editor.Save($true)
  } finally { $clip.DestroyPropertyEditor() }
 } finally { $lock.Dispose() }
 $lockedName=$clip.Name; $lockedTempo=$clip.PartTempo
 $oldUnknown=([Text.Encoding]::UTF8.GetString($oldProp) | ConvertFrom-Json).x_media19_property | ConvertTo-Json -Depth 100 -Compress
 $newUnknown=([Text.Encoding]::UTF8.GetString($newProp) | ConvertFrom-Json).x_media19_property | ConvertTo-Json -Depth 100 -Compress
 $manager.Dispose(); $manager=$null
 $errorCode=[Yamaha.VOCALOID.VMM.VMMError]::None
 $manager=[Yamaha.VOCALOID.VMM.MediaManagerIF]::CreateMediaManager('VOCALOID6',$empty,$rootPath,[string[]]@(),[string[]]@(),[ref]$errorCode)
 if ($null -eq $manager -or $errorCode -ne [Yamaha.VOCALOID.VMM.VMMError]::None -or $manager.ReadAllClipFiles() -ne [Yamaha.VOCALOID.VMM.VMMError]::None) { throw 'Manager restart failed' }
 $reloaded=@($manager.AllClipEnumerator() | Where-Object { $_.ID -eq $ClipId }); if ($reloaded.Count -ne 1) { throw 'Reload missing clip' }; $reloaded=$reloaded[0]
 $partOk=$reloaded.ReadPart()
 $reload=@{name=$reloaded.Name; tempo=$reloaded.PartTempo; genres=@($reloaded.Filter.GenreEnumerator()); types=@($reloaded.Filter.TypeEnumerator()); read_part=$partOk; notes=$reloaded.MidiPart.NumNotes}
 $finalUnknown=([Text.Encoding]::UTF8.GetString([IO.File]::ReadAllBytes($prop)) | ConvertFrom-Json).x_media19_property | ConvertTo-Json -Depth 100 -Compress
 $result=@{unknown_property=@{before=$oldUnknown; after_save=$newUnknown; after_lock_and_reload=$finalUnknown; preserved_after_save=($oldUnknown -eq $newUnknown); preserved_after_lock_and_reload=($oldUnknown -eq $finalUnknown)}; reload=$reload; desktop=$desktop; success=@{save_result=$saved; clip_unchanged=$sameClip; property_changed=$changedProp; metadata_unchanged=($oldMeta -eq $newMeta); name=$beforeName; tempo=$beforeTempo; property=([Text.Encoding]::UTF8.GetString($newProp) | ConvertFrom-Json)}; locked=@{save_result=$lockResult; clip_unchanged=([Convert]::ToBase64String([IO.File]::ReadAllBytes($clipPath)) -eq [Convert]::ToBase64String($newClip)); property_unchanged=([Convert]::ToBase64String([IO.File]::ReadAllBytes($prop)) -eq [Convert]::ToBase64String($newProp)); name=$lockedName; tempo=$lockedTempo} }
 $result | ConvertTo-Json -Depth 100 -Compress
} finally { $manager.Dispose() }
