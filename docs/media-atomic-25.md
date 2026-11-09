# Synthetic media atomicity probe — session 25

## Scope

Run `.venv\Scripts\python.exe tools\probe_media_atomic_25.py` from the workspace. It creates a uniquely named synthetic directory under `artifacts` with `property.json` and a candidate, and validates child paths; it does not open a native session, user assets, or any archive-bearing material. Receipt: `artifacts/media-atomic-25-a5cd2aa12cbf4df5b0d324e8692fc427/receipt.json`. Each direct child was synchronously waited for. No deletion or build occurred.

## Controlled overlap

With a parent read/write handle sharing read, write and delete, an exclusive byte-range lock on byte zero remained held throughout three independent child attempts. Python read and write reported permission errors; `MoveFileEx` replacement returned Windows error 5. After release, the target was empty: the write attempt opened with truncation before its data write failed. Thus the lock did not preserve content against this writer, even though its write reported failure. This result is specific to the tested open/write behavior and does not characterize all readers, writers, sharing modes or filesystems.

With a parent read/write handle sharing read only, an independent read returned the original text; a writer failed to open and `MoveFileEx` returned error 5. After release the original text remained. This single forced interleaving does not establish isolation from handles opened before the parent, all replacement methods, hard links, crashes, or native compatibility.

## Native refresh and recovery

Not tested in this probe. Earlier session 22 observed a successful refresh response that omitted a locked item and stale references after a subsequent refresh; that observation does not prove recovery. No claim is made about refresh completeness, identity, rollback, unknown-field merge or durability. No production change or guard relaxation is supported by this experiment.
