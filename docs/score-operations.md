# Native Score Operations

`score_edit` calls `EngineHost.EditScore(session_id, operation, options)` on the
existing native host STA. `options` must be a JSON object. The result envelope is:

```json
{
  "session_id": "SESSION_ID",
  "operation": "note.list",
  "native": true,
  "result": {"notes": []}
}
```

Only the installed VOCALOID6 VSM objects are modified. There is no GUI automation,
alternate engine, JSON reconstruction of projects, or audio synthesis in these
operations. The caller opens a session and saves it through the existing project
lifecycle. Original project files are not written by score operations.

## Indices and Bounds

- Track, part, note, tempo, time-signature, and controller indices are zero-based
  snapshots. Re-list after insertion, movement, removal, undo, or redo.
- A part's `start_tick` is absolute. Note `start_tick` and controller `tick` are
  relative to the containing part. Direct-pitch `tick` is relative to the note.
- Time-signature `bar` is the native zero-based bar index, not an absolute tick.
- Tick inputs are nonnegative signed 32-bit integers. Durations are positive,
  bounded by native limits, and new/updated notes must fit within their part.
- Collections are capped at 65,536 items; input curves contain 1..8,192 points
  with distinct ticks. Strings are limited to 16,384 characters and exclude NUL.
- BPM is bounded by the sequence's native minimum/maximum and rounded to native
  hundredths. Controller values and expression fields use native object limits.
- Direct-pitch values are finite fractional MIDI note numbers in 0..127.
  The installed `VSMScore.GetPitchFromRawNoteNumber` converts them to native
  cents relative to A4: `number * 100 - 6900`. Readback uses the native inverse
  `GetRawNoteNumberFromPitch`; for example, 62.25 is stored as -675 cents.
- Wrong track kinds, missing objects, invalid bounds, and native failures are
  errors. MIDI/AI part operations do not accept audio tracks.

## Transactions and References

Score mutations require `Sequence.IsStaged == false` on entry. Commit or roll
back any pending edits made through generic native calls before using this API.
Each successful staged mutation calls native `Commit()` with history enabled,
sets session `Dirty`, and invalidates child references. The session/root reference
is retained. Failed mutation attempts also invalidate children; staged edits are
rolled back and rollback failure is reported explicitly. No save occurs here.
Track and pitch responses are read after commit. A post-commit readback mismatch
raises an error with the session still dirty; it cannot roll back an already
committed change. Redundant track fields are not written and do not create
artificial history entries.

Read/list operations do not set `Dirty` or invalidate references. `undo` and
`redo` call native history methods and set `Dirty`; they fail if history is
unavailable. Engine settings that do not create native history entries cannot be
made undoable by this wrapper. History is not a transaction journal for files.

## Track Operations

| Operation | Options | `result` |
| --- | --- | --- |
| `track.list` | None | `tracks`: track summaries |
| `track.create` | Optional `type` (`Midi`, `MidiAi`, `Audio`; default `MidiAi`), `name` (default `Track`), insertion `index` (default append) | Created track summary |
| `track.update` | `track_index`; one or more of `name`, native palette `color` (0..15), `mute`, `solo`, `bus_no`, MIDI-only `midi_recording` | Updated track summary |
| `track.remove` | `track_index` | `removed`, old `track_index` |
| `track.reorder` | `track_index`, `to_index` in the existing list | Moved track summary |
| `track.duplicate` | `track_index`; optional insertion `index` (default immediately after source), `name` | Native duplicate summary |
| `track.freeze_state` | `track_index` | Native `frozen`, `can_freeze`, and whether the cache is owned by this session |
| `track.freeze` | `track_index` | Render a private native track cache; active only for this session, with authoring settings preserved on save/clone |
| `track.unfreeze` | `track_index` | Release a cache owned by this session and restore editable native playback |

