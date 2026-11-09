"""Run one no-foreground native lifecycle check through the actual MCP transport."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys
import uuid
import zipfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import win32gui


ROOT = Path(__file__).resolve().parents[1]


async def run() -> None:
    foreground = win32gui.GetForegroundWindow()
    run_id = uuid.uuid4().hex[:12]
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "vocaloid_bridge"],
        cwd=str(ROOT),
        env={**os.environ, "VOCALOID_WORKSPACE": str(ROOT), "PYTHONUTF8": "1"},
    )
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            tools = await session.list_tools()

            async def call(name: str, **arguments):
                result = await session.call_tool(name, arguments)
                if result.isError:
                    raise AssertionError(f"{name}: {result.content}")
                if result.structuredContent is None:
                    raise AssertionError(f"{name} did not return structured content")
                return result.structuredContent

            status = await call("vocaloid_status")
            assert status["backend"] == "native-vsm", status
            assert status["desktop"] == status["isolation_desktop_expected"], status
            created = await call("project_create", title="Native background smoke", bpm=112)
            session_id = created["session_id"]
            members = await call("project_members", session_id=session_id)
            assert any(item["name"] == "Title" for item in members["properties"]), members
            await call("project_set", session_id=session_id, member="Title", value="Native background verified")
            title = await call("project_get", session_id=session_id, member="Title")
            assert title["value"] == "Native background verified", title
            saved = await call("project_save", session_id=session_id, output_name=f"native-smoke-{run_id}.vpr")
            assert saved["native"] and saved["saved"], saved
            assert zipfile.is_zipfile(saved["path"]), saved
            closed = await call("project_close", session_id=session_id)
            assert closed["closed"], closed
            reopened = await call("project_open", path=saved["path"])
            reread = await call("project_get", session_id=reopened["session_id"], member="Title")
            assert reread["value"] == "Native background verified", reread
            await call("project_close", session_id=reopened["session_id"])
            notes = [
                {"start": index, "duration": 0.8, "pitch": pitch,
                 "lyric": "\u3042", "phoneme": "a", "lang_id": 0}
                for index, pitch in enumerate([60, 64, 67, 64])
            ]
            composition = await call("score_compose", output_name=f"score-smoke-{run_id}.vpr",
                                     title="Native score verified", bpm=120, notes=notes)
            score_session = composition["native_session"]["session_id"]
            native_score = await call("project_save", session_id=score_session,
                                      output_name=f"native-score-smoke-{run_id}.vpr")
            with zipfile.ZipFile(native_score["path"]) as archive:
                sequence = json.loads(archive.read("Project/sequence.json"))
            saved_notes = sequence["tracks"][0]["parts"][0]["notes"]
            assert [note["number"] for note in saved_notes] == [60, 64, 67, 64], saved_notes
            assert all(note["phoneme"] == "a" for note in saved_notes), saved_notes
            await call("project_close", session_id=score_session)
            assert win32gui.GetForegroundWindow() == foreground, "Foreground changed during native MCP smoke"
            receipt = {
                "run_id": run_id,
                "tools": len(tools.tools),
                "backend": status["backend"],
                "mcp_version": status["mcp_version"],
                "desktop": status["desktop"],
                "project_path": saved["path"],
                "native_create_save_close_reopen": True,
                "native_property_roundtrip": True,
                "native_note_roundtrip": True,
                "native_score_path": native_score["path"],
                "foreground_before": foreground,
                "foreground_after": win32gui.GetForegroundWindow(),
            }
            destination = ROOT / "artifacts" / f"mcp-smoke-{run_id}.json"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
            print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    asyncio.run(run())
