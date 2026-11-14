using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using Yamaha.VOCALOID.VSM;
#if !VOCALOID7
using Yamaha.VOCALOID.VMM;
#endif

internal sealed partial class EngineHost
{
    private const string BridgeAiDvqmPointer = "/vocaloid_bridge_ai_dvqm_v1";

    private static bool BridgeDvqmRequested(JsonElement options) =>
        LibraryText(options, "storage", "native") == "bridge_metadata";

    private JsonObject? BridgeDvqmRoot(EngineSession session, WIVSMNote note)
    {
        if (!archiveStates.TryGetValue(session.Id, out ArchiveState? state))
            return null;
        if (state.Invalid is not null)
            throw new InvalidOperationException("project_preservation: " + state.Invalid);
        if (!state.Live.TryGetValue(ArchiveKey(note), out ArchiveEntry? entry))
        {
            if (state.HasEntityExtensions)
                throw new InvalidDataException("AI DVQM bridge note identity is not tracked.");
            return null;
        }
        if (!entry.Extra.TryGetPropertyValue(BridgeAiDvqmPointer, out JsonNode? value))
            return null;
        if (value is not JsonObject root || root["version"]?.GetValue<int>() != 1)
            throw new InvalidDataException("AI DVQM bridge metadata has an invalid version or structure.");
        return root;
    }

    private LibraryDvqmMetadata? BridgeDvqmSelection(EngineSession session, WIVSMNote note, bool isAttack)
    {
        JsonObject? root = BridgeDvqmRoot(session, note);
        string name = isAttack ? "attack" : "release";
        if (root is null || !root.TryGetPropertyValue(name, out JsonNode? node))
            return null;
        if (node is not JsonObject selection)
            throw new InvalidDataException("AI DVQM bridge selection is not an object.");
        LibraryDvqmMetadata metadata = selection.Deserialize<LibraryDvqmMetadata>()
            ?? throw new InvalidDataException("AI DVQM bridge selection is empty.");
        if (string.IsNullOrEmpty(metadata.ComponentId) || metadata.LevelNames is null ||
            metadata.LevelNames.Count == 0 || metadata.LevelNames.Any(string.IsNullOrEmpty) || !float.IsFinite(metadata.TopFactor))
            throw new InvalidDataException("AI DVQM bridge selection has invalid component, levels or factor.");
        return metadata;
    }

    private object BridgeDvqmView(EngineSession session, WIVSMMidiPart part, WIVSMNote note, bool isAttack)
    {
        if (!part.IsAi)
            throw new ArgumentException("bridge_metadata storage requires an AI note.");
        LibraryDvqmMetadata? metadata = BridgeDvqmSelection(session, note, isAttack);
        int databaseId = -1, nameId = -1;
        if (metadata is not null)
        {
            var manager = EnsureDatabase();
            var database = LibraryValues(manager.NumDvqmDBs, manager.GetDvqmDBByIndex)
                .FirstOrDefault(value => value is not null && value.CompID == metadata.ComponentId)
                ?? throw new InvalidOperationException("The AI DVQM bridge database is not installed: " + metadata.ComponentId);
            var property = LibraryValues(database.NumDvqmProperties(isAttack), index => database.GetDvqmPropertyByIndex(isAttack, index))
                .FirstOrDefault(value => value is not null && value.LevelNames.SequenceEqual(metadata.LevelNames))
                ?? throw new InvalidOperationException("The AI DVQM bridge level names are not installed.");
            databaseId = database.ID;
            nameId = property.ID;
        }
        return new
        {
            is_attack = isAttack, is_empty = metadata is null, db_id = databaseId, name_id = nameId,
            component_id = metadata?.ComponentId, level_names = metadata?.LevelNames ?? [],
            speed = metadata?.Speed ?? 50, top_factor = metadata?.TopFactor ?? 1f,
            is_protected = metadata?.IsProtected ?? false, applies_to = "Midi",
            applicable_to_current_part = false, storage = "bridge_metadata"
        };
    }

