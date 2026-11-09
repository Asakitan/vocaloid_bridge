# Native AI insertion and lyric transactions — session 31

## AI note.add

An AI note without explicit phonemes now uses its assigned installed Dnn voice,
native language manager and two installed-editor default seed pairs. It no
longer needs a previous note. Native CanConvert must accept the lyric; the
result must retain the complete requested lyric, exactly one syllable, valid
phonemes, all non-lyric target fields and all surrounding note identities and
summaries. Candidates corroborate the result when supplied; an empty list
requires agreement after conversion from different phoneme seeds. This is a
structural acceptance rule, not independent pronunciation assessment.

The existing ScoreMutate transaction performs the single final commit and
rollback; no intermediate history entry is introduced. Explicit phonemes and
the existing classic context path are unchanged. Existing extension guards are
not relaxed.

`artifacts/feature-acceptance-37a539fe748f/summary.json` records one passing
case and cleanup: asa Japanese/English/Chinese first notes, default lyric and
language, expression/velocity, phrase rejection with surrounding-note rollback,
invalid-input rejection, one-step undo/redo and native save/reopen.

## Lyric and phoneme transactions

The four apply/reset operations retain the unstaged preflight and now use
ScoreMutate instead of the earlier Commit(false) path. A changed successful
operation is undoable. A staged pre-commit failure rolls back only the current
operation, preserving earlier history and dirty state in the tested case.
lyrics_apply checks native CanConvert before applying input that was observed
to retain stale phonemes. Reset managers still act in the one enclosing
transaction.

`artifacts/feature-acceptance-ee5cb7d6ce6c/summary.json` records one passing
MCP case and cleanup. It checks apply/reset undo/redo and invalid input. The
case also starts an isolated native helper, injects a validation failure after
observing the changed lyric and staged state, and verifies restoration of the
full note summaries, prior undo/redo availability and dirty state. No production
failure-injection switch is exposed.

Native commit failure, native rollback failure, errors after commit/readback,
arbitrary phrase coverage, other voices and auditory quality were not proven
by these cases. File-authoring and native library mutation extension guards
remain separate.
