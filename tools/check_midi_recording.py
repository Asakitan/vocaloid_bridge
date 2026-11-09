"""Real MCP synthetic-input MIDI recording probe; opens no MIDI device."""

import asyncio
import argparse
import json
import os
from pathlib import Path
import sys
import uuid

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


async def main(transport_device_id=None):
    run = uuid.uuid4().hex[:12]
    fixture = ROOT / "vocaloid_bridge/templates/ai-starter.vpr"
    original = fixture.read_bytes()
    args = StdioServerParameters(command=sys.executable, args=["-m", "vocaloid_bridge"], cwd=str(ROOT),
        env={**os.environ, "VOCALOID_WORKSPACE": str(ROOT), "PYTHONUTF8": "1"})
    receipt = {"mode": "synthetic", "hardware_opened": False, "fixture": str(fixture)}
    session = None
    async with stdio_client(args) as (reader, writer):
        async with ClientSession(reader, writer) as client:
            await client.initialize()
            async def call(tool, **arguments):
                response = await client.call_tool(tool, arguments)
                if response.isError or response.structuredContent is None:
                    raise RuntimeError(f"{tool}: {response.content}")
                return response.structuredContent
            async def midi(operation, **options):
                return (await call("project_midi", session_id=session, operation=operation, options=options))["result"]
            async def edit(operation, **options):
                return (await call("project_edit", session_id=session, operation=operation, options=options))["result"]
            try:
                receipt["devices"] = (await call("project_midi", operation="devices", options={}))["result"]
                session = (await call("project_open", path=str(fixture)))["session_id"]
                await edit("note.clear", track_index=0, part_index=0)
                await edit("track.update", track_index=0, midi_recording=True)
                scope = {"mode": "synthetic", "track_index": 0, "part_index": 0,
                         "start_tick": 0, "lyric": "あ", "phonemes": "a", "lang_id": 0}
                receipt["started"] = await midi("start", **scope)
                assert receipt["started"]["mode"] == "synthetic" and receipt["started"]["active"]
                response = await client.call_tool("project_edit", {"session_id": session, "operation": "note.add",
                    "options": {"track_index": 0, "part_index": 0, "start_tick": 0, "duration_tick": 100}})
                assert response.isError, "An edit was allowed while recording"
                events = [
                    {"elapsed_ms": 100, "channel": 0, "number": 60, "velocity": 91, "on": True},
                    {"elapsed_ms": 600, "channel": 0, "number": 60, "velocity": 0, "on": False},
                    {"elapsed_ms": 700, "channel": 1, "number": 64, "velocity": 73, "on": True},
                    {"elapsed_ms": 1000, "channel": 1, "number": 64, "velocity": 0, "on": False},
                    {"elapsed_ms": 1100, "channel": 2, "number": 67, "velocity": 64, "on": True},
                    {"elapsed_ms": 1250, "channel": 2, "number": 70, "velocity": 0, "on": False},
                ]
                await midi("synthetic_events", events=events)
                receipt["stopped"] = await midi("stop", end_ms=1400)
                assert receipt["stopped"]["inserted"] == 3 and receipt["stopped"]["closed_on_stop"] == 1
                assert receipt["stopped"]["unmatched_off"] == 1
                notes = (await edit("note.list", track_index=0, part_index=0))["notes"]
                expected = [(96, 480, 60, 91), (672, 288, 64, 73), (1056, 288, 67, 64)]
                actual = [(n["start_tick"], n["duration_tick"], n["number"], n["velocity"]) for n in notes]
                assert actual == expected, actual
                receipt["notes"] = actual
                saved = await call("project_save", session_id=session, output_name=f"midi-synthetic-{run}.vpr")
                # Prevalidation failure: second completed note extends beyond this part.
                await midi("start", **scope)
                invalid = [
                    {"elapsed_ms": 0, "channel": 0, "number": 72, "velocity": 64, "on": True},
                    {"elapsed_ms": 100, "channel": 0, "number": 72, "velocity": 0, "on": False},
                    {"elapsed_ms": 9000, "channel": 0, "number": 73, "velocity": 64, "on": True},
                    {"elapsed_ms": 10000, "channel": 0, "number": 73, "velocity": 0, "on": False},
                ]
                await midi("synthetic_events", events=invalid)
                rejected = await client.call_tool("project_midi", {"session_id": session, "operation": "stop", "options": {"end_ms": 10000}})
                assert rejected.isError, "Out-of-part recording was accepted"
                assert (await edit("note.list", track_index=0, part_index=0))["notes"] == notes
                await midi("cancel")
                receipt["invalid_batch_no_partial_write"] = True
                if transport_device_id:
                    async def audio(operation, **options):
                        return await call("project_audio", session_id=session, operation=operation, options=options)
                    prepared = await audio("transport_prepare", device_id=transport_device_id, sample_rate=44100,
                                           buffer_samples=2048, mute_output=True)
                    assert prepared["muted"] and prepared["device_id"] == transport_device_id
                    await audio("transport_seek", seconds=4.0)
                    await asyncio.sleep(0.15)
                    await audio("transport_play")
                    await asyncio.sleep(0.15)
                    synced_scope = {k: v for k, v in scope.items() if k != "start_tick"}
                    receipt["sync_start"] = await midi("start", **synced_scope, sync_to_transport=True)
                    assert receipt["sync_start"]["sync_to_transport"] and receipt["sync_start"]["start_seconds"] >= 3.5
                    paused = await client.call_tool("project_audio", {"session_id": session, "operation": "transport_stop", "options": {}})
                    assert paused.isError, "Transport pause was allowed during synchronized recording"
                    await asyncio.sleep(0.3)
                    await midi("synthetic_events", events=[
                        {"elapsed_ms": 50, "channel": 0, "number": 72, "velocity": 77, "on": True},
                        {"elapsed_ms": 200, "channel": 0, "number": 72, "velocity": 0, "on": False}])
                    receipt["sync_stop"] = await midi("stop", end_ms=250)
                    assert receipt["sync_stop"]["inserted"] == 1
                    assert not (await audio("transport_status"))["prepared"]
                    final = (await edit("note.list", track_index=0, part_index=0))["notes"]
                    recorded = next(n for n in final if n["number"] == 72)
                    expected = round((receipt["sync_start"]["start_seconds"] + 0.05) * 960)
                    assert abs(recorded["start_tick"] - expected) <= 1 and recorded["velocity"] == 77, recorded
                    receipt["sync_recorded_note"] = {"start_tick": recorded["start_tick"], "expected_tick": expected,
                                                       "duration_tick": recorded["duration_tick"]}
                    receipt["transport_released"] = True
                await edit("tempo.set", start_tick=2400, bpm=60)
                await midi("start", **{**scope, "start_tick": 1920})
                await midi("synthetic_events", events=[
                    {"elapsed_ms": 250, "channel": 0, "number": 75, "velocity": 80, "on": True},
                    {"elapsed_ms": 750, "channel": 0, "number": 75, "velocity": 0, "on": False}])
                await midi("stop", end_ms=800)
                tempo_notes = (await edit("note.list", track_index=0, part_index=0))["notes"]
                crossed = next(note for note in tempo_notes if note["number"] == 75)
                assert (crossed["start_tick"], crossed["duration_tick"]) == (2160, 360), crossed
                receipt["tempo_crossing"] = {"start_tick": crossed["start_tick"], "duration_tick": crossed["duration_tick"]}
                await midi("start", **scope)
                await midi("synthetic_events", events=[{"elapsed_ms": 100, "channel": 0, "number": 78, "velocity": 70, "on": True}])
                bad_stop = await client.call_tool("project_midi", {"session_id": session, "operation": "stop", "options": {"end_ms": 50}})
                assert bad_stop.isError
                retry = await client.call_tool("project_midi", {"session_id": session, "operation": "stop", "options": {"end_ms": 200}})
                assert retry.isError, "Invalid stop was retried after the source was closed"
                await midi("cancel")
                receipt["invalid_stop_requires_cancel"] = True
                await midi("start", **scope)
                await call("project_close", session_id=session, discard_changes=True)
                session = (await call("project_open", path=saved["path"]))["session_id"]
                assert (await edit("note.list", track_index=0, part_index=0))["notes"] == notes
                receipt["active_close_and_reopen"] = True
                receipt["source_unchanged"] = fixture.read_bytes() == original
                assert receipt["source_unchanged"]
                receipt["status"] = "passed"
            finally:
                if session:
                    await call("project_close", session_id=session, discard_changes=True)
    destination = ROOT / "artifacts" / f"midi-synthetic-{run}.json"
    destination.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"receipt": str(destination), **receipt}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport-device-id")
    asyncio.run(main(parser.parse_args().transport_device_id))
