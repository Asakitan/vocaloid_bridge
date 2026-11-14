# Native VPR unknown-data preservation

The same preservation path applies to VOCALOID7 `.vprx` archives. Native
open/import, save and revert retain tracked extensions and embedded resources;
the original-file overwrite guard applies to both suffixes. Offline patch and
note-composition outputs accept `.vprx`; native-assisted composition requires
VOCALOID7. A suffix change is not a project schema conversion. Session 51 covers
uppercase input, an unknown root field, a binary resource and source-byte
preservation through native open/import, revert and save.

## Note Skill and Attack/Release

On supported extension-bearing projects, `note_skill_set` and
`note_skill_reset` use the existing note-owner and history protection. Unknown
fields inside the target `singingSkill` or `dvqm` subtree cause rejection;
unrelated note, curve, controller, automation and ZIP resource data are
preserved. AI notes with existing Attack/Release reject these edits, and AI
DVQM writes are rejected even through direct native reflection because native
history cannot reliably preserve both representations. V6 and V7 tests cover
set/reset, undo/redo, save/reopen and the guarded conflict fixture.
Clearing an already-empty Attack/Release is a read-only no-op and is allowed on
extension-bearing projects without changing the archive, history or references.
The explicit AI `bridge_metadata` storage keeps Attack/Release annotations in
the note-owned `vocaloid_bridge_ai_dvqm_v1` extension, separately from native
`dvqm` and `singingSkill`. It participates in the existing identity and history
journal; it is not an audible native AI parameter. Unknown selection fields
block edits rather than being discarded.
Native open and file-level VPR output reject an AI note containing both a
nonempty Attack/Release object and a `singingSkill` object. The file-output check
runs before the destination is created, including for `score_patch` and
`score_replace_notes`. V6/V7 native reopen of a copied project with both
representations lost the Singing Skill state.

Use `score_inspect` to inspect the conflicting note, then use `score_patch` to
remove either complete subtree in a separate VPR. For example, the following
operation keeps Singing Skill and removes both Attack and Release from track 0,
part 0, note 0:

```json
[{"op":"remove","path":"/tracks/0/parts/0/notes/0/dvqm"}]
```

Removing `/tracks/0/parts/0/notes/0/singingSkill` instead keeps the DVQM record
and deliberately discards those skill weights. Use the indices reported by the
open error, include every conflicting note in the same patch, and choose the
representation explicitly. Other data and the original VPR are preserved.
V6/V7 conflict rejection, both repair choices and resource preservation passed
in `artifacts/feature-acceptance-8936678672bb/summary.json` and
`artifacts/feature-acceptance-b48c40ba8f6a/summary.json` respectively.

## Session-Owned Freeze

Freeze and unfreeze are permitted on extension-bearing projects using the
existing session-owned cache and authoring-state restoration. Focused V6/V7
tests preserve unrelated note, pitch, controller, automation, effect and ZIP
resource data across save, clone, reopen and undo/redo after unfreeze. Other
unknown-field combinations remain subject to their existing identity checks.

## V7 track identity and AI edits

V7 stores primary and secondary voices on the track. Its archive identity
signature now includes both track compIDs and checks them against native IDs;
different-voice tracks with otherwise identical shapes are no longer falsely
rejected. Identical signatures with conflicting opaque fields remain errors.
The snapshot voice-table and structural checks remain unchanged.

Track volume and pan event positions/values also distinguish otherwise equal
tracks. They are checked against the native automation arrays before use;
unknown event fields do not contribute to identity. Equal known identities
with conflicting opaque data still fail instead of being matched by index.
Volume and pan edits on extended multi-track projects preflight an isolated
native clone, including save and archive overlay. Edits that collapse distinct
identities with conflicting opaque data leave the source state/history intact.

V7's `soloState` also participates in track identity and is checked against
the native track on load and snapshot. Tracks distinguished by `Off` versus
`Defeat` can carry different opaque fields and survive reorder/reopen. Before
an identity-changing `track.update` on an extension-bearing V6 or V7 project,
an isolated clone is edited and saved with archive preservation; a resulting
identity collision is rejected before changing the source session. Identical
signatures with different opaque fields remain rejected. V7 evidence:
`artifacts/feature-acceptance-ae04d8be8cbc/summary.json`; V6 evidence:
`artifacts/feature-acceptance-9922cd58c241/summary.json`.