Track summaries contain `track_index`, native `type`, `name`, `color`, `mute`,
`solo`, and `part_count`. Track duplication uses the installed public
`DuplicateTrack(ulong, WIVSMTrack, out string)` overload, not manual reconstruction.
Native track-count limits are checked before insertion and duplication.
The omitted-type default is `MidiAi` for the requested VOCALOID:AI workflow;
clients requiring the previous classic-track behavior must pass `type=Midi`
explicitly. This selects a track type, not a replacement voicebank; assign an
installed AI voice explicitly with `voice.set` before synthesizing a new part.
The installed `TrackColorTable` has 16 entries; `color` is an index, not packed
RGB or ARGB. Invalid colors fail validation before any supplied field is changed.
Unchanged fields are skipped rather than treating native no-op setter results
as failures. Changed color writes must succeed, and all requested fields must
match freshly acquired native getters after commit.

A `track.update` containing only unchanged `name`, `color`, `mute`, `solo` and/or
`bus_no` returns the current summary without changing a clean or already-dirty
state, after checking for pending native edits. Requests containing
`midi_recording` retain the native setter path even when the value is unchanged.
The AI case in `artifacts/feature-acceptance-3fc96299dad5/summary.json` checks
individual and combined no-ops, a real edit and reopen, and pending-edit rejection.
An earlier observation found that an enabled recording flag reopened as false;
the flag is not claimed to persist across reopening.

For VPRs with supported entity extensions, note and part split/join also journal
the opaque fields by native identity. Conflicting join fields or ambiguous
child correspondence cause the native transaction to roll back; see
[project preservation](project-preservation.md) for tested scope and limits.

## MIDI and AI Parts

| Operation | Options | `result` |
| --- | --- | --- |
| `part.list` | Optional `track_index`; without it, all MIDI/AI tracks | `parts`: part summaries |
| `part.create` | `track_index`, `start_tick`, `duration_tick`; optional `name` (default `Part`) | Created part summary |
| `part.update` | `track_index`, `part_index`; `name` and/or `duration_tick` | Updated part summary |
| `part.remove` | `track_index`, `part_index` | `removed`, old indices |
| `part.move` | `track_index`, `part_index`, `start_tick`; optional `to_track_index` (default source) | Moved part summary |
| `part.resize` | `track_index`, `part_index`, `duration_tick`; optional `name` | Resized part summary |
| `part.duplicate` | `track_index`, `part_index`, `start_tick`; optional `to_track_index` | Native duplicate summary |
| `part.split` | `track_index`, `part_index`, `split_tick` relative to the part, strictly inside it | `parts`: original and created part summaries |
| `part.join` | `track_index`, distinct `part_indices` containing at least two indices | Native joined part summary |

Part summaries contain indices, `name`, `start_tick`, `duration_tick`,
`note_count`, `ai`, primary voice IDs/names, `lang_id`, and `ai_lang_ids`.
Moves/duplicates across tracks require matching native track types. Resizing
changes the right edge with native `SetDuration`; it does not silently shift,
delete, or rebuild notes. Voice services initialize through the existing host.

## Notes

All note operations require `track_index` and `part_index`.

| Operation | Additional Options | `result` |
| --- | --- | --- |
| `note.list` | `track_index`, `part_index` | `notes`: note summaries |
| `note.expression_bounds` | `track_index`, `part_index` | Current native part's minimum, maximum and default dictionaries for `expression` and `ai_expression` |
| `note.add` | `track_index`, `part_index`, `start_tick`, `duration_tick`; optional `number`, `velocity`, `lyric`, `phonemes`, `is_valid_phonemes`, `lang_id`, `expression`, `ai_expression`, `is_protected`, `ai_vibrato_enabled` | Inserted note summary |
| `note.update` | `track_index`, `part_index`, `note_index`; one or more of `start_tick`, `duration_tick`, `number`, `velocity`, `lyric`, `phonemes`, `is_valid_phonemes`, `lang_id`, `expression`, `ai_expression`, `is_protected`, `ai_vibrato_enabled` | Updated note summary |
| `note.remove` | `track_index`, `part_index`, `note_index` | `removed`, old `note_index` |
| `note.duplicate` | `track_index`, `part_index`, `note_index`, new `start_tick` | Native duplicate summary |
| `note.clear` | `track_index`, `part_index` | `removed`, remaining `note_count` |
| `note.split` | `track_index`, `part_index`, `note_index`, `split_tick` relative to the part and strictly inside the note | `notes`: original and created note summaries |
| `note.join` | `track_index`, `part_index`, distinct `note_indices` containing at least two indices | `notes`: the containing part's post-join note list |

