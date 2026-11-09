using System.Text.Json.Nodes;

internal sealed partial class EngineHost
{
    // Inputs are current native maps. Positions are explicit merge destinations,
    // never inferred array indices.
    private Dictionary<int, ProjectArchiveArrays.Tempo>? PrepareTempoMerge(
        EngineSession target, EngineSession source, long offsetTick, bool replace)
    {
        archiveStates.TryGetValue(target.Id, out ArchiveState? targetState);
        archiveStates.TryGetValue(source.Id, out ArchiveState? sourceState);
        if (targetState?.Tempo is null && sourceState?.Tempo is null) return null;
        var targetNative = ProjectArchiveArrays.ReadTempo(ArchiveNativeTempos(target.Sequence), false);
        var sourceNative = ProjectArchiveArrays.ReadTempo(ArchiveNativeTempos(source.Sequence), false);
        if (targetState?.Tempo is not null)
            ProjectArchiveArrays.ValidateTempo(targetState.Tempo, ArchiveNativeTempos(target.Sequence));
        if (sourceState?.Tempo is not null)
            ProjectArchiveArrays.ValidateTempo(sourceState.Tempo, ArchiveNativeTempos(source.Sequence));
        var result = new Dictionary<int, ProjectArchiveArrays.Tempo>();
        if (!replace)
            foreach (var (position, value) in targetNative)
            {
                JsonObject extra = targetState?.Tempo is not null ? targetState.Tempo[position].Extra : value.Extra;
                result.Add(position, new(position, value.Value, (JsonObject)extra.DeepClone()));
            }
        foreach (var (position, value) in sourceNative)
        {
            int destination = checked((int)(position + offsetTick));
            JsonObject extra = sourceState?.Tempo is not null ? sourceState.Tempo[position].Extra : value.Extra;
            // Native PasteTempo replaces an event at the destination. Its
            // imported fields therefore replace the former event's fields too.
            result[destination] = new(destination, value.Value, (JsonObject)extra.DeepClone());
        }
        return result;
    }
}
