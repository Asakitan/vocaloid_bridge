# Structured Project and MIDI Layer

## Scope and Evidence

VOCALOID7 stores the active AI voice at `track.voice`; VOCALOID6 uses
`part.aiVoice`. File editing and automatic phoneme conversion prefer the track
voice when present. Summaries expose that effective voice in the existing
`aiVoice` result field. New V7 notes use `vibrato.aiCurveModel`; explicitly
selected source-note snapshots retain their fields. Changing a V7 template's
voice clears its old `voiceTypeID`, allowing native open to initialize the
selected bank's default. Actual V7 asa create/save/replace/reopen evidence is
recorded in [session 44](session-log/session-44.md).

This Windows-targeted layer reads and writes files only. VPR access uses pywin32.
It does not start, focus, automate, or communicate with VOCALOID, and it does
not implement an MCP server.

The observed VOCALOID 6.5.1 fixtures are:

- `artifacts/fixtures/editor-seed.vpr`: an editor-authored ZIP containing
  `Project/Audio/` and `Project/sequence.json`, with one type-2 AI track and no notes.
- `artifacts/fixtures/editor-note.vpr`: the same structure with one editor-authored
  native note at position 480, duration 240, MIDI pitch 59, and velocity 64.

The parent editor observation established 480 ticks per quarter note: a four-bar
4/4 part has duration 7680. Native tempo event values use hundredths of BPM:
`{"pos": 0, "value": 12000}` means 120 BPM.

Only VPR ZIP sources are accepted. Plain JSON files are not VPR inputs.

## Public API

```python
class ProjectStore:
    def __init__(self, workspace: Path): ...
    def read(self, path: str | Path) -> dict: ...
    def summary(self, path: str | Path) -> dict: ...
    def inspect(self, path: str | Path, pointer: str = "") -> Any: ...
    def write_copy(self, source: str | Path, data: dict, output_name: str) -> dict: ...
    def patch(self, source: str, operations: list[dict], output_name: str) -> dict: ...
    def compose(self, template: str, output_name: str, title: str, bpm: float,
                notes: list[dict], track_index: int = 0, part_index: int = 0,
                voice_comp_id: str | None = None) -> dict: ...
    def edit_notes(self, source: str, output_name: str, notes: list[dict],
                   track_index: int = 0, part_index: int = 0) -> dict: ...
    def set_curve(self, source: str, output_name: str, controller: str,
                  events: list[dict], track_index: int = 0,
                  part_index: int = 0) -> dict: ...
    def set_tempo(self, source: str, output_name: str, events: list[dict]) -> dict: ...

def export_midi(workspace: Path, title: str, bpm: float,
                tracks: list[dict], output_name: str) -> dict: ...
def import_midi(path: str | Path) -> dict: ...
```

`ProjectStore` is exported from `vocaloid_bridge.projects`; the MIDI functions
are exported from `vocaloid_bridge.music`.

`read` returns the sequence JSON object directly. `inspect` uses an RFC 6901
JSON Pointer; an empty pointer returns the root object. `patch` uses the installed
`jsonpatch` implementation, applies RFC 6902 operations to a copy, and writes a
new VPR. It is not an editor-schema validator. The resulting document must remain
an object and contain only finite JSON numbers. Note-tree changes on projects
with guarded controller, track-automation or direct-pitch-item extensions are
stopped before output creation.

Project mutations return `{"path": absolute_path, "summary": summary_object}`.
The summary includes `title`, `version`, `ticks_per_beat`, native `tempo`, `voices`,
`track_count`, `note_count`, and track/part indices, names, types, durations, and
AI voice data. `summary` does not return all note or effect objects; use `inspect`
or `read` to access those fields.

## Paths and Archive Preservation

The workspace must already exist. Relative project sources stay inside that
workspace; explicitly supplied absolute source paths may be outside it and are
read-only. Traversal, symlinks, directory junctions, and other reparse points are
rejected, including links in parent components. Standalone MIDI import also
accepts existing paths outside the workspace and rejects links and reparse points.

Every write targets `workspace/output/<output_name>`. The name must be relative;
parent traversal, absolute/drive paths, alternate streams, Windows reserved device
names, invalid characters, and trailing dots/spaces are rejected. Nested relative
directories are allowed. Missing suffixes become `.vpr` or `.mid`; incompatible
suffixes are rejected. MIDI export also accepts `.midi`.

Output files are opened exclusively. Existing outputs, including the source itself,
are never replaced. A failed write removes only its newly created partial file.

On Windows, the VPR source is opened with a single read-only handle that shares
reads but not writes or deletion; this handle backs the same ZIP reader throughout
the sequence edit and archive copy. A conflicting existing writer stops the edit
before output creation. `write_copy` accepts caller-provided data and does not
verify the revision from which the caller obtained that data. Controlled local
concurrency evidence and its limits are in [source consistency](source-snapshot-25.md).

