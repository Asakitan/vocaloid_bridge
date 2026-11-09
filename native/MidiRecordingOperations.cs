using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text.Json;
using Yamaha.VOCALOID.MIDIInput;
using Yamaha.VOCALOID.VAE;
using Yamaha.VOCALOID.VSM;

internal sealed partial class EngineHost
{
    private sealed record MidiInputEvent(double Milliseconds, int Channel, int Number, int Velocity, bool On);
    private sealed record MidiCapturedNote(double BeginMs, double EndMs, int Number, int Velocity);

    private sealed class MidiRecording
    {
        internal readonly object Gate = new();
        internal readonly List<MidiInputEvent> Events = [];
        internal readonly Stopwatch Clock = new();
        internal required string Mode;
        internal required int TrackIndex;
        internal required int PartIndex;
        internal required int StartTick;
        internal required string Lyric;
        internal required string Phonemes;
        internal required int LangId;
        internal bool SyncToTransport;
        internal double? StartSeconds;
        internal int? DeviceId;
        internal string? DeviceName;
        internal nint Handle;
        internal MidiCallback? Callback;
        internal bool Active;
        internal bool Overflow;
        internal bool SourceClosed;
        internal bool CommitAttempted;
        internal double StopMs;
        internal int IgnoredNonNote;
        internal void Add(MidiInputEvent value)
        {
            lock (Gate)
            {
                if (!Active) return;
                if (Events.Count >= 8192) { Overflow = true; return; }
                Events.Add(value);
            }
        }
    }

    private readonly Dictionary<string, MidiRecording> midiRecordings = new(StringComparer.Ordinal);
    [UnmanagedFunctionPointer(CallingConvention.Winapi)]
    private delegate void MidiCallback(nint handle, uint message, nuint instance, nuint data, nuint timestamp);
    [DllImport("winmm.dll", EntryPoint = "midiInGetNumDevs")]
    [DefaultDllImportSearchPaths(DllImportSearchPath.System32)]
    private static extern uint MidiInGetNumDevs();
    [DllImport("winmm.dll", EntryPoint = "midiInGetDevCapsW", CharSet = CharSet.Unicode)]
    [DefaultDllImportSearchPaths(DllImportSearchPath.System32)]
    private static extern uint MidiInGetDevCaps(nuint deviceId, ref MIDIINCAPS caps, uint size);
    [DllImport("winmm.dll", EntryPoint = "midiInOpen")]
    [DefaultDllImportSearchPaths(DllImportSearchPath.System32)]
    private static extern uint MidiInOpen(out nint handle, uint deviceId, MidiCallback callback, nuint instance, uint flags);
    [DllImport("winmm.dll", EntryPoint = "midiInStart")]
    [DefaultDllImportSearchPaths(DllImportSearchPath.System32)]
    private static extern uint MidiInStart(nint handle);
    [DllImport("winmm.dll", EntryPoint = "midiInStop")]
    [DefaultDllImportSearchPaths(DllImportSearchPath.System32)]
    private static extern uint MidiInStop(nint handle);
    [DllImport("winmm.dll", EntryPoint = "midiInReset")]
    [DefaultDllImportSearchPaths(DllImportSearchPath.System32)]
    private static extern uint MidiInReset(nint handle);
    [DllImport("winmm.dll", EntryPoint = "midiInClose")]
    [DefaultDllImportSearchPaths(DllImportSearchPath.System32)]
    private static extern uint MidiInClose(nint handle);

    private static int MidiDeviceCount()
    {
        uint count = MidiInGetNumDevs();
        if (count > 4096) throw new InvalidOperationException("MIDI input device count exceeds the limit.");
        return (int)count;
    }

    private static MIDIINCAPS MidiDeviceInfo(int index)
    {
        MIDIINCAPS caps = default;
        uint result = MidiInGetDevCaps((nuint)index, ref caps, (uint)Marshal.SizeOf<MIDIINCAPS>());
        if (result != 0) throw new InvalidOperationException("MIDI input device lookup failed: " + result);
        return caps;
    }

