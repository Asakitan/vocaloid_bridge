# G2PA API inspection — session 28

## Scope and method

`tools/probe_g2pa_api_28.py` reads the previously decompiled installed-editor managed sources under `.runtime/decompiled-audio`; it does not load the editor or invoke native code. Run it with `python tools/probe_g2pa_api_28.py`. The focused run returned five default lists containing 12, 9, 20, 15 and 13 entries. This is static evidence of the inspected managed wrapper, not a guarantee of installed voice compatibility. No fresh dynamic experiment was performed in this slice; existing private AI observations below are explicitly identified as session 27 evidence.

## Managed surface

The observed factory signature is `G2PAManager? CreateManager(G2PAManagerLangID langID, string g2paDirPath)`. The enum has JPN, ENG, KOR, ESP, CHS. The manager exposes `string DefaultLyric()`, `bool CanConvert(string lyrics, bool useExtensionDictionary, bool isAi)`, `bool SetLyrics(nint pNote, string lyrics, bool useExtensionDictionary, bool isAi, out int length)`, and `List<List<SyllableArgs>> CandidatePhonemes(nint pNote, string lyrics, bool useExtensionDictionary, bool isAi)`, plus note/part mutation methods. Signatures are extracted from decompiled managed source rather than inferred from names. The wrapper rejects a null note in `SetLyrics`; `CanConvert` takes no note but returns only a Boolean. CandidatePhonemes still requires a note argument; its behavior with a null pointer is not established here. These are not evidence of a context-free phoneme conversion API.

The editor-level `DefaultLyricManager` exposes `GetInitialDefaultLyric(VSMLanguageID)`, `GetDefaultPhoneme(VSMLanguageID, string)`, `GetDefaultLyricsByIndex(VSMLanguageID, int, out string?, out string?)`, and user-setting-dependent variants. Its static lists begin Japanese `あ`/`a`, English `Ooh`/`u:`, Korean `아`/`a`, Spanish `a`/`a`, Chinese `a`/`a`. `GetDefaultPhoneme` is an exact lookup in those lists and returns empty when no match exists, not a general converter. Editor defaults, manager defaults, current user settings, and voice-specific support are distinct concepts; their equivalence has not been tested.

## First-note bootstrap and voice limitations

The inspected bridge requires same-language valid existing-note phonemes before its omitted-phoneme `note.add`; this is bridge policy, not proof no lower-level strategy exists. An editor default pair is a possible seed to investigate, but neither a temporary note constructed from it nor removal of that seed has been verified in this session. The default tables do not establish that a given installed AI voice supports a language or that its phonemes are accepted. The G2PA enum identifies manager languages, not per-voice AI support. A per-voice supported-language interface and comparative tests across installed AI voices were not established here.

Session 27 private asa fixture evidence (`docs/native-note-27.md`, `docs/lyrics-native-27.md`) observed successful Japanese conversion but also phrase truncation and stale phonemes on emoji; Chinese Han input could retain old phonemes and `CanConvert` could be false. These results are observations, not fresh tests or proof of voice-independent behavior. Reliable first-note language bootstrap and semantic correctness, cross-voice differences, rollback and listening remain unverified. Do not relax production guards on this basis.
