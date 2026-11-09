using System.IO;
using System.Text.Json.Nodes;
using Yamaha.VOCALOID.VSM;

internal sealed partial class EngineHost
{
    // Replay the managed wrapper's PasteTimeSig algorithm on a private snapshot,
    // recording each actual native bar before the corresponding duplicate.
    private Dictionary<int, ProjectArchiveArrays.TimeSig>? PrepareTimeSigMerge(
        EngineSession target, EngineSession source, long offsetTick, bool replace)
    {
        archiveStates.TryGetValue(target.Id, out ArchiveState? targetState);
        archiveStates.TryGetValue(source.Id, out ArchiveState? sourceState);
        if (targetState?.TimeSig is null && sourceState?.TimeSig is null) return null;
        var targetNative = ProjectArchiveArrays.ReadTimeSig(ArchiveNativeTimeSigs(target.Sequence), false);
        var sourceNative = ProjectArchiveArrays.ReadTimeSig(ArchiveNativeTimeSigs(source.Sequence), false);
        if (targetState?.TimeSig is not null) ProjectArchiveArrays.ValidateTimeSig(targetState.TimeSig, ArchiveNativeTimeSigs(target.Sequence));
        if (sourceState?.TimeSig is not null) ProjectArchiveArrays.ValidateTimeSig(sourceState.TimeSig, ArchiveNativeTimeSigs(source.Sequence));
        WIVSMTimeSig[] items = source.Sequence.TimeSigs.ToArray();
        if (items.Length != sourceNative.Count || items.Select(x => x.PosBar).Distinct().Count() != items.Length)
            throw new InvalidDataException("project_preservation: time signature source identities are not unique.");
        EngineSession candidate = CloneProject(target.Id, null);
        try
        {
            if (replace && !candidate.Sequence.RemoveTimeSigsEx(candidate.Sequence.TimeSigs))
                throw new InvalidOperationException("Native time signature probe replacement failed: " + candidate.Sequence.LastError);
            var baseline = ProjectArchiveArrays.ReadTimeSig(ArchiveNativeTimeSigs(candidate.Sequence), false);
            var result = new Dictionary<int, ProjectArchiveArrays.TimeSig>();
            if (!replace && (baseline.Count != targetNative.Count || baseline.Any(p => !targetNative.TryGetValue(p.Key, out var v) || v.Numer != p.Value.Numer || v.Denom != p.Value.Denom)))
                throw new InvalidDataException("project_preservation: time signature probe baseline diverged.");
            foreach (var (bar, value) in baseline)
            {
                JsonObject extra = !replace && targetState?.TimeSig is not null ? targetState.TimeSig[bar].Extra : value.Extra;
                result.Add(bar, new(bar, value.Numer, value.Denom, (JsonObject)extra.DeepClone()));
            }
            HashSet<int> remainingReplacementBaseline = replace ? baseline.Keys.ToHashSet() : [];
            WIVSMClipboard clipboard = manager.CreateClipboard(candidate.Sequence)
                ?? throw new InvalidOperationException("Native time signature probe clipboard creation failed: " + manager.LastError);
            try
            {
                if (!clipboard.PushTimeSigs(items) || clipboard.NumTimeSig != (ulong)items.Length)
                    throw new InvalidOperationException("Native time signature probe clipboard snapshot failed: " + clipboard.LastError);
                for (ulong i = 0; i < clipboard.NumTimeSig; i++)
                {
                    WIVSMTimeSig item = clipboard.GetTimeSig(i)
                        ?? throw new InvalidDataException("project_preservation: missing time signature probe event.");
                    if (item.PosBar != items[(int)i].PosBar || !sourceNative.TryGetValue(item.PosBar, out var original) || item.Numer != original.Numer || item.Denom != original.Denom)
                        throw new InvalidDataException("project_preservation: clipboard time signature identity diverged.");
                    int bar = candidate.Sequence.GetMostRecentBarFromTick(candidate.Sequence.GetTickFromBar(item.PosBar) + new VSMRelTick(offsetTick));
                    WIVSMTimeSig duplicate = candidate.Sequence.DuplicateTimeSig(bar, item)
                        ?? throw new InvalidOperationException("Native time signature probe duplicate failed: " + candidate.Sequence.LastError);
                    duplicate.IsSelected = true;
                    JsonObject extra = sourceState?.TimeSig?[original.Bar].Extra ?? original.Extra;
                    result[bar] = new(bar, original.Numer, original.Denom, (JsonObject)extra.DeepClone());
                    remainingReplacementBaseline.Remove(bar);
                    ProjectArchiveArrays.ValidateTimeSig(result, ArchiveNativeTimeSigs(candidate.Sequence));
                }
            }
            finally
            {
                if (!clipboard.Destroy()) throw new InvalidOperationException("Native time signature probe clipboard cleanup failed.");
                clipboard.Dispose();
            }
            if (remainingReplacementBaseline.Count != 0)
                throw new InvalidDataException("project_preservation: native time signature replacement retained unmatched target events.");
            return result;
        }
        finally { Close(candidate.Id, true); }
    }
}
