using System.Text.Json;
using Yamaha.VOCALOID.G2PA;
using Yamaha.VOCALOID.VSM;

internal static class V7Compat
{
#if VOCALOID7
    internal const string SettingsScope = "track";
    internal static WIVSMMidiTrack Track(WIVSMMidiTrack track) => track;
    internal static WIVSMMidiTrack Track(WIVSMMidiPart part) =>
        part.Parent ?? throw new System.InvalidOperationException("The native MIDI part has no track.");

    internal static string VoiceBankId(WIVSMMidiPart part) => Track(part).VoiceBankID;
    internal static string SecondaryVoiceBankId(WIVSMMidiPart part) => Track(part).SecondaryVoiceBankID;
    internal static string VoiceName(WIVSMMidiPart part) => Track(part).VoiceName;
    internal static string SecondaryVoiceName(WIVSMMidiPart part) => Track(part).SecondaryVoiceName;
    internal static int LangId(WIVSMMidiPart part) => Track(part).LangIDSize == 0 ? -1 : Track(part).LangIDByIndex(0);
    internal static System.Collections.Generic.List<int> LangIds(WIVSMMidiPart part) => Track(part).LangIDs;
    internal static bool IsAi(WIVSMMidiTrack track) => track.Type == VSMTrackType.MidiAi;
    internal static string VoiceBankId(WIVSMMidiTrack track) => track.VoiceBankID;
    internal static string SecondaryVoiceBankId(WIVSMMidiTrack track) => track.SecondaryVoiceBankID;
    internal static string VoiceName(WIVSMMidiTrack track) => track.VoiceName;
    internal static string SecondaryVoiceName(WIVSMMidiTrack track) => track.SecondaryVoiceName;
    internal static int LangId(WIVSMMidiTrack track) => track.LangIDSize == 0 ? -1 : track.LangIDByIndex(0);
    internal static List<int> LangIds(WIVSMMidiTrack track) => track.LangIDs;

    internal static bool? IsAiVibratoEnabled(WIVSMNote note) => null;

    internal static bool SetAiVibratoEnabled(WIVSMNote note, bool enabled) =>
        throw new NotSupportedException("VOCALOID7 has VibratoAiCurveModel; the legacy AI vibrato boolean has no verified equivalent.");

    internal static bool IsMute(WIVSMTrack track) => track.IsChannelMute;
    internal static void SetMute(WIVSMTrack track, bool mute)
    {
        if (track.IsChannelMute != mute)
            track.ToggleMute();
    }

    internal static bool IsSolo(WIVSMTrack track) => track.SoloState == VSMTrackSoloState.On;
    internal static void SetSolo(WIVSMTrack track, bool solo)
    {
        if (IsSolo(track) != solo)
            track.ToggleSolo();
    }
            internal static bool SetVoice(WIVSMMidiPart part, string value) => Track(part).SetVoiceBankID(value);
            internal static bool SetSecondaryVoice(WIVSMMidiPart part, string value) => Track(part).SetSecondaryVoiceBankID(value);
            internal static bool SetVoice(WIVSMMidiTrack track, string value) => track.SetVoiceBankID(value);
            internal static bool SetSecondaryVoice(WIVSMMidiTrack track, string value) => track.SetSecondaryVoiceBankID(value);
        #else
            internal const string SettingsScope = "part";
            internal static WIVSMMidiPart Track(WIVSMMidiPart part) => part;
            internal static string VoiceBankId(WIVSMMidiPart part) => part.IsAi ? part.AiVoiceBankID : part.VoiceBankID;
            internal static string SecondaryVoiceBankId(WIVSMMidiPart part) => part.IsAi ? part.SecondaryAiVoiceBankID : part.SecondaryVoiceBankID;
            internal static string VoiceName(WIVSMMidiPart part) => part.IsAi ? part.AiVoiceName : part.VoiceName;
            internal static string SecondaryVoiceName(WIVSMMidiPart part) => part.IsAi ? part.SecondaryAiVoiceName : part.SecondaryVoiceName;
            internal static int LangId(WIVSMMidiPart part) => part.LangID;
            internal static List<int> LangIds(WIVSMMidiPart part) => part.AiLangIDs;
            internal static bool IsAiVibratoEnabled(WIVSMNote note) => note.IsAiVibratoEnabled;
            internal static bool SetAiVibratoEnabled(WIVSMNote note, bool enabled) => note.SetAiVibratoEnabled(enabled);
            internal static bool IsMute(WIVSMTrack track) => track.IsMute;
            internal static void SetMute(WIVSMTrack track, bool mute) => track.SetMute(mute);
            internal static bool IsSolo(WIVSMTrack track) => track.IsSolo;
            internal static void SetSolo(WIVSMTrack track, bool solo) => track.SetSolo(solo);
            internal static bool SetVoice(WIVSMMidiPart part, string value) => part.IsAi ? part.SetAiVoiceBankID(value) : part.SetVoiceBankID(value);
            internal static bool SetSecondaryVoice(WIVSMMidiPart part, string value) => part.IsAi ? part.SetSecondaryAiVoiceBankID(value) : part.SetSecondaryVoiceBankID(value);
#endif
    internal static bool IsAi(WIVSMMidiPart part) => part.IsAi;

