"""Synthetic native tempo map merge with opaque event fields."""
import json
import zipfile

import verify_features as v


@v.feature("preservation.tempo_merge", "preservation", "project_create", "project_open",
           "project_merge", "project_edit", "project_save")
async def tempo_merge(check):
    async with check.project() as source_id:
        await check.edit(source_id, "tempo.set", start_tick=480, bpm=140)
        source_json, source_seed = await check.save(source_id, "tempo-merge-seed")
    _, members = v.read_vpr(source_seed)
    for event in source_json["masterTrack"]["tempo"]["events"]:
        event["x_merge_tempo"] = {"source": event["pos"]}
    members["Project/sequence.json"] = json.dumps(source_json, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("tempo-merge-source")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    original = source.read_bytes()

    async with check.project() as target:
        await check.edit(target, "tempo.set", start_tick=960, bpm=90)
        await check.call("project_merge", session_id=target, path=str(source), include_tracks=False,
                         include_tempo=True, replace_tempo=False, offset_tick=3840)
        saved, path = await check.save(target, "tempo-merge-offset")
        events = saved["masterTrack"]["tempo"]["events"]
        v.require([e["pos"] for e in events] == [0, 960, 3840, 4320] and
                  [e.get("x_merge_tempo") for e in events] == [None, None, {"source": 0}, {"source": 480}],
                  "Offset tempo merge changed identity or extension", events)
        await check.edit(target, "undo")
        undone, _ = await check.save(target, "tempo-merge-undo")
        v.require([e["pos"] for e in undone["masterTrack"]["tempo"]["events"]] == [0, 960], "Tempo merge undo failed")
        await check.edit(target, "redo")
        redone, path = await check.save(target, "tempo-merge-redo")
        v.require(redone["masterTrack"]["tempo"]["events"] == events, "Tempo merge redo changed metadata")
        reopened = (await check.call("project_open", path=str(path)))["session_id"]
        try:
            actual, _ = await check.save(reopened, "tempo-merge-reopen")
            v.require(actual["masterTrack"]["tempo"]["events"] == events, "Reopen changed tempo metadata")
        finally:
            await check.close(reopened)
        await check.call("project_merge", session_id=target, path=str(source), include_tracks=False,
                         include_tempo=True, offset_tick=3840)
        repeated, _ = await check.save(target, "tempo-merge-repeated")
        v.require(repeated["masterTrack"]["tempo"]["events"] == events,
                  "Repeated tempo collision changed the source fields")
        await check.edit(target, "undo")
        repeated_undo, _ = await check.save(target, "tempo-merge-repeated-undo")
        v.require(repeated_undo["masterTrack"]["tempo"]["events"] == events,
                  "Repeated tempo collision undo changed earlier metadata")

    async with check.project() as target:
        await check.edit(target, "tempo.set", start_tick=960, bpm=90)
        await check.call("project_merge", session_id=target, path=str(source), include_tracks=False,
                         include_tempo=True, replace_tempo=True)
        saved, _ = await check.save(target, "tempo-merge-replace")
        v.require(saved["masterTrack"]["tempo"]["events"] == source_json["masterTrack"]["tempo"]["events"],
                  "Tempo replacement changed source map")
        await check.edit(target, "undo")
        undone, _ = await check.save(target, "tempo-merge-replace-undo")
        v.require([e["pos"] for e in undone["masterTrack"]["tempo"]["events"]] == [0, 960], "Tempo replacement undo failed")
        await check.edit(target, "redo")
        redone, _ = await check.save(target, "tempo-merge-replace-redo")
        v.require(redone["masterTrack"]["tempo"]["events"] == source_json["masterTrack"]["tempo"]["events"],
                  "Tempo replacement redo changed metadata")
    v.require(source.read_bytes() == original, "Tempo merge changed the source file")


if __name__ == "__main__":
    raise SystemExit(v.main())
