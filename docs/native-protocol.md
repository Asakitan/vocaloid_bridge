# Native VSM JSON-Lines Protocol

## Startup and Ownership

The production command is `dotnet native/bin/Release/net8.0-windows/VocaloidBridge.Host.dll --serve INSTALL WORKSPACE`.
It must be launched through the bridge's private-Windows-desktop launcher. The host
reads its actual thread desktop and rejects `Default`, `Winlogon`, and `Disconnect`
before creating a native manager. `ping.desktop` is that observed desktop name.
The Python launcher copies the built DLL, dependency manifest and runtime config
to a private `.runtime/hosts/<id>` directory before starting it, preventing CLR
assembly locks on the build output. Each native manager also has an independent
cache namespace reported by `ping.cache_namespace`.
The native render cache capacity is zero, reported by `ping.render_cache_bytes`,
so changed MIDI effects are not served from a prior project's synthesis cache.
No WPF Application, App startup, main window, input injection, UI automation,
foreground activation, or frontend fallback is used. The host itself does not
create or switch Windows desktops.

Part-render responses include `lua_result` from the native controller. A
`NoError` result alone does not prove that an audible effect occurred; the
acceptance runner compares actual output samples separately.

Managed VOCALOID dependencies resolve from INSTALL. Native DLL resolution is
restricted to INSTALL and the system DLL search path before entering no-inline
engine code. Every RPC operation, lazy database initialization, and disposal runs
on the main STA thread. `stdout` is reserved for UTF-8 JSON responses; managed
diagnostic output is redirected to `stderr`. EOF disposes all owned sequences,
then the VSM manager, DSE manager, and database manager. Forced process termination
cannot promise managed cleanup; clients should close sessions and close stdin.

`--probe INSTALL OUTPUT` and the legacy `INSTALL OUTPUT` invocation retain the
native create/save/close/reopen probe, but also require a private desktop. They
must not be run directly on the interactive desktop.

## Framing

Send one JSON object per LF or CRLF-delimited line:

```json
{"id":1,"method":"ping","params":{}}
```

Each line produces and flushes exactly one response:

```json
{"id":1,"result":{"backend":"native-vsm","pid":1234,"version":"6.13.3.1","sessions":0,"desktop":"PRIVATE_DESKTOP"}}
{"id":2,"error":{"type":"KeyNotFoundException","message":"Unknown session_id."}}
```

Request IDs are signed 32-bit integers. An unparsable/missing ID is returned as
`null`. Duplicate object keys, nonobject requests/params, invalid types, and lines
over 1,048,576 UTF-16 characters are rejected. Maximum JSON depth is 64. Oversized
lines are drained before the next request. No notifications, batch requests, or
automatic retry are implemented. Startup failures go to stderr and exit nonzero.

## Lifecycle Methods

| Method | Parameters | Result |
| --- | --- | --- |
| `ping` | `{}` | backend, pid, version, sessions, actual desktop, cache_namespace, render_cache_bytes |
| `create` | title; bpm=120; sample_rate=44100 | session summary |
| `open` | absolute VPR path | session summary |
| `session` | session_id | session summary |
| `save` | session_id; output_name; overwrite=false | session_id, path, saved=true, native=true |
| `render_part` | session_id; track_index=0; part_index=0; output_name; overwrite=false | session_id, path, native=true, result, lua_result, render_observation, bytes, channels, sample_rate, bits_per_sample, frames |
| `close` | session_id; discard=false | session_id, closed=true |
| `voices` | `{}` | voices array from the real DatabaseManager |
| `api_catalog` | optional exact type/namespace; include_excluded=true; offset=0; limit=25 | installed type/member metadata and exclusion reasons |
| `import_project` | absolute path; code_page=65001; prefer_ai=true for MIDI/SMF/VSQ loader only | imported session summary |
| `export_midi` | session_id; output_name; encoding=Utf8; overwrite=false | native Standard MIDI File metadata |
| `clone_project` | session_id; optional title | independent native session summary |
| `revert_project` | session_id; discard=false | replacement session summary; old session closed |
| `merge_project` | session_id; path; offset_tick=0; include_tracks=true; include_tempo=false; replace_tempo=false; code_page=65001 | native merge result |
| `score_edit` | session_id; operation; options object | native structured score result |
| `audio_op` | session_id; operation; options object | native audio/effect result |
| `library_op` | optional session_id; operation; options object | native language/style/media result |
| `clipboard` | optional session_id; operation; options object | private native clipboard result |
| `midi_recording` | optional session_id for `devices`; operation; options object | native-session MIDI recording result |

The MCP `vocaloid_status` wrapper also returns `server_pid` for the Python process,
separate from the native host's `pid`. Verification attributes foreground windows
to these PIDs without activating or restoring any window.

