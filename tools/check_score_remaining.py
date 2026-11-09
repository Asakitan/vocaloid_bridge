"""Focused native score smoke check; run only after rebuilding the host."""

import argparse
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vocaloid_bridge.native_client import NativeClient, NativeError


def followup(fixture):
    client = NativeClient(ROOT)
    session = None
    run_id = uuid.uuid4().hex[:12]
    try:
        session = client.request("open", {"path": str(fixture.resolve(strict=True))})["session_id"]

        def edit(operation, **options):
            return client.request("score_edit", {"session_id": session, "operation": operation, "options": options})["result"]

        def method(name, ref=None, args=None):
            args = args or []
            params = {"session_id": session, "ref": ref}
            available = client.request("members", params)["methods"]
            candidates = [m for m in available if m["member_id"].startswith(name + "(") and len(m["parameters"]) == len(args)]
            assert len(candidates) == 1, candidates
            return client.request("call", {**params, "member_id": candidates[0]["member_id"], "args": args})["value"]

        try:
            initial = edit("tempo.list")
            tempo_ref = method("GetTempo", args=[0])["$ref"]
            old = client.request("get", {"session_id": session, "ref": tempo_ref, "member": "Value"})["value"]
            client.request("set", {"session_id": session, "ref": tempo_ref, "member": "Value", "value": old + 100})
            assert edit("history.status")["staged"] is True
            result = edit("history.rollback")
            assert result["rolled_back"] is True and edit("tempo.list") == initial
            print("PASS staged tempo rollback", json.dumps(result), flush=True)
        except Exception as error:
            print("FAIL staged tempo rollback:", error, flush=True)
            if edit("history.status")["staged"]:
                edit("history.rollback")

        parts = edit("part.list")["parts"]
        part = parts[0]
        scope = {"track_index": part["track_index"], "part_index": part["part_index"]}
        print("render scope", scope, "sequence", edit("sequence.get"), flush=True)
        try:
            result = client.request("render_part", {"session_id": session, **scope, "output_name": "timing-clean-" + run_id + ".wav"})
            print("render result", result, flush=True)
        except Exception as error:
            print("FAIL clean render:", error, flush=True)
        notes = edit("note.list", **scope)["notes"]
        found = None
        for i in range(len(notes)):
            note = dict(scope, note_index=i)
            timing = edit("phoneme_timing.get", **note)
            print("phoneme timing", i, timing, flush=True)
            for j, (position, bounds) in enumerate(zip(timing["positions"], timing["ranges"])):
                target = position + 1 if position < bounds["end"] else position - 1
                if bounds["begin"] <= target <= bounds["end"]:
                    changed = edit("phoneme_timing.set", **note, phoneme_index=j, tick=target)
                    assert changed["positions"][j] == target
                    found = (note, j, position, target)
                    break
            if found:
                break
        if found is None:
            print("UNVERIFIED no movable phoneme positions", flush=True)
            return
        note, index, before, target = found
        saved = client.request("save", {"session_id": session, "output_name": "timing-edited-" + run_id + ".vpr"})
        client.request("close", {"session_id": session})
        session = client.request("open", {"path": saved["path"]})["session_id"]
        client.request("render_part", {"session_id": session, **scope, "output_name": "timing-reopened-" + run_id + ".wav"})
        timing = edit("phoneme_timing.get", **note)
        assert timing["positions"][index] == target, timing
        reset = edit("phoneme_timing.reset", **note, phoneme_index=index)
        assert reset["positions"][index] == before, reset
        print("PASS phoneme timing changed, saved/reopened and reset", found, flush=True)
    finally:
        if session is not None:
            client.request("close", {"session_id": session, "discard": True})
        client.close()


