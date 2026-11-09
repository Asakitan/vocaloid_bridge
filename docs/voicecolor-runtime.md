# VoiceColor Runtime Evidence

`performance.get` enumerates nine `VSMVoiceColor` names and their native
limits. `performance.set` accepts each enum name and uses native setters and
post-commit readback. Readback by itself is not evidence of a change in sound.

The installed editor's decompiled `ExpressionView` selects the AI VoiceColor
view for `IsAi` and the classic view otherwise. Its AI view exposes
`S5Expression`, `S5Air`, and `S5Character`; its classic view exposes `Exciter`,
`Growl`, `Breathiness`, `Air`, `Mouth`, and `Character`. The native enum accepts
all nine, which does not establish that every voice engine uses all nine.
The bridge reports this mapping as `applies_to` and
`applicable_to_current_part` on each descriptor. These fields describe engine
applicability, not a guarantee of audible change or the bypass setting.

## Actual MCP Probe

`tools/check_voicecolor_audio.py` creates one native AI singing fixture, turns
VoiceColor on, renders a baseline and a repeated control, then changes each
native field separately to the farther endpoint of its reported range. It
restores each original field before changing the next one. Finally it compares
enabled and bypassed VoiceColor with the strongest changed field. It records
native readbacks and independently decoded WAV metrics; changed active samples
exceed an absolute difference of one 16-bit LSB and use an activity threshold
of `1e-4`. A difference must exceed the greater of one percent of baseline RMS,
five times repeat-control RMS, or `1e-6` to be labeled detected. These numerical
checks are not a listening test.

The run `artifacts/feature-acceptance-dc7fdcb678e4/voicecolor.audio.json` used
one installed DNN voice and a three-note Japanese vowel phrase. Its baseline
repeat was sample-identical; detection threshold RMS was approximately
`0.00011287`. Changes below compare each field to the same enabled baseline:

| Field | Changed value | Delta RMS | Active samples differing by more than 1 LSB16 | Observation |
| --- | ---: | ---: | ---: | --- |
| Exciter | -64 | 0 | 0 | No measured change on this AI fixture |
| Growl | 127 | 0 | 0 | No measured change on this AI fixture |
| Breathiness | 127 | 0 | 0 | No measured change on this AI fixture |
| Air | 127 | 0 | 0 | No measured change on this AI fixture |
| Mouth | -127 | 0 | 0 | No measured change on this AI fixture |
| Character | -64 | 0 | 0 | No measured change on this AI fixture |
| S5Expression | 100 | 0.041512 | 54804 | Measured difference |
| S5Air | -100 | 0.00167848 | 58677 | Measured difference |
| S5Character | -64 | 0.0105455 | 58442 | Measured difference |

With `S5Expression=100`, comparing enabled versus bypassed VoiceColor yielded
delta RMS `0.0415197` and 57445 changed active samples. All nine native writes
read back as requested in the current session. This probe does not establish
that the six classic parameters affect a classic voice, nor does it prove
every value, voicebank, phrase, or perceptual outcome. The probe did not
perform a save/reopen persistence check; other persistence receipts remain a
separate evidence category. Its measurement case and session cleanup passed;
the original enclosing runner incorrectly selected full-operation coverage and
returned a nonzero exit code. The script now defaults to the `voicecolor`
category without discarding the other registered cases. This selection-only
correction does not add another audio run or change the original measurements.
