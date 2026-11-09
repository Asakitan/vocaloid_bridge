# Native Standalone Transport

`project_audio` exposes native VAE device enumeration and a session-scoped
standalone transport. It does not instantiate the editor `AudioPlayer`, alter
system default devices or global preferences, or automate the user interface.

`devices` lists native devices and supported rates. `transport_prepare` takes
an explicit enumerated `device_id` and optional `sample_rate`, `buffer_samples`,
`track_indices`, and `mute_output`; there is no implicit device choice.
`transport_play`, `transport_stop`, `transport_seek`, `transport_status`, and
`transport_release` act on the prepared native transport. A prepared transport
owns native VAE state until release; closing its session also releases it.
Concurrent operations that would mutate or render the prepared session are
rejected until release. Full option and return details are in
`docs/audio-operations.md`.

The seek response includes `requested_seconds` and
`position_update_async=true`; its `seconds` value remains the native observation,
which may still show the previous position. `output_peak_db` is in decibels,
not linear amplitude. The later integrated MCP run
`artifacts/feature-acceptance-26a71f9b1dc5/` passes the same transport closure
alongside formal freeze operations and operation discovery.

`tools/check_transport.py` is a targeted actual-MCP device test. It selects an
enumerated DirectSound device explicitly, prepares with `mute_output=true`,
checks playback-clock advance, `output_peak_db` at the observed -120 dB floor, stopped seek, release,
save after release, and automatic release on session close. It waits for an
integrated build. The first run `artifacts/feature-acceptance-a4b85195a342/summary.json`
confirmed prepare, playback-clock advance, busy save rejection, and cleanup,
but failed because the test incorrectly treated the native dB peak as linear
amplitude. With that assertion corrected, the run
`artifacts/feature-acceptance-1982cb4b10cd/summary.json` observed 44100 Hz,
2048 samples, a 0.388934-second advancing clock and a -120 dB peak. It failed
at a stopped seek: requesting 0.5 seconds returned 0.388934 seconds immediately.
Release and cleanup completed on that failure.

The targeted timing follow-up `artifacts/feature-acceptance-ee57bb3213da/summary.json`
passed on an explicitly selected HECATE DirectSound device at 44100 Hz and
2048 samples. With output muted, the reported peak stayed at -120 dB. Playback
advanced to 0.406349 seconds; after stop, `seek(1.2)` immediately returned the
old 0.406349 position, but status after 100 ms returned 1.2 seconds without
restarting playback. Playback then advanced to 1.321905 seconds. Thus the
native observed position can lag the seek request; an immediate response is
not completion confirmation. The test also confirmed busy save rejection,
release followed by a successful save, and automatic release on session close.
This is one device and one timing sample, not a general latency guarantee. An available
physical or virtual device is an external prerequisite. A muted transport test
does not establish audible playback quality, recording, or DAW host sync.
