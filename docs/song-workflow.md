# Song workflow for agents

The path from an empty session to a mixed WAV with the installed VOCALOID:AI
voices, and the controls that VOCALOID:AI synthesis actually sings. Option names
are exact. `vocaloid_operations` gives the complete contract of every operation.

## Conventions

- Start with `vocaloid_status`: a new host selects the newest installed supported
  engine. On V7, voice, style and performance settings require explicit
  `scope="track"` and affect every part on the track; on V6 they remain part-level.
  V7 uses `take_number` and vibrato `curve_model`, not legacy booleans/take lanes.
  Query native bounds and voicebank `is_ai`/version rather than inferring editor
  track labels from a singer name. The control audio audit below was on V6.

- Time is in ticks, 480 per quarter note. Parts, tempo and automation use
  project ticks. Notes and controller points count from the start of their
  part. Pitch and vibrato points count from the start of their note.
- Pitch is a MIDI note number.
- `lang_id` is 0 Japanese, 1 English, 4 Chinese. `voicebanks` lists the
  `lang_ids` each singer can sing; `native_lang_id` is the singer's own language.
- Output files go to the workspace `output` folder. An existing name is never
  replaced unless `overwrite=true`.
- A VPR is a project, not audio. Only `project_render_part` and
  `project_audio` `mixdown` produce sound; check their results with
  `audio_inspect`.

## Steps

1. `voicebanks`: choose a singer's `comp_id`. `kind` `Dnn` is VOCALOID:AI.
2. `project_create(title, bpm)`: leave `sample_rate` at 44100.
3. `project_edit` `track.create` `{name}`: creates a VOCALOID:AI track.
4. `project_edit` `part.create` `{track_index, start_tick, duration_tick}`: end
   the part at least one beat after its last note. The mixdown stops at the end
   of the last part, so leave room there for the release and any reverb tail.
5. `project_edit` `voice.set` `{track_index, part_index, ai_voice_bank_id}`;
  on V7 add `scope: "track"` (the part index does not restrict the change).
   `installed_voice` in the result names the singer the ID resolves to.
6. `project_library` `style_list` `{query: "<singer name>"}`, then `style_apply`
  `{track_index, part_index, style_id}` (V7 also `scope: "track"`) with the style called
   `<singer name> Default`. A new part starts with Breath bypassed and with no
   audio effects, so without the singer's default style the voice is rendered
   bare.
7. `project_edit` `note.add` `{track_index, part_index, start_tick,
   duration_tick, number, lyric, lang_id}`, one call per syllable. The result
   shows the phonemes that will be sung.
8. Shape the performance with the controls in the next sections.
9. `project_render_part(session_id, output_name)` for a quick check of one
   part, then `project_audio` `mixdown` `{output_name, sample_rate,
   bits_per_sample, channels}` for the deliverable.
10. `project_save(session_id, output_name)`, then `project_close(session_id)`.

`score_compose` is a one-call start for steps 2 to 7: it writes notes given in
beats into a template that already carries the asa default style and returns an
open `native_session`. Continue from step 8 with that `session_id`, and close it
when done.

## Lyrics

One syllable per note. A lyric the native converter does not accept is an
error, not a silent mispronunciation.

| Language | Write the lyric as | Example | Not accepted |
| --- | --- | --- | --- |
| Japanese (0) | kana, one mora or syllable | `ら` | several morae in one note |
| English (1) | a plain word of one syllable | `cat` | a longer word in one note |
| Chinese (4) | unmarked pinyin | `wo` | Han characters, tone numbers such as `wo3` |

- To show other text, for example a Han character, pass both `lyric` and
  explicit `phonemes`. Add the note with the pinyin first to learn its phonemes.
- `project_library` `lyrics_apply` `{note_index, lyrics, language_id}` spreads
  a word or phrase over the notes that follow, for example `ni hao` or `hello`.
- `note.update` with a new `lyric` and no `phonemes` regenerates the phonemes of
  an AI note. A note with `is_protected` true keeps its phonemes.
  `note.batch_update` `lyrics` writes text only and never converts.

