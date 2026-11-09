# Owned runtime cleanup — session 31

Native child TEMP/TMP now point to the workspace
`.runtime/tmp/<private-desktop-name>`. Shutdown validates that exact owned path
before recursive removal. A normally released VSM manager also removes only its
own GUID namespace under LOCALAPPDATA/VOCALOID6/VSM and VSMCaches. It never
targets the user's shared VOCALOID6 namespace or another live host.

The final media case's native namespace was absent from both cache roots after
exit; the workspace temporary and media-property staging roots were empty.
Forced process termination and power loss can still leave owned directories.

`tools/clean_owned_caches.py --apply` cleans historical GUID namespaces only
when a local receipt identifies the owning PID and Windows process state or
creation time proves that recorded process has ended. It rechecks before
deleting, validates the exact parent and refuses reparse trees. Active, unknown
and explicitly preserved namespaces stay in place; it does not use age alone.

Receipt `artifacts/cleanup-31-f0c9dced5f0b/manifest.json` records removal of
195 old namespace directories, 7,215,084 bytes (6.88 MiB). One hundred active or
insufficiently documented directories were retained, including the existing
conversation host namespace. An additional CIM inventory timed out; that was
not treated as proof of process termination. No editor, voicebank, user media,
global settings or other project's temporary tree was deleted.
