using System.IO;
using System.Text.Json;
using System.Collections.Concurrent;
using Yamaha.VOCALOID;
using Yamaha.VOCALOID.VAE;
using Yamaha.VOCALOID.VDM;
using Yamaha.VOCALOID.VEM;
using Yamaha.VOCALOID.VSM;
using Yamaha.VOCALOID.WOR;

#if VOCALOID7
using WEffectManager = Yamaha.VOCALOID.VEM.WAudioEffectManager;
#endif

internal sealed partial class EngineHost
{
    private WEffectManager? audioEffects;
    private Exception? audioEffectsFailure;
    private bool audioEngineInitialized;
    private AudioMixCallbacks? activeAudioMix;

    internal object AudioOperation(string id, string operation, JsonElement options)
    {
        EngineSession session = GetSession(id);
        if (options.ValueKind is not (JsonValueKind.Object or JsonValueKind.Undefined))
            throw new ArgumentException("Audio options must be an object.");
        if (transport is not null && operation != "devices" && !operation.StartsWith("transport_", StringComparison.Ordinal))
            throw new InvalidOperationException("Release the prepared transport before using other native audio operations.");
        return operation switch
        {
            "devices" or "transport_prepare" or "transport_status" or "transport_play" or "transport_stop" or "transport_seek" or "transport_release"
                => TransportOperation(session, operation, options),
            "inspect_audio" => InspectAudioFile(session, options),
            "import_audio" => ImportAudio(session, options),
            "edit_audio" => EditAudio(session, options),
            "export_audio" => ExportAudio(session, options),
            "process_audio" => ProcessAudio(session, options),
            "effects" => AudioEffects(session, options),
            "set_effect" => SetAudioEffect(session, options),
            "mixdown" => MixAudio(session, options),
            "mixdown_stems" => MixAudioStems(session, options),
            _ => throw new ArgumentException("Unknown audio operation: " + operation)
        };
    }

    private sealed class AudioMixCallbacks
    {
        internal readonly ManualResetEventSlim Completed = new(false);
        internal readonly ConcurrentQueue<(int Request, short Error)> Placements = new();
        internal readonly VEAudioEngineContext Context;
        internal readonly FuncMixdownProgress ProgressCallback;
        internal readonly FuncMixdownCompletion CompletionCallback;
        internal int Result = -1;
        internal float Progress;
        internal string? Failure;

        internal AudioMixCallbacks((double Quarter, double Seconds, int Tempo)[] tempos)
        {
            Context = new VEAudioEngineContext
            {
                Client = nint.Zero,
                EngineTickToTime = (client, tick) =>
                {
                    double quarter = tick / 15360.0;
                    var segment = tempos[0];
                    foreach (var candidate in tempos)
                    {
                        if (candidate.Quarter > quarter)
                            break;
                        segment = candidate;
                    }
                    return segment.Seconds + (quarter - segment.Quarter) * 6000.0 / segment.Tempo;
                },
                EngineTimeToTick = (client, seconds) =>
                {
                    var segment = tempos[0];
                    foreach (var candidate in tempos)
                    {
                        if (candidate.Seconds > seconds)
                            break;
                        segment = candidate;
                    }
                    double tick = (segment.Quarter + (seconds - segment.Seconds) * segment.Tempo / 6000.0) * 15360.0;
                    return (int)Math.Clamp(Math.Round(tick), int.MinValue, int.MaxValue);
                },
                EngineNTAudioDidStopAuto = client => { },
                EngineNTAudioDeviceDidDeactive = client => Volatile.Write(ref Failure, "Native audio device deactivated."),
                EngineNTAudioDeviceNeedReload = (client, sampleRate) => Volatile.Write(ref Failure, "Native audio device requested reload."),
                EngineNTLoopDidChange = (client, enabled, range) => { },
                EngineNTSampleRateDidChange = (client, sampleRate) => { },
                EngineNTCurrentPositionDidChange = (client, tick, tempo) => { },
                EngineNTNeedRequestSampleRate = client => { },
                EngineNTNeedReleaseAudioBuffer = (client, handle) => Volatile.Write(ref Failure, "Unexpected memory buffer in file-only native mix."),
                EngineNTPlacementResult = (client, type, request, error) => Placements.Enqueue((request, error))
            };
            ProgressCallback = (client, progress) => Volatile.Write(ref Progress, progress);
            CompletionCallback = (client, result) =>
            {
                Volatile.Write(ref Result, (int)result);
                Completed.Set();
            };
        }
    }

    private static (double Quarter, double Seconds, int Tempo)[] AudioTempoSnapshot(WIVSMSequence sequence)
    {
        if (sequence.NumTempos > 65536)
            throw new InvalidDataException("Native tempo count exceeds 65536 events.");
        List<(double Quarter, double Seconds, int Tempo)> tempos = [(0, sequence.GetTimeFromQuarter(0), sequence.GetDefaultTempoValue())];
        for (ulong index = 0; index < sequence.NumTempos; index++)
        {
            WIVSMTempo tempo = sequence.GetTempo(index) ?? throw new InvalidDataException("Native tempo event is missing.");
            double seconds = sequence.GetTimeFromTick(new VSMAbsTick(tempo.RelPosTick.Value));
            tempos.Add((sequence.GetQuarterFromTime(seconds), seconds, tempo.Value));
        }
        return tempos.GroupBy(value => value.Quarter).Select(group => group.Last()).OrderBy(value => value.Quarter).ToArray();
    }

    private static ulong[] AudioMixTrackIndices(EngineSession session, JsonElement options)
    {
        if (session.Sequence.NumTrack > 127)
            throw new InvalidOperationException("The native VAE mixer supports at most 127 tracks.");
        ulong[] tracks = options.TryGetProperty("track_indices", out JsonElement requested)
            ? requested.EnumerateArray().Select(value => value.GetUInt64()).Distinct().ToArray()
            : Enumerable.Range(0, (int)session.Sequence.NumTrack).Select(value => (ulong)value).ToArray();
        if (tracks.Length == 0 || tracks.Any(index => index >= session.Sequence.NumTrack))
            throw new ArgumentException("track_indices must contain existing native track indices.");
        return tracks;
    }

    private object MixAudioStems(EngineSession session, JsonElement options)
    {
        string prefix = AudioText(options, "output_prefix");
        ulong[] tracks = AudioMixTrackIndices(session, options);
        foreach (ulong track in tracks)
            PrepareOutput(session, prefix + "-track-" + track + ".wav", ".wav", AudioFlag(options, "overwrite"));
        List<object> results = [];
        foreach (ulong track in tracks)
        {
            Dictionary<string, object?> stemOptions = options.EnumerateObject().ToDictionary(property => property.Name, property => (object?)property.Value.Clone());
            stemOptions["output_name"] = prefix + "-track-" + track + ".wav";
            stemOptions["track_indices"] = new[] { track };
            results.Add(MixAudio(session, JsonSerializer.SerializeToElement(stemOptions), true));
        }
        return new { session_id = session.Id, native = true, stems = results };
    }

