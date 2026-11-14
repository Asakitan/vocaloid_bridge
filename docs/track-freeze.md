# Native track freeze investigation

`project_edit` exposes `track.freeze_state`, `track.freeze`, and
`track.unfreeze`, each selecting a MIDI or MIDI-AI `track_index`. State reports
`frozen`, native `can_freeze`, and whether this session owns the frozen wave.
Freeze renders a 16-bit stereo track stem, materializes its time origin in a
session-owned file, and registers it with the native frozen-track machinery.
Unfreeze acts only on the exact wave registered by this session. Frozen audio is
temporary: saving or cloning produces the original unfrozen authoring state;
the live session remains frozen until unfreeze or close. Changes that could
invalidate the frozen authoring snapshot are rejected while the session is
frozen. Clearing an already-empty note Attack/Release is a read-only no-op and
does not invalidate the frozen cache. This is not an assertion that every effect, device, or sample rate has
been acoustically validated.

`artifacts/freeze-mcp-59c5a9b898b7.json` records a real MCP smoke of the three
operations, mutation rejection, save/clone authoring equality, unfreeze,
source-file preservation and failure cleanup on an empty track.
The maintained `freeze.lifecycle` case also passes in the integrated receipt
`artifacts/feature-acceptance-26a71f9b1dc5/`.

V6/V7 extension-bearing projects can freeze and unfreeze through the same
session-owned cache. Focused tests preserve root/track/part/note, pitch,
controller, automation, effect and parameter extensions plus an extra ZIP
resource across freeze, save, clone, unfreeze, reopen and existing undo/redo.
After presend alignment, frozen-cache PCM matches the pre-freeze native mix
within 2/32768 for the tested project. `project_inspect(feature="freeze")`
binds state, freeze and unfreeze templates to the selected track. Clearing an
existing AI Attack remains rejected during freeze. Evidence: V7
`artifacts/feature-acceptance-382ecd42cead/summary.json`, V6
`artifacts/feature-acceptance-bc5654ce2c9d/summary.json`. Other extension
combinations and real-time playback are not established by these cases.

## Native surface and editor evidence

The installed `WIVSMMidiTrack` exposes `bool CanFreeze()`, `bool IsFrozen`
with a setter, `string WaveFilePath` with a setter, and
`void StoreAudioEffectBypass()`. The setter for `IsFrozen` returns no result.
Existing bridge mixdown recognizes an already frozen MIDI track and creates a
native frozen-track audio placement.

The installed editor's `AudioPlayer.ExecuteFreezeTrack(WIVSMMidiTrack, string)`
is more than a flag setter: it chooses the track mixer input, bypasses the
master effect block, assigns a wave path, submits a stereo native mixdown, and
on completion replaces the frozen-track placement and stores audio-effect
bypass state. It also constructs a WPF progress dialog and invokes a dispatcher,
so it is not a suitable headless entry point. A managed IL search found no
direct call to this method, `CanFreeze()`, or the `IsFrozen` setter outside the
wrapper declarations; this does not exclude dynamic or unmanaged calls. The
installed 6.13 English reference text contains no `freeze`/`frozen` match.
These observations do not establish a supported user-facing freeze feature.

## Private-session probes

`artifacts/freeze-probe-cf7799164663.json` records a native AI track reporting
`CanFreeze=false` before its part render and `CanFreeze=true` afterward, while
`IsFrozen` remains false. The probe did not modify the freeze state.

`artifacts/freeze-probe-1bc7699193f7.json` records a separate discarded private
session: after native part rendering, generic `IsFrozen=true` read back true,
but `IsStaged` stayed false and native mixdown failed with `Native file
placement creation failed`. No frozen wave/placement had been made. This is a
negative test of flag-only behavior, not an implementation or successful freeze.

