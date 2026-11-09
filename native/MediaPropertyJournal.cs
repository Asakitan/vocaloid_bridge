using System.Buffers.Binary;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.Win32.SafeHandles;

internal sealed class MediaLibraryLease : IDisposable
{
    private readonly Mutex mutex;
    internal MediaLibraryLease(string workspace)
    {
        string root = Path.TrimEndingDirectorySeparator(Path.GetFullPath(workspace)).ToUpperInvariant();
        string key = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(root)));
        mutex = new Mutex(false, "Local\\VocaloidBridge.MediaLibrary." + key);
        try
        {
            if (!mutex.WaitOne(0)) throw new IOException("The media library is busy in another bridge process.");
        }
        catch (AbandonedMutexException) { /* Ownership was acquired; the journal is recovered before use. */ }
        catch { mutex.Dispose(); throw; }
    }
    public void Dispose() { mutex.ReleaseMutex(); mutex.Dispose(); }
}

internal sealed class MediaPropertyJournal : IDisposable
{
    private const string Format = "vocaloid-media-property-journal";
    private sealed record Record(string Format, int Version, string Token, string ClipId, string ClipIdentity,
        string ClipHash, string OriginalIdentity, string OriginalHash, string CandidateIdentity, string CandidateHash);
    private sealed record Decision(int Version, string Choice, string JournalHash, string AcceptedIdentity, string AcceptedHash);
    private sealed record Observed(string Identity, string Hash);

    private readonly string workspace, id, stage, target;
    private readonly MediaLibraryLease lease;
    private FileStream? clip;
    private BoundFile? original, candidate;
    private Record? record;
    internal byte[] Original { get; }
    internal bool Committed { get; private set; }
    internal Action<string>? Checkpoint { get; set; }

    internal MediaPropertyJournal(string workspace, string id, string stage)
    {
        this.workspace = Path.GetFullPath(workspace);
        ValidateId(id); this.id = id;
        this.stage = Path.GetFullPath(stage);
        string root = JournalRoot(workspace);
        if (Path.GetDirectoryName(this.stage) != root || !Guid.TryParseExact(Path.GetFileName(stage), "N", out _))
            throw new IOException("Invalid owned media journal directory.");
        PathGuard.TreeNoLinks(stage);
        target = Target(workspace, id);
        lease = new MediaLibraryLease(workspace);
        try
        {
            clip = OpenClip(workspace, id);
            original = BoundFile.Open(target, false);
            Original = original.Read();
            WriteMarker(Path.Combine(stage, "owner.json"), JsonSerializer.SerializeToUtf8Bytes(new { format = Format, version = 1, clip_id = id }));
        }
        catch { CloseHandles(); lease.Dispose(); throw; }
    }

    internal void Publish(byte[] updated)
    {
        if (record is not null || original is null || clip is null) throw new InvalidOperationException("Media journal already prepared.");
        if (updated.Length > 16 * 1024 * 1024) throw new IOException("Media properties exceed 16 MiB.");
        WriteDurable(Path.Combine(stage, "original.json"), Original);
        WriteDurable(Path.Combine(stage, "candidate.json"), updated);
        candidate = BoundFile.Open(Path.Combine(stage, "publication.json"), true);
        candidate.Write(updated);
        record = new(Format, 1, Path.GetFileName(stage), id, Identity(clip.SafeFileHandle), Hash(clip),
            original.Identity, Hash(Original), candidate.Identity, Hash(updated));
        WriteMarker(Path.Combine(stage, "journal.json"), JsonSerializer.SerializeToUtf8Bytes(record));
        Checkpoint?.Invoke("prepared");
        original.Rename(Path.Combine(stage, "displaced.json"));
        original.Flush();
        Checkpoint?.Invoke("detached");
        candidate.Rename(target);
        candidate.Flush();
        Checkpoint?.Invoke("published");
        CloseHandles();
    }

    internal void Complete()
    {
        Record expected = record ?? throw new InvalidOperationException("Media publication was not prepared.");
        using FileStream boundClip = OpenClip(workspace, id);
        VerifyClip(boundClip, expected);
        using BoundFile current = BoundFile.Open(target, false);
        if (current.Identity != expected.CandidateIdentity || Hash(current.Read()) != expected.CandidateHash)
            throw new IOException("Published media property was changed by another writer; recovery data retained.");
        WriteMarker(Path.Combine(stage, "committed.json"), JsonSerializer.SerializeToUtf8Bytes(expected));
        Committed = true;
        Checkpoint?.Invoke("committed");
        RemoveStage(stage);
    }

