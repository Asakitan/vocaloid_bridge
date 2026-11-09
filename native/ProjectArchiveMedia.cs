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
        internal ArchiveNoteSignature Signature => new(Position, Duration, Number, Velocity, Lyric, Phonemes, Language, Valid);
    }
    private sealed class LibraryArchiveClip
    {
        [JsonRequired] public int Version { get; set; }
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
        if (entry.Controller is not null)
            throw new InvalidOperationException("project_preservation: selected media part has controller extensions.");
        if (track.Type is not (VSMTrackType.Midi or VSMTrackType.MidiAi))
        {
            if (entry.Extra.Count != 0) throw new InvalidOperationException("project_preservation: audio media extensions are unsupported.");
            return null;
        }
        WIVSMMidiPart midi = part as WIVSMMidiPart ?? new WIVSMMidiPart(part);
        LibraryArchiveClip result = new() { Version = 1, Duration = midi.DurationTick.Value, PartExtra = (JsonObject)entry.Extra.DeepClone() };
        HashSet<(long, long, int, string, string)> seen = [];
        foreach (WIVSMNote note in midi.Notes)
        {
            ArchiveNoteSignature signature = ArchiveNoteKey(note);
            if (!seen.Add((signature.Position, signature.Duration, signature.Number, signature.Lyric, signature.Phonemes)) || !state.Live.TryGetValue(ArchiveKey(note), out ArchiveEntry? source) || source.Parent != ArchiveKey(part))
                throw new InvalidDataException("project_preservation: ambiguous or untracked media source note.");
            result.Notes.Add(new LibraryArchiveNote { Position = signature.Position, Duration = signature.Duration,
                Number = signature.Number, Velocity = signature.Velocity, Lyric = signature.Lyric,
                Phonemes = signature.Phonemes, Language = signature.Language, Valid = signature.Valid,
                Extra = (JsonObject)source.Extra.DeepClone() });
        }
        return result.PartExtra.Count != 0 || result.Notes.Any(note => note.Extra.Count != 0) ? result : null;
    }

    private void LibraryArchiveWrite(UserClip clip, LibraryArchiveClip data)
    {
        data.ClipId = clip.ID;
        LibraryUpdateClip(clip, root =>
        {
            if (root.ContainsKey(LibraryArchiveKey)) throw new InvalidDataException("Reserved media archive metadata already exists.");
            root.Add(LibraryArchiveKey, JsonSerializer.SerializeToNode(data));
        });
        LibraryRequire(clip.ReadPart(), "read captured media archive");
        MidiPart midi = clip.MidiPart ?? throw new InvalidDataException("Captured media MIDI part is missing.");
        LibraryArchiveRead(clip, midi, LibraryReadValidity(clip, midi));
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
        foreach ((string pointer, _) in extra)
        {
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
        if (data.Version != 1 || !string.Equals(data.ClipId, clip.ID, StringComparison.Ordinal) || data.PartExtra is null ||
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
                (current.Parent != parent || current.Extra.Count != 0 || current.Controller is not null))
                throw new InvalidDataException("project_preservation: media target identity has conflicting payload.");
            state.Live[key] = new ArchiveEntry((JsonObject)extra.DeepClone(), parent);
        }
        if (track.Parts.Any(other => ArchiveKey(other) != ArchiveKey(part) && ArchivePartKey(other) == ArchivePartKey(part)))
            throw new InvalidDataException("project_preservation: media target part identity is ambiguous.");
        Attach(part, ArchiveKey(track), data.PartExtra);
        HashSet<ArchiveEntity> keys = [];
        for (int i = 0; i < notes.Count; i++)
        {
            if (!keys.Add(ArchiveKey(notes[i])) || ArchiveNoteKey(notes[i]) != data.Notes[i].Signature)
                throw new InvalidDataException("project_preservation: media target note identity changed.");
            Attach(notes[i], ArchiveKey(part), data.Notes[i].Extra);
        }
    }
}
