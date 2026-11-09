# Controller extensions with note edits — session 22

The existing controller-event extension guard rejects note add, update and batch
update while any controller lane carries unknown fields. This is distinct from
the separately guarded cross-project transfer path. A synthetic dual-AI-track
fixture with distinct per-owner controller and note markers was added in
`tools/check_controller_notes_22.py`. The old host rejected the first intended
note update in `artifacts/feature-acceptance-72bcbfa55a05/summary.json`; cleanup
passed and the later history, clone and reopen assertions were not reached.

Automatic review blocked the combined proposed track/controller guard relaxation
because the candidate lacked native identity and failure-rollback evidence and
could silently lose metadata. No proposed controller guard or commit-validation
change was applied. The prospective case is standalone, not a release gate.
`preservation.extension_edit_guards_22` in
`artifacts/feature-acceptance-80b1c4779514/summary.json` confirms the three
controller note operations still reject before mutation on a synthetic fixture,
with source and history unchanged. Existing controller cross-project transfer,
extended audio, archive media and pitch deletion review boundaries are untouched.
Further work needs a sound native identity transaction, failure/rollback and
mixed-extension evidence, plus individual approval and review before a guard
change.
