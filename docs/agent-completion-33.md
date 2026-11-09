# Agent-facing completion work — 0.24.0

This release expands the existing native transaction paths, not a second editor or an input-emulation backend. All targeted runs used private desktops and E-drive temporary storage.

## Recovery API

`media_recovery_list` returns pending journal tokens, clip IDs, state, source-match status, digests and an opaque revision. Call `media_recovery_resolve` with `journal_token`, `expected_revision` and `choice` (`keep_current` or `restore_original`). Re-inspect after a stale-revision error. Resolution can acknowledge a missing current property; restoring requires the original clip identity and bytes. Original/candidate/accepted bytes are retained under the returned recovery archive. A persisted restore decision is resumed after process death. These are workspace library operations and require no project session.

The existing property worker is now usable for archive-bearing clips: it serializes a private copy, verifies the complete clip byte stream unchanged, merges only requested property fields, then publishes through the journal. This does not add controller/pitch/audio metadata support to media capture or import.

## Identity transactions

- Ordinary operations retain existing curve-owner identities, maps and complete native values. An unexpected replacement is a transaction error.
- Deletion captures the complete current native parent graph and the exact selected descendant set. Staged output must contain exactly the surviving graph. Untracked ordinary new notes are included in the graph, not incorrectly required in the archival payload table.
- Native duplicates and cross-project transfers validate complete point values and deep-copy unknown fields. Track automation offsets apply to nonzero points; controller and direct-pitch positions remain owner-relative.
- Note splitting duplicates the source pitch trajectory into each native result using part-absolute pitch coordinates. Joining reconciles matching coordinates and values; conflicting unknown fields are rejected. Native generated points start without inherited fields. Removed note owners are pruned before pre-commit validation.
- The occupied meter boundary is an explicitly retained event with a changed signature, checked by native pointer, bar and value. Empty generated boundaries retain no old metadata.
- Audio import/edit and effect edits use the existing score transaction and curve validators. Microphone capture and external DAW routing are not added.

## Evidence

Five focused contracts passed across recorded runs: installed AI voices/phrases (`f9604580d8c2`), recovery decisions (`f422e21aaea7`), mixed mutations including cut/effect undo (`a140e922062d`), occupied meter (`8c470b8733ab`), pitch split/join and conflict rollback (`d8d071b1a2e4`). The first, third and fourth IDs also have earlier failures in their batch or lineage; consult per-case receipts rather than calling every batch green. No broad suite was run. The final semantic check covered 31 source files and 211 references; build completed with zero warnings/errors.

The remaining constraints are maintained in `TODO.md`. No per-provider or hardware integration guarantee follows from these tests.

## Cleanup

Synthetic VPR/WAV outputs, candidates and disposable logs from this session were removed after receipts were retained. Cleanup removed 107 files (262,919 bytes) and the orphan test clip. Nine E-drive compiler assemblies remain locked by the shared compiler; no process-wide shutdown was issued. Pending media journals and private-process temporary directories were empty. See `artifacts/cleanup-33.json`.
