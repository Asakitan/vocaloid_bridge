"""Exercise the added score dispatch names through actual MCP, not only native RPC."""
import verify_features as v


@v.feature("remaining.score_dispatch", "remaining", "project_edit", "project_get", "project_set", "project_items",
           "project_render_part", "project_save", "project_open")
async def score_dispatch(check):
    async with check.project(score=True) as sid:
        note = {"track_index": 0, "part_index": 0, "note_index": 0}
        converted = await check.edit(sid, "time.convert", **{"from": "tick", "value": 480})
        v.require(converted["tick"] == 480 and abs(converted["seconds"] - 0.5) < 1e-6, "Time conversion mismatch", converted)
        await check.edit(sid, "note.batch_update", track_index=0, part_index=0, note_indices=[0], transpose=1, lyrics=["\u3042"])
        curve = await check.edit(sid, "vibrato.set", **note, type="Normal_1", duration_tick=144,
                                 depth=[{"tick": 0, "value": 32}, {"tick": 144, "value": 64}],
                                 rate=[{"tick": 0, "value": 48}, {"tick": 144, "value": 56}])
        v.require((await check.edit(sid, "vibrato.get", **note)) == curve, "Vibrato readback changed")
        tempos = (await check.call("project_get", session_id=sid, member="Tempos"))["value"]
        tempo = (await check.call("project_items", session_id=sid, ref=tempos["$ref"]))["items"][0]
        initial = (await check.call("project_get", session_id=sid, ref=tempo["$ref"], member="Value"))["value"]
        await check.call("project_set", session_id=sid, ref=tempo["$ref"], member="Value", value=initial + 1)
        rolled = await check.edit(sid, "history.rollback")
        v.require(rolled["rolled_back"] and not rolled["staged"], "Staged rollback failed", rolled)
        v.require((await check.edit(sid, "tempo.list"))["tempos"][0]["bpm"] == initial / 100, "Rollback lost original tempo")
        rendered = await check.call("project_render_part", session_id=sid, output_name=check.output("timing-render", ".wav"))
        timing = await check.edit(sid, "phoneme_timing.get", **note)
        v.require(len(timing["positions"]) > 1, "Rendered note has no phoneme boundaries", timing)
        index = len(timing["positions"]) - 1
        current = timing["positions"][index]
        bounds = timing["ranges"][index]
        target = current + 1 if current < bounds["end"] else current - 1
        v.require(bounds["begin"] <= target <= bounds["end"] and current != target, "Phoneme boundary has no editable range")
        edited = await check.edit(sid, "phoneme_timing.set", **note, phoneme_index=index, tick=target)
        v.require(edited["positions"][index] == target, "Phoneme edit failed")
        await check.edit(sid, "phoneme_timing.reset", **note, phoneme_index=index)
        await check.edit(sid, "track.update", track_index=0, bus_no=1, midi_recording=True)
        await check.edit(sid, "sequence.update", sample_rate=48000)
        _, path = await check.save(sid, "remaining-score")
        reopened = (await check.call("project_open", path=str(path)))["session_id"]
        try:
            v.require((await check.edit(reopened, "sequence.get"))["sample_rate"] == 48000, "Sample rate did not persist")
            v.require((await check.edit(reopened, "track.list"))["tracks"][0]["bus_no"] == 1, "Bus routing did not persist")
            v.require((await check.edit(reopened, "vibrato.get", **note)) == curve, "Vibrato curves did not persist")
        finally:
            await check.close(reopened)
        check.evidence("score_dispatch", {"vpr": str(path), "render": rendered["path"], "phoneme_before": timing,
                                           "phoneme_edited": edited, "vibrato": curve, "record_arm_is_session_only": True})


if __name__ == "__main__":
    v.CASES[:] = [case for case in v.CASES if case.identifier == "remaining.score_dispatch"]
    raise SystemExit(v.main())
