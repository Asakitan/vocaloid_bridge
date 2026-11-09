# AI file-note identity contract — session 26

## Implemented policy

For `score_replace_notes` and `score_compose`, each AI input note selects either
`source: {index, expected}` or no source (new). The index identifies a note in
the selected part before sorting. `expected` is the complete JSON note inspected
from that source archive. The implementation rejects invalid, repeated and stale
selectors using strict canonical JSON; JSON booleans and numbers are distinct.
Matching and output copying occur while the same source archive handle is held.

Selected identity follows explicit moves, edits and input reordering. It is not
inferred from tick or musical content; a new note at an old tick is still new.
Unselected old notes are removed. This is file-level provenance, not proof of
native object identity or native history. Other populated vocal track types retain
the earlier first-prototype behavior and do not accept AI source selectors.

Selected notes retain their own defaults and unknown fields; `raw` is merged
recursively before structured fields are applied. For new AI notes, the observed
editor baseline supplies expressions and velocity 64, while omitted language
uses the first source note's language if present, otherwise baseline language 0.
Selected notes with the same lyric and language retain their original phoneme if
omitted. `score_replace_notes` still writes an empty phoneme for other omissions;
in a tested AI voice, that empty phoneme caused the native note-count integrity
check to fail on open. Since 0.20.0, `score_compose` resolves those omissions in
the native G2PA session before publishing; see [the conversion contract](compose-phonemes-29.md).

The validity sidecar is checked against the original sequence before replacement.
Every sidecar-referenced note in the edited part must retain its selected source
index at the same output index, in addition to the original field checks; no
sidecar migration is claimed. This prevents assigning validity to a new note
with identical visible fields. File note replacement checks the whole source
project for track volume/pan-event, controller-event and direct-pitch item
extensions and stops on those guarded types. The native guards were not modified.

## Evidence and limits

The earlier independent `tools/probe_note_identity_26.py` demonstrates the
selector concept in synthetic JSON. It used baseline language 0 for new notes;
production retains an existing part's first-note language default as described
above. Its sidecar check alone was insufficient to prove identity.

Old implementation MCP red baseline:
`artifacts/feature-acceptance-79599f48f49f/summary.json` recorded A/A/A and
velocity 70/70/70 where B/new/A and 90/64/70 were requested. An earlier harness
run `artifacts/feature-acceptance-4fbd9aaf25c3/summary.json` stopped because
the test expected one text block for a list; the test then read each note by
individual pointer and was rerun. Both failures are retained.

The new MCP case `artifacts/feature-acceptance-57ffec017ade/summary.json` passed
with cleanup. It exercises exact source snapshots, moved/reordered and new notes,
nested fields, distinct default velocities, invalid/repeated/stale selectors,
same-field sidecar identity conflict, source/resource preservation, and native
save/reopen for the tested ordinary AI project. Three extension-guard predicates
were also checked with in-memory examples without editing extension projects.

The separate `artifacts/feature-acceptance-4768f923d99b/summary.json` passed four
focused lifecycle, ordinary interchange, invalid-phoneme media and existing-guard
cases plus cleanup. Neither batch proves arbitrary voices, all sidecar migrations,
or full editor-feature coverage.
