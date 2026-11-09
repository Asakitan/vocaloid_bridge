using System.IO;
using System.Reflection;
using System.Text.Json.Nodes;
using Yamaha.VOCALOID.VSM;

internal sealed partial class EngineHost
{
    private sealed record TimePoint(nint Id, long Position, int Value, int Second = 0);
    private static TimePoint[] TimeVolumes(WIVSMSequence sequence) => sequence.MasterVolumes
        .Select(x => new TimePoint((nint)x, x.RelPosTick.Value, x.Value)).ToArray();
    private static TimePoint[] TimeVolumes(WIVSMTrack track, bool pan) => pan
        ? track.Panpots.Select(x => new TimePoint((nint)x, x.RelPosTick.Value, x.Value)).ToArray()
        : track.Volumes.Select(x => new TimePoint((nint)x, x.RelPosTick.Value, x.Value)).ToArray();

    private static void NativeTimeHelper(string name, object owner, VSMTickRange range)
    {
        MethodInfo method = typeof(Yamaha.VOCALOID.WIVSMSequenceExtension).GetMethod(name,
            BindingFlags.Static | BindingFlags.NonPublic, null, [owner is WIVSMSequence ? typeof(WIVSMSequence) : typeof(WIVSMTrack), typeof(VSMTickRange)], null)
            ?? throw new MissingMethodException("Installed native time helper: " + name);
        try
        {
            if (method.Invoke(null, [owner, range]) is not true)
                throw new InvalidOperationException("Native time helper failed: " + name);
        }
        catch (TargetInvocationException error) { throw new InvalidOperationException("Native time helper failed: " + name, error.InnerException ?? error); }
    }

    private static Dictionary<int, ProjectArchiveArrays.ControllerPoint> TimeMap(TimePoint[] before, TimePoint[] after,
        IReadOnlyDictionary<int, ProjectArchiveArrays.ControllerPoint> payload, int start, int end, bool insert, bool tempo = false)
    {
        if (before.Select(p => p.Id).Distinct().Count() != before.Length || after.Select(p => p.Id).Distinct().Count() != after.Length)
            throw new InvalidDataException("project_preservation: ambiguous timeline curve identity.");
        var prior = before.ToDictionary(p => p.Id);
        var current = after.ToDictionary(p => p.Id);
        foreach (TimePoint old in before)
            if (!current.ContainsKey(old.Id) && (insert || old.Position < start || old.Position >= end))
                throw new InvalidDataException("project_preservation: timeline removed an unselected curve point.");
        Dictionary<int, ProjectArchiveArrays.ControllerPoint> result = [];
        foreach (TimePoint point in after)
        {
            JsonObject extra = new();
            if (prior.TryGetValue(point.Id, out TimePoint? old))
            {
                bool boundary = old.Position == start || old.Position == 0 && start == 0;
                long expected = insert ? (tempo ? old.Position > start : old.Position >= start) ? checked(old.Position + end - start) : old.Position
                    : old.Position >= end ? old.Position - (end - start) : old.Position;
                if (!boundary && (point.Position != expected || point.Value != old.Value))
                    throw new InvalidDataException("project_preservation: timeline changed an unselected curve point.");
                if (payload.TryGetValue(checked((int)old.Position), out var data)) extra = (JsonObject)data.Extra.DeepClone();
            }
            if (!result.TryAdd(checked((int)point.Position), new(point.Value, extra)))
                throw new InvalidDataException("project_preservation: timeline curve destination collision.");
        }
        return result;
    }

