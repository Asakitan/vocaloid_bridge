"""MCP tools for isolated native VOCALOID sessions and music interchange."""

from __future__ import annotations

import asyncio
import atexit
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Literal

WORKSPACE = Path(os.environ.get("VOCALOID_WORKSPACE", Path(__file__).resolve().parents[1])).resolve()
MCP_TEMP = WORKSPACE / ".runtime" / "mcp-temp"
MCP_TEMP.mkdir(parents=True, exist_ok=True)
os.environ["TEMP"] = os.environ["TMP"] = str(MCP_TEMP)
tempfile.tempdir = str(MCP_TEMP)

from mcp.server.fastmcp import FastMCP
import numpy as np
import soundfile as sf

from . import __version__, cleanup as temp_cleanup
from .compose import compose as compose_native, replace_notes as replace_notes_native
from .music import _source, export_midi, import_midi
from .native_client import NativeClient
from .projects import ProjectStore


TEMPLATE = Path(__file__).parent / "templates" / "ai-starter.vpr"
WORKFLOW = WORKSPACE / "docs" / "song-workflow.md"
STORE = ProjectStore(WORKSPACE)
NATIVE = NativeClient(WORKSPACE)
atexit.register(NATIVE.close)
temp_cleanup.start_background_sweep(WORKSPACE)
mcp = FastMCP(
    "VOCALOID Native",
    instructions=(
        "Control the latest installed supported VOCALOID6/7 native engine on a private Windows desktop. "
        "Check vocaloid_status for the selected product. On VOCALOID7, voice/style/performance "
        "settings require explicit scope='track' and affect all parts on that track; "
        "media library operations and part-level audio effects are unavailable. "
        "Use vocaloid_features for executable feature contracts and project_inspect for real "
        "current enums/bounds before edits. project_ai_adjust runs VOCALOID7 native AI generation "
        "from existing notes and lyrics; it is not aesthetic optimization or an exported WAV. "
        "Never automate, activate, minimize, close or send input to the user's interactive editor. "
        "There is no UI or alternate-backend fallback. When making a song, call vocaloid_workflow first: "
        "it gives the tested steps, the lyric form each language accepts and the controls VOCALOID:AI "
        "actually sings. Start with project_create or project_open; "
        "save through project_save and close through project_close. Lyrics are one syllable per note, "
        "and Chinese lyrics are unmarked pinyin. Discover exact native object "
        "signatures with project_members before project_call. A saved VPR is not rendered audio."
    ),
)


async def _rpc(method: str, **parameters: Any) -> dict[str, Any]:
    return await asyncio.to_thread(NATIVE.request, method, parameters)


@mcp.tool()
async def vocaloid_status() -> dict[str, Any]:
    """Initialize the isolated native engine and return its real version and session count."""
    result = await _rpc("ping")
    version7 = result.get("product") == "VOCALOID7"
    limitations = ["Complete editor-feature coverage has not been validated."]
    if version7:
        limitations.extend([
            "Voice, style and performance settings require scope='track' and affect all parts on the track.",
            "Media library operations, native WOR reverse and VOCALO CHANGER are unavailable in VOCALOID7; PCM/float WAV reverse uses bridge processing.",
            "Part-level audio effects are unavailable; select track or master scope.",
            "Use take_number and vibrato curve_model, not legacy take_lane or AI vibrato booleans.",
        ])
    return {**result, "mcp_version": __version__, "workspace": str(WORKSPACE), "server_pid": os.getpid(),
            "installation": NATIVE.installation.to_dict(),
            "generation": NATIVE.generation, "managed_by_mcp": True,
            "isolation_desktop_expected": NATIVE.child.desktop_name, "fallbacks": False,
            "temp_cleanup": temp_cleanup.summary(WORKSPACE),
            "settings_scope": "track" if version7 else "part", "known_limitations": limitations}


@mcp.tool()
async def vocaloid_runtime(operation: Literal["status", "start", "stop", "restart"] = "status",
                           discard_sessions: bool = False) -> dict[str, Any]:
    """Start, inspect, stop or restart this MCP's private VOCALOID background process.
    Projects auto-start it. Stop/restart protect open projects unless discard_sessions=true.
    A lost in-flight request is never automatically replayed; reopen the last saved project.
    This controls VOCALOID, not Codex or the user's interactive editor.
    """
    result = await asyncio.to_thread(NATIVE.runtime, operation, discard_sessions)
    return {**result, "mcp_version": __version__, "workspace": str(WORKSPACE)}


@mcp.tool()
async def project_create(title: str = "Untitled", bpm: float = 120, sample_rate: int = 44100) -> dict[str, Any]:
    """Create a real native engine project without opening or changing the interactive editor.
    Keep sample_rate at 44100: vocal synthesis runs only at that rate, and the delivery rate
    is chosen later in project_audio mixdown.
    """
    return await _rpc("create", title=title, bpm=bpm, sample_rate=sample_rate)


@mcp.tool()
async def project_open(path: str) -> dict[str, Any]:
    """Open a VPR (or VPRX with VOCALOID7) as an independent native session. The source remains unchanged.
    Reject AI notes combining a nonempty Attack/Release object with Singing Skill before native loading.
    Use score_inspect and an explicit score_patch copy to resolve all such conflicts first.
    """
    return await _rpc("open", path=str(_source(WORKSPACE, path)))


@mcp.tool()
async def project_import(path: str, code_page: int = 65001, prefer_ai: bool = True) -> dict[str, Any]:
    """Import MIDI, VSQX, PPSF, VPR or VPRX (VOCALOID7) through the native loader as an owned session.
    Legacy input is staged privately. Save the imported session as a new VPR before closing.
    prefer_ai is passed to the native MIDI/SMF/VSQ loader only; it does not convert
    VPR, VSQX or PPSF tracks or assign a voicebank.
    """
    return await _rpc("import_project", path=str(_source(WORKSPACE, path)), code_page=code_page, prefer_ai=prefer_ai)


@mcp.tool()
async def project_export_midi(session_id: str, output_name: str, encoding: str = "Utf8",
                              overwrite: bool = False) -> dict[str, Any]:
    """Export the actual native session to Standard MIDI, including its tempo, meter and lyrics."""
    return await _rpc("export_midi", session_id=session_id, output_name=output_name,
                      encoding=encoding, overwrite=overwrite)


@mcp.tool()
async def project_save(session_id: str, output_name: str, overwrite: bool = False) -> dict[str, Any]:
    """Save to workspace/output as .vpr, or .vprx with VOCALOID7. Overwriting requires explicit permission."""
    return await _rpc("save", session_id=session_id, output_name=output_name, overwrite=overwrite)


