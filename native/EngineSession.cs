using System.IO;
using System.IO.Compression;
using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Serialization;
using Yamaha.VOCALOID.DSE;
using Yamaha.VOCALOID.VDM;
using Yamaha.VOCALOID.VLC;
using Yamaha.VOCALOID.VSM;

internal sealed class NativeReference(object value, Action<object>? writeBack = null)
{
    internal object Value { get; } = value;
    internal IDisposable? Cursor { get; set; }
    internal void WriteBack() => writeBack?.Invoke(Value);
}

internal sealed class EngineSession
{
    private readonly Dictionary<string, NativeReference> references = new(StringComparer.Ordinal);
    private readonly Dictionary<object, string> identities = new(ReferenceEqualityComparer.Instance);
    private long nextReference;

    internal EngineSession(string id, string directory, WIVSMSequence sequence, string? originalPath, bool dirty)
    {
        Id = id;
        Directory = directory;
        Sequence = sequence;
        OriginalPath = originalPath;
        Dirty = dirty;
        RootRef = Register(sequence);
    }

    internal string Id { get; }
    internal string Directory { get; }
    internal WIVSMSequence Sequence { get; }
    internal string? OriginalPath { get; }
    internal string RootRef { get; }
    internal bool Dirty { get; set; }
    internal string? LastSavedPath { get; set; }
    internal Action<string>? ArchiveBegin { get; set; }
    internal Action<string>? ArchiveEnd { get; set; }
    internal Action<object, object>? ArchiveCopy { get; set; }
    internal Action? ArchiveValidate { get; set; }

    internal object Summary() => new
    {
        session_id = Id,
        title = Sequence.Title,
        track_count = Sequence.NumTrack,
        dirty = Dirty,
        root_ref = RootRef,
        last_saved_path = LastSavedPath
    };

    internal string Register(object value, Action<object>? writeBack = null)
    {
        if (!value.GetType().IsValueType && identities.TryGetValue(value, out string? existing))
            return existing;
        if (references.Count >= 65536)
            throw new InvalidOperationException("Session object reference limit reached.");
        string reference = Id + ":" + (++nextReference).ToString(System.Globalization.CultureInfo.InvariantCulture);
        references.Add(reference, new NativeReference(value, writeBack));
        if (!value.GetType().IsValueType)
            identities.Add(value, reference);
        return reference;
    }

    internal NativeReference Resolve(string? reference)
    {
        if (!references.TryGetValue(reference ?? RootRef, out NativeReference? value))
            throw new KeyNotFoundException("Unknown or expired object reference for this session.");
        return value;
    }

    internal void InvalidateChildren()
    {
        NativeReference root = references[RootRef];
        foreach (NativeReference reference in references.Values)
            reference.Cursor?.Dispose();
        references.Clear();
        identities.Clear();
        references.Add(RootRef, root);
        identities.Add(Sequence, RootRef);
    }

    internal void InvalidateAll()
    {
        foreach (NativeReference reference in references.Values)
            reference.Cursor?.Dispose();
        references.Clear();
        identities.Clear();
    }
}

internal sealed partial class EngineHost : IDisposable
{
    internal const string EngineVersion = "6.13.3.1";
    private const string ProjectValidityEntry = "vocaloid_bridge/phoneme-validity-v1.json";
    private const long MaxArchiveBytes = 8L * 1024 * 1024 * 1024;
    private readonly Dictionary<string, EngineSession> sessions = new(StringComparer.Ordinal);
    private readonly HashSet<WIVSMSequence> ownedSequences = new(ReferenceEqualityComparer.Instance);
    private readonly HashSet<string> ownedDirectories = new(StringComparer.OrdinalIgnoreCase);
    private readonly WIVSMSequenceManager manager;
    private readonly int ownerThread = Environment.CurrentManagedThreadId;
    private DatabaseManager? database;
    private DSEManager? dse;
    private Exception? databaseFailure;
    private Exception? dseFailure;
    private bool databaseAttempted;
    private bool dseAttempted;
    private bool disposed;

    private sealed class ProjectInvalidNote
    {
        [JsonRequired] public int TrackIndex { get; set; }
        [JsonRequired] public int PartIndex { get; set; }
        [JsonRequired] public int NoteIndex { get; set; }
        [JsonRequired] public LibraryNoteValidity Note { get; set; } = new();
    }

    private sealed class ProjectValidityMetadata
    {
        [JsonRequired] public string Format { get; set; } = "";
        [JsonRequired] public int Version { get; set; }
        [JsonRequired] public List<ProjectInvalidNote> Notes { get; set; } = [];
    }

    internal EngineHost(string workspace)
    {
        Workspace = Path.GetFullPath(workspace);
        PathGuard.NoLinks(Workspace);
        if (!System.IO.Directory.Exists(Workspace))
            throw new DirectoryNotFoundException("Workspace does not exist.");
        RuntimeRoot = Path.Combine(Workspace, ".runtime");
        OutputRoot = Path.Combine(Workspace, "output");
        PathGuard.CreateDirectory(RuntimeRoot);
        PathGuard.CreateDirectory(OutputRoot);
        manager = WVSMModuleIF.CreateManager(CacheNamespace, EngineVersion)
            ?? throw new InvalidOperationException("VSM manager creation failed: " + WVSMModuleIF.LastError());
        try
        {
            manager.CacheCapacity = 0;
            if (manager.CacheCapacity != 0)
                throw new InvalidOperationException("Native render cache policy was not applied.");
            EnsureDatabase();
        }
        catch
        {
            manager.Dispose();
            database?.Dispose();
            throw;
        }
    }