Note fields are `number`, `velocity`, `lyric`, `phonemes`,
`is_valid_phonemes`, `lang_id`, `expression`, `ai_expression`, `is_protected`, and
`ai_vibrato_enabled`; update also accepts `start_tick` and `duration_tick`.
The default number/velocity/expressions come from the native part. Language comes
from the note/part or the explicitly assigned bank's native language when a new
part has not populated its language cache. Supplying `phonemes` defaults
`is_valid_phonemes` to true. Since 0.22.0, an AI insertion without phonemes uses
the assigned available AI voice and the native language manager, seeded from the
installed editor defaults; no previous note is required. Native CanConvert must
accept the lyric. The full requested lyric, exactly one syllable, valid phonemes,
candidates where available and unchanged surrounding notes are checked. Empty
candidates require agreement from two different seed phonemes. Failures use the
existing score rollback; successful insertion is one undo step. Explicit phonemes
and the existing classic-note context path are retained. An update without
phoneme fields preserves them. See [current evidence](native-authoring-31.md)
and [historical observations](native-note-27.md).

Expression objects patch only supplied native fields, preserving other fields.
Names are case-sensitive:

- `expression`: `Accent`, `Decay`, `BendDepth`, `BendLength`, `Opening`,
  `RisePort`, `FallPort`.
- `ai_expression`: `PitchFine`, `PitchDriftStart`, `PitchDriftEnd`,
  `PitchScalingCenter`, `PitchScalingOrigin`, `PitchTransitionStart`,
  `PitchTransitionEnd`, `AmplitudeWhole`, `AmplitudeStart`, `AmplitudeEnd`,
  `VibratoLeadingDepth`, `VibratoFollowingDepth`.

Integer/float expression fields use `GetMin/MaxNoteExpression` and
`GetMin/MaxAiNoteExpression`; portamento flags are Boolean. Unknown expression
field names are rejected. Language is an integer in 0..255 with native support
still required. Note summaries return indices, timing, number, velocity, lyric,
phonemes/validity/language, protection, AI vibrato flag, and both expression maps.
Native phoneme generation and per-voice language support are not fabricated.
Split/join use the native `DivideNote`, `JoinNotes`, `DividePart`, and `JoinParts`
methods. They do not invoke the editor's post-edit phoneme-reset command.

## Voice Selection

Both operations require `track_index`, `part_index`.

| Operation | Additional Options | `result` |
| --- | --- | --- |
| `voice.get` | `track_index`, `part_index` | Voice summary |
| `voice.set` | `track_index`, `part_index`; MIDI: `voice_bank_id` and/or `secondary_voice_bank_id`; AI: `ai_voice_bank_id` and/or `secondary_ai_voice_bank_id` | Voice summary after native setters and readback |

IDs must be installed IDs accepted by VSM, not display names. MIDI and AI option
names cannot be mixed. Voice summaries contain `ai`, all four IDs and names,
`lang_id`, and `ai_lang_ids`. The existing voice inventory API supplies installed
voice information; this operation does not change licensing or install voices.

## Tempo and Time Signatures

| Operation | Options | `result` |
| --- | --- | --- |
| `tempo.list` | None | `tempos`, `min_bpm`, `max_bpm` |
| `tempo.set` | `bpm`; optional `tempo_index`, `start_tick` | Tempo summary |
| `tempo.remove` | `tempo_index` | `removed` |
| `time_signature.list` | None | `time_signatures` |
| `time_signature.set` | `numerator`, `denominator`; optional `time_signature_index`, `bar` | Time-signature summary |
| `time_signature.remove` | `time_signature_index` | `removed` |

For VPRs with unknown `masterTrack.tempo.events` fields, the selected native
tempo operation carries those fields through moves and value changes; deletion
followed by recreation does not inherit them. Undo/redo and save/reopen have a
focused synthetic test. Tempo-map merge also maps the source event and its
fields onto a shared destination tick, replacing the former target event fields;
the complete native result and history are checked on an independent candidate.

