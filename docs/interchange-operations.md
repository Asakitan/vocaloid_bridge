# Native interchange: current evidence

Import dispatch uses the native VSQX, PPSF V2, PPSF V3, MIDI and VPR loaders;
the PPSF loader is selected by signature. Import does not alter the source file.
Native project clone saves to a private directory before reopening the snapshot.
Its `OpenSequence` second parameter is named `vsqxSchemaDirPath` in the installed
managed wrapper; its behavior for VPR resources has not been independently
established. Clone audio independence requires the focused runtime test below.

## Known data-loss limitation

On 2026-11-10, the existing `interchange.ppsf2` acceptance case was rerun against
`.runtime/radio-miku-gohan-20220311.ppsf` through the isolated MCP host. The 497
imported notes survived save/reopen, but all four classic MIDI tracks reopened as
AI tracks and the classic `BCNFCY43LB2LZCD4` voice IDs were absent. The native
save output's `Project/sequence.json` already had track type 0, no part voice
properties and an empty root `voices` list. This identifies the native save
output as the point by which identity is lost; it does not establish why the
engine omitted it. The wrapper signature `Save(string filePath, bool prettify)`
was inspected in the installed assembly. Changing its formatting flag is not an
identity fix. See `artifacts/feature-acceptance-424fbfff4980/interchange.ppsf2.json`
for the runtime receipt. The issue remains unresolved; a successful call to save
must not be interpreted as a verified identity-preserving roundtrip.