    private object MixAudio(EngineSession session, JsonElement options, bool stem = false)
    {
        ulong[] selected = AudioMixTrackIndices(session, options);
        if (options.TryGetProperty("start_seconds", out _) || options.TryGetProperty("end_seconds", out _) ||
            options.TryGetProperty("tail_seconds", out _))
            throw new NotSupportedException("Native mixdown exports complete selected tracks; start_seconds, end_seconds, and tail_seconds are not supported.");
        HashSet<ulong> selectedSet = new(selected);
        string destination = AudioDestination(session, options);
        int sampleRate = checked((int)AudioInteger(options, "sample_rate", 44100, 8000, 192000));
        if (sampleRate is not (44100 or 48000 or 96000 or 192000))
            throw new ArgumentException("Native mix sample_rate must be 44100, 48000, 96000, or 192000.");
        ushort channels = checked((ushort)AudioInteger(options, "channels", 2, 1, 2));
        int bits = checked((int)AudioInteger(options, "bits_per_sample", 24, 16, 24));
        if (bits is not (16 or 24))
            throw new ArgumentException("Native mix bits_per_sample must be 16 or 24.");
        int timeout = checked((int)AudioInteger(options, "timeout_seconds", 120, 1, 600));
        WIVSMSequence sequence = session.Sequence;
        EnsureVoiceServices();
        string temporary = AudioTemporary(session);
        List<VEAudioPlacement> placements = [];
        AudioMixCallbacks? callbacks = null;
        try
        {
            foreach (ulong index in selected)
            {
                WIVSMTrack track = sequence.GetTrack(index)!;
                if (track.Type is not (VSMTrackType.Midi or VSMTrackType.MidiAi))
                    continue;
                WIVSMMidiTrack midi = new(track);
                if (midi.IsFrozen)
                    continue;
                foreach (WIVSMPart item in track.Parts)
                {
                    WIVSMMidiPart part = new(item);
                    PrepareRobotVoice(part);
                    PrepareSingingSkill(part);
                    bool staged = sequence.IsStaged;
                    if (!sequence.Commit(false) && (staged || sequence.LastError != VSMResult.NoError))
                        throw new InvalidOperationException("Native pre-mix commit failed: " + sequence.LastError);
                    string rendered = AudioTemporary(session);
                    try
                    {
                        RenderNativePart(sequence, part, rendered);
                        InspectWave(rendered);
                    }
                    finally
                    {
                        if (File.Exists(rendered))
                            File.Delete(rendered);
                    }
                }
            }
            WEffectManager effects = SyncAudioEffects(session, !stem);
            effects.SetSampleRate(sampleRate);
            var tempos = AudioTempoSnapshot(sequence);
            if (!effects.RecreateTempoInfo(tempos.Select(value => new WEffectManager.VEMTempoInfo(value.Seconds, value.Tempo)).ToArray()))
                throw new InvalidOperationException("Native effect tempo synchronization failed.");
            effects.SetBypassAll(AudioFlag(options, "bypass_effects"));
            effects.ClearProcessMemory();
            callbacks = new AudioMixCallbacks(tempos);
            activeAudioMix = callbacks;
            VEAudioEngine.Initialize(nint.Zero);
            audioEngineInitialized = true;
            VEAudioEngineContext context = callbacks.Context;
            VEAudioEngine.SetAudioEngineContext(ref context);
            VEDeviceConfig configuration = new();
            configuration.Init();
            configuration.SampleRate = (uint)sampleRate;
            VEAudioEngineError engineResult = VEAudioEngine.StartEngine(ref configuration, out _, VEConnectMode.VST, out VEConnectMode connection);
            if (engineResult != VEAudioEngineError.Success || connection != VEConnectMode.VST)
                throw new InvalidOperationException("Native host-only mixer initialization failed: " + engineResult + "; connection=" + connection);
            if (VEAudioEngine.IsPlaying())
                throw new InvalidOperationException("Native host-only mixer unexpectedly entered playback.");
            VEAudioEngine.SetSampleRateFromHost(sampleRate);
#if VOCALOID7
            if (!VEAudioEngine.SetAudioEffectManager((nint)effects))
#else
            if (!VEAudioEngine.SetEffectManager((nint)effects))
#endif
                throw new InvalidOperationException("Native mixer effect-manager attachment failed.");
            VEAudioEngineError modeResult = VEAudioEngine.SetMixdownMode(VEMixdownMode.Manual);
            if (modeResult != VEAudioEngineError.Success)
                throw new InvalidOperationException("Native manual mixer initialization failed: " + modeResult);
            VEBusInfo buses = new() { BusBits = new uint[4], ExtBus = new VEExtBusInfo[127], ExtBusCount = 0 };
            foreach (ulong index in selected)
                buses.BusBits[(int)index >> 5] |= 1u << ((int)index & 31);
            VEAudioEngine.SetBusInfo(buses);
            SetAudioMixAutomation(sequence, !stem);
            bool explicitSelection = options.TryGetProperty("track_indices", out _);
#if !VOCALOID7
            bool anySolo = sequence.Tracks.Any(track => V7Compat.IsSolo(track));
#endif
            HashSet<int> pending = [];
            for (ulong index = 0; index < sequence.NumTrack; index++)
            {
                WIVSMTrack track = sequence.GetTrack(index)!;
#if VOCALOID7
                bool enabled = selectedSet.Contains(index) && (explicitSelection || !track.IsChannelMute);
#else
                bool enabled = selectedSet.Contains(index) && (explicitSelection || V7Compat.IsSolo(track) || (!V7Compat.IsMute(track) && !anySolo));
#endif
                VEAudioEngine.SetMixerInputEnabled((uint)index, enabled);
                if (!enabled)
                    continue;
                if (track.Type is VSMTrackType.Midi or VSMTrackType.MidiAi && new WIVSMMidiTrack(track) is { IsFrozen: true } frozen)
                {
                    AddAudioPlacement(AudioPlacementBuilder.CreateAudioPlacementFrozenTrack(sequence, frozen,
                        FrozenTrackTimeRange(sequence, frozen)), placements, pending);
                    continue;
                }
                foreach (WIVSMPart part in track.Parts)
                {
                    if (part.DurationSec <= 0)
                        continue;
                    PathGuard.NoLinks(part.PartFilePath);
                    InspectWave(part.PartFilePath);
                    AddAudioPlacement(AudioPlacementBuilder.CreateAudioPlacement(sequence, part, PlacementStorageType.File, null,
                        AudioPlacementBuilder.CreateTimeRange(sequence, part, PlacementStorageType.File, null)), placements, pending);
                }
            }
            if (placements.Count == 0)
                throw new InvalidOperationException("No audible native placements were selected for mixdown.");
            System.Diagnostics.Stopwatch elapsed = System.Diagnostics.Stopwatch.StartNew();
            while (pending.Count != 0)
            {
                DrainAudioPlacements(callbacks, pending);
                if (pending.Count == 0)
                    break;
                if (elapsed.Elapsed.TotalSeconds >= timeout)
                    throw new TimeoutException("Native mixer did not acknowledge file placements.");
                callbacks.Completed.Wait(10);
            }
            VEMixdownParam parameters = new()
            {
                UserKey = nint.Zero,
                Channels = channels,
                BitDepthIndex = (ushort)(bits == 16 ? 0 : 1),
                SampleRate = (uint)sampleRate
            };
            VEAudioEngineError result = VEAudioEngine.MixdownToFile(temporary, parameters, nint.Zero,
                callbacks.ProgressCallback, callbacks.CompletionCallback);
            if (result != VEAudioEngineError.Success)
                throw new InvalidOperationException("Native mixdown submission failed: " + result);
            while (!callbacks.Completed.Wait(20))
            {
                if (Volatile.Read(ref callbacks.Failure) is string failure)
                    throw new InvalidOperationException(failure);
                if (elapsed.Elapsed.TotalSeconds >= timeout)
                    throw new TimeoutException("Native mixdown timed out; progress=" + Volatile.Read(ref callbacks.Progress));
            }
            if (Volatile.Read(ref callbacks.Result) != (int)VEMixdownResult.Success)
                throw new InvalidOperationException("Native mixdown failed: " + (VEMixdownResult)callbacks.Result);
            StopNativeAudio();
            return PublishAudio(session, temporary, destination, AudioFlag(options, "overwrite"), "VAE.Manual+VEM");
        }
        finally
        {
            StopNativeAudio();
            foreach (VEAudioPlacement placement in placements)
                placement.Dispose();
            callbacks?.Completed.Dispose();
            if (File.Exists(temporary))
                File.Delete(temporary);
        }
    }

