# Synthetic media refresh and race observations — session 22

## Method and receipt

A fresh copy of the session 21 synthetic ordinary AI media fixture was placed under `artifacts/media-failure-22-045a23ff9013/media20-private`. The existing `tools/probe_media_process_20.ps1` was launched by `IsolatedProcess` on a private desktop, with no interactive editor or user library involved. The driver is retained at `.runtime/media-failure-22.py`; its observations are in `artifacts/media-failure-22-045a23ff9013/receipt.json`. Its `cleanup: true` records that `IsolatedProcess.close()` returned, not an independent process enumeration. The fixture and receipt are retained as evidence.

## Check-to-replacement race

The probe confirmed the target matched its snapshot, then wrote an external marker after that check, then replaced the file with a prepared candidate via `MoveFileEx`. The candidate survived and the external marker did not. This controlled interleaving demonstrates lost external data when no exclusion spans check and replacement; it does not establish behavior under all Windows sharing modes or filesystems.

## Locked refresh and recovery

An exclusive sharing handle was opened on the candidate `property.json`. While held, an independent read raised `PermissionError`, confirming that the intended access restriction was active. The manager then called `ReadAllClipFiles()`: its returned status was `None` (the native success enum), but enumeration no longer found the target, and the retained original clip reference reported an empty name. After unlocking, the original reference still reported an empty name and tempo 12345. A second refresh returned `None` and a newly enumerated clip had the prior name and tempo; the old reference still had an empty name. The candidate marker remained on disk after the sequence.

Thus this is evidence of a silently incomplete refresh and retained-reference invalidation under a verified sharing conflict, **not** evidence of a non-success refresh return, an exception path, or full recovery of existing references. The lock proves an external read was denied; it does not directly instrument native file-open calls. Disk content was observed after the sequence, not sampled during the held lock. These observations do not establish crash durability or general cache consistency.

## Implications and next steps

A return status alone is insufficient for this observed failure mode. Any future transaction design must account for enumeration validation, invalidated references, and fail-closed cache handling, alongside a verified concurrency protocol and general extension identity. Obtain separate evidence for an actual native non-success return or thrown failure, partial multi-clip refresh, and crash recovery before proposing production behavior. Ordinary media updates still lose unknown fields; archive-bearing update guards remain unchanged.
