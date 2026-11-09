using System.IO;
using System.Text.Json;
using Yamaha.VOCALOID.VSM;

internal sealed partial class EngineHost
{
    // These operations read the sequence or change only bridge-owned library
    // files. Media capture may proceed only when the selected part and notes
    // have no archive payload that native VMM would omit from the clip.
    internal bool IsIndependentArchiveLibraryOperation(string? id, string operation, JsonElement options)
    {
        if (operation is "style_capture" or "style_update" or "style_delete" or "media_update" or "media_delete")
            return true;
        if (operation != "media_capture") return false;
        EngineSession session = LibrarySession(id);
        if (!archiveStates.TryGetValue(session.Id, out ArchiveState? state) || !state.HasEntityExtensions)
            return true;
        ArchiveCheck(state);
        WIVSMTrack track = session.Sequence.GetTrack(LibraryIndex(options, "track_index"))
            ?? throw new ArgumentException("track_index was not found.");
        WIVSMPart part = track.GetPart(LibraryIndex(options, "part_index"))
            ?? throw new ArgumentException("part_index was not found.");
        if (!state.Live.TryGetValue(ArchiveKey(part), out ArchiveEntry? partEntry))
            throw new InvalidDataException("project_preservation: selected media part identity is not tracked.");
        if (partEntry.Extra.Count != 0 || partEntry.Controller is not null)
            throw new InvalidOperationException("project_preservation: selected media part has archive extensions not represented in the native clip.");
        if (track.Type is VSMTrackType.Midi or VSMTrackType.MidiAi)
        {
            WIVSMMidiPart midi = part as WIVSMMidiPart ?? new WIVSMMidiPart(part);
            foreach (WIVSMNote note in midi.Notes)
            {
                if (!state.Live.TryGetValue(ArchiveKey(note), out ArchiveEntry? noteEntry))
                    throw new InvalidDataException("project_preservation: selected media note identity is not tracked.");
                if (noteEntry.Extra.Count != 0)
                    throw new InvalidOperationException("project_preservation: selected media note has archive extensions not represented in the native clip.");
            }
        }
        return true;
    }
}