    private static void AddAudioPlacement(VEAudioPlacement? placement, List<VEAudioPlacement> placements, HashSet<int> pending)
    {
        if (placement is null || !placement.IsValid)
            throw new InvalidOperationException("Native file placement creation failed.");
        placements.Add(placement);
        int request = VEAudioEngine.GenerateRequestId();
        pending.Add(request);
        VEAudioEngineError result = VEAudioEngine.AddOrReplaceAudioPlacement(placement.BusNo, placement, request);
        if (result != VEAudioEngineError.Success)
            throw new InvalidOperationException("Native file placement submission failed: " + result);
    }

    private static VETimeRange FrozenTrackTimeRange(WIVSMSequence sequence, WIVSMMidiTrack track)
    {
        VETimeRange first = AudioPlacementBuilder.CreateTimeRangeFrozenTrack(sequence, track);
        double end = track.Parts.Select(part => part.EndSec).DefaultIfEmpty(first.End).Max();
        return new VETimeRange(first.Begin, Math.Max(first.End, end));
    }

    private static void DrainAudioPlacements(AudioMixCallbacks callbacks, HashSet<int> pending)
    {
        while (callbacks.Placements.TryDequeue(out var result))
        {
            pending.Remove(result.Request);
            if (result.Error != 0)
                throw new InvalidOperationException("Native file placement failed: " + (VEAudioEngineError)result.Error);
        }
        if (Volatile.Read(ref callbacks.Failure) is string failure)
            throw new InvalidOperationException(failure);
    }

    private static void SetAudioMixAutomation(WIVSMSequence sequence, bool includeMaster)
    {
        VEAudioEngine.BeginEditOutputGain();
        if (!includeMaster)
            VEAudioEngine.AddOutputGain(0, 1);
        else if (sequence.NumMasterVolumes == 0)
            VEAudioEngine.AddOutputGain(0, AudioGain(sequence.GetDefaultVolumeValue()));
        if (includeMaster)
            foreach (WIVSMMasterVolume volume in sequence.MasterVolumesEnumerator)
                VEAudioEngine.AddOutputGain(sequence.GetTimeFromTick(VSMAbsTick.Zero + volume.RelPosTick), AudioGain(volume.Value));
        VEAudioEngine.EndEditOutputGain();
        for (ulong index = 0; index < sequence.NumTrack; index++)
        {
            WIVSMTrack track = sequence.GetTrack(index)!;
            uint bus = (uint)index;
            if (track.Type is VSMTrackType.Midi or VSMTrackType.MidiAi && new WIVSMMidiTrack(track).IsFrozen)
            {
                // The owned frozen stem already includes track gain and pan.
                // Apply master processing only while replaying that stem.
                VEAudioEngine.BeginEditInputGain(bus);
                VEAudioEngine.AddInputGain(bus, 0, 1);
                VEAudioEngine.EndEditInputGain(bus);
                VEAudioEngine.BeginEditInputPan(bus);
                VEAudioEngine.AddInputPan(bus, 0, 0);
                VEAudioEngine.EndEditInputPan(bus);
                continue;
            }
            VEAudioEngine.BeginEditInputGain(bus);
            if (track.NumVolumes == 0)
                VEAudioEngine.AddInputGain(bus, 0, AudioGain(track.GetDefaultVolumeValue()));
            foreach (WIVSMTrackVolume volume in track.VolumesEnumerator)
                VEAudioEngine.AddInputGain(bus, sequence.GetTimeFromTick(VSMAbsTick.Zero + volume.RelPosTick), AudioGain(volume.Value));
            VEAudioEngine.EndEditInputGain(bus);
            VEAudioEngine.BeginEditInputPan(bus);
            if (track.NumPanpots == 0)
                VEAudioEngine.AddInputPan(bus, 0, AudioPan(track, track.GetDefaultPanpotValue()));
            foreach (WIVSMPanpot pan in track.PanpotsEnumerator)
                VEAudioEngine.AddInputPan(bus, sequence.GetTimeFromTick(VSMAbsTick.Zero + pan.RelPosTick), AudioPan(track, pan.Value));
            VEAudioEngine.EndEditInputPan(bus);
        }
    }

    private static float AudioGain(int volume) => (float)Math.Pow(10, volume / 200.0);

    private static float AudioPan(WIVSMTrack track, int pan) =>
        (pan - track.GetMinPanpotValue()) * 2f / (track.GetMaxPanpotValue() - track.GetMinPanpotValue()) - 1f;

    private void StopNativeAudio()
    {
        if (!audioEngineInitialized)
            return;
        VEAudioEngine.CancelMixdown();
        VEAudioEngine.Terminate();
        audioEngineInitialized = false;
        activeAudioMix = null;
    }

    private WEffectManager EnsureAudioEffects()
    {
        CheckThread();
        if (transport is not null)
            throw new InvalidOperationException("Release the prepared transport before using the shared native effect manager.");
        if (audioEffects is not null)
            return audioEffects;
        if (audioEffectsFailure is not null)
            throw new InvalidOperationException("Native effect initialization previously failed.", audioEffectsFailure);
        try
        {
            string directory = Path.Combine(Path.GetDirectoryName(typeof(WIVSMSequence).Assembly.Location)!, "AudioEffects") + Path.DirectorySeparatorChar;
            PathGuard.NoLinks(directory);
            if (!System.IO.Directory.Exists(directory))
                throw new DirectoryNotFoundException("Installed native AudioEffects directory is missing: " + directory);
            audioEffects = new WEffectManager(directory);
            return audioEffects;
        }
        catch (Exception error)
        {
            audioEffectsFailure = error;
            throw;
        }
    }

    private WEffectManager SyncAudioEffects(EngineSession session, bool includeMaster = true)
    {
        WEffectManager effects = EnsureAudioEffects();
        effects.ResetAll();
        if (includeMaster && !effects.SynchronizeAudioEffect(session.Sequence))
            throw new InvalidOperationException("Native master effect synchronization failed.");
        if (!includeMaster && effects.AddMasterBlock((nint)session.Sequence) is null)
            throw new InvalidOperationException("Native dry master block initialization failed.");
        foreach (WIVSMTrack track in session.Sequence.Tracks)
        {
            if (!effects.SynchronizeAudioEffect(track))
                throw new InvalidOperationException("Native track effect synchronization failed: " + track.Name);
#if !VOCALOID7
            foreach (WIVSMPart part in track.Parts)
                if (!effects.SynchronizeAudioEffect(part))
                    throw new InvalidOperationException("Native part effect synchronization failed: " + part.Name);
#endif
        }
        return effects;
    }

    private static (object Owner, WIVSMEffectManager Manager) AudioEffectScope(EngineSession session, JsonElement options)
    {
        string scope = AudioText(options, "scope", "master");
#if VOCALOID7
        if (scope == "part")
            throw new NotSupportedException("VOCALOID7 does not support part audio effects. Explicit scope='track' affects every part on the track.");
#endif
        object owner = session.Sequence;
        WIVSMEffectManager? effects = session.Sequence.EffectManager;
        if (scope is "track" or "part")
        {
            WIVSMTrack track = session.Sequence.GetTrack(options.GetProperty("track_index").GetUInt64())
                ?? throw new ArgumentOutOfRangeException("track_index");
            owner = track;
            effects = track.EffectManager;
            if (scope == "part")
            {
#if !VOCALOID7
                WIVSMPart part = track.GetPart(options.GetProperty("part_index").GetUInt64())
                    ?? throw new ArgumentOutOfRangeException("part_index");
                owner = part;
                effects = part.EffectManager;
#endif
            }
        }
        else if (scope != "master")
            throw new ArgumentException("Effect scope must be master, track, or part.");
        return (owner, effects ?? throw new InvalidOperationException("Native object has no audio effect manager."));
    }

