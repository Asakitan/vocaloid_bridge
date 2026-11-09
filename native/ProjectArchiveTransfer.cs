using System.IO;
using System.Text.Json.Nodes;
using Yamaha.VOCALOID.VSM;

internal sealed partial class EngineHost
{
    // Callers that do not prepare resource transfer retain the strict guard.
    private void ArchiveTransferValidateSource(EngineSession source)
    {
        if (!archiveStates.TryGetValue(source.Id, out ArchiveState? state)) return;
        ArchiveCheck(state);
        if (state.ExtraFiles.Count != 0)
            throw new InvalidOperationException("project_preservation: source opaque archive resources have no transfer contract.");
    }

    private (JsonObject Root, JsonObject Master) ArchiveMergePrepare(EngineSession source, EngineSession target)
    {
        archiveStates.TryGetValue(source.Id, out ArchiveState? from);
        if (from is not null) ArchiveCheck(from);
        archiveStates.TryGetValue(target.Id, out ArchiveState? to);
        if (to is not null) ArchiveCheck(to);
        JsonObject root = to is null ? new JsonObject() : (JsonObject)to.Root.DeepClone();
        JsonObject master = to is null ? new JsonObject() : (JsonObject)to.Master.DeepClone();
        JsonObject nestedRoot = new();
        JsonObject nestedMaster = new();
        static void Merge(JsonObject destination, JsonObject? sourceFields, JsonObject nested)
        {
            if (sourceFields is null) return;
            foreach ((string pointer, JsonNode? value) in sourceFields)
            {
                if (destination.TryGetPropertyValue(pointer, out JsonNode? existing))
                {
                    if (!JsonNode.DeepEquals(existing, value))
                        throw new InvalidDataException("project_preservation: source root or master extension conflicts at " + pointer);
                    continue;
                }
                // Newly introduced nested leaves are validated against an
                // independent current native snapshot before target mutation.
                if (pointer.IndexOf('/', 1) >= 0)
                    nested.Add(pointer, value?.DeepClone());
                destination.Add(pointer, value?.DeepClone());
            }
        }
        Merge(root, from?.Root, nestedRoot);
        Merge(master, from?.Master, nestedMaster);
        if (nestedRoot.Count != 0 || nestedMaster.Count != 0)
        {
            EngineSession snapshot = CloneProject(target.Id, null);
            try
            {
                string path = Path.Combine(snapshot.Directory, "Project", "sequence.json");
                PathGuard.NoLinks(path);
                if (new FileInfo(path).Length > 128L * 1024 * 1024)
                    throw new InvalidDataException("project_preservation: snapshot JSON exceeds 128 MiB.");
                JsonObject current = ArchiveObject(JsonNode.Parse(File.ReadAllText(path)), "");
                ArchiveOverlay(current, nestedRoot);
                ArchiveOverlay(ArchiveObject(current["masterTrack"], "/masterTrack"), nestedMaster);
            }
            finally { Close(snapshot.Id, true); }
        }
        return (root, master);
    }

