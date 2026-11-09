# Native compose conversion investigation (session 28)

## Scope and evidence

`tools/probe_compose_native_28.py` observes the existing bridge `note.add` path, not an implementation of `score_compose` conversion. It creates independent synthetic projects from the existing ordinary asa AI template, uses a fresh private session per case, and tests empty and same-language note contexts. It makes no production or guard changes. The first run `artifacts/feature-acceptance-7af440ed5449/compose_native28.json` failed because the probe assumed an empty saved part contains a `notes` key; the native empty-part rejection was nevertheless recorded and cleanup passed. After fixing that probe assumption, `artifacts/feature-acceptance-5e7049b88492/compose_native28.json` completed all observations and `transport.cleanup.json` reported zero sessions. A passing observation case does not assert pronunciation correctness.

| Case | Observation |
| --- | --- |
| Empty Japanese part; add `い` without phonemes | Bridge rejected first note for missing explicit context; empty notes, dirty flag and history remained unchanged; native save and reopen retained the empty part. |
| Japanese `あ/a` context; add `い` | Added `い/i`; saved and reopened with two notes. |
| English `hello/h @ l oU` context; add `hello` | Added `hel-/h e` on one note, rather than the full requested word; saved and reopened. |
| Chinese pinyin `ni/n i` context; add `hao` | Added `hao/x AU`; saved and reopened. No listening or independent pronunciation evaluation was performed. |
| Japanese `あ/a` context; add `こんにちは` | Success returned only `こ/k o`; saved and reopened. |
| Japanese context; add empty lyric | Native returned `InvalidLyric`; notes, dirty flag and history remained unchanged; saved and reopened with original note. |

The test records source notes after the native save separately from the saved output, showing the source note lists remained unchanged in these cases; this is not a byte-for-byte archive independence test. Voice inspection reported asa with languages 0, 1, and 4. The English and Chinese context phonemes are explicit test inputs, not proven pronunciation references. The selected source template and voice are the default only; explicit source-note selectors, alternate template paths, explicit `voice_comp_id`, and other AI voices were not tested. No extension-bearing project, multi-note phrase assignment, rendering, listening, arbitrary error rollback, or concurrent output collision was tested.

## Design boundary

A single reliable automatic omitted-phoneme conversion path is not established. Empty parts need a proven native bootstrap; same-language context permits observed conversion but success can truncate lyrics, and the converted phoneme cannot be trusted purely from success or validity. A possible future experiment would stage the requested score in a disposable private native session using the actual target AI voice and verified same-language context, compare note count, requested lyrics and language against output, save/reopen and publish a separate output only after all checks succeed, and close the session on every exit. Exact lyric comparison catches the observed truncations but does not establish phonetic correctness or solve contextual phrase distribution. Bootstrap, preserved source-note expression/identity, voice selection, output atomicity and comprehensive failure semantics need independent proof before production integration. Existing source selectors, extension guards and AI-only policy remain unchanged.
