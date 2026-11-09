using System.IO;
using System.Text.Json.Nodes;
using Yamaha.VOCALOID.VSM;

internal sealed partial class EngineHost
{
    // Called before any target mutation, including for a source without entity
    // extensions. Opaque resources have no transfer or collision contract yet.
    private void ArchiveTransferValidateSource(EngineSession source)
    {
        if (!archiveStates.TryGetValue(source.Id, out ArchiveState? state)) return;
        ArchiveCheck(state);
        if (state.ExtraFiles.Count != 0)
            throw new InvalidOperationException("project_preservation: source opaque archive resources have no transfer contract.");
    }

    private void ArchiveMergeValidateSource(EngineSession source)
    {
        ArchiveTransferValidateSource(source);
        if (archiveStates.TryGetValue(source.Id, out ArchiveState? state) &&
            (state.Root.Count != 0 || state.Master.Count != 0))
            throw new InvalidOperationException("project_preservation: source root or master extensions have no merge contract.");
    }

    // Call on a freshly returned native duplicate, inside a target archive
    // transaction, after moving a duplicated track's parts for its offset.
    // partOffset applies to track child parts or a directly duplicated part;
    // noteOffset applies to a directly duplicated note. Notes within copied
    // parts retain their relative positions.
    // Caller commits only after every mapping succeeds and rolls both journals
    // back on any exception. Target observer/state must already be initialized.
    private void ArchiveTransferCopy(EngineSession source, EngineSession target,
        object original, object duplicate, long partOffset = 0, long noteOffset = 0)
    {
        if (ReferenceEquals(source, target))
            throw new InvalidOperationException("project_preservation: transfer requires an independent snapshot.");
        ArchiveTransferValidateSource(source);
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
            pending.Add((b, new ArchiveEntry(extra, parent)));
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
            if (left is not WIVSMMidiPart a || right is not WIVSMMidiPart b ||
                a.IsAi != b.IsAi || left.Name != right.Name || left.DurationTick.Value != right.DurationTick.Value ||
                checked(left.AbsPosTick.Value + offset) != right.AbsPosTick.Value)
                throw new InvalidDataException("project_preservation: transferred MIDI part identity changed.");
            WIVSMMidiTrack sourceParent = a.Parent ?? throw new InvalidDataException("project_preservation: source part has no parent.");
            if (!source.Sequence.Tracks.Any(item => ArchiveKey(item) == ArchiveKey(sourceParent)) ||
                !sourceParent.Parts.Any(item => ArchiveKey(item) == ArchiveKey(left)))
                throw new InvalidDataException("project_preservation: source part is not in the snapshot.");
            Add(left, right, ArchiveKey(sourceParent), parent);
            Notes(a, b);
        }
        if (original is WIVSMTrack leftTrack && duplicate is WIVSMTrack rightTrack)
        {
            if (noteOffset != 0 || leftTrack.Type is not (VSMTrackType.Midi or VSMTrackType.MidiAi) ||
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
        else if (original is WIVSMMidiPart leftPart && duplicate is WIVSMMidiPart rightPart)
        {
            if (noteOffset != 0) throw new InvalidDataException("project_preservation: invalid part transfer offset.");
            WIVSMMidiTrack parent = rightPart.Parent ?? throw new InvalidDataException("project_preservation: transferred part has no parent.");
            Part(leftPart, rightPart, ArchiveKey(parent), partOffset);
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
        if (pending.Any(item => item.Entry.Extra.Count != 0)) to.HasEntityExtensions = true;
    }
}
