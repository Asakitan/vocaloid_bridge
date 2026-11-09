# Default-pair bootstrap probe — session 28

## Scope

`tools/probe_default_bootstrap_28.py` ran one private native stdio test using three fresh synthetic projects, each with an empty AI part and the installed asa Dnn voice explicitly assigned. No interactive editor, classic engine, extension guard changes, synthesis, or listening was involved. Receipt: `artifacts/feature-acceptance-cba7992351b1/default_bootstrap28.json`; cleanup: `artifacts/feature-acceptance-cba7992351b1/transport.cleanup.json`. The receipt retains full call results, before/after notes, saved sequence notes and reopened notes. The focused case and transport cleanup passed; this is not a full-suite result.

The native `project_library` `languages` defaults matched the first pairs in the previously decompiled installed editor `DefaultLyricManager` for each tested language. The static pair supplies phonemes; native `DefaultLyric` supplies only the lyric. The installed `voicebanks` response reported asa supports language IDs 0, 1 and 4; `voice.set` returned the assigned component ID, but its immediate part metadata had an empty `ai_lang_ids` array. This is not a comparison across voices.

## Observation

| Language | Explicit seed lyric / phoneme | Applied lyric | Native result phoneme | Saved and reopened |
| --- | --- | --- | --- | --- |
| Japanese (0) | `あ` / `a` | `い` | `i` | retained |
| English (1) | `Ooh` / `u:` | `cat` | `kh { t` | retained |
| Chinese (4) | `a` / `a` | `ni` | `n i` | retained |

In all three cases, the empty-part note insertion returned the explicit language and valid-phoneme flag; `CanConvert` returned true for the target; `lyrics_apply` reported affected length 1, the target lyric, shown phonemes and valid flag. A native save followed by close and reopen retained each target lyric, phoneme and language. The probe records observations rather than asserting an expected pronunciation; its pass indicates the observation completed, not general conversion correctness.

## Limits

This demonstrates a narrow explicit-default-pair seed followed by conversion of that same first note for these three single inputs and asa. It does not test direct insertion with omitted phonemes, multi-syllable distribution, failed-conversion rollback, semantic accuracy by listening, other voicebanks, extensions, or robustness across user settings. Previous session 27 observations include stale output and phrase truncation, so success flags alone remain insufficient for arbitrary input. Production guard behavior was not changed.
