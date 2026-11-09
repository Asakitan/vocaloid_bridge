using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using Yamaha.VOCALOID.VMM;
using Yamaha.VOCALOID.VSM;

internal sealed partial class EngineHost
{
    private const string LibraryArchiveKey = "vocaloid_bridge_archive_entities_v1";
    private sealed class LibraryArchiveNote
    {
        [JsonRequired] public long Position { get; set; }
        [JsonRequired] public long Duration { get; set; }
        [JsonRequired] public int Number { get; set; }
        [JsonRequired] public int Velocity { get; set; }
        [JsonRequired] public string Lyric { get; set; } = "";
        [JsonRequired] public string Phonemes { get; set; } = "";
        [JsonRequired] public int Language { get; set; }
        [JsonRequired] public bool Valid { get; set; }
        [JsonRequired] public JsonObject Extra { get; set; } = new();
        public Dictionary<int, ProjectArchiveNoteArrays.Point>? DirectPitch { get; set; }
        internal ArchiveNoteSignature Signature => new(Position, Duration, Number, Velocity, Lyric, Phonemes, Language, Valid);
    }
    private sealed class LibraryArchiveClip
    {
        [JsonRequired] public int Version { get; set; }
        public string Kind { get; set; } = "midi";
        public string? AudioHash { get; set; }
        public Dictionary<VSMControllerType, Dictionary<int, ProjectArchiveArrays.ControllerPoint>>? Controllers { get; set; }
        [JsonRequired] public string ClipId { get; set; } = "";
        [JsonRequired] public long Duration { get; set; }
        [JsonRequired] public JsonObject PartExtra { get; set; } = new();
        [JsonRequired] public List<LibraryArchiveNote> Notes { get; set; } = [];
    }

    private LibraryArchiveClip? LibraryArchiveCapture(EngineSession session, WIVSMTrack track, WIVSMPart part)
    {
        if (!archiveStates.TryGetValue(session.Id, out ArchiveState? state) || !state.HasEntityExtensions) return null;
        ArchiveCheck(state);
        if (!state.Live.TryGetValue(ArchiveKey(part), out ArchiveEntry? entry) || entry.Parent != ArchiveKey(track))
            throw new InvalidDataException("project_preservation: media source part identity is not tracked under its track.");
        if (track.Type is not (VSMTrackType.Midi or VSMTrackType.MidiAi))
        {
            return entry.Extra.Count == 0 ? null : new LibraryArchiveClip { Version = 2, Kind = "audio", PartExtra = (JsonObject)entry.Extra.DeepClone() };
        }
        WIVSMMidiPart midi = part as WIVSMMidiPart ?? new WIVSMMidiPart(part);
        LibraryArchiveClip result = new() { Version = 2, Duration = midi.DurationTick.Value, PartExtra = (JsonObject)entry.Extra.DeepClone(), Controllers = entry.Controller };
        HashSet<(long, long, int, string, string)> seen = [];
        foreach (WIVSMNote note in midi.Notes)
        {
            ArchiveNoteSignature signature = ArchiveNoteKey(note);
            if (!seen.Add((signature.Position, signature.Duration, signature.Number, signature.Lyric, signature.Phonemes)) || state.Live.TryGetValue(ArchiveKey(note), out var existing) && existing.Parent != ArchiveKey(part))
                throw new InvalidDataException("project_preservation: ambiguous or untracked media source note.");
            state.Live.TryGetValue(ArchiveKey(note), out var source);
            result.Notes.Add(new LibraryArchiveNote { Position = signature.Position, Duration = signature.Duration,
                Number = signature.Number, Velocity = signature.Velocity, Lyric = signature.Lyric,
                Phonemes = signature.Phonemes, Language = signature.Language, Valid = signature.Valid,
                Extra = source is null ? new() : (JsonObject)source.Extra.DeepClone(), DirectPitch = source?.DirectPitch });
        }
        return result.PartExtra.Count != 0 || result.Controllers is not null || result.Notes.Any(note => note.Extra.Count != 0 || note.DirectPitch is not null) ? result : null;
    }

