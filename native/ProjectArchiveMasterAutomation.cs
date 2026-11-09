using System.IO;
using System.Text.Json.Nodes;
using Yamaha.VOCALOID.VSM;

internal sealed partial class EngineHost
{
    private static JsonArray ArchiveNativeMasterVolumes(WIVSMSequence sequence)
    {
        JsonArray events = new();
        foreach (var item in sequence.MasterVolumesEnumerator)
            events.Add(new JsonObject { ["pos"] = checked((int)item.RelPosTick.Value), ["value"] = item.Value });
        return events;
    }

    private static bool ArchiveCaptureMasterVolume(ArchiveState state, JsonObject master, JsonObject masterSchema)
    {
        JsonArray events = ArchiveArray(master["volume"]?["events"], "/masterTrack/volume/events");
        bool hasExtensions = events.Any(node => node is JsonObject item && item.Any(pair => pair.Key is not ("pos" or "value")));
        if (!hasExtensions) return false;
        JsonObject eventSchema = ArchiveResolveSchema(ArchiveItemSchema(ArchivePropertySchema(
            ArchivePropertySchema(masterSchema, "volume"), "events")), ArchiveSchema());
        JsonObject properties = eventSchema["properties"] as JsonObject
            ?? throw new InvalidDataException("project_preservation: missing master volume event schema.");
        if (properties.Count != 2 || !properties.ContainsKey("pos") || !properties.ContainsKey("value"))
            throw new InvalidDataException("project_preservation: unsupported master volume event schema.");
        var result = ProjectArchiveArrays.ReadController(events, true);
        ProjectArchiveArrays.ValidateController(result, ArchiveNativeMasterVolumes(state.Session.Sequence));
        state.MasterVolume = result;
        state.HasEntityExtensions = true;
        return true;
    }

    private void ArchiveMasterVolumePreflight(EngineSession session, string scope)
    {
        if (scope != "master_volume" || !archiveStates.TryGetValue(session.Id, out ArchiveState? state) || state.MasterVolume is null) return;
        ArchiveCheck(state);
        ProjectArchiveArrays.ValidateController(state.MasterVolume, ArchiveNativeMasterVolumes(session.Sequence));
    }

    private void ArchiveMasterVolumeTransition(EngineSession session, string scope,
        IReadOnlyList<(int Tick, int Value)> points, bool replace, int? removeTick)
    {
        if (scope != "master_volume" || !archiveStates.TryGetValue(session.Id, out ArchiveState? state) || state.MasterVolume is null) return;
        if (state.Before is null) throw new InvalidOperationException("project_preservation: master volume edit outside mutation boundary.");
        Dictionary<int, ProjectArchiveArrays.ControllerPoint> next = new(state.MasterVolume);
        if (replace)
        {
            HashSet<int> requested = points.Select(point => point.Tick).ToHashSet();
            foreach (int tick in next.Keys.Where(tick => tick != 0 && !requested.Contains(tick)).ToArray()) next.Remove(tick);
        }
        if (removeTick is int removed && !next.Remove(removed))
            throw new InvalidDataException("project_preservation: selected master volume event is absent.");
        foreach ((int tick, int value) in points)
        {
            JsonObject extra = next.TryGetValue(tick, out ProjectArchiveArrays.ControllerPoint? old) ? old.Extra : new JsonObject();
            next[tick] = new(value, extra);
        }
        ProjectArchiveArrays.ValidateController(next, ArchiveNativeMasterVolumes(session.Sequence));
        state.MasterVolume = next;
    }

    private void ValidateArchiveMasterVolumeBeforeCommit(EngineSession session)
    {
        if (archiveStates.TryGetValue(session.Id, out ArchiveState? state) && state.Before is not null && state.MasterVolume is not null)
            ProjectArchiveArrays.ValidateController(state.MasterVolume, ArchiveNativeMasterVolumes(session.Sequence));
    }
}
