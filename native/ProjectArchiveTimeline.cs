using System.IO;
using Yamaha.VOCALOID.VSM;

internal sealed partial class EngineHost
{
    private sealed record TimelinePart(ArchiveEntity Track, ArchiveEntity Part, long Tick,
        HashSet<ArchiveEntity> Notes);
    private sealed record TimelineEntities(HashSet<ArchiveEntity> Tracks, Dictionary<ArchiveEntity, TimelinePart> Parts);

    private void ArchiveTimelineGuard(EngineSession session)
    {
        if (!archiveStates.TryGetValue(session.Id, out ArchiveState? state)) return;
        if (ArchiveHasNoteArrayState(session))
            throw new InvalidOperationException("project_preservation: direct pitch extension timeline mapping is not verified.");
        if (state.Tempo is not null || state.TimeSig is not null || ArchiveHasControllerExtensions(session))
            throw new InvalidOperationException("project_preservation: timeline event extensions have no verified identity transaction.");
        foreach (WIVSMTrack track in session.Sequence.Tracks)
            if (track.Type is not (VSMTrackType.Midi or VSMTrackType.MidiAi))
                throw new InvalidOperationException("project_preservation: extended timeline edits require MIDI/AI tracks and exclude audio.");
    }

    private static TimelineEntities ArchiveTimelineCapture(EngineSession session, int start, int end, bool insert)
    {
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
        return new TimelineEntities(tracks, parts);
    }

    private static void ArchiveTimelineValidate(EngineSession session, TimelineEntities expected)
    {
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