    private object AudioEffects(EngineSession session, JsonElement options)
    {
        if (AudioText(options, "scope", "catalog") == "catalog")
        {
            WEffectManager catalog = EnsureAudioEffects();
            List<string> identifiers = catalog.CollectedEffectGUID();
            if (identifiers.Count > 4096)
                throw new InvalidDataException("Native effect catalog exceeds 4096 entries.");
            if (!options.TryGetProperty("effect_id", out JsonElement requested))
                return new
                {
                    session_id = session.Id,
                    native = true,
                    scope = "catalog",
                    effects = identifiers.Select(identifier => new
                    {
                        effect_id = identifier,
                        name = catalog.CollectedEffectName(identifier),
                        module = catalog.CollectedEffectModuleName(identifier),
                        parameter_count = catalog.CollectedEffectNumParameter(identifier)
                    }).ToArray()
                };
            string identifier = requested.GetString() ?? throw new ArgumentException("effect_id cannot be null.");
            if (!identifiers.Contains(identifier, StringComparer.OrdinalIgnoreCase))
                throw new ArgumentException("effect_id is not an installed bundled effect.");
            identifier = identifiers.First(value => string.Equals(value, identifier, StringComparison.OrdinalIgnoreCase));
            catalog.ResetAll();
            try
            {
                WEffectBlock block = catalog.AddMasterBlock((nint)1)
                    ?? throw new InvalidOperationException("Native effect probe block creation failed.");
                WEffectController controller = block.AddLoadEffect(identifier)
                    ?? throw new InvalidOperationException("Native effect load failed: " + identifier);
                return DescribeEffectController(controller);
            }
            finally
            {
                catalog.ResetAll();
            }
        }
        WEffectManager current = SyncAudioEffects(session);
        var scope = AudioEffectScope(session, options);
        WEffectBlock live = current.EffectBlockOf(scope.Owner)
            ?? throw new InvalidOperationException("Native effect block is absent.");
        return new
        {
            session_id = session.Id,
            native = true,
            scope = AudioText(options, "scope"),
            effects = scope.Manager.AudioEffects.Select((effect, index) => new
            {
                slot = index,
                effect_id = effect.Id,
                bypass = effect.IsBypassed,
                parameters = effect.GetEffectValues.Select(value => new
                {
                    name = value.Name,
                    type = value.Type.ToString(),
                    value = value.Type switch
                    {
                        VSMEffectValueType.Float => (object)value.RawFloat,
                        VSMEffectValueType.Int => value.RawInt,
                        _ => value.RawString
                    }
                }).ToArray(),
                metadata = live.EffectController(effect.Id) is WEffectController controller
                    ? DescribeEffectController(controller, live) : null
            }).ToArray()
        };
    }

    private static int AudioEffectModeIndex(string effectId) =>
        effectId.Equals(WEffectController.GetGuid(WEffectController.Type.CHORUS), StringComparison.OrdinalIgnoreCase) ||
        effectId.Equals(WEffectController.GetGuid(WEffectController.Type.PHASER), StringComparison.OrdinalIgnoreCase) ? 18 :
        effectId.Equals(WEffectController.GetGuid(WEffectController.Type.REVERB), StringComparison.OrdinalIgnoreCase) ? 11 : -1;

    private static object DescribeEffectController(WEffectController controller, WEffectBlock? block = null)
    {
        if (controller.NumParameter > 4096 || controller.NumPreset > 4096)
            throw new InvalidDataException("Native effect metadata exceeds the 4096-entry limit.");
#if !VOCALOID7
        if (block is WPartEffectBlock)
        {
            int modeIndex = AudioEffectModeIndex(controller.EffectGUID);
            if (modeIndex >= 0 && controller.IsValidParameter((ulong)modeIndex))
            {
                string modeName = controller.ParameterName((ulong)modeIndex);
                float mode = block.GetParameterValue(controller.EffectGUID, modeName);
                if (mode != float.MinValue && (!float.IsFinite(mode) || !controller.SetParamNormalized((ulong)modeIndex, mode)))
                    throw new InvalidDataException("Native part effect mode could not be read: " + modeName);
            }
        }
#endif
        List<object> parameters = [];
        for (ulong index = 0; index < controller.NumParameter; index++)
        {
            if (!controller.IsValidParameter(index))
                continue;
            bool hasRange = controller.PlainParamRange(index, out int minimum, out int maximum);
            string name = controller.ParameterName(index);
            float normalized = controller.ParamNormalized(index);
#if !VOCALOID7
            if (block is WPartEffectBlock)
            {
                float stored = block.GetParameterValue(controller.EffectGUID, name);
                if (stored != float.MinValue) normalized = stored;
            }
#endif
            float defaultValue = controller.DefaultParamNormalized(index);
            if (!float.IsFinite(normalized) || !float.IsFinite(defaultValue))
                throw new InvalidDataException("Native effect returned a non-finite parameter value.");
            controller.ParamNormalizedToString(index, normalized, out string display);
            parameters.Add(new
            {
                index,
                name,
                label = controller.ParameterLabel(index),
                normalized,
                default_normalized = defaultValue,
                plain_min = hasRange ? (int?)minimum : null,
                plain_max = hasRange ? (int?)maximum : null,
                display
            });
        }
        List<string?> presets = [];
        for (ulong index = 0; index < controller.NumPreset; index++)
            presets.Add(controller.PresetName(index));
        return new { effect_id = controller.EffectGUID, name = controller.EffectName, parameters, presets };
    }

    private object SetAudioEffect(EngineSession session, JsonElement options, bool recordHistory = true)
    {
        if (recordHistory)
            return ScoreMutate(session, "audio.set_effect", () => SetAudioEffectCore(session, options));
        object result = SetAudioEffectCore(session, options);
        CommitAudio(session);
        return result;
    }

