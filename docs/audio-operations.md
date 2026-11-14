# Native Audio Operations

`EngineHost.AudioOperation(session_id, operation, options)` implements the native
`audio_op` request. All calls enter through the existing STA host on its private
desktop. This module never instantiates `AudioPlayer`, editor windows, effect
windows, or `App`, and never sends UI input.

```json
{
  "session_id": "SESSION_ID",
  "operation": "process_audio",
  "options": {
    "path": "E:/VC/vocaloid_bridge/output/background-demo-31c27fd842.wav",
    "action": "normalize",
    "output_name": "normalized.wav"
  }
}
```

## Output Rules

VOCALOID7 effects support track/master scope, not part scope. Its installed WOR
does not expose the V6 reverse or VOCALO CHANGER entry points. `voice_change`
returns unsupported; `reverse` processes PCM or IEEE-float RIFF WAV frames in
the bridge using bounded buffers. Its result reports `native=false`,
`backend=bridge.pcm_frame_reverse` and a `metadata_warning`, not a WOR render.
Other routes compile against their version-specific API, but the historical V6
mixdown and device evidence below is not V7 runtime acceptance.
V7 has separate focused evidence for a two-track native-vocal audio fixture:
44.1 kHz stereo master/stem comparison and a 192 kHz mono master-effect
comparison passed in `artifacts/feature-acceptance-4c197f2d178a/summary.json`.

- `output_name` is relative to the existing workspace `output` directory.
- `overwrite` defaults to `false`; publication uses exclusive file movement.
- Input paths must be absolute existing files and cannot traverse links.
- Offline processing and asset export refuse to replace their own input even
  when `overwrite` is true. The existing host protects the opened original VPR.
- Temporary rendered WAV files also live under `output` and are removed on
  normal completion or failure. No sound is generated in Python or NumPy.
- Every published WAV is inspected for a complete RIFF/WAVE container, valid
  format, and nonempty whole audio frames. This does not prove nonzero sample
  amplitude; the external acceptance probe must measure that separately.
- The installed writer can omit the padding byte after a final odd-sized DATA
  chunk. The inspector accepts only a complete payload ending exactly at the
  RIFF boundary in that case; partial payloads and truncated interior chunks fail.
- Mutations mark the session dirty and commit native state. Ordinary-project
  `import_audio`, `edit_audio`, and direct `set_effect` use a staged native
  transaction with undo/redo and rollback on failure. Other mutation paths may
  leave dirty native changes after an error; no automatic project reload or
  silent retry occurs.

## Operation Schema

Indices are zero-based. Fields marked optional have the defaults shown.

