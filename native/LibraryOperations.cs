using System.Buffers.Binary;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using Yamaha.VOCALOID.G2PA;
using Yamaha.VOCALOID.PathResource;
using Yamaha.VOCALOID.VEM;
using Yamaha.VOCALOID.VMM;
using Yamaha.VOCALOID.VSM;
using Yamaha.VOCALOID.VSStyle;
using NativeStyle = Yamaha.VOCALOID.VSStyle.Style;
using NativeStyleEffect = Yamaha.VOCALOID.VSStyle.Effect;
using NativeMutableEffect = Yamaha.VOCALOID.VMM.MutableEffect;

internal sealed partial class EngineHost
{
    [DllImport("vmm", EntryPoint = "VIS_VMM_MidiPartBase_secondaryVoiceBankID", CallingConvention = CallingConvention.Cdecl)]
    [DefaultDllImportSearchPaths(DllImportSearchPath.UserDirectories)]
    private static extern nint LibrarySecondaryVoiceBankId(nint part);

    [DllImport("vmm", EntryPoint = "VIS_VMM_MidiPartBase_secondaryAiVoiceBankID", CallingConvention = CallingConvention.Cdecl)]
    [DefaultDllImportSearchPaths(DllImportSearchPath.UserDirectories)]
    private static extern nint LibrarySecondaryAiVoiceBankId(nint part);

    private readonly Dictionary<G2PAManagerLangID, G2PAManager> libraryLyrics = new();
    private StyleManager? libraryStyles;
    private MediaManager? libraryMedia;

    private sealed class LibraryNoteValidity
    {
        [JsonRequired] public long Position { get; set; }
        [JsonRequired] public long Duration { get; set; }
        [JsonRequired] public int Number { get; set; }
        [JsonRequired] public string Lyric { get; set; } = "";
        [JsonRequired] public string Phonemes { get; set; } = "";
        [JsonRequired] public int LanguageId { get; set; }
        [JsonRequired] public bool IsValid { get; set; }
        public LibraryDvqmMetadata? AiAttack { get; set; }
        public LibraryDvqmMetadata? AiRelease { get; set; }
    }

    private sealed class LibraryDvqmMetadata
    {
        [JsonRequired] public string ComponentId { get; set; } = "";
        [JsonRequired] public List<string> LevelNames { get; set; } = [];
        [JsonRequired] public int Speed { get; set; }
        [JsonRequired] public float TopFactor { get; set; }
        [JsonRequired] public bool IsProtected { get; set; }
    }

    private sealed class LibraryClipValidity
    {
        [JsonRequired] public int Version { get; set; }
        [JsonRequired] public string ClipId { get; set; } = "";
        [JsonRequired] public List<LibraryNoteValidity> Notes { get; set; } = [];
    }

    private static LibraryNoteValidity LibrarySnapshotValidity(WIVSMNote note) => new()
    {
        Position = note.RelPosTick.Value, Duration = note.DurationTick.Value, Number = note.NoteNumber,
        Lyric = note.Lyric, Phonemes = note.Phonemes, LanguageId = note.LangID, IsValid = note.IsValidPhonemes
    };

    private LibraryNoteValidity LibrarySnapshotMediaNote(WIVSMNote note)
    {
        LibraryNoteValidity result = LibrarySnapshotValidity(note);
        if (!note.IsAi)
            return result;
        foreach (bool isAttack in new[] { true, false })
        {
            WIVSMDvqm? selection = note.GetDvqm(isAttack);
            if (selection is null || selection.IsEmpty)
                continue;
            var resolved = LibraryResolveDvqm(selection, isAttack);
            LibraryDvqmMetadata value = new()
            {
                ComponentId = resolved.Database.CompID, LevelNames = resolved.Property.LevelNames,
                Speed = selection.Speed, TopFactor = selection.TopFactor, IsProtected = selection.IsProtect
            };
            if (isAttack)
                result.AiAttack = value;
            else
                result.AiRelease = value;
        }
        return result;
    }

    internal object LibraryOperation(string? id, string operation, JsonElement options)
    {
        CheckThread();
        if (options.ValueKind is not (JsonValueKind.Object or JsonValueKind.Undefined or JsonValueKind.Null))
            throw new ArgumentException("options must be an object.");
        bool mediaOperation = operation.StartsWith("media_", StringComparison.Ordinal);
        using MediaLibraryLease? lease = mediaOperation ? new MediaLibraryLease(Workspace) : null;
        if (mediaOperation)
        {
            if (operation is not ("media_recovery_list" or "media_recovery_resolve")) MediaPropertyJournal.RecoverAll(Workspace);
            InvalidateMediaCatalog();
            mediaAccessDepth++;
        }
        try
        {
            object result = operation switch
            {
                "languages" => Enum.GetValues<G2PAManagerLangID>().Select(language => new
                {
                    language_id = (int)language,
                    name = language.ToString(),
                    default_lyric = LibraryLyrics(language).DefaultLyric()
                }).ToArray(),
                "phoneme_table" => LibraryPhonemeTable(options),
                "dvqm_catalog" => LibraryDvqmCatalog(options),
                "dvqm_get" => LibraryDvqmView(LibrarySession(id), options),
                "dvqm_set" or "dvqm_clear" => LibraryDvqmEdit(LibrarySession(id), operation, options),
                "singing_skill_catalog" => LibrarySingingSkillCatalog(),
                "singing_skill_get" => LibrarySingingSkillView(LibrarySession(id), options),
                "singing_skill_set" => LibrarySingingSkillEdit(LibrarySession(id), options),
                "note_skill_get" => LibraryNoteSkillView(LibrarySession(id), options),
                "note_skill_set" or "note_skill_reset" => LibraryNoteSkillEdit(LibrarySession(id), operation, options),
                "lyrics_can_convert" => LibraryCanConvert(options),
                "lyrics_candidates" => LibraryCandidates(LibrarySession(id), options),
                "lyrics_apply" or "phonemes_apply" or "lyrics_reset" or "phonemes_reset"
                    => LibraryApplyLyrics(LibrarySession(id), operation, options),
                "style_list" => LibraryStyleList(options),
                "style_get" => LibraryStyleView(LibraryStyle(LibraryText(options, "style_id")), true),
                "style_apply" => LibraryApplyStyle(LibrarySession(id), options),
                "style_capture" => LibraryCaptureStyle(LibrarySession(id), options),
                "style_update" => LibraryUpdateStyle(LibrarySession(id), options),
                "style_delete" => LibraryDeleteStyle(LibrarySession(id), options),
                "media_list" => LibraryMediaList(options),
                "media_get" => LibraryClipView(LibraryClip(LibraryText(options, "clip_id")), true),
                "media_update" => LibraryUpdateMedia(LibrarySession(id), options),
                "media_delete" => LibraryDeleteMedia(LibrarySession(id), options),
                "media_capture" => LibraryCaptureMedia(LibrarySession(id), options),
                "media_import" => LibraryImportMedia(LibrarySession(id), options),
                "media_recovery_list" => MediaPropertyJournal.ListPending(Workspace),
                "media_recovery_resolve" => MediaPropertyJournal.Resolve(Workspace, LibraryText(options, "journal_token"),
                    LibraryText(options, "choice"), LibraryText(options, "expected_revision")),
                _ => throw new ArgumentException("Unknown library operation: " + operation)
            };
            return new { session_id = id, operation, native = operation != "phoneme_table", result };
        }
        finally { if (mediaOperation) mediaAccessDepth--; }
    }

    private EngineSession LibrarySession(string? id) => GetSession(id
        ?? throw new ArgumentException("session_id is required for this operation."));

    private static JsonElement LibraryOption(JsonElement options, string name) =>
        options.ValueKind == JsonValueKind.Object && options.TryGetProperty(name, out JsonElement value)
            ? value : default;

    private static string LibraryText(JsonElement options, string name, string? fallback = null)
    {
        JsonElement value = LibraryOption(options, name);
        string text = value.ValueKind == JsonValueKind.Undefined && fallback is not null ? fallback
            : value.ValueKind == JsonValueKind.String ? value.GetString()!
            : throw new ArgumentException(name + " must be a string.");
        if (text.Length > 16384 || text.Contains('\0'))
            throw new ArgumentException(name + " is too long or contains NUL.");
        return text;
    }

    private static bool LibraryBool(JsonElement options, string name, bool fallback = false)
    {
        JsonElement value = LibraryOption(options, name);
        return value.ValueKind == JsonValueKind.Undefined ? fallback
            : value.ValueKind is JsonValueKind.True or JsonValueKind.False ? value.GetBoolean()
            : throw new ArgumentException(name + " must be boolean.");
    }

    private static ulong LibraryIndex(JsonElement options, string name, ulong fallback = 0)
    {
        JsonElement value = LibraryOption(options, name);
        return value.ValueKind == JsonValueKind.Undefined ? fallback
            : value.ValueKind == JsonValueKind.Number && value.TryGetUInt64(out ulong result) ? result
            : throw new ArgumentException(name + " must be a nonnegative integer.");
    }

    private static G2PAManagerLangID LibraryLanguage(JsonElement options, int fallback = 0)
    {
        JsonElement value = LibraryOption(options, "language_id");
        G2PAManagerLangID language;
        if (value.ValueKind == JsonValueKind.Undefined)
            language = (G2PAManagerLangID)fallback;
        else if (value.ValueKind == JsonValueKind.Number && value.TryGetInt32(out int number))
            language = (G2PAManagerLangID)number;
        else if (value.ValueKind == JsonValueKind.String && Enum.TryParse(value.GetString(), true, out language))
        { }
        else
            throw new ArgumentException("language_id must be a native G2PA language integer or name.");
        if (!Enum.IsDefined(language))
            throw new ArgumentException("language_id must be JPN/0, ENG/1, KOR/2, ESP/3, or CHS/4.");
        return language;
    }

    private static object LibraryPhonemeTable(JsonElement options)
    {
        G2PAManagerLangID language = LibraryLanguage(options);
        string symbols = language switch
        {
            G2PAManagerLangID.JPN => @"a i M e o k k' g g' N N' s S z Z dz dZ t t' ts tS d d' n J h h\ C p\ p\' b b' p p' m m' j 4 4' w N\",
            G2PAManagerLangID.ENG => "V e I i: { O: Q U u: @r eI aI OI @U aU I@ e@ U@ O@ Q@ w j b d g bh dh gh dZ v D z Z m n N r l l0 p t k ph th kh tS f T s S h @",
            G2PAManagerLangID.KOR => "a ja 7 j7 o jo u ju M i e je oa u7 ue ui Mi g gp n np d dp r l rp m mp b bp s sh N Np c ch k t p h g' d' b' s' sh' c'",
            G2PAManagerLangID.ESP => @"a e i o u I U j w p t k b d g B D G tS f T s x m n J l r rr L j\",
            G2PAManagerLangID.CHS => @"a o 7 i u y @` i\ i` aI ei AU @U ia iE_r ua uo yE_r iAU i@U uaI uei a_n @_n i_n iE_n ua_n u@_n y_n y{_n AN @N iN iAN uAN u@N UN iUN p p_h m f t t_h n l k k_h x ts\ ts\_h s\ ts` ts`_h s` z` ts ts_h s",
            _ => throw new ArgumentException("Unsupported phoneme table language.")
        };
        return new
        {
            language_id = (int)language,
            language = language.ToString(),
            symbols = symbols.Split(' ', StringSplitOptions.RemoveEmptyEntries),
            source = "VOCALOID6 Reference Manual V6.13.0",
            source_pages = language switch
            {
                G2PAManagerLangID.JPN => new[] { 80, 81 },
                G2PAManagerLangID.ENG => new[] { 77, 78, 79 },
                G2PAManagerLangID.KOR => new[] { 82, 83 },
                G2PAManagerLangID.ESP => new[] { 84, 85 },
                G2PAManagerLangID.CHS => new[] { 86, 87, 88, 89, 90, 91 },
                _ => Array.Empty<int>()
            },
            ai_unvoiced_symbols = language == G2PAManagerLangID.JPN ? new[] { "N", "N'" } : Array.Empty<string>(),
            native_enumeration = false
        };
    }

