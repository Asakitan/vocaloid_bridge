# JSON Patch phoneme-validity provenance — session 27

## Old behavior and evidence

The 0.18.0 `ProjectStore.patch` applied JSON Patch to the sequence and then
checked sidecar indices and fields, without tracking note identity. In
`artifacts/patch-sidecar-27-9dda41d946cb4cfe856b7b9c79a7b694/receipt.json`
synthetic notes had identical six compared fields but distinct owners A/B.
Insertion, deletion, movement, copying, replacement and track movement could
therefore attach A's invalid flag to B. A failed `test` left no output.

The separate native observation `artifacts/feature-acceptance-f428a8882714/summary.json`
created an invalid note, copied it by JSON Patch, and changed the copy's position.
The original reopened with is_valid_phonemes=false while the copy reopened with
is_valid_phonemes=true: copying sequence JSON alone had not copied the sidecar
flag. This observation was made before the 0.19.0 change; it does not establish
a universal native copy contract.

## Implemented file-level contract

The source sidecar is first validated against the original sequence. JSON Patch
runs sequentially on a private copy. The implementation tracks each sidecar note
by its actual Python object identity while using the installed `jsonpatch`
operations for RFC 6902 semantics, rather than inferring identity from equal
fields. A `move` carries identity and is checked for retained object identity;
a `copy` creates independent note objects with independent copied sidecar entries.
Removed or replaced note objects lose their old entries. Track/part/note indices
are updated from their actual locations after the patch. When a tracked note's
position, duration or number changes, those signature fields are updated.
A change to its lyric, phoneme or language is rejected and must be handled through
the native edit path. New literal notes do not implicitly inherit old entries.

Unknown root and per-entry sidecar fields survive the tested file-level copies.
The sidecar bytes are reused when the computed metadata is unchanged; otherwise
only that member and sequence JSON are reserialized. All validation happens before
exclusive output creation. Note-tree patch operations respect the existing
controller, track-automation and direct-pitch-item extension boundaries. This is
file-level provenance, not a native history transaction or proof of arbitrary
unmodeled metadata.

## Verification and limits

`artifacts/feature-acceptance-2212e75bc34a/summary.json` is the old real-MCP
copy regression: the expected second invalid entry was absent. The current
`artifacts/feature-acceptance-840e52ca3977/summary.json` passed one feature
case plus cleanup, with note copy and track copy/move, original note
position/duration/pitch edits, deletion, replacement, unchanged sidecar bytes,
failure atomicity and native open/save/reopen. Unrelated resource and synthetic
unknown sidecar fields were checked at the file level.

`tools/check_patch_semantics_27.py` passed in memory for multiple references,
copy chains, copy through a temporary subtree, root copy, note movement between
parts, array insertion, escaped pointer keys and failure cases. Guard predicates
were checked using only in-memory examples; no extension-bearing project was
edited or opened.

A broader selected batch `artifacts/feature-acceptance-daac15c8755e/summary.json`
had one failure because its previous test expected a pitch patch to be rejected;
four other feature cases and cleanup passed. That owned synthetic media clip was
identified by ID, name and resolved path and deleted through a separate private
native session. After a dedicated native open/save/reopen proved pitch, duration
and position edits preserve the invalid flag, the old test was updated to check
the positive pitch case and retain lyric-change rejection. The updated case plus
cleanup passed in `artifacts/feature-acceptance-0f1de36b3862/summary.json`.
The batches are separate and are not a full-suite result.

Other voicebanks, malformed/cyclic non-JSON Python inputs, arbitrary array
extensions, every native operation combination, native undo/redo for file-level
patches and pronunciation quality remain unverified. The original session-27
probe scripts record earlier observations and are not release-gate tests.