    internal bool HasMidiRecording(EngineSession session) => midiRecordings.ContainsKey(session.Id);

    internal void CheckMidiRecordingAccess(EngineSession session, string method, JsonElement parameters)
    {
        bool syncActive = midiRecordings.Values.Any(value => value.SyncToTransport && !value.SourceClosed);
        if (syncActive && method == "audio_op")
        {
            string audioOperation = parameters.GetProperty("operation").GetString() ?? "";
            if (audioOperation is not ("devices" or "transport_status"))
                throw new InvalidOperationException("Stop synchronized MIDI recording before changing audio transport or running an audio operation.");
        }
        if (!HasMidiRecording(session)) return;
        if (method is "session" or "close" or "members" or "get" or "enumerate" or "construct") return;
        if (method == "score_edit")
        {
            string operation = parameters.GetProperty("operation").GetString() ?? "";
            if (operation.EndsWith(".get", StringComparison.Ordinal) || operation.EndsWith(".list", StringComparison.Ordinal) ||
                operation is "controller.types" or "note.expression_bounds" or "time.convert" or "history.status" or "track.freeze_state") return;
        }
        if (method == "audio_op" && (parameters.GetProperty("operation").GetString() is "devices" or "transport_status")) return;
        throw new InvalidOperationException("Stop or cancel MIDI recording before changing this session.");
    }

    internal void CancelMidiRecording(EngineSession session)
    {
        if (!midiRecordings.TryGetValue(session.Id, out MidiRecording? recording)) return;
        try { CloseMidiSource(recording); }
        finally { if (recording.SyncToTransport && transport?.SessionId == session.Id) ReleaseTransport(); }
        midiRecordings.Remove(session.Id);
    }

    private static void CloseMidiSource(MidiRecording recording)
    {
        lock (recording.Gate)
        {
            if (recording.Mode == "device" && recording.Active) recording.StopMs = recording.Clock.Elapsed.TotalMilliseconds;
            recording.Active = false;
        }
        if (recording.Handle != nint.Zero)
        {
            uint stop = MidiInStop(recording.Handle);
            uint reset = MidiInReset(recording.Handle);
            uint close = MidiInClose(recording.Handle);
            if (close != 0) throw new InvalidOperationException($"MIDI input close failed: {close}; stop={stop}; reset={reset}.");
            recording.Handle = nint.Zero;
            if (stop != 0 || reset != 0)
            {
                recording.SourceClosed = true;
                throw new InvalidOperationException($"MIDI input stop/reset failed: stop={stop}; reset={reset}.");
            }
        }
        recording.Clock.Stop();
        recording.SourceClosed = true;
    }