    private object LibraryDvqmCatalog(JsonElement options)
    {
        bool isAttack = LibraryBool(options, "is_attack", true);
        string voiceId = LibraryText(options, "voice_id", "");
        ulong offset = LibraryIndex(options, "offset");
        ulong limit = LibraryIndex(options, "limit", 100);
        if (offset > int.MaxValue || limit is < 1 or > 256)
            throw new ArgumentException("offset must be nonnegative and limit must be 1..256.");
        EnsureVoiceServices();
        var manager = EnsureDatabase();
        var databases = voiceId.Length == 0
            ? LibraryValues(manager.NumDvqmDBs, manager.GetDvqmDBByIndex).Where(value => value is not null).ToList()
            : manager.GetDvqmDBList(voiceId).Cast<Yamaha.VOCALOID.VDM.DvqmDB?>().ToList();
        List<object> entries = [];
        foreach (var database in databases)
        {
            if (database is null)
                throw new InvalidOperationException("Native DVQM database lookup failed.");
            foreach (var property in LibraryValues(database.NumDvqmProperties(isAttack),
                         index => database.GetDvqmPropertyByIndex(isAttack, index)))
            {
                if (property is null)
                    throw new InvalidOperationException("Native DVQM property lookup failed.");
                string[] levelNames = LibraryValues(property.NumLevelNames, property.GetLevelName);
                entries.Add(new
                {
                    db_id = database.ID, component_id = database.CompID, language_id = database.LangID,
                    name_id = property.ID, level_names = levelNames, is_attack = isAttack,
                    can_speed_control = property.CanSpeedControl, has_vibrato = property.HasVibrato
                });
            }
        }
        return new
        {
            is_attack = isAttack, voice_id = voiceId, total = entries.Count, offset, limit,
            entries = entries.Skip((int)offset).Take((int)limit).ToArray()
        };
    }

    private static WIVSMMidiPart LibraryMidiPart(EngineSession session, JsonElement options)
    {
        WIVSMTrack track = session.Sequence.GetTrack(LibraryIndex(options, "track_index"))
            ?? throw new ArgumentException("track_index was not found.");
        if (track.Type is not (VSMTrackType.Midi or VSMTrackType.MidiAi))
            throw new ArgumentException("This operation requires a MIDI or MIDI AI track.");
        return new WIVSMMidiTrack(track).GetPart(LibraryIndex(options, "part_index"))
            ?? throw new ArgumentException("part_index was not found.");
    }

    private static WIVSMNote LibraryNote(WIVSMMidiPart part, JsonElement options) =>
        part.GetNote(LibraryIndex(options, "note_index"))
            ?? throw new ArgumentException("note_index was not found.");

    private (Yamaha.VOCALOID.VDM.DvqmDB Database, Yamaha.VOCALOID.VDM.DvqmProperty Property)
        LibraryResolveDvqm(WIVSMDvqm selection, bool isAttack)
    {
        if (selection.DBID < 0 || selection.NameID < 0)
            throw new InvalidDataException("The native Attack/Release selection has incomplete database IDs.");
        var database = EnsureDatabase().GetDvqmDBByID(selection.DBID)
            ?? throw new InvalidOperationException("The native Attack/Release database is not installed: " + selection.DBID);
        var property = database.GetDvqmPropertyByID(isAttack, selection.NameID)
            ?? throw new InvalidOperationException("The native Attack/Release name is not installed: " + selection.NameID);
        if (database.CompID.Length == 0 || property.NumLevelNames == 0 || property.LevelNames.Count != (int)property.NumLevelNames)
            throw new InvalidDataException("The native Attack/Release selection has incomplete component or level names.");
        return (database, property);
    }

    private object LibraryDvqmView(EngineSession session, JsonElement options)
    {
        bool isAttack = LibraryBool(options, "is_attack", true);
        WIVSMDvqm selection = LibraryNote(LibraryMidiPart(session, options), options).GetDvqm(isAttack)
            ?? throw new NotSupportedException("The native note has no Attack/Release record.");
        string? componentId = null;
        string[] levels = [];
        if (!selection.IsEmpty)
        {
            var resolved = LibraryResolveDvqm(selection, isAttack);
            componentId = resolved.Database.CompID;
            levels = resolved.Property.LevelNames.ToArray();
        }
        return new
        {
            is_attack = isAttack, is_empty = selection.IsEmpty, db_id = selection.DBID, name_id = selection.NameID,
            component_id = componentId, level_names = levels, speed = selection.Speed,
            top_factor = selection.TopFactor, is_protected = selection.IsProtect
        };
    }

    private object LibraryDvqmEdit(EngineSession session, string operation, JsonElement options)
    {
        bool isAttack = LibraryBool(options, "is_attack", true);
        WIVSMDvqm selection = LibraryNote(LibraryMidiPart(session, options), options).GetDvqm(isAttack)
            ?? throw new NotSupportedException("The native note has no Attack/Release record.");
        if (operation == "dvqm_clear")
            return ScoreMutate(session, operation, () =>
            {
                if (!selection.IsEmpty)
                    LibraryRequire(selection.Reset(), operation);
                return true;
            }, () => LibraryDvqmView(session, options));
        int databaseId = ScoreInt(options, "db_id", 0, int.MaxValue);
        int nameId = ScoreInt(options, "name_id", 0, int.MaxValue);
        var database = EnsureDatabase().GetDvqmDBByID(databaseId)
            ?? throw new ArgumentException("The requested native Attack/Release database is not installed.");
        if (database.GetDvqmPropertyByID(isAttack, nameId) is null)
            throw new ArgumentException("The requested native Attack/Release name is not installed.");
        int? speed = options.TryGetProperty("speed", out _) ? ScoreInt(options, "speed", int.MinValue, int.MaxValue) : null;
        float? topFactor = options.TryGetProperty("top_factor", out _)
            ? ScoreFloat(options, "top_factor", float.MinValue, float.MaxValue) : null;
        bool? protect = options.TryGetProperty("is_protected", out _) ? LibraryBool(options, "is_protected") : null;
        return ScoreMutate(session, operation, () =>
        {
            LibraryRequire(selection.Set(databaseId, nameId, false), operation);
            if (speed.HasValue && selection.Speed != speed.Value)
                LibraryRequire(selection.SetSpeed(speed.Value), operation + " speed");
            if (topFactor.HasValue && selection.TopFactor != topFactor.Value)
                LibraryRequire(selection.SetTopFactor(topFactor.Value), operation + " top factor");
            if (protect.HasValue)
                selection.SetProtect(protect.Value);
            return true;
        }, () => LibraryDvqmView(session, options));
    }

    private static object LibraryNoteView(WIVSMNote note) => new
    {
        tick = note.RelPosTick.Value,
        duration = note.DurationTick.Value,
        note_number = note.NoteNumber,
        lyric = note.Lyric,
        phonemes = note.Phonemes,
        language_id = note.LangID,
        valid_phonemes = note.IsValidPhonemes,
        @protected = note.IsProtected
    };

    private static Yamaha.VOCALOID.LuaManager LibrarySkillManager() => new();

    private static object LibrarySingingSkillCatalog() => new
    {
        skills = LibrarySkillManager().SingingSkillList.Select(skill => new
        {
            name = skill.Name, plugin_id = skill.PluginID, genres = skill.GenreTags,
            timing = skill.Timing.ToString(), available = !string.IsNullOrEmpty(skill.LuaFilePath) && File.Exists(skill.LuaFilePath)
        }).ToArray()
    };

    private static void PrepareSingingSkill(WIVSMMidiPart part)
    {
        if (part.IsAi) return;
        WIVSMSingingSkillEffect? effect = part.SingingSkillEffect;
        if (effect is null || part.IsBypassed(VSMMidiEffectType.SingingSkill))
            return;
        Yamaha.VOCALOID.LuaManager manager = LibrarySkillManager();
        Yamaha.VOCALOID.SingingSkill skill = manager.GetSingingSkillByPluginID(effect.PluginID)
            ?? throw new InvalidOperationException("The selected native Singing Skill is not installed.");
        if (string.IsNullOrEmpty(skill.LuaFilePath) || !File.Exists(skill.LuaFilePath))
            throw new FileNotFoundException("The selected native Singing Skill script is missing.");
        PathGuard.NoLinks(skill.LuaFilePath);
        LibraryRequire(manager.SetScriptFilePathToMidiEffectSingingSkill(effect) &&
            manager.SetTimingToMidiEffectSingingSkill(effect), "prepare Singing Skill runtime");
    }

    private object LibrarySingingSkillView(EngineSession session, JsonElement options)
    {
        WIVSMMidiPart part = LibraryMidiPart(session, options);
        if (part.IsAi) throw new NotSupportedException("Singing Skill is available on classic VOCALOID parts.");
        WIVSMSingingSkillEffect effect = part.SingingSkillEffect
            ?? throw new NotSupportedException("Singing Skill is available on classic VOCALOID parts.");
        return new
        {
            plugin_id = effect.PluginID, skill = effect.Skill, amount = effect.Amount,
            bypassed = effect.IsBypassed, skill_bounds = effect.SkillSetting, amount_bounds = effect.AmountSetting,
            timing = effect.Timing.ToString()
        };
    }

    private object LibrarySingingSkillEdit(EngineSession session, JsonElement options)
    {
        WIVSMMidiPart part = LibraryMidiPart(session, options);
        if (part.IsAi) throw new NotSupportedException("Singing Skill is available on classic VOCALOID parts.");
        WIVSMSingingSkillEffect effect = part.SingingSkillEffect
            ?? throw new NotSupportedException("Singing Skill is available on classic VOCALOID parts.");
        string plugin = LibraryText(options, "plugin_id", effect.PluginID);
        if (LibrarySkillManager().GetSingingSkillByPluginID(plugin) is null)
            throw new ArgumentException("plugin_id must identify an installed native Singing Skill.");
        int skill = options.TryGetProperty("skill", out _) ? ScoreInt(options, "skill", effect.SkillSetting.LowerBoundValue, effect.SkillSetting.UpperBoundValue) : effect.Skill;
        int amount = options.TryGetProperty("amount", out _) ? ScoreInt(options, "amount", effect.AmountSetting.LowerBoundValue, effect.AmountSetting.UpperBoundValue) : effect.Amount;
        bool bypass = LibraryBool(options, "bypassed", effect.IsBypassed);
        return ScoreMutate(session, "singing_skill_set", () =>
        {
            if (effect.PluginID != plugin) LibraryRequire(effect.SetPluginID(plugin), "Singing Skill plugin");
            if (effect.Skill != skill) LibraryRequire(effect.SetSkill(skill), "Singing Skill level");
            if (effect.Amount != amount) LibraryRequire(effect.SetAmount(amount), "Singing Skill amount");
            if (effect.IsBypassed != bypass) LibraryRequire(effect.SetBypass(bypass), "Singing Skill bypass");
            PrepareSingingSkill(part);
            return true;
        }, () => LibrarySingingSkillView(session, options));
    }

    private object LibraryNoteSkillView(EngineSession session, JsonElement options)
    {
        WIVSMNote note = LibraryNote(LibraryMidiPart(session, options), options);
        return new { duration_tick = note.HmmWeightDuration, pre_weight = note.PreHmmWeight, post_weight = note.PostHmmWeight };
    }