    // Opaque members are project-scoped: no claim is made that they belong to
    // any imported track. Never replace an existing member or case alias.
    private List<(string Name, string Source)> ArchivePrepareResources(EngineSession source, EngineSession target, bool includeTracks)
    {
        List<(string Name, string Source)> additions = [];
        if (!archiveStates.TryGetValue(source.Id, out ArchiveState? from) || from.ExtraFiles.Count == 0) return additions;
        ArchiveCheck(from);
        if (!includeTracks) throw new InvalidOperationException("project_preservation: opaque resource merge requires track import.");
        archiveStates.TryGetValue(target.Id, out ArchiveState? to);
        if (to is not null) ArchiveCheck(to);
        foreach (string name in from.ExtraFiles)
        {
            PathGuard.Under(source.Directory, name);
            string sourcePath = from.ResourcePaths[name];
            if (!PathGuard.IsUnder(source.Directory, sourcePath)) throw new IOException("project_preservation: resource escaped source session.");
            PathGuard.NoLinks(sourcePath);
            string? same = to?.ExtraFiles.FirstOrDefault(existing => existing.Equals(name, StringComparison.OrdinalIgnoreCase));
            if (same is not null)
            {
                if (!same.Equals(name, StringComparison.Ordinal) || !ArchiveFilesEqual(sourcePath, to!.ResourcePaths[same]))
                    throw new InvalidDataException("project_preservation: opaque member conflict: " + name);
                continue;
            }
            foreach (string existing in to?.ExtraFiles ?? [])
                if (existing.StartsWith(name + "/", StringComparison.OrdinalIgnoreCase) || name.StartsWith(existing + "/", StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("project_preservation: opaque member path conflict: " + name);
            additions.Add((name, sourcePath));
        }
        return additions;
    }

    private bool ArchiveHasResources(EngineSession session) =>
        archiveStates.TryGetValue(session.Id, out ArchiveState? state) && state.ExtraFiles.Count != 0;

    // Clipboard selections carry the entire project-scoped opaque set, even
    // when the selected entities are parts or notes rather than whole tracks.
    private List<(string Name, string Source)> ArchivePrepareClipboardResources(EngineSession source, EngineSession target) =>
        ArchivePrepareResources(source, target, true);

    private static bool ArchiveFilesEqual(string first, string second)
    {
        PathGuard.NoLinks(second);
        using FileStream a = File.OpenRead(first), b = File.OpenRead(second);
        if (a.Length != b.Length) return false;
        byte[] x = new byte[65536], y = new byte[65536];
        int count;
        while ((count = a.Read(x, 0, x.Length)) != 0)
        {
            b.ReadExactly(y, 0, count);
            if (!x.AsSpan(0, count).SequenceEqual(y.AsSpan(0, count))) return false;
        }
        return true;
    }

    private void ArchiveAddResources(EngineSession target, List<(string Name, string Source)> additions)
    {
        if (additions.Count == 0) return;
        ArchiveState state = archiveStates[target.Id];
        if (state.Before is null || !target.Sequence.IsStaged)
            throw new InvalidOperationException("project_preservation: resource merge requires a native history entry.");
        string storage = Path.Combine(target.Directory, ".bridge-resources-" + Guid.NewGuid().ToString("N"));
        PathGuard.CreateDirectory(storage);
        foreach ((string name, string source) in additions)
        {
            string destination = PathGuard.Under(storage, name);
            PathGuard.CreateDirectory(Path.GetDirectoryName(destination)!);
            PathGuard.NoLinks(source);
            File.Copy(source, destination, false);
            state.ExtraFiles.Add(name);
            state.ResourcePaths.Add(name, destination);
        }
    }

    // Call on a freshly returned native duplicate, inside a target archive
    // transaction, after moving a duplicated track's parts for its offset.
    // partOffset applies to track child parts or a directly duplicated part;
    // noteOffset applies to a directly duplicated note. Notes within copied
    // parts retain their relative positions.
    // Caller commits only after every mapping succeeds and rolls both journals
    // back on any exception. Target observer/state must already be initialized.
    private void ArchiveTransferCopy(EngineSession source, EngineSession target,
        object original, object duplicate, long partOffset = 0, long noteOffset = 0, bool mergeResources = false)
    {
        if (ReferenceEquals(source, target))
            throw new InvalidOperationException("project_preservation: transfer requires an independent snapshot.");
        if (!mergeResources) ArchiveTransferValidateSource(source);
        if (!archiveStates.TryGetValue(target.Id, out ArchiveState? to) || to.Before is null || !to.ObserverAttached)
            throw new InvalidOperationException("project_preservation: transfer target identity transaction is not initialized.");
        archiveStates.TryGetValue(source.Id, out ArchiveState? from);
        List<(ArchiveEntity Key, ArchiveEntry Entry)> pending = [];
        void Add(object left, object right, ArchiveEntity? sourceParent, ArchiveEntity? parent)
        {
            ArchiveEntity a = ArchiveKey(left), b = ArchiveKey(right);
            if (a.Pointer == nint.Zero || b.Pointer == nint.Zero || a == b || to.Live.ContainsKey(b) ||
                pending.Any(item => item.Key == b))
                throw new InvalidDataException("project_preservation: transfer identity is invalid or already tracked.");
            JsonObject extra = from is not null && from.Live.TryGetValue(a, out ArchiveEntry? entry)
                ? (JsonObject)entry.Extra.DeepClone() : new JsonObject();
            if (from is not null && from.HasEntityExtensions && !from.Live.ContainsKey(a))
                throw new InvalidDataException("project_preservation: source transfer identity is not tracked.");
            if (from is not null && from.Live.TryGetValue(a, out ArchiveEntry? sourceEntry) && sourceEntry.Parent != sourceParent)
                throw new InvalidDataException("project_preservation: source transfer parent identity changed.");
            if (parent is ArchiveEntity parentKey && !to.Live.ContainsKey(parentKey) && !pending.Any(item => item.Key == parentKey))
                throw new InvalidDataException("project_preservation: target transfer parent is not tracked.");
            Dictionary<VSMControllerType, Dictionary<int, ProjectArchiveArrays.ControllerPoint>>? controllers = null;
            if (from is not null && from.Live.TryGetValue(a, out ArchiveEntry? retained) && retained.Controller is not null)
            {
                if (left is not WIVSMMidiPart sourcePart || right is not WIVSMMidiPart targetPart)
                    throw new InvalidDataException("project_preservation: controller payload is not attached to a MIDI part.");
                controllers = [];
                foreach ((VSMControllerType type, Dictionary<int, ProjectArchiveArrays.ControllerPoint> points) in retained.Controller)
                {
                    ProjectArchiveArrays.ValidateController(points, ArchiveNativeControllers(sourcePart, type));
                    ProjectArchiveArrays.ValidateController(points, ArchiveNativeControllers(targetPart, type));
                    controllers.Add(type, points.ToDictionary(pair => pair.Key,
                        pair => new ProjectArchiveArrays.ControllerPoint(pair.Value.Value, (JsonObject)pair.Value.Extra.DeepClone())));
                }
            }
            pending.Add((b, new ArchiveEntry(extra, parent, controllers)));
        }
        void Notes(WIVSMMidiPart left, WIVSMMidiPart right)
        {
            WIVSMNote[] originals = left.Notes.ToArray(), copies = right.Notes.ToArray();
            if (originals.Length != copies.Length)
                throw new InvalidDataException("project_preservation: transferred part note count changed.");
            Dictionary<ArchiveNoteSignature, WIVSMNote> targets = [];
            foreach (WIVSMNote item in copies)
                if (!targets.TryAdd(ArchiveNoteKey(item), item))
                    throw new InvalidDataException("project_preservation: ambiguous target notes in transfer.");
            HashSet<ArchiveNoteSignature> seen = [];
            foreach (WIVSMNote item in originals)
            {
                ArchiveNoteSignature key = ArchiveNoteKey(item);
                if (!seen.Add(key) || !targets.TryGetValue(key, out WIVSMNote? copy))
                    throw new InvalidDataException("project_preservation: source note transfer is ambiguous or changed.");
                Add(item, copy ?? throw new InvalidDataException("project_preservation: target note is missing."), ArchiveKey(left), ArchiveKey(right));
            }
        }
        void Part(WIVSMPart left, WIVSMPart right, ArchiveEntity parent, long offset)
        {
            if (left.Type != right.Type || left.Name != right.Name ||
                left.DurationTick.Value != right.DurationTick.Value ||
                checked(left.AbsPosTick.Value + offset) != right.AbsPosTick.Value)
                throw new InvalidDataException("project_preservation: transferred part identity changed.");
            WIVSMTrack[] owners = source.Sequence.Tracks.Where(track =>
                track.Parts.Any(item => ArchiveKey(item) == ArchiveKey(left))).ToArray();
            if (owners.Length != 1)
                throw new InvalidDataException("project_preservation: source part parent is missing or ambiguous.");
            Add(left, right, ArchiveKey(owners[0]), parent);
            if (left is WIVSMMidiPart a && right is WIVSMMidiPart b)
            {
                if (a.IsAi != b.IsAi) throw new InvalidDataException("project_preservation: transferred voice type changed.");
                Notes(a, b);
            }
            else if (left.Type != VSMPartType.Audio || left is WIVSMMidiPart || right is WIVSMMidiPart)
                throw new InvalidDataException("project_preservation: unsupported transferred part kind.");
        }
        if (original is WIVSMTrack leftTrack && duplicate is WIVSMTrack rightTrack)
        {
            if (noteOffset != 0 || leftTrack.Type is not (VSMTrackType.Midi or VSMTrackType.MidiAi or VSMTrackType.Audio) ||
                leftTrack.Type != rightTrack.Type || leftTrack.Name != rightTrack.Name || leftTrack.NumParts != rightTrack.NumParts)
                throw new InvalidDataException("project_preservation: transferred MIDI track identity changed.");
            if (!source.Sequence.Tracks.Any(item => ArchiveKey(item) == ArchiveKey(leftTrack)))
                throw new InvalidDataException("project_preservation: source track is not in the snapshot.");
            Add(leftTrack, rightTrack, null, null);
            Dictionary<ArchivePartSignature, WIVSMPart> targets = [];
            foreach (WIVSMPart item in rightTrack.Parts)
                if (!targets.TryAdd(ArchivePartKey(item), item))
                    throw new InvalidDataException("project_preservation: ambiguous target parts in transfer.");
            HashSet<ArchivePartSignature> seen = [];
            foreach (WIVSMPart item in leftTrack.Parts)
            {
                ArchivePartSignature originalKey = ArchivePartKey(item);
                ArchivePartSignature key = originalKey with { Position = checked(originalKey.Position + partOffset) };
                if (!seen.Add(key) || !targets.TryGetValue(key, out WIVSMPart? copy))
                    throw new InvalidDataException("project_preservation: source part transfer is ambiguous or changed.");
                Part(item, copy ?? throw new InvalidDataException("project_preservation: target part is missing."), ArchiveKey(rightTrack), partOffset);
            }
        }
        else if (original is WIVSMPart leftPart && duplicate is WIVSMPart rightPart)
        {
            if (noteOffset != 0) throw new InvalidDataException("project_preservation: invalid part transfer offset.");
            WIVSMTrack[] owners = target.Sequence.Tracks.Where(track =>
                track.Parts.Any(item => ArchiveKey(item) == ArchiveKey(rightPart))).ToArray();
            if (owners.Length != 1) throw new InvalidDataException("project_preservation: transferred part parent is missing or ambiguous.");
            Part(leftPart, rightPart, ArchiveKey(owners[0]), partOffset);
        }
        else if (original is WIVSMNote leftNote && duplicate is WIVSMNote rightNote)
        {
            ArchiveNoteSignature key = ArchiveNoteKey(leftNote);
            if (partOffset != 0 || leftNote.IsAi != rightNote.IsAi ||
                key with { Position = checked(key.Position + noteOffset) } != ArchiveNoteKey(rightNote))
                throw new InvalidDataException("project_preservation: transferred note identity changed.");
            WIVSMMidiPart parent = rightNote.Parent ?? throw new InvalidDataException("project_preservation: transferred note has no parent.");
            WIVSMMidiPart sourceParent = leftNote.Parent ?? throw new InvalidDataException("project_preservation: source note has no parent.");
            WIVSMMidiTrack sourceTrack = sourceParent.Parent ?? throw new InvalidDataException("project_preservation: source note track is missing.");
            if (!source.Sequence.Tracks.Any(item => ArchiveKey(item) == ArchiveKey(sourceTrack)) ||
                !sourceTrack.Parts.Any(item => ArchiveKey(item) == ArchiveKey(sourceParent)) ||
                !sourceParent.Notes.Any(item => ArchiveKey(item) == ArchiveKey(leftNote)))
                throw new InvalidDataException("project_preservation: source note is not in the snapshot.");
            Add(leftNote, rightNote, ArchiveKey(sourceParent), ArchiveKey(parent));
        }
        else throw new InvalidDataException("project_preservation: unsupported transfer entity kind.");

        foreach ((ArchiveEntity key, ArchiveEntry entry) in pending) to.Live.Add(key, entry);
        if (pending.Any(item => item.Entry.Extra.Count != 0 || item.Entry.Controller is not null)) to.HasEntityExtensions = true;
    }
}
