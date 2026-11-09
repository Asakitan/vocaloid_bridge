# Master volume timeline investigation (session 24)

## Current evidence and boundary

The session 23 private synthetic-AI receipt `artifacts/master23-probe-c9e1fe80edaa.json` demonstrates one insert and one delete range with both tempo options. It records native pointer, tick, value, explicit rollback after a successful pending edit, and undo/redo. Explicit rollback is not evidence of native internal failure recovery. No host red-baseline, failure injection, build, or guard change was performed in this investigation. The master-volume timeline guard remains in place.

## Probe design

Use fresh independent synthetic AI fixtures per operation and tempo option, with unique values and unknown-field markers for each original master point. Capture pointers, positions and values immediately before and after the native call, rollback, commit, undo and redo. Record the actual boolean return or exception, and distinguish a failed native call from a successful call followed by explicit rollback. Run insertion and deletion with `includeTempo` both false and true for each fixture:

- Existing events at start and end, including a point immediately before start, to observe retained, moved, deleted and generated identities.
- No event at either boundary, with unequal neighboring values, to exercise interpolation and generated boundaries; repeat with equal neighboring values.
- An event at start minus one, an event at end, and events within the range, to expose generated-point destination conflicts and replacement decisions.
- Start zero and adjacent ticks, separately for insert and delete, to observe initial-point semantics and invalid range handling.
- No interior points and several interior points, with events before and after the interval; use a nontrivial tempo map so tempo options actually differ.

The probe must compare original and resulting pointers independently of positions, test pointer uniqueness and destination uniqueness, and record all allocations and disappearances. For host red-baseline use a marked fixture and assert the existing extension guard rejects the requested timeline edit before mutation, then confirm native state and saved unknown fields are unchanged. A true rollback test requires a reproducible failure occurring inside or after native mutation, with before/after identity and archive snapshots, return/exception evidence, and rollback result. An explicitly requested rollback after success is a different test. Do not infer native failure from host preflight rejection.

## Integration criteria and unproven scope

A future independent candidate may snapshot native master identities and map retained originals to their actual validated destinations. New identities receive empty extension objects; removed identities lose their extensions. Validate event count, unique pointer and tick, values, destinations, and collision handling before publishing archive state. Hook capture before the native call and apply only within the existing transaction, then verify save/reopen, clone and history behavior. This is a proposed contract, not a demonstrated implementation. Native failure recovery, unknown-field preservation, interpolation branches, zero boundaries and conflict behavior remain unproven. No unrelated guard is in scope.

## Private managed identity probes

The existing ordinary synthetic AI fixture `output/feature-master23-delete-native-before.vpr` was run through `.runtime/probe_master23.ps1` on isolated private desktops with both `includeTempo` values. Receipts are `artifacts/master24-missing.json` for `[1100,1450)` (neither endpoint exists) and `artifacts/master24-adjacent.json` for `[999,1500)` (end exists and start is adjacent to the next point). Original master points were `(0,0), (900,-1), (1000,-2), (1200,-3), (1500,-4), (2000,-5)`. The managed calls succeeded for insert and delete in all four option/range combinations. Within each range, both tempo options produced the same master identity outcome:

- Missing-boundary insertion retained all original identities, shifting points at and after 1200 by 350; new points appeared at `(1100,-2)` and `(1450,-2)`.
- Missing-boundary deletion removed the original 1200 identity, shifted original 1500 and 2000 to 1150 and 1650, and created `(1099,-2)` and `(1100,-3)`.
- Adjacent insertion retained all originals, shifting points at and after 1000 by 501; new points appeared at `(999,-1)` and `(1500,-1)`.
- Adjacent deletion removed originals 1000 and 1200, shifted originals 1500 and 2000 to 999 and 1499, and created `(998,-1)`.

For all eight cases, the recorded master pointer/tick/value lists after explicit rollback and undo matched the respective before lists, and redo matched committed lists. Explicit rollback followed successful calls and does not demonstrate recovery from an internal native failure. The first launcher attempt used Windows PowerShell 5 and failed to load the .NET 8 host; the recorded runs used PowerShell 7. No extended project or production guard was modified. Receipt pointers are meaningful only within their own process and session. The probes do not establish arbitrary interpolation, unknown-field mapping, save/reopen, clone, or native failure recovery.