    private object LibraryNoteSkillEdit(EngineSession session, string operation, JsonElement options)
    {
        WIVSMNote note = LibraryNote(LibraryMidiPart(session, options), options);
        int duration = options.TryGetProperty("duration_tick", out _) ? ScoreInt(options, "duration_tick", 0, checked((int)note.DurationTick.Value)) : note.HmmWeightDuration;
        int pre = options.TryGetProperty("pre_weight", out _) ? ScoreInt(options, "pre_weight", 0, 127) : note.PreHmmWeight;
        int post = options.TryGetProperty("post_weight", out _) ? ScoreInt(options, "post_weight", 0, 127) : note.PostHmmWeight;
        return ScoreMutate(session, operation, () =>
        {
            if (operation == "note_skill_reset") LibraryRequire(note.ResetHmmWeightDefault(), operation);
            else
            {
                if (duration != note.HmmWeightDuration) LibraryRequire(note.SetHmmWeightDuration(new VSMRelTick(duration)), operation);
                if (pre != note.PreHmmWeight || post != note.PostHmmWeight) LibraryRequire(note.SetHmmWeight(pre, post), operation);
            }
            return true;
        }, () => LibraryNoteSkillView(session, options));
    }

    private object LibraryCanConvert(JsonElement options)
    {
        G2PAManagerLangID language = LibraryLanguage(options);
        string lyrics = LibraryText(options, "lyrics");
        return new
        {
            language_id = (int)language,
            lyrics,
            can_convert = LibraryLyrics(language).CanConvert(lyrics,
                LibraryBool(options, "use_extension_dictionary"), LibraryBool(options, "is_ai"))
        };
    }

    private object LibraryCandidates(EngineSession session, JsonElement options)
    {
        WIVSMNote note = LibraryNote(LibraryMidiPart(session, options), options);
        G2PAManagerLangID language = LibraryLanguage(options, note.LangID);
        string lyrics = LibraryText(options, "lyrics");
        var candidates = LibraryLyrics(language).CandidatePhonemes((nint)note, lyrics,
            LibraryBool(options, "use_extension_dictionary"), note.IsAi);
        return new
        {
            language_id = (int)language,
            lyrics,
            candidates = candidates.Select(candidate => candidate.Select(syllable => new
            {
                lyric = syllable.Syllable,
                phonemes = syllable.Phoneme
            }).ToArray()).ToArray()
        };
    }

    private object LibraryApplyLyrics(EngineSession session, string operation, JsonElement options)
    {
        ScoreRequireUnstaged(session.Sequence);
        WIVSMMidiPart part = LibraryMidiPart(session, options);
        int affectedLength = 0;
        return ScoreMutate(session, operation, () =>
        {
            if (operation is "lyrics_reset" or "phonemes_reset")
            {
                int[] languages = LibraryOption(options, "language_id").ValueKind != JsonValueKind.Undefined
                    ? [(int)LibraryLanguage(options)]
                    : part.Notes.Select(note => note.LangID).Append(part.LangID)
                        .Where(language => Enum.IsDefined((G2PAManagerLangID)language)).Distinct().ToArray();
                if (languages.Length == 0)
                    throw new ArgumentException("language_id is required because the part and its notes have no initialized native language.");
                G2PAManager[] managers = languages.Select(language => LibraryLyrics((G2PAManagerLangID)language)).ToArray();
                foreach (G2PAManager manager in managers)
                    LibraryRequire(operation == "lyrics_reset"
                        ? manager.ResetLyrics((nint)part, part.IsAi)
                        : manager.ResetPhonemes((nint)part, part.IsAi), operation);
                affectedLength = part.Notes.Count;
            }
            else
            {
                WIVSMNote note = LibraryNote(part, options);
                G2PAManagerLangID requestedLanguage = LibraryLanguage(options, note.LangID);
                G2PAManager manager = LibraryLyrics(requestedLanguage);
                string text = LibraryText(options, operation == "lyrics_apply" ? "lyrics" : "phonemes");
                bool extension = LibraryBool(options, "use_extension_dictionary");
                bool? protect = LibraryOption(options, "protect").ValueKind == JsonValueKind.Undefined
                    ? null : LibraryBool(options, "protect");
                if (operation == "phonemes_apply")
                {
                    LibraryRequire(manager.SetPhonemes((nint)note, text, note.IsAi), operation);
                    affectedLength = 1;
                }
                else
                {
                    if (!manager.CanConvert(text, extension, note.IsAi))
                        throw new ArgumentException("Native G2PA does not accept the requested lyrics.");
                    WIVSMNote[] before = part.Notes.ToArray();
                    int first = ScoreNoteIndex(part, note);
                    var candidates = manager.CandidatePhonemes((nint)note, text, extension, note.IsAi);
                    string[] states = before.Select(item => LibraryLyricState(item, false)).ToArray();
                    string[] fullStates = before.Select(item => LibraryLyricState(item, true)).ToArray();
                    LibraryRequire(manager.SetLyrics((nint)note, text, extension, note.IsAi, out affectedLength), operation);
                    WIVSMNote[] after = part.Notes.ToArray();
                    if (affectedLength < 1 || affectedLength > after.Length - first || before.Length != after.Length)
                        throw new InvalidOperationException("Native G2PA did not cover the requested phrase within the available notes.");
                    for (int i = 0; i < after.Length; i++)
                    {
                        bool affected = i >= first && i < first + affectedLength;
                        if (!after[i].Equals(before[i]) || (affected ? LibraryLyricState(after[i], false) != states[i]
                            : LibraryLyricState(after[i], true) != fullStates[i]))
                            throw new InvalidOperationException("Native G2PA changed a note outside its lyric assignment.");
                    }
                    WIVSMNote[] applied = after.Skip(first).Take(affectedLength).ToArray();
                    if (applied.Any(item => item.LangID != (int)requestedLanguage || !item.IsValidPhonemes || string.IsNullOrEmpty(item.Phonemes)))
                        throw new InvalidOperationException("Native G2PA returned invalid phrase phonemes.");
                    if (candidates.Count > 0)
                    {
                        if (!candidates.Any(candidate => candidate.Count == applied.Length &&
                            candidate.Zip(applied).All(pair => pair.First.Syllable == pair.Second.Lyric && pair.First.Phoneme == pair.Second.Phonemes)))
                            throw new InvalidOperationException("Native G2PA did not preserve a complete phrase candidate.");
                    }
                    else
                    {
                        string Compact(string value) => new(value.Where(character => !char.IsWhiteSpace(character)).ToArray());
                        if (Compact(string.Concat(applied.Select(item => item.Lyric))) != Compact(text))
                            throw new InvalidOperationException("Native G2PA truncated the requested phrase.");
                    }
                }
                if (protect.HasValue)
                {
                    note.IsProtected = protect.Value;
                    LibraryRequire(note.IsProtected == protect.Value, "lyric protection readback");
                }
            }
            return true;
        }, () => new
        {
            session_id = session.Id,
            operation,
            affected_length = affectedLength,
            notes = LibraryMidiPart(session, options).Notes.Select(LibraryNoteView).ToArray()
        });
    }

    private static string LibraryLyricState(WIVSMNote note, bool includeLyrics) => JsonSerializer.Serialize(
        JsonSerializer.SerializeToElement(ScoreNoteSummary(note, 0)).EnumerateObject()
            .Where(item => includeLyrics || item.Name is not ("lyric" or "phonemes" or "is_valid_phonemes" or "lang_id"))
            .ToDictionary(item => item.Name, item => item.Value));

    private static void LibraryRequire(bool result, string operation)
    {
        if (!result)
            throw new InvalidOperationException("Native library operation failed: " + operation + ".");
    }

    private static void LibraryCommit(EngineSession session, string operation)
    {
        bool staged = session.Sequence.IsStaged;
        if (!session.Sequence.Commit(false) && (staged || session.Sequence.LastError != VSMResult.NoError))
            throw new InvalidOperationException("Native library commit failed for " + operation + ": " + session.Sequence.LastError);
    }

    private string LibraryDirectory(string child)
    {
        string path = Path.Combine(RuntimeRoot, "library", child);
        PathGuard.CreateDirectory(path);
        return path;
    }

    private static string[] LibraryReadOnlyRoots(ResourceType resource) =>
        resource.SystemExtraPaths().Concat([resource.UserPrimaryPath()]).Concat(resource.UserExtraPaths())
            .Where(path => !string.IsNullOrEmpty(path) && Directory.Exists(path))
            .Select(Path.GetFullPath).Distinct(StringComparer.OrdinalIgnoreCase).ToArray();

    private StyleManager LibraryStyles()
    {
        if (libraryStyles is not null)
            return libraryStyles;
        StyleManager? created = StyleManagerIF.CreateStyleManager("VOCALOID6",
            ResourceType.StylePreset.SystemPrimaryPath(), LibraryDirectory("styles"),
            LibraryReadOnlyRoots(ResourceType.StylePreset), [], out VSStyleError result);
        if (created is null || result != VSStyleError.None)
        {
            created?.Dispose();
            throw new InvalidOperationException("Native style manager creation failed: " + result);
        }
        try
        {
            result = created.ReadSystemStyles();
            if (result != VSStyleError.None)
                throw new InvalidOperationException("Native system style load failed: " + result);
            result = created.ReadUserStyles();
            if (result != VSStyleError.None)
                throw new InvalidOperationException("Native private style load failed: " + result);
            libraryStyles = created;
            return created;
        }
        catch
        {
            created.Dispose();
            throw;
        }
    }

    private MediaManager LibraryMedia()
    {
        if (libraryMedia is not null)
            return libraryMedia;
        using MediaLibraryLease? lease = mediaAccessDepth == 0 ? new MediaLibraryLease(Workspace) : null;
        if (lease is not null) MediaPropertyJournal.RecoverAll(Workspace);
        VMMError result = VMMError.None;
        MediaManager? created = MediaManagerIF.CreateMediaManager("VOCALOID6",
            ResourceType.Media.SystemPrimaryPath(), LibraryDirectory("media"),
            LibraryReadOnlyRoots(ResourceType.Media), [], ref result);
        if (created is null || result != VMMError.None)
        {
            created?.Dispose();
            throw new InvalidOperationException("Native media manager creation failed: " + result);
        }
        try
        {
            result = created.ReadAllClipFiles();
            if (result != VMMError.None)
                throw new InvalidOperationException("Native media catalog load failed: " + result);
            libraryMedia = created;
            return created;
        }
        catch
        {
            created.Dispose();
            throw;
        }
    }

    private static T[] LibraryValues<T>(ulong count, Func<ulong, T> read)
    {
        T[] values = new T[checked((int)count)];
        for (ulong index = 0; index < count; index++)
            values[checked((int)index)] = read(index);
        return values;
    }

    private static string[] LibraryStrings(JsonElement options, string name)
    {
        JsonElement value = LibraryOption(options, name);
        if (value.ValueKind == JsonValueKind.Undefined)
            return [];
        if (value.ValueKind != JsonValueKind.Array)
            throw new ArgumentException(name + " must be a string array.");
        return value.EnumerateArray().Select(item => item.ValueKind == JsonValueKind.String
            ? item.GetString()! : throw new ArgumentException(name + " must contain strings.")).ToArray();
    }

    private NativeStyle LibraryStyle(string id) => LibraryStyles().AllStylesEnumerator
        .FirstOrDefault(style => style.Id == id)
        ?? throw new ArgumentException("style_id was not found in the native catalog.");

    private Clip LibraryClip(string id) => LibraryMedia().AllClipEnumerator()
        .FirstOrDefault(clip => clip.ID == id)
        ?? throw new ArgumentException("clip_id was not found in the native catalog.");

    private static object LibraryStyleEffectView(NativeStyleEffect effect) => new
    {
        id = effect.Id,
        type = effect.Type.ToString(),
        bypassed = effect.IsBypassed,
        parameters = LibraryValues(effect.NumParameter, index =>
        {
            Parameter parameter = effect.Parameter(index);
            object value = parameter.Type switch
            {
                VSStyleEffectParameterType.Int => parameter.ValueInt,
                VSStyleEffectParameterType.Float => parameter.ValueFloat,
                VSStyleEffectParameterType.String => parameter.ValueString,
                _ => throw new InvalidDataException("Unsupported native style parameter type: " + parameter.Type)
            };
            return new { name = parameter.Name, type = parameter.Type.ToString(), value };
        })
    };

