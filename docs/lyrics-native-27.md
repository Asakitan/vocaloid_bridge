# Native lyric conversion observations (session 27)

## Scope and method

Run `.venv/Scripts/python.exe tools/probe_lyrics_native_27.py`. The isolated stdio harness creates a separate ordinary synthetic two-note AI project per input; both notes start as Japanese `あ` / `a`, velocity 64, with no direct-pitch entries. The installed voice was asa (`BLKEA452HDSKXLD7`), which reports AI language IDs 0, 1 and 4. No user projects, foreground editor, voice installation, production code or extension guards were touched. The receipt is `artifacts/feature-acceptance-081dbbadce90/lyrics_native27.json`; `transport.cleanup` passed. The harness passed as an observation workflow, not a pronunciation-quality test.

The `CanConvert` queries vary the AI flag and extension-dictionary flag; candidates use the actual AI note. Apply uses the stated language, AI note, extension dictionary false and `protect=false`. The table lists immediate actual note values, with `lyric/phonemes`; all values and note lists matched after save and reopen. All notes reported native phoneme validity true and each project retained two notes.

| Language/input | CanConvert, extension false | Candidates, extension false | Apply affected length; resulting notes |
|---|---|---|---|
| JPN `い` | true | empty | 1; `い/i`, `あ/a` |
| JPN `😀` | false | empty | 1; `😀/a`, `あ/a` |
| ENG `hello` | true | `hel-/h e`, `lo/l @U`; another first syllable `h V` | 2; `hel-/h e`, `lo/l @U` |
| ENG `😀` | false | empty | 1; `😀/u:`, `あ/a` |
| CHS `你好` | false | empty | 2; `你/a`, `好/a` |
| CHS `ni hao` | true | `ni/n i`, `hao/x AU` | 2; `ni/n i`, `hao/x AU` |
| CHS `ni3 hao3` | false | empty | 2; `ni3/a`, `hao3/a` |
| CHS `你` | false | empty | 1; `你/a`, `あ/a` |

The AI and non-AI query flags returned the same boolean in this small matrix. With extension dictionary true, `hello` still returned true, but offered a different candidate (`hel-/h e l`, `lo/l0 @U`); `い` and `ni hao` changed from true to false, and all other tested inputs remained false. Extension-true application was not tested. The successful pinyin case shows that the installed CHS manager and language parameter work for at least this input; these samples distinguish accepted unmarked pinyin from the tested Han characters and numbered-tone spelling, but do not determine the internal dictionary, Unicode handling, or all supported Chinese forms. Japanese Unicode `い` succeeds, so this is not evidence of a general Unicode transport failure.

For every apply, dirty changed false to true; staged, can-undo and can-redo were false before and after. A false conversion query did not imply an apply error or correct phonemes: the Japanese and Chinese examples retained `a`, whereas the English emoji became `u:`. Native validity, a successful apply and an affected-length count are therefore insufficient conversion evidence. `hello` and `ni hao` demonstrate two-note distribution in this fixture.

An invalid string `protect` was rejected before the native mutation, with note list, dirty, staged and history unchanged relative to the preceding apply. This is validation failure, not evidence of rollback after a native mutation or commit failure. Code inspection shows `SetLyrics` is called without `CanConvert`; dirty is set and children invalidated before native invocation, followed by commit on success. Native failure and post-mutation rollback remain untested. Render, listening, other voices, arbitrary inputs and extension-bearing projects remain outside this observation.