@mcp.tool()
async def project_clone(session_id: str, title: str | None = None) -> dict[str, Any]:
    """Create an independent native project copy with its own staged audio resources."""
    return await _rpc("clone_project", session_id=session_id, title=title)


@mcp.tool()
async def project_revert(session_id: str, discard_changes: bool = False) -> dict[str, Any]:
    """Reopen the last saved VPR/VPRX and close the old session, returning a new session_id."""
    return await _rpc("revert_project", session_id=session_id, discard=discard_changes)


@mcp.tool()
async def project_merge(session_id: str, path: str, offset_tick: int = 0,
                        include_tracks: bool = True, include_tempo: bool = False,
                        replace_tempo: bool = False, code_page: int = 65001) -> dict[str, Any]:
    """Import another project's tracks or tempo/meter into the native session.
    offsets use native ticks (480 per quarter note); originals stay unchanged.
    """
    return await _rpc("merge_project", session_id=session_id, path=str(_source(WORKSPACE, path)),
                      offset_tick=offset_tick, include_tracks=include_tracks,
                      include_tempo=include_tempo, replace_tempo=replace_tempo, code_page=code_page)


@mcp.tool()
async def project_close(session_id: str, discard_changes: bool = False) -> dict[str, Any]:
    """Close an owned native project. Unsaved changes require discard_changes=true."""
    return await _rpc("close", session_id=session_id, discard=discard_changes)


@mcp.tool()
async def project_status(session_id: str) -> dict[str, Any]:
    """Read the real native session title, track count, dirty flag and saved path."""
    return await _rpc("session", session_id=session_id)


@mcp.tool()
async def project_members(session_id: str, ref: str | None = None) -> dict[str, Any]:
    """List actual native properties and exact method signatures for a session-owned object."""
    return await _rpc("members", session_id=session_id, ref=ref)


@mcp.tool()
async def native_api_catalog(type: str | None = None, namespace: str | None = None,
                             include_excluded: bool = True, offset: int = 0,
                             limit: int = 25, include_members: bool = True) -> dict[str, Any]:
    """Inspect installed native types and exact signatures, including exclusion reasons.
    This is metadata discovery, not a claim that every member has passed functional tests.
    """
    return await _rpc("api_catalog", type=type, namespace=namespace, include_excluded=include_excluded,
                      offset=offset, limit=limit, include_members=include_members)


