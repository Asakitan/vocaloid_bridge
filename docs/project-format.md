# Structured Project and MIDI Layer

## Scope and Evidence

This layer reads and writes files only. It does not start, focus, automate, or
communicate with VOCALOID, and it does not implement an MCP server.

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
new VPR. It permits arbitrary JSON fields; it is not an editor-schema validator.
The resulting document must remain an object and contain only finite JSON numbers.

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

Files are opened exclusively. Existing output files, including the source itself,
are never replaced. A failed write removes only its newly created partial file.

VPR copy operations require exactly one `Project/sequence.json`. They preserve
member ordering, member payloads other than that JSON, member metadata supported
by `zipfile`, and the archive comment. Embedded audio is copied without decoding.
Only the sequence JSON is reserialized; ZIP compression and JSON whitespace may
change. Unknown JSON fields remain present unless the caller explicitly changes
them. No archive member is extracted to the filesystem.

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

The selected part's first native note supplies defaults. For an empty type-2 AI
part with `aiVoice`, defaults come from the exact observed `editor-note.vpr` schema
embedded in the implementation. Other empty track types require a native prototype.
Defaults include `exp`, `aiExp`, `singingSkill`, `vibrato`, protection flags, language,
and velocity. Unknown prototype fields are retained. Nested `raw` dictionaries
merge into these defaults, while lists/scalars replace their corresponding values.
Raw extras cannot override native core fields `pos`, `duration`, `number`, `lyric`,
`phoneme`, `velocity`, or `langID`; use their validated beat-note inputs instead.
Nested native expression/vibrato durations are retained, not automatically scaled.

An omitted phoneme is written as `""`, never copied from an unrelated prototype
lyric. The layer does not generate phonemes; editor acceptance or recomputation of
an empty phoneme still requires the parent's editor test. Explicit phonemes are
preserved verbatim. `lang_id` defaults to the prototype's `langID` and must belong
to a populated `aiVoice.langIDs` list. The fixture contains language IDs 0, 1, and 4;
language selection is explicit, not inferred from lyric text.

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
Native event and tempo-container extras are retained. The stored global tempo
value is synchronized with the first event, and global-tempo override is disabled
so that the event map remains authoritative.

No controller structure occurs in either supplied fixture. `set_curve` therefore
does not invent lanes. It can replace a unique already-present entry under
`part.controllers` with an exact matching `name` and a nonempty native `events`
prototype containing numeric `pos`/`value` fields. Otherwise it fails explicitly.
Events use `{"start": beats, "value": number}`; positions must be nonnegative and
distinct after quantization, and values finite and consistent with the prototype's
integer/float type. Native event extras and unrelated controller lanes remain.
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
reported no Python errors. These checks are not VOCALOID loading, synthesis,
phoneme generation, controller acceptance, or audio-export verification.