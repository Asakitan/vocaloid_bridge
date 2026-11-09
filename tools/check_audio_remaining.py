"""Focused actual-MCP audio acceptance; uses the existing host without building it."""
import sys
import verify_features as v

if __name__ == "__main__":
    v.CASES.clear()
NAMES = ("Gain", "De-Esser", "Compressor", "Equalizer", "Distortion", "Chorus", "Phaser", "Tremolo", "AutoPan", "Delay", "Reverb")

def register(name):
    @v.feature("remaining.effect." + name.lower().replace("-", ""), "remaining", "project_audio", "project_save", "project_open")
    async def run(check):
        import numpy as np
        source = await check.audio_input()
        async with check.project() as sid:
            await check.audio(sid, "import_audio", path=str(source))
            catalog = await check.audio(sid, "effects", scope="catalog")
            matches = [e for e in catalog["effects"] if e["name"].casefold() == name.casefold()]
            v.require(len(matches) == 1, "Effect missing or ambiguous", name)
            effect = matches[0]
            meta = await check.audio(sid, "effects", scope="catalog", effect_id=effect["effect_id"])
            v.require(meta["parameters"], "No native parameters", name)
            await check.audio(sid, "set_effect", action="add", scope="master", effect_id=effect["effect_id"])
            slot = len((await check.audio(sid, "effects", scope="master"))["effects"]) - 1
            presets = [p for p in meta["presets"] if p]
            if presets:
                await check.audio(sid, "set_effect", action="set", scope="master", slot=slot, preset=presets[0])
                preset_values = (await check.audio(sid, "effects", scope="master"))["effects"][slot]["parameters"]
                await check.audio(sid, "set_effect", action="set", scope="master", slot=slot, preset=presets[0])
                v.require(preset_values == (await check.audio(sid, "effects", scope="master"))["effects"][slot]["parameters"], "Preset readback was not deterministic", name)
            values = {p["name"]: 0.25 for p in meta["parameters"]}
            v.require(len(values) == len(meta["parameters"]), "Ambiguous parameter names", name)
            await check.audio(sid, "set_effect", action="set", scope="master", slot=slot, parameters=values, bypass=True)
            before = (await check.audio(sid, "effects", scope="master"))["effects"][slot]
            v.require(before["bypass"] is True and len(before["parameters"]) == len(values), "Bypass/parameter readback failed", before)
            native_values = {p["name"]: p["normalized"] for p in before["metadata"]["parameters"]}
            v.require(all(p["name"] in native_values and abs(p["value"] - native_values[p["name"]]) < 1e-5 for p in before["parameters"]), "Persisted values differ from native controller", before)
            _, path = await check.save(sid, "remaining-effect")
            reopened = (await check.call("project_open", path=str(path)))["session_id"]
            try:
                after = (await check.audio(reopened, "effects", scope="master"))["effects"][slot]
                v.require(after["effect_id"] == effect["effect_id"] and after["bypass"] is True and after["parameters"] == before["parameters"], "Reopened effect differs", {"before": before, "after": after})
                await check.audio(reopened, "set_effect", action="set", scope="master", slot=slot, bypass=False)
                v.require((await check.audio(reopened, "effects", scope="master"))["effects"][slot]["bypass"] is False, "Effect remained bypassed", name)
                rendered = await check.audio(reopened, "mixdown", output_name=check.output("remaining-effect", ".wav"))
                metadata, pcm = v.read_audio(rendered["path"])
                v.require(np.max(np.abs(pcm)) > 0, "Effect mix has no nonzero audio", name)
                check.evidence("effect", {"name": name, "preset_applied": presets[0] if presets else None, "parameter_count": len(values), "mix": rendered["path"], "metadata": metadata})
            finally:
                await check.close(reopened)
    return run

for name in NAMES:
    register(name)

@v.feature("remaining.rates_bounds", "remaining", "project_audio", "project_save", "project_open")
async def rates_bounds(check):
    import numpy as np
    source = await check.audio_input()
    original = source.read_bytes()
    _, original_pcm = v.read_audio(source)
    async with check.project() as sid:
        part = await check.audio(sid, "import_audio", path=str(source))
        width = part["end_tick"] - part["begin_tick"]
        v.require(width > 8, "Audio fixture too short")
        select = {"track_index": part["track_index"], "part_index": part["part_index"]}
        activity = np.flatnonzero(np.max(np.abs(original_pcm), axis=1) > np.max(np.abs(original_pcm)) * 0.001)
        v.require(len(activity) > 1, "Audio fixture has no active region")
        source_meta, _ = v.read_audio(source)
        ticks_per_second = 960  # The fixture project is 120 BPM at 480 PPQ.
        begin = max(1, min(width - 2, int((activity[0] / source_meta["sample_rate"] - 0.05) * ticks_per_second)))
        end = min(width - 1, max(begin + 1, int((activity[-1] / source_meta["sample_rate"] + 0.05) * ticks_per_second)))
        changed = await check.audio(sid, "edit_audio", **select, begin_tick=begin, end_tick=end, position_tick=240)
        v.require(changed["begin_tick"] == begin and changed["end_tick"] == end and changed["position_tick"] == 240, "Both audio boundaries did not persist in session", changed)
        _, path = await check.save(sid, "remaining-boundaries")
        reopened = (await check.call("project_open", path=str(path)))["session_id"]
        try:
            state = await check.audio(reopened, "edit_audio", **select)
            v.require(state["begin_tick"] == begin and state["end_tick"] == end and state["position_tick"] == 240, "Saved audio boundaries differ", state)
            exported = await check.audio(reopened, "export_audio", **select, original=True, output_name=check.output("whole-original", ".wav"))
            _, pcm = v.read_audio(exported["path"])
            v.require(pcm.shape == original_pcm.shape and np.allclose(pcm, original_pcm, atol=2/32768, rtol=0), "Whole original asset changed after trim")
            for rate in (48000, 96000):
                out = await check.audio(reopened, "mixdown", sample_rate=rate, bits_per_sample=24, channels=2, output_name=check.output(str(rate), ".wav"))
                meta, samples = v.read_audio(out["path"])
                v.require(meta["sample_rate"] == rate and meta["subtype"] == "PCM_24" and meta["channels"] == 2 and np.max(np.abs(samples)) > 0, "Rate render mismatch", meta)
                check.evidence("mix_" + str(rate), {"path": out["path"], **meta})
        finally:
            await check.close(reopened)
    v.require(source.read_bytes() == original, "Source asset modified")

if __name__ == "__main__":
    sys.exit(v.main())
