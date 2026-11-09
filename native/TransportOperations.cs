using System.Diagnostics;
using System.IO;
using System.Text.Json;
using Yamaha.VOCALOID;
using Yamaha.VOCALOID.VAE;
using Yamaha.VOCALOID.VSM;

internal sealed partial class EngineHost
{
    private sealed class NativeTransport(string sessionId, string deviceId, bool muted, AudioMixCallbacks callbacks)
    {
        internal readonly string SessionId = sessionId;
        internal readonly string DeviceId = deviceId;
        internal readonly bool Muted = muted;
        internal readonly AudioMixCallbacks Callbacks = callbacks;
        internal readonly List<VEAudioPlacement> Placements = [];
        internal VEDeviceConfig Configuration;
        internal double EndSeconds;
    }

    private NativeTransport? transport;

    private static string TransportDeviceId(VEAudioDevice device)
    {
        var value = device.Guid;
        Guid guid = new(unchecked((int)value.Data1), unchecked((short)value.Data2), unchecked((short)value.Data3), value.Data4);
        return device.DeviceType + ":" + guid.ToString("D");
    }

    private static List<VEAudioDevice> TransportDeviceList()
    {
        ushort count = VEAudioEngine.GetAudioDeviceCount();
        if (count > 4096)
            throw new InvalidDataException("Native audio device count exceeds 4096.");
        List<VEAudioDevice> result = [];
        for (ushort index = 0; index < count; index++)
        {
            if (!VEAudioEngine.GetAudioDevice(index, 1, out VEAudioDevice device))
                throw new InvalidOperationException("Native audio device enumeration failed at " + index + ".");
            if (device.SampleRateInfo.SampleRateCount > 16)
                throw new InvalidDataException("Native audio device sample-rate count is invalid.");
            result.Add(device);
        }
        return result;
    }

    private object TransportDevices()
    {
        bool temporary = transport is null;
        if (temporary)
        {
            if (audioEngineInitialized)
                throw new InvalidOperationException("The native audio engine is already in use.");
            VEAudioEngine.Initialize(nint.Zero);
            audioEngineInitialized = true;
        }
        try
        {
            return new { devices = TransportDeviceList().Select(device => new
            {
                device_id = TransportDeviceId(device), name = device.Desc, type = device.DeviceType.ToString(),
                sample_rates = device.SampleRateInfo.SampleRates.Take((int)device.SampleRateInfo.SampleRateCount).ToArray()
            }).ToArray(), native = true };
        }
        finally
        {
            if (temporary)
            {
                VEAudioEngine.Terminate();
                audioEngineInitialized = false;
            }
        }
    }

    internal void CheckTransportAccess(EngineSession session, string method, JsonElement parameters)
    {
        if (transport?.SessionId != session.Id || method is "session" or "close")
            return;
        if (method == "audio_op")
        {
            string operation = parameters.GetProperty("operation").GetString() ?? "";
            if (operation == "devices" || operation.StartsWith("transport_", StringComparison.Ordinal))
                return;
        }
        throw new InvalidOperationException("Release this session's prepared transport before editing, saving, cloning or rendering it.");
    }

    private object TransportOperation(EngineSession session, string operation, JsonElement options)
    {
        if (operation == "devices")
            return TransportDevices();
        if (operation == "transport_prepare")
            return PrepareTransport(session, options);
        if (operation == "transport_status" && transport is null)
            return new { prepared = false, playing = false };
        NativeTransport current = transport ?? throw new InvalidOperationException("Prepare a native transport first.");
        if (current.SessionId != session.Id)
            throw new InvalidOperationException("The native transport belongs to a different session.");
        if (operation == "transport_release")
        {
            ReleaseTransport();
            return new { prepared = false, playing = false, released = true };
        }
        if (Volatile.Read(ref current.Callbacks.Failure) is string failure)
            throw new InvalidOperationException(failure);
        double? requestedSeconds = null;
        switch (operation)
        {
            case "transport_play":
                VEAudioEngine.PlayStart();
                break;
            case "transport_stop":
                VEAudioEngine.PlayStop();
                break;
            case "transport_seek":
                double seconds = AudioNumber(options, "seconds", double.NaN);
                if (!double.IsFinite(seconds) || seconds < 0 || seconds > current.EndSeconds)
                    throw new ArgumentOutOfRangeException("seconds", "Transport position must be within the prepared project.");
                VEAudioEngine.SetCurrentTime(seconds);
                requestedSeconds = seconds;
                break;
            case "transport_status":
                break;
            default:
                throw new ArgumentException("Unknown native transport operation: " + operation);
        }
        double position = VEAudioEngine.GetCurrentTime();
        var left = VEAudioEngine.GetMixerOutputLevel(0);
        var right = VEAudioEngine.GetMixerOutputLevel(1);
        return new { prepared = true, playing = VEAudioEngine.IsPlaying(), session_id = session.Id,
                     device_id = current.DeviceId, muted = current.Muted, seconds = position,
                     sample_rate = current.Configuration.SampleRate, buffer_samples = current.Configuration.BufferSample,
                     requested_seconds = requestedSeconds, position_update_async = requestedSeconds.HasValue,
                     end_seconds = current.EndSeconds, loop_enabled = VEAudioEngine.GetLoopEnabled(),
                     output_peak_db = new[] { left.PeakHold, right.PeakHold }, native = true };
    }