def _feature_catalog(product: str) -> dict[str, dict[str, Any]]:
    version7 = product == "VOCALOID7"
    track = {"track_index": "TRACK_INDEX"}
    part = {**track, "part_index": "PART_INDEX"}
    note = {**part, "note_index": "NOTE_INDEX"}
    settings = {**track, "scope": "track"} if version7 else part
    catalog: dict[str, dict[str, Any]] = {}

    def call(operation: str, options: dict[str, Any], tool: str = "project_edit") -> dict[str, Any]:
        return {"tool": tool, "arguments": {"session_id": "SESSION_ID", "operation": operation, "options": options}}

    def add(name: str, label: str, scope: str, reads: list[dict[str, Any]],
            writes: list[dict[str, Any]], parameters: dict[str, Any]) -> None:
        catalog[name] = {"label": label, "product": product, "support": "native_contract",
                         "scope": scope, "read_calls": reads, "write_calls": writes,
                         "parameters": parameters, "verification": "Contract discovery, not audio or roundtrip acceptance."}

    scope = "track" if version7 else "part"
    performance = call("performance.get", settings)
    voice = call("voice.get", settings)
    add("voice", "Voice", scope, [{"tool": "voicebanks", "arguments": {}}, voice],
        [call("voice.set", {**settings, "ai_voice_bank_id": "VOICE_BANK_ID"})],
        {"ai_voice_bank_id": {"type": "string", "source": "voicebanks; select an installed AI bank compatible with the target"},
         "classic_alternative": "voice_bank_id; never pass both AI and classic ID keys"})
    if version7:
        add("voice_type", "Voice Type", "track", [voice],
            [call("voice.set", {**settings, "voice_type_id": "VOICE_TYPE_ID"})],
            {"voice_type_id": {"type": "string", "source": "voice.get.voice_types[].voice_type_id",
                               "requires": "voice.get.voice_type_supported=true; VOCALOID7 AI bank only"}})
    else:
        catalog["voice_type"] = {"label": "Voice Type", "product": product, "support": "unsupported",
                                 "reason": "Voice Type requires VOCALOID7 and a VOCALOID7 AI voice bank.",
                                 "read_calls": [], "write_calls": []}
    add("style", "Style", scope,
        [call("style_list", {}, "project_library"), performance],
        [call("style_apply", {**settings, "style_id": "STYLE_ID", "include_audio": True}, "project_library")],
        {"style_id": {"type": "string", "source": "style_list.styles[].style_id"},
         "include_audio": {"type": "boolean", "default": True},
         "readback": "style_apply receipt and performance.get; inspect track/master audio effects separately"})
    for name, label, field, source in (
        ("robot", "Robot", "robot_mode", "performance.get.robot.modes"),
        ("breath", "Breath", "breath_mode", "performance.get.breath.modes"),
        ("breath_type", "Breath Type", "breath_type", "performance.get.breath.types"),
        ("exhalation", "Exhalation", "breath_exhalation", "performance.get.breath.setting"),
        ("take", "Take", "take_number" if version7 else "take_lane",
         "performance.get.take.max_take_number (minimum 0)" if version7 else "performance.get.take.setting"),
    ):
        add(name, label, scope, [performance], [call("performance.set", {**settings, field: "VALUE"})],
            {field: {"type": "integer" if name in {"exhalation", "take"} else "string", "source": source},
             "availability": "Null effect means unavailable; do not invent an enum or range."})
    for name, label, color, controller in (
        ("expression", "Expression", "S5Expression", "Expression"),
        ("air", "Air", "S5Air", "S5Air"),
        ("character", "Character", "S5Character", "S5Character"),
        ("attack", "Attack", "S5Attack", None),
    ):
        if name == "attack" and not version7:
            catalog[name] = {"label": label, "product": product, "support": "unsupported",
                             "reason": "VOCALOID7 AI Attack macro is not a VOCALOID6 control; classic dvqm Attack is different.",
                             "read_calls": [], "write_calls": []}
            continue
        add(name, label + " Macro", scope, [performance],
            [call("performance.set", {**settings, "voice_colors": {color: "VALUE"}})],
            {"voice_colors." + color: {"type": "integer", "source": "performance.get.voice_colors[] where name=" + color,
                                       "bounds": "setting.LowerBoundValue/UpperBoundValue", "require_applicable": True}})
        if controller is not None:
            add(name + "_curve", label + " Curve", "part",
                [call("controller.types", part), call("controller.list", {**part, "type": controller})],
                [call("controller.set", {**part, "type": controller, "points": [{"tick": "TICK", "value": "VALUE"}], "replace": False})],
                {"value": {"type": "integer", "source": "controller.types.types[] where type=" + controller,
                           "bounds": "minimum/maximum/default_value", "require_applicable": True},
                 "tick": {"type": "integer", "unit": "part-relative ticks; 480 per quarter note"}})
    for name, label, lane in (("volume", "Track Volume", "track_volume"), ("pan", "Track Pan", "track_pan")):
        add(name, label, "track", [call("automation.list", {**track, "scope": lane})],
            [call("automation.set", {**track, "scope": lane, "points": [{"tick": 0, "value": "VALUE"}], "replace": False})],
            {"value": {"type": "integer", "source": "automation.list.minimum/maximum/default_value", "unit": "native raw value, not normalized"},
             "tick": {"type": "integer", "unit": "sequence ticks; zero sets the baseline without deleting later automation"}})
    for name in ("mute", "solo"):
        parameter = {"type": "boolean", "enum": [False, True]}
        if version7:
            parameter["semantics"] = ("mute is the stored mute flag; channel_mute is the effective "
                                      "channel state and may differ when tracks are soloed.")
        parameters = {name: parameter}
        writes = [call("track.update", {**track, name: True})]
        if version7 and name == "solo":
            parameters["solo_state"] = {"type": "string", "enum": ["Off", "On", "Defeat"],
                                        "semantics": "Specify solo or solo_state, not both."}
            writes.append(call("track.update", {**track, "solo_state": "VALUE"}))
        add(name, name.title(), "track", [call("track.list", {})],
            writes, parameters)
    add("freeze", "Track Freeze", "track", [call("track.freeze_state", track)],
        [call("track.freeze", track), call("track.unfreeze", track)],
        {"frozen": {"type": "boolean", "source": "track.freeze_state.frozen"},
         "owned": {"type": "boolean", "source": "track.freeze_state.owned",
                   "semantics": "Only session-owned frozen audio can be released."},
         "scope": "Runtime cache only; saving and cloning preserve the authoring state."})
    for name, effect in (("robot_bypass", "RobotVoice"), ("breath_bypass", "Breath"),
                         ("voice_color_bypass", "VoiceColor")):
        add(name, effect + " Switch", scope, [performance],
            [call("performance.set", {**settings, "bypass": {effect: False}})],
            {"bypass." + effect: {"type": "boolean", "false": "enabled", "true": "bypassed",
                                  "source": "performance.get.bypass[]; require available=true"}})
    add("record_arm", "MIDI Recording Arm", "track", [call("track.list", {})],
        [call("track.update", {**track, "midi_recording": True})],
        {"midi_recording": {"type": "boolean", "semantics": "Arm only; use project_midi for actual recording."}})
    add("tempo", "Tempo", "sequence", [call("tempo.list", {})],
        [call("tempo.set", {"start_tick": "TICK", "bpm": "VALUE"})],
        {"bpm": {"type": "number", "source": "tempo.list.min_bpm/max_bpm"}, "start_tick": {"type": "integer", "minimum": 0}})
    add("time_signature", "Time Signature", "sequence", [call("time_signature.list", {}),
        {"tool": "project_get", "arguments": {"session_id": "SESSION_ID", "member": "MinTimeSigValue"}},
        {"tool": "project_get", "arguments": {"session_id": "SESSION_ID", "member": "MaxTimeSigValue"}}],
        [call("time_signature.set", {"bar": "BAR", "numerator": "NUMERATOR", "denominator": "DENOMINATOR"})],
        {"bar": {"type": "integer", "minimum": 0}, "numerator": {"type": "integer", "source": "project_get MinTimeSigValue/MaxTimeSigValue"},
         "denominator": {"type": "integer", "constraint": "positive power of two within native MinTimeSigValue/MaxTimeSigValue"}})
    add("notes", "Notes", "part", [call("note.list", part), call("note.expression_bounds", part)],
        [call("note.add", {**part, "start_tick": "TICK", "duration_tick": "DURATION", "number": "PITCH", "lyric": "LYRIC"}),
         call("note.update", {**note, "number": "PITCH"}),
         call("note.remove", note), call("note.clear", part),
         call("note.duplicate", {**note, "start_tick": "TICK"}),
         call("note.split", {**note, "split_tick": "TICK"}),
         call("note.join", {**part, "note_indices": ["NOTE_INDEX_1", "NOTE_INDEX_2"]}),
         call("note.batch_update", {**part, "updates": [{"note_index": "NOTE_INDEX", "number": "PITCH"}]})],
        {"number": {"type": "integer", "unit": "MIDI note number"}, "start_tick": {"type": "integer", "unit": "part-relative ticks"},
         "expression": {"type": "object", "source": "note.expression_bounds"},
         "note_index": {"type": "integer", "source": "note.list.notes[].note_index", "rule": "Refresh note indices after structural edits."},
         "note.clear": "Removes every note in the selected part."})
    add("lyrics", "Lyrics", "note", [call("note.list", part)],
        [call("note.update", {**note, "lyric": "LYRIC"})],
        {"lyric": {"type": "string", "rule": "one syllable per note; AI changes without explicit phonemes run native G2PA unless protected"},
         "phrase_tool": "project_library lyrics_apply; discover options with vocaloid_operations"})
    metadata_note = {**note, "is_attack": True, "storage": "bridge_metadata"}
    add("ai_dvqm_metadata", "AI Attack/Release Metadata", "note",
        [call("dvqm_get", metadata_note, "project_library"),
         call("dvqm_catalog", {"is_attack": True}, "project_library")],
        [call("dvqm_set", {**metadata_note, "db_id": "DB_ID", "name_id": "NAME_ID"}, "project_library"),
         call("dvqm_clear", metadata_note, "project_library")],
        {"storage": "bridge_metadata", "ids": "Use dvqm_catalog db_id and name_id.",
         "semantics": "Bridge-owned note metadata only; native=false and it does not affect AI synthesis."})
    catalog["ai_dvqm_metadata"]["support"] = "bridge_contract"
    add("pitch", "Direct Pitch", "note", [call("pitch.list", note)],
        [call("pitch.set", {**note, "points": [{"tick": "TICK", "value": "VALUE"}], "replace": False})],
        {"points": {"type": "array", "source": "pitch.list", "rule": "value is an absolute fractional MIDI note number; tick is note-relative, not sequence-relative"}})
    add("vibrato", "Vibrato", "note", [call("vibrato.get", note)],
        [call("vibrato.set", {**note, "curve_model" if version7 else "ai_enabled": "VALUE"})],
        {"curve_model" if version7 else "ai_enabled": {"type": "string" if version7 else "boolean", "source": "vibrato.get"}})
    add("note_expression", "Note Expression Actions", "note",
        [call("note.expression_bounds", part), call("note.list", part)],
        [call("note.update", {**note, "ai_expression": {"PitchTransitionStart": "VALUE"}})],
        {"ai_expression": {"type": "object", "source": "note.expression_bounds.ai_expression",
                           "semantics": "Native pitch transitions, drift and amplitude; not GUI tool selection."}})
    add("phoneme_timing", "Phoneme Timing", "note", [call("phoneme_timing.get", note)],
        [call("phoneme_timing.reset", note)],
        {"timing": {"source": "phoneme_timing.get; discover phoneme_timing.set options through vocaloid_operations",
                    "requires": "A generated native score; call project_ai_adjust on V7 first."}})
    if version7:
        add("pitch_preserve", "Preserve Generated Pitch", "note", [call("ai.status", part), call("pitch.list", note)],
            [call("pitch.set", {**note, "from_rendered": True, "overwrite_existing": False})],
            {"overwrite_existing": {"type": "boolean", "default": False},
             "prerequisite": "ai.generate on this session, not an archive export snapshot",
             "multiple_notes": "Use project_ai_adjust preserve_pitch=true for one atomic native transaction."})
        add("ai_vibrato_defaults", "AI Vibrato Defaults", "note", [call("vibrato.get", note)],
            [call("vibrato.set", {**note, "reset_ai_defaults": True})],
            {"reset_ai_defaults": {"type": "boolean", "requires": "vibrato.get.reset_ai_defaults_available",
                                    "semantics": "Reset native AI vibrato defaults and select AiEstimatedBase."}})
        add("ai_adjust", "Native AI Generation", "part", [call("ai.status", part), performance],
            [{"tool": "project_ai_adjust", "arguments": {"session_id": "SESSION_ID", **part}}, call("ai.generate", part)],
            {"take_number": {"type": "integer", "optional": True, "source": "performance.get.take.max_take_number (minimum 0)",
                             "scope": "track; affects every part on the track"},
             "preserve_pitch": {"type": "boolean", "default": False, "effect": "copy real generated pitch into editable direct-pitch curves in one native transaction"},
             "note_indices": {"type": "array", "items": "distinct nonnegative integers", "optional": True,
                              "requires": "preserve_pitch=true; omit to preserve all renderable notes"},
             "overwrite_existing": {"type": "boolean", "default": False, "requires": "preserve_pitch=true; explicit permission to replace existing direct pitches"},
             "semantics": "Native AI synthesis from existing notes and lyrics, not aesthetic optimization or an independent AutoTune API.",
             "output": "Native rendering cache and status; use project_render_part for a verified deliverable WAV."})
    else:
        catalog["ai_adjust"] = {"label": "Native AI Generation", "product": product, "support": "unsupported",
                                "reason": "ai.status/ai.generate require VOCALOID7 AI; V6 rendering remains project_render_part.",
                                "read_calls": [], "write_calls": []}
    for name, label, reason in (
        ("media", "VMM Media Library", "VOCALOID7 native VMM interface is unavailable."),
        ("part_effects", "Part Audio Effects", "VOCALOID7 supports track/master audio effects, not part scope."),
        ("reverse", "Reverse", "VOCALOID7 native reverse is unavailable."),
        ("voice_change", "VOCALO CHANGER", "VOCALOID7 native voice change is unavailable."),
    ):
        catalog[name] = {"label": label, "product": product,
                         "support": "unsupported" if version7 else "operation_catalog",
                         "reason": reason if version7 else "Discover the existing library/audio operation with vocaloid_operations.",
                         "read_calls": [], "write_calls": []}
    if version7:
        catalog["reverse"].update({"support": "operation_catalog",
            "reason": "PCM/IEEE-float WAV frame reversal is bridge processing, not native WOR rendering."})
    catalog["reverse"]["write_calls"] = [{"tool": "project_audio", "arguments": {"session_id": "SESSION_ID",
        "operation": "process_audio", "options": {"action": "reverse", "path": "SOURCE_WAV", "output_name": "OUTPUT_NAME"}}}]
    catalog["editor_view"] = {"label": "Grid, Zoom, Panels and Character Image", "product": product,
                              "support": "unsupported", "reason": "Interactive editor layout is not operated by the private native host.",
                              "read_calls": [], "write_calls": []}
    return catalog


