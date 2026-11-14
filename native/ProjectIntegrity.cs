using System.IO;
using System.Text.Json;
using System.Xml;
using Yamaha.VOCALOID.VDM;
using Yamaha.VOCALOID.VSM;

internal sealed partial class EngineHost
{
    // These checks inspect the actual staged native JSON; they do not synthesize
    // a missing voicebank or change the engine's selected track type.
    private static JsonElement IntegrityArray(JsonElement owner, string name)
    {
        if (!owner.TryGetProperty(name, out JsonElement value))
            return default;
        if (value.ValueKind != JsonValueKind.Array)
            throw new InvalidDataException($"project_integrity: {name} must be an array.");
        return value;
    }

    private static int IntegrityLength(JsonElement array) =>
        array.ValueKind == JsonValueKind.Undefined ? 0 : array.GetArrayLength();

    private static VSMTrackType IntegrityTrackType(JsonElement track, int index)
    {
        if (track.ValueKind != JsonValueKind.Object ||
            !track.TryGetProperty("type", out JsonElement value) || value.ValueKind != JsonValueKind.Number ||
            !value.TryGetInt32(out int kind) ||
            kind is < 0 or > 2)
            throw new InvalidDataException($"project_integrity: invalid track type at index {index}.");
        return (VSMTrackType)kind;
    }

    private static string IntegrityVoice(JsonElement part, string property)
    {
        if (!part.TryGetProperty(property, out JsonElement voice))
            return string.Empty;
        if (voice.ValueKind != JsonValueKind.Object || !voice.TryGetProperty("compID", out JsonElement id) ||
            id.ValueKind != JsonValueKind.String)
            throw new InvalidDataException($"project_integrity: invalid {property}.compID.");
        return id.GetString() ?? string.Empty;
    }

    private void ValidateOpenRequirements(string jsonPath)
    {
        PathGuard.NoLinks(jsonPath);
        using FileStream file = File.OpenRead(jsonPath);
        using JsonDocument document = JsonDocument.Parse(file);
        JsonElement tracks = IntegrityArray(document.RootElement, "tracks");
        bool classic = false;
        for (int index = 0; index < IntegrityLength(tracks); index++)
        {
            JsonElement track = tracks[index];
            VSMTrackType type = IntegrityTrackType(track, index);
            classic |= type == VSMTrackType.Midi;
            if (type != VSMTrackType.MidiAi)
                continue;
            JsonElement parts = IntegrityArray(track, "parts");
            for (int partIndex = 0; partIndex < IntegrityLength(parts); partIndex++)
            {
                JsonElement part = parts[partIndex];
                if (part.ValueKind != JsonValueKind.Object)
                    continue;
                JsonElement notes = IntegrityArray(part, "notes");
                for (int noteIndex = 0; noteIndex < IntegrityLength(notes); noteIndex++)
                {
                    JsonElement note = notes[noteIndex];
                    if (note.ValueKind != JsonValueKind.Object ||
                        !note.TryGetProperty("singingSkill", out JsonElement skill) || skill.ValueKind != JsonValueKind.Object ||
                        !note.TryGetProperty("dvqm", out JsonElement dvqm) || dvqm.ValueKind != JsonValueKind.Object)
                        continue;
                    foreach (string name in new[] { "attack", "release" })
                        if (dvqm.TryGetProperty(name, out JsonElement selection) && selection.ValueKind == JsonValueKind.Object &&
                            selection.EnumerateObject().Any())
                            throw new InvalidDataException($"project_integrity: AI note {index}/{partIndex}/{noteIndex} combines Attack/Release and Singing Skill; native reopening loses Singing Skill. Use score_patch to remove one representation in a separate VPR.");
                }
            }
        }
        if (!classic)
            return;
        ValidateClassicVoiceBanks("native VPR loading");
    }

    private void ValidateVsqxOpenRequirements(string path)
    {
        using XmlReader reader = XmlReader.Create(path, new XmlReaderSettings
        {
            DtdProcessing = DtdProcessing.Prohibit,
            XmlResolver = null,
            MaxCharactersInDocument = MaxArchiveBytes
        });
        reader.MoveToContent();
        string schema = reader.NamespaceURI;
        if (!((reader.LocalName == "vsq3" && schema == "http://www.yamaha.co.jp/vocaloid/schema/vsq3/") ||
              (reader.LocalName == "vsq4" && schema == "http://www.yamaha.co.jp/vocaloid/schema/vsq4/")))
            return;
        while (reader.Read())
        {
            if (reader.NodeType != XmlNodeType.Element || reader.Depth != 1 ||
                reader.LocalName != "vsTrack" || reader.NamespaceURI != schema)
                continue;
            ValidateClassicVoiceBanks("native VSQX loading");
            return;
        }
    }

    private void ValidateClassicVoiceBanks(string operation)
    {
        DatabaseManager current = EnsureDatabase();
        ulong dse = current.GetNumVoiceBanks(VDMVoiceBankType.Dse);
        ulong dnn = current.GetNumVoiceBanks(VDMVoiceBankType.Dnn);
        if (dse == 0 && dnn != 0)
            throw new InvalidOperationException($"missing_classic_bank: {operation} would convert classic MIDI tracks to AI (Dse={dse}, Dnn={dnn}); source remains unchanged.");
    }

