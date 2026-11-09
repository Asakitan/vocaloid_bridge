# Archive transfer investigation

MIDI/AI/Audio clipboard cut/paste and track merge transfer supported entity extensions
with identity-bound paths. Track-inclusive merge and clipboard selections also
transfer bounded opaque project resources. Tested native-managed audio assets
survive the cases below; unsupported non-entity arrays remain separate work.

The private clipboard clones the source project and captures fresh archive bindings in the clone. Its lifetime is independent of the source session. The previous external-operation guard checked only the session supplied to the current call. `artifacts/feature-acceptance-fb8cedfece70/summary.json` confirms that a source with entity extensions could be pasted into a target without them, contrary to the guard then in place; the probe did not inspect the resulting JSON. Native clipboard duplication alone has no extension transfer. The integrated path retains the explicit source selection in its owned snapshot, duplicates those native entities into the target, maps returned identities and unique child signatures, and journals the extension transfer. Clipboard clear releases its snapshot observer; extended cut journals source removal and retains the snapshot if the cut result is uncertain. Audio track/part extension transfer passed the bounded case below.

Clipboard tracks, parts and notes carry the complete opaque project-resource
set from the independent snapshot; the bridge does not infer which entity owns
a member. Cut keeps project-scoped resources in the source. Paste shares equal
path/equal bytes, rejects differing bytes, case aliases, prefix and native ZIP
collisions, and checks a candidate archive before target mutation. Added copies
and entity changes share the native undo/redo journal. Resource-only sources
use the same path even with no entity extension. The old binary rejected the
cut in `artifacts/feature-acceptance-1a8e9b24ebfe/summary.json`; the maintained
case passed in `artifacts/feature-acceptance-5f7c71ba55ed/summary.json`, covering
AI track/part/note copies, note cut, source close, resource sharing and three
conflict types, undo/redo, save/reopen and the resource-only case. The updated
`artifacts/feature-acceptance-9cc33036cca5/summary.json` also verifies pasting
the cut note and rejecting a collision with a native WAV before target mutation.
Native audio asset ownership and all possible file combinations are not established by this case.

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

The transfer uses detached metadata copies, source snapshot indices rather than clipboard enumeration order, semantic unique child matching with explicit position offsets, and a target observer and archive state even when the target initially has no extensions. Native changes and archive journal changes are bracketed together. Extension-aware paste verifies an independent candidate before target mutation; the tested identical-data duplicate remains allowed. Broader repeated-paste ambiguity, native audio resource combinations and failure permutations require additional fixture tests. Project-level fields and other non-entity arrays retain separate conflict and ownership semantics.

## Focused native clipboard observation

On the existing isolated MCP host, a synthetic AI project contained two notes at relative ticks 100 and 500. Copying the notes with indices `[1, 0]`, closing the source session, and pasting into a separate AI part with `offset_tick=300` returned two pasted notes. Readback showed the two notes at ticks 400 and 800 with their original pitches and lyrics. The clipboard was then cleared and the target closed. This verifies those values and source-close lifetime for this one case only: the public list sorts the resulting notes, so it does not establish clipboard iteration order, native pointer identity, `PushTrack`/`PushNote` return identity, or `PushParts` correspondence. No unknown-field migration was exercised.

An exploratory private-desktop reflection probe exited with access violation `0xC0000005` in `WIVSMTrack.get_Name` after several clipboard pushes; the stderr is `.runtime/VocaloidBridge-d9536331f89d4584834f1c17c698b0e0.stderr.log`. It did not produce a successful receipt or isolate which track wrapper was invalid. The failing batch probe remains only in ignored `.runtime`; the maintained launcher requires an explicit bounded mode and its native probes enforce a private desktop.

`tools/run_clipboard_identity_probe.py --direct` ran `tools/probe_clipboard_direct.ps1` on a private desktop against two independent opens of the synthetic AI fixture. The machine-readable receipt `artifacts/clipboard-direct-probe-20261110.json` records successful direct target `DuplicateNote`, `DuplicatePart`, and `DuplicateTrack` calls using source-session objects, distinct returned native pointers, and commits. The copied note retained pitch and lyric at the requested tick, the copied part retained two notes at the requested absolute tick, and the copied track retained two parts. This supports pairing each directly selected snapshot object with its duplicate return, without relying on clipboard enumeration order. It does not establish equivalence for all fields, audio resources, source-close/clone lifetime, unknown-field migration, undo, or failure rollback.