    internal string Workspace { get; }
    internal string CacheNamespace { get; } = "VocaloidBridge-" + Guid.NewGuid().ToString("N");
    internal long RenderCacheBytes => manager.CacheCapacity;
    internal string RuntimeRoot { get; }
    internal string OutputRoot { get; }
    internal int SessionCount { get { CheckThread(); return sessions.Count; } }
    internal WIVSMSequenceManager SequenceManager { get { CheckThread(); return manager; } }
    internal DatabaseManager DatabaseManager { get { CheckThread(); return EnsureDatabase(); } }
    internal DSEManager DseManager { get { EnsureVoiceServices(); return dse!; } }

    internal EngineSession GetSession(string id)
    {
        CheckThread();
        return sessions.TryGetValue(id, out EngineSession? session)
            ? session : throw new KeyNotFoundException("Unknown session_id.");
    }

    internal WIVSMSequence GetSequence(string sessionId) => GetSession(sessionId).Sequence;

    internal EngineSession Create(string title, double bpm, int sampleRate)
    {
        CheckThread();
        if (!double.IsFinite(bpm) || bpm < WIVSMTempo.MinValue / 100.0 || bpm > WIVSMTempo.MaxValue / 100.0)
            throw new ArgumentOutOfRangeException(nameof(bpm), "BPM must be finite and between 20 and 300.");
        if (!Enum.IsDefined(typeof(VSMSamplingRate), sampleRate))
            throw new ArgumentOutOfRangeException(nameof(sampleRate), "Supported sample rates: 44100, 48000, 96000.");
        int tempo = checked((int)Math.Round(bpm * 100, MidpointRounding.AwayFromZero));
        (string id, string directory) = NewDirectory();
        WIVSMSequence? sequence = null;
        try
        {
            sequence = manager.CreateSequence(new VSMSequenceData((VSMSamplingRate)sampleRate, 32, 100))
                ?? throw new InvalidOperationException("Native create failed: " + manager.LastError);
            ownedSequences.Add(sequence);
            if (tempo < sequence.GetMinTempoValue() || tempo > sequence.GetMaxTempoValue())
                throw new ArgumentOutOfRangeException(nameof(bpm), "BPM exceeds the native sequence range.");
            sequence.Title = title ?? throw new ArgumentNullException(nameof(title));
            if (sequence.InsertTimeSig(0, new VSMTimeSigEvent(4, 4)) is null ||
                sequence.InsertTempo(VSMRelTick.Zero, tempo) is null || !sequence.Commit(false))
                throw new InvalidOperationException("Native initialization failed: " + sequence.LastError);
            EngineSession session = new(id, directory, sequence, null, true);
            sessions.Add(id, session);
            return session;
        }
        catch
        {
            ReleaseFailedSequence(sequence, directory);
            throw;
        }
    }

