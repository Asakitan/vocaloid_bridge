using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using Yamaha.VOCALOID.VMM;

internal static class MediaPropertyWorker
{
    internal static int Run(string workspace, string token)
    {
        if (!Guid.TryParseExact(token, "N", out _)) throw new ArgumentException("Invalid media staging token.");
        string stage = PathGuard.Under(Path.Combine(workspace, ".runtime", "media-property"), token);
        PathGuard.TreeNoLinks(stage);
        using JsonDocument request = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(stage, "request.json")));
        JsonElement options = request.RootElement;
        string id = options.GetProperty("clip_id").GetString()!;
        if (!Guid.TryParse(id, out _)) throw new ArgumentException("Invalid media clip ID.");
        VMMError error = VMMError.None;
        using MediaManager manager = MediaManagerIF.CreateMediaManager("VOCALOID6", Path.Combine(stage, "empty"),
            Path.Combine(stage, "media"), [], [], ref error)
            ?? throw new IOException("Native staged media manager creation failed: " + error);
        if (error != VMMError.None || manager.ReadAllClipFiles() != VMMError.None)
            throw new IOException("Native staged media catalog load failed.");
        UserClip clip = manager.AllClipEnumerator().OfType<UserClip>().Single(item => item.ID == id);
        string expectedPath = Path.Combine(stage, "media", id, id + ".vsclip");
        if (!string.Equals(Path.GetFullPath(clip.ClipPath), expectedPath, StringComparison.OrdinalIgnoreCase))
            throw new IOException("Native staging selected a different clip path.");
        byte[] originalClip = File.ReadAllBytes(expectedPath);
        var editor = clip.CreatePropertyEditor() ?? throw new IOException("Native staged property editor was not created.");
        try
        {
            void Require(bool value) { if (!value) throw new IOException("Native staged media property edit failed."); }
            Require(editor.SetClipName(options.TryGetProperty("name", out JsonElement name) ? name.GetString()! : clip.Name));
            if (options.TryGetProperty("tempo", out JsonElement tempo)) Require(editor.SetPartTempo(tempo.GetInt32()));
            else if (clip.PartTempo > 0) Require(editor.SetPartTempo(clip.PartTempo));
            Require(editor.SetPartKey(clip.PartKey));
            foreach (string genre in clip.Filter.GenreEnumerator().Concat(options.GetProperty("add_genres").EnumerateArray().Select(item => item.GetString()!)).Distinct(StringComparer.Ordinal))
                Require(editor.AddFilterGenre(genre));
            foreach (string type in clip.Filter.TypeEnumerator().Concat(options.GetProperty("add_types").EnumerateArray().Select(item => item.GetString()!)).Distinct(StringComparer.Ordinal))
                Require(editor.AddFilterType(type));
            Require(editor.Save(true));
        }
        finally { clip.DestroyPropertyEditor(); }
        if (!File.ReadAllBytes(expectedPath).AsSpan().SequenceEqual(originalClip))
            throw new IOException("Native property serialization modified the staged clip content.");
        return 0;
    }
}

internal sealed partial class EngineHost
{
    private sealed class MediaWriteLease : IDisposable
    {
        private readonly Mutex mutex;
        internal MediaWriteLease(string id)
        {
            if (!Guid.TryParse(id, out _)) throw new ArgumentException("Invalid media clip ID.");
            mutex = new Mutex(false, "Local\\VocaloidBridge.Media." + id);
            try
            {
                if (!mutex.WaitOne(0)) throw new IOException("Media clip is being modified by another bridge process.");
            }
            catch (AbandonedMutexException)
            {
                mutex.ReleaseMutex(); mutex.Dispose();
                throw new IOException("A previous media writer ended unexpectedly; inspect its recovery directory before retrying.");
            }
            catch { mutex.Dispose(); throw; }
        }
        public void Dispose() { mutex.ReleaseMutex(); mutex.Dispose(); }
    }

    private static byte[] MediaReadLocked(FileStream stream)
    {
        if (stream.Length > 16 * 1024 * 1024) throw new IOException("Media properties exceed the 16 MiB limit.");
        byte[] bytes = new byte[checked((int)stream.Length)];
        stream.ReadExactly(bytes);
        return bytes;
    }

