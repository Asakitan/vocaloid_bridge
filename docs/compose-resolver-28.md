# Native single-note resolver observations (session 28)

## Method

`tools/probe_compose_resolver_28.py` creates a separate three-note synthetic project per input using the default asa AI template; all seed notes are Japanese `あ/a`. In a private native session it queries `lyrics_can_convert`, `lyrics_candidates` and then invokes `lyrics_apply` at the middle note, with extension dictionary disabled. It compares the entire neighboring note objects before and after. The acceptance rule requires CanConvert, affected_length exactly one, nonempty valid phonemes, and, when any candidates exist, an exact lyric and phoneme match to a one-element candidate; when candidates are empty, it instead requires the actual lyric to equal the request. The rule does not independently prove pronunciation. Observation receipt: `artifacts/feature-acceptance-a8a508f71da6/compose_resolver28.json`; cleanup receipt reports zero sessions. The earlier `60509dda655d` receipt records the same raw observation before rule evaluation was added.

| Language / request | Can | Candidate(s) | Actual middle lyric / phoneme / language / valid | affected | Rule | Changed neighbor |
| --- | --- | --- | --- | --- | --- | --- |
| Japanese `い` | true | none | `い` / `i` / 0 / true | 1 | accept | no |
| Japanese `か` | true | none | `か` / `k a` / 0 / true | 1 | accept | no |
| Japanese `きゃ` | true | none | `きゃ` / `k' a` / 0 / true | 1 | accept | no |
| Japanese `こんにちは` | true | none | `こ` / `k o` / 0 / true | 2 | reject | next `ん/N\` |
| English `cat` | true | one `cat/kh { t` | `cat` / `kh { t` / 1 / true | 1 | accept | no |
| English `CAT` | true | one `CAT/kh { t` | `CAT` / `kh { t` / 1 / true | 1 | accept | no |
| English `hello` | true | two two-syllable alternatives | `hel-` / `h e` / 1 / true | 2 | reject | next `lo/l @U` |
| Chinese `ni` | true | one `ni/n i` | `ni` / `n i` / 4 / true | 1 | accept | no |
| Chinese `hao` | true | one `hao/x AU` | `hao` / `x AU` / 4 / true | 1 | accept | no |
| Chinese `你好` | false | none | `你` / `a` / 4 / true | 2 | reject | next `好/a` |
| Chinese `ni3` | false | none | `ni3` / `a` / 4 / true | 1 | reject | no |

The `你好` and `ni3` cases retained the seed phoneme despite valid=true; the CanConvert condition rejected them. The rule rejects multi-note `hello` and `こんにちは` for this single-note contract, not as evidence that phrase conversion is incorrect; their rejection would be a false rejection only for a contract that intends multi-note phrases. No accepted case was independently judged mispronounced, so no false acceptance is established; the empty-candidate Japanese branch in particular could still accept a stale or incorrect phoneme. No listening or ground-truth pronunciation oracle was used. The test provides no basis for a false-rejection rate over valid single-note inputs.

## Boundaries

The seed provides existing notes; this is not an empty-part bootstrap, and it does not test insertion of an omitted-phoneme first note. The tested target was initially a Japanese note even for English and Chinese: this is a `lyrics_apply` observation, not proof of first-note or same-language `note.add` behavior. Only the default asa voice and default template were used; explicit template, source note selectors, other voices, extension dictionaries and extension-bearing projects remain untested. No output was saved or reopened in this resolver run; see `docs/compose-native-28.md` for separate save/reopen observations. No production integration or guard changes were made. The observed neighbor mutation on rejected multi-note inputs requires staging in a disposable session or demonstrated rollback before any future publishing workflow.
