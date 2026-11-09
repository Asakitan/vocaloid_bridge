# File-note identity investigation (session 25)

## Scope and evidence

`tools/check_file_note_identity_25.py` constructs an isolated synthetic AI VPR containing ordinary notes with distinct unknown markers. It calls `ProjectStore.edit_notes`, checks that the source and an unrelated archive member are unchanged, and expects a proposed tick identity policy. It intentionally does not contain direct-pitch extensions, use real projects, invoke native operations, or change the editor.

The old implementation returns markers A, A, A at ticks 0, 480, 960 rather than A, B, none. It also defaults all three velocities to the first note's 70 even though the second original note had 90. Explicit language and phoneme values are applied, and the unsorted input is sorted by tick. The probe exits 1 as a red regression. This test establishes file transformation behavior only, not native acceptance or identity.

## Identity and semantics

The existing API takes replacement notes, not identity tokens. A selected starting tick is an explicit possible file-level matching policy, not proof of native object identity: it preserves an unchanged tick but treats a moved note as deletion plus insertion, and reuse of a tick could attach stale metadata to a different note. Duplicate original ticks require rejection or an explicit identity contract; source index and musical content are likewise ambiguous under insertion, sorting and edits. Explicit caller-supplied old-note identity plus one-to-one validation would distinguish moves, but requires an API contract and ambiguity handling. Without a defensible mapping, rejecting ambiguous preservation is safer than silently copying unknown metadata.

New AI notes require a validated clean native baseline, not a copied arbitrary populated note. `_EDITOR_AI_NOTE` supplies observed defaults only for an empty AI part; extending its use requires separate native roundtrip and audio evidence. Existing code recursively merges caller `raw` before overwriting reserved fields; velocity and language default from the prototype unless supplied, phoneme defaults to an empty string, lyric defaults to empty, and allowed language IDs are checked against `aiVoice.langIDs` when present. A change in prototype policy can therefore change singing parameters, language, and phoneme behavior as well as metadata. Existing phoneme-validity sidecar validation rejects references whose fields no longer match, and remains a distinct constraint. No preservation or synthesis behavior beyond the synthetic file-level observation is established.
