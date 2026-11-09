# Native Library Operations

## Entry Point and Ownership

`EngineHost.LibraryOperation(string? id, string operation, JsonElement options)`
is dispatched on the existing engine owner STA in the private desktop. The
parent supplies the `library_op` RPC and `project_library` MCP wrapper.

Every successful response is an object:

```json
{"session_id":null,"operation":"languages","native":true,"result":[]}
```

`options` is an object (omitted/null means an empty object). Catalog calls may
omit `session_id`; every mutation resolves `GetSession(id)` first. A supplied
session is required for note-based candidate generation. Native errors are
exceptions, not fabricated empty success results. Invalid indices are rejected.
`phoneme_table` is an explicit exception to the native-result flag: it returns
`native:false` and a versioned static manual reference, not an engine query.

`DisposeLibraryServices()` releases the persistent VMM, VSStyle, and per-language
G2PA managers. The parent must call it on the same owner STA before host teardown.
No operation constructs `App`, calls `App.OnStartup`, uses the interactive
editor, or changes global user settings. Manager creation is lazy.

Installed system resources and existing user resources are read-only catalog
roots. Existing user resources are deliberately registered as additional system
roots. Writable manager paths are exclusively:

- `.runtime/library/styles`
- `.runtime/library/media`

VPR saves remain owned by the existing project APIs. These operations do not
save over source VPRs or change the synthesis backend.

## Operation Schema

All fields below are inside `options`. Indices are zero-based nonnegative
integers; the default `track_index`, `part_index`, and `note_index` is `0`.
`language_id` accepts a native integer or case-insensitive enum name:
`JPN=0`, `ENG=1`, `KOR=2`, `ESP=3`, `CHS=4`.

| Operation | Session | Options | `result` |
| --- | --- | --- | --- |
| `languages` | Optional | `{}` | Array of `{language_id,name,default_lyric}` from real native managers |
| `phoneme_table` | Optional | `language_id=0` | Manual symbol inventory, source pages, and documented Japanese AI restriction; `native_enumeration=false` |
| `dvqm_catalog` | Optional | `is_attack=true`, `voice_id=""`, `offset=0`, `limit=100` (1..256) | Installed native Attack/Release component IDs, numeric IDs, level names, capabilities and total |
| `dvqm_get` | Required | Target note, `is_attack=true` | Native selection, component/level names, speed, top factor and protection |
| `dvqm_set` | Required | Target note, `is_attack=true`, `db_id`, `name_id`, optional `speed`, `top_factor`, `is_protected` | Committed native selection readback |
| `dvqm_clear` | Required | Target note, `is_attack=true` | Cleared native selection readback |
| `singing_skill_catalog` | Optional | `{}` | Installed Singing Skill plugin IDs, names, tags, timing and script availability |
| `singing_skill_get` | Required | Target classic part | Skill, amount, plugin ID, bypass and native bounds |
| `singing_skill_set` | Required | Target classic part; optional `plugin_id`, `skill`, `amount`, `bypassed` | Committed Singing Skill readback |
| `note_skill_get` | Required | Target note | `duration_tick`, `pre_weight`, `post_weight` |
| `note_skill_set` | Required | Target note; optional `duration_tick`, `pre_weight`, `post_weight` (weights 0..127) | Committed note-level HMM weights |
| `note_skill_reset` | Required | Target note | Native default HMM weights |
| `lyrics_can_convert` | Optional | `language_id=0, lyrics, is_ai=false, use_extension_dictionary=false` | `{language_id,lyrics,can_convert}` |
| `lyrics_candidates` | Required | Target note, `lyrics`, optional `language_id` (default note language), `use_extension_dictionary=false` | `{language_id,lyrics,candidates:[[{lyric,phonemes}]]}` |
| `lyrics_apply` | Required | Target note, `lyrics`, optional `language_id`, `use_extension_dictionary=false`, `protect` | Mutation result below |
| `phonemes_apply` | Required | Target note, `phonemes`, optional `language_id`, `protect` | Mutation result below |
| `lyrics_reset` | Required | Target part, optional `language_id` | Mutation result below |
| `phonemes_reset` | Required | Target part, optional `language_id` | Mutation result below |
| `style_list` | Optional | `query=""`, `sub_genres=[]`, `colors=[]` | `{total,styles:[Style]}` |
| `style_get` | Optional | `style_id` | Style with native effect parameter arrays |
| `style_apply` | Required | Target part, `style_id`, `include_audio=true` | `{session_id,style_id,name,midi_effects_applied,audio_effects_applied,audio_effect_count,scope}` |
| `style_capture` | Required | Target part, `name`; optional `sub_genres=[]`, `colors=[]`, `include_audio=true`, `overwrite_style_id` | Native private style snapshot and saved path |
| `style_update` | Required | Private `style_id`; optional `name`, `add_sub_genres=[]`, `add_colors=[]` | Native saved property readback; existing tags preserved |
| `style_delete` | Required | Private `style_id` | Native removal, verified file and catalog absence |
| `media_list` | Optional | `query=""`, `genres=[]`, `types=[]` | `{total,clips:[Clip]}` |
| `media_get` | Optional | `clip_id` | Clip with native part properties |
| `media_update` | Required | `clip_id`, optional `name`, `tempo`, `add_genres=[]`, `add_types=[]` | `{session_id,clip:Clip}` |
| `media_delete` | Required | `clip_id` | `{session_id,clip_id,deleted:true}` after native file/catalog removal |
| `media_capture` | Required | Target part, optional `name`, `tempo` (native hundredths of BPM), `genres=[]`, `types=[]` | `{session_id,clip:Clip,preview_audio_created:false}` |
| `media_import` | Required | `clip_id`, `track_index=0`, `position_tick=0`, optional `name` | MIDI: `{session_id,clip_id,track_index,position_tick,duration,notes}`; audio: `{session_id,clip_id,track_index,imported}` |

