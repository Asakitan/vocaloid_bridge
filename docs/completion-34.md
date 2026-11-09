# Remaining Agent functionality — 0.25.0

## Complex timeline operations

The time-edit path now splits crossing MIDI/AI notes and parts with native VSM primitives, and splits audio regions with native duplicate/region operations. It does not call the editor-global phoneme reset service. The operation keeps a single native transaction, moves the retained pieces, removes selected pieces and checks the native curve owner maps. Track/master automation and tempo/meter use the installed native time algorithms, with metadata bound to actual event identities; generated points have no inherited unknown fields.

Audio part identities include region bounds, not just name/base position/duration. This distinguishes two pieces referencing different regions of the same WAV. Crossing edits can produce multiple parts; callers should re-enumerate after an edit rather than retain old part indices.

## Versioned media metadata

The existing `vocaloid_bridge_archive_entities_v1` container now accepts payload versions 1 and 2. Version 2 adds a `Kind`, controller maps, per-note direct pitch, and audio metadata. Existing v1 MIDI payloads remain readable. A captured audio waveform is bound by a SHA-256 digest; its file is locked read-only through import and preflight. The native region is materialized at capture, so imported audio starts with the captured region rather than its source project's absolute timeline.

MIDI and audio import attach their fields before the same native commit as content/effects. Capture requires no pending edits. Native file/identity checks and unknown-field/schema validation remain active. The capture operation now carries all declared AI languages, not only languages occurring in notes.

## Other object arrays

`ProjectArchiveNestedArrays.cs` captures unknown leaves inside schema-described arrays. Entries use owner-relative array roles, available natural keys (`compID`, `langID`, `name`, `id`, `pos`, `bar`) and known-field projections. Unchanged entries are paired first; a unique unmatched natural-key pair can follow a value edit. Indistinguishable conflicting entries fail before commit instead of guessing by index. Primitive arrays contain no object extension leaves and remain native data.

Staged native JSON snapshots reconcile the metadata before commit. Their original native modified flag is restored, their staging state is checked, and temporary directories are deleted. Explicit array edits may remove the selected fields; unrelated array loss raises an error. Undo/redo retain the reconciled immutable maps.

## Transaction completion

Readback now executes before commit so its exception can use native rollback. A failed commit with live staging follows the same rollback path; a failure that has no restorable native staging is marked invalid rather than reported as a successful edit. Metadata-only tempo/meter differences create a native history marker; identical metadata/native maps do not invent one.

## Evidence and limits

The three focused contracts are indexed in `artifacts/completion-34-evidence.json`: timeline edits, media/arrays, and transaction faults/no-op merges. All passed on their recorded final attempts; initial fixture/region-identity failures remain in their original receipts. Final semantic check: 32 files and 211 references, zero errors; Release build: zero warnings/errors. No broad acceptance suite was run.

This implements the stated Agent backlog, not every possible future format or hardware environment. Ambiguous metadata, incompatible native types and native range errors remain errors, not unsupported TODO placeholders. Physical storage faults, external DAWs and hardware MIDI are outside this delivery.

Cleanup removed 525 owned files (7,240,806 bytes), including the stopped old host's exact two C-drive cache namespaces. No pending media journals, private-process temporary directories or locked cleanup files remained. Synthetic VPR/WAV/schema output was removed; JSON receipts remain.
