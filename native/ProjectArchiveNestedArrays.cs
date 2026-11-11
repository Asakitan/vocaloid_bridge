using System.IO;
using System.Text.Json.Nodes;
using Yamaha.VOCALOID.VSM;

internal sealed partial class EngineHost
{
    private const string ArrayPrefix = "@array:";
    private static bool DedicatedArray(string owner, string pointer) =>
        owner == "" && pointer is "/tracks" || owner == "/tracks[]" && pointer == "/parts" ||
        owner == "/tracks[]/parts[]" && pointer == "/notes" ||
        owner.EndsWith("/notes[]", StringComparison.Ordinal) && pointer == "/directPitches" ||
        owner == "/masterTrack" && pointer is "/tempo/events" or "/timeSig/events" or "/volume/events" ||
        owner == "/tracks[]" && pointer is "/volume/events" or "/panpot/events" ||
        owner.EndsWith("/controllers[]", StringComparison.Ordinal) && pointer == "/events";

    private static JsonObject ArrayItemSchema(JsonObject schema)
    {
        schema = ArchiveResolveSchema(schema, ArchiveSchema());
        if (schema["items"] is JsonObject item) return ArchiveResolveSchema(item, ArchiveSchema());
        if (schema["langID"] is JsonObject language) return new JsonObject
            { ["type"] = "object", ["properties"] = new JsonObject { ["langID"] = language.DeepClone() } };
        return new JsonObject();
    }

    private static JsonNode? KnownJson(JsonNode? value, JsonObject schema)
    {
        schema = ArchiveResolveSchema(schema, ArchiveSchema());
        if (value is JsonObject obj && schema["properties"] is JsonObject properties)
        {
            JsonObject result = new();
            foreach (var field in obj.OrderBy(x => x.Key, StringComparer.Ordinal))
                if (properties[field.Key] is JsonObject child) result[field.Key] = KnownJson(field.Value, child);
            return result;
        }
        if (value is JsonArray array)
            return new JsonArray(array.Select(item => KnownJson(item, ArrayItemSchema(schema))).ToArray());
        return value?.DeepClone();
    }

    private static string Canonical(JsonNode? value)
    {
        if (value is JsonObject obj)
            return "{" + string.Join(",", obj.OrderBy(x => x.Key, StringComparer.Ordinal).Select(x =>
                System.Text.Json.JsonSerializer.Serialize(x.Key) + ":" + Canonical(x.Value))) + "}";
        if (value is JsonArray array) return "[" + string.Join(",", array.Select(Canonical)) + "]";
        return value?.ToJsonString() ?? "null";
    }

    private static JsonObject? CaptureArray(JsonArray values, JsonObject schema, string owner)
    {
        JsonObject itemSchema = ArrayItemSchema(schema);
        if (itemSchema["properties"] is not JsonObject) return null;
        var objects = values.OfType<JsonObject>().ToArray();
        if (objects.Length != values.Count) throw new InvalidDataException("project_preservation: mixed object array.");
        string field = new[] { "compID", "langID", "name", "id", "pos", "bar" }
            .FirstOrDefault(key => objects.Length != 0 && objects.All(item => item[key] is JsonValue)) ?? "";
        JsonArray entries = new();
        bool payload = false;
        foreach (JsonObject item in objects)
        {
            JsonObject extra = ArchiveUnknownFields(item, itemSchema, owner);
            payload |= extra.Count != 0;
            entries.Add(new JsonObject { ["key"] = field.Length == 0 ? "" : Canonical(item[field]),
                ["known"] = KnownJson(item, itemSchema), ["extra"] = extra });
        }
        return payload ? new JsonObject { ["version"] = 1, ["field"] = field, ["items"] = entries } : null;
    }

    private static void ValidateArrayMetadata(string pointer, JsonNode? metadata, JsonObject schema)
    {
        if (!pointer.StartsWith("/", StringComparison.Ordinal) || metadata is not JsonObject payload ||
            payload["version"]?.GetValue<int>() != 1 || payload["items"] is not JsonArray items || items.Count > 65536)
            throw new InvalidDataException("project_preservation: invalid media array metadata.");
        foreach (string segment in pointer[1..].Split('/'))
            schema = ArchivePropertySchema(schema, segment.Replace("~1", "/", StringComparison.Ordinal).Replace("~0", "~", StringComparison.Ordinal));
        JsonObject itemSchema = ArrayItemSchema(schema);
        string field = payload["field"]?.GetValue<string>() ?? throw new InvalidDataException("Array key is absent.");
        if (field.Length != 0 && (itemSchema["properties"] as JsonObject)?.ContainsKey(field) != true)
            throw new InvalidDataException("Array key is not a native field.");
        foreach (JsonNode? node in items)
        {
            if (node is not JsonObject item || item["extra"] is not JsonObject extra || item["known"] is not JsonObject known ||
                Canonical(KnownJson(known, itemSchema)) != Canonical(known) ||
                item["key"]?.GetValue<string>() != (field.Length == 0 ? "" : Canonical(known[field])))
                throw new InvalidDataException("Invalid array item metadata.");
            LibraryArchiveValidateExtra(extra, itemSchema);
        }
    }

