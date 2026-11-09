# Robot Voice native runtime investigation

This document records focused observations and the tested Robot audio case,
not an assertion about every voice, mode or MIDI-effect combination.
All probes use private native sessions and distinct per-host VSM cache
namespaces; no interactive editor or shared `VOCALOID6` cache was controlled.

## Known behaviour

`synthesis.robot_voice` receipt `artifacts/feature-acceptance-7085da10d352/summary.json`
reports Hard mode and bypass state surviving save/reopen, both render results
reporting `NoError`, and baseline and Hard PCM being exactly equal. `NoError`
alone is not proof that the MIDI effect was executed.

Installed managed wrapper decompilation shows the original `Sequence` binds an
application-lifetime `LuaControllerManager` to the sequence before starting
the async renderer. The original part-level `SetRobotVoiceMode` changes the
effect mode, complements the installed script path and uses `BeforeRendering`.
The bridge sets the same mode, resolved script path and timing but, before the
current lifecycle investigation, created/bound a controller only during render,
after the edit and pre-render commit. This is a timing difference, not yet a
demonstrated cause. The installed Hard script is Lua 5.1 bytecode and its
constant table references native note and control update calls.

## Controlled observations

- `artifacts/robot-isolated-28d76c5f421a.json`: separate native hosts with
  distinct cache namespaces, using the previously saved baseline and Hard
  fixtures, returned identical input note lists and different PCM. The baseline
  was bypassed and the Hard effect enabled. Baseline RMS was approximately
  0.0112547 and difference RMS 0.0157427; the new baseline was byte-identical
  to the earlier baseline. This shows a unique namespace does not by itself
  prevent an audible native Hard result. It does not isolate all host state.
- `artifacts/robot-transition-5c34e06d815e.json`: opening those two existing
  fixtures sequentially in one fresh host also produced different PCM. Both
  wave/score validity flags were false before render and true afterward. Thus
  same-host reopening alone does not explain the failure.
- `artifacts/robot-transition-95cd5b645234.json`: render baseline, edit the
  same session to Hard, save, close, reopen and render yielded identical PCM.
  After edit, the old wave and score remained valid while `IsFinishedRendering`
  became false. The reopened Hard part began with both validity flags false;
  after the render call they were true, but its progress counters remained zero
  and `BlockRenderingEnabled` was false. The counters do not establish exactly
  which internal work was performed.
- The two Hard VPRs in the previous comparisons contained identical
  `Project/sequence.json` content and no embedded audio. This points toward a
  history-dependent native runtime condition but does not identify its cache
  key, invalidation semantics or controller timing as the cause.
- `artifacts/robot-stage-97704a61920b.json`: in a fresh private session,
  `WIVSMRobotVoiceEffect.SetRobotVoiceMode(Hard)` returned true and individually
  changed `IsStaged` false→true. After rollback, `WIVSMMidiPart.SetBypass`
  independently returned true and also staged a change; rollback succeeded.
  This verifies staging, not whether either edit invalidates a particular
  render cache entry. A read-only printable-string search of `VSM.dll` did not
  establish a cache-key definition.

The managed `WIVSMSequenceManager` exposes manager-wide `ClearCache`,
`ShrinkCache`, and capacity/size; no matching part-level invalidation method
was identified in the inspected managed wrappers. Manager-wide cache clearing
may affect other sessions, so it is not a proposed production fix.

Read-only inspection of installed `VLC.dll` found its sole UTF-16 `VOCALOID6`
string at file offset `0x3c718` (RVA `0x3d718`). The function at RVA `0x19b0`
calls `SHGetFolderPathW` with CSIDL `0x1c` (`LOCAL_APPDATA`), appends
`VOCALOID6`, then appends `JOB_PLUGINS` and checks file attributes. This is
direct evidence of a local JOB_PLUGINS path, not evidence that VLC requires a
fixed VSM manager ID. Searching VSM exports for invalidate, refresh and forced
render names identified only manager-wide `clearCache`.

## Lifecycle and cache experiments

A coordinated experiment bound a host-lifetime controller immediately after
sequence creation/open/import/clone, retaining the unique cache namespace. The
focused acceptance run `artifacts/feature-acceptance-7fa568665902/summary.json`
still reported zero PCM difference. Early controller binding by itself therefore
did not resolve the observed failure.

The earlier renderer waited only for `HasValidRenderedWave`; the edit probe
observed that flag true while `IsFinishedRendering` was false. An independent
completion-wait experiment `artifacts/feature-acceptance-a3709eb1ef6f/summary.json`
reported Started, Completed, Finished and second_end=100 for both renders but
still showed equal PCM. Waiting alone did not explain the behavior.

Setting the private host's native `WIVSMSequenceManager.CacheCapacity` to zero
was tested as a separate change, without changing the per-host namespace or
calling `ClearCache`. Focused MCP acceptance
`artifacts/feature-acceptance-b08ff3a55109/synthesis.robot_voice.json` passed:
baseline → Hard edit → save → close → reopen → render produced an audio
difference, and the test also passed native mixdown. This is causal evidence
for the manager cache-capacity change under this workflow, not proof of the
native cache-key implementation.

`artifacts/robot-concurrent-55f6b5ff5c73.json` adds a two-active-session probe
in one host: session A rendered baseline, session B imported a WAV, session A
switched directly to Hard and rendered different PCM with the same format, and
session B exported its original audio with identical PCM. This test does not
cover every effect, all voicebanks, every processed-audio path, or devices.