`Style` contains `style_id,name,type,path,vendor,languages,singers,genres,
sub_genres,colors,midi_effect_count,audio_effect_count`. For `style_get`,
`midi_effects` and `audio_effects` contain
`{id,type,bypassed,parameters:[{name,type,value}]}`; in list results these two
fields are null. Search uses the installed `StyleManager.FilteredStyleList`.

`Clip` contains `clip_id,name,type,part_type,path,vendor,key,tempo,writable,
languages,singers,genres,types,part`. List results have a null `part`. Details
invoke native `ReadPart()`, then return audio `{wav_path,audio_effects}` or MIDI
`{duration,notes,voice_id,ai_voice_id,secondary_voice_id,secondary_ai_voice_id,secondary_voice_source,style_id}`. `media_list` searches name, ID,
and vendor case-insensitively; requested genre and type tags must all match.

The G2PA mutation result is:

```json
{
  "session_id":"SESSION",
  "operation":"lyrics_apply",
  "affected_length":1,
  "notes":[{
    "tick":0,"duration":480,"note_number":60,
    "lyric":"hello","phonemes":"NATIVE_RESULT","language_id":1,
    "valid_phonemes":true,"protected":false
  }]
}
```

`affected_length` is returned by native G2PA (reset operations use the actual
part note count). The complete part note array is read back after commit; no
text-to-phoneme approximation is used. Phrase application begins at the target
note and lets native G2PA distribute syllables over subsequent notes. `protect`
sets the target note's phoneme-protection flag when explicitly supplied.
An empty candidate list is a legitimate native result, not proof that the lyric
cannot be converted: the installed Japanese manager returns no alternatives for
`U+3044`, while native English `hello` returns two candidates and applies across
two notes. Use `lyrics_can_convert` or actual application to test convertibility.

Without an explicit language, reset calls process the distinct valid native note
and part languages, excluding unset (`-1`) part caches. If none is initialized,
an explicit `language_id` is required. No user preference or multilingual
priority setting is read.
Mutation paths mark the session dirty and invalidate child references before
calling the native mutation, including error paths that may leave staged data.
Commits accept a native no-op false result only when no changes were staged and
the native error remains `NoError`.

`media_update` accepts only a native `UserClip` whose resolved path passes the
same path/link guard under `.runtime/library/media`. Built-in, pre-existing user,
and externally rooted clips are never edited. Tag edits append; they do not
silently replace tags. A property editor is always destroyed after its save.
`tempo` values use native hundredths of BPM (`12000` means 120 BPM).
Because the native editor starts with default draft values, the implementation
explicitly seeds the existing name, key, tempo, genres, and types before applying
requested edits. Omitted fields are preserved.
`media_delete` uses exactly the same ownership/path gate, calls native
`UserClip.Remove()`, and verifies both file and catalog-entry disappearance.
It cannot delete built-in or pre-existing user media.

`style_apply` uses the existing headless native audio service. Audio parameters
are preflighted through a native VEM effect block, converted from style plain
integers with `ToNormalized`, and passed to the existing `SetAudioEffect` path.
Unavailable, virtual, duplicate, noneditable, or unconvertible effects fail
before part mutation. Full application replaces the audio chain; explicitly
setting `include_audio=false` preserves it and returns `scope=midi_only`.
The `VoiceBID` and `VoiceBlend` MIDI parameters are not overwritten, matching the
installed editor's style-transfer logic.

