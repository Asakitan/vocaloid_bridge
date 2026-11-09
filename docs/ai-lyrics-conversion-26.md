# Native AI lyric conversion observations (session 26)

## Method and scope

Run `.venv/Scripts/python.exe tools/probe_ai_lyrics_conversion_26.py`. The independent stdio harness creates a separate ordinary synthetic AI project for each input, checks that the project has no `directPitches`, and starts with one note `あ` / `a` with native validity true. It calls `lyrics_can_convert`, `lyrics_candidates`, and `lyrics_apply`, independently reads the note, saves, closes, reopens, and reads again. The cases are observations, not claims that all requested conversions succeed. Owned sessions are closed and the harness ends its child server; files and receipts remain in ignored output/artifacts. No production code, guards, user projects or foreground editor are touched.

Receipt: `artifacts/feature-acceptance-1ca9890042f3/ai_lyrics26.json`; `transport.cleanup` passed. The case passed as an observation workflow, not as a conversion-accuracy assertion.

## Installed voice and results

The selected installed AI Dnn voice was `asa`, component `BLKEA452HDSKXLD7`; native voice readback and seed list language IDs 0, 1, 4. The installed catalog in the receipt listed 21 Dnn voices available in sequence, each listing those three IDs; this is catalog support, not independent conversion or sound-quality testing of each voice.

| Language and input | can_convert | candidates | lyrics_apply and saved/reopened result |
|---|---|---|---|
| Japanese `い` (0) | true | empty | `い`, phonemes `i`, language 0, native validity true |
| English `hello` (1) | true | two two-syllable alternatives | one available note became `hel-`, phonemes `h e`, language 1, native validity true; the second syllable did not fit into the one-note fixture |
| Chinese `你` (4) | false | empty | call completed but changed lyric to `你`, language 4, and retained original phonemes `a`, validity true |
| Japanese `😀` (0) | false | empty | call completed but changed lyric to `😀` and retained original phonemes `a`, validity true |

Every row's resulting lyric, phonemes, language and native validity were read again after save/reopen; results matched the immediate readback. The latter two rows demonstrate that an unconvertible input did **not** produce an error or roll back: an old phoneme can remain valid according to the native validity flag even when it was not generated for the new lyric. Japanese candidates being empty did not prevent `lyrics_apply` from generating `i`; English multisyllable input requires sufficient notes to represent the complete candidate.

These are bounded observations for one voice and four inputs. They do not establish a generic grapheme-to-phoneme conversion contract, pronunciation correctness, audio quality, automatic safe handling of missing phonemes, or applicability to extension-bearing projects. No render or listening was performed. A genuine thrown conversion error was not observed, so error rollback remains unverified.
