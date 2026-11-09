# Direct-pitch deletion transaction — session 21

The unvalidated candidate helper is retained at `.runtime/note-delete-candidate-21.cs`,
outside the compiled host and not an enabled operation. It binds explicit native targets before deletion, computes descendants
from the pre-edit parent graph, then checks the complete staged native identity
and parent graph before removing those entries from the live map. It validates
all surviving tracked pitch point sets. The normal archive journal is expected
to own rollback and history snapshots; this assumption needs native testing.

The four deletion call sites and the operation guard require separate integration.
Deletion, rollback, undo/redo, history branching, recreated entities, source byte
preservation and save/reopen have not yet been verified for this candidate. At
that investigation checkpoint no old-host red baseline had been run. Existing cross-project
controller, audio and archive media-update guards remain untouched.

## Red baseline and review boundary

The old host rejected all four new cases at the direct-pitch operation guard in
`artifacts/feature-acceptance-830a85e95c28/summary.json`; cleanup passed, no
owned foreground switch was observed, and no owned sessions remained. The
post-deletion assertions did not execute. The tests cover marked survivors,
undo/redo, a history branch, source bytes and save/reopen; they do not yet
cover recreated objects or native rollback after a staged failure.

Auto-review rejected a standalone guard relaxation because the score call sites
had not yet integrated the target-bound hooks and could lose metadata. The guard
remains in place. Hook integration and any later guard change require review and
appropriate individual approval. No current test establishes that the candidate
helper is correct or suitable for production.
