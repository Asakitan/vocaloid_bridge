# Native VPR unknown-data preservation

## Reproduction

`tools/check_project_preservation.py --case preservation.unknown_fields` makes a
copy of a native-saved AI project, adds independent unknown root, master, track,
part and note properties plus a benign extra ZIP member, edits the note using
the native session, saves, reopens and clones. Before the preservation work,
the native edit survived but all five fields and the extra member were lost on
both save and clone. The input remained unchanged. The failed runtime receipt is
`artifacts/feature-acceptance-4d0be911da4b/preservation.unknown_fields.json`.

## Observer evidence and boundaries

The installed managed wrapper exposes `WIVSMUpdateObserver`, `DidInsert`,
`DidRemove`, and value/position/name notifications. One private-desktop native
probe saw a note retain its native pointer across pitch and position changes,
and a track retain its pointer across reorder. Deletion emitted `DidRemove`,
duplication `DidInsert`, and undo/redo of the replacement emitted remove/insert
on the same address. The console transcription is
`artifacts/preservation-observer-transcript-19ce-session08.json`; it is labeled
as a transcription rather than a machine-written native receipt. It does not
establish notification behavior for all edits, deletion cascades, generic native
calls, concurrent callbacks or every history path.

## Implemented scope and validation

`native/ProjectArchivePreservation.cs` is integrated into open, save and clone.
It reads known property names from the
installed native VPR schema, with a narrow correction for that schema's missing
`langIDs` array item description. It binds unknown root/master fields and
track/part/note fields to current native entities, validates counts and
positional identity before initial binding and snapshot overlay, and blocks
ambiguous equal signatures. Observer removal invalidates tracked identities and
their descendants. History snapshots must be bracketed around each actual native
commit, undo, redo and rollback; unverified arbitrary or multi-commit mutation
paths are gated when entity extensions exist.

Unknown fields inside schema-known fixed child objects of those owners are also
collected as relative JSON Pointers. The snapshot must retain each parent object;
missing parents and conflicting leaves are errors, and known values are never
copied from the source. The focused run
`artifacts/feature-acceptance-1fc72536a94a/` verified unknown fields in
`masterTrack.loop` and `note.exp`, including escaped pointer characters and a
structured value, while a native Accent change to 51 remained intact across
save, reopen and source-independent clone. Unknown fields inside non-entity
arrays remain outside this support.

`artifacts/feature-acceptance-f0e3121b86c8/` additionally verifies retained
extensions across title, tempo, loop, tuning, batch-note, VoiceColor and vibrato
changes. True native history commits advance the identity journal; no-op and
non-history synchronization do not add fictitious undo steps. Journal storage
is bounded by the native undo limit.

Only unknown properties are overlaid onto fresh native output. The implementation
retains additional non-native-managed files without overwriting native output;
native-referenced `Project/Audio` assets are not resurrected after deletion,
while members already unreferenced at open are retained as opaque extras. Other
unsupported array-contained unknown fields are rejected rather than dropped. Clone must
overlay the source snapshot before native open, then establish fresh bindings in
the new session; it must never reuse source pointers. Session close must detach
and dispose its observer before native lifetime ends.

The focused real-MCP run `artifacts/feature-acceptance-d58315058dcd/` passed
both `preservation.unknown_fields` and `preservation.identity`. The former
verified root/master/track/part/note sentinels, a Project extra file, an
unreferenced Audio member and an archive-root extra through save, reopen and
save again, plus clone after closing the source. The latter verified track
reorder/rename, note move/pitch edit, same-value delete/recreate without stale
metadata, and double undo/redo. These are bounded examples, not proof for every
VPR or mutation.

To prevent ambiguous attachment, files with extended entities and duplicate
track type/name signatures, duplicate part name/position/duration signatures,
or duplicate note identity signatures are rejected. Unsupported unknown fields
inside array elements are also rejected. With entity extensions present,
unverified raw/native mutations, clipboard paste, merge, library/audio writes,
and score operations outside the explicitly tracked subset are rejected; they
are not silently treated as safe. Split/join, duplicate/paste extension
semantics, larger history/rollback permutations, and other archive formats have
not been verified.
