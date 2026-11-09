using System.IO;
using System.Text.Json;
using Yamaha.VOCALOID.VSM;

internal sealed partial class EngineHost
{
    private sealed class ProjectClipboardData(string id, string kind, EngineSession snapshot, WIVSMClipboard value,
        ulong sourceTrackIndex, ulong sourcePartIndex, ulong[] sourceIndices)
    {
        internal string Id { get; } = id;
        internal string Kind { get; } = kind;
        internal EngineSession Snapshot { get; } = snapshot;
        internal WIVSMClipboard Value { get; } = value;
        internal ulong SourceTrackIndex { get; } = sourceTrackIndex;
        internal ulong SourcePartIndex { get; } = sourcePartIndex;
        internal ulong[] SourceIndices { get; } = sourceIndices;
        internal bool Pasted { get; set; }
    }

    private readonly Dictionary<string, ProjectClipboardData> projectClipboards = new(StringComparer.Ordinal);

    internal object ClipboardOperation(string? id, string operation, JsonElement options)
    {
        CheckThread();
        if (options.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("Clipboard options must be an object.");
        if (operation == "list")
            return new { clipboards = projectClipboards.Values.Select(ClipboardSummary).ToArray() };
        if (operation == "clear")
        {
            string clipboardId = ClipboardText(options, "clipboard_id");
            ProjectClipboardData stored = GetProjectClipboard(clipboardId);
            ClearProjectClipboard(stored);
            return new { clipboard_id = clipboardId, cleared = true, native = true, cached_assets_retained = stored.Pasted };
        }
        EngineSession session = GetSession(id ?? throw new ArgumentException("session_id is required."));
        if (session.Sequence.IsStaged)
            throw new InvalidOperationException("Commit or roll back pending native edits before a clipboard operation.");
        return operation switch
        {
            "copy" or "cut" => CopyProjectClipboard(session, operation, options),
            "paste" => PasteProjectClipboard(session, options),
            _ => throw new ArgumentException("Clipboard operation must be copy, cut, paste, clear, or list.")
        };
    }

    private static object ClipboardSummary(ProjectClipboardData stored) => new
    {
        clipboard_id = stored.Id, kind = stored.Kind, native = true,
        tracks = stored.Value.NumTrack, midi_parts = stored.Value.NumMidiPart,
        audio_parts = stored.Value.NumAudioPart, notes = stored.Value.NumNote
    };

    private ProjectClipboardData GetProjectClipboard(string id) => projectClipboards.TryGetValue(id, out ProjectClipboardData? value)
        ? value : throw new KeyNotFoundException("Unknown private clipboard_id.");

