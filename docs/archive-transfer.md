# Archive transfer investigation

MIDI/AI clipboard cut/paste and track merge transfer supported entity extensions
with identity-bound paths. Opaque-resource and non-entity-array transfer remain
separate work.

The private clipboard clones the source project and captures fresh archive bindings in the clone. Its lifetime is independent of the source session. The previous external-operation guard checked only the session supplied to the current call. `artifacts/feature-acceptance-fb8cedfece70/summary.json` confirms that a source with entity extensions could be pasted into a target without them, contrary to the required guard; the probe did not inspect the resulting JSON. Native clipboard duplication alone has no extension transfer. The integrated path now retains the explicit source selection in its owned snapshot, duplicates those native entities into the target, maps returned identities and unique child signatures, and journals the extension transfer. Source opaque extra resources and unsupported track kinds are rejected before mutation. Clipboard clear releases its snapshot observer; extended cut journals source removal and retains the snapshot if the cut result is uncertain.

Extended cut checks source opaque resources before removing any source entity.
`artifacts/feature-acceptance-fdeed6a511d6/summary.json` preserves the earlier
missing-guard result; `artifacts/feature-acceptance-adac1d5901d0/summary.json`
verifies the guard, unchanged source session and normal extended cut.

`artifacts/feature-acceptance-b8c01e2d4375/summary.json` verifies AI track,
part and note transfers with offsets, distinct note extensions, source close,
clipboard clear, undo/redo and VPR reopen. It also verifies pre-existing target
undo history across the first extension transfer and a new redo-clearing branch.
`artifacts/feature-acceptance-a21669fbf03f/summary.json` retains the earlier test
failure caused by indexing an absent `tracks` field in an empty VPR; the test
was corrected without changing that historical receipt. The separately scoped
opaque-resource guard case passed on the integrated host. These are bounded
synthetic AI examples, not an assertion for all media or extension formats.
`artifacts/feature-acceptance-e57fec059ac3/summary.json` adds ordinary clipboard
and merge regression, extended cut and merge, source protection and tempo-only
merge. `artifacts/feature-acceptance-4cb5b47a3915/summary.json` covers track,
part and note cut; `artifacts/feature-acceptance-288f3f9a90b8/summary.json`
also verifies that target root/master unknown fields and an existing opaque
resource survive the first clipboard transfer.

The transfer uses detached metadata copies, source snapshot indices rather than clipboard enumeration order, semantic unique child matching with explicit position offsets, and a target observer and archive state even when the target initially has no extensions. Native changes and archive journal changes are bracketed together. Broader repeated-paste ambiguity, audio resources, merge and cut failure permutations require additional fixture tests. Project-level fields, non-entity arrays, tempo metadata and ZIP extras require separate conflict and ownership semantics.

## Focused native clipboard observation

On the existing isolated MCP host, a synthetic AI project contained two notes at relative ticks 100 and 500. Copying the notes with indices `[1, 0]`, closing the source session, and pasting into a separate AI part with `offset_tick=300` returned two pasted notes. Readback showed the two notes at ticks 400 and 800 with their original pitches and lyrics. The clipboard was then cleared and the target closed. This verifies those values and source-close lifetime for this one case only: the public list sorts the resulting notes, so it does not establish clipboard iteration order, native pointer identity, `PushTrack`/`PushNote` return identity, or `PushParts` correspondence. No unknown-field migration was exercised.

An exploratory private-desktop reflection probe exited with access violation `0xC0000005` in `WIVSMTrack.get_Name` after several clipboard pushes; the stderr is `.runtime/VocaloidBridge-d9536331f89d4584834f1c17c698b0e0.stderr.log`. It did not produce a successful receipt or isolate which track wrapper was invalid. The failing batch probe remains only in ignored `.runtime`; the maintained launcher requires an explicit bounded mode and its native probes enforce a private desktop.

`tools/run_clipboard_identity_probe.py --direct` ran `tools/probe_clipboard_direct.ps1` on a private desktop against two independent opens of the synthetic AI fixture. The machine-readable receipt `artifacts/clipboard-direct-probe-20261110.json` records successful direct target `DuplicateNote`, `DuplicatePart`, and `DuplicateTrack` calls using source-session objects, distinct returned native pointers, and commits. The copied note retained pitch and lyric at the requested tick, the copied part retained two notes at the requested absolute tick, and the copied track retained two parts. This supports pairing each directly selected snapshot object with its duplicate return, without relying on clipboard enumeration order. It does not establish equivalence for all fields, audio resources, source-close/clone lifetime, unknown-field migration, undo, or failure rollback.

`tools/run_clipboard_identity_probe.py --track-one` isolates one `PushTrack` on a fresh private-desktop process. Its receipt `artifacts/clipboard-track-one-probe-20261110.json` records the same source pointer and name before and after the push. `GetTrack(0)` returned the same name but a pointer different from the push return pointer. The push return was not dereferenced, and a second push was not attempted; the earlier access violation remains unlocalized.

The identity probes require the locally generated `output/clipboard_probe_synthetic_20261110.vpr` fixture; that ignored output is not included in a fresh checkout. The maintained archive-transfer checks construct their own synthetic inputs and do not depend on this exploratory fixture.

## Transfer helper

`native/ProjectArchiveTransfer.cs` contains a transfer helper restricted to MIDI and MIDI AI tracks, parts and notes. It requires an independent source snapshot, an initialized target observer and identity transaction, and pairs child entities by unique semantic signatures. Track mapping occurs after offsetting its parts; direct part and note transfers pass their offset to the helper. Source opaque extra files are rejected before transfer; their ownership and collision semantics are not implemented. The caller brackets the native change and archive journal together. Clipboard acceptance evidence is tracked in the session log.

Merge uses the same helper and `ScoreMutate`, rejects source root/master unknown fields and opaque extra files before mutation, and restricts extension-aware track import to MIDI/AI. Unknown array-contained fields remain rejected by archive capture. `tools/check_archive_merge.py` exercises offset, distinct note markers, source protection, tempo-only merge and undo/redo with both initially empty and extended targets. The focused case passed in `artifacts/feature-acceptance-e57fec059ac3/summary.json`; it does not prove all source formats or resource combinations.
