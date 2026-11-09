# Synthetic same-handle media isolation probe — session 26

## Scope and execution

Run `.venv\Scripts\python.exe tools\probe_media_handle_26.py` from the workspace. It creates a uniquely named synthetic directory under `artifacts`, validates all operated paths against that directory pattern, and waits for each direct child. It uses ordinary synthetic text files only; no native session, user material, archive-bearing update, production code, or build is involved. The initial run stopped on a PyHANDLE context-manager error; its fixture was retained. The corrected run produced `artifacts/media-handle-26-349c07fdd1874a6c9e3fc24d73e16b33/receipt.json`.

## Results and limitations

- A target handle opened with `GENERIC_READ | DELETE` and `FILE_SHARE_READ` blocked the child writer with sharing violation 32. The Python reader also received permission denied: granting read sharing on this handle does not mean a later opener is compatible when that opener does not share the existing DELETE access.
- `SetFileInformationByHandle` with `FileRenameInfo` successfully renamed that same held target handle to an unused name; the moved file contained `original`. This demonstrates a same-handle rename in this interleaving, not an atomic candidate replacement or a general commit protocol.
- A separate candidate handle with DELETE access attempted `FileRenameInfo` replacement over the held target. The call failed with Windows error 5; the target remained `original` and the candidate remained present.
- A writer already open with write access caused the subsequent target isolation open to fail with sharing violation 32. The writer then wrote `external`, observed after its close. No claim is made about every existing-handle or mapping configuration.
- An injected Python exception exited the handle context; a subsequent child writer succeeded and the final file contained `external`. This tests ordinary exception cleanup only, not process termination, machine failure, or durable persistence.

These observations are restricted to the tested local Windows filesystem and access/share combinations. They do not establish generic array identities, a race-free complete transaction, native cache invalidation or refresh recovery, rollback, or crash durability. The session 22 refresh observation remains relevant: a successful refresh status did not establish complete enumeration or survival of old references. No production change or guard relaxation follows from this probe.
