# Ordinary media property preservation — session 20

Historical preservation investigation; the 0.22.0 production path and its remaining recovery limits are documented in [current media properties](media-properties-31.md).

## Regression and evidence

`tools/check_media_property_20.py` captures a new ordinary AI clip in the bridge-owned library, confirms the clip has no `vocaloid_bridge_archive_entities_v1`, and injects synthetic unknown nested values at the property root and under `part`. The regression expects both to survive a successful `media_update`, together with native name/tempo readback and unchanged clip bytes. It deletes the fixture in a `finally` block.

Against the existing host, `artifacts/feature-acceptance-5f2872117662/summary.json` records a failing preservation case: native update succeeded, but both injected values disappeared. Transport cleanup passed. This is a red baseline, not a successful preservation implementation. Earlier isolated native save and locked-file observations are documented in `media-update-probe-19.md`.

## Transaction boundary and outstanding evidence

The production path calls the native property editor's `Save(true)` on the live owned clip and then reads the same manager object. Prior evidence shows that success changes the property file and cache, and a read-shared lock caused a tested save failure without changing observed bytes or cache. It does not establish behavior for mid-write errors, crashes, concurrent writers, manager refresh, or external replacement.

Restoring unknown fields after saving the live file would create a second fallible write after native success and could leave the file stripped or cache inconsistent. A design requires isolation of native serialization, merging unknown nested members without overwriting requested native fields, an atomic same-volume commit with a concurrency check/lock, and a demonstrated manager-cache synchronization and failure contract. Those properties remain unverified; no production change was made on the basis of the current evidence.

The archive-bearing update guard and other protected paths remain unchanged. This regression exercises only its newly generated ordinary AI clip; it does not establish other property shapes, process-crash durability, or broader acceptance.

## Same-process staging probe

`tools/check_media_native_20.py` and `tools/probe_media_native_20.ps1` copy an ordinary AI clip into two separate artifact roots and create two native managers in one private-desktop process. In `artifacts/feature-acceptance-7069a2a902c4/preservation.media_native_20.json`, the intended staged editor save instead changed the live copy and live cached name; the supposed stage copy retained the original name. A subsequent locked replacement failed, but the live file was already changed by the earlier native save. A later replacement and `ReadAllClipFiles()` restored the original name in both the looked-up and old object in this observation. This rules out treating these two manager instances as proven independent; it does not establish the native implementation's internal singleton mechanism. The probe failed its expected staged-commit assertion and its cleanup passed. Earlier attempts `1d8554a93433` and `4938cafa6802` failed inside the probe before the replacement observation due to PowerShell member and null-argument mistakes, respectively.

Future work must isolate native serialization in a separate process and verify which file the native editor modifies, then test locked commit, concurrent changes, manager refresh failure, and post-commit recovery. This same-process experiment cannot establish atomic replacement or safe rollback, and no production change is justified by it.

## Separate-process staging probe

`tools/check_media_process_20.py` and `tools/probe_media_process_20.ps1` exercise two new ordinary AI fixture copies with a manager per private-desktop process. `artifacts/feature-acceptance-e07cbc63bd95/summary.json` records a passing targeted observation and cleanup: the staged native edit changed its own copy without altering the live bytes or cached name; a read-sharing lock rejected the attempted replacement and the live bytes and cache remained unchanged; after unlocking, replacement retained the injected top-level nested marker, the live cache remained stale until `ReadAllClipFiles()`, and a successful refresh returned the staged name and tempo. The initial probe attempt `72cdf08fa8ad` failed before subprocess start due to a test-script ID variable error.

The dispatcher later found that the checked-in candidate again referenced its fixture ID before assigning it. The ID assignment and case name were corrected, and the current script passed the same observation and cleanup in `artifacts/feature-acceptance-6db3c881f0f0/summary.json`.

The test restores one known top-level marker after native serialization; it does not implement a general unknown-member merge. It also does not exercise refresh failure after commit, external concurrent modification between snapshot and replacement, crashes, replacement durability, nested unknown fields under known objects, or production-host manager behavior. In particular, a successful replacement followed by failed refresh remains an unresolved partial-commit boundary. The success observation alone does not justify changing production code.