Set with an index edits that event; omitted position preserves its position.
Without an index, position defaults to zero and the event at that position is
updated, or a native event is inserted. Tempo summaries contain `tempo_index`,
`start_tick`, `bpm`. Time-signature summaries contain `time_signature_index`,
`bar`, `numerator`, `denominator`. Numerator/denominator use native limits and
denominator must be a positive power of two. Initial events cannot be moved away
from zero or removed; update their values instead.

## Whole-Timeline Edits

| Operation | Options | `result` |
| --- | --- | --- |
| `time.insert` | `start_tick`, positive `duration_tick`; optional `include_tempo` (default true) | Applied range, `include_tempo`, `track_count` |
| `time.delete` | `start_tick`, positive `duration_tick`; optional `include_tempo` (default true) | Applied range, `include_tempo`, `track_count` |

The range is `[start_tick, start_tick + duration_tick)`. These call the installed
`Yamaha.VOCALOID.WIVSMSequenceExtension.InsertSilence` and `DeleteTime` directly,
not the editor commands. The native helpers include time signatures, master
volume, MIDI/audio parts, and track volume/pan automation. Tempo events are
included only when `include_tempo` is true. Insertion rejects known tick/bar
overflow before mutation.

If an insertion boundary, or either deletion boundary, is strictly inside a
MIDI/AI part, the request fails before mutation with `NotSupportedException`.
The installed helper's crossing-part branch calls `App.GetG2PAManager`, an
editor-owned phoneme service not initialized by the isolated VSM host. Call
`part.split` at each boundary first, re-list indices, then retry the time edit.
No editor singleton is synthesized and no fallback is run. Native audio boundary
handling does not use that MIDI phoneme-reset branch. For projects with tracked
archive extensions, 0.25.0 handles MIDI/AI/audio boundaries and controller, pitch, master-volume and track-automation metadata through the dedicated native transaction. For insertion, tempo and meter extension maps follow the installed
managed helper's one-to-one native moves. Tested deletion maps surviving tempo
and same-boundary-meter events, discards deleted events' extensions, and gives a
newly generated tempo boundary no inherited extensions. A tested generated meter
boundary at an unoccupied begin bar also receives no inherited extensions;
0.25.0 also supports initial-tempo deletion and crossing MIDI/audio part boundaries through native split/move transactions. Occupied-start meter replacement retains and validates the native event identity. Identity, position and
value are checked on an independent candidate and around the actual transaction;
event kinds without extensions retain native behavior. Audio and other unverified
combinations remain guarded. Focused insertion and deletion cases passed in
`artifacts/feature-acceptance-5b8f6372f11d/summary.json` and
`artifacts/feature-acceptance-e8eb9b6496cb/summary.json`; generated meter
boundaries are covered by `artifacts/feature-acceptance-80b1c4779514/summary.json`.

## Selection

| Operation | Options | `result` |
| --- | --- | --- |
| `selection.get` | `target` is `track`, `part`, `note`, `tempo`, `time_signature`, or `controller`; `part` requires `track_index`, `note` requires `track_index` and `part_index`, and `controller` also requires native `type` | `target`, `selected_indices` |
| `selection.set` | `target` is `track`, `part`, `note`, `tempo`, `time_signature`, or `controller`; `part` requires `track_index`, `note` requires `track_index` and `part_index`, and `controller` also requires native `type`; distinct `indices` may be empty; optional `selected=true`, `clear_existing=true` | Selection after native setters and readback |

`target` is one of `track`, `part`, `note`, `tempo`, `time_signature`, or
`controller`. Tracks, tempos, and time signatures use the session list. Parts
require `track_index`; notes require `track_index` and `part_index`; controllers
add the native controller `type`. Part selection here is MIDI/AI only.
Indices refer to that scoped list. With `clear_existing`, entries outside the
provided indices are deselected; otherwise they are unchanged. `selected:false`
deselects the provided entries. This only changes native model selection and
does not focus the editor or synthesize input.

## Controller Curves and Direct Pitch

Controller operations require `track_index`, `part_index`. Except
`controller.types`, they also require exact native enum `type`.

