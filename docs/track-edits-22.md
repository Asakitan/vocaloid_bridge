# Track automation with ordinary score edits — session 22

## Baseline and candidate

The 0.16.0 source guard rejects `track.create`, `part.create`, `part.update`, `part.move`, `part.resize`, `note.add`, `note.update`, and `note.batch_update` whenever track automation items have extension data. The session 21 receipt `artifacts/feature-acceptance-e8eb9b6496cb/summary.json` does not establish support for these operations.

The candidate consists only of those eight operations. Existing direct-pitch deletion, controller cross-project, extended-audio write and archive-bearing media property guards remain independent and unchanged. Deletion, duplication, split, join, time edits, transfer and import are excluded.

## Transaction and test

Before mutation, `BeginArchiveMutation` validates tracked native owners and complete point maps and snapshots the journal. Before commit, `ValidateArchiveTrackAutomationBeforeCommit` checks that each previous owner survives, that non-automation actions retain the same lane payload, and that all native ticks and values match. History restores journal snapshots and validates live owners again. These static checks do not establish operation-specific behavior or rollback on failure.

`tools/check_track_edits_22.py` uses separate private AI fixtures per operation, two owners, two lanes and distinct zero/nonzero event markers. It checks complete track and lane state, undo, redo, branch, clone, reopen, source preservation and a separate duplicate guard. The original host is expected to reject the candidate mutations; the corresponding failures are a red baseline, not support. Further evidence is needed for native failure rollback and mixed-extension guard interactions. Integrate no candidate until its actual native success and history behavior are verified.

## Old-host execution

`artifacts/feature-acceptance-dd354933659d/summary.json`: eight expected-success cases failed at the track automation identity guard, and transport cleanup passed. No owned foreground switch or remaining owned session was recorded. Thus no post-edit assertion ran. An earlier run `artifacts/feature-acceptance-ef256eebecdd/summary.json` failed during fixture setup because the notes lacked `lang_id`; the fixture was corrected and the earlier receipt remains evidence of that setup failure only. No Release build was run.

## Review boundary

Automatic review blocked a combined patch that would have relaxed the track
and controller note-edit guards because the prospective cases were still red and
native identity and rollback evidence were insufficient; the stated risk was
silent metadata loss. No guard change from that patch was applied. The eight
track cases remain standalone prospective tests, not release acceptance cases.
`preservation.extension_edit_guards_22` in
`artifacts/feature-acceptance-80b1c4779514/summary.json` confirms the eight
track operations and three controller note operations still reject before
mutation on the synthetic fixtures, preserving source and history. Any later
change requires stronger evidence and individual approval/review.
