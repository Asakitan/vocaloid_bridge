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

A subsequent private AI-only observer probe
`artifacts/preservation-copy-observer-1ef325a59a30.json` exercised native
track, part and note duplicate followed by undo/redo. Track duplication
reported only the new track insertion, although its parts and notes had new
native identities; part duplication similarly reported only its new part.
Note duplication reported its new note. In this one run undo removed and redo
reinserted the same new object addresses. The probe also observed note split
preserving the left identity and inserting the right, and note join removing the
right; part split/join showed the analogous parent notifications, but its right
side was empty and this is not proof for all part contents.

In a second native probe, the right half of a part contained two notes
(`artifacts/preservation-part-split-15fd889b4936.json`). Split removed their
old note objects and put new note objects in the new part without individual
insert events for those children. Joining then created a third set of note
objects in the retained left part. Therefore tracking parent notifications or
addresses alone is insufficient for part split/join; these operations require
a pre/post identity-migration rule. Conflicting unknown values
on join must not be silently discarded.

The current note-split implementation copies the original note's unknown
payload to the new right note inside the staged transaction. Note join merges
distinct unknown keys and equal values, while conflicting values at the same
pointer cause rollback. Its focused `preservation.note_split` case exercises
split and join with save, undo, redo and reopen. The case also
checks conflicting note-join values and rollback. Part split/join now match
children using unique absolute-position and note-semantic signatures, copy part
unknown data on split, and merge equal or disjoint fields on join. Conflicts or
ambiguous/changed child signatures roll back. The `preservation.part_split_join`
case covers a crossing note, a nonempty right part, history, conflict and reopen.
Both cases passed through a freshly built private MCP host in
`artifacts/feature-acceptance-a4a1a5dc7d8d/summary.json`. These cases do not
establish behavior for every possible note shape or extension combination.

`artifacts/feature-acceptance-ab2b02a98d56/` independently verified live versus
saved order for one AI project after same-name track duplication, reorder, part
duplicate and note duplicate, with reopened track order also matching. That
single example does not prove ordering for every indistinguishable object.

The integrated duplicate-extension implementation copies unknown data to each
new native track/part/note, associates descendants by unique semantic keys
rather than array indices, and uses transaction history for undo/redo. Same
signature tracks with different unknown data must be rejected when identity is
ambiguous. `artifacts/feature-acceptance-647c107fc2bd/preservation.duplicates.json`
records same-name track, part and note copies, child undo/redo, source-independent
clone and rejection of divergent unknown fields on indistinguishable tracks.

## Non-entity array investigation

The controller event implementation binds extension fields to native part
identity, controller type and event tick, validating native known values before
applying unknown fields. Ordinary `controller.set` retains the metadata of a
same-tick event, while `replace=true` removes and recreates all events and does
not inherit their metadata. A single-point `controller.set` with
`controller_index` explicitly moves the selected event; an occupied destination
is rejected. Removing and later creating an event does not inherit metadata.
The retained state participates in native undo/redo snapshots and clone uses a
saved snapshot. Other score mutations and clipboard transfers on projects with
controller extensions are guarded until their identity mappings are established;
cross-project source transfer is guarded before mutation. When the last unknown
controller field is deleted, unrelated edits are available again while older
history retains the previous controller snapshot. The focused
`preservation.controller_array_roundtrip` case covers an AI fixture, collision,
move, history, delete/recreate, replacement, clone, save and reopen; the separate
ambiguity case checks same-shaped tracks carrying distinct controller fields.
Both passed in `artifacts/feature-acceptance-b0b2d367967f/summary.json`.

The guard rejects unknown properties in unsupported element arrays, including
`parts[].audioEffects[].parameters` and `parts[].aiVoice.langIDs`.
`preservation.array_guard` constructs each extension separately and expects
rejection without input modification. A focused private-MCP run
passed these guards, an additional pre-integration tempo guard, and transport cleanup, as recorded in
`artifacts/feature-acceptance-c07d27541b4c/summary.json`. An earlier sandboxed
attempt stopped before process startup on an access-denied artifact directory.

