"""MCP tools for isolated native VOCALOID6 sessions and music interchange."""

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
    "VOCALOID6 Native",
    instructions=(
        "Control real VOCALOID6 native engine sessions on a private Windows desktop. "
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
    return {**result, "mcp_version": __version__, "workspace": str(WORKSPACE), "server_pid": os.getpid(),
            "generation": NATIVE.generation, "managed_by_mcp": True,
            "isolation_desktop_expected": NATIVE.child.desktop_name, "fallbacks": False,
            "temp_cleanup": temp_cleanup.summary(WORKSPACE),
            "known_limitations": ["Complete editor-feature coverage has not been validated."]}


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
    """Open an existing VPR as an independent native session. The source remains unchanged."""
    return await _rpc("open", path=str(_source(WORKSPACE, path)))


@mcp.tool()
async def project_import(path: str, code_page: int = 65001, prefer_ai: bool = True) -> dict[str, Any]:
    """Import MIDI, VSQX, PPSF or VPR through the native loader as an owned session.
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
    """Save the native session to workspace/output. Overwriting requires explicit permission."""
    return await _rpc("save", session_id=session_id, output_name=output_name, overwrite=overwrite)


@mcp.tool()
async def project_clone(session_id: str, title: str | None = None) -> dict[str, Any]:
    """Create an independent native project copy with its own staged audio resources."""
    return await _rpc("clone_project", session_id=session_id, title=title)


@mcp.tool()
async def project_revert(session_id: str, discard_changes: bool = False) -> dict[str, Any]:
    """Reopen the last saved VPR and close the old session, returning a new session_id."""
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


@mcp.tool()
def vocaloid_features() -> dict[str, Any]:
    """Read the complete feature matrix, including unverified and unavailable items."""
    path = WORKSPACE / "docs" / "feature-matrix.md"
    return {"engine_version": "6.13.3.1", "path": str(path), "matrix": path.read_text(encoding="utf-8")}


@mcp.tool()
def vocaloid_workflow() -> dict[str, Any]:
    """Read this first when making a song: the tested steps from an empty session to a mixed WAV,
    the lyric form each language accepts, the controls VOCALOID:AI actually sings and the ones
    it only stores. Times are ticks, 480 per quarter note.
    """
    return {"mcp_version": __version__, "ticks_per_quarter": 480, "path": str(WORKFLOW),
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
    for value in selected.values():
        value["documentation_path"] = str(WORKSPACE / value["documentation"])
        if include_documentation:
            value["documentation_text"] = (WORKSPACE / value["documentation"]).read_text(encoding="utf-8")
    return {**index, "domains": selected, "total": sum(len(value["operations"]) for value in selected.values())}


@mcp.resource("vocaloid://features")
def feature_matrix() -> str:
    return (WORKSPACE / "docs" / "feature-matrix.md").read_text(encoding="utf-8")


@mcp.tool()
async def project_edit(session_id: str, operation: str,
                       options: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a typed native score operation with its documented options.
    Operations cover tracks, parts, notes, voices, tempo, meter, curves, automation and history.
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
    """Execute a documented native audio operation without activating the editor.
    mixdown is the deliverable render, with effects, at sample_rate 44100, 48000, 96000 or 192000;
    it stops at the end of the last part. Unsupported operations return explicit errors; no
    alternate audio backend is used.
    """
    parameters = {"session_id": session_id, "operation": operation, "options": options or {}}
    return await asyncio.to_thread(NATIVE.request, "audio_op", parameters, 180)


@mcp.tool()
async def project_library(operation: str, options: dict[str, Any] | None = None,
                           session_id: str | None = None) -> dict[str, Any]:
    """Use native language, phoneme, style and media-library operations.
    style_apply with the singer's "<name> Default" style gives a new part the editor's default
    sound. lyrics_apply spreads a word or phrase over following notes. Attack/Release (dvqm_*)
    and Singing Skill act on standard VOCALOID parts; an AI part stores them without singing them.
    phoneme_table returns a versioned manual reference, not native enumeration.
    Catalog reads need no project; operations changing notes or parts require a session_id.
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
    """
    return STORE.patch(path, operations, output_name)


@mcp.tool()
async def score_replace_notes(path: str, output_name: str, notes: list[dict[str, Any]],
                              track_index: int = 0, part_index: int = 0) -> dict[str, Any]:
    """Create a revised score with explicit beat-based notes and unchanged non-note project data.
    For AI notes, source={index, expected} preserves one inspected source note; omit source for a new note.
    Source snapshots must match exactly and be selected only once; guarded extension projects remain guarded.
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
        "backend": "VOCALOID6 native VSM in an isolated Windows desktop",
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