    internal void Rollback()
    {
        CloseHandles();
        RecoverOne(workspace, stage);
    }

    internal static bool RecoverAll(string workspace)
    {
        using MediaLibraryLease lease = new(workspace);
        string root = JournalRoot(workspace);
        if (!Directory.Exists(root)) return false;
        PathGuard.NoLinks(root);
        bool recovered = false;
        foreach (string stage in Directory.EnumerateDirectories(root).ToArray())
        {
            string name = Path.GetFileName(stage);
            if (name.StartsWith("completed-", StringComparison.Ordinal) && Guid.TryParseExact(name[10..], "N", out _))
            {
                RemoveStage(stage);
                recovered = true;
                continue;
            }
            if (!Guid.TryParseExact(Path.GetFileName(stage), "N", out _)) continue;
            if (!File.Exists(Path.Combine(stage, "journal.json")) && !File.Exists(Path.Combine(stage, "owner.json"))) continue;
            RecoverOne(workspace, stage);
            recovered = true;
        }
        return recovered;
    }

    internal static object ListPending(string workspace)
    {
        using MediaLibraryLease lease = new(workspace);
        string root = JournalRoot(workspace);
        if (!Directory.Exists(root)) return new { journals = Array.Empty<object>() };
        PathGuard.NoLinks(root);
        List<object> journals = [];
        foreach (string stage in Directory.EnumerateDirectories(root).OrderBy(path => path, StringComparer.Ordinal))
        {
            string token = Path.GetFileName(stage);
            if (!Guid.TryParseExact(token, "N", out _) || !File.Exists(Path.Combine(stage, "journal.json"))) continue;
            try
            {
                PathGuard.TreeNoLinks(stage);
                Record record = ReadRecord(Path.Combine(stage, "journal.json"), stage);
                Observed current = ObserveFile(Target(workspace, record.ClipId));
                Observed clip = ObserveFile(ClipPath(workspace, record.ClipId));
                string state = File.Exists(Path.Combine(stage, "committed.json")) ? "committed"
                    : current.Hash == record.OriginalHash ? "original"
                    : current.Identity == record.CandidateIdentity && current.Hash == record.CandidateHash ? "candidate"
                    : current.Identity.Length == 0 ? "missing" : "conflict";
                journals.Add(new { token, clip_id = record.ClipId, state,
                    source_matches = clip.Identity == record.ClipIdentity && clip.Hash == record.ClipHash,
                    revision = Revision(stage, current, clip), current_hash = current.Hash,
                    original_hash = record.OriginalHash, candidate_hash = record.CandidateHash, path = stage });
            }
            catch (Exception error) { journals.Add(new { token, state = "unreadable", error = error.Message }); }
        }
        return new { journals };
    }

    internal static object Resolve(string workspace, string token, string choice, string expectedRevision, Action<string>? checkpoint = null)
    {
        if (!Guid.TryParseExact(token, "N", out _)) throw new ArgumentException("Invalid journal token.");
        if (choice is not ("keep_current" or "restore_original")) throw new ArgumentException("choice must be keep_current or restore_original.");
        using MediaLibraryLease lease = new(workspace);
        string stage = PathGuard.Under(JournalRoot(workspace), token);
        PathGuard.TreeNoLinks(stage);
        Record record = ReadRecord(Path.Combine(stage, "journal.json"), stage);
        if (File.Exists(Path.Combine(stage, "committed.json")) || File.Exists(Path.Combine(stage, "rolled-back.json")))
            throw new InvalidOperationException("This journal is already completed; ordinary media access will clean it.");
        string clipPath = ClipPath(workspace, record.ClipId), target = Target(workspace, record.ClipId);
        PathGuard.NoLinks(clipPath);
        using (FileStream? clip = File.Exists(clipPath) ? new(clipPath, FileMode.Open, FileAccess.Read, FileShare.Read) : null)
        using (BoundFile? current = File.Exists(target) ? BoundFile.Open(target, false) : null)
        {
            byte[]? currentBytes = current?.Read();
            Observed observed = current is null ? new("", "") : new(current.Identity, Hash(currentBytes!));
            Observed observedClip = clip is null ? new("", "") : new(Identity(clip.SafeFileHandle), Hash(clip));
            if (Revision(stage, observed, observedClip) != expectedRevision)
                throw new IOException("Journal revision changed; inspect the current conflict before resolving.");
            if (choice == "restore_original" && (observedClip.Identity != record.ClipIdentity || observedClip.Hash != record.ClipHash))
                throw new IOException("The media clip identity changed; original properties will not be assigned to another clip.");
            if (currentBytes is not null)
                WriteDurable(Path.Combine(stage, "accepted-current-" + Guid.NewGuid().ToString("N") + ".json"), currentBytes);
            string decisionPath = Path.Combine(stage, "resolution.json");
            if (File.Exists(decisionPath))
            {
                using BoundFile previous = BoundFile.Open(decisionPath, false);
                previous.Rename(Path.Combine(stage, "resolution-history-" + Guid.NewGuid().ToString("N") + ".json"));
                previous.Flush();
            }
            Decision decision = new(1, choice, Hash(File.ReadAllBytes(Path.Combine(stage, "journal.json"))), observed.Identity, observed.Hash);
            WriteMarker(decisionPath, JsonSerializer.SerializeToUtf8Bytes(decision));
            checkpoint?.Invoke("decision");
        }
        RecoverOne(workspace, stage);
        return new { resolved = true, token, clip_id = record.ClipId, choice,
            recovery_archive = Path.Combine(HistoryRoot(workspace), token) };
    }

