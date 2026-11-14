"""Exercise unknown VPR data through a real private native MCP session.

The diagnostic fixture is a copy of a freshly native-saved project with
sentinel-only unknown properties and one benign extra ZIP member.
"""
import json
from pathlib import Path
import zipfile

import verify_features as v


SENTINELS = {
    "root": "root-sentinel", "master": "master-sentinel", "track": "track-sentinel",
    "part": "part-sentinel", "note": "note-sentinel", "master_nested": "loop-sentinel",
    "note_nested": {"marker": "expression-sentinel", "value": [1, True, None]},
}
KEY = "x_bridge_preservation_probe"
NESTED_KEY = "x~nested/name"
EXTRA = "Project/bridge-probe/extra.bin"
EXTRA_BYTES = b"independent-project-resource\x00\x01"
EXTRA_AUDIO = "Project/Audio/opaque-extra.bin"
EXTRA_ROOT = "custom-probe/root.bin"


@v.feature("preservation.ai_dvqm_version_probe_50", "preservation", "voicebanks", "vocaloid_features",
           "project_create", "project_edit", "project_library", "project_save", "project_open")
async def ai_dvqm_version_probe(check):
    from vocaloid_bridge.install import discover, host_path, validate_target
    from vocaloid_bridge.native_client import IsolatedProcess

    product = (await check.call("vocaloid_features"))["product"]
    major = "7." if product == "VOCALOID7" else "6."
    voice_name = "GekiyakuV" if product == "VOCALOID7" else "asa"
    candidates = [item for item in (await check.call("voicebanks"))["voices"]
                  if str(item["version"]).startswith(major) and item["kind"] == "Dnn"
                  and item["available_in_sequence"]]
    if not candidates:
        raise v.Blocked(f"An installed available {product} AI voicebank is required")
    voice = next((item for item in candidates if item["name"] == voice_name), candidates[0])
    catalog = await check.library("dvqm_catalog", is_attack=True, voice_id=voice["comp_id"], limit=1)
    if not catalog["entries"]:
        raise v.Blocked("An installed native Attack preset is required for the isolated conflict probe")
    entry = catalog["entries"][0]
    part = {"track_index": 0, "part_index": 0}
    voice_scope = {**part, **({"scope": "track"} if product == "VOCALOID7" else {})}
    async with check.project() as identifier:
        await check.edit(identifier, "track.create", type="MidiAi", name="Version-specific AI DVQM probe")
        await check.edit(identifier, "part.create", track_index=0, start_tick=0, duration_tick=1920)
        await check.edit(identifier, "voice.set", **voice_scope, ai_voice_bank_id=voice["comp_id"])
        await check.edit(identifier, "note.add", **part, start_tick=0, duration_tick=480,
                         number=60, lyric="あ", phonemes="a", lang_id=0)
        expected_skill = await check.library("note_skill_set", identifier, **part, note_index=0,
                                             duration_tick=73, pre_weight=37, post_weight=91)
        sequence, baseline_path = await check.save(identifier, "version-ai-dvqm-baseline")
    saved_note = sequence["tracks"][0]["parts"][0]["notes"][0]
    v.require(saved_note["singingSkill"]["weight"] == {"pre": 37, "post": 91},
              "Native baseline did not save the intended HMM weights", saved_note)
    root = check.directory / "ai-dvqm-version-probe"
    root.mkdir()
    baseline = root / "baseline.vpr"
    baseline.write_bytes(baseline_path.read_bytes())
    _, members = v.read_vpr(baseline_path)
    saved_note["dvqm"] = {"attack": {"compID": entry["component_id"], "levelNames": entry["level_names"],
                                      "isProtected": True, "speed": 77, "topFactor": 1.0}}
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    conflict = root / "conflict.vpr"
    with zipfile.ZipFile(conflict, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    await check.rejected("project_open", "AI note .* combines Attack/Release and Singing Skill", path=str(conflict))
    installation = discover()
    host = host_path(v.ROOT, installation)
    validate_target(installation, host)
    v.require(installation.product == product, "AI DVQM probe selected a different native product")
    process = IsolatedProcess([r"C:\Program Files\PowerShell\7\pwsh.exe", "-NoProfile", "-File",
                               str(v.ROOT / "tools/probe_ai_dvqm_native_50.ps1"), "-Root", str(root),
                               "-Baseline", str(baseline), "-Conflict", str(conflict),
                               "-Install", str(installation.path), "-Product", product, "-HostPath", str(host),
                               "-DbId", str(entry["db_id"]), "-NameId", str(entry["name_id"])], v.ROOT)
    try:
        observed = json.loads(process.read_line(60))
    finally:
        process.close()
    check.evidence("ai_dvqm_product_probe", {"voice": voice, "preset": entry, "expected_skill": expected_skill,
                   "native": observed, "baseline": str(baseline), "conflict": str(conflict)})
    baseline_state = observed["baseline"]["state"]
    conflict_state = observed["conflict"]["state"]
    v.require(observed["product"] == product and observed["core_assembly"] == product
              and baseline_state["voice_id"] == voice["comp_id"] and conflict_state["voice_id"] == voice["comp_id"]
              and baseline_state["note_is_ai"] and conflict_state["note_is_ai"]
              and baseline_state["pre_weight"] == 37 and baseline_state["post_weight"] == 91
              and baseline_state["duration_tick"] == 73 and baseline_state["attack_empty"]
              and not conflict_state["attack_empty"] and conflict_state["pre_weight"] == 0
              and conflict_state["post_weight"] == 0 and observed["conflict"]["saved_singing_skill"] is None,
              "Native product probe did not reproduce the guarded conflict", observed)
    dvqm_first = observed["dvqm_then_hmm"]
    hmm_first = observed["hmm_then_dvqm"]
    for order in (dvqm_first, hmm_first):
        v.require(order["dvqm_result"] and order["weight_result"] and order["duration_result"] and order["commit"]
                  and order["saved_singing_skill"] is None and order["saved_dvqm"] is not None
                  and order["reopened"]["pre_weight"] == 0 and order["reopened"]["post_weight"] == 0,
                  "Native setter-order probe did not reproduce the serialization loss", order)
    v.require((dvqm_first["after"]["pre_weight"], dvqm_first["after"]["post_weight"]) == (37, 91)
              and (dvqm_first["undo"]["pre_weight"], dvqm_first["undo"]["post_weight"]) == (64, 64)
              and (hmm_first["after"]["pre_weight"], hmm_first["after"]["post_weight"]) == (0, 0)
              and (hmm_first["undo"]["pre_weight"], hmm_first["undo"]["post_weight"]) == (37, 91),
              "Native setter-order history differs from the observed conflict", observed)


@v.feature("preservation.note_library_transactions", "preservation", "score_compose", "project_edit",
           "project_library", "project_open", "project_save", "project_status", "project_get", "project_members", "project_call", "project_value_create", "native_api_catalog", "score_patch", "score_replace_notes")
async def note_library_transactions(check):
    catalog = await check.library("dvqm_catalog", is_attack=True, limit=1)
    if not catalog["entries"]:
        raise v.Blocked("An installed native Attack preset is required")
    entry = catalog["entries"][0]
    scope = {"track_index": 0, "part_index": 0}
    target = {**scope, "note_index": 0}
    attack = {**target, "is_attack": True}
    async with check.project(score=True) as identifier:
        await check.edit(identifier, "pitch.set", **target, points=[{"tick": 100, "value": 60}])
        await check.edit(identifier, "controller.set", **scope, type="Dynamics", points=[{"tick": 100, "value": 42}])
        lane = await check.edit(identifier, "automation.list", scope="track_volume", track_index=0)
        await check.edit(identifier, "automation.set", scope="track_volume", track_index=0,
                         points=[{"tick": 480, "value": lane["minimum"]}])
        original_skill = await check.library("note_skill_get", identifier, **target)
        sequence, native = await check.save(identifier, "note-library-native")
    native_original = native.read_bytes()
    attack_data = {"compID": entry["component_id"], "levelNames": entry["level_names"],
                   "isProtected": True, "speed": 77, "topFactor": 1.0}
    patch_output = check.output("note-library-dual")
    await check.rejected("score_patch", "AI note cannot combine Attack/Release and Singing Skill",
                         path=str(native), output_name=patch_output,
                         operations=[{"op": "add", "path": "/tracks/0/parts/0/notes/0/dvqm",
                                      "value": {"attack": attack_data}}])
    replacement_output = check.output("note-library-dual-replacement")
    await check.rejected("score_replace_notes", "AI note cannot combine Attack/Release and Singing Skill",
                         path=str(native), output_name=replacement_output,
                         notes=[{"start": 0, "duration": 1, "pitch": 60, "lyric": "あ", "phoneme": "a",
                                 "raw": {"dvqm": {"attack": attack_data}}}])
    v.require(native.read_bytes() == native_original and not (v.ROOT / "output" / patch_output).exists()
              and not (v.ROOT / "output" / replacement_output).exists(),
              "Rejected AI DVQM file edits changed their source or published an output")
    _, members = v.read_vpr(native)
    track = sequence["tracks"][0]
    part = track["parts"][0]
    note = part["notes"][0]
    sequence[KEY] = "root"
    track[KEY] = "track"
    part[KEY] = "part"
    note[KEY] = "note"
    note["aiExp"][KEY] = "expression"
    note["directPitches"][0][KEY] = "pitch"
    next(item for item in part["controllers"] if item["name"].lower() == "dynamics")["events"][0][KEY] = "controller"
    next(item for item in track["volume"]["events"] if item["pos"] == 480)[KEY] = "automation"
    members[EXTRA] = EXTRA_BYTES

    def write_fixture(data, label):
        result = v.ROOT / "output" / check.output(label)
        contents = dict(members)
        contents["Project/sequence.json"] = json.dumps(data, ensure_ascii=False).encode("utf-8")
        with zipfile.ZipFile(result, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, payload in contents.items():
                archive.writestr(name, payload)
        return result

    dual_data = json.loads(json.dumps(sequence))
    dual_data["tracks"][0]["parts"][0]["notes"][0]["dvqm"] = {"attack": attack_data}
    dual_source = write_fixture(dual_data, "note-library-external-dual")
    dual_original = dual_source.read_bytes()
    await check.rejected("project_open", "AI note .* combines Attack/Release and Singing Skill",
                         path=str(dual_source))
    repaired = await check.call("score_patch", path=str(dual_source), output_name=check.output("note-library-dual-repaired"),
                                operations=[{"op": "remove", "path": "/tracks/0/parts/0/notes/0/dvqm"}])
    expected_repaired = json.loads(json.dumps(dual_data))
    del expected_repaired["tracks"][0]["parts"][0]["notes"][0]["dvqm"]
    v.require(v.read_vpr(repaired["path"])[0] == expected_repaired,
              "Explicit VPR repair changed data outside the requested subtree")
    dual = (await check.call("project_open", path=repaired["path"]))["session_id"]
    try:
        dual_saved, _ = await check.save(dual, "note-library-external-dual-saved")
        saved_note = dual_saved["tracks"][0]["parts"][0]["notes"][0]
        v.require((await check.library("dvqm_get", dual, **attack))["is_empty"]
                  and await check.library("note_skill_get", dual, **target) == original_skill
                  and saved_note.get("singingSkill") == dual_data["tracks"][0]["parts"][0]["notes"][0].get("singingSkill")
                  and v.read_vpr(repaired["path"])[1][EXTRA] == EXTRA_BYTES
                  and dual_source.read_bytes() == dual_original,
                  "Explicit VPR repair lost Singing Skill, resources or the original file")
    finally:
        await check.close(dual)

    release_catalog = await check.library("dvqm_catalog", is_attack=False, limit=1)
    if not release_catalog["entries"]:
        raise v.Blocked("An installed native Release preset is required")
    release_entry = release_catalog["entries"][0]
    release_data = {"compID": release_entry["component_id"], "levelNames": release_entry["level_names"],
                    "isProtected": True, "speed": 77, "topFactor": 1.0}
    release_dual_data = json.loads(json.dumps(sequence))
    release_dual_data["tracks"][0]["parts"][0]["notes"][0]["dvqm"] = {"release": release_data}
    release_source = write_fixture(release_dual_data, "note-library-external-release-dual")
    release_original = release_source.read_bytes()
    await check.rejected("project_open", "AI note .* combines Attack/Release and Singing Skill",
                         path=str(release_source))
    release_repaired = await check.call("score_patch", path=str(release_source),
                                        output_name=check.output("note-library-release-repaired"),
                                        operations=[{"op": "remove", "path": "/tracks/0/parts/0/notes/0/singingSkill"}])
    expected_release = json.loads(json.dumps(release_dual_data))
    del expected_release["tracks"][0]["parts"][0]["notes"][0]["singingSkill"]
    v.require(v.read_vpr(release_repaired["path"])[0] == expected_release,
              "Explicit Release repair changed data outside the requested subtree")
    release_session = (await check.call("project_open", path=release_repaired["path"]))["session_id"]
    try:
        selected_release = await check.library("dvqm_get", release_session, **target, is_attack=False)
        release_saved, release_saved_path = await check.save(release_session, "note-library-release-saved")
        saved_release = release_saved["tracks"][0]["parts"][0]["notes"][0]["dvqm"]["release"]
        v.require(not selected_release["is_empty"] and selected_release["component_id"] == release_entry["component_id"]
                  and saved_release["compID"] == release_entry["component_id"]
                  and v.read_vpr(release_saved_path)[1][EXTRA] == EXTRA_BYTES
                  and release_source.read_bytes() == release_original,
                  "Explicit Release repair lost the selection, resource or original file")
    finally:
        await check.close(release_session)

    def verify_markers(data):
        track = data["tracks"][0]
        part = track["parts"][0]
        note = part["notes"][0]
        v.require(data[KEY] == "root" and track[KEY] == "track" and part[KEY] == "part"
                  and note[KEY] == "note" and note["aiExp"][KEY] == "expression"
                  and note["directPitches"][0][KEY] == "pitch"
                  and next(item for item in part["controllers"] if item["name"].lower() == "dynamics")["events"][0][KEY] == "controller"
                  and next(item for item in track["volume"]["events"] if item["pos"] == 480)[KEY] == "automation",
                  "A note library mutation lost unrelated metadata")

    source = write_fixture(sequence, "note-library-extended")
    original = source.read_bytes()
    identifier = (await check.call("project_open", path=str(source)))["session_id"]
    try:
        before, _ = await check.save(identifier, "note-library-before")
        before_status = await check.call("project_status", session_id=identifier)
        before_history = await check.edit(identifier, "history.status")
        track_ref = (await check.method(identifier, "GetTrack", [0]))["value"]["$ref"]
        part_ref = (await check.method(identifier, "GetPart", [0], track_ref))["value"]["$ref"]
        note_ref = (await check.method(identifier, "GetNote", [0], part_ref))["value"]["$ref"]
        for is_attack in (True, False):
            selected = {**target, "is_attack": is_attack}
            before_selection = await check.library("dvqm_get", identifier, **selected)
            v.require(before_selection["is_empty"], "No-op fixture unexpectedly contains DVQM")
            v.require(await check.library("dvqm_clear", identifier, **selected) == before_selection,
                      "Clearing an empty DVQM changed the selection")
        v.require((await check.call("project_status", session_id=identifier))["dirty"] == before_status["dirty"]
                  and await check.edit(identifier, "history.status") == before_history
                  and (await check.call("project_get", session_id=identifier, ref=note_ref, member="NoteNumber"))["value"] == 60,
                  "Empty DVQM clear changed dirty state, history or existing references")
        after_noop, _ = await check.save(identifier, "note-library-noop")
        v.require(after_noop == before, "Empty DVQM clear changed the saved project")
        skill = await check.library("note_skill_get", identifier, **target)
        weight = 0 if skill["pre_weight"] != 0 else 1
        changed = await check.library("note_skill_set", identifier, **target, pre_weight=weight)
        v.require(changed["pre_weight"] == weight, "Note skill update failed", changed)
        changed_data, _ = await check.save(identifier, "note-library-changed")
        verify_markers(changed_data)
        await check.edit(identifier, "undo")
        undone, _ = await check.save(identifier, "note-library-undo")
        v.require(undone == before and await check.library("note_skill_get", identifier, **target) == skill,
                  "Note skill undo did not restore the original project")
        await check.edit(identifier, "redo")
        redone, redone_path = await check.save(identifier, "note-library-redo")
        v.require(redone == changed_data, "Note skill redo did not restore the modified project")
        reopened = (await check.call("project_open", path=str(redone_path)))["session_id"]
        try:
            restored, restored_path = await check.save(reopened, "note-library-reopened")
            verify_markers(restored)
            v.require(await check.library("note_skill_get", reopened, **target) == changed,
                      "Note skill update did not survive reopening")
            v.require(v.read_vpr(restored_path)[1][EXTRA] == EXTRA_BYTES, "Project resource changed")
        finally:
            await check.close(reopened)
        await check.library("note_skill_reset", identifier, **target)
        reset, _ = await check.save(identifier, "note-library-reset")
        verify_markers(reset)
    finally:
        await check.close(identifier)
    v.require(source.read_bytes() == original, "Source project changed")

    guarded = json.loads(json.dumps(before))
    guarded_note = guarded["tracks"][0]["parts"][0]["notes"][0]
    guarded_note["singingSkill"][KEY] = "skill-extension"
    guarded_source = write_fixture(guarded, "note-library-guarded")
    guarded_original = guarded_source.read_bytes()
    identifier = (await check.call("project_open", path=str(guarded_source)))["session_id"]
    try:
        before, _ = await check.save(identifier, "note-library-guard-before")
        history = await check.edit(identifier, "history.status")
        for operation, options in (("note_skill_set", {**target, "pre_weight": 0}), ("note_skill_reset", target)):
            await check.rejected("project_library", "unknown fields", session_id=identifier,
                                 operation=operation, options=options)
        after, _ = await check.save(identifier, "note-library-guard-after")
        v.require(after == before and await check.edit(identifier, "history.status") == history,
                  "Rejected note library mutation changed the project or history")
    finally:
        await check.close(identifier)
    v.require(guarded_source.read_bytes() == guarded_original, "Guarded source project changed")
    conflict = json.loads(json.dumps(before))
    conflict_note = conflict["tracks"][0]["parts"][0]["notes"][0]
    conflict_note.pop("singingSkill", None)
    conflict_note["dvqm"] = {"attack": {"compID": entry["component_id"], "levelNames": entry["level_names"],
                                         "isProtected": True, "speed": 77, "topFactor": 1.0}}
    conflict_source = write_fixture(conflict, "note-library-dvqm-conflict")
    conflict_original = conflict_source.read_bytes()
    identifier = (await check.call("project_open", path=str(conflict_source)))["session_id"]
    try:
        before_conflict, _ = await check.save(identifier, "note-library-conflict-before")
        history = await check.edit(identifier, "history.status")
        v.require(not (await check.library("dvqm_get", identifier, **attack))["is_empty"],
                  "DVQM conflict fixture did not load")
        await check.rejected("project_library", "identity transaction|cannot preserve", session_id=identifier,
                     operation="dvqm_clear", options=attack)
        for operation, options in (("note_skill_set", {**target, "pre_weight": 0}), ("note_skill_reset", target)):
            await check.rejected("project_library", "cannot persist", session_id=identifier,
                                 operation=operation, options=options)
        track_ref = (await check.method(identifier, "GetTrack", [0]))["value"]["$ref"]
        part_ref = (await check.method(identifier, "GetPart", [0], track_ref))["value"]["$ref"]
        note_ref = (await check.method(identifier, "GetNote", [0], part_ref))["value"]["$ref"]
        members = await check.call("project_members", session_id=identifier, ref=note_ref)
        catalog = await check.call("native_api_catalog", type="Yamaha.VOCALOID.VSM.VSMRelTick")
        constructor = next(item for item in catalog["types"][0]["members"] if item["kind"] == "constructor"
                           and item["supported"] and len(item["parameters"]) == 1
                           and item["parameters"][0]["value_type"] in ("System.Int32", "System.Int64"))
        tick = await check.call("project_value_create", session_id=identifier, type=catalog["types"][0]["type"],
                                args=[240], member_id=constructor["member_id"])
        arguments = {"SetHmmWeight": [0, 0], "SetHmmWeightDuration": [tick["value"]], "ResetHmmWeightDefault": []}
        for name, args in arguments.items():
            method = next(item for item in members["methods"] if item["member_id"].startswith(name + "("))
            await check.rejected("project_call", "AI notes with Attack/Release cannot preserve Singing Skill",
                                 session_id=identifier, ref=note_ref, member_id=method["member_id"], args=args)
        after_conflict, _ = await check.save(identifier, "note-library-conflict-after")
        v.require(after_conflict == before_conflict and await check.edit(identifier, "history.status") == history,
                  "Rejected DVQM conflict changed the project or history")
    finally:
        await check.close(identifier)
    v.require(conflict_source.read_bytes() == conflict_original, "DVQM conflict source changed")


@v.feature("preservation.controller_split_native_probe", "preservation", "score_compose", "project_edit", "project_save")
async def controller_split_native_probe(check):
    seed = await check.call("score_compose", output_name=check.output("controller-split-probe"), title="Controller split probe", bpm=120,
                            notes=[{"start": 0, "duration": 0.5, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    sid = seed["native_session"]["session_id"]
    await check.edit(sid, "controller.set", track_index=0, part_index=0, type="Dynamics", replace=True,
                     points=[{"tick": 60, "value": 30}, {"tick": 480, "value": 40}, {"tick": 720, "value": 50}])
    await check.edit(sid, "part.split", track_index=0, part_index=0, split_tick=480)
    split, _ = await check.save(sid, "controller-split-probe-result")
    check.evidence("controller_split_native", {"parts": [{"pos": p["pos"], "duration": p["duration"], "controllers": p["controllers"]} for p in split["tracks"][0]["parts"]]})
    await check.edit(sid, "part.join", track_index=0, part_indices=[0, 1])
    joined, _ = await check.save(sid, "controller-join-probe-result")
    check.evidence("controller_join_native", {"parts": [{"pos": p["pos"], "duration": p["duration"], "controllers": p["controllers"]} for p in joined["tracks"][0]["parts"]]})
    await check.close(sid)


@v.feature("preservation.array_guard", "preservation", "score_compose", "project_open")
async def array_guard(check):
    """Unknown array-element fields must survive edits and archive roundtrips."""
    seed = await check.call("score_compose", output_name=check.output("array-guard-seed"),
                            title="Array guard", bpm=120,
                            notes=[{"start": 0, "duration": 1, "pitch": 60,
                                    "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    await check.close(seed["native_session"]["session_id"])
    sequence, members = v.read_vpr(seed["path"])
    for label, select in (
        ("effect-parameter", lambda s: s["tracks"][0]["parts"][0]["audioEffects"][0]["parameters"][0]),
        ("language", lambda s: s["tracks"][0]["parts"][0]["aiVoice"]["langIDs"][0]),
    ):
        fixture = json.loads(json.dumps(sequence))
        select(fixture)[KEY] = label
        fixture_members = dict(members)
        fixture_members[EXTRA] = EXTRA_BYTES
        fixture_members["Project/sequence.json"] = json.dumps(fixture, ensure_ascii=False).encode("utf-8")
        path = v.ROOT / "output" / check.output("array-guard-" + label)
        with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, payload in fixture_members.items():
                archive.writestr(name, payload)
        original = path.read_bytes()
        sid = (await check.call("project_open", path=str(path)))["session_id"]
        before, _ = await check.save(sid, "array-before-" + label)
        await check.edit(sid, "track.update", track_index=0, name="Array preserved")
        edited, _ = await check.save(sid, "array-edited-" + label)
        v.require(edited["tracks"][0]["name"] == "Array preserved", "Track rename did not persist")
        await check.edit(sid, "undo")
        undone, _ = await check.save(sid, "array-undo-" + label)
        v.require(undone == before, "Array metadata undo differs")
        await check.edit(sid, "redo")
        saved, saved_path = await check.save(sid, "array-redo-" + label)
        v.require(saved == edited, "Array metadata redo differs")
        reopened = (await check.call("project_open", path=str(saved_path)))["session_id"]
        restored, restored_path = await check.save(reopened, "array-reopen-" + label)
        v.require(restored == saved and select(restored)[KEY] == label, "Unknown array field was lost")
        v.require(v.read_vpr(restored_path)[1][EXTRA] == EXTRA_BYTES, "Array fixture resource was lost")
        v.require(path.read_bytes() == original, "Array fixture was modified")
        check.evidence("array_guard_" + label, {"path": str(restored_path), "preserved": True})
        await check.close(reopened)
        await check.close(sid)


async def preserved_edit(check, sid, operation, **options):
    before, before_path = await check.save(sid, "preserved-before")
    history = await check.edit(sid, "history.status")
    await check.edit(sid, operation, **options)
    after, after_path = await check.save(sid, "preserved-after")
    resources = lambda path: {name: data for name, data in v.read_vpr(path)[1].items()
                              if name != "Project/sequence.json"}
    v.require(resources(before_path) == resources(after_path), "Mutation changed archive resources")
    if before != after:
        await check.edit(sid, "undo")
        undone, _ = await check.save(sid, "preserved-undo")
        v.require(undone == before, "Mutation undo differs", operation)
        await check.edit(sid, "redo")
        redone, _ = await check.save(sid, "preserved-redo")
        v.require(redone == after, "Mutation redo differs", operation)
    else:
        v.require(await check.edit(sid, "history.status") == history, "No-op added native history")
    reopened = (await check.call("project_open", path=str(after_path)))["session_id"]
    try:
        restored, restored_path = await check.save(reopened, "preserved-reopen")
        v.require(restored == after and resources(restored_path) == resources(after_path),
                  "Mutation reopen lost sequence or resources", operation)
    finally:
        await check.close(reopened)
    if before != after:
        await check.edit(sid, "undo")
    return before, after


@v.feature("preservation.controller_array_roundtrip", "preservation", "score_compose", "project_open", "project_edit", "project_save")
async def controller_array_roundtrip(check):
    """Exercise explicit controller identities across edits and native history."""
    seed = await check.call("score_compose", output_name=check.output("controller-seed"),
                            title="Controller array guard", bpm=120,
                            notes=[{"start": 0, "duration": 1, "pitch": 60,
                                    "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    sid = seed["native_session"]["session_id"]
    await check.edit(sid, "controller.set", track_index=0, part_index=0, type="Dynamics",
                     points=[{"tick": 60, "value": 30}, {"tick": 180, "value": 64}], replace=True)
    sequence, seed_path = await check.save(sid, "controller-native")
    await check.close(sid)
    controllers = sequence["tracks"][0]["parts"][0]["controllers"]
    events = next(c["events"] for c in controllers if c["name"] == "dynamics")
    v.require([(e["pos"], e["value"]) for e in events] == [(60, 30), (180, 64)],
              "Controller serialization differs", events)
    _, members = v.read_vpr(seed_path)
    events[0][KEY] = {"marker": "first", "nested": [True, None]}
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("controller-extension-input")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    original = source.read_bytes()
    sid = (await check.call("project_open", path=str(source)))["session_id"]
    async with check.project() as plain_target:
        before, _ = await check.save(plain_target, "controller-merge-before")
        await check.call("project_merge", session_id=plain_target,
                         path=str(source), include_tracks=True, include_tempo=False)
        merged, merged_path = await check.save(plain_target, "controller-merge-after")
        v.require(merged["tracks"][-1]["parts"][0]["controllers"] == controllers,
                  "Controller merge lost extended events")
        await check.edit(plain_target, "undo")
        undone, _ = await check.save(plain_target, "controller-merge-undo")
        v.require(undone == before, "Controller merge undo differs")
        await check.edit(plain_target, "redo")
        redone, _ = await check.save(plain_target, "controller-merge-redo")
        v.require(redone == merged, "Controller merge redo differs")
        reopened = (await check.call("project_open", path=str(merged_path)))["session_id"]
        restored, _ = await check.save(reopened, "controller-merge-reopen")
        v.require(restored == merged, "Controller merge reopen differs")
        await check.close(reopened)
        v.require(source.read_bytes() == original, "Controller merge changed source")
    initial_guard, _ = await check.save(sid, "controller-timeline-guard-before")
    for operation in ("time.insert", "time.delete"):
        _, current = await preserved_edit(check, sid, operation,
            start_tick=20000, duration_tick=480, include_tempo=True)
        v.require(current["tracks"] == initial_guard["tracks"] and source.read_bytes() == original,
                  "Distant timeline edit changed controller metadata or source")
    lane = {"track_index": 0, "part_index": 0, "type": "Dynamics"}
    marker = {"marker": "first", "nested": [True, None]}

    async def snapshot(session, label, expected):
        result, path = await check.save(session, "controller-" + label)
        lanes = result["tracks"][0]["parts"][0].get("controllers", [])
        events = next((c["events"] for c in lanes if c["name"] == "dynamics"), [])
        actual = [(e["pos"], e["value"], e.get(KEY)) for e in events]
        v.require(actual == expected, "Controller metadata differs", {"actual": actual, "expected": expected})
        return path

    initial = [(60, 30, marker), (180, 64, None)]
    moved = [(180, 64, None), (240, 40, marker)]
    await snapshot(sid, "initial", initial)
    await check.rejected("project_edit", "destination is ambiguous", session_id=sid,
                         operation="controller.set", options={**lane, "controller_index": 0,
                         "points": [{"tick": 180, "value": 40}]})
    await snapshot(sid, "collision", initial)
    await check.edit(sid, "controller.set", **lane, controller_index=0, points=[{"tick": 240, "value": 40}])
    await snapshot(sid, "moved", moved)
    await check.edit(sid, "undo"); await snapshot(sid, "undo", initial)
    await check.edit(sid, "redo"); await snapshot(sid, "redo", moved)
    clone = (await check.call("project_clone", session_id=sid))["session_id"]
    await check.edit(sid, "controller.remove", **lane, controller_index=1)
    await check.edit(sid, "controller.set", **lane, points=[{"tick": 240, "value": 40}])
    recreated = [(180, 64, None), (240, 40, None)]
    await snapshot(sid, "recreated", recreated)
    await check.edit(sid, "note.update", track_index=0, part_index=0, note_index=0, number=61)
    await check.edit(sid, "undo")
    await snapshot(sid, "empty-controller-unrelated-undo", recreated)
    await check.edit(sid, "undo"); await snapshot(sid, "undo-insert", moved[:1])
    await check.edit(sid, "undo"); await snapshot(sid, "undo-remove", moved)
    await check.edit(sid, "redo"); await check.edit(sid, "redo")
    await check.edit(sid, "controller.set", **lane, replace=True,
                     points=[{"tick": 240, "value": 40}])
    path = await snapshot(sid, "replace", [(240, 40, None)])
    await snapshot(clone, "clone", moved)
    await check.edit(clone, "controller.set", **lane, replace=True,
                     points=[{"tick": 240, "value": 40}])
    await snapshot(clone, "replace-marked", [(240, 40, None)])
    await check.edit(clone, "undo"); await snapshot(clone, "undo-replace", moved)
    reopened = (await check.call("project_open", path=str(path)))["session_id"]
    await snapshot(reopened, "reopen", [(240, 40, None)])
    await check.edit(clone, "part.duplicate", track_index=0, part_index=0, start_tick=9600)
    duplicate, _ = await check.save(clone, "controller-duplicate")
    parts = duplicate["tracks"][0]["parts"]
    for part in parts:
        events = next(c["events"] for c in part["controllers"] if c["name"] == "dynamics")
        v.require([(e["pos"], e["value"], e.get(KEY)) for e in events] == moved, "Duplicated controller mapping differs", events)
    await check.edit(clone, "undo")
    await snapshot(clone, "duplicate-undo", moved)
    await check.edit(clone, "redo")
    await check.edit(clone, "undo")
    await check.edit(clone, "part.split", track_index=0, part_index=0, split_tick=480)
    split, _ = await check.save(clone, "controller-split")
    events = next(c["events"] for c in split["tracks"][0]["parts"][0]["controllers"] if c["name"] == "dynamics")
    v.require([(e["pos"], e["value"], e.get(KEY)) for e in events] == moved, "Split controller mapping differs", events)
    right = next(c["events"] for c in split["tracks"][0]["parts"][1]["controllers"] if c["name"] == "dynamics")
    v.require([(e["pos"], e["value"], e.get(KEY)) for e in right] == [(0, 40, None)],
              "Generated native boundary point inherited metadata", right)
    await check.edit(clone, "part.join", track_index=0, part_indices=[0, 1])
    joined = moved + [(480, 40, None)]
    joined_path = await snapshot(clone, "join", joined)
    joined_session = (await check.call("project_open", path=str(joined_path)))["session_id"]
    await snapshot(joined_session, "join-reopen", joined)
    await check.close(joined_session)
    await check.edit(clone, "undo")
    await check.edit(clone, "undo")
    await snapshot(clone, "split-undo", moved)
    v.require(source.read_bytes() == original, "Controller source fixture was modified")
    for session in (reopened, clone, sid): await check.close(session)



@v.feature("preservation.controller_identity_ambiguity", "preservation", "score_compose", "project_open", "project_edit", "project_save")
async def controller_identity_ambiguity(check):
    seed = await check.call("score_compose", output_name=check.output("controller-ambiguous-seed"),
                            title="Controller ambiguity", bpm=120,
                            notes=[{"start": 0, "duration": 1, "pitch": 60,
                                    "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    sid = seed["native_session"]["session_id"]
    await check.edit(sid, "controller.set", track_index=0, part_index=0, type="Dynamics",
                     points=[{"tick": 60, "value": 30}])
    tracks = (await check.edit(sid, "track.list"))["tracks"]
    await check.edit(sid, "track.duplicate", track_index=0, name=tracks[0]["name"])
    sequence, path = await check.save(sid, "controller-ambiguous-native")
    await check.close(sid)
    _, members = v.read_vpr(path)
    for index, track in enumerate(sequence["tracks"]):
        events = next(c["events"] for c in track["parts"][0]["controllers"] if c["name"] == "dynamics")
        events[0][KEY] = {"track": index}
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("controller-ambiguous-input")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    original = source.read_bytes()
    await check.rejected("project_open", "indistinguishable track identities", path=str(source))
    v.require(source.read_bytes() == original, "Ambiguous controller fixture was modified")


@v.feature("preservation.timesig_array_roundtrip", "preservation", "score_compose", "project_open", "project_edit", "project_save", "project_clone", "project_merge")
async def timesig_array_roundtrip(check):
    seed = await check.call("score_compose", output_name=check.output("timesig-seed"), title="Time signature extensions", bpm=120,
                            notes=[{"start": 0, "duration": 1, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    sid = seed["native_session"]["session_id"]
    await check.edit(sid, "time_signature.set", bar=2, numerator=3, denominator=4)
    await check.edit(sid, "time_signature.set", bar=4, numerator=5, denominator=4)
    sequence, seed_path = await check.save(sid, "timesig-native")
    await check.close(sid)
    _, members = v.read_vpr(seed_path)
    for event in sequence["masterTrack"]["timeSig"]["events"]:
        event[KEY] = {"marker": event["bar"], "nested": [True, None]}
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("timesig-input")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    original = source.read_bytes()
    sid = (await check.call("project_open", path=str(source)))["session_id"]
    async def assert_events(session, label, expected):
        result, path = await check.save(session, "timesig-" + label)
        actual = [(e["bar"], e["numer"], e["denom"], e.get(KEY)) for e in result["masterTrack"]["timeSig"]["events"]]
        v.require(actual == expected, "Time signature metadata state differs", {"actual": actual, "expected": expected})
        return path

    def marker(bar): return {"marker": bar, "nested": [True, None]}
    initial = [(0, 4, 4, marker(0)), (2, 3, 4, marker(2)), (4, 5, 4, marker(4))]
    moved = [(0, 4, 4, marker(0)), (4, 5, 4, marker(4)), (6, 7, 8, marker(2))]
    await assert_events(sid, "initial", initial)
    await check.rejected("project_edit", "time signature destination is ambiguous", session_id=sid,
                         operation="time_signature.set", options={"time_signature_index": 1, "bar": 4, "numerator": 7, "denominator": 8})
    await assert_events(sid, "collision", initial)
    await check.edit(sid, "time_signature.set", time_signature_index=1, bar=6, numerator=7, denominator=8)
    await assert_events(sid, "move", moved)
    await check.edit(sid, "undo"); await assert_events(sid, "undo", initial)
    await check.edit(sid, "redo"); await assert_events(sid, "redo", moved)
    clone = (await check.call("project_clone", session_id=sid))["session_id"]
    await check.edit(sid, "time_signature.remove", time_signature_index=2)
    await check.edit(sid, "time_signature.set", bar=6, numerator=7, denominator=8)
    recreated = moved[:-1] + [(6, 7, 8, None)]
    await assert_events(sid, "recreated", recreated)
    await check.edit(sid, "undo"); await assert_events(sid, "undo-insert", moved[:-1])
    await check.edit(sid, "undo"); await assert_events(sid, "undo-remove", moved)
    await check.edit(sid, "redo"); await check.edit(sid, "redo")
    path = await assert_events(sid, "redo-recreated", recreated)
    await assert_events(clone, "clone", moved)
    reopened = (await check.call("project_open", path=str(path)))["session_id"]
    await assert_events(reopened, "reopen", recreated)
    v.require(source.read_bytes() == original, "Source project changed")
    for session in (reopened, clone, sid): await check.close(session)


@v.feature("preservation.tempo_array_semantics", "preservation", "score_compose", "project_edit", "project_save")
async def tempo_array_semantics(check):
    """Observe serialized tempo transitions without opening user projects."""
    seed = await check.call("score_compose", output_name=check.output("tempo-array-seed"),
                            title="Tempo array semantics", bpm=120,
                            notes=[{"start": 0, "duration": 1, "pitch": 60,
                                    "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    sid = seed["native_session"]["session_id"]

    async def snapshot(label):
        sequence, path = await check.save(sid, "tempo-array-" + label)
        result = [(e["pos"], e["value"]) for e in sequence["masterTrack"]["tempo"]["events"]]
        check.evidence("tempo_" + label, {"path": str(path), "events": result})
        return result

    await check.edit(sid, "tempo.set", start_tick=480, bpm=130)
    await check.edit(sid, "tempo.set", start_tick=960, bpm=140)
    before = await snapshot("before")
    await check.edit(sid, "tempo.set", tempo_index=1, start_tick=1440, bpm=135)
    moved = await snapshot("moved")
    v.require(moved == [(0, 12000), (960, 14000), (1440, 13500)], "Unexpected tempo move")
    await check.edit(sid, "undo")
    v.require(await snapshot("undo_move") == before, "Undo did not restore tempo array")
    await check.edit(sid, "redo")
    v.require(await snapshot("redo_move") == moved, "Redo did not restore tempo array")
    await check.edit(sid, "tempo.remove", tempo_index=2)
    await check.edit(sid, "tempo.set", start_tick=1440, bpm=135)
    v.require(await snapshot("recreated") == moved, "Recreated tempo serialized differently")
    await check.close(sid)


@v.feature("preservation.tempo_array_roundtrip", "preservation", "score_compose", "project_open", "project_edit", "project_save", "project_clone", "project_clipboard", "project_create", "project_merge")
async def tempo_array_roundtrip(check):
    seed = await check.call("score_compose", output_name=check.output("tempo-extension-seed"),
                            title="Tempo extensions", bpm=120,
                            notes=[{"start": 0, "duration": 1, "pitch": 60,
                                    "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    sid = seed["native_session"]["session_id"]
    await check.edit(sid, "tempo.set", start_tick=480, bpm=130)
    await check.edit(sid, "tempo.set", start_tick=960, bpm=140)
    sequence, seed_path = await check.save(sid, "tempo-extension-native")
    await check.close(sid)
    _, members = v.read_vpr(seed_path)
    events = sequence["masterTrack"]["tempo"]["events"]
    for event in events:
        event[KEY] = {"marker": "event-" + str(event["pos"]), "nested": [True, None]}
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("tempo-extension-input")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    original = source.read_bytes()
    sid = (await check.call("project_open", path=str(source)))["session_id"]

    async def assert_events(session, label, expected):
        result, path = await check.save(session, "tempo-extension-" + label)
        actual = [(event["pos"], event["value"], event.get(KEY))
                  for event in result["masterTrack"]["tempo"]["events"]]
        v.require(actual == expected, "Tempo metadata state differs", {"actual": actual, "expected": expected})
        check.evidence("tempo_extension_" + label, {"path": str(path), "events": actual})
        return path

    def marker(pos):
        return {"marker": "event-" + str(pos), "nested": [True, None]}
    initial = [(0, 12000, marker(0)), (480, 13000, marker(480)), (960, 14000, marker(960))]
    moved = [(0, 12000, marker(0)), (960, 14000, marker(960)), (1440, 13500, marker(480))]
    await assert_events(sid, "initial", initial)
    await check.rejected("project_edit", "tempo destination is ambiguous", session_id=sid,
                         operation="tempo.set", options={"tempo_index": 1, "start_tick": 960, "bpm": 135})
    await assert_events(sid, "collision", initial)
    await check.edit(sid, "tempo.set", tempo_index=1, start_tick=480, bpm=130)
    await assert_events(sid, "no-op", initial)
    await check.call("project_merge", session_id=sid, path=str(seed_path), include_tracks=False,
                     include_tempo=True, offset_tick=1920)
    merged, _ = await check.save(sid, "tempo-extension-target-merge")
    merged_events = merged["masterTrack"]["tempo"]["events"]
    v.require([e["pos"] for e in merged_events] == [0, 480, 960, 1920, 2400, 2880] and
              [e.get(KEY) for e in merged_events] == [marker(0), marker(480), marker(960), None, None, None],
              "Merge changed target tempo extensions")
    await check.edit(sid, "undo")
    await assert_events(sid, "merge-target-undo", initial)
    plain = (await check.call("project_open", path=str(seed_path)))["session_id"]
    try:
        await check.edit(plain, "tempo.set", start_tick=1920, bpm=90)
        await check.call("project_merge", session_id=plain, path=str(source), include_tracks=False,
                         include_tempo=True, replace_tempo=True)
        await assert_events(plain, "merge-source-replace", initial)
        await check.edit(plain, "undo")
        undone, _ = await check.save(plain, "tempo-extension-source-merge-undo")
        v.require([e["pos"] for e in undone["masterTrack"]["tempo"]["events"]] == [0, 480, 960, 1920] and
                  all(KEY not in e for e in undone["masterTrack"]["tempo"]["events"]),
                  "Source tempo merge undo changed original target")
    finally:
        await check.close(plain)
    clip = (await check.call("project_clipboard", session_id=sid, operation="copy",
                             options={"kind": "tracks", "indices": [0]}))["clipboard_id"]
    try:
        target = (await check.call("project_create", title="Tempo clipboard target"))["session_id"]
        try:
            await check.call("project_clipboard", session_id=target, operation="paste", options={"clipboard_id": clip})
            pasted, _ = await check.save(target, "tempo-clipboard-target")
            v.require(all(KEY not in event for event in pasted["masterTrack"]["tempo"]["events"]),
                      "Track-only clipboard paste incorrectly transferred project tempo metadata")
        finally:
            await check.close(target)
    finally:
        await check.call("project_clipboard", operation="clear", options={"clipboard_id": clip})
    await check.edit(sid, "tempo.set", tempo_index=1, start_tick=1440, bpm=135)
    await assert_events(sid, "moved", moved)
    await check.edit(sid, "undo")
    await assert_events(sid, "undo", initial)
    await check.edit(sid, "redo")
    await assert_events(sid, "redo", moved)
    clone = (await check.call("project_clone", session_id=sid))["session_id"]
    await check.edit(sid, "tempo.remove", tempo_index=2)
    await check.edit(sid, "tempo.set", start_tick=1440, bpm=135)
    recreated = moved[:-1] + [(1440, 13500, None)]
    path = await assert_events(sid, "recreated", recreated)
    await check.edit(sid, "undo")
    await assert_events(sid, "undo-recreate", moved[:-1])
    await check.edit(sid, "undo")
    await assert_events(sid, "undo-remove", moved)
    await check.edit(sid, "redo")
    await check.edit(sid, "redo")
    path = await assert_events(sid, "redo-recreate", recreated)
    await assert_events(clone, "clone", moved)
    reopened = (await check.call("project_open", path=str(path)))["session_id"]
    await assert_events(reopened, "reopened", recreated)
    v.require(source.read_bytes() == original, "Source project changed")
    for session in (reopened, clone, sid):
        await check.close(session)


@v.feature("preservation.tempo_only_similar_tracks", "preservation", "score_compose", "project_open", "project_edit", "project_save")
async def tempo_only_similar_tracks(check):
    seed = await check.call("score_compose", output_name=check.output("tempo-similar-seed"),
                            title="Tempo-only metadata", bpm=120,
                            notes=[{"start": 0, "duration": 1, "pitch": 60,
                                    "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    sid = seed["native_session"]["session_id"]
    await check.edit(sid, "track.duplicate", track_index=0)
    await check.edit(sid, "automation.set", scope="track_volume", track_index=1,
                     points=[{"tick": 0, "value": -120}], replace=True)
    sequence, seed_path = await check.save(sid, "tempo-similar-native")
    await check.close(sid)
    v.require(sequence["tracks"][0]["volume"] != sequence["tracks"][1]["volume"],
              "Fixture does not contain different known track values")
    _, members = v.read_vpr(seed_path)
    sequence["masterTrack"]["tempo"]["events"][0][KEY] = "tempo-only"
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("tempo-similar-input")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    original = source.read_bytes()
    target = (await check.call("project_open", path=str(source)))["session_id"]
    try:
        await check.edit(target, "tempo.set", tempo_index=0, start_tick=0, bpm=125)
        saved, path = await check.save(target, "tempo-similar-saved")
        v.require(saved["masterTrack"]["tempo"]["events"][0][KEY] == "tempo-only" and
                  saved["tracks"][0]["volume"] != saved["tracks"][1]["volume"],
                  "Tempo-only extension or known track values were lost")
        reopened = (await check.call("project_open", path=str(path)))["session_id"]
        await check.close(reopened)
    finally:
        await check.close(target)
    v.require(source.read_bytes() == original, "Tempo-only source changed")


def properties(sequence, members):
    track = sequence["tracks"][0]
    part = track["parts"][0]
    note = part["notes"][0]
    return {"root": sequence.get(KEY), "master": sequence["masterTrack"].get(KEY),
            "track": track.get(KEY), "part": part.get(KEY), "note": note.get(KEY),
            "master_nested": sequence["masterTrack"]["loop"].get(NESTED_KEY),
            "note_nested": note["exp"].get(NESTED_KEY),
            "extra": members.get(EXTRA) == EXTRA_BYTES,
            "extra_audio": members.get(EXTRA_AUDIO) == EXTRA_BYTES,
            "extra_root": members.get(EXTRA_ROOT) == EXTRA_BYTES}


@v.feature("preservation.unknown_fields", "preservation", "score_compose", "project_open", "project_edit",
           "project_save", "project_clone")
async def unknown_fields(check):
    seed = await check.call("score_compose", output_name=check.output("preservation-seed"),
                            title="Preservation probe", bpm=120,
                            notes=[{"start": 0, "duration": 1, "pitch": 60,
                                    "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    seed_session = seed["native_session"]["session_id"]
    await check.close(seed_session)
    sequence, members = v.read_vpr(seed["path"])
    for obj, value in ((sequence, SENTINELS["root"]), (sequence["masterTrack"], SENTINELS["master"]),
                       (sequence["tracks"][0], SENTINELS["track"]),
                       (sequence["tracks"][0]["parts"][0], SENTINELS["part"]),
                       (sequence["tracks"][0]["parts"][0]["notes"][0], SENTINELS["note"])):
        obj[KEY] = value
    sequence["masterTrack"]["loop"][NESTED_KEY] = SENTINELS["master_nested"]
    sequence["tracks"][0]["parts"][0]["notes"][0]["exp"][NESTED_KEY] = SENTINELS["note_nested"]
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    members[EXTRA] = EXTRA_BYTES
    members[EXTRA_AUDIO] = EXTRA_BYTES
    members[EXTRA_ROOT] = EXTRA_BYTES
    source = v.ROOT / "output" / check.output("preservation-input")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    original = source.read_bytes()
    identifier = (await check.call("project_open", path=str(source)))['session_id']
    await check.edit(identifier, "note.update", track_index=0, part_index=0, note_index=0,
                     number=61, expression={"Accent": 51})
    saved, path = await check.save(identifier, "preservation-edited")
    _, saved_members = v.read_vpr(path)
    state = properties(saved, saved_members)
    check.evidence("saved_unknown_fields", {"source": str(source), "saved": str(path), "observed": state})
    reopened = (await check.call("project_open", path=str(path)))['session_id']
    actual_note = (await check.edit(reopened, "note.list", track_index=0, part_index=0))["notes"][0]
    v.require(actual_note["number"] == 61, "Known note edit did not persist")
    v.require(actual_note["expression"]["Accent"] == 51 and saved["tracks"][0]["parts"][0]["notes"][0]["exp"]["accent"] == 51,
              "Known expression edit was overwritten by retained unknown data")
    reopened_saved, reopened_path = await check.save(reopened, "preservation-reopened")
    _, reopened_members = v.read_vpr(reopened_path)
    reopened_state = properties(reopened_saved, reopened_members)
    check.evidence("reopened_unknown_fields", {"saved": str(reopened_path), "observed": reopened_state})
    clone = (await check.call("project_clone", session_id=identifier))["session_id"]
    await check.close(identifier)
    clone_saved, clone_path = await check.save(clone, "preservation-clone")
    _, clone_members = v.read_vpr(clone_path)
    clone_state = properties(clone_saved, clone_members)
    check.evidence("clone_unknown_fields", {"saved": str(clone_path), "observed": clone_state})
    v.require(source.read_bytes() == original, "Native editing modified the input VPR")
    expected = {**SENTINELS, "extra": True, "extra_audio": True, "extra_root": True}
    v.require(state == expected and reopened_state == expected and clone_state == expected,
              "Unknown project data did not roundtrip", {"save": state, "reopened": reopened_state, "clone": clone_state})
    await check.close(clone)
    await check.close(reopened)


@v.feature("preservation.identity", "preservation", "score_compose", "project_open", "project_edit", "project_save")
async def identity(check):
    seed = await check.call("score_compose", output_name=check.output("identity-seed"), title="Identity probe", bpm=120,
                            notes=[{"start": 0, "duration": .5, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0},
                                   {"start": 1, "duration": .5, "pitch": 64, "lyric": "い", "phoneme": "i", "lang_id": 0}])
    seed_id = seed["native_session"]["session_id"]
    await check.edit(seed_id, "track.duplicate", track_index=0, name="Other")
    sequence, native_seed = await check.save(seed_id, "identity-native-seed")
    await check.close(seed_id)
    _, members = v.read_vpr(native_seed)
    for track_index, track in enumerate(sequence["tracks"]):
        track[KEY] = f"track-{track_index}"
        for part_index, part in enumerate(track["parts"]):
            part[KEY] = f"part-{track_index}-{part_index}"
            for note_index, note in enumerate(part["notes"]):
                note[KEY] = f"note-{track_index}-{part_index}-{note_index}"
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("identity-input")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    identifier = (await check.call("project_open", path=str(source)))["session_id"]
    await check.edit(identifier, "track.reorder", track_index=0, to_index=1)
    await check.edit(identifier, "track.update", track_index=1, name="Renamed original")
    await check.edit(identifier, "note.update", track_index=1, part_index=0, note_index=0,
                     start_tick=120, number=61)
    saved, path = await check.save(identifier, "identity-moved")
    moved = saved["tracks"][1]
    require = v.require
    require(saved["tracks"][0].get(KEY) == "track-1" and moved.get(KEY) == "track-0",
            "Reordered track metadata attached to the wrong track")
    require(moved["parts"][0].get(KEY) == "part-0-0" and
            moved["parts"][0]["notes"][0].get(KEY) == "note-0-0-0",
            "Part or moved/edited note metadata was lost")
    await check.edit(identifier, "note.remove", track_index=1, part_index=0, note_index=0)
    await check.edit(identifier, "note.add", track_index=1, part_index=0, start_tick=120,
                     duration_tick=240, number=61, lyric="あ", phonemes="a", lang_id=0)
    replaced, _ = await check.save(identifier, "identity-replacement")
    require(KEY not in replaced["tracks"][1]["parts"][0]["notes"][0],
            "Removed note metadata was attached to a replacement note")
    await check.edit(identifier, "undo")
    await check.edit(identifier, "undo")
    undone, _ = await check.save(identifier, "identity-undo")
    require(undone["tracks"][1]["parts"][0]["notes"][0].get(KEY) == "note-0-0-0",
            "Undo failed to restore original note metadata")
    await check.edit(identifier, "redo")
    await check.edit(identifier, "redo")
    redone, _ = await check.save(identifier, "identity-redo")
    require(KEY not in redone["tracks"][1]["parts"][0]["notes"][0],
            "Redo attached deleted metadata to replacement note")
    check.evidence("identity_outputs", {"source": str(source), "moved": str(path)})
    await check.close(identifier)


@v.feature("preservation.parameter_edits", "preservation", "score_compose", "project_edit", "project_open", "project_save")
async def parameter_edits(check):
    seed = await check.call("score_compose", output_name=check.output("parameter-seed"), title="Preserved parameters", bpm=120,
                            notes=[{"start": 0, "duration": 1, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    await check.close(seed["native_session"]["session_id"])
    sequence, members = v.read_vpr(seed["path"])
    sequence[KEY] = "root"
    sequence["masterTrack"]["loop"][KEY] = "loop"
    track = sequence["tracks"][0]
    track[KEY] = "track"
    part = track["parts"][0]
    part[KEY] = "part"
    part["notes"][0][KEY] = "note"
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("parameter-input")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    sid = (await check.call("project_open", path=str(source)))["session_id"]
    scope = {"track_index": 0, "part_index": 0}
    await check.edit(sid, "sequence.update", title="Changed title")
    await check.edit(sid, "tempo.set", start_tick=0, bpm=130)
    await check.edit(sid, "loop.set", start_tick=0, end_tick=1920, enabled=True)
    await check.edit(sid, "tuning.set", value=442)
    await check.edit(sid, "note.batch_update", **scope, note_indices=[0], transpose=2)
    product = (await check.call("vocaloid_features"))["product"]
    performance_scope = {"scope": "track", "track_index": 0} if product == "VOCALOID7" else scope
    check.evidence("performance_scope", {"product": product, **performance_scope})
    await check.edit(sid, "performance.set", **performance_scope, voice_colors={"S5Air": 25})
    if product == "VOCALOID7":
        vibrato = await check.edit(sid, "vibrato.get", **scope, note_index=0)
        model = next(value for value in vibrato["curve_models"] if value != vibrato["curve_model"])
        await check.edit(sid, "vibrato.set", **scope, note_index=0, curve_model=model)
        check.evidence("vibrato_curve_model", model)
    else:
        await check.edit(sid, "vibrato.set", **scope, note_index=0, ai_enabled=False)
    saved, path = await check.save(sid, "parameter-preserved")
    v.require(saved[KEY] == "root" and saved["masterTrack"]["loop"][KEY] == "loop", "Root/loop metadata changed")
    part = saved["tracks"][0]["parts"][0]
    v.require(saved["tracks"][0][KEY] == "track" and part[KEY] == "part" and part["notes"][0][KEY] == "note",
              "Parameter edits lost entity metadata")
    reopened = (await check.call("project_open", path=str(path)))["session_id"]
    note = (await check.edit(reopened, "note.list", **scope))["notes"][0]
    v.require(note["number"] == 62 and
              (note["curve_model"] == model if product == "VOCALOID7" else not note["ai_vibrato_enabled"]),
              "Parameter edits were replaced by old data", note)
    v.require((await check.edit(reopened, "tuning.get"))["value"] == 442, "Native tuning changed")
    check.evidence("parameter_preservation", {"source": str(source), "saved": str(path), "note": note})
    await check.close(reopened)
    await check.close(sid)


@v.feature("preservation.duplicates", "preservation", "score_compose", "project_edit", "project_open", "project_save", "project_clone")
async def duplicates(check):
    seed = await check.call("score_compose", output_name=check.output("duplicates-seed"), title="Duplicate metadata", bpm=120,
                            notes=[{"start": 0, "duration": .5, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    await check.close(seed["native_session"]["session_id"])
    sequence, members = v.read_vpr(seed["path"])
    track = sequence["tracks"][0]; part = track["parts"][0]; note = part["notes"][0]
    track[KEY] = "track-copy"; part[KEY] = "part-copy"; note[KEY] = "note-copy"
    note["exp"][NESTED_KEY] = {"copy": [1, 2]}
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("duplicates-input")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    original = source.read_bytes()
    identifier = (await check.call("project_open", path=str(source)))["session_id"]
    await check.edit(identifier, "track.duplicate", track_index=0, name=track["name"])
    saved, same_path = await check.save(identifier, "duplicates-same-name")
    def check_track(track):
        v.require(track[KEY] == "track-copy", "Copied track metadata lost")
        v.require(track["parts"][0][KEY] == "part-copy", "Copied part metadata lost")
        v.require(track["parts"][0]["notes"][0][KEY] == "note-copy" and
                  track["parts"][0]["notes"][0]["exp"][NESTED_KEY] == {"copy": [1, 2]}, "Copied note metadata lost")
    v.require(len(saved["tracks"]) == 2 and saved["tracks"][0]["name"] == saved["tracks"][1]["name"],
              "Test requires same-name duplicate tracks")
    for track in saved["tracks"]: check_track(track)
    divergent = json.loads(json.dumps(saved)); divergent["tracks"][1][KEY] = "different-unknown-value"
    _, same_members = v.read_vpr(same_path)
    same_members["Project/sequence.json"] = json.dumps(divergent, ensure_ascii=False).encode("utf-8")
    ambiguous_path = v.ROOT / "output" / check.output("duplicates-ambiguous")
    with zipfile.ZipFile(ambiguous_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in same_members.items(): archive.writestr(name, payload)
    ambiguous_bytes = ambiguous_path.read_bytes()
    await check.rejected("project_open", "indistinguishable|ambiguous", path=str(ambiguous_path))
    v.require(ambiguous_path.read_bytes() == ambiguous_bytes, "Ambiguous open changed the source")
    await check.edit(identifier, "undo")
    undone, _ = await check.save(identifier, "duplicates-undo")
    v.require(len(undone["tracks"]) == 1, "Undo did not remove duplicate")
    check_track(undone["tracks"][0])
    await check.edit(identifier, "redo")
    await check.edit(identifier, "note.duplicate", track_index=0, part_index=0, note_index=0, start_tick=1920)
    await check.edit(identifier, "part.duplicate", track_index=0, part_index=0, start_tick=9600)
    expanded, path = await check.save(identifier, "duplicates-expanded")
    v.require(len(expanded["tracks"]) == 2, "Redo did not restore duplicated track")
    for track in expanded["tracks"]: check_track(track)
    parts = expanded["tracks"][0]["parts"]
    v.require(len(parts) == 2 and all(p[KEY] == "part-copy" for p in parts), "Part duplicate lost metadata")
    v.require(all(len(p["notes"]) == 2 and all(n[KEY] == "note-copy" and n["exp"][NESTED_KEY] == {"copy": [1, 2]}
                                               for n in p["notes"]) for p in parts), "Duplicated notes lost metadata")
    await check.edit(identifier, "undo"); await check.edit(identifier, "undo")
    reverted, _ = await check.save(identifier, "duplicates-children-undo")
    v.require(len(reverted["tracks"][0]["parts"]) == 1 and len(reverted["tracks"][0]["parts"][0]["notes"]) == 1,
              "Child duplicate undo did not restore the source tree")
    await check.edit(identifier, "redo"); await check.edit(identifier, "redo")
    expanded, path = await check.save(identifier, "duplicates-children-redo")
    v.require(len(expanded["tracks"][0]["parts"]) == 2 and
              all(n[KEY] == "note-copy" for p in expanded["tracks"][0]["parts"] for n in p["notes"]),
              "Child duplicate redo lost note metadata")
    reopened = (await check.call("project_open", path=str(path)))["session_id"]
    clone = (await check.call("project_clone", session_id=reopened))["session_id"]
    await check.close(reopened); await check.close(identifier)
    cloned, _ = await check.save(clone, "duplicates-clone")
    v.require(len(cloned["tracks"]) == 2 and all(t[KEY] == "track-copy" for t in cloned["tracks"]),
              "Duplicate metadata did not survive source-independent clone")
    v.require(source.read_bytes() == original, "Duplicate operations changed the original VPR")
    await check.close(clone)


@v.feature("preservation.note_split", "preservation", "score_compose", "project_edit", "project_open", "project_save")
async def note_split(check):
    seed = await check.call("score_compose", output_name=check.output("split-seed"), title="Split metadata", bpm=120,
                            notes=[{"start": 0, "duration": 1, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    await check.close(seed["native_session"]["session_id"])
    sequence, members = v.read_vpr(seed["path"])
    note = sequence["tracks"][0]["parts"][0]["notes"][0]
    note[KEY] = "split-note"
    note["exp"][NESTED_KEY] = {"split": [1, 2]}
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("split-input")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    identifier = (await check.call("project_open", path=str(source)))["session_id"]
    scope = {"track_index": 0, "part_index": 0}
    await check.edit(identifier, "note.split", **scope, note_index=0, split_tick=240)
    def verify(saved, count):
        notes = saved["tracks"][0]["parts"][0]["notes"]
        v.require(len(notes) == count and all(n.get(KEY) == "split-note" and
                  n["exp"].get(NESTED_KEY) == {"split": [1, 2]} for n in notes), "Split note metadata changed")
    saved, _ = await check.save(identifier, "split-result"); verify(saved, 2)
    await check.edit(identifier, "undo")
    saved, _ = await check.save(identifier, "split-undo"); verify(saved, 1)
    await check.edit(identifier, "redo")
    saved, path = await check.save(identifier, "split-redo"); verify(saved, 2)
    conflict, conflict_members = v.read_vpr(path)
    conflict["tracks"][0]["parts"][0]["notes"][1][KEY] = "different"
    conflict_members["Project/sequence.json"] = json.dumps(conflict, ensure_ascii=False).encode("utf-8")
    conflict_path = v.ROOT / "output" / check.output("join-conflict")
    with zipfile.ZipFile(conflict_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in conflict_members.items(): archive.writestr(name, payload)
    conflict_id = (await check.call("project_open", path=str(conflict_path)))["session_id"]
    await check.rejected("project_edit", "conflicting note join metadata", session_id=conflict_id,
                         operation="note.join", options={**scope, "note_indices": [0, 1]})
    conflict_saved, _ = await check.save(conflict_id, "join-conflict-rollback")
    v.require([n[KEY] for n in conflict_saved["tracks"][0]["parts"][0]["notes"]] == ["split-note", "different"],
              "Join conflict did not roll back both notes and metadata")
    await check.close(conflict_id)
    reopened = (await check.call("project_open", path=str(path)))["session_id"]
    saved, _ = await check.save(reopened, "split-reopen"); verify(saved, 2)
    await check.edit(reopened, "note.join", **scope, note_indices=[0, 1])
    saved, _ = await check.save(reopened, "join-result"); verify(saved, 1)
    await check.edit(reopened, "undo")
    saved, _ = await check.save(reopened, "join-undo"); verify(saved, 2)
    await check.edit(reopened, "redo")
    saved, path = await check.save(reopened, "join-redo"); verify(saved, 1)
    joined = (await check.call("project_open", path=str(path)))["session_id"]
    saved, _ = await check.save(joined, "join-reopen"); verify(saved, 1)
    await check.close(joined)
    await check.close(reopened); await check.close(identifier)


@v.feature("preservation.part_split_join", "preservation", "score_compose", "project_edit", "project_open", "project_save")
async def part_split_join(check):
    seed = await check.call("score_compose", output_name=check.output("part-split-seed"), title="Part split", bpm=120,
                            notes=[{"start": i, "duration": 1, "pitch": 60 + i, "lyric": "あ", "phoneme": "a", "lang_id": 0}
                                   for i in (0, 1, 3)])
    await check.close(seed["native_session"]["session_id"])
    sequence, members = v.read_vpr(seed["path"])
    part = sequence["tracks"][0]["parts"][0]; part[KEY] = "part"
    for i, note in enumerate(part["notes"]): note[KEY] = "note-" + str(i)
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("part-split-input")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    sid = (await check.call("project_open", path=str(source)))["session_id"]
    await check.edit(sid, "part.split", track_index=0, part_index=0, split_tick=720)
    def verify(saved, counts):
        parts = saved["tracks"][0]["parts"]
        v.require([len(p["notes"]) for p in parts] == counts and all(p[KEY] == "part" for p in parts), "Part split/join changed metadata")
        v.require([n[KEY] for p in parts for n in p["notes"]] == ["note-0", "note-1", "note-2"], "Part split/join changed note metadata")
    saved, _ = await check.save(sid, "part-split"); verify(saved, [2, 1])
    await check.edit(sid, "undo"); saved, _ = await check.save(sid, "part-split-undo"); verify(saved, [3])
    await check.edit(sid, "redo"); saved, path = await check.save(sid, "part-split-redo"); verify(saved, [2, 1])
    conflict, cm = v.read_vpr(path); conflict["tracks"][0]["parts"][1][KEY] = "different"
    cm["Project/sequence.json"] = json.dumps(conflict, ensure_ascii=False).encode("utf-8")
    cp = v.ROOT / "output" / check.output("part-join-conflict")
    with zipfile.ZipFile(cp, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in cm.items(): archive.writestr(name, payload)
    cid = (await check.call("project_open", path=str(cp)))["session_id"]
    await check.rejected("project_edit", "conflicting part join metadata", session_id=cid,
                         operation="part.join", options={"track_index": 0, "part_indices": [0, 1]})
    saved, _ = await check.save(cid, "part-conflict-rollback")
    v.require([p[KEY] for p in saved["tracks"][0]["parts"]] == ["part", "different"], "Part conflict rollback changed metadata")
    await check.close(cid)
    await check.edit(sid, "part.join", track_index=0, part_indices=[0, 1])
    saved, _ = await check.save(sid, "part-join"); verify(saved, [3])
    await check.edit(sid, "undo"); saved, _ = await check.save(sid, "part-join-undo"); verify(saved, [2, 1])
    await check.edit(sid, "redo"); saved, path = await check.save(sid, "part-join-redo"); verify(saved, [3])
    reopened = (await check.call("project_open", path=str(path)))["session_id"]
    saved, _ = await check.save(reopened, "part-join-reopen"); verify(saved, [3])
    await check.close(reopened); await check.close(sid)


@v.feature("preservation.clipboard_old_history", "preservation", "score_compose", "project_open", "project_create",
           "project_clipboard", "project_edit", "project_save")
async def clipboard_old_history(check):
    seed = await check.call("score_compose", output_name=check.output("history-source-seed"), title="History source", bpm=120,
                            notes=[{"start": 0, "duration": .5, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    await check.close(seed["native_session"]["session_id"])
    sequence, members = v.read_vpr(seed["path"])
    sequence["tracks"][0][KEY] = "transferred-track"
    sequence["tracks"][0]["parts"][0]["notes"][0][KEY] = "transferred-note"
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("history-source")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    sid = (await check.call("project_open", path=str(source)))["session_id"]
    clip = (await check.call("project_clipboard", session_id=sid, operation="copy",
                             options={"kind": "tracks", "indices": [0]}))["clipboard_id"]
    await check.close(sid)
    try:
        async with check.project() as target:
            await check.edit(target, "track.create", name="old")
            await check.edit(target, "track.update", track_index=0, name="old-edited")
            await check.call("project_clipboard", session_id=target, operation="paste",
                             options={"clipboard_id": clip, "offset_tick": 960})
            saved, _ = await check.save(target, "history-paste")
            v.require(len(saved["tracks"]) == 2 and saved["tracks"][1][KEY] == "transferred-track", "Paste lost extension")
            await check.edit(target, "undo")
            saved, _ = await check.save(target, "history-unpaste")
            v.require(len(saved["tracks"]) == 1 and saved["tracks"][0]["name"] == "old-edited", "Undo paste changed old track")
            await check.edit(target, "undo")
            saved, _ = await check.save(target, "history-old-undo")
            v.require(len(saved["tracks"]) == 1 and saved["tracks"][0]["name"] == "old", "Old edit undo failed")
            await check.edit(target, "undo")
            saved, _ = await check.save(target, "history-old-empty")
            v.require(not saved.get("tracks", []), "Old create undo failed")
            await check.edit(target, "redo"); await check.edit(target, "redo"); await check.edit(target, "redo")
            saved, path = await check.save(target, "history-redo-paste")
            v.require(len(saved["tracks"]) == 2 and saved["tracks"][0]["name"] == "old-edited" and
                      saved["tracks"][1][KEY] == "transferred-track" and
                      saved["tracks"][1]["parts"][0]["notes"][0][KEY] == "transferred-note", "History redo lost data")
            reopened = (await check.call("project_open", path=str(path)))["session_id"]
            await check.close(reopened)
            await check.edit(target, "undo"); await check.edit(target, "undo")
            await check.edit(target, "track.update", track_index=0, name="branch")
            status = await check.edit(target, "history.status")
            v.require(not status["can_redo"], "New branch retained redo")
            saved, _ = await check.save(target, "history-branch")
            v.require(len(saved["tracks"]) == 1 and saved["tracks"][0]["name"] == "branch", "Branch changed old state")
    finally:
        await check.call("project_clipboard", operation="clear", options={"clipboard_id": clip})


@v.feature("preservation.native_duplicate_order", "preservation", "score_compose", "project_edit", "project_save", "project_open")
async def native_duplicate_order(check):
    seed = await check.call("score_compose", output_name=check.output("duplicate-order-seed"), title="Native order", bpm=120,
                            notes=[{"start": 0, "duration": .5, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0},
                                   {"start": 1, "duration": .5, "pitch": 64, "lyric": "い", "phoneme": "i", "lang_id": 0}])
    identifier = seed["native_session"]["session_id"]
    original = (await check.edit(identifier, "track.list"))["tracks"][0]
    await check.edit(identifier, "track.update", track_index=0, color=3)
    await check.edit(identifier, "track.duplicate", track_index=0, name=original["name"])
    await check.edit(identifier, "track.update", track_index=1, color=7)
    await check.edit(identifier, "track.reorder", track_index=0, to_index=1)
    await check.edit(identifier, "part.duplicate", track_index=0, part_index=0, start_tick=9600)
    await check.edit(identifier, "note.duplicate", track_index=0, part_index=0, note_index=0, start_tick=1920)
    tracks = (await check.edit(identifier, "track.list"))["tracks"]
    parts = (await check.edit(identifier, "part.list", track_index=0))["parts"]
    notes = (await check.edit(identifier, "note.list", track_index=0, part_index=0))["notes"]
    saved, path = await check.save(identifier, "duplicate-order")
    v.require([(t["name"], t["color"], t["type"]) for t in tracks] ==
              [(t["name"], t["color"], {0: "Midi", 1: "Audio", 2: "MidiAi"}[t["type"]]) for t in saved["tracks"]],
              "Native VPR track order differs from live enumeration")
    v.require([(p["start_tick"], p["duration_tick"]) for p in parts] ==
              [(p["pos"], p["duration"]) for p in saved["tracks"][0]["parts"]],
              "Native VPR part order differs from live enumeration")
    v.require([(n["start_tick"], n["number"]) for n in notes] ==
              [(n["pos"], n["number"]) for n in saved["tracks"][0]["parts"][0]["notes"]],
              "Native VPR note order differs from live enumeration")
    reopened = (await check.call("project_open", path=str(path)))["session_id"]
    reopened_tracks = (await check.edit(reopened, "track.list"))["tracks"]
    v.require([(t["name"], t["color"], t["type"]) for t in reopened_tracks] ==
              [(t["name"], t["color"], t["type"]) for t in tracks], "Native reopen changed track order")
    check.evidence("native_duplicate_order", {"vpr": str(path), "tracks": tracks, "parts": parts,
                                              "notes": [(n["start_tick"], n["number"]) for n in notes]})
    await check.close(reopened)
    await check.close(identifier)



@v.feature("preservation.timeline_native_probe", "preservation", "score_compose", "project_edit", "project_save")
async def timeline_native_probe(check):
    """Capture private native timeline and history behavior, without claiming extension mapping."""
    for include_tempo in (False, True):
        seed = await check.call("score_compose", output_name=check.output("timeline-seed"), title="Timeline probe", bpm=120,
            notes=[{"start": 0, "duration": .5, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0},
                   {"start": 1, "duration": .5, "pitch": 64, "lyric": "い", "phoneme": "i", "lang_id": 0}])
        sid = seed["native_session"]["session_id"]
        scope = {"track_index": 0, "part_index": 0}
        await check.edit(sid, "controller.set", **scope, type="Dynamics", replace=True,
                         points=[{"tick": 60, "value": 30}, {"tick": 480, "value": 60}])
        await check.edit(sid, "part.move", **scope, start_tick=3840)
        await check.edit(sid, "tempo.set", start_tick=1920, bpm=130)
        await check.edit(sid, "tempo.set", start_tick=3840, bpm=140)
        await check.edit(sid, "time_signature.set", bar=2, numerator=3, denominator=4)
        async def snapshot(label):
            sequence, _ = await check.save(sid, "timeline-%s-%s" % (include_tempo, label))
            return {"tracks": sequence["tracks"], "master": sequence["masterTrack"]}
        before = await snapshot("before")
        for operation, start, duration in (("time.insert", 4000, 120), ("time.delete", 3700, 400)):
            original, changed = await preserved_edit(check, sid, operation,
                start_tick=start, duration_tick=duration, include_tempo=include_tempo)
            v.require(changed["tracks"] != original["tracks"], "Crossing timeline edit did not change parts")
            v.require(await snapshot(operation + "-restored") == before, "Crossing undo changed project")
        await check.edit(sid, "time.insert", start_tick=1920, duration_tick=1920, include_tempo=include_tempo)
        inserted = await snapshot("inserted")
        await check.edit(sid, "undo")
        v.require(await snapshot("insert-undo") == before, "Insert undo mismatch")
        await check.edit(sid, "redo")
        v.require(await snapshot("insert-redo") == inserted, "Insert redo mismatch")
        await check.edit(sid, "time.delete", start_tick=1920, duration_tick=1920, include_tempo=include_tempo)
        deleted = await snapshot("deleted")
        await check.edit(sid, "undo")
        v.require(await snapshot("delete-undo") == inserted, "Delete undo mismatch")
        await check.edit(sid, "redo")
        v.require(await snapshot("delete-redo") == deleted, "Delete redo mismatch")
        check.evidence("timeline_native_" + str(include_tempo), {"before": before, "inserted": inserted, "deleted": deleted})
        await check.close(sid)

@v.feature("preservation.timeline_extension_guard", "preservation", "score_compose", "project_open", "project_edit", "project_save")
async def timeline_extension_guard(check):
    """Generated meter boundaries preserve surviving entity and event metadata."""
    seed = await check.call("score_compose", output_name=check.output("timeline-extension-seed"), title="Timeline extension guard", bpm=120,
        notes=[{"start": 0, "duration": .5, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    sid = seed["native_session"]["session_id"]
    await check.edit(sid, "part.move", track_index=0, part_index=0, start_tick=7680)
    await check.edit(sid, "tempo.set", start_tick=1920, bpm=130)
    await check.edit(sid, "time_signature.set", bar=2, numerator=3, denominator=4)
    await check.edit(sid, "time_signature.set", bar=3, numerator=4, denominator=4)
    seq, path = await check.save(sid, "timeline-extension-native")
    await check.close(sid)
    _, members = v.read_vpr(path)
    seq["tracks"][0][KEY] = "track"
    seq["tracks"][0]["parts"][0][KEY] = "part"
    seq["tracks"][0]["parts"][0]["notes"][0][KEY] = "note"
    seq["masterTrack"]["tempo"]["events"][1][KEY] = "tempo"
    seq["masterTrack"]["timeSig"]["events"][1][KEY] = "signature"
    members["Project/sequence.json"] = json.dumps(seq, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("timeline-extension-input")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    original = source.read_bytes()
    sid = (await check.call("project_open", path=str(source)))["session_id"]
    _, changed = await preserved_edit(check, sid, "time.delete",
        start_tick=3840, duration_tick=1700, include_tempo=True)
    part = changed["tracks"][0]["parts"][0]
    v.require(part["pos"] == 5980 and part[KEY] == "part" and part["notes"][0][KEY] == "note"
              and changed["tracks"][0][KEY] == "track", "Timeline deletion lost entity identity")
    v.require(changed["masterTrack"]["tempo"] == seq["masterTrack"]["tempo"], "Earlier tempo metadata changed")
    v.require(any(event.get(KEY) == "signature" for event in changed["masterTrack"]["timeSig"]["events"]),
              "Surviving boundary meter lost metadata")
    saved, out = await check.save(sid, "timeline-extension-guarded")
    v.require(saved == seq, "Guard changed project content")
    v.require(source.read_bytes() == original, "Guard changed source file")
    clone = (await check.call("project_clone", session_id=sid))["session_id"]
    cloned, _ = await check.save(clone, "timeline-extension-clone")
    v.require(cloned == seq, "Clone changed guarded project")
    reopened = (await check.call("project_open", path=str(out)))["session_id"]
    reopened_seq, _ = await check.save(reopened, "timeline-extension-reopened")
    v.require(reopened_seq == seq, "Reopen changed guarded project")
    await check.close(reopened); await check.close(clone); await check.close(sid)

@v.feature("preservation.timeline_entity_roundtrip", "preservation", "score_compose", "project_open", "project_edit", "project_save")
async def timeline_entity_roundtrip(check):
    """AI entity extensions follow moving and wholly deleted parts through history."""
    seed = await check.call("score_compose", output_name=check.output("timeline-entity-seed"), title="Timeline entities", bpm=120,
        notes=[{"start": 0, "duration": .5, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    sid = seed["native_session"]["session_id"]
    await check.edit(sid, "part.move", track_index=0, part_index=0, start_tick=7680)
    await check.edit(sid, "tempo.set", start_tick=2000, bpm=130)
    seq, path = await check.save(sid, "timeline-entity-native")
    await check.close(sid)
    _, members = v.read_vpr(path)
    seq["tracks"][0][KEY] = "track"
    seq["tracks"][0]["parts"][0][KEY] = "part"
    seq["tracks"][0]["parts"][0]["notes"][0][KEY] = "note"
    members["Project/sequence.json"] = json.dumps(seq, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("timeline-entity-input")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    original = source.read_bytes()
    sid = (await check.call("project_open", path=str(source)))["session_id"]
    await check.edit(sid, "track.update", track_index=0, name="prior history")
    before, _ = await check.save(sid, "timeline-entity-before")
    _, split = await preserved_edit(check, sid, "time.insert",
        start_tick=8000, duration_tick=500, include_tempo=True)
    parts = split["tracks"][0]["parts"]
    v.require(len(parts) == 2 and all(part.get(KEY) == "part" for part in parts)
              and all(note.get(KEY) == "note" for part in parts for note in part.get("notes", [])),
              "Crossing insertion lost split entity metadata", parts)
    await check.edit(sid, "time.insert", start_tick=1000, duration_tick=500, include_tempo=True)
    moved, _ = await check.save(sid, "timeline-entity-moved")
    part = moved["tracks"][0]["parts"][0]
    v.require(part["pos"] == 8180 and part[KEY] == "part" and part["notes"][0][KEY] == "note", "Moved entity metadata mismatch")
    v.require([e["pos"] for e in moved["masterTrack"]["tempo"]["events"]] == [0, 2500],
              "Unextended tempo map did not follow timeline insertion")
    await check.edit(sid, "undo")
    restored, _ = await check.save(sid, "timeline-entity-move-undo")
    v.require(restored == before, "Move undo mismatch")
    await check.edit(sid, "undo")
    await check.edit(sid, "redo")
    older, _ = await check.save(sid, "timeline-entity-older-redo")
    v.require(older == before, "Older history mismatch")
    await check.edit(sid, "redo")
    redone, _ = await check.save(sid, "timeline-entity-move-redo")
    v.require(redone == moved, "Move redo mismatch")
    await check.edit(sid, "time.delete", start_tick=7000, duration_tick=10000, include_tempo=False)
    deleted, _ = await check.save(sid, "timeline-entity-deleted")
    v.require(not deleted["tracks"][0].get("parts", []) and deleted["tracks"][0][KEY] == "track", "Deletion retained a part")
    await check.edit(sid, "undo")
    restored, _ = await check.save(sid, "timeline-entity-delete-undo")
    v.require(restored == moved, "Delete undo mismatch")
    await check.edit(sid, "redo")
    redone, out = await check.save(sid, "timeline-entity-delete-redo")
    v.require(redone == deleted, "Delete redo mismatch")
    clone = (await check.call("project_clone", session_id=sid))["session_id"]
    cloned, _ = await check.save(clone, "timeline-entity-clone")
    reopened = (await check.call("project_open", path=str(out)))["session_id"]
    reopened_seq, _ = await check.save(reopened, "timeline-entity-reopen")
    v.require(cloned == deleted and reopened_seq == deleted and source.read_bytes() == original, "Clone, reopen or source mismatch")
    await check.close(reopened); await check.close(clone); await check.close(sid)

@v.feature("preservation.timeline_audio_guard", "preservation", "score_compose", "project_audio", "project_open", "project_edit", "project_save")
async def timeline_audio_guard(check):
    """Distant timeline edits preserve audio assets and extended entities."""
    seed = await check.call("score_compose", output_name=check.output("timeline-audio-seed"), title="Timeline audio guard", bpm=120,
        notes=[{"start": 0, "duration": .5, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    sid = seed["native_session"]["session_id"]
    audio = await check.audio_input()
    audio_original = audio.read_bytes()
    await check.audio(sid, "import_audio", path=str(audio), position_tick=0)
    seq, path = await check.save(sid, "timeline-audio-native")
    await check.close(sid)
    _, members = v.read_vpr(path)
    audio_members = {name: data for name, data in members.items() if name.startswith("Project/Audio/")}
    v.require(bool(audio_members), "Audio fixture has no project audio resources")
    seq["tracks"][0][KEY] = "entity extension"
    members["Project/sequence.json"] = json.dumps(seq, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("timeline-audio-input")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    original = source.read_bytes()
    sid = (await check.call("project_open", path=str(source)))["session_id"]
    before, _ = await check.save(sid, "timeline-audio-before")
    for operation in ("time.insert", "time.delete"):
        for include_tempo in (False, True):
            _, after = await preserved_edit(check, sid, operation,
                start_tick=20000, duration_tick=480, include_tempo=include_tempo)
            v.require(after["tracks"] == before["tracks"], "Distant timeline edit changed audio or entity metadata")
            v.require(source.read_bytes() == original and audio.read_bytes() == audio_original, "Audio guard changed source")
    await check.close(sid)

@v.feature("preservation.timeline_boundary_probe", "preservation", "score_compose", "project_edit", "project_save")
async def timeline_boundary_probe(check):
    """Observe non-bar-aligned edits and deletion collisions on an ordinary private project."""
    for include_tempo in (False, True):
        for operation, start, duration in (("time.insert", 1000, 500), ("time.delete", 1000, 500)):
            seed = await check.call("score_compose", output_name=check.output("timeline-boundary-seed"), title="Timeline boundary",
                bpm=120, notes=[{"start": 0, "duration": .5, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0}])
            sid = seed["native_session"]["session_id"]
            try:
                scope = {"track_index": 0, "part_index": 0}
                await check.edit(sid, "controller.set", **scope, type="Dynamics", replace=True,
                                 points=[{"tick": 60, "value": 30}, {"tick": 480, "value": 60}])
                await check.edit(sid, "part.move", **scope, start_tick=7680)
                for tick, bpm in ((1000, 130), (1200, 140), (1500, 150), (2000, 160)):
                    await check.edit(sid, "tempo.set", start_tick=tick, bpm=bpm)
                await check.edit(sid, "time_signature.set", bar=2, numerator=3, denominator=4)
                async def snapshot(label):
                    sequence, _ = await check.save(sid, "boundary-" + label)
                    return {"tracks": sequence["tracks"], "master": sequence["masterTrack"]}
                before = await snapshot("before")
                await check.edit(sid, operation, start_tick=start, duration_tick=duration, include_tempo=include_tempo)
                after = await snapshot("after")
                await check.edit(sid, "undo")
                v.require(await snapshot("undo") == before, "Boundary edit undo mismatch")
                await check.edit(sid, "redo")
                v.require(await snapshot("redo") == after, "Boundary edit redo mismatch")
                check.evidence("boundary_%s_%s" % (operation, include_tempo), {"before": before, "after": after})
            finally:
                await check.close(sid)

@v.feature("preservation.timeline_event_unchanged", "preservation", "score_compose", "project_open", "project_edit", "project_save")
async def timeline_event_unchanged(check):
    """Timeline edits preserve metadata on surviving tempo and meter events."""
    seed = await check.call("score_compose", output_name=check.output("event-map-seed"), title="Event map",
        bpm=120, notes=[{"start": 0, "duration": .5, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    sid = seed["native_session"]["session_id"]
    await check.edit(sid, "part.move", track_index=0, part_index=0, start_tick=7680)
    for tick, bpm in ((1000, 130), (1200, 140), (1500, 150), (2000, 160)):
        await check.edit(sid, "tempo.set", start_tick=tick, bpm=bpm)
    await check.edit(sid, "time_signature.set", bar=2, numerator=3, denominator=4)
    await check.edit(sid, "time_signature.set", bar=3, numerator=4, denominator=4)
    seq, path = await check.save(sid, "event-map-native")
    await check.close(sid)
    _, members = v.read_vpr(path)
    seq["tracks"][0][KEY] = "track"
    for index, event in enumerate(seq["masterTrack"]["tempo"]["events"]):
        event[KEY] = "tempo-" + str(index)
    for index, event in enumerate(seq["masterTrack"]["timeSig"]["events"]):
        event[KEY] = "meter-" + str(index)
    members["Project/sequence.json"] = json.dumps(seq, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("event-map-input")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    original = source.read_bytes()
    sid = (await check.call("project_open", path=str(source)))["session_id"]
    try:
        before, _ = await check.save(sid, "event-map-before")
        _, changed = await preserved_edit(check, sid, "time.delete",
            start_tick=3840, duration_tick=1700, include_tempo=True)
        v.require(changed["masterTrack"]["tempo"] == before["masterTrack"]["tempo"], "Earlier tempo metadata changed")
        meter_events = changed["masterTrack"]["timeSig"]["events"]
        v.require([(event["bar"], event["numer"], event["denom"], event.get(KEY)) for event in meter_events]
              == [(0, 4, 4, "meter-0"), (2, 4, 4, "meter-1")],
              "Boundary meter metadata changed", meter_events)
        await check.edit(sid, "time.delete", start_tick=1000, duration_tick=500, include_tempo=False)
        after, out = await check.save(sid, "event-map-after")
        v.require(after["masterTrack"] == before["masterTrack"], "Unchanged event map lost metadata")
        await check.edit(sid, "undo")
        undone, _ = await check.save(sid, "event-map-undo")
        v.require(undone == before, "Event map undo changed project")
        await check.edit(sid, "redo")
        redone, out = await check.save(sid, "event-map-redo")
        v.require(redone == after, "Event map redo changed project")
        reopened = (await check.call("project_open", path=str(out)))["session_id"]
        try:
            reopened_seq, _ = await check.save(reopened, "event-map-reopen")
            v.require(reopened_seq == after, "Event map reopen changed project")
        finally:
            await check.close(reopened)
    finally:
        await check.close(sid)
    v.require(source.read_bytes() == original, "Event map edit changed source archive")

    # The unextended meter map may change when only tempo events carry fields.
    tempo_only = json.loads(json.dumps(seq))
    for event in tempo_only["masterTrack"]["timeSig"]["events"]:
        event.pop(KEY, None)
    members["Project/sequence.json"] = json.dumps(tempo_only, ensure_ascii=False).encode("utf-8")
    tempo_source = v.ROOT / "output" / check.output("event-map-tempo-only-input")
    with zipfile.ZipFile(tempo_source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    original_tempo_source = tempo_source.read_bytes()
    sid = (await check.call("project_open", path=str(tempo_source)))["session_id"]
    try:
        before, _ = await check.save(sid, "event-map-tempo-only-before")
        await check.edit(sid, "time.insert", start_tick=1000, duration_tick=500, include_tempo=False)
        after, _ = await check.save(sid, "event-map-tempo-only-after")
        v.require(after["masterTrack"]["tempo"] == before["masterTrack"]["tempo"] and
                  after["masterTrack"]["timeSig"]["events"] != before["masterTrack"]["timeSig"]["events"],
                  "Unextended meter did not move independently of retained tempo fields")
        await check.edit(sid, "undo")
        undone, _ = await check.save(sid, "event-map-tempo-only-undo")
        v.require(undone == before, "Tempo-only extension timeline undo differs")
        await check.edit(sid, "redo")
        redone, _ = await check.save(sid, "event-map-tempo-only-redo")
        v.require(redone == after, "Tempo-only extension timeline redo differs")
    finally:
        await check.close(sid)
    v.require(tempo_source.read_bytes() == original_tempo_source, "Tempo-only timeline edit changed source archive")

# timeline move probe
@v.feature("preservation.timeline_event_move_20", "preservation", "score_compose", "project_open", "project_edit", "project_save")
async def timeline_event_move_20(check):
    seed = await check.call("score_compose", output_name=check.output("move-seed"), title="Move", bpm=120, notes=[{"start": 0, "duration": .5, "pitch": 60, "lyric": "あ", "phoneme": "a", "lang_id": 0}])
    sid = seed["native_session"]["session_id"]
    await check.edit(sid, "part.move", track_index=0, part_index=0, start_tick=7680)
    for tick, bpm in ((1000, 130), (1200, 140), (1500, 150), (2000, 160)):
        await check.edit(sid, "tempo.set", start_tick=tick, bpm=bpm)
    await check.edit(sid, "time_signature.set", bar=2, numerator=3, denominator=4)
    await check.edit(sid, "time_signature.set", bar=4, numerator=5, denominator=8)
    seq, path = await check.save(sid, "move-native")
    await check.close(sid)
    _, members = v.read_vpr(path)
    for kind in ("tempo", "timeSig"):
        for i, event in enumerate(seq["masterTrack"][kind]["events"]): event[KEY] = kind + str(i)
    members["Project/sequence.json"] = json.dumps(seq, ensure_ascii=False).encode("utf-8")
    source = v.ROOT / "output" / check.output("move-input")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    original = source.read_bytes()
    for include_tempo in (False, True):
        sid = (await check.call("project_open", path=str(source)))["session_id"]
        try:
            before, _ = await check.save(sid, "move-before")
            await check.edit(sid, "time.insert", start_tick=1000, duration_tick=500, include_tempo=include_tempo)
            after, out = await check.save(sid, "move-after")
            old = before["masterTrack"]["tempo"]["events"]
            new = after["masterTrack"]["tempo"]["events"]
            v.require([(e["pos"], e[KEY]) for e in new] ==
                      [(e["pos"] + (500 if include_tempo and e["pos"] > 1000 else 0), e[KEY]) for e in old],
                      "Tempo metadata move differs")
            old = before["masterTrack"]["timeSig"]["events"]
            new = after["masterTrack"]["timeSig"]["events"]
            v.require([(e["bar"], e[KEY]) for e in new] ==
                      [(e["bar"] + (1 if e["bar"] > 0 else 0), e[KEY]) for e in old],
                      "Meter metadata move differs")
            await check.edit(sid, "undo")
            undone, _ = await check.save(sid, "move-undo")
            v.require(undone == before, "Move undo differs")
            await check.edit(sid, "redo")
            redone, out = await check.save(sid, "move-redo")
            v.require(redone == after, "Move redo differs")
            clone = (await check.call("project_clone", session_id=sid))["session_id"]
            try:
                copied, _ = await check.save(clone, "move-clone")
                v.require(copied == after, "Move clone differs")
            finally: await check.close(clone)
            reopened = (await check.call("project_open", path=str(out)))["session_id"]
            try:
                restored, _ = await check.save(reopened, "move-reopen")
                v.require(restored == after, "Move reopen differs")
            finally: await check.close(reopened)
        finally: await check.close(sid)
    v.require(source.read_bytes() == original, "Move changed source")


if __name__ == "__main__":
    raise SystemExit(v.main())
