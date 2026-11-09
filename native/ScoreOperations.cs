using System.IO;
using System.Reflection;
using System.Text.Json;
using Yamaha.VOCALOID.G2PA;
using Yamaha.VOCALOID.VDM;
using Yamaha.VOCALOID.VSM;

internal sealed partial class EngineHost
{
    internal object EditScore(string id, string operation, JsonElement options)
    {
        EngineSession session = GetSession(id);
        if (options.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("options must be a JSON object.", nameof(options));
        object result = operation switch
        {
            "track.freeze" or "track.unfreeze" or "track.freeze_state"
                => TrackFreezeOperation(session, operation, options),
            "track.list" => new { tracks = Enumerable.Range(0, ScoreCount(session.Sequence.NumTrack))
                .Select(index => ScoreTrackSummary(ScoreTrack(session, index), index)).ToArray() },
            "track.create" or "track.update" or "track.remove" or "track.reorder" or "track.duplicate"
                => ScoreTrackEdit(session, operation, options),
            "part.list" => ScorePartList(session, options),
            "part.create" or "part.update" or "part.remove" or "part.move" or "part.resize" or "part.duplicate" or "part.split" or "part.join"
                => ScorePartEdit(session, operation, options),
            "note.list" => ScoreNoteList(session, options),
            "note.expression_bounds" => ScoreNoteExpressionBounds(session, options),
            "note.batch_update" => ScoreNoteBatchUpdate(session, options),
            "vibrato.get" or "vibrato.set" => ScoreVibrato(session, operation, options),
            "phoneme_timing.get" or "phoneme_timing.set" or "phoneme_timing.reset" => ScorePhonemeTiming(session, operation, options),
            "time.convert" => ScoreTimeConvert(session.Sequence, options),
            "history.rollback" => ScoreRollback(session),
            "note.add" or "note.update" or "note.remove" or "note.duplicate" or "note.clear" or "note.split" or "note.join"
                => ScoreNoteEdit(session, operation, options),
            "selection.get" => ScoreSelectionSummary(session, options),
            "selection.set" => ScoreSelectionEdit(session, options),
            "voice.get" => ScoreVoiceSummary(ScorePart(ScoreMidiTrack(session, ScoreTrackIndex(session, options)), options)),
            "voice.set" => ScoreVoiceEdit(session, options),
            "tempo.list" => ScoreTempoList(session.Sequence),
            "tempo.set" or "tempo.remove" => ScoreTempoEdit(session, operation, options),
            "time_signature.list" => ScoreTimeSignatureList(session.Sequence),
            "time_signature.set" or "time_signature.remove" => ScoreTimeSignatureEdit(session, operation, options),
            "time.insert" or "time.delete" => ScoreTimeEdit(session, operation, options),
            "controller.types" => ScoreControllerTypes(session, options),
            "controller.list" => ScoreControllerList(session, options),
            "controller.set" or "controller.remove" => ScoreControllerEdit(session, operation, options),
            "automation.list" => ScoreAutomationList(session, options),
            "automation.set" or "automation.remove" => ScoreAutomationEdit(session, operation, options),
            "performance.get" => ScorePerformanceView(ScorePart(ScoreMidiTrack(session, ScoreTrackIndex(session, options)), options)),
            "performance.set" => ScorePerformanceEdit(session, options),
            "pitch.list" => ScorePitchList(session, options),
            "pitch.set" or "pitch.clear" => ScorePitchEdit(session, operation, options),
            "sequence.get" => ScoreSequenceSummary(session.Sequence),
            "sequence.update" => ScoreSequenceEdit(session, options),
            "loop.get" => ScoreLoopSummary(session.Sequence),
            "loop.set" => ScoreLoopEdit(session, options),
            "tuning.get" => ScoreTuningSummary(session.Sequence),
            "tuning.set" => ScoreTuningEdit(session, options),
            "history.status" => ScoreHistory(session.Sequence),
            "undo" => ScoreHistoryMove(session, false),
            "redo" => ScoreHistoryMove(session, true),
            _ => throw new ArgumentException("Unsupported score operation: " + operation, nameof(operation))
        };
        return new { session_id = id, operation, native = true, result };
    }

    private static WIVSMTrack ScoreTrack(EngineSession session, int index)
    {
        if (index < 0 || (ulong)index >= session.Sequence.NumTrack)
            throw new ArgumentOutOfRangeException(nameof(index), "track_index is outside the native track list.");
        return session.Sequence.GetTrack((ulong)index)
            ?? throw new InvalidOperationException("Native track lookup failed: " + session.Sequence.LastError);
    }

    private static int ScoreTrackIndex(EngineSession session, JsonElement options, string name = "track_index")
        => ScoreInt(options, name, 0, ScoreCount(session.Sequence.NumTrack) - 1);

    private static WIVSMMidiTrack ScoreMidiTrack(EngineSession session, int index)
    {
        WIVSMTrack track = ScoreTrack(session, index);
        if (track.Type is not (VSMTrackType.Midi or VSMTrackType.MidiAi))
            throw new ArgumentException("Score parts require a Midi or MidiAi track.");
        return track as WIVSMMidiTrack ?? new WIVSMMidiTrack(track);
    }

    private static object ScoreTrackSummary(WIVSMTrack track, int index) => new
    {
        track_index = index,
        type = track.Type.ToString(),
        name = track.Name,
        color = track.Color,
        mute = track.IsMute,
        solo = track.IsSolo,
        bus_no = track.GetBusNo(),
        midi_recording = track.Type is VSMTrackType.Midi or VSMTrackType.MidiAi ? new WIVSMMidiTrack(track).IsEnabledMidiRecording : (bool?)null,
        part_count = track.NumParts
    };

    private static object ScoreTrackEdit(EngineSession session, string operation, JsonElement options)
    {
        WIVSMSequence sequence = session.Sequence;
        if (operation == "track.create")
        {
            int index = ScoreInt(options, "index", 0, ScoreCount(sequence.NumTrack), ScoreCount(sequence.NumTrack));
            string name = ScoreString(options, "name", "Track");
            string typeName = ScoreString(options, "type", "MidiAi");
            if (!Enum.TryParse(typeName, true, out VSMTrackType type) ||
                type is not (VSMTrackType.Midi or VSMTrackType.MidiAi or VSMTrackType.Audio))
                throw new ArgumentException("type must be Midi, MidiAi, or Audio.");
            if (sequence.NumTrack >= sequence.MaxNumTrack)
                throw new InvalidOperationException("Native maximum track count reached.");
            return ScoreMutate(session, operation, () =>
            {
                WIVSMTrack created = sequence.InsertTrackEx((ulong)index, type, name)
                    ?? throw new InvalidOperationException("Native track.create failed: " + sequence.LastError);
                return ScoreTrackSummary(created, index);
            });
        }

        int trackIndex = ScoreTrackIndex(session, options);
        WIVSMTrack track = ScoreTrack(session, trackIndex);
        if (operation == "track.reorder")
        {
            int destination = ScoreInt(options, "to_index", 0, ScoreCount(sequence.NumTrack) - 1);
            return ScoreMutate(session, operation, () =>
            {
                ScoreRequire(sequence.MoveTrack((ulong)trackIndex, (ulong)destination), operation, sequence);
                return ScoreTrackSummary(track, destination);
            });
        }
        if (operation == "track.duplicate")
        {
            int destination = ScoreInt(options, "index", 0, ScoreCount(sequence.NumTrack), trackIndex + 1);
            string? name = options.TryGetProperty("name", out _) ? ScoreString(options, "name") : null;
            if (sequence.NumTrack >= sequence.MaxNumTrack)
                throw new InvalidOperationException("Native maximum track count reached.");
            return ScoreMutate(session, operation, () =>
            {
                WIVSMTrack created = sequence.DuplicateTrack((ulong)destination, track, out string message)
                    ?? throw new InvalidOperationException("Native track.duplicate failed: " + message + "; " + sequence.LastError);
                if (name is not null)
                {
                    created.Name = name;
                    ScoreRequire(created.Name == name, operation, sequence);
                }
                session.ArchiveCopy?.Invoke(track, created);
                return ScoreTrackSummary(created, destination);
            });
        }
        if (operation == "track.remove")
            return ScoreMutate(session, operation, () =>
            {
                ScoreRequire(sequence.RemoveTrack(track), operation, sequence);
                return new { removed = true, track_index = trackIndex };
            });

        string? newName = options.TryGetProperty("name", out _) ? ScoreString(options, "name") : null;
        int? color = options.TryGetProperty("color", out _) ? ScoreInt(options, "color", 0, 15) : null;
        bool? mute = options.TryGetProperty("mute", out _) ? ScoreBool(options, "mute") : null;
        bool? solo = options.TryGetProperty("solo", out _) ? ScoreBool(options, "solo") : null;
        int? bus = options.TryGetProperty("bus_no", out _) ? ScoreInt(options, "bus_no", 0, int.MaxValue) : null;
        bool? recording = options.TryGetProperty("midi_recording", out _) ? ScoreBool(options, "midi_recording") : null;
        if (recording is not null && track.Type is not (VSMTrackType.Midi or VSMTrackType.MidiAi))
            throw new ArgumentException("midi_recording requires a MIDI track.");
        if (newName is null && color is null && mute is null && solo is null && bus is null && recording is null)
            throw new ArgumentException("track.update requires a track field to update.");
        return ScoreMutate(session, operation, () =>
        {
            if (bus is not null && track.GetBusNo() != (uint)bus.Value)
                ScoreRequire(track.SetBusNo((uint)bus.Value), operation + " bus_no", sequence);
            if (recording is not null)
                ScoreMidiTrack(session, trackIndex).IsEnabledMidiRecording = recording.Value;
            if (newName is not null && track.Name != newName)
                track.Name = newName;
            if (color is not null && track.Color != color.Value)
                ScoreRequire(track.SetColor(color.Value), operation, sequence);
            if (mute is not null && track.IsMute != mute.Value)
                track.SetMute(mute.Value);
            if (solo is not null && track.IsSolo != solo.Value)
                track.SetSolo(solo.Value);
            return true;
        }, () =>
        {
            WIVSMTrack updated = ScoreTrack(session, trackIndex);
            ScoreRequire((newName is null || updated.Name == newName) &&
                (color is null || updated.Color == color.Value) &&
                (mute is null || updated.IsMute == mute.Value) &&
                (solo is null || updated.IsSolo == solo.Value) &&
                (bus is null || updated.GetBusNo() == (uint)bus.Value) &&
                (recording is null || ScoreMidiTrack(session, trackIndex).IsEnabledMidiRecording == recording.Value), operation + " readback", sequence);
            return ScoreTrackSummary(updated, trackIndex);
        });
    }

    private static WIVSMMidiPart ScorePart(WIVSMMidiTrack track, JsonElement options)
    {
        int index = ScoreInt(options, "part_index", 0, ScoreCount(track.NumParts) - 1);
        return track.GetPart((ulong)index)
            ?? throw new InvalidOperationException("Native part lookup failed: " + track.LastError);
    }

    private static object ScorePartSummary(WIVSMMidiTrack track, WIVSMMidiPart part, int trackIndex) => new
    {
        track_index = trackIndex,
        part_index = track.IndexOf(part),
        name = part.Name,
        start_tick = part.AbsPosTick.Value,
        duration_tick = part.DurationTick.Value,
        note_count = part.NumNotes,
        ai = part.IsAi,
        voice_bank_id = part.VoiceBankID,
        ai_voice_bank_id = part.AiVoiceBankID,
        voice_name = part.VoiceName,
        ai_voice_name = part.AiVoiceName,
        lang_id = part.LangID,
        ai_lang_ids = part.AiLangIDs
    };

