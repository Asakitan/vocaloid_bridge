using System.IO;
using System.Text.Json.Nodes;

// A transaction primitive for the tempo.events array. The caller owns history,
// clone and merge boundaries and invokes this helper for tracked tempo metadata.
internal static class ProjectArchiveArrays
{
    internal sealed record ControllerPoint(int Value, JsonObject Extra);

    internal static Dictionary<int, ControllerPoint> ReadController(JsonArray events, bool captureExtra)
    {
        Dictionary<int, ControllerPoint> result = [];
        foreach (JsonNode? node in events)
        {
            JsonObject item = node as JsonObject ?? throw Error("controller event is not an object");
            int pos = item["pos"]?.GetValue<int>() ?? throw Error("controller position is absent");
            int value = item["value"]?.GetValue<int>() ?? throw Error("controller value is absent");
            JsonObject extra = new();
            foreach ((string key, JsonNode? child) in item)
                if (key is not ("pos" or "value"))
                {
                    if (!captureExtra) throw Error("native controller output has unexpected fields");
                    extra.Add(key, child?.DeepClone());
                }
            if (!result.TryAdd(pos, new ControllerPoint(value, extra))) throw Error("duplicate controller position");
        }
        return result;
    }

    internal static void ValidateController(IReadOnlyDictionary<int, ControllerPoint> state, JsonArray native)
    {
        Dictionary<int, ControllerPoint> observed = ReadController(native, false);
        if (state.Count != observed.Count || state.Any(p => !observed.TryGetValue(p.Key, out ControllerPoint? item) || item.Value != p.Value.Value))
            throw Error("native controller snapshot diverged from retained state");
    }

    internal static void OverlayController(JsonArray native, IReadOnlyDictionary<int, ControllerPoint> state)
    {
        ValidateController(state, native);
        foreach (JsonNode? node in native)
        {
            JsonObject item = (JsonObject)node!;
            foreach ((string key, JsonNode? value) in state[item["pos"]!.GetValue<int>()].Extra)
            {
                if (item.ContainsKey(key)) throw Error("controller extension conflicts with native output");
                item.Add(key, value?.DeepClone());
            }
        }
    }
    internal sealed record TimeSig(int Bar, int Numer, int Denom, JsonObject Extra);

    internal static Dictionary<int, TimeSig> ReadTimeSig(JsonArray array, bool captureExtra)
    {
        Dictionary<int, TimeSig> result = [];
        foreach (JsonNode? node in array)
        {
            JsonObject item = node as JsonObject ?? throw Error("time signature event is not an object");
            int bar = item["bar"]?.GetValue<int>() ?? throw Error("time signature bar is absent");
            int numer = item["numer"]?.GetValue<int>() ?? throw Error("time signature numerator is absent");
            int denom = item["denom"]?.GetValue<int>() ?? throw Error("time signature denominator is absent");
            JsonObject extra = new();
            foreach ((string key, JsonNode? child) in item)
                if (key is not ("bar" or "numer" or "denom"))
                {
                    if (!captureExtra) throw Error("native time signature output has unexpected fields");
                    extra.Add(key, child?.DeepClone());
                }
            if (!result.TryAdd(bar, new TimeSig(bar, numer, denom, extra))) throw Error("duplicate time signature bar");
        }
        return result;
    }

    internal static Dictionary<int, TimeSig> TimeSigTransition(IReadOnlyDictionary<int, TimeSig> before,
        JsonArray nativeAfter, int? oldBar, int? newBar, int? numer, int? denom)
    {
        if (oldBar is null && newBar is null) throw Error("empty time signature transition");
        if ((newBar is null) != (numer is null) || (newBar is null) != (denom is null)) throw Error("incomplete time signature destination");
        Dictionary<int, TimeSig> next = before.ToDictionary(p => p.Key,
            p => new TimeSig(p.Value.Bar, p.Value.Numer, p.Value.Denom, (JsonObject)p.Value.Extra.DeepClone()));
        TimeSig? retained = null;
        if (oldBar is int old && !next.Remove(old, out retained)) throw Error("selected time signature is absent");
        if (newBar is int bar && !next.TryAdd(bar, new TimeSig(bar, numer!.Value, denom!.Value, retained?.Extra ?? new JsonObject())))
            throw Error("time signature destination is ambiguous");
        ValidateTimeSig(next, nativeAfter);
        return next;
    }

    internal static void ValidateTimeSig(IReadOnlyDictionary<int, TimeSig> state, JsonArray native)
    {
        Dictionary<int, TimeSig> observed = ReadTimeSig(native, false);
        if (observed.Count != state.Count || state.Any(p => !observed.TryGetValue(p.Key, out TimeSig? item) || item.Numer != p.Value.Numer || item.Denom != p.Value.Denom))
            throw Error("native time signature snapshot diverged from retained state");
    }

    internal static void OverlayTimeSig(JsonArray native, IReadOnlyDictionary<int, TimeSig> state)
    {
        ValidateTimeSig(state, native);
        foreach (JsonNode? node in native)
        {
            JsonObject item = (JsonObject)node!;
            foreach ((string key, JsonNode? value) in state[item["bar"]!.GetValue<int>()].Extra)
            {
                if (item.ContainsKey(key)) throw Error("time signature extension conflicts with native output");
                item.Add(key, value?.DeepClone());
            }
        }
    }
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
