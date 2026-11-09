"""Verify file-level tempo and controller metadata follow selected ticks."""
import json
from pathlib import Path
import sys
import zipfile

import verify_features as v

KEY = "x_file_event_24"


async def fixture(check):
    seed = await check.call("score_compose", output_name=check.output("file-events-seed"), title="File events", bpm=120,
                            notes=[{"start": 0, "duration": .5, "pitch": 60,
                                    "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    sid = seed["native_session"]["session_id"]
    try:
        for tick, bpm in ((480, 130), (960, 140)):
            await check.edit(sid, "tempo.set", start_tick=tick, bpm=bpm)
        await check.edit(sid, "controller.set", track_index=0, part_index=0, type="Dynamics", replace=True,
                         points=[{"tick": 60, "value": 30}, {"tick": 180, "value": 64}, {"tick": 300, "value": 80}])
        sequence, path = await check.save(sid, "file-events-native")
    finally:
        await check.close(sid)
    _, members = v.read_vpr(path)
    sequence["x_file_root_24"] = {"keep": True}
    for event in sequence["masterTrack"]["tempo"]["events"]:
        event[KEY] = {"kind": "tempo", "tick": event["pos"]}
    lane = next(item for item in sequence["tracks"][0]["parts"][0]["controllers"] if item["name"] == "dynamics")
    for event in lane["events"]:
        event[KEY] = {"kind": "controller", "tick": event["pos"]}
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("file-events-extended")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return source, source.read_bytes()


def tempo_events(sequence):
    return [(event["pos"], event["value"], event.get(KEY)) for event in sequence["masterTrack"]["tempo"]["events"]]


def controller_events(sequence):
    lane = next(item for item in sequence["tracks"][0]["parts"][0]["controllers"] if item["name"] == "dynamics")
    return [(event["pos"], event["value"], event.get(KEY)) for event in lane["events"]]


def duplicate_fixture(check, source, kind):
    sequence, members = v.read_vpr(source)
    events = (sequence["masterTrack"]["tempo"]["events"] if kind == "tempo" else
              next(item["events"] for item in sequence["tracks"][0]["parts"][0]["controllers"] if item["name"] == "dynamics"))
    events.append(json.loads(json.dumps(events[0])))
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    path = v.ROOT / "output" / check.output("file-events-duplicate-" + kind)
    with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return path, path.read_bytes()


async def native_roundtrip(check, path, expected, extract):
    sid = (await check.call("project_open", path=str(path)))["session_id"]
    try:
        saved, _ = await check.save(sid, "file-events-reopened")
        v.require(extract(saved) == expected and saved["x_file_root_24"] == {"keep": True},
                  "Native save changed file event metadata", extract(saved))
    finally:
        await check.close(sid)


@v.feature("preservation.file_tempo_identity_24", "preservation", "score_compose", "score_tempo", "project_open", "project_save")
async def file_tempo_identity(check):
    v.require("Retained ticks keep their unknown event fields" in (check.tools["score_tempo"].description or ""),
              "Tempo tool description omits the event metadata policy")
    source, original = await fixture(check)
    result = await check.call("score_tempo", path=str(source), output_name=check.output("file-tempo-edited"),
                              events=[{"start": 0, "bpm": 121}, {"start": 2, "bpm": 141}, {"start": 3, "bpm": 150}])
    path = Path(result["path"])
    sequence, _ = v.read_vpr(path)
    expected = [(0, 12100, {"kind": "tempo", "tick": 0}),
                (960, 14100, {"kind": "tempo", "tick": 960}), (1440, 15000, None)]
    v.require(tempo_events(sequence) == expected, "Tempo extension copied to a new or different event", tempo_events(sequence))
    await native_roundtrip(check, path, expected, tempo_events)
    v.require(source.read_bytes() == original, "Tempo file edit changed source archive")
    duplicate, duplicate_bytes = duplicate_fixture(check, source, "tempo")
    output_name = check.output("file-tempo-duplicate-rejected")
    await check.rejected("score_tempo", "existing tempo event positions must be distinct", path=str(duplicate),
                         output_name=output_name, events=[{"start": 0, "bpm": 120}])
    v.require(duplicate.read_bytes() == duplicate_bytes and not (v.ROOT / "output" / output_name).exists(),
              "Rejected duplicate tempo changed input or produced output")


@v.feature("preservation.file_curve_identity_24", "preservation", "score_compose", "score_curve", "project_open", "project_save")
async def file_curve_identity(check):
    v.require("Retained ticks keep their unknown event fields" in (check.tools["score_curve"].description or ""),
              "Curve tool description omits the event metadata policy")
    source, original = await fixture(check)
    result = await check.call("score_curve", path=str(source), output_name=check.output("file-curve-edited"),
                              controller="dynamics", track_index=0, part_index=0,
                              events=[{"start": .125, "value": 31}, {"start": .625, "value": 81},
                                      {"start": .875, "value": 90}])
    path = Path(result["path"])
    sequence, _ = v.read_vpr(path)
    expected = [(60, 31, {"kind": "controller", "tick": 60}),
                (300, 81, {"kind": "controller", "tick": 300}), (420, 90, None)]
    v.require(controller_events(sequence) == expected, "Controller extension copied to a new or different event", controller_events(sequence))
    await native_roundtrip(check, path, expected, controller_events)
    v.require(source.read_bytes() == original, "Curve file edit changed source archive")
    duplicate, duplicate_bytes = duplicate_fixture(check, source, "controller")
    output_name = check.output("file-curve-duplicate-rejected")
    await check.rejected("score_curve", "existing controller event positions must be distinct", path=str(duplicate),
                         output_name=output_name, controller="dynamics", events=[{"start": 0, "value": 64}])
    v.require(duplicate.read_bytes() == duplicate_bytes and not (v.ROOT / "output" / output_name).exists(),
              "Rejected duplicate controller changed input or produced output")


if __name__ == "__main__":
    if "--case" not in sys.argv:
        sys.argv.extend(["--case", "preservation.file_tempo_identity_24", "--case", "preservation.file_curve_identity_24"])
    raise SystemExit(v.main())