    private static object ScorePartList(EngineSession session, JsonElement options)
    {
        List<object> parts = [];
        int first = 0;
        int last = ScoreCount(session.Sequence.NumTrack);
        if (options.TryGetProperty("track_index", out _))
        {
            first = ScoreTrackIndex(session, options);
            last = first + 1;
            ScoreMidiTrack(session, first);
        }
        for (int trackIndex = first; trackIndex < last; trackIndex++)
        {
            WIVSMTrack track = ScoreTrack(session, trackIndex);
            if (track.Type is not (VSMTrackType.Midi or VSMTrackType.MidiAi))
                continue;
            WIVSMMidiTrack midiTrack = ScoreMidiTrack(session, trackIndex);
            for (int index = 0; index < ScoreCount(midiTrack.NumParts); index++)
            {
                WIVSMMidiPart part = midiTrack.GetPart((ulong)index)
                    ?? throw new InvalidOperationException("Native part lookup failed: " + midiTrack.LastError);
                parts.Add(ScorePartSummary(midiTrack, part, trackIndex));
            }
        }
        return new { parts };
    }

    private object ScorePartEdit(EngineSession session, string operation, JsonElement options)
    {
        int trackIndex = ScoreTrackIndex(session, options);
        WIVSMMidiTrack track = ScoreMidiTrack(session, trackIndex);
        if (operation == "part.create")
        {
            int start = ScoreInt(options, "start_tick", 0, int.MaxValue);
            int duration = ScoreInt(options, "duration_tick", Math.Max(1, track.GetMinPartDuration()), track.GetMaxPartDuration(start));
            string name = ScoreString(options, "name", "Part");
            EnsureVoiceServices();
            return ScoreMutate(session, operation, () =>
            {
                WIVSMMidiPart created = track.InsertPart(new VSMAbsTick(start), new VSMRelTick(duration), name)
                    ?? throw new InvalidOperationException("Native part.create failed: " + track.LastError);
                return ScorePartSummary(track, created, trackIndex);
            });
        }
        if (operation == "part.join")
        {
            int[] indices = ScoreIndices(options, "part_indices", ScoreCount(track.NumParts), 2);
            WIVSMMidiPart[] selected = indices.Select(index => track.GetPart((ulong)index)
                ?? throw new InvalidOperationException("Native part lookup failed.")).OrderBy(part => part.AbsPosTick.Value).ToArray();
            ArchivePartSnapshot[] snapshots = HasArchiveEntityExtensions(session) ? selected.Select(ArchiveSnapshotPart).ToArray() : [];
            return ScoreMutate(session, operation, () =>
            {
                WIVSMMidiPart joined = track.JoinParts(selected)
                    ?? throw new InvalidOperationException("Native part.join failed: " + track.LastError);
                ArchiveMigrateParts(session, snapshots, [joined], false);
                return ScorePartSummary(track, joined, trackIndex);
            });
        }
        WIVSMMidiPart part = ScorePart(track, options);
        if (operation == "part.split")
        {
            int tick = ScoreInt(options, "split_tick", 1, checked((int)part.DurationTick.Value) - 1);
            ArchivePartSnapshot[] snapshots = HasArchiveEntityExtensions(session) ? [ArchiveSnapshotPart(part)] : [];
            return ScoreMutate(session, operation, () =>
            {
                WIVSMMidiPart created = track.DividePart(new VSMRelTick(tick), part)
                    ?? throw new InvalidOperationException("Native part.split failed: " + track.LastError);
                ArchiveMigrateParts(session, snapshots, [part, created], true);
                return new { parts = new[] { ScorePartSummary(track, part, trackIndex), ScorePartSummary(track, created, trackIndex) } };
            });
        }
        if (operation == "part.remove")
        {
            ulong partIndex = track.IndexOf(part);
            return ScoreMutate(session, operation, () =>
            {
                ScoreRequire(track.RemovePart(part), operation, session.Sequence);
                return new { removed = true, track_index = trackIndex, part_index = partIndex };
            });
        }
        if (operation is "part.move" or "part.duplicate")
        {
            int destination = options.TryGetProperty("to_track_index", out _)
                ? ScoreTrackIndex(session, options, "to_track_index") : trackIndex;
            WIVSMMidiTrack target = ScoreMidiTrack(session, destination);
            if (track.Type != target.Type)
                throw new ArgumentException("MIDI and AI parts cannot move or duplicate across different track types.");
            int start = ScoreInt(options, "start_tick", 0, int.MaxValue);
            if (part.DurationTick.Value > target.GetMaxPartDuration(start))
                throw new ArgumentOutOfRangeException("start_tick", "Part end exceeds the native tick range.");
            return ScoreMutate(session, operation, () =>
            {
                WIVSMMidiPart result = part;
                if (operation == "part.move")
                    ScoreRequire(track.MovePart(new VSMAbsTick(start), target, part), operation, session.Sequence);
                else
                {
                    result = target.DuplicatePart(new VSMAbsTick(start), part)
                        ?? throw new InvalidOperationException("Native part.duplicate failed: " + target.LastError);
                    session.ArchiveCopy?.Invoke(part, result);
                }
                return ScorePartSummary(target, result, destination);
            });
        }
        int? newDuration = options.TryGetProperty("duration_tick", out _)
            ? ScoreInt(options, "duration_tick", Math.Max(1, track.GetMinPartDuration()), track.GetMaxPartDuration(checked((int)part.AbsPosTick.Value))) : null;
        string? newName = options.TryGetProperty("name", out _) ? ScoreString(options, "name") : null;
        if ((operation == "part.resize" && newDuration is null) || (newDuration is null && newName is null))
            throw new ArgumentException(operation + " requires duration_tick" + (operation == "part.update" ? " or name." : "."));
        return ScoreMutate(session, operation, () =>
        {
            if (newName is not null)
                ScoreRequire(part.SetName(newName), operation, session.Sequence);
            if (newDuration is not null)
                ScoreRequire(part.SetDuration(new VSMRelTick(newDuration.Value)), operation, session.Sequence);
            return ScorePartSummary(track, part, trackIndex);
        });
    }

    private static WIVSMNote ScoreNote(WIVSMMidiPart part, JsonElement options)
    {
        int index = ScoreInt(options, "note_index", 0, ScoreCount(part.NumNotes) - 1);
        return part.GetNote((ulong)index)
            ?? throw new InvalidOperationException("Native note lookup failed: " + part.LastError);
    }

    private static object ScoreNoteSummary(WIVSMNote note, int index) => new
    {
        note_index = index,
        start_tick = note.RelPosTick.Value,
        duration_tick = note.DurationTick.Value,
        number = note.NoteNumber,
        velocity = note.NoteVelocity,
        lyric = note.Lyric,
        phonemes = note.Phonemes,
        is_valid_phonemes = note.IsValidPhonemes,
        lang_id = note.LangID,
        is_protected = note.IsProtected,
        ai_vibrato_enabled = note.IsAiVibratoEnabled,
        expression = ScoreExpressionSummary(note.GetNoteExpression()),
        ai_expression = ScoreExpressionSummary(note.GetAiNoteExpression())
    };

    private static int ScoreNoteIndex(WIVSMMidiPart part, WIVSMNote note)
    {
        for (int index = 0; index < ScoreCount(part.NumNotes); index++)
            if (note.Equals(part.GetNote((ulong)index)))
                return index;
        throw new InvalidOperationException("Native note is no longer attached to its part.");
    }

    private static object ScoreNoteList(EngineSession session, JsonElement options)
    {
        WIVSMMidiPart part = ScorePart(ScoreMidiTrack(session, ScoreTrackIndex(session, options)), options);
        return new
        {
            notes = Enumerable.Range(0, ScoreCount(part.NumNotes)).Select(index =>
                ScoreNoteSummary(part.GetNote((ulong)index)
                    ?? throw new InvalidOperationException("Native note lookup failed."), index)).ToArray()
        };
    }

    private object ScoreNoteEdit(EngineSession session, string operation, JsonElement options)
    {
        WIVSMMidiPart part = ScorePart(ScoreMidiTrack(session, ScoreTrackIndex(session, options)), options);
        if (operation == "note.join")
        {
            int[] indices = ScoreIndices(options, "note_indices", ScoreCount(part.NumNotes), 2);
            List<WIVSMNote> selected = indices.Select(index => part.GetNote((ulong)index)
                ?? throw new InvalidOperationException("Native note lookup failed.")).OrderBy(note => note.RelPosTick.Value).ToList();
            ArchiveEntity[] identities = selected.Select(ArchiveKey).ToArray();
            return ScoreMutate(session, operation, () =>
            {
                ScoreRequire(part.JoinNotes(selected), operation, session.Sequence);
                ArchiveJoinNotes(session, part, identities);
                return ScoreNoteList(session, options);
            });
        }
        if (operation == "note.clear")
            return ScoreMutate(session, operation, () =>
            {
                ScoreRequire(part.RemoveAllNotes(), operation, session.Sequence);
                return new { removed = true, note_count = part.NumNotes };
            });
        WIVSMNote? note = operation == "note.add" ? null : ScoreNote(part, options);
        if (operation == "note.split")
        {
            int tick = ScoreInt(options, "split_tick", checked((int)note!.RelPosTick.Value) + 1,
                checked((int)note.RelEndTick.Value) - 1);
            return ScoreMutate(session, operation, () =>
            {
                WIVSMNote created = part.DivideNote(note, new VSMRelTick(tick))
                    ?? throw new InvalidOperationException("Native note.split failed: " + part.LastError);
                ArchiveCopySplitNote(session, note, created);
                return new { notes = new[] { ScoreNoteSummary(note, ScoreNoteIndex(part, note)), ScoreNoteSummary(created, ScoreNoteIndex(part, created)) } };
            });
        }
        if (operation == "note.remove")
        {
            int noteIndex = ScoreNoteIndex(part, note!);
            return ScoreMutate(session, operation, () =>
            {
                ScoreRequire(part.RemoveNote(note!), operation, session.Sequence);
                return new { removed = true, note_index = noteIndex };
            });
        }

        int start = ScoreInt(options, "start_tick", 0, checked((int)part.DurationTick.Value) - 1,
            note is null ? null : checked((int)note.RelPosTick.Value));
        VSMNoteEvent minimum = part.GetMinNoteEvent();
        VSMNoteEvent maximum = part.GetMaxNoteEvent(start);
        int duration = ScoreInt(options, "duration_tick", Math.Max(1, minimum.Duration),
            Math.Min(maximum.Duration, checked((int)part.DurationTick.Value) - start),
            note is null ? null : checked((int)note.DurationTick.Value));
        if (duration > part.DurationTick.Value - start || duration > maximum.Duration)
            throw new ArgumentOutOfRangeException("duration_tick", "Note must fit in the part and native note range.");
        if (operation == "note.duplicate")
            return ScoreMutate(session, operation, () =>
            {
                WIVSMNote created = part.DuplicateNote(new VSMRelTick(start), note!)
                    ?? throw new InvalidOperationException("Native note.duplicate failed: " + part.LastError);
                session.ArchiveCopy?.Invoke(note!, created);
                return ScoreNoteSummary(created, ScoreNoteIndex(part, created));
            });