| Operation | Additional Options | `result` |
| --- | --- | --- |
| `controller.types` | `track_index`, `part_index` | `types`: native names and min/max/default values |
| `controller.list` | `track_index`, `part_index`, native controller `type` | `type`, `points`, min/max/default values |
| `controller.set` | `track_index`, `part_index`, native controller `type`, `points` array of `{tick,value}`; optional `replace=false`, `controller_index` to move one selected point with one point and `replace=false` | Updated controller list |
| `controller.remove` | `track_index`, `part_index`, native controller `type`, `controller_index` | `removed`, old index |
| `pitch.list` | `track_index`, `part_index`, `note_index` | `points`: `{tick, value}` |
| `pitch.set` | `track_index`, `part_index`, `note_index`, `points` array of `{tick,value}`; optional `replace` | Updated pitch list |
| `pitch.clear` | `track_index`, `part_index`, `note_index`; optional `begin_tick=0`, exclusive `end_tick` (default note duration) | Updated pitch list |

Controller types in the inspected assembly are `DynamicsHmm`, `Dynamics`,
`PitchBendSens`, `PitchBendHmm`, `PitchBend`, `WeightHmm`, `Breathiness`,
`Brightness`, `Clearness`, `Portamento`, `Growl`, `Exciter`, `Air`, `Character`,
`XSynth`, `Expression`, `S5Air`, `S5Character`. Native acceptance remains
part/voice dependent. Point lists include `controller_index` for controllers.

Controller writes upsert specified ticks without removing unspecified data.
Direct pitch uses `WIVSMNote.SetDirectPitch` and `ClearDirectPitches` inside the
native transaction. Ticks remain note-relative. The interactive part-level
drawing lifecycle did not persist anchors in the isolated host and is not used.
The engine may materialize intermediate samples;
the response is the actual native point list, not a copy of the input array.
No wrapper-generated interpolation or replacement synthesis is used.

Explicit `replace: true` removes all points of the selected controller type, or
clears the addressed note's direct pitch using native clearing sentinels, before
writing. A full `pitch.clear` also uses those sentinels; a partial clear uses the
specified half-open note-relative range. The native primitive includes its end
tick, so the bridge passes `end_tick - 1` and verifies the complete remaining
point set while staged and again after commit. A pre-commit mismatch rolls back.
The native-boundary probe is recorded in `artifacts/pitch-clear-native-08cb8e42a1df.json`;
the actual MCP regression in `artifacts/feature-acceptance-ecd0ad6f2b5c/summary.json`
passes exact and single-tick boundaries, empty and invalid intervals, native
history, full clear and saved-project reopen.
For `pitch.set`, requested anchors are checked in the staged transaction and
again after commit, reacquiring the note for the latter check. A private native
probe (`artifacts/pitch-set-native-5c4bdb0f4c9b.json`) observed staged readback
and rollback after an injected failure; a spontaneous mismatch was not observed.
These checks require every requested anchor to have the correct native value. Readback failures are reported rather
than accepting an empty or shortened curve. Uncommitted failures use the existing
staged rollback path.

For tracked `directPitches` item extensions, the selected tick retains its
unknown fields on upsert; replacement creates new point metadata and clear
removes the fields with the corresponding points. The full point set is
validated against native output. Tested note, part and track duplicates preserve
item metadata through native history and save/reopen. Track update/reorder and
part update/move verify each prior owner and complete point set before commit;
an indistinguishable destination part is rejected before moving or duplicating.
0.24.0 validates selected-owner deletion, note/part split and join, clipboard transfer and project merge. Note pitch joins reject conflicting coordinate/value provenance; generated points have no inherited fields. Media metadata v2 also captures and imports pitch-item extensions. See [current evidence](agent-completion-33.md).

## Part Performance

`performance.get` reports native Robot Voice, Breath, Take, VoiceColor and MIDI
effect-bypass availability, modes, values and native bounds for a selected
`track_index`/`part_index`. `performance.set` accepts `robot_mode`,
`breath_mode`, `breath_type`, `breath_exhalation`, `take_lane`, a
`voice_colors` object keyed by native color name, and a `bypass` object keyed
by native MIDI effect name. Unsupported effects, invalid enums and out-of-range
values are rejected before mutation. Changes use native transaction/commit and
post-commit readback.

