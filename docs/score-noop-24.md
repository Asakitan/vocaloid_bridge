# Score name-only no-op, session 24

## Observation and red baseline

An independent private native project with one `MidiAi` track named `Noop AI`
was saved, closed and reopened. On the previous host, a same-name-only
`track.update` returned successfully but marked the clean session dirty without
changing its native history. The standalone initial probe observed this before
its later assertions; a real-MCP reproduction is preserved in
`artifacts/feature-acceptance-410a03ae2d30/summary.json` (one failed case,
cleanup passed). The earlier sandboxed attempt failed to create its private
host snapshot with access denied; the approved run reached the dirty assertion.

## Implementation and verification

`native/ScoreOperations.cs` returns the existing summary when a `track.update`
contains only an unchanged name, after verifying that native edits are
unstaged. It neither calls the mutation wrapper nor changes the existing dirty
state. Other fields, mixed updates and the native history behavior of unstaged
setters are not generalized by this change.

The rebuilt host passed `score.track_name_noop_24` in
`artifacts/feature-acceptance-f4c4b6029e12/summary.json`: a clean project stays
clean, an already dirty project stays dirty, history is unchanged, a real
rename saves and reopens, and a same-name request with an independently staged
native tempo is rejected without consuming that staged edit. Source bytes are
unchanged. The same batch checked ordinary track editing, lifecycle, file-level
event metadata and existing review guards; no owned foreground switch or
remaining session was reported. This is bounded evidence for the name-only
fixture, not all no-op operations or arbitrary extensions.
