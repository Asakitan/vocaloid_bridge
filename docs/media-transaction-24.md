# Synthetic media transaction probe — session 24

## Scope and reproduction

Run `.venv\Scripts\python.exe tools\probe_media_transaction_24.py` from the workspace root. The probe creates a fresh synthetic directory and two files, and constrains child paths to that directory. It launches no native process and touches no media library. Receipt: `artifacts/media-transaction-24-e9c72d5172d0/receipt.json`. Every direct child was synchronously waited for by `subprocess.run`; no global process enumeration was performed.

## Forced interleaving

A parent opened the original target for read/write with READ, WRITE and DELETE sharing, then held an exclusive one-byte range lock at offset 4096. While that lock remained held, independent children read the original content, wrote `external` to the target, and attempted to replace it with a prepared candidate using `MoveFileEx`. Read and write succeeded; replacement failed with Windows error 5; the target contained `external`. These are forced overlapping handle lifetimes, not a stress test. The lock was outside the tested data range, so the write result does not characterize writes overlapping a locked range. The replacement error does not isolate its exact cause.

## Conclusion and limits

This sample gives no sustained check-through-commit exclusion: the competing write succeeded, while the attempted replacement failed. It does not test a handle-based rename API, all sharing modes, hard links, pre-existing writers, filesystems, or crash durability. It also does not establish a protocol compatible with native refresh. Session 22 observed an incomplete native refresh with an exclusive handle, and existing native references remained invalid after a later refresh; this probe did not rerun or extend those observations. General unknown-field merge identity, rollback and cache recovery remain open. No production code or guard was changed.
