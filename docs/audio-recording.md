# Audio Recording and External Host Boundary

## Audio Input and Recording

The [VOCALOID6 Editor support FAQ](https://www.vocaloid.com/en/support/faq/625)
states that the editor has no audio recording function. Its
[VOCALO CHANGER FAQ](https://www.vocaloid.com/support/faq/681) directs users to
record in a DAW and import the WAV. Accordingly this bridge does not advertise
a native microphone-recording operation. Existing `import_audio` accepts an
already recorded WAV; it is asset import, not live recording.

The installed `RealtimeRecorder` handles `MIDIInputController`, note events,
`RecNote`, and MIDI tracks. This is distinct from waveform capture; the
[official MIDI recording FAQ](https://www.vocaloid.com/en/support/faq/613)
also describes a MIDI keyboard and a piano guide. No MIDI or microphone input
was opened for this audit.

`tools/check_audio_recording.py` reads the installed `VAE.dll` export table and
the locally decompiled managed wrappers without loading the engine. Its output
`artifacts/audio-recording-static-5a1b123b54f8.json` lists all exports and found
no export containing record, capture, wavein, or inputdevice. That is a search
of names and managed wrappers, not proof that no undocumented binary interface
exists. VAE's `InputGain` and `InputPan` refer to mixer input buses, not an
identified microphone-capture API. `devices` in the current bridge enumerates
the VAE output device configuration and must not be treated as an input-device
inventory. No proprietary native recording implementation or Windows audio
capture substitute was added.

## DAW / Plugin Host

The [VOCALOID6 reference manual](https://rsc-net.vocaloid.com/assets/pdf_files/bb/VOCALOID_Reference_Manual_ENG.pdf)
describes VST/AU operation and ARA through VOCALOID Bridge inside a compatible
host. The installed VAE wrapper exposes `SetSampleRateFromHost`,
`SetCurrentPositionFromHost`, `SetPlaybackFromHost`, `SetLoopFromHost`, and
`RenderWaveDataParams`. The latter accepts a `VocRWWaveDataParams` structure
containing channel, position, sample-count and unmanaged data pointers.
`VOCALOID VSTi.vst3` and `VOCALOIDBridge.vst3` are present in the machine's
VST3 directory, each exporting `InitDll`, `GetPluginFactory`, and `ExitDll`.
Cubase 16 is installed at `C:/Program Files/Steinberg/Cubase 16/Cubase 16.exe`.
Presence does not mean either plugin has been loaded or tested with a DAW; this
audit did not start Cubase or connect to the user's editor.

A real integration requires an actual compatible host to instantiate the
plugin, provide its realtime callback, properly scoped audio-buffer lifetime,
playback clock, tempo, loop and external bus mapping, and observe results.
Exposing raw pointers to a stateless JSON call or fabricating host clocks would
not establish this integration. The bridge's existing VAE `VST` connection for
offline Manual mixdown is a host-clocked mixer configuration, not evidence of
a DAW connection. The current private standalone transport and offline mixdown
own the per-process VAE engine; any future host bridge must coordinate
exclusive ownership and lifetime with them. No external host synchronization,
ARA, or realtime recording is claimed by this audit.

## Isolated Host Candidate

The current [Steinberg VST3 SDK 3.8.x](https://github.com/steinbergmedia/vst3sdk)
uses the MIT license and includes a command-line plugin validator. Its
[host process data](https://steinbergmedia.github.io/vst3_doc/vstsdk/classSteinberg_1_1Vst_1_1HostProcessData.html)
and [audio processor interface](https://steinbergmedia.github.io/vst3_doc/vstinterfaces/classSteinberg_1_1Vst_1_1IAudioProcessor.html)
provide a basis for a real isolated plugin host with bounded PCM buffers,
MIDI events and process context. A dedicated child process on a private desktop
could load the installed plugin, instantiate its component, negotiate buses,
set explicit state, supply real process contexts and record callback outcomes;
plugin lifecycle and buffers would stay inside that child. A validator-only
pass would establish neither a VOCALOID editor connection nor DAW sync.

Both installed plugin binaries contain named-pipe creation references; the
VSTi also contains a bridge connection message. Private desktop isolation alone
does not establish isolation of named IPC. Before plugin instantiation, its
actual IPC addressing and process ownership need to be demonstrated to avoid
connecting to an existing user editor. Plugin state, event, transport and
process-buffer behavior remain untested, as does ARA hosting. No SDK, host or
plugin was downloaded, built, started, or installed in this investigation.

[Pedalboard](https://github.com/spotify/pedalboard) is a GPLv3 library that
[hosts VST3 and exposes MIDI and plugin state](https://spotify.github.io/pedalboard/reference/pedalboard.html).
Its documented Python process interface inspected here does not expose the
DAW transport/tempo controls needed for this test. The SDK candidate therefore
provides a clearer route for explicit process context, subject to an actual
isolated-host implementation and the IPC check above.