    private static Observed ObserveFile(string path)
    {
        PathGuard.NoLinks(path);
        if (!File.Exists(path)) return new("", "");
        using FileStream file = new(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        return new(Identity(file.SafeFileHandle), Hash(file));
    }

    private static string Revision(string stage, Observed current, Observed clip)
    {
        string decision = Path.Combine(stage, "resolution.json");
        return Hash(Encoding.UTF8.GetBytes(string.Join("|", Hash(File.ReadAllBytes(Path.Combine(stage, "journal.json"))),
            current.Identity, current.Hash, clip.Identity, clip.Hash, File.Exists(decision) ? Hash(File.ReadAllBytes(decision)) : "")));
    }

    private static void RecoverOne(string workspace, string stage)
    {
        PathGuard.TreeNoLinks(stage);
        if (!File.Exists(Path.Combine(stage, "journal.json")))
        {
            // A live file is never detached before the durable journal is written.
            using JsonDocument owner = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(stage, "owner.json")));
            if (owner.RootElement.GetProperty("format").GetString() != Format) throw new IOException("Unknown media staging owner.");
            RemoveStage(stage);
            return;
        }
        Record journal = ReadRecord(Path.Combine(stage, "journal.json"), stage);
        Decision? decision = null;
        string decisionPath = Path.Combine(stage, "resolution.json");
        if (File.Exists(decisionPath))
        {
            decision = JsonSerializer.Deserialize<Decision>(File.ReadAllBytes(decisionPath)) ?? throw new IOException("Invalid recovery decision.");
            if (decision.Version != 1 || decision.Choice is not ("keep_current" or "restore_original") ||
                decision.JournalHash != Hash(File.ReadAllBytes(Path.Combine(stage, "journal.json"))))
                throw new IOException("Recovery decision does not match its journal.");
            if (decision.Choice == "keep_current") { ArchiveResolved(workspace, stage); return; }
        }
        string marker = File.Exists(Path.Combine(stage, "committed.json")) ? "committed.json" : "rolled-back.json";
        if (File.Exists(Path.Combine(stage, marker)))
        {
            if (ReadRecord(Path.Combine(stage, marker), stage) != journal)
                throw new IOException("Media completion marker does not match its journal.");
            if (decision is null) RemoveStage(stage); else ArchiveResolved(workspace, stage);
            return;
        }
        byte[] saved = File.ReadAllBytes(Path.Combine(stage, "original.json"));
        if (Hash(saved) != journal.OriginalHash) throw new IOException("Media original snapshot failed integrity validation.");
        using FileStream clip = OpenClip(workspace, journal.ClipId);
        VerifyClip(clip, journal);
        string target = Target(workspace, journal.ClipId);
        if (File.Exists(target))
        {
            using BoundFile current = BoundFile.Open(target, false);
            string hash = Hash(current.Read());
            if (hash == journal.OriginalHash)
            {
                WriteMarker(Path.Combine(stage, "rolled-back.json"), JsonSerializer.SerializeToUtf8Bytes(journal));
                if (decision is null) RemoveStage(stage); else ArchiveResolved(workspace, stage);
                return;
            }
            bool accepted = decision is not null && current.Identity == decision.AcceptedIdentity && hash == decision.AcceptedHash;
            if (!accepted && (current.Identity != journal.CandidateIdentity || hash != journal.CandidateHash))
                throw new IOException("External media property conflict; current file preserved, journal retained at " + stage);
            current.Rename(Path.Combine(stage, "rollback-" + Guid.NewGuid().ToString("N") + ".json"));
            current.Flush();
        }
        string displaced = Path.Combine(stage, "displaced.json");
        if (File.Exists(displaced))
        {
            using BoundFile old = BoundFile.Open(displaced, false);
            if (old.Identity != journal.OriginalIdentity || Hash(old.Read()) != journal.OriginalHash)
                throw new IOException("Displaced media original does not match the journal.");
            old.Rename(target); old.Flush();
        }
        else
        {
            using BoundFile restore = BoundFile.Open(Path.Combine(stage, "restore-" + Guid.NewGuid().ToString("N") + ".json"), true);
            restore.Write(saved); restore.Rename(target); restore.Flush();
        }
        WriteMarker(Path.Combine(stage, "rolled-back.json"), JsonSerializer.SerializeToUtf8Bytes(journal));
        if (decision is null) RemoveStage(stage); else ArchiveResolved(workspace, stage);
    }

    private static Record ReadRecord(string path, string stage)
    {
        Record record = JsonSerializer.Deserialize<Record>(File.ReadAllBytes(path)) ?? throw new IOException("Empty media journal.");
        ValidateId(record.ClipId);
        if (record.Format != Format || record.Version != 1 || record.Token != Path.GetFileName(stage) ||
            new[] { record.ClipHash, record.OriginalHash, record.CandidateHash }.Any(value => value is null || value.Length != 64 || value.Any(c => !Uri.IsHexDigit(c))) ||
            new[] { record.ClipIdentity, record.OriginalIdentity, record.CandidateIdentity }.Any(value => string.IsNullOrEmpty(value)))
            throw new IOException("Invalid media journal metadata.");
        return record;
    }

    private static void VerifyClip(FileStream clip, Record record)
    {
        if (Identity(clip.SafeFileHandle) != record.ClipIdentity || Hash(clip) != record.ClipHash)
            throw new IOException("Media clip identity changed; property recovery stopped.");
    }

    private static FileStream OpenClip(string workspace, string id)
    {
        string path = ClipPath(workspace, id);
        PathGuard.NoLinks(path);
        FileStream stream = new(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        try
        {
            using JsonDocument data = JsonDocument.Parse(stream);
            if (data.RootElement.ValueKind != JsonValueKind.Object)
                throw new IOException("Media clip root must be an object.");
            stream.Position = 0;
            return stream;
        }
        catch { stream.Dispose(); throw; }
    }

    private static string Target(string workspace, string id)
    {
        ValidateId(id);
        string root = Path.Combine(Path.GetFullPath(workspace), ".runtime", "library", "media");
        string target = PathGuard.Under(root, id + "/property.json");
        PathGuard.NoLinks(target);
        return target;
    }
    private static void ValidateId(string id) { if (!Guid.TryParseExact(id, "D", out _)) throw new IOException("Invalid media journal clip ID."); }
    private static string JournalRoot(string workspace) => Path.Combine(Path.GetFullPath(workspace), ".runtime", "media-property");
    private static string ClipPath(string workspace, string id) => Path.Combine(Path.GetDirectoryName(Target(workspace, id))!, id + ".vsclip");
    private static string HistoryRoot(string workspace) => Path.Combine(Path.GetFullPath(workspace), ".runtime", "media-recovery-history");
    private static void ArchiveResolved(string workspace, string stage)
    {
        string history = HistoryRoot(workspace);
        PathGuard.CreateDirectory(history);
        string destination = PathGuard.Under(history, Path.GetFileName(stage));
        PathGuard.TreeNoLinks(stage); PathGuard.NoLinks(destination);
        Directory.Move(stage, destination);
    }
    private static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes));
    private static string Hash(FileStream file) { file.Position = 0; string hash = Convert.ToHexString(SHA256.HashData(file)); file.Position = 0; return hash; }
    private static void WriteDurable(string path, byte[] bytes)
    {
        using FileStream file = new(path, FileMode.CreateNew, FileAccess.Write, FileShare.None, 4096, FileOptions.WriteThrough);
        file.Write(bytes); file.Flush(true);
    }
    private static void WriteMarker(string path, byte[] bytes)
    {
        using BoundFile marker = BoundFile.Open(path + ".new", true);
        marker.Write(bytes); marker.Rename(path); marker.Flush();
    }
    private static void RemoveStage(string stage)
    {
        string parent = Path.GetDirectoryName(Path.GetFullPath(stage))!;
        string name = Path.GetFileName(stage);
        if (Path.GetFileName(parent) != "media-property") throw new IOException("Invalid media staging cleanup root.");
        if (Guid.TryParseExact(name, "N", out _))
        {
            string completed = PathGuard.Under(parent, "completed-" + name);
            PathGuard.TreeNoLinks(stage); PathGuard.NoLinks(completed);
            Directory.Move(stage, completed);
            stage = completed;
        }
        else if (!name.StartsWith("completed-", StringComparison.Ordinal) || !Guid.TryParseExact(name[10..], "N", out _))
            throw new IOException("Invalid media staging cleanup name.");
        PathGuard.TreeNoLinks(stage);
        Directory.Delete(stage, true);
    }
    private void CloseHandles() { candidate?.Dispose(); candidate = null; original?.Dispose(); original = null; clip?.Dispose(); clip = null; }
    public void Dispose() { CloseHandles(); lease.Dispose(); }

    [StructLayout(LayoutKind.Sequential)]
    private struct FileInformation
    {
        internal uint Attributes;
        internal System.Runtime.InteropServices.ComTypes.FILETIME Creation, Access, Write;
        internal uint Volume, SizeHigh, SizeLow, Links, IndexHigh, IndexLow;
    }
    [DllImport("kernel32", SetLastError = true)]
    private static extern bool GetFileInformationByHandle(SafeFileHandle file, out FileInformation information);
    private static string Identity(SafeFileHandle file)
    {
        if (!GetFileInformationByHandle(file, out FileInformation info)) throw new Win32Exception(Marshal.GetLastWin32Error());
        if ((info.Attributes & 0x400) != 0) throw new IOException("Reparse media files are not supported.");
        return $"{info.Volume:X8}:{info.IndexHigh:X8}{info.IndexLow:X8}";
    }

    private sealed class BoundFile : IDisposable
    {
        [DllImport("kernel32", EntryPoint = "CreateFileW", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern SafeFileHandle CreateFile(string path, uint access, uint share, nint security, uint disposition, uint flags, nint template);
        [DllImport("kernel32", SetLastError = true)]
        private static extern bool SetFileInformationByHandle(SafeFileHandle file, int kind, byte[] data, uint size);
        private readonly FileStream stream;
        internal string Identity => MediaPropertyJournal.Identity(stream.SafeFileHandle);
        private BoundFile(SafeFileHandle file) { stream = new FileStream(file, FileAccess.ReadWrite); _ = Identity; }
        internal static BoundFile Open(string path, bool create)
        {
            PathGuard.NoLinks(path);
            SafeFileHandle file = CreateFile(path, 0xc0010000, 0, 0, create ? 1u : 3u, 0x80200080, 0);
            if (file.IsInvalid) { int error = Marshal.GetLastWin32Error(); file.Dispose(); throw new Win32Exception(error); }
            try { return new BoundFile(file); } catch { file.Dispose(); throw; }
        }
        internal byte[] Read()
        {
            if (stream.Length > 16 * 1024 * 1024) throw new IOException("Media properties exceed 16 MiB.");
            stream.Position = 0; byte[] bytes = new byte[checked((int)stream.Length)]; stream.ReadExactly(bytes); return bytes;
        }
        internal void Write(byte[] bytes) { stream.Write(bytes); Flush(); }
        internal void Flush() => stream.Flush(true);
        internal void Rename(string destination)
        {
            PathGuard.NoLinks(destination);
            byte[] name = Encoding.Unicode.GetBytes(Path.GetFullPath(destination));
            int lengthOffset = IntPtr.Size == 8 ? 16 : 8;
            byte[] buffer = new byte[lengthOffset + 4 + name.Length + 2];
            BinaryPrimitives.WriteUInt32LittleEndian(buffer.AsSpan(lengthOffset), checked((uint)name.Length));
            name.CopyTo(buffer, lengthOffset + 4);
            // ReplaceIfExists is zero: a competing directory entry is never overwritten.
            if (!SetFileInformationByHandle(stream.SafeFileHandle, 3, buffer, (uint)buffer.Length))
                throw new Win32Exception(Marshal.GetLastWin32Error());
        }
        public void Dispose() => stream.Dispose();
    }
}
