# Note array preservation investigation

The bridge implements a restricted `directPitches` extension path; other
unknown note-array fields remain guarded. The focused native MCP cases in
`artifacts/feature-acceptance-1de6c1d0abc4/summary.json` verify retained fields,
set/clear history, clone/reopen, duplicate positions and unsupported-operation
guards on synthetic AI projects.

## Direct-pitch probe

Run `python tools/check_note_array_extensions.py --case preservation.note_pitch_array_probe`.
The runner uses a fresh MCP stdio server and the private native desktop. It
creates and closes its own project and does not open a MIDI device.

In receipt `artifacts/feature-acceptance-770a00324d1b/preservation.note_pitch_array_probe.json`,
one AI note serialized direct pitch points as `{pos: 100, value: -900.0}` and
`{pos: 300, value: -700.0}`. Upserting tick 100 changed its serialized value
to -800.0 while tick 300 stayed unchanged. Clearing [90, 110) left the point
at 300. The run closed its session and passed the runner cleanup. This is a
single ordinary project probe, not proof of unknown-field roundtripping.

The native engine can materialize intermediate pitch samples, as documented in
`score-operations.md`. This probe does not establish whether generated points,
replacement, note edits, duplication, split/join, undo/redo or clone preserve
point identity. Phoneme positions were absent in this fixture. Position-only
matching is therefore not claimed as native identity; the later restricted
implementation uses selected ticks as an explicit bridge policy.

## Extended transition observations

Receipt `artifacts/feature-acceptance-480ae99ab11f/preservation.note_pitch_transitions.json`
records one AI note and native serialization after each operation. This is a
diagnostic run, not an assertion that every possible identity transition is safe.
The `note_update` evidence entry was mutated by the later fixture construction;
the corresponding saved VPR and the clone/reopen entries contain no `x_probe`.
The runner now deep-copies its evidence before constructing the fixture; the
corrected transition probe and cleanup passed in
`artifacts/feature-acceptance-c76ddf7a946f/summary.json`.

* Inserting pos 200 produced points 100/-900, 200/-800, 300/-700; replacing
  with pos 100/63 and 400/64 produced 100/-600, 400/-500. No additional point
  appeared in these set operations. A point move was not separately tested.
* Clearing [90, 399) removed 100 and retained 400; undo restored both and redo
  restored only 400. Exact-boundary clear [100, 400) failed the wrapper's
  native readback in `artifacts/feature-acceptance-6eb15e22889c/`; this is a
  failed operation, not evidence for either inclusive or exclusive semantics.
* Moving the note to 100 while changing its pitch preserved relative points
  100/-900 and 300/-700; save, clone, reopen and duplicate preserved those values
  in this fixture. The duplicate was a distinct note, not the same identity.
* Splitting at absolute tick 480 produced first-note points 100/-900, 300/-700,
  1340/`ZeroPitch`, and second-note points -280/-900, -80/-700,
  1540/`ZeroPitch`. Joining produced 100/-900, 300/-700, 1920/`ZeroPitch`.
  These generated points and negative positions rule out naïve positional
  copying for split/join. Collision and metadata provenance remain unproved.
* The old host rejected a copied VPR with `x_probe` on a direct-pitch item; its
  source bytes remained unchanged. The updated path opened and preserved that
  fixture in `artifacts/feature-acceptance-1dec42d402a5/summary.json`.

Treat same-position upsert, replacement, split/join and history restoration as
different identity decisions: neither matching solely on value nor copying
metadata to generated points is justified by these observations. Unsupported
transitions were guarded at that observation checkpoint; the later restricted
set/clear and note/part-copy validations are described below.

## Native clear boundary probe

`python tools/run_pitch_clear_native_probe.py <synthetic-vpr>` launches
`tools/probe_pitch_clear_native.ps1` on a private desktop. The launcher accepts
only the synthetic `feature-*-pitch-transitions-replace.vpr` fixture under
workspace `output`; that fixture has one AI note with native points at positions 100 and 400. The probe opens an
independent session for every case and writes separate output VPRs. It calls
`WIVSMNote.ClearDirectPitches` and `Commit(true)` directly, then reads points,
undoes, redoes, and inspects the saved redo serialization. No device is opened.

