"""Check ordinary AI track no-ops through an isolated native MCP host."""
import sys
import verify_features as v

FIELDS = ("name", "color", "mute", "solo", "bus_no")

@v.feature("score.track_fields_noop_25", "score", "project_create", "project_edit", "project_save", "project_open", "project_status", "project_get", "project_items", "project_set")
async def track_fields_noop(check):
    features = await check.call("vocaloid_features")
    is_v7 = features["product"] == "VOCALOID7"
    if is_v7:
        for field in ("mute", "solo"):
            v.require("stored mute" in features["features"][field]["parameters"][field]["semantics"],
                      "Mute/solo feature discovery omitted the stored/effective distinction")
        operations = await check.call("vocaloid_operations", domain="score", operation="track.update")
        v.require("stored mute" in operations["domains"]["score"]["operations"][0]["mute_semantics"],
                  "Track update discovery omitted the stored/effective distinction")
        v.require(features["features"]["solo"]["parameters"]["solo_state"]["enum"] == ["Off", "On", "Defeat"],
              "Solo feature discovery omitted native V7 solo states")
    async with check.project() as seed:
        await check.rejected("project_edit", "type must", session_id=seed, operation="track.create",
                             options={"type": "2", "name": "Invalid numeric type"})
        await check.edit(seed, "track.create", type="mIdIaI", name="Noop AI")
        _, source = await check.save(seed, "track-fields-source")
    original = source.read_bytes()
    sid = (await check.call("project_open", path=str(source)))["session_id"]
    try:
        track = (await check.edit(sid, "track.list"))["tracks"][0]
        status = await check.call("project_status", session_id=sid)
        history = await check.edit(sid, "history.status")
        v.require(not status["dirty"] and not history["staged"], "Fixture must start clean and unstaged")
        if not is_v7:
            await check.rejected("project_edit", "requires VOCALOID7", session_id=sid, operation="track.update",
                                 options={"track_index": 0, "solo_state": "Defeat"})
            v.require(await check.call("project_status", session_id=sid) == status
                      and await check.edit(sid, "history.status") == history,
                      "Unsupported V6 solo state changed project state or history")
        observed = {}
        for field in FIELDS:
            probe = (await check.call("project_open", path=str(source)))["session_id"]
            try:
                before = await check.call("project_status", session_id=probe)
                hist_before = await check.edit(probe, "history.status")
                result = await check.edit(probe, "track.update", track_index=0, **{field: track[field]})
                after = await check.call("project_status", session_id=probe)
                hist_after = await check.edit(probe, "history.status")
                observed[field] = {"before": before, "after": after, "history_before": hist_before, "history_after": hist_after, "result": result}
            finally:
                await check.close(probe)
        check.evidence("individual_clean", observed)
        failures = [field for field, item in observed.items() if item["before"] != item["after"] or item["history_before"] != item["history_after"]]

        recording_probe = (await check.call("project_open", path=str(source)))["session_id"]
        try:
            recording_history = await check.edit(recording_probe, "history.status")
            await check.edit(recording_probe, "track.update", track_index=0, midi_recording=track["midi_recording"])
            recording_after = await check.call("project_status", session_id=recording_probe)
            v.require(recording_after["dirty"] and await check.edit(recording_probe, "history.status") == recording_history,
                      "MIDI recording no longer followed its existing setter path")
        finally:
            await check.close(recording_probe)

        values = {field: track[field] for field in FIELDS}
        await check.edit(sid, "track.update", track_index=0, **values)
        v.require(await check.call("project_status", session_id=sid) == status and await check.edit(sid, "history.status") == history, "Combined no-op changed clean state")
        ordered = {}
        for order in (("mute", "solo"), ("solo", "mute")):
            probe = (await check.call("project_open", path=str(source)))["session_id"]
            try:
                events = []
                initial_history = await check.edit(probe, "history.status")
                for field in order:
                    result = await check.raw("project_edit", {"session_id": probe, "operation": "track.update",
                                                              "options": {"track_index": 0, field: True}})
                    current_track = (await check.edit(probe, "track.list"))["tracks"][0]
                    events.append({"field": field, "is_error": bool(result.isError), "track": current_track,
                                   "history": await check.edit(probe, "history.status"),
                                   "content": [getattr(item, "text", "") for item in result.content]})
                ordered["-".join(order)] = events
                check.evidence("history_initial_" + "-".join(order), initial_history)
            finally:
                await check.close(probe)
        check.evidence("mute_solo_order", ordered)
        if is_v7:
            for order, events in ordered.items():
                v.require(all(not event["is_error"] for event in events)
                          and events[1]["track"]["mute"] and events[1]["track"]["solo"]
                          and not events[1]["track"]["channel_mute"],
                          "V7 mute and solo did not retain independent stored states", {"order": order, "events": events})
            imported = await check.call("score_patch", path=str(source), output_name=check.output("track-both-import"),
                                        operations=[{"op": "replace", "path": "/tracks/0/isMuted", "value": True},
                                                    {"op": "replace", "path": "/tracks/0/soloState", "value": 1}])
            imported_session = (await check.call("project_open", path=imported["path"]))["session_id"]
            try:
                imported_track = (await check.edit(imported_session, "track.list"))["tracks"][0]
                check.evidence("imported_mute_solo", imported_track)
                imported_saved, _ = await check.save(imported_session, "track-both-import-saved")
                check.evidence("imported_mute_solo_saved", imported_saved["tracks"][0])
                v.require(imported_track["mute"] and not imported_track["channel_mute"]
                          and imported_saved["tracks"][0]["isMuted"],
                          "Native stored mute did not match the imported project")
                un_solo = await check.edit(imported_session, "track.update", track_index=0, solo=False)
                check.evidence("imported_after_solo_off", un_solo)
                un_solo_saved, _ = await check.save(imported_session, "track-both-solo-off")
                check.evidence("imported_after_solo_off_saved", un_solo_saved["tracks"][0])
                v.require(un_solo["mute"] and not un_solo["solo"] and un_solo["channel_mute"],
                          "Disabling solo lost the stored mute state")
            finally:
                await check.close(imported_session)
            combined_session = (await check.call("project_open", path=imported["path"]))["session_id"]
            try:
                cleared = await check.edit(combined_session, "track.update", track_index=0, mute=False, solo=False)
                cleared_saved, _ = await check.save(combined_session, "track-both-cleared")
                v.require(not cleared["mute"] and not cleared["solo"]
                          and not cleared_saved["tracks"][0]["isMuted"] and cleared_saved["tracks"][0]["soloState"] == 0,
                          "Combined unmute/unsolo did not clear the stored and effective state", cleared_saved["tracks"][0])
            finally:
                await check.close(combined_session)
            multitrack = (await check.call("project_open", path=str(source)))["session_id"]
            try:
                await check.edit(multitrack, "track.create", name="Other", type="Audio")
                await check.edit(multitrack, "track.create", name="Also Solo")
                await check.edit(multitrack, "track.update", track_index=0, solo=True)
                await check.edit(multitrack, "track.update", track_index=2, solo=True)
                other_tracks = await check.edit(multitrack, "track.list")
                other_saved, _ = await check.save(multitrack, "other-solo-state")
                check.evidence("other_solo_tracks", other_tracks)
                check.evidence("other_solo_saved", other_saved["tracks"])
                v.require(other_tracks["tracks"][1]["channel_mute"] and not other_tracks["tracks"][1]["mute"]
                          and not other_saved["tracks"][1]["isMuted"],
                          "Native stored mute did not match the non-solo track")
                before_mute_history = await check.edit(multitrack, "history.status")
                muted_other = await check.edit(multitrack, "track.update", track_index=1, mute=True)
                after_mute_history = await check.edit(multitrack, "history.status")
                check.evidence("mute_history", {"before": before_mute_history, "after": after_mute_history})
                tracks_after_muting = (await check.edit(multitrack, "track.list"))["tracks"]
                v.require(muted_other["mute"] and muted_other["channel_mute"]
                          and all(tracks_after_muting[index]["solo"] for index in (0, 2)),
                          "Muting a track masked by other solos did not preserve them")
                unmuted_other = await check.edit(multitrack, "track.update", track_index=1, mute=False)
                v.require(not unmuted_other["mute"] and unmuted_other["channel_mute"],
                          "Unmuting a track masked by another solo did not clear stored mute")
                await check.edit(multitrack, "track.update", track_index=0, solo=False)
                await check.edit(multitrack, "track.update", track_index=2, solo=False)
                v.require(not (await check.edit(multitrack, "track.list"))["tracks"][1]["channel_mute"],
                          "Cleared stored mute returned after the other solo was disabled")
            finally:
                await check.close(multitrack)
            defeat = await check.call("score_patch", path=str(source), output_name=check.output("track-solo-defeat"),
                                      operations=[{"op": "replace", "path": "/tracks/0/soloState", "value": 2}])
            defeat_session = (await check.call("project_open", path=defeat["path"]))["session_id"]
            try:
                original_defeat = (await check.edit(defeat_session, "track.list"))["tracks"][0]
                v.require(original_defeat["solo_state"] == "Defeat", "Native Solo Defeat state was not reported")
                await check.edit(defeat_session, "track.update", track_index=0, mute=True)
                defeat_saved, _ = await check.save(defeat_session, "track-solo-defeat-saved")
                v.require(defeat_saved["tracks"][0]["soloState"] == 2 and defeat_saved["tracks"][0]["isMuted"],
                          "Mute update changed the existing Solo Defeat state", defeat_saved["tracks"][0])
                for state, expected in (("On", 1), ("Off", 0), ("Defeat", 2)):
                    changed_state = await check.edit(defeat_session, "track.update", track_index=0, solo_state=state)
                    state_saved, state_path = await check.save(defeat_session, "track-solo-" + state.lower())
                    v.require(changed_state["solo_state"] == state and changed_state["mute"]
                              and state_saved["tracks"][0]["soloState"] == expected
                              and state_saved["tracks"][0]["isMuted"],
                              "Native solo-state change lost mute or did not persist", state_saved["tracks"][0])
                    if state == "Defeat":
                        reopened_defeat = (await check.call("project_open", path=str(state_path)))["session_id"]
                        try:
                            reloaded = (await check.edit(reopened_defeat, "track.list"))["tracks"][0]
                            v.require(reloaded["solo_state"] == "Defeat" and reloaded["mute"],
                                      "Native Solo Defeat and mute did not survive reopen", reloaded)
                        finally:
                            await check.close(reopened_defeat)
                inspected = await check.call("project_inspect", session_id=defeat_session, feature="solo", track_index=0)
                v.require(any(call["arguments"]["options"].get("solo_state") == "VALUE"
                              for call in inspected["contract"]["write_calls"]),
                          "Solo inspection omitted the native state write template")
                cleared_defeat = await check.edit(defeat_session, "track.update", track_index=0, solo=False)
                v.require(cleared_defeat["solo_state"] == "Off", "Boolean solo=false did not clear Solo Defeat")
                mixed_case = await check.edit(defeat_session, "track.update", track_index=0, solo_state="oFf")
                v.require(mixed_case["solo_state"] == "Off", "Solo state names lost case-insensitive matching")
                for invalid_state in ("invalid", "0", "1", "2"):
                    await check.rejected("project_edit", "solo_state", session_id=defeat_session, operation="track.update",
                                         options={"track_index": 0, "solo_state": invalid_state})
                await check.rejected("project_edit", "solo_state", session_id=defeat_session, operation="track.update",
                                     options={"track_index": 0, "solo": True, "solo_state": "Defeat"})
                unchanged = (await check.edit(defeat_session, "track.list"))["tracks"][0]
                v.require(unchanged["solo_state"] == "Off" and unchanged["mute"],
                          "Rejected solo_state changed the native track", unchanged)
            finally:
                await check.close(defeat_session)
            identical_session = (await check.call("project_open", path=str(source)))["session_id"]
            try:
                await check.edit(identical_session, "track.duplicate", track_index=0, name=track["name"])
                await check.edit(identical_session, "track.update", track_index=1, solo_state="Defeat")
                _, distinct_path = await check.save(identical_session, "solo-distinct-tracks")
            finally:
                await check.close(identical_session)
            extended = await check.call("score_patch", path=str(distinct_path), output_name=check.output("solo-distinct-extended"),
                                        operations=[{"op": "add", "path": "/tracks/0/x_solo_identity", "value": "off"},
                                                    {"op": "add", "path": "/tracks/1/x_solo_identity", "value": "defeat"}])
            extended_session = (await check.call("project_open", path=extended["path"]))["session_id"]
            try:
                extended_before = await check.edit(extended_session, "track.list")
                extended_status = await check.call("project_status", session_id=extended_session)
                extended_history = await check.edit(extended_session, "history.status")
                await check.rejected("project_edit", "project_preservation|ambiguous|indistinguishable",
                                     session_id=extended_session, operation="track.update",
                                     options={"track_index": 1, "solo_state": "Off"})
                v.require(await check.edit(extended_session, "track.list") == extended_before
                          and await check.call("project_status", session_id=extended_session) == extended_status
                          and await check.edit(extended_session, "history.status") == extended_history,
                          "Rejected solo identity collision changed the project")
                await check.edit(extended_session, "track.reorder", track_index=0, to_index=1)
                extended_saved, extended_path = await check.save(extended_session, "solo-distinct-reordered")
                v.require([(item["soloState"], item["x_solo_identity"]) for item in extended_saved["tracks"]]
                          == [(2, "defeat"), (0, "off")],
                          "Track solo identity metadata did not follow the reordered tracks", extended_saved["tracks"])
                reopened_extended = (await check.call("project_open", path=str(extended_path)))["session_id"]
                try:
                    reopened_tracks = (await check.edit(reopened_extended, "track.list"))["tracks"]
                    v.require([item["solo_state"] for item in reopened_tracks] == ["Defeat", "Off"],
                              "Distinct track solo states did not survive reopen", reopened_tracks)
                finally:
                    await check.close(reopened_extended)
            finally:
                await check.close(extended_session)
            ambiguous = await check.call("score_patch", path=str(distinct_path), output_name=check.output("solo-ambiguous-extended"),
                                         operations=[{"op": "replace", "path": "/tracks/1/soloState", "value": 0},
                                                     {"op": "add", "path": "/tracks/0/x_solo_identity", "value": "first"},
                                                     {"op": "add", "path": "/tracks/1/x_solo_identity", "value": "second"}])
            await check.rejected("project_open", "indistinguishable|ambiguous", path=ambiguous["path"])
        else:
            distinct_session = (await check.call("project_open", path=str(source)))["session_id"]
            try:
                await check.edit(distinct_session, "track.duplicate", track_index=0, name=track["name"])
                await check.edit(distinct_session, "track.update", track_index=1, mute=True)
                _, distinct_path = await check.save(distinct_session, "mute-distinct-tracks")
            finally:
                await check.close(distinct_session)
            extended = await check.call("score_patch", path=str(distinct_path), output_name=check.output("mute-distinct-extended"),
                                        operations=[{"op": "add", "path": "/tracks/0/x_mute_identity", "value": "off"},
                                                    {"op": "add", "path": "/tracks/1/x_mute_identity", "value": "on"}])
            extended_session = (await check.call("project_open", path=extended["path"]))["session_id"]
            try:
                extended_before = await check.edit(extended_session, "track.list")
                extended_status = await check.call("project_status", session_id=extended_session)
                extended_history = await check.edit(extended_session, "history.status")
                await check.rejected("project_edit", "project_preservation|ambiguous|indistinguishable",
                                     session_id=extended_session, operation="track.update",
                                     options={"track_index": 1, "mute": False})
                v.require(await check.edit(extended_session, "track.list") == extended_before
                          and await check.call("project_status", session_id=extended_session) == extended_status
                          and await check.edit(extended_session, "history.status") == extended_history,
                          "Rejected V6 mute identity collision changed the project")
            finally:
                await check.close(extended_session)
        rollback_probe = (await check.call("project_open", path=str(source)))["session_id"]
        try:
            rollback_before = await check.edit(rollback_probe, "track.list")
            rollback_status = await check.call("project_status", session_id=rollback_probe)
            rollback_history = await check.edit(rollback_probe, "history.status")
            rollback_options = {"track_index": 0, "name": "X" * 16384, "midi_recording": True, "mute": True,
                                **({"solo_state": "Defeat"} if is_v7 else {"solo": True})}
            long_name_result = await check.raw("project_edit", {"session_id": rollback_probe, "operation": "track.update",
                                                                 "options": rollback_options})
            check.evidence("long_track_name_rejected", bool(long_name_result.isError))
            if long_name_result.isError:
                v.require(await check.edit(rollback_probe, "track.list") == rollback_before
                          and await check.call("project_status", session_id=rollback_probe) == rollback_status
                          and await check.edit(rollback_probe, "history.status") == rollback_history,
                          "Rejected composite track update left native state changed")
        finally:
            await check.close(rollback_probe)
        changed = {"name": "Noop AI changed", "color": (track["color"] + 1) % 16, "mute": not track["mute"], "solo": not track["solo"]}
        await check.edit(sid, "track.update", track_index=0, **changed)
        dirty = await check.call("project_status", session_id=sid)
        dirty_history = await check.edit(sid, "history.status")
        v.require(dirty["dirty"] and not dirty_history["staged"], "Real edit not committed and dirty")
        current = (await check.edit(sid, "track.list"))["tracks"][0]
        await check.edit(sid, "track.update", track_index=0, **{field: current[field] for field in FIELDS})
        v.require(await check.call("project_status", session_id=sid) == dirty and await check.edit(sid, "history.status") == dirty_history, "No-op altered dirty state")
        _, output = await check.save(sid, "track-fields-changed")
        reopened = (await check.call("project_open", path=str(output)))["session_id"]
        try:
            saved = (await check.edit(reopened, "track.list"))["tracks"][0]
            v.require(all(saved[field] == value for field, value in changed.items()), "Real changes did not survive reopen", saved)
        finally:
            await check.close(reopened)
        tempos = (await check.call("project_get", session_id=sid, member="Tempos"))["value"]
        item = (await check.call("project_items", session_id=sid, ref=tempos["$ref"]))["items"][0]
        value = (await check.call("project_get", session_id=sid, ref=item["$ref"], member="Value"))["value"]
        await check.call("project_set", session_id=sid, ref=item["$ref"], member="Value", value=value + 1)
        v.require((await check.edit(sid, "history.status"))["staged"], "Tempo did not stage")
        await check.rejected("project_edit", "pending native edits", session_id=sid, operation="track.update", options={"track_index": 0, **{field: current[field] for field in FIELDS}})
        v.require((await check.edit(sid, "history.status"))["staged"], "No-op consumed pending edit")
        await check.edit(sid, "history.rollback")
    finally:
        await check.close(sid)
    v.require(source.read_bytes() == original, "Source archive changed")
    v.require(not failures, "Same-value fields changed state or history", failures)

if __name__ == "__main__":
    if "--case" not in sys.argv:
        sys.argv.extend(["--case", "score.track_fields_noop_25"])
    raise SystemExit(v.main())