Each VoiceColor descriptor also includes `applies_to` (`Midi` or `MidiAi`)
and `applicable_to_current_part`, following the installed editor's classic/AI
parameter mapping. The three `S5` fields apply to AI parts; the other six to
classic parts. Native storage of an inactive field is still supported, but is
not advertised as an audible effect on the current part. Bypass remains a
separate setting.

`artifacts/feature-acceptance-f01a08f3680e/session.breath_audio.json` adds
actual Breath audio evidence on a gapped AI phrase: enabled versus bypassed
difference RMS about 0.01209, exhalation 0 versus 10 about 0.01205, and Rarely
versus Often about 0.00721. Male and Female selections produced identical PCM
in that fixture; their parameter storage is verified, not a gender-specific
audio difference. The selected Breath state and bypass survive save/reopen.

The installed `WIVSMTakeEffect` wrapper exposes one Take-specific value,
`Lane`, with `LaneSetting` bounds and `SetLane`; Take bypass is exposed through
the part's effect API. The 6.13 manual describes Take as pronunciation timing
variation on VOCALOID:AI parts, not a separate collection of lane parameters.
`artifacts/score-parameters-66761d50d26c.json` exercises native lanes 0 and 9
through MCP with Take enabled, verifies lane 9 and bypass after save/reopen,
and asserts different nonzero native PCM with equal formats (difference RMS
about 0.01557). The script authors its own fixture through `score_compose`.
This fixture does not establish the sound of every lane or voicebank.

Robot mode uses the native effect setter and the installed Lua manager, avoiding
the editor's `App` initializer. Script path and timing are runtime-only fields;
the host restores them before part synthesis and mixdown after reopening a VPR.
`artifacts/feature-acceptance-84721c900e94/summary.json` verifies setting and
reopening the fields; `artifacts/feature-acceptance-23de638ffae9/summary.json`
verifies distinct nonzero native Robot audio and a nonzero native mixdown.

## Track and Master Automation

`automation.list`, `automation.set`, and `automation.remove` accept `scope` as
`track_volume`, `track_pan`, or `master_volume`. Track scopes require `track_index`;
points use absolute project ticks and integer native values. List returns the
native minimum, maximum, default and `{event_index,tick,value}` points.

`automation.set` upserts distinct `{tick,value}` points. `replace=true` removes
unspecified nonzero events while preserving the zero-tick baseline unless it is
explicitly updated. `automation.remove` requires `event_index` and rejects the
zero-tick event. All edits use the existing native commit and history path.

For tracked `masterTrack.volume.events` item extensions, a same-tick upsert
retains unknown fields; `replace=true` retains fields for existing selected
events and the required zero event, removes fields with removed events, and
creates new events without prior fields. The complete map is checked against
native values during the transaction and on history restoration and save.
The same selected-tick policy applies to tested track-volume and track-pan item
extensions, bound to their native track owner. Tested track update/reorder,
undo/redo, clone/reopen and ambiguous-owner protection retain the fields.
Timeline edits with these item extensions are implemented in 0.25.0 with native event identity mapping. Ordinary score mutations, selected-owner deletion and native track transfers now use complete owner/point validation; see [0.24.0 contracts](agent-completion-33.md). The master-volume case passed in
`artifacts/feature-acceptance-5b8f6372f11d/summary.json`; the track cases passed
in `artifacts/feature-acceptance-e8eb9b6496cb/summary.json`.

`artifacts/feature-acceptance-4d341970430a/summary.json` verifies editing,
rejection and save/reopen for all three scopes. Actual master and track gain,
stereo pan, and master-volume bypass on stems are measured from native PCM in
`artifacts/feature-acceptance-6e1b905dc259/summary.json`.

## Sequence Settings and History