    private static JsonNode? JsonPath(JsonObject owner, string pointer)
    {
        JsonNode? current = owner;
        foreach (string segment in pointer.TrimStart('/').Split('/'))
            current = (current as JsonObject)?[segment.Replace("~1", "/", StringComparison.Ordinal).Replace("~0", "~", StringComparison.Ordinal)];
        return current;
    }

    private static JsonObject ReconcileArray(JsonObject payload, JsonArray actual, bool overlay,
        bool allowRemoval = false, Func<string, bool>? removals = null)
    {
        if (payload["version"]?.GetValue<int>() != 1 || payload["items"] is not JsonArray entries)
            throw new InvalidDataException("project_preservation: invalid array metadata.");
        string field = payload["field"]?.GetValue<string>() ?? "";
        var saved = entries.Select(item => item as JsonObject ?? throw new InvalidDataException("Invalid array entry.")).ToList();
        var live = actual.Select(item => item as JsonObject ?? throw new InvalidDataException("Invalid native object array.")).ToArray();
        Dictionary<int, int> pairs = [];
        HashSet<int> used = [];
        // Match unchanged entries first. Natural-key groups with exactly one
        // unmatched entry can then retain metadata across a value edit.
        for (int i = 0; i < live.Length; i++)
        {
            string key = field.Length == 0 ? "" : Canonical(live[i][field]);
            var matches = Enumerable.Range(0, saved.Count).Where(j => !used.Contains(j) && saved[j]["key"]?.GetValue<string>() == key &&
                Canonical(saved[j]["known"]) == Canonical(live[i])).ToArray();
            if (matches.Length == 1) { pairs[i] = matches[0]; used.Add(matches[0]); }
        }
        foreach (string key in saved.Select(item => item["key"]!.GetValue<string>()).Distinct())
        {
            var old = Enumerable.Range(0, saved.Count).Where(j => !used.Contains(j) && saved[j]["key"]!.GetValue<string>() == key).ToArray();
            var next = Enumerable.Range(0, live.Length).Where(i => !pairs.ContainsKey(i) && (field.Length == 0 ? "" : Canonical(live[i][field])) == key).ToArray();
            if (old.Length == 1 && next.Length == 1 && field.Length != 0) { pairs[next[0]] = old[0]; used.Add(old[0]); }
            else if (next.Length != 0 && old.Any(j => (saved[j]["extra"] as JsonObject)?.Count > 0))
                throw new InvalidDataException("project_preservation: ambiguous array item identity.");
        }
        if (!allowRemoval && Enumerable.Range(0, saved.Count).Any(j => !used.Contains(j) && (saved[j]["extra"] as JsonObject)?.Count > 0))
            throw new InvalidDataException("project_preservation: an unselected array item lost its metadata identity.");
        JsonArray retained = new();
        for (int i = 0; i < live.Length; i++)
        {
            JsonObject extra = pairs.TryGetValue(i, out int index)
                ? (JsonObject)saved[index]["extra"]!.DeepClone() : new();
            ReconcileNested(live[i], extra, overlay, removals);
            retained.Add(new JsonObject { ["key"] = field.Length == 0 ? "" : Canonical(live[i][field]),
                ["known"] = StripOverlay(live[i], extra), ["extra"] = extra });
        }
        return new JsonObject { ["version"] = 1, ["field"] = field, ["items"] = retained };
    }

    private static JsonNode StripOverlay(JsonObject source, JsonObject extra)
    {
        JsonObject result = (JsonObject)source.DeepClone();
        foreach (var item in extra)
        {
            if (item.Key.StartsWith(ArrayPrefix, StringComparison.Ordinal)) continue;
            int slash = item.Key.LastIndexOf('/');
            var parent = slash == 0 ? result : JsonPath(result, item.Key[..slash]) as JsonObject;
            parent?.Remove(item.Key[(slash + 1)..].Replace("~1", "/", StringComparison.Ordinal).Replace("~0", "~", StringComparison.Ordinal));
        }
        return result;
    }

