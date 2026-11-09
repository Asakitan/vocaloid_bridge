# Occupied meter boundary collision — session 23

## Native identity observation

The private-desktop identity probe ran on the synthetic AI fixture
`output/feature-467a9a7eaeab-006-delete-native-before.vpr` with
`DeleteTime(3840, 5500, false)` and each value of `include_tempo`. The receipt is
`artifacts/timeline-identity-probe-eee54488979d.json`. Before deletion the
meters were bar 0 4/4, bar 2 3/4, bar 3 4/4 and bar 4 5/8. In both variants the
original bar-2 object retained its pointer and changed to 4/4, the original
bar-3 object disappeared, and the original bar-4 object retained its pointer
and shifted to bar 3. Pending, commit, rollback, undo and redo snapshots show
these identity maps. The probe has one tempo and does not cover simultaneous
tempo boundary generation.

Rollback here is an explicit rollback after a successful pending operation,
not an injected native failure. No conclusion is drawn about exception or
partial-failure recovery, pointer reuse in other cases, initial-bar collisions
or duplicate events. The fixture has no unknown-field markers, so this is
identity evidence rather than a serialized metadata roundtrip.

## Positive fixture, red baseline and review

`tools/check_timeline_meter_collision_23.py` creates an AI fixture with distinct
unknown fields per meter event. Its expected result retains the begin-bar
payload, drops the removed bar-3 payload and moves the bar-4 payload with its
native object. It includes both tempo options, undo/redo, clone, reopen and
source protection assertions. On 0.17.0,
`artifacts/feature-acceptance-7e646bbd736f/summary.json` records the first
positive deletion rejected by the occupied-boundary guard, followed by
successful transport cleanup. Later assertions, including the second tempo
option, did not execute; this is a red baseline, not a successful metadata
transaction.

Automatic review rejected a proposed production mapping and guard removal:
unknown-field roundtrip and native failure rollback were not established, and
the reviewer identified metadata-loss risk and a need for approval specific to
the guard change. The patch was not applied; the occupied-boundary guard and
all earlier reviewed guards remain unchanged. The prospective test is
standalone and is not registered as a release-pass case. Further work requires
native failure/rollback evidence and a reviewed extension transaction before a
separate approval request; do not route around the retained guard.