    private void LibraryArchiveWrite(UserClip clip, LibraryArchiveClip data)
    {
        data.ClipId = clip.ID;
        LibraryRequire(clip.ReadPart(), "read captured media");
        if (data.Kind == "audio") data.AudioHash = MediaAudioHash(clip.AudioPart!.WavFilePath);
        LibraryUpdateClip(clip, root =>
        {
            if (root.ContainsKey(LibraryArchiveKey)) throw new InvalidDataException("Reserved media archive metadata already exists.");
            root.Add(LibraryArchiveKey, JsonSerializer.SerializeToNode(data));
        });
        LibraryRequire(clip.ReadPart(), "read captured media archive");
        if (data.Kind == "audio") LibraryArchiveReadAudio(clip);
        else { MidiPart midi = clip.MidiPart ?? throw new InvalidDataException("Captured media MIDI part is missing.");
            LibraryArchiveRead(clip, midi, LibraryReadValidity(clip, midi)); }
    }

    private static bool LibraryArchiveHasMetadata(Clip clip)
    {
        PathGuard.NoLinks(clip.ClipPath);
        using FileStream file = new(clip.ClipPath, FileMode.Open, FileAccess.Read, FileShare.Read);
        using JsonDocument document = JsonDocument.Parse(file);
        return document.RootElement.TryGetProperty(LibraryArchiveKey, out _);
    }

    // ArchiveUnknownFields produces paths ending at unknown object properties,
    // never at a native field or through an array. Recheck that invariant for
    // the editable private clip before accepting its metadata as archive data.
    private static void LibraryArchiveValidateExtra(JsonObject extra, JsonObject ownerSchema)
    {
        foreach ((string pointer, JsonNode? value) in extra)
        {
            if (pointer.StartsWith(ArrayPrefix, StringComparison.Ordinal))
            {
                ValidateArrayMetadata(pointer[ArrayPrefix.Length..], value, ownerSchema);
                continue;
            }
            if (!pointer.StartsWith("/", StringComparison.Ordinal))
                throw new InvalidDataException("project_preservation: invalid media archive metadata path.");
            string[] segments = pointer[1..].Split('/');
            JsonObject current = ownerSchema;
            for (int index = 0; index < segments.Length; index++)
            {
                string encoded = segments[index];
                for (int i = 0; i < encoded.Length; i++)
                    if (encoded[i] == '~' && (i + 1 == encoded.Length || encoded[++i] is not ('0' or '1')))
                        throw new InvalidDataException("project_preservation: invalid media archive metadata escape.");
                string key = encoded.Replace("~1", "/", StringComparison.Ordinal).Replace("~0", "~", StringComparison.Ordinal);
                JsonObject properties = ArchiveResolveSchema(current, ArchiveSchema())["properties"] as JsonObject
                    ?? throw new InvalidDataException("project_preservation: media archive metadata traverses a non-object field.");
                if (index == segments.Length - 1)
                {
                    if (properties.ContainsKey(key))
                        throw new InvalidDataException("project_preservation: media archive metadata targets a native field.");
                }
                else
                    current = properties[key] as JsonObject
                        ?? throw new InvalidDataException("project_preservation: media archive metadata parent is not a native object.");
            }
        }
    }