        VSMNoteEvent defaultEvent = part.GetDefaultNoteEvent();
        int number = ScoreInt(options, "number", minimum.Number, maximum.Number, note?.NoteNumber ?? defaultEvent.Number);
        int velocity = ScoreInt(options, "velocity", minimum.Velocity, maximum.Velocity, note?.NoteVelocity ?? defaultEvent.Velocity);
        string lyric = ScoreString(options, "lyric", note?.Lyric ?? "a");
        string phonemes = ScoreString(options, "phonemes", note?.Phonemes ?? string.Empty);
        bool validPhonemes = ScoreBool(options, "is_valid_phonemes",
            options.TryGetProperty("phonemes", out _) ? true : note?.IsValidPhonemes ?? false);
        int defaultLanguage = note?.LangID ?? (part.IsAi && part.AiLangIDs.Count > 0 ? part.AiLangIDs[0] : part.LangID);
        if (defaultLanguage < 0 && !options.TryGetProperty("lang_id", out _))
        {
            string voiceId = part.IsAi ? part.AiVoiceBankID : part.VoiceBankID;
            if (string.IsNullOrEmpty(voiceId))
                throw new InvalidOperationException("Assign a native voice before adding notes without lang_id.");
            VoiceBank voice = (part.IsAi ? EnsureDatabase().GetVoiceBankByCompID(voiceId, VDMVoiceBankType.Dnn)
                : EnsureDatabase().GetVoiceBankByCompID(voiceId))
                ?? throw new InvalidOperationException("The assigned native voice could not be resolved: " + voiceId);
            defaultLanguage = voice.NativeLangID;
        }
        int language = ScoreInt(options, "lang_id", 0, 255, defaultLanguage);
        G2PAManager? noteConverter = null;
        if (note is null && !options.TryGetProperty("phonemes", out _))
        {
            noteConverter = LibraryLyrics((G2PAManagerLangID)language);
            if (!options.TryGetProperty("lyric", out _))
                lyric = noteConverter.DefaultLyric();
            WIVSMNote context = part.Notes.FirstOrDefault(item => item.LangID == language && item.IsValidPhonemes && !string.IsNullOrEmpty(item.Phonemes))
                ?? throw new ArgumentException("The first note in an empty part requires explicit phonemes; native G2PA needs a note context.");
            phonemes = context.Phonemes;
            validPhonemes = true;
        }
        VSMNoteExpression expression = ScorePatchExpression(options, "expression", note?.GetNoteExpression() ?? part.GetDefaultNoteExpression(),
            part.GetMinNoteExpression(), part.GetMaxNoteExpression());
        VSMAiNoteExpression aiExpression = ScorePatchExpression(options, "ai_expression", note?.GetAiNoteExpression() ?? part.GetDefaultAiNoteExpression(),
            part.GetMinAiNoteExpression(), part.GetMaxAiNoteExpression());
        bool? protect = options.TryGetProperty("is_protected", out _) ? ScoreBool(options, "is_protected") : null;
        bool? vibrato = options.TryGetProperty("ai_vibrato_enabled", out _) ? ScoreBool(options, "ai_vibrato_enabled") : null;
        string[] mutable = ["start_tick", "duration_tick", "number", "velocity", "lyric", "phonemes", "is_valid_phonemes",
            "lang_id", "expression", "ai_expression", "is_protected", "ai_vibrato_enabled"];
        if (note is not null && !mutable.Any(name => options.TryGetProperty(name, out _)))
            throw new ArgumentException("note.update requires a note field to update.");
        return ScoreMutate(session, operation, () =>
        {
            WIVSMNote edited;
            if (note is null)
            {
                edited = part.InsertNote(new VSMRelTick(start), new VSMNoteEvent(duration, number, velocity),
                    expression, aiExpression, lyric, phonemes, validPhonemes, language)
                    ?? throw new InvalidOperationException("Native note.add failed: " + part.LastError);
                if (noteConverter is not null && (!noteConverter.SetLyrics((nint)edited, lyric, false, part.IsAi, out int converted) || converted != 1))
                    throw new ArgumentException("Native G2PA did not produce one syllable; use lyrics_apply for a phrase.");
            }
            else
            {
                edited = note;
                if (duration < edited.DurationTick.Value)
                    ScoreRequire(edited.SetDuration(new VSMRelTick(duration)), operation, session.Sequence);
                if (start != edited.RelPosTick.Value)
                    ScoreRequire(part.MoveNote(new VSMRelTick(start), edited), operation, session.Sequence);
                if (duration != edited.DurationTick.Value)
                    ScoreRequire(edited.SetDuration(new VSMRelTick(duration)), operation, session.Sequence);
                if (options.TryGetProperty("number", out _))
                    ScoreRequire(edited.SetNoteNumber(number), operation, session.Sequence);
                if (options.TryGetProperty("velocity", out _))
                {
                    edited.NoteVelocity = velocity;
                    ScoreRequire(edited.NoteVelocity == velocity, operation, session.Sequence);
                }
                if (options.TryGetProperty("lyric", out _))
                {
                    edited.Lyric = lyric;
                    ScoreRequire(edited.Lyric == lyric, operation, session.Sequence);
                }
                if (options.TryGetProperty("phonemes", out _) || options.TryGetProperty("is_valid_phonemes", out _))
                    ScoreRequire(edited.SetPhonemes(phonemes, validPhonemes, language), operation, session.Sequence);
                else if (options.TryGetProperty("lang_id", out _))
                    ScoreRequire(edited.SetLangID(language), operation, session.Sequence);
                if (options.TryGetProperty("expression", out _))
                    ScoreRequire(edited.SetNoteExpression(expression), operation, session.Sequence);
                if (options.TryGetProperty("ai_expression", out _))
                    ScoreRequire(edited.SetAiNoteExpression(aiExpression), operation, session.Sequence);
            }
            if (protect is not null)
            {
                edited.IsProtected = protect.Value;
                ScoreRequire(edited.IsProtected == protect.Value, operation, session.Sequence);
            }
            if (vibrato is not null)
                ScoreRequire(edited.SetAiVibratoEnabled(vibrato.Value), operation, session.Sequence);
            return ScoreNoteSummary(edited, ScoreNoteIndex(part, edited));
        });
    }

    private sealed record ScoreSelectionTarget(Func<bool> Get, Action<bool> Set);

    private static List<ScoreSelectionTarget> ScoreSelectionTargets(EngineSession session, JsonElement options)
    {
        List<ScoreSelectionTarget> targets = [];
        string target = ScoreString(options, "target");
        WIVSMSequence sequence = session.Sequence;
        switch (target)
        {
            case "track":
                for (int index = 0; index < ScoreCount(sequence.NumTrack); index++)
                {
                    WIVSMTrack track = ScoreTrack(session, index);
                    targets.Add(new(() => track.IsSelected, selected => track.IsSelected = selected));
                }
                break;
            case "part":
                WIVSMMidiTrack parentTrack = ScoreMidiTrack(session, ScoreTrackIndex(session, options));
                for (int index = 0; index < ScoreCount(parentTrack.NumParts); index++)
                {
                    WIVSMMidiPart part = parentTrack.GetPart((ulong)index)
                        ?? throw new InvalidOperationException("Native part lookup failed.");
                    targets.Add(new(() => part.IsSelected, selected => part.IsSelected = selected));
                }
                break;
            case "note":
                WIVSMMidiPart parentPart = ScorePart(ScoreMidiTrack(session, ScoreTrackIndex(session, options)), options);
                for (int index = 0; index < ScoreCount(parentPart.NumNotes); index++)
                {
                    WIVSMNote note = parentPart.GetNote((ulong)index)
                        ?? throw new InvalidOperationException("Native note lookup failed.");
                    targets.Add(new(() => note.IsSelected, selected => note.IsSelected = selected));
                }
                break;
            case "tempo":
                for (int index = 0; index < ScoreCount(sequence.NumTempos); index++)
                {
                    WIVSMTempo tempo = sequence.GetTempo((ulong)index)
                        ?? throw new InvalidOperationException("Native tempo lookup failed.");
                    targets.Add(new(() => tempo.IsSelected, selected => tempo.IsSelected = selected));
                }
                break;
            case "time_signature":
                for (int index = 0; index < ScoreCount(sequence.NumTimeSigs); index++)
                {
                    WIVSMTimeSig signature = sequence.GetTimeSig((ulong)index)
                        ?? throw new InvalidOperationException("Native time signature lookup failed.");
                    targets.Add(new(() => signature.IsSelected, selected => signature.IsSelected = selected));
                }
                break;
            case "controller":
                WIVSMMidiPart controllerPart = ScorePart(ScoreMidiTrack(session, ScoreTrackIndex(session, options)), options);
                VSMControllerType type = ScoreControllerType(options);
                for (int index = 0; index < ScoreCount(controllerPart.GetNumController(type)); index++)
                {
                    WIVSMMidiController controller = controllerPart.GetController(type, (ulong)index)
                        ?? throw new InvalidOperationException("Native controller lookup failed.");
                    targets.Add(new(() => controller.Selected, selected => controller.Selected = selected));
                }
                break;
            default:
                throw new ArgumentException("target must be track, part, note, tempo, time_signature, or controller.");
        }
        return targets;
    }

    private static object ScoreSelectionSummary(EngineSession session, JsonElement options)
    {
        List<ScoreSelectionTarget> targets = ScoreSelectionTargets(session, options);
        return new { target = ScoreString(options, "target"), selected_indices = Enumerable.Range(0, targets.Count).Where(index => targets[index].Get()).ToArray() };
    }

    private static object ScoreSelectionEdit(EngineSession session, JsonElement options)
    {
        List<ScoreSelectionTarget> targets = ScoreSelectionTargets(session, options);
        HashSet<int> indices = ScoreIndices(options, "indices", targets.Count, 0).ToHashSet();
        bool selected = ScoreBool(options, "selected", true);
        bool clear = ScoreBool(options, "clear_existing", true);
        return ScoreMutate(session, "selection.set", () =>
        {
            for (int index = 0; index < targets.Count; index++)
            {
                if (!indices.Contains(index) && !clear)
                    continue;
                bool value = indices.Contains(index) && selected;
                targets[index].Set(value);
                ScoreRequire(targets[index].Get() == value, "selection.set", session.Sequence);
            }
            return ScoreSelectionSummary(session, options);
        });
    }

    private static Dictionary<string, object?> ScoreExpressionSummary<T>(T value) where T : struct
    {
        Dictionary<string, object?> result = new(StringComparer.Ordinal);
        foreach (PropertyInfo property in typeof(T).GetProperties(BindingFlags.Instance | BindingFlags.Public))
            result.Add(property.Name, property.GetValue(value));
        foreach (FieldInfo field in typeof(T).GetFields(BindingFlags.Instance | BindingFlags.Public))
            result.Add(field.Name, field.GetValue(value));
        return result;
    }

    private static object ScoreNoteExpressionBounds(EngineSession session, JsonElement options)
    {
        WIVSMMidiPart part = ScorePart(ScoreMidiTrack(session, ScoreTrackIndex(session, options)), options);
        return new
        {
            expression = new
            {
                minimum = ScoreExpressionSummary(part.GetMinNoteExpression()),
                maximum = ScoreExpressionSummary(part.GetMaxNoteExpression()),
                defaults = ScoreExpressionSummary(part.GetDefaultNoteExpression())
            },
            ai_expression = new
            {
                minimum = ScoreExpressionSummary(part.GetMinAiNoteExpression()),
                maximum = ScoreExpressionSummary(part.GetMaxAiNoteExpression()),
                defaults = ScoreExpressionSummary(part.GetDefaultAiNoteExpression())
            }
        };
    }

    private static T ScorePatchExpression<T>(JsonElement options, string name, T current, T minimum, T maximum) where T : struct
    {
        if (!options.TryGetProperty(name, out JsonElement patch))
            return current;
        if (patch.ValueKind != JsonValueKind.Object)
            throw new ArgumentException(name + " must be an object using native expression field names.");
        object result = current;
        foreach (JsonProperty entry in patch.EnumerateObject())
        {
            PropertyInfo? property = typeof(T).GetProperty(entry.Name, BindingFlags.Instance | BindingFlags.Public);
            FieldInfo? field = typeof(T).GetField(entry.Name, BindingFlags.Instance | BindingFlags.Public);
            Type memberType = property?.PropertyType ?? field?.FieldType
                ?? throw new ArgumentException("Unknown " + name + " field: " + entry.Name);
            object? low = property is not null ? property.GetValue(minimum) : field!.GetValue(minimum);
            object? high = property is not null ? property.GetValue(maximum) : field!.GetValue(maximum);
            object value = memberType == typeof(int) ? ScoreInt(patch, entry.Name, (int)low!, (int)high!) :
                memberType == typeof(float) ? ScoreFloat(patch, entry.Name, (float)low!, (float)high!) :
                memberType == typeof(bool) ? ScoreBool(patch, entry.Name) :
                throw new ArgumentException("Unsupported native expression field type.");
            if (property is not null)
                property.SetValue(result, value);
            else
                field!.SetValue(result, value);
        }
        return (T)result;
    }

