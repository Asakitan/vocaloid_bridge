"""Focused native time-signature extension merge regression; no build."""
import json
import zipfile
import verify_features as v

KEY = "x_timesig_merge_probe"

@v.feature("preservation.timesig_merge", "preservation", "project_create", "project_edit", "project_save", "project_open", "project_merge")
async def timesig_merge(check):
    async with check.project() as seed:
        await check.edit(seed, "time_signature.set", bar=2, numerator=3, denominator=4)
        await check.edit(seed, "time_signature.set", bar=4, numerator=5, denominator=4)
        seq, plain = await check.save(seed, "timesig-merge-seed")
    _, members = v.read_vpr(plain)
    for event in seq["masterTrack"]["timeSig"]["events"]:
        event[KEY] = {"source_bar": event["bar"]}
    members["Project/sequence.json"] = json.dumps(seq, ensure_ascii=False).encode("utf-8")
    path = v.ROOT / "output" / check.output("timesig-merge-extended")
    with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    original = path.read_bytes()
    def events(sequence):
        return [(e["bar"], e["numer"], e["denom"], e.get(KEY)) for e in sequence["masterTrack"]["timeSig"]["events"]]
    def marker(bar): return {"source_bar": bar}
    source = [(0, 4, 4, marker(0)), (2, 3, 4, marker(2)), (4, 5, 4, marker(4))]
    async def snapshot(sid, label):
        result, saved = await check.save(sid, "timesig-merge-" + label)
        return events(result), saved
    async with check.project() as target:
        await check.edit(target, "time_signature.set", bar=1, numerator=7, denominator=8)
        before, _ = await snapshot(target, "before-replace")
        await check.call("project_merge", session_id=target, path=str(path), include_tracks=False, include_tempo=True, replace_tempo=True)
        actual, _ = await snapshot(target, "replace")
        v.require(actual == source, "Replacement metadata differs", actual)
        await check.edit(target, "undo")
        actual, _ = await snapshot(target, "replace-undo")
        v.require(actual == before, "Replacement undo differs", actual)
        await check.edit(target, "redo")
        actual, saved = await snapshot(target, "replace-redo")
        v.require(actual == source, "Replacement redo differs", actual)
        reopened = (await check.call("project_open", path=str(saved)))["session_id"]
        try:
            actual, _ = await snapshot(reopened, "reopen")
            v.require(actual == source, "Reopen metadata differs", actual)
        finally: await check.close(reopened)
    async with check.project() as target:
        await check.call("project_merge", session_id=target, path=str(path), include_tracks=False, include_tempo=True, offset_tick=1920)
        actual, _ = await snapshot(target, "offset")
        expected = [(0,4,4,None),(1,4,4,marker(0)),(3,3,4,marker(2)),(5,5,4,marker(4))]
        v.require(actual == expected, "Offset metadata differs", actual)
    async with check.project() as target:
        await check.call("project_merge", session_id=target, path=str(path), include_tracks=False, include_tempo=True, offset_tick=5000)
        actual, _ = await snapshot(target, "offset-5000")
        expected = [(0,4,4,None),(2,4,4,marker(0)),(4,3,4,marker(2)),(7,5,4,marker(4))]
        v.require(actual == expected, "Non-aligned offset metadata differs", actual)
        await check.edit(target, "undo")
        actual, _ = await snapshot(target, "offset-undo")
        v.require(actual == [(0,4,4,None)], "Offset undo differs", actual)
        await check.edit(target, "redo")
        actual, _ = await snapshot(target, "offset-redo")
        v.require(actual == expected, "Offset redo differs", actual)
    async with check.project() as single:
        _, single_path = await check.save(single, "single-source")
    target = (await check.call("project_open", path=str(path)))["session_id"]
    try:
        await check.call("project_merge", session_id=target, path=str(single_path), include_tracks=False, include_tempo=True, offset_tick=7680)
        actual, _ = await snapshot(target, "target-fields")
        v.require(actual == [(0,4,4,marker(0)),(2,3,4,marker(2)),(4,4,4,None)], "Target retained or overwritten metadata differs", actual)
    finally: await check.close(target)
    # Same-value bar zero overwrite must take the source extension, not retain the target one.
    target = (await check.call("project_open", path=str(path)))["session_id"]
    try:
        await check.call("project_merge", session_id=target, path=str(plain), include_tracks=False, include_tempo=True, offset_tick=0)
        actual, _ = await snapshot(target, "same-value-overwrite")
        v.require(actual == [(0,4,4,None),(2,3,4,None),(4,5,4,None)], "Same-value overwrite retained target metadata", actual)
        await check.edit(target, "undo")
        actual, _ = await snapshot(target, "same-value-undo")
        v.require(actual == source, "Same-value overwrite undo differs", actual)
    finally: await check.close(target)
    v.require(path.read_bytes() == original, "Merge changed source archive")

if __name__ == "__main__":
    raise SystemExit(v.main())