    internal object MidiRecordingOperation(string? id, string operation, JsonElement options)
    {
        CheckThread();
        if (options.ValueKind != JsonValueKind.Object) throw new ArgumentException("options must be an object.");
        if (operation == "devices")
        {
            int count = MidiDeviceCount();
            return new { native = true, devices = Enumerable.Range(0, count).Select(index => {
                MIDIINCAPS caps = MidiDeviceInfo(index);
                return new { device_id = index, name = caps.szPname, manufacturer_id = caps.wMid, product_id = caps.wPid,
                    driver_version = caps.vDriverVersion, support = caps.dwSupport };
            }).ToArray() };
        }
        EngineSession session = GetSession(id ?? throw new ArgumentException("session_id is required."));
        if (operation == "start")
        {
            if (midiRecordings.ContainsKey(session.Id)) throw new InvalidOperationException("MIDI recording is already active for this session.");
            ScoreRequireUnstaged(session.Sequence);
            int trackIndex = ScoreTrackIndex(session, options);
            WIVSMMidiTrack track = ScoreMidiTrack(session, trackIndex);
            WIVSMMidiPart part = ScorePart(track, options);
            if (!part.IsAi || !track.IsEnabledMidiRecording || track.IsFrozen)
                throw new InvalidOperationException("MIDI recording requires an armed, unfrozen AI track and AI part.");
            if (string.IsNullOrEmpty(part.AiVoiceBankID)) throw new InvalidOperationException("The AI part must have a voice assigned.");
            int begin = checked((int)part.AbsPosTick.Value);
            int end = checked((int)(part.AbsPosTick.Value + part.DurationTick.Value));
            string mode = ScoreString(options, "mode");
            if (mode is not ("device" or "synthetic")) throw new ArgumentException("mode must be device or synthetic.");
            if (mode == "synthetic" && (options.TryGetProperty("device_id", out _) || options.TryGetProperty("device_name", out _)))
                throw new ArgumentException("Synthetic recording does not accept device fields.");
            bool sync = ScoreBool(options, "sync_to_transport");
            if (HasFrozenAuthoring(session)) throw new InvalidOperationException("Unfreeze this session before MIDI recording.");
            if (!sync && transport?.SessionId == session.Id)
                throw new InvalidOperationException("Release this session's transport before independent-clock MIDI recording.");
            double? startSeconds = null;
            int startTick;
            if (sync)
            {
                if (options.TryGetProperty("start_tick", out _)) throw new ArgumentException("Synchronized recording captures its transport origin; omit start_tick.");
                if (transport?.SessionId != session.Id || !VEAudioEngine.IsPlaying() || VEAudioEngine.GetLoopEnabled() || session.Sequence.IsLoopOn)
                    throw new InvalidOperationException("Synchronized recording requires this session's playing transport with loop disabled.");
                startSeconds = VEAudioEngine.GetCurrentTime();
                if (!double.IsFinite(startSeconds.Value) || startSeconds.Value < 0) throw new InvalidOperationException("Native transport position is invalid.");
                startTick = checked((int)session.Sequence.GetTickFromTime(new VSMAbsTick(0), startSeconds.Value).Value);
                if (startTick < begin || startTick >= end) throw new ArgumentOutOfRangeException("sync_to_transport", "Transport position is outside the target part.");
            }
            else startTick = ScoreInt(options, "start_tick", begin, end - 1);
            MidiRecording recording = new() { Mode = mode, TrackIndex = trackIndex,
                PartIndex = ScoreInt(options, "part_index", 0, ScoreCount(track.NumParts) - 1),
                StartTick = startTick, SyncToTransport = sync, StartSeconds = startSeconds,
                Lyric = ScoreString(options, "lyric"), Phonemes = ScoreString(options, "phonemes"),
                LangId = ScoreInt(options, "lang_id", 0, 255), Active = true };
            if (string.IsNullOrWhiteSpace(recording.Phonemes)) throw new ArgumentException("phonemes must be nonempty.");
            recording.Clock.Start();
            if (mode == "device")
            {
                int device = ScoreInt(options, "device_id", 0, MidiDeviceCount() - 1);
                string name = MidiDeviceInfo(device).szPname;
                if (!string.Equals(name, ScoreString(options, "device_name"), StringComparison.Ordinal))
                    throw new ArgumentException("device_name does not match the currently enumerated device_id.");
                if (midiRecordings.Values.Any(item => item.DeviceId == device && !item.SourceClosed))
                    throw new InvalidOperationException("The MIDI input is already owned by another bridge session.");
                recording.DeviceId = device; recording.DeviceName = name;
                recording.Callback = (handle, message, instance, data, timestamp) => {
                    if (message != 0x3c3) return; // MIM_DATA
                    uint packed = unchecked((uint)data);
                    int status = (int)(packed & 0xf0), channel = (int)(packed & 0x0f);
                    if (status is not (0x80 or 0x90))
                    {
                        lock (recording.Gate) if (recording.Active) recording.IgnoredNonNote++;
                        return;
                    }
                    int number = (int)((packed >> 8) & 0x7f), velocity = (int)((packed >> 16) & 0x7f);
                    recording.Add(new MidiInputEvent(recording.Clock.Elapsed.TotalMilliseconds, channel, number, velocity, status == 0x90 && velocity != 0));
                };
                uint result = MidiInOpen(out recording.Handle, (uint)device, recording.Callback, 0, 0x30000);
                if (result != 0) { recording.Active = false; throw new InvalidOperationException("MIDI input open failed: " + result); }
                result = MidiInStart(recording.Handle);
                if (result != 0)
                {
                    lock (recording.Gate) recording.Active = false;
                    uint close = MidiInClose(recording.Handle);
                    if (close != 0) { midiRecordings.Add(session.Id, recording); throw new InvalidOperationException($"MIDI input start failed: {result}; close failed: {close}."); }
                    recording.Handle = nint.Zero;
                    throw new InvalidOperationException("MIDI input start failed: " + result);
                }
            }
            midiRecordings.Add(session.Id, recording);
            return MidiRecordingStatus(recording);
        }
        if (!midiRecordings.TryGetValue(session.Id, out MidiRecording? active))
            throw new InvalidOperationException("This session has no MIDI recording.");
        if (operation == "status") return MidiRecordingStatus(active);
        if (operation == "cancel") { CancelMidiRecording(session); return new { cancelled = true }; }
        if (operation == "synthetic_events")
        {
            if (active.Mode != "synthetic" || !active.Active) throw new InvalidOperationException("Synthetic events require an active synthetic recording.");
            try
            {
            if (!options.TryGetProperty("events", out JsonElement array) || array.ValueKind != JsonValueKind.Array || array.GetArrayLength() is < 1 or > 8192)
                throw new ArgumentException("events must contain 1..8192 note events.");
            List<MidiInputEvent> parsed = [];
            foreach (JsonElement item in array.EnumerateArray())
            {
                float ms = ScoreFloat(item, "elapsed_ms", 0, 3600000);
                int channel = ScoreInt(item, "channel", 0, 15), number = ScoreInt(item, "number", 0, 127), velocity = ScoreInt(item, "velocity", 0, 127);
                if (!item.TryGetProperty("on", out _)) throw new ArgumentException("Each event requires an on Boolean.");
                bool on = ScoreBool(item, "on");
                if (on && velocity == 0) throw new ArgumentException("A note-on requires positive velocity.");
                parsed.Add(new MidiInputEvent(ms, channel, number, velocity, on));
            }
            lock (active.Gate)
            {
                if (active.Events.Count + parsed.Count > 8192) throw new ArgumentException("Recording exceeds 8192 events.");
                double prior = active.Events.Count == 0 ? 0 : active.Events[^1].Milliseconds;
                foreach (MidiInputEvent value in parsed) {
                    if (value.Milliseconds < prior) throw new ArgumentException("Event times must be nondecreasing.");
                    if (active.SyncToTransport && value.Milliseconds > active.Clock.Elapsed.TotalMilliseconds)
                        throw new ArgumentException("Synchronized synthetic events cannot be in the future.");
                    prior = value.Milliseconds;
                }
                active.Events.AddRange(parsed);
            }
            return MidiRecordingStatus(active);
            }
            catch
            {
                CancelMidiRecording(session);
                throw;
            }
        }
        if (operation != "stop") throw new ArgumentException("Unknown MIDI recording operation.");
        if (active.CommitAttempted) throw new InvalidOperationException("Recording commit was already attempted; cancel rather than retrying it.");
        Exception? stopError = null;
        try
        {
            if (active.Mode == "synthetic" && !active.SourceClosed)
            {
                float endMs = ScoreFloat(options, "end_ms", 0, 3600000);
                lock (active.Gate)
                {
                    if (active.Events.Count != 0 && endMs < active.Events[^1].Milliseconds)
                        throw new ArgumentException("end_ms must not precede the last synthetic event.");
                    if (active.SyncToTransport && endMs > active.Clock.Elapsed.TotalMilliseconds)
                        throw new ArgumentException("Synchronized synthetic stop cannot be in the future.");
                    active.StopMs = endMs;
                }
            }
            if (active.Mode == "device" && options.TryGetProperty("end_ms", out _))
                throw new ArgumentException("Device recordings use the actual stop time, not end_ms.");
            if (active.SyncToTransport && !active.SourceClosed)
            {
                if (transport?.SessionId != session.Id || !VEAudioEngine.IsPlaying() || VEAudioEngine.GetLoopEnabled() || session.Sequence.IsLoopOn)
                    throw new InvalidOperationException("Synchronized transport stopped, changed, or looped during recording.");
                double current = VEAudioEngine.GetCurrentTime(), elapsed = active.Clock.Elapsed.TotalSeconds;
                double tolerance = 0.05 + 3.0 * transport.Configuration.BufferSample / transport.Configuration.SampleRate;
                if (!double.IsFinite(current) || Math.Abs(current - active.StartSeconds!.Value - elapsed) > tolerance)
                    throw new InvalidOperationException("Native transport and recording clocks diverged beyond the buffer tolerance.");
            }
        }
        catch (Exception error) { stopError = error; }
        try { if (!active.SourceClosed) CloseMidiSource(active); }
        catch { active.CommitAttempted = true; throw; }
        finally { if (active.SyncToTransport && transport?.SessionId == session.Id) ReleaseTransport(); }
        if (stopError is not null)
        {
            active.CommitAttempted = true;
            throw stopError;
        }
        try { return CommitMidiRecording(session, active); }
        catch { active.CommitAttempted = true; throw; }
    }