`artifacts/freeze-chain-5df018f67b0b.json` records a separate diagnostic partial:
the existing native single-track stem mixer produced a WAV, then the probe set
the native wave path, stored effect-bypass state and set `IsFrozen=true`.
Frozen-track native mixdown completed, but it did **not** match the unfrozen
baseline: difference RMS was about 0.03096. An independent PCM cross-correlation
found the frozen mix approximately 22,048 samples (0.49995 s at 44.1 kHz) earlier
than baseline; the session's native pre-send was 0.5 s. This is evidence of a
timing discrepancy, not proof of its precise cause.

In the same session setting `IsFrozen=false` restored a mix byte-identical to
baseline and preserved note readback. The native setter also cleared the frozen
wave path and deleted the diagnostic WAV. A VPR saved while frozen reopened as
`IsFrozen=false` with an empty wave path; MIDI notes and the original source VPR
were preserved. Reopened mix succeeded but differed from the original baseline,
and that audio difference has not been explained. No persistent frozen state or
cross-session ownership behavior is established by this probe.

The installed `AudioPlacementBuilder.CreateTimeRangeFrozenTrack` uses only the
first MIDI part to calculate position/length and subtracts the sequence's
`PresendTimeSec`; `CreateAudioPlacementFrozenTrack` derives a file offset from
that part. The diagnostic stem's alignment and multipart behavior must not be
assumed to match the editor's freeze file semantics.

A subsequent diagnostic candidate materializes the 16-bit stereo native stem
relative to first-part begin minus native pre-send, padding negative origins
with silent frames or trimming a positive origin. It rounds to the nearest
sample frame and retains the remaining stem rather than intentionally cutting
effect tails. The candidate writes only a uniquely named session-owned WAV;
the candidate built and the single-part zero-origin case
`artifacts/freeze-chain-378c07d5ae15.json` differed from baseline by RMS
0.00001182 on baseline RMS 0.0228943. The nonzero first-part case
`artifacts/freeze-chain-0f8d27b3d1c5.json` differed by RMS 0.00001203 on
baseline RMS 0.0206116. In both, session-owned frozen WAV deletion was checked
on unfreeze and the MIDI/source remained intact. These are 16-bit cases, not
evidence for every effect or sample rate.

The multipart probe `artifacts/freeze-chain-1c5a187fdab5.json` failed: baseline
was 18 seconds but frozen mix ended after 10 seconds, consistent with the
first-part-only frozen placement range. The native snapshot saved during the
zero-origin freeze also changed three standard part audio-effect bypass values
from false to true even though reopened state was unfrozen. A subsequent
implementation captures pre-freeze native bypass state and restores only identity-
checked standard fields in the private save/clone snapshot; it does not modify
the live frozen track. The placement range is extended through the last part.

`artifacts/freeze-chain-ed2c6f011aac.json` tested an extended multipart range,
an enabled track Gain effect, and track-volume automation. The baseline and
frozen renders now both lasted 18 seconds, but their RMS difference was
0.005472 against baseline RMS 0.023614, so audio equivalence failed. The saved
project's complete `sequence.json` matched its pre-freeze snapshot and the
live freeze remained active; after reopen, the native track was unfrozen.
The second part's voice display name changed from empty to `asa`, while its
voice ID and notes were unchanged. A mixer-only unity gain/center pan treatment
for frozen tracks was subsequently added to avoid applying baked track gain
and pan a second time.

After that mixer change, `artifacts/freeze-chain-6ad650a432ef.json` passed the
same nonzero-origin, two-part, track-Gain/volume-automation case. Both renders
were 18 seconds; RMS difference was 0.00001272 on baseline RMS 0.023614.
The full pre-freeze and frozen-save sequence JSONs were equal; the live frozen
wave remained present after saving, unfreeze removed the owned wave, and
reopened authoring notes and voice IDs and the source bytes were preserved.

## Verification boundaries

The frozen asset uses 16-bit stereo PCM, matching the installed editor freeze
mixdown bit-depth setting. Time origins are rounded to the nearest sample frame;
negative origins are padded with silence and positive origins trimmed. The
materializer retains the remaining stem, but long effect tails beyond the
placement range, additional sample rates, pan automation, concurrent frozen
sessions, and audio-device/DAW playback are not covered by the receipts above.
Frozen-state persistence is deliberately not promised.
