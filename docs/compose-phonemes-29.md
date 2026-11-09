# Native phonemes for score composition — session 29

## Contract

`score_compose` resolves omitted phonemes for new or lyric-changed AI notes
through the installed G2PA manager in an owned native session. It retains the
existing source-note selection and project-extension protections. A selected
source note with unchanged lyric and language retains its source phoneme.
Explicit phonemes still use the existing file-authoring path; an explicit empty
phoneme is rejected. `score_replace_notes` has not adopted this conversion.

The target must be an installed available Dnn voice supporting the requested
language, and the template's language checks continue to apply. The temporary
project uses editor default lyric/phoneme pairs for the target language and
actual template and voice. Each input must be accepted by native `CanConvert`,
resolve to exactly one note with the complete requested lyric and a nonempty
valid phoneme, and leave all other notes and non-lyric fields unchanged. If the
manager supplies candidates, the result must match a single-syllable candidate.
When the candidate list is empty, the operation repeats the native conversion
from a second editor default with a different phoneme and requires the results
to agree. This reduces the observed stale-seed risk; it is not an independent
pronunciation oracle or a claim of perceptual accuracy.

The template's single read-only archive handle remains open while the temporary
candidate and final candidate are generated. The final candidate is published
with an exclusive same-volume hard link, then opened in the native engine and
compared with the conversion session. Existing output is not overwritten;
rejected conversions close their owned session and leave no target file in the
tested cases. A late cancelled request can leave a completed output file, while
its returned native session is closed. Hard-link availability, a process or
system crash, concurrent external deletion or modification, and recovery after
native close failure are not covered by the observation.

## Evidence and limits

`tools/check_compose_phonemes_29.py` ran once against a fresh private stdio
server. `artifacts/feature-acceptance-2dfe4fb88811/summary.json` records one
passing feature case and transport cleanup, with no owned foreground switches
or remaining sessions. The asa AI template produced and reopened `い/i`,
`cat/kh { t`, `ni/n i`, and one explicit `あ/a` note. The case also checked
that a pre-existing output stayed byte-identical and that tested `hello`, `ni3`
and `こんにちは` requests produced no destination. No audio was rendered or
independently assessed. The first attempt stopped before starting the server
because the sandbox denied creation of the test receipt; the authorized run
created the receipt and passed.

No other voice, template, selected source note, non-default expression,
extension-bearing project, cancellation, concurrent modification, injected
native error, or crash was exercised by this case. All existing extension
guards remain in force. Other native lyric operations and `note.add` retain
their separate documented limitations.