`batch.run` dispatches each child through its own archive preflight. `ai.status`
is read-only; `ai.generate` admits the existing performance preparation and,
when requested, pitch mutation contracts. Selected-note pitch preservation
uses one native pitch transaction and the existing note-array metadata hooks;
it does not bypass unknown-field protection. Existing curves require explicit
overwrite authorization before generation.

Session 46 verifies seven read-only identity cases and one real V7 GekiyakuV
stdio roundtrip: parameters, two-note pitch preservation, undo/redo, rejection
of implicit overwrite, and root/track/part/note/voice/effect/parameter extensions
plus an extra ZIP member survive save/reopen. Source bytes remain unchanged.
Evidence: `artifacts/feature-acceptance-78bc268d0a70/summary.json`. This is not
acceptance of every possible V7 extension schema or mutation combination.

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
saved snapshot. Score mutations beyond direct controller edits and the tested
track/part duplicate and part split/join paths, plus clipboard transfers on
projects with controller extensions, remain guarded until their mappings are established;
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

### Timeline boundary probe

The ordinary-project private native probe `preservation.timeline_boundary_probe`
(`artifacts/feature-acceptance-e64467f2aa7f/preservation.timeline_boundary_probe.json`)
exercised insert and delete at tick 1000 for 500 ticks with both `include_tempo`
settings. In that fixture a part moved from tick 7680 to 8180 or 7180, with
its notes and controller data included in the saved snapshots. Inserting moved
the 3/4 signature from bar 2 to bar 3 even when tempo movement was disabled.
With tempo movement enabled, deletion changed the event at tick 1000 from 130
BPM to 150 BPM, removed the event at 1200, and moved the event at 2000 to
1500; the event originally at 1500 supplied the resulting 1000 value. All four
cases restored the exact saved track/master snapshots on undo and redo. These
are observations of serialized values, not proof of native event identity or of
extension migration. Nonaligned meter mapping, collision ownership, controller
identity, failure rollback, and extension-bearing clone/reopen required
independent proof at that checkpoint. Changed event-extension time edits remain
guarded; the later unchanged-map path is described below.

The separate private-desktop pointer probe is reproducible by running the
boundary case above and then `python tools/run_timeline_identity_probe.py
--fixture output/feature-RUN-ID-NNN-boundary-before.vpr`. The launcher accepts
only a boundary fixture in the workspace output directory and never uses the
interactive editor. The observed run is
`artifacts/timeline-identity-probe-be167ab09a30.json`. For the deletion with
tempo enabled, the original tick-1500 tempo object moved to 1000 while the
original tick-1000 and tick-1200 objects disappeared. Rollback and undo
restored those exact observed addresses, and redo restored the moved-object
state. In the insert cases the moved meter and tempo objects retained their
addresses; the moved part, note and its two controller events retained their
addresses in all four cases. These values agree with the serialized boundary
probe. Address equality in this one process does not establish ownership after
address reuse or general event notification behavior.

With `--omit-end-tempo`, the launcher creates a synthetic variant without the
tick-1500 tempo. In `artifacts/timeline-identity-probe-7f40b43c2298.json`,
deleting 1000–1500 generated a new tick-1000, 140 BPM event instead of moving
the original tick-1200 object. After rollback, repeating the operation created
the equivalent event at a different native address. Thus candidate object
addresses cannot map generated events in the real transaction; the generated
boundary event must not automatically inherit unknown fields from either the
deleted tick-1000 event or the tick-1200 event. Its extension policy and mapping
need an explicit tested contract before that deletion case can be enabled.

A private-desktop observer probe now records all native notification types and
object addresses together with before, staged, rollback, committed, undo and
redo snapshots. Run `python tools/run_timeline_observer_probe.py --fixture
output/feature-e64467f2aa7f-002-boundary-before.vpr`, adding
`--omit-end-tempo` for the generated-boundary variant. Receipts
`artifacts/timeline-observer-probe-dc6f5147dc07.json` and
`artifacts/timeline-observer-probe-2455465b7ff1.json` show no observer events
during the first staged edit or rollback in these cases; notifications arrived
on commit and during undo/redo. For deletion with the end tempo present, commit
reported removal of the two deleted tempo objects and position updates. With
the end tempo absent, commit reported insertion of the newly generated tempo,
then removal of the two original tempo objects, and position updates. Undo and
redo reported corresponding inverse and repeated structural notifications.
These are bounded observations: the staged candidate has no notification log
from which to distinguish a removed object and a newly allocated object that
reuses its address. The probe does not establish same-tick overwrite semantics,
nonaligned meter collisions, or address reuse. These were blockers at that
investigation checkpoint; the later restricted deletion contract and remaining
generation guards are described in `docs/timeline-delete-21.md`. The existing
audio and controller transfer guards are unchanged.