    private LibraryArchiveClip? LibraryArchiveRead(Clip clip, MidiPart midi, LibraryClipValidity? validity)
    {
        PathGuard.NoLinks(clip.ClipPath);
        using FileStream file = new(clip.ClipPath, FileMode.Open, FileAccess.Read, FileShare.Read);
        using JsonDocument document = JsonDocument.Parse(file);
        if (!document.RootElement.TryGetProperty(LibraryArchiveKey, out JsonElement value)) return null;
        // Metadata is a bridge-owned contract, never silently ignored on a foreign clip.
        LibraryOwnedClip(clip.ID);
        LibraryArchiveClip data = value.Deserialize<LibraryArchiveClip>() ?? throw new InvalidDataException("Media archive metadata is empty.");
        if (data.Version is not (1 or 2) || data.Kind != "midi" || !string.Equals(data.ClipId, clip.ID, StringComparison.Ordinal) || data.PartExtra is null ||
            data.Notes is null || data.Duration != midi.Duration || (ulong)data.Notes.Count != midi.NumNotes)
            throw new InvalidDataException("Media archive metadata does not match its clip.");
        JsonObject trackSchema = ArchiveItemSchema(ArchivePropertySchema(ArchiveSchema(), "tracks"));
        JsonObject partSchema = ArchiveItemSchema(ArchivePropertySchema(trackSchema, "parts"));
        JsonObject noteSchema = ArchiveItemSchema(ArchivePropertySchema(partSchema, "notes"));
        LibraryArchiveValidateExtra(data.PartExtra, partSchema);
        HashSet<(long, long, int, string, string)> seen = [];
        for (int i = 0; i < data.Notes.Count; i++)
        {
            LibraryArchiveNote saved = data.Notes[i] ?? throw new InvalidDataException("Media archive note is null.");
            Yamaha.VOCALOID.VMM.Note note = midi.GetNote((ulong)i) ?? throw new InvalidDataException("Media note is missing.");
            if (saved.Extra is null || saved.Lyric is null || saved.Phonemes is null || !seen.Add((saved.Position, saved.Duration, saved.Number, saved.Lyric, saved.Phonemes)) ||
                saved.Position != note.Position || saved.Duration != note.Duration || saved.Number != note.Number ||
                saved.Velocity != note.Velocity || saved.Lyric != note.Lyric || saved.Phonemes != note.Phoneme ||
                saved.Language != note.LangID || saved.Valid != (validity?.Notes[i].IsValid ?? true))
                throw new InvalidDataException("Media archive note identity is ambiguous or changed.");
            LibraryArchiveValidateExtra(saved.Extra, noteSchema);
        }
        if (data.Controllers is not null)
            foreach (var lane in data.Controllers)
            {
                var controller = midi.GetMidiController(LibraryMapEnum<VMMMidiControllerType>(lane.Key));
                JsonArray events = new();
                if (controller is not null)
                    for (ulong i = 0; i < controller.NumEvents; i++) { var point = controller.GetEvent(i)!; events.Add(new JsonObject { ["pos"] = point.Position, ["value"] = point.Value }); }
                ProjectArchiveArrays.ValidateController(lane.Value, events);
            }
        for (int i = 0; i < data.Notes.Count; i++)
            if (data.Notes[i].DirectPitch is { } pitch)
                ProjectArchiveNoteArrays.Validate(pitch, midi.GetNote((ulong)i)!.DirectPitches.Select(p => new VSMDirectPitchData(p.Tick, p.Value)));
        return data;
    }

