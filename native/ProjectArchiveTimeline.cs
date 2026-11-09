using System.IO;
using System.Text.Json.Nodes;
using Yamaha.VOCALOID.VSM;

internal sealed partial class EngineHost
{
    private sealed record TimelinePart(ArchiveEntity Track, ArchiveEntity Part, long Tick,
        HashSet<ArchiveEntity> Notes);
    private sealed record TimelineEventMap(bool CheckTempo, bool CheckTimeSig,
        Dictionary<nint, (long Tick, int Value)> Tempos,
        Dictionary<nint, (int Bar, int Numer, int Denom)> TimeSigs);
    private sealed record TimelineEntities(HashSet<ArchiveEntity> Tracks, Dictionary<ArchiveEntity, TimelinePart> Parts,
        TimelineEventMap Events, TimelineEventMap BeforeEvents, (long Tick, int Value)? GeneratedTempo);

    private static TimelineEventMap ArchiveTimelineEvents(WIVSMSequence sequence, bool checkTempo, bool checkTimeSig)
    {
        Dictionary<nint, (long Tick, int Value)> tempos = [];
        Dictionary<nint, (int Bar, int Numer, int Denom)> timeSigs = [];
        HashSet<long> ticks = [];
        HashSet<int> bars = [];
        if (checkTempo) foreach (WIVSMTempo item in sequence.Tempos)
        {
            nint key = (nint)item;
            long tick = item.RelPosTick.Value;
            if (key == nint.Zero || !ticks.Add(tick) || !tempos.TryAdd(key, (tick, item.Value)))
                throw new InvalidDataException("project_preservation: ambiguous timeline tempo identity or position.");
        }
        if (checkTimeSig) foreach (WIVSMTimeSig item in sequence.TimeSigs)
        {
            nint key = (nint)item;
            int bar = item.PosBar;
            if (key == nint.Zero || !bars.Add(bar) || !timeSigs.TryAdd(key, (bar, item.Value.Numer, item.Value.Denom)))
                throw new InvalidDataException("project_preservation: ambiguous timeline time signature identity or position.");
        }
        return new(checkTempo, checkTimeSig, tempos, timeSigs);
    }

    private void ArchiveTimelineGuard(EngineSession session)
    {
        if (!archiveStates.ContainsKey(session.Id)) return;
        if (ArchiveHasNoteArrayState(session))
            throw new InvalidOperationException("project_preservation: direct pitch extension timeline mapping is not verified.");
        if (ArchiveHasControllerExtensions(session))
            throw new InvalidOperationException("project_preservation: timeline event extensions have no verified identity transaction.");
        foreach (WIVSMTrack track in session.Sequence.Tracks)
            if (track.Type is not (VSMTrackType.Midi or VSMTrackType.MidiAi))
                throw new InvalidOperationException("project_preservation: extended timeline edits require MIDI/AI tracks and exclude audio.");
    }