@mcp.tool()
def vocaloid_features(feature: str | None = None, include_matrix: bool = False) -> dict[str, Any]:
    """Read feature evidence with explicit product attribution, without starting the engine.
    Lists UI feature IDs with executable write templates, scope, parameter types and live
    enum/bounds sources. Use project_inspect(session_id, feature, indices) before editing.
    The optional historical matrix covers VOCALOID6 only, never VOCALOID7 acceptance.
    """
    path = WORKSPACE / "docs" / "feature-matrix.md"
    catalog = _feature_catalog(NATIVE.installation.product)
    if feature is not None:
        if feature not in catalog:
            raise ValueError("Unknown feature; call vocaloid_features for available feature IDs.")
        catalog = {feature: catalog[feature]}
    result = {"product": NATIVE.installation.product, "engine_version": NATIVE.installation.version,
            "matrix_product": "VOCALOID6", "matrix_engine_version": "6.13.3.1",
            "matrix_applies_to_selected_product": NATIVE.installation.product == "VOCALOID6",
            "verification": "Historical VOCALOID6 evidence only; VOCALOID7 requires separate native acceptance.",
            "path": str(path), "features": catalog,
            "template_rule": "Replace uppercase value placeholders using native discovery; templates are not submitted automatically."}
    if include_matrix:
        result["matrix"] = path.read_text(encoding="utf-8")
    return result


