using System.Buffers.Binary;
using System.IO;
using System.Text;
using System.Text.Json.Nodes;
using Yamaha.VOCALOID.VSM;

internal sealed partial class EngineHost
{
    private readonly Dictionary<string, List<string>> importedProjectDirectories = new(StringComparer.Ordinal);

    internal EngineSession CloneProject(string id, string? title)
    {
        EngineSession source = GetSession(id);
        (string cloneId, string directory) = NewDirectory();
        WIVSMSequence? sequence = null;
        try
        {
            if (source.Sequence.IsStaged && !source.Sequence.Commit(false))
                throw new InvalidOperationException("Native snapshot commit failed: " + source.Sequence.LastError);
            ProjectValidityMetadata validity = CaptureProjectValidity(source.Sequence);
            if (!source.Sequence.Save(directory, false))
                throw new InvalidOperationException("Native snapshot save failed: " + source.Sequence.LastError);
            string project = Path.Combine(directory, "Project");
            string json = Path.Combine(project, "sequence.json");
            ValidateNativeSnapshot(source.Sequence, json);
            ApplyArchivePreservation(source, directory);
            ApplyFrozenAuthoringState(source, directory);
            ValidateOpenRequirements(json);
            sequence = manager.OpenSequence(json,
                Path.GetDirectoryName(typeof(WVSMModuleIF).Assembly.Location)!,
                new VSMSequenceData(source.Sequence.GetSamplingRate(), 32, 100))
                ?? throw new InvalidOperationException("Native clone open failed: " + manager.LastError);
            ownedSequences.Add(sequence);
            ValidateLoadedTrackKinds(sequence, json);
            ApplyProjectValidity(sequence, validity);
            if (title is not null)
                sequence.Title = title;
            EngineSession clone = new(cloneId, directory, sequence, null, true);
            CaptureArchivePreservation(clone, directory);
            sessions.Add(cloneId, clone);
            return clone;
        }
        catch
        {
            ReleaseFailedSequence(sequence, directory);
            throw;
        }
    }