    internal EngineSession Open(string path)
    {
        CheckThread();
        if (!Path.IsPathFullyQualified(path) || !string.Equals(Path.GetExtension(path), ".vpr", StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("path must be an absolute VPR filename.");
        path = Path.GetFullPath(path);
        PathGuard.NoLinks(path);
        EnsureVoiceServices();
        (string id, string directory) = NewDirectory();
        WIVSMSequence? sequence = null;
        try
        {
            Extract(path, directory);
            string project = Path.Combine(directory, "Project");
            string json = Path.Combine(project, "sequence.json");
            if (!File.Exists(json))
                throw new InvalidDataException("VPR must contain Project/sequence.json.");
            ValidateOpenRequirements(json);
            sequence = manager.OpenSequence(json, Path.GetDirectoryName(typeof(WVSMModuleIF).Assembly.Location)!,
                new VSMSequenceData(VSMSamplingRate._44100, 32, 100))
                ?? throw new InvalidOperationException("Native open failed: " + manager.LastError);
            ownedSequences.Add(sequence);
            ValidateLoadedTrackKinds(sequence, json);
            RestoreProjectValidity(sequence, directory);
            EngineSession session = new(id, directory, sequence, path, false);
            CaptureArchivePreservation(session, directory);
            sessions.Add(id, session);
            return session;
        }
        catch
        {
            ReleaseFailedSequence(sequence, directory);
            throw;
        }
    }

    internal object Save(string id, string outputName, bool overwrite)
    {
        EngineSession session = GetSession(id);
        string destination = PrepareOutput(session, outputName, ".vpr", overwrite);
        string stage = Path.Combine(session.Directory, "save-" + Guid.NewGuid().ToString("N"));
        PathGuard.CreateDirectory(stage);
        if (session.Sequence.IsStaged && !session.Sequence.Commit(false))
            throw new InvalidOperationException("Native commit failed: " + session.Sequence.LastError);
        ProjectValidityMetadata validity = CaptureProjectValidity(session.Sequence);
        if (!session.Sequence.Save(stage, false))
            throw new InvalidOperationException("Native save failed: " + session.Sequence.LastError);
        string project = Path.Combine(stage, "Project");
        if (!File.Exists(Path.Combine(project, "sequence.json")))
            throw new InvalidDataException("Native Save did not produce Project/sequence.json.");
        PathGuard.TreeNoLinks(project);
        ValidateNativeSnapshot(session.Sequence, Path.Combine(project, "sequence.json"));
        ApplyArchivePreservation(session, stage);
        ApplyFrozenAuthoringState(session, stage);
        string archive = Path.Combine(stage, "saved.vpr");
        WriteProjectArchive(session, stage, archive, validity);
        PathGuard.NoLinks(destination);
        File.Move(archive, destination, overwrite);
        session.LastSavedPath = destination;
        session.Dirty = false;
        return new { session_id = session.Id, path = destination, saved = true, native = true,
                     bridge_phoneme_validity_count = validity.Notes.Count };
    }

    private void WriteProjectArchive(EngineSession session, string stage, string archive, ProjectValidityMetadata validity)
    {
        string project = Path.Combine(stage, "Project");
        PathGuard.TreeNoLinks(project);
        ZipFile.CreateFromDirectory(project, archive, CompressionLevel.Optimal, true);
        if (validity.Notes.Count != 0)
        {
            using ZipArchive zip = ZipFile.Open(archive, ZipArchiveMode.Update);
            using Stream output = zip.CreateEntry(ProjectValidityEntry, CompressionLevel.Optimal).Open();
            JsonSerializer.Serialize(output, validity);
        }
        AddOuterArchiveMembers(session, stage, archive);
        ValidateArchiveExport(archive, stage);
    }

    // Check the actual ZIP central directory against the same extraction bounds
    // before publishing it. The optional limits support tiny synthetic tests.
    private static void ValidateArchiveExport(string path, string root, int maxEntries = 16384, long maxBytes = MaxArchiveBytes)
    {
        if (maxEntries < 0 || maxBytes < 0) throw new ArgumentOutOfRangeException("archive limits");
        using ZipArchive archive = ZipFile.OpenRead(path);
        if (archive.Entries.Count > maxEntries) throw new InvalidDataException("VPR exceeds the archive entry limit.");
        HashSet<string> names = new(StringComparer.OrdinalIgnoreCase), files = new(StringComparer.OrdinalIgnoreCase);
        long total = 0;
        foreach (ZipArchiveEntry entry in archive.Entries)
        {
            string name = entry.FullName.Replace('\\', '/');
            bool isDirectory = name.EndsWith('/');
            string destination = PathGuard.Under(root, isDirectory ? name[..^1] : name);
            int unixType = (entry.ExternalAttributes >> 16) & 0xf000;
            if ((unixType != 0 && unixType != 0x8000 && unixType != 0x4000) ||
                (entry.ExternalAttributes & (int)FileAttributes.ReparsePoint) != 0)
                throw new InvalidDataException("VPR contains a link or special filesystem entry.");
            if (!names.Add(destination)) throw new InvalidDataException("VPR contains duplicate case-insensitive paths.");
            if (entry.Length < 0 || entry.Length > maxBytes - total) throw new InvalidDataException("VPR exceeds the archive extraction size limit.");
            total += entry.Length;
            if (isDirectory && entry.Length != 0) throw new InvalidDataException("VPR directory entry has a payload.");
            if (!isDirectory) files.Add(destination);
        }
        foreach (string name in names)
        {
            string? parent = Path.GetDirectoryName(name);
            while (parent is not null && PathGuard.IsUnder(root, parent))
            {
                if (files.Contains(parent)) throw new InvalidDataException("VPR contains a file/directory path conflict.");
                parent = Path.GetDirectoryName(parent);
            }
        }
    }

    private static ProjectValidityMetadata CaptureProjectValidity(WIVSMSequence sequence)
    {
        ProjectValidityMetadata metadata = new() { Format = "vocaloid-bridge-phoneme-validity", Version = 1 };
        for (int trackIndex = 0; trackIndex < ScoreCount(sequence.NumTrack); trackIndex++)
        {
            WIVSMTrack track = sequence.GetTrack((ulong)trackIndex)
                ?? throw new InvalidDataException("Native track is missing during validity snapshot.");
            if (track.Type is not (VSMTrackType.Midi or VSMTrackType.MidiAi))
                continue;
            WIVSMMidiTrack midi = new(track);
            for (int partIndex = 0; partIndex < ScoreCount(midi.NumParts); partIndex++)
            {
                WIVSMMidiPart part = midi.GetPart((ulong)partIndex)
                    ?? throw new InvalidDataException("Native MIDI part is missing during validity snapshot.");
                for (int noteIndex = 0; noteIndex < ScoreCount(part.NumNotes); noteIndex++)
                {
                    WIVSMNote note = part.GetNote((ulong)noteIndex)
                        ?? throw new InvalidDataException("Native note is missing during validity snapshot.");
                    if (!note.IsValidPhonemes)
                        metadata.Notes.Add(new ProjectInvalidNote
                        {
                            TrackIndex = trackIndex, PartIndex = partIndex, NoteIndex = noteIndex,
                            Note = LibrarySnapshotValidity(note)
                        });
                }
            }
        }
        if (metadata.Notes.Count > 65536)
            throw new InvalidDataException("Project contains too many invalid-phoneme notes.");
        return metadata;
    }

    private static WIVSMNote ProjectValidityNote(WIVSMSequence sequence, ProjectInvalidNote entry)
    {
        if (entry.TrackIndex < 0 || entry.PartIndex < 0 || entry.NoteIndex < 0 || entry.Note is null || entry.Note.IsValid)
            throw new InvalidDataException("Project phoneme-validity metadata contains an invalid note reference.");
        WIVSMTrack track = sequence.GetTrack((ulong)entry.TrackIndex)
            ?? throw new InvalidDataException("Project phoneme-validity track is missing.");
        if (track.Type is not (VSMTrackType.Midi or VSMTrackType.MidiAi))
            throw new InvalidDataException("Project phoneme-validity track is not MIDI.");
        WIVSMMidiPart part = new WIVSMMidiTrack(track).GetPart((ulong)entry.PartIndex)
            ?? throw new InvalidDataException("Project phoneme-validity part is missing.");
        WIVSMNote note = part.GetNote((ulong)entry.NoteIndex)
            ?? throw new InvalidDataException("Project phoneme-validity note is missing.");
        LibraryNoteValidity expected = entry.Note;
        if (note.RelPosTick.Value != expected.Position || note.DurationTick.Value != expected.Duration ||
            note.NoteNumber != expected.Number || note.Lyric != expected.Lyric || note.Phonemes != expected.Phonemes ||
            note.LangID != expected.LanguageId)
            throw new InvalidDataException("Project phoneme-validity metadata does not match the native note.");
        return note;
    }

    private static void RestoreProjectValidity(WIVSMSequence sequence, string directory)
    {
        string path = PathGuard.Under(directory, ProjectValidityEntry);
        if (!File.Exists(path))
            return;
        PathGuard.NoLinks(path);
        using FileStream file = new(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        ProjectValidityMetadata metadata = JsonSerializer.Deserialize<ProjectValidityMetadata>(file)
            ?? throw new InvalidDataException("Project phoneme-validity metadata is empty.");
        ApplyProjectValidity(sequence, metadata);
    }

    private static void ApplyProjectValidity(WIVSMSequence sequence, ProjectValidityMetadata metadata)
    {
        if (metadata.Format != "vocaloid-bridge-phoneme-validity" || metadata.Version != 1 ||
            metadata.Notes is null || metadata.Notes.Count > 65536)
            throw new InvalidDataException("Project phoneme-validity metadata has an invalid format.");
        HashSet<(int Track, int Part, int Note)> seen = [];
        List<(ProjectInvalidNote Entry, WIVSMNote Note)> targets = [];
        foreach (ProjectInvalidNote entry in metadata.Notes)
        {
            if (entry is null || !seen.Add((entry.TrackIndex, entry.PartIndex, entry.NoteIndex)))
                throw new InvalidDataException("Project phoneme-validity metadata has duplicate or null notes.");
            targets.Add((entry, ProjectValidityNote(sequence, entry)));
        }
        foreach ((ProjectInvalidNote entry, WIVSMNote note) in targets)
            if (note.IsValidPhonemes && !note.SetPhonemes(entry.Note.Phonemes, false, entry.Note.LanguageId))
                throw new InvalidOperationException("Native phoneme-validity restoration failed: " + sequence.LastError);
        if (sequence.IsStaged && !sequence.Commit(false))
            throw new InvalidOperationException("Native phoneme-validity restoration commit failed: " + sequence.LastError);
        foreach ((ProjectInvalidNote entry, _) in targets)
            if (ProjectValidityNote(sequence, entry).IsValidPhonemes)
                throw new InvalidDataException("Native phoneme-validity restoration did not persist in the session.");
    }

    private string PrepareOutput(EngineSession session, string outputName, string extension, bool overwrite)
    {
        string destination = PathGuard.Under(OutputRoot, outputName);
        if (!string.Equals(Path.GetExtension(destination), extension, StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("output_name must end in " + extension + ".");
        if (string.Equals(destination, session.OriginalPath, StringComparison.OrdinalIgnoreCase))
            throw new IOException("The original opened project cannot be overwritten.");
        PathGuard.NoLinks(destination);
        if (System.IO.Directory.Exists(destination))
            throw new IOException("Output path is a directory.");
        if (!overwrite && File.Exists(destination))
            throw new IOException("Output exists; choose another name or set overwrite explicitly.");
        PathGuard.CreateDirectory(Path.GetDirectoryName(destination)!);
        return destination;
    }

    internal object RenderPart(string id, ulong trackIndex, ulong partIndex, string outputName, bool overwrite)
    {
        EngineSession session = GetSession(id);
        string destination = PrepareOutput(session, outputName, ".wav", overwrite);
        WIVSMTrack track = session.Sequence.GetTrack(trackIndex)
            ?? throw new ArgumentOutOfRangeException(nameof(trackIndex), "Native track was not found.");
        if (track.Type is not (VSMTrackType.Midi or VSMTrackType.MidiAi))
            throw new ArgumentException("render_part requires a native MIDI or MIDI AI track.");
        EnsureVoiceServices();
        WIVSMMidiTrack midiTrack = track as WIVSMMidiTrack ?? new WIVSMMidiTrack(track);
        WIVSMMidiPart part = midiTrack.GetPart(partIndex)
            ?? throw new ArgumentOutOfRangeException(nameof(partIndex), "Native MIDI part was not found.");
        PrepareRobotVoice(part);
        PrepareSingingSkill(part);
        bool hadStagedChanges = session.Sequence.IsStaged;
        if (!session.Sequence.Commit(false) && (hadStagedChanges || session.Sequence.LastError != VSMResult.NoError))
            throw new InvalidOperationException("Native pre-render commit failed: " + session.Sequence.LastError);
        PathGuard.NoLinks(session.Directory);
        string temporary = Path.Combine(session.Directory, "render-" + Guid.NewGuid().ToString("N") + ".wav");
        var render = RenderNativePart(session.Sequence, part, temporary);
        PathGuard.NoLinks(temporary);
        var wave = InspectWave(temporary);
        PathGuard.NoLinks(destination);
        File.Move(temporary, destination, overwrite);
        return new
        {
            session_id = id,
            path = destination,
            native = true,
            lua_result = render.LuaResult.ToString(),
            render_observation = render.Observation,
            result = "AsyncRenderingCompleted",
            bytes = wave.Bytes,
            channels = wave.Channels,
            sample_rate = wave.SampleRate,
            bits_per_sample = wave.Bits,
            frames = wave.Frames
        };
    }

    private static (VLCResult LuaResult, object Observation) RenderNativePart(WIVSMSequence sequence, WIVSMMidiPart part, string output)
    {
        if (sequence.GetSamplingRate() != VSMSamplingRate._44100)
            throw new NotSupportedException("Native vocal-part synthesis requires a 44100 Hz project; mixdown output sample_rate is independent.");
        Stopwatch elapsed = Stopwatch.StartNew();
        nint controller = LuaControllerIF.CreateController();
        if (controller == nint.Zero)
            throw new InvalidOperationException("Native MIDI controller initialization failed: " + LuaControllerIF.LastError);
        using WIVSMRendererObserver observer = new();
        string? cancellation = null;
        bool started = false, completed = false;
        bool beforeValid = part.HasValidRenderedWave, beforeFinished = sequence.IsFinishedRendering;
        observer.Started += (_, details) => { if (details.MidiPart.Equals(part)) started = true; };
        observer.Completed += (_, details) => { if (details.MidiPart.Equals(part)) completed = true; };
        observer.Canceled += (_, details) =>
        {
            if (details.MidiPart.Equals(part))
                cancellation = details.CancelReason.ToString();
        };
        bool attached = false;
        try
        {
            sequence.SetLuaController(controller);
            sequence.BlockRenderingEnabled = WIVSMSequence.DefaultBlockRenderingEnabled;
            sequence.BlockRenderingLengthMsec = WIVSMSequence.DefaultBlockRenderingBlockSize;
            sequence.BlockRenderingPartDurationThresholdMsec = WIVSMSequence.DefaultBlockRenderingPartDurationThresholdMsec;
            while (sequence.InvokeRendererObserver()) { }
            attached = sequence.AddRendererObserver(observer);
            if (!attached)
                throw new InvalidOperationException("Native renderer observer could not be attached: " + sequence.LastError);
            sequence.SetActivePart(part);
            sequence.StartAsyncRendering();
            bool afterStartFinished = sequence.IsFinishedRendering;
            while (true)
            {
                for (int notification = 0; notification < 64 && sequence.InvokeRendererObserver(); notification++) { }
                if (cancellation is not null)
                    throw new InvalidOperationException("Native rendering cancelled: " + cancellation);
                if (part.HasValidRenderedWave && sequence.IsFinishedRendering)
                    break;
                if (elapsed.Elapsed > TimeSpan.FromMinutes(2))
                {
                    VSMRendererProgress progress = part.RendererProgress;
                    throw new TimeoutException($"Native part rendering timed out: part={part.Name}, first_end={progress.FirstEnd}, second_begin={progress.SecondBegin}, second_end={progress.SecondEnd}, paused={progress.IsPaused}, finished={sequence.IsFinishedRendering}, started={started}, completed={completed}, valid_wave={part.HasValidRenderedWave}.");
                }
                Thread.Sleep(20);
            }
            string rendered = part.WaveFilePath;
            if (string.IsNullOrEmpty(rendered) || !File.Exists(rendered))
                throw new InvalidDataException("Native renderer reported completion without a WAV file.");
            File.Copy(rendered, output, false);
            VSMRendererProgress finishedProgress = part.RendererProgress;
            return (LuaControllerIF.LastError, new
            {
                before_valid_wave = beforeValid, before_finished = beforeFinished, after_start_finished = afterStartFinished,
                started, completed, finished = sequence.IsFinishedRendering, first_end = finishedProgress.FirstEnd,
                second_begin = finishedProgress.SecondBegin, second_end = finishedProgress.SecondEnd
            });
        }
        finally
        {
            sequence.StopAsyncRendering();
            sequence.SetActivePart(null);
            if (attached)
                sequence.RemoveRendererObserver(observer);
            sequence.SetLuaController(nint.Zero);
            LuaControllerIF.DestroyController(controller);
        }
    }

    private static (long Bytes, ushort Channels, uint SampleRate, ushort Bits, long Frames) InspectWave(string path)
    {
        using FileStream file = new(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        using BinaryReader reader = new(file);
        if (file.Length < 44 || reader.ReadUInt32() != 0x46464952)
            throw new InvalidDataException("Native render did not produce a RIFF WAV file.");
        long end = reader.ReadUInt32() + 8L;
        if (end > file.Length || end < 44 || reader.ReadUInt32() != 0x45564157)
            throw new InvalidDataException("Native WAV container is truncated or invalid.");
        ushort channels = 0, bits = 0, alignment = 0;
        uint sampleRate = 0;
        long dataBytes = 0;
        while (file.Position + 8 <= end)
        {
            uint chunk = reader.ReadUInt32();
            uint size = reader.ReadUInt32();
            long payloadEnd = file.Position + size;
            long next = payloadEnd + (size & 1);
            if (payloadEnd > end || (next > end && (chunk != 0x61746164 || payloadEnd != end)))
                throw new InvalidDataException($"Native WAV chunk is truncated: id=0x{chunk:x8}, payload_end={payloadEnd}, padded_end={next}, riff_end={end}, file_length={file.Length}.");
            next = Math.Min(next, end);
            if (chunk == 0x20746d66)
            {
                if (size < 16)
                    throw new InvalidDataException("Native WAV fmt chunk is invalid.");
                ushort format = reader.ReadUInt16();
                channels = reader.ReadUInt16();
                sampleRate = reader.ReadUInt32();
                uint byteRate = reader.ReadUInt32();
                alignment = reader.ReadUInt16();
                bits = reader.ReadUInt16();
                if (format != 1 && format != 3 && format != 0xfffe)
                    throw new InvalidDataException("Native WAV is not PCM or IEEE float.");
                if (channels == 0 || sampleRate == 0 || alignment == 0 || bits == 0 ||
                    byteRate != (long)sampleRate * alignment || alignment != channels * ((bits + 7) / 8))
                    throw new InvalidDataException("Native WAV format fields are inconsistent.");
                if (format == 0xfffe && size < 40)
                    throw new InvalidDataException("Native WAV extensible format is truncated.");
            }
            else if (chunk == 0x61746164)
                dataBytes += size;
            file.Position = next;
        }
        if (channels == 0 || alignment == 0 || dataBytes == 0 || dataBytes % alignment != 0)
            throw new InvalidDataException("Native WAV contains no complete audio frames.");
        return (file.Length, channels, sampleRate, bits, dataBytes / alignment);
    }

    internal object Close(string id, bool discard)
    {
        EngineSession session = GetSession(id);
        if ((session.Dirty || HasMidiRecording(session)) && !discard)
            throw new InvalidOperationException("Unsaved changes or a pending MIDI recording; save/stop it or set discard=true.");
        CancelMidiRecording(session);
        if (transport?.SessionId == id)
            ReleaseTransport();
        if (!session.Sequence.Close() || session.Sequence.IsOpen)
            throw new InvalidOperationException("Native close failed: " + session.Sequence.LastError);
        ReleaseArchivePreservation(session);
        ForgetFrozenAuthoring(session);
        ownedSequences.Remove(session.Sequence);
        session.InvalidateAll();
        sessions.Remove(id);
        CleanupImportedProjects(id);
        Cleanup(session.Directory);
        return new { session_id = id, closed = true };
    }

    internal object Voices()
    {
        CheckThread();
        DatabaseManager current = EnsureDatabase();
        List<object> voices = [];
        foreach (VDMVoiceBankType type in Enum.GetValues<VDMVoiceBankType>())
        {
            ulong count = current.GetNumVoiceBanks(type);
            if (count > 4096)
                throw new InvalidDataException("Native voicebank count exceeds the 4096-bank limit.");
            for (ulong index = 0; index < count; index++)
            {
                VoiceBank voice = current.GetVoiceBankByIndex(index, type)
                    ?? throw new InvalidOperationException("Native voicebank lookup failed.");
                if (voice.LangIDSize > 256)
                    throw new InvalidDataException("Native language count exceeds the 256-language limit.");
                voices.Add(new
                {
                    name = voice.Name,
                    component_name = voice.ComponentName,
                    comp_id = voice.CompID,
                    kind = type.ToString(),
                    native_lang_id = voice.NativeLangID,
                    lang_ids = voice.LangIDs,
                    available_in_sequence = voice.IsAvailableInSequence,
                    available_for_voice_changer = voice.IsAvailableForVoiceChanger,
                    synthesizable_version = voice.IsSynthesizableVersion
                });
            }
        }
        return new { voices };
    }

    internal void EnsureVoiceServices()
    {
        CheckThread();
        DatabaseManager current = EnsureDatabase();
        if (dse is not null && dseFailure is null)
            return;
        if (dseAttempted)
            throw new InvalidOperationException("DSE initialization previously failed: " + dseFailure?.Message, dseFailure);
        dseAttempted = true;
        try
        {
            dse = DSEManagerIF.CreateManager(current)
                ?? throw new InvalidOperationException("DSEManagerIF.CreateManager returned null.");
            manager.SetDSEManager(dse);
            LicenseResult editor = LicenseResult.Undefined;
            LicenseResult lite = LicenseResult.Undefined;
            foreach (Yamaha.VOCALOID.DSE.License license in dse.GetLicenses())
            {
                if (license.CompType != Yamaha.VOCALOID.DSE.License.Type.Application)
                    continue;
                if (license.CompID == Yamaha.VOCALOID.Identifier.Component.EditorId)
                    editor = license.Result;
                else if (license.CompID == Yamaha.VOCALOID.Identifier.Component.EditorLiteId)
                    lite = license.Result;
            }
            bool validEditor = editor is LicenseResult.ValidLeaseFile or LicenseResult.PaidOffLeaseFile or LicenseResult.ValidExpiryKey or LicenseResult.NoError;
            bool validLite = lite is LicenseResult.ValidLeaseFile or LicenseResult.PaidOffLeaseFile or LicenseResult.ValidExpiryKey or LicenseResult.NoError;
            manager.SetYvs(validEditor ? YVS.CCAD9AC02E2B : validLite ? YVS.E9413638C757 : YVS.A91D77BC1F12);
        }
        catch (Exception error)
        {
            dseFailure = error;
            throw;
        }
    }

    private DatabaseManager EnsureDatabase()
    {
        if (database is not null && databaseFailure is null)
            return database;
        if (databaseAttempted)
            throw new InvalidOperationException("Database initialization previously failed: " + databaseFailure?.Message, databaseFailure);
        databaseAttempted = true;
        try
        {
            VDMError result = default;
            string explib = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonProgramFiles), "VOCALOID6", "Explib");
            database = DatabaseManagerIF.CreateDatabaseManager("VOCALOID6", explib, ref result)
                ?? throw new InvalidOperationException("DatabaseManagerIF.CreateDatabaseManager failed: " + result);
            if (result != VDMError.None)
                throw new InvalidOperationException("Database initialization failed: " + result);
            manager.SetDatabaseManager(database);
            return database;
        }
        catch (Exception error)
        {
            databaseFailure = error;
            throw;
        }
    }

    private (string Id, string Directory) NewDirectory()
    {
        string id = Guid.NewGuid().ToString("N");
        string directory = PathGuard.Under(RuntimeRoot, id);
        if (System.IO.Directory.Exists(directory) || File.Exists(directory))
            throw new IOException("Session directory already exists.");
        PathGuard.CreateDirectory(directory);
        ownedDirectories.Add(directory);
        return (id, directory);
    }

    private static void Extract(string path, string directory)
    {
        using FileStream input = new(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        using ZipArchive archive = new(input, ZipArchiveMode.Read);
        if (archive.Entries.Count > 16384)
            throw new InvalidDataException("VPR exceeds the 16384-entry limit.");
        HashSet<string> names = new(StringComparer.OrdinalIgnoreCase);
        long total = 0;
        byte[] buffer = new byte[65536];
        foreach (ZipArchiveEntry entry in archive.Entries)
        {
            string name = entry.FullName.Replace('\\', '/');
            bool isDirectory = name.EndsWith('/');
            string relative = isDirectory ? name[..^1] : name;
            string destination = PathGuard.Under(directory, relative);
            int unixType = (entry.ExternalAttributes >> 16) & 0xf000;
            if ((unixType != 0 && unixType != 0x8000 && unixType != 0x4000) ||
                (entry.ExternalAttributes & (int)FileAttributes.ReparsePoint) != 0)
                throw new InvalidDataException("VPR contains a link or special filesystem entry.");
            if (!names.Add(destination))
                throw new InvalidDataException("VPR contains duplicate case-insensitive paths.");
            if (entry.Length < 0 || entry.Length > MaxArchiveBytes - total)
                throw new InvalidDataException("VPR exceeds the 8 GiB extraction limit.");
            total += entry.Length;
            if (isDirectory)
            {
                if (entry.Length != 0)
                    throw new InvalidDataException("VPR directory entry has a payload.");
                PathGuard.CreateDirectory(destination);
                continue;
            }
            PathGuard.CreateDirectory(Path.GetDirectoryName(destination)!);
            PathGuard.NoLinks(destination);
            using Stream source = entry.Open();
            using FileStream target = new(destination, FileMode.CreateNew, FileAccess.Write, FileShare.None);
            long copied = 0;
            int read;
            while ((read = source.Read(buffer, 0, buffer.Length)) != 0)
            {
                copied += read;
                if (copied > entry.Length)
                    throw new InvalidDataException("VPR entry exceeds its declared length.");
                target.Write(buffer, 0, read);
            }
            if (copied != entry.Length)
                throw new InvalidDataException("VPR entry is truncated.");
        }
    }

    private void Cleanup(string directory)
    {
        if (!PathGuard.IsUnder(RuntimeRoot, directory))
            throw new IOException("Refusing cleanup outside the owned runtime root.");
        if (System.IO.Directory.Exists(directory))
        {
            PathGuard.TreeNoLinks(directory);
            System.IO.Directory.Delete(directory, true);
        }
        ownedDirectories.Remove(directory);
    }

    private void ReleaseFailedSequence(WIVSMSequence? sequence, string directory)
    {
        if (sequence is not null)
        {
            if (sequence.IsOpen && !sequence.Close())
                return;
            ownedSequences.Remove(sequence);
        }
        Cleanup(directory);
    }

    private void CheckThread()
    {
        ObjectDisposedException.ThrowIf(disposed, this);
        if (Environment.CurrentManagedThreadId != ownerThread || Thread.CurrentThread.GetApartmentState() != ApartmentState.STA)
            throw new InvalidOperationException("All native operations must execute on the owning STA thread.");
    }

    public void Dispose()
    {
        if (disposed)
            return;
        CheckThread();
        List<Exception> errors = [];
        foreach (EngineSession session in sessions.Values)
            try { CancelMidiRecording(session); } catch (Exception error) { errors.Add(error); }
        try { ReleaseTransport(); } catch (Exception error) { errors.Add(error); }
        foreach (EngineSession session in sessions.Values)
            try { ReleaseArchivePreservation(session); } catch (Exception error) { errors.Add(error); }
        foreach (EngineSession session in sessions.Values)
            ForgetFrozenAuthoring(session);
        try { DisposeProjectClipboards(); } catch (Exception error) { errors.Add(error); }
        foreach (WIVSMSequence sequence in ownedSequences)
        {
            try
            {
                if (sequence.IsOpen && !sequence.Close())
                    throw new InvalidOperationException("Native shutdown close failed: " + sequence.LastError);
            }
            catch (Exception error) { errors.Add(error); }
        }
        foreach (EngineSession session in sessions.Values)
            session.InvalidateAll();
        try { DisposeLibraryServices(); } catch (Exception error) { errors.Add(error); }
        try { DisposeAudioServices(); } catch (Exception error) { errors.Add(error); }
        bool managerReleased = false;
        try { manager.Dispose(); managerReleased = true; } catch (Exception error) { errors.Add(error); }
        try { dse?.Dispose(); } catch (Exception error) { errors.Add(error); }
        try { database?.Dispose(); } catch (Exception error) { errors.Add(error); }
        foreach (string directory in ownedDirectories.ToArray())
        {
            try { Cleanup(directory); } catch (Exception error) { errors.Add(error); }
        }
        if (managerReleased)
        {
            string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            foreach (string kind in new[] { "VSM", "VSMCaches" })
            {
                string root = Path.Combine(local, "VOCALOID6", kind);
                string cache = PathGuard.Under(root, CacheNamespace);
                try
                {
                    if (System.IO.Directory.Exists(cache))
                    {
                        PathGuard.TreeNoLinks(cache);
                        System.IO.Directory.Delete(cache, true);
                    }
                }
                catch (Exception error) { errors.Add(error); }
            }
        }
        sessions.Clear();
        ownedSequences.Clear();
        disposed = true;
        if (errors.Count != 0)
            throw new AggregateException("Native shutdown did not fully succeed.", errors);
    }
}

internal static class PathGuard
{
    internal static bool IsUnder(string root, string path) => path.StartsWith(
        Path.TrimEndingDirectorySeparator(Path.GetFullPath(root)) + Path.DirectorySeparatorChar,
        StringComparison.OrdinalIgnoreCase);

    internal static string Under(string root, string relative)
    {
        if (string.IsNullOrWhiteSpace(relative) || Path.IsPathRooted(relative))
            throw new ArgumentException("A nonempty relative path is required.");
        string[] parts = relative.Replace('\\', '/').Split('/');
        foreach (string part in parts)
        {
            if (part.Length == 0 || part is "." or ".." || part.EndsWith('.') || part.EndsWith(' ') ||
                part.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0)
                throw new ArgumentException("Path contains an unsafe Windows filename component.");
            string stem = part.Split('.')[0].ToUpperInvariant();
            if (stem is "CON" or "PRN" or "AUX" or "NUL" or "CLOCK$" or "CONIN$" or "CONOUT$" ||
                (stem.Length == 4 && (stem.StartsWith("COM", StringComparison.Ordinal) || stem.StartsWith("LPT", StringComparison.Ordinal)) &&
                 "123456789\u00b9\u00b2\u00b3".Contains(stem[3])))
                throw new ArgumentException("Reserved Windows device filename.");
        }
        string result = Path.GetFullPath(Path.Combine(root, Path.Combine(parts)));
        if (!IsUnder(root, result))
            throw new ArgumentException("Path escapes its root.");
        return result;
    }

    internal static void NoLinks(string path)
    {
        string? current = Path.GetFullPath(path);
        while (!string.IsNullOrEmpty(current))
        {
            try
            {
                if ((File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                    throw new IOException("Links and reparse points are not permitted.");
            }
            catch (FileNotFoundException) { }
            catch (DirectoryNotFoundException) { }
            string? parent = Path.GetDirectoryName(Path.TrimEndingDirectorySeparator(current));
            if (string.Equals(current, parent, StringComparison.OrdinalIgnoreCase))
                break;
            current = parent;
        }
    }

    internal static void CreateDirectory(string path)
    {
        NoLinks(path);
        Directory.CreateDirectory(path);
        NoLinks(path);
    }

    internal static void TreeNoLinks(string path)
    {
        NoLinks(path);
        foreach (string child in Directory.EnumerateFileSystemEntries(path))
        {
            NoLinks(child);
            if ((File.GetAttributes(child) & FileAttributes.Directory) != 0)
                TreeNoLinks(child);
        }
    }
}