`media_capture` stores native VMM metadata in the private media directory. It
copies notes, classic/AI expressions, phoneme protection, AI-vibrato flags,
vibrato curves, direct pitch, singing-skill weights, MIDI controllers, and audio
and MIDI effect values. `DefaultLyric` is not exported as an effect. It does not
render or invent an audition WAV. For audio clips the selected region of the
existing WAV is materialized in `.runtime/library/audio-sources` using the
sequence's tempo mapping, without resampling or changing sample values. The
materialized WAV preserves format and applicable fact metadata, but does not
claim to preserve unrelated WAV metadata chunks. That owned source remains
available for native clip loading. Native clip-file existence is checked after save.

On an extension-tracked project, `style_capture`, `style_update`, `style_delete`,
`media_update` and `media_delete` remain available because they read the source
or update only bridge-owned library files. For MIDI parts, capture can embed
unknown part and note fields in private, versioned bridge metadata, bound to the
clip ID and unique native note signatures. Controller-event and selected-note
direct-pitch-item extensions remain guarded for media capture; a target with
tracked direct-pitch-item extensions is also guarded for media import. Import
validates the metadata and stages the corresponding target
identities in one native history transaction. Before changing the target, the
bridge repeats the import on an isolated native clone when the clip carries
archive metadata or the target tracks entity extensions, and validates its saved
snapshot and extension overlay. During the candidate and target import the
clip file is held read-only, and native wrappers are reacquired after the
candidate closes. Metadata pointers must end at unknown native-schema fields;
native fields and paths through arrays are rejected. Clip property edits with
this metadata are rejected rather than risking its loss. The AI fixture in
`artifacts/feature-acceptance-39ed0d000904/summary.json` verifies source and
target extensions, ordinary-target upgrade and prior undo history, redo,
clone, reopen, conflicts and malformed metadata. Controller extensions and
extension-tracked audio import remain guarded; only the tested combinations
are established.

MIDI capture writes both primary and secondary voice IDs through native VMM.
The installed VMM reader returns an empty secondary ID even when its native
writer saved that ID in `.vsclip`. The bridge reads the native file's structured
secondary field to repair this demonstrated discrepancy, reports
`secondary_voice_source=clip_json`, and rejects conflicting nonempty native/file
values. This does not replace or modify a synthesizer. An actual two-AI-voice
capture/import/save/reopen passes in
`artifacts/feature-acceptance-cd7113488f36/summary.json`; classic secondary-voice
variants remain unverified.

`media_import` requires an existing target track of exactly the clip's native
type; it does not substitute voices/backends or silently convert track types.
It copies native VMM data into newly inserted VSM parts and restores attack/
release selections by their native CompID and level names. Audio imports reuse
the existing native audio-import path and then copy the clip's effect values.

VMM does not persist invalid-phoneme flags or AI Attack/Release selections.
New private clips embed these fields in the bridge-specific
`vocaloid_bridge_phoneme_validity_v1` JSON extension. The details response reports
`bridge_validity_metadata` and `bridge_dvqm_metadata`; import checks note identity
and installed component/level names before applying them. VPR saves carry invalid
phoneme flags in a separate bridge-owned ZIP entry. These extensions are not native
VMM/VPR fields and their retention by other software has not been tested.

## Singing Skill and Private Styles

Singing Skill is the native classic-part MIDI effect, not the note-level HMM
weights. The two have separate operations. Skill/amount bounds come from the
installed effect. Plugin IDs are restricted to the installed LuaManager catalog;
no request accepts a script path or script text. Before rendering, the host
restores the catalog-selected script path and native timing without creating the
editor App. These are runtime properties and are re-established after reopening.
An installed classic voice is still required for classic vocal synthesis.
AI parts are explicitly excluded from this classic script, even if the native
part exposes a legacy SingingSkill record; executing that record can overwrite
AI/Robot pitch processing.

`style_capture` copies native MIDI and (by default) audio effect values in their
existing order, excluding `DefaultLyric`. Saving creates a new native VSStyle
file under `.runtime/library/styles`. Overwrite is explicit and limited to that
same owned directory. Property edits preserve existing subgenre/color tags;
delete verifies both the file and native catalog. Built-in and pre-existing user
styles stay read-only. Applying a captured style retains the documented voice
identity exclusions (`VoiceBID` and `VoiceBlend`).
Audio values are converted from the VSM normalized floats to native VSStyle
plain integers through VEM `ToPlain`, matching the inverse `ToNormalized` path
used on application; discrete parameters retain their native quantization.