The subsequent restricted timeline transaction captures native identities and known values
before mutation, applies the operation to a candidate, establishes an
operation-specific mapping for retained events, validates the entire post-state,
and commits the extension snapshot with native history. Deleted events lose
their metadata; newly generated tempo boundaries inherit none. Additional
evidence is needed for occupied-start meter collisions, address reuse and
untested combinations. The earlier observations alone do not
justify mapping all generated tempo and meter extensions.
The bridge implements a restricted MIDI/AI route: it excludes audio tracks,
controller-event, direct-pitch-item, master-volume-item and track-automation-item
extensions, preflights an independent clone and checks retained track, part and
note identities and expected positions before and after commit. Insertion maps
tested one-to-one tempo/meter event moves. Restricted deletion maps survivors,
discards deleted payloads and assigns no inherited extension to a generated
tempo boundary. Tested unoccupied generated meter boundaries also receive no
inherited fields; occupied-start collisions remain guarded. The focused cases in `artifacts/feature-acceptance-5b8f6372f11d/summary.json` and
`artifacts/feature-acceptance-e8eb9b6496cb/summary.json` pass the tested paths,
history, reopen and source preservation.
The controller-array case also checks timeline rejection, and
`preservation.timeline_audio_guard` prepares an unextended project with an owned
synthetic audio asset before adding an entity extension, then checks that rejected
time edits preserve its audio resources, source files and history. Those guard
cases passed in the same receipt. Whole-part deletion in the ordinary fixture produced only a
part removal notification, with descendants restored via history; see
`artifacts/timeline-observer-probe-6f666cc0d21f.json`.

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
save, reopen and source-independent clone. Later work added restricted tempo,
time-signature, controller, direct-pitch and master-volume event array paths;
other non-entity arrays remain outside this support.

`artifacts/feature-acceptance-f0e3121b86c8/` additionally verifies retained
extensions across title, tempo, loop, tuning, batch-note, VoiceColor and vibrato
changes. True native history commits advance the identity journal; no-op and
non-history synchronization do not add fictitious undo steps. Journal storage
is bounded by the native undo limit.

Only unknown properties are overlaid onto fresh native output. The implementation
retains additional non-native-managed files without overwriting native output;
native-referenced `Project/Audio` assets are not resurrected after deletion,
while members already unreferenced at open are retained as opaque extras. Other
other unsupported array-contained unknown fields are rejected rather than dropped. A
restricted direct-pitch item path is described in `note-array-preservation.md`.
Clone must
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
global-only merges use a staged-and-restored native tempo marker if no other
native history entry exists and no tempo/meter extension transaction is active.
The marker preserves the final tempo and the archive journal shares that native
history entry. The focused metadata-only merge and maximum-tempo case passed in
`artifacts/feature-acceptance-fc6a72130b1c/summary.json`. The focused
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

Controller extension duplication now stages independent copies for native track
and part duplicates. Each tracked lane is checked against both source and
duplicate native tick/value maps before its payload is attached. Other score
mutations remain guarded while controller extensions are live, except controller
edits, part split/join, duplication and history. Split/join map every native
controller by lane and absolute tick, require equal native values and exactly
one source and destination, and reject overlapping identities or changed/lost
points within the staged transaction. A native unextended probe in
`artifacts/feature-acceptance-10339d63e076/` observed that a split-boundary
point moves to tick zero of the right part and rejoins at its original tick.
The focused runs `artifacts/feature-acceptance-6d389ad715a5/summary.json` and
`artifacts/feature-acceptance-6cc1fd525f8e/summary.json` verify these paths,
including a marked event exactly at the split boundary, copied tracks/parts,
undo/redo, reopen and rejection of overlapping extended controller identities.
Native split may also create a boundary event carrying the preceding value; the
new event starts without unknown fields rather than inheriting the earlier
event's payload. Unextended lanes retain native split/join behavior. Tracked
controller maps are checked before a native mutation commits.

