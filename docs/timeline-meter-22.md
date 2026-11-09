# Generated meter boundary identity — session 22

## Native observation

A private-desktop probe ran the installed native implementation on the synthetic
AI fixture `output/feature-467a9a7eaeab-006-delete-native-before.vpr`, with
`DeleteTime(1920, 4300, false)` and `include_tempo=true`. The original meter map
was bar 0: 4/4, bar 2: 3/4, bar 3: 4/4, bar 4: 5/8. In both cases the
result was bar 0: 4/4, bar 1: 3/4, bar 2: 4/4, bar 3: 5/8. The bar-1 object
had a new pointer distinct from every original; original bar 2 disappeared;
original bars 3 and 4 retained their pointers as they shifted. Rollback and
undo restored the original pointer map; redo restored the committed map. The
pending and committed generated objects may have different pointers because the
probe performs an edit, rolls it back, and then performs the edit a second time
before committing.

The original observation is `artifacts/meter-identity-22-6e7a06b52bb9.json`.
The reusable `tools/run_timeline_identity_probe.py` and
`tools/probe_timeline_identity.ps1` were parameterized and rerun on the same
fixture using `--start-tick 1920 --end-tick 4300 --operation delete`; its
`artifacts/timeline-identity-probe-47ef55371dd5.json` has the same observed
identity relationships. These are bounded observations, not proof for arbitrary
boundary collisions.

The locally decompiled installed `WIVSMSequenceExtension.DeleteTimeInTimeSigTrack`
computes begin/end bars, inserts a signature at begin bar when endpoint meter
values differ, removes signatures in `(beginBar,endBar]`, then shifts signatures
after end bar. Inserting over an existing event at begin bar has not been
identified; that collision remains guarded.

## Implementation and verification

`ProjectArchiveTimeline.cs` models an unoccupied generated boundary with empty
unknown fields. Deleted events lose their payload, retained events keep their
own payload, and candidate and actual states require the complete survivor map
and a generated boundary pointer distinct from original pointers. Existing
controller transfer, extended audio, archive media and pitch deletion guards
remain unchanged.

The old 0.16.0 host rejected the positive fixture before mutation in
`artifacts/feature-acceptance-336f60d13d89/summary.json`; cleanup passed. After
one Release build, `preservation.timeline_meter_22` passed with both tempo
options, including simultaneous generated meter and tempo boundaries, metadata,
undo/redo, clone, reopening and source protection in
`artifacts/feature-acceptance-80b1c4779514/summary.json`. That same batch
checks the existing occupied-start collision guard, other timeline regressions,
and the reviewed track/controller/pitch guards. It contains 12 feature cases
and cleanup, all passed, with no owned foreground switch or remaining session.
Unverified meter collisions and other item-extension combinations remain guarded.