New Singing Skill, HMM-weight and style-authoring operations are implemented;
their targeted acceptance results are recorded in session 06 rather than inferred
from their presence in the catalog.

The installed VMM writer returns success from its note-weight setters but emits
default `singingSkill` fields. The bridge therefore writes the actual captured
VSM weights into the existing standard `notes[].singingSkill` object of its own
new clip, after checking note identity. This is a standard-format serialization
repair, not a new private extension; the native VMM reader remains the import
path. The original part and all other clip fields are preserved.

## Native Mappings

| Surface | Installed native wrapper calls |
| --- | --- |
| Languages | `G2PAManagerIF.CreateManager`, `G2PAManager.DefaultLyric` |
| Conversion | `G2PAManager.CanConvert`, `CandidatePhonemes` |
| Phrase/phoneme edits | `SetLyrics`, `SetPhonemes`, `ResetLyrics`, `ResetPhonemes` |
| Style catalog | `StyleManagerIF.CreateStyleManager`, `ReadSystemStyles`, `ReadUserStyles`, `AllStylesEnumerator` |
| MIDI style application | `SetupAndResetAllMidiEffects`, `GetMidiEffectById`, `SetParameterInt/Float/String`, `SetBypass`, `SetStyleName`, `SetStylePresetID` |
| Audio style application | Existing `EnsureAudioEffects`, VEM `AddMasterBlock`, `AddLoadEffect`, `ToNormalized`, existing `SetAudioEffect` |
| Media catalog | `MediaManagerIF.CreateMediaManager`, `ReadAllClipFiles`, `AllClipEnumerator`, `Clip.ReadPart` |
| Media properties | `UserClip.CreatePropertyEditor`, `SetClipName`, `SetPartTempo`, `AddFilterGenre`, `AddFilterType`, `Save`, `DestroyPropertyEditor` |
| Private media deletion | `UserClip.Remove`, file existence and native catalog readback |
| Media capture | `MediaManager.CreateMutableClip`, native mutable filter/part/note/effect/controller setters, `MutableClip.Save`, `MutableClip.Destroy` |
| Media import | `WIVSMMidiTrack.InsertPart`, `WIVSMMidiPart.InsertNote/InsertController`, native note/vibrato/effect setters, existing `ImportAudio` |

## Verification and Remaining Gaps

Installed target: `C:/Program Files/VOCALOID6/Editor/VOCALOID6.dll`.
The previous Release build and real-MCP suite passed the original 16 library operation names:
`artifacts/feature-acceptance-19d5e92a5f26/summary.json`. The private-media case
captures three native notes, updates metadata, imports into another track,
saves/reopens the project, and deletes its own clip. Note/phoneme/voice data
survive the roundtrip and the native catalog no longer contains the deleted clip.

VMM writes metadata to the clip directory's `property.json`; the `.vsclip`
resource containing notes remains unchanged. Acceptance reads both actual files,
not only the manager's cached property view. Tempo is in native hundredths of BPM.

Focused acceptance command:

```powershell
.venv/Scripts/python.exe tools/verify_features.py --category library `
  --vsqx-fixture .runtime/benben_01/cant_stop/cant_stop.vsqx `
  --phoneme-manual-text .runtime/VOCALOID6_Reference_Manual_6130_ENG.txt
```

The separate `tools/check_library_operations.py` is an additional native probe,
not the delivery receipt. The final suite also verifies English candidate
generation, phrase application, Japanese empty-candidate behavior, phoneme
reset, complete style effects, and original-file protection.

Current explicit gaps (not reported as successful operations):

- The full static symbol inventory comes from the V6.13.0 reference manual,
  not from the examined G2PA public wrapper. Actual voice/language support is
  not inferred from this table; use the native G2PA and selected voice to check
  a concrete conversion.
- After voice-service initialization, the installed native catalog reports 36
  Attack and 42 Release entries. One of each was tested through classic and AI
  media capture/import and VPR reopen; actual singing with these presets and
  the remaining combinations are unverified. The initially empty catalog was
  queried before initialization.
- Invalid-phoneme flags survive the bridge-owned media/VPR extension, clone and
  reopen; edits that invalidate a VPR extension's note references are rejected.
  The bridge does not claim that external editors preserve this metadata.
- Capturing audio with nonzero trim endpoints is validated for a 44.1 kHz
  PCM16 mono source, including a nonzero position and a tempo change across the
  region; additional formats and tempo-map combinations remain unverified.
- Audition/preview synthesis is not part of `media_capture`; a MIDI clip is not
  a synthesized WAV.