    private static void ReconcileNested(JsonObject native, JsonObject extra, bool overlay, Func<string, bool>? removals = null)
    {
        foreach (string path in extra.Select(x => x.Key).Where(key => key.StartsWith(ArrayPrefix, StringComparison.Ordinal)).ToArray())
        {
            if (extra[path] is not JsonObject payload) throw new InvalidDataException("Invalid nested array payload.");
            if (JsonPath(native, path[ArrayPrefix.Length..]) is not JsonArray actual)
            {
                if (removals?.Invoke(path) != true && payload["items"] is JsonArray old && old.Any(x => (x?["extra"] as JsonObject)?.Count > 0))
                    throw new InvalidDataException("project_preservation: an unselected array disappeared.");
                extra.Remove(path); continue;
            }
            extra[path] = ReconcileArray(payload, actual, overlay, removals?.Invoke(path) == true, removals);
        }
        if (overlay)
        {
            JsonObject fields = new();
            foreach (var pair in extra.Where(x => !x.Key.StartsWith(ArrayPrefix, StringComparison.Ordinal)))
                fields[pair.Key] = pair.Value?.DeepClone();
            ArchiveOverlay(native, fields);
        }
    }

    private void ReconcileStagedArrays(EngineSession session)
    {
        if (!archiveStates.TryGetValue(session.Id, out var state) || state.Before is null) return;
        bool Has(JsonObject extra) => extra.Any(x => x.Key.StartsWith(ArrayPrefix, StringComparison.Ordinal));
        if (!Has(state.Root) && !Has(state.Master) && !state.Live.Values.Any(entry => Has(entry.Extra))) return;
        string dir = Path.Combine(session.Directory, "array-" + Guid.NewGuid().ToString("N"));
        PathGuard.CreateDirectory(dir);
        bool modified = session.Sequence.IsModifiedOutsideOfEditHistory, staged = session.Sequence.IsStaged;
        bool AllowRemoval(string path) => state.Action switch
        {
            "vibrato.set" => path.Contains("/vibrato/", StringComparison.Ordinal),
            "phoneme_timing.set" or "phoneme_timing.reset" or "lyrics_apply" or "phonemes_apply" or "lyrics_reset" or "phonemes_reset" => path.Contains("/phonemePositions", StringComparison.Ordinal),
            "audio.set_effect" or "style_apply" => path.Contains("Effects", StringComparison.Ordinal) || path.Contains("/parameters", StringComparison.Ordinal),
            "voice.set" => path.Contains("/voices", StringComparison.Ordinal) || path.Contains("/langIDs", StringComparison.Ordinal),
            _ => false
        };
        try
        {
            if (!session.Sequence.Save(dir, false) || session.Sequence.IsStaged != staged)
                throw new InvalidDataException("Native staged array snapshot failed.");
            var json = ArchiveObject(JsonNode.Parse(File.ReadAllText(Path.Combine(dir, "Project", "sequence.json"))), "");
            state.Root = (JsonObject)state.Root.DeepClone(); state.Master = (JsonObject)state.Master.DeepClone();
            ReconcileNested(json, state.Root, false, AllowRemoval);
            ReconcileNested(ArchiveObject(json["masterTrack"], "master"), state.Master, false, AllowRemoval);
            void Update(object owner, JsonObject node)
            {
                var key = ArchiveKey(owner);
                if (!state.Live.TryGetValue(key, out var entry) || !Has(entry.Extra)) return;
                JsonObject extra = (JsonObject)entry.Extra.DeepClone();
                ReconcileNested(node, extra, false, AllowRemoval);
                state.Live[key] = entry with { Extra = extra };
            }
            var tracks = ArchiveArray(json["tracks"], "tracks");
            for (int ti = 0; ti < tracks.Count; ti++)
            {
                var track = session.Sequence.GetTrack((ulong)ti)!; var node = ArchiveObject(tracks[ti], "track"); Update(track, node);
                var parts = ArchiveArray(node["parts"], "parts");
                for (int pi = 0; pi < parts.Count; pi++)
                {
                    var part = track.GetPart((ulong)pi)!; var pj = ArchiveObject(parts[pi], "part"); Update(part, pj);
                    if (part is not WIVSMMidiPart midi) continue;
                    var notes = ArchiveArray(pj["notes"], "notes");
                    for (int ni = 0; ni < notes.Count; ni++) Update(midi.GetNote((ulong)ni)!, ArchiveObject(notes[ni], "note"));
                }
            }
        }
        finally { session.Sequence.IsModifiedOutsideOfEditHistory = modified; PathGuard.TreeNoLinks(dir); Directory.Delete(dir, true); }
    }
}
