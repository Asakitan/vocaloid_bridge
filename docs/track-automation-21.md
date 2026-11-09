# Track automation event extensions — session 21

## Baseline

The previous host rejected a synthetic VOCALOID:AI VPR with an unknown field
on a track-volume event during `project_open` in
`artifacts/feature-acceptance-79945951763e/summary.json`. This red baseline and
its cleanup are preserved; it is not evidence of support.

## Implemented transaction

`native/ProjectArchiveTrackAutomation.cs` stores each extended volume or pan lane
on its native track identity in the entity journal. It validates the complete
native tick/value map on capture, before and after edits, after history
transitions and during output overlay. A same-tick upsert keeps the unknown
fields; replace keeps the selected surviving points and the zero-tick baseline,
while removed points lose their fields and new points start without them.
Track update/reorder requires the same owner and complete expected lane maps
before commit, independently of removal notifications. The existing track
ambiguity check also applies to this payload. Source-track project merge is
guarded before mutation when the source has track-automation extensions.

`tools/check_track_automation_21.py` checks track-volume and track-pan edits,
replace, remove/recreate, undo/redo, clone/reopen, duplicate ticks,
indistinguishable tracks with distinct markers, timeline and track-duplicate
guards, source-merge rejection and source preservation. Two further dual-track
cases check owner fields after track update/reorder and both history directions.
These four cases passed in
`artifacts/feature-acceptance-e8eb9b6496cb/summary.json`, with the associated
cleanup and without an owned foreground switch or remaining session.

This is bounded fixture evidence, not arbitrary array or migration support.
Time edits, track duplication/removal, clipboard transfers, project source
merge and other unverified mutations remain guarded when this extension is
tracked. The earlier controller cross-project, extended-audio and
archive-bearing media-update guards remain unchanged.