@mcp.tool()
async def project_inspect(session_id: str, feature: str, track_index: int | None = None,
                          part_index: int | None = None, note_index: int | None = None) -> dict[str, Any]:
    """Read a UI feature's actual native state and enum/bounds sources, without changing the project.
    Get feature IDs from vocaloid_features. Supply explicit indices for the feature's scope;
    VOCALOID7 voice/style/performance automatically read scope=track, never a guessed part.
    Returns readback receipts and bound write-call templates; no write, synthesis or retry occurs.
    """
    catalog = _feature_catalog(NATIVE.installation.product)
    if feature not in catalog:
        raise ValueError("Unknown feature; call vocaloid_features for available feature IDs.")
    for name, value in (("track_index", track_index), ("part_index", part_index), ("note_index", note_index)):
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            raise ValueError(name + " must be a nonnegative integer.")
    replacements = {"SESSION_ID": session_id, "TRACK_INDEX": track_index,
                    "PART_INDEX": part_index, "NOTE_INDEX": note_index}

    def bind(value: Any, required: bool) -> Any:
        if isinstance(value, dict):
            return {key: bind(item, required) for key, item in value.items()}
        if isinstance(value, list):
            return [bind(item, required) for item in value]
        if isinstance(value, str) and value in replacements:
            replacement = replacements[value]
            if replacement is None and required:
                raise ValueError(value.lower() + " is required for " + feature + ".")
            return value if replacement is None else replacement
        return value

    contract = catalog[feature]
    if contract["support"] == "native_contract":
        required = {"track": ("TRACK_INDEX",), "part": ("TRACK_INDEX", "PART_INDEX"),
                    "note": ("TRACK_INDEX", "PART_INDEX", "NOTE_INDEX"), "sequence": ()}[contract["scope"]]
        for placeholder in required:
            bind(placeholder, True)
    calls = [bind(item, True) for item in contract["read_calls"]]
    readbacks = []
    for invocation in calls:
        tool = invocation["tool"]
        method = {"project_edit": "score_edit", "project_library": "library_op", "voicebanks": "voices", "project_get": "get"}[tool]
        value = await _rpc(method, **invocation["arguments"])
        if feature == "time_signature" and tool == "project_get":
            reference = value["value"]["$ref"]
            fields = {}
            for member in ("Numer", "Denom"):
                field = await _rpc("get", session_id=session_id, ref=reference, member=member)
                fields[member] = field["value"]
            value = {**value, "fields": fields}
        readbacks.append({**invocation, "result": value})
    return {"session_id": session_id, "feature": feature, "product": NATIVE.installation.product,
            "read_only": True, "contract": bind(contract, False), "readbacks": readbacks,
            "verification": "Readback only; no save/reopen or synthesized-audio acceptance is implied."}


@mcp.tool()
def vocaloid_workflow() -> dict[str, Any]:
    """Read this first when making a song: the tested steps from an empty session to a mixed WAV,
    the lyric form each language accepts, the controls VOCALOID:AI actually sings and the ones
    it only stores. Times are ticks, 480 per quarter note.
    """
    version7 = NATIVE.installation.product == "VOCALOID7"
    return {"mcp_version": __version__, "product": NATIVE.installation.product,
            "settings_scope": "track" if version7 else "part",
            "feature_discovery": {"tool": "vocaloid_features", "arguments": {}},
            "before_edit": {"tool": "project_inspect", "arguments": {"session_id": "SESSION_ID", "feature": "FEATURE_ID",
                                     "track_index": "TRACK_INDEX"}},
            "verification": "The guide's V6 historical audio evidence does not establish V7 behavior; inspect current native values and verify saved files/audio separately.",
            "ticks_per_quarter": 480, "path": str(WORKFLOW),
            "guide": WORKFLOW.read_text(encoding="utf-8")}


@mcp.tool()
def vocaloid_operations(domain: str | None = None, operation: str | None = None,
                        include_documentation: bool = False) -> dict[str, Any]:
    """Discover structured score/audio/library/clipboard/MIDI operations and their documented options.
    Use the returned tool with operation and options. This index is not functional-test evidence;
    vocaloid_features reports verification. Select a domain or an operation with
    include_documentation for full rules; vocaloid_workflow gives the order to use them in.
    """
    index = json.loads((Path(__file__).with_name("operations.json")).read_text(encoding="utf-8"))
    domains = index["domains"]
    if domain is not None and domain not in domains:
        raise ValueError("domain must be score, audio, library, clipboard, or midi.")
    if include_documentation and domain is None and operation is None:
        raise ValueError("include_documentation needs a domain (score, audio, library, clipboard or midi) "
                         "or an operation; the combined documents are too large for one result.")
    selected = {key: value for key, value in domains.items() if domain is None or key == domain}
    if operation is not None:
        selected = {key: {**value, "operations": [entry for entry in value["operations"] if entry["operation"] == operation]}
                    for key, value in selected.items()}
        selected = {key: value for key, value in selected.items() if value["operations"]}
        if not selected:
            raise ValueError("operation is not present in the selected domain.")
    product = NATIVE.installation.product
    catalog = _feature_catalog(product)
    for value in selected.values():
        value["documentation_path"] = str(WORKSPACE / value["documentation"])
        if include_documentation:
            value["documentation_text"] = (WORKSPACE / value["documentation"]).read_text(encoding="utf-8")
        for entry in value["operations"]:
            entry["features"] = [name for name, feature in catalog.items() if any(
                invocation["tool"] == value["tool"] and invocation["arguments"].get("operation") == entry["operation"]
                for invocation in feature["read_calls"] + feature["write_calls"])]
            unsupported = ((product == "VOCALOID6" and entry["operation"] in {"ai.status", "ai.generate"}) or
                (product == "VOCALOID7" and value["tool"] == "project_library" and entry["operation"].startswith("media_")))
            entry["product_support"] = "unsupported" if unsupported else "see_contract_and_live_inspect"
            if product == "VOCALOID7" and value["tool"] == "project_edit" and entry["operation"] == "track.update":
                entry["mute_semantics"] = ("mute is the stored mute flag; channel_mute is the effective "
                                           "channel state and may differ when tracks are soloed.")
            if value["tool"] == "project_audio" and entry["operation"] == "process_audio":
                entry["action_support"] = {
                    action: "unsupported" if product == "VOCALOID7" and action == "voice_change"
                    else "see_contract_and_live_inspect"
                    for action in ("reverse", "normalize", "time_stretch", "pitch_shift", "voice_change")
                }
                if product == "VOCALOID7":
                    entry["action_limitations"] = {"reverse": "PCM/IEEE-float RIFF WAV with complete frame-aligned data chunks; bridge processing (native=false). Valid standard integer smpl loops and unambiguous cue points, including labl/note labels and ltxt regions, are remapped; playlist-linked or ambiguous cue points, fractional loops, sampler-specific chunks and other time references remain unchanged."}
            if value["tool"] == "project_audio" and entry["operation"] in {"effects", "set_effect"}:
                entry["scope_support"] = {
                    scope: "unsupported" if product == "VOCALOID7" and scope == "part"
                    else "see_contract_and_live_inspect"
                    for scope in ("master", "track", "part")
                }
            if value["tool"] == "project_library":
                if entry["operation"] in {"dvqm_get", "dvqm_set", "dvqm_clear"}:
                    entry["storage_support"] = {
                        "native": "Native DVQM; AI writes remain restricted.",
                        "bridge_metadata": "Explicit AI note metadata only; native=false and no AI synthesis effect."}
                if entry["operation"] in {"dvqm_set", "dvqm_clear"}:
                    entry["track_support"] = {"Midi": "see_contract_and_live_inspect",
                        "MidiAi": "unsupported" if entry["operation"] == "dvqm_set" else "empty_noop_only"}
                    entry["limitation"] = ("AI DVQM writes cannot preserve Singing Skill and native undo; "
                        "empty clear is a read-only no-op, including on frozen tracks.")
                elif entry["operation"] in {"note_skill_set", "note_skill_reset"}:
                    entry["limitation"] = ("AI notes with existing Attack or Release cannot persist Singing Skill; "
                        "unknown fields in the target subtree are protected.")
    return {**index, "product": product, "settings_scope": "track" if product == "VOCALOID7" else "part",
            "verification": "Discovery only. Historical VOCALOID6 evidence is not VOCALOID7 acceptance.",
            "feature_discovery_tool": "vocaloid_features", "live_inspection_tool": "project_inspect",
            "domains": selected, "total": sum(len(value["operations"]) for value in selected.values())}