    private object SetAudioEffectCore(EngineSession session, JsonElement options)
    {
        var scope = AudioEffectScope(session, options);
        string action = AudioText(options, "action", "set");
        ulong slot = checked((ulong)AudioInteger(options, "slot", action == "add" ? (long)scope.Manager.NumAudioEffect : 0, 0, 4096));
        WEffectManager current = SyncAudioEffects(session);
        WEffectBlock block = current.EffectBlockOf(scope.Owner)
            ?? throw new InvalidOperationException("Native effect block is absent.");
        if (action is "remove" or "move")
        {
            WIVSMAudioEffect effect = scope.Manager.GetAudioEffect(slot)
                ?? throw new ArgumentOutOfRangeException("slot");
            ulong target = action == "move" ? checked((ulong)AudioInteger(options, "target_slot", 0, 0, (long)scope.Manager.NumAudioEffect - 1)) : 0;
            bool changed = action == "remove" ? scope.Manager.RemoveAudioEffect(effect) : scope.Manager.MoveAudioEffect(target, effect);
            if (!changed)
                throw new InvalidOperationException("Native effect " + action + " failed: " + scope.Manager.LastError);
        }
        else if (action is "add" or "set")
        {
            WIVSMAudioEffect effect;
            WEffectController controller;
            if (action == "add")
            {
                string identifier = AudioText(options, "effect_id");
                string? installed = current.CollectedEffectGUID().FirstOrDefault(value => string.Equals(value, identifier, StringComparison.OrdinalIgnoreCase));
                if (installed is null || WEffectController.IsVirtualEffect(installed))
                    throw new ArgumentException("effect_id must identify an installed non-virtual audio effect.");
                if (scope.Manager.AudioEffects.Any(value => value.Id == installed))
                    throw new ArgumentException("The native chain already contains this effect GUID.");
                if (slot > scope.Manager.NumAudioEffect)
                    throw new ArgumentOutOfRangeException("slot");
                controller = block.InsertLoadEffect(installed, slot)
                    ?? throw new InvalidOperationException("Native effect loading failed: " + installed);
                ValidateEffectParameters(controller, options);
                effect = scope.Manager.InsertAudioEffect(slot, installed)
                    ?? throw new InvalidOperationException("Native effect insertion failed: " + scope.Manager.LastError);
            }
            else
            {
                effect = scope.Manager.GetAudioEffect(slot) ?? throw new ArgumentOutOfRangeException("slot");
                controller = block.EffectController(effect.Id)
                    ?? throw new InvalidOperationException("Native effect controller is absent: " + effect.Id);
                ValidateEffectParameters(controller, options);
                for (ulong index = 0; index < controller.NumParameter; index++)
                {
                    if (!controller.IsValidParameter(index))
                        continue;
                    float existing = block.GetParameterValue(effect.Id, controller.ParameterName(index));
                    if (existing != float.MinValue && float.IsFinite(existing) && !controller.SetParamNormalized(index, existing))
                        throw new InvalidOperationException("Native effect parameter state could not be restored.");
                }
            }
            if (options.TryGetProperty("preset", out JsonElement preset) && !controller.ChangePreset(preset.GetString() ?? ""))
                throw new InvalidOperationException("Native effect preset was not found.");
            if (options.TryGetProperty("parameters", out JsonElement parameters))
                foreach (JsonProperty parameter in parameters.EnumerateObject())
                {
                    int index = controller.ToParameterIndex(parameter.Name);
                    if (!controller.SetParamNormalized((ulong)index, parameter.Value.GetSingle()))
                        throw new InvalidOperationException("Native effect parameter update failed: " + parameter.Name);
                }
            for (ulong index = 0; index < controller.NumParameter; index++)
            {
                if (!controller.IsValidParameter(index))
                    continue;
                string name = controller.ParameterName(index);
                float value = controller.ParamNormalized(index);
                if (!float.IsFinite(value) || !block.SetParameterValue(effect.Id, name, value) || !effect.ReplaceValueFloat(name, value))
                    throw new InvalidOperationException("Native effect parameter persistence failed: " + name);
            }
            if (options.TryGetProperty("bypass", out JsonElement bypass) && !effect.SetBypass(bypass.GetBoolean()))
                throw new InvalidOperationException("Native effect bypass update failed: " + effect.LastError);
        }
        else
            throw new ArgumentException("Effect action must be add, set, remove, or move.");
        return new { session_id = session.Id, native = true, action, scope = AudioText(options, "scope", "master"), slot };
    }

