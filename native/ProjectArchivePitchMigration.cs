using System.IO;
using System.Text.Json.Nodes;
using Yamaha.VOCALOID.VSM;

internal sealed partial class EngineHost
{
    private sealed record ArchivePitchSource(long Position, Dictionary<int, ProjectArchiveNoteArrays.Point> Points);

    private ArchivePitchSource[]? ArchivePitchCapture(EngineSession session, IEnumerable<WIVSMNote> selected)
    {
        if (!ArchiveHasNoteArrayState(session)) return null;
        var state = archiveStates[session.Id];
        return selected.Select(note =>
        {
            var native = ScorePitchPoints(note).ToDictionary(point => point.Tick,
                point => new ProjectArchiveNoteArrays.Point(point.Value, new JsonObject()));
            if (state.Live.TryGetValue(ArchiveKey(note), out var entry) && entry.DirectPitch is not null)
            {
                ProjectArchiveNoteArrays.Validate(entry.DirectPitch, ScorePitchPoints(note));
                native = ProjectArchiveNoteArrays.Clone(entry.DirectPitch);
            }
            return new ArchivePitchSource(note.RelPosTick.Value, native);
        }).ToArray();
    }

    private void ArchivePitchMigrate(EngineSession session, ArchivePitchSource[]? sources, IEnumerable<WIVSMNote> targets)
    {
        if (sources is null) return;
        var state = archiveStates[session.Id];
        if (state.Before is null || state.Action is not ("note.split" or "note.join"))
            throw new InvalidOperationException("project_preservation: pitch migration outside split/join transaction.");
        Dictionary<long, ProjectArchiveNoteArrays.Point> expected = [];
        foreach (var source in sources)
            foreach (var point in source.Points)
            {
                long tick = checked(source.Position + point.Key);
                if (expected.TryGetValue(tick, out var old))
                {
                    if ((old.Extra.Count != 0 || point.Value.Extra.Count != 0) &&
                        (old.Value != point.Value.Value || (old.Extra.Count != 0 && point.Value.Extra.Count != 0 &&
                         !JsonNode.DeepEquals(old.Extra, point.Value.Extra))))
                        throw new InvalidDataException("project_preservation: conflicting pitch provenance in note join.");
                    if (old.Extra.Count != 0) continue;
                }
                expected[tick] = point.Value;
            }
        foreach (WIVSMNote target in targets)
        {
            Dictionary<int, ProjectArchiveNoteArrays.Point> mapped = [];
            HashSet<long> retained = [];
            foreach (var point in ScorePitchPoints(target))
            {
                long tick = checked(target.RelPosTick.Value + point.Tick);
                JsonObject extra = new();
                if (expected.TryGetValue(tick, out var old) && old.Extra.Count != 0)
                {
                    if (old.Value != point.Value)
                        throw new InvalidDataException("project_preservation: split/join changed an extended pitch value.");
                    extra = (JsonObject)old.Extra.DeepClone();
                    retained.Add(tick);
                }
                if (!mapped.TryAdd(point.Tick, new(point.Value, extra)))
                    throw new InvalidDataException("project_preservation: duplicate migrated pitch position.");
            }
            if (expected.Any(point => point.Value.Extra.Count != 0 && !retained.Contains(point.Key)))
                throw new InvalidDataException("project_preservation: split/join discarded extended pitch provenance.");
            var key = ArchiveKey(target);
            if (!state.Live.TryGetValue(key, out var entry))
                throw new InvalidDataException("project_preservation: migrated pitch owner is not tracked.");
            state.Live[key] = entry with { DirectPitch = mapped };
        }
    }
}
