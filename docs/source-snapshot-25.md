# File source consistency — session 25

## Change

`ProjectStore` opens a resolved Windows VPR source with one read-only Win32
handle that shares reads but not writes or deletion. The same handle backs one
`ZipFile` for sequence reading, transformation and copying of all archive members.
The source handle remains open until the independent output has been closed.
`read` and externally supplied `write_copy` use the same source-opening policy;
`write_copy` applies the caller-provided data to the archive opened in that call
and does not establish when the caller obtained that data. An existing conflicting
writer causes the source open to fail before output creation.

This is a Windows file-level policy, not a native project transaction or a
replacement for the archive-extension guards. It does not change output exclusivity
or the validity-sidecar check. The probe does not establish behavior for every
filesystem, remote share, writable mapping, crash or path-race condition. The
platform sharing contract is documented by [CreateFile](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilea).

## Controlled evidence

`tools/check_source_snapshot_25.py` uses uniquely named synthetic archives in
`artifacts`, with a child process constrained to that directory. The old code's
`artifacts/source-snapshot-25-cdvpdpa1/receipt.json` shows a replace between
sequence read and archive copy: source A's sequence was combined with source B's
resource and comment. A preexisting writable handle was also not excluded.

The new code's `artifacts/source-snapshot-25-uvxy01h9/receipt.json` shows that
during the held read handle the competing in-place open and replacement failed,
the output sequence/resource/comment all came from A, and replacement succeeded
after release. A previously opened writable handle made the edit fail before
creating output; a validation error also released the handle without output.
Each child was waited for. One interim probe run stopped on an unrecognized
`pywintypes.error`; the test was corrected to identify the Win32 sharing violation
and rerun. These controlled observations are not proof of arbitrary concurrency.

`artifacts/feature-acceptance-3fc96299dad5/summary.json` separately records eight
selected real-MCP cases and cleanup passing, including VPR editing and native
create/open/save, with no owned foreground switch or remaining owned session.
