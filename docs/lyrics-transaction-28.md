# Native lyric transaction boundary (session 28)

Historical session 28 evidence; 0.22.0 replaces the apply/reset commit path with the score transaction. See [current transaction evidence](native-authoring-31.md).

## Method

`.venv/Scripts/python.exe tools/probe_lyrics_transaction_28.py` used a separate ordinary synthetic one-note asa AI project per case, with no direct-pitch items or added controller/track automation. Receipt: `artifacts/feature-acceptance-0b599a61750f/lyrics_transaction28.json`; `transport.cleanup` in the same directory records cleanup. The case reports observations rather than asserting atomicity. No production code or extension guard was changed.

Each project began at 120 BPM, note `あ / a`, dirty=false, staged=false, undo=false, redo=false. The harness obtained `Tempos` and its first native item using `project_get` / `project_items`, then set its `Value` from 12000 to 12100 using `project_set`. This yielded 121 BPM, dirty=true and staged=true, with the note unchanged. It then applied Japanese lyrics, took state snapshots, invoked `history.rollback`, and took another snapshot.

## Observations

| Input to SetLyrics | Apply result | After apply | After rollback |
|---|---|---|---|
| `い` | success | 121 BPM, `い / i`, staged=false, dirty=true | rolled_back=false; values unchanged |
| empty string | success | 121 BPM, `あ / a`, staged=false, dirty=true | rolled_back=false; values unchanged |
| three spaces | native error `Native library operation failed: lyrics_apply.` | 121 BPM, `あ / a`, staged=true, dirty=true | rolled_back=true; 120 BPM, `あ / a`, staged=false, dirty=true |
| newline | success | 121 BPM, newline / `a`, staged=false, dirty=true | rolled_back=false; values unchanged |

Undo and redo remained false in every recorded snapshot. An empty operation also committed the unrelated pending tempo change despite no observed note change. The space case reaches the native `SetLyrics` call: the host validates it as a string and `LibraryRequire` reports the native false result; it is not an argument-type rejection. Its tested failure left the staged tempo in place, and the subsequent explicit rollback removed that unrelated pending change as well. Dirty remained true after rollback. The note looked unchanged in this case; this does not establish that every native failure has no partial mutation.

## Implication and limits

In 0.19.0, `LibraryApplyLyrics` called `LibraryCommit(session, operation)` on success against the sequence, not an isolated lyric transaction. An in-place conversion therefore commits unrelated staged edits, including a no-op lyric application in this fixture. Conversely, blanket rollback on failure can discard unrelated work. A conversion preflight must use a separate candidate and must not assume success, failure, or rollback isolates edits on a live session. A safe promotion mechanism and post-mutation/commit-failure behavior remain unproven. These observations concern the tested private project and host version only; no injected partial native mutation, commit failure, save/reopen or additional voicebank was tested.

## 0.19.1 change

The four lyric/phoneme apply/reset operations now call `ScoreRequireUnstaged` before
entering their existing native mutation path. The single focused real-MCP case
`artifacts/feature-acceptance-c9c5f40275ad/summary.json` checks that all four
leave a pre-existing staged tempo, history, note and dirty state unchanged, then
checks an ordinary lyric apply, save and reopen. The case and cleanup passed.
This is a preflight boundary, not proof of rollback after a fresh native failure,
and it does not change the existing `Commit(false)` undo behavior.
