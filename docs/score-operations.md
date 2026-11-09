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
| `track.create` | Optional `type` (`Midi`, `MidiAi`, `Audio`; default `Midi`), `name` (default `Track`), insertion `index` (default append) | Created track summary |
| `track.update` | `track_index`; one or more of `name`, native palette `color` (0..15), `mute`, `solo` | Updated track summary |
| `track.remove` | `track_index` | `removed`, old `track_index` |
| `track.reorder` | `track_index`, `to_index` in the existing list | Moved track summary |
| `track.duplicate` | `track_index`; optional insertion `index` (default immediately after source), `name` | Native duplicate summary |

Track summaries contain `track_index`, native `type`, `name`, `color`, `mute`,
`solo`, and `part_count`. Track duplication uses the installed public
`DuplicateTrack(ulong, WIVSMTrack, out string)` overload, not manual reconstruction.
Native track-count limits are checked before insertion and duplication.
The installed `TrackColorTable` has 16 entries; `color` is an index, not packed
RGB or ARGB. Invalid colors fail validation before any supplied field is changed.
Unchanged fields are skipped rather than treating native no-op setter results
as failures. Changed color writes must succeed, and all requested fields must
match freshly acquired native getters after commit.

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
| `note.list` | None | `notes`: note summaries |
| `note.add` | `start_tick`, `duration_tick`; optional note fields below | Inserted note summary |
| `note.update` | `note_index`; one or more note fields below | Updated note summary |
| `note.remove` | `note_index` | `removed`, old `note_index` |
| `note.duplicate` | `note_index`, new `start_tick` | Native duplicate summary |
| `note.clear` | None | `removed`, remaining `note_count` |
| `note.split` | `note_index`, `split_tick` relative to the part and strictly inside the note | `notes`: original and created note summaries |
| `note.join` | Distinct `note_indices` containing at least two indices | `notes`: the containing part's post-join note list |

Note fields are `number`, `velocity`, `lyric`, `phonemes`,
`is_valid_phonemes`, `lang_id`, `expression`, `ai_expression`, `is_protected`, and
`ai_vibrato_enabled`; update also accepts `start_tick` and `duration_tick`.
The default number/velocity/expressions come from the native part. Language comes
from the note/part or the explicitly assigned bank's native language when a new
part has not populated its language cache. Supplying `phonemes` defaults
`is_valid_phonemes` to true. Without phonemes, an existing same-language note (or
the native G2PA input note) supplies the conversion context; the native default
lyric and a native single-syllable candidate are used. The first note in an empty
part requires explicit phonemes. An update without phoneme fields preserves them.

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
| `voice.get` | None | Voice summary |
| `voice.set` | MIDI: `voice_bank_id` and/or `secondary_voice_bank_id`; AI: `ai_voice_bank_id` and/or `secondary_ai_voice_bank_id` | Voice summary after native setters and readback |

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
handling does not use that MIDI phoneme-reset branch.

## Selection

| Operation | Options | `result` |
| --- | --- | --- |
| `selection.get` | `target` plus scope below | `target`, `selected_indices` |
| `selection.set` | Same scope, distinct `indices` (may be empty); optional `selected` (default true), `clear_existing` (default true) | Selection after native setters and readback |

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
| `controller.types` | None | `types`: native names and min/max/default values |
| `controller.list` | None | `type`, `points`, min/max/default values |
| `controller.set` | `points`: array of `{tick, value}`; optional `replace` (default false) | Updated controller list |
| `controller.remove` | `controller_index` | `removed`, old index |
| `pitch.list` | `note_index` | `points`: `{tick, value}` |
| `pitch.set` | `note_index`, `points`: array of `{tick, value}`; optional `replace` | Updated pitch list |
| `pitch.clear` | `note_index`; optional `begin_tick` (default 0), exclusive `end_tick` (default note duration) | Updated pitch list |

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
specified half-open note-relative range and verifies that outside points remain.
After commit, pitch writes reacquire the note and require every requested anchor
to exist with the correct native value. Readback failures are reported rather
than accepting an empty or shortened curve. Uncommitted failures use the existing
staged rollback path.

## Part Performance

`performance.get` reports native Robot Voice, Breath, Take, VoiceColor and MIDI
effect-bypass availability, modes, values and native bounds for a selected
`track_index`/`part_index`. `performance.set` accepts `robot_mode`,
`breath_mode`, `breath_type`, `breath_exhalation`, `take_lane`, a
`voice_colors` object keyed by native color name, and a `bypass` object keyed
by native MIDI effect name. Unsupported effects, invalid enums and out-of-range
values are rejected before mutation. Changes use native transaction/commit and
post-commit readback.

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

`artifacts/feature-acceptance-4d341970430a/summary.json` verifies editing,
rejection and save/reopen for all three scopes. Actual master and track gain,
stereo pan, and master-volume bypass on stems are measured from native PCM in
`artifacts/feature-acceptance-6e1b905dc259/summary.json`.

## Sequence Settings and History

| Operation | Options | `result` |
| --- | --- | --- |
| `sequence.get` | None | Title, track count, sample rate, global tempo settings, current tick |
| `sequence.update` | One or more of `title`, `global_bpm`, `global_tempo_enabled` | Sequence summary |
| `loop.get` | None | `enabled`, `start_tick`, `end_tick` |
| `loop.set` | `enabled` and/or `start_tick`, `end_tick` | Loop summary |
| `tuning.get` | None | Native `value`, `minimum`, `maximum`, `default_value` |
| `tuning.set` | Finite native `value` | Tuning summary |
| `history.status` | None | `can_undo`, `can_redo`, `max_undo_count`, `staged` |
| `undo` | None | History status after native undo |
| `redo` | None | History status after native redo |

Global tempo is distinct from tempo events. Loop changes do not start playback.
Tuning is passed in the native API's value domain without an inferred unit.

## Verification and Remaining Work

The Release host build and real MCP acceptance passed for all 51 operation names.
The final receipt is `artifacts/feature-acceptance-19d5e92a5f26/summary.json`.
Track colors, native no-op handling, direct pitch anchors, clear operations,
history, saved VPR readback, and child-reference invalidation are exercised.
Every enum value, voice and parameter combination is not covered by this result.

The repeatable category check is:

```powershell
./.venv/Scripts/python.exe tools/verify_features.py --category score
```

The separate `tools/check_score_operations.py` remains an additional native
probe. The final MCP result above is the delivery gate; do not repeatedly run
unchanged passing checks.

## Additional native operations

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
changed-rate/changed-bus render failed with `FailedToCreateDseWaveBuffer`; its
cause and audio behavior for changed routing/rate remain unverified.

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