| Operation | Options | `result` |
| --- | --- | --- |
| `sequence.get` | None | Title, track count, sample rate, read-only `presend_time_sec`, global tempo settings, current tick |
| `sequence.update` | One or more of `title`, `sample_rate`, `global_bpm`, `global_tempo_enabled` | Sequence summary |
| `loop.get` | None | `enabled`, `start_tick`, `end_tick` |
| `loop.set` | `enabled` and/or `start_tick`, `end_tick` | Loop summary |
| `tuning.get` | None | Native `value`, `minimum`, `maximum`, `default_value` |
| `tuning.set` | Finite native `value` | Tuning summary |
| `history.status` | None | `can_undo`, `can_redo`, `max_undo_count`, `staged` |
| `undo` | None | History status after native undo |
| `redo` | None | History status after native redo |

Global tempo is distinct from tempo events. Loop changes do not start playback.
The manual describes project tuning in Hertz; this bridge passes the value
directly to native `SetMainTuning`. The installed wrapper exposes
`PresendTimeSec` as a getter only; this is not an editable pre-send setting.

## Emotion and Timing Mapping

The 6.13 reference manual's Emotion tool applies to classic VOCALOID parts:
its note accent maps to `note.update` with `expression.Accent`, consonant
velocity to the note's `velocity`, and its vibrato controls to the native
`vibrato` operations. Its Timing tool applies to VOCALOID:AI parts and maps to
`phoneme_timing.get/set/reset`, rather than to the AI expression fields.
The AI phoneme edit/save/reopen/render/reset chain has a recorded native result
in `artifacts/score-followup-receipt-208cabf8d914.json`. Classic Emotion audio
and classic-track save/reopen remain unverified with this installation's voice
assets; the field mapping does not imply a classic synthesis result.

## Verification and Remaining Work

The earlier Release host build and real MCP acceptance passed for the then-51
operation names in `artifacts/feature-acceptance-19d5e92a5f26/summary.json`.
The current dispatch has 68 operations; session 06, 07 and 08 receipts cover
the additions, including `note.expression_bounds` and all 19 expression fields
in `artifacts/feature-acceptance-9eec19449679/summary.json`.
The three session-freeze operations pass the real-MCP case in
`artifacts/feature-acceptance-26a71f9b1dc5/summary.json`; see `track-freeze.md`
for the audio and authoring-state boundaries.
Track colors, native no-op handling, direct pitch anchors, clear operations,
history, saved VPR readback, and child-reference invalidation are exercised.
Every enum value, voice and parameter combination is not covered by this result.

The repeatable category check is:

```powershell
./.venv/Scripts/python.exe tools/verify_features.py --category score
```

The separate `tools/check_score_operations.py` remains an additional native
probe. Historical counts are not the current complete-function gate; do not
repeatedly run unchanged passing checks.

## Additional native operations

The following concise contracts complement the detailed behavior in the
sections above. Track, part and note indices refer to the current native state.

| Operation | Options | `result` |
| --- | --- | --- |
| `automation.list` | `scope` is `master_volume`, `track_volume`, or `track_pan`; track scopes require `track_index` | Bounds, default and indexed `{tick,value}` points |
| `automation.set` | `scope` is `master_volume`, `track_volume`, or `track_pan`; track scopes require `track_index`; distinct `points` of `{tick,value}`; optional `replace=false` | Current automation list; replacement retains the zero-tick baseline |
| `automation.remove` | `scope` is `master_volume`, `track_volume`, or `track_pan`; track scopes require `track_index`; `event_index` | Current automation list; the zero-tick baseline is protected |
| `history.rollback` | None | `rolled_back` and `staged` |
| `note.batch_update` | `track_index`, `part_index`, distinct `note_indices`; `transpose` and/or a `lyrics` array | Updated note list; lyrics do not run G2PA |
| `performance.get` | `track_index`, `part_index` | Native Robot, Breath, Take, VoiceColor and MIDI-effect bypass state and bounds |
| `performance.set` | `track_index`, `part_index`; one or more of `robot_mode`, `breath_mode`, `breath_type`, `breath_exhalation`, `take_lane`, `voice_colors`, `bypass` | Updated native performance state |
| `phoneme_timing.get` | `track_index`, `part_index`, `note_index` | Current and original phoneme positions and native ranges |
| `phoneme_timing.set` | `track_index`, `part_index`, `note_index`, `phoneme_index`, `tick` | Updated phoneme positions and ranges |
| `phoneme_timing.reset` | `track_index`, `part_index`, `note_index`, `phoneme_index` | Reset phoneme positions and ranges |
| `time.convert` | `from` is `tick`, `bar`, `sample`, or `seconds`; `value` | Seconds, tick, zero-based bar/beat/clock, sample and sample rate |
| `vibrato.get` | `track_index`, `part_index`, `note_index` | Type, duration, AI enable state and depth/rate events |
| `vibrato.set` | `track_index`, `part_index`, `note_index`; one or more of `type`, `duration_tick`, `ai_enabled`, `depth`, `rate` | Updated vibrato state; supplied event arrays replace that event type |