| Operation | Options | Result / native mapping |
| --- | --- | --- |
| `inspect_audio` | `path` | Reads actual WAV metadata using the host RIFF inspector; no synthesis claim. |
| `import_audio` | `path`; optional `track_index`, `position_tick=0`, `name=source stem` | Imports a WAV with `WIVSMAudioPart.SetOriginalWaveFile`. Omitting `track_index` creates an Audio track using `InsertTrackEx`; supplying it requires an existing Audio track. Returns the actual sorted part index, region, asset paths, and duration. |
| `edit_audio` | `track_index`, `part_index`; optional `position_tick`, `begin_tick`, `end_tick`, `name` | Calls `SetRegion`, `MovePart`, and `SetName`; returns the new native sorted part index. Region tick offsets are relative to the underlying audio asset, not the project start. |
| `export_audio` | `track_index`, `part_index`, `output_name`; optional `overwrite=false`, `original=false` | Copies the current native stored WAV, or original stored asset with `original=true`. This is **whole-asset export**, not region trimming, effects rendering, or resynthesis. |
| `process_audio` | `path`, `action` (`reverse`, `normalize`, `time_stretch`, `pitch_shift`, or `voice_change`), `output_name`; optional `overwrite=false`, `ratio=1`, `pitch_cents=0`; `voice_id` required for voice change | Uses the installed WOR renderer, except V7 `reverse` uses bridge PCM/float frame reversal with `native=false`; see action table. Creates a separate WAV without changing the imported part. |
| `mixdown` | `output_name`; optional `track_indices`, `sample_rate=44100` (or 48000, 96000, 192000), `bits_per_sample=24` (or 16), `channels=2` (or 1), `bypass_effects=false`, `timeout_seconds=120`, `overwrite=false` | Native VAE manual mixdown with VEM effects, file placements, and VSM-rendered vocal parts. The file ends at the end of the last part. |
| `mixdown_stems` | `output_prefix`; optional `track_indices`, `sample_rate=44100`, `bits_per_sample=24`, `channels=2`, `bypass_effects=false`, `timeout_seconds=120`, `overwrite=false` | One native mix per selected track, named `PREFIX-track-INDEX.wav`. Existing destinations are preflighted before the first stem. Earlier completed stems remain if a later native render fails. |
| `effects` | optional `scope=catalog`, `effect_id`, `track_index`, `part_index` | Bundled VEM effect discovery or current master/track/part chain inspection. |
| `set_effect` | `action` is `add`, `set`, `remove`, or `move`; optional `scope=master`, `slot`, `track_index`, `part_index`, `effect_id`, `parameters`, `preset`, `bypass`, `target_slot` | Edits the native persisted effect chain; no plugin editor is opened. |
| `devices` | None | Enumerates native VAE devices and sample rates without selecting a system default. |
| `transport_prepare` | `device_id`; optional `track_indices`, `sample_rate=44100`, `buffer_samples=2048`, `mute_output=false` | Pre-renders native parts and prepares one explicitly selected standalone VAE device for this session. |
| `transport_status` | None | Prepared/playing state, device, native position, loop and output peak. |
| `transport_play` | None | Starts the prepared private native transport. |
| `transport_stop` | None | Stops playback, retaining the prepared transport. |
| `transport_seek` | `seconds` within prepared duration | Requests a native asynchronous position change; returns `requested_seconds` and `position_update_async=true` separately from current `seconds`. Poll `transport_status` to observe application. |
| `transport_release` | None | Stops and releases the private device, placements and callbacks. |

Direct `set_effect` add, set, move, and remove operations use the native score
transaction; a staged change commits to native history and can be undone or
redone.
Applying a style stages its complete MIDI/audio chain and identity in one score
transaction, including on supported extension-bearing projects. One undo restores
the prior chain; constituent effects no longer commit independently.
Style effects initialize the native controller and apply mode parameters before
converting the other preset values. V6 part-effect readback uses the persisted
part parameter map and its selected mode for mode-dependent bounds; track and
master effect readback uses their native controllers. Native parameter values
can be quantized, so use their returned values for subsequent comparisons.
In 0.24.0, extension-bearing effect edits use the same transaction and validate existing curve owners; add/undo has focused evidence. The actual master-effect transaction and rollback case passed in
`artifacts/feature-acceptance-f97d35cd5451/audio.effect_history.json`; that
batch also records two later-corrected test failures in other cases.

Audio import initializes the region before attaching the source file, matching
the installed editor's import path. A previous run produced a saved track and
embedded WAV without a serialized part in
`artifacts/feature-acceptance-3390026d37e5/remaining.effect.gain.json` and its
saved VPR. Database initialization was subsequently moved into host startup;
the focused run below successfully saves, reopens and mixes ten imported audio
projects, and an isolated Delay rerun also succeeds. This observation does not
establish the internal native cause of the earlier omission. The end tick is calculated from the actual
WAV frame count and sample rate with `WIVSMSequence.GetTickFromTime` at the
requested position, so the sequence tempo map is respected. A zero-length or
out-of-range native tick duration is rejected rather than creating an empty
part. The corrected import, region edit, resource export and saved-project
roundtrip pass the final actual MCP acceptance.

### Offline Actions

| `action` | Additional input | Native call |
| --- | --- | --- |
| `reverse` | None | V6: `WOR.ReverseRenderer.RenderAudioFile(input, output, 0)`; V7: bounded bridge PCM/IEEE-float RIFF WAV frame reversal, `native=false` |
| `normalize` | None | `WOR.NormalizeRenderer.RenderAudioFile(input, output)`; native normalization target is not overridden. |
| `time_stretch` | `ratio=1`, `pitch_cents=0` | `WOR.TimeStretchRenderer.RenderAudioFile(input, output, ratio, pitch_cents)` |
| `pitch_shift` | `pitch_cents=0` | Same renderer with native `bpmMag=1`. |
| `voice_change` | Required `voice_id`; optional `pitch_cents=0` | `WOR.VoiceChangeRenderer.RenderAudioFile(input, output, model, NPIndex, pitch_cents)` |

