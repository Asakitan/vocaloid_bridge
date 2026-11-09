using System.IO;
using System.Text.Json.Nodes;
using Yamaha.VOCALOID.VSM;

// Integration is deliberately restricted to same-note operations. The central
// archive journal owns snapshots and must call these hooks at its boundaries.
internal sealed partial class EngineHost
{
    private static bool ArchiveNoteArrayHasExtensions(JsonObject noteJson) =>
        ArchiveArray(noteJson["directPitches"], "directPitches").Any(node => node is JsonObject item &&
            item.Any(pair => pair.Key is not ("pos" or "value")));

    private static void ArchiveCaptureNoteArray(ArchiveState state, WIVSMNote note, JsonObject noteJson, JsonObject noteSchema)
    {
        if (!ArchiveNoteArrayHasExtensions(noteJson)) return;
        JsonObject itemSchema = ArchiveResolveSchema(ArchiveItemSchema(ArchivePropertySchema(noteSchema, "directPitches")), ArchiveSchema());
        JsonObject properties = itemSchema["properties"] as JsonObject
            ?? throw new InvalidDataException("project_preservation: missing direct pitch item schema.");
        if (properties.Count != 2 || !properties.ContainsKey("pos") || !properties.ContainsKey("value"))
            throw new InvalidDataException("project_preservation: unsupported direct pitch item schema.");
        ArchiveEntity key = ArchiveKey(note);
        if (key.Pointer == nint.Zero || !state.Live.TryGetValue(key, out ArchiveEntry? entry))
            throw new InvalidDataException("project_preservation: direct pitch owner is not bound.");
        Dictionary<int, ProjectArchiveNoteArrays.Point> points = ProjectArchiveNoteArrays.Read(
            ArchiveArray(noteJson["directPitches"], "directPitches"), true);
        ProjectArchiveNoteArrays.Validate(points, ScorePitchPoints(note));
        state.Live[key] = entry with { DirectPitch = points };
        state.HasEntityExtensions = true;
    }

    private bool ArchiveHasNoteArrayState(EngineSession session) =>
        archiveStates.TryGetValue(session.Id, out ArchiveState? state) &&
        state.Live.Values.Any(entry => entry.DirectPitch is not null);

    // A non-null state is tracked even after its last extension is deleted,
    // because undo can restore that extension and history still needs binding.
    private void RequireArchiveNoteArrayOperation(EngineSession session, string operation)
    {
        if (!ArchiveHasNoteArrayState(session)) return;
        if (operation is not ("note.update" or "pitch.set" or "pitch.clear" or "undo" or "redo" or "history.rollback"))
            throw new InvalidOperationException("project_preservation: direct pitch extension operation has no verified identity mapping: " + operation);
    }

    private void RequireArchiveNoteArrayExternalOperation(EngineSession session, string domain, string operation)
    {
        if (!ArchiveHasNoteArrayState(session)) return;
        if (domain == "clipboard" && operation is ("copy" or "cut" or "paste"))
            throw new InvalidOperationException("project_preservation: direct pitch extension clipboard mapping is unverified.");
    }

    private void ArchiveNoteArrayValidateBeforeEdit(EngineSession session, WIVSMNote note)
    {
        if (!archiveStates.TryGetValue(session.Id, out ArchiveState? state) ||
            !state.Live.TryGetValue(ArchiveKey(note), out ArchiveEntry? entry) || entry.DirectPitch is null) return;
        if (state.Before is null) throw new InvalidOperationException("project_preservation: direct pitch edit outside tracked transaction.");
        ProjectArchiveNoteArrays.Validate(entry.DirectPitch, ScorePitchPoints(note));
    }

    private void ArchiveNoteArraySetStaged(EngineSession session, WIVSMNote note,
        IEnumerable<VSMDirectPitchData> requested, bool replace)
    {
        if (!archiveStates.TryGetValue(session.Id, out ArchiveState? state) ||
            !state.Live.TryGetValue(ArchiveKey(note), out ArchiveEntry? entry) || entry.DirectPitch is null) return;
        if (state.Before is null || state.Action != "pitch.set")
            throw new InvalidOperationException("project_preservation: direct pitch set outside tracked transaction.");
        state.Live[ArchiveKey(note)] = entry with { DirectPitch = ProjectArchiveNoteArrays.Set(
            entry.DirectPitch, requested, replace, ScorePitchPoints(note)) };
    }

    private void ArchiveNoteArrayClearStaged(EngineSession session, WIVSMNote note, int begin, int end, bool clearAll)
    {
        if (!archiveStates.TryGetValue(session.Id, out ArchiveState? state) ||
            !state.Live.TryGetValue(ArchiveKey(note), out ArchiveEntry? entry) || entry.DirectPitch is null) return;
        if (state.Before is null || state.Action != "pitch.clear")
            throw new InvalidOperationException("project_preservation: direct pitch clear outside tracked transaction.");
        state.Live[ArchiveKey(note)] = entry with { DirectPitch = ProjectArchiveNoteArrays.Clear(
            entry.DirectPitch, begin, end, clearAll, ScorePitchPoints(note)) };
    }

    // Call before commit and after history restoration; a changed unselected
    // point or replaced note fails before metadata can be serialized.
    private static void ArchiveValidateNoteArrays(ArchiveState state)
    {
        HashSet<ArchiveEntity> seen = [];
        foreach (WIVSMTrack track in state.Session.Sequence.Tracks)
            foreach (WIVSMPart part in track.Parts)
                if (part is WIVSMMidiPart midi)
                    foreach (WIVSMNote note in midi.Notes)
                    {
                        ArchiveEntity key = ArchiveKey(note);
                        if (!state.Live.TryGetValue(key, out ArchiveEntry? entry) || entry.DirectPitch is null) continue;
                        if (!seen.Add(key)) throw new InvalidDataException("project_preservation: duplicate direct pitch owner.");
                        ProjectArchiveNoteArrays.Validate(entry.DirectPitch, ScorePitchPoints(note));
                    }
        if (state.Live.Count(pair => pair.Value.DirectPitch is not null) != seen.Count)
            throw new InvalidDataException("project_preservation: direct pitch owner disappeared.");
    }

    private void ValidateArchiveNoteArraysBeforeCommit(EngineSession session)
    {
        if (archiveStates.TryGetValue(session.Id, out ArchiveState? state) && state.Before is not null)
            ArchiveValidateNoteArrays(state);
    }

    private static void ArchiveOverlayNoteArray(WIVSMNote note, JsonObject noteJson, ArchiveEntry entry)
    {
        if (entry.DirectPitch is null) return;
        ProjectArchiveNoteArrays.Validate(entry.DirectPitch, ScorePitchPoints(note));
        ProjectArchiveNoteArrays.Overlay(ArchiveArray(noteJson["directPitches"], "directPitches"), entry.DirectPitch);
    }
}