    private static object ScoreVoiceSummary(WIVSMMidiPart part) => new
    {
        ai = part.IsAi,
        voice_bank_id = part.VoiceBankID,
        ai_voice_bank_id = part.AiVoiceBankID,
        secondary_voice_bank_id = part.SecondaryVoiceBankID,
        secondary_ai_voice_bank_id = part.SecondaryAiVoiceBankID,
        voice_name = part.VoiceName,
        ai_voice_name = part.AiVoiceName,
        secondary_voice_name = part.SecondaryVoiceName,
        secondary_ai_voice_name = part.SecondaryAiVoiceName,
        lang_id = part.LangID,
        ai_lang_ids = part.AiLangIDs
    };

    private object ScoreVoiceEdit(EngineSession session, JsonElement options)
    {
        WIVSMMidiPart part = ScorePart(ScoreMidiTrack(session, ScoreTrackIndex(session, options)), options);
        string primaryKey = part.IsAi ? "ai_voice_bank_id" : "voice_bank_id";
        string secondaryKey = part.IsAi ? "secondary_ai_voice_bank_id" : "secondary_voice_bank_id";
        if (options.TryGetProperty(part.IsAi ? "voice_bank_id" : "ai_voice_bank_id", out _) ||
            options.TryGetProperty(part.IsAi ? "secondary_voice_bank_id" : "secondary_ai_voice_bank_id", out _))
            throw new ArgumentException("Voice ID option does not match the part's native MIDI/AI type.");
        string? primary = options.TryGetProperty(primaryKey, out _) ? ScoreString(options, primaryKey) : null;
        string? secondary = options.TryGetProperty(secondaryKey, out _) ? ScoreString(options, secondaryKey) : null;
        if (primary is null && secondary is null)
            throw new ArgumentException("voice.set requires " + primaryKey + " or " + secondaryKey + ".");
        EnsureVoiceServices();
        return ScoreMutate(session, "voice.set", () =>
        {
            if (primary is not null)
            {
                ScoreRequire(part.IsAi ? part.SetAiVoiceBankID(primary) : part.SetVoiceBankID(primary), "voice.set", session.Sequence);
                ScoreRequire((part.IsAi ? part.AiVoiceBankID : part.VoiceBankID) == primary, "voice.set readback", session.Sequence);
            }
            if (secondary is not null)
            {
                ScoreRequire(part.IsAi ? part.SetSecondaryAiVoiceBankID(secondary) : part.SetSecondaryVoiceBankID(secondary), "voice.set", session.Sequence);
                ScoreRequire((part.IsAi ? part.SecondaryAiVoiceBankID : part.SecondaryVoiceBankID) == secondary, "voice.set readback", session.Sequence);
            }
            return ScoreVoiceSummary(part);
        });
    }

    private static object ScoreTempoSummary(WIVSMTempo tempo, int index) => new
    {
        tempo_index = index,
        start_tick = tempo.RelPosTick.Value,
        bpm = tempo.Value / 100.0
    };

    private static object ScoreTempoList(WIVSMSequence sequence) => new
    {
        tempos = Enumerable.Range(0, ScoreCount(sequence.NumTempos)).Select(index =>
            ScoreTempoSummary(sequence.GetTempo((ulong)index)
                ?? throw new InvalidOperationException("Native tempo lookup failed."), index)).ToArray(),
        min_bpm = sequence.GetMinTempoValue() / 100.0,
        max_bpm = sequence.GetMaxTempoValue() / 100.0
    };

    private static int ScoreTempoIndex(WIVSMSequence sequence, WIVSMTempo tempo)
    {
        for (int index = 0; index < ScoreCount(sequence.NumTempos); index++)
            if (tempo.Equals(sequence.GetTempo((ulong)index)))
                return index;
        throw new InvalidOperationException("Native tempo is no longer attached.");
    }

    private static object ScoreTempoEdit(EngineSession session, string operation, JsonElement options)
    {
        WIVSMSequence sequence = session.Sequence;
        WIVSMTempo? tempo = null;
        if (options.TryGetProperty("tempo_index", out _))
        {
            int index = ScoreInt(options, "tempo_index", 0, ScoreCount(sequence.NumTempos) - 1);
            tempo = sequence.GetTempo((ulong)index) ?? throw new InvalidOperationException("Native tempo lookup failed.");
        }
        if (operation == "tempo.remove")
        {
            if (tempo is null)
                throw new ArgumentException("tempo.remove requires tempo_index.");
            if (tempo.RelPosTick.Value == 0)
                throw new ArgumentException("The initial tempo cannot be removed; update it with tempo.set.");
            return ScoreMutate(session, operation, () =>
            {
                ScoreRequire(sequence.RemoveTempo(tempo), operation, sequence);
                return new { removed = true };
            });
        }
        int start = ScoreInt(options, "start_tick", 0, int.MaxValue, tempo is null ? 0 : checked((int)tempo.RelPosTick.Value));
        if (tempo?.RelPosTick.Value == 0 && start != 0)
            throw new ArgumentException("The initial tempo must remain at tick zero.");
        int value = ScoreBpm(options, "bpm", sequence);
        tempo ??= sequence.TemposEnumerator.FirstOrDefault(item => item.RelPosTick.Value == start);
        return ScoreMutate(session, operation, () =>
        {
            WIVSMTempo edited = tempo ?? sequence.InsertTempo(new VSMRelTick(start), value)
                ?? throw new InvalidOperationException("Native tempo.set failed: " + sequence.LastError);
            if (tempo is not null)
            {
                if (edited.RelPosTick.Value != start)
                    ScoreRequire(sequence.MoveTempo(new VSMRelTick(start), edited), operation, sequence);
                edited.Value = value;
                ScoreRequire(edited.Value == value, operation, sequence);
            }
            return ScoreTempoSummary(edited, ScoreTempoIndex(sequence, edited));
        });
    }

    private static int ScoreBpm(JsonElement options, string name, WIVSMSequence sequence)
    {
        if (!options.TryGetProperty(name, out JsonElement value) || value.ValueKind != JsonValueKind.Number ||
            !value.TryGetDouble(out double bpm) || !double.IsFinite(bpm) ||
            bpm < sequence.GetMinTempoValue() / 100.0 || bpm > sequence.GetMaxTempoValue() / 100.0)
            throw new ArgumentOutOfRangeException(name, "BPM must be finite and within the native tempo range.");
        return checked((int)Math.Round(bpm * 100, MidpointRounding.AwayFromZero));
    }

    private static object ScoreTimeSignatureSummary(WIVSMTimeSig signature, int index) => new
    {
        time_signature_index = index,
        bar = signature.PosBar,
        numerator = signature.Numer,
        denominator = signature.Denom
    };

    private static object ScoreTimeSignatureList(WIVSMSequence sequence) => new
    {
        time_signatures = Enumerable.Range(0, ScoreCount(sequence.NumTimeSigs)).Select(index =>
            ScoreTimeSignatureSummary(sequence.GetTimeSig((ulong)index)
                ?? throw new InvalidOperationException("Native time signature lookup failed."), index)).ToArray()
    };

    private static int ScoreTimeSignatureIndex(WIVSMSequence sequence, WIVSMTimeSig signature)
    {
        for (int index = 0; index < ScoreCount(sequence.NumTimeSigs); index++)
            if (signature.Equals(sequence.GetTimeSig((ulong)index)))
                return index;
        throw new InvalidOperationException("Native time signature is no longer attached.");
    }

    private static object ScoreTimeSignatureEdit(EngineSession session, string operation, JsonElement options)
    {
        WIVSMSequence sequence = session.Sequence;
        WIVSMTimeSig? signature = null;
        if (options.TryGetProperty("time_signature_index", out _))
        {
            int index = ScoreInt(options, "time_signature_index", 0, ScoreCount(sequence.NumTimeSigs) - 1);
            signature = sequence.GetTimeSig((ulong)index) ?? throw new InvalidOperationException("Native time signature lookup failed.");
        }
        if (operation == "time_signature.remove")
        {
            if (signature is null)
                throw new ArgumentException("time_signature.remove requires time_signature_index.");
            if (signature.PosBar == 0)
                throw new ArgumentException("The initial time signature cannot be removed; update it with time_signature.set.");
            return ScoreMutate(session, operation, () =>
            {
                ScoreRequire(sequence.RemoveTimeSig(signature), operation, sequence);
                return new { removed = true };
            });
        }
        int bar = ScoreInt(options, "bar", 0, int.MaxValue, signature?.PosBar ?? 0);
        int numerator = ScoreInt(options, "numerator", sequence.MinTimeSigValue.Numer, sequence.MaxTimeSigValue.Numer);
        int denominator = ScoreInt(options, "denominator", sequence.MinTimeSigValue.Denom, sequence.MaxTimeSigValue.Denom);
        if (denominator <= 0 || (denominator & (denominator - 1)) != 0)
            throw new ArgumentException("denominator must be a positive power of two.");
        if (signature?.PosBar == 0 && bar != 0)
            throw new ArgumentException("The initial time signature must remain at bar zero.");
        signature ??= sequence.TimeSigsEnumerator.FirstOrDefault(item => item.PosBar == bar);
        return ScoreMutate(session, operation, () =>
        {
            WIVSMTimeSig edited = signature ?? sequence.InsertTimeSig(bar, new VSMTimeSigEvent(numerator, denominator))
                ?? throw new InvalidOperationException("Native time_signature.set failed: " + sequence.LastError);
            if (signature is not null)
            {
                if (edited.PosBar != bar)
                    ScoreRequire(sequence.MoveTimeSig(bar, edited), operation, sequence);
                ScoreRequire(edited.SetTimeSig(numerator, denominator), operation, sequence);
            }
            return ScoreTimeSignatureSummary(edited, ScoreTimeSignatureIndex(sequence, edited));
        });
    }

    private static object ScoreTimeEdit(EngineSession session, string operation, JsonElement options)
    {
        WIVSMSequence sequence = session.Sequence;
        int start = ScoreInt(options, "start_tick", 0, int.MaxValue - 1);
        int duration = ScoreInt(options, "duration_tick", 1, int.MaxValue - start);
        int end = checked(start + duration);
        bool includeTempo = ScoreBool(options, "include_tempo", true);
        bool insert = operation == "time.insert";
        for (int trackIndex = 0; trackIndex < ScoreCount(sequence.NumTrack); trackIndex++)
        {
            WIVSMTrack track = ScoreTrack(session, trackIndex);
            for (int partIndex = 0; partIndex < ScoreCount(track.NumParts); partIndex++)
            {
                WIVSMPart part = track.GetPart((ulong)partIndex)
                    ?? throw new InvalidOperationException("Native part lookup failed.");
                bool crossesStart = part.AbsBeginTick.Value < start && start < part.AbsEndTick.Value;
                bool crossesEnd = !insert && part.AbsBeginTick.Value < end && end < part.AbsEndTick.Value;
                if (track.Type is VSMTrackType.Midi or VSMTrackType.MidiAi && (crossesStart || crossesEnd))
                    throw new NotSupportedException("Time edits crossing MIDI/AI parts require the editor-owned phoneme service. Split those parts with part.split first; no time edit was applied.");
                if (insert && part.AbsEndTick.Value > int.MaxValue - duration)
                    throw new ArgumentOutOfRangeException("duration_tick", "Inserted time would exceed the native part tick range.");
            }
            if (insert && (track.Volumes.Any(point => point.RelPosTick.Value > int.MaxValue - duration) ||
                track.Panpots.Any(point => point.RelPosTick.Value > int.MaxValue - duration)))
                throw new ArgumentOutOfRangeException("duration_tick", "Inserted time would exceed the native automation tick range.");
        }
        if (insert && (sequence.Tempos.Any(point => point.RelPosTick.Value > int.MaxValue - duration) ||
            sequence.MasterVolumes.Any(point => point.RelPosTick.Value > int.MaxValue - duration) ||
            sequence.TimeSigs.Any(point => point.PosBar > int.MaxValue - duration)))
            throw new ArgumentOutOfRangeException("duration_tick", "Inserted time would exceed the native timeline range.");
        return ScoreMutate(session, operation, () =>
        {
            VSMTickRange range = new(start, end);
            bool success = insert
                ? Yamaha.VOCALOID.WIVSMSequenceExtension.InsertSilence(sequence, range, includeTempo)
                : Yamaha.VOCALOID.WIVSMSequenceExtension.DeleteTime(sequence, range, includeTempo);
            ScoreRequire(success, operation, sequence);
            return new { start_tick = start, duration_tick = duration, include_tempo = includeTempo, track_count = sequence.NumTrack };
        });
    }