Matching elements by index or by a complete known-value signature is insufficient:
reordering changes indices, editing changes signatures, and a delete followed by
same-value insertion has the same serialized before/after state as no deletion.
Duplicate signatures with distinct extensions are likewise ambiguous. A safe
implementation needs per-array identity or operation-specific pre/post mapping,
transaction history for removal and reinsertion, explicit copy/transfer mapping,
and rejection before mutation when unique correspondence is not established. It
must apply unknown leaves only, never copy known values from the original element.
These rules remain a requirement for arrays outside the tested controller, tempo
and time-signature changes described here.

The source now also maps `masterTrack.timeSig.events` extensions using the
selected native operation and unique bar, with full native-state validation,
transaction history, collision rejection and deletion that discards the deleted
extension. Schema capture checks the installed event fields (`bar`, `numer`,
`denom`); no old array index is used for overlay. The focused
`preservation.timesig_array_roundtrip` case exercises moves, changes, conflicts,
undo/redo, deletion and same-value recreation, clone and reopen. The private-MCP
run `artifacts/feature-acceptance-5f7c71ba55ed/summary.json` passed this case
and recorded the earlier merge guard. Time-signature extension merge has since
been implemented and tested as described in `interchange-operations.md`.

A focused private-MCP probe (`preservation.tempo_array_semantics`, receipt
`artifacts/feature-acceptance-dca2b07208c6/summary.json`) observed a tempo
move across another event, undo/redo, and deletion followed by same-value
recreation. The last state serialized identically to the earlier moved state;
the result does not establish native pointer or notification stability.

`native/ProjectArchiveArrays.cs` contains a tempo transaction
primitive. Given an explicitly selected source and destination, it preserves
only unknown leaves, validates the entire observed native post-state, rejects
duplicate positions and destination collisions, and drops metadata on deletion
so reinsertion starts empty. The standalone in-memory
`tools/check_tempo_array_helper.ps1` probe passed for move, reorder, known-value
preservation, deletion/recreation, snapshot isolation and duplicate rejection.
The current source connects schema-aware capture, native-operation mapping before
commit, history/rollback snapshots and save/clone overlay. Tempo merges with
extensions use explicit destination tick mappings and a candidate snapshot. The original
`preservation.tempo_array_roundtrip` red result on the old binary is retained in
`artifacts/feature-acceptance-39d061aa7454/summary.json`. The focused native MCP
run `artifacts/feature-acceptance-a2ec5efb0ad1/summary.json` passes tempo extension
editing, collision rejection, undo/redo, deletion and same-value recreation,
clone, save/reopen and a track-only clipboard transfer. The updated target/source
merge and undo case passed in `artifacts/feature-acceptance-0f5180183d62/summary.json`.
The earlier source guard is historical, not the current contract. A
separate case verifies that tempo-only metadata does not require unrelated
same-shaped tracks with different known values to be treated as ambiguous.

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
arrays other than tempo events and the pending time-signature implementation
remain outside this support.

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

To prevent ambiguous attachment, the duplicate-aware implementation rejects
tracks with the same type/name/color, mixer flags and part/note shape when their
complete serialized data differs; identical tracks with identical extension
data may coexist. Duplicate part name/position/duration signatures and duplicate
note identity signatures remain rejected. Unsupported unknown fields
inside other array elements are also rejected. With entity or tempo extensions present,
unverified raw/native mutations, library/audio writes, and score operations
outside the explicitly tracked subset are rejected. MIDI/AI/Audio clipboard cut/paste
and track merge now use identity transactions. Source root/master fields with
equal or disjoint pointers can be merged with target fields; new nested leaves
are preflighted against a native target snapshot, while conflicting values and
global-only merges without a native history entry are rejected. The focused
`artifacts/feature-acceptance-5a2c12f87c28/summary.json` verifies direct and
nested additions, save/reopen, undo/redo, source protection and rejection of
an indistinguishable-track conflict on an independent candidate before target
mutation. Extension-aware clipboard paste now performs the same candidate
validation; `artifacts/feature-acceptance-a2ec5efb0ad1/summary.json` verifies
rejection before mutation and successful unambiguous and equal-data pastes.
Other edit paths can still discover such ambiguity only at save. Opaque-resource
merge has the bounded project-level semantics in `docs/interchange-operations.md`;
clipboard resource transfer has the semantics in `docs/archive-transfer.md`. The focused cases in
`artifacts/feature-acceptance-e57fec059ac3/summary.json` and
`artifacts/feature-acceptance-4cb5b47a3915/summary.json` verify those bounded
paths, not every source format, larger history permutation or resource case.