    private static object MidiRecordingStatus(MidiRecording recording)
    {
        lock (recording.Gate) return new { mode = recording.Mode, active = recording.Active, source_closed = recording.SourceClosed,
            device_id = recording.DeviceId, device_name = recording.DeviceName, track_index = recording.TrackIndex,
            part_index = recording.PartIndex, start_tick = recording.StartTick, event_count = recording.Events.Count,
            overflow = recording.Overflow, commit_attempted = recording.CommitAttempted, ignored_non_note = recording.IgnoredNonNote,
            sync_to_transport = recording.SyncToTransport, start_seconds = recording.StartSeconds };
    }

    private object CommitMidiRecording(EngineSession session, MidiRecording recording)
    {
        MidiInputEvent[] events;
        lock (recording.Gate)
        {
            if (recording.Overflow) throw new InvalidOperationException("MIDI event capacity exceeded; cancel this recording.");
            events = recording.Events.ToArray();
        }
        Dictionary<(int, int), Queue<MidiInputEvent>> pending = [];
        List<MidiCapturedNote> notes = [];
        int unmatchedOff = 0;
        foreach (MidiInputEvent item in events)
        {
            var key = (item.Channel, item.Number);
            if (item.On)
            {
                if (!pending.TryGetValue(key, out Queue<MidiInputEvent>? queue)) pending.Add(key, queue = new());
                queue.Enqueue(item);
            }
            else if (pending.TryGetValue(key, out Queue<MidiInputEvent>? queue) && queue.Count != 0)
            {
                MidiInputEvent on = queue.Dequeue();
                if (item.Milliseconds <= on.Milliseconds) throw new ArgumentException("Each note-off must follow its note-on.");
                notes.Add(new MidiCapturedNote(on.Milliseconds, item.Milliseconds, item.Number, on.Velocity));
            }
            else unmatchedOff++;
        }
        int closedOnStop = 0;
        foreach (Queue<MidiInputEvent> queue in pending.Values)
            foreach (MidiInputEvent on in queue)
            {
                if (recording.StopMs <= on.Milliseconds) throw new ArgumentException("Each held note requires a positive duration before stop.");
                notes.Add(new MidiCapturedNote(on.Milliseconds, recording.StopMs, on.Number, on.Velocity));
                closedOnStop++;
            }
        WIVSMMidiTrack track = ScoreMidiTrack(session, recording.TrackIndex);
        WIVSMMidiPart part = track.GetPart((ulong)recording.PartIndex) ?? throw new InvalidOperationException("Recording part is missing.");
        long partStart = part.AbsPosTick.Value, partEnd = partStart + part.DurationTick.Value;
        var prepared = notes.Select(note => {
            long begin = recording.SyncToTransport ? session.Sequence.GetTickFromTime(new VSMAbsTick(0), recording.StartSeconds!.Value + note.BeginMs / 1000.0).Value :
                session.Sequence.GetTickFromTime(new VSMAbsTick(recording.StartTick), note.BeginMs / 1000.0).Value;
            long end = recording.SyncToTransport ? session.Sequence.GetTickFromTime(new VSMAbsTick(0), recording.StartSeconds!.Value + note.EndMs / 1000.0).Value :
                session.Sequence.GetTickFromTime(new VSMAbsTick(recording.StartTick), note.EndMs / 1000.0).Value;
            if (begin < partStart || end > partEnd || end <= begin) throw new ArgumentOutOfRangeException("events", "Recorded note exceeds the target part or is shorter than one tick.");
            int relative = checked((int)(begin - partStart)), duration = checked((int)(end - begin));
            VSMNoteEvent minimum = part.GetMinNoteEvent(), maximum = part.GetMaxNoteEvent(relative);
            if (note.Number < minimum.Number || note.Number > maximum.Number || note.Velocity < minimum.Velocity || note.Velocity > maximum.Velocity ||
                duration < minimum.Duration || duration > maximum.Duration) throw new ArgumentOutOfRangeException("events", "Recorded note exceeds native bounds.");
            return (relative, duration, note.Number, note.Velocity);
        }).OrderBy(note => note.relative).ToArray();
        int beforeCount = ScoreCount(part.NumNotes);
        var beforeNotes = part.Notes.GroupBy(note => (note.RelPosTick.Value, note.DurationTick.Value, note.NoteNumber,
            note.NoteVelocity, note.Lyric, note.Phonemes, note.LangID)).ToDictionary(group => group.Key, group => group.Count());
        if (prepared.Length != 0) recording.CommitAttempted = true;
        object result = prepared.Length == 0 ? new { inserted = 0, closed_on_stop = closedOnStop, unmatched_off = unmatchedOff, ignored_non_note = recording.IgnoredNonNote } :
            ScoreMutate(session, "midi.recording.stop", () => {
                foreach (var note in prepared)
                    if (part.InsertNote(new VSMRelTick(note.relative), new VSMNoteEvent(note.duration, note.Number, note.Velocity),
                        part.GetDefaultNoteExpression(), part.GetDefaultAiNoteExpression(), recording.Lyric, recording.Phonemes, true, recording.LangId) is null)
                        throw new InvalidOperationException("Native MIDI note insertion failed: " + part.LastError);
                return true;
            }, () => {
                WIVSMMidiPart current = ScoreMidiTrack(session, recording.TrackIndex).GetPart((ulong)recording.PartIndex)
                    ?? throw new InvalidOperationException("Recording part is missing after commit.");
                var after = current.Notes.GroupBy(note => (note.RelPosTick.Value, note.DurationTick.Value, note.NoteNumber,
                    note.NoteVelocity, note.Lyric, note.Phonemes, note.LangID)).ToDictionary(group => group.Key, group => group.Count());
                ScoreRequire(ScoreCount(current.NumNotes) == beforeCount + prepared.Length, "midi.recording.stop note count readback", session.Sequence);
                foreach (var group in prepared.GroupBy(note => ((long)note.relative, (long)note.duration, note.Number, note.Velocity,
                    recording.Lyric, recording.Phonemes, recording.LangId)))
                    ScoreRequire(after.GetValueOrDefault(group.Key) == beforeNotes.GetValueOrDefault(group.Key) + group.Count(),
                        "midi.recording.stop note readback", session.Sequence);
                return new { inserted = prepared.Length, closed_on_stop = closedOnStop, unmatched_off = unmatchedOff, ignored_non_note = recording.IgnoredNonNote };
            });
        midiRecordings.Remove(session.Id);
        return result;
    }
}
