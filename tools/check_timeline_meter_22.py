"""Exercise extended tempo and meter metadata during native timeline deletion."""
import json
import sys
import zipfile

import verify_features as v

KEY = "x_timeline_delete_21"


@v.feature("preservation.timeline_meter_22", "preservation", "score_compose", "project_edit",
           "project_open", "project_save", "project_clone")
async def timeline_meter_22(check):
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

    for include_tempo in (False, True):
        sid = (await check.call("project_open", path=str(main)))["session_id"]
        try:
            before, _ = await check.save(sid, "meter22-before")
            await check.edit(sid, "time.delete", start_tick=1920, duration_tick=2380, include_tempo=include_tempo)
            after, saved = await check.save(sid, "meter22-after")
            expected = [(0, 4, 4, meter_marker(0)), (1, 3, 4, None),
                        (2, 4, 4, meter_marker(3)), (3, 5, 8, meter_marker(4))]
            v.require(meter(after) == expected, "Generated meter identity metadata differs", meter(after))
            expected_tempo = ([(0, 12000, tempo_marker(0)), (1000, 13000, tempo_marker(1000)),
                               (1200, 14000, tempo_marker(1200)), (1500, 15000, tempo_marker(1500)),
                               (1920, 16000, None)] if include_tempo else tempo(before))
            v.require(tempo(after) == expected_tempo, "Tempo deletion metadata differs", tempo(after))
            await check.edit(sid, "undo")
            undone, _ = await check.save(sid, "meter22-undo")
            v.require(undone == before, "Meter boundary undo differs")
            await check.edit(sid, "redo")
            redone, saved = await check.save(sid, "meter22-redo")
            v.require(redone == after, "Meter boundary redo differs")
            clone = (await check.call("project_clone", session_id=sid))["session_id"]
            try:
                clone_json, _ = await check.save(clone, "meter22-clone")
                v.require(clone_json == after, "Meter boundary clone differs")
            finally: await check.close(clone)
            reopened = (await check.call("project_open", path=str(saved)))["session_id"]
            try:
                reopened_json, _ = await check.save(reopened, "meter22-reopen")
                v.require(reopened_json == after, "Meter boundary reopen differs")
            finally: await check.close(reopened)
        finally: await check.close(sid)
    v.require(all(path.read_bytes() == data for path, data in sources.items()), "Source archives changed")

if __name__ == "__main__":
    if "--case" not in sys.argv:
        sys.argv.extend(["--case", "preservation.timeline_meter_22"])
    raise SystemExit(v.main())
