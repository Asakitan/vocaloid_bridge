# Ordinary media property transaction — session 21

## Baseline

The existing host was tested against `tools/check_media_property_20.py`, which creates and deletes a fresh bridge-owned ordinary AI clip and injects unknown fields at the root and under `part`. `artifacts/feature-acceptance-25f45d337d42/summary.json` records the expected red result: `media_update` succeeded but discarded both markers; transport cleanup passed. The archive-bearing guard was not changed. The first sandboxed attempt stopped before fixture creation because creation of its artifact directory was denied; the authorized rerun produced the cited evidence.

## Transaction analysis

A separate process can stage a native edit on a fixture copy, as observed in the prior session 20 probe, but that observation is not a complete production transaction. In particular:

- A general merge must identify which members and collection elements the native serializer owns. Recursively copying missing object members alone does not establish identity for arrays, removed parent objects, duplicate keys, or type changes; blindly restoring those can overwrite native intent or associate extensions with the wrong entity.
- A snapshot comparison followed by replacement has a check-to-replace race unless the chosen Windows sharing and replacement protocol prevents all cooperating and external writers for the full interval. A file handle on the old file alone does not prove that a directory entry cannot be replaced. This has not been demonstrated for this host and its actual filesystem.
- Atomic namespace replacement is not itself proof of durable commit after a crash, nor of recovery of process-local native cache. The session 20 lock experiment showed one rejected replacement and one successful refresh, not all failure modes.
- `ReadAllClipFiles()` is a fallible native call after replacement. Its failure may leave disk committed while manager state is stale or partially changed; rollback is another fallible operation, and retained native object references might also have changed. The existing API has no demonstrated committed-but-cache-invalid state or recovery contract.

Because these boundaries remain unproved, no production update or helper was introduced. Ordinary `media_update` still drops the demonstrated unknown fields; do not describe this as fixed. The archive metadata, controller cross-project and extended audio guards remain untouched.

## Next evidence required

Use only new synthetic ordinary fixtures in private processes to establish element identity and merge conflict behavior, directory-entry concurrency and lock behavior, and injected refresh failure with disk/cache observations and explicit recovery semantics. A candidate is appropriate only after the transaction can make a truthful failure report and prevent stale-cache operations. Crash durability remains a distinct claim requiring its own evidence.

## Independent-process synthetic comparison

`tools/check_media_process_21.py` creates a new ordinary fixture and uses the private processes from the session 20 probe. `artifacts/feature-acceptance-2ca7dc2676b2/summary.json` records a passing probe and cleanup. Native staging changed the name and tempo without modifying the live copy. The probe explicitly restored three known test markers: a root object containing an array, an object under `part` containing an array, and an array under `filter`; after replacement the markers and the original native `filter.languages` array matched, while the staged tempo and name survived. This is a manual test-specific merge, not a generic merge algorithm, and does not establish identity when native arrays are edited or reordered.

After taking a byte snapshot, the probe wrote an external synthetic marker to the target and compared current bytes with the snapshot. The comparison detected the change, skipped replacement, and observed the external bytes and prior native cached name/tempo unchanged. It then restored the fixture for the separate lock and success observations. This demonstrates detection at that instant only: there is no lock spanning comparison and commit, and another writer can race after comparison. It is not a production concurrency guarantee.

The existing probe exposes successful refresh, not a controlled failure injection into `ReadAllClipFiles()`. A refresh-failure outcome was not observed in this session; partial cache mutation and recovery remain open. No production behavior was changed.