    private void TimeSplitPart(EngineSession session, WIVSMTrack track, WIVSMPart part, int tick)
    {
        var state = archiveStates[session.Id];
        if (part is WIVSMMidiPart midi)
        {
            int relative = checked(tick - (int)midi.AbsPosTick.Value);
            foreach (WIVSMNote note in midi.Notes.Where(n => n.RelPosTick.Value < relative && relative < n.RelEndTick.Value).ToArray())
            {
                state.Live.TryGetValue(ArchiveKey(note), out var payload);
                var pitches = ArchivePitchCapture(session, [note]);
                WIVSMNote right = midi.DivideNote(note, new VSMRelTick(relative))
                    ?? throw new InvalidOperationException("Native timeline note split failed.");
                ArchiveCopySplitNote(session, note, right, payload);
                ArchivePitchMigrate(session, pitches, [note, right]);
            }
            var entries = new Dictionary<ArchiveEntity, ArchiveEntry>(state.Live);
            var snapshot = ArchiveSnapshotPart(session, midi);
            WIVSMMidiPart tail = new WIVSMMidiTrack(track).DividePart(new VSMRelTick(relative), midi)
                ?? throw new InvalidOperationException("Native timeline part split failed.");
            ArchiveMigrateParts(session, [snapshot], [midi, tail], true, entries);
        }
        else if (part.Type == VSMPartType.Audio)
        {
            var audio = new WIVSMAudioPart(part);
            var region = audio.Region;
            var entries = new Dictionary<ArchiveEntity, ArchiveEntry>(state.Live);
            var tail = new WIVSMAudioTrack(track).DuplicatePart(audio.AbsPosTick, audio)
                ?? throw new InvalidOperationException("Native timeline audio split failed.");
            int split = checked(region.TickEnd - (int)audio.AbsEndTick.Value + tick);
            ScoreRequire(audio.SetRegion(new(region.TickBegin, split)) && tail.SetRegion(new(split, region.TickEnd)), "time audio split", session.Sequence);
            if (entries.TryGetValue(ArchiveKey(audio), out var entry))
                state.Live[ArchiveKey(tail)] = entry with { Extra = (JsonObject)entry.Extra.DeepClone() };
        }
        else throw new InvalidDataException("Unknown native timeline part kind.");
    }