    private object BridgeDvqmEdit(EngineSession session, string operation, JsonElement options, bool preflight = true)
    {
        bool isAttack = LibraryBool(options, "is_attack", true);
        WIVSMMidiPart part = LibraryMidiPart(session, options);
        WIVSMNote note = LibraryNote(part, options);
        if (!part.IsAi)
            throw new ArgumentException("bridge_metadata storage requires an AI note.");
        LibraryDvqmMetadata? current = BridgeDvqmSelection(session, note, isAttack);
        JsonObject? currentRoot = BridgeDvqmRoot(session, note);
        string selectionName = isAttack ? "attack" : "release";
        if (currentRoot?[selectionName] is JsonObject existing && existing.Any(field => field.Key is not
            ("ComponentId" or "LevelNames" or "Speed" or "TopFactor" or "IsProtected")))
            throw new InvalidOperationException("AI DVQM bridge selection has unknown fields; mutation is not supported.");
        LibraryDvqmMetadata? desired = null;
        if (operation == "dvqm_set")
        {
            int databaseId = ScoreInt(options, "db_id", 0, int.MaxValue);
            int nameId = ScoreInt(options, "name_id", 0, int.MaxValue);
            var database = EnsureDatabase().GetDvqmDBByID(databaseId)
                ?? throw new ArgumentException("The requested native Attack/Release database is not installed.");
            var property = database.GetDvqmPropertyByID(isAttack, nameId)
                ?? throw new ArgumentException("The requested native Attack/Release name is not installed.");
            WIVSMDvqm native = note.GetDvqm(isAttack)
                ?? throw new NotSupportedException("The native note has no Attack/Release record.");
            desired = new LibraryDvqmMetadata
            {
                ComponentId = database.CompID, LevelNames = property.LevelNames.ToList(),
                Speed = options.TryGetProperty("speed", out _) ? ScoreInt(options, "speed", int.MinValue, int.MaxValue) : current?.Speed ?? native.Speed,
                TopFactor = options.TryGetProperty("top_factor", out _) ? ScoreFloat(options, "top_factor", float.MinValue, float.MaxValue) : current?.TopFactor ?? native.TopFactor,
                IsProtected = options.TryGetProperty("is_protected", out _) ? LibraryBool(options, "is_protected") : current?.IsProtected ?? native.IsProtect
            };
            if (desired.ComponentId.Length == 0 || desired.LevelNames.Count == 0 || desired.LevelNames.Any(string.IsNullOrEmpty))
                throw new InvalidDataException("The native Attack/Release selection has incomplete component or level names.");
        }
        JsonNode? currentNode = current is null ? null : JsonSerializer.SerializeToNode(current);
        JsonNode? desiredNode = desired is null ? null : JsonSerializer.SerializeToNode(desired);
        if (JsonNode.DeepEquals(currentNode, desiredNode))
            return BridgeDvqmView(session, part, note, isAttack);
        if (preflight)
        {
            ScoreRequireUnstaged(session.Sequence);
            EngineSession candidate = CloneProject(session.Id, null);
            try
            {
                BridgeDvqmEdit(candidate, operation, options, false);
                string stage = Path.Combine(candidate.Directory, "dvqm-preflight-" + Guid.NewGuid().ToString("N"));
                PathGuard.CreateDirectory(stage);
                if (!candidate.Sequence.Save(stage, false))
                    throw new InvalidOperationException("Native AI DVQM metadata preflight snapshot failed: " + candidate.Sequence.LastError);
                ValidateNativeSnapshot(candidate.Sequence, Path.Combine(stage, "Project", "sequence.json"));
                ApplyArchivePreservation(candidate, stage);
            }
            finally { Close(candidate.Id, true); }
        }
        bool upgraded = EnsureArchiveEntityTracking(session);
        try
        {
            return ScoreMutate(session, "dvqm_metadata", () =>
            {
                ArchiveState state = archiveStates[session.Id];
                ArchiveEntity key = ArchiveKey(note);
                if (state.Before is null || !state.Live.TryGetValue(key, out ArchiveEntry? entry))
                    throw new InvalidOperationException("AI DVQM bridge metadata has no tracked note identity.");
                JsonObject extra = (JsonObject)entry.Extra.DeepClone();
                JsonObject root = currentRoot is null ? new JsonObject { ["version"] = 1 } : (JsonObject)currentRoot.DeepClone();
                if (desiredNode is null)
                    root.Remove(selectionName);
                else
                    root[selectionName] = desiredNode.DeepClone();
                if (root.Count == 1)
                    extra.Remove(BridgeAiDvqmPointer);
                else
                    extra[BridgeAiDvqmPointer] = root;
                StageArchiveMetadataHistory(session.Sequence);
                state.Live[key] = entry with { Extra = extra };
                return true;
            }, () => BridgeDvqmView(session, part, note, isAttack));
        }
        catch
        {
            if (upgraded) DropArchiveEntityTracking(session);
            throw;
        }
    }

