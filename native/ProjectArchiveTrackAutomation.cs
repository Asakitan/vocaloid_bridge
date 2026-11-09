using System.IO;
using System.Text.Json.Nodes;
using Yamaha.VOCALOID.VSM;

internal sealed partial class EngineHost
{
    private bool ArchiveHasTrackAutomationExtensions(EngineSession session) =>
        archiveStates.TryGetValue(session.Id, out ArchiveState? state) &&
        state.Live.Values.Any(entry => entry.TrackAutomation is not null);

    private static JsonArray ArchiveNativeTrackAutomation(WIVSMTrack track, string scope)
    {
        JsonArray events = new();
        if (scope == "track_volume")
            foreach (var item in track.VolumesEnumerator)
                events.Add(new JsonObject { ["pos"] = checked((int)item.RelPosTick.Value), ["value"] = item.Value });
        else if (scope == "track_pan")
            foreach (var item in track.PanpotsEnumerator)
                events.Add(new JsonObject { ["pos"] = checked((int)item.RelPosTick.Value), ["value"] = item.Value });
        else throw new InvalidDataException("project_preservation: unknown track automation lane.");
        return events;
    }

    private static string ArchiveTrackAutomationProperty(string scope) => scope switch
    {
        "track_volume" => "volume", "track_pan" => "panpot",
        _ => throw new InvalidDataException("project_preservation: unknown track automation lane.")
    };

    private static bool ArchiveCaptureTrackAutomation(ArchiveState state, WIVSMTrack track, JsonObject json, JsonObject schema)
    {
        Dictionary<string, Dictionary<int, ProjectArchiveArrays.ControllerPoint>> lanes = [];
        foreach (string scope in new[] { "track_volume", "track_pan" })
        {
            string property = ArchiveTrackAutomationProperty(scope);
            JsonArray events = ArchiveArray(json[property]?["events"], "/tracks[]/" + property + "/events");
            if (!events.Any(node => node is JsonObject item && item.Any(pair => pair.Key is not ("pos" or "value")))) continue;
            JsonObject itemSchema = ArchiveResolveSchema(ArchiveItemSchema(ArchivePropertySchema(ArchivePropertySchema(schema, property), "events")), ArchiveSchema());
            JsonObject properties = itemSchema["properties"] as JsonObject ?? throw new InvalidDataException("project_preservation: missing track automation schema.");
            if (properties.Count != 2 || !properties.ContainsKey("pos") || !properties.ContainsKey("value"))
                throw new InvalidDataException("project_preservation: unsupported track automation schema.");
            var points = ProjectArchiveArrays.ReadController(events, true);
            ProjectArchiveArrays.ValidateController(points, ArchiveNativeTrackAutomation(track, scope));
            lanes.Add(scope, points);
        }
        if (lanes.Count == 0) return false;
        ArchiveEntity key = ArchiveKey(track);
        state.Live[key] = state.Live[key] with { TrackAutomation = lanes };
        state.HasEntityExtensions = true;
        return true;
    }

    private void ArchiveTrackAutomationPreflight(EngineSession session, string scope, WIVSMTrack? track)
    {
        if (!archiveStates.TryGetValue(session.Id, out ArchiveState? state)) return;
        ArchiveCheck(state);
        ArchiveValidateTrackAutomation(state);
    }

