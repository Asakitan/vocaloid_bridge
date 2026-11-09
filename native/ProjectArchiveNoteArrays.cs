using System.IO;
using System.Text.Json.Nodes;
using Yamaha.VOCALOID.VSM;

// The owner binds this state to one native note and snapshots it with native history.
// A coordinate is an operation-selected key, not a claim of native point identity.
internal static class ProjectArchiveNoteArrays
{
    internal sealed record Point(float Value, JsonObject Extra);

    private static InvalidDataException Error(string text) => new("project_preservation: direct pitch " + text);

    private static float ReadValue(JsonNode? node)
    {
        if (node is null) throw Error("value is absent");
        if (node is JsonValue value && value.TryGetValue<string>(out string? text))
            return text == "ZeroPitch" ? float.MinValue : throw Error("unknown symbolic value");
        try { return node.GetValue<float>(); }
        catch (Exception e) when (e is InvalidOperationException or FormatException or OverflowException)
        { throw Error("value is not a float"); }
    }

    internal static Dictionary<int, Point> Read(JsonArray array, bool captureExtra)
    {
        Dictionary<int, Point> result = [];
        foreach (JsonNode? node in array)
        {
            JsonObject item = node as JsonObject ?? throw Error("item is not an object");
            int tick = item["pos"]?.GetValue<int>() ?? throw Error("position is absent");
            float value = ReadValue(item["value"]);
            JsonObject extra = new();
            foreach ((string key, JsonNode? child) in item)
                if (key is not ("pos" or "value"))
                {
                    if (!captureExtra) throw Error("native item has unexpected fields");
                    extra.Add(key, child?.DeepClone());
                }
            if (!result.TryAdd(tick, new Point(value, extra))) throw Error("duplicate position");
        }
        return result;
    }

    internal static void Validate(IReadOnlyDictionary<int, Point> state, IEnumerable<VSMDirectPitchData> native)
    {
        Dictionary<int, float> actual = [];
        foreach (VSMDirectPitchData point in native)
            if (!actual.TryAdd(point.Tick, point.Value)) throw Error("duplicate native position");
        if (state.Count != actual.Count || state.Any(pair => !actual.TryGetValue(pair.Key, out float value) || value != pair.Value.Value))
            throw Error("complete native snapshot diverged");
    }

    // replace clears every old item; upsert retains metadata at the selected tick.
    // Caller validates the complete pre-state and invokes this against staged native output.
    internal static Dictionary<int, Point> Set(IReadOnlyDictionary<int, Point> before,
        IEnumerable<VSMDirectPitchData> requested, bool replace, IEnumerable<VSMDirectPitchData> nativeAfter)
    {
        Dictionary<int, Point> next = replace ? [] : Clone(before);
        HashSet<int> seen = [];
        foreach (VSMDirectPitchData point in requested)
        {
            if (!seen.Add(point.Tick)) throw Error("duplicate requested position");
            JsonObject extra = next.TryGetValue(point.Tick, out Point? old) ? old.Extra : new JsonObject();
            next[point.Tick] = new Point(point.Value, extra);
        }
        Validate(next, nativeAfter);
        return next;
    }

    internal static Dictionary<int, Point> Clear(IReadOnlyDictionary<int, Point> before,
        int begin, int end, bool clearAll, IEnumerable<VSMDirectPitchData> nativeAfter)
    {
        if (end <= begin) throw Error("invalid half-open clear interval");
        Dictionary<int, Point> next = Clone(before);
        foreach (int tick in next.Keys.Where(tick => clearAll || (tick >= begin && tick < end)).ToArray()) next.Remove(tick);
        Validate(next, nativeAfter);
        return next;
    }

    internal static Dictionary<int, Point> Clone(IReadOnlyDictionary<int, Point> source) =>
        source.ToDictionary(pair => pair.Key, pair => new Point(pair.Value.Value, (JsonObject)pair.Value.Extra.DeepClone()));

    internal static void Overlay(JsonArray native, IReadOnlyDictionary<int, Point> state)
    {
        Dictionary<int, Point> actual = Read(native, false);
        if (state.Count != actual.Count || state.Any(pair => !actual.TryGetValue(pair.Key, out Point? item) || item.Value != pair.Value.Value))
            throw Error("serialized snapshot diverged");
        foreach (JsonNode? node in native)
        {
            JsonObject item = (JsonObject)node!;
            foreach ((string key, JsonNode? child) in state[item["pos"]!.GetValue<int>()].Extra)
            {
                if (item.ContainsKey(key)) throw Error("serialized extension conflict");
                item.Add(key, child?.DeepClone());
            }
        }
    }
}
