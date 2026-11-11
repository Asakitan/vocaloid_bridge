#if VOCALOID7
using System.IO;
using System.Text.Json;
using Yamaha.VOCALOID.VSM;

internal sealed partial class EngineHost
{
    private static WIVSMMidiPart ScoreAiPart(EngineSession session, JsonElement options)
    {
        WIVSMMidiPart part = ScorePart(ScoreMidiTrack(session, ScoreTrackIndex(session, options)), options);
        if (!part.IsAi)
            throw new NotSupportedException("Native AI generation requires a MidiAi part.");
        return part;
    }

    private static object ScoreAiStatus(EngineSession session, JsonElement options)
    {
        WIVSMMidiPart part = ScoreAiPart(session, options);
        return new
        {
            generation = "native_ai_synthesis",
            rendered_score_valid = part.HasValidRenderedScore,
            rendered_wave_valid = part.HasValidRenderedWave,
            rendering_finished = session.Sequence.IsFinishedRendering,
            preserves_existing_direct_pitches = true,
            notes = Enumerable.Range(0, ScoreCount(part.NumNotes)).Select(index =>
            {
                WIVSMNote note = part.GetNote((ulong)index)
                    ?? throw new InvalidOperationException("Native AI note lookup failed.");
                return new { note_index = index, renderable = note.IsRenderable,
                    direct_pitch_points = note.NumDirectPitches };
            }).ToArray()
        };
    }

    private object ScoreAiGenerate(EngineSession session, JsonElement options)
    {
        ScoreRequireUnstaged(session.Sequence);
        WIVSMMidiPart part = ScoreAiPart(session, options);
        if (!part.Notes.Any(note => note.IsRenderable))
            throw new InvalidOperationException("Native AI generation requires at least one renderable note with valid lyrics and phonemes.");
        bool preservePitch = ScoreBool(options, "preserve_pitch");
        bool overwriteExisting = ScoreBool(options, "overwrite_existing");
        if (!preservePitch && (options.TryGetProperty("note_indices", out _) || options.TryGetProperty("overwrite_existing", out _)))
            throw new ArgumentException("note_indices and overwrite_existing require preserve_pitch=true.");
        int[] selected = preservePitch
            ? options.TryGetProperty("note_indices", out _)
                ? ScoreIndices(options, "note_indices", ScoreCount(part.NumNotes), 1)
                : Enumerable.Range(0, ScoreCount(part.NumNotes)).Where(index => part.GetNote((ulong)index)!.IsRenderable).ToArray()
            : [];
        foreach (int index in selected)
        {
            WIVSMNote note = part.GetNote((ulong)index)!;
            if (!note.IsRenderable)
                throw new InvalidOperationException("Selected AI note is not renderable: " + index);
            if (note.NumDirectPitches != 0 && !overwriteExisting)
                throw new InvalidOperationException("Selected AI note already has direct pitches: " + index
                    + "; preserve them or explicitly set overwrite_existing=true.");
        }
        EnsureVoiceServices();
        ScoreMutate(session, "performance.set", () =>
        {
            PrepareRobotVoice(part);
            PrepareSingingSkill(part);
            return true;
        });
        part = ScoreAiPart(session, options);
        VSMDirectPitchData[][] before = part.Notes.Select(ScorePitchPoints).ToArray();
        PathGuard.NoLinks(session.Directory);
        string temporary = Path.Combine(session.Directory, "ai-generation-" + Guid.NewGuid().ToString("N") + ".wav");
        try
        {
            var rendered = RenderNativePart(session.Sequence, part, temporary);
            var wave = InspectWave(temporary);
            WIVSMMidiPart current = ScoreAiPart(session, options);
            VSMDirectPitchData[][] after = current.Notes.Select(ScorePitchPoints).ToArray();
            ScoreRequire(current.HasValidRenderedScore && session.Sequence.IsFinishedRendering,
                "ai.generate rendered score", session.Sequence);
            ScoreRequire(before.Length == after.Length && before.Zip(after).All(notes =>
                notes.First.Length == notes.Second.Length && notes.First.Zip(notes.Second).All(points =>
                    points.First.Tick == points.Second.Tick && points.First.Value == points.Second.Value)),
                "ai.generate direct pitch preservation", session.Sequence);
            object? captured = preservePitch ? ScoreAiPreserve(session, options, selected) : null;
            return new
            {
                generation = "native_ai_synthesis",
                generated = true,
                direct_pitch_capture = preservePitch,
                preservation = captured,
                lua_result = rendered.LuaResult.ToString(),
                render_observation = rendered.Observation,
                audio = new { frames = wave.Frames, sample_rate = wave.SampleRate, channels = wave.Channels },
                status = ScoreAiStatus(session, options)
            };
        }
        finally
        {
            if (File.Exists(temporary)) File.Delete(temporary);
        }
    }

    private object ScoreAiPreserve(EngineSession session, JsonElement options, int[] selected)
    {
        WIVSMMidiPart part = ScoreAiPart(session, options);
        Dictionary<int, VSMDirectPitchData[]> expected = [];
        return ScoreMutate(session, "pitch.set", () =>
        {
            foreach (int index in selected)
                ArchiveNoteArrayValidateBeforeEdit(session, part.GetNote((ulong)index)!);
            foreach (int index in selected)
            {
                WIVSMNote note = part.GetNote((ulong)index)!;
                ScoreRequire(note.SetDirectPitchesFromRenderedPitches(), "ai.generate preserve note " + index, session.Sequence);
                VSMDirectPitchData[] points = ScorePitchPoints(note);
                ScoreRequire(points.Length != 0 && points.All(point => float.IsFinite(point.Value)),
                    "ai.generate preserve points " + index, session.Sequence);
                expected.Add(index, points);
                ArchiveNoteArraySetStaged(session, note, points, true);
            }
            return true;
        }, () =>
        {
            WIVSMMidiPart current = ScoreAiPart(session, options);
            foreach ((int index, VSMDirectPitchData[] points) in expected)
            {
                VSMDirectPitchData[] actual = ScorePitchPoints(current.GetNote((ulong)index)!);
                ScoreRequire(actual.Length == points.Length && points.Zip(actual).All(pair =>
                    pair.First.Tick == pair.Second.Tick && pair.First.Value == pair.Second.Value),
                    "ai.generate preserved pitch readback " + index, session.Sequence);
            }
            return new { notes = expected.Select(pair => new { note_index = pair.Key, point_count = pair.Value.Length }).ToArray(),
                atomic = true, undoable = true };
        });
    }
}
#endif