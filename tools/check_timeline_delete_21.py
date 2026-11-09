"""Exercise extended tempo and meter metadata during native timeline deletion."""
import json
import sys
import zipfile

import verify_features as v

KEY = "x_timeline_delete_21"


@v.feature("preservation.timeline_delete_extensions_21", "preservation", "score_compose", "project_edit",
           "project_open", "project_save", "project_clone")
async def timeline_delete_extensions(check):
    seed = await check.call("score_compose", output_name=check.output("delete21-seed"), title="Delete extensions", bpm=120,
                            notes=[{"start": 0, "duration": .5, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    sid = seed["native_session"]["session_id"]
    try:
        await check.edit(sid, "part.move", track_index=0, part_index=0, start_tick=16000)
        for tick, bpm in ((1000, 130), (1200, 140), (1500, 150), (2000, 160)):
            await check.edit(sid, "tempo.set", start_tick=tick, bpm=bpm)
        for bar, numerator, denominator in ((2, 3, 4), (3, 4, 4), (4, 5, 8)):
            await check.edit(sid, "time_signature.set", bar=bar, numerator=numerator, denominator=denominator)
        sequence, seed_path = await check.save(sid, "delete21-native")
    finally:
        await check.close(sid)
    _, members = v.read_vpr(seed_path)
    for event in sequence["masterTrack"]["tempo"]["events"]:
        event[KEY] = {"kind": "tempo", "origin": event["pos"]}
    for event in sequence["masterTrack"]["timeSig"]["events"]:
        event[KEY] = {"kind": "meter", "origin": event["bar"]}

    def fixture(label, data):
        path = v.ROOT / "output" / check.output("delete21-" + label)
        content = dict(members)
        content["Project/sequence.json"] = json.dumps(data, ensure_ascii=False).encode("utf-8")
        with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, payload in content.items(): archive.writestr(name, payload)
        return path

    def tempo(project):
        return [(e["pos"], e["value"], e.get(KEY)) for e in project["masterTrack"]["tempo"]["events"]]

    def meter(project):
        return [(e["bar"], e["numer"], e["denom"], e.get(KEY)) for e in project["masterTrack"]["timeSig"]["events"]]

    def tempo_marker(tick): return {"kind": "tempo", "origin": tick}
    def meter_marker(bar): return {"kind": "meter", "origin": bar}
    main = fixture("source", sequence)
    generated = json.loads(json.dumps(sequence))
    generated["masterTrack"]["tempo"]["events"] = [e for e in generated["masterTrack"]["tempo"]["events"] if e["pos"] != 1500]
    generated_path = fixture("generated", generated)
    sources = {main: main.read_bytes(), generated_path: generated_path.read_bytes()}

    for path, generated_boundary in ((main, False), (generated_path, True)):
        sid = (await check.call("project_open", path=str(path)))["session_id"]
        try:
            before, _ = await check.save(sid, "delete21-before")
            await check.edit(sid, "time.delete", start_tick=1000, duration_tick=500, include_tempo=True)
            after, _ = await check.save(sid, "delete21-after")
            boundary_value = 14000 if generated_boundary else 15000
            boundary_marker = None if generated_boundary else tempo_marker(1500)
            expected = [(0, 12000, tempo_marker(0)), (1000, boundary_value, boundary_marker),
                        (1500, 16000, tempo_marker(2000))]
            v.require(tempo(after) == expected, "Tempo deletion metadata differs", tempo(after))
            v.require(meter(after) == meter(before), "Tempo deletion changed meter metadata")
            await check.edit(sid, "undo")
            undone, _ = await check.save(sid, "delete21-undo")
            v.require(undone == before, "Tempo deletion undo differs")
            await check.edit(sid, "redo")
            redone, path_after = await check.save(sid, "delete21-redo")
            v.require(redone == after, "Tempo deletion redo differs")
            clone = (await check.call("project_clone", session_id=sid))["session_id"]
            try:
                clone_json, _ = await check.save(clone, "delete21-clone")
                v.require(clone_json == after, "Tempo deletion clone differs")
            finally: await check.close(clone)
            reopened = (await check.call("project_open", path=str(path_after)))["session_id"]
            try:
                reopened_json, _ = await check.save(reopened, "delete21-reopen")
                v.require(reopened_json == after, "Tempo deletion reopen differs")
            finally: await check.close(reopened)
        finally: await check.close(sid)

    sid = (await check.call("project_open", path=str(main)))["session_id"]
    try:
        before, _ = await check.save(sid, "delete21-meter-before")
        await check.edit(sid, "time.delete", start_tick=1920, duration_tick=3360, include_tempo=False)
        after, _ = await check.save(sid, "delete21-meter-after")
        expected = [(0, 4, 4, meter_marker(0)), (2, 5, 8, meter_marker(4))]
        v.require(meter(after) == expected, "Meter deletion metadata differs", meter(after))
        v.require(tempo(after) == tempo(before), "Meter deletion changed excluded tempo")
        await check.edit(sid, "undo")
        undone, _ = await check.save(sid, "delete21-meter-undo")
        v.require(undone == before, "Meter deletion undo differs")
        await check.edit(sid, "redo")
        redone, saved = await check.save(sid, "delete21-meter-redo")
        v.require(redone == after, "Meter deletion redo differs")
        reopened = (await check.call("project_open", path=str(saved)))["session_id"]
        try:
            reopened_json, _ = await check.save(reopened, "delete21-meter-reopen")
            v.require(reopened_json == after, "Meter deletion reopen differs")
        finally: await check.close(reopened)
    finally: await check.close(sid)

    sid = (await check.call("project_open", path=str(main)))["session_id"]
    try:
        before, _ = await check.save(sid, "delete21-meter-guard-before")
        history = await check.edit(sid, "history.status")
        await check.rejected("project_edit", "timeline|signature|project_preservation", session_id=sid,
                             operation="time.delete", options={"start_tick": 3840, "duration_tick": 1700, "include_tempo": False})
        after, _ = await check.save(sid, "delete21-meter-guard-after")
        v.require(after == before and await check.edit(sid, "history.status") == history,
                  "Guarded occupied meter boundary changed target or history")
    finally: await check.close(sid)
    v.require(all(path.read_bytes() == data for path, data in sources.items()), "Timeline deletion changed source archives")


@v.feature("preservation.timeline_delete_native_21", "preservation", "score_compose", "project_edit", "project_save")
async def timeline_delete_native(check):
    for label, duration in (("same_meter", 3360), ("different_meter", 2380)):
        seed = await check.call("score_compose", output_name=check.output("delete-native-seed"), title="Native deletion", bpm=120,
                                notes=[{"start": 0, "duration": .5, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0}])
        sid = seed["native_session"]["session_id"]
        try:
            await check.edit(sid, "part.move", track_index=0, part_index=0, start_tick=16000)
            for bar, numerator, denominator in ((2, 3, 4), (3, 4, 4), (4, 5, 8)):
                await check.edit(sid, "time_signature.set", bar=bar, numerator=numerator, denominator=denominator)
            before, _ = await check.save(sid, "delete-native-before")
            await check.edit(sid, "time.delete", start_tick=1920, duration_tick=duration, include_tempo=False)
            after, _ = await check.save(sid, "delete-native-after")
            check.evidence(label, {"before": before["masterTrack"]["timeSig"]["events"],
                                   "after": after["masterTrack"]["timeSig"]["events"]})
            if label == "same_meter":
                v.require([(e["bar"], e["numer"], e["denom"]) for e in after["masterTrack"]["timeSig"]["events"]]
                          == [(0, 4, 4), (2, 5, 8)], "Same-meter native deletion differs")
            await check.edit(sid, "undo")
            undone, _ = await check.save(sid, "delete-native-undo")
            v.require(undone == before, "Native meter deletion undo differs")
        finally: await check.close(sid)


if __name__ == "__main__":
    if "--case" not in sys.argv:
        sys.argv.extend(["--case", "preservation.timeline_delete_extensions_21"])
    raise SystemExit(v.main())
