using System.IO;
using System.Text.Json.Nodes;

// A transaction primitive for the tempo.events array. The caller owns history,
// clone and merge boundaries and invokes this helper for tracked tempo metadata.
internal static class ProjectArchiveArrays
{
    internal sealed record Tempo(int Position, int Value, JsonObject Extra);

    internal static Dictionary<int, Tempo> ReadTempo(JsonArray array, bool captureExtra)
    {
        Dictionary<int, Tempo> result = [];
        foreach (JsonNode? node in array)
        {
            JsonObject item = node as JsonObject ?? throw Error("tempo event is not an object");
            int pos = item["pos"]?.GetValue<int>() ?? throw Error("tempo event position is absent");
            int value = item["value"]?.GetValue<int>() ?? throw Error("tempo event value is absent");
            JsonObject extra = new();
            foreach ((string key, JsonNode? child) in item)
                if (key is not ("pos" or "value"))
                {
                    if (!captureExtra) throw Error("native tempo output has unexpected fields");
                    extra.Add(key, child?.DeepClone());
                }
            if (!result.TryAdd(pos, new Tempo(pos, value, extra))) throw Error("duplicate tempo position");
        }
        return result;
    }

    // Explicit identity comes from the selected native operation, not signatures
    // inferred from before/after arrays. Null oldPosition denotes insertion;
    // null newPosition denotes deletion. Results are independent snapshots.
    internal static Dictionary<int, Tempo> TempoTransition(
        IReadOnlyDictionary<int, Tempo> before, JsonArray nativeAfter,
        int? oldPosition, int? newPosition, int? newValue)
    {
        if (oldPosition is null && newPosition is null) throw Error("empty tempo transition");
        if ((newPosition is null) != (newValue is null)) throw Error("incomplete tempo destination");
        Dictionary<int, Tempo> next = before.ToDictionary(p => p.Key,
            p => new Tempo(p.Value.Position, p.Value.Value, (JsonObject)p.Value.Extra.DeepClone()));
        Tempo? retained = null;
        if (oldPosition is int old && !next.Remove(old, out retained)) throw Error("selected tempo is absent");
        if (newPosition is int position && !next.TryAdd(position,
            new Tempo(position, newValue!.Value, retained?.Extra ?? new JsonObject())))
            throw Error("tempo destination is ambiguous");
        Dictionary<int, Tempo> observed = ReadTempo(nativeAfter, false);
        if (observed.Count != next.Count || next.Any(p => !observed.TryGetValue(p.Key, out Tempo? item) || item.Value != p.Value.Value))
            throw Error("native tempo transition diverged from selected operation");
        return next;
    }

    internal static void OverlayTempo(JsonArray native, IReadOnlyDictionary<int, Tempo> state)
    {
        ValidateTempo(state, native);
        foreach (JsonNode? node in native)
        {
            JsonObject item = (JsonObject)node!;
            foreach ((string key, JsonNode? value) in state[item["pos"]!.GetValue<int>()].Extra)
            {
                if (item.ContainsKey(key)) throw Error("tempo extension conflicts with native output");
                item.Add(key, value?.DeepClone());
            }
        }
    }

    internal static void ValidateTempo(IReadOnlyDictionary<int, Tempo> state, JsonArray native)
    {
        Dictionary<int, Tempo> observed = ReadTempo(native, false);
        if (observed.Count != state.Count || state.Any(p => !observed.TryGetValue(p.Key, out Tempo? item) || item.Value != p.Value.Value))
            throw Error("native tempo snapshot diverged from retained state");
    }

    private static InvalidDataException Error(string message) => new("project_preservation: " + message);
}