The historical real-MCP acceptance receipt is
`artifacts/feature-acceptance-19d5e92a5f26/summary.json`: 44 feature cases plus
cleanup pass, covering all 35 advertised tools and the 81 structured operations.
This does not certify every raw native member, voice, effect, or file format.
The current 37-tool, 125-operation surface and subsequent focused receipts are
listed in `STATUS.md`. Open/load and save/clone now check native track and voice
identity. The known no-classic-bank condition reports `missing_classic_bank`
before loading a classic VPR; a lossy native snapshot reports
`project_integrity` before publication. These checks preserve existing files,
not add a missing voice model or promise classic synthesis.

Native standalone transport is exposed through `audio_op` with an explicit
enumerated device ID. Its device and callback lifetime is owned by one session;
prepared-session mutations are blocked until release, and close releases it.
Seek requests are asynchronous: `requested_seconds` is distinct from observed
`seconds`. Frozen track caches are likewise session-owned; saved/cloned VPRs
retain the pre-freeze authoring effect state. Raw writes to `IsFrozen` are
excluded in favor of the complete structured operation.

`midi_recording` allows session-free `devices`; other operations require the
session. Input callbacks enqueue MIDI notes only, while tempo conversion and
VSM writes occur on the owning STA. Synchronized recording uses an already
playing transport from that same session and releases it before score commit.
Recording blocks session mutations and session-scoped clipboard/library calls;
session close with pending recording requires explicit discard. Event-stream
and muted-transport tests passed; an independently owned virtual input has
also exercised the WinMM callback and endpoint cleanup. Physical MIDI-device
capture and real driver-error notifications remain unverified.

For VPR extensions, the host binds supported unknown properties to observed
native entity lifetimes and transaction history, then overlays only those
unknown properties onto native snapshots. MIDI/AI clipboard cut and paste and
project merge use tracked native transactions and identity mapping. A failed
cut retains its independent clipboard snapshot and reports its ID. Merge combines
nonconflicting source root/master extensions in the target history, preflighting
new nested parents and the merged output in independent snapshots; metadata-only merges without a native
history entry and opaque resource transfers are explicit errors. Plain projects
retain their existing operation paths. Extra archive members are
preserved on save without reviving deleted native-managed audio.

Summaries contain `session_id`, native `title`, native `track_count`, host `dirty`,
`root_ref`, and nullable `last_saved_path`. Creation uses the real VSM manager,
default 4/4 at bar zero, and native tempo at tick zero, with 32 tracks and 100 undo
slots. Native tick resolution is 480 per quarter note. BPM must be finite and in
20..300; it is rounded to native hundredths of BPM. Actual sequence tempo limits
are also checked. Accepted native sample rates are 44100, 48000, and 96000.
New sessions are dirty; opened sessions start clean. `close` rejects dirty sessions
unless `discard=true`. Unknown/already-closed IDs return an explicit error.

`open` initializes the normal database/DSE context and extracts a ZIP into `WORKSPACE/.runtime/SESSION`, including embedded audio,
and calls `OpenSequence(Project/sequence.json, Project, settings)`. There is no
fake JSON fallback. Extraction rejects absolute paths, traversal, reserved Windows
names, alternate streams, links/reparse points, special files, duplicate
case-insensitive archive paths, more than 16384 entries, or over 8 GiB expanded
data. Extracted files remain until the session is closed; originals are read-only.

`save` commits native edits when `IsStaged` is true and invokes native `Save` into a unique session-owned
staging directory. Only the resulting native `Project` directory is archived with
its directory prefix. The archive is moved into `WORKSPACE/output/output_name`;
the move is exclusive unless `overwrite=true`. Names must be relative `.vpr`
paths, with no traversal, invalid/reserved Windows names, trailing dots/spaces,
links/reparse points, or output-root escape. Overwrite is confined to output and
never replaces the original opened project. Dirty/last_saved_path changes happen
only after publication succeeds. Native staging/audio stay owned by the session
until close. Path checks do not establish isolation from a hostile concurrent
administrator replacing filesystem components; the workspace must be trusted.

`voices` lazily calls `DatabaseManagerIF.CreateDatabaseManager("VOCALOID6",
CommonProgramFiles/VOCALOID6/Explib, ref error)` and attaches that manager to VSM.
It returns only name, component_name, comp_id, kind, native_lang_id, lang_ids,
available_in_sequence, available_for_voice_changer, and synthesizable_version. It never reads license records,
activation data, serials, or keys. Native project loading and mutating MIDI/voice operations create
and attach the normal DSE manager. Its actual application license result selects
the same product variant as the installed editor; license secrets are not returned.
Initialization failures are real errors, are
retained without retries, and never become fake empty voice lists.

