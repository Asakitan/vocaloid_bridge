using System.IO;
using System.Text.Json;
using Yamaha.VOCALOID.VSM;
using Yamaha.VOCALOID.VMM;

internal sealed partial class EngineHost
{
    // These operations read the sequence or change only bridge-owned library
    // files. Controller extensions remain guarded; MIDI part and note payloads
    // are carried by bridge-owned clip metadata.
    internal bool IsPreservedMidiMediaImport(string? id, string operation, JsonElement options)
    {
        if (operation != "media_import" || id is null) return false;
        EngineSession session = LibrarySession(id);
        if (!HasArchiveEntityExtensions(session) || ArchiveHasControllerExtensions(session)) return false;
        Clip clip = LibraryClip(LibraryText(options, "clip_id"));
        LibraryRequire(clip.ReadPart(), "read media before preservation guard");
        return clip.PartType is VMMPartType.Midi or VMMPartType.MidiAi;
    }

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
        if (partEntry.Controller is not null)
            throw new InvalidOperationException("project_preservation: selected media part has archive extensions not represented in the native clip.");
        if (track.Type is VSMTrackType.Midi or VSMTrackType.MidiAi)
        {
            WIVSMMidiPart midi = part as WIVSMMidiPart ?? new WIVSMMidiPart(part);
            foreach (WIVSMNote note in midi.Notes)
            {
                if (!state.Live.TryGetValue(ArchiveKey(note), out _))
                    throw new InvalidDataException("project_preservation: selected media note identity is not tracked.");
            }
        }
        return true;
    }
}