    private object CopyProjectClipboard(EngineSession source, string operation, JsonElement options)
    {
        if (projectClipboards.Count >= 128 || ownedDirectories.Count >= 1024)
            throw new InvalidOperationException("Private clipboard cache limit reached; clear clips or close this MCP host.");
        string kind = ClipboardText(options, "kind");
        ulong trackIndex = ClipboardIndex(options, "track_index", 0);
        ulong partIndex = ClipboardIndex(options, "part_index", 0);
        ulong count = kind switch
        {
            "tracks" => source.Sequence.NumTrack,
            "parts" => ClipboardTrack(source, trackIndex).NumParts,
            "notes" => ClipboardMidiPart(source, trackIndex, partIndex).NumNotes,
            _ => throw new ArgumentException("Clipboard kind must be tracks, parts, or notes.")
        };
        ulong[] indices = ClipboardIndices(options, count);
        EngineSession snapshot = CloneProject(source.Id, null);
        WIVSMClipboard? clipboard = null;
        string clipboardId = Guid.NewGuid().ToString("N");
        bool retained = false;
        try
        {
            clipboard = manager.CreateClipboard(snapshot.Sequence)
                ?? throw new InvalidOperationException("Native clipboard creation failed: " + manager.LastError);
            foreach (ulong index in indices)
            {
                bool copied = kind switch
                {
                    "tracks" => clipboard.PushTrack(ClipboardTrack(snapshot, index)) is not null,
                    "parts" => clipboard.PushParts([ClipboardTrack(snapshot, trackIndex).GetPart(index)!]),
                    "notes" => clipboard.PushNote(ClipboardMidiPart(snapshot, trackIndex, partIndex).GetNote(index)!) is not null,
                    _ => false
                };
                if (!copied)
                    throw new InvalidOperationException("Native clipboard copy failed: " + clipboard.LastError);
            }
            ProjectClipboardData stored = new(clipboardId, kind, snapshot, clipboard, trackIndex, partIndex, indices);
            object summary = ClipboardSummary(stored);
            projectClipboards.Add(clipboardId, stored);
            sessions.Remove(snapshot.Id);
            retained = true;
            if (operation == "cut")
            {
                try
                {
                    ScoreMutate(source, "clipboard.cut", () =>
                    {
                        var selected = indices.Select(index => kind switch
                        {
                            "tracks" => (object)ClipboardTrack(source, index),
                            "parts" => ClipboardTrack(source, trackIndex).GetPart(index)!,
                            "notes" => ClipboardMidiPart(source, trackIndex, partIndex).GetNote(index)!,
                            _ => throw new InvalidOperationException("Unknown clipboard selection.")
                        }).ToArray();
                        var deleted = ArchiveDeletePrepare(source, selected);
                        foreach (ulong index in indices.OrderDescending())
                        {
                            bool removed = kind switch
                            {
                                "tracks" => source.Sequence.RemoveTrack(ClipboardTrack(source, index)),
                                "parts" => ClipboardTrack(source, trackIndex).RemovePart(ClipboardTrack(source, trackIndex).GetPart(index)!),
                                "notes" => ClipboardMidiPart(source, trackIndex, partIndex).RemoveNote(ClipboardMidiPart(source, trackIndex, partIndex).GetNote(index)!),
                                _ => false
                            };
                            if (!removed)
                                throw new InvalidOperationException("Native clipboard cut failed: " + source.Sequence.LastError);
                        }
                        ArchiveDeleteStaged(source, deleted);
                        return true;
                    });
                }
                catch (Exception error)
                {
                    throw new InvalidOperationException("Clipboard cut failed; the independent snapshot remains available as clipboard_id=" + clipboardId + ".", error);
                }
            }
            return summary;
        }
        catch
        {
            if (!retained)
            {
                clipboard?.Destroy();
                clipboard?.Dispose();
                Close(snapshot.Id, true);
            }
            throw;
        }
    }