A candidate based on the [public classic VPR example](https://docs.rs/crate/vsqx/latest/source/src/test/vpr.json)
added standard root `voices` and part `voice` fields to a copy of the native
output, using the actual imported ID, name and language. Native reopen then
reported the original ID and name but still returned four `MidiAi` tracks and
`ai=true` parts: `artifacts/feature-acceptance-088b37756308/remaining.classic_candidate.json`.
A freshly created classic track with an empty voice similarly reopened as AI,
independent of a classic bank ID. Native duplicate into a fresh sequence kept
the track type and ID but lost the reported voice name; save/reopen still lost
identity. VSQX 3 and 4 fixtures also lost their source voice IDs after reopen.
These observations are in `artifacts/feature-acceptance-441fd332a26d/`.
No candidate has been promoted to production serialization.

### Editor/native call-site audit

The installed editor's managed `Yamaha.VOCALOID.Sequence` uses the same native
`Save(temp, false)` and `OpenSequence`/PPSF loader calls. For VPR and VSQX it
passes the editor assembly directory as `vsqxSchemaDirPath` and uses
`VSMSequenceData(44100, 32, 0)`; the bridge now also passes the assembly
directory but retains a 100-entry undo limit. The assembly-directory change
did not prevent the independent-host classic conversion described below; the
undo-limit difference is not an established cause.
All four editor `VSMSequenceData` creation sites use an undo limit of zero;
the managed wrapper exposes `SetMaxUndoCount`, but the decompiled editor does
not call it. No evidence establishes that changing the value after load is
equivalent or changes the conversion.
The installed wrapper reports `WIVSMTrack.Type` directly from native
`VIS_VSM_WIVSMTrack_type`; the managed `GetTrack` wrapper does not remap it.
The editor's load initialization also invokes `ReplaceVoiceHelper.ReplaceVoice`,
which can replace missing or mismatched voices with available ones, so it is not
an identity-preserving operation and is not used by this bridge. Its VSM manager
sets database, DSE, license-derived YVS, track limits, and cache capacity; the
bridge's YVS selection uses the same license-result categories. No causal link
between the remaining manager settings and this bug has been established.

The installed `VSM.dll` contains a JSON schema accepting track type values 0,
1 and 2 and defining `voice`, `aiVoice`, `secondaryVoice` and
`secondaryAiVoice` as part fields; the schema does not specify the semantic
mapping of type values. This native schema corroborates the diagnostic fields,
but does not explain why native save omitted them or why native open returns
`MidiAi`. The 6.13.3.1 editor assembly version matches the bridge engine version.
An independent new private host opened the earlier saved PPSF-derived VPR and
also reported all four serialized type-0 tracks as `MidiAi`
(`artifacts/feature-acceptance-1a0d64460db7/remaining.classic_separate.json`).
This rules out reuse of the original importing host as a necessary condition for
that reproduction; it does not rule out other native caching or initialization.

Static x64 inspection of this installed `VSM.dll` found a narrower native
decision path: the routine at RVA `0xAE180` dispatches serialized track type 0
and type 2 to the routine at RVA `0xADB00` with corresponding values. That
routine reads classic `voice.compID`/`voice.langID` or `aiVoice.compID` from
parts and performs virtual calls before returning a mode. The caller then
selects between native classic and AI track-creation routines at RVAs `0x900F0`
and `0x90350`, respectively, corroborated by the native sequence virtual table
and managed `insertMidiTrack` and `insertMidiAiTrack` export wrappers. A pair of
virtual calls early in the helper is passed 1 and 0. Their vtable slot `+0x10`
matches the installed VDM export `VDM_DatabaseManager_numVoiceBanks`, and the
later `compID` lookup slot `+0x28` matches
`VDM_DatabaseManager_voiceBankByCompID`. The installed `VDMVoiceBankType` enum
maps Dse to 0 and Dnn to 1. Under that matching database-interface interpretation,
the observed 21 Dnn and zero Dse banks select mode 2 immediately; if only Dnn
is absent the routine selects mode 0, and if both counts are zero it returns the
supplied mode. This explains the observed forced AI track without requiring a
part voice field. The exact identity of the object returned to this call and
remaining per-voice selection behavior have not been independently traced or
tested with an installed classic bank. These RVAs are specific to this binary.
No installed DLL or license state was modified.

`artifacts/classic-native-audit-025cb925c173.json` contains the exact
instructions, bytes, enum text and prior runtime bank counts used for this audit.
Run `tools/check_interchange_remaining.py --static-classic-audit` with the
workspace Python to record the same version-specific evidence again; the counts
are explicitly historical, not a new live enumeration. The tool uses the
workspace's existing `.tools/analysis` and `ilspycmd` installations.

The `ProjectIntegrity.cs` checks are integrated into the native open, save and
clone paths. They detect VPR type-0 tracks and current
`Dse=0, Dnn>0` before native VPR open and report `missing_classic_bank`; compare
actual loaded track types, counts and specified part voice IDs against the input;
and check every nonempty native primary/secondary voice ID and the voices table
against a staged save before publication. They also compare staged track types
and part counts. A rejected snapshot must not replace an existing destination;
source files and the open native session remain available. These checks are not
evidence of full classic support or synthesis. Classic track creation and
editing within a live session remain distinct from reopening or rendering with
a missing voicebank. A nonzero Dse count alone does not prove that a particular
component is installed. Focused real-MCP run
`artifacts/feature-acceptance-8a94a4ae3dcd/` verified the expected open, clone,
and overwrite-save rejections, an unchanged source session and pre-existing
destination, and an ordinary AI save/reopen control. This is not a successful
classic roundtrip or a complete cross-format acceptance.

One direct audio import followed immediately by clone returned an empty clone;
calling `voicebanks` before clone made a separate run pass audio independence
including export after source closure (`artifacts/feature-acceptance-71e10f9c1900/`).
That observation does not alone distinguish database initialization from timing.
With the host initializing its native database at manager construction, the
focused no-prior-voicebanks test passed on the rebuilt host: the edited clone
did not change its source, and original and current WAV assets matched the input
after closing the source (`artifacts/feature-acceptance-caccb6a49ed7/`). This is
one audio fixture, not an assertion about every possible asset.

## Focused checks

`tools/check_interchange_remaining.py` runs through the existing MCP acceptance
harness without building. `remaining.clone_audio` edits a clone, checks the
source, closes the source, and compares original and current clone audio with
the input before saving the clone. `remaining.vsqx3`, `remaining.vsqx4` and
`remaining.ppsf3` compare all vocal parts' reported voice identities, tracks,
and notes before and after native VPR save/reopen. They require actual fixtures;
the PPSF V3 case also checks the ZIP signature. The V2 case remains available
as `interchange.ppsf2` in `tools/verify_features.py`. Passing one fixture does
not establish support for all files or voicebanks.

`remaining.integrity_guard` exercises the actual PPSF V2 import, rejects an
existing classic VPR when the installed bank counts trigger conversion, and
checks that rejected clone and save preserve the source, with save also
preserving an existing output.
`remaining.integrity_ai` is a positive ordinary AI save/reopen control. Both
require the integrated rebuilt host and produce runtime receipts; neither is a
claim that classic roundtrip or synthesis succeeds without a classic bank.

The public PPSF 3.2 `Monologue.ppsf` sample is available from the author's
[page](https://javawock7618.blogspot.com/2021/11/5ep-2nd11111-feat-hatsune-miku111.html) and
[public folder](https://drive.google.com/drive/folders/12A0GeYGkXnaF6wyi5q-R7sdlKkZ4WQ5E).
`tools/fetch_public_ppsf_fixture.py --source monologue` fetches the original
archive into `.runtime`, validates its declared PPSF version and 190-note count,
and writes provenance; its app version is project-declared metadata, not proof
of native-editor authorship. No license is asserted or source song redistributed.
The separate `--source utaformatix` fixture is pinned open-source test JSON
packaged as a ZIP, not a native-editor-authored project.

For the Monologue sample, `artifacts/feature-acceptance-a3cc87f45ce7/`
verified all 190 source events' absolute position, duration, pitch and lyric
against native import, plus 80 BPM and 4/4 against native import and reopen;
native note timing, pitch, lyric and phonemes also survived save/reopen. PPSF
tempo scaling and meter fields were cross-checked against the pinned
[UtaFormatix PPSF parser](https://github.com/sdercolin/utaformatix3/blob/91d0aeb994bc846e380ea98cd4c6f75c5ea7c6ae/core/src/main/kotlin/core/io/Ppsf.kt).
The NT source symbols differed from native VOCALOID phonemes for 99 of 190
events in the inspected sample; equality between those symbol systems is not
claimed. NT singer identifiers are distinct from VOCALOID voicebank IDs, and
the initially imported part reported empty VOCALOID voice IDs.

One explicit test selected the installed `asa` Dnn voice after import; its ID
survived save/reopen, and a native 99.5001-second render was independently
decoded as nonzero PCM (peak 0.2026367, RMS 0.0377195). Lyrics and phoneme values
and validity flags were unchanged by the explicit selection. The first test case
was marked failed solely because its generic WAV reader imposed a 30-second
limit; the existing output was inspected without a second render, and the
case's reader was updated for longer bounded streaming. The original receipt is
`artifacts/feature-acceptance-9ec33f2e51bf/`;
`artifacts/ppsf3-render-stream-check-9ec33f2e51bf.json` records the corrected
streaming function's independent pass without a new render. The original case
remains failed, and the corrected end-to-end case has not yet been rerun. This
is explicit assignment, not retention of the
original NT singer or a change to default import behavior. Other fixtures and
voicebanks remain unverified. The installed
managed `WIVSMSequence` wrapper exposes `Save` and `SaveSMF`, but no PPSF save
method; this alone does not rule out other native APIs.

The maintained integrity regression now creates its classic empty-track VPR
through the current native API, rather than depending on an old generated
output. `artifacts/feature-acceptance-2ccd799e0d5e/` records this variant and
the current operation-catalog check. The genuine PPSF V2 input is still
required for the voice-loss save/clone checks.
