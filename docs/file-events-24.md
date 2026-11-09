# File-level tempo and controller event metadata — session 24

The previous `score_tempo` implementation copied the first existing tempo event
as a prototype for a new tick. The previous `score_curve` implementation copied
the first controller event for every replacement tick. A synthetic AI fixture
with distinct unknown fields exposed new tempo events inheriting the first
marker, and retained/new controller events inheriting the first controller
marker. The red baseline is
`artifacts/feature-acceptance-da5678235623/summary.json` (two failed feature
cases, cleanup passed).

`vocaloid_bridge/projects.py` now uses the source tick as the explicit
file-level identity policy. A replacement point at an existing tick keeps that
point's unknown event fields; removed points lose theirs; a new tick starts with
only native `pos` and `value`. Existing duplicate positions are rejected before
creating output rather than choosing an ambiguous source. Unknown tempo-container
fields and unrelated controller/root fields are preserved; known global tempo
settings are updated as documented. These are file-level
replacement rules, not native object-pointer identity or a history transaction.

`artifacts/feature-acceptance-f4c4b6029e12/summary.json` passed both focused
cases with distinct markers, same-tick value edits, removal, insertion,
duplicate-input rejection, source protection and a native open/save roundtrip.
After the MCP tool descriptions were updated, both cases and cleanup passed
again in `artifacts/feature-acceptance-6615c4d86e30/summary.json`, including
their advertised field policy. The cases exercise synthetic tempo and Dynamics
controller lanes only; this does
not prove all formats or controller types. The native controller cross-project,
track-automation ordinary-edit, direct-pitch, audio and archive-media review
guards were not changed or bypassed.