    private TimelineEntities ArchiveTimelineCapture(EngineSession session, int start, int end, bool insert, bool includeTempo)
    {
        if (!archiveStates.TryGetValue(session.Id, out ArchiveState? state))
            throw new InvalidOperationException("project_preservation: missing timeline archive state.");
        HashSet<ArchiveEntity> tracks = [];
        Dictionary<ArchiveEntity, TimelinePart> parts = [];
        long duration = (long)end - start;
        foreach (WIVSMTrack track in session.Sequence.Tracks)
        {
            ArchiveEntity trackKey = ArchiveKey(track);
            if (!tracks.Add(trackKey) || trackKey.Pointer == nint.Zero)
                throw new InvalidDataException("project_preservation: ambiguous timeline track identity.");
            WIVSMMidiTrack midi = track as WIVSMMidiTrack ?? new WIVSMMidiTrack(track);
            for (ulong index = 0; index < midi.NumParts; index++)
            {
                WIVSMMidiPart part = midi.GetPart(index) ?? throw new InvalidDataException("project_preservation: timeline part lookup failed.");
                long begin = part.AbsBeginTick.Value, finish = part.AbsEndTick.Value;
                if (!insert && begin >= start && finish <= end) continue;
                long tick = begin;
                if (insert && begin >= start) tick += duration;
                else if (!insert && begin >= end) tick -= duration;
                ArchiveEntity key = ArchiveKey(part);
                HashSet<ArchiveEntity> notes = part.Notes.Select(ArchiveKey).ToHashSet();
                if (key.Pointer == nint.Zero || notes.Count != checked((int)part.NumNotes) || notes.Any(note => note.Pointer == nint.Zero) ||
                    !parts.TryAdd(key, new TimelinePart(trackKey, key, tick, notes)))
                    throw new InvalidDataException("project_preservation: ambiguous timeline part or note identity.");
            }
        }
        TimelineEventMap before = ArchiveTimelineEvents(session.Sequence, state.Tempo is not null, state.TimeSig is not null);
        if (state.Tempo is not null) ProjectArchiveArrays.ValidateTempo(state.Tempo, ArchiveNativeTempos(session.Sequence));
        if (state.TimeSig is not null) ProjectArchiveArrays.ValidateTimeSig(state.TimeSig, ArchiveNativeTimeSigs(session.Sequence));
        Dictionary<nint, (long Tick, int Value)> tempos = [];
        (long Tick, int Value)? generatedTempo = null;
        if (!insert && before.CheckTempo && includeTempo && start == 0)
            throw new InvalidOperationException("project_preservation: timeline deletion of the initial tempo is not verified.");
        foreach (var (key, value) in before.Tempos)
        {
            if (!insert && includeTempo && value.Tick >= start && value.Tick < end) continue;
            long offset = !includeTempo ? 0 : insert
                ? (value.Tick > start ? duration : 0)
                : (value.Tick >= end ? -duration : 0);
            tempos.Add(key, (checked(value.Tick + offset), value.Value));
        }
        if (!insert && before.CheckTempo && includeTempo)
        {
            var removed = before.Tempos.Values.Where(value => value.Tick >= start && value.Tick < end)
                .OrderBy(value => value.Tick).ToArray();
            if (removed.Length != 0 && !before.Tempos.Values.Any(value => value.Tick == end))
                generatedTempo = (start, removed[^1].Value);
        }
        Dictionary<nint, (int Bar, int Numer, int Denom)> meters = [];
        if (before.CheckTimeSig)
        {
            WIVSMTimeSig current = session.Sequence.GetTimeSig(new VSMAbsTick(start), true, false)
                ?? throw new InvalidDataException("project_preservation: timeline current time signature is absent.");
            if (insert)
            {
                int barTicks = checked(Yamaha.VOCALOID.Design.Sequence.resolution * 4 * current.Numer / current.Denom);
                if (barTicks <= 0) throw new InvalidDataException("project_preservation: invalid timeline meter duration.");
                int shift = checked((int)((duration + barTicks - 1) / barTicks));
                foreach (var (key, value) in before.TimeSigs)
                    meters.Add(key, (checked(value.Bar + (value.Bar > current.PosBar ? shift : 0)), value.Numer, value.Denom));
            }
            else
            {
                WIVSMTimeSig final = session.Sequence.GetTimeSig(new VSMAbsTick(end), true, false)
                    ?? throw new InvalidDataException("project_preservation: timeline end time signature is absent.");
                int beginBar = session.Sequence.GetMostRecentBarFromTick(new VSMAbsTick(start));
                int endBar = session.Sequence.GetMostRecentBarFromTick(new VSMAbsTick(end));
                int shift = checked(endBar - beginBar);
                if (shift < 0) throw new InvalidDataException("project_preservation: timeline bar order changed.");
                if (shift != 0 && (current.Numer != final.Numer || current.Denom != final.Denom))
                    throw new InvalidOperationException("project_preservation: timeline time signature boundary generation is not verified.");
                foreach (var (key, value) in before.TimeSigs)
                {
                    if (shift != 0 && value.Bar > beginBar && value.Bar <= endBar) continue;
                    meters.Add(key, (checked(value.Bar - (shift != 0 && value.Bar > endBar ? shift : 0)), value.Numer, value.Denom));
                }
            }
        }
        return new TimelineEntities(tracks, parts, new TimelineEventMap(before.CheckTempo, before.CheckTimeSig, tempos, meters), before, generatedTempo);
    }


