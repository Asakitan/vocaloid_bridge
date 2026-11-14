"""Muted, explicitly selected DirectSound test of preserved-project transport."""
import asyncio
import json
import sys
import zipfile
from pathlib import Path
import verify_features as v

DEVICE = "DS:062aa9fc-7997-489c-84e3-0ad0e162ac2b"  # Previously validated HECATE output.


@v.feature("preservation.archive_transport", "transport_device", "score_compose", "project_open", "project_audio", "project_edit", "project_save", "project_close", "project_status", "project_library")
async def archive_transport(check):
    product = (await check.call("vocaloid_features"))["product"]
    is_v7 = product == "VOCALOID7"
    effect_scope = {"scope": "track", "track_index": 0} if is_v7 else {"scope": "part", "track_index": 0, "part_index": 0}
    style_scope = {"scope": "track", "track_index": 0} if is_v7 else {"track_index": 0, "part_index": 0}
    report = {"device_id": DEVICE, "mute_output": True, "product": product,
              "effect_fixture_scope": effect_scope, "part_effect_supported": not is_v7}
    check.evidence("archive_transport", report)
    async with check.project(score=True) as seed:
        _, path = await check.save(seed, "archive-transport-seed")
    seq, members = v.read_vpr(path)
    seq["tracks"][0]["x_transport_track"] = {"opaque": "track"}
    seq["tracks"][0]["parts"][0]["x_transport_part"] = ["opaque", 42]
    members["Project/transport-opaque.bin"] = b"archive transport resource"
    members["Project/sequence.json"] = json.dumps(seq, ensure_ascii=False).encode("utf-8")
    fixture = v.ROOT / "output" / check.output("archive-transport-fixture")
    with zipfile.ZipFile(fixture, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items(): archive.writestr(name, data)
    fixture_bytes = fixture.read_bytes()
    sid = (await check.call("project_open", path=str(fixture)))["session_id"]
    prepared = False
    try:
        before = await check.call("project_status", session_id=sid)
        history = await check.edit(sid, "history.status")
        _, before_path = await check.save(sid, "archive-transport-before")
        before_seq, before_members = v.read_vpr(before_path)
        before_status = await check.call("project_status", session_id=sid)
        async def audio(op, **options):
            return await check.call("project_audio", session_id=sid, operation=op, options=options)
        catalog = await audio("devices")
        matches = [d for d in catalog["devices"] if d["device_id"] == DEVICE and d["type"] == "DS" and 44100 in d["sample_rates"]]
        if len(matches) != 1: raise v.Blocked("Previously validated HECATE DirectSound output is unavailable")
        # A nonexistent explicit device exercises failure after native engine initialization.
        await check.rejected("project_audio", "device_id|device", session_id=sid, operation="transport_prepare",
                             options={"device_id": "DS:00000000-0000-0000-0000-000000000000", "mute_output": True})
        v.require(not (await audio("transport_status"))["prepared"], "Failed prepare retained transport")
        async with check.project(score=True) as other:
            effects = await check.audio(other, "effects", scope="catalog")
            if is_v7:
                await check.rejected("project_audio", "VOCALOID7.*part audio effects", session_id=other,
                                     operation="effects", options={"scope": "part", "track_index": 0, "part_index": 0})
            chain = await check.audio(other, "effects", **effect_scope)
            existing = {effect["effect_id"] for effect in chain["effects"]}
            effect_id = next(effect["effect_id"] for effect in effects["effects"] if effect["effect_id"] not in existing)
            await check.audio(other, "set_effect", **effect_scope, action="add", effect_id=effect_id)
            style = (await check.library("style_capture", other, **style_scope, name="Transport style " + check.run_id))["style"]
            style_id = style["style_id"]
            try:
                state = await audio("transport_prepare", device_id=DEVICE, sample_rate=44100, mute_output=True)
                prepared = True
                v.require(state["session_id"] == sid and state["prepared"] and state["muted"], "Wrong source identity or state", state)
                await check.rejected("project_save", "release|transport", session_id=sid, output_name=check.output("busy-save"))
                await check.rejected("project_edit", "release|transport", session_id=sid, operation="track.update", options={"track_index": 0, "name": "blocked"})
                await check.rejected("project_audio", "transport|release|busy", session_id=other, operation="effects", options={"scope": "catalog"})
                await check.rejected("project_library", "transport|release|busy", session_id=other, operation="style_capture", options={**style_scope, "name": "blocked"})
                await check.rejected("project_library", "transport|release|busy", session_id=other, operation="style_apply", options={**style_scope, "style_id": style_id})
                start = await audio("transport_play"); await asyncio.sleep(.4); progress = await audio("transport_status")
                v.require(progress["session_id"] == sid and progress["playing"] and progress["seconds"] > start["seconds"] + .05 and max(progress["output_peak_db"]) <= -120, "Muted playback did not advance", progress)
                v.require(not (await audio("transport_stop"))["playing"], "Stop failed")
                seek = await audio("transport_seek", seconds=1.2); await asyncio.sleep(.1)
                observed = await audio("transport_status")
                v.require(seek["session_id"] == sid and abs(observed["seconds"] - 1.2) < .1, "Seek not observed", observed)
                await audio("transport_release"); prepared = False
                await check.library("style_apply", other, style_id=style_id, **style_scope)
                await check.library("style_capture", other, **style_scope, name="Transport resumed " + check.run_id, overwrite_style_id=style_id)
                report.update(play=progress, seek=observed)
            finally:
                if prepared:
                    await audio("transport_release"); prepared = False
                await check.library("style_delete", other, style_id=style_id)
        after = await check.call("project_status", session_id=sid)
        v.require(after == before_status and await check.edit(sid, "history.status") == history, "Source status/history changed", {"before": before, "after": after})
        after_seq, after_path = await check.save(sid, "archive-transport-after")
        after_members = v.read_vpr(after_path)[1]
        v.require(after_seq == before_seq and after_members == before_members, "Archive changed after playback")
        v.require(fixture.read_bytes() == fixture_bytes, "Original source archive changed")
        state = await audio("transport_prepare", device_id=DEVICE, sample_rate=44100, mute_output=True)
        prepared = True
        v.require(state["session_id"] == sid, "Second prepare lost source identity")
        await check.close(sid); prepared = False
        async with check.project() as probe:
            v.require(not (await check.call("project_audio", session_id=probe, operation="transport_status", options={}))['prepared'], "Source close leaked transport")
    finally:
        if prepared and sid in check.sessions: await check.audio(sid, "transport_release")
        if sid in check.sessions: await check.close(sid)


if __name__ == "__main__":
    if "--case" not in sys.argv: sys.argv.extend(["--case", "preservation.archive_transport"])
    raise SystemExit(v.main())