    private object PasteProjectClipboard(EngineSession target, JsonElement options)
    {
        ProjectClipboardData stored = GetProjectClipboard(ClipboardText(options, "clipboard_id"));
        long offset = checked((long)ClipboardIndex(options, "offset_tick", 0));
        if (offset > int.MaxValue)
            throw new ArgumentOutOfRangeException("offset_tick");
        if (HasArchiveEntityExtensions(stored.Snapshot) || HasArchiveEntityExtensions(target) ||
            ArchiveHasResources(stored.Snapshot))
            return PastePreservedClipboard(target, stored, options, offset);
        ulong inserted = 0;
        target.Dirty = true;
        try
        {
            if (stored.Kind == "tracks")
            {
                ulong insertion = ClipboardIndex(options, "index", target.Sequence.NumTrack);
                if (insertion > target.Sequence.NumTrack || target.Sequence.NumTrack + stored.Value.NumTrack > 32)
                    throw new ArgumentOutOfRangeException("index", "Clipboard paste exceeds native track bounds.");
                for (ulong index = 0; index < stored.Value.NumTrack; index++)
                {
                    WIVSMTrack track = target.Sequence.DuplicateTrack(insertion++, stored.Value.GetTrack(index)!, out string error)
                        ?? throw new InvalidOperationException("Native clipboard track paste failed: " + error);
                    foreach (WIVSMPart part in track.Parts.ToArray())
                        if (offset != 0 && !track.MovePart(part.AbsBeginTick + new VSMRelTick(offset), track, part))
                            throw new InvalidOperationException("Native clipboard part offset failed.");
                    if (offset != 0)
                    {
                        foreach (WIVSMTrackVolume volume in track.Volumes.Where(item => item.RelPosTick.Value > 0).ToArray())
                            if (!track.MoveVolume(volume.RelPosTick + new VSMRelTick(offset), volume))
                                throw new InvalidOperationException("Native clipboard volume offset failed.");
                        foreach (WIVSMPanpot panpot in track.Panpots.Where(item => item.RelPosTick.Value > 0).ToArray())
                            if (!track.MovePanpot(panpot.RelPosTick + new VSMRelTick(offset), panpot))
                                throw new InvalidOperationException("Native clipboard pan offset failed.");
                    }
                    inserted++;
                }
            }
            else if (stored.Kind == "parts")
            {
                WIVSMTrack track = ClipboardTrack(target, ClipboardIndex(options, "track_index", 0));
                foreach (WIVSMPart part in stored.Value.GetParts)
                {
                    if ((part.Type == VSMPartType.Audio) != (track.Type == VSMTrackType.Audio))
                        throw new ArgumentException("Clipboard part type does not match the target track.");
                    if (part.Type == VSMPartType.Midi && new WIVSMMidiPart(part).ClipboardParentTrackType() != track.Type)
                        throw new ArgumentException("Clipboard part type must match the target track.");
                    if (track.DuplicatePart(part.AbsBeginTick + new VSMRelTick(offset), part) is null)
                        throw new InvalidOperationException("Native clipboard part paste failed: " + track.LastError);
                    inserted++;
                }
            }
            else
            {
                WIVSMMidiPart part = ClipboardMidiPart(target, ClipboardIndex(options, "track_index", 0), ClipboardIndex(options, "part_index", 0));
                foreach (WIVSMNote note in stored.Value.GetNotes)
                {
                    if (note.IsAi != part.IsAi)
                        throw new ArgumentException("Clipboard note and target part must use the same native voice type.");
                    if (part.DuplicateNote(note.RelPosTick + new VSMRelTick(offset), note) is null)
                        throw new InvalidOperationException("Native clipboard note paste failed: " + part.LastError);
                    inserted++;
                }
            }
            if (target.Sequence.IsStaged && !target.Sequence.Commit(true))
                throw new InvalidOperationException("Native clipboard paste commit failed: " + target.Sequence.LastError);
            stored.Pasted = true;
            return new { session_id = target.Id, clipboard_id = stored.Id, native = true, pasted = inserted };
        }
        catch { target.Sequence.Rollback(); throw; }
        finally { target.InvalidateChildren(); }
    }

