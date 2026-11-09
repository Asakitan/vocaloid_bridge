# Native observation: JSON Patch copy and validity — session 27

An isolated private MCP session created a synthetic ordinary AI project with one note at tick 0, duration 480, lyric `あ`, phonemes `a`, language 0. Native `note.update` set `is_valid_phonemes=false`; native save generated one sidecar entry referencing that note. The seed and saved sequence had no `directPitches` and passed the existing note-replacement extension guard. The source was retained byte-for-byte.

The 0.18.0 `score_patch` copied `/tracks/0/parts/0/notes/0` to the array end, then changed the copy's `pos` to 960. The original note, its index and sidecar bytes remained unchanged. Native open returned two notes: original tick 0 `is_valid_phonemes=false`, copy tick 960 `is_valid_phonemes=true`. Native save retained only the original sidecar entry; reopening the saved file returned the same false/true values. Thus, in this observed path, the JSON Patch copy does not inherit the source note's invalid flag. This observation does not establish whether copy should inherit validity as a product contract or generalize to other notes/voices/operations.

Evidence: `tools/probe_patch_copy_validity_27.py`, `artifacts/feature-acceptance-f428a8882714/patch_copy_validity27.json`, and `artifacts/feature-acceptance-f428a8882714/summary.json`. The focused case and transport cleanup passed; this was not the full suite. No production code or extension guard changed; no compilation, interactive editor or real project was used.

Session 27 later introduced explicit file-level copy provenance; the 0.19.0 focused acceptance in `artifacts/feature-acceptance-840e52ca3977/summary.json` verifies that the tested copied note retains the invalid flag. See [patch provenance](patch-sidecar-27.md).