    private static void ValidateNativeSnapshot(WIVSMSequence sequence, string jsonPath) =>
        ValidateProjectIdentity(sequence, jsonPath, "native_snapshot", snapshot: true);

    // On external open only specified serialized IDs are asserted: absent IDs do
    // not authorize the engine to alter a track kind or drop a part.
    private static void ValidateLoadedTrackKinds(WIVSMSequence sequence, string jsonPath) =>
        ValidateProjectIdentity(sequence, jsonPath, "native_open", snapshot: false);

    private static void ValidateProjectIdentity(WIVSMSequence sequence, string jsonPath, string operation, bool snapshot)
    {
        PathGuard.NoLinks(jsonPath);
        using FileStream file = File.OpenRead(jsonPath);
        using JsonDocument document = JsonDocument.Parse(file);
        JsonElement tracks = IntegrityArray(document.RootElement, "tracks");
        JsonElement voices = IntegrityArray(document.RootElement, "voices");
        HashSet<string> voiceIds = new(StringComparer.Ordinal);
        for (int voiceIndex = 0; voiceIndex < IntegrityLength(voices); voiceIndex++)
        {
            JsonElement voice = voices[voiceIndex];
            if (voice.ValueKind == JsonValueKind.Object && voice.TryGetProperty("compID", out JsonElement id) &&
                id.ValueKind == JsonValueKind.String && id.GetString() is string voiceId)
                voiceIds.Add(voiceId);
        }
        int trackCount = IntegrityLength(tracks);
        if ((ulong)trackCount != sequence.NumTrack)
            throw new InvalidDataException($"project_integrity: {operation} track count differs (JSON={trackCount}, native={sequence.NumTrack}).");
        for (int index = 0; index < trackCount; index++)
        {
            JsonElement serializedTrack = tracks[index];
            VSMTrackType expectedType = IntegrityTrackType(serializedTrack, index);
            WIVSMTrack track = sequence.GetTrack((ulong)index)
                ?? throw new InvalidDataException($"project_integrity: {operation} native track {index} is missing.");
            if (track.Type != expectedType)
                throw new InvalidDataException($"project_integrity: {operation} track {index} type differs (JSON={expectedType}, native={track.Type}).");
            JsonElement parts = IntegrityArray(serializedTrack, "parts");
            int partCount = IntegrityLength(parts);
            if ((ulong)partCount != track.NumParts)
                throw new InvalidDataException($"project_integrity: {operation} track {index} part count differs (JSON={partCount}, native={track.NumParts}).");
            if (track.Type is not (VSMTrackType.Midi or VSMTrackType.MidiAi))
                continue;
            WIVSMMidiTrack midi = track as WIVSMMidiTrack ?? new WIVSMMidiTrack(track);
#if VOCALOID7
            if (snapshot || serializedTrack.TryGetProperty("voice", out _))
            {
                ValidateVoiceIdentity(IntegrityVoice(serializedTrack, "voice"), midi.VoiceBankID,
                    snapshot, voiceIds, $"{operation} track {index} voice");
                ValidateVoiceIdentity(IntegrityVoice(serializedTrack, "secondaryVoice"), midi.SecondaryVoiceBankID,
                    snapshot, voiceIds, $"{operation} track {index} secondaryVoice");
            }
#endif
            for (int partIndex = 0; partIndex < partCount; partIndex++)
            {
                JsonElement serializedPart = parts[partIndex];
                if (serializedPart.ValueKind != JsonValueKind.Object)
                    throw new InvalidDataException($"project_integrity: {operation} track {index} part {partIndex} is invalid.");
                WIVSMMidiPart part = midi.GetPart((ulong)partIndex)
                    ?? throw new InvalidDataException($"project_integrity: {operation} native track {index} part {partIndex} is missing.");
#if VOCALOID7
                if (snapshot || serializedTrack.TryGetProperty("voice", out _))
                    continue;
                foreach ((string key, string nativeId) in new[] {
                    (part.IsAi ? "aiVoice" : "voice", midi.VoiceBankID),
                    (part.IsAi ? "secondaryAiVoice" : "secondaryVoice", midi.SecondaryVoiceBankID) })
                {
                    string jsonId = IntegrityVoice(serializedPart, key);
#else
                foreach ((string key, string nativeId) in new[] {
                    ("voice", part.VoiceBankID), ("aiVoice", part.AiVoiceBankID),
                    ("secondaryVoice", part.SecondaryVoiceBankID), ("secondaryAiVoice", part.SecondaryAiVoiceBankID) })
                {
                    string jsonId = IntegrityVoice(serializedPart, key);
#endif
                    ValidateVoiceIdentity(jsonId, nativeId, snapshot, voiceIds,
                        $"{operation} track {index} part {partIndex} {key}");
                }
            }
        }
    }

    private static void ValidateVoiceIdentity(string jsonId, string nativeId, bool snapshot,
        HashSet<string> voiceIds, string context)
    {
        if ((snapshot || jsonId.Length != 0) && !string.Equals(jsonId, nativeId, StringComparison.Ordinal))
            throw new InvalidDataException($"project_integrity: {context} ID differs (JSON='{jsonId}', native='{nativeId}').");
        if (snapshot && nativeId.Length != 0 && !voiceIds.Contains(nativeId))
            throw new InvalidDataException($"project_integrity: {context} ID is absent from the voices table.");
    }
}
