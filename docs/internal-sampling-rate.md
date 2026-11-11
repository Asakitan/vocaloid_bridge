# Internal Vocal Synthesis Sampling Rate

The project sequence rate and the output mix rate are distinct. Project
creation and editing preserve the native `44100`, `48000`, and `96000` enum
values. Current vocal-part rendering is explicitly guarded to `44100` Hz;
this is a reported boundary, not a conversion of the project or a claim that
all rates have been dynamically tested. Output-only mixdown supports separate
rates and does not change the project sequence rate.

## Existing Runtime Observations

- A `48000` Hz project with track `bus_no=0` failed native part rendering with
  `FailedToCreateDseWaveBuffer`; the earlier combined rate/bus failure is
  documented in `artifacts/score-deep-receipt-28484b82a63a.json`. The isolated
  `bus_no=0` failure was observed in the session 07 command output, not saved as
  a standalone machine receipt. It excludes the bus value as a necessary cause.
- The `96000` Hz DSE path has not been run. Both non-44100 project values are
  accepted and read back, but current part-render requests return a fast
  explicit guard error; `artifacts/audio-routing-guard-9f833b494596.json`.
- A 44100 Hz project produced nonzero native vocal renders and 44100, 48000,
  and 96000 Hz native output mixes; `artifacts/audio-routing-acda7649870c.json`.
  Output-rate success does not establish high-rate internal synthesis.

## Installed Managed and Native Code

The installed managed editor's four observed sequence-creation sites specify
44100 Hz, and a search of the decompiled managed assembly found no call site
for `SetSamplingRate`; the relevant automated matches are in
`artifacts/audio-routing-static-acda7649870c.json`. Its managed
`DSEManagerIF.CreateManager` takes a database manager and calls native create
and initialize; it exposes no separate sampling-rate parameter. This does not
rule out native interfaces not represented in that wrapper.

The version-specific read-only scanner `tools/check_internal_rate_static.py`
records VSM instructions and native enum ordinals in
`artifacts/internal-rate-static-aa7e6f0f7992.json`. The scan observes:

- The native sequence rate setter checks all three enum values, consistent
  with rate storage support rather than proving synthesis support.
- In a function at RVA `0x60570`, an internal object's `+0x28` field is
  compared with `44100` at `0x60b18`. On the non-equal branch, `0x60b49`
  writes `0x10` into a notification structure before returning. Managed
  `VSMRenderCancelReason` ordinal 16 is `FailedToCreateDseWaveBuffer`.
- A separate function at RVA `0x59aa0` compares an internal object's `+0x28`
  field with `44100` at `0x59ed8`; the non-equal branch returns `0x49` at
  `0x59f6e`. Managed `VSMResult` ordinal 73 has the same failure name.

The Reference Manual 6.13 (page 37) states that pasted audio is converted to
44.1 kHz/16-bit "in accordance with the internal operating specifications of
VOCALOID", and its export dialog offers the output sampling rate separately.
Session 36 confirmed through MCP that 48000 and 96000 Hz projects store their
rate, that part rendering and mixdown reject them with the explicit guard
message, and that rendering succeeds after `sequence.update` sets 44100. The
native 96000 Hz path itself was still not run.

These static branches are consistent with the observed 48000 Hz failure and
show an explicit 44100 comparison in the installed VSM binary. The exact
internal object type, provenance of its `+0x28` field, full dynamic call chain,
and whether another supported native configuration reaches a different path
remain unproven. This evidence does not identify a safe rate/configuration
pair that enables internal 48000/96000 synthesis. The diagnostic reads
installed files only; it neither patches the binaries nor changes the guard.