    private void ArchiveTimelineApplyEvents(EngineSession session, TimelineEntities expected)
    {
        if (!archiveStates.TryGetValue(session.Id, out ArchiveState? state) || state.Before is null)
            throw new InvalidOperationException("project_preservation: timeline event transition outside mutation boundary.");
        if (state.Tempo is not null)
        {
            Dictionary<int, ProjectArchiveArrays.Tempo> next = [];
            foreach (var (key, old) in expected.BeforeEvents.Tempos)
            {
                if (!expected.Events.Tempos.TryGetValue(key, out var target)) continue;
                var entry = state.Tempo[checked((int)old.Tick)];
                int tick = checked((int)target.Tick);
                if (!next.TryAdd(tick, new ProjectArchiveArrays.Tempo(tick, target.Value, entry.Extra)))
                    throw new InvalidDataException("project_preservation: timeline tempo destination collision.");
            }
            if (expected.GeneratedTempo is { } generated &&
                !next.TryAdd(checked((int)generated.Tick), new ProjectArchiveArrays.Tempo(checked((int)generated.Tick), generated.Value, new JsonObject())))
                throw new InvalidDataException("project_preservation: generated timeline tempo destination collision.");
            ProjectArchiveArrays.ValidateTempo(next, ArchiveNativeTempos(session.Sequence));
            state.Tempo = next;
        }
        if (state.TimeSig is not null)
        {
            Dictionary<int, ProjectArchiveArrays.TimeSig> next = [];
            foreach (var (key, old) in expected.BeforeEvents.TimeSigs)
            {
                if (!expected.Events.TimeSigs.TryGetValue(key, out var target)) continue;
                var entry = state.TimeSig[old.Bar];
                if (!next.TryAdd(target.Bar, new ProjectArchiveArrays.TimeSig(target.Bar, target.Numer, target.Denom, entry.Extra)))
                    throw new InvalidDataException("project_preservation: timeline time signature destination collision.");
            }
            ProjectArchiveArrays.ValidateTimeSig(next, ArchiveNativeTimeSigs(session.Sequence));
            state.TimeSig = next;
        }
    }

    private static void ArchiveTimelineValidate(EngineSession session, TimelineEntities expected)
    {
        TimelineEventMap events = ArchiveTimelineEvents(session.Sequence, expected.Events.CheckTempo, expected.Events.CheckTimeSig);
        int generatedCount = expected.GeneratedTempo.HasValue ? 1 : 0;
        if (events.Tempos.Count != expected.Events.Tempos.Count + generatedCount ||
            expected.Events.Tempos.Any(pair => !events.Tempos.TryGetValue(pair.Key, out var value) || value != pair.Value) ||
            events.TimeSigs.Count != expected.Events.TimeSigs.Count ||
            events.TimeSigs.Any(pair => !expected.Events.TimeSigs.TryGetValue(pair.Key, out var value) || value != pair.Value))
            throw new InvalidDataException("project_preservation: timeline event identity transaction changed the tempo or time signature map.");
        var created = events.Tempos.Where(pair => !expected.Events.Tempos.ContainsKey(pair.Key)).ToArray();
        if (created.Length != generatedCount || (expected.GeneratedTempo is { } generated &&
            (expected.BeforeEvents.Tempos.ContainsKey(created[0].Key) || created[0].Value != generated)))
            throw new InvalidDataException("project_preservation: generated timeline tempo identity differs from the expected boundary.");
        HashSet<ArchiveEntity> tracks = [];
        HashSet<ArchiveEntity> parts = [];
        foreach (WIVSMTrack track in session.Sequence.Tracks)
        {
            ArchiveEntity trackKey = ArchiveKey(track);
            if (!tracks.Add(trackKey)) throw new InvalidDataException("project_preservation: duplicate timeline track identity.");
            WIVSMMidiTrack midi = track as WIVSMMidiTrack ?? new WIVSMMidiTrack(track);
            for (ulong index = 0; index < midi.NumParts; index++)
            {
                WIVSMMidiPart part = midi.GetPart(index) ?? throw new InvalidDataException("project_preservation: timeline part lookup failed.");
                ArchiveEntity key = ArchiveKey(part);
                if (!parts.Add(key) || !expected.Parts.TryGetValue(key, out TimelinePart? entry) ||
                    entry.Track != trackKey || entry.Tick != part.AbsBeginTick.Value ||
                    !entry.Notes.SetEquals(part.Notes.Select(ArchiveKey)) || entry.Notes.Count != checked((int)part.NumNotes))
                    throw new InvalidDataException("project_preservation: timeline changed an entity identity or produced an unexpected position.");
            }
        }
        if (!tracks.SetEquals(expected.Tracks) || !parts.SetEquals(expected.Parts.Keys))
            throw new InvalidDataException("project_preservation: timeline removed or created unexpected entities.");
    }
}