    private void ArchiveTrackAutomationTransition(EngineSession session, string scope, WIVSMTrack? track,
        IReadOnlyList<(int Tick, int Value)> points, bool replace, int? removeTick)
    {
        if (scope == "master_volume" || track is null || !archiveStates.TryGetValue(session.Id, out ArchiveState? state) ||
            !state.Live.TryGetValue(ArchiveKey(track), out ArchiveEntry? entry) || entry.TrackAutomation is null ||
            !entry.TrackAutomation.TryGetValue(scope, out var previous)) return;
        if (state.Before is null) throw new InvalidOperationException("project_preservation: track automation edit outside mutation boundary.");
        Dictionary<int, ProjectArchiveArrays.ControllerPoint> next = new(previous);
        if (replace)
        {
            HashSet<int> requested = points.Select(point => point.Tick).ToHashSet();
            foreach (int tick in next.Keys.Where(tick => tick != 0 && !requested.Contains(tick)).ToArray()) next.Remove(tick);
        }
        if (removeTick is int removed && !next.Remove(removed))
            throw new InvalidDataException("project_preservation: selected track automation event is absent.");
        foreach ((int tick, int value) in points)
            next[tick] = new(value, next.TryGetValue(tick, out var old) ? old.Extra : new JsonObject());
        ProjectArchiveArrays.ValidateController(next, ArchiveNativeTrackAutomation(track, scope));
        var lanes = new Dictionary<string, Dictionary<int, ProjectArchiveArrays.ControllerPoint>>(entry.TrackAutomation) { [scope] = next };
        state.Live[ArchiveKey(track)] = entry with { TrackAutomation = lanes };
    }

    private static void ArchiveValidateTrackAutomation(ArchiveState state)
    {
        var tracked = state.Live.Where(pair => pair.Value.TrackAutomation is not null).ToDictionary(pair => pair.Key, pair => pair.Value);
        HashSet<ArchiveEntity> seen = [];
        foreach (WIVSMTrack track in state.Session.Sequence.Tracks)
        {
            ArchiveEntity key = ArchiveKey(track);
            if (!tracked.TryGetValue(key, out ArchiveEntry? entry)) continue;
            foreach (var lane in entry.TrackAutomation!)
                ProjectArchiveArrays.ValidateController(lane.Value, ArchiveNativeTrackAutomation(track, lane.Key));
            seen.Add(key);
        }
        if (seen.Count != tracked.Count) throw new InvalidDataException("project_preservation: track automation owner is absent.");
    }

    private void ValidateArchiveTrackAutomationBeforeCommit(EngineSession session)
    {
        if (!archiveStates.TryGetValue(session.Id, out ArchiveState? state) || state.Before is null) return;
        ArchiveValidateTrackAutomation(state);
        var native = session.Sequence.Tracks.ToDictionary(track => ArchiveKey(track));
        foreach (var pair in state.Before.Where(pair => pair.Value.TrackAutomation is not null))
        {
            if (state.Deleted?.Contains(pair.Key) == true) continue;
            if (!native.TryGetValue(pair.Key, out WIVSMTrack? track) ||
                !state.Live.TryGetValue(pair.Key, out ArchiveEntry? current) || current.TrackAutomation is null)
                throw new InvalidDataException("project_preservation: track automation owner disappeared before commit.");
            var expected = state.Action is "automation.set" or "automation.remove" or "time.insert" or "time.delete"
                ? current.TrackAutomation : pair.Value.TrackAutomation!;
            if (state.Action is not ("automation.set" or "automation.remove" or "time.insert" or "time.delete") &&
                !ReferenceEquals(expected, current.TrackAutomation))
                throw new InvalidDataException("project_preservation: track automation payload changed before commit.");
            foreach (var lane in expected)
                ProjectArchiveArrays.ValidateController(lane.Value, ArchiveNativeTrackAutomation(track, lane.Key));
            if (!expected.Keys.ToHashSet().SetEquals(current.TrackAutomation.Keys))
                throw new InvalidDataException("project_preservation: track automation lanes changed before commit.");
        }
    }

    private static void ArchiveOverlayTrackAutomation(WIVSMTrack track, JsonObject json, ArchiveEntry entry)
    {
        if (entry.TrackAutomation is null) return;
        foreach (var lane in entry.TrackAutomation)
        {
            ProjectArchiveArrays.ValidateController(lane.Value, ArchiveNativeTrackAutomation(track, lane.Key));
            string property = ArchiveTrackAutomationProperty(lane.Key);
            ProjectArchiveArrays.OverlayController(ArchiveArray(json[property]?["events"], "/tracks[]/" + property + "/events"), lane.Value);
        }
    }
}