`ratio` is passed unchanged as native `bpmMag`; pitch is in cents, not semitones.
Bounds come from the installed `TimeStretchRenderer.MinBpmMag`, `MaxBpmMag`,
`MinPitchShift`, and `MaxPitchShift`. `WORError` values are included in failures,
including no-op `HaveNoUseRenderer`; no no-op is disguised as a render.

V7 reverse combines frame-aligned multiple data chunks into one data chunk and
preserves the input sample format. Valid standard integer `smpl` loop endpoints
are mapped to the reversed frame indices. Cue points are also mapped when
there is exactly one data chunk, no `smpl` or `plst` chunk, and their data-chunk
offsets and play-order positions match the supported PCM layout. A `LIST/adtl`
containing well-formed `labl`, `note` and `ltxt` records is permitted. A unique,
in-range `ltxt` region is mapped using its sample length; conflicting lengths,
duplicate cue IDs, zero-length or out-of-range regions stay unchanged. Duplicate
IDs are detected across cue chunks, whether or not labels or regions exist.
At most 65536 distinct cue IDs and region references are processed; exceeding
either limit or encountering other or malformed lists leaves cue points unchanged.
Fractional, invalid, unknown-type or sampler-specific loops,
playlist-linked or ambiguous cue points and other time-dependent metadata remain unchanged. The response
reports `sampler_loops_reversed`, `sampler_loops_unchanged`,
`sampler_chunks_unchanged`, `cue_points_reversed`, `cue_points_unchanged` and
`cue_chunks_unchanged`; malformed chunks have no reliable point or loop count.
Compressed or unknown extensible formats, incomplete frames and non-RIFF formats
are rejected. The source file is unchanged.

VOCALO CHANGER initializes the existing VDM/DSE services, resolves `voice_id`
explicitly in `VDMVoiceBankType.Dnn`, requires `IsAvailableForVoiceChanger` and
`IsSynthesizableVersion`, and requires
`voice.DirectoryPath/voice.GroupName.vtb2` to exist.
Missing models, unsupported banks, native loading errors, and licenses are not
replaced by another voice or synthesis backend. A converted WAV can be imported
separately; this operation does not fabricate or change a part's voice metadata.

The installed native `WaveOfflineRenderer.dll` supports `.vtb2`; the managed
`OfflineProcessor` still constructs a legacy `.vtbr` path. Read-only VDM
inspection of the failed case's `BCLFDT43M6TL2CD5` returns NAOKI, group
`VOCALOID6_Voicebanks_03`, `NPIndex=1542`, and both availability flags true. Its
actual model is
`C:/Program Files/Common Files/VOCALOID6/Model/VOCALOID6 Voicebanks/VOCALOID6_Voicebanks_03.vtb2`
(7,467,025 bytes). The operation derives this from the selected bank rather than
hardcoding that path, changing voice, copying packages, or changing authorization.

### Mix Options

Vocal rendering keeps the Lua controller and observer attached until the target
wave is valid and the sequence renderer has finished. A target-part completion
event alone is not sufficient: stopping the shared queue at that point can leave
other parts partially rendered and make the next pre-mix render time out. Single
part exports use the same completion rule and may finish other queued parts
before returning the requested WAV. The existing timeout limits are unchanged.
The 12-part VPR regression and per-part nonzero PCM checks pass in
`artifacts/feature-acceptance-e83d8be0e2a2/mixdown.project_fixture.json`.

- `track_indices`: optional array of native track indices. With no selection,
  master export respects native mute and solo. An explicit selection, including
  stem selection, overrides mute/solo for those tracks without editing them.
- The native export covers complete selected tracks. `start_seconds`,
  `end_seconds`, and `tail_seconds` are rejected: the native manual mixer ignores
  playback-loop ranges, so this API does not advertise them as export controls.
- `sample_rate=44100`: `44100`, `48000`, `96000`, or `192000`.
- `bits_per_sample=24`: `16` or `24`, mapped to native bit-depth indices 0 or 1.
- `channels=2`: `1` or `2`.
- `bypass_effects=false`: bypasses all VEM effects for this mix only.
- `timeout_seconds=120`: 1 through 600; covers placement acknowledgements and
  final mix completion. Individual voice synthesis uses the existing host's
  native part-render timeout.