VPR copy operations require exactly one `Project/sequence.json`. They preserve
member ordering, member metadata supported by `zipfile`, and the archive comment.
Embedded audio and unrelated members are copied without decoding. Sequence JSON
is reserialized; JSON Patch also reserializes the phoneme-validity sidecar when
tracked note identities or signature fields change. Unknown sidecar root and
per-entry fields remain in the tested file-level cases. ZIP compression and JSON
whitespace may change. AI replacement notes use the explicit identity policy
below. No archive member is extracted to the filesystem.

## JSON Patch and phoneme-validity provenance

When a `phoneme-validity-v1.json` sidecar is present, `patch` validates it
against the source and follows each invalid note through RFC 6902 operations on
a private in-memory copy. A moved note retains its sidecar identity at its new
track/part/note index. A copied note receives an independent copy of its entry.
Removed or replaced note objects lose the former entry; newly added literal notes
do not inherit it. Position, duration and pitch updates update the stored signature.
Changing a tracked note's lyric, phoneme or language is rejected before output;
use the native project edit path for that change.

If the calculated sidecar is unchanged, its original bytes are retained. A changed
sidecar is reserialized with its other JSON fields intact in the tested cases.
This is a file-level provenance contract, not native undo/redo or a general
schema validator. See [patch provenance](patch-sidecar-27.md).

## Notes and Voices

Notes use quarter-note beats, not seconds or native ticks:

```json
{
  "start": 0,
  "duration": 1,
  "pitch": "C4",
  "lyric": "hello",
  "phoneme": "h e l oU",
  "velocity": 64,
  "lang_id": 1,
  "raw": {"exp": {"accent": 40}}
}
```

`start`, `duration`, and `pitch` are required. `lyric` defaults to an empty string.
Pitch accepts integer MIDI 0..127 or scientific names with an optional sharp/flat;
`C4` is MIDI 60. Timing is rounded to the nearest 1/480 beat, with half ticks
rounded upward. Starts must be finite and nonnegative; durations must be finite,
positive, and round to at least one tick. Boolean numeric values are rejected.
Velocity must be an integer 1..127 when supplied. VPR notes may not overlap before
or after quantization; decimal beat comparisons avoid binary floating-point false
overlaps. MIDI tracks may be polyphonic.

For a type-2 AI part with `aiVoice`, every input note without a `source` selector
is a new note using the observed editor-authored AI baseline. It does not inherit
another note's unknown fields, velocity, expressions or vibrato; default velocity
is 64. An omitted language defaults to the first source note's `langID` when
available, or the baseline language 0 when there is no first source note. The
result must belong to a populated `aiVoice.langIDs` list.

To retain a particular existing AI note's fields across a move or edit, supply
`source: {"index": INDEX, "expected": NOTE}`. `INDEX` is the original note index
before replacement, and `NOTE` must be the full JSON object inspected from that
source. A source index may be used once; stale snapshots, invalid indices and
duplicate claims are rejected before output creation. Matching is strict JSON,
including the distinction between `false` and `0`. A note without a selector,
including one at the same tick as an old note, is new; all unselected source notes
are removed. This is a file-level identity policy, not a native object identity.

For example, `old_note` below is obtained from the same source archive:

```python
old_note = store.inspect(source, "/tracks/0/parts/0/notes/0")
store.edit_notes(source, "edited.vpr", [{
    "start": 1, "duration": 0.5, "pitch": 60,
    "lyric": "あ", "phoneme": "a",
    "source": {"index": 0, "expected": old_note}
}])
```

A selected source note retains its own velocity, language, expression, vibrato and
unknown fields unless the caller explicitly changes them. Nested `raw` dictionaries
merge recursively, while lists/scalars replace their corresponding values. Raw
extras cannot override `pos`, `duration`, `number`, `lyric`, `phoneme`, `velocity`,
or `langID`; use the validated beat-note inputs instead. Nested native
expression/vibrato durations are retained, not automatically scaled.

For a selected source note with unchanged lyric and language, omitted `phoneme`
retains that note's original phoneme. Otherwise omission writes `""`. The layer
does not generate phonemes. In the tested AI voice an empty phoneme caused native
open to report a note-count mismatch; give an explicitly valid phoneme for a new
or lyric-changed note until conversion is established. The observation is not a
universal claim about all voices or phonemes. See [AI default evidence](ai-note-defaults-26.md).

If a phoneme-validity sidecar refers to this part, each referenced note must retain
both its source index at the same output index and the referenced fields; conflicts
are rejected rather than remapped. File-level note replacement also rejects source
projects containing tracked controller-event, track volume/pan-event or direct-pitch
item extensions, keeping the existing guarded boundaries. Other populated vocal
track types retain their prior first-note prototype behavior; source selectors are
specific to AI parts.