    private static VSMControllerType ScoreControllerType(JsonElement options)
    {
        string name = ScoreString(options, "type");
        if (!Enum.TryParse(name, false, out VSMControllerType type) || !Enum.IsDefined(type))
            throw new ArgumentException("Unknown native controller type: " + name);
        return type;
    }

    private static object ScoreControllerTypes(EngineSession session, JsonElement options)
    {
        WIVSMMidiPart part = ScorePart(ScoreMidiTrack(session, ScoreTrackIndex(session, options)), options);
        return new
        {
            types = Enum.GetValues<VSMControllerType>().Select(type => new
            {
                type = type.ToString(),
                minimum = part.MinControllerValue(type),
                maximum = part.MaxControllerValue(type),
                default_value = part.DefaultControllerValue(type)
            }).ToArray()
        };
    }

    private static object ScoreControllerSummary(WIVSMMidiController controller, int index) => new
    {
        controller_index = index,
        tick = controller.RelPosTick.Value,
        value = controller.Value
    };

    private static object ScoreControllerList(EngineSession session, JsonElement options)
    {
        WIVSMMidiPart part = ScorePart(ScoreMidiTrack(session, ScoreTrackIndex(session, options)), options);
        VSMControllerType type = ScoreControllerType(options);
        return ScoreControllerList(part, type);
    }

    private static object ScoreControllerList(WIVSMMidiPart part, VSMControllerType type) => new
    {
        type = type.ToString(),
        points = Enumerable.Range(0, ScoreCount(part.GetNumController(type))).Select(index =>
            ScoreControllerSummary(part.GetController(type, (ulong)index)
                ?? throw new InvalidOperationException("Native controller lookup failed."), index)).ToArray(),
        minimum = part.MinControllerValue(type),
        maximum = part.MaxControllerValue(type),
        default_value = part.DefaultControllerValue(type)
    };

    private static JsonElement ScorePoints(JsonElement options)
    {
        if (!options.TryGetProperty("points", out JsonElement points) || points.ValueKind != JsonValueKind.Array ||
            points.GetArrayLength() is < 1 or > 8192)
            throw new ArgumentException("points must be an array of 1..8192 objects.");
        foreach (JsonElement point in points.EnumerateArray())
            if (point.ValueKind != JsonValueKind.Object)
                throw new ArgumentException("Each curve point must be an object.");
        return points;
    }

    private static object ScoreControllerEdit(EngineSession session, string operation, JsonElement options)
    {
        WIVSMMidiPart part = ScorePart(ScoreMidiTrack(session, ScoreTrackIndex(session, options)), options);
        VSMControllerType type = ScoreControllerType(options);
        if (operation == "controller.remove")
        {
            int index = ScoreInt(options, "controller_index", 0, ScoreCount(part.GetNumController(type)) - 1);
            WIVSMMidiController controller = part.GetController(type, (ulong)index)
                ?? throw new InvalidOperationException("Native controller lookup failed.");
            return ScoreMutate(session, operation, () =>
            {
                ScoreRequire(part.RemoveController(controller), operation, session.Sequence);
                return new { removed = true, controller_index = index };
            });
        }
        List<(int Tick, int Value)> points = [];
        HashSet<int> ticks = [];
        foreach (JsonElement point in ScorePoints(options).EnumerateArray())
        {
            int tick = ScoreInt(point, "tick", 0, checked((int)part.DurationTick.Value) - 1);
            if (!ticks.Add(tick))
                throw new ArgumentException("Curve points must have distinct ticks.");
            points.Add((tick, ScoreInt(point, "value", part.MinControllerValue(type), part.MaxControllerValue(type))));
        }
        bool replace = ScoreBool(options, "replace");
        Dictionary<long, WIVSMMidiController> existing = [];
        for (int index = 0; index < ScoreCount(part.GetNumController(type)); index++)
        {
            WIVSMMidiController controller = part.GetController(type, (ulong)index)
                ?? throw new InvalidOperationException("Native controller lookup failed.");
            existing.Add(controller.RelPosTick.Value, controller);
        }
        return ScoreMutate(session, operation, () =>
        {
            if (replace)
            {
                foreach (WIVSMMidiController controller in existing.Values)
                    ScoreRequire(part.RemoveController(controller), operation, session.Sequence);
                existing.Clear();
            }
            foreach ((int tick, int value) in points.OrderBy(point => point.Tick))
            {
                if (existing.TryGetValue(tick, out WIVSMMidiController? controller))
                {
                    controller.Value = value;
                    ScoreRequire(controller.Value == value, operation, session.Sequence);
                }
                else if (part.InsertController(new VSMRelTick(tick), type, value) is null)
                    throw new InvalidOperationException("Native controller.set failed: " + part.LastError);
            }
            return ScoreControllerList(part, type);
        });
    }

    private static object ScorePerformanceView(WIVSMMidiPart part)
    {
        WIVSMRobotVoiceEffect? robot = part.RobotVoiceEffect;
        WIVSMBreathEffect? breath = part.BreathEffect;
        WIVSMTakeEffect? take = part.TakeEffect;
        WIVSMVoiceColorEffect? color = part.VoiceColorEffect;
        return new
        {
            robot = robot is null ? null : new { mode = robot.RobotVoiceMode.ToString(), modes = Enum.GetNames<VSMRobotVoiceMode>() },
            breath = breath is null ? null : new
            {
                mode = breath.BreathMode.ToString(), modes = Enum.GetNames<VSMBreathMode>(),
                type = breath.BreathType.ToString(), types = Enum.GetNames<VSMBreathType>(),
                exhalation = breath.Exhalation, setting = breath.ExhalationSetting
            },
            take = take is null ? null : new { lane = take.Lane, setting = take.LaneSetting },
            voice_colors = color is null ? null : Enum.GetValues<VSMVoiceColor>().Select(value => new
            {
                name = value.ToString(), value = color.VoiceColorValue(value), setting = color.VoiceColorSetting(value),
                applies_to = value is VSMVoiceColor.S5Expression or VSMVoiceColor.S5Air or VSMVoiceColor.S5Character ? "MidiAi" : "Midi",
                applicable_to_current_part = part.IsAi == (value is VSMVoiceColor.S5Expression or VSMVoiceColor.S5Air or VSMVoiceColor.S5Character)
            }).ToArray(),
            bypass = Enum.GetValues<VSMMidiEffectType>().Select(value => new
            {
                effect = value.ToString(), available = part.GetMidiEffect(value) is not null,
                bypassed = part.IsBypassed(value)
            }).ToArray()
        };
    }

    private static T ScorePerformanceEnum<T>(JsonElement options, string name) where T : struct, Enum
    {
        string text = ScoreString(options, name);
        if (!Enum.TryParse(text, true, out T value) || !Enum.IsDefined(value))
            throw new ArgumentException(name + " must be one of: " + string.Join(", ", Enum.GetNames<T>()));
        return value;
    }

    private static string ScoreRobotVoiceScript(VSMRobotVoiceMode mode)
    {
        string path = new Yamaha.VOCALOID.LuaManager().GetRobotVoiceScriptPath(mode);
        if (string.IsNullOrEmpty(path) || !File.Exists(path))
            throw new FileNotFoundException("The installed native RobotVoice script is missing.", path);
        PathGuard.NoLinks(path);
        return path;
    }

    private static void PrepareRobotVoice(WIVSMMidiPart part)
    {
        WIVSMRobotVoiceEffect? effect = part.RobotVoiceEffect;
        if (effect is null || part.IsBypassed(VSMMidiEffectType.RobotVoice))
            return;
        string path = ScoreRobotVoiceScript(effect.RobotVoiceMode);
        if (effect.ScriptFilePath != path)
            effect.ScriptFilePath = path;
        if (effect.Timing != VSMMidiEffectTiming.BeforeRendering)
            effect.Timing = VSMMidiEffectTiming.BeforeRendering;
        if (effect.ScriptFilePath != path || effect.Timing != VSMMidiEffectTiming.BeforeRendering)
            throw new InvalidOperationException("Native RobotVoice runtime script setup failed.");
    }

    private static object ScorePerformanceEdit(EngineSession session, JsonElement options)
    {
        int trackIndex = ScoreTrackIndex(session, options);
        WIVSMMidiPart part = ScorePart(ScoreMidiTrack(session, trackIndex), options);
        VSMRobotVoiceMode? robot = options.TryGetProperty("robot_mode", out _) ? ScorePerformanceEnum<VSMRobotVoiceMode>(options, "robot_mode") : null;
        VSMBreathMode? breathMode = options.TryGetProperty("breath_mode", out _) ? ScorePerformanceEnum<VSMBreathMode>(options, "breath_mode") : null;
        VSMBreathType? breathType = options.TryGetProperty("breath_type", out _) ? ScorePerformanceEnum<VSMBreathType>(options, "breath_type") : null;
        if (robot.HasValue && part.RobotVoiceEffect is null)
            throw new NotSupportedException("The native part has no RobotVoice effect.");
        string? robotScript = null;
        if (robot.HasValue && part.RobotVoiceMode != robot.Value)
            robotScript = ScoreRobotVoiceScript(robot.Value);
        WIVSMBreathEffect? breath = part.BreathEffect;
        WIVSMTakeEffect? take = part.TakeEffect;
        WIVSMVoiceColorEffect? color = part.VoiceColorEffect;
        if ((breathMode.HasValue || breathType.HasValue || options.TryGetProperty("breath_exhalation", out _)) && breath is null)
            throw new NotSupportedException("The native part has no Breath effect.");
        if (options.TryGetProperty("take_lane", out _) && take is null)
            throw new NotSupportedException("The native part has no Take effect.");
        int? exhalation = options.TryGetProperty("breath_exhalation", out _)
            ? ScoreInt(options, "breath_exhalation", breath!.ExhalationSetting.LowerBoundValue, breath.ExhalationSetting.UpperBoundValue) : null;
        int? lane = options.TryGetProperty("take_lane", out _)
            ? ScoreInt(options, "take_lane", take!.LaneSetting.LowerBoundValue, take.LaneSetting.UpperBoundValue) : null;
        Dictionary<VSMVoiceColor, int> colors = [];
        if (options.TryGetProperty("voice_colors", out JsonElement colorOptions))
        {
            if (colorOptions.ValueKind != JsonValueKind.Object || color is null)
                throw new ArgumentException("voice_colors requires a native VoiceColor effect and an object of values.");
            foreach (JsonProperty entry in colorOptions.EnumerateObject())
            {
                if (!Enum.TryParse(entry.Name, true, out VSMVoiceColor name) || !Enum.IsDefined(name) || colors.ContainsKey(name))
                    throw new ArgumentException("Unknown or duplicate voice color: " + entry.Name);
                VSMMidiEffectSetting bounds = color.VoiceColorSetting(name);
                if (!entry.Value.TryGetInt32(out int value) || value < bounds.LowerBoundValue || value > bounds.UpperBoundValue)
                    throw new ArgumentOutOfRangeException(entry.Name, "Voice color exceeds its native bounds.");
                colors.Add(name, value);
            }
        }
        Dictionary<VSMMidiEffectType, bool> bypass = [];
        if (options.TryGetProperty("bypass", out JsonElement bypassOptions))
        {
            if (bypassOptions.ValueKind != JsonValueKind.Object)
                throw new ArgumentException("bypass must be an object of native MIDI effect names and booleans.");
            foreach (JsonProperty entry in bypassOptions.EnumerateObject())
            {
                if (!Enum.TryParse(entry.Name, true, out VSMMidiEffectType name) || !Enum.IsDefined(name) || bypass.ContainsKey(name)
                    || part.GetMidiEffect(name) is null || entry.Value.ValueKind is not (JsonValueKind.True or JsonValueKind.False))
                    throw new ArgumentException("Unavailable, duplicate, or invalid MIDI effect bypass: " + entry.Name);
                bypass.Add(name, entry.Value.GetBoolean());
            }
        }
        if (!robot.HasValue && !breathMode.HasValue && !breathType.HasValue && !exhalation.HasValue && !lane.HasValue
            && colors.Count == 0 && bypass.Count == 0)
            throw new ArgumentException("performance.set requires at least one performance value.");

