using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;

internal sealed partial class EngineHost
{
    // Rendering and exporting may issue native pre-render commits or prepare
    // runtime effects. Run them on a native snapshot when archive identity is
    // tracked, leaving the source sequence and its history untouched.
    internal bool UsesArchiveOutputSnapshot(EngineSession session, string method, JsonElement parameters)
    {
        if (!HasArchiveEntityExtensions(session)) return false;
        if (method is "render_part" or "export_midi") return true;
        return method == "audio_op" && parameters.GetProperty("operation").GetString() is "mixdown" or "mixdown_stems";
    }

    internal object ArchiveRenderOutput(EngineSession source, ulong trackIndex, ulong partIndex, string outputName, bool overwrite)
    {
        PrepareOutput(source, outputName, ".wav", overwrite);
        return RunArchiveOutput(source, snapshot => RenderPart(snapshot.Id, trackIndex, partIndex, outputName, overwrite));
    }

    internal object ArchiveMidiOutput(EngineSession source, string outputName, string encoding, bool overwrite)
    {
        string extension = Path.GetExtension(outputName).ToLowerInvariant();
        if (extension is not (".mid" or ".midi"))
            throw new ArgumentException("output_name must end in .mid or .midi.");
        // Check against the actual source path, not the detached clone's path.
        PrepareOutput(source, outputName, extension, overwrite);
        return RunArchiveOutput(source, snapshot => ExportMidi(snapshot.Id, outputName, encoding, overwrite));
    }

    internal object ArchiveAudioOutput(EngineSession source, string operation, JsonElement options)
    {
        if (operation == "mixdown")
            AudioDestination(source, options);
        else if (operation == "mixdown_stems")
        {
            string prefix = AudioText(options, "output_prefix");
            foreach (ulong track in AudioMixTrackIndices(source, options))
                PrepareOutput(source, prefix + "-track-" + track + ".wav", ".wav", AudioFlag(options, "overwrite"));
        }
        else throw new ArgumentException("Unknown snapshot audio operation: " + operation);
        return RunArchiveOutput(source, snapshot => AudioOperation(snapshot.Id, operation, options));
    }

    private object RunArchiveOutput(EngineSession source, Func<EngineSession, object> operation)
    {
        if (source.Sequence.IsStaged)
            throw new InvalidOperationException("Commit or roll back pending native edits before exporting a preserved project.");
        EngineSession snapshot = CloneProject(source.Id, null);
        try
        {
            JsonNode result = JsonSerializer.SerializeToNode(operation(snapshot))
                ?? throw new InvalidDataException("Native snapshot output returned no result.");
            RewriteOutputSession(result, snapshot.Id, source.Id);
            return result;
        }
        finally { Close(snapshot.Id, true); }
    }

    private static void RewriteOutputSession(JsonNode node, string snapshotId, string sourceId)
    {
        if (node is JsonObject obj)
        {
            if (obj["session_id"] is JsonValue value && value.TryGetValue<string>(out string? id) && id == snapshotId)
                obj["session_id"] = sourceId;
            foreach ((string key, JsonNode? child) in obj)
                if (key != "session_id" && child is not null) RewriteOutputSession(child, snapshotId, sourceId);
        }
        else if (node is JsonArray array)
            foreach (JsonNode? child in array)
                if (child is not null) RewriteOutputSession(child, snapshotId, sourceId);
    }
}