    private static void ValidateEffectParameters(WEffectController controller, JsonElement options)
    {
        if (controller.NumParameter > 4096)
            throw new InvalidDataException("Native effect has more than 4096 parameters.");
        if (!options.TryGetProperty("parameters", out JsonElement parameters))
            return;
        if (parameters.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("parameters must map native parameter names to normalized numeric values.");
        foreach (JsonProperty parameter in parameters.EnumerateObject())
        {
            int index = controller.ToParameterIndex(parameter.Name);
            float value = parameter.Value.GetSingle();
            if (index < 0 || !controller.IsValidParameter((ulong)index))
                throw new ArgumentException("Unknown native effect parameter: " + parameter.Name);
            if (!float.IsFinite(value) || value < 0 || value > 1)
                throw new ArgumentOutOfRangeException(parameter.Name, "Normalized effect values must be in 0..1.");
        }
    }

    private object ImportAudio(EngineSession session, JsonElement options, Action<WIVSMAudioPart>? configure = null, string operation = "part.create")
    {
        string source = AudioInputPath(options);
        var wave = InspectWave(source);
        long position = AudioInteger(options, "position_tick", 0, 0, int.MaxValue);
        VSMAbsTick start = new(position);
        long duration = (session.Sequence.GetTickFromTime(start, wave.Frames / (double)wave.SampleRate) - start).Value;
        if (duration <= 0 || duration > int.MaxValue)
            throw new InvalidDataException("The WAV duration is outside the native audio part tick range.");
        string name = AudioText(options, "name", Path.GetFileNameWithoutExtension(source));
        ulong trackIndex = options.TryGetProperty("track_index", out JsonElement requested)
            ? requested.GetUInt64() : session.Sequence.NumTrack;
        bool createTrack = !options.TryGetProperty("track_index", out _);
        return ScoreMutate(session, operation, () =>
        {
            WIVSMAudioTrack track;
            if (createTrack)
            {
                WIVSMTrack inserted = session.Sequence.InsertTrackEx(trackIndex, VSMTrackType.Audio, name)
                    ?? throw new InvalidOperationException("Native audio track insertion failed: " + session.Sequence.LastError);
                track = new WIVSMAudioTrack(inserted);
            }
            else
                track = AudioTrack(session, trackIndex);
            WIVSMAudioPart part = track.InsertPart(new VSMAbsTick(position), name)
                ?? throw new InvalidOperationException("Native audio part insertion failed: " + track.LastError);
            if (!part.SetRegion(new VSMAudioPartRegion(0, (int)duration)))
                throw new InvalidOperationException("Native audio region initialization failed: " + part.LastError);
            if (!part.SetOriginalWaveFile(source, Path.GetFileName(source)))
                throw new InvalidOperationException("Native audio import failed: " + part.LastError);
            configure?.Invoke(part);
            return DescribeAudioPart(session, trackIndex, track.IndexOf(part), part);
        });
    }

    private object EditAudio(EngineSession session, JsonElement options)
    {
        ulong trackIndex = options.GetProperty("track_index").GetUInt64();
        ulong partIndex = options.GetProperty("part_index").GetUInt64();
        WIVSMAudioTrack track = AudioTrack(session, trackIndex);
        WIVSMAudioPart part = AudioPart(track, partIndex);
        VSMAudioPartRegion region = part.Region;
        int begin = checked((int)AudioInteger(options, "begin_tick", region.TickBegin, 0, int.MaxValue));
        int end = checked((int)AudioInteger(options, "end_tick", region.TickEnd, 1, int.MaxValue));
        if (end <= begin)
            throw new ArgumentException("end_tick must be greater than begin_tick.");
        long position = AudioInteger(options, "position_tick", part.AbsPosTick.Value, 0, int.MaxValue);
        string? name = options.TryGetProperty("name", out JsonElement nameValue) ? nameValue.GetString() ?? "" : null;
        return ScoreMutate(session, "part.update", () =>
        {
            if (name is not null && !part.SetName(name))
                throw new InvalidOperationException("Native audio name update failed: " + part.LastError);
            if (!part.SetRegion(new VSMAudioPartRegion(begin, end)))
                throw new InvalidOperationException("Native audio region update failed: " + part.LastError);
            if (position != part.AbsPosTick.Value && !track.MovePart(new VSMAbsTick(position), track, part))
                throw new InvalidOperationException("Native audio move failed: " + track.LastError);
            return DescribeAudioPart(session, trackIndex, track.IndexOf(part), part);
        });
    }

    private object ExportAudio(EngineSession session, JsonElement options)
    {
        WIVSMAudioPart part = AudioPart(AudioTrack(session, options.GetProperty("track_index").GetUInt64()),
            options.GetProperty("part_index").GetUInt64());
        string source = AudioFlag(options, "original") ? part.GetOriginalWaveFilePath() : part.GetWaveFilePath();
        if (string.IsNullOrEmpty(source))
            throw new InvalidOperationException("The native audio part has no stored WAV asset.");
        PathGuard.NoLinks(source);
        string destination = AudioDestination(session, options, source);
        string temporary = AudioTemporary(session);
        try
        {
            File.Copy(source, temporary, false);
            return PublishAudio(session, temporary, destination, AudioFlag(options, "overwrite"), "native_asset_copy");
        }
        finally
        {
            if (File.Exists(temporary))
                File.Delete(temporary);
        }
    }

    private object ProcessAudio(EngineSession session, JsonElement options)
    {
        string source = AudioInputPath(options);
        var sourceWave = InspectWave(source);
        string action = AudioText(options, "action");
        string destination = AudioDestination(session, options, source);
        string temporary = AudioTemporary(session);
        double ratio = AudioNumber(options, "ratio", 1);
        double cents = AudioNumber(options, "pitch_cents", 0);
        if (ratio < TimeStretchRenderer.MinBpmMag || ratio > TimeStretchRenderer.MaxBpmMag)
            throw new ArgumentOutOfRangeException("ratio", "Ratio exceeds the installed native renderer range.");
        if (cents < TimeStretchRenderer.MinPitchShift || cents > TimeStretchRenderer.MaxPitchShift)
            throw new ArgumentOutOfRangeException("pitch_cents", "Pitch exceeds the installed native renderer range.");
        try
        {
            WORError result;
            switch (action)
            {
#if VOCALOID7
                case "reverse":
                    var metadata = ReverseWaveFrames(source, temporary, sourceWave.Channels, sourceWave.Bits, sourceWave.Frames);
                    var reversed = PublishAudio(session, temporary, destination, AudioFlag(options, "overwrite"), "bridge.pcm_frame_reverse", false);
                    reversed["sampler_loops_reversed"] = metadata.LoopsReversed;
                    reversed["sampler_loops_unchanged"] = metadata.LoopsUnchanged;
                    reversed["sampler_chunks_unchanged"] = metadata.SamplerChunksUnchanged;
                    reversed["cue_points_reversed"] = metadata.CuePointsReversed;
                    reversed["cue_points_unchanged"] = metadata.CuePointsUnchanged;
                    reversed["cue_chunks_unchanged"] = metadata.CueChunksUnchanged;
                    reversed["metadata_warning"] = "Some cue and other time references are not reversed; fractional, unsupported, or sampler-specific loops may remain unchanged.";
                    return reversed;
#else
                case "reverse":
                    using (ReverseRenderer renderer = new())
                        result = renderer.RenderAudioFile(source, temporary, 0);
                    break;
#endif
                case "normalize":
                    using (NormalizeRenderer renderer = new())
                        result = renderer.RenderAudioFile(source, temporary);
                    break;
                case "time_stretch":
                case "pitch_shift":
                    using (TimeStretchRenderer renderer = new())
                        result = renderer.RenderAudioFile(source, temporary, action == "time_stretch" ? (float)ratio : 1f, (float)cents);
                    break;
#if VOCALOID7
                case "voice_change":
                    throw new NotSupportedException("VOCALOID7 removed the native VOCALO CHANGER renderer.");
#else
                case "voice_change":
                    EnsureVoiceServices();
                    string voiceId = AudioText(options, "voice_id");
                    VoiceBank voice = EnsureDatabase().GetVoiceBankByCompID(voiceId, VDMVoiceBankType.Dnn)
                        ?? throw new ArgumentException("Installed voice_id was not found.");
                    if (!voice.IsAvailableForVoiceChanger || !voice.IsSynthesizableVersion)
                        throw new InvalidOperationException("Voice bank is not available for native VOCALO CHANGER: " + voiceId);
                    string model = Path.Combine(voice.DirectoryPath, voice.GroupName + ".vtb2");
                    PathGuard.NoLinks(model);
                    if (!File.Exists(model))
                        throw new FileNotFoundException("Native VOCALO CHANGER model is missing.", model);
                    using (VoiceChangeRenderer renderer = new())
                        result = renderer.RenderAudioFile(source, temporary, model, voice.NPIndex, (float)cents);
                    break;
#endif
                default:
                    throw new ArgumentException("Unknown native audio action: " + action);
            }
            if (result != WORError.None)
                throw new InvalidOperationException("Native " + action + " failed: " + result);
            return PublishAudio(session, temporary, destination, AudioFlag(options, "overwrite"), "WOR." + action);
        }
        finally
        {
            if (File.Exists(temporary))
                File.Delete(temporary);
        }
    }

#if VOCALOID7
    private static bool ReadCueAssociatedList(BinaryReader reader, long offset, Dictionary<uint, uint?> regions)
    {
        Stream input = reader.BaseStream;
        input.Position = offset + 4;
        uint size = reader.ReadUInt32();
        if (size < 4 || reader.ReadUInt32() != 0x6c746461)
            return false;
        long end = offset + 8L + size;
        while (input.Position < end)
        {
            if (end - input.Position < 8)
                return false;
            uint id = reader.ReadUInt32();
            uint length = reader.ReadUInt32();
            long payloadEnd = input.Position + length;
            long next = payloadEnd + (length & 1);
            if (next > end)
                return false;
            if (id is 0x6c62616c or 0x65746f6e)
            {
                if (length < 5)
                    return false;
                input.Position = payloadEnd - 1;
                if (reader.ReadByte() != 0)
                    return false;
            }
            else if (id == 0x7478746c)
            {
                if (length < 20)
                    return false;
                uint pointId = reader.ReadUInt32();
                uint regionLength = reader.ReadUInt32();
                if (regions.TryGetValue(pointId, out uint? previous))
                {
                    if (previous != regionLength)
                        regions[pointId] = null;
                }
                else
                {
                    if (regions.Count >= 65536)
                        return false;
                    regions.Add(pointId, regionLength == 0 ? null : regionLength);
                }
                if (length > 20)
                {
                    input.Position = payloadEnd - 1;
                    if (reader.ReadByte() != 0)
                        return false;
                }
            }
            else
                return false;
            input.Position = next;
        }
        return input.Position == end;
    }

    private static (long LoopsReversed, long LoopsUnchanged, long SamplerChunksUnchanged,
        long CuePointsReversed, long CuePointsUnchanged, long CueChunksUnchanged) ReverseWaveFrames(
        string source, string destination, ushort channels, ushort bits, long expectedFrames)
    {
        int frameBytes = checked(channels * ((bits + 7) / 8));
        using FileStream input = new(source, FileMode.Open, FileAccess.Read, FileShare.Read);
        using BinaryReader reader = new(input, System.Text.Encoding.UTF8, true);
        if (reader.ReadUInt32() != 0x46464952)
            throw new InvalidDataException("Audio input is not RIFF WAV.");
        long end = reader.ReadUInt32() + 8L;
        if (end > input.Length || end < 44 || reader.ReadUInt32() != 0x45564157)
            throw new InvalidDataException("Audio input has an invalid RIFF boundary.");
        List<(long Offset, long Length)> chunks = [];
        List<(uint Id, long Offset, long Length)> layout = [];
        bool formatSeen = false;
        long dataBytes = 0;
        while (input.Position + 8 <= end)
        {
            long headerOffset = input.Position;
            uint id = reader.ReadUInt32();
            uint size = reader.ReadUInt32();
            long offset = input.Position;
            long payloadEnd = offset + size;
            long next = payloadEnd + (size & 1);
            if (payloadEnd > end || (next > end && (id != 0x61746164 || payloadEnd != end)))
                throw new InvalidDataException("Audio input contains a truncated WAV chunk.");
            if (id == 0x20746d66)
            {
                if (formatSeen || size < 16)
                    throw new InvalidDataException("Audio input has an invalid or duplicate WAV format chunk.");
                formatSeen = true;
                ushort format = reader.ReadUInt16();
                ushort actualChannels = reader.ReadUInt16();
                _ = reader.ReadUInt32();
                _ = reader.ReadUInt32();
                ushort alignment = reader.ReadUInt16();
                ushort actualBits = reader.ReadUInt16();
                if (actualChannels != channels || actualBits != bits || alignment != frameBytes)
                    throw new InvalidDataException("Audio input WAV format changed during inspection.");
                if (format == 0xfffe)
                {
                    if (size < 40)
                        throw new InvalidDataException("Audio input has a truncated extensible WAV format.");
                    ushort extraBytes = reader.ReadUInt16();
                    if (extraBytes < 22 || extraBytes > size - 18)
                        throw new InvalidDataException("Audio input has a truncated extensible WAV format.");
                    _ = reader.ReadUInt16();
                    _ = reader.ReadUInt32();
                    Guid subtype = new(reader.ReadBytes(16));
                    if (subtype != new Guid("00000001-0000-0010-8000-00aa00389b71") &&
                        subtype != new Guid("00000003-0000-0010-8000-00aa00389b71"))
                        throw new NotSupportedException("WAV reverse requires PCM or IEEE float audio.");
                }
                else if (format is not (1 or 3))
                    throw new NotSupportedException("WAV reverse requires PCM or IEEE float audio.");
            }
            else if (id == 0x61746164)
            {
                if (!formatSeen)
                    throw new InvalidDataException("WAV format must precede audio data.");
                if (size % frameBytes != 0)
                    throw new InvalidDataException("Each WAV data chunk must contain complete audio frames.");
                chunks.Add((offset, size));
                dataBytes += size;
            }
            layout.Add((id, headerOffset, Math.Min(next, end) - headerOffset));
            input.Position = Math.Min(next, end);
        }
        if (!formatSeen || dataBytes / frameBytes != expectedFrames)
            throw new InvalidDataException("Audio input WAV frames changed during inspection.");
        long unparsedOffset = input.Position;
        Dictionary<uint, uint?> regions = [];
        bool cueContextUncertain = chunks.Count != 1 || layout.Any(entry =>
            entry.Id is 0x6c706d73 or 0x74736c70 ||
            (entry.Id == 0x5453494c && !ReadCueAssociatedList(reader, entry.Offset, regions)));
        Dictionary<uint, bool> cueIdentities = [];
        if (!cueContextUncertain)
        {
            foreach (var entry in layout.Where(entry => entry.Id == 0x20657563))
            {
                input.Position = entry.Offset + 4;
                uint size = reader.ReadUInt32();
                if (size < 4)
                {
                    cueContextUncertain = true;
                    break;
                }
                uint count = reader.ReadUInt32();
                if (4L + 24L * count != size)
                {
                    cueContextUncertain = true;
                    break;
                }
                for (long index = 0; index < count; index++)
                {
                    input.Position = entry.Offset + 12 + 24 * index;
                    uint pointId = reader.ReadUInt32();
                    if (cueIdentities.ContainsKey(pointId))
                        cueIdentities[pointId] = false;
                    else if (cueIdentities.Count < 65536)
                        cueIdentities.Add(pointId, true);
                    else
                    {
                        cueContextUncertain = true;
                        break;
                    }
                }
                if (cueContextUncertain)
                    break;
            }
        }
        byte[] buffer = new byte[Math.Max(frameBytes, (65536 / frameBytes) * frameBytes)];
        using FileStream output = new(destination, FileMode.CreateNew, FileAccess.Write, FileShare.None);
        using BinaryWriter writer = new(output, System.Text.Encoding.UTF8, true);
        void CopyRange(long offset, long length)
        {
            input.Position = offset;
            while (length > 0)
            {
                int count = checked((int)Math.Min(buffer.Length, length));
                input.ReadExactly(buffer.AsSpan(0, count));
                output.Write(buffer.AsSpan(0, count));
                length -= count;
            }
        }
        writer.Write(0x46464952u);
        writer.Write(0u);
        writer.Write(0x45564157u);
        long audioOffset = -1;
        long samplerLoopsReversed = 0;
        long samplerLoopsUnchanged = 0;
        long samplerChunksUnchanged = 0;
        long cuePointsReversed = 0;
        long cuePointsUnchanged = 0;
        long cueChunksUnchanged = 0;
        foreach (var entry in layout)
        {
            if (entry.Id != 0x61746164)
            {
                long outputChunkOffset = output.Position;
                CopyRange(entry.Offset, entry.Length);
                if (entry.Id == 0x6c706d73)
                {
                    long outputChunkEnd = output.Position;
                    input.Position = entry.Offset + 4;
                    uint size = reader.ReadUInt32();
                    if (size < 36)
                        samplerChunksUnchanged++;
                    else
                    {
                        input.Position = entry.Offset + 8 + 28;
                        uint loopCount = reader.ReadUInt32();
                        uint extraSize = reader.ReadUInt32();
                        if (extraSize != 0 || 36L + 24L * loopCount != size)
                        {
                            samplerChunksUnchanged++;
                            if (36L + 24L * loopCount + extraSize == size)
                                samplerLoopsUnchanged += loopCount;
                        }
                        else
                        {
                            for (long loopIndex = 0; loopIndex < loopCount; loopIndex++)
                            {
                                long loopOffset = 8 + 36 + 24 * loopIndex;
                                input.Position = entry.Offset + loopOffset + 4;
                                uint type = reader.ReadUInt32();
                                uint start = reader.ReadUInt32();
                                uint endSample = reader.ReadUInt32();
                                uint fraction = reader.ReadUInt32();
                                if (type > 2 || fraction != 0 || start > endSample || endSample >= expectedFrames)
                                {
                                    samplerLoopsUnchanged++;
                                    continue;
                                }
                                output.Position = outputChunkOffset + loopOffset + 8;
                                writer.Write(checked((uint)(expectedFrames - 1 - endSample)));
                                writer.Write(checked((uint)(expectedFrames - 1 - start)));
                                samplerLoopsReversed++;
                            }
                        }
                    }
                    output.Position = outputChunkEnd;
                }
                else if (entry.Id == 0x20657563)
                {
                    long outputChunkEnd = output.Position;
                    input.Position = entry.Offset + 4;
                    uint size = reader.ReadUInt32();
                    if (size < 4)
                        cueChunksUnchanged++;
                    else
                    {
                        uint pointCount = reader.ReadUInt32();
                        if (4L + 24L * pointCount != size)
                            cueChunksUnchanged++;
                        else if (cueContextUncertain)
                        {
                            cueChunksUnchanged++;
                            cuePointsUnchanged += pointCount;
                        }
                        else
                        {
                            for (long pointIndex = 0; pointIndex < pointCount; pointIndex++)
                            {
                                long pointOffset = 8 + 4 + 24 * pointIndex;
                                input.Position = entry.Offset + pointOffset;
                                uint pointId = reader.ReadUInt32();
                                uint position = reader.ReadUInt32();
                                uint chunkId = reader.ReadUInt32();
                                uint chunkStart = reader.ReadUInt32();
                                uint blockStart = reader.ReadUInt32();
                                uint sampleOffset = reader.ReadUInt32();
                                if (!cueIdentities[pointId] || chunkId != 0x61746164 || chunkStart != 0 || blockStart != 0 ||
                                    position != sampleOffset || sampleOffset >= expectedFrames)
                                {
                                    cuePointsUnchanged++;
                                    continue;
                                }
                                long reversedSample = expectedFrames - 1 - sampleOffset;
                                if (regions.TryGetValue(pointId, out uint? regionLength))
                                {
                                    if (!regionLength.HasValue || (long)sampleOffset + regionLength.Value > expectedFrames)
                                    {
                                        cuePointsUnchanged++;
                                        continue;
                                    }
                                    reversedSample = expectedFrames - sampleOffset - regionLength.Value;
                                }
                                uint reversedPosition = checked((uint)reversedSample);
                                output.Position = outputChunkOffset + pointOffset + 4;
                                writer.Write(reversedPosition);
                                output.Position = outputChunkOffset + pointOffset + 20;
                                writer.Write(reversedPosition);
                                cuePointsReversed++;
                            }
                        }
                    }
                    output.Position = outputChunkEnd;
                }
                continue;
            }
            if (audioOffset >= 0)
                continue;
            writer.Write(0x61746164u);
            writer.Write(checked((uint)dataBytes));
            audioOffset = output.Position;
            output.Position += dataBytes;
            if ((dataBytes & 1) != 0)
                writer.Write((byte)0);
            if (output.Length < output.Position)
                output.SetLength(output.Position);
        }
        CopyRange(unparsedOffset, end - unparsedOffset);
        long outputEnd = output.Position;
        if (outputEnd - 8 > uint.MaxValue)
            throw new InvalidDataException("Reversed WAV exceeds the RIFF size limit.");
        output.Position = 4;
        writer.Write((uint)(outputEnd - 8));
        output.Position = outputEnd;
        CopyRange(end, input.Length - end);
        output.Position = audioOffset;
        for (int sourceIndex = chunks.Count - 1; sourceIndex >= 0; sourceIndex--)
        {
            var chunk = chunks[sourceIndex];
            long remaining = chunk.Length;
            while (remaining > 0)
            {
                int count = checked((int)Math.Min(buffer.Length, remaining));
                input.Position = chunk.Offset + remaining - count;
                input.ReadExactly(buffer.AsSpan(0, count));
                for (int left = 0, right = count - frameBytes; left < right; left += frameBytes, right -= frameBytes)
                    for (int index = 0; index < frameBytes; index++)
                        (buffer[left + index], buffer[right + index]) = (buffer[right + index], buffer[left + index]);
                output.Write(buffer.AsSpan(0, count));
                remaining -= count;
            }
        }
        return (samplerLoopsReversed, samplerLoopsUnchanged, samplerChunksUnchanged,
            cuePointsReversed, cuePointsUnchanged, cueChunksUnchanged);
    }
#endif

    private string AudioDestination(EngineSession session, JsonElement options, string? source = null)
    {
        string destination = PrepareOutput(session, AudioText(options, "output_name"), ".wav", AudioFlag(options, "overwrite"));
        if (source is not null && string.Equals(Path.GetFullPath(source), destination, StringComparison.OrdinalIgnoreCase))
            throw new IOException("An audio operation cannot overwrite its source input.");
        return destination;
    }

    private string AudioTemporary(EngineSession session) =>
        PrepareOutput(session, ".audio-" + Guid.NewGuid().ToString("N") + ".wav", ".wav", false);

    private static Dictionary<string, object> PublishAudio(EngineSession session, string temporary, string destination, bool overwrite, string backend, bool native = true)
    {
        PathGuard.NoLinks(temporary);
        var wave = InspectWave(temporary);
        PathGuard.NoLinks(destination);
        File.Move(temporary, destination, overwrite);
        return new Dictionary<string, object>
        {
            ["session_id"] = session.Id,
            ["path"] = destination,
            ["native"] = native,
            ["backend"] = backend,
            ["bytes"] = wave.Bytes,
            ["channels"] = wave.Channels,
            ["sample_rate"] = wave.SampleRate,
            ["bits_per_sample"] = wave.Bits,
            ["frames"] = wave.Frames,
            ["duration_seconds"] = (double)wave.Frames / wave.SampleRate
        };
    }

    private static WIVSMAudioTrack AudioTrack(EngineSession session, ulong trackIndex)
    {
        WIVSMTrack track = session.Sequence.GetTrack(trackIndex)
            ?? throw new ArgumentOutOfRangeException("track_index", "Native track does not exist.");
        if (track.Type != VSMTrackType.Audio)
            throw new ArgumentException("track_index must identify an Audio track.");
        return new WIVSMAudioTrack(track);
    }

    private static WIVSMAudioPart AudioPart(WIVSMAudioTrack track, ulong partIndex) =>
        track.GetPart(partIndex) ?? throw new ArgumentOutOfRangeException("part_index", "Native audio part does not exist.");

    private static object DescribeAudioPart(EngineSession session, ulong trackIndex, ulong partIndex, WIVSMAudioPart part) => new
    {
        session_id = session.Id,
        native = true,
        track_index = trackIndex,
        part_index = partIndex,
        name = part.Name,
        position_tick = part.AbsPosTick.Value,
        begin_tick = part.Region.TickBegin,
        end_tick = part.Region.TickEnd,
        duration_seconds = part.DurationSec,
        original_path = part.GetOriginalWaveFilePath(),
        current_path = part.GetWaveFilePath(),
#if VOCALOID7
        voice_id = (string?)null
#else
        voice_id = part.AiVoiceBankID
#endif
    };

    private static void CommitAudio(EngineSession session)
    {
        session.Dirty = true;
        session.InvalidateChildren();
        bool staged = session.Sequence.IsStaged;
        if (!session.Sequence.Commit(false) && (staged || session.Sequence.LastError != VSMResult.NoError))
            throw new InvalidOperationException("Native audio commit failed: " + session.Sequence.LastError);
    }

    private static string AudioText(JsonElement options, string name, string? fallback = null) =>
        options.TryGetProperty(name, out JsonElement value) ? value.GetString() ?? throw new ArgumentException(name + " cannot be null.")
            : fallback ?? throw new ArgumentException(name + " is required.");

    private static bool AudioFlag(JsonElement options, string name) =>
        options.TryGetProperty(name, out JsonElement value) && value.GetBoolean();

    private static double AudioNumber(JsonElement options, string name, double fallback)
    {
        double number = options.TryGetProperty(name, out JsonElement value) ? value.GetDouble() : fallback;
        if (!double.IsFinite(number))
            throw new ArgumentOutOfRangeException(name, "Value must be finite.");
        return number;
    }

    private static long AudioInteger(JsonElement options, string name, long fallback, long minimum, long maximum)
    {
        long number = options.TryGetProperty(name, out JsonElement value) ? value.GetInt64() : fallback;
        if (number < minimum || number > maximum)
            throw new ArgumentOutOfRangeException(name, $"Value must be in {minimum}..{maximum}.");
        return number;
    }

    private static object InspectAudioFile(EngineSession session, JsonElement options)
    {
        string path = AudioInputPath(options);
        var wave = InspectWave(path);
        return new
        {
            session_id = session.Id,
            path,
            bytes = wave.Bytes,
            channels = wave.Channels,
            sample_rate = wave.SampleRate,
            bits_per_sample = wave.Bits,
            frames = wave.Frames,
            duration_seconds = (double)wave.Frames / wave.SampleRate
        };
    }

    private static string AudioInputPath(JsonElement options)
    {
        string path = options.GetProperty("path").GetString()
            ?? throw new ArgumentException("path is required.");
        if (!Path.IsPathFullyQualified(path))
            throw new ArgumentException("path must be absolute.");
        path = Path.GetFullPath(path);
        PathGuard.NoLinks(path);
        if (!File.Exists(path))
            throw new FileNotFoundException("Audio input does not exist.", path);
        return path;
    }

    private void DisposeAudioServices()
    {
        ReleaseTransport();
        StopNativeAudio();
        audioEffects?.Dispose();
        audioEffects = null;
    }
}