        return ScoreMutate(session, "performance.set", () =>
        {
            if (robot.HasValue && part.RobotVoiceMode != robot.Value)
            {
                WIVSMRobotVoiceEffect effect = part.RobotVoiceEffect!;
                ScoreRequire(effect.SetRobotVoiceMode(robot.Value), "performance.set robot", session.Sequence);
                effect.ScriptFilePath = robotScript!;
                effect.Timing = VSMMidiEffectTiming.BeforeRendering;
                ScoreRequire(effect.ScriptFilePath == robotScript && effect.Timing == VSMMidiEffectTiming.BeforeRendering,
                    "performance.set robot script", session.Sequence);
            }
            if (breathMode.HasValue && part.BreathMode != breathMode.Value)
                ScoreRequire(part.SetBreathMode(breathMode.Value), "performance.set breath mode", session.Sequence);
            if (breathType.HasValue && part.BreathType != breathType.Value)
                ScoreRequire(part.SetBreathType(breathType.Value), "performance.set breath type", session.Sequence);
            if (exhalation.HasValue && part.BreathExhalation != exhalation.Value)
                ScoreRequire(part.SetBreathExhalation(exhalation.Value), "performance.set exhalation", session.Sequence);
            if (lane.HasValue && part.TakeLane != lane.Value)
                ScoreRequire(part.SetTake(lane.Value), "performance.set take", session.Sequence);
            foreach ((VSMVoiceColor name, int value) in colors)
                if (part.VoiceColorValue(name) != value)
                    ScoreRequire(part.SetVoiceColor(name, value), "performance.set voice color", session.Sequence);
            foreach ((VSMMidiEffectType name, bool value) in bypass)
                if (part.IsBypassed(name) != value)
                    ScoreRequire(part.SetBypass(name, value), "performance.set bypass", session.Sequence);
            return true;
        }, () =>
        {
            WIVSMMidiPart current = ScorePart(ScoreMidiTrack(session, trackIndex), options);
            ScoreRequire((!robot.HasValue || current.RobotVoiceMode == robot.Value)
                && (!breathMode.HasValue || current.BreathMode == breathMode.Value)
                && (!breathType.HasValue || current.BreathType == breathType.Value)
                && (!exhalation.HasValue || current.BreathExhalation == exhalation.Value)
                && (!lane.HasValue || current.TakeLane == lane.Value)
                && colors.All(entry => current.VoiceColorValue(entry.Key) == entry.Value)
                && bypass.All(entry => current.IsBypassed(entry.Key) == entry.Value), "performance.set readback", session.Sequence);
            return ScorePerformanceView(current);
        });
    }

    private static object ScoreAutomationList(EngineSession session, JsonElement options)
    {
        string scope = ScoreString(options, "scope");
        WIVSMSequence sequence = session.Sequence;
        int? trackIndex = scope == "master_volume" ? null : ScoreTrackIndex(session, options);
        WIVSMTrack? track = trackIndex.HasValue ? ScoreTrack(session, trackIndex.Value) : null;
        (long Tick, int Value)[] points = scope switch
        {
            "master_volume" => sequence.MasterVolumesEnumerator.Select(item => (item.RelPosTick.Value, item.Value)).ToArray(),
            "track_volume" => track!.VolumesEnumerator.Select(item => (item.RelPosTick.Value, item.Value)).ToArray(),
            "track_pan" => track!.PanpotsEnumerator.Select(item => (item.RelPosTick.Value, item.Value)).ToArray(),
            _ => throw new ArgumentException("scope must be master_volume, track_volume, or track_pan.")
        };
        int minimum = scope == "master_volume" ? sequence.GetMinVolumeValue()
            : scope == "track_volume" ? track!.GetMinVolumeValue() : track!.GetMinPanpotValue();
        int maximum = scope == "master_volume" ? sequence.GetMaxVolumeValue()
            : scope == "track_volume" ? track!.GetMaxVolumeValue() : track!.GetMaxPanpotValue();
        int defaultValue = scope == "master_volume" ? sequence.GetDefaultVolumeValue()
            : scope == "track_volume" ? track!.GetDefaultVolumeValue() : track!.GetDefaultPanpotValue();
        return new
        {
            scope, track_index = trackIndex, minimum, maximum, default_value = defaultValue,
            points = points.Select((point, index) => new { event_index = index, tick = point.Tick, value = point.Value }).ToArray()
        };
    }

    private static object ScoreAutomationEdit(EngineSession session, string operation, JsonElement options)
    {
        string scope = ScoreString(options, "scope");
        if (scope is not ("master_volume" or "track_volume" or "track_pan"))
            throw new ArgumentException("scope must be master_volume, track_volume, or track_pan.");
        WIVSMSequence sequence = session.Sequence;
        WIVSMTrack? track = scope == "master_volume" ? null : ScoreTrack(session, ScoreTrackIndex(session, options));
        int minimum = scope == "master_volume" ? sequence.GetMinVolumeValue()
            : scope == "track_volume" ? track!.GetMinVolumeValue() : track!.GetMinPanpotValue();
        int maximum = scope == "master_volume" ? sequence.GetMaxVolumeValue()
            : scope == "track_volume" ? track!.GetMaxVolumeValue() : track!.GetMaxPanpotValue();
        if (operation == "automation.remove")
        {
            int count = scope == "master_volume" ? ScoreCount(sequence.NumMasterVolumes)
                : scope == "track_volume" ? ScoreCount(track!.NumVolumes) : ScoreCount(track!.NumPanpots);
            int index = ScoreInt(options, "event_index", 0, count - 1);
            long tick = scope == "master_volume" ? sequence.GetMasterVolume((ulong)index)!.RelPosTick.Value
                : scope == "track_volume" ? track!.GetVolume((ulong)index)!.RelPosTick.Value
                : track!.GetPanpot((ulong)index)!.RelPosTick.Value;
            if (tick == 0)
                throw new ArgumentException("The zero-tick automation event must be retained.");
            return ScoreMutate(session, operation, () =>
            {
                bool removed = scope == "master_volume" ? sequence.RemoveMasterVolume(sequence.GetMasterVolume((ulong)index))
                    : scope == "track_volume" ? track!.RemoveVolume(track.GetVolume((ulong)index)!)
                    : track!.RemovePanpot(track.GetPanpot((ulong)index)!);
                ScoreRequire(removed, operation, sequence);
                return true;
            }, () => ScoreAutomationList(session, options));
        }

        List<(int Tick, int Value)> points = [];
        HashSet<int> ticks = [];
        foreach (JsonElement point in ScorePoints(options).EnumerateArray())
        {
            int tick = ScoreInt(point, "tick", 0, int.MaxValue);
            if (!ticks.Add(tick))
                throw new ArgumentException("Automation points must have distinct ticks.");
            points.Add((tick, ScoreInt(point, "value", minimum, maximum)));
        }
        bool replace = ScoreBool(options, "replace");

        void Apply<T>(IEnumerable<T> values, Func<T, long> getTick, Func<T, int> getValue,
            Action<T, int> setValue, Func<T, bool> remove, Func<int, int, T?> insert) where T : class
        {
            Dictionary<long, T> existing = values.ToDictionary(getTick);
            if (replace)
                foreach ((long tick, T item) in existing.ToArray())
                    if (tick != 0 && !ticks.Contains(checked((int)tick)))
                    {
                        ScoreRequire(remove(item), operation + " remove", sequence);
                        existing.Remove(tick);
                    }
            foreach ((int tick, int value) in points.OrderBy(point => point.Tick))
                if (existing.TryGetValue(tick, out T? item))
                {
                    if (getValue(item) != value)
                        setValue(item, value);
                    ScoreRequire(getValue(item) == value, operation + " value", sequence);
                }
                else if (insert(tick, value) is null)
                    throw new InvalidOperationException("Native " + operation + " insertion failed: " + sequence.LastError);
        }

        return ScoreMutate(session, operation, () =>
        {
            if (scope == "master_volume")
                Apply(sequence.MasterVolumesEnumerator, item => item.RelPosTick.Value, item => item.Value,
                    (item, value) => item.Value = value, sequence.RemoveMasterVolume,
                    (tick, value) => sequence.InsertMasterVolume(new VSMRelTick(tick), value));
            else if (scope == "track_volume")
                Apply(track!.VolumesEnumerator, item => item.RelPosTick.Value, item => item.Value,
                    (item, value) => item.Value = value, track.RemoveVolume,
                    (tick, value) => track.InsertVolume(new VSMRelTick(tick), value));
            else
                Apply(track!.PanpotsEnumerator, item => item.RelPosTick.Value, item => item.Value,
                    (item, value) => item.Value = value, track.RemovePanpot,
                    (tick, value) => track.InsertPanpot(new VSMRelTick(tick), value));
            return true;
        }, () => ScoreAutomationList(session, options));
    }

    private static object ScorePitchList(EngineSession session, JsonElement options)
    {
        WIVSMMidiPart part = ScorePart(ScoreMidiTrack(session, ScoreTrackIndex(session, options)), options);
        return ScorePitchList(ScoreNote(part, options));
    }

    private static object ScorePitchList(WIVSMNote note)
    {
        return ScorePitchList(ScorePitchPoints(note));
    }

    private static VSMDirectPitchData[] ScorePitchPoints(WIVSMNote note)
    {
        return Enumerable.Range(0, ScoreCount(note.NumDirectPitches)).Select(index =>
            note.DirectPitchData((ulong)index) ?? throw new InvalidOperationException("Native direct pitch lookup failed.")).ToArray();
    }

    private static object ScorePitchList(IEnumerable<VSMDirectPitchData> points)
    {
        return new { points = points.Select(point => new { tick = point.Tick, value = VSMScore.GetRawNoteNumberFromPitch(point.Value) }).ToArray() };
    }