- VMM `AudioPartBase.Begin` and `End` are marked obsolete-as-error by the installed
  assembly and are not used or claimed as supported fields.

Aggregate limits and untested variants remain recorded in the feature matrix.

Session 06 evidence: private style capture/update/overwrite/application/delete
and standard HMM-weight media roundtrip passed in
`artifacts/feature-acceptance-09a5d49126c6/summary.json`. The Singing Skill
classic-part parameters are callable in the original session, but reopening
that classic project currently produces an AI part; the stricter operation
then reports the type mismatch. See
`artifacts/feature-acceptance-6d7fb89e808b/remaining.singing_skill.json`.
This classic-format failure is not an accepted full roundtrip.

Style capture or apply with `include_audio=true` requires releasing any active
native transport first, including one owned by another session. The guard runs
before creating a style draft or mutating the target part.

A separate ordinary private MIDI clip probe, `tools/check_archive_media_update.py`,
passed in `artifacts/feature-acceptance-2456c42fd76b/summary.json`. Its native
property update changed `property.json` while leaving the `.vsclip` bytes intact;
`media_get` remained consistent after saving and reopening the project (this does
not restart the media manager). With the same new clip's `property.json` held
open without write/delete sharing, native save returned an error and the observed
property file, clip file, catalog view, and project history remained unchanged.
The handle was closed and the disposable clip deleted. This establishes one
locked-file failure only, not crash atomicity, manager restart, arbitrary I/O
failures, external concurrent writers, or archive-bearing clip update safety;
the archive metadata update guard remains in place.

The archive-bearing expected-success case `preservation.media_update_entities`
in `tools/check_archive_media_update.py` is a red baseline against the current
host: `artifacts/feature-acceptance-720b23a039dd/summary.json` records the
existing archive-metadata property guard rejecting the update, with cleanup
passing. Its subsequent locked-file and import/history/reopen assertions were
not reached. Automatic review rejected a request to remove the guard because the
ordinary-clip probe and lack of rebuilt end-to-end evidence do not establish
that archive extensions survive; losing extension metadata remains the risk.
The guard remains unchanged. A later independent private-desktop probe on a
disposable archive-bearing AI clip found that native property `Save(true)` left
the `.vsclip` bytes and its archive metadata unchanged, but removed an injected
unknown nested field from `property.json`; a locked save left the tested files
unchanged. See `artifacts/feature-acceptance-39dc398383e1/summary.json` and
`docs/media-update-probe-19.md`. This exposes an additional property-field
preservation issue, including for ordinary native property writes, and does not
establish bridge update or crash atomicity. The older `preservation.media_entities` case still
expects this rejection and would need reconciliation if the guard is changed
through an approved, validated implementation.

The ordinary bridge-owned AI clip regression in
`artifacts/feature-acceptance-5f2872117662/summary.json` confirms that the current
production `media_update` drops synthetic unknown property members at the root
and under `part`. A same-process two-manager staging experiment did not isolate
the intended roots (`artifacts/feature-acceptance-7069a2a902c4/summary.json`);
a separate-process disposable-copy experiment preserved one top-level marker
and observed lock and cache-refresh behavior
(`artifacts/feature-acceptance-e07cbc63bd95/summary.json`). General nested
retention, concurrent changes, refresh failure after commit and crash atomicity
remain unproven, so no production property update change was made. See
`docs/media-property-preservation-20.md`; the corrected, reproducible process
probe and cleanup passed in `artifacts/feature-acceptance-6db3c881f0f0/summary.json`.

Session 21 repeated the ordinary private AI clip regression in
`artifacts/feature-acceptance-25f45d337d42/summary.json`: production
`media_update` succeeded while dropping synthetic root and `part` unknown
fields. The separate-process experiment in
`artifacts/feature-acceptance-2ca7dc2676b2/summary.json` manually restored only
known fixture markers and detected one intervening write before replacement.
It does not establish a generic array merge, a race-free transaction or recovery
from native manager refresh failure. Production behavior and the
archive-bearing property guard were not changed; see `docs/media-property-21.md`.

A session 22 private-process probe in
`artifacts/media-failure-22-045a23ff9013/receipt.json` confirmed a lost external
write in a check-to-replacement interleaving. With `property.json` exclusively
locked, an independent reader was denied, while native `ReadAllClipFiles()`
returned its success enum and omitted the clip from enumeration; the old clip
reference remained invalid even after an unlock and later successful enumeration.
This is a silently incomplete refresh observation, not an injected native
non-success return or full recovery proof. See `docs/media-failure-22.md`.
Production property behavior and the archive-bearing guard remain unchanged.