    private static object LibraryStyleView(NativeStyle style, bool details) => new
    {
        style_id = style.Id,
        name = style.Name,
        type = style.Type.ToString(),
        path = style.Path,
        vendor = style.Vendor,
        languages = LibraryValues(style.NumLanguage, style.Language),
        singers = LibraryValues(style.NumSingerID, style.SingerID),
        genres = LibraryValues(style.NumGenre, style.Genre),
        sub_genres = LibraryValues(style.NumSubGenre, style.SubGenre),
        colors = LibraryValues(style.NumColor, style.Color),
        midi_effect_count = style.NumMidiEffect,
        audio_effect_count = style.NumAudioEffect,
        midi_effects = details ? LibraryValues(style.NumMidiEffect, index =>
            LibraryStyleEffectView(style.MidiEffect(index)
                ?? throw new InvalidDataException("Native style MIDI effect was null."))) : null,
        audio_effects = details ? LibraryValues(style.NumAudioEffect, index =>
            LibraryStyleEffectView(style.AudioEffect(index)
                ?? throw new InvalidDataException("Native style audio effect was null."))) : null
    };

    private object LibraryStyleList(JsonElement options)
    {
        var matches = StyleManager.FilteredStyleList(LibraryStyles().AllStylesEnumerator,
            LibraryText(options, "query", ""), LibraryStrings(options, "sub_genres").ToList(),
            LibraryStrings(options, "colors").ToList());
        return new { total = matches.Count, styles = matches.Select(style => LibraryStyleView(style, false)).ToArray() };
    }

    private UserStyle LibraryOwnedStyle(string id)
    {
        if (LibraryStyle(id) is not UserStyle style)
            throw new ArgumentException("Only bridge-owned private styles may be edited or deleted.");
        string root = LibraryDirectory("styles");
        PathGuard.Under(root, Path.GetRelativePath(root, Path.GetFullPath(style.Path)));
        PathGuard.NoLinks(style.Path);
        return style;
    }

    private static void LibraryCaptureStyleEffect(WIVSMEffect source, Yamaha.VOCALOID.VSStyle.MutableEffect target)
    {
        target.AddParameter("Bypass").ValueInt = source.IsBypassed ? 1 : 0;
        foreach (WIVSMEffectValue value in source.GetEffectValues)
        {
            if (value.Name == "Bypass") continue;
            MutableParameter parameter = target.AddParameter(value.Name);
            switch (value.Type)
            {
                case VSMEffectValueType.Int: parameter.ValueInt = value.RawInt; break;
                case VSMEffectValueType.Float: parameter.ValueFloat = value.RawFloat; break;
                case VSMEffectValueType.String: parameter.ValueString = value.RawString; break;
                default: throw new InvalidDataException("Unsupported native style parameter type.");
            }
        }
    }

    private object LibraryCaptureStyle(EngineSession session, JsonElement options)
    {
        bool includeAudio = LibraryBool(options, "include_audio", true);
        LibraryRequireStyleTransportReleased(includeAudio);
        WIVSMMidiPart part = LibraryMidiPart(session, options);
        string name = LibraryText(options, "name");
        string overwriteId = LibraryText(options, "overwrite_style_id", "");
        if (overwriteId.Length != 0) LibraryOwnedStyle(overwriteId);
        MutableStyle draft = LibraryStyles().CreateMutableStyle();
        try
        {
            draft.Name = name;
            if (part.LangID >= 0) LibraryRequire(draft.AddLanguage(part.LangID), "capture style language");
            foreach (string tag in LibraryStrings(options, "sub_genres")) LibraryRequire(draft.AddSubGenre(tag), "capture style genre");
            foreach (string tag in LibraryStrings(options, "colors")) LibraryRequire(draft.AddColor(tag), "capture style color");
            WIVSMEffectManager effects = part.EffectManager
                ?? throw new InvalidOperationException("Native part effect manager is absent.");
            ulong destination = 0;
            for (ulong index = 0; index < effects.NumMidiEffect; index++)
            {
                WIVSMMidiEffect effect = effects.GetMidiEffectByIndex(index)!;
                if (effect.Id != "DefaultLyric") LibraryCaptureStyleEffect(effect, draft.InsertMidiEffect(destination++, effect.Id));
            }
            if (includeAudio)
                LibraryCaptureStyleAudio(effects, draft);
            VSStyleError error = VSStyleError.None;
            UserStyle? saved = overwriteId.Length == 0 ? draft.Save(true, ref error) : draft.Overwrite(overwriteId, true, ref error);
            if (saved is null || error != VSStyleError.None)
                throw new InvalidOperationException("Native style save failed: " + error);
            string savedId = saved.Id;
            if (LibraryStyles().ReadUserStyles() != VSStyleError.None)
                throw new InvalidOperationException("Native style catalog refresh failed.");
            UserStyle verified = LibraryOwnedStyle(savedId);
            if (!File.Exists(verified.Path)) throw new IOException("Native style save did not create its file.");
            return new { session_id = session.Id, style = LibraryStyleView(verified, true) };
        }
        finally { draft.Destroy(); }
    }

    private void LibraryRequireStyleTransportReleased(bool includeAudio)
    {
        if (includeAudio && transport is not null)
            throw new InvalidOperationException("Release the native transport before using style audio effects.");
    }

    private void LibraryCaptureStyleAudio(WIVSMEffectManager effects, MutableStyle draft)
    {
        if (effects.NumAudioEffect == 0) return;
        WEffectManager manager = EnsureAudioEffects();
        manager.ResetAll();
        try
        {
            WEffectBlock block = manager.AddMasterBlock((nint)1)
                ?? throw new InvalidOperationException("Native style normalization block could not be created.");
            for (ulong index = 0; index < effects.NumAudioEffect; index++)
            {
                WIVSMAudioEffect effect = effects.GetAudioEffect(index)!;
                if (block.AddLoadEffect(effect.Id) is null)
                    throw new InvalidOperationException("Native style effect could not be loaded: " + effect.Id);
                Yamaha.VOCALOID.VSStyle.MutableEffect target = draft.InsertAudioEffect(index, effect.Id);
                target.AddParameter("Bypass").ValueInt = effect.IsBypassed ? 1 : 0;
                foreach (WIVSMEffectValue value in effect.GetEffectValues)
                {
                    if (value.Name == "Bypass") continue;
                    if (value.Type != VSMEffectValueType.Float || !float.IsFinite(value.RawFloat))
                        throw new InvalidDataException("Native audio effect value must be normalized: " + value.Name);
                    target.AddParameter(value.Name).ValueInt = block.ToPlain(effect.Id, value.Name, value.RawFloat);
                }
            }
        }
        finally { manager.ResetAll(); }
    }

    private object LibraryUpdateStyle(EngineSession session, JsonElement options)
    {
        UserStyle style = LibraryOwnedStyle(LibraryText(options, "style_id"));
        string[] genres = LibraryValues(style.NumSubGenre, index => style.SubGenre(index)
            ?? throw new InvalidDataException("Native style subgenre is null.")).Concat(LibraryStrings(options, "add_sub_genres")).Distinct(StringComparer.Ordinal).ToArray();
        string[] colors = LibraryValues(style.NumColor, index => style.Color(index)
            ?? throw new InvalidDataException("Native style color is null.")).Concat(LibraryStrings(options, "add_colors")).Distinct(StringComparer.Ordinal).ToArray();
        string name = LibraryText(options, "name", style.Name);
        Yamaha.VOCALOID.VSStyle.PropertyEditor editor = style.CreatePropertyEditor()
            ?? throw new InvalidOperationException("Native style property editor creation failed.");
        try
        {
            LibraryRequire(editor.SetStyleName(name), "style name");
            foreach (string value in genres) LibraryRequire(editor.AddSubGenre(value), "style genre");
            foreach (string value in colors) LibraryRequire(editor.AddColor(value), "style color");
            LibraryRequire(editor.Save(true), "style property save");
        }
        finally { style.DestroyPropertyEditor(); }
        string id = style.Id;
        if (LibraryStyles().ReadUserStyles() != VSStyleError.None)
            throw new InvalidOperationException("Native style catalog refresh failed.");
        return new { session_id = session.Id, style = LibraryStyleView(LibraryOwnedStyle(id), true) };
    }

    private object LibraryDeleteStyle(EngineSession session, JsonElement options)
    {
        UserStyle style = LibraryOwnedStyle(LibraryText(options, "style_id"));
        string id = style.Id, path = style.Path;
        VSStyleError error = style.Remove();
        if (error != VSStyleError.None) throw new InvalidOperationException("Native style removal failed: " + error);
        if (LibraryStyles().ReadUserStyles() != VSStyleError.None || File.Exists(path) || LibraryStyles().AllStylesEnumerator.Any(value => value.Id == id))
            throw new IOException("Native style removal did not remove the file and catalog entry.");
        return new { session_id = session.Id, style_id = id, deleted = true };
    }

    private object LibraryApplyStyle(EngineSession session, JsonElement options)
    {
        NativeStyle style = LibraryStyle(LibraryText(options, "style_id"));
        bool includeAudio = LibraryBool(options, "include_audio", true);
        LibraryRequireStyleTransportReleased(includeAudio);
        WIVSMMidiPart part = LibraryMidiPart(session, options);
        WIVSMEffectManager effects = part.EffectManager
            ?? throw new InvalidOperationException("Native part has no effect manager.");
        JsonElement[] audioPlans = includeAudio ? LibraryStyleAudioPlans(style, options) : [];
        session.Dirty = true;
        session.InvalidateChildren();
        effects.SetupAndResetAllMidiEffects();
        foreach (Yamaha.VOCALOID.VSStyle.MidiEffect source in style.MidiEffects)
        {
            WIVSMMidiEffect target = effects.GetMidiEffectById(source.Id)
                ?? throw new InvalidOperationException("Native MIDI effect is unavailable: " + source.Id);
            for (ulong index = 0; index < source.NumParameter; index++)
            {
                Parameter parameter = source.Parameter(index);
                if (parameter.Name == "VoiceBlend" ||
                    parameter.Name == "VoiceBID" && target.MidiEffectType == VSMMidiEffectType.VoiceColor)
                    continue;
                bool applied = parameter.Name == "Bypass"
                    ? target.SetBypass(parameter.ValueInt == 1)
                    : parameter.Type switch
                    {
                        VSStyleEffectParameterType.Int => target.SetParameterInt(parameter.Name, parameter.ValueInt),
                        VSStyleEffectParameterType.Float => target.SetParameterFloat(parameter.Name, parameter.ValueFloat),
                        VSStyleEffectParameterType.String => target.SetParameterString(parameter.Name, parameter.ValueString),
                        _ => false
                    };
                LibraryRequire(applied, "style MIDI parameter " + parameter.Name);
            }
        }
        if (includeAudio)
        {
            while (effects.NumAudioEffect != 0)
                SetAudioEffect(session, JsonSerializer.SerializeToElement(new
                {
                    scope = "part", action = "remove", slot = 0,
                    track_index = LibraryIndex(options, "track_index"),
                    part_index = LibraryIndex(options, "part_index")
                }), recordHistory: false);
            foreach (JsonElement plan in audioPlans)
                SetAudioEffect(session, plan, recordHistory: false);
        }
        LibraryRequire(part.SetStyleName(style.Name) && part.SetStylePresetID(style.Id), "style identity");
        PrepareSingingSkill(part);
        LibraryCommit(session, "style");
        return new
        {
            session_id = session.Id,
            style_id = part.StylePresetID,
            name = part.StyleName,
            midi_effects_applied = style.NumMidiEffect,
            audio_effects_applied = includeAudio,
            audio_effect_count = includeAudio ? style.NumAudioEffect : (ulong?)null,
            scope = includeAudio ? "complete" : "midi_only"
        };
    }