    private static JsonObject MediaPropertyObject(byte[] bytes)
    {
        // A parsed object must not silently collapse duplicate unknown keys.
        int offset = bytes.AsSpan().StartsWith(new byte[] { 0xef, 0xbb, 0xbf }) ? 3 : 0;
        using JsonDocument document = JsonDocument.Parse(bytes.AsMemory(offset));
        void Validate(JsonElement node)
        {
            if (node.ValueKind == JsonValueKind.Object)
            {
                HashSet<string> names = new(StringComparer.Ordinal);
                foreach (JsonProperty property in node.EnumerateObject())
                {
                    if (!names.Add(property.Name)) throw new IOException("Duplicate media property key: " + property.Name);
                    Validate(property.Value);
                }
            }
            else if (node.ValueKind == JsonValueKind.Array)
                foreach (JsonElement item in node.EnumerateArray()) Validate(item);
        }
        Validate(document.RootElement);
        return JsonNode.Parse(bytes.AsSpan(offset)) as JsonObject ?? throw new IOException("Media property root is not an object.");
    }

    private void InvalidateMediaCatalog()
    {
        MediaManager? old = libraryMedia;
        libraryMedia = null;
        old?.Dispose();
    }

    private object UpdateMediaProperties(EngineSession session, JsonElement options)
    {
        string id = LibraryText(options, "clip_id");
        using MediaWriteLease lease = new(id);
        // Reacquire after refresh rather than using an object cached by an earlier call.
        if (LibraryMedia().ReadAllClipFiles() != VMMError.None)
        {
            InvalidateMediaCatalog();
            throw new IOException("Native media catalog refresh failed before editing.");
        }
        UserClip clip = LibraryOwnedClip(id);
        if (LibraryArchiveHasMetadata(clip))
            throw new InvalidOperationException("project_preservation: property editing a media clip with archive metadata is not supported.");
        string[] genres = LibraryStrings(options, "add_genres"), types = LibraryStrings(options, "add_types");
        JsonObject request = new() { ["clip_id"] = id, ["add_genres"] = JsonSerializer.SerializeToNode(genres), ["add_types"] = JsonSerializer.SerializeToNode(types) };
        if (LibraryOption(options, "name").ValueKind != JsonValueKind.Undefined) request["name"] = LibraryText(options, "name");
        JsonElement tempo = LibraryOption(options, "tempo");
        if (tempo.ValueKind != JsonValueKind.Undefined)
        {
            if (tempo.ValueKind != JsonValueKind.Number || !tempo.TryGetInt32(out int value) || value <= 0)
                throw new ArgumentException("tempo must be a positive native integer.");
            request["tempo"] = value;
        }
        if (request.Count == 3 && genres.Length == 0 && types.Length == 0)
            return new { session_id = session.Id, clip = LibraryClipView(clip, true) };
        string sourceDirectory = Path.GetDirectoryName(clip.ClipPath)!;
        string propertyPath = Path.Combine(sourceDirectory, "property.json");
        PathGuard.TreeNoLinks(sourceDirectory);
        string stageRoot = Path.Combine(RuntimeRoot, "media-property");
        PathGuard.CreateDirectory(stageRoot);
        string token = Guid.NewGuid().ToString("N"), stage = PathGuard.Under(stageRoot, token);
        PathGuard.CreateDirectory(stage);
        string backup = Path.Combine(stage, "previous-property.json");
        bool committed = false, retain = false;
        try
        {
            byte[] original;
            JsonObject merged;
            using (FileStream sourceLock = new(clip.ClipPath, FileMode.Open, FileAccess.Read, FileShare.Read))
            using (FileStream propertyLock = new(propertyPath, FileMode.Open, FileAccess.Read, FileShare.Read))
            {
                original = MediaReadLocked(propertyLock);
                merged = MediaPropertyObject(original);
                foreach (string collection in new[] { "genres", "types" })
                    if (merged["filter"]?[collection] is JsonArray values && values.Any(item => item is not JsonValue value || !value.TryGetValue<string>(out _)))
                        throw new IOException("Media tag arrays must contain strings.");
                string copiedRoot = Path.Combine(stage, "media", id);
                PathGuard.CreateDirectory(copiedRoot);
                PathGuard.CreateDirectory(Path.Combine(stage, "empty"));
                foreach (string source in Directory.EnumerateFiles(sourceDirectory, "*", SearchOption.AllDirectories))
                {
                    string target = PathGuard.Under(copiedRoot, Path.GetRelativePath(sourceDirectory, source));
                    PathGuard.CreateDirectory(Path.GetDirectoryName(target)!);
                    File.Copy(source, target, false);
                }
                File.WriteAllText(Path.Combine(stage, "request.json"), request.ToJsonString());
                ProcessStartInfo start = new(Environment.ProcessPath!) { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true };
                foreach (string argument in new[] { Assembly.GetExecutingAssembly().Location, "--media-property", Path.GetDirectoryName(typeof(Yamaha.VOCALOID.VSM.WIVSMSequence).Assembly.Location)!, Workspace, token })
                    start.ArgumentList.Add(argument);
                string temp = Path.Combine(stage, "temp"); PathGuard.CreateDirectory(temp);
                start.Environment["TEMP"] = temp; start.Environment["TMP"] = temp;
                using Process worker = Process.Start(start) ?? throw new IOException("Native media serializer did not start.");
                Task<string> output = worker.StandardOutput.ReadToEndAsync(), error = worker.StandardError.ReadToEndAsync();
                if (!worker.WaitForExit(60000)) { worker.Kill(true); worker.WaitForExit(); throw new IOException("Native media serialization timed out."); }
                Task.WaitAll(output, error);
                if (worker.ExitCode != 0) throw new IOException("Native staged media serialization failed: " + error.Result);
                JsonObject serialized = MediaPropertyObject(File.ReadAllBytes(Path.Combine(copiedRoot, "property.json")));
                if (request.ContainsKey("name")) merged["name"] = serialized["name"]?.DeepClone() ?? throw new IOException("Native media name missing.");
                if (request.ContainsKey("tempo"))
                    (merged["part"] as JsonObject ?? throw new IOException("Media part properties missing."))["tempo"] = serialized["part"]?["tempo"]?.DeepClone() ?? throw new IOException("Native media tempo missing.");
                foreach ((string key, string[] additions) in new[] { ("genres", genres), ("types", types) })
                    if (additions.Length > 0)
                        (merged["filter"] as JsonObject ?? throw new IOException("Media filter missing."))[key] = serialized["filter"]?[key]?.DeepClone() ?? throw new IOException("Native media tag array missing.");
            }
            string candidate = Path.Combine(stage, "merged-property.json");
            byte[] updated = JsonSerializer.SerializeToUtf8Bytes(merged);
            using (FileStream stream = new(candidate, FileMode.CreateNew, FileAccess.Write, FileShare.None)) { stream.Write(updated); stream.Flush(true); }
            if (!File.ReadAllBytes(propertyPath).AsSpan().SequenceEqual(original)) throw new IOException("Media properties changed during staging; no update published.");
            File.Replace(candidate, propertyPath, backup);
            committed = true;
            if (!File.ReadAllBytes(backup).AsSpan().SequenceEqual(original))
                throw new IOException("An external writer changed the replaced file; its bytes are retained in the recovery snapshot.");
            if (LibraryMedia().ReadAllClipFiles() != VMMError.None)
                throw new IOException("Native media catalog refresh failed after publication.");
            UserClip refreshed = LibraryOwnedClip(id);
            if ((request.ContainsKey("name") && refreshed.Name != request["name"]!.GetValue<string>()) ||
                (request.ContainsKey("tempo") && refreshed.PartTempo != request["tempo"]!.GetValue<int>()) ||
                genres.Except(refreshed.Filter.GenreEnumerator(), StringComparer.Ordinal).Any() ||
                types.Except(refreshed.Filter.TypeEnumerator(), StringComparer.Ordinal).Any())
                throw new IOException("Native media property readback differs from the committed values.");
            return new { session_id = session.Id, clip = LibraryClipView(refreshed, true) };
        }
        catch (Exception error) when (committed)
        {
            retain = true;
            InvalidateMediaCatalog();
            throw new IOException("Media properties committed; native cache invalidated; recovery snapshot retained at " + backup, error);
        }
        finally
        {
            if (!retain) Cleanup(stage);
        }
    }
}
