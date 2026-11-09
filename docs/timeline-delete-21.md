# Timeline deletion with event extensions — session 21

## Native evidence and policy

The installed managed `DeleteTime` implementation was inspected locally. With
`include_tempo=true`, it removes tempo events in `[start,end)`, moves events at
or after `end` left by the duration, and may create a boundary event when the
last tempo in the range is needed and no tempo exists exactly at `end`. The
native routine creates that boundary before removing the old events. The bridge
requires its staged pointer to differ from all original tempo pointers and
checks its expected value and position. Deleted tempo extensions disappear;
retained event extensions follow their verified original owner; the generated
boundary has no inherited unknown fields. Deleting an extended initial tempo at
start zero remains guarded.

For meter events, the installed helper compares the starting and ending meter,
removes events after the begin bar through the end bar, and shifts later bars
left by the resulting bar difference. At the session 21 checkpoint the bridge
implemented this map only when the endpoint meters match or no bar shift occurs.
Session 22 subsequently added
the tested unoccupied generated time-signature boundary; an occupied begin-bar
collision remains guarded. See `docs/timeline-meter-22.md`. The private
ordinary native meter probe in
`artifacts/feature-acceptance-467a9a7eaeab/summary.json` observed one same-meter
removal/shift and one different-meter generated boundary; this observation is
not a general identity proof.

## Verified scope

The old host rejected the expected-success fixture before mutation in
`artifacts/feature-acceptance-cfe62cee3296/summary.json`. After one Release
build, `preservation.timeline_delete_extensions_21` passed in
`artifacts/feature-acceptance-e8eb9b6496cb/summary.json`: existing and generated
tempo boundaries, same-meter deletion and shifted survivors, unknown-field
ownership, undo/redo, clone/reopen, source preservation, and the then-current
different-meter guard. That guard was narrowed in session 22 for tested empty
begin bars and retained for occupied-start collisions. The same run covered insertion and unchanged-map regressions and cleaned
up all owned sessions without a foreground switch.

The restricted MIDI/AI route preflights an independent native candidate and
validates the actual post-state against complete expected pointer, position and
value maps. This is bounded evidence for these fixtures, not support for every
collision, meter configuration, boundary or native implementation. Time edits
with controller, direct-pitch, master-volume, track-automation or audio
extensions remain guarded. Existing reviewed transfer, audio and media guards
were not altered.