    private JsonElement[] LibraryStyleAudioPlans(NativeStyle style, JsonElement options)
    {
        if (style.NumAudioEffect == 0)
            return [];
        WEffectManager engine = EnsureAudioEffects();
        string[] installed = engine.CollectedEffectGUID().ToArray();
        List<JsonElement> plans = [];
        HashSet<string> seen = new(StringComparer.OrdinalIgnoreCase);
        engine.ResetAll();
        try
        {
            WEffectBlock block = engine.AddMasterBlock((nint)1)
                ?? throw new InvalidOperationException("Native style normalization block could not be created.");
            for (ulong effectIndex = 0; effectIndex < style.NumAudioEffect; effectIndex++)
            {
                Yamaha.VOCALOID.VSStyle.AudioEffect source = style.AudioEffect(effectIndex)
                    ?? throw new InvalidDataException("Native style audio effect was null.");
                string effectId = installed.FirstOrDefault(value => value.Equals(source.Id, StringComparison.OrdinalIgnoreCase))
                    ?? throw new NotSupportedException("Style requires an unavailable native audio effect: " + source.Id);
                if (WEffectController.IsVirtualEffect(effectId) || !seen.Add(effectId))
                    throw new NotSupportedException("Style contains a virtual or duplicate audio effect: " + effectId);
                WEffectController controller = block.AddLoadEffect(effectId)
                    ?? throw new InvalidOperationException("Native style effect could not be loaded: " + effectId);
                Dictionary<string, float> parameters = new(StringComparer.Ordinal);
                bool bypass = false;
                for (ulong parameterIndex = 0; parameterIndex < source.NumParameter; parameterIndex++)
                {
                    Parameter parameter = source.Parameter(parameterIndex);
                    if (parameter.Type != VSStyleEffectParameterType.Int)
                        throw new NotSupportedException("Native style audio parameter is not a plain integer: " + parameter.Name);
                    if (parameter.Name == "Bypass")
                    {
                        bypass = parameter.ValueInt == 1;
                        continue;
                    }
                    int index = controller.ToParameterIndex(parameter.Name);
                    if (index < 0 || !controller.IsValidParameter((ulong)index))
                        throw new NotSupportedException("Native style audio parameter is unavailable: " + parameter.Name);
                    float normalized = block.ToNormalized(effectId, parameter.Name, parameter.ValueInt);
                    if (!float.IsFinite(normalized) || normalized < 0 || normalized > 1)
                        throw new InvalidDataException("Native style audio normalization failed: " + parameter.Name);
                    parameters.Add(parameter.Name, normalized);
                }
                plans.Add(JsonSerializer.SerializeToElement(new
                {
                    scope = "part", action = "add", effect_id = effectId, parameters, bypass,
                    track_index = LibraryIndex(options, "track_index"),
                    part_index = LibraryIndex(options, "part_index")
                }));
            }
            return plans.ToArray();
        }
        finally
        {
            engine.ResetAll();
        }
    }

    private static string LibrarySecondaryVoice(MidiPartBase part, bool isAi)
    {
        nint handle = (nint)(PartBase)part;
        if (handle == nint.Zero)
            throw new InvalidOperationException("Native media part handle is absent.");
        return Marshal.PtrToStringUni(isAi ? LibrarySecondaryAiVoiceBankId(handle) : LibrarySecondaryVoiceBankId(handle))
            ?? string.Empty;
    }

    private static (string Voice, string AiVoice, bool UsedFile) LibrarySecondaryVoices(Clip clip, MidiPartBase part)
    {
        string nativeVoice = LibrarySecondaryVoice(part, false);
        string nativeAiVoice = LibrarySecondaryVoice(part, true);
        PathGuard.NoLinks(clip.ClipPath);
        using FileStream file = new(clip.ClipPath, FileMode.Open, FileAccess.Read, FileShare.Read);
        using JsonDocument document = JsonDocument.Parse(file);
        string key = clip.PartType == VMMPartType.MidiAi ? "midiAi" : "midi";
        if (!document.RootElement.TryGetProperty(key, out JsonElement data) || data.ValueKind != JsonValueKind.Object)
            throw new InvalidDataException("Native media file is missing its MIDI part object.");
        string ReadVoice(string name)
        {
            if (!data.TryGetProperty(name, out JsonElement voice))
                return string.Empty;
            if (voice.ValueKind != JsonValueKind.Object || !voice.TryGetProperty("compID", out JsonElement id)
                || id.ValueKind != JsonValueKind.String)
                throw new InvalidDataException("Native media has an invalid " + name + " component ID.");
            return id.GetString()!;
        }
        string fileVoice = ReadVoice("secondaryVoice");
        string fileAiVoice = ReadVoice("secondaryAiVoice");
        if ((nativeVoice.Length != 0 && fileVoice.Length != 0 && nativeVoice != fileVoice) ||
            (nativeAiVoice.Length != 0 && fileAiVoice.Length != 0 && nativeAiVoice != fileAiVoice))
            throw new InvalidDataException("Native and saved media secondary voice IDs disagree.");
        return (fileVoice.Length == 0 ? nativeVoice : fileVoice,
                fileAiVoice.Length == 0 ? nativeAiVoice : fileAiVoice,
                (nativeVoice.Length == 0 && fileVoice.Length != 0) || (nativeAiVoice.Length == 0 && fileAiVoice.Length != 0));
    }

    private LibraryClipValidity? LibraryReadValidity(Clip clip, MidiPart source)
    {
        PathGuard.NoLinks(clip.ClipPath);
        using FileStream file = new(clip.ClipPath, FileMode.Open, FileAccess.Read, FileShare.Read);
        using JsonDocument document = JsonDocument.Parse(file);
        if (!document.RootElement.TryGetProperty("vocaloid_bridge_phoneme_validity_v1", out JsonElement extension))
            return null;
        LibraryClipValidity data = extension.Deserialize<LibraryClipValidity>()
            ?? throw new InvalidDataException("Private media phoneme-validity metadata is empty.");
        if (data.Version != 1 || !string.Equals(data.ClipId, clip.ID, StringComparison.OrdinalIgnoreCase)
            || data.Notes is null || (ulong)data.Notes.Count != source.NumNotes)
            throw new InvalidDataException("Private media phoneme-validity metadata does not match the clip.");
        for (int index = 0; index < data.Notes.Count; index++)
        {
            LibraryNoteValidity saved = data.Notes[index] ?? throw new InvalidDataException("Private media validity note is null.");
            Yamaha.VOCALOID.VMM.Note note = source.GetNote((ulong)index)
                ?? throw new InvalidDataException("Native media note is missing.");
            if (saved.Position != note.Position || saved.Duration != note.Duration || saved.Number != note.Number
                || saved.Lyric != note.Lyric || saved.Phonemes != note.Phoneme || saved.LanguageId != note.LangID)
                throw new InvalidDataException("Private media phoneme-validity metadata does not match its native note.");
            foreach (LibraryDvqmMetadata? selection in new[] { saved.AiAttack, saved.AiRelease })
                if (selection is not null && (clip.PartType != VMMPartType.MidiAi || string.IsNullOrEmpty(selection.ComponentId)
                    || selection.LevelNames is null || selection.LevelNames.Count == 0 || selection.LevelNames.Any(string.IsNullOrEmpty)
                    || !float.IsFinite(selection.TopFactor)))
                    throw new InvalidDataException("Private media AI Attack/Release metadata is invalid.");
        }
        return data;
    }

    private void LibraryWriteValidity(UserClip clip, LibraryClipValidity data)
        => LibraryUpdateClip(clip, root =>
        {
            const string name = "vocaloid_bridge_phoneme_validity_v1";
            if (root.ContainsKey(name))
                throw new InvalidDataException("Native media already contains reserved phoneme-validity metadata.");
            root.Add(name, JsonSerializer.SerializeToNode(data));
        });

    private void LibraryWriteNoteSkills(UserClip clip, WIVSMMidiPart source)
        => LibraryUpdateClip(clip, root =>
        {
            string key = source.IsAi ? "midiAi" : "midi";
            JsonArray notes = root[key]?["notes"] as JsonArray
                ?? throw new InvalidDataException("Native media has no MIDI note array.");
            WIVSMNote[] originals = source.Notes.ToArray();
            if (notes.Count != originals.Length)
                throw new InvalidDataException("Native media note count differs from the captured part.");
            for (int index = 0; index < originals.Length; index++)
            {
                WIVSMNote note = originals[index];
                JsonObject saved = notes[index] as JsonObject
                    ?? throw new InvalidDataException("Native media note is not an object.");
                if (saved["pos"]?.GetValue<long>() != note.RelPosTick.Value ||
                    saved["duration"]?.GetValue<long>() != note.DurationTick.Value ||
                    saved["number"]?.GetValue<int>() != note.NoteNumber)
                    throw new InvalidDataException("Native media note identity differs from the captured part.");
                JsonObject skill = saved["singingSkill"] as JsonObject
                    ?? throw new InvalidDataException("Native media note has no standard Singing Skill object.");
                JsonObject weight = skill["weight"] as JsonObject
                    ?? throw new InvalidDataException("Native media Singing Skill has no standard weight object.");
                skill["duration"] = note.HmmWeightDuration;
                weight["pre"] = note.PreHmmWeight;
                weight["post"] = note.PostHmmWeight;
            }
        });

