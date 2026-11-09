# Media update evidence probe — session 19

## Independent native property editor experiment

Run `.venv/Scripts/python.exe tools/check_media_native_19.py` from the workspace. The first receipt is `artifacts/feature-acceptance-91857f90edde/summary.json` and the detailed observation is in `preservation.media_native_19.json` in the same directory; the case and cleanup passed. The current script also injects the unknown property described below.

The script creates an AI project with synthetic unknown part and note fields, captures a bridge-owned clip, copies its new directory to a unique `artifacts/feature-acceptance-.../media19-private` directory, and deletes the bridge-owned original. A separate private-desktop PowerShell process then creates a native media manager rooted only in the copied fixture and an empty synthetic system directory. It directly calls the native `UserClip` property editor on the copy. It never changes the host, its guards, or redirects a protected bridge request.

On this fixture, native `Save(true)` returned true after setting name, tempo, and genre/type tags. The entire `.vsclip` file remained byte-identical, including the bridge archive metadata, while `property.json` changed; the in-memory name and tempo matched. Holding the property file with read sharing only made a second native save return false; `.vsclip` and `property.json` bytes and in-memory name/tempo remained unchanged. Destroying and recreating the isolated manager then recovered the changed name, tempo, tags, and one MIDI note. The copied fixture remains in the receipt directory for examination.

The first experiment did not demonstrate bridge `media_update` on metadata-bearing clips, reimport after the independent write, history behavior after that write, crash atomicity, arbitrary I/O failures, concurrent writers, other property variants, audio resources, or preservation for all metadata shapes. The later unknown-property observation is documented below. The unchanged whole `.vsclip` bytes support preservation of its particular payload and metadata, not those wider cases.

## Guard and import baseline

`.venv/Scripts/python.exe tools/check_archive_media_extensions.py` produced `artifacts/feature-acceptance-e94e214370e0/summary.json`: `preservation.media_entities` and `transport.cleanup` passed. The production `media_update` request for an archive-bearing clip was rejected; import into a synthetic project, undo/redo, clone and save/reopen preserved the tested unknown part/note fields. This test also checks controller and extension-audio rejections, malformed private clip metadata rejection, and clip cleanup. Its import is on a separately captured clip, not the independently property-edited copy.

An ordinary private MIDI clip observation is in `artifacts/feature-acceptance-2456c42fd76b/summary.json`; the archive-bearing expected-success case in `artifacts/feature-acceptance-720b23a039dd/summary.json` stopped at the guard, before its subsequent assertions.

## Decision boundary

The previous automatic-review denial and the requirement for the relevant user confirmation and approval remain in force. These isolated observations do not authorize removal or circumvention of the production guard.

## Unknown property field experiment

The updated `tools/check_media_native_19.py` adds `x_media19_property` with the nested value `{"nested":[true,null,{"value":"synthetic"}]}` exclusively to the disposable copied `property.json`, before the isolated native manager loads it. The independent receipt `artifacts/feature-acceptance-39dc398383e1/summary.json` and its `preservation.media_native_19.json` show that the native property save succeeded but **removed that unknown property field**. It remained absent after the locked failure and isolated manager recreation. Meanwhile the complete `.vsclip` bytes and their archive metadata remained unchanged; locked save returned false and left the then-current property bytes and cache name/tempo unchanged, and restarted native readback found the expected name, tempo, tags and note. The test is observational: its passing status means the stated core checks completed, not that the unknown property survived.

This evidence identifies a concrete unknown-property loss risk for native property save. The earlier receipt `artifacts/feature-acceptance-faa734bfa7ff/summary.json` contains an invalid locked cache name read taken after manager disposal and omitted the explicit unknown-field comparison; use `39dc398383e1` for this experiment. The disposable copy was not imported into, or written back to, the production library. Existing approval and guard boundaries remain unchanged.
