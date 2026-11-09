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

No PPSF V3 fixture has been found in the workspace. The installed managed
`WIVSMSequence` wrapper exposes `Save` and `SaveSMF`, but no PPSF save method;
this observation alone does not rule out other native APIs. PPSF V3, VSQX
identity for other fixtures remains unverified until focused cases are run
against the rebuilt host and genuine fixtures.
