# Native AI note initialization probe (session 27)

Historical observations from session 27; the 0.22.0 AI insertion contract and targeted evidence are in [native authoring](native-authoring-31.md).

## Scope

`tools/probe_native_note_27.py` uses a fresh stdio server and private native session for each synthetic asa AI fixture. The seed contains one Japanese `あ/a` note, and is checked for `directPitches`, `controllers`, and `automations` keys before editing. It does not alter production code or guards. The test observes the existing bridge `note.add` implementation, not the bare engine in isolation. Receipt: `artifacts/feature-acceptance-b3983340ab31/native_note27.json`; cleanup: `artifacts/feature-acceptance-b3983340ab31/transport.cleanup.json` (passed). The probe's pass means observation completed, not that every input succeeded.

## Results

| Input | Observed result |
| --- | --- |
| lyric and phoneme omitted | `あ/a`, language 0, velocity 64 |
| Japanese `い`, phoneme omitted | `い/i`, language 0, velocity 64 |
| Japanese `い`, explicit `i` | `い/i`, language 0, velocity 64 |
| empty lyric, phoneme omitted | insertion error `InvalidLyric`; one original note remains |
| `こんにちは`, phoneme omitted | returned success but produced only `こ/k o` |
| English `hello`, language 1, phoneme omitted | rejected before insertion: no same-language valid phoneme context |
| Chinese `你`, language 4, phoneme omitted | rejected before insertion: no same-language valid phoneme context |
| Japanese emoji, phoneme omitted | returned success, lyric remained emoji and phoneme remained seed `a` |

Each successful case saved, reopened and rendered. The 2.6–2.9 s windows were nonzero; these renders also contain the seed and no seed-only subtraction or listening was performed. The success and validity flag do not demonstrate the intended syllable or pronunciation. Success cases changed history from no undo to undo available, with no staged transaction. The three rejected cases retained one note and unchanged history, unstaged; this does not prove rollback for every possible failure.

The observed defaults arise from the bridge plus native calls: `GetDefaultNoteEvent` supplies velocity, the AI part supplies language, `DefaultLyric` supplies the omitted lyric, a valid same-language existing note supplies initial phonemes, and `SetLyrics` then operates on the inserted note. They are not established universal engine defaults. Saved native-added notes have singing skill duration 160 and vibrato duration 0 in this fixture, distinct from the seed's 80 and 160 respectively.

## Design conclusion and limits

A single unconditional conversion path is not established: truncation and stale-phoneme success are observable, and first-note/same-language bootstrap is unresolved. Do not treat `SetLyrics` success, converted count or validity alone as semantic conversion proof. A candidate workflow needs explicit rejection or exact input-to-output checks, language-specific bootstrap, phrase distribution across intended note boundaries, transactional behavior and preservation review before production use. This run tests a phrase on one note, not a multi-note phrase distribution, English/Chinese with a same-language context, or an empty part. Session 26 `docs/ai-lyrics-conversion-26.md` separately observed `lyrics_apply`: Japanese `い` and English `hello` converted, whereas Chinese `你` and emoji retained old `a` despite success; it did not establish a universal converter. No listening, other voicebanks, extension-bearing inputs, or full-suite acceptance is claimed.