def deep(fixture):
    client = NativeClient(ROOT)
    session = None
    results = {}
    run_id = uuid.uuid4().hex[:12]
    try:
        opened = client.request("open", {"path": str(fixture.resolve(strict=True))})
        session = opened["session_id"]

        def edit(operation, **options):
            return client.request("score_edit", {"session_id": session, "operation": operation, "options": options})["result"]

        def probe(name, fn):
            try:
                results[name] = {"status": "pass", "detail": fn()}
            except Exception as exc:
                results[name] = {"status": "failed", "error": str(exc)}
            print(name, json.dumps(results[name], ensure_ascii=False), flush=True)

        def rollback():
            initial = edit("tempo.list")
            methods = client.request("members", {"session_id": session})["methods"]
            method_id = next(m["member_id"] for m in methods if m["member_id"].startswith("GetTempo(") and len(m["parameters"]) == 1)
            tempo = client.request("call", {"session_id": session, "member_id": method_id, "args": [0]})["value"]["$ref"]
            value = client.request("get", {"session_id": session, "ref": tempo, "member": "Value"})["value"]
            client.request("set", {"session_id": session, "ref": tempo, "member": "Value", "value": value + 100})
            assert edit("history.status")["staged"]
            response = edit("history.rollback")
            assert response["rolled_back"] and edit("tempo.list") == initial
            return response

        probe("staged_rollback", rollback)
        tracks = edit("track.list")["tracks"]
        parts = edit("part.list")["parts"]
        source = parts[0]
        source_scope = {"track_index": source["track_index"], "part_index": source["part_index"]}
        voice = edit("voice.get", **source_scope)
        voice_key = "ai_voice_bank_id" if source["ai"] else "voice_bank_id"
        track = edit("track.create", type=tracks[source["track_index"]]["type"], name="Deep score probe " + run_id)
        ti = track["track_index"]
        part = edit("part.create", track_index=ti, start_tick=0, duration_tick=1920, name="Deep probe")
        scope = {"track_index": ti, "part_index": part["part_index"]}
        edit("voice.set", **scope, **{voice_key: voice[voice_key]})
        edit("note.add", **scope, start_tick=0, duration_tick=960, number=60, velocity=64,
             lyric="a", phonemes="a", is_valid_phonemes=True)
        note = dict(scope, note_index=0)

        def changed_track():
            actual = edit("track.update", track_index=ti, bus_no=1, midi_recording=not track["midi_recording"])
            assert actual["bus_no"] == 1 and actual["midi_recording"] != track["midi_recording"], actual
            return actual

        probe("track_changed", changed_track)

        def changed_rate():
            initial = edit("sequence.get")["sample_rate"]
            rate = 48000 if initial != 48000 else 44100
            actual = edit("sequence.update", sample_rate=rate)
            assert actual["sample_rate"] == rate, actual
            return {"before": initial, "after": rate}

        probe("sample_rate_changed", changed_rate)

        def vibrato():
            value = edit("vibrato.set", **note, type="Normal_1", duration_tick=480,
                         depth=[{"tick": 0, "value": 50}, {"tick": 120, "value": 60}],
                         rate=[{"tick": 0, "value": 50}, {"tick": 120, "value": 60}])
            assert len(value["depth"]) == 2 and len(value["rate"]) == 2, value
            return value

        probe("vibrato_changed", vibrato)

        saved = client.request("save", {"session_id": session, "output_name": "score-deep-" + run_id + ".vpr"})
        client.request("close", {"session_id": session})
        session = client.request("open", {"path": saved["path"]})["session_id"]
        reopened = edit("track.list")["tracks"]
        ti = next(t["track_index"] for t in reopened if t["name"] == "Deep score probe " + run_id)
        note = {"track_index": ti, "part_index": 0, "note_index": 0}

        def verify_saved():
            expected = results["vibrato_changed"]
            actual = edit("vibrato.get", **note)
            if expected["status"] == "pass":
                assert actual["depth"] == expected["detail"]["depth"] and actual["rate"] == expected["detail"]["rate"], actual
            if results["track_changed"]["status"] == "pass":
                assert reopened[ti]["bus_no"] == results["track_changed"]["detail"]["bus_no"]
            if results["sample_rate_changed"]["status"] == "pass":
                assert edit("sequence.get")["sample_rate"] == results["sample_rate_changed"]["detail"]["after"]
            return {"vibrato": actual, "sample_rate": edit("sequence.get")["sample_rate"], "track": reopened[ti]}

        probe("save_reopen", verify_saved)
        print("RECEIPT", json.dumps(results, ensure_ascii=False), flush=True)
    finally:
        if session is not None:
            client.request("close", {"session_id": session, "discard": True})
        client.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--deep", action="store_true")
    parser.add_argument("--followup", action="store_true")
    args = parser.parse_args()
    if args.followup:
        followup(args.fixture)
        return
    if args.deep:
        deep(args.fixture)
        return
    client = NativeClient(ROOT)
    session = None
    try:
        session = client.request("open", {"path": str(args.fixture.resolve(strict=True))})["session_id"]

        def edit(operation, **options):
            return client.request("score_edit", {"session_id": session, "operation": operation, "options": options})["result"]

        zero = edit("time.convert", **{"from": "tick", "value": 0})
        assert zero["tick"] == 0 and zero["seconds"] == 0 and zero["sample"] == 0, zero
        assert edit("history.rollback")["staged"] is False
        tracks = edit("track.list")["tracks"]
        assert all("bus_no" in track and "midi_recording" in track for track in tracks)
        sequence = edit("sequence.get")
        assert "presend_time_sec" in sequence
        assert edit("sequence.update", sample_rate=sequence["sample_rate"])["sample_rate"] == sequence["sample_rate"]
        source = edit("part.list")["parts"][0]
        source_scope = {"track_index": source["track_index"], "part_index": source["part_index"]}
        voice = edit("voice.get", **source_scope)
        voice_key = "ai_voice_bank_id" if source["ai"] else "voice_bank_id"
        track = edit("track.create", type=tracks[source["track_index"]]["type"], name="Remaining score probe")
        ti = track["track_index"]
        edit("track.update", track_index=ti, bus_no=track["bus_no"], midi_recording=track["midi_recording"])
        part = edit("part.create", track_index=ti, start_tick=0, duration_tick=1920, name="Probe")
        scope = {"track_index": ti, "part_index": part["part_index"]}
        edit("voice.set", **scope, **{voice_key: voice[voice_key]})
        edit("note.add", **scope, start_tick=0, duration_tick=480, number=60, velocity=64,
             lyric="a", phonemes="a", is_valid_phonemes=True)
        result = edit("note.batch_update", **scope, note_indices=[0], transpose=1, lyrics=["a"])
        assert result["notes"][0]["number"] == 61
        try:
            edit("note.batch_update", **scope, note_indices=[0], transpose=127, lyrics=["bad"])
            raise AssertionError("invalid transpose was accepted")
        except NativeError:
            assert edit("note.list", **scope)["notes"][0]["lyric"] == "a"
        note = dict(scope, note_index=0)
        timing = edit("phoneme_timing.get", **note)
        assert "positions" in timing and "ranges" in timing
        for i, (position, bounds) in enumerate(zip(timing["positions"], timing["ranges"])):
            if bounds["begin"] <= position <= bounds["end"]:
                edit("phoneme_timing.set", **note, phoneme_index=i, tick=position)
                edit("phoneme_timing.reset", **note, phoneme_index=i)
                print("PASS: phoneme timing set/reset", i, flush=True)
                break
        vibrato = edit("vibrato.get", **note)
        assert "depth" in vibrato and "rate" in vibrato
        print("Native timing:", timing, "vibrato:", vibrato, flush=True)
        edit("vibrato.set", **note, ai_enabled=vibrato["ai_enabled"], type=vibrato["type"], duration_tick=vibrato["duration_tick"])
        saved = client.request("save", {"session_id": session, "output_name": f"score-remaining-{uuid.uuid4().hex[:12]}.vpr"})
        client.request("close", {"session_id": session})
        session = client.request("open", {"path": saved["path"]})["session_id"]
        reopened = edit("track.list")["tracks"]
        ti = next(t["track_index"] for t in reopened if t["name"] == "Remaining score probe")
        notes = edit("note.list", track_index=ti, part_index=0)["notes"]
        assert notes[0]["number"] == 61 and notes[0]["lyric"] == "a"
        print("PASS: time conversion, rollback status, track, sample rate, batch notes including rejection and save/reopen, phoneme/vibrato reads and vibrato enable")
    finally:
        if session is not None:
            client.request("close", {"session_id": session, "discard": True})
        client.close()


if __name__ == "__main__":
    main()