`edit_notes` replaces the selected part's note list. `compose` also sets the project
title, replaces the tempo map with the supplied BPM at beat zero, and optionally
changes the selected part's `aiVoice.compID`. A requested voice must already occur
in the project's `voices` list. Existing `langIDs`, other parts/tracks, and effect
settings are retained. Use JSON Patch to explicitly edit voice registry metadata.

Part duration is extended to contain the latest note end and is never shortened,
even when notes are removed. Indices must be nonnegative integers; booleans and
out-of-range track/part selections are rejected. The layer does not expand the
master loop range or guess cache invalidation. Neither observed fixture contains
a known synthesis cache, so no unknown fields or archive members are deleted as
purported caches.

## Tempo and Controllers

`set_tempo` accepts `[{"start": 0, "bpm": 120}, {"start": 8, "bpm": 90}]`.
The list must be nonempty, begin at beat zero, and have distinct quantized tick
positions. BPM must be finite, positive, and representable in hundredths.
For an existing selected tick, its unknown event fields are retained; a newly
created tick does not inherit another event's fields, and removed ticks lose
their fields. Existing duplicate positions are rejected before output creation.
Tempo-container extras are retained. The stored global tempo
value is synchronized with the first event, and global-tempo override is disabled
so that the event map remains authoritative.

No controller structure occurred in either original fixture. `set_curve` therefore
does not invent lanes. It can replace a unique already-present entry under
`part.controllers` with an exact matching `name` and a nonempty native `events`
prototype containing numeric `pos`/`value` fields. Otherwise it fails explicitly.
Events use `{"start": beats, "value": number}`; positions must be nonnegative and
distinct after quantization, and values finite and consistent with the prototype's
integer/float type. Unknown fields stay on their original selected tick; new
ticks inherit no event fields, and removed ticks lose them. Duplicate existing
positions are rejected before output creation. Unrelated controller lanes remain.
Controller ranges, creation, and acceptance by VOCALOID are not asserted; use a
real editor-authored controller template or explicit JSON Patch for unknown data.

## MIDI Interchange

Export tracks use `{"name": "Lead", "channel": 0, "program": 40, "notes": [...]}`.
Channels are zero-based 0..15 and default to track index modulo 16; programs are
optional zero-based 0..127. Omitted note velocities become 64. Phoneme/language/raw
expression fields have no MIDI representation and are not exported.

Export creates a synchronous type-1 SMF with 480 PPQ, UTF-8 text/lyrics, and a
separate meta track containing title, tempo, and 4/4 time signature. At a shared
tick, note-offs precede lyric events and note-ons. All tracks end at the latest
note end to retain a stable overall duration. The result includes `path`, `format`,
`title`, `ticks_per_beat`, `bpm`, `track_count`, `note_count`, and `duration_beats`;
the reported track count excludes the meta track.

Import accepts synchronous MIDI type 0/1 with positive PPQ and uses the source
resolution to return quarter-note beats. It returns all tracks, including empty
meta tracks, plus `tempos`, `time_signatures`, `ticks_per_beat`, and `duration_beats`.
Each track includes `name`, `notes`, standalone `lyrics`, `channels`, and timed
`programs`. Each note retains channel, active program, velocity, pitch, duration,
and a same-tick lyric when available. Multiple channels in one track remain
distinct. Same-channel/pitch overlapping note pairs are matched FIFO. A zero-
velocity note-on is a note-off. Unmatched note-offs are ignored; unterminated notes
are rejected rather than silently truncated. Sustain pedal playback is not modeled.
Type-2 asynchronous songs and SMPTE time division are rejected.

Import preserves tempo changes as beat/BPM/microseconds-per-beat events, inserting
the standard 120 BPM initial tempo only when no event exists at beat zero. It does
not infer seconds, lyric language, or phonemes. Same-tick lyric events are assigned
to same-tick notes in source note-on order; unmatched lyric events remain in the
track's standalone lyrics list. Consumers can regroup imported multi-channel notes
into export tracks when desired.

## Validation Boundary

Narrow checks used the isolated workspace Python and disposable output directories.
They covered Unicode MIDI lyrics, 480 PPQ, simultaneous note-off ordering, channel
separation, zero-velocity releases, note validation, exclusive files, VPR embedded
member preservation, archive comments, unknown JSON, native note defaults, language
retention, part extension, JSON Pointer/Patch, and tempo maps. Editor diagnostics
reported no Python errors. Those original checks are not VOCALOID loading, synthesis,
phoneme generation, controller acceptance, or audio-export verification. A
later focused synthetic tempo and Dynamics-controller event test opened and
saved through the native engine in
`artifacts/feature-acceptance-f4c4b6029e12/summary.json`; it does not establish
all controller types or synthesis behavior.
