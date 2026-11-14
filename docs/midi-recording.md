# Background MIDI input and recording

Status: integrated and tested with explicit event streams, a muted transport,
and an independently owned virtual WinMM input. No physical MIDI hardware has
been opened in this investigation.

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
| `status` | none | Active/source-closed state, target, event count, overflow, callback error, invalid-input and backlog counts |
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
The device callback records `MIM_ERROR` and `MIM_LONGERROR` even if the source
is stopping. A reported invalid message, callback fault or queue overflow blocks
the score commit and requires cancellation. `MIDI_IO_STATUS` requests
`MIM_MOREDATA`: it is processed as the same complete MIDI message and counted as
a backlog notification, not treated as evidence of loss. These semantics are
documented by [Microsoft](https://learn.microsoft.com/en-us/windows/win32/multimedia/managing-midi-thru)
and its [MIM_MOREDATA reference](https://learn.microsoft.com/en-us/windows/win32/multimedia/mim-moredata).
`artifacts/midi-callback-b0fae6312bd4.json` exercises the built callback
classifier and pre-commit check through reflection: normal data and backlog
messages are queued, while invalid messages, callback fault and overflow are
rejected. This isolated logic test opens no MIDI device and does not verify a
hardware driver's delivery, timing, callback concurrency or cleanup.
Notes outside the part, zero-tick lengths, native note-range errors, and event
overflow fail rather than producing a partial batch. An attempted write whose
result is uncertain requires cancel rather than replaying a batch.

Recording into an extension-bearing project uses the same archive identity
transaction as native note insertion. Existing tracked curve owners and points
remain subject to their pre-commit checks; unsupported mutations are still
rejected. A recorded note batch that creates indistinguishable serialized note
identities in an extension-bearing project is rolled back before commit. The
tested V6/V7 synthetic streams preserve existing note, pitch,
controller and track-automation extensions plus an extra archive resource
through save/reopen and undo/redo. This does not establish arbitrary extension
combinations or physical MIDI-device behavior.

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

An independently created virtual input has now been tested as described below;
neither CubaseAI port nor the user's interactive editor was opened.

`tools/check_midi_recording.py` performs the synthetic real-MCP test without
opening a MIDI device. Pass `--transport-device-id` only when an independent,
explicitly selected VAE output is available for the muted synchronized test;
the script never selects an output device automatically.

### Independent virtual input feasibility

A read-only host inspection on 2026-11-10 returned Windows build `22631`,
`DisplayVersion` `23H2`, and no service whose name contains `midi`; it did
not open a MIDI port or modify the machine. The registry `ProductName` value
was `Windows 10 Pro`, which by itself does not establish the Windows release.
Microsoft documents that application-owned virtual endpoint creation requires
the Windows MIDI Services API, while WinMM compatibility is optional and
endpoint arrival can be delayed. The API requires Windows 11 25H2 or later:
see the official [virtual device transport](https://microsoft.github.io/MIDI/kb/virtual-device-app/),
[minimum requirements](https://microsoft.github.io/MIDI/kb/minimum-requirements/),
and [MIDI 1.0 integration](https://microsoft.github.io/MIDI/kb/integrating-midi1-and-midi2-apis/)
references. Existing installations of loopMIDI 1.0.16.27 and teVirtualMIDI
SDK 1.3.0.43 were then found; `System32/teVirtualMIDI64.dll` has a valid
Authenticode signature and an x64 PE header. No component was installed,
uninstalled, or reconfigured. The installed SDK header states that named ports
are removed when their creating process terminates, with an inactive endpoint
possible while another application holds its frontend.

`tools/check_midi_owned_input.py` creates a uniquely named input-only endpoint
with the existing SDK, opens only its matching WinMM ID and name, sends short
note-on/off messages with `virtualMIDISendData`, stops and commits, edits the
note, saves and reopens it, closes the project and endpoint, and checks endpoint
absence using a fresh enumeration process. It opens no WinMM output. Receipt
`artifacts/midi-owned-78935c45c6f9.json` reports two received callback events,
one committed note, successful edit/save/reopen, zero remaining owned sessions,
and endpoint absence in the fresh process. The original template was unchanged.
The previous `artifacts/midi-owned-608946611532.json` remains a failed receipt:
same-process enumeration still listed the closed endpoint; a subsequent fresh
process listed only the two original CubaseAI ports. This is virtual driver
input, not a physical MIDI-device test; concurrent delivery, real device loss,
and hardware timing remain unverified. The vendor's
[SDK page](https://www.tobias-erichsen.de/software/virtualmidi/virtualmidi-sdk.html)
documents evaluation and distribution restrictions.