    private object PastePreservedClipboard(EngineSession target, ProjectClipboardData stored, JsonElement options, long offset,
        bool preflight = true)
    {
        // Opaque members are project-scoped, so every selection carries the
        // complete snapshot resource set rather than claiming entity ownership.
        var resources = ArchivePrepareClipboardResources(stored.Snapshot, target);
        WIVSMTrack? targetTrack = null;
        WIVSMMidiPart? targetPart = null;
        ulong insertion = 0;
        if (stored.Kind == "tracks")
        {
            insertion = ClipboardIndex(options, "index", target.Sequence.NumTrack);
            if (insertion > target.Sequence.NumTrack || target.Sequence.NumTrack + (ulong)stored.SourceIndices.Length > 32)
                throw new ArgumentOutOfRangeException("index", "Clipboard paste exceeds native track bounds.");
            foreach (ulong index in stored.SourceIndices)
                if (ClipboardTrack(stored.Snapshot, index).Type is not (VSMTrackType.Midi or VSMTrackType.MidiAi or VSMTrackType.Audio))
                    throw new InvalidOperationException("project_preservation: unsupported extended clipboard track type.");
        }
        else if (stored.Kind == "parts")
        {
            targetTrack = ClipboardTrack(target, ClipboardIndex(options, "track_index", 0));
            if (targetTrack.Type is not (VSMTrackType.Midi or VSMTrackType.MidiAi or VSMTrackType.Audio) ||
                ClipboardTrack(stored.Snapshot, stored.SourceTrackIndex).Type != targetTrack.Type)
                throw new ArgumentException("Clipboard part type must match the target track.");
        }
        else
        {
            targetPart = ClipboardMidiPart(target, ClipboardIndex(options, "track_index", 0), ClipboardIndex(options, "part_index", 0));
            WIVSMMidiPart sourcePart = ClipboardMidiPart(stored.Snapshot, stored.SourceTrackIndex, stored.SourcePartIndex);
            if (sourcePart.IsAi != targetPart.IsAi)
                throw new ArgumentException("Clipboard note and target part must use the same native voice type.");
        }

        if (preflight)
        {
            // A successful native duplicate can still produce an archive whose
            // extended entities cannot be rebound after save/reopen. Exercise
            // the same paste and snapshot on an independent target first.
            EngineSession candidate = CloneProject(target.Id, null);
            try
            {
                PastePreservedClipboard(candidate, stored, options, offset, false);
                EngineSession verified = CloneProject(candidate.Id, null);
                try
                {
                    if (resources.Count != 0)
                    {
                        string archive = Path.Combine(verified.Directory, "clipboard-resource-preflight-" + Guid.NewGuid().ToString("N") + ".vpr");
                        WriteProjectArchive(verified, verified.Directory, archive, CaptureProjectValidity(verified.Sequence));
                    }
                }
                finally { Close(verified.Id, true); }
            }
            finally { Close(candidate.Id, true); }
            // Reacquire target wrappers after saving the independent snapshot.
            if (stored.Kind == "parts")
                targetTrack = ClipboardTrack(target, ClipboardIndex(options, "track_index", 0));
            else if (stored.Kind == "notes")
                targetPart = ClipboardMidiPart(target, ClipboardIndex(options, "track_index", 0), ClipboardIndex(options, "part_index", 0));
        }

        bool upgraded = EnsureArchiveEntityTracking(target);
        try
        {
            object result = ScoreMutate(target, "clipboard.paste", () =>
            {
                ulong inserted = 0;
                foreach (ulong index in stored.SourceIndices)
                {
                    if (stored.Kind == "tracks")
                    {
                        WIVSMTrack source = ClipboardTrack(stored.Snapshot, index);
                        WIVSMTrack track = target.Sequence.DuplicateTrack(insertion++, source, out string error)
                            ?? throw new InvalidOperationException("Native clipboard track paste failed: " + error);
                        if (offset != 0)
                        {
                            foreach (WIVSMPart part in track.Parts.ToArray())
                                if (!track.MovePart(part.AbsBeginTick + new VSMRelTick(offset), track, part))
                                    throw new InvalidOperationException("Native clipboard part offset failed.");
                            foreach (WIVSMTrackVolume volume in track.Volumes.Where(item => item.RelPosTick.Value > 0).ToArray())
                                if (!track.MoveVolume(volume.RelPosTick + new VSMRelTick(offset), volume))
                                    throw new InvalidOperationException("Native clipboard volume offset failed.");
                            foreach (WIVSMPanpot panpot in track.Panpots.Where(item => item.RelPosTick.Value > 0).ToArray())
                                if (!track.MovePanpot(panpot.RelPosTick + new VSMRelTick(offset), panpot))
                                    throw new InvalidOperationException("Native clipboard pan offset failed.");
                        }
                        ArchiveTransferCopy(stored.Snapshot, target, source, track, partOffset: offset, mergeResources: true);
                    }
                    else if (stored.Kind == "parts")
                    {
                        WIVSMPart source = ClipboardTrack(stored.Snapshot, stored.SourceTrackIndex).GetPart(index)
                            ?? throw new InvalidOperationException("Clipboard snapshot part is missing.");
                        WIVSMTrack track = targetTrack ?? throw new InvalidOperationException("Clipboard target track is missing.");
                        WIVSMPart part = track.DuplicatePart(source.AbsBeginTick + new VSMRelTick(offset), source)
                            ?? throw new InvalidOperationException("Native clipboard part paste failed: " + track.LastError);
                        ArchiveTransferCopy(stored.Snapshot, target, source, part, partOffset: offset, mergeResources: true);
                    }
                    else
                    {
                        WIVSMMidiPart sourcePart = ClipboardMidiPart(stored.Snapshot, stored.SourceTrackIndex, stored.SourcePartIndex);
                        WIVSMNote source = sourcePart.GetNote(index) ?? throw new InvalidOperationException("Clipboard snapshot note is missing.");
                        WIVSMMidiPart part = targetPart ?? throw new InvalidOperationException("Clipboard target part is missing.");
                        WIVSMNote note = part.DuplicateNote(source.RelPosTick + new VSMRelTick(offset), source)
                            ?? throw new InvalidOperationException("Native clipboard note paste failed: " + part.LastError);
                        ArchiveTransferCopy(stored.Snapshot, target, source, note, noteOffset: offset, mergeResources: true);
                    }
                    inserted++;
                }
                ArchiveAddResources(target, resources);
                return new { session_id = target.Id, clipboard_id = stored.Id, native = true, pasted = inserted };
            });
            if (preflight) stored.Pasted = true;
            return result;
        }
        catch (Exception error)
        {
            if (upgraded)
            {
                try { DropArchiveEntityTracking(target); }
                catch (Exception cleanup) { throw new AggregateException("Clipboard preservation failed and tracking cleanup was incomplete.", error, cleanup); }
            }
            throw;
        }
    }