### Timeline edit investigation (historical baseline)

`preservation.timeline_native_probe` exercises private AI projects with notes,
controller points, nonzero tempo events and a meter change, both values of
`include_tempo`, crossing-boundary rejection and insert/delete undo/redo. In
`artifacts/feature-acceptance-a59c6e1025a7/summary.json`, inserting 1920 ticks
at tick 1920 moved a part from 3840 to 5760 and the meter change from bar 2 to
3; deleting the range restored those positions. With `include_tempo=false`,
tempo ticks 0/1920/3840 stayed fixed; with it true they became 0/1920/5760
and then returned on deletion. The tempo event exactly at the insertion point
stayed there. This is one native fixture, not a general identity rule. The
crossing MIDI/AI boundaries were rejected before mutation; the probe checks
project snapshots and history. Both history directions passed in this fixture.

The historical `preservation.timeline_extension_guard` was a guard baseline,
not evidence of extension-aware timeline support. The passing
`artifacts/feature-acceptance-46720e1ebe0a/summary.json` checks both edits and
both tempo options on a project with track, part, note, tempo and meter unknown
fields: the event-extension guard rejects them, history remains unchanged, and the
source, save, clone and reopen retain the fields. Controller-extension and
extended-audio write guards remain unchanged. The current insertion and
restricted deletion paths are described above and in `docs/timeline-move-20.md`
and `docs/timeline-delete-21.md`. Session 22 added the bounded unoccupied meter
boundary mapping in `docs/timeline-meter-22.md`; occupied-start collisions and
other unverified combinations still require evidence.

### Master volume event metadata

`ProjectArchiveMasterAutomation.cs` binds unknown fields on master-volume events
to their explicitly selected native ticks and values. Upsert preserves fields on
an existing tick; replacement preserves existing selected events and tick zero,
removes fields for removed events, and assigns no old fields to new events.
History snapshots and output overlays validate the full native map. The focused
case in `artifacts/feature-acceptance-5b8f6372f11d/summary.json` covers edit,
removal/recreation, undo/redo, clone/reopen, duplicate ticks and source
preservation. A mixed master-volume/tempo extension fixture passed in
`artifacts/feature-acceptance-551c645ece17/summary.json`. Time edits with this
state remain guarded. Track volume/pan extensions now have their own restricted
owner-bound transaction; see `docs/track-automation-21.md`.

### MIDI media entity metadata

Owned AI MIDI clips can carry captured part and note unknown fields in a
versioned clip extension. The bridge verifies unique native note identities,
rejects metadata paths that target native fields or traverse arrays, locks the
clip while testing and importing, and tests the native import plus saved
archive overlay on an independent candidate before changing the target.
`artifacts/feature-acceptance-39ed0d000904/summary.json` covers source and
target preservation, imported and pre-existing history, clone and reopen,
conflicting or malformed metadata, and retained controller and audio guards.
Controller-event and direct-pitch-item extension capture/import and
extension-tracked audio writes are not part of this result. Clip property
updates with this metadata remain guarded.

### Session 22 review boundary

The proposed combined relaxation of track-automation and controller extension
note/score guards was blocked by automatic review due to missing native identity
and rollback evidence and possible silent metadata loss. No guard change was
applied. Prospective cases remain red and standalone; the passing guard case and
precise boundaries are in `docs/track-edits-22.md` and
`docs/controller-notes-22.md`. Earlier controller cross-project, extended audio,
archive-media and direct-pitch deletion guard decisions remain in force.

### File-level event replacement

The separate file-level `score_tempo` and `score_curve` operations now preserve
unknown event fields at an existing selected tick, drop fields with removed
points, and assign no fields from other events to new ticks. Duplicate existing
positions are rejected before output creation. This policy is not native
pointer identity or native history. The focused synthetic and native
open/save cases passed in `artifacts/feature-acceptance-f4c4b6029e12/summary.json`;
the former incorrect field copying remains recorded in
`artifacts/feature-acceptance-da5678235623/summary.json`. Reviewed native
transfer, audio, pitch, track and controller edit guards are unchanged.
