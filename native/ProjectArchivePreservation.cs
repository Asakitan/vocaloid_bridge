using System.IO;
using System.IO.Compression;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Yamaha.VOCALOID.VSM;

internal sealed partial class EngineHost
{
    private readonly record struct ArchiveEntity(string Kind, nint Pointer);
    private sealed record ArchiveEntry(JsonObject Extra, ArchiveEntity? Parent);

    private sealed class ArchiveState
    {
        internal required EngineSession Session;
        internal required WIVSMUpdateObserver Observer;
        internal required UpdateObserverNotifyEventHandler Handler;
        internal JsonObject Root = new();
        internal JsonObject Master = new();
        internal Dictionary<ArchiveEntity, ArchiveEntry> Live = [];
        internal readonly Stack<Dictionary<ArchiveEntity, ArchiveEntry>> Undo = new();
        internal readonly Stack<Dictionary<ArchiveEntity, ArchiveEntry>> Redo = new();
        internal Dictionary<ArchiveEntity, ArchiveEntry>? Before;
        internal string? Action;
        internal readonly List<string> ExtraFiles = [];
        internal string? Invalid;
        internal bool HasEntityExtensions;
        internal bool ObserverAttached;
        internal bool PreUpgradeEmptyHistory;
    }

    private readonly Dictionary<string, ArchiveState> archiveStates = new(StringComparer.Ordinal);
    // Identity-free history states are represented by this unique sentinel,
    // never by a dictionary that happens to contain zero entities.
    private static readonly Dictionary<ArchiveEntity, ArchiveEntry> EmptyHistoryMarker = new();
    private static JsonObject? archiveSchema;

    private static JsonObject ArchiveSchema()
    {
        if (archiveSchema is not null)
            return archiveSchema;
        string install = Path.GetDirectoryName(typeof(WVSMModuleIF).Assembly.Location)!;
        byte[] binary = File.ReadAllBytes(Path.Combine(install, "VSM.dll"));
        byte[] prefix = Encoding.Unicode.GetBytes("{\"$schema\":\"http://json-schema.org/draft-04/schema\"");
        int start = binary.AsSpan().IndexOf(prefix);
        if (start < 0)
            throw new InvalidDataException("project_preservation: native VPR schema was not found.");
        int end = start;
        while (end + 1 < binary.Length && (binary[end] != 0 || binary[end + 1] != 0)) end += 2;
        if (end + 1 >= binary.Length || end - start > 2 * 1024 * 1024)
            throw new InvalidDataException("project_preservation: invalid native schema bounds.");
        archiveSchema = JsonNode.Parse(Encoding.Unicode.GetString(binary, start, end - start)) as JsonObject
            ?? throw new InvalidDataException("project_preservation: native VPR schema is invalid.");
        return archiveSchema;
    }

    private static JsonObject ArchiveResolveSchema(JsonObject schema, JsonObject root)
    {
        string? path = schema["$ref"]?.GetValue<string>();
        if (path is null)
            return schema;
        if (!path.StartsWith("#/", StringComparison.Ordinal))
            throw new InvalidDataException("project_preservation: unsupported schema reference.");
        JsonNode? node = root;
        foreach (string segment in path[2..].Split('/'))
            node = node?[segment.Replace("~1", "/", StringComparison.Ordinal).Replace("~0", "~", StringComparison.Ordinal)];
        return node as JsonObject ?? throw new InvalidDataException("project_preservation: unresolved native schema reference.");
    }

    private static JsonObject ArchiveUnknownFields(JsonObject value, JsonObject schema, string path)
    {
        JsonObject result = new();
        void Collect(JsonObject current, JsonObject currentSchema, string pointer)
        {
            JsonObject properties = ArchiveResolveSchema(currentSchema, ArchiveSchema())["properties"] as JsonObject
                ?? throw new InvalidDataException("project_preservation: missing object schema at " + path + pointer);
            foreach ((string key, JsonNode? item) in current)
            {
                string escaped = key.Replace("~", "~0", StringComparison.Ordinal).Replace("/", "~1", StringComparison.Ordinal);
                string childPointer = pointer + "/" + escaped;
                if (properties[key] is not JsonObject childSchema)
                    result.Add(childPointer, item?.DeepClone());
                else if (item is JsonObject child && !(path == "" && pointer == "" && key == "masterTrack"))
                    Collect(child, childSchema, childPointer);
            }
        }
        Collect(value, schema, "");
        return result;
    }

    private static JsonObject ArchiveObject(JsonNode? node, string path) => node as JsonObject
        ?? throw new InvalidDataException("project_preservation: expected object at " + path);

    private static JsonArray ArchiveArray(JsonNode? node, string path) => node is null ? new JsonArray() : node as JsonArray
        ?? throw new InvalidDataException("project_preservation: expected array at " + path);

    private static JsonObject ArchivePropertySchema(JsonObject schema, string name)
    {
        JsonObject resolved = ArchiveResolveSchema(schema, ArchiveSchema());
        return resolved["properties"]?[name] as JsonObject
            ?? throw new InvalidDataException("project_preservation: missing native schema property " + name);
    }

    private static JsonObject ArchiveItemSchema(JsonObject schema)
    {
        JsonObject resolved = ArchiveResolveSchema(schema, ArchiveSchema());
        return resolved["items"] as JsonObject
            ?? throw new InvalidDataException("project_preservation: missing native array schema.");
    }

    // Reject extensions outside the currently supported object owners rather than
    // silently copying stale structures or losing fields. The installed schema's
    // langIDs array omits items; its only declared member is handled explicitly.
    private static void ArchiveValidateNested(JsonNode? node, JsonObject schema, string path,
        bool owner = false)
    {
        if (node is null) return;
        JsonObject resolved = ArchiveResolveSchema(schema, ArchiveSchema());
        if (node is JsonObject value)
        {
            JsonObject properties = resolved["properties"] as JsonObject
                ?? throw new InvalidDataException("project_preservation: no native object schema at " + path);
            foreach ((string key, JsonNode? child) in value)
            {
                if (properties[key] is not JsonObject childSchema)
                {
                    if (!owner) throw new InvalidDataException("project_preservation: unsupported nested unknown field at " + path + "/" + key);
                    continue;
                }
                // These owners are visited separately and bound to native identities.
                if ((path == "" && (key == "masterTrack" || key == "tracks")) ||
                    (path == "/tracks[]" && key == "parts") ||
                    (path == "/tracks[]/parts[]" && key == "notes")) continue;
                ArchiveValidateNested(child, childSchema, path + "/" + key, owner && child is JsonObject);
            }
        }
        else if (node is JsonArray array)
        {
            if (resolved["items"] is JsonObject items)
                foreach (JsonNode? child in array) ArchiveValidateNested(child, items, path + "[]");
            else if (path.EndsWith("/langIDs", StringComparison.Ordinal) && resolved["langID"] is JsonObject)
            {
                foreach (JsonNode? child in array)
                {
                    JsonObject lang = ArchiveObject(child, path);
                    if (lang.Any(pair => pair.Key != "langID"))
                        throw new InvalidDataException("project_preservation: unsupported language metadata at " + path);
                }
            }
            else if (array.Count != 0 && array.Any(child => child is JsonObject or JsonArray))
                throw new InvalidDataException("project_preservation: native schema does not describe array items at " + path);
        }
    }

