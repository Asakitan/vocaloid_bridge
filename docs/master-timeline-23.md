# Master volume timeline investigation (session 23)

## Scope

The existing archive timeline guard remains unchanged. This investigation used a synthetic AI project, the installed managed implementation, and an isolated private desktop. It did not operate the interactive editor or real DAW/MIDI devices. It does not establish general preservation or release acceptance.

## Native evidence

Receipt: `artifacts/master23-probe-c9e1fe80edaa.json`. The source was `output/feature-master23-delete-native-before.vpr`, synthesized from the prior AI fixture `output/feature-80b1c4779514-107-delete21-native.vpr` with master volume events `(tick,value)` at `(0,0)`, `(900,-1)`, `(1000,-2)`, `(1200,-3)`, `(1500,-4)`, `(2000,-5)`. The temporary private-desktop probe is `.runtime/probe_master23.ps1`. Its snapshots record native pointer, tick, and value for each master event.

For `[1000,1500)`, both tempo options showed the same master-volume behavior:

- Insert: the original event at 1000 moved to 1500, later events moved by 500, and a new event at 1000 had value -2 and a distinct pointer.
- Delete: original events at 1000 and 1200 were removed; the original 1500 and 2000 events moved to 1000 and 1500. A new event at 999 had value -1 and a distinct pointer.
- Rollback and undo restored the original pointer, tick and value set; redo restored the committed set. A newly allocated pointer in the pending attempt need not equal the subsequent committed attempt.

The native probe does not validate unknown-field archival metadata, failure injection, clone, save/reopen, or arbitrary ranges. No old-host red-baseline test was executed in this slice.

## Installed managed behavior and next evidence

Decompilation of `Yamaha.VOCALOID.WIVSMSequenceExtension` shows insertion can move an existing boundary event back, duplicate it, or generate interpolated points depending on neighbors. Deletion can generate an interpolated point at `start - 1`, generate a point at `end`, delete points in `[start,end)`, and move later points. Therefore a tick-only metadata map is insufficient: the eventual hook must snapshot original native identities and values, validate retained and generated identities and destinations before transferring unknown fields, assign no unknown fields to newly generated events, and participate in the existing mutation rollback and history boundaries. Guard changes require distinct tests for the branches, collisions, zero boundary, generated end, save/reopen, clone, and error rollback before any integration. Existing unrelated guarded operations remain untouched.
