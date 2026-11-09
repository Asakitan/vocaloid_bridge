# Background MIDI input and recording

Status: integrated and tested with explicit event streams and a muted transport.
No hardware MIDI input has been opened in this investigation.

## Installed editor evidence

The installed `MIDIInputDevice` enumerates WinMM input devices. The installed
`MIDIInputController` opens an input, starts it, and reports note-on/off events;
it filters other channel messages and discards the WinMM timestamp. The editor
assigns current sequence ticks in `MainViewModel.MidiInNoteOnOff`, accumulates
events in `RealtimeRecorder`, and writes notes via VSM transactions. The editor
recorder also calls global `AudioPlayer`/soft-synth and is not used as a
headless entry point. Read-only enumeration on this host found two CubaseAI MCP
ports; neither was opened or tested.

The editor's `MIDIInputDevice` P/Invoke searches only user DLL directories;
that fails to resolve `winmm.dll` in this restricted host. The bridge calls the
same WinMM device enumeration functions directly with `System32` resolution
and the installed editor's `MIDIINCAPS` layout. This does not select or open a
device by itself.

## Contract

`project_midi` operations: `devices`, `start`, `status`, `synthetic_events`,
`stop`, and `cancel`. Devices returns the current numeric WinMM input index,
name and native capabilities without opening ports. For a device recording,
`start` requires both explicit `device_id` and matching `device_name`; no port
is chosen automatically. A name match does not establish that a port is unused
by another application, and Windows device indices can change. MIDI input itself
does not open an audio device; synchronized transport uses its explicitly chosen
output. No interactive editor is controlled.

| Operation | Required options | Result |
| --- | --- | --- |
| `devices` | none; session ID may be omitted | WinMM input indices, names and capabilities; no input opened |
| `start` | `mode`, `track_index`, `part_index`, `lyric`, `phonemes`, `lang_id`; independent mode also needs `start_tick`; device mode needs `device_id`, `device_name` | Active source, target, event count, origin and synchronization flag |
| `status` | none | Active/source-closed state, target, event count, overflow and ignored-message count |
| `synthetic_events` | `events` array | Updated synthetic recording status; no hardware used |
| `stop` | `end_ms` in synthetic mode; no `end_ms` in device mode | Inserted notes, held notes closed on stop, unmatched note-offs and ignored non-note messages |
| `cancel` | none | Close owned input and discard queued events |

`sync_to_transport` is an optional Boolean on `start`, default false. When
true, omit `start_tick`; native transport time supplies the origin. `stop`
closes the source and releases the synchronized transport before score commit.
If stop validation, native close, or score commit fails, queued events cannot
be retried as a commit; cancel is required. A close failure retains the callback
and handle for a subsequent cleanup attempt rather than dropping their owner.

Start requires an armed, unfrozen AI MIDI track, existing AI part with an
assigned AI voice, absolute project `start_tick`, and explicit `lyric`,
`phonemes`, and `lang_id`. MIDI callbacks only queue note events; they never
call VSM from the callback thread. On stop the host converts elapsed times
through the sequence's native tempo map and commits notes to the selected part
in one VSM transaction. MIDI channel and note number distinguish simultaneous
keys; note-on velocity is retained. Missing note-offs close at the actual
device stop time and are counted as `closed_on_stop`; unmatched note-offs are
counted. CC, pitch bend and other non-note short messages are ignored and
counted; SysEx buffers are not registered or counted.
The device callback currently does not report WinMM `MIM_ERROR` notifications;
hardware input and driver-error handling remain unverified.
Notes outside the part, zero-tick lengths, native note-range errors, and event
overflow fail rather than producing a partial batch. An attempted write whose
result is uncertain requires cancel rather than replaying a batch.

By default this is a free-running monotonic recording clock with an explicit
project origin. With `sync_to_transport=true`, start instead requires the same
session's already-playing native transport with looping disabled, captures its
native time as the origin, and checks clock divergence against a tolerance
derived from its device buffer. Stop closes MIDI input and releases that
transport before writing VSM notes. This is buffered-clock alignment, not a
sample-accurate guarantee. While recording is active, the session must be
protected from mutations, seek, render, clone and transport changes;
close/dispose must close the input first. The recorder does not monitor or
synthesize audio and does not implement looping or live DAW sync.

`mode=synthetic` receives an explicitly submitted `synthetic_events` array of
`{elapsed_ms, channel, number, velocity, on}`. It opens no hardware. Synthetic
stop requires explicit `end_ms` to close held notes deterministically. This is
a user-supplied note-event stream, not evidence of hardware input. In transport
sync mode, submitted event and stop times must not be in the future.

## Validation boundaries

`artifacts/feature-acceptance-878d0c135692/summary.json` passed the maintained
MCP case and cleanup, including every `project_midi` operation, explicit event
input, guards and save/reopen. `artifacts/midi-synthetic-3fa675486b20.json`
additionally records note velocity, held-note closure, unmatched note-off,
prevalidation, nonzero origin across a tempo change, and muted synchronized
transport. The selected output was a DirectSound device; no MIDI input was
opened. This verifies an explicitly submitted event stream, not physical device
capture or sample-accurate alignment. The earlier wrapper enumeration failure
is preserved at `artifacts/feature-acceptance-647c107fc2bd/summary.json`.

An explicitly selected independent MIDI input remains unverified; neither
CubaseAI port nor the user's interactive editor was opened for the test.

`tools/check_midi_recording.py` performs the synthetic real-MCP test without
opening a MIDI device. Pass `--transport-device-id` only when an independent,
explicitly selected VAE output is available for the muted synchronized test;
the script never selects an output device automatically.
