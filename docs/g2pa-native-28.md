# Native G2PA single-syllable investigation (session 28)

## Scope and evidence

Run `.venv/Scripts/python.exe tools/probe_g2pa_native_28.py`. Receipt: `artifacts/feature-acceptance-2b132719eb9c/g2pa_native28.json`; case passed as an observation and its two-note synthetic projects were closed. The private stdio harness used asa AI (`BLKEA452HDSKXLD7`), no direct-pitch items, and no controller or track-automation extension. It tested language IDs 0, 1, 4, separately querying both dictionary flags and AI/non-AI flags. Application used the AI note, extension false, and protect false. All rows below preserved their lyric, phoneme and language readbacks across save/reopen. No listening or other voicebank was tested.

| Input | CanConvert (AI, extension false) | Candidates | affectedLength | Actual first / second lyric and phonemes |
|---|---|---|---:|---|
| JPN `か` | true | empty | 1 | `か / k a`; `あ / a` |
| JPN `カ` | true | empty | 1 | `カ / k a`; `あ / a` |
| JPN `こんにちは` | true | empty | 2 | `こ / k o`; `ん / N\` |
| ENG `cat` / `CAT` | true | one matching single-syllable candidate each | 1 | original case / `kh { t`; `あ / a` |
| ENG `hello` | true | two two-syllable candidates | 2 | `hel- / h e`; `lo / l @U` |
| CHS `ni` / `NI` | true | one matching single-syllable candidate each | 1 | original case / `n i`; `あ / a` |
| CHS `ni3` / `你` | false | empty | 1 | original input / `a`; `あ / a` |
| CHS `ni hao` | true | two-syllable candidate | 2 | `ni / n i`; `hao / x AU` |
| ENG `😀` | false | empty | 1 | `😀 / u:`; `あ / a` |

The `こんにちは` test is especially important: `CanConvert=true` and affectedLength=2 conceal truncation to available notes. Candidate availability differs by language: a valid Japanese kana produced an empty list. `CanConvert`, validity, nonempty phonemes, SetLyrics success and affectedLength are individually insufficient evidence of faithful conversion. Reusing a previous phoneme can also look valid. Candidate matching is useful corroboration where candidates exist, not a universal requirement. The invalid `protect` type was rejected before mutation; this is not evidence of native failure rollback.

## Proposed bounded contract

1. Define automatic conversion as a **single native syllable**, not arbitrary text. Fix actual AI voice, language, dictionary flag, and target context before querying. Reject `CanConvert=false` rather than applying it. Do not silently transliterate Han characters or strip tone numbers; explicitly report unsupported input or require caller-supplied phonemes. No blanket lowercasing, trimming, Unicode normalization, or character-count test is justified by these observations.
2. Where candidates are nonempty, require at least one complete candidate of exactly one syllable. Apply on an isolated copy and require affectedLength=1, one target note retained, nonempty phonemes and valid flag, requested language, and unchanged adjacent note identities and values. Compare resulting lyric/phonemes to one complete single-syllable candidate using native-returned strings, not raw input equality. This permits native spelling normalization when reflected in the candidate and avoids treating unchanged phonemes alone as failure. Divergence is an explicit unverified conversion, not proof that pronunciation is wrong.
3. Empty candidate arrays are ambiguous, especially Japanese. An isolated SetLyrics result with affectedLength=1 does not establish full input coverage: a one-note project can truncate a phrase. Until an independently validated native segmentation/coverage signal exists, return an explicit unsupported/unverified result rather than infer a single syllable from length or raw string equality. A small independently tested, versioned language-specific allowlist could be introduced as a separately scoped contract, not inferred from this sample.
4. Inspect the entire affected range and surrounding note state in a private candidate; reject changes outside the requested note. Store and return the native resulting lyric and phonemes, keeping the original request separately if needed. Check that the selected voice supports the language. This establishes structural acceptance, not pronunciation quality.
5. Failure atomicity is still an implementation requirement, not a demonstrated property: `LibraryApplyLyrics` sets dirty and invalidates children before `SetLyrics`, then calls `LibraryCommit`, with no rollback in that path. A candidate copy that is closed/discarded on every rejection protects the original during conversion; promote only with an independently proven transaction that preserves all project state and handles commit/open/save failure. Preflight by itself is not a commit protocol. Do not claim rollback until mutation, commit, promotion and cleanup failure paths have been deliberately tested against full original state. File-level creation must not emit an empty phoneme to the native loader.

## Limits and next checks

The two-note fixtures start as Japanese seed notes even when applying another language; same-language context, a true single-note fixture, longer phrases and normalization beyond case remain open. The candidate check is an intentionally conservative sufficient condition for the tested ENG/CHS samples, not a documented guarantee for every native engine version. Test context sensitivity, multiple candidate selection, legitimate normalized lyric output, adjacent-note invariants and injected native/commit failures before production integration. The probe does not exercise a native post-mutation failure or establish listening quality.