    internal EngineSession RevertProject(string id, bool discard)
    {
        EngineSession current = GetSession(id);
        if (current.Dirty && !discard)
            throw new InvalidOperationException("Reverting discards changes; set discard_changes=true.");
        string path = current.LastSavedPath ?? current.OriginalPath
            ?? throw new InvalidOperationException("The project has no saved version to restore.");
        if (!string.Equals(Path.GetExtension(path), ".vpr", StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Save the imported project as a VPR before reverting it.");
        EngineSession replacement = Open(path);
        try { Close(id, true); }
        catch
        {
            Close(replacement.Id, true);
            throw;
        }
        return replacement;
    }

    internal object MergeProject(string id, string path, long offsetTick, bool includeTracks, bool includeTempo, bool replaceTempo, uint codePage)
    {
        EngineSession target = GetSession(id);
        if (offsetTick < 0 || offsetTick > int.MaxValue)
            throw new ArgumentOutOfRangeException(nameof(offsetTick));
        if (!includeTracks && !includeTempo)
            throw new ArgumentException("Select tracks or tempo/time-signature data to import.");
        if (replaceTempo && (!includeTempo || offsetTick != 0))
            throw new ArgumentException("Replacing the tempo map requires include_tempo=true and offset_tick=0.");
        if (target.Sequence.IsStaged)
            throw new InvalidOperationException("Commit or roll back pending native edits before merging.");
        EngineSession source = ImportProject(path, codePage, true);
        bool touched = false;
        bool trackedMutation = false;
        try
        {
            if (includeTracks && ArchiveHasControllerExtensions(source))
                throw new InvalidOperationException("project_preservation: controller extension project merge has no verified identity mapping.");
            bool timeSigExtensions = includeTempo &&
                ((archiveStates.TryGetValue(source.Id, out ArchiveState? sourceTimeSigState) && sourceTimeSigState.TimeSig is not null) ||
                 (archiveStates.TryGetValue(target.Id, out ArchiveState? targetTimeSigState) && targetTimeSigState.TimeSig is not null));
            bool tempoExtensions = includeTempo &&
                ((archiveStates.TryGetValue(source.Id, out ArchiveState? sourceTempoState) && sourceTempoState.Tempo is not null) ||
                 (archiveStates.TryGetValue(target.Id, out ArchiveState? targetTempoState) && targetTempoState.Tempo is not null));
            var globalFields = ArchiveMergePrepare(source, target);
            var resources = ArchivePrepareResources(source, target, includeTracks);
            if (includeTracks && target.Sequence.NumTrack + source.Sequence.NumTrack > 32)
                throw new InvalidOperationException("The merged project exceeds the native 32-track limit.");
            bool globalChange = !archiveStates.TryGetValue(target.Id, out ArchiveState? targetArchive)
                ? globalFields.Root.Count != 0 || globalFields.Master.Count != 0
                : !JsonNode.DeepEquals(globalFields.Root, targetArchive.Root) || !JsonNode.DeepEquals(globalFields.Master, targetArchive.Master);
            if ((includeTracks && HasArchiveEntityExtensions(source)) || HasArchiveEntityExtensions(target) || globalChange || resources.Count != 0 || tempoExtensions || timeSigExtensions)
            {
                if (includeTracks && source.Sequence.Tracks.Any(track => track.Type is not (VSMTrackType.Midi or VSMTrackType.MidiAi or VSMTrackType.Audio)))
                    throw new InvalidOperationException("project_preservation: unsupported extended project track type.");
                // The native writer cannot safely rebind indistinguishable
                // tracks with different extension payloads. Verify the merged
                // snapshot on an independent target before changing this one.
                PreflightPreservedMerge(target, source, offsetTick, includeTracks, includeTempo, replaceTempo, globalFields, globalChange, resources);
                // The source directory must remain alive if native duplication
                // references imported assets, including after a staged failure.
                touched = true;
                trackedMutation = true;
                return MergePreservedProject(target, source, offsetTick, includeTracks, includeTempo, replaceTempo, globalFields, globalChange, resources);
            }
            if (includeTracks)
            {
                foreach (WIVSMTrack sourceTrack in source.Sequence.Tracks.ToArray())
                {
                    touched = true;
                    WIVSMTrack track = target.Sequence.DuplicateTrack(target.Sequence.NumTrack, sourceTrack, out string error)
                        ?? throw new InvalidOperationException("Native track import failed: " + error);
                    if (offsetTick == 0)
                        continue;
                    VSMRelTick offset = new(offsetTick);
                    foreach (WIVSMPart part in track.Parts.ToArray())
                        if (!track.MovePart(part.AbsBeginTick + offset, track, part))
                            throw new InvalidOperationException("Native imported-part offset failed: " + track.LastError);
                    foreach (WIVSMTrackVolume volume in track.Volumes.Where(item => item.RelPosTick.Value > 0).ToArray())
                        if (!track.MoveVolume(volume.RelPosTick + offset, volume))
                            throw new InvalidOperationException("Native imported-volume offset failed: " + track.LastError);
                    foreach (WIVSMPanpot panpot in track.Panpots.Where(item => item.RelPosTick.Value > 0).ToArray())
                        if (!track.MovePanpot(panpot.RelPosTick + offset, panpot))
                            throw new InvalidOperationException("Native imported-pan offset failed: " + track.LastError);
                }
            }
            if (includeTempo)
            {
                WIVSMClipboard clipboard = manager.CreateClipboard(target.Sequence)
                    ?? throw new InvalidOperationException("Native import clipboard creation failed: " + manager.LastError);
                try
                {
                    if (!clipboard.PushTempos(source.Sequence.Tempos) || !clipboard.PushTimeSigs(source.Sequence.TimeSigs))
                        throw new InvalidOperationException("Native tempo import snapshot failed: " + clipboard.LastError);
                    touched = true;
                    if (replaceTempo && (!target.Sequence.RemoveTempos(target.Sequence.Tempos) ||
                                         !target.Sequence.RemoveTimeSigsEx(target.Sequence.TimeSigs)))
                        throw new InvalidOperationException("Native tempo-map replacement failed: " + target.Sequence.LastError);
                    if (!target.Sequence.PasteTempo(clipboard, new VSMRelTick(offsetTick)) ||
                        !target.Sequence.PasteTimeSig(clipboard, new VSMRelTick(offsetTick)))
                        throw new InvalidOperationException("Native tempo-map import failed: " + target.Sequence.LastError);
                }
                finally
                {
                    if (!clipboard.Destroy())
                        throw new InvalidOperationException("Native import clipboard cleanup failed.");
                    clipboard.Dispose();
                }
            }
            if (target.Sequence.IsStaged && !target.Sequence.Commit(true))
                throw new InvalidOperationException("Native merge commit failed: " + target.Sequence.LastError);
            target.Dirty = true;
            target.InvalidateChildren();
            return new { session_id = id, native = true, imported_tracks = includeTracks ? source.Sequence.NumTrack : 0,
                         include_tempo = includeTempo, offset_tick = offsetTick, track_count = target.Sequence.NumTrack };
        }
        catch
        {
            if (touched && !trackedMutation)
            {
                target.Sequence.Rollback();
                target.Dirty = true;
                target.InvalidateChildren();
            }
            throw;
        }
        finally
        {
            if (touched)
            {
                if (!source.Sequence.Close())
                    throw new InvalidOperationException("Native imported-source close failed: " + source.Sequence.LastError);
                ReleaseArchivePreservation(source);
                ownedSequences.Remove(source.Sequence);
                source.InvalidateAll();
                sessions.Remove(source.Id);
                if (!importedProjectDirectories.TryGetValue(id, out List<string>? directories))
                    importedProjectDirectories.Add(id, directories = []);
                directories.Add(source.Directory);
            }
            else
                Close(source.Id, true);
        }
    }

    private void PreflightPreservedMerge(EngineSession target, EngineSession source, long offsetTick,
        bool includeTracks, bool includeTempo, bool replaceTempo, (JsonObject Root, JsonObject Master) globalFields, bool globalChange, List<(string Name, string Source)> resources)
    {
        EngineSession candidate = CloneProject(target.Id, null);
        try
        {
            var fields = ((JsonObject)globalFields.Root.DeepClone(), (JsonObject)globalFields.Master.DeepClone());
            MergePreservedProject(candidate, source, offsetTick, includeTracks, includeTempo, replaceTempo, fields, globalChange, resources);
            EngineSession verified = CloneProject(candidate.Id, null);
            try
            {
                if (resources.Count != 0)
                {
                    string archive = Path.Combine(verified.Directory, "resource-preflight-" + Guid.NewGuid().ToString("N") + ".vpr");
                    WriteProjectArchive(verified, verified.Directory, archive, CaptureProjectValidity(verified.Sequence));
                }
            }
            finally { Close(verified.Id, true); }
        }
        finally { Close(candidate.Id, true); }
    }

    private object MergePreservedProject(EngineSession target, EngineSession source, long offsetTick,
        bool includeTracks, bool includeTempo, bool replaceTempo, (JsonObject Root, JsonObject Master) globalFields, bool globalChange, List<(string Name, string Source)> resources)
    {
        Dictionary<int, ProjectArchiveArrays.TimeSig>? mergedTimeSig = includeTempo
            ? PrepareTimeSigMerge(target, source, offsetTick, replaceTempo) : null;
        bool upgraded = EnsureArchiveEntityTracking(target);
        try
        {
            return ScoreMutate(target, "project.merge", () =>
            {
                if (includeTracks)
                {
                    foreach (WIVSMTrack original in source.Sequence.Tracks.ToArray())
                    {
                        WIVSMTrack track = target.Sequence.DuplicateTrack(target.Sequence.NumTrack, original, out string error)
                            ?? throw new InvalidOperationException("Native track import failed: " + error);
                        if (offsetTick != 0)
                        {
                            VSMRelTick offset = new(offsetTick);
                            foreach (WIVSMPart part in track.Parts.ToArray())
                                if (!track.MovePart(part.AbsBeginTick + offset, track, part))
                                    throw new InvalidOperationException("Native imported-part offset failed: " + track.LastError);
                            foreach (WIVSMTrackVolume volume in track.Volumes.Where(item => item.RelPosTick.Value > 0).ToArray())
                                if (!track.MoveVolume(volume.RelPosTick + offset, volume))
                                    throw new InvalidOperationException("Native imported-volume offset failed: " + track.LastError);
                            foreach (WIVSMPanpot panpot in track.Panpots.Where(item => item.RelPosTick.Value > 0).ToArray())
                                if (!track.MovePanpot(panpot.RelPosTick + offset, panpot))
                                    throw new InvalidOperationException("Native imported-pan offset failed: " + track.LastError);
                        }
                        ArchiveTransferCopy(source, target, original, track, partOffset: offsetTick, mergeResources: true);
                    }
                }
                Dictionary<int, ProjectArchiveArrays.Tempo>? mergedTempo = includeTempo
                    ? PrepareTempoMerge(target, source, offsetTick, replaceTempo) : null;
                if (includeTempo)
                {
                    WIVSMClipboard clipboard = manager.CreateClipboard(target.Sequence)
                        ?? throw new InvalidOperationException("Native import clipboard creation failed: " + manager.LastError);
                    try
                    {
                        if (!clipboard.PushTempos(source.Sequence.Tempos) || !clipboard.PushTimeSigs(source.Sequence.TimeSigs))
                            throw new InvalidOperationException("Native tempo import snapshot failed: " + clipboard.LastError);
                        if (replaceTempo && (!target.Sequence.RemoveTempos(target.Sequence.Tempos) ||
                                             !target.Sequence.RemoveTimeSigsEx(target.Sequence.TimeSigs)))
                            throw new InvalidOperationException("Native tempo-map replacement failed: " + target.Sequence.LastError);
                        if (!target.Sequence.PasteTempo(clipboard, new VSMRelTick(offsetTick)) ||
                            !target.Sequence.PasteTimeSig(clipboard, new VSMRelTick(offsetTick)))
                            throw new InvalidOperationException("Native tempo-map import failed: " + target.Sequence.LastError);
                    }
                    finally
                    {
                        if (!clipboard.Destroy())
                            throw new InvalidOperationException("Native import clipboard cleanup failed.");
                        clipboard.Dispose();
                    }
                }
                if (mergedTempo is not null)
                {
                    ProjectArchiveArrays.ValidateTempo(mergedTempo, ArchiveNativeTempos(target.Sequence));
                    if (!target.Sequence.IsStaged)
                        throw new InvalidOperationException("project_preservation: tempo extension merge requires a native history entry.");
                    archiveStates[target.Id].Tempo = mergedTempo;
                }
                if (mergedTimeSig is not null)
                {
                    ProjectArchiveArrays.ValidateTimeSig(mergedTimeSig, ArchiveNativeTimeSigs(target.Sequence));
                    if (!target.Sequence.IsStaged)
                        throw new InvalidOperationException("project_preservation: time signature extension merge requires a native history entry.");
                    archiveStates[target.Id].TimeSig = mergedTimeSig;
                }
                ArchiveAddResources(target, resources);
                if (globalChange)
                {
                    if (!target.Sequence.IsStaged)
                        throw new InvalidOperationException("project_preservation: global extension merge requires a native history entry.");
                    ArchiveState state = archiveStates[target.Id];
                    state.Root = globalFields.Root;
                    state.Master = globalFields.Master;
                }
                return new { session_id = target.Id, native = true, imported_tracks = includeTracks ? source.Sequence.NumTrack : 0,
                             include_tempo = includeTempo, offset_tick = offsetTick, track_count = target.Sequence.NumTrack };
            });
        }
        catch (Exception error)
        {
            if (upgraded)
            {
                try { DropArchiveEntityTracking(target); }
                catch (Exception cleanup) { throw new AggregateException("Merge preservation failed and tracking cleanup was incomplete.", error, cleanup); }
            }
            throw;
        }
    }

    private void CleanupImportedProjects(string id)
    {
        if (!importedProjectDirectories.Remove(id, out List<string>? directories))
            return;
        foreach (string directory in directories)
            Cleanup(directory);
    }

    internal EngineSession ImportProject(string path, uint codePage, bool preferMidiAiTrack)
    {
        CheckThread();
        if (!Path.IsPathFullyQualified(path))
            throw new ArgumentException("path must be an absolute project or MIDI filename.");
        path = Path.GetFullPath(path);
        PathGuard.NoLinks(path);
        string extension = Path.GetExtension(path).ToLowerInvariant();
        if (extension == ".vpr")
            return Open(path);
        if (extension is not (".vsqx" or ".ppsf" or ".mid" or ".midi" or ".smf" or ".vsq"))
            throw new ArgumentException("Supported imports: VPR, VSQX, PPSF, MIDI, SMF and VSQ.");
        FileInfo source = new(path);
        if (!source.Exists || source.Length > MaxArchiveBytes)
            throw new IOException("Import source is missing or exceeds 8 GiB.");
        Encoding.RegisterProvider(CodePagesEncodingProvider.Instance);
        _ = Encoding.GetEncoding(checked((int)codePage));
        EnsureVoiceServices();
        (string id, string directory) = NewDirectory();
        WIVSMSequence? sequence = null;
        try
        {
            string stagedInput = Path.Combine(directory, "source" + extension);
            File.Copy(path, stagedInput, false);
            VSMSequenceData settings = new(VSMSamplingRate._44100, 32, 100);
            if (extension == ".vsqx")
            {
                string schemaDirectory = Path.GetDirectoryName(typeof(WVSMModuleIF).Assembly.Location)!;
                sequence = manager.OpenSequence(stagedInput, schemaDirectory, settings);
            }
            else if (extension == ".ppsf")
            {
                Span<byte> signature = stackalloc byte[4];
                using (FileStream input = File.OpenRead(stagedInput))
                    input.ReadExactly(signature);
                if (signature.SequenceEqual("PK\u0003\u0004"u8))
                {
                    string extracted = Path.Combine(directory, "ppsf");
                    PathGuard.CreateDirectory(extracted);
                    Extract(stagedInput, extracted);
                    string json = Path.Combine(extracted, "ppsf.json");
                    if (!File.Exists(json))
                        throw new InvalidDataException("PPSF archive does not contain ppsf.json.");
                    sequence = manager.OpenSequenceFromPpsfV3(json, settings);
                }
                else
                    sequence = manager.OpenSequenceFromPpsfV2(stagedInput, settings);
            }
            else
                sequence = manager.OpenLegacySequence(stagedInput, settings, codePage, true, preferMidiAiTrack);
            if (sequence is null)
                throw new InvalidDataException("Native project import failed: " + manager.LastError);
            ownedSequences.Add(sequence);
            if (manager.LastYVSResult == YVSResult.LimitedTrackDeletion)
                throw new InvalidDataException("Native import removed tracks because of an engine limit; the partial project was rejected.");
            EngineSession session = new(id, directory, sequence, path, true);
            sessions.Add(id, session);
            return session;
        }
        catch
        {
            ReleaseFailedSequence(sequence, directory);
            throw;
        }
    }

    internal object ExportMidi(string id, string outputName, string encoding, bool overwrite)
    {
        EngineSession session = GetSession(id);
        string normalizedEncoding = encoding.Replace("_", "", StringComparison.Ordinal).Replace("-", "", StringComparison.Ordinal);
        string? nativeEncoding = Enum.GetNames<VSMEncoding>().FirstOrDefault(name =>
            string.Equals(name.Replace("_", "", StringComparison.Ordinal), normalizedEncoding, StringComparison.OrdinalIgnoreCase));
        if (nativeEncoding is null)
            throw new ArgumentException("Unknown MIDI lyric encoding. Native values: " + string.Join(", ", Enum.GetNames<VSMEncoding>()));
        string extension = Path.GetExtension(outputName).ToLowerInvariant();
        if (extension is not (".mid" or ".midi"))
            throw new ArgumentException("output_name must end in .mid or .midi.");
        string destination = PrepareOutput(session, outputName, extension, overwrite);
        if (session.Sequence.IsStaged && !session.Sequence.Commit(false))
            throw new InvalidOperationException("Native pre-export commit failed: " + session.Sequence.LastError);
        string temporary = Path.Combine(session.Directory, "midi-" + Guid.NewGuid().ToString("N") + ".mid");
        if (!session.Sequence.SaveSMF(temporary, Enum.Parse<VSMEncoding>(nativeEncoding)))
            throw new InvalidOperationException("Native SMF export failed: " + session.Sequence.LastError);
        PathGuard.NoLinks(temporary);
        Span<byte> header = stackalloc byte[14];
        using (FileStream input = File.OpenRead(temporary))
        {
            input.ReadExactly(header);
            if (!header[..4].SequenceEqual("MThd"u8) || BinaryPrimitives.ReadUInt32BigEndian(header[4..8]) != 6)
                throw new InvalidDataException("Native export did not produce a valid Standard MIDI File header.");
        }
        ushort format = BinaryPrimitives.ReadUInt16BigEndian(header[8..10]);
        ushort tracks = BinaryPrimitives.ReadUInt16BigEndian(header[10..12]);
        ushort division = BinaryPrimitives.ReadUInt16BigEndian(header[12..14]);
        if (format > 1 || tracks == 0 || division == 0 || (division & 0x8000) != 0)
            throw new InvalidDataException("Native export produced unsupported MIDI timing or tracks.");
        PathGuard.NoLinks(destination);
        File.Move(temporary, destination, overwrite);
        return new { session_id = id, path = destination, native = true, format = "midi", encoding = nativeEncoding,
                     midi_format = format, track_count = tracks, ticks_per_beat = division };
    }
}