`render_part` is a validated native extension. It rejects non-MIDI tracks,
attaches the normal database/DSE services and a native Lua controller, and uses
`StartAsyncRendering` with a native renderer observer. Before starting it always
calls `Commit(false)` to refresh the native render queue, including for a clean
reopened sequence. A false Commit return is accepted only when there were no
staged edits and `LastError` remains `NoError`. Skipping this call leaves a clean
loaded part outside the render queue and was the cause of the previous timeout.
It waits for the requested
part's `HasValidRenderedWave`, retrieves that part's own `WaveFilePath`, and checks
the actual RIFF/WAVE file before publishing it under output. The wait is bounded
to 120 seconds, within the Python RPC deadline of 180 seconds. Observer delivery
is polled on the owning STA thread; no WPF message loop is needed. The Python MCP layer also reads audio samples and rejects an
empty or silent result. The same path and overwrite rules apply, with a required
`.wav` suffix. No sound or backend is substituted. Dirty state and last_saved_path
are unchanged. Native cancellation, initialization failure and timeout remain
explicit errors; timeout details include the native progress and finished state.

## Native Object Access

| Method | Parameters | Result |
| --- | --- | --- |
| `members` | session_id; ref defaults to root_ref | ref, type, properties, methods, constructors |
| `get` | session_id; optional ref; member | value |
| `set` | session_id; optional ref; member; value | updated=true, actual readable value |
| `call` | session_id; optional ref; member_id; args=[] | value |
| `construct` | session_id; type; optional member_id; args=[] | value containing $ref/type |
| `enumerate` | session_id; ref; offset=0; limit=100 | items, offset, has_more |

The object surface is derived from installed public `Yamaha.VOCALOID.VSM` members,
not a handwritten model. Properties and public fields are reported together with
name/type/can_read/can_write. Safe static defaults are readable but not writable.
Methods report exact overload IDs using .NET parameter full names, for example
`GetTrack(System.UInt64)`. Constructors use IDs such as `.ctor(System.Int32)`.
Pointer-free scalar, enum and data-struct ref/out signatures are supported, with
explicit null placeholders for output-only arguments and returned `out_args`.
Other byref layouts remain excluded. Optional CLR parameters must still be
supplied explicitly in args. The full metadata and marshalling contract is in
[native-api-catalog.md](native-api-catalog.md).

Scalars and enums serialize directly; an enum is its declared name, or its
underlying number if unnamed. Objects/data structs serialize as `{"$ref":"...",
"type":"..."}`; collections may also include `count` without traversing them.
There is no automatic graph expansion. A `$ref` resolves only in its owner session
and must match the exact expected argument type. Close invalidates every reference.
Remove/delete/clear/replace/reset/rollback/undo/redo calls conservatively invalidate
all child references; re-fetch them from the root afterward. At most 65536 live
references are retained per session.

Only pointer-free public VSM data structs/enums can be constructed. Empty args
with no constructor ID create a default value. Nonempty args require a real exact
constructor ID; enums have no CLR constructors, so pass named/numeric enum values
directly to typed setters/calls instead. JSON object literals can populate writable
VSM struct members; nullable values, typed primitive arrays/lists, and compatible
session references are accepted. Strings/bools/numbers are not implicitly coerced.
Numeric ranges, finite floating values, enum membership/flags, and argument counts
are checked. Writable nested struct references write back through their parent;
read-only struct snapshots are detached values. Set/call mutations mark dirty
conservatively, including failed native calls that could have partially changed
state. Get/Can/Has/Is/Contains/IndexOf methods are treated as reads.

Enumeration is explicit and bounded: limit 1..1000, offset 0..100000. Normal
enumerables obtain a fresh enumerator for every page. One-shot enumerator references
retain a cursor and reject backwards offsets; obtain a new reference to restart.
Generic collection objects expose only Count and enumerate, not arbitrary System
methods or constructors. Input array literals are limited to 4096 items and typed
conversion depth to 16. Native result strings are limited to 1 Mi characters.

## Deliberate Restrictions and Extension Point

The safe model excludes pointers, pointer-bearing data structs, callbacks,
observers, sequence-manager lifecycle, raw native-wrapper constructors, App/UI,
arbitrary System objects, file/path APIs, playback/render entry points, and
license/activation/serial/credential members. Lifecycle and persistence use the
dedicated RPC methods only. These excluded methods are not advertised as working
capabilities. There is no authorization patch, activation change, or UI fallback.

