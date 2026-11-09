# Ordinary media property preservation — session 31

## Production flow

Only bridge-owned ordinary clips under `.runtime/library/media` are accepted;
the existing archive-bearing clip guard remains. Update and delete share a
per-clip named mutex across bridge processes. The update refreshes and reacquires
its native clip, validates input, and holds read-sharing source and property
handles while copying and serializing a private candidate.

The same native host assembly starts a private-desktop `--media-property`
worker restricted to `.runtime/media-property/<GUID>`. Its VMM manager edits
only the copied clip. It seeds the native name, key, tempo and tags and saves
through the native property editor. The original clip is not sent to that
writer. The parent clones the original JSON and copies only requested `name`,
`part.tempo`, `filter.genres` and `filter.types` from native output; unknown
nested objects and arrays outside those fields remain associated with their
original owners. Duplicate JSON keys and non-string tag arrays are rejected.
This is not a generic unknown-array merge algorithm.

The merged candidate is flushed and atomically replaces the live property file
with a backup of the exact replaced bytes. Snapshot comparison checks before
replacement and comparison with the actual backup detects a check-to-replace
conflict after publication. The native catalog is refreshed and the clip is
reacquired and read back before success. Normal completion and pre-publication
failure clean the staging directory.

## Explicit partial-commit boundary

The mutex serializes cooperating bridge writers, not arbitrary external tools.
A non-cooperating writer can still race between comparison and replacement.
If the replaced backup differs, or native refresh/readback fails after commit,
the error explicitly reports that properties were committed, discards the
process-local media catalog and retains the backup path for recovery. It does
not claim that an unproved rollback happened or silently return stale cache.
The next access constructs a fresh native catalog. The retained recovery
directory is meaningful data, not an automatically disposable temporary folder.

Process/system crashes, hostile repeated writers, injected post-commit refresh
errors and full crash recovery are unverified. Backup retention makes the old
bytes available; it is not a complete recovery journal. Archive-bearing media
property updates remain guarded.

## Necessary evidence

`artifacts/feature-acceptance-d4949727b918/summary.json` records one passing
case and cleanup. A fresh ordinary asa clip retained unknown root and part
objects and an unknown filter array while changing name, tempo, genres and
types. Native getters agreed and `.vsclip` bytes stayed unchanged. A read-sharing
lock rejected publication; property bytes and cached name remained unchanged.
No owned foreground activation or remaining session was observed.

Earlier red preservation evidence in `media-property-21.md` remains historical;
the new path addresses that normal-operation loss without asserting the broader
concurrency and crash guarantees listed above.
