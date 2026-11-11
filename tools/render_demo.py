"""Verify clean-project native synthesis through the actual MCP stdio transport."""

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


async def main() -> None:
    root = Path(__file__).resolve().parents[1]
    stem = "background-demo-" + uuid.uuid4().hex[:10]
    foreground = win32gui.GetForegroundWindow()
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "vocaloid_bridge"],
        cwd=str(root),
           env={**os.environ, "VOCALOID_WORKSPACE": str(root), "PYTHONUTF8": "1",
               "VOCALOID_TEMP_CLEANUP": "0", "VOCALOID_RENDER_TIMEOUT_SECONDS": "15"},
    )
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer) as client:
            await client.initialize()

            async def call(name: str, **arguments):
                result = await asyncio.wait_for(client.call_tool(name, arguments), timeout=40)
                if result.isError or result.structuredContent is None:
                    raise AssertionError(f"{name}: {result.content}")
                return result.structuredContent

            status = await call("vocaloid_status")
            assert status["backend"] == "native-vsm", status
            assert status["desktop"] == status["isolation_desktop_expected"], status
            voices = await call("voicebanks")
            notes = [
                {"start": index, "duration": 0.8, "pitch": pitch,
                 "lyric": "\u3042", "phoneme": "a", "lang_id": 0}
                for index, pitch in enumerate([60, 64, 67, 64])
            ]
            del notes[0]["phoneme"]
            score = await call("score_compose", output_name=stem + "-score.vpr",
                               title="Background demo", bpm=120, notes=notes)
            saved = await call("project_save", session_id=score["native_session"]["session_id"],
                               output_name=stem + "-before.vpr")
            await call("project_close", session_id=score["native_session"]["session_id"])
            opened = await call("project_open", path=saved["path"])
            session_id = opened["session_id"]
            assert opened["dirty"] is False, opened
            voice_options = {"track_index": 0, "part_index": 0}
            if status["product"] == "VOCALOID7":
                voice_options["scope"] = "track"
            voice = await call("project_edit", session_id=session_id,
                               operation="voice.get", options=voice_options)
            if status["product"] == "VOCALOID7":
                assert voice["result"]["voice_type_id"], voice
            rendered = await call("project_render_part", session_id=session_id,
                                  output_name=stem + ".wav", track_index=0, part_index=0)
            audio = rendered["audio"]
            assert rendered["native"] and audio["frames"] > 0 and audio["peak"] > 0 and audio["rms"] > 0, rendered
            saved = await call("project_save", session_id=session_id, output_name=stem + ".vpr")
            with zipfile.ZipFile(saved["path"]) as archive:
                sequence = json.loads(archive.read("Project/sequence.json"))
            saved_notes = sequence["tracks"][0]["parts"][0]["notes"]
            assert [note["number"] for note in saved_notes] == [60, 64, 67, 64], saved_notes
            assert all(note["phoneme"] == "a" and note["lyric"] == "\u3042" for note in saved_notes), saved_notes
            await call("project_close", session_id=session_id)
            after = await call("vocaloid_status")
            assert after["sessions"] == 0, after
            if foreground != win32gui.GetForegroundWindow():
                raise RuntimeError("Foreground changed during the rendering check.")
            report = {
                "transport": "mcp-stdio", "backend": status["backend"], "desktop": status["desktop"],
                "mcp_version": status["mcp_version"],
                "product": status["product"], "version": status["version"], "voice": voice,
                "voicebank_count": len(voices["voices"]), "rendered_clean_reopened_project": True,
                "native_project": saved["path"], "native_render": rendered,
                "audio": audio, "native_note_roundtrip": True, "remaining_sessions": after["sessions"],
                "foreground_before": foreground, "foreground_after": win32gui.GetForegroundWindow(),
                "foreground_unchanged": True,
            }
    destination = root / "artifacts" / (stem + ".json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(asyncio.wait_for(main(), timeout=120))