    private void LibraryUpdateClip(UserClip clip, Action<JsonObject> update)
    {
        LibraryOwnedClip(clip.ID);
        PathGuard.NoLinks(clip.ClipPath);
        JsonObject root;
        using (FileStream input = new(clip.ClipPath, FileMode.Open, FileAccess.Read, FileShare.Read))
            root = JsonNode.Parse(input) as JsonObject ?? throw new InvalidDataException("Native media JSON is not an object.");
        update(root);
        string temporary = clip.ClipPath + "." + Guid.NewGuid().ToString("N") + ".tmp";
        bool created = false;
        try
        {
            using (FileStream output = new(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                created = true;
                JsonSerializer.Serialize(output, root);
            }
            PathGuard.NoLinks(clip.ClipPath);
            File.Move(temporary, clip.ClipPath, true);
            created = false;
        }
        finally
        {
            if (created && File.Exists(temporary))
                File.Delete(temporary);
        }
    }

    private object LibraryClipView(Clip clip, bool details)
    {
        if (details)
            LibraryRequire(clip.ReadPart(), "read media part " + clip.ID);
        Filter filter = clip.Filter;
        MidiPart? midi = details && clip.PartType is VMMPartType.Midi or VMMPartType.MidiAi ? clip.MidiPart : null;
        (string Voice, string AiVoice, bool UsedFile) secondary = midi is null ? ("", "", false) : LibrarySecondaryVoices(clip, midi);
        LibraryClipValidity? validity = midi is null ? null : LibraryReadValidity(clip, midi);
        return new
        {
            clip_id = clip.ID,
            name = clip.Name,
            type = clip.ClipType.ToString(),
            part_type = clip.PartType.ToString(),
            path = clip.ClipPath,
            vendor = clip.VendorName,
            key = clip.PartKey.ToString(),
            tempo = clip.PartTempo,
            writable = clip is UserClip,
            languages = filter.LanguageEnumerator().ToArray(),
            singers = filter.SingerGroupEnumerator().ToArray(),
            genres = filter.GenreEnumerator().ToArray(),
            types = filter.TypeEnumerator().ToArray(),
            part = !details ? null : clip.PartType == VMMPartType.Audio
                ? (object?)new { wav_path = clip.AudioPart?.WavFilePath, audio_effects = clip.AudioPart?.NumAudioEffects }
                : new
                {
                    duration = clip.MidiPart?.Duration,
                    notes = clip.MidiPart?.NumNotes,
                    voice_id = clip.MidiPart?.VoiceBankID,
                    ai_voice_id = clip.MidiPart?.AiVoiceBankID,
                    secondary_voice_id = secondary.Voice,
                    secondary_ai_voice_id = secondary.AiVoice,
                    secondary_voice_source = secondary.UsedFile ? "clip_json" : "native",
                    bridge_validity_metadata = validity?.Notes.Any(note => !note.IsValid) ?? false,
                    bridge_dvqm_metadata = validity?.Notes.Any(note => note.AiAttack is not null || note.AiRelease is not null) ?? false,
                    style_id = clip.MidiPart?.StylePresetID
                }
        };
    }

    private object LibraryMediaList(JsonElement options)
    {
        string query = LibraryText(options, "query", "");
        string[] genres = LibraryStrings(options, "genres");
        string[] types = LibraryStrings(options, "types");
        Clip[] matches = LibraryMedia().AllClipEnumerator().Where(clip =>
            (query.Length == 0 || clip.Name.Contains(query, StringComparison.OrdinalIgnoreCase) ||
                clip.ID.Contains(query, StringComparison.OrdinalIgnoreCase) ||
                clip.VendorName.Contains(query, StringComparison.OrdinalIgnoreCase)) &&
            genres.All(genre => clip.Filter.GenreEnumerator().Contains(genre, StringComparer.OrdinalIgnoreCase)) &&
            types.All(type => clip.Filter.TypeEnumerator().Contains(type, StringComparer.OrdinalIgnoreCase))).ToArray();
        return new { total = matches.Length, clips = matches.Select(clip => LibraryClipView(clip, false)).ToArray() };
    }

    private UserClip LibraryOwnedClip(string id)
    {
        Clip clip = LibraryClip(id);
        if (clip is not UserClip userClip)
            throw new ArgumentException("Only bridge-owned private media may be edited or deleted.");
        string root = LibraryDirectory("media");
        string relative = Path.GetRelativePath(root, Path.GetFullPath(clip.ClipPath));
        PathGuard.Under(root, relative);
        PathGuard.NoLinks(clip.ClipPath);
        return userClip;
    }

    private object LibraryUpdateMedia(EngineSession session, JsonElement options)
        => UpdateMediaProperties(session, options);

    private object LibraryDeleteMedia(EngineSession session, JsonElement options)
    {
        UserClip clip = LibraryOwnedClip(LibraryText(options, "clip_id"));
        string id = clip.ID;
        string path = clip.ClipPath;
        LibraryRequire(clip.Remove(), "delete private media");
        if (File.Exists(path) || LibraryMedia().AllClipEnumerator().Any(item => item.ID == id))
            throw new IOException("Native media removal did not remove both the private file and catalog entry.");
        return new { session_id = session.Id, clip_id = id, deleted = true };
    }

    private static TEnum LibraryMapEnum<TEnum>(Enum source) where TEnum : struct, Enum
    {
        string normalized = source.ToString().Replace("_", "", StringComparison.Ordinal);
        foreach (TEnum value in Enum.GetValues<TEnum>())
            if (value.ToString().Replace("_", "", StringComparison.Ordinal) == normalized)
                return value;
        throw new NotSupportedException("Native media has no mapping for " + source.GetType().Name + "." + source + ".");
    }

    private object LibraryCaptureMedia(EngineSession session, JsonElement options)
    {
        WIVSMTrack track = session.Sequence.GetTrack(LibraryIndex(options, "track_index"))
            ?? throw new ArgumentException("track_index was not found.");
        WIVSMPart part = track.GetPart(LibraryIndex(options, "part_index"))
            ?? throw new ArgumentException("part_index was not found.");
        LibraryArchiveClip? archiveClip = LibraryArchiveCapture(session, track, part);
        string name = LibraryText(options, "name", part.Name);
        string[] genres = LibraryStrings(options, "genres");
        string[] types = LibraryStrings(options, "types");
        WIVSMMidiPart? midi = track.Type is VSMTrackType.Midi or VSMTrackType.MidiAi
            ? new WIVSMMidiPart(part) : null;
        WIVSMAudioPart? audio = track.Type == VSMTrackType.Audio ? new WIVSMAudioPart(part) : null;
        if (midi is null && audio is null)
            throw new NotSupportedException("Only native MIDI and audio parts can be captured.");
        if (midi is not null)
            foreach (WIVSMNote note in midi.Notes)
            {
                foreach (bool isAttack in new[] { true, false })
                    if (note.GetDvqm(isAttack) is { IsEmpty: false } selection)
                    {
                        LibraryResolveDvqm(selection, isAttack);
                    }
            }
        string? wave = null;
        if (audio is not null)
        {
            wave = audio.GetWaveFilePath();
            PathGuard.NoLinks(wave);
            InspectWave(wave);
        }
        MediaManager media = LibraryMedia();
        MutableClip mutable = media.CreateMutableClip()
            ?? throw new InvalidOperationException("Native mutable clip creation failed.");
        try
        {
            MutableFilter filter = mutable.Filter
                ?? throw new InvalidOperationException("Native mutable clip has no filter.");
            foreach (string genre in genres)
                LibraryRequire(filter.AddGenre(genre), "capture genre");
            foreach (string type in types)
                LibraryRequire(filter.AddType(type), "capture type");
            int tempo = session.Sequence.GetTempo(part.AbsPosTick, true, false)?.Value
                ?? session.Sequence.GetDefaultTempoValue();
            int mediaTempo = checked((int)LibraryIndex(options, "tempo", (ulong)tempo));
            LibraryRequire(mutable.SetPartTempo(mediaTempo), "capture tempo");
            if (midi is not null)
            {
                int language = midi.LangID >= 0 ? midi.LangID : midi.Notes.FirstOrDefault()?.LangID ?? 0;
                MutableMidiPart target = (midi.IsAi ? mutable.CreateMidiAiPart : mutable.CreateMidiPart)
                    ?? throw new InvalidOperationException("Native mutable MIDI part creation failed.");
                LibraryRequire(target.SetDuration(midi.DurationTick), "capture duration");
                LibraryRequire(target.SetStyleName(midi.StyleName) && target.SetStylePresetID(midi.StylePresetID), "capture style");
                LibraryRequire(target.SetLangID(language), "capture language");
                if (midi.VoiceBankID.Length != 0)
                    LibraryRequire(target.SetVoiceBankID(midi.VoiceBankID), "capture voice");
                if (midi.AiVoiceBankID.Length != 0)
                    LibraryRequire(target.SetAiVoiceBankID(midi.AiVoiceBankID), "capture AI voice");
                if (midi.SecondaryVoiceBankID.Length != 0)
                    LibraryRequire(target.SetSecondaryVoiceBankID(midi.SecondaryVoiceBankID), "capture secondary voice");
                if (midi.SecondaryAiVoiceBankID.Length != 0)
                    LibraryRequire(target.SetSecondaryAiVoiceBankID(midi.SecondaryAiVoiceBankID), "capture secondary AI voice");
                foreach (int lang in midi.Notes.Select(note => note.LangID).Where(lang => lang >= 0).Append(language).Distinct())
                {
                    LibraryRequire(filter.AddLanguage(lang), "capture language filter");
                    if (midi.IsAi)
                        LibraryRequire(target.AddAiLangID(lang), "capture AI language");
                }
                foreach (WIVSMNote note in midi.Notes)
                    LibraryCaptureNote(note, target);
                LibraryCaptureEffects(midi.EffectManager!, target, null);
                foreach (VSMControllerType controllerType in Enum.GetValues<VSMControllerType>())
                {
                    ulong count = midi.GetNumController(controllerType);
                    if (count == 0)
                        continue;
                    MutableMidiController controller = target.AddMidiController(LibraryMapEnum<VMMMidiControllerType>(controllerType))
                        ?? throw new InvalidOperationException("Native media controller creation failed.");
                    for (ulong index = 0; index < count; index++)
                    {
                        WIVSMMidiController point = midi.GetController(controllerType, index)!;
                        if (controller.InsertEvent(point.RelPosTick, point.Value) is null)
                            throw new InvalidOperationException("Native media controller insertion failed.");
                    }
                }
            }
            else
            {
                string sourceDirectory = LibraryDirectory("audio-sources");
                string privateWave = Path.Combine(sourceDirectory, Guid.NewGuid().ToString("N") + ".wav");
                LibraryMaterializeAudio(session.Sequence, audio!, wave!, privateWave);
                MutableAudioPart target = mutable.CreateAudioPart
                    ?? throw new InvalidOperationException("Native mutable audio part creation failed.");
                LibraryRequire(target.SetWavFilePath(privateWave), "capture audio source");
                LibraryCaptureEffects(audio!.EffectManager!, null, target);
            }
            UserClip saved = mutable.Save(name, true, out VMMError error)
                ?? throw new InvalidOperationException("Native media save failed: " + error);
            if (error != VMMError.None || !media.HasUserClip(saved))
                throw new InvalidOperationException("Native media save did not register the clip: " + error);
            PathGuard.NoLinks(saved.ClipPath);
            if (!File.Exists(saved.ClipPath))
                throw new IOException("Native media save did not produce its declared clip file.");
            try
            {
                if (midi is not null)
                    LibraryWriteNoteSkills(saved, midi);
                List<LibraryNoteValidity>? snapshots = midi?.Notes.Select(LibrarySnapshotMediaNote).ToList();
                if (snapshots is not null && snapshots.Any(note => !note.IsValid || note.AiAttack is not null || note.AiRelease is not null))
                {
                    LibraryClipValidity validity = new()
                    {
                        Version = 1, ClipId = saved.ID, Notes = snapshots
                    };
                    LibraryWriteValidity(saved, validity);
                }
                if (archiveClip is not null)
                    LibraryArchiveWrite(saved, archiveClip);
                return new { session_id = session.Id, clip = LibraryClipView(saved, true), preview_audio_created = false };
            }
            catch (Exception captureError)
            {
                if (!saved.Remove())
                    throw new InvalidOperationException("Native media capture failed and its new clip could not be removed.", captureError);
                throw;
            }
        }
        finally
        {
            mutable.Destroy();
        }
    }

    private static void LibraryMaterializeAudio(WIVSMSequence sequence, WIVSMAudioPart part, string source, string destination)
    {
        var wave = InspectWave(source);
        double beginSeconds = sequence.GetTimeFromTick(part.AbsPosTick, part.AbsBeginTick);
        double endSeconds = sequence.GetTimeFromTick(part.AbsPosTick, part.AbsEndTick);
        long firstFrame = checked((long)Math.Round(beginSeconds * wave.SampleRate, MidpointRounding.AwayFromZero));
        long endFrame = checked((long)Math.Round(endSeconds * wave.SampleRate, MidpointRounding.AwayFromZero));
        if (endFrame == wave.Frames + 1)
            endFrame = wave.Frames;
        if (firstFrame < 0 || endFrame <= firstFrame || endFrame > wave.Frames)
            throw new InvalidDataException("Native audio region is outside the available WAV frames.");
        if (firstFrame == 0 && endFrame == wave.Frames)
        {
            File.Copy(source, destination, false);
            return;
        }

        using FileStream input = new(source, FileMode.Open, FileAccess.Read, FileShare.Read);
        using BinaryReader reader = new(input);
        reader.ReadUInt32();
        long riffEnd = reader.ReadUInt32() + 8L;
        reader.ReadUInt32();
        byte[]? format = null;
        byte[]? fact = null;
        long dataOffset = -1;
        long dataBytes = 0;
        while (input.Position + 8 <= riffEnd)
        {
            uint chunk = reader.ReadUInt32();
            uint size = reader.ReadUInt32();
            long payload = input.Position;
            if (chunk == 0x20746d66 || chunk == 0x74636166)
            {
                if (size > 65536)
                    throw new InvalidDataException("Native WAV format metadata exceeds 65536 bytes.");
                byte[] content = reader.ReadBytes(checked((int)size));
                if (content.Length != size)
                    throw new InvalidDataException("Native WAV format metadata is truncated.");
                if (chunk == 0x20746d66)
                {
                    if (format is not null)
                        throw new InvalidDataException("Native WAV contains multiple format chunks.");
                    format = content;
                }
                else
                    fact = content;
            }
            else if (chunk == 0x61746164)
            {
                if (dataOffset >= 0)
                    throw new InvalidDataException("Trimmed media capture requires a single WAV data chunk.");
                dataOffset = payload;
                dataBytes = size;
            }
            input.Position = Math.Min(checked(payload + size + (size & 1)), riffEnd);
        }
        int alignment = checked(wave.Channels * ((wave.Bits + 7) / 8));
        long selectedBytes = checked((endFrame - firstFrame) * alignment);
        if (format is null || dataOffset < 0 || checked(endFrame * alignment) > dataBytes)
            throw new InvalidDataException("Native WAV does not contain the selected complete audio frames.");
        if (fact is not null)
        {
            if (fact.Length < 4)
                throw new InvalidDataException("Native WAV fact chunk is truncated.");
            BinaryPrimitives.WriteUInt32LittleEndian(fact, checked((uint)(endFrame - firstFrame)));
        }
        long riffSize = checked(4L + 8 + format.Length + (format.Length & 1)
            + (fact is null ? 0 : 8 + fact.Length + (fact.Length & 1))
            + 8 + selectedBytes + (selectedBytes & 1));
        if (riffSize > uint.MaxValue || selectedBytes > uint.MaxValue)
            throw new InvalidDataException("Trimmed audio exceeds the RIFF WAV size limit.");
        bool created = false;
        try
        {
            using (FileStream output = new(destination, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            using (BinaryWriter writer = new(output))
            {
                created = true;
                writer.Write(0x46464952u);
                writer.Write((uint)riffSize);
                writer.Write(0x45564157u);
                writer.Write(0x20746d66u);
                writer.Write((uint)format.Length);
                writer.Write(format);
                if ((format.Length & 1) != 0)
                    writer.Write((byte)0);
                if (fact is not null)
                {
                    writer.Write(0x74636166u);
                    writer.Write((uint)fact.Length);
                    writer.Write(fact);
                    if ((fact.Length & 1) != 0)
                        writer.Write((byte)0);
                }
                writer.Write(0x61746164u);
                writer.Write((uint)selectedBytes);
                input.Position = checked(dataOffset + firstFrame * alignment);
                byte[] buffer = new byte[65536];
                long remaining = selectedBytes;
                while (remaining > 0)
                {
                    int count = input.Read(buffer, 0, (int)Math.Min(buffer.Length, remaining));
                    if (count == 0)
                        throw new EndOfStreamException("Native WAV ended before the selected audio frames.");
                    output.Write(buffer, 0, count);
                    remaining -= count;
                }
                if ((selectedBytes & 1) != 0)
                    writer.Write((byte)0);
            }
            InspectWave(destination);
        }
        catch
        {
            if (created && File.Exists(destination))
                File.Delete(destination);
            throw;
        }
    }

    private static void LibraryCaptureEffects(WIVSMEffectManager source, MutableMidiPart? midi, MutableAudioPart? audio)
    {
        if (source is null)
            throw new InvalidOperationException("Native part effect manager is absent.");
        for (ulong index = 0; index < source.NumAudioEffect; index++)
        {
            WIVSMAudioEffect effect = source.GetAudioEffect(index)!;
            NativeMutableEffect target = midi is not null ? midi.InsertAudioEffect(index, effect.Id)!
                : audio!.InsertAudioEffect(index, effect.Id)!;
            LibraryCaptureEffect(effect, target);
        }
        if (midi is null)
            return;
        ulong destination = 0;
        for (ulong index = 0; index < source.NumMidiEffect; index++)
        {
            WIVSMMidiEffect effect = source.GetMidiEffectByIndex(index)!;
            if (effect.Id == "DefaultLyric")
                continue;
            LibraryCaptureEffect(effect, midi.InsertMidiEffect(destination++, effect.Id)!);
        }
    }

    private static void LibraryCaptureEffect(WIVSMEffect source, NativeMutableEffect target)
    {
        if (target is null)
            throw new InvalidOperationException("Native mutable effect creation failed.");
        LibraryRequire(target.AddParameter("Bypass")?.SetValueInt(source.IsBypassed ? 1 : 0) == true, "capture effect bypass");
        foreach (WIVSMEffectValue value in source.GetEffectValues)
        {
            if (value.Name == "Bypass")
                continue;
            MutableEffectParameter parameter = target.AddParameter(value.Name)
                ?? throw new InvalidOperationException("Native mutable parameter creation failed.");
            LibraryRequire(value.Type switch
            {
                VSMEffectValueType.Int => parameter.SetValueInt(value.RawInt),
                VSMEffectValueType.Float => parameter.SetValueFloat(value.RawFloat),
                VSMEffectValueType.String => parameter.SetValueString(value.RawString),
                _ => false
            }, "capture effect parameter " + value.Name);
        }
    }

    private void LibraryCaptureNote(WIVSMNote source, MutableMidiPart part)
    {
        MutableNote target = part.InsertNote(source.RelPosTick, source.DurationTick, source.Lyric, source.Phonemes, source.LangID)
            ?? throw new InvalidOperationException("Native mutable note creation failed.");
        VSMNoteExpression expression = source.GetNoteExpression();
        VSMAiNoteExpression ai = source.GetAiNoteExpression();
        LibraryRequire(target.SetNumber(source.NoteNumber) && target.SetVelocity(source.NoteVelocity) &&
            target.SetProtected(source.IsProtected) && target.SetAiVibratoEnabled(source.IsAiVibratoEnabled) &&
            target.SetAccent(expression.Accent) && target.SetBendDepth(expression.BendDepth) &&
            target.SetBendLength(expression.BendLength) && target.SetDecay(expression.Decay) &&
            target.SetOpening(expression.Opening) && target.SetFallPort(expression.FallPort) && target.SetRisePort(expression.RisePort) &&
            target.SetPitchFine(ai.PitchFine) && target.SetPitchDriftStart(ai.PitchDriftStart) && target.SetPitchDriftEnd(ai.PitchDriftEnd) &&
            target.SetPitchScalingCenter(ai.PitchScalingCenter) && target.SetPitchScalingOrigin(ai.PitchScalingOrigin) &&
            target.SetPitchTransitionStart(ai.PitchTransitionStart) && target.SetPitchTransitionEnd(ai.PitchTransitionEnd) &&
            target.SetAmplitudeWhole(ai.AmplitudeWhole) && target.SetAmplitudeStart(ai.AmplitudeStart) && target.SetAmplitudeEnd(ai.AmplitudeEnd) &&
            target.SetVibratoLeadingDepth(ai.VibratoLeadingDepth) && target.SetVibratoFollowingDepth(ai.VibratoFollowingDepth), "capture note expression");
        MutableSingingSkill skill = target.SingingSkill
            ?? throw new InvalidOperationException("Native singing-skill record is absent.");
        LibraryRequire(skill.SetDuration(source.HmmWeightDuration) && skill.SetPreWeight(source.PreHmmWeight) &&
            skill.SetPostWeight(source.PostHmmWeight), "capture singing skill");
        foreach (bool isAttack in new[] { true, false })
        {
            WIVSMDvqm? selection = source.GetDvqm(isAttack);
            if (selection is null || selection.IsEmpty)
                continue;
            if (source.IsAi)
                continue;
            var resolved = LibraryResolveDvqm(selection, isAttack);
            MutableDvqm destination = target.GetDvqm(isAttack)
                ?? throw new InvalidOperationException("Native mutable Attack/Release record is absent.");
            destination.SetCompID(resolved.Database.CompID);
            foreach (string level in resolved.Property.LevelNames)
                LibraryRequire(destination.AddLevelName(level), "capture Attack/Release level");
            if (destination.Speed != selection.Speed)
                LibraryRequire(destination.SetSpeed(selection.Speed), "capture Attack/Release speed");
            if (destination.TopFactor != selection.TopFactor)
                LibraryRequire(destination.SetTopFactor(selection.TopFactor), "capture Attack/Release top factor");
            destination.SetProtect(selection.IsProtect);
            LibraryRequire(destination.CompID == resolved.Database.CompID && destination.Speed == selection.Speed
                && destination.TopFactor == selection.TopFactor && destination.IsProtected == selection.IsProtect
                && LibraryValues(destination.NumLevelNames, destination.GetLevelName).SequenceEqual(resolved.Property.LevelNames),
                "capture Attack/Release readback");
        }
        MutableVibrato vibrato = target.Vibrato
            ?? throw new InvalidOperationException("Native vibrato record is absent.");
        LibraryRequire(vibrato.SetType(LibraryMapEnum<VMMVibratoType>(source.VibratoType)) &&
            vibrato.SetDuration(source.VibratoDurationTick), "capture vibrato");
        foreach (VSMVibratoEventType type in Enum.GetValues<VSMVibratoEventType>())
            for (ulong index = 0; index < source.GetNumVibratoEvent(type); index++)
            {
                WIVSMVibratoEvent point = source.GetVibratoEvent(type, index)!;
                if (vibrato.InsertParameter(LibraryMapEnum<VMMVibratoParameterType>(type), point.RelPosTick, point.Value) is null)
                    throw new InvalidOperationException("Native media vibrato insertion failed.");
            }
        foreach (VSMDirectPitchData point in source.DirectPitches)
            LibraryRequire(target.SetDirectPitch(point.Tick, point.Value), "capture direct pitch");
    }

    private object LibraryImportMedia(EngineSession session, JsonElement options, bool preflight = true)
    {
        Clip clip = LibraryClip(LibraryText(options, "clip_id"));
        LibraryRequire(clip.ReadPart(), "read media before import");
        ulong trackIndex = LibraryIndex(options, "track_index");
        long position = checked((long)LibraryIndex(options, "position_tick"));
        if (position > int.MaxValue)
            throw new ArgumentOutOfRangeException("position_tick");
        WIVSMTrack track = session.Sequence.GetTrack(trackIndex)
            ?? throw new ArgumentException("track_index was not found.");
        EnsureVoiceServices();
        if (clip.PartType == VMMPartType.Audio)
        {
            if (LibraryArchiveHasMetadata(clip))
                throw new InvalidDataException("project_preservation: archive entity metadata is not valid on audio media.");
            if (track.Type != VSMTrackType.Audio)
                throw new ArgumentException("An audio clip requires an audio target track.");
            Yamaha.VOCALOID.VMM.AudioPart source = clip.AudioPart
                ?? throw new InvalidDataException("Native media audio part is absent.");
            HashSet<nint> existingParts = track.Parts.Select(part => (nint)part).ToHashSet();
            object imported = ImportAudio(session, JsonSerializer.SerializeToElement(new
            {
                path = source.WavFilePath, track_index = trackIndex, position_tick = position,
                name = LibraryText(options, "name", clip.Name)
            }));
            WIVSMPart target = track.Parts.FirstOrDefault(part => !existingParts.Contains((nint)part))
                ?? throw new InvalidOperationException("Imported native audio part was not found.");
            WIVSMEffectManager effects = target.EffectManager!;
            for (ulong index = 0; index < source.NumAudioEffects; index++)
            {
                Yamaha.VOCALOID.VMM.AudioEffect effect = source.GetAudioEffect(index)!;
                LibraryImportEffect(effect, effects.InsertAudioEffect(index, effect.ID)!);
            }
            LibraryCommit(session, "import audio media");
            return new { session_id = session.Id, clip_id = clip.ID, track_index = trackIndex, imported };
        }
        VSMTrackType expected = clip.PartType == VMMPartType.MidiAi ? VSMTrackType.MidiAi : VSMTrackType.Midi;
        if (clip.PartType is not (VMMPartType.Midi or VMMPartType.MidiAi) || track.Type != expected)
            throw new ArgumentException("Native media and target track types must match exactly.");
        Yamaha.VOCALOID.VMM.MidiPart sourceMidi = clip.MidiPart
            ?? throw new InvalidDataException("Native media MIDI part is absent.");
        LibraryClipValidity? validity = LibraryReadValidity(clip, sourceMidi);
        if (validity is not null)
            foreach (LibraryNoteValidity note in validity.Notes)
                foreach ((bool isAttack, LibraryDvqmMetadata? selection) in new[] { (true, note.AiAttack), (false, note.AiRelease) })
                    if (selection is not null)
                        LibraryValidateMediaDvqm(selection, isAttack);
        LibraryArchiveClip? archiveClip = LibraryArchiveRead(clip, sourceMidi, validity);
        if (preflight && (archiveClip is not null || HasArchiveEntityExtensions(session)))
        {
            // The candidate reloads the same native VMM clip. Keep its file
            // stable and reacquire all wrappers after the candidate is closed.
            PathGuard.NoLinks(clip.ClipPath);
            using FileStream clipGuard = new(clip.ClipPath, FileMode.Open, FileAccess.Read, FileShare.Read);
            try { LibraryArchivePreflight(session, options); }
            catch (Exception error)
            {
                throw new InvalidOperationException("project_preservation: media preflight failed: " + error.Message, error);
            }
            return LibraryImportMedia(session, options, false);
        }
        bool upgraded = archiveClip is not null && EnsureArchiveEntityTracking(session);
        try
        {
            return ScoreMutate(session, "media_import", () =>
            {
                WIVSMMidiPart targetMidi = new WIVSMMidiTrack(track).InsertPart(new VSMAbsTick(position),
                    new VSMRelTick(sourceMidi.Duration), LibraryText(options, "name", clip.Name))
                    ?? throw new InvalidOperationException("Native media part insertion failed.");
                if (sourceMidi.VoiceBankID.Length != 0)
                    LibraryRequire(targetMidi.SetVoiceBankID(sourceMidi.VoiceBankID), "import voice");
                if (sourceMidi.AiVoiceBankID.Length != 0)
                    LibraryRequire(targetMidi.SetAiVoiceBankID(sourceMidi.AiVoiceBankID), "import AI voice");
                (string secondaryVoice, string secondaryAiVoice, _) = LibrarySecondaryVoices(clip, sourceMidi);
                if (secondaryVoice.Length != 0)
                    LibraryRequire(targetMidi.SetSecondaryVoiceBankID(secondaryVoice), "import secondary voice");
                if (secondaryAiVoice.Length != 0)
                    LibraryRequire(targetMidi.SetSecondaryAiVoiceBankID(secondaryAiVoice), "import secondary AI voice");
                LibraryRequire(targetMidi.SetStyleName(sourceMidi.StyleName) && targetMidi.SetStylePresetID(sourceMidi.StylePresetID), "import style");
                WIVSMEffectManager targetEffects = targetMidi.EffectManager
                    ?? throw new InvalidOperationException("Native imported part effect manager is absent.");
                for (ulong index = 0; index < sourceMidi.NumAudioEffects; index++)
                {
                    Yamaha.VOCALOID.VMM.AudioEffect effect = sourceMidi.GetAudioEffect(index)!;
                    LibraryImportEffect(effect, targetEffects.InsertAudioEffect(index, effect.ID)!);
                }
                for (ulong index = 0; index < sourceMidi.NumMidiEffects; index++)
                {
                    Yamaha.VOCALOID.VMM.MidiEffect effect = sourceMidi.GetMidiEffect(index)!;
                    if (effect.ID == "DefaultLyric")
                        continue;
                    LibraryImportEffect(effect, targetEffects.GetMidiEffectById(effect.ID)!);
                }
                List<WIVSMNote> importedNotes = [];
                for (ulong index = 0; index < sourceMidi.NumNotes; index++)
                    importedNotes.Add(LibraryImportNote(sourceMidi.GetNote(index)!, targetMidi, validity?.Notes[checked((int)index)]));
                foreach (VMMMidiControllerType type in Enum.GetValues<VMMMidiControllerType>())
                {
                    MidiController? controller = sourceMidi.GetMidiController(type);
                    if (controller is null || controller.NumEvents == 0)
                        continue;
                    VSMControllerType destination = LibraryMapEnum<VSMControllerType>(type);
                    for (ulong index = 0; index < controller.NumEvents; index++)
                    {
                        MidiEvent point = controller.GetEvent(index)!;
                        if (targetMidi.InsertController(new VSMRelTick(point.Position), destination, point.Value) is null)
                            throw new InvalidOperationException("Native media controller import failed.");
                    }
                }
                if (archiveClip is not null)
                    LibraryArchiveAttach(session, track, targetMidi, importedNotes, archiveClip);
                return new
                {
                    session_id = session.Id, clip_id = clip.ID, track_index = trackIndex,
                    position_tick = targetMidi.AbsPosTick.Value, duration = targetMidi.DurationTick.Value,
                    notes = targetMidi.Notes.Select(LibraryNoteView).ToArray()
                };
            });
        }
        catch (Exception error)
        {
            if (upgraded)
            {
                try { DropArchiveEntityTracking(session); }
                catch (Exception cleanup) { throw new AggregateException("Media preservation failed and tracking cleanup was incomplete.", error, cleanup); }
            }
            throw;
        }
    }

    private static void LibraryImportEffect(Yamaha.VOCALOID.VMM.Effect source, WIVSMEffect target)
    {
        if (target is null)
            throw new InvalidOperationException("Native media target effect is unavailable: " + source.ID);
        for (ulong index = 0; index < source.NumParameters; index++)
        {
            EffectParameter parameter = source.GetParameter(index)!;
            LibraryRequire(parameter.Name == "Bypass"
                ? target.SetBypass(parameter.ValueInt == 1)
                : parameter.Type switch
                {
                    VMMEffectParameterType.Int32 => target.ReplaceValueInt(parameter.Name, parameter.ValueInt),
                    VMMEffectParameterType.Float => target.ReplaceValueFloat(parameter.Name, parameter.ValueFloat),
                    VMMEffectParameterType.String => target.ReplaceValueString(parameter.Name, parameter.ValueString),
                    _ => false
                }, "import effect parameter " + parameter.Name);
        }
    }

    private void LibraryValidateMediaDvqm(LibraryDvqmMetadata selection, bool isAttack)
    {
        var manager = EnsureDatabase();
        var database = LibraryValues(manager.NumDvqmDBs, manager.GetDvqmDBByIndex)
            .FirstOrDefault(item => item is not null && item.CompID == selection.ComponentId)
            ?? throw new InvalidOperationException("The media Attack/Release database is not installed: " + selection.ComponentId);
        bool found = LibraryValues(database.NumDvqmProperties(isAttack), index => database.GetDvqmPropertyByIndex(isAttack, index))
            .Any(item => item is not null && item.LevelNames.SequenceEqual(selection.LevelNames));
        if (!found)
            throw new InvalidOperationException("The media Attack/Release level names are not installed.");
    }

    private static WIVSMNote LibraryImportNote(Yamaha.VOCALOID.VMM.Note source, WIVSMMidiPart part, LibraryNoteValidity? metadata)
    {
        VSMNoteEvent noteEvent = new() { Duration = source.Duration, Number = source.Number, Velocity = source.Velocity };
        VSMNoteExpression expression = new()
        {
            Accent = source.Accent, BendDepth = source.BendDepth, BendLength = source.BendLength,
            Decay = source.Decay, Opening = source.Opening, FallPort = source.IsFallPort, RisePort = source.IsRisePort
        };
        VSMAiNoteExpression ai = new()
        {
            PitchFine = source.PitchFine, PitchDriftStart = source.PitchDriftStart, PitchDriftEnd = source.PitchDriftEnd,
            PitchScalingCenter = source.PitchScalingCenter, PitchScalingOrigin = source.PitchScalingOrigin,
            PitchTransitionStart = source.PitchTransitionStart, PitchTransitionEnd = source.PitchTransitionEnd,
            AmplitudeWhole = source.AmplitudeWhole, AmplitudeStart = source.AmplitudeStart, AmplitudeEnd = source.AmplitudeEnd,
            VibratoLeadingDepth = source.VibratoLeadingDepth, VibratoFollowingDepth = source.VibratoFollowingDepth
        };
        WIVSMNote target = part.InsertNote(new VSMRelTick(source.Position), noteEvent, expression, ai,
            source.Lyric, source.Phoneme, metadata?.IsValid ?? true, source.LangID)
            ?? throw new InvalidOperationException("Native media note insertion failed.");
        target.IsProtected = source.IsProtected;
        LibraryRequire(target.SetAiVibratoEnabled(source.IsAiVibratoEnabled), "import AI vibrato flag");
        if (source.Vibrato is Vibrato vibrato)
        {
            target.VibratoType = LibraryMapEnum<VSMVibratoType>(vibrato.Type);
            LibraryRequire(target.SetVibratoDuration(vibrato.DurationTick), "import vibrato duration");
            foreach (VMMVibratoParameterType type in Enum.GetValues<VMMVibratoParameterType>())
                for (ulong index = 0; index < vibrato.GetNumParameters(type); index++)
                {
                    VibratoParameter point = vibrato.GetVibratoParameter(type, index)!;
                    if (target.InsertVibratoEvent(point.RelPosTick, LibraryMapEnum<VSMVibratoEventType>(type), point.Value) is null)
                        throw new InvalidOperationException("Native media vibrato import failed.");
                }
        }
        if (source.SingingSkill is SingingSkill skill)
            LibraryRequire(target.SetHmmWeightDuration(skill.DurationTick) && target.SetHmmWeight(skill.PreWeight, skill.PostWeight), "import singing skill");
        foreach (bool attack in new[] { true, false })
        {
            Dvqm? sourceDvqm = source.Dvqm(attack);
            LibraryDvqmMetadata? extra = attack ? metadata?.AiAttack : metadata?.AiRelease;
            if (extra is null && (sourceDvqm is null || sourceDvqm.CompID.Length == 0))
                continue;
            WIVSMDvqm destination = target.GetDvqm(attack)
                ?? throw new InvalidOperationException("Native attack/release record is absent.");
            string component = extra?.ComponentId ?? sourceDvqm!.CompID;
            var levels = extra?.LevelNames ?? LibraryValues(sourceDvqm!.NumLevelNames, sourceDvqm.GetLevelName).Select(value => value!).ToList();
            int speed = extra?.Speed ?? sourceDvqm!.Speed;
            float topFactor = extra?.TopFactor ?? sourceDvqm!.TopFactor;
            bool protect = extra?.IsProtected ?? sourceDvqm!.IsProtected;
            LibraryRequire(destination.SetDBIDByCompID(component) && destination.SetNameIDByLevelNames(component, levels) &&
                destination.SetSpeed(speed) && destination.SetTopFactor(topFactor), "import attack/release");
            destination.SetProtect(protect);
        }
        foreach (VMMDirectPitchData point in source.DirectPitches)
            LibraryRequire(target.SetDirectPitch(new VSMRelTick(point.Tick), point.Value), "import direct pitch");
        return target;
    }

    private G2PAManager LibraryLyrics(G2PAManagerLangID language)
    {
        CheckThread();
        if (!Enum.IsDefined(language))
            throw new ArgumentOutOfRangeException(nameof(language));
        if (libraryLyrics.TryGetValue(language, out G2PAManager? existing))
            return existing;
        using G2PAManagerIF factory = new();
        string directory = System.IO.Path.GetDirectoryName(typeof(G2PAManager).Assembly.Location)!;
        G2PAManager created = factory.CreateManager(language, directory)
            ?? throw new InvalidOperationException("Native G2PA manager creation failed for " + language + ".");
        libraryLyrics.Add(language, created);
        return created;
    }

    private void DisposeLibraryServices()
    {
        CheckThread();
        libraryMedia?.Dispose();
        libraryMedia = null;
        libraryStyles?.Dispose();
        libraryStyles = null;
        foreach (G2PAManager manager in libraryLyrics.Values)
            manager.Dispose();
        libraryLyrics.Clear();
    }
}