## Controls that VOCALOID:AI sings

Each of these changed the rendered audio of an AI part.

| Goal | Operation | Values |
| --- | --- | --- |
| Note pitch | `note.update` `number` | MIDI note number |
| Drawn pitch curve | `pitch.set` `{note_index, points: [{tick, value}]}` | `value` is a MIDI note number with fractions; 67.5 is 50 cents above 67 |
| Pitch bend lane | `controller.set` `type` `PitchBend`, range set by `PitchBendSens` | -8192..8191; sensitivity 0..24 semitones, default 2 |
| Level | `controller.set` `type` `Dynamics` | 0..127, default 64; a gain (see below) |
| Vocal effort | `controller.set` `type` `Expression` | 0..100, default 50; level AND brightness (see below) |
| Shape of one note | `note.update` `ai_expression` with `PitchFine`, `PitchDriftStart`, `PitchDriftEnd`, `PitchScalingCenter`, `PitchScalingOrigin`, `PitchTransitionStart`, `PitchTransitionEnd`, `AmplitudeWhole`, `AmplitudeStart`, `AmplitudeEnd` | 0..1, default 0.5 |
| Vibrato | `vibrato.set` `{note_index, type, duration_tick, depth: [{tick, value}], rate: [{tick, value}]}` | see below |
| Timbre of a part | `performance.set` `{voice_colors: {S5Expression, S5Air, S5Character}}` | bounds in `performance.get`; enables VoiceColor unless explicitly bypassed |
| Timbre over time | `controller.set` `type` `S5Air` or `S5Character` | -100..100; -64..63 |
| Breath, Take, Robot voice | `performance.set` | modes and bounds in `performance.get` |
| Consonant timing | `phoneme_timing.set` after the part has been rendered once | ranges in `phoneme_timing.get` |
| Words | `note.add`, `note.update` `lyric`, `lyrics_apply`, or explicit `phonemes` | see Lyrics |

`Expression` is not a second volume lane: it is how hard the voice sings. Measured
on IA :[R] against the same phrase at 50 (level change at 0.4-1.5 kHz / at
1.5-4 kHz): 0 = -16 / -22 dB, 15 = -11 / -14 dB, 85 = +5 / +13 dB, 100 = +9 /
+13 dB. Use it per phrase for soft and belted singing, and trim the level that
comes with it on `Dynamics`. `Dynamics` is close to a plain gain (64 = unity,
0 = silence) but a cut arrives at about 77 % of its dB value, so write a wanted
-4 dB as about -5. `S5Character` behaves like effort with more change above
4 kHz (+45: +10 dB at 4-9 kHz, -45: -9 dB); `S5Air` adds breath (+70: +9 dB
above 9 kHz, -2 to -3 dB below 1.5 kHz). Values hold from one point to the next:
place the point in the rest before the phrase.

`PitchBend` with `PitchBendSens` 24 is an exact, stepwise pitch shifter (341.33
units per semitone). A jump of +3 to +12 semitones for 50-190 ms, with
`Dynamics` lowered for its length, sings a falsetto flip that the note model
itself does not produce.

Vibrato on an AI note needs all three of a `type` other than `None`, a
`duration_tick` above zero and a `depth` event; `vibrato.get` lists the type
names and the value ranges. `duration_tick` is the length of the vibrato
counted back from the end of the note. The note sings one depth and one rate:
only the first event of each array is used, so give a single event at tick 0
for each. Which non-`None` type is named makes no difference. Type and duration
alone, or `rate` without `depth`, render no vibrato, and a depth of 0 is none.
`ai_vibrato_enabled` must stay true on the note. `ai_expression`
`VibratoLeadingDepth` and `VibratoFollowingDepth` reshape a vibrato that exists
and do nothing otherwise.

The voice colour values are ignored while the VoiceColor effect is bypassed,
which is its state on a new part and after the default style. `performance.set`
now enables the effect when its parameters are supplied; Robot, Breath and Take
follow the same rule. An explicit `bypass: {VoiceColor: true}` in that call keeps
it bypassed. Applying a style still uses the bypass state stored in that style.

