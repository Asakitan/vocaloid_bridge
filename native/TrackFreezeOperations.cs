using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using Yamaha.VOCALOID.VSM;

internal sealed partial class EngineHost
{
    private sealed record FrozenEffect(string Id, bool Bypassed);
    private sealed record FrozenAuthoringState(int TrackIndex, FrozenEffect[] TrackEffects, FrozenEffect[][] PartEffects, string OwnedWavePath);
    private readonly Dictionary<string, Dictionary<int, FrozenAuthoringState>> frozenAuthoring = new(StringComparer.Ordinal);

    private static FrozenEffect[] CaptureFrozenEffects(WIVSMEffectManager? manager)
        => manager is null ? [] : manager.AudioEffects.Select(effect => new FrozenEffect(effect.Id, effect.IsBypassed)).ToArray();

    private static FrozenAuthoringState CaptureFrozenAuthoring(WIVSMMidiTrack track, int index)
        => new(index, CaptureFrozenEffects(track.EffectManager),
#if VOCALOID7
            track.Parts.Select(part => Array.Empty<FrozenEffect>()).ToArray(), "");
#else
            track.Parts.Select(part => CaptureFrozenEffects(part.EffectManager)).ToArray(), "");
#endif

    private void ForgetFrozenAuthoring(EngineSession session) => frozenAuthoring.Remove(session.Id);

    private bool HasFrozenAuthoring(EngineSession session)
        => frozenAuthoring.TryGetValue(session.Id, out var states) && states.Count != 0;

    internal void CheckFrozenRequest(EngineSession session, string method, JsonElement parameters)
    {
        if (!HasFrozenAuthoring(session)) return;
        if (method is "session" or "save" or "clone_project" or "close" or "revert_project" or
            "members" or "get" or "enumerate" or "construct" or "set" or "call" or "render_part") return;
        if (method == "score_edit")
        {
            string operation = parameters.GetProperty("operation").GetString() ?? "";
            if (operation.EndsWith(".get", StringComparison.Ordinal) || operation.EndsWith(".list", StringComparison.Ordinal) ||
                operation is "controller.types" or "note.expression_bounds" or "time.convert" or "history.status" or
                    "track.freeze" or "track.unfreeze" or "track.freeze_state") return;
        }
        if (method == "audio_op")
        {
            string operation = parameters.GetProperty("operation").GetString() ?? "";
            if (operation.StartsWith("transport_", StringComparison.Ordinal) || operation is "devices" or "inspect_audio" or
                "export_audio" or "effects" or "mixdown" or "mixdown_stems" or "process_audio") return;
        }
        throw new InvalidOperationException("Unfreeze the session's cached tracks before editing the project.");
    }

    internal void CheckFrozenNativeMutation(EngineSession session)
    {
        if (HasFrozenAuthoring(session))
            throw new InvalidOperationException("Unfreeze the session's cached tracks before a raw native mutation.");
    }

    internal void CheckFrozenExternalOperation(string? id, string domain, string operation, JsonElement options = default)
    {
        if (id is null || !HasFrozenAuthoring(GetSession(id))) return;
        if (domain == "library" && IsEmptyDvqmClear(id, operation, options)) return;
        bool readOnly = domain == "clipboard" ? operation is "list" or "clear" :
            operation is "languages" or "phoneme_table" or "lyrics_can_convert" or "lyrics_candidates" or
                "style_list" or "style_get" or "media_list" or "media_get" or "dvqm_catalog" or "dvqm_get" or
                "note_skill_get" or "singing_skill_catalog" or "singing_skill_get";
        if (!readOnly) throw new InvalidOperationException("Unfreeze the session's cached tracks before editing or copying their data.");
    }

    private void ApplyFrozenAuthoringState(EngineSession session, string stage)
    {
        if (!HasFrozenAuthoring(session)) return;
        string path = Path.Combine(stage, "Project", "sequence.json");
        PathGuard.NoLinks(path);
        JsonNode root = JsonNode.Parse(File.ReadAllText(path)) ?? throw new InvalidDataException("Native frozen snapshot JSON is empty.");
        JsonArray tracks = root["tracks"] as JsonArray ?? throw new InvalidDataException("Native frozen snapshot has no tracks.");
        static void Restore(JsonNode owner, FrozenEffect[] expected, string location)
        {
            JsonArray? effects = owner["audioEffects"] as JsonArray;
            if (effects is null && expected.Length == 0) return;
            if (effects is null || effects.Count != expected.Length)
                throw new InvalidDataException("Frozen authoring effect count mismatch: " + location);
            for (int i = 0; i < expected.Length; i++)
            {
                JsonNode effect = effects[i] ?? throw new InvalidDataException("Frozen authoring effect entry is null: " + location);
                string? id = effect["id"]?.GetValue<string>();
                if (!string.Equals(id, expected[i].Id, StringComparison.OrdinalIgnoreCase) || effect["isBypassed"] is null)
                    throw new InvalidDataException("Frozen authoring effect identity mismatch: " + location + " slot " + i);
                effect["isBypassed"] = expected[i].Bypassed;
            }
        }
        foreach (FrozenAuthoringState snapshot in frozenAuthoring[session.Id].Values)
        {
            int index = snapshot.TrackIndex;
            WIVSMMidiTrack current = ScoreMidiTrack(session, index);
            if (index >= tracks.Count || !current.IsFrozen || !string.Equals(current.WaveFilePath, snapshot.OwnedWavePath, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("Frozen authoring track identity/state changed.");
            JsonNode track = tracks[index] ?? throw new InvalidDataException("Frozen authoring track is missing.");
            Restore(track, snapshot.TrackEffects, "track " + index);
            JsonArray parts = track["parts"] as JsonArray ?? throw new InvalidDataException("Frozen authoring parts are missing.");
            if (parts.Count != snapshot.PartEffects.Length) throw new InvalidDataException("Frozen authoring part count changed.");
#if !VOCALOID7
            for (int i = 0; i < parts.Count; i++)
                Restore(parts[i] ?? throw new InvalidDataException("Frozen authoring part is missing."), snapshot.PartEffects[i], $"track {index} part {i}");
#endif
        }
        File.WriteAllText(path, root.ToJsonString());
    }

    private object TrackFreezeOperation(EngineSession session, string operation, JsonElement options)
    {
        int index = ScoreTrackIndex(session, options);
        WIVSMMidiTrack track = ScoreMidiTrack(session, index);
        object State(WIVSMMidiTrack value) => new
        {
            track_index = index,
            frozen = value.IsFrozen,
            can_freeze = value.CanFreeze(),
            owned = frozenAuthoring.TryGetValue(session.Id, out var existing) && existing.ContainsKey(index)
        };
        if (operation == "track.freeze_state") return State(track);
        ScoreRequireUnstaged(session.Sequence);
        if (operation == "track.unfreeze")
        {
            if (!track.IsFrozen) throw new InvalidOperationException("Track is not frozen.");
            if (!frozenAuthoring.TryGetValue(session.Id, out var owned) || !owned.TryGetValue(index, out FrozenAuthoringState? snapshot) ||
                !string.Equals(track.WaveFilePath, snapshot.OwnedWavePath, StringComparison.OrdinalIgnoreCase) ||
                !PathGuard.IsUnder(session.Directory, snapshot.OwnedWavePath))
                throw new InvalidOperationException("Frozen wave is not owned by this session.");
            PathGuard.NoLinks(session.Directory);
            if (File.Exists(snapshot.OwnedWavePath)) PathGuard.NoLinks(snapshot.OwnedWavePath);
            track.IsFrozen = false;
            ScoreRequire(!track.IsFrozen, operation, session.Sequence);
            if (frozenAuthoring.TryGetValue(session.Id, out var states))
            {
                states.Remove(index);
                if (states.Count == 0) frozenAuthoring.Remove(session.Id);
            }
            session.Dirty = true;
            session.InvalidateChildren();
            return State(ScoreMidiTrack(session, index));
        }
        if (operation != "track.freeze") throw new ArgumentException("Unknown freeze operation.");
        if (track.IsFrozen) throw new InvalidOperationException("Track is already frozen.");
        if (!string.IsNullOrEmpty(track.WaveFilePath)) throw new InvalidOperationException("Track has a non-owned frozen wave path.");
        FrozenAuthoringState authoring = CaptureFrozenAuthoring(track, index);
        string outputName = "freeze-stem-" + Guid.NewGuid().ToString("N") + ".wav";
        JsonElement mixOptions = JsonSerializer.SerializeToElement(new
        {
            output_name = outputName,
            track_indices = new[] { index },
            sample_rate = (int)session.Sequence.GetSamplingRate(),
            channels = 2,
            bits_per_sample = 16,
            bypass_effects = false
        });
        string stemPath = PathGuard.Under(OutputRoot, outputName);
        if (File.Exists(stemPath)) throw new IOException("Generated freeze stem already exists.");
        string path = Path.Combine(session.Directory, "frozen-" + Guid.NewGuid().ToString("N") + ".wav");
        PathGuard.NoLinks(session.Directory);
        bool stemOwned = false, touchedTrack = false;
        try
        {
            object rendered = MixAudio(session, mixOptions, true);
            stemOwned = true;
            JsonElement mix = JsonSerializer.SerializeToElement(rendered);
            if (!string.Equals(mix.GetProperty("path").GetString(), stemPath, StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("Native stem mix returned an unexpected output path.");
            track = ScoreMidiTrack(session, index);
            if (!track.CanFreeze()) throw new InvalidOperationException("Native track is not ready to freeze after rendering.");
            PathGuard.NoLinks(stemPath);
            InspectWave(stemPath);
            WIVSMMidiPart first = track.GetPart(0) ?? throw new InvalidOperationException("Native frozen track has no first MIDI part.");
            double startSeconds = session.Sequence.GetTimeFromTick(first.AbsBeginTick) - session.Sequence.PresendTimeSec;
            TrackFreezeMaterialize(stemPath, path, startSeconds);
            touchedTrack = true;
            track.WaveFilePath = path;
            if (track.WaveFilePath != path) throw new InvalidOperationException("Native frozen wave path readback failed.");
            track.StoreAudioEffectBypass();
            track.IsFrozen = true;
            ScoreRequire(track.IsFrozen, operation, session.Sequence);
            if (!frozenAuthoring.TryGetValue(session.Id, out var states))
                frozenAuthoring.Add(session.Id, states = []);
            states.Add(index, authoring with { OwnedWavePath = path });
            session.Dirty = true;
            return State(track);
        }
        catch
        {
            if (touchedTrack)
            {
                track.IsFrozen = false;
                track.WaveFilePath = "";
            }
            if (File.Exists(path)) File.Delete(path);
            throw;
        }
        finally
        {
            if (stemOwned && File.Exists(stemPath)) File.Delete(stemPath);
            session.InvalidateChildren();
        }
    }

    // Materialize the native 16-bit stereo mix on the frozen placement's time origin.
    private static void TrackFreezeMaterialize(string source, string destination, double startSeconds)
    {
        using FileStream input = File.OpenRead(source);
        using BinaryReader reader = new(input);
        if (reader.ReadUInt32() != 0x46464952 || reader.ReadUInt32() + 8L > input.Length || reader.ReadUInt32() != 0x45564157)
            throw new InvalidDataException("Invalid native RIFF wave.");
        ushort format = 0, channels = 0, alignment = 0, bits = 0;
        uint rate = 0;
        long dataStart = -1, dataBytes = 0;
        while (input.Position + 8 <= input.Length)
        {
            uint id = reader.ReadUInt32(), size = reader.ReadUInt32();
            long start = input.Position;
            if (start + size > input.Length) throw new InvalidDataException("Truncated native wave chunk.");
            if (id == 0x20746d66 && size >= 16)
            {
                format = reader.ReadUInt16(); channels = reader.ReadUInt16(); rate = reader.ReadUInt32();
                reader.ReadUInt32(); alignment = reader.ReadUInt16(); bits = reader.ReadUInt16();
            }
            else if (id == 0x61746164) { dataStart = start; dataBytes = size; }
            input.Position = start + size + (size & 1);
        }
        if (format != 1 || channels != 2 || bits != 16 || alignment != 4 || rate == 0 || dataStart < 0 || dataBytes % alignment != 0)
            throw new InvalidDataException("Freeze requires the native 16-bit stereo PCM stem.");
        long startFrame = checked((long)Math.Round(startSeconds * rate, MidpointRounding.AwayFromZero));
        long skip = Math.Max(0, startFrame), pad = Math.Max(0, -startFrame);
        long available = dataBytes / alignment;
        if (skip > available) throw new InvalidOperationException("Frozen time origin exceeds the native stem.");
        long length = checked((available - skip + pad) * alignment);
        if (length > uint.MaxValue - 36) throw new InvalidOperationException("Frozen cache PCM exceeds RIFF limits.");
        using FileStream output = new(destination, FileMode.CreateNew, FileAccess.Write, FileShare.None);
        using BinaryWriter writer = new(output);
        writer.Write(0x46464952u); writer.Write((uint)(36 + length)); writer.Write(0x45564157u);
        writer.Write(0x20746d66u); writer.Write(16u); writer.Write(format); writer.Write(channels);
        writer.Write(rate); writer.Write(rate * alignment); writer.Write(alignment); writer.Write(bits);
        writer.Write(0x61746164u); writer.Write((uint)length);
        byte[] buffer = new byte[65536];
        long silence = pad * alignment;
        while (silence > 0) { int count = (int)Math.Min(silence, buffer.Length); output.Write(buffer, 0, count); silence -= count; }
        input.Position = dataStart + skip * alignment;
        long remaining = dataBytes - skip * alignment;
        while (remaining > 0)
        {
            int count = input.Read(buffer, 0, (int)Math.Min(remaining, buffer.Length));
            if (count == 0) throw new EndOfStreamException("Truncated native stem data.");
            output.Write(buffer, 0, count); remaining -= count;
        }
    }
}
