"""Compare Robot mode on separate private native hosts with distinct caches."""

import json
import argparse
from pathlib import Path
import sys
import uuid
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vocaloid_bridge.native_client import NativeClient


def concurrent():
    run = uuid.uuid4().hex[:12]
    client = NativeClient(ROOT)
    sessions = []
    try:
        ping = client.request("ping")
        a = client.request("open", {"path": str(ROOT / "output/feature-7085da10d352-001-robot-seed.vpr")})["session_id"]
        sessions.append(a)
        selected = {"track_index": 0, "part_index": 0}
        baseline = client.request("render_part", {"session_id": a, **selected, "output_name": f"robot-concurrent-{run}-baseline.wav"})
        b = client.request("create", {"title": "Robot concurrent audio probe"})["session_id"]
        sessions.append(b)
        source = ROOT / "output/background-demo-31c27fd842.wav"
        imported = client.request("audio_op", {"session_id": b, "operation": "import_audio", "options": {
            "path": str(source), "name": "Concurrent audio probe", "position_tick": 0}})
        changed = client.request("score_edit", {"session_id": a, "operation": "performance.set", "options": {
            **selected, "robot_mode": "Hard", "bypass": {"RobotVoice": False}}})["result"]
        hard = client.request("render_part", {"session_id": a, **selected, "output_name": f"robot-concurrent-{run}-hard.wav"})
        exported = client.request("audio_op", {"session_id": b, "operation": "export_audio", "options": {
            "track_index": imported["track_index"], "part_index": imported["part_index"], "original": True,
            "output_name": f"robot-concurrent-{run}-audio.wav"}})
        def read(path):
            with wave.open(str(path), "rb") as wav:
                return (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()), wav.readframes(wav.getnframes())
        base_format, base_pcm = read(baseline["path"])
        hard_format, hard_pcm = read(hard["path"])
        source_format, source_pcm = read(source)
        export_format, export_pcm = read(exported["path"])
        result = {"ping": ping, "baseline": baseline, "hard": hard, "changed": changed,
            "imported": imported, "exported": exported, "same_robot_format": base_format == hard_format,
            "robot_pcm_changed": base_pcm != hard_pcm, "source_format": source_format,
            "export_format": export_format, "audio_pcm_equal": source_pcm == export_pcm}
        destination = ROOT / "artifacts" / f"robot-concurrent-{run}.json"
        destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"receipt": str(destination), "same_robot_format": result["same_robot_format"],
                          "robot_pcm_changed": result["robot_pcm_changed"], "audio_pcm_equal": result["audio_pcm_equal"]}))
        assert result["same_robot_format"] and result["robot_pcm_changed"] and result["audio_pcm_equal"], result
    finally:
        for session in reversed(sessions):
            client.request("close", {"session_id": session, "discard": True})
        client.close()


def stage_probe():
    run = uuid.uuid4().hex[:12]
    client = NativeClient(ROOT)
    session = None
    try:
        fixture = ROOT / "output/feature-7085da10d352-001-robot-seed.vpr"
        session = client.request("open", {"path": str(fixture)})["session_id"]
        def call(name, args, ref=None):
            params = {"session_id": session, "ref": ref}
            methods = client.request("members", params)["methods"]
            candidates = [m for m in methods if m["member_id"].startswith(name + "(") and len(m["parameters"]) == len(args)]
            assert len(candidates) == 1, candidates
            return client.request("call", {**params, "member_id": candidates[0]["member_id"], "args": args})
        def history():
            return client.request("score_edit", {"session_id": session, "operation": "history.status", "options": {}})["result"]
        track = call("GetTrack", [0])["value"]["$ref"]
        part = call("GetPart", [0], track)["value"]["$ref"]
        effect = client.request("get", {"session_id": session, "ref": part, "member": "RobotVoiceEffect"})["value"]["$ref"]
        result = {"before": history()}
        result["effect_mode_call"] = call("SetRobotVoiceMode", ["Hard"], effect)
        result["after_effect_mode"] = history()
        if result["after_effect_mode"]["staged"]:
            result["mode_rollback"] = client.request("score_edit", {"session_id": session, "operation": "history.rollback", "options": {}})["result"]
        track = call("GetTrack", [0])["value"]["$ref"]
        part = call("GetPart", [0], track)["value"]["$ref"]
        result["bypass_call"] = call("SetBypass", ["RobotVoice", False], part)
        result["after_bypass"] = history()
        if result["after_bypass"]["staged"]:
            result["rollback"] = client.request("score_edit", {"session_id": session, "operation": "history.rollback", "options": {}})["result"]
        destination = ROOT / "artifacts" / f"robot-stage-{run}.json"
        destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"receipt": str(destination), "result": result}, ensure_ascii=False))
    finally:
        if session:
            client.request("close", {"session_id": session, "discard": True})
        client.close()


