"""Private AI clipboard transfers preserve project-scoped opaque members."""
import json
import wave
import zipfile

import verify_features as v


def fixture(check, label, sequence, members, extras):
    content = dict(members)
    content["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    content.update(extras)
    path = v.ROOT / "output" / check.output(label)
    with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in content.items():
            archive.writestr(name, payload)
    return path


@v.feature("preservation.clipboard_resources", "preservation", "score_compose", "project_open",
           "project_clipboard", "project_edit", "project_save", "project_audio")
async def clipboard_resources(check):
    seed = await check.call("score_compose", output_name=check.output("clipboard-resource-seed"),
                            title="Clipboard resource fixture", bpm=120,
                            notes=[{"start": 0, "duration": .5, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0},
                                   {"start": 1, "duration": .5, "pitch": 62, "lyric": "い", "phoneme": "i", "lang_id": 0}])
    await check.close(seed["native_session"]["session_id"])
    sequence, members = v.read_vpr(seed["path"])
    sequence["tracks"][0]["x_resource"] = "track"
    sequence["tracks"][0]["parts"][0]["x_resource"] = "part"
    for i, note in enumerate(sequence["tracks"][0]["parts"][0]["notes"]):
        note["x_resource"] = "note-" + str(i)
    extras = {"Project/probe/source.bin": b"source", "Project/probe/shared.bin": b"same"}
    source_path = fixture(check, "clipboard-resource-source", sequence, members, extras)
    original = source_path.read_bytes()
    source = (await check.call("project_open", path=str(source_path)))["session_id"]
    clips = []
    try:
        for options in ({"kind": "tracks", "indices": [0]},
                        {"kind": "parts", "indices": [0], "track_index": 0},
                        {"kind": "notes", "indices": [1], "track_index": 0, "part_index": 0}):
            clips.append((await check.call("project_clipboard", session_id=source, operation="copy", options=options))["clipboard_id"])
        cut = (await check.call("project_clipboard", session_id=source, operation="cut",
                                options={"kind": "notes", "indices": [1], "track_index": 0, "part_index": 0}))["clipboard_id"]
        clips.append(cut)
        cut_json, cut_path = await check.save(source, "clipboard-resource-cut")
        v.require(len(cut_json["tracks"][0]["parts"][0]["notes"]) == 1, "Cut note remained")
        _, cut_members = v.read_vpr(cut_path)
        v.require(all(cut_members[name] == value for name, value in extras.items()), "Cut lost project resources")
        await check.close(source)

        async with check.project() as base:
            target_json, base_path = await check.save(base, "clipboard-resource-target-seed")
        _, base_members = v.read_vpr(base_path)
        target_path = fixture(check, "clipboard-resource-target", target_json, base_members,
                              {"Project/probe/shared.bin": b"same", "Project/probe/target.bin": b"target"})
        target = (await check.call("project_open", path=str(target_path)))["session_id"]
        try:
            await check.call("project_clipboard", session_id=target, operation="paste",
                             options={"clipboard_id": clips[0], "offset_tick": 960})
            pasted, path = await check.save(target, "clipboard-resources-pasted")
            _, written = v.read_vpr(path)
            v.require(all(written[name] == value for name, value in extras.items()) and
                      written["Project/probe/target.bin"] == b"target", "Pasted resource set changed")
            v.require(pasted["tracks"][0]["x_resource"] == "track", "Track extension lost")
            await check.edit(target, "undo")
            _, path = await check.save(target, "clipboard-resources-undo")
            _, undone = v.read_vpr(path)
            v.require("Project/probe/source.bin" not in undone and undone["Project/probe/shared.bin"] == b"same",
                      "Clipboard undo changed original resources")
            await check.edit(target, "redo")
            await check.call("project_clipboard", session_id=target, operation="paste",
                             options={"clipboard_id": clips[1], "track_index": 0, "offset_tick": 9600})
            await check.call("project_clipboard", session_id=target, operation="paste",
                             options={"clipboard_id": clips[2], "track_index": 0, "part_index": 0, "offset_tick": 3000})
            await check.call("project_clipboard", session_id=target, operation="paste",
                             options={"clipboard_id": clips[3], "track_index": 0, "part_index": 0, "offset_tick": 5000})
            pasted, path = await check.save(target, "clipboard-resources-children")
            parts = pasted["tracks"][0]["parts"]
            v.require(parts[1]["x_resource"] == "part" and
                      sum(n.get("x_resource") == "note-1" for n in parts[0]["notes"]) == 3,
                      "Child extension metadata changed")
            reopened = (await check.call("project_open", path=str(path)))["session_id"]
            try:
                _, path = await check.save(reopened, "clipboard-resources-reopened")
                _, written = v.read_vpr(path)
                v.require(all(written[name] == value for name, value in extras.items()), "Reopen lost resources")
            finally:
                await check.close(reopened)
        finally:
            await check.close(target)

        for label, conflict in (("bytes", {"Project/probe/source.bin": b"different"}),
                                ("case", {"Project/probe/SOURCE.bin": b"source"}),
                                ("prefix", {"Project/probe/source.bin/child": b"source"})):
            conflicting = fixture(check, "clipboard-resource-conflict-" + label, target_json, base_members, conflict)
            target = (await check.call("project_open", path=str(conflicting)))["session_id"]
            try:
                before = await check.call("project_status", session_id=target)
                await check.rejected("project_clipboard", "opaque member.*conflict", session_id=target, operation="paste",
                                     options={"clipboard_id": clips[0]})
                v.require(await check.call("project_status", session_id=target) == before,
                          "Resource conflict changed the target")
            finally:
                await check.close(target)

        plain = json.loads(json.dumps(sequence))
        track = plain["tracks"][0]
        track.pop("x_resource")
        part = track["parts"][0]
        part.pop("x_resource")
        for note in part["notes"]:
            note.pop("x_resource")
        plain_path = fixture(check, "clipboard-resource-plain", plain, members, extras)
        plain_id = (await check.call("project_open", path=str(plain_path)))["session_id"]
        clip = (await check.call("project_clipboard", session_id=plain_id, operation="copy",
                                 options={"kind": "tracks", "indices": [0]}))["clipboard_id"]
        clips.append(clip)
        await check.close(plain_id)
        async with check.project() as target:
            await check.call("project_clipboard", session_id=target, operation="paste", options={"clipboard_id": clip})
            _, path = await check.save(target, "clipboard-resources-no-entity-extensions")
            _, written = v.read_vpr(path)
            v.require(all(written[name] == value for name, value in extras.items()), "Plain paste lost resources")

        wav = v.ROOT / "output" / check.output("clipboard-native-collision", ".wav")
        with wave.open(str(wav), "wb") as audio:
            audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(44100)
            audio.writeframes(b"\x00\x00" * 4410)
        async with check.project() as target:
            await check.audio(target, "import_audio", path=str(wav), name="Native collision", position_tick=0)
            target_json, target_path = await check.save(target, "clipboard-native-target")
            _, target_members = v.read_vpr(target_path)
            audio_names = [part["wav"][key] for track in target_json.get("tracks", [])
                           for part in track.get("parts", []) if isinstance(part.get("wav"), dict)
                           for key in ("name", "processedName") if part["wav"].get(key)]
            collisions = ["Project/Audio/" + name for name in audio_names if "Project/Audio/" + name in target_members]
            v.require(bool(collisions), "Native target has no audio member", audio_names)
            collision = collisions[0]
            collision_source = fixture(check, "clipboard-native-collision-source", plain, members,
                                       {collision: b"opaque collision"})
            collision_id = (await check.call("project_open", path=str(collision_source)))["session_id"]
            collision_clip = (await check.call("project_clipboard", session_id=collision_id, operation="copy",
                                               options={"kind": "tracks", "indices": [0]}))["clipboard_id"]
            clips.append(collision_clip)
            await check.close(collision_id)
            before = await check.call("project_status", session_id=target)
            await check.rejected("project_clipboard", "collides with retained member", session_id=target,
                                 operation="paste", options={"clipboard_id": collision_clip})
            v.require(await check.call("project_status", session_id=target) == before,
                      "Native output collision changed the target")
            _, protected_path = await check.save(target, "clipboard-native-protected")
            v.require(v.read_vpr(protected_path)[1][collision] == target_members[collision],
                      "Native audio member changed after rejected paste")
        v.require(source_path.read_bytes() == original, "Clipboard changed original VPR")
    finally:
        for clip in clips:
            await check.call("project_clipboard", operation="clear", options={"clipboard_id": clip})


if __name__ == "__main__":
    raise SystemExit(v.main())
