"""Candidate score edits with extended track automation; private AI fixtures only."""
import json
import sys
import zipfile
import verify_features as v

KEY = "x_track_edits_22"
CASES = {
    "track.create": {"type": "MidiAi", "name": "New AI"},
    "part.create": {"track_index": 1, "start_tick": 1920, "duration_tick": 960},
    "part.update": {"track_index": 0, "part_index": 0, "name": "Changed"},
    "part.move": {"track_index": 0, "part_index": 0, "start_tick": 240},
    "part.resize": {"track_index": 0, "part_index": 0, "duration_tick": 2400},
    "note.add": {"track_index": 0, "part_index": 0, "start_tick": 960, "duration_tick": 240, "number": 65, "lang_id": 0, "lyric": "あ", "phonemes": "a"},
    "note.update": {"track_index": 0, "part_index": 0, "note_index": 0, "number": 62},
    "note.batch_update": {"track_index": 0, "part_index": 0, "note_indices": [0], "transpose": 2},
}


def register(operation, options):
    @v.feature("preservation.track_edits_22." + operation, "preservation", "project_create", "project_edit", "project_save", "project_open", "project_clone")
    async def case(check):
        async with check.project() as seed:
            for name in ("AI A", "AI B"):
                t = (await check.edit(seed, "track.create", type="MidiAi", name=name))["track_index"]
                await check.edit(seed, "part.create", track_index=t, start_tick=0, duration_tick=1920, name="Seed")
                await check.edit(seed, "note.add", track_index=t, part_index=0, start_tick=0, duration_tick=480, number=60, lang_id=0, lyric="あ", phonemes="a")
                for scope in ("track_volume", "track_pan"):
                    spec = await check.edit(seed, "automation.list", scope=scope, track_index=t)
                    await check.edit(seed, "automation.set", scope=scope, track_index=t,
                                     points=[{"tick": 480, "value": spec["minimum"]}])
            _, seed_path = await check.save(seed, "track-edit-seed")
        sequence, members = v.read_vpr(seed_path)
        for index, track in enumerate(sequence["tracks"]):
            for prop in ("volume", "panpot"):
                for event in track[prop]["events"]:
                    event[KEY] = {"owner": index, "lane": prop, "tick": event["pos"]}
        members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
        source = v.ROOT / "output" / check.output("track-edit-source")
        with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, payload in members.items():
                archive.writestr(name, payload)
        original = source.read_bytes()
        def lanes(project):
            return [(track["name"], [(prop, track[prop]["events"]) for prop in ("volume", "panpot")])
                    for track in project["tracks"][:2]]
        sid = (await check.call("project_open", path=str(source)))["session_id"]
        try:
            before, _ = await check.save(sid, "track-edit-before")
            expected = lanes(before)
            await check.edit(sid, operation, **options)
            changed, _ = await check.save(sid, "track-edit-changed")
            v.require(lanes(changed) == expected, "Track automation owners or events changed")
            v.require(changed["tracks"] != before["tracks"], "Expected score mutation absent")
            if operation == "track.create":
                v.require(len(changed["tracks"]) == 3 and KEY not in json.dumps(changed["tracks"][2]), "New track inherited metadata")
            await check.edit(sid, "undo")
            undone, _ = await check.save(sid, "track-edit-undo")
            v.require(undone["tracks"] == before["tracks"], "Undo differs from pre-edit track state")
            await check.edit(sid, "redo")
            redone, path = await check.save(sid, "track-edit-redo")
            v.require(redone["tracks"] == changed["tracks"], "Redo differs from edited track state")
            clone = (await check.call("project_clone", session_id=sid))["session_id"]
            try:
                cloned, _ = await check.save(clone, "track-edit-clone")
                v.require(cloned["tracks"] == changed["tracks"], "Clone differs")
            finally:
                await check.close(clone)
            reopened = (await check.call("project_open", path=str(path)))["session_id"]
            try:
                reopened_json, _ = await check.save(reopened, "track-edit-reopen")
                v.require(reopened_json["tracks"] == changed["tracks"], "Reopen differs")
            finally:
                await check.close(reopened)
            history = await check.edit(sid, "history.status")
            await check.rejected("project_edit", "project_preservation", session_id=sid, operation="track.duplicate", options={"track_index": 0})
            v.require(await check.edit(sid, "history.status") == history, "Rejected operation changed history")
            await check.edit(sid, "undo")
            await check.edit(sid, operation, **options)
            branched, _ = await check.save(sid, "track-edit-branch")
            v.require(branched["tracks"] == changed["tracks"], "Undo branch differs")
        finally:
            await check.close(sid)
        v.require(source.read_bytes() == original, "Source archive changed")
    return case

for operation, options in CASES.items():
    register(operation, options)

if __name__ == "__main__":
    if "--case" not in sys.argv:
        for operation in CASES:
            sys.argv.extend(["--case", "preservation.track_edits_22." + operation])
    raise SystemExit(v.main())
