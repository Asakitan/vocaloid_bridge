# Direct-pitch copy mapping — session 19

The private native observer receipt `artifacts/pitch-item-observer-8289ec7c9157.json` records ordinary native values, not extension transfer. In its one two-point fixture, note duplication preserved both point coordinates and values on the source and destination through staged state, commit, undo and redo. No stable point pointer was exposed.

Splitting at 480 produced negative destination ticks and generated `float.MinValue` (`ZeroPitch`) points on both notes. Joining produced another generated `ZeroPitch` at a different position. Generated points must not acquire unknown fields by value or position alone. Negative tick positions are valid native observations and must not be clipped.

The receipt does not prove extension-bearing copy, part duplication, reordered or repeated positions, metadata history, or save/reopen. The later candidate tests distinct extension markers, source preservation, duplicate tick and ambiguous note rejection, history and reopen as described below. Split and join remain guarded until collision, generated-point and provenance policies are supported by separate evidence.

The controller cross-project, extension-audio and metadata-bearing media-update boundaries remain untouched. The later candidate changes are described below.

## Extended-input native copy observation

`python tools/run_pitch_copy_extended_native.py output/feature-1de6c1d0abc4-138-pitch-ext-input.vpr` ran on a private desktop; receipt `artifacts/pitch-copy-extended-native-9abedbb8a0f3.json` records note duplication at tick 1200 and part duplication at tick 4000. The input contains two distinct `x_identity` markers. For each case, complete native point sets in the source and copy matched at staged, committed and redo states; undo restored the one-source state, and the source archive bytes remained unchanged. The launcher rejects duplicate native positions and compares sorted signed ticks and values, independent of native order.

This probe observes only native point values: native wrappers do not expose the opaque markers. It did not serialize the copies, reopen them, or exercise a duplicate-position input or reordered multi-note correspondence. Existing `preservation.note_pitch_extension_duplicate_tick` checks rejection of duplicate extended positions and source preservation; existing `preservation.note_pitch_extension_roundtrip` checks source-only save/reopen and guards. Neither establishes copied metadata roundtrip. At this evidence checkpoint, copy guards remained in place. The later implementation and rebuilt-host validation are described below.

## Validated copy integration

The session 19 implementation narrowed the direct-pitch operation guard for `note.duplicate` and `part.duplicate`. The existing `ArchiveCopyDuplicate` hook pairs child notes by unique semantic signature, validates the complete tracked point set against both the source and returned native copy, and deep-clones per-point metadata into the copy's archive entry. The central transaction validates tracked owners before commit and on history restoration. Session 20 added tested track duplication and identity-preserving track/part operations; split, join, deletion, clipboard and cross-project paths remain guarded. Native `ZeroPitch` and negative positions are compared as native values and signed tick keys; duplicate positions fail the existing complete-set reader and validator.

`preservation.note_pitch_copy_roundtrip` creates two notes with four distinct nested markers, checks source and copied metadata through undo/redo and save/reopen, and checks the original fixture bytes. The old host correctly rejected its first copy operation; receipt `artifacts/feature-acceptance-89eb15811c5b/summary.json` records this red baseline and cleanup. The rebuilt host passed the copy, duplicate-tick and ambiguity cases in `artifacts/feature-acceptance-970ae8c4e0d2/summary.json`. The ambiguous-signature fixture was rejected at open, so it did not exercise a copy-path conflict.