def transition(edit_first=False):
    run = uuid.uuid4().hex[:12]
    client = NativeClient(ROOT)
    session = None
    results, samples = {}, {}
    try:
        results["host"] = client.request("ping")
        for label, name in (("baseline", "001-robot-seed"), ("hard", "003-robot-voice")):
            fixture = ROOT / "output" / f"feature-7085da10d352-{name}.vpr"
            if label == "hard" and edit_first:
                fixture = Path(results["edited_saved_project"])
            session = client.request("open", {"path": str(fixture)})["session_id"]
            def method(name, ref=None):
                p = {"session_id": session, "ref": ref}
                matches = [m for m in client.request("members", p)["methods"] if m["member_id"].startswith(name + "(") and len(m["parameters"]) == 1]
                assert len(matches) == 1, matches
                return client.request("call", {**p, "member_id": matches[0]["member_id"], "args": [0]})["value"]["$ref"]
            track = method("GetTrack")
            part = method("GetPart", track)
            def get(member):
                return client.request("get", {"session_id": session, "ref": part, "member": member})["value"]
            def state():
                result = {member: get(member) for member in ("HasValidRenderedWave", "HasValidRenderedScore")}
                result["is_finished"] = client.request("get", {"session_id": session, "member": "IsFinishedRendering"})["value"]
                progress = get("RendererProgress")
                if isinstance(progress, dict) and "$ref" in progress:
                    progress = {name: client.request("get", {"session_id": session, "ref": progress["$ref"], "member": name})["value"]
                                for name in ("FirstEnd", "SecondBegin", "SecondEnd", "IsPaused", "BlockRenderingEnabled")}
                result["progress"] = progress
                return result
            before = state()
            render = client.request("render_part", {"session_id": session, "track_index": 0, "part_index": 0,
                "output_name": f"robot-transition-{run}-{label}.wav"})
            after = state()
            with wave.open(render["path"], "rb") as wav:
                samples[label] = wav.readframes(wav.getnframes())
            results[label] = {"fixture": str(fixture), "before": before, "after": after, "render": render}
            if label == "baseline" and edit_first:
                results["edit"] = client.request("score_edit", {"session_id": session, "operation": "performance.set",
                    "options": {"track_index": 0, "part_index": 0, "robot_mode": "Hard", "bypass": {"RobotVoice": False}}})["result"]
                track = method("GetTrack")
                part = method("GetPart", track)
                results["after_edit"] = state()
                saved = client.request("save", {"session_id": session, "output_name": f"robot-transition-{run}-edited.vpr"})
                results["edited_saved_project"] = saved["path"]
            client.request("close", {"session_id": session, "discard": True})
            session = None
        results["same_pcm_bytes"] = samples["baseline"] == samples["hard"]
        destination = ROOT / "artifacts" / f"robot-transition-{run}.json"
        destination.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"receipt": str(destination), "result": results}, ensure_ascii=False))
    finally:
        if session:
            client.request("close", {"session_id": session, "discard": True})
        client.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--transition", action="store_true")
    parser.add_argument("--edit-transition", action="store_true")
    parser.add_argument("--stage", action="store_true")
    parser.add_argument("--concurrent", action="store_true")
    args = parser.parse_args()
    if args.concurrent:
        concurrent()
        return
    if args.stage:
        stage_probe()
        return
    if args.transition or args.edit_transition:
        transition(args.edit_transition)
        return
    run = uuid.uuid4().hex[:12]
    fixtures = {
        "baseline": ROOT / "output/feature-7085da10d352-001-robot-seed.vpr",
        "hard": ROOT / "output/feature-7085da10d352-003-robot-voice.vpr",
    }
    records = {}
    samples = {}
    for label, fixture in fixtures.items():
        client = NativeClient(ROOT)
        session = None
        try:
            ping = client.request("ping")
            opened = client.request("open", {"path": str(fixture.resolve(strict=True))})
            session = opened["session_id"]

            def edit(operation, **options):
                return client.request("score_edit", {"session_id": session, "operation": operation, "options": options})["result"]

            selected = {"track_index": 0, "part_index": 0}
            performance = edit("performance.get", **selected)
            notes = edit("note.list", **selected)
            render = client.request("render_part", {"session_id": session, **selected,
                "output_name": f"robot-isolated-{run}-{label}.wav"})
            with wave.open(render["path"], "rb") as wav:
                params = {"channels": wav.getnchannels(), "width": wav.getsampwidth(),
                          "rate": wav.getframerate(), "frames": wav.getnframes()}
                samples[label] = wav.readframes(wav.getnframes())
            records[label] = {"cache_namespace": ping.get("cache_namespace"),
                "fixture": str(fixture), "performance": performance, "notes": notes,
                "render": render, "pcm": params}
        finally:
            if session is not None:
                client.request("close", {"session_id": session, "discard": True})
            client.close()
    records["comparison"] = {
        "distinct_cache_namespaces": records["baseline"]["cache_namespace"] != records["hard"]["cache_namespace"],
        "same_pcm_format": records["baseline"]["pcm"] == records["hard"]["pcm"],
        "same_pcm_bytes": samples["baseline"] == samples["hard"],
    }
    destination = ROOT / "artifacts" / f"robot-isolated-{run}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"receipt": str(destination), "comparison": records["comparison"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