    private static object ScorePitchEdit(EngineSession session, string operation, JsonElement options)
    {
        WIVSMMidiPart part = ScorePart(ScoreMidiTrack(session, ScoreTrackIndex(session, options)), options);
        WIVSMNote note = ScoreNote(part, options);
        int start = checked((int)note.RelPosTick.Value);
        int duration = checked((int)note.DurationTick.Value);
        VSMDirectPitchData[] before = ScorePitchPoints(note);
        if (operation == "pitch.clear")
        {
            int begin = ScoreInt(options, "begin_tick", 0, duration - 1, 0);
            int end = ScoreInt(options, "end_tick", begin + 1, duration, duration);
            bool clearAll = begin == 0 && end == duration;
            VSMDirectPitchData[] expected = clearAll ? [] : before.Where(point => point.Tick < begin || point.Tick >= end).ToArray();
            object ReadClearedPitch()
            {
                VSMDirectPitchData[] actual = ScorePitchPoints(ScoreNote(
                    ScorePart(ScoreMidiTrack(session, ScoreTrackIndex(session, options)), options), options));
                ScoreRequire(actual.Length == expected.Length && expected.All(point => actual.Any(item =>
                    item.Tick == point.Tick && item.Value == point.Value)), operation + " readback", session.Sequence);
                return ScorePitchList(actual);
            }
            if (before.Length == expected.Length)
                return ScoreMutate(session, operation, () => true, ReadClearedPitch);
            return ScoreMutate(session, operation, () =>
            {
                ScoreRequire(note.ClearDirectPitches(clearAll ? WIVSMNote.DirectPitchClearingBeginTick : new VSMRelTick(begin),
                    clearAll ? WIVSMNote.DirectPitchClearingEndTick : new VSMRelTick(end)), operation, session.Sequence);
                return true;
            }, ReadClearedPitch);
        }
        List<VSMDirectPitchData> points = [];
        HashSet<int> ticks = [];
        foreach (JsonElement point in ScorePoints(options).EnumerateArray())
        {
            int tick = ScoreInt(point, "tick", 0, duration - 1);
            float value = VSMScore.GetPitchFromRawNoteNumber(ScoreFloat(point, "value", 0, 127));
            if (!ticks.Add(tick))
                throw new ArgumentException("Direct pitch points require distinct ticks.");
            points.Add(new VSMDirectPitchData(tick, value));
        }
        bool replace = ScoreBool(options, "replace");
        return ScoreMutate(session, operation, () =>
        {
            if (replace && before.Length != 0)
                ScoreRequire(note.ClearDirectPitches(WIVSMNote.DirectPitchClearingBeginTick, WIVSMNote.DirectPitchClearingEndTick),
                    operation + " replace", session.Sequence);
            foreach (VSMDirectPitchData point in points.OrderBy(point => point.Tick))
                ScoreRequire(note.SetDirectPitch(new VSMRelTick(point.Tick), point.Value), operation + " set point", session.Sequence);
            return true;
        }, () =>
        {
            VSMDirectPitchData[] actual = ScorePitchPoints(ScoreNote(
                ScorePart(ScoreMidiTrack(session, ScoreTrackIndex(session, options)), options), options));
            foreach (VSMDirectPitchData point in points)
                ScoreRequire(actual.Any(item => item.Tick == point.Tick && Math.Abs(item.Value - point.Value) <= 0.01f),
                    operation + " point " + point.Tick + " readback", session.Sequence);
            return ScorePitchList(actual);
        });
    }

    private static object ScoreSequenceSummary(WIVSMSequence sequence) => new
    {
        title = sequence.Title,
        track_count = sequence.NumTrack,
        sample_rate = (int)sequence.GetSamplingRate(),
        presend_time_sec = sequence.PresendTimeSec,
        global_bpm = sequence.GlobalTempo / 100.0,
        global_tempo_enabled = sequence.IsGlobalTempoEnabled,
        current_tick = sequence.CurrentPosTick.Value
    };

    private static object ScoreSequenceEdit(EngineSession session, JsonElement options)
    {
        WIVSMSequence sequence = session.Sequence;
        string? title = options.TryGetProperty("title", out _) ? ScoreString(options, "title") : null;
        int? tempo = options.TryGetProperty("global_bpm", out _) ? ScoreBpm(options, "global_bpm", sequence) : null;
        bool? global = options.TryGetProperty("global_tempo_enabled", out _) ? ScoreBool(options, "global_tempo_enabled") : null;
        int? sampleRate = options.TryGetProperty("sample_rate", out _) ? ScoreInt(options, "sample_rate", 44100, 96000) : null;
        if (sampleRate is not null && !Enum.IsDefined(typeof(VSMSamplingRate), sampleRate.Value))
            throw new ArgumentException("sample_rate must be 44100, 48000, or 96000.");
        if (title is null && tempo is null && global is null && sampleRate is null)
            throw new ArgumentException("sequence.update requires a sequence field to update.");
        return ScoreMutate(session, "sequence.update", () =>
        {
            if (sampleRate is not null)
            {
                ScoreRequire(sequence.SetSamplingRate((VSMSamplingRate)sampleRate.Value), "sequence.update sample_rate", sequence);
                ScoreRequire((int)sequence.GetSamplingRate() == sampleRate.Value, "sequence.update sample_rate readback", sequence);
            }
            if (title is not null)
            {
                sequence.Title = title;
                ScoreRequire(sequence.Title == title, "sequence.update title", sequence);
            }
            if (tempo is not null)
            {
                sequence.GlobalTempo = tempo.Value;
                ScoreRequire(sequence.GlobalTempo == tempo.Value, "sequence.update global_bpm", sequence);
            }
            if (global is not null)
            {
                sequence.IsGlobalTempoEnabled = global.Value;
                ScoreRequire(sequence.IsGlobalTempoEnabled == global.Value, "sequence.update global_tempo_enabled", sequence);
            }
            return ScoreSequenceSummary(sequence);
        });
    }

    private static object ScoreLoopSummary(WIVSMSequence sequence) => new
    {
        enabled = sequence.IsLoopOn,
        start_tick = sequence.LoopRange.Begin,
        end_tick = sequence.LoopRange.End
    };

    private static object ScoreLoopEdit(EngineSession session, JsonElement options)
    {
        WIVSMSequence sequence = session.Sequence;
        bool range = options.TryGetProperty("start_tick", out _) || options.TryGetProperty("end_tick", out _);
        bool hasEnabled = options.TryGetProperty("enabled", out _);
        if (!range && !hasEnabled)
            throw new ArgumentException("loop.set requires enabled or loop range ticks.");
        int begin = ScoreInt(options, "start_tick", 0, int.MaxValue - 1, sequence.LoopRange.Begin);
        int end = ScoreInt(options, "end_tick", begin + 1, int.MaxValue, sequence.LoopRange.End);
        if (range && end <= begin)
            throw new ArgumentException("Loop end_tick must be greater than start_tick.");
        bool enabled = ScoreBool(options, "enabled", sequence.IsLoopOn);
        return ScoreMutate(session, "loop.set", () =>
        {
            if (range)
                ScoreRequire(sequence.SetLoopRange(new VSMTickRange(begin, end)), "loop.set range", sequence);
            if (hasEnabled)
            {
                sequence.IsLoopOn = enabled;
                ScoreRequire(sequence.IsLoopOn == enabled, "loop.set enabled", sequence);
            }
            return ScoreLoopSummary(sequence);
        });
    }

    private static object ScoreTuningSummary(WIVSMSequence sequence) => new
    {
        value = sequence.MainTuning,
        minimum = sequence.MinMainTuning,
        maximum = sequence.MaxMainTuning,
        default_value = sequence.DefaultMainTuning
    };

    private static object ScoreTuningEdit(EngineSession session, JsonElement options)
    {
        WIVSMSequence sequence = session.Sequence;
        float value = ScoreFloat(options, "value", sequence.MinMainTuning, sequence.MaxMainTuning);
        return ScoreMutate(session, "tuning.set", () =>
        {
            ScoreRequire(sequence.SetMainTuning(value), "tuning.set", sequence);
            return ScoreTuningSummary(sequence);
        });
    }

    private static object ScoreNoteBatchUpdate(EngineSession session, JsonElement options)
    {
        WIVSMMidiPart part = ScorePart(ScoreMidiTrack(session, ScoreTrackIndex(session, options)), options);
        int[] indices = ScoreIndices(options, "note_indices", ScoreCount(part.NumNotes), 1);
        int? transpose = options.TryGetProperty("transpose", out _) ? ScoreInt(options, "transpose", -127, 127) : null;
        string[]? lyrics = null;
        if (options.TryGetProperty("lyrics", out JsonElement array))
        {
            if (array.ValueKind != JsonValueKind.Array || array.GetArrayLength() != indices.Length)
                throw new ArgumentException("lyrics must contain one string per note index.");
            lyrics = array.EnumerateArray().Select(item => item.ValueKind == JsonValueKind.String && item.GetString()!.Length <= 16384 && !item.GetString()!.Contains('\0')
                ? item.GetString()! : throw new ArgumentException("lyrics must contain valid strings.")).ToArray();
        }
        if (transpose is null && lyrics is null) throw new ArgumentException("transpose or lyrics is required.");
        WIVSMNote[] notes = indices.Select(index => part.GetNote((ulong)index)!).ToArray();
        int[] numbers = notes.Select(note => note.NoteNumber + (transpose ?? 0)).ToArray();
        if (numbers.Any(number => number < part.GetMinNoteEvent().Number || number > part.GetMaxNoteEvent(0).Number))
            throw new ArgumentOutOfRangeException("transpose");
        return ScoreMutate(session, "note.batch_update", () => {
            for (int i = 0; i < notes.Length; i++)
            {
                if (transpose is not null) ScoreRequire(notes[i].SetNoteNumber(numbers[i]), "note.batch_update number", session.Sequence);
                if (lyrics is not null) notes[i].Lyric = lyrics[i];
            }
            return true;
        }, () => {
            WIVSMMidiPart current = ScorePart(ScoreMidiTrack(session, ScoreTrackIndex(session, options)), options);
            for (int i = 0; i < indices.Length; i++)
            {
                WIVSMNote note = current.GetNote((ulong)indices[i])!;
                ScoreRequire(note.NoteNumber == numbers[i] && (lyrics is null || note.Lyric == lyrics[i]), "note.batch_update readback", session.Sequence);
            }
            return ScoreNoteList(session, options);
        });
    }

