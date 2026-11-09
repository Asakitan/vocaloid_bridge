# Media concurrency and process-crash recovery — session 32

## Scope and protocol

Version 0.23.0 replaces the check-then-replace publisher from session 31 with a
journaled, no-overwrite protocol for ordinary bridge-owned media properties.
All new-version media operations share a workspace-scoped named mutex. Reads
rebuild the native catalog under that lease, so another bridge process's
completed write is not hidden behind a stale manager. Busy callers receive an
explicit error instead of racing another writer.

The journal publisher keeps the original property open with exclusive read,
write and delete access throughout native staging. The native child edits a
copy; original bytes are copied from the bound handle, not reopened by path.
The source clip's file identity and digest bind recovery to the same media
object. Before detaching the live property, the publisher durably writes the
original bytes, candidate bytes and a manifest containing identities and
digests. Markers are published only after their complete contents are flushed.

Publication renames the bound original into the journal and then renames the
bound candidate to the target, both with replacement disabled. A competing
entry created in the short gap therefore causes an error, not an overwrite.
This is a serialized journal transaction, **not** one atomic namespace swap for
arbitrary external readers: non-cooperating readers can see a sharing error or
a briefly absent path. These choices follow Windows [file-sharing semantics](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)
and [no-replacement rename semantics](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_rename_info).

After native reload/readback succeeds, a flushed commit marker completes the
operation. The active journal directory is renamed to a completed-directory
name before recursive cleanup, separating partial cleanup from active recovery.
Every staging file, snapshot, helper temporary directory and build temporary
directory used in this session is under the E-drive workspace.

## Recovery decisions

Before media access, a new-version host recovers journals under the same mutex:

| Durable/observed state | Action |
| --- | --- |
| Staging owner but no published manifest | Discard private staging; live file was not detached |
| Valid journal; original bytes still at target | Abort the uncommitted operation |
| Valid journal; target missing after detachment | Restore the original without overwriting a new entry |
| Valid journal; target is the exact uncommitted candidate | Move it aside, then restore the original |
| Valid commit marker | Retain the committed target and finish journal cleanup |
| Foreign property content/identity or changed source clip | Preserve current data and journal; report a conflict |

The saved original is used if its displaced live file is missing. Byte and
identity checks prevent treating a different candidate as transaction-owned.
Recovery renames also disable replacement. An explicit external conflict is
not silently resolved by guessing which writer the user intended to keep.
Legacy session-31 recovery directories without the new markers are retained.

## Necessary evidence

Only this changed protocol was exercised; no general suite was rerun.
`artifacts/media-journal-32-evidence.json` indexes the five covered branches:

- `artifacts/feature-acceptance-7a197ab75ddc/summary.json` records successful
  assertions for exclusive writer rejection, cross-process bridge contention,
  an injected exception before detachment, process termination after detachment,
  process termination after publication, and termination after the commit marker.
  Each recovered state agreed with native media getters and preserved clip bytes.
  Its overall case failed later in the foreign-entry test harness.
- `artifacts/feature-acceptance-eb00cdb1cef0/summary.json` passed the isolated
  foreign-entry case and transport cleanup: the competing file was preserved,
  conflict was reported, and removing only that test-created competing entry
  allowed automatic restoration of the original and native-cache refresh.

The first harness invocation failed on a PowerShell reflection argument wrapper;
the foreign-entry harness then exposed non-UTF-8 localized error output. Both
were corrected without changing the native publisher or rerunning the already
covered four branches. Those failed receipts are retained. The native source
was built once for the protocol and once after review made the staging-owner
marker use the same atomic marker primitive; both builds had zero warnings or
errors. Final full semantic preflight covered 29 files and 211 references.

## Remaining limits

Tests terminate real owned processes; they do not cut physical power or damage
storage. Write-through and flush requests rely on the OS/filesystem/device
honoring persistence. Network shares, hostile filesystem redirection, legacy
writers that ignore the lease, arbitrary storage corruption and ACL-specific
cases are not claimed as verified. Foreign conflicts deliberately retain data
for an explicit resolution. The archive-bearing media guard is unchanged.

Failed synthetic clips and resolved journals from this session were cleaned.
Runtime process-temp and journal roots were empty afterward. A compiler-server
assembly still in use was left in the E-drive build-temp directory; no global
compiler process or user application was terminated to remove it.