    private static WIVSMTrack ClipboardTrack(EngineSession session, ulong index) => session.Sequence.GetTrack(index)
        ?? throw new ArgumentOutOfRangeException("track_index");

    private static WIVSMMidiPart ClipboardMidiPart(EngineSession session, ulong trackIndex, ulong partIndex)
    {
        WIVSMTrack track = ClipboardTrack(session, trackIndex);
        if (track.Type is not (VSMTrackType.Midi or VSMTrackType.MidiAi))
            throw new ArgumentException("Clipboard notes require a MIDI or MIDI AI track.");
        return new WIVSMMidiTrack(track).GetPart(partIndex) ?? throw new ArgumentOutOfRangeException("part_index");
    }

    private static string ClipboardText(JsonElement options, string name) => options.GetProperty(name).GetString()
        ?? throw new ArgumentException(name + " must be a string.");

    private static ulong ClipboardIndex(JsonElement options, string name, ulong fallback) =>
        options.TryGetProperty(name, out JsonElement value) ? value.GetUInt64() : fallback;

    private static ulong[] ClipboardIndices(JsonElement options, ulong count)
    {
        JsonElement values = options.GetProperty("indices");
        if (values.ValueKind != JsonValueKind.Array || values.GetArrayLength() is < 1 or > 4096)
            throw new ArgumentException("indices must contain 1..4096 native indices.");
        ulong[] indices = values.EnumerateArray().Select(value => value.GetUInt64()).ToArray();
        if (indices.Distinct().Count() != indices.Length || indices.Any(index => index >= count))
            throw new ArgumentException("indices must identify distinct existing objects.");
        return indices;
    }

    private void ClearProjectClipboard(ProjectClipboardData stored)
    {
        if (!stored.Value.Destroy())
            throw new InvalidOperationException("Native clipboard destruction failed.");
        stored.Value.Dispose();
        if (!stored.Snapshot.Sequence.Close())
            throw new InvalidOperationException("Native clipboard snapshot close failed.");
        ReleaseArchivePreservation(stored.Snapshot);
        ownedSequences.Remove(stored.Snapshot.Sequence);
        stored.Snapshot.InvalidateAll();
        projectClipboards.Remove(stored.Id);
        if (!stored.Pasted)
            Cleanup(stored.Snapshot.Directory);
    }

    private void DisposeProjectClipboards()
    {
        foreach (ProjectClipboardData stored in projectClipboards.Values.ToArray())
            ClearProjectClipboard(stored);
    }
}