Receipt `artifacts/pitch-clear-native-08cb8e42a1df.json` shows that in this
fixture native clear treats both supplied endpoints as inclusive: 100..400
removed both points, 100..100 and 99..100 removed 100, 400..401 removed 400,
and 90..399 removed 100 but retained 400. Native full-range sentinels removed
both. Undo restored both and redo restored the cleared result in each case;
serialized redo agreed (empty pitch array was omitted). These observations
explain the wrapper's exact-boundary readback failure, rather than proving every
native edge case.

For the wrapper's integer-tick half-open contract, partial clears now pass
`begin` and `end - 1`, retaining the native sentinels for full clear. The
validation guarantees `end >= begin + 1` and checks the complete point set while
staged, then again after commit. The MCP cases in
`artifacts/feature-acceptance-ecd0ad6f2b5c/summary.json` pass boundary, invalid
and no-op intervals, native history, full clear and saved-project reopen. This
fix alone did not enable unknown note-array fields; the later restricted
extension path is described below.

## Further integration work

### Item observer and proposed restricted transition helper

`tools/run_pitch_item_observer_probe.py` runs `tools/probe_pitch_item_observer.ps1`
on a private desktop with the existing synthetic replace fixture. Receipt
`artifacts/pitch-item-observer-8289ec7c9157.json` records set, clear, duplicate,
split and join, with staged, committed, undo and redo snapshots. In this probe,
`VSMDirectPitchData` exposes no `CppObjPtr`; `DidUpdateDirectPitch` notifications
identify notes, not individual points. This is not evidence of native item identity.

The expected-success extended-input regression
`preservation.note_pitch_extension_roundtrip` was red on the previous host:
`artifacts/feature-acceptance-63223b91968a/summary.json` records rejection at
`project_open`, followed by successful cleanup. Its later clear and history
assertions did not run. Invoke it directly using
`python tools/check_note_array_extensions.py --case preservation.note_pitch_extension_roundtrip`.

`native/ProjectArchiveNoteArrays.cs` and `ProjectArchiveNoteIntegration.cs`
now define an identity-bound note state with complete point-set validation and
transactional history. For the supported operations, an upsert at the selected
tick retains its unknown fields, replacement creates fresh points without the
old fields, and clear removes fields together with points. This is a bridge
contract, not evidence of a native point object. Unknown point state is validated
against the native note before mutation and again while staged and on history
restoration; save overlays it only onto matching native output. Split/join,
deletion, clipboard, source-track merge and media capture remain guarded while
this state is tracked. The updated host passed the focused
roundtrip and duplicate-tick rejection in
`artifacts/feature-acceptance-1de6c1d0abc4/summary.json`. A mixed controller and
direct-pitch extension fixture retained both fields and preserved the respective
guards in `artifacts/feature-acceptance-97ee96429bd9/summary.json`.
An emptied tracked map remains attached for the session so undo can restore the
extensions; its operation restrictions remain until that session is reopened
from a saved project with no remaining direct-pitch item extensions.

The `note.duplicate` and `part.duplicate` paths now validate the complete source
and copied native point sets and deep-copy item metadata into the returned note
identities. Child notes in a part are matched by unique semantic signatures,
not collection order. The synthetic two-note, four-marker case in
`artifacts/feature-acceptance-970ae8c4e0d2/summary.json` passed source checks,
undo/redo and save/reopen. An ambiguous-signature fixture was rejected at open,
not on the duplicate path. The later track duplication and identity-preserving
track update/reorder and part update/move cases passed in
`artifacts/feature-acceptance-5b8f6372f11d/summary.json`; cross-track part move,
including a pre-mutation ambiguous-destination rejection, passed in
`artifacts/feature-acceptance-17fec2e1ace1/summary.json`. Split/join and deletion
remain guarded; generated `ZeroPitch` points and negative ticks are not assigned
metadata by guessing their provenance.