`tools/run_clipboard_identity_probe.py --track-one` isolates one `PushTrack` on a fresh private-desktop process. Its receipt `artifacts/clipboard-track-one-probe-20261110.json` records the same source pointer and name before and after the push. `GetTrack(0)` returned the same name but a pointer different from the push return pointer. The push return was not dereferenced, and a second push was not attempted; the earlier access violation remains unlocalized.

The identity probes require the locally generated `output/clipboard_probe_synthetic_20261110.vpr` fixture; that ignored output is not included in a fresh checkout. The maintained archive-transfer checks construct their own synthetic inputs and do not depend on this exploratory fixture.

## Transfer helper

`native/ProjectArchiveTransfer.cs` contains a transfer helper for MIDI, MIDI AI and Audio tracks and parts, and MIDI notes. It requires an independent source snapshot, an initialized target observer and identity transaction, and pairs child entities by unique semantic signatures. Track mapping occurs after offsetting its parts; direct part and note transfers pass their offset to the helper. Clipboard and track-inclusive merge transfer opaque files as project-level resources. The caller brackets the native change and archive journal together. Clipboard acceptance evidence is tracked in the session log.

Merge uses the same helper and `ScoreMutate`, combines disjoint or equal source root/master unknown fields and rejects conflicting values before mutation. New nested leaves are preflighted against an independent native target snapshot; missing parents and native output collisions are errors. The complete extension-aware merge is performed and saved on an independent candidate first, so the tested indistinguishable-track conflict is detected before changing the real target. A merge with added opaque resources additionally packs and checks the candidate ZIP. Root/master payloads and opaque resource mappings participate in the same undo/redo journal as entities. A global-field or resource addition requires a native history entry. Tempo and time-signature extensions have tested merge mappings; controller extension transfer and other unsupported array-contained fields remain guarded. The session 13 and 14 receipts cover the tested resource, tempo and clipboard paths; they do not prove all source formats or resource combinations. Other edit paths have not yet received the same ambiguity preflight.

The transfer helper now also copies a MIDI part's retained controller-event
payload into independent lane dictionaries and cloned JSON values. It validates
each retained lane against both native parts before attaching the payload to the
new native identity; a part offset changes the part position, not the relative
controller ticks. Notes transferred alone do not carry their containing part's
controller lanes. This implementation remains behind the controller transfer
guards pending integration and a focused native acceptance run; it is not yet
evidence of clipboard or merge support.
`tools/check_controller_transfer.py` defines an independent synthetic AI
acceptance scenario for track, part and note clipboard selections, source cut
history and closure, clipboard clear, offsets, target history, merge conflict,
merge history, delete/recreate, source-file preservation and save/reopen.
The scenario has not yet been run against the modified host.

## Audio transfer implementation and focused validation

The preserved clipboard path maps Audio tracks and parts by unique native
identities and part signatures, with detached extension payloads. Referenced
WAVs remain native-managed; opaque archive members retain the existing
project-scoped copy and collision rules. A private ordinary-track probe imported
a synthetic mono WAV, closed the source, pasted and cleared the clipboard, then
saved and reopened the target; the exported original matched the input bytes.
`tools/check_archive_audio_transfer.py` passed in
`artifacts/feature-acceptance-b0b2d367967f/summary.json`: two distinct
same-named synthetic files and distinct processed WAVs, track and part cut,
source close, clipboard clear, source and target undo/redo, opaque conflict,
merge, save/reopen and byte-for-byte native asset export. Native-managed files
remain native-owned and referenced snapshot/import directories remain alive
according to the existing session lifecycle; the test does not prove every
audio processing or collision permutation.

The old-host baseline `artifacts/feature-acceptance-0c6ca115f949/summary.json`
verified both original and distinct processed asset bytes in the first synthetic
source before the expected old MIDI/AI-only paste guard. Cleanup passed. It does
not validate the modified source or the later scenarios in the acceptance case.