    private object PrepareTransport(EngineSession session, JsonElement options)
    {
        if (transport is not null || audioEngineInitialized)
            throw new InvalidOperationException("Release the existing native transport before preparing another.");
        string deviceId = AudioText(options, "device_id");
        int sampleRate = (int)AudioInteger(options, "sample_rate", 44100, 44100, 96000);
        if (sampleRate is not (44100 or 48000 or 96000))
            throw new ArgumentException("Transport sample_rate must be 44100, 48000 or 96000.");
        uint bufferSamples = (uint)AudioInteger(options, "buffer_samples", 2048, 256, 4096);
        bool muted = AudioFlag(options, "mute_output");
        ulong[] selected = AudioMixTrackIndices(session, options);
        WIVSMSequence sequence = session.Sequence;
        EnsureVoiceServices();
        foreach (ulong index in selected)
        {
            WIVSMTrack track = sequence.GetTrack(index)!;
            if (track.Type is not (VSMTrackType.Midi or VSMTrackType.MidiAi) || new WIVSMMidiTrack(track).IsFrozen)
                continue;
            foreach (WIVSMPart item in track.Parts)
            {
                WIVSMMidiPart part = new(item);
                PrepareRobotVoice(part);
                PrepareSingingSkill(part);
                bool staged = sequence.IsStaged;
                if (!sequence.Commit(false) && (staged || sequence.LastError != VSMResult.NoError))
                    throw new InvalidOperationException("Native transport pre-render commit failed: " + sequence.LastError);
                string output = AudioTemporary(session);
                try { RenderNativePart(sequence, part, output); }
                finally { if (File.Exists(output)) File.Delete(output); }
            }
        }
        var effects = SyncAudioEffects(session, true);
        effects.SetSampleRate(sampleRate);
        var tempos = AudioTempoSnapshot(sequence);
        if (!effects.RecreateTempoInfo(tempos.Select(value => new Yamaha.VOCALOID.VEM.WEffectManager.VEMTempoInfo(value.Seconds, value.Tempo)).ToArray()))
            throw new InvalidOperationException("Native transport tempo synchronization failed.");
        effects.SetBypassAll(false);
        effects.ClearProcessMemory();
        var callbacks = new AudioMixCallbacks(tempos);
        NativeTransport current = new(session.Id, deviceId, muted, callbacks);
        transport = current;
        try
        {
            VEAudioEngine.Initialize(nint.Zero);
            audioEngineInitialized = true;
            var devices = TransportDeviceList().Where(device => TransportDeviceId(device) == deviceId).ToArray();
            if (devices.Length != 1)
                throw new ArgumentException("device_id must identify one currently enumerated native audio device.");
            VEAudioEngineContext context = callbacks.Context;
            VEAudioEngine.SetAudioEngineContext(ref context);
            VEDeviceConfig configuration = new();
            configuration.Init();
            configuration.DeviceType = devices[0].DeviceType;
            configuration.Guid = devices[0].Guid;
            configuration.SampleRate = (uint)sampleRate;
            configuration.BufferSample = bufferSamples;
            configuration.ChannelInfo.ChannelCount = 2;
            VEDeviceChannel[] channels = configuration.ChannelInfo.Channels
                ?? throw new InvalidOperationException("Native channel configuration was not initialized.");
            channels[0].ChannelIndex = 0;
            channels[0].ChannelSource = 0;
            channels[1].ChannelIndex = 1;
            channels[1].ChannelSource = 1;
            VEAudioEngineError result = VEAudioEngine.StartEngine(ref configuration, out var actual, VEConnectMode.StandAlone, out var connection);
            if (result != VEAudioEngineError.Success || connection != VEConnectMode.StandAlone || actual.SampleRate != sampleRate ||
                actual.DeviceType != devices[0].DeviceType || !Yamaha.VOCALOID.VAE.GUID.Equals(actual.Guid, devices[0].Guid))
                throw new InvalidOperationException("Native standalone transport initialization failed: " + result + "; connection=" + connection + "; sample_rate=" + actual.SampleRate);
            current.Configuration = actual;
            if (!VEAudioEngine.SetEffectManager((nint)effects))
                throw new InvalidOperationException("Native transport effect-manager attachment failed.");
            VEBusInfo buses = new() { BusBits = new uint[4], ExtBus = new VEExtBusInfo[127], ExtBusCount = 0 };
            foreach (ulong index in selected)
                buses.BusBits[(int)index >> 5] |= 1u << ((int)index & 31);
            VEAudioEngine.SetBusInfo(buses);
            SetAudioMixAutomation(sequence, true);
            if (muted)
            {
                VEAudioEngine.BeginEditOutputGain();
                VEAudioEngine.AddOutputGain(0, 0);
                VEAudioEngine.EndEditOutputGain();
            }
            bool explicitSelection = options.TryGetProperty("track_indices", out _);
            bool anySolo = sequence.Tracks.Any(track => track.IsSolo);
            HashSet<int> pending = [];
            foreach (ulong index in selected)
            {
                WIVSMTrack track = sequence.GetTrack(index)!;
                bool enabled = explicitSelection || track.IsSolo || (!track.IsMute && !anySolo);
                VEAudioEngine.SetMixerInputEnabled((uint)index, enabled);
                if (!enabled)
                    continue;
                foreach (WIVSMPart part in track.Parts)
                    current.EndSeconds = Math.Max(current.EndSeconds, part.EndSec);
                if (track.Type is VSMTrackType.Midi or VSMTrackType.MidiAi && new WIVSMMidiTrack(track) is { IsFrozen: true } frozen)
                    AddAudioPlacement(AudioPlacementBuilder.CreateAudioPlacementFrozenTrack(sequence, frozen,
                        FrozenTrackTimeRange(sequence, frozen)), current.Placements, pending);
                else
                    foreach (WIVSMPart part in track.Parts)
                    {
                        if (part.DurationSec <= 0) continue;
                        PathGuard.NoLinks(part.PartFilePath);
                        InspectWave(part.PartFilePath);
                        AddAudioPlacement(AudioPlacementBuilder.CreateAudioPlacement(sequence, part, PlacementStorageType.File, null,
                            AudioPlacementBuilder.CreateTimeRange(sequence, part, PlacementStorageType.File, null)), current.Placements, pending);
                    }
            }
            if (current.Placements.Count == 0)
                throw new InvalidOperationException("No audible native placements were selected for transport.");
            Stopwatch elapsed = Stopwatch.StartNew();
            while (pending.Count != 0)
            {
                DrainAudioPlacements(callbacks, pending);
                if (elapsed.Elapsed.TotalSeconds > 30)
                    throw new TimeoutException("Native transport did not acknowledge file placements.");
                if (pending.Count != 0) Thread.Sleep(10);
            }
            var loop = sequence.LoopRange;
            double begin = sequence.IsLoopOn ? sequence.GetTimeFromTick(new VSMAbsTick(loop.Begin)) : 0;
            double end = sequence.IsLoopOn ? sequence.GetTimeFromTick(new VSMAbsTick(loop.End)) : current.EndSeconds;
            VEAudioEngine.SetLoopRange(new VETimeRange(begin, end));
            VEAudioEngine.SetLoopEnabled(sequence.IsLoopOn);
            VEAudioEngine.SetAutoStopAtLoopEnd(!sequence.IsLoopOn);
            VEAudioEngine.SetCurrentTime(begin);
            return TransportOperation(session, "transport_status", options);
        }
        catch
        {
            ReleaseTransport();
            throw;
        }
    }

    private void ReleaseTransport()
    {
        NativeTransport? current = transport;
        if (current is null) return;
        if (audioEngineInitialized)
        {
            VEAudioEngine.PlayStop();
            VEAudioEngine.Terminate();
            audioEngineInitialized = false;
        }
        transport = null;
        foreach (VEAudioPlacement placement in current.Placements)
            placement.Dispose();
        current.Callbacks.Completed.Dispose();
    }
}