The following changes were checked against installed managed wrapper signatures.
The integrated host built with zero warnings/errors. A private-session smoke
using `tools/check_score_remaining.py` and
`output/background-demo-07ca3af496-score.vpr` passed time conversion at zero,
unstaged rollback, same-value bus/MIDI recording and sample-rate updates,
batch transpose/lyric and invalid-transpose rejection, batch save/reopen,
phoneme timing read (empty positions), and vibrato read and same-value AI enable,
`None` type and zero duration. A deeper private-session probe set bus 1,
MIDI record-arm false→true, sample rate 44100→48000 and vibrato type, duration,
depth and rate points; native immediate readback passed. Bus, sample rate and
vibrato points survived save/reopen; MIDI record-arm returned to false on reopen
and is a session state rather than a verified persistent setting. A native tempo
value staged through generic access was successfully rolled back. Using a clean
44100 Hz/bus 0 session, a synthesized note's second phoneme position was changed
311→312, saved, reopened and rendered, read back as 312, then reset to its
original 311. Phoneme positions were empty immediately after reopening until
rendering; use the per-host cache isolation build for this check. The combined
changed-rate/changed-bus render failed with `FailedToCreateDseWaveBuffer`.
Session 07 isolated the same failure with a 48000 Hz internal rate and bus 0.
Part synthesis now explicitly requires a 44100 Hz project; this is independent
of the mixdown output rate. Bus 0/1 with 44100 Hz internal synthesis and
44100/48000/96000 output passed. External host routing remains unverified;
see `audio-operations.md` for the corresponding receipts.

- `note.batch_update`: `track_index`, `part_index`, `note_indices`, and at least
  one of integer `transpose` or `lyrics` (one string per selected note). Lyrics
  are written as note text; this operation does not run G2PA or regenerate
  phonemes. Changes are submitted in one native transaction and read back.
- `phoneme_timing.get`, `.set`, `.reset`: select a note with `track_index`,
  `part_index`, `note_index`. Get returns current/original positions and native
  ranges. Set/reset additionally require `phoneme_index`; set requires `tick`.
- `vibrato.get`, `.set`: use the same note selector. Set accepts any of native
  `type`, `duration_tick`, `ai_enabled`, and `depth`/`rate` arrays of
  `{tick,value}`. A supplied event array replaces that event type; an empty
  array clears it. Nonempty depth/rate events passed native readback and VPR
  save/reopen on the tested voice; other voice combinations remain unverified.
- `time.convert`: `from` is `tick`, zero-based `bar`, `sample`, or `seconds`;
  `value` is converted using the sequence tempo map and sample rate. The result
  includes seconds, tick, zero-based bar/beat/clock and sample. Integer inputs
  currently use signed 32-bit bounds.
- `history.rollback` discards pending staged native changes; it reports whether
  a rollback was performed. Normal score mutations already commit or rollback.
- `track.update` accepts `bus_no` and MIDI-only `midi_recording`; `track.list`
  exposes these fields. `sequence.update` accepts `sample_rate` 44100, 48000,
  or 96000; `sequence.get` also returns read-only `presend_time_sec`.

Unimplemented here: markers and metronome (no matching VSM sequence API found),
direct audio-part editing, MIDI/AI conversion, arbitrary left-edge trimming, detailed
vibrato editing beyond the operations above, transport playback, style/preset management,
rendered pitch extraction, and automatic phoneme reset when a time boundary
crosses a MIDI/AI part. These are not substituted with JSON metadata or
UI actions. Other owned modules may expose separate native capabilities.
