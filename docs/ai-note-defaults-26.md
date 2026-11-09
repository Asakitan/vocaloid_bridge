# AI note defaults probe (session 26)

## Scope and method

Run `.venv/Scripts/python.exe tools/probe_ai_note_defaults_26.py`. The probe starts its own MCP stdio server and private native desktop through the acceptance harness. It creates a synthetic populated AI part, verifies that the sequence has no `directPitches`, appends a copy of `_EDITOR_AI_NOTE` through a separate VPR, opens it natively, saves it, closes and reopens it, and renders the part. It never edits a user project or changes production code. Native sessions are closed, including on error; generated VPRs, WAVs and the receipt remain under ignored `output` and `artifacts` for inspection. The harness reports cleanup separately.

## Observations

Receipt: `artifacts/feature-acceptance-2d0a18053e43/ai_defaults26.json`; cleanup: `artifacts/feature-acceptance-2d0a18053e43/transport.cleanup.json`. This one probe failed overall because two cases failed; transport cleanup passed.

- Explicit Japanese `lyric=あ`, `phoneme=a`, `langID=0`, `velocity=64` on the new note: native open, save, reopen and part render completed. The saved note retained these values and the observed expression, singing-skill and vibrato structure. WAV: 44100 Hz, mono, PCM 16-bit, 374850 frames, 8.5 s, peak 0.1086121, RMS 0.0122912. The render includes the original note too; nonzero audio does not establish that the newly appended note sang correctly or that its phoneme is perceptually correct.
- Three keys absent from the serialized new note: native opening failed with `InvalidDataException: project_preservation: note count changed while loading.` There is no save/reopen or WAV evidence for this case.
- API-style omission simulated as `phoneme=""`, `langID=0`, `velocity=64`: native opening failed with the same preservation error. This does not isolate which field caused it. No save/reopen or WAV evidence exists for this case.

The explicit case is a narrow observation for one installed AI voice, Japanese phoneme and populated part. The two omission cases alter multiple fields together; they do not determine independent defaults. The note count error is surfaced by the bridge preservation check and does not alone establish the underlying native cause. The test does not validate arbitrary phonemes, language IDs, other voices, audio perceptual quality, track mixdown, note identity, sidecar validity across edits, or extension-bearing projects. These observations alone do not establish note identity or justify removing existing guards.

## Single-field follow-up and conversion (session 26)

The probe was subsequently extended; the preceding observations refer to its earlier run. Current receipt: `artifacts/feature-acceptance-f4436a433348/ai_defaults26.json`, cleanup `artifacts/feature-acceptance-f4436a433348/transport.cleanup.json`. Synthetic AI voice component `BLKEA452HDSKXLD7`, Japanese `あ`, 120 BPM. The original note ends at beat 1; the appended note begins at beat 4. The rendered waveform has an observed approximately 0.5-second lead-in.

- Explicit `phoneme=a`, `langID=0`, `velocity=64`: open, save, reopen and render completed; the 2.6–2.9 second WAV window, corresponding to the separated second note in this render, has peak 0.1086121 and RMS 0.0374149. The 44100 Hz mono PCM16 WAV is `output/feature-f4436a433348-004-ai-defaults-explicit.wav`. This is objective nonzero window evidence, not listening or phonetic-quality validation.
- Only `langID` absent: open/save/reopen/render completed, and native save wrote `langID=0`; the same window has peak 0.1086121 and RMS 0.0374149. This is one observed loader result, not a universal default.
- Only empty `phoneme`: native open raised `InvalidDataException: project_preservation: note count changed while loading.`
- Only absent `velocity`: native open raised the same error. Neither failure identifies the internal cause or yields a WAV.
- In the synthetic seed session, `lyrics_can_convert` for Japanese `あ`, `is_ai=true` returned `can_convert=true`, while `lyrics_candidates` for that note and language returned an empty candidate list. Therefore this call did not produce a phoneme for this input; convertibility alone is not evidence of an actual candidate.

The separated waveform interval supports a nonzero later event but has no seed-only subtraction; effects or tail contributions have not been independently excluded. No track mixdown or listening was performed. Overall case status remains failed due to the two rejected variants; cleanup passed.
