"""Necessary ordinary-media preservation and locked-publication checks."""
import json
from pathlib import Path
import sys
import win32con
import win32file
import verify_features as v


@v.feature("library.media_properties_31", "library", "score_compose", "project_library")
async def media_properties(check):
    async with check.project(score=True) as sid:
        clip = (await check.library("media_capture", sid, track_index=0, part_index=0, name="Property31 " + check.run_id))["clip"]
        path = Path(clip["path"]).resolve()
        prop = path.with_name("property.json")
        original_clip = path.read_bytes()
        try:
            data = json.loads(prop.read_text(encoding="utf-8-sig"))
            marker = {"nested": [True, None, {"value": "ordinary synthetic property"}]}
            data["x_property31"] = marker
            data["part"]["x_property31"] = marker
            data["filter"]["x_property31"] = [marker, 7]
            prop.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            updated = (await check.library("media_update", sid, clip_id=clip["clip_id"], name="Property31 updated", tempo=12345,
                                           add_genres=["Property31"], add_types=["Synthetic31"]))["clip"]
            result = json.loads(prop.read_text(encoding="utf-8"))
            v.require(result["x_property31"] == marker and result["part"]["x_property31"] == marker
                      and result["filter"]["x_property31"] == [marker, 7], "Unknown media properties lost", result)
            v.require(updated["name"] == "Property31 updated" and updated["tempo"] == 12345
                      and "Property31" in updated["genres"] and "Synthetic31" in updated["types"]
                      and path.read_bytes() == original_clip, "Native media readback differs", updated)
            before = prop.read_bytes()
            lock = win32file.CreateFile(str(prop), win32con.GENERIC_READ, win32con.FILE_SHARE_READ, None,
                                        win32con.OPEN_EXISTING, win32con.FILE_ATTRIBUTE_NORMAL, None)
            try:
                await check.rejected("project_library", "sharing|access|process|使用|访问", session_id=sid, operation="media_update",
                                     options={"clip_id": clip["clip_id"], "name": "Property31 locked"})
            finally:
                lock.Close()
            after = await check.library("media_get", sid, clip_id=clip["clip_id"])
            v.require(prop.read_bytes() == before and after["name"] == updated["name"]
                      and path.read_bytes() == original_clip, "Locked publication changed disk or cache")
            check.evidence("ordinary_media_properties", {"updated": updated, "property": result, "locked_unchanged": True})
        finally:
            await check.library("media_delete", sid, clip_id=clip["clip_id"])


if __name__ == "__main__":
    if "--case" not in sys.argv:
        sys.argv.extend(["--case", "library.media_properties_31"])
    raise SystemExit(v.main())
