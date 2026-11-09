"""Actual-MCP, explicitly selected DS device transport smoke; output muted."""
import asyncio
import sys
import verify_features as v

@v.feature("transport.native_device", "transport_device", "project_audio", "project_save", "project_close")
async def native_device(check):
    report = {"muted": True}
    check.evidence("transport", report)
    async with check.project(score=True) as sid:
        async def audio(operation, **options):
            return await check.call("project_audio", session_id=sid, operation=operation, options=options)
        catalog = await audio("devices")
        devices = [d for d in catalog["devices"] if d["type"] == "DS" and 44100 in d["sample_rates"]]
        report["enumerated_devices"] = catalog["devices"]
        if not devices:
            raise v.Blocked("No native DS output with advertised 44100 Hz is available")
        device = devices[0]
        report["selected_device"] = device
        prepared = False
        try:
            state = await audio("transport_prepare", device_id=device["device_id"], mute_output=True)
            prepared = True
            report["prepare"] = state
            v.require(state["prepared"] and not state["playing"] and state["muted"] and state["device_id"] == device["device_id"], "Incorrect prepare state", state)
            v.require(state["end_seconds"] > 1.0, "Native test phrase is too short", state)
            await check.rejected("project_save", "release|transport", session_id=sid, output_name=check.output("busy-save"))
            started = await audio("transport_play")
            await asyncio.sleep(0.4)
            progressing = await audio("transport_status")
            report.update(play=started, progressing=progressing)
            v.require(started["playing"] and progressing["playing"] and progressing["seconds"] > started["seconds"] + 0.05,
                      "Native transport clock did not advance", report)
            v.require(progressing["muted"] and max(progressing["output_peak_db"]) <= -120,
                      "Muted output peak was above the observed -120 dB floor", progressing)
            stopped = await audio("transport_stop")
            v.require(not stopped["playing"], "Transport did not stop", stopped)
            sought = await audio("transport_seek", seconds=1.2)
            await asyncio.sleep(0.1)
            sought_after_wait = await audio("transport_status")
            resumed = await audio("transport_play")
            await asyncio.sleep(0.1)
            sought_after_play = await audio("transport_status")
            stopped_again = await audio("transport_stop")
            report.update(stop=stopped, seek_immediate=sought, seek_after_wait=sought_after_wait,
                          seek_play=resumed, seek_after_play=sought_after_play, seek_stop=stopped_again)
            v.require(not sought["playing"] and not sought_after_wait["playing"] and resumed["playing"] and not stopped_again["playing"],
                      "Unexpected stopped/playing state during seek diagnostic", report)
            v.require(abs(sought_after_wait["seconds"] - 1.2) < 0.1 or
                      1.2 <= sought_after_play["seconds"] < 1.6,
                      "Seek was not observed while stopped or after resuming", report)
            released = await audio("transport_release")
            prepared = False
            report["release"] = released
            v.require(released["released"] and not released["prepared"] and not released["playing"], "Release failed", released)
            _, path = await check.save(sid, "post-transport")
            report["post_release_save"] = str(path)
            again = await audio("transport_prepare", device_id=device["device_id"], mute_output=True)
            prepared = True
            v.require(again["prepared"] and again["muted"], "Second muted prepare failed", again)
            await check.close(sid)
            prepared = False
            report["close_with_prepared_transport"] = "closed"
        finally:
            if prepared and sid in check.sessions:
                await audio("transport_release")
    async with check.project() as other:
        state = await check.call("project_audio", session_id=other, operation="transport_status", options={})
        report["after_close"] = state
        v.require(not state["prepared"] and not state["playing"], "Close did not release transport", state)

if __name__ == "__main__":
    if not any(argument in ("--case", "--category") for argument in sys.argv[1:]):
        sys.argv.extend(["--category", "transport_device"])
    sys.exit(v.main())
