using System.IO;
using System.Text.Json;
using Yamaha.VOCALOID.VSM;
#if !VOCALOID7
using Yamaha.VOCALOID.VMM;
#endif

internal sealed partial class EngineHost
{
#if VOCALOID7
    internal bool IsPreservedMidiMediaImport(string? id, string operation, JsonElement options) => false;

    internal bool IsIndependentArchiveLibraryOperation(string? id, string operation, JsonElement options) =>
        operation is "style_update" or "style_delete";
#else
    // These operations read the sequence or change only bridge-owned library
    // files. Controller extensions remain guarded; MIDI part and note payloads
    // are carried by bridge-owned clip metadata.
    internal bool IsPreservedMidiMediaImport(string? id, string operation, JsonElement options)
    {
        if (operation != "media_import" || id is null) return false;
        EngineSession session = LibrarySession(id);
        if (!HasArchiveEntityExtensions(session)) return false;
        Clip clip = LibraryClip(LibraryText(options, "clip_id"));
        LibraryRequire(clip.ReadPart(), "read media before preservation guard");
        return true;
    }

    internal bool IsIndependentArchiveLibraryOperation(string? id, string operation, JsonElement options)
    {
        if (operation is "style_update" or "style_delete" or "media_update" or "media_delete" or "media_recovery_list" or "media_recovery_resolve")
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
        return true;
    }
#endif
}

