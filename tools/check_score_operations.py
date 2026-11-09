"""Verify native score operations after the parent builds and wires score_edit."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
import uuid
import zipfile

import win32gui


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vocaloid_bridge.native_client import NativeClient, NativeError


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def require_pitch(points: list[dict], expected: dict[int, float], message: str) -> None:
    actual = {point["tick"]: point["value"] for point in points}
    require(len(actual) == len(points), message + ": duplicate native ticks")
    require(all(math.isfinite(value) for value in actual.values()), message + ": nonfinite value")
    require(all(tick in actual and math.isclose(actual[tick], value, rel_tol=0, abs_tol=0.001)
                for tick, value in expected.items()), message + ": " + json.dumps(points))


def reference_in(value: object, root_ref: str) -> str | None:
    if isinstance(value, dict):
        for key in ("ref", "$ref"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate != root_ref:
                return candidate
        for child in value.values():
            found = reference_in(child, root_ref)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = reference_in(child, root_ref)
            if found is not None:
                return found
    return None


def run(fixture: Path) -> dict:
    fixture = fixture.resolve(strict=True)
    original = fixture.read_bytes()
    foreground = win32gui.GetForegroundWindow()
    client = NativeClient(ROOT)
    sessions: set[str] = set()
    operations: set[str] = set()
    run_id = uuid.uuid4().hex[:12]
    session_id = ""

    def edit(operation: str, **options):
        response = client.request("score_edit", {
            "session_id": session_id, "operation": operation, "options": options,
        })
        require(response["native"] is True, f"{operation}: nonnative response")
        require(response["session_id"] == session_id, f"{operation}: wrong session")
        require(response["operation"] == operation, f"{operation}: wrong operation")
        operations.add(operation)
        return response["result"]

    try:
        opened = client.request("open", {"path": str(fixture)})
        session_id = opened["session_id"]
        sessions.add(session_id)
        root_ref = opened["root_ref"]
        tracks = edit("track.list")["tracks"]
        parts = edit("part.list")["parts"]
        require(bool(parts), "Fixture must contain a native MIDI or AI part")
        template = parts[0]
        kind = tracks[template["track_index"]]["type"]
        source_voice = edit("voice.get", track_index=template["track_index"], part_index=template["part_index"])
        voice_key = "ai_voice_bank_id" if template["ai"] else "voice_bank_id"
        require(bool(source_voice[voice_key]), "Fixture requires an assigned native voice")

        created = edit("track.create", type=kind, name="Score probe working track")
        track_index = created["track_index"]
        part = edit("part.create", track_index=track_index, start_tick=0, duration_tick=3840, name="Score probe part")
        part_index = part["part_index"]
        scope = {"track_index": track_index, "part_index": part_index}
        edit("voice.set", **scope, **{voice_key: source_voice[voice_key]})
        edit("part.update", **scope, name="Score probe edited part")
        edit("part.resize", **scope, duration_tick=4320)
        edit("part.move", **scope, start_tick=240)
        print(json.dumps({"phase": "before-note-add", "voice": edit("voice.get", **scope)}), flush=True)

        added = edit("note.add", **scope, start_tick=0, duration_tick=480, number=60, velocity=64,
                     lyric="a", phonemes="a", is_valid_phonemes=True)
        require(added["number"] == 60, "Native note insert readback failed")
        stale = reference_in(client.request("get", {"session_id": session_id, "member": "Tracks"}), root_ref)
        require(stale is not None, "Generic Tracks getter did not create a child reference")
        edit("note.update", **scope, note_index=0, number=62, lyric="la",
             expression={"Accent": added["expression"]["Accent"]})
        try:
            client.request("members", {"session_id": session_id, "ref": stale})
        except NativeError as error:
            require("expired" in str(error).lower() or "unknown" in str(error).lower(), str(error))
        else:
            raise AssertionError("Score mutation did not expire a native child reference")
        history = edit("history.status")
        require(history["can_undo"], "Native score mutation did not create undo history")
        edit("undo")
        require(edit("note.list", **scope)["notes"][0]["number"] == 60, "Native undo did not restore the note")
        edit("redo")
        require(edit("note.list", **scope)["notes"][0]["number"] == 62, "Native redo did not restore the edit")
        selected = edit("selection.set", **scope, target="note", indices=[0])
        require(selected["selected_indices"] == [0], "Native note selection setter failed")
        require(edit("selection.get", **scope, target="note")["selected_indices"] == [0], "Native selection readback failed")
        edit("selection.set", **scope, target="note", indices=[])

        duplicate = edit("note.duplicate", **scope, note_index=0, start_tick=960)
        edit("note.remove", **scope, note_index=duplicate["note_index"])
        extra = edit("note.add", **scope, start_tick=1440, duration_tick=480, number=67)
        split = edit("note.split", **scope, note_index=extra["note_index"], split_tick=1680)
        joined = edit("note.join", **scope, note_indices=[item["note_index"] for item in split["notes"]])
        extra_index = next(item["note_index"] for item in joined["notes"] if item["start_tick"] == 1440)
        edit("note.remove", **scope, note_index=extra_index)
        try:
            edit("note.update", **scope, note_index=0, number=1000)
        except NativeError:
            pass
        else:
            raise AssertionError("Out-of-range native note number was accepted")
        require(edit("note.list", **scope)["notes"][0]["number"] == 62, "Rejected edit changed native note state")

        controller_types = edit("controller.types", **scope)["types"]
        dynamics = next(item for item in controller_types if item["type"] == "Dynamics")
        controller_value = dynamics["default_value"]
        curve = edit("controller.set", **scope, type="Dynamics", replace=True,
                     points=[{"tick": 0, "value": controller_value}, {"tick": 480, "value": controller_value}])
        require(len(curve["points"]) == 2, "Native controller curve did not retain both points")
        edit("controller.list", **scope, type="Dynamics")
        edit("controller.remove", **scope, type="Dynamics", controller_index=1)

        edit("note.update", **scope, note_index=0, start_tick=120)
        expected_pitch = {0: 62.25, 120: 62.5, 240: 62.75}
        pitch = edit("pitch.set", **scope, note_index=0, replace=True,
                 points=[{"tick": tick, "value": value} for tick, value in expected_pitch.items()])
        require_pitch(pitch["points"], expected_pitch, "Native direct pitch anchors were not written")
        require(edit("pitch.list", **scope, note_index=0)["points"] == pitch["points"],
            "Pitch mutation returned a precommit snapshot")
        edit("undo")
        require(not edit("pitch.list", **scope, note_index=0)["points"], "Native undo did not remove direct pitch")
        edit("redo")
        require(edit("pitch.list", **scope, note_index=0)["points"] == pitch["points"],
            "Native redo did not restore direct pitch")
        partial = edit("pitch.clear", **scope, note_index=0, begin_tick=60, end_tick=180)
        require_pitch(partial["points"], {0: 62.25, 240: 62.75}, "Partial pitch clear changed outside anchors")
        require(all(not 60 <= point["tick"] < 180 for point in partial["points"]),
            "Partial pitch clear retained points in the requested range")
        cleared = edit("pitch.clear", **scope, note_index=0)
        require(not cleared["points"], "Native direct pitch clear did not remove the curve")
        expected_saved_pitch = {0: 62.25, 240: 62.75}
        saved_pitch = edit("pitch.set", **scope, note_index=0,
                   points=[{"tick": tick, "value": value} for tick, value in expected_saved_pitch.items()])["points"]
        require_pitch(saved_pitch, expected_saved_pitch, "Final pitch anchors differ")

        edit("tempo.list")
        tempo = edit("tempo.set", start_tick=960, bpm=133.25)
        require(tempo["bpm"] == 133.25, "Native tempo readback failed")
        edit("tempo.remove", tempo_index=tempo["tempo_index"])
        edit("tempo.set", start_tick=0, bpm=125.5)
        edit("time_signature.list")
        signature = edit("time_signature.set", bar=2, numerator=3, denominator=4)
        edit("time_signature.remove", time_signature_index=signature["time_signature_index"])
        edit("time_signature.set", bar=0, numerator=4, denominator=4)

        edit("sequence.get")
        title = "Native score verification " + run_id
        edit("sequence.update", title=title, global_bpm=125.5, global_tempo_enabled=False)
        edit("loop.get")
        loop = edit("loop.set", start_tick=0, end_tick=4320, enabled=True)
        require(loop["enabled"] and loop["end_tick"] == 4320, "Native loop readback failed")
        tuning = edit("tuning.get")
        edit("tuning.set", value=tuning["default_value"])

        part_copy = edit("part.duplicate", **scope, start_tick=5040)
        split_parts = edit("part.split", track_index=track_index, part_index=part_copy["part_index"], split_tick=2160)
        part_copy = edit("part.join", track_index=track_index,
                 part_indices=[item["part_index"] for item in split_parts["parts"]])
        edit("note.clear", track_index=track_index, part_index=part_copy["part_index"])
        edit("part.remove", track_index=track_index, part_index=part_copy["part_index"])
        edit("track.update", track_index=track_index, name="Score probe verified track", color=3, mute=True, solo=True)
        verified_track = edit("track.update", track_index=track_index, mute=False, solo=False)
        repeated_track = edit("track.update", track_index=track_index,
                              name="Score probe verified track", color=3, mute=False, solo=False)
        require(repeated_track == verified_track, "No-op track update changed native state")
        try:
            edit("track.update", track_index=track_index, name="Must not be applied", color=2245734)
        except NativeError:
            pass
        else:
            raise AssertionError("Packed RGB was accepted as a native palette index")
        require(edit("track.list")["tracks"][track_index] == verified_track,
                "Rejected track color changed native state")
        track_copy = edit("track.duplicate", track_index=track_index, name="Score probe duplicate")
        edit("track.remove", track_index=track_copy["track_index"])
        moved = edit("track.reorder", track_index=track_index, to_index=0)
        require(moved["track_index"] == 0, "Native track reorder failed")
        edit("track.reorder", track_index=0, to_index=track_index)
        other_kind = "Midi" if kind == "MidiAi" else "MidiAi"
        other = edit("track.create", type=other_kind, name="Score probe other MIDI kind")
        other_part = edit("part.create", track_index=other["track_index"], start_tick=0, duration_tick=3840)
        edit("part.remove", track_index=other["track_index"], part_index=other_part["part_index"])
        edit("track.remove", track_index=other["track_index"])
        audio = edit("track.create", type="Audio", name="Score probe empty audio track")
        edit("track.remove", track_index=audio["track_index"])
        edit("time.insert", start_tick=0, duration_tick=1920)
        edit("time.delete", start_tick=0, duration_tick=1920)
        restored_parts = edit("part.list", track_index=track_index)["parts"]
        require(restored_parts[0]["start_tick"] == 240, "Native insert/delete did not restore part timing")

        saved = client.request("save", {"session_id": session_id, "output_name": f"score-operations-{run_id}.vpr"})
        output_path = Path(saved["path"])
        require(output_path.is_relative_to(ROOT / "output"), "Native save escaped output")
        require(zipfile.is_zipfile(output_path), "Native save did not produce a VPR archive")
        with zipfile.ZipFile(output_path) as archive:
            saved_json = json.loads(archive.read("Project/sequence.json"))
        require(saved_json["title"] == title, "Saved native project title does not match")
        client.request("close", {"session_id": session_id})
        sessions.remove(session_id)
        reopened = client.request("open", {"path": str(output_path)})
        session_id = reopened["session_id"]
        sessions.add(session_id)
        require(edit("sequence.get")["title"] == title, "Reopened native project title differs")
        reopened_tracks = edit("track.list")["tracks"]
        reopened_index = next(item["track_index"] for item in reopened_tracks if item["name"] == "Score probe verified track")
        require(reopened_tracks[reopened_index]["color"] == 3 and not reopened_tracks[reopened_index]["mute"]
            and not reopened_tracks[reopened_index]["solo"], "Saved/reopened native track settings differ")
        reopened_part = edit("part.list", track_index=reopened_index)["parts"][0]
        reopened_scope = {"track_index": reopened_index, "part_index": reopened_part["part_index"]}
        notes = edit("note.list", **reopened_scope)["notes"]
        require(len(notes) == 1 and notes[0]["number"] == 62 and notes[0]["lyric"] == "la"
            and notes[0]["start_tick"] == 120, "Saved/reopened native note differs")
        reopened_pitch = edit("pitch.list", **reopened_scope, note_index=0)["points"]
        require_pitch(reopened_pitch, expected_saved_pitch, "Saved/reopened direct pitch anchors differ")
        require(reopened_pitch == saved_pitch, "Saved/reopened native direct pitch differs")
        require(bool(edit("controller.list", **reopened_scope, type="Dynamics")["points"]), "Saved/reopened controller is missing")
        client.request("close", {"session_id": session_id})
        sessions.remove(session_id)
        require(fixture.read_bytes() == original, "Original fixture bytes changed")
        require(win32gui.GetForegroundWindow() == foreground, "Foreground changed during score verification")
        require(len(operations) == 51, f"Expected 51 distinct operations, verified {len(operations)}")
        return {
            "native": True,
            "fixture": str(fixture),
            "saved_project": str(output_path),
            "operation_count": len(operations),
            "operations": sorted(operations),
            "saved_reopened": True,
            "original_unchanged": True,
            "stale_child_reference_rejected": True,
            "native_undo_redo": True,
            "native_pitch_undo_redo": True,
            "pitch_note_relative_ticks": True,
            "pitch_units": "fractional MIDI note numbers",
            "saved_pitch_points": reopened_pitch,
            "native_palette_noop_and_rejection": True,
            "foreground_unchanged": True,
            "synthesized_audio": False,
        }
    finally:
        for pending in list(sessions):
            try:
                client.request("close", {"session_id": pending, "discard": True})
            except NativeError:
                pass
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=ROOT / "artifacts/fixtures/editor-note.vpr")
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.fixture), indent=2))


if __name__ == "__main__":
    main()