    private static ArchiveEntity ArchiveKey(object value) => value switch
    {
        WIVSMNote note => new("note", note.CppObjPtr),
        WIVSMTrack track => new("track", (nint)track),
        WIVSMPart part => new("part", (nint)part),
        _ => default
    };

    private static void ArchiveBind(ArchiveState state, object entity, JsonObject unknown, ArchiveEntity? parent)
    {
        ArchiveEntity key = ArchiveKey(entity);
        if (key.Pointer == nint.Zero || !state.Live.TryAdd(key, new ArchiveEntry(unknown, parent)))
            throw new InvalidDataException("project_preservation: duplicate or missing native identity.");
        state.HasEntityExtensions |= unknown.Count != 0;
    }

    private static string ArchiveString(JsonObject value, string key) => value[key]?.GetValue<string>() ?? "";

    private ArchiveState CreateArchiveState(EngineSession session)
    {
        WIVSMUpdateObserver observer = new();
        ArchiveState? state = null;
        UpdateObserverNotifyEventHandler handler = e =>
        {
            try
            {
                if (state is null) return;
                if (Environment.CurrentManagedThreadId != ownerThread) { state.Invalid = "observer callback left owner thread"; return; }
                if ((e.NotifyType is VSMNotifyType.DidRemove or VSMNotifyType.DidInsert) &&
                    state.Before is null && state.HasEntityExtensions)
                {
                    state.Invalid = "structural notification outside a tracked mutation";
                    return;
                }
                if (e.NotifyType != VSMNotifyType.DidRemove) return;
                foreach (object item in e.Objects)
                {
                    ArchiveEntity removed = ArchiveKey(item);
                    if (removed.Pointer == nint.Zero) continue;
                    HashSet<ArchiveEntity> dead = [removed];
                    bool changed;
                    do
                    {
                        changed = false;
                        foreach ((ArchiveEntity key, ArchiveEntry entry) in state.Live)
                            if (entry.Parent is ArchiveEntity parent && dead.Contains(parent) && dead.Add(key)) changed = true;
                    } while (changed);
                    foreach (ArchiveEntity key in dead) state.Live.Remove(key);
                }
            }
            catch (Exception error) { if (state is not null) state.Invalid = error.Message; }
        };
        state = new ArchiveState { Session = session, Observer = observer, Handler = handler };
        return state;
    }

    private void CaptureArchivePreservation(EngineSession session, string extractedRoot)
    {
        string jsonPath = Path.Combine(extractedRoot, "Project", "sequence.json");
        PathGuard.NoLinks(jsonPath);
        if (new FileInfo(jsonPath).Length > 128L * 1024 * 1024)
            throw new InvalidDataException("project_preservation: sequence JSON exceeds 128 MiB.");
        JsonObject root = ArchiveObject(JsonNode.Parse(File.ReadAllText(jsonPath)), "");
        JsonObject schema = ArchiveSchema();
        JsonObject master = ArchiveObject(root["masterTrack"], "/masterTrack");
        JsonObject masterSchema = ArchivePropertySchema(schema, "masterTrack");
        JsonObject trackSchema = ArchiveItemSchema(ArchivePropertySchema(schema, "tracks"));
        JsonObject partSchema = ArchiveItemSchema(ArchivePropertySchema(trackSchema, "parts"));
        JsonObject noteSchema = ArchiveItemSchema(ArchivePropertySchema(partSchema, "notes"));
        ArchiveState state = CreateArchiveState(session);
        WIVSMUpdateObserver observer = state.Observer;
        UpdateObserverNotifyEventHandler handler = state.Handler;
        bool registered = false;
        try
        {
            state.Root = ArchiveUnknownFields(root, schema, "");
            state.Master = ArchiveUnknownFields(master, masterSchema, "/masterTrack");
            ArchiveValidateNested(root, schema, "", true);
            ArchiveValidateNested(master, masterSchema, "/masterTrack", true);
            JsonArray tracks = ArchiveArray(root["tracks"], "/tracks");
            if ((ulong)tracks.Count != session.Sequence.NumTrack)
                throw new InvalidDataException("project_preservation: track count changed while loading.");
            for (int ti = 0; ti < tracks.Count; ti++)
            {
                JsonObject trackJson = ArchiveObject(tracks[ti], "/tracks[]");
                WIVSMTrack track = session.Sequence.GetTrack((ulong)ti) ?? throw new InvalidDataException("project_preservation: missing track.");
                ArchiveValidateTrack(track, trackJson);
                ArchiveBind(state, track, ArchiveUnknownFields(trackJson, trackSchema, "/tracks[]"), null);
                ArchiveValidateNested(trackJson, trackSchema, "/tracks[]", true);
                JsonArray parts = ArchiveArray(trackJson["parts"], "/tracks[]/parts");
                if ((ulong)parts.Count != track.NumParts) throw new InvalidDataException("project_preservation: part count changed while loading.");
                for (int pi = 0; pi < parts.Count; pi++)
                {
                    JsonObject partJson = ArchiveObject(parts[pi], "/tracks[]/parts[]");
                    WIVSMPart part = track.GetPart((ulong)pi) ?? throw new InvalidDataException("project_preservation: missing part.");
                    ArchiveValidatePart(part, partJson);
                    ArchiveBind(state, part, ArchiveUnknownFields(partJson, partSchema, "/tracks[]/parts[]"), ArchiveKey(track));
                    ArchiveValidateNested(partJson, partSchema, "/tracks[]/parts[]", true);
                    JsonArray notes = ArchiveArray(partJson["notes"], "/tracks[]/parts[]/notes");
                    if (part is not WIVSMMidiPart midi)
                    {
                        if (notes.Count != 0) throw new InvalidDataException("project_preservation: notes on non-MIDI part.");
                        continue;
                    }
                    if ((ulong)notes.Count != midi.NumNotes) throw new InvalidDataException("project_preservation: note count changed while loading.");
                    for (int ni = 0; ni < notes.Count; ni++)
                    {
                        JsonObject noteJson = ArchiveObject(notes[ni], "/tracks[]/parts[]/notes[]");
                        WIVSMNote note = midi.GetNote((ulong)ni) ?? throw new InvalidDataException("project_preservation: missing note.");
                        ArchiveValidateNote(note, noteJson);
                        ArchiveBind(state, note, ArchiveUnknownFields(noteJson, noteSchema, "/tracks[]/parts[]/notes[]"), ArchiveKey(part));
                        ArchiveValidateNested(noteJson, noteSchema, "/tracks[]/parts[]/notes[]", true);
                    }
                }
            }
            if (state.HasEntityExtensions)
            {
                ArchiveValidateUnambiguous(tracks);
                for (int index = 0; index < tracks.Count; index++)
                    ArchiveValidateTrackDetails(session.Sequence.GetTrack((ulong)index)
                        ?? throw new InvalidDataException("project_preservation: missing track."),
                        ArchiveObject(tracks[index], "/tracks[]"));
            }
            // Referenced audio remains native-managed; opaque members that were
            // already unreferenced are retained as independent archive content.
            HashSet<string> audioNames = new(StringComparer.OrdinalIgnoreCase);
            foreach (JsonNode? track in tracks)
                foreach (JsonNode? part in ArchiveArray(track?["parts"], "parts"))
                    if (part?["wav"] is JsonObject wav)
                        foreach (string key in new[] { "name", "processedName" })
                            if (wav[key] is JsonValue name && name.TryGetValue(out string? n) && !string.IsNullOrEmpty(n)) audioNames.Add(n);
            foreach (string file in Directory.EnumerateFiles(extractedRoot, "*", SearchOption.AllDirectories))
            {
                PathGuard.NoLinks(file);
                string relative = Path.GetRelativePath(extractedRoot, file).Replace('\\', '/');
                if (relative.Equals("Project/sequence.json", StringComparison.OrdinalIgnoreCase) ||
                    relative.Equals(ProjectValidityEntry, StringComparison.OrdinalIgnoreCase)) continue;
                if (relative.StartsWith("Project/Audio/", StringComparison.OrdinalIgnoreCase))
                {
                    string audioName = relative["Project/Audio/".Length..];
                    if (!audioNames.Contains(audioName)) state.ExtraFiles.Add(relative);
                    continue;
                }
                state.ExtraFiles.Add(relative);
            }
            if (!state.HasEntityExtensions) state.Live.Clear();
            if (!state.HasEntityExtensions && state.Root.Count == 0 && state.Master.Count == 0 && state.ExtraFiles.Count == 0)
            {
                observer.Dispose();
                return;
            }
            if (state.HasEntityExtensions)
            {
                observer.Notified += handler;
                if (!session.Sequence.AddUpdateObserver(observer))
                    throw new InvalidOperationException("project_preservation: native observer registration failed.");
                registered = true;
                state.ObserverAttached = true;
            }
            archiveStates.Add(session.Id, state);
            if (state.HasEntityExtensions) session.ArchiveBegin = operation =>
            {
                RequireArchiveMutationSupported(session, operation);
                BeginArchiveMutation(session, operation);
            };
            if (state.HasEntityExtensions) session.ArchiveEnd = action => EndArchiveMutation(session, action);
            if (state.HasEntityExtensions) session.ArchiveCopy = (source, target) => ArchiveCopyDuplicate(session, source, target);
        }
        catch
        {
            if (registered) session.Sequence.RemoveUpdateObserver(observer);
            observer.Notified -= handler;
            observer.Dispose();
            throw;
        }
    }

