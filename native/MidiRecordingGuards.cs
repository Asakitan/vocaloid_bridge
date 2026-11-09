internal sealed partial class EngineHost
{
    // MIDI device enumeration may omit a session. Check start before opening input.
    internal void CheckMidiStart(EngineSession session, string operation)
    {
        if (operation != "start") return;
        if (HasArchiveEntityExtensions(session))
            throw new InvalidOperationException("project_preservation: MIDI recording requires a verified entity-identity transaction.");
    }

    // Clipboard and library calls are routed before ordinary session RPCs.
    internal void CheckSessionExternalAccess(string? id)
    {
        if (id is null) return;
        EngineSession session = GetSession(id);
        if (HasMidiRecording(session))
            throw new InvalidOperationException("Stop or cancel MIDI recording before using this session's clipboard or library.");
        if (transport?.SessionId == session.Id)
            throw new InvalidOperationException("Release this session's transport before using its clipboard or library.");
    }
}