    private void ApplyNativeTimeEdit(EngineSession session, int start, int end, bool insert, bool includeTempo)
    {
        var sequence = session.Sequence;
        var state = archiveStates[session.Id];
        int duration = checked(end - start);
        VSMTickRange range = new(start, end);
        WIVSMTrack[] tracks = sequence.Tracks.ToArray();
        if (insert && (tracks.SelectMany(t => t.Parts).Any(p => p.AbsEndTick.Value > int.MaxValue - duration) ||
            tracks.Any(t => TimeVolumes(t, false).Concat(TimeVolumes(t, true)).Any(p => p.Position > int.MaxValue - duration)) ||
            TimeVolumes(sequence).Any(p => p.Position > int.MaxValue - duration)))
            throw new ArgumentOutOfRangeException("duration_tick", "Inserted time exceeds the native tick range.");
        var tempo = sequence.Tempos.Select(x => new TimePoint((nint)x, x.RelPosTick.Value, x.Value)).ToArray();
        var meters = sequence.TimeSigs.Select(x => new TimePoint((nint)x, x.PosBar, x.Numer, x.Denom)).ToArray();
        var master = TimeVolumes(sequence);
        var automation = tracks.ToDictionary(ArchiveKey, t => (Volume: TimeVolumes(t, false), Pan: TimeVolumes(t, true)));
        var oldTempo = state.Tempo;
        var oldMeters = state.TimeSig;
        var oldMaster = state.MasterVolume;
        var oldTracks = new Dictionary<ArchiveEntity, ArchiveEntry>(state.Live);
        int beginBar = sequence.GetMostRecentBarFromTick(new(start)), endBar = sequence.GetMostRecentBarFromTick(new(end));

        // Split with native VSM primitives. No editor-global phoneme service is
        // called, and each generated entity receives an explicit metadata map.
        foreach (int boundary in insert ? new[] { start } : new[] { end, start })
            foreach (WIVSMTrack track in tracks)
                foreach (WIVSMPart part in track.Parts.Where(p => p.AbsBeginTick.Value < boundary && boundary < p.AbsEndTick.Value).ToArray())
                    TimeSplitPart(session, track, part, boundary);
        foreach (WIVSMTrack track in tracks)
        {
            if (!insert)
            {
                object[] removed = track.Parts.Where(p => start <= p.AbsBeginTick.Value && p.AbsEndTick.Value <= end).Cast<object>().ToArray();
                var plan = ArchiveDeletePrepare(session, removed);
                foreach (WIVSMPart part in removed) ScoreRequire(track.RemovePart(part), "time part removal", sequence);
                ArchiveDeleteStaged(session, plan);
            }
            var moving = track.Parts.Where(p => p.AbsBeginTick.Value >= (insert ? start : end));
            foreach (WIVSMPart part in (insert ? moving.OrderByDescending(p => p.AbsBeginTick.Value) : moving.OrderBy(p => p.AbsBeginTick.Value)).ToArray())
            {
                long offset = insert ? duration : -duration;
                VSMAbsTick destination;
                if (part is WIVSMAudioPart audio && audio.Region.TickBegin > 0)
                {
                    double lead = sequence.GetTimeFromTick(audio.AbsPosTick, audio.AbsBeginTick);
                    destination = sequence.GetTickFromTime(new(audio.AbsBeginTick.Value + offset), -lead);
                }
                else destination = new(part.AbsPosTick.Value + offset);
                ScoreRequire(track.MovePart(destination, track, part), "time part move", sequence);
            }
        }
        foreach (WIVSMTrack track in tracks)
        {
            NativeTimeHelper(insert ? "InsertSpaceIntoVolumeAutomation" : "DeleteTimeInVolumeAutomation", track, range);
            NativeTimeHelper(insert ? "InsertSpaceIntoPanpotAutomation" : "DeleteTimeInPanpotAutomation", track, range);
        }
        NativeTimeHelper(insert ? "InsertSpaceIntoMainTrack" : "DeleteTimeInMainTrack", sequence, range);
        NativeTimeHelper(insert ? "InsertSpaceIntoTimeSigTrack" : "DeleteTimeInTimeSigTrack", sequence, range);
        if (includeTempo)
        {
            if (insert)
                foreach (WIVSMTempo point in sequence.Tempos.Where(x => x.RelPosTick.Value > start).OrderByDescending(x => x.RelPosTick.Value).ToArray())
                    ScoreRequire(sequence.MoveTempo(new(point.RelPosTick.Value + duration), point), "time tempo move", sequence);
            else NativeTimeHelper("DeleteTimeInTempoTrack", sequence, range);
        }
        if (oldTempo is not null)
        {
            var current = sequence.Tempos.Select(x => new TimePoint((nint)x, x.RelPosTick.Value, x.Value)).ToArray();
            var payload = oldTempo.ToDictionary(x => x.Key, x => new ProjectArchiveArrays.ControllerPoint(x.Value.Value, x.Value.Extra));
            var mapped = includeTempo ? TimeMap(tempo, current, payload, start, end, insert, true) : payload;
            state.Tempo = mapped.ToDictionary(x => x.Key, x => new ProjectArchiveArrays.Tempo(x.Key, x.Value.Value, x.Value.Extra));
        }
        if (oldMeters is not null)
        {
            var prior = meters.ToDictionary(x => x.Id);
            var after = sequence.TimeSigs.ToArray();
            foreach (var old in meters)
                if (!after.Any(x => (nint)x == old.Id) && (insert || old.Position <= beginBar || old.Position > endBar))
                    throw new InvalidDataException("project_preservation: timeline removed an unselected meter.");
            state.TimeSig = after.ToDictionary(x => x.PosBar, x => new ProjectArchiveArrays.TimeSig(x.PosBar, x.Numer, x.Denom,
                prior.TryGetValue((nint)x, out var old) ? (JsonObject)oldMeters[(int)old.Position].Extra.DeepClone() : new JsonObject()));
        }
        if (oldMaster is not null) state.MasterVolume = TimeMap(master, TimeVolumes(sequence), oldMaster, start, end, insert);
        foreach (WIVSMTrack track in tracks)
            if (oldTracks.TryGetValue(ArchiveKey(track), out var entry) && entry.TrackAutomation is not null)
            {
                var lanes = new Dictionary<string, Dictionary<int, ProjectArchiveArrays.ControllerPoint>>();
                foreach (var lane in entry.TrackAutomation)
                    lanes[lane.Key] = TimeMap(lane.Key == "track_pan" ? automation[ArchiveKey(track)].Pan : automation[ArchiveKey(track)].Volume,
                        TimeVolumes(track, lane.Key == "track_pan"), lane.Value, start, end, insert);
                state.Live[ArchiveKey(track)] = entry with { TrackAutomation = lanes };
            }
    }
}