- `overwrite=false`.

The mix output rate is distinct from the project sequence's internal synthesis
rate. On the installed editor, managed sequence-creation paths use 44100 Hz;
the decompiled managed code has no `SetSamplingRate` call site, and its memory
placement length also assumes 44100 Hz. The automatically extracted source
observations are in `artifacts/audio-routing-static-acda7649870c.json`; they
do not prove that the underlying native DSE supports no other rate. A sequence
changed to 48000 Hz with `bus_no=0` produced native
`FailedToCreateDseWaveBuffer` on part render in the session 07 probe. The host
now returns a fast, explicit error for non-44100 internal part rendering while
leaving project rate metadata editable; 48000 and 96000 readback and rejection
are recorded in `artifacts/audio-routing-guard-9f833b494596.json`. This does
not prove that 96000 Hz DSE rendering itself was exercised. The guard does not apply to output-only rate
selection: native 44100 Hz singing mixed at 44100/48000/96000 Hz with bus 0
and bus 1 produced nonzero WAVs with the requested output rates in
`artifacts/audio-routing-acda7649870c.json`.

`bus_no` is a persisted external-output assignment, not the VAE input index.
The installed placement builder uses the sequence track index for its mixer
input; the installed editor maps that index to `GetBusNo()` in `ExtBus` for
non-standalone connections. This offline Manual mix intentionally uses no
external host bus mapping (`ExtBusCount=0`), sums the selected tracks and does
not validate or route to a DAW output. The six output files above were
sample-identical between bus settings at each output rate, as measured in
`artifacts/audio-routing-comparison-acda7649870c.json`; that is evidence for
the current offline sum, not proof of external DAW routing.

The route commits even an otherwise clean sequence before each required native
voice render. Frozen MIDI tracks use their native frozen track asset. Other
parts use `AudioPlacementBuilder` and `VEAudioPlacement`, preserving region
offsets and native fades. VAE receives native master-volume, track-volume, and
pan curves; VEM receives the native tempo map and saved master/track/part effects.
The export calls `VEAudioEngine.MixdownToFile` in `VEMixdownMode.Manual`.
Enabled Robot Voice runtime scripts are resolved from the installed Lua manager
before rendering, without initializing the editor's `App`. The same pre-render
path prepares installed Singing Skill scripts for reopened MIDI parts. This new
Singing Skill mixdown path has not yet been validated independently. A reopened Robot
project's actual nonzero master mix is verified in
`artifacts/feature-acceptance-23de638ffae9/summary.json`.

Stems retain their native individual lengths, track automation and part/track effects, but bypass master automation
and master effects, matching the manual's multi-track export semantics. They are
not a claim of bit-exact decomposition of a nonlinear master mix. Each result reports `backend: VAE.Manual+VEM` only after a
native success callback and valid on-disk WAV.

The mixer initializes VAE with no window handle, installs the rooted native
context, then calls `StartEngine` with exactly `VEConnectMode.VST` before entering
Manual mode. This requests the native externally clocked host route, not
standalone DirectSound/ASIO output. The returned connection mode must be VST;
another mode or an already-playing engine is rejected. No `PlayStart`, editor
startup, device-selection UI, or fallback mode is invoked. Sample rate and VEM
attachment are set after engine creation; effect attachment failure is reported.

The installed managed API exposes only ASIO and DirectSound device types, not a
null-device enum. `Initialize` alone did not create a running engine: the first
acceptance run failed at `SetMixdownMode(Manual)` with `NoEngineRunning`. The
explicit host-engine route passes actual native completion and nonzero-waveform
checks in the final acceptance receipt.

### Effects

`effects` with `scope=catalog` lists the modules discovered by `WEffectManager`
from the installed editor's `AudioEffects` directory. Supplying `effect_id`
loads that bundled effect into a temporary native block and returns names,
labels, default/current normalized values, plain-value bounds where available,
and preset names. No arbitrary DLL search path or third-party VST scanner is
implemented.

`scope=master`, `scope=track` plus `track_index`, or `scope=part` plus both indices
returns persisted effects and corresponding native controller metadata.

`set_effect` fields:

- `slot`: insertion index for `add` (defaults to end); existing index for other
  actions (defaults to zero).
- `effect_id`: required for `add`; must be a discovered non-virtual effect.
- `parameters`: optional object mapping exact native parameter names to finite
  normalized values in `[0, 1]`, for `add`/`set`.