    // Returns true only when this call enabled tracking. Existing native undo
    // history predating this upgrade contains no entity extension payloads.
    private bool EnsureArchiveEntityTracking(EngineSession session)
    {
        bool existed = archiveStates.TryGetValue(session.Id, out ArchiveState? existing);
        ArchiveState state = existing ?? CreateArchiveState(session);
        if (state.HasEntityExtensions) { ArchiveCheck(state); return false; }
        bool attached = false;
        try
        {
            ArchiveCheck(state);
            Dictionary<ArchiveEntity, ArchiveEntry> live = [];
            void Add(object entity, ArchiveEntity? parent)
            {
                ArchiveEntity key = ArchiveKey(entity);
                if (key.Pointer == nint.Zero || !live.TryAdd(key, new ArchiveEntry(new JsonObject(), parent)))
                    throw new InvalidDataException("project_preservation: duplicate or missing native identity during tracking upgrade.");
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
            state.Observer.Notified += state.Handler;
            if (!session.Sequence.AddUpdateObserver(state.Observer))
                throw new InvalidOperationException("project_preservation: native observer registration failed.");
            attached = true;
            if (!existed) archiveStates.Add(session.Id, state);
            state.Live = live;
            state.ObserverAttached = true;
            state.HasEntityExtensions = true;
            state.PreUpgradeEmptyHistory = true;
            session.ArchiveBegin = operation =>
            {
                RequireArchiveMutationSupported(session, operation);
                BeginArchiveMutation(session, operation);
            };
            session.ArchiveEnd = action => EndArchiveMutation(session, action);
            session.ArchiveCopy = (source, target) => ArchiveCopyDuplicate(session, source, target);
            return true;
        }
        catch
        {
            if (attached) session.Sequence.RemoveUpdateObserver(state.Observer);
            state.Observer.Notified -= state.Handler;
            if (!existed) { archiveStates.Remove(session.Id); state.Observer.Dispose(); }
            throw;
        }
    }

    // Only valid for an upgrade whose first attempted mutation rolled back or
    // did not commit. It restores the pre-upgrade preservation scope.
    private void DropArchiveEntityTracking(EngineSession session)
    {
        if (!archiveStates.TryGetValue(session.Id, out ArchiveState? state) || !state.HasEntityExtensions)
            throw new InvalidOperationException("project_preservation: no tracking upgrade to drop.");
        ArchiveCheck(state);
        if (state.Undo.Count != 0 || state.Redo.Count != 0 || state.Live.Values.Any(entry => entry.Extra.Count != 0))
            throw new InvalidOperationException("project_preservation: tracking upgrade already contains committed identity data.");
        session.Sequence.RemoveUpdateObserver(state.Observer);
        state.Observer.Notified -= state.Handler;
        state.ObserverAttached = false;
        state.HasEntityExtensions = false;
        state.PreUpgradeEmptyHistory = false;
        state.Live.Clear();
        session.ArchiveBegin = null; session.ArchiveEnd = null; session.ArchiveCopy = null;
        if (state.Root.Count == 0 && state.Master.Count == 0 && state.ExtraFiles.Count == 0)
        {
            archiveStates.Remove(session.Id);
            state.Observer.Dispose();
        }
    }

    private static void ArchiveValidateNote(WIVSMNote note, JsonObject json)
    {
        if (json["pos"]?.GetValue<long>() != note.RelPosTick.Value ||
            json["duration"]?.GetValue<long>() != note.DurationTick.Value ||
            json["number"]?.GetValue<int>() != note.NoteNumber ||
            ArchiveString(json, "lyric") != note.Lyric || ArchiveString(json, "phoneme") != note.Phonemes)
            throw new InvalidDataException("project_preservation: native note order or identity differs from serialized data.");
    }

    private static void ArchiveValidateTrack(WIVSMTrack track, JsonObject json)
    {
        if ((json["name"] is not null && ArchiveString(json, "name") != track.Name) ||
            json["type"]?.GetValue<int>() != (int)track.Type)
            throw new InvalidDataException("project_preservation: native track order or identity differs from serialized data.");
    }

    private static void ArchiveValidateTrackDetails(WIVSMTrack track, JsonObject json)
    {
        if ((json["color"] is not null && json["color"]!.GetValue<int>() != track.Color) ||
            (json["isMuted"] is not null && json["isMuted"]!.GetValue<bool>() != track.IsMute) ||
            (json["isSoloMode"] is not null && json["isSoloMode"]!.GetValue<bool>() != track.IsSolo) ||
            (json["busNo"] is not null && json["busNo"]!.GetValue<uint>() != track.GetBusNo()))
            throw new InvalidDataException("project_preservation: native track order or identity differs from serialized data.");
    }

    private static void ArchiveValidatePart(WIVSMPart part, JsonObject json)
    {
        if ((json["name"] is not null && ArchiveString(json, "name") != part.Name) ||
            (json["pos"] is not null && json["pos"]!.GetValue<long>() != part.AbsPosTick.Value) ||
            (json["duration"] is not null && json["duration"]!.GetValue<long>() != part.DurationTick.Value))
            throw new InvalidDataException("project_preservation: native part order or identity differs from serialized data.");
    }

    private static void ArchiveValidateUnambiguous(JsonArray tracks)
    {
        static string Key(JsonObject value, params string[] names) => string.Join("|", names.Select(name => value[name]?.ToJsonString() ?? "null"));
        Dictionary<string, JsonObject> trackKeys = new(StringComparer.Ordinal);
        foreach (JsonNode? trackNode in tracks)
        {
            JsonObject track = ArchiveObject(trackNode, "tracks[]");
            HashSet<string> partKeys = new(StringComparer.Ordinal);
            List<string> trackShape = [Key(track, "type", "name", "color", "isMuted", "isSoloMode", "busNo")];
            foreach (JsonNode? partNode in ArchiveArray(track["parts"], "parts"))
            {
                JsonObject part = ArchiveObject(partNode, "parts[]");
                if (!partKeys.Add(Key(part, "name", "pos", "duration")))
                    throw new InvalidDataException("project_preservation: ambiguous part identities in snapshot.");
                trackShape.Add(Key(part, "name", "pos", "duration"));
                if (part["wav"] is JsonObject wav) trackShape.Add(Key(wav, "name", "originalName", "processedName"));
                if (part["region"] is JsonObject region) trackShape.Add(Key(region, "begin", "end"));
                HashSet<string> noteKeys = new(StringComparer.Ordinal);
                foreach (JsonNode? noteNode in ArchiveArray(part["notes"], "notes"))
                {
                    JsonObject note = ArchiveObject(noteNode, "notes[]");
                    string noteKey = Key(note, "pos", "duration", "number", "lyric", "phoneme");
                    if (!noteKeys.Add(noteKey))
                        throw new InvalidDataException("project_preservation: ambiguous note identities in snapshot.");
                    trackShape.Add(noteKey);
                }
            }
            string signature = JsonSerializer.Serialize(trackShape);
            if (trackKeys.TryGetValue(signature, out JsonObject? previous))
            {
                if (!JsonNode.DeepEquals(previous, track))
                    throw new InvalidDataException("project_preservation: indistinguishable track identities carry different data.");
            }
            else trackKeys.Add(signature, track);
        }
    }

    private bool HasArchiveEntityExtensions(EngineSession session) =>
        archiveStates.TryGetValue(session.Id, out ArchiveState? state) && state.HasEntityExtensions;

    private readonly record struct ArchiveNoteSignature(long Position, long Duration, int Number, int Velocity,
        string Lyric, string Phonemes, int Language, bool Valid);
    private readonly record struct ArchivePartSignature(long Position, long Duration, string Name);
    private sealed record ArchivePartSnapshot(ArchiveEntity Key, ArchiveEntity Parent,
        (ArchiveEntity Key, ArchiveNoteSignature Signature)[] Notes);

    private static ArchivePartSnapshot ArchiveSnapshotPart(WIVSMMidiPart part)
    {
        WIVSMMidiTrack parent = part.Parent ?? throw new InvalidDataException("project_preservation: part has no parent.");
        long offset = part.AbsPosTick.Value;
        return new(ArchiveKey(part), ArchiveKey(parent), part.Notes.Select(note =>
            (ArchiveKey(note), ArchiveNoteKey(note) with { Position = checked(offset + note.RelPosTick.Value) })).ToArray());
    }

    private void ArchiveMigrateParts(EngineSession session, ArchivePartSnapshot[] sources, WIVSMMidiPart[] targets, bool split)
    {
        if (!archiveStates.TryGetValue(session.Id, out ArchiveState? state) || !state.HasEntityExtensions) return;
        if (state.Before is null || state.Action != (split ? "part.split" : "part.join"))
            throw new InvalidOperationException("project_preservation: part migration outside its tracked transaction.");
        JsonObject merged = new();
        foreach (ArchivePartSnapshot source in sources)
            if (state.Before.TryGetValue(source.Key, out ArchiveEntry? entry))
                foreach ((string key, JsonNode? value) in entry.Extra)
                {
                    if (merged.ContainsKey(key))
                    {
                        if (!JsonNode.DeepEquals(merged[key], value))
                            throw new InvalidDataException("project_preservation: conflicting part join metadata at " + key);
                    }
                    else merged.Add(key, value?.DeepClone());
                }
        var original = sources.SelectMany(source => source.Notes).ToArray();
        var result = targets.SelectMany(part => part.Notes.Select(note =>
            (Key: ArchiveKey(note), Parent: ArchiveKey(part), Signature: ArchiveNoteKey(note) with
                { Position = checked(part.AbsPosTick.Value + note.RelPosTick.Value) }))).ToArray();
        var sourceIdentities = sources.Select(source => source.Key)
            .Concat(original.Select(note => note.Key)).ToArray();
        var sourceKeys = sourceIdentities.ToHashSet();
        var targetKeys = targets.Select(ArchiveKey).Concat(result.Select(note => note.Key)).ToArray();
        if (sourceIdentities.Any(key => key.Pointer == nint.Zero) || sourceKeys.Count != sourceIdentities.Length ||
            targetKeys.Any(key => key.Pointer == nint.Zero) ||
            targetKeys.Distinct().Count() != targetKeys.Length ||
            targetKeys.Any(key => state.Live.ContainsKey(key) && !sourceKeys.Contains(key)))
            throw new InvalidDataException("project_preservation: part operation has conflicting native identities.");
        foreach (ArchivePartSnapshot source in sources)
        {
            if (state.Before.TryGetValue(source.Key, out ArchiveEntry? partEntry) && partEntry.Parent != source.Parent)
                throw new InvalidDataException("project_preservation: source part parent identity changed.");
            foreach (var note in source.Notes)
                if (state.Before.TryGetValue(note.Key, out ArchiveEntry? noteEntry) && noteEntry.Parent != source.Key)
                    throw new InvalidDataException("project_preservation: source note parent identity changed.");
        }
        if (original.Length != result.Length || original.Select(n => n.Signature).Distinct().Count() != original.Length ||
            result.Select(n => n.Signature).Distinct().Count() != result.Length)
            throw new InvalidDataException("project_preservation: part operation has ambiguous or changed note identities.");
        var lookup = result.ToDictionary(n => n.Signature);
        if (original.Any(note => !lookup.ContainsKey(note.Signature)))
            throw new InvalidDataException("project_preservation: part operation changed a note identity.");
        foreach (ArchivePartSnapshot source in sources)
        {
            state.Live.Remove(source.Key);
            foreach (var note in source.Notes) state.Live.Remove(note.Key);
        }
        foreach (WIVSMMidiPart target in targets)
        {
            WIVSMMidiTrack parent = target.Parent ?? throw new InvalidDataException("project_preservation: migrated part has no parent.");
            if (sources.Any(source => source.Parent != ArchiveKey(parent)))
                throw new InvalidDataException("project_preservation: part operation changed track identity.");
            state.Live[ArchiveKey(target)] = new ArchiveEntry((JsonObject)merged.DeepClone(), ArchiveKey(parent));
        }
        foreach (var note in original)
            if (state.Before.TryGetValue(note.Key, out ArchiveEntry? entry))
            {
                var destination = lookup[note.Signature];
                state.Live[destination.Key] = new ArchiveEntry((JsonObject)entry.Extra.DeepClone(), destination.Parent);
            }
    }

    private static ArchiveNoteSignature ArchiveNoteKey(WIVSMNote note) => new(note.RelPosTick.Value,
        note.DurationTick.Value, note.NoteNumber, note.NoteVelocity, note.Lyric, note.Phonemes,
        note.LangID, note.IsValidPhonemes);

    private static ArchivePartSignature ArchivePartKey(WIVSMPart part) =>
        new(part.AbsPosTick.Value, part.DurationTick.Value, part.Name);

    // Called inside the corresponding ScoreMutate action, after the native
    // duplicate returned its new object and before Commit(true). Children are
    // paired by unique native semantic signatures, not by collection indices.
    private void ArchiveCopyDuplicate(EngineSession session, object source, object target)
    {
        if (!archiveStates.TryGetValue(session.Id, out ArchiveState? state) || !state.HasEntityExtensions) return;
        if (state.Before is null || state.Action is not ("track.duplicate" or "part.duplicate" or "note.duplicate"))
            throw new InvalidOperationException("project_preservation: duplicate outside its tracked transaction.");
        List<(ArchiveEntity Source, ArchiveEntity Target, ArchiveEntity? Parent)> pending = [];
        void Add(object original, object copy, ArchiveEntity? parent)
        {
            ArchiveEntity from = ArchiveKey(original), to = ArchiveKey(copy);
            if (from.Pointer == nint.Zero || to.Pointer == nint.Zero || from == to || state.Live.ContainsKey(to) ||
                pending.Any(pair => pair.Target == to))
                throw new InvalidDataException("project_preservation: duplicate native identity is invalid or already tracked.");
            if (state.Live.ContainsKey(from)) pending.Add((from, to, parent));
        }
        void CopyNotes(WIVSMMidiPart original, WIVSMMidiPart copy)
        {
            WIVSMNote[] sourceNotes = original.Notes.ToArray(), targetNotes = copy.Notes.ToArray();
            if (sourceNotes.Length != targetNotes.Length)
                throw new InvalidDataException("project_preservation: duplicated part changed note count.");
            Dictionary<ArchiveNoteSignature, WIVSMNote> targets = [];
            foreach (WIVSMNote note in targetNotes)
                if (!targets.TryAdd(ArchiveNoteKey(note), note))
                    throw new InvalidDataException("project_preservation: duplicate has ambiguous note identities.");
            HashSet<ArchiveNoteSignature> used = [];
            foreach (WIVSMNote note in sourceNotes)
            {
                ArchiveNoteSignature key = ArchiveNoteKey(note);
                if (!used.Add(key) || !targets.TryGetValue(key, out WIVSMNote? copyNote))
                    throw new InvalidDataException("project_preservation: duplicated note correspondence is ambiguous or changed.");
                Add(note, copyNote ?? throw new InvalidDataException("project_preservation: duplicated note is missing."), ArchiveKey(copy));
            }
        }
        void CopyPart(WIVSMPart original, WIVSMPart copy, ArchiveEntity targetTrack)
        {
            if (original.Name != copy.Name || original.DurationTick.Value != copy.DurationTick.Value)
                throw new InvalidDataException("project_preservation: duplicated part identity fields changed.");
            Add(original, copy, targetTrack);
            if (original is WIVSMMidiPart midi && copy is WIVSMMidiPart targetMidi) CopyNotes(midi, targetMidi);
            else if ((original is WIVSMMidiPart) != (copy is WIVSMMidiPart))
                throw new InvalidDataException("project_preservation: duplicated part kind changed.");
        }
        if (source is WIVSMTrack track && target is WIVSMTrack copiedTrack && state.Action == "track.duplicate")
        {
            if (track.Type != copiedTrack.Type || track.NumParts != copiedTrack.NumParts)
                throw new InvalidDataException("project_preservation: duplicated track type or part count changed.");
            Add(track, copiedTrack, null);
            Dictionary<ArchivePartSignature, WIVSMPart> targets = [];
            foreach (WIVSMPart part in copiedTrack.Parts)
                if (!targets.TryAdd(ArchivePartKey(part), part))
                    throw new InvalidDataException("project_preservation: duplicate has ambiguous part identities.");
            HashSet<ArchivePartSignature> used = [];
            foreach (WIVSMPart part in track.Parts)
            {
                ArchivePartSignature key = ArchivePartKey(part);
                if (!used.Add(key) || !targets.TryGetValue(key, out WIVSMPart? copiedPart))
                    throw new InvalidDataException("project_preservation: duplicated part correspondence is ambiguous or changed.");
                CopyPart(part, copiedPart ?? throw new InvalidDataException("project_preservation: duplicated part is missing."), ArchiveKey(copiedTrack));
            }
        }
        else if (source is WIVSMMidiPart part && target is WIVSMMidiPart copiedPart && state.Action == "part.duplicate")
        {
            WIVSMMidiTrack parent = copiedPart.Parent
                ?? throw new InvalidDataException("project_preservation: duplicated part has no parent.");
            CopyPart(part, copiedPart, ArchiveKey(parent));
        }
        else if (source is WIVSMNote note && target is WIVSMNote copiedNote && state.Action == "note.duplicate")
        {
            ArchiveNoteSignature original = ArchiveNoteKey(note), copy = ArchiveNoteKey(copiedNote);
            if (original with { Position = copy.Position } != copy)
                throw new InvalidDataException("project_preservation: duplicated note identity fields changed.");
            WIVSMMidiPart parent = copiedNote.Parent
                ?? throw new InvalidDataException("project_preservation: duplicated note has no parent.");
            Add(note, copiedNote, ArchiveKey(parent));
        }
        else throw new InvalidOperationException("project_preservation: duplicate kind does not match the native operation.");
        foreach ((ArchiveEntity from, ArchiveEntity to, ArchiveEntity? parent) in pending)
            state.Live.Add(to, new ArchiveEntry((JsonObject)state.Live[from].Extra.DeepClone(), parent));
    }

    // Copy the opaque payload while the native split is staged; the normal
    // transaction journal then records both the old and new identities.
    private void ArchiveCopySplitNote(EngineSession session, WIVSMNote source, WIVSMNote target)
    {
        if (!archiveStates.TryGetValue(session.Id, out ArchiveState? state) || !state.HasEntityExtensions) return;
        if (state.Before is null || state.Action != "note.split")
            throw new InvalidOperationException("project_preservation: note split outside its tracked transaction.");
        ArchiveEntity from = ArchiveKey(source), to = ArchiveKey(target);
        WIVSMMidiPart parent = target.Parent
            ?? throw new InvalidDataException("project_preservation: split note has no parent.");
        if (from.Pointer == nint.Zero || to.Pointer == nint.Zero || from == to || state.Live.ContainsKey(to))
            throw new InvalidDataException("project_preservation: invalid split note identity.");
        if (state.Before.TryGetValue(from, out ArchiveEntry? entry))
        {
            if (entry.Parent != ArchiveKey(parent) || !state.Live.ContainsKey(from))
                throw new InvalidDataException("project_preservation: split note identity changed.");
            state.Live.Add(to, new ArchiveEntry((JsonObject)entry.Extra.DeepClone(), ArchiveKey(parent)));
        }
    }

    private void ArchiveJoinNotes(EngineSession session, WIVSMMidiPart part, IReadOnlyList<ArchiveEntity> sources)
    {
        if (!archiveStates.TryGetValue(session.Id, out ArchiveState? state) || !state.HasEntityExtensions) return;
        if (state.Before is null || state.Action != "note.join")
            throw new InvalidOperationException("project_preservation: note join outside its tracked transaction.");
        JsonObject merged = new();
        foreach (ArchiveEntity source in sources)
        {
            if (!state.Before.TryGetValue(source, out ArchiveEntry? entry)) continue;
            if (entry.Parent != ArchiveKey(part))
                throw new InvalidDataException("project_preservation: note join source parent identity changed.");
            foreach ((string key, JsonNode? value) in entry.Extra)
            {
                if (merged.ContainsKey(key))
                {
                    if (!JsonNode.DeepEquals(merged[key], value))
                        throw new InvalidDataException("project_preservation: conflicting note join metadata at " + key);
                }
                else merged.Add(key, value?.DeepClone());
            }
        }
        HashSet<ArchiveEntity> sourceSet = sources.ToHashSet();
        ArchiveEntity[] surviving = part.Notes.Select(ArchiveKey).Where(sourceSet.Contains).ToArray();
        if (surviving.Length != 1)
            throw new InvalidDataException("project_preservation: note join survivor identity is ambiguous.");
        if (surviving[0].Pointer == nint.Zero ||
            (state.Live.TryGetValue(surviving[0], out ArchiveEntry? survivor) && survivor.Parent != ArchiveKey(part)))
            throw new InvalidDataException("project_preservation: note join survivor identity conflicts with another entity.");
        state.Live[surviving[0]] = new ArchiveEntry(merged, ArchiveKey(part));
    }

    internal void CheckArchiveRequest(EngineSession session, string method, JsonElement parameters)
    {
        if (!HasArchiveEntityExtensions(session)) return;
        if (method is "session" or "save" or "clone_project" or "close" or "revert_project" or "merge_project" or
            "members" or "get" or "enumerate" or "construct" or "set" or "call") return;
        if (method == "score_edit")
        {
            string operation = parameters.GetProperty("operation").GetString() ?? "";
            if (operation.EndsWith(".get", StringComparison.Ordinal) || operation.EndsWith(".list", StringComparison.Ordinal) ||
                operation is "controller.types" or "note.expression_bounds" or "time.convert" or "history.status" or "track.freeze_state") return;
            RequireArchiveMutationSupported(session, operation);
            return;
        }
        if (method == "audio_op")
        {
            string operation = parameters.GetProperty("operation").GetString() ?? "";
            if (operation is "devices" or "inspect_audio" or "export_audio" or "effects" or "transport_status" or "transport_release") return;
        }
        throw new InvalidOperationException("project_preservation: this operation requires a verified entity-identity transaction: " + method);
    }

    internal void CheckArchiveNativeMutation(EngineSession session, string operation)
    {
        if (HasArchiveEntityExtensions(session))
            throw new InvalidOperationException("project_preservation: raw native mutation has no tracked entity-identity transaction: " + operation);
    }

    internal void CheckArchiveExternalOperation(string? id, string domain, string operation)
    {
        if (id is null || !HasArchiveEntityExtensions(GetSession(id))) return;
        bool readOnly = domain == "clipboard"
            ? operation is "copy" or "cut" or "paste" or "list" or "clear"
            : operation is "languages" or "phoneme_table" or "lyrics_can_convert" or "lyrics_candidates" or
                "style_list" or "style_get" or "media_list" or "media_get" or "dvqm_catalog" or "dvqm_get" or
                "note_skill_get" or "singing_skill_catalog" or "singing_skill_get";
        if (!readOnly)
            throw new InvalidOperationException("project_preservation: this operation requires a verified entity-identity transaction: " + domain + "." + operation);
    }

    private void RequireArchiveMutationSupported(EngineSession session, string operation)
    {
        if (!HasArchiveEntityExtensions(session)) return;
        if (operation is not ("track.create" or "track.update" or "track.reorder" or "track.remove" or "track.duplicate" or
            "part.create" or "part.update" or "part.move" or "part.resize" or "part.remove" or "part.duplicate" or "part.split" or "part.join" or
            "note.update" or "note.remove" or "note.add" or "note.clear" or "note.batch_update" or "note.duplicate" or "note.split" or "note.join" or
            "voice.set" or "tempo.set" or "tempo.remove" or "time_signature.set" or "time_signature.remove" or
            "controller.set" or "controller.remove" or "automation.set" or "automation.remove" or "loop.set" or
            "tuning.set" or "vibrato.set" or "phoneme_timing.set" or "phoneme_timing.reset" or
            "pitch.set" or "pitch.clear" or "performance.set" or "selection.set" or "sequence.update" or
            "undo" or "redo" or "history.rollback" or "clipboard.paste" or "clipboard.cut" or "project.merge"))
            throw new InvalidOperationException("project_preservation: this mutation has no verified identity transaction: " + operation);
    }

    private void BeginArchiveMutation(EngineSession session, string action)
    {
        if (!archiveStates.TryGetValue(session.Id, out ArchiveState? state)) return;
        ArchiveCheck(state);
        if (state.Before is not null) throw new InvalidOperationException("project_preservation: nested mutation is unsupported.");
        bool oldEmptyUndo = action == "undo" && state.Undo.Count == 0 && state.PreUpgradeEmptyHistory &&
            state.Live.Values.All(entry => entry.Extra.Count == 0);
        if (state.HasEntityExtensions && ((action == "undo" && state.Undo.Count == 0 && !oldEmptyUndo) || (action == "redo" && state.Redo.Count == 0)))
            throw new InvalidOperationException("project_preservation: native history has no corresponding identity snapshot.");
        state.Before = new(state.Live);
        state.Action = action;
    }

    // action is commit, sync, undo, redo or rollback. Only an actual
    // Commit(true) advances history. A no-op/Commit(false) uses sync.
    private void EndArchiveMutation(EngineSession session, string action)
    {
        if (!archiveStates.TryGetValue(session.Id, out ArchiveState? state)) return;
        Dictionary<ArchiveEntity, ArchiveEntry> before = state.Before
            ?? throw new InvalidOperationException("project_preservation: mutation boundary was not started.");
        state.Before = null;
        Dictionary<ArchiveEntity, ArchiveEntry> HistorySnapshot(Dictionary<ArchiveEntity, ArchiveEntry> snapshot) =>
            state.PreUpgradeEmptyHistory && snapshot.Values.All(entry => entry.Extra.Count == 0) ? EmptyHistoryMarker : snapshot;
        bool rebindEmpty = false;
        switch (action)
        {
            case "commit": state.Undo.Push(HistorySnapshot(before)); state.Redo.Clear(); break;
            case "undo":
                if (state.Undo.Count == 0 && (!state.PreUpgradeEmptyHistory || before.Values.Any(entry => entry.Extra.Count != 0)))
                { state.Invalid = "untracked undo"; break; }
                state.Redo.Push(HistorySnapshot(before));
                state.Live = state.Undo.Count == 0 ? EmptyHistoryMarker : state.Undo.Pop();
                rebindEmpty = ReferenceEquals(state.Live, EmptyHistoryMarker); break;
            case "redo":
                if (state.Redo.Count == 0) { state.Invalid = "untracked redo"; break; }
                state.Undo.Push(HistorySnapshot(before)); state.Live = state.Redo.Pop();
                rebindEmpty = ReferenceEquals(state.Live, EmptyHistoryMarker); break;
            case "rollback": state.Live = before; break;
            case "sync":
                if (!before.Keys.ToHashSet().SetEquals(state.Live.Keys)) { state.Undo.Clear(); state.Redo.Clear(); state.PreUpgradeEmptyHistory = false; }
                break;
            default: state.Invalid = "unknown mutation boundary"; break;
        }
        bool preserveExisting = state.Action is "track.create" or "track.update" or "track.reorder" or "part.create" or
            "part.update" or "part.move" or "part.resize" or "note.update" or "note.batch_update" or "note.add" or
            "voice.set" or "tempo.set" or "tempo.remove" or "time_signature.set" or "time_signature.remove" or
            "controller.set" or "controller.remove" or "automation.set" or "automation.remove" or "loop.set" or
            "tuning.set" or "vibrato.set" or "phoneme_timing.set" or "phoneme_timing.reset" or
            "pitch.set" or "pitch.clear" or "performance.set" or "selection.set" or "sequence.update";
        if (rebindEmpty)
        {
            try { ArchiveRebindEmpty(state); }
            catch { state.Invalid = "empty-history identity rebinding failed"; throw; }
        }
        else ArchiveRefreshParents(state, preserveExisting ? before : null, action is "undo" or "redo");
        int limit = (int)Math.Min(state.Session.Sequence.GetMaxUndoCount(), 65536UL);
        if (state.Undo.Count > limit) state.PreUpgradeEmptyHistory = false;
        TrimArchiveHistory(state.Undo, limit);
        TrimArchiveHistory(state.Redo, limit);
        state.Action = null;
        ArchiveCheck(state);
    }

    private static void ArchiveRebindEmpty(ArchiveState state)
    {
        Dictionary<ArchiveEntity, ArchiveEntry> live = [];
        void Add(object value, ArchiveEntity? parent)
        {
            ArchiveEntity key = ArchiveKey(value);
            if (key.Pointer == nint.Zero || !live.TryAdd(key, new ArchiveEntry(new JsonObject(), parent)))
                throw new InvalidDataException("project_preservation: ambiguous empty-history native identity.");
        }
        foreach (WIVSMTrack track in state.Session.Sequence.Tracks)
        {
            ArchiveEntity trackKey = ArchiveKey(track); Add(track, null);
            foreach (WIVSMPart part in track.Parts)
            {
                ArchiveEntity partKey = ArchiveKey(part); Add(part, trackKey);
                if (part is WIVSMMidiPart midi)
                    foreach (WIVSMNote note in midi.Notes) Add(note, partKey);
            }
        }
        state.Live = live;
    }

    private static void TrimArchiveHistory(Stack<Dictionary<ArchiveEntity, ArchiveEntry>> history, int limit)
    {
        if (history.Count <= limit) return;
        var keep = history.Take(limit).Reverse().ToArray();
        history.Clear();
        foreach (var snapshot in keep) history.Push(snapshot);
    }

    private static void ArchiveRefreshParents(ArchiveState state, Dictionary<ArchiveEntity, ArchiveEntry>? preserve, bool strictParents = false)
    {
        HashSet<ArchiveEntity> seen = [];
        void Mark(object entity, ArchiveEntity? parent)
        {
            ArchiveEntity key = ArchiveKey(entity);
            if (!state.Live.ContainsKey(key) && preserve is not null && preserve.TryGetValue(key, out ArchiveEntry? previous))
                state.Live.Add(key, previous);
            if (state.Live.TryGetValue(key, out ArchiveEntry? entry))
            {
                if (strictParents && entry.Extra.Count != 0 && entry.Parent != parent)
                    state.Invalid = "history restored an extended entity under a different parent";
                state.Live[key] = entry with { Parent = parent };
                seen.Add(key);
            }
        }
        foreach (WIVSMTrack track in state.Session.Sequence.Tracks)
        {
            ArchiveEntity trackKey = ArchiveKey(track);
            Mark(track, null);
            foreach (WIVSMPart part in track.Parts)
            {
                ArchiveEntity partKey = ArchiveKey(part);
                Mark(part, trackKey);
                if (part is WIVSMMidiPart midi)
                    foreach (WIVSMNote note in midi.Notes) Mark(note, partKey);
            }
        }
        if (seen.Count != state.Live.Count)
            state.Invalid = "native object lifecycle diverged from tracked identities";
        if (preserve is not null && preserve.Any(pair => pair.Value.Extra.Count != 0 && !seen.Contains(pair.Key)))
            state.Invalid = "a non-destructive edit replaced an extended native entity";
    }

    private static void ArchiveCheck(ArchiveState state)
    {
        if (state.Invalid is not null)
            throw new InvalidOperationException("project_preservation: " + state.Invalid);
        if (state.Before is not null)
            throw new InvalidOperationException("project_preservation: mutation remains in progress.");
    }

    private void ApplyArchivePreservation(EngineSession session, string stageRoot)
    {
        if (!archiveStates.TryGetValue(session.Id, out ArchiveState? state)) return;
        ArchiveCheck(state);
        string path = Path.Combine(stageRoot, "Project", "sequence.json");
        PathGuard.NoLinks(path);
        if (new FileInfo(path).Length > 128L * 1024 * 1024)
            throw new InvalidDataException("project_preservation: snapshot JSON exceeds 128 MiB.");
        JsonObject root = ArchiveObject(JsonNode.Parse(File.ReadAllText(path)), "");
        JsonObject master = ArchiveObject(root["masterTrack"], "/masterTrack");
        ArchiveOverlay(root, state.Root); ArchiveOverlay(master, state.Master);
        JsonArray tracks = ArchiveArray(root["tracks"], "/tracks");
        if ((ulong)tracks.Count != session.Sequence.NumTrack) throw new InvalidDataException("project_preservation: snapshot track count changed.");
        if (state.HasEntityExtensions)
        {
        HashSet<ArchiveEntity> seen = [];
        void Overlay(object entity, JsonObject target)
        {
            ArchiveEntity key = ArchiveKey(entity);
            if (state.Live.TryGetValue(key, out ArchiveEntry? entry)) { ArchiveOverlay(target, entry.Extra); seen.Add(key); }
        }
        for (int ti = 0; ti < tracks.Count; ti++)
        {
            JsonObject trackJson = ArchiveObject(tracks[ti], "/tracks[]");
            WIVSMTrack track = session.Sequence.GetTrack((ulong)ti) ?? throw new InvalidDataException("project_preservation: missing snapshot track.");
            ArchiveValidateTrack(track, trackJson);
            ArchiveValidateTrackDetails(track, trackJson);
            Overlay(track, trackJson);
            JsonArray parts = ArchiveArray(trackJson["parts"], "parts");
            if ((ulong)parts.Count != track.NumParts) throw new InvalidDataException("project_preservation: snapshot part count changed.");
            for (int pi = 0; pi < parts.Count; pi++)
            {
                JsonObject partJson = ArchiveObject(parts[pi], "parts[]");
                WIVSMPart part = track.GetPart((ulong)pi) ?? throw new InvalidDataException("project_preservation: missing snapshot part.");
                ArchiveValidatePart(part, partJson);
                Overlay(part, partJson);
                if (part is not WIVSMMidiPart midi) continue;
                JsonArray notes = ArchiveArray(partJson["notes"], "notes");
                if ((ulong)notes.Count != midi.NumNotes) throw new InvalidDataException("project_preservation: snapshot note count changed.");
                for (int ni = 0; ni < notes.Count; ni++)
                {
                    JsonObject noteJson = ArchiveObject(notes[ni], "notes[]");
                    WIVSMNote note = midi.GetNote((ulong)ni) ?? throw new InvalidDataException("project_preservation: missing snapshot note.");
                    ArchiveValidateNote(note, noteJson); Overlay(note, noteJson);
                }
            }
        }
        if (seen.Count != state.Live.Count)
            throw new InvalidDataException("project_preservation: tracked object is no longer present; refusing ambiguous attachment.");
        ArchiveValidateUnambiguous(tracks);
        }
        File.WriteAllText(path, root.ToJsonString());
        foreach (string relative in state.ExtraFiles)
        {
            string source = PathGuard.Under(session.Directory, relative);
            string target = PathGuard.Under(stageRoot, relative);
            PathGuard.NoLinks(source); PathGuard.CreateDirectory(Path.GetDirectoryName(target)!);
            if (File.Exists(target)) throw new IOException("project_preservation: native output collides with retained member: " + relative);
            File.Copy(source, target, false);
        }
    }

    private static void ArchiveOverlay(JsonObject target, JsonObject extra)
    {
        foreach ((string pointer, JsonNode? value) in extra)
        {
            string[] segments = pointer[1..].Split('/').Select(segment => segment
                .Replace("~1", "/", StringComparison.Ordinal).Replace("~0", "~", StringComparison.Ordinal)).ToArray();
            JsonObject parent = target;
            for (int index = 0; index < segments.Length - 1; index++)
                parent = parent[segments[index]] as JsonObject
                    ?? throw new InvalidDataException("project_preservation: retained field parent is absent: " + pointer);
            string key = segments[^1];
            if (parent.ContainsKey(key)) throw new InvalidDataException("project_preservation: retained field conflicts with native output: " + pointer);
            parent.Add(key, value?.DeepClone());
        }
    }

    private void AddOuterArchiveMembers(EngineSession session, string stageRoot, string archivePath)
    {
        if (!archiveStates.TryGetValue(session.Id, out ArchiveState? state)) return;
        using ZipArchive archive = ZipFile.Open(archivePath, ZipArchiveMode.Update);
        HashSet<string> names = new(archive.Entries.Select(entry => entry.FullName.TrimEnd('/')), StringComparer.OrdinalIgnoreCase);
        foreach (string relative in state.ExtraFiles.Where(name => !name.StartsWith("Project/", StringComparison.OrdinalIgnoreCase)))
        {
            if (!names.Add(relative.TrimEnd('/')))
                throw new IOException("project_preservation: archive member collides case-insensitively: " + relative);
            string path = PathGuard.Under(stageRoot, relative);
            PathGuard.NoLinks(path);
            using Stream input = File.OpenRead(path);
            using Stream output = archive.CreateEntry(relative, CompressionLevel.Optimal).Open();
            input.CopyTo(output);
        }
    }

    private void ReleaseArchivePreservation(EngineSession session)
    {
        if (!archiveStates.Remove(session.Id, out ArchiveState? state)) return;
        session.ArchiveBegin = null;
        session.ArchiveEnd = null;
        session.ArchiveCopy = null;
        if (state.ObserverAttached)
        {
            session.Sequence.RemoveUpdateObserver(state.Observer);
            state.Observer.Notified -= state.Handler;
        }
        state.Observer.Dispose();
    }
}
