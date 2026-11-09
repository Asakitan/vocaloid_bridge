"""Focused MCP Take-lane read/write/render/save/reopen probe."""

import asyncio
import json
import os
from pathlib import Path
import sys
import uuid
import wave

import numpy as np
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]


def pcm(path):
    with wave.open(str(path), "rb") as wav:
        assert wav.getsampwidth() == 2
        shape = (wav.getnchannels(), wav.getframerate(), wav.getnframes())
        data = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(np.float64) / 32768
    return shape, data


async def main():
    run = uuid.uuid4().hex[:12]
    params = StdioServerParameters(command=sys.executable, args=["-m", "vocaloid_bridge"], cwd=str(ROOT),
        env={**os.environ, "VOCALOID_WORKSPACE": str(ROOT), "PYTHONUTF8": "1"})
    records = {"run_id": run}
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as client:
            await client.initialize()
            async def call(tool, **arguments):
                response = await client.call_tool(tool, arguments)
                if response.isError or response.structuredContent is None:
                    raise RuntimeError(f"{tool}: {response.content}")
                return response.structuredContent
            session = None
            try:
                seed = await call("score_compose", output_name=f"take-lane-{run}-seed.vpr",
                    title="Take lane probe", bpm=120,
                    notes=[{"start": i, "duration": 0.6, "pitch": pitch, "lyric": "あ", "phoneme": "a", "lang_id": 0}
                           for i, pitch in enumerate((60, 64, 67))])
                session = seed["native_session"]["session_id"]
                records["fixture"] = seed["path"]
                scope = {"track_index": 0, "part_index": 0}
                async def edit(operation, **options):
                    return (await call("project_edit", session_id=session, operation=operation, options=options))["result"]
                before = await edit("performance.get", **scope)
                setting = before["take"]["setting"]
                low, high = setting["LowerBoundValue"], setting["UpperBoundValue"]
                assert low < high, setting
                records["setting"] = setting
                records["low"] = await edit("performance.set", **scope, take_lane=low, bypass={"Take": False})
                assert records["low"]["take"]["lane"] == low
                low_render = await call("project_render_part", session_id=session, **scope, output_name=f"take-lane-{run}-low.wav")
                records["high"] = await edit("performance.set", **scope, take_lane=high, bypass={"Take": False})
                assert records["high"]["take"]["lane"] == high
                high_render = await call("project_render_part", session_id=session, **scope, output_name=f"take-lane-{run}-high.wav")
                records["low_render"], records["high_render"] = low_render, high_render
                low_format, low_samples = pcm(low_render["path"])
                high_format, high_samples = pcm(high_render["path"])
                assert low_format == high_format, (low_format, high_format)
                size = min(len(low_samples), len(high_samples))
                records["audio"] = {"low_format": low_format, "high_format": high_format,
                    "rms_low": float(np.sqrt(np.mean(low_samples ** 2))),
                    "rms_difference": float(np.sqrt(np.mean((low_samples[:size] - high_samples[:size]) ** 2))),
                    "pcm_identical": bool(np.array_equal(low_samples, high_samples))}
                assert records["audio"]["rms_low"] > 1e-5, records["audio"]
                assert records["audio"]["rms_difference"] > 1e-5, records["audio"]
                saved = await call("project_save", session_id=session, output_name=f"take-lane-{run}.vpr")
                await call("project_close", session_id=session)
                session = (await call("project_open", path=saved["path"]))["session_id"]
                restored = await edit("performance.get", **scope)
                records["saved_path"], records["restored"] = saved["path"], restored
                assert restored["take"]["lane"] == high
                assert not next(x for x in restored["bypass"] if x["effect"] == "Take")["bypassed"]
                records["status"] = "passed"
            finally:
                if session is not None:
                    await call("project_close", session_id=session, discard=True)
    destination = ROOT / "artifacts" / f"score-parameters-{run}.json"
    destination.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"receipt": str(destination), "status": records["status"], "audio": records["audio"]}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