The native manager and actual sequence remain accessible internally through
`EngineHost.SequenceManager`, `DatabaseManager`, `DseManager`, and
`GetSequence(session_id)` for additional reviewed rendering integration. Calls
must stay on this same STA thread and retain this host's lifetime. `render_part`
has passed real MCP audio validation; compile-only checks are not audio evidence.

## Discovery-First Examples

The structured editing, audio and library operations are described separately in
[score-operations.md](score-operations.md), [audio-operations.md](audio-operations.md)
and [library-operations.md](library-operations.md). These routes retain the same
native owner thread and are not unrestricted reflection or UI automation.

`clipboard` is separate from the operating-system clipboard. `copy` and `cut`
require a session, `kind` of `tracks`, `parts`, or `notes`, and an `indices`
array. Parts/notes additionally use `track_index` and notes use `part_index`.
The host stores an independent native snapshot and returns `clipboard_id`.
`paste` takes that ID plus a target session and optional nonnegative
`offset_tick`; track insertion uses `index`, other kinds use target track/part
indices. `clear` and `list` need no session. Native MIDI and AI kinds are not
implicitly converted. Snapshots survive closing their original source session.
Pasted asset caches remain owned until host shutdown; at most 128 active private
clipboards and 1024 owned runtime directories are admitted.

Native project import uses staged sources and explicit format dispatch for VPR,
VSQX, PPSF and MIDI/SMF/VSQ. PPSF ZIP and legacy binary forms select their native
loaders by file signature, not by retrying different backends. MIDI export uses
native `SaveSMF`, validates its file header and publishes only under output.
Project merge retains imported asset directories until the target closes.
Tempo-only import uses `include_tracks=false`, `include_tempo=true` and
`replace_tempo=true`; replacing tempo requires zero offset. Revert returns a new
session ID only after a replacement VPR has opened successfully.

These illustrate the wire format; session/object identifiers and constructor
signatures must be taken from actual responses. They are not live-test receipts.

```json
{"id":10,"method":"create","params":{"title":"Native composition","bpm":120}}
{"id":11,"method":"members","params":{"session_id":"SESSION"}}
{"id":12,"method":"call","params":{"session_id":"SESSION","member_id":"GetTrack(System.UInt64)","args":[0]}}
{"id":13,"method":"get","params":{"session_id":"SESSION","member":"TracksEnumerator"}}
{"id":14,"method":"enumerate","params":{"session_id":"SESSION","ref":"COLLECTION_REF","offset":0,"limit":100}}
{"id":15,"method":"set","params":{"session_id":"SESSION","member":"Title","value":"Revised title"}}
{"id":16,"method":"save","params":{"session_id":"SESSION","output_name":"native-composition.vpr"}}
{"id":17,"method":"close","params":{"session_id":"SESSION"}}
```

The installed `InsertMidiAiTrack` method is private, so it is deliberately not
exposed. Its public native route is
`InsertTrackEx(System.UInt64,Yamaha.VOCALOID.VSM.VSMTrackType,System.String)`;
pass `[0,"MidiAi","Lead"]` to insert the first AI track. The returned native
MIDI track exposes
`InsertPart(Yamaha.VOCALOID.VSM.VSMAbsTick,Yamaha.VOCALOID.VSM.VSMRelTick,System.String)`.
The resulting part exposes
`InsertNote(Yamaha.VOCALOID.VSM.VSMRelTick,Yamaha.VOCALOID.VSM.VSMNoteEvent,Yamaha.VOCALOID.VSM.VSMNoteExpression,Yamaha.VOCALOID.VSM.VSMAiNoteExpression,System.String,System.String,System.Boolean,System.Int32)`.
Use `members` and discovered struct constructors/default properties to supply
these arguments. Do not guess overloads or native pointer values. Availability
and synthesis still depend on installed native components and legitimately
available voicebanks. These signatures are metadata evidence, not live editing
or synthesis receipts.

## Validation Status

The real MCP stdio lifecycle has passed native creation, property modification,
save, close, reopen, persisted-property checks and a four-note score roundtrip
through the private-desktop launcher. Evidence:
`artifacts/mcp-smoke-1e947e9c5020.json`, with an unchanged foreground handle and
matching child desktop name. Native VDM enumeration returned 21 available Dnn
voicebanks. The original asynchronous timeout was resolved on 2026-11-10 by
refreshing the clean sequence's render queue through Commit.

`artifacts/background-demo-31c27fd842.json` records the final real MCP stdio check:
compose, native save, close, clean reopen, native synthesis, persisted note/lyric/
phoneme checks, and close with zero sessions remaining. The asa WAV has 374849
mono frames at 44100 Hz in 16-bit PCM, duration 8.499977 seconds, peak 0.1177368
and RMS 0.0138641. Foreground handles before and after are both 19992790. The
complete editor feature surface remains separately unverified.
