using System.IO;
using Yamaha.VOCALOID.VSM;

internal sealed partial class EngineHost
{
    private static bool ArchiveDeletionOperation(string operation) =>
        operation is "track.remove" or "part.remove" or "note.remove" or "note.clear" or "clipboard.cut";

    private sealed record ArchiveDeletionPlan(Dictionary<ArchiveEntity, ArchiveEntity?> Before, HashSet<ArchiveEntity> Dead, Dictionary<ArchiveEntity, ArchiveEntry> Live);

    private ArchiveDeletionPlan? ArchiveDeletePrepare(EngineSession session, IEnumerable<object> targets)
    {
        if (!archiveStates.TryGetValue(session.Id, out ArchiveState? state) || !state.HasEntityExtensions) return null;
        if (state.Before is null || !ArchiveDeletionOperation(state.Action!) && state.Action is not ("time.insert" or "time.delete"))
            throw new InvalidOperationException("project_preservation: deletion outside tracked transaction.");
        Dictionary<ArchiveEntity, ArchiveEntity?> current = ArchiveNativeParents(session);
        if (state.Live.Any(pair => !current.TryGetValue(pair.Key, out var parent) || pair.Value.Parent != parent))
            throw new InvalidDataException("project_preservation: deletion preflight identity or parent mismatch.");
        ArchiveValidateNoteArrays(state);
        ArchiveValidateTrackAutomation(state);
        HashSet<ArchiveEntity> dead = [];
        foreach (object target in targets)
        {
            ArchiveEntity key = ArchiveKey(target);
            if (!current.ContainsKey(key) || !dead.Add(key))
                throw new InvalidDataException("project_preservation: deletion target is missing or ambiguous.");
        }
        bool changed;
        do
        {
            changed = false;
            foreach ((ArchiveEntity key, ArchiveEntity? parent) in current)
                if (parent is ArchiveEntity p && dead.Contains(p) && dead.Add(key)) changed = true;
        } while (changed);
        return new(current, dead, new(state.Live));
    }

    private void ArchiveDeleteStaged(EngineSession session, ArchiveDeletionPlan? plan)
    {
        if (plan is null) return;
        var dead = plan.Dead;
        ArchiveState state = archiveStates[session.Id];
        var before = state.Before ?? throw new InvalidOperationException("project_preservation: deletion transaction ended early.");
        var current = ArchiveNativeParents(session);
        if (!current.Keys.ToHashSet().SetEquals(plan.Before.Keys.Where(key => !dead.Contains(key))) ||
            current.Any(pair => plan.Before[pair.Key] != pair.Value))
            throw new InvalidDataException("project_preservation: deletion changed an unselected identity or parent.");
        state.Live = plan.Live.Where(pair => !dead.Contains(pair.Key)).ToDictionary(pair => pair.Key, pair => pair.Value);
        state.Deleted ??= [];
        state.Deleted.UnionWith(dead);
        ArchiveValidateNoteArrays(state);
        ArchiveValidateTrackAutomation(state);
    }

    private static Dictionary<ArchiveEntity, ArchiveEntity?> ArchiveNativeParents(EngineSession session)
    {
        Dictionary<ArchiveEntity, ArchiveEntity?> result = [];
        void Add(object entity, ArchiveEntity? parent)
        {
            ArchiveEntity key = ArchiveKey(entity);
            if (key.Pointer == nint.Zero || !result.TryAdd(key, parent))
                throw new InvalidDataException("project_preservation: ambiguous native entity identity.");
        }
        foreach (WIVSMTrack track in session.Sequence.Tracks)
        {
            ArchiveEntity trackKey = ArchiveKey(track); Add(track, null);
            foreach (WIVSMPart part in track.Parts)
            {
                ArchiveEntity partKey = ArchiveKey(part); Add(part, trackKey);
                if (part is WIVSMMidiPart midi)
                    foreach (WIVSMNote note in midi.Notes) Add(note, partKey);
            }
        }
        return result;
    }
}
