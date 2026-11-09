# Synthetic media replacement sharing observations — session 23

## Scope and reproduction

Run `.venv\Scripts\python.exe tools\probe_media_atomic_23.py` from the workspace root. The probe creates new synthetic files beneath a unique `artifacts/media-atomic-23-*` directory; the candidate is the source of `MoveFileEx`, and `target-*.json` is its destination. No user media or native editor is accessed. Receipt: `artifacts/media-atomic-23-4a3d54785412/receipt.json`.

## Observed file-sharing cases

The parent holds an existing target handle opened for generic read. After checking its content, it synchronously launches and waits for independent child processes to attempt a direct write and a candidate-to-target `MoveFileEx` replacement while the handle remains held. With share mode READ, both attempts failed; replacement reported Windows error 5. With share mode READ | DELETE, both attempts likewise failed, and replacement again reported error 5. The target retained `original` and the candidate remained present in both cases. After releasing the handle, the same candidate-to-target replacement succeeded in each case and the target contained `candidate`. Each direct child was waited for by `subprocess.run`; no global process enumeration was performed.

This shows a forced interleaving with concurrent handle lifetimes, not a stress test of simultaneous racing operations. The error does not by itself isolate which sharing, filesystem or access rule caused each failure. Both tested modes prevent the attempted replacement while the handle is held, so these observations do not establish a usable check-through-commit protocol. Unlocking before the successful replacement reopens the previously demonstrated check-to-replace race. This experiment does not test directory handles, pre-existing writer handles, alternate names, hard links, privilege differences, remote filesystems, or every replacement API. No general system guarantee is inferred from these samples.

## Native refresh and open boundaries

No new native process was launched in this probe. The separate session 22 actual native experiment documented in `docs/media-failure-22.md` observed a successful status with an omitted clip while an exclusive property handle was held; after unlocking, a fresh enumeration recovered that clip but the old reference remained invalid. That is an observed sample, not proof of full cache recovery, an injected non-success status, or a complete production recovery contract. Session 22 cleanup records `IsolatedProcess.close()` returning, not independent process enumeration.

A workable protocol would still need evidence for sustained exclusion through the actual commit, controlled competing writers and directory-entry changes, native refresh validation and cache invalidation, rollback failure, multi-clip behavior, and crash durability. The probe does not implement a merge or alter production behavior; ordinary media unknown-field loss remains unresolved and archive-bearing guards remain unchanged.

The probe child now validates that both resolved paths belong to the same
synthetic `artifacts/media-atomic-23-*` directory and have the expected target
and candidate names. A rerun after this path constraint produced the same
observed outcomes in `artifacts/media-atomic-23-dbc4a1ee15e6/receipt.json`.
This path constraint does not establish a production transaction protocol.
