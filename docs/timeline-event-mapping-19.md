# Timeline event mapping: session 19

## Scope and conclusion

The old blanket guard was first narrowed for transactions where each extension-bearing tempo or time-signature map remained unchanged in native identity, position and value. Session 20 subsequently added tested one-to-one insertion moves, described in `docs/timeline-move-20.md`. Generated, deleted or collided extension-bearing events remain guarded because their source-to-result metadata mapping is not established.

## Existing native evidence

`artifacts/timeline-observer-probe-dc6f5147dc07.json` observes a synthetic AI/MIDI fixture using the private desktop probe. For the `[1000,1500)` range with tempo inclusion enabled, insertion retained the original tempo pointers and moved ticks 1200, 1500, 2000 to 1700, 2000, 2500; the event at 1000 remained there. Deletion removed the original 1000 and 1200 events and moved the original 1500 event to 1000. Undo restored the old event pointers and redo restored the resulting pointers. A meter at bar 2 moved to bar 3 on insertion, even when tempo inclusion was false. These are observations for this fixture, not general mapping rules.

`artifacts/timeline-observer-probe-2455465b7ff1.json` uses a synthetic variant without a tempo at tick 1500. Deletion produced a new tick-1000 tempo with the former tick-1200 value; its pointer was distinct from all source event pointers. Rollback followed by the same edit generated a different pointer. Undo and redo preserved the respective observed pre-edit and committed states. This shows value equality or a generated pointer alone does not establish which source metadata should transfer.

`artifacts/timeline-observer-probe-6f666cc0d21f.json` records a separate observation with unchanged tempo and meter positions; its range must be recovered from the original probe invocation before comparing it to the cases above. The observer records object snapshots and notifications, not unknown archive fields or save/reopen evidence.

## Current attempt and remaining evidence

A fresh observation was attempted with `python tools/run_timeline_observer_probe.py --fixture output/feature-4f9bc695e9c8-boundary-before.vpr --start-tick 7680 --end-tick 9600`. The sandbox initially denied the private-desktop log write. After approval, the native probe ran but returned `Native delete failed` at `tools/probe_timeline_observer.ps1:56`; its stderr is `.runtime/VocaloidBridge-dbbd7c7e0e8c4bc290e6cdaeeb9dffda.stderr.log`. The probe emits a result only after all cases succeed, so this attempt produced no observation receipt. No foreground editor, existing MIDI/DAW endpoints, or voice installation was touched.

A future probe must isolate event metadata on each relevant tempo and meter, cover boundary events, generated and collided events, multiple meter boundaries and both tempo-inclusion settings, and compare archive content after commit, undo, redo, save and reopen. Define and validate an explicit policy for source metadata of generated events before mapping changed event routes. Pointer stability within one history instance is not proof of archive identity across reopen. Controller cross-project, extended audio, and metadata-bearing media-update guards are outside this slice and remain unchanged.

## Validated unchanged-map transaction

The session 19 implementation retained extension metadata only when each extension-bearing native tempo or meter map had the same event pointers, positions and values across the staged and committed operation. Duplicate pointers or positions were rejected. Maps without extensions retained native edit behavior. Session 20 extends insertion to tested one-to-one event moves; deletion still requires an unchanged extended map. The candidate preflight executes checks before the real edit; the real mutation uses the existing rollback path on staged failure. Controller, pitch-item and audio exclusions remain.

The session 19 `preservation.timeline_event_unchanged` case placed distinct markers on each tempo and meter event and used `[1000,1500)`: deletion with `include_tempo=false` was the unchanged-map positive case; insertion and deletion with `include_tempo=true` were negative cases under the former guard. It checked history and saved content after rejections, and positive undo, redo, save and reopen. A tempo-only extension case also verified that an unextended meter map could change. The session 19 native build and these cases passed in `artifacts/feature-acceptance-970ae8c4e0d2/summary.json`; the current insertion cases use the session 20 movement contract.

Old-host red baseline: `artifacts/feature-acceptance-6f72924aa999/preservation.timeline_event_unchanged.json` records all three negative edits rejected with unchanged saved content and history, followed by rejection of the intended `time.delete` / `include_tempo=false` positive case by the old blanket guard. The older `timeline_extension_guard` case now uses only `include_tempo=true` edits of `[1000,1500)`, which move its tick-1920 tempo; separate controller/audio/pitch protections are untouched.