    private bool IsBridgeDvqmEdit(string? id, string operation, JsonElement options)
    {
        if (id is null || operation is not ("dvqm_set" or "dvqm_clear") || !BridgeDvqmRequested(options))
            return false;
        return LibraryMidiPart(LibrarySession(id), options).IsAi;
    }

    private bool IsEmptyDvqmClear(string? id, string operation, JsonElement options)
    {
        if (id is null || operation != "dvqm_clear") return false;
        EngineSession session = LibrarySession(id);
        WIVSMMidiPart part = LibraryMidiPart(session, options);
        WIVSMNote note = LibraryNote(part, options);
        if (BridgeDvqmRequested(options))
            return part.IsAi && BridgeDvqmSelection(session, note, LibraryBool(options, "is_attack", true)) is null;
        return note.GetDvqm(LibraryBool(options, "is_attack", true)) is { IsEmpty: true };
    }

#if VOCALOID7
    internal bool IsPreservedMidiMediaImport(string? id, string operation, JsonElement options) => false;

    internal bool IsIndependentArchiveLibraryOperation(string? id, string operation, JsonElement options) =>
        operation is "style_update" or "style_delete" || IsEmptyDvqmClear(id, operation, options) || IsBridgeDvqmEdit(id, operation, options);
#else
    // These operations read the sequence or change only bridge-owned library
    // files. Controller extensions remain guarded; MIDI part and note payloads
    // are carried by bridge-owned clip metadata.
    internal bool IsPreservedMidiMediaImport(string? id, string operation, JsonElement options)
    {
        if (operation != "media_import" || id is null) return false;
        EngineSession session = LibrarySession(id);
        if (!HasArchiveEntityExtensions(session)) return false;
        Clip clip = LibraryClip(LibraryText(options, "clip_id"));
        LibraryRequire(clip.ReadPart(), "read media before preservation guard");
        return true;
    }

    internal bool IsIndependentArchiveLibraryOperation(string? id, string operation, JsonElement options)
    {
        if (operation is "style_update" or "style_delete" or "media_update" or "media_delete" or "media_recovery_list" or "media_recovery_resolve")
            return true;
        if (IsEmptyDvqmClear(id, operation, options)) return true;
        if (IsBridgeDvqmEdit(id, operation, options)) return true;
        if (operation != "media_capture") return false;
        EngineSession session = LibrarySession(id);
        if (!archiveStates.TryGetValue(session.Id, out ArchiveState? state) || !state.HasEntityExtensions)
            return true;
        ArchiveCheck(state);
        WIVSMTrack track = session.Sequence.GetTrack(LibraryIndex(options, "track_index"))
            ?? throw new ArgumentException("track_index was not found.");
        WIVSMPart part = track.GetPart(LibraryIndex(options, "part_index"))
            ?? throw new ArgumentException("part_index was not found.");
        if (!state.Live.TryGetValue(ArchiveKey(part), out ArchiveEntry? partEntry))
            throw new InvalidDataException("project_preservation: selected media part identity is not tracked.");
        return true;
    }
#endif
}