    private static object ScoreVibrato(EngineSession session, string operation, JsonElement options)
    {
        WIVSMNote GetNote() => ScoreNote(ScorePart(ScoreMidiTrack(session, ScoreTrackIndex(session, options)), options), options);
        object Read()
        {
            WIVSMNote n = GetNote();
            object[] Events(VSMVibratoEventType type) => Enumerable.Range(0, ScoreCount(n.GetNumVibratoEvent(type)))
                .Select(i => n.GetVibratoEvent(type, (ulong)i)!).Select(e => (object)new { tick = e.RelPosTick.Value, value = e.Value }).ToArray();
            return new { type = n.VibratoType.ToString(), duration_tick = n.VibratoDurationTick.Value, ai_enabled = n.IsAiVibratoEnabled,
                depth = Events(VSMVibratoEventType.Depth), rate = Events(VSMVibratoEventType.Rate) };
        }
        if (operation == "vibrato.get") return Read();
        WIVSMNote note = GetNote();
        VSMVibratoType? type = options.TryGetProperty("type", out _) ? ScorePerformanceEnum<VSMVibratoType>(options, "type") : null;
        int? duration = options.TryGetProperty("duration_tick", out _) ? ScoreInt(options, "duration_tick", 0, checked((int)note.DurationTick.Value)) : null;
        bool? enabled = options.TryGetProperty("ai_enabled", out _) ? ScoreBool(options, "ai_enabled") : null;
        List<(VSMVibratoEventType Type, int Tick, int Value)> points = [];
        foreach ((string name, VSMVibratoEventType kind) in new[] { ("depth", VSMVibratoEventType.Depth), ("rate", VSMVibratoEventType.Rate) })
        {
            if (!options.TryGetProperty(name, out JsonElement values)) continue;
            if (values.ValueKind != JsonValueKind.Array || values.GetArrayLength() > 8192)
                throw new ArgumentException(name + " must be an array of at most 8192 events.");
            HashSet<int> ticks = [];
            foreach (JsonElement value in values.EnumerateArray())
            {
                int tick = ScoreInt(value, "tick", 0, checked((int)note.DurationTick.Value));
                if (!ticks.Add(tick)) throw new ArgumentException(name + " ticks must be distinct.");
                points.Add((kind, tick, ScoreInt(value, "value", note.GetMinVibratoEventValue(kind), note.GetMaxVibratoEventValue(kind))));
            }
        }
        bool hasDepth = options.TryGetProperty("depth", out _), hasRate = options.TryGetProperty("rate", out _);
        if (type is null && duration is null && enabled is null && !hasDepth && !hasRate) throw new ArgumentException("A vibrato field is required.");
        return ScoreMutate(session, operation, () => {
            if (type is not null) note.VibratoType = type.Value;
            if (duration is not null) ScoreRequire(note.SetVibratoDuration(new VSMRelTick(duration.Value)), operation + " duration", session.Sequence);
            if (enabled is not null) ScoreRequire(note.SetAiVibratoEnabled(enabled.Value), operation + " ai_enabled", session.Sequence);
            if (hasDepth && note.GetNumVibratoEvent(VSMVibratoEventType.Depth) > 0)
                ScoreRequire(note.RemoveAllVibratoEvents(VSMVibratoEventType.Depth), operation + " depth clear", session.Sequence);
            if (hasRate && note.GetNumVibratoEvent(VSMVibratoEventType.Rate) > 0)
                ScoreRequire(note.RemoveAllVibratoEvents(VSMVibratoEventType.Rate), operation + " rate clear", session.Sequence);
            foreach (var point in points.OrderBy(point => point.Tick))
                if (note.InsertVibratoEvent(new VSMRelTick(point.Tick), point.Type, point.Value) is null)
                    throw new InvalidOperationException("Native vibrato event insertion failed: " + session.Sequence.LastError);
            return true;
        }, () => {
            WIVSMNote current = GetNote();
            ScoreRequire((type is null || current.VibratoType == type.Value) && (duration is null || current.VibratoDurationTick.Value == duration.Value) &&
                (enabled is null || current.IsAiVibratoEnabled == enabled.Value), operation + " readback", session.Sequence);
            foreach (VSMVibratoEventType kind in new[] { VSMVibratoEventType.Depth, VSMVibratoEventType.Rate })
            {
                if (kind == VSMVibratoEventType.Depth ? !hasDepth : !hasRate) continue;
                var expected = points.Where(point => point.Type == kind).ToArray();
                ScoreRequire(current.GetNumVibratoEvent(kind) == (ulong)expected.Length && expected.All(point =>
                    Enumerable.Range(0, expected.Length).Select(i => current.GetVibratoEvent(kind, (ulong)i)!).Any(e => e.RelPosTick.Value == point.Tick && e.Value == point.Value)), operation + " event readback", session.Sequence);
            }
            return Read();
        });
    }

    private static object ScoreTimeConvert(WIVSMSequence sequence, JsonElement options)
    {
        string from = ScoreString(options, "from");
        double seconds = from switch
        {
            "tick" => sequence.GetTimeFromTick(new VSMAbsTick(0), new VSMAbsTick(ScoreInt(options, "value", 0, int.MaxValue))),
            "bar" => sequence.GetTimeFromTick(new VSMAbsTick(0), sequence.GetTickFromBar(ScoreInt(options, "value", 0, int.MaxValue))),
            "sample" => sequence.GetTimeFromSample(ScoreInt(options, "value", 0, int.MaxValue), sequence.GetSamplingRate()),
            "seconds" => ScoreFloat(options, "value", 0, float.MaxValue),
            _ => throw new ArgumentException("from must be tick, bar, sample, or seconds.")
        };
        VSMAbsTick tick = sequence.GetTickFromTime(new VSMAbsTick(0), seconds);
        VSMBeatTime beat = sequence.GetBeatTimeFromTick(tick);
        return new { seconds, tick = tick.Value, bar = beat.Bar, beat = beat.Beat, clock = beat.Clock,
            sample = sequence.GetSampleFromTime(seconds, sequence.GetSamplingRate()), sample_rate = (int)sequence.GetSamplingRate() };
    }

    private static object ScoreRollback(EngineSession session)
    {
        WIVSMSequence sequence = session.Sequence;
        if (!sequence.IsStaged) return new { rolled_back = false, staged = false };
        session.ArchiveBegin?.Invoke("history.rollback");
        bool tracking = session.ArchiveEnd is not null;
        void End(string action) { if (tracking) { tracking = false; session.ArchiveEnd!(action); } }
        try
        {
            ScoreRequire(sequence.Rollback(), "history.rollback", sequence);
            ScoreRequire(!sequence.IsStaged, "history.rollback readback", sequence);
            End("rollback");
            return new { rolled_back = true, staged = false };
        }
        catch { End("invalid"); throw; }
        finally { session.InvalidateChildren(); }
    }

    private static object ScorePhonemeTiming(EngineSession session, string operation, JsonElement options)
    {
        WIVSMNote GetNote() => ScoreNote(ScorePart(ScoreMidiTrack(session, ScoreTrackIndex(session, options)), options), options);
        object Read()
        {
            WIVSMNote n = GetNote();
            return new { positions = n.GetPhonemePositions(), original_positions = n.GetOriginalPhonemePositions(),
                ranges = Enumerable.Range(0, n.NumPhonemePosition).Select(i => {
                    VSMTickRange range = n.GetAcceptablePhonemePositionRange(i);
                    return new { index = i, begin = range.Begin, end = range.End }; }).ToArray() };
        }
        WIVSMNote note = GetNote();
        if (operation == "phoneme_timing.get") return Read();
        int index = ScoreInt(options, "phoneme_index", 0, note.NumPhonemePosition - 1);
        VSMTickRange acceptable = note.GetAcceptablePhonemePositionRange(index);
        int position = operation == "phoneme_timing.set" ? ScoreInt(options, "tick", acceptable.Begin, acceptable.End) : 0;
        return ScoreMutate(session, operation, () => {
            ScoreRequire(operation == "phoneme_timing.set" ? note.SetEditedPhonemePosition(index, new VSMRelTick(position)) : note.ResetEditedPhonemePosition(index), operation, session.Sequence);
            return true;
        }, () => {
            if (operation == "phoneme_timing.set") ScoreRequire(GetNote().GetPhonemePositions()[index] == position, operation + " readback", session.Sequence);
            return Read();
        });
    }

    private static object ScoreHistory(WIVSMSequence sequence) => new
    {
        can_undo = sequence.CanUndo(),
        can_redo = sequence.CanRedo(),
        max_undo_count = sequence.GetMaxUndoCount(),
        staged = sequence.IsStaged
    };

    private static object ScoreHistoryMove(EngineSession session, bool redo)
    {
        WIVSMSequence sequence = session.Sequence;
        ScoreRequireUnstaged(sequence);
        if (!(redo ? sequence.CanRedo() : sequence.CanUndo()))
            throw new InvalidOperationException(redo ? "Native redo is unavailable." : "Native undo is unavailable.");
        session.ArchiveBegin?.Invoke(redo ? "redo" : "undo");
        bool tracking = session.ArchiveEnd is not null;
        void End(string action) { if (tracking) { tracking = false; session.ArchiveEnd!(action); } }
        try
        {
            if (redo)
                sequence.Redo();
            else
                sequence.Undo();
            End(redo ? "redo" : "undo");
            session.Dirty = true;
            return ScoreHistory(sequence);
        }
        catch { End("invalid"); throw; }
        finally
        {
            session.InvalidateChildren();
        }
    }

    private static object ScoreMutate(EngineSession session, string operation, Func<object> action, Func<object>? readback = null)
    {
        WIVSMSequence sequence = session.Sequence;
        ScoreRequireUnstaged(sequence);
        session.ArchiveBegin?.Invoke(operation);
        bool tracking = session.ArchiveEnd is not null;
        void End(string action) { if (tracking) { tracking = false; session.ArchiveEnd!(action); } }
        try
        {
            object result = action();
            bool staged = sequence.IsStaged;
            if (staged && !sequence.Commit())
            {
                End("invalid");
                throw new InvalidOperationException("Native " + operation + " commit failed: " + sequence.LastError);
            }
            End(staged ? "commit" : "sync");
            session.Dirty = true;
            return readback is null ? result : readback();
        }
        catch (Exception error)
        {
            bool staged = sequence.IsStaged;
            if (staged && !sequence.Rollback())
            {
                session.Dirty = true;
                End("invalid");
                throw new InvalidOperationException("Native " + operation + " failed and rollback failed: " + sequence.LastError, error);
            }
            End(staged ? "rollback" : "sync");
            throw;
        }
        finally
        {
            session.InvalidateChildren();
        }
    }

    private static void ScoreRequireUnstaged(WIVSMSequence sequence)
    {
        if (sequence.IsStaged)
            throw new InvalidOperationException("Commit or rollback pending native edits before using score mutations.");
    }

    private static void ScoreRequire(bool success, string operation, WIVSMSequence sequence)
    {
        if (!success)
            throw new InvalidOperationException("Native " + operation + " failed: " + sequence.LastError);
    }

    private static int ScoreCount(ulong count)
    {
        if (count > 65536)
            throw new InvalidOperationException("Native score collection exceeds the 65536-item limit.");
        return (int)count;
    }

    private static int[] ScoreIndices(JsonElement options, string name, int count, int minimumCount)
    {
        if (!options.TryGetProperty(name, out JsonElement values) || values.ValueKind != JsonValueKind.Array ||
            values.GetArrayLength() < minimumCount || values.GetArrayLength() > 65536)
            throw new ArgumentException(name + " must be an index array with " + minimumCount + "..65536 entries.");
        HashSet<int> seen = [];
        List<int> result = [];
        foreach (JsonElement value in values.EnumerateArray())
        {
            if (value.ValueKind != JsonValueKind.Number || !value.TryGetInt32(out int index) || index < 0 || index >= count || !seen.Add(index))
                throw new ArgumentException(name + " must contain distinct existing indices.");
            result.Add(index);
        }
        return result.ToArray();
    }

    private static int ScoreInt(JsonElement options, string name, int minimum, int maximum, int? defaultValue = null)
    {
        if (!options.TryGetProperty(name, out JsonElement value))
        {
            int fallback = defaultValue ?? throw new ArgumentException("Missing integer option: " + name);
            if (fallback < minimum || fallback > maximum)
                throw new ArgumentOutOfRangeException(name, $"{name} must be an integer in {minimum}..{maximum}.");
            return fallback;
        }
        if (value.ValueKind != JsonValueKind.Number || !value.TryGetInt32(out int result) || result < minimum || result > maximum)
            throw new ArgumentOutOfRangeException(name, $"{name} must be an integer in {minimum}..{maximum}.");
        return result;
    }

    private static float ScoreFloat(JsonElement options, string name, float minimum, float maximum, float? defaultValue = null)
    {
        if (!options.TryGetProperty(name, out JsonElement value))
            return defaultValue ?? throw new ArgumentException("Missing numeric option: " + name);
        if (value.ValueKind != JsonValueKind.Number || !value.TryGetSingle(out float result) ||
            !float.IsFinite(result) || result < minimum || result > maximum)
            throw new ArgumentOutOfRangeException(name, $"{name} must be finite and in {minimum}..{maximum}.");
        return result;
    }

    private static bool ScoreBool(JsonElement options, string name, bool defaultValue = false)
    {
        if (!options.TryGetProperty(name, out JsonElement value))
            return defaultValue;
        if (value.ValueKind is not (JsonValueKind.True or JsonValueKind.False))
            throw new ArgumentException(name + " must be a Boolean.");
        return value.GetBoolean();
    }

    private static string ScoreString(JsonElement options, string name, string? defaultValue = null)
    {
        if (!options.TryGetProperty(name, out JsonElement value))
            return defaultValue ?? throw new ArgumentException("Missing string option: " + name);
        if (value.ValueKind != JsonValueKind.String)
            throw new ArgumentException(name + " must be a string.");
        string result = value.GetString()!;
        if (result.Length > 16384 || result.Contains('\0'))
            throw new ArgumentException(name + " exceeds 16384 characters or contains NUL.");
        return result;
    }
}