    private static string MediaAudioHash(string path)
    {
        PathGuard.NoLinks(path);
        using var stream = File.OpenRead(path);
        return Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(stream));
    }

    private LibraryArchiveClip? LibraryArchiveReadAudio(Clip clip)
    {
        using var file = File.OpenRead(clip.ClipPath);
        using var doc = JsonDocument.Parse(file);
        if (!doc.RootElement.TryGetProperty(LibraryArchiveKey, out var value)) return null;
        LibraryOwnedClip(clip.ID);
        var data = value.Deserialize<LibraryArchiveClip>() ?? throw new InvalidDataException("Empty audio metadata.");
        if (data.Version != 2 || data.Kind != "audio" || data.ClipId != clip.ID || data.Notes.Count != 0 || data.Controllers is not null ||
            data.AudioHash != MediaAudioHash(clip.AudioPart!.WavFilePath))
            throw new InvalidDataException("Audio metadata does not match the captured waveform.");
        var trackSchema = ArchiveItemSchema(ArchivePropertySchema(ArchiveSchema(), "tracks"));
        LibraryArchiveValidateExtra(data.PartExtra, ArchiveItemSchema(ArchivePropertySchema(trackSchema, "parts")));
        return data;
    }

    // Exercise the exact import on an isolated native clone, then serialize and
    // overlay all retained fields there before touching the requested target.
    private void LibraryArchivePreflight(EngineSession session, JsonElement options)
    {
        ScoreRequireUnstaged(session.Sequence);
        EngineSession clone = CloneProject(session.Id, null);
        try
        {
            LibraryImportMedia(clone, options, false);
            string stage = Path.Combine(clone.Directory, "media-preflight-" + Guid.NewGuid().ToString("N"));
            PathGuard.CreateDirectory(stage);
            if (!clone.Sequence.Save(stage, false))
                throw new InvalidOperationException("Native media preflight snapshot failed: " + clone.Sequence.LastError);
            string project = Path.Combine(stage, "Project");
            PathGuard.TreeNoLinks(project);
            ValidateNativeSnapshot(clone.Sequence, Path.Combine(project, "sequence.json"));
            ApplyArchivePreservation(clone, stage);
        }
        finally { Close(clone.Id, true); }
    }

    private void LibraryArchiveAttach(EngineSession session, WIVSMTrack track, WIVSMMidiPart part,
        IReadOnlyList<WIVSMNote> notes, LibraryArchiveClip data)
    {
        if (!archiveStates.TryGetValue(session.Id, out ArchiveState? state) || state.Before is null || state.Action != "media_import")
            throw new InvalidOperationException("project_preservation: media import is outside its tracked transaction.");
        if (part.DurationTick.Value != data.Duration || notes.Count != data.Notes.Count || (ulong)notes.Count != part.NumNotes)
            throw new InvalidDataException("project_preservation: media target shape changed.");
        void Attach(object item, ArchiveEntity parent, JsonObject extra)
        {
            ArchiveEntity key = ArchiveKey(item);
            if (key.Pointer == nint.Zero || state.Before.ContainsKey(key))
                throw new InvalidDataException("project_preservation: media target identity collides with an existing entity.");
            if (state.Live.TryGetValue(key, out ArchiveEntry? current) &&
                (current.Parent != parent || ArchiveEntryHasPayload(current)))
                throw new InvalidDataException("project_preservation: media target identity has conflicting payload.");
            state.Live[key] = new ArchiveEntry((JsonObject)extra.DeepClone(), parent);
        }
        if (track.Parts.Any(other => ArchiveKey(other) != ArchiveKey(part) && ArchivePartKey(other) == ArchivePartKey(part)))
            throw new InvalidDataException("project_preservation: media target part identity is ambiguous.");
        Attach(part, ArchiveKey(track), data.PartExtra);
        if (data.Controllers is not null)
        {
            foreach (var lane in data.Controllers) ProjectArchiveArrays.ValidateController(lane.Value, ArchiveNativeControllers(part, lane.Key));
            state.Live[ArchiveKey(part)] = state.Live[ArchiveKey(part)] with { Controller = data.Controllers };
        }
        HashSet<ArchiveEntity> keys = [];
        for (int i = 0; i < notes.Count; i++)
        {
            if (!keys.Add(ArchiveKey(notes[i])) || ArchiveNoteKey(notes[i]) != data.Notes[i].Signature)
                throw new InvalidDataException("project_preservation: media target note identity changed.");
            Attach(notes[i], ArchiveKey(part), data.Notes[i].Extra);
            if (data.Notes[i].DirectPitch is { } pitch)
            {
                ProjectArchiveNoteArrays.Validate(pitch, ScorePitchPoints(notes[i]));
                state.Live[ArchiveKey(notes[i])] = state.Live[ArchiveKey(notes[i])] with { DirectPitch = ProjectArchiveNoteArrays.Clone(pitch) };
            }
        }
    }
}