- `preset`: optional native preset name, applied before `parameters`.
- `bypass`: optional Boolean persisted to the native effect.
- `target_slot`: required destination in practice for `move`, default zero.

The native VEM block addresses instances by effect GUID, so duplicate GUIDs in
one chain are rejected. Virtual reverse/pitch UI effects are not hosted plugins;
use the WOR offline actions instead. Edited parameters are persisted with
`WIVSMEffect.ReplaceValueFloat` and reapplied through VEM synchronization before
mixdown. Existing native values not explicitly edited are preserved.

## Lifetime and Validation Boundary

`DisposeAudioServices()` must run before `manager.Dispose()` in the host.
It terminates any active VAE engine and disposes the lazy VEM manager. Native
callback delegates remain rooted through termination. Callbacks touch managed
completion state and an STA-captured tempo map only, never native VSM objects.
File placements are disposed after native termination.

The Release host and all audio/effect/mixdown cases pass in
`artifacts/feature-acceptance-19d5e92a5f26/summary.json`. Actual files verify
nonzero samples, reverse ordering, normalization, duration scaling, pitch/voice
change, master/stem relationships, preset persistence, and a 192 kHz mono
24-bit mix with an audible master-effect difference. This is not evidence for
every effect or all available sample-rate combinations.

`tools/check_audio_remaining.py` adds focused actual-MCP cases for both audio
region boundaries and whole-original export, 48/96 kHz mixes, and each of the
eleven discovered effects' parameters, presets (when present), bypass,
save/reopen and nonzero offline mix. The first run's 48/96 kHz and boundary
case passed in `artifacts/feature-acceptance-3390026d37e5/summary.json`.
Its effect checks did not pass: ten assumed exact rather than native-quantized
values, and Gain exposed the missing serialized part. With corrected quantized
readback checks and the initialized host, ten effects, both rates and boundary
case passed in `artifacts/feature-acceptance-3fac4de49264/summary.json`; Delay
was blocked by a missing native temporary WAV in that run. Delay and cleanup
passed in the isolated rerun `artifacts/feature-acceptance-22609728e8c0/summary.json`.
The previous fixed VSM application ID allowed one host's cleanup to remove
another host's native cache, reproduced separately in
`artifacts/host-isolation-22aebb82b8c7.json`. Per-host VSM cache namespaces
pass the same two-host regression in `artifacts/host-isolation-732451efccb9.json`;
Delay also passes on the isolated-cache build in
`artifacts/feature-acceptance-111643a4386e/summary.json`. This establishes the
cross-host cleanup failure mode but does not prove the exact cause of the
original Delay failure. These tests verify a
nonzero reopened-project mix with each enabled effect, not that every effect
produces an audible difference or that every preset is covered.

Runtime prerequisites are the installed VDM/DSE services,
the selected readable VTB2 model, native `WaveOfflineRenderer.dll`, VAE's accepted
VST host connection and Manual mode, rooted callbacks, and a writable workspace
output directory. No physical audio device should be required or selected.

The earlier effect suite uses actual native vocal synthesis as its input. The
focused transaction tests below use their own generated WAV fixtures. Both
close sessions without foreground activation and leave source files unchanged;
audio processing uses the installed native renderer.

Import and edit now use the shared native score transaction boundary: staged
changes commit with native undo history, and failures attempt native rollback.
An ordinary-project import/edit/undo/redo/reopen case passed in
`artifacts/feature-acceptance-eb4111329c4f/summary.json`; ordinary audio media
capture/import also passed in `artifacts/feature-acceptance-6cc1fd525f8e/summary.json`.
0.24.0 has a focused archive-extension audio import/edit and effect add/undo case. Broader resource-name collisions and media-archive audio metadata still have separate boundaries; see [Agent completion](agent-completion-33.md).
For extension-tracked projects, `process_audio` is available for an explicit
external WAV because it changes no sequence data; the same receipt verifies
native reverse samples, input protection, project history and saved fields.

## Media metadata v2

Captured audio carries part/region/effect extension metadata, bound to its materialized WAV by a digest. Import keeps the waveform read-locked and attaches all effects and metadata before one native commit. Complex timeline edits split audio regions and use the region in part identity. See [0.25.0 completion](completion-34.md).