Use `style_capture` to save the current part's settings as a private preset and
associate the part with its new name and ID, then `project_save` to write the VPR.
`style_apply` changes MIDI parameters, audio effects and identity in one undo step,
including on supported extension-bearing projects.

`controller.types` and `performance.get` mark every lane and colour with
`applies_to` and `applicable_to_current_part`.

Things the score has to respect on an AI voice (found on IA :[R], English and
Japanese lyrics):

- A `-` continuation note sustains the LAST phoneme of the syllable before it.
  For a syllable that ends in consonants, put onset and vowel on the head note
  (explicit `phonemes`), continue with `-`, and give the closing consonants a
  short note of their own at the end. Otherwise the melisma hums on the
  consonant, or is silent.
- A rest before `-` makes the continuation silent: the notes must touch.
- The voice starts a consonant up to ~200 ticks before its note and ends a
  phrase-final vowel at about 70 % of the note. Move single phonemes with
  `phoneme_timing.set`; positions are note-relative ticks and exist only after
  the part has been rendered once (rebuild notes, render, then set).
- Japanese `N` is unvoiced for AI voices; use `N\` (or `m` / `n` before a
  labial / dental). The syllabic nasal is sung 10-15 dB under the vowels.
- For jobs of hundreds of notes or thousands of curve points use `batch.run`
  with `operations_file`, `note.batch_update` with `updates_file` and
  `points_file` (see score operations).

## Stored but not sung by VOCALOID:AI

These calls succeed on an AI part and are saved in the project, but the AI part
renders the same audio. They belong to standard VOCALOID parts, which need a
standard voicebank.

- Note `velocity` and the `expression` fields `Accent`, `Decay`, `BendDepth`,
  `BendLength`, `Opening`, `RisePort`, `FallPort`.
- Attack and Release effects: `dvqm_set`, `dvqm_clear`.
- Note skill weights: `note_skill_set`. `singing_skill_set` is rejected on an AI
  part.
- Controller lanes `Brightness`, `Clearness`, `Breathiness`, `Growl`, `Exciter`,
  `Air`, `Character`, `XSynth`, `Portamento`, `DynamicsHmm`, `PitchBendHmm`,
  `WeightHmm`.
- Voice colours `Exciter`, `Growl`, `Breathiness`, `Air`, `Mouth`, `Character`.

## Mixing and delivery

- `project_render_part` writes the dry voice of one part: 44.1 kHz, mono,
  16-bit, with lead-in and tail padding and without audio effects. It is a
  check, not the deliverable.
- `project_audio` `mixdown` renders the selected tracks with part, track and
  master effects. `sample_rate` is 44100, 48000, 96000 or 192000,
  `bits_per_sample` 16 or 24, `channels` 1 or 2. `mixdown_stems` writes one file
  per track.
- Vocal synthesis runs at 44100 Hz inside the engine. A project created at
  another rate cannot render vocals until `sequence.update` `{sample_rate:
  44100}`; choose the delivery rate in the mixdown instead.
- Effects: `project_audio` `effects` `{scope: "catalog"}` lists the bundled
  effects, `set_effect` adds or edits one on the master, a track or a part.
- Level and pan over time: `project_edit` `automation.set` with `scope`
  `track_volume`, `track_pan` or `master_volume`.
- Backing audio: `project_audio` `import_audio` `{path}` adds a WAV on a new
  audio track.
- Harmony: `track.duplicate`, then `note.batch_update` `{note_indices,
  transpose}`.

## Checks before reporting

- `audio_inspect(path)` shows sample rate, duration, peak and RMS. A peak of 0
  is silence.
- The saved VPR reopens with `project_open`; `note.list` shows what will be
  sung.
- Report the real output paths. Nothing here plays sound or touches the user's
  editor, so nothing has been listened to unless a person does it.

## Evidence

The sung and not-sung lists come from sample-exact comparisons of native part
renders with the asa voice, recorded by `tools/check_ai_effect_audit_36.py`.
They match the AI parameter set in the VOCALOID6 Reference Manual 6.13. Other
singers were not compared one by one.