    internal static void RejectLegacyVibrato(JsonElement options, string field)
    {
#if VOCALOID7
        if (options.TryGetProperty(field, out _))
            throw new NotSupportedException("VOCALOID7 does not have a verified equivalent for " + field + "; use vibrato curve_model instead.");
#endif
    }

            internal static void RequireSettingsScope(JsonElement options)
            {
            string scope = options.TryGetProperty("scope", out JsonElement value) ? value.GetString() ?? "part" : "part";
        #if VOCALOID7
            if (scope != "track")
                throw new NotSupportedException("VOCALOID7 stores voice, style and performance on the track. Explicit scope='track' is required and affects every part on that track.");
        #else
            if (scope != "part")
                throw new NotSupportedException("VOCALOID6 voice, style and performance settings require scope='part'.");
        #endif
            }

            internal static List<List<(string Syllable, string Phonemes)>> CandidatePhonemes(G2PAManager manager, WIVSMNote note, string lyrics, bool extension, bool ai)
            {
        #if VOCALOID7
            return manager.CandidatePhonemes(note.G2PANote ?? throw new InvalidOperationException("Native G2PA note getter returned null."), lyrics, extension, ai)
                .Select(candidate => candidate.Select(item => (item.Syllable, item.Phonemes)).ToList()).ToList();
        #else
            return manager.CandidatePhonemes((nint)note, lyrics, extension, ai)
                .Select(candidate => candidate.Select(item => (item.Syllable, item.Phoneme)).ToList()).ToList();
        #endif
            }

            internal static bool SetLyrics(G2PAManager manager, WIVSMNote note, string lyrics, bool extension, bool ai, out int length)
            {
        #if VOCALOID7
            return manager.SetLyricsAndPhonemes(note.G2PANote ?? throw new InvalidOperationException("Native G2PA note getter returned null."), lyrics, extension, ai, out length);
        #else
            return manager.SetLyrics((nint)note, lyrics, extension, ai, out length);
        #endif
            }

            internal static bool SetPhonemes(G2PAManager manager, WIVSMNote note, string phonemes, bool ai)
            {
        #if VOCALOID7
            return manager.SetPhonemes(note.G2PANote ?? throw new InvalidOperationException("Native G2PA note getter returned null."), phonemes, ai);
        #else
            return manager.SetPhonemes((nint)note, phonemes, ai);
        #endif
            }

            internal static bool ResetLyrics(G2PAManager manager, WIVSMMidiPart part)
            {
        #if VOCALOID7
            return manager.NormalizeAllLyrics(part.G2PAMidiPart ?? throw new InvalidOperationException("Native G2PA part getter returned null."), part.IsAi);
        #else
            return manager.ResetLyrics((nint)part, part.IsAi);
        #endif
            }

            internal static bool ResetPhonemes(G2PAManager manager, WIVSMMidiPart part)
            {
        #if VOCALOID7
            return manager.NormalizeAllPhonemes(part.G2PAMidiPart ?? throw new InvalidOperationException("Native G2PA part getter returned null."), part.IsAi);
        #else
            return manager.ResetPhonemes((nint)part, part.IsAi);
        #endif
            }
        }