@mcp.resource("vocaloid://features")
def feature_matrix() -> str:
    return ("Historical VOCALOID6 6.13.3.1 evidence only; this is not VOCALOID7 acceptance.\n\n"
            + (WORKSPACE / "docs" / "feature-matrix.md").read_text(encoding="utf-8"))


@mcp.tool()
async def project_edit(session_id: str, operation: str,
                       options: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a typed native score operation with its documented options.
    Operations cover tracks, parts, notes, voices, tempo, meter, curves, automation and history.
    Discover editable UI controls through vocaloid_features and their actual state/bounds through
    project_inspect. VOCALOID7 voice/performance need scope='track'; AI generation uses ai.generate.
    On V7, track mute is the stored flag; channel_mute is the effective state during solo.
    track.update accepts solo_state='Off'/'On'/'Defeat' as an alternative to solo.
    Ticks are 480 per quarter note. Lyrics are one syllable per note: Japanese kana, a
    one-syllable English word, or unmarked pinyin for Chinese; other text needs explicit phonemes.
    controller.types and performance.get mark which lanes the current part actually sings.
    """
    return await _rpc("score_edit", session_id=session_id, operation=operation, options=options or {})


@mcp.tool()
async def project_midi(operation: str, options: dict[str, Any] | None = None,
                       session_id: str | None = None) -> dict[str, Any]:
    """Enumerate MIDI inputs or record note events into an armed native AI part.
    A device is opened only with an explicit device ID and matching name. Synthetic
    events are an explicit event stream, not evidence of hardware input.
    """
    return await _rpc("midi_recording", session_id=session_id, operation=operation, options=options or {})


@mcp.tool()
async def project_audio(session_id: str, operation: str,
                        options: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a documented audio operation without activating the editor.
    mixdown is the deliverable render, with effects, at sample_rate 44100, 48000, 96000 or 192000;
    it stops at the end of the last part. Unsupported operations return explicit errors; no
    alternate audio backend is used.
    VOCALOID7 effects use track/master scope; part scope and voice_change are unsupported.
    V7 reverse processes PCM/IEEE-float RIFF WAV frames in the bridge and reports native=false;
    other processing uses the installed native renderer.
    """
    parameters = {"session_id": session_id, "operation": operation, "options": options or {}}
    return await asyncio.to_thread(NATIVE.request, "audio_op", parameters, 180)


@mcp.tool()
async def project_library(operation: str, options: dict[str, Any] | None = None,
                           session_id: str | None = None) -> dict[str, Any]:
    """Use native language, phoneme, style and media-library operations.
    style_apply with the singer's "<name> Default" style gives a new part the editor's default
    sound. lyrics_apply spreads a word or phrase over following notes. Attack/Release (dvqm_*)
    and Singing Skill act on standard VOCALOID parts; this is not the VOCALOID7 AI Attack macro.
    For AI notes, dvqm_get/set/clear with storage='bridge_metadata' manage bridge-owned metadata
    only, return native=false, and do not change native DVQM or synthesized AI audio.
    The V7 AI Attack macro uses project_edit performance.set voice_colors.S5Attack after
    performance.get confirms bank compatibility and bounds.
    phoneme_table returns a versioned manual reference, not native enumeration.
    Catalog reads need no project; operations changing notes or parts require a session_id.
    VOCALOID7 style and Singing Skill settings need explicit scope='track' and affect every
    part on that track. VOCALOID7 does not expose the VMM media library; media_* is unsupported.
    """
    return await _rpc("library_op", operation=operation, options=options or {}, session_id=session_id)


@mcp.tool()
async def project_clipboard(operation: str, options: dict[str, Any] | None = None,
                             session_id: str | None = None) -> dict[str, Any]:
    """Copy, cut or paste native tracks, parts or notes using a private clipboard.
    Use kind=tracks|parts|notes and indices for copy/cut; clipboard_id and target scope for paste.
    list/clear require no session. Clipboard snapshots never use the system clipboard.
    """
    return await _rpc("clipboard", operation=operation, options=options or {}, session_id=session_id)


@mcp.tool()
async def project_get(session_id: str, member: str, ref: str | None = None) -> dict[str, Any]:
    """Read a native property. Object values return session-scoped $ref handles."""
    return await _rpc("get", session_id=session_id, ref=ref, member=member)


@mcp.tool()
async def project_set(session_id: str, member: str, value: Any, ref: str | None = None) -> dict[str, Any]:
    """Set a native property using its real type. Object arguments use {$ref: HANDLE}."""
    return await _rpc("set", session_id=session_id, ref=ref, member=member, value=value)


@mcp.tool()
async def project_call(session_id: str, member_id: str, args: list[Any], ref: str | None = None) -> dict[str, Any]:
    """Call an exact member_id returned by project_members; overloads are never guessed."""
    return await _rpc("call", session_id=session_id, ref=ref, member_id=member_id, args=args)


@mcp.tool()
async def project_value_create(session_id: str, type: str, args: list[Any] | None = None,
                               member_id: str | None = None) -> dict[str, Any]:
    """Construct a native VSM data value, for example a tick or note-data struct."""
    return await _rpc("construct", session_id=session_id, type=type, args=args or [], member_id=member_id)


@mcp.tool()
async def project_items(session_id: str, ref: str, offset: int = 0, limit: int = 100) -> dict[str, Any]:
    """Enumerate an actual native collection using bounded pages."""
    return await _rpc("enumerate", session_id=session_id, ref=ref, offset=offset, limit=limit)


@mcp.tool()
async def voicebanks() -> dict[str, Any]:
    """Read installed voicebank names, IDs and availability from the native database."""
    return await _rpc("voices")


@mcp.tool()
async def project_ai_adjust(session_id: str, track_index: int, part_index: int,
                            take_number: int | None = None, preserve_pitch: bool = False,
                            note_indices: list[int] | None = None,
                            overwrite_existing: bool = False) -> dict[str, Any]:
    """Generate the selected VOCALOID7 AI part's real native singing/pitch cache from its notes/lyrics.
    Optional take_number changes the whole track, including other parts, before generation.
    preserve_pitch copies generated pitch to editable curves in one native transaction;
    note_indices selects notes (omit for all renderable notes), and overwrite_existing permits replacement.
    This is native AI synthesis, not aesthetic optimization or a separate AutoTune algorithm.
    It does not save a VPR or export WAV; use project_save or project_render_part separately.
    If generation fails after a Take change, the explicit Take edit remains; no automatic retry.
    """
    if NATIVE.installation.product != "VOCALOID7":
        raise ValueError("project_ai_adjust requires VOCALOID7 AI; use project_render_part for V6 synthesis.")
    for name, value in (("track_index", track_index), ("part_index", part_index)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(name + " must be a nonnegative integer.")
    if take_number is not None and (isinstance(take_number, bool) or not isinstance(take_number, int) or take_number < 0):
        raise ValueError("take_number must be a nonnegative integer from performance.get bounds.")
    if not preserve_pitch and (note_indices is not None or overwrite_existing):
        raise ValueError("note_indices and overwrite_existing require preserve_pitch=true.")
    if note_indices is not None and (not note_indices or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in note_indices)
            or len(set(note_indices)) != len(note_indices)):
        raise ValueError("note_indices must be a nonempty array of distinct nonnegative integers.")
    options = {"track_index": track_index, "part_index": part_index}
    before = await _rpc("score_edit", session_id=session_id, operation="ai.status", options=options)
    notes = {note["note_index"]: note for note in before["result"]["notes"]}
    renderable = [index for index, note in notes.items() if note["renderable"]]
    if not renderable:
        raise ValueError("Native AI generation requires at least one renderable note with valid lyrics and phonemes.")
    if preserve_pitch:
        for index in renderable if note_indices is None else note_indices:
            if index not in notes or not notes[index]["renderable"]:
                raise ValueError(f"Selected AI note is missing or not renderable: {index}.")
            if notes[index]["direct_pitch_points"] and not overwrite_existing:
                raise ValueError(f"Selected AI note {index} already has direct pitches; explicit overwrite_existing=true is required.")
    take = None
    if take_number is not None:
        take = await _rpc("score_edit", session_id=session_id, operation="performance.set",
                          options={"track_index": track_index, "scope": "track", "take_number": take_number})
    generation_options: dict[str, Any] = {**options, "preserve_pitch": preserve_pitch}
    if preserve_pitch:
        generation_options["overwrite_existing"] = overwrite_existing
    if note_indices is not None:
        generation_options["note_indices"] = note_indices
    try:
        result = await asyncio.to_thread(NATIVE.request, "score_edit",
                                        {"session_id": session_id, "operation": "ai.generate", "options": generation_options}, 180)
    except Exception as error:
        if take is None:
            raise
        raise RuntimeError(f"ai.generate failed after track {track_index} Take was set to {take_number}: {error}. "
                           "The track-wide Take edit remains applied; generation/pitch state needs readback. "
                           "No automatic retry or rollback was performed.") from error
    return {"session_id": session_id, "track_index": track_index, "part_index": part_index,
            "product": "VOCALOID7", "before": before, "generation": result,
            "take_change": take, "take_affects_all_parts_on_track": take_number is not None,
            "preserve_pitch_requested": preserve_pitch,
            "delivery_audio_exported": False,
            "semantics": "Native AI generation; no aesthetic optimization, fallback synthesis or automatic retry."}


@mcp.tool()
async def project_render_part(session_id: str, output_name: str, track_index: int = 0,
                               part_index: int = 0, overwrite: bool = False) -> dict[str, Any]:
    """Render the dry voice of one native vocal part to a verified WAV without playback or UI
    interaction. The file is 44.1 kHz mono 16-bit; effects and the delivery format belong to
    project_audio mixdown.
    """
    parameters = {"session_id": session_id, "output_name": output_name,
                  "track_index": track_index, "part_index": part_index, "overwrite": overwrite}
    result = await asyncio.to_thread(NATIVE.request, "render_part", parameters, 180)
    report = audio_inspect(result["path"])
    if report["frames"] <= 0 or report["peak"] == 0:
        raise RuntimeError("The native renderer produced an empty or silent WAV.")
    return {**result, "audio": report}


@mcp.tool()
def audio_inspect(path: str) -> dict[str, Any]:
    """Inspect actual audio samples, including duration, sample rate, channels, peak and RMS."""
    source = _source(WORKSPACE, path)
    sample_count = 0
    energy = 0.0
    peak = 0.0
    with sf.SoundFile(source) as audio:
        metadata = {"path": str(source), "frames": audio.frames, "sample_rate": audio.samplerate,
                    "channels": audio.channels, "format": audio.format, "subtype": audio.subtype,
                    "duration_seconds": audio.frames / audio.samplerate}
        for block in audio.blocks(blocksize=65536, dtype="float64", always_2d=True):
            if not np.isfinite(block).all():
                raise ValueError("Audio contains nonfinite samples.")
            sample_count += block.size
            energy += float(np.sum(block * block))
            peak = max(peak, float(np.max(np.abs(block), initial=0.0)))
    return {**metadata, "peak": peak, "rms": math.sqrt(energy / sample_count) if sample_count else 0.0}


@mcp.tool()
async def score_compose(output_name: str, title: str, bpm: float, notes: list[dict[str, Any]],
                        template: str | None = None, track_index: int = 0, part_index: int = 0,
                        voice_comp_id: str | None = None) -> dict[str, Any]:
    """Author and open a vocal score. Notes use quarter-note start/duration, MIDI pitch, lyric,
    optional phoneme, lang_id (0 Japanese, 1 English, 4 Chinese) and native raw expression data.
    Omitted AI-note phonemes use native G2PA for one complete syllable per note: kana, a
    one-syllable English word, or unmarked pinyin. Other lyric text needs an explicit phoneme.
    AI notes may select one template note with source={index, expected}; unselected notes are new.
    Uses an editor-authored template, then verifies loading in the real native engine.
    """
    task = asyncio.create_task(asyncio.to_thread(
        compose_native, STORE, NATIVE, template or str(TEMPLATE), output_name, title, bpm,
        notes, track_index, part_index, voice_comp_id))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        try:
            result = await task
        except Exception:
            pass
        else:
            await _rpc("close", session_id=result["native_session"]["session_id"], discard=True)
        raise


@mcp.tool()
def score_inspect(path: str, pointer: str = "") -> Any:
    """Read native project JSON or an RFC 6901 JSON Pointer without modifying any file."""
    return STORE.inspect(path, pointer)


@mcp.tool()
def score_summary(path: str) -> dict[str, Any]:
    """Read VPR tracks, voices, tempo and note counts without activating the editor."""
    return STORE.summary(path)


@mcp.tool()
def score_patch(path: str, output_name: str, operations: list[dict[str, Any]]) -> dict[str, Any]:
    """Create a separate VPR using RFC 6902 JSON Patch and preserve audio members.
    Tracked invalid-phoneme notes carry sidecar identity through moves and copies;
    deleted or replaced notes lose their old sidecar entry. Lyric, phoneme and language
    changes to tracked notes require native project_edit. Existing extension guards apply.
    AI notes cannot combine nonempty Attack/Release with Singing Skill: native loading loses the latter.
    For a conflicting AI note, explicitly removing either complete subtree is permitted in a separate copy.
    """
    return STORE.patch(path, operations, output_name)


@mcp.tool()
async def score_replace_notes(path: str, output_name: str, notes: list[dict[str, Any]],
                              track_index: int = 0, part_index: int = 0) -> dict[str, Any]:
    """Create a revised score with explicit beat-based notes and unchanged non-note project data.
    For AI notes, source={index, expected} preserves one inspected source note; omit source for a new note.
    Source snapshots must match exactly and be selected only once; guarded extension projects remain guarded.
    AI notes cannot combine nonempty Attack/Release with Singing Skill: native loading loses the latter.
    Omitted AI-note phonemes use native G2PA for one complete syllable per note; no session is retained.
    """
    task = asyncio.create_task(asyncio.to_thread(
        replace_notes_native, STORE, NATIVE, path, output_name, notes, track_index, part_index))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        try:
            await task
        except Exception:
            pass
        raise


@mcp.tool()
def score_tempo(path: str, output_name: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    """Write tempo events [{start: BEAT, bpm: BPM}], beginning at beat zero, to a separate VPR.
    Retained ticks keep their unknown event fields; new ticks inherit none.
    """
    return STORE.set_tempo(path, output_name, events)


@mcp.tool()
def score_curve(path: str, output_name: str, controller: str, events: list[dict[str, Any]],
                track_index: int = 0, part_index: int = 0) -> dict[str, Any]:
    """Replace a native controller lane already present in the template; units match that lane.
    Retained ticks keep their unknown event fields; new ticks inherit none.
    """
    return STORE.set_curve(path, output_name, controller, events, track_index, part_index)


@mcp.tool()
def midi_write(output_name: str, title: str, bpm: float, tracks: list[dict[str, Any]]) -> dict[str, Any]:
    """Write 480-PPQ MIDI with multiple instrument tracks and UTF-8 lyric events.
    Each track has name, optional channel/program, and beat-based notes as in score_compose.
    """
    return export_midi(WORKSPACE, title, bpm, tracks, output_name)


@mcp.tool()
def midi_read(path: str) -> dict[str, Any]:
    """Read MIDI notes, channels, instrument programs, lyrics, meter and tempo maps."""
    return import_midi(_source(WORKSPACE, path))


@mcp.resource("vocaloid://workflow")
def workflow() -> str:
    return json.dumps({
        "backend": "VOCALOID6/7 native VSM in an isolated Windows desktop",
        "workflow": ["vocaloid_workflow", "voicebanks", "score_compose or project_create",
                     "project_edit track.create, part.create, voice.set", "project_library style_apply",
                     "project_edit note.add and expression", "project_render_part", "project_audio mixdown",
                     "project_save", "project_close"],
        "rules": ["Never use interactive-editor UI automation.", "Never silently switch backend.",
                  "A VPR or MIDI is not a synthesized WAV.", "Do not guess native member signatures.",
                  "Lyrics are one syllable per note; Chinese lyrics are unmarked pinyin.",
                  "Save before close, or explicitly discard changes."],
        "ticks_per_quarter": 480,
        "template": str(TEMPLATE),
        "guide": WORKFLOW.read_text(encoding="utf-8"),
    }, ensure_ascii=False)


@mcp.prompt()
def write_song(brief: str, language: str = "Chinese", bpm: str = "120", key: str = "C major") -> str:
    return (
        f"Write an original song from this brief: {brief}\nLanguage: {language}; tempo: {bpm}; key: {key}.\n"
        "Plan sections, chords, melody, breath points and singable lyrics. Call vocaloid_workflow and "
        "follow its steps. Use one syllable per note in the written form the language needs: kana for "
        "Japanese, one-syllable words for English, unmarked pinyin for Chinese. Read voicebanks, create "
        "a native project or use score_compose with explicit beat-based notes, apply the singer's "
        "default style, and shape the performance only with controls the guide lists as sung by "
        "VOCALOID:AI. Render with project_audio mixdown, check the file with audio_inspect, save the "
        "project and close its session. Never touch the interactive editor and never "
        "claim audio synthesis from a score file alone. Report the actual output paths."
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
