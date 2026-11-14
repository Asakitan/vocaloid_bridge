"""Run bounded feature acceptance through the actual isolated MCP stdio server.

No host is built by this script. Run only after the integrated host is ready:
    .venv/Scripts/python.exe tools/verify_features.py
    .venv/Scripts/python.exe tools/verify_features.py --category score
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Awaitable, Callable
import uuid
import zipfile


ROOT = Path(__file__).resolve().parents[1]
CASES: list["Feature"] = []
EXPECTED_OPERATIONS = {
    domain["tool"]: {operation["operation"] for operation in domain["operations"]}
    for domain in json.loads((ROOT / "vocaloid_bridge" / "operations.json").read_text(encoding="utf-8"))["domains"].values()
}


class Blocked(RuntimeError):
    """A required capability or input is unavailable; this is not a pass."""


class Skipped(RuntimeError):
    """A case is intentionally inapplicable; this is not a pass."""


class ToolFailure(AssertionError):
    pass


def require(condition: Any, message: str, evidence: Any = None) -> None:
    if not condition:
        raise AssertionError(message + (": " + repr(evidence) if evidence is not None else ""))


@dataclass(frozen=True)
class Feature:
    identifier: str
    category: str
    tools: tuple[str, ...]
    run: Callable[["Acceptance"], Awaitable[None]]


def feature(identifier: str, category: str, *tools: str):
    def register(function):
        CASES.append(Feature(identifier, category, tools, function))
        return function
    return register


def read_vpr(path: str | Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    with zipfile.ZipFile(path) as archive:
        require(archive.testzip() is None, "Corrupt VPR archive", str(path))
        members = {name: archive.read(name) for name in archive.namelist()}
    require("Project/sequence.json" in members, "VPR has no sequence.json", str(path))
    sequence = json.loads(members["Project/sequence.json"])
    require(isinstance(sequence, dict) and isinstance(sequence.get("tracks", []), list), "Invalid VPR sequence")
    return sequence, members


def contains_atom(value: Any, expected: Any) -> bool:
    if isinstance(value, dict):
        return any(contains_atom(child, expected) for child in value.values())
    if isinstance(value, list):
        return any(contains_atom(child, expected) for child in value)
    return value == expected


class Acceptance:
    def __init__(self, arguments: argparse.Namespace):
        self.arguments = arguments
        self.run_id = uuid.uuid4().hex[:12]
        self.directory = ROOT / "artifacts" / ("feature-acceptance-" + self.run_id)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.client = None
        self.tools: dict[str, Any] = {}
        self.sessions: set[str] = set()
        self.results: list[dict[str, Any]] = []
        self.active: dict[str, Any] | None = None
        self.foreground_initial: int | None = None
        self.foreground_changes: list[dict[str, Any]] = []
        self.owned_pids: set[int] = {os.getpid()}
        self.monitor = None
        self.fixture: Path | None = None
        self.rendered_fixture: Path | None = None
        self.render_attempted = False
        self.counter = 0
        self.transport_error: str | None = None

    def output(self, label: str, suffix: str = ".vpr") -> str:
        self.counter += 1
        return f"feature-{self.run_id}-{self.counter:03d}-{label}{suffix}"

    def evidence(self, name: str, value: Any) -> None:
        if self.active is not None:
            self.active.setdefault("evidence", {})[name] = value

    def record(self, receipt: dict[str, Any]) -> None:
        destination = self.directory / (receipt["id"] + ".json")
        receipt["receipt"] = str(destination)
        destination.write_text(json.dumps(receipt, ensure_ascii=True, indent=2), encoding="utf-8")
        self.results.append(receipt)
        print(f"{receipt['status'].upper():7} {receipt['id']}: {receipt.get('reason', 'verified')}", flush=True)

    async def raw(self, name: str, arguments: dict[str, Any]):
        if name not in self.tools:
            raise Blocked("MCP tool is not advertised: " + name)
        if self.transport_error:
            raise Blocked("MCP transport is unavailable: " + self.transport_error)
        started = time.monotonic()
        try:
            result = await self.client.call_tool(name, arguments)
        except Exception as error:
            self.transport_error = f"{type(error).__name__}: {error}"
            raise
        structured = result.structuredContent
        if name == "vocaloid_status" and not result.isError and isinstance(structured, dict):
            for key in ("pid", "server_pid"):
                if isinstance(structured.get(key), int):
                    self.owned_pids.add(structured[key])
        entry = {
            "tool": name, "arguments": arguments, "is_error": bool(result.isError),
            "duration_seconds": round(time.monotonic() - started, 3), "result": structured,
        }
        if result.isError or structured is None:
            entry["content"] = [item.model_dump(mode="json") for item in result.content]
        if self.active is not None:
            self.active.setdefault("calls", []).append(entry)
        if not result.isError and isinstance(structured, dict):
            if name == "project_revert":
                self.sessions.discard(arguments["session_id"])
            for candidate in (structured, structured.get("native_session")):
                if isinstance(candidate, dict) and isinstance(candidate.get("session_id"), str):
                    if name == "project_close" and structured.get("closed"):
                        self.sessions.discard(candidate["session_id"])
                    else:
                        self.sessions.add(candidate["session_id"])
            if name == "project_close" and structured.get("closed"):
                self.sessions.discard(arguments["session_id"])
        return result

    async def call(self, name: str, **arguments):
        result = await self.raw(name, arguments)
        if result.isError:
            text = " ".join(getattr(item, "text", str(item)) for item in result.content)
            raise ToolFailure(name + ": " + text)
        content = result.structuredContent
        schema = self.tools[name].outputSchema or {}
        if content is None:
            require(not schema, name + " omitted advertised structuredContent")
            texts = [item.text for item in result.content if getattr(item, "type", None) == "text"]
            require(len(texts) == 1, name + " did not return one decodable text result")
            try:
                return json.loads(texts[0])
            except json.JSONDecodeError:
                return texts[0]
        if set(schema.get("properties", {})) == {"result"} and set(content) == {"result"}:
            return content["result"]
        return content

    async def rejected(self, name: str, pattern: str, **arguments) -> None:
        result = await self.raw(name, arguments)
        require(result.isError, "Invalid request unexpectedly succeeded", {"tool": name, "arguments": arguments})
        text = " ".join(getattr(item, "text", str(item)) for item in result.content)
        require(re.search(pattern, text, flags=re.IGNORECASE), "Wrong error; rejection does not verify the intended guard", text)

    @asynccontextmanager
    async def project(self, *, score: bool = False):
        if score:
            response = await self.call(
                "score_compose", output_name=self.output("seed"), title="Feature acceptance",
                bpm=120, notes=[{"start": index, "duration": 0.6, "pitch": pitch,
                                 "lyric": "\u3042", "phoneme": "a", "lang_id": 0}
                                for index, pitch in enumerate((60, 64, 67))],
            )
            identifier = response["native_session"]["session_id"]
        else:
            identifier = (await self.call("project_create", title="Feature acceptance", bpm=120))["session_id"]
        try:
            yield identifier
        finally:
            if identifier in self.sessions:
                await self.close(identifier)

    async def close(self, identifier: str, *, discard: bool = True) -> None:
        result = await self.call("project_close", session_id=identifier, discard_changes=discard)
        require(result.get("closed") is True, "Native session was not closed", result)

    async def save(self, identifier: str, label: str) -> tuple[dict[str, Any], Path]:
        result = await self.call("project_save", session_id=identifier, output_name=self.output(label))
        require(result.get("native") is True and result.get("saved") is True, "Not a native project save", result)
        path = Path(result["path"]).resolve()
        require(path.parent == (ROOT / "output").resolve(), "Saved file escaped output directory", str(path))
        sequence, _ = read_vpr(path)
        self.evidence(label + "_path", str(path))
        return sequence, path

    async def edit(self, identifier: str, operation: str, **options):
        result = await self.call("project_edit", session_id=identifier, operation=operation, options=options)
        require(result.get("native") is True and result.get("operation") == operation,
                "Unexpected score operation envelope", result)
        return result["result"]

    async def audio(self, identifier: str, operation: str, *, expected_native: bool = True, **options):
        result = await self.call("project_audio", session_id=identifier, operation=operation, options=options)
        metadata = operation == "inspect_audio" or (operation == "effects" and options.get("effect_id") is not None)
        require(result.get("native") is expected_native or metadata,
                "Audio operation backend attribution does not match the expected path", result)
        return result

    async def render_fixture(self) -> Path:
        if self.rendered_fixture is not None:
            return self.rendered_fixture
        if self.render_attempted:
            raise Blocked("Native fixture synthesis already failed in this run; it is not retried")
        self.render_attempted = True
        async with self.project(score=True) as identifier:
            _, score_path = await self.save(identifier, "render-source")
            await self.close(identifier, discard=False)
            opened = await self.call("project_open", path=str(score_path))
            require(opened["dirty"] is False, "Native singing fixture must render from a clean reopened project")
            result = await self.call("project_render_part", session_id=opened["session_id"],
                                     output_name=self.output("singing", ".wav"), track_index=0, part_index=0)
            require(result.get("native") is True, "Singing fixture was not synthesized by the native engine")
            metadata, _ = read_audio(result["path"])
            require(result["audio"]["frames"] == metadata["frames"], "Render report disagrees with decoded WAV")
            await self.close(opened["session_id"])
            self.rendered_fixture = Path(result["path"])
            self.fixture = self.rendered_fixture
            return self.rendered_fixture

    async def audio_input(self) -> Path:
        if self.fixture is None:
            supplied = self.arguments.audio_fixture
            if supplied is not None:
                candidate = supplied.resolve()
                if not candidate.is_file():
                    raise Blocked("Supplied native singing fixture does not exist: " + str(candidate))
                self.fixture = candidate
            else:
                existing = ROOT / "output" / "background-demo-31c27fd842.wav"
                self.fixture = existing if existing.is_file() else await self.render_fixture()
        metadata, _ = read_audio(self.fixture)
        self.evidence("native_singing_input", {"path": str(self.fixture), **metadata})
        return self.fixture

    async def method(self, identifier: str, name: str, arguments: list[Any], reference: str | None = None):
        members = await self.call("project_members", session_id=identifier, ref=reference)
        matches = [method for method in members["methods"] if method["member_id"].startswith(name + "(")
                   and len(method["parameters"]) == len(arguments)]
        if len(matches) != 1:
            raise Blocked(f"No unique advertised {name}/{len(arguments)} signature on {members['type']}")
        return await self.call("project_call", session_id=identifier, ref=reference,
                               member_id=matches[0]["member_id"], args=arguments)

    async def library(self, operation: str, identifier: str | None = None, *, expected_native: bool = True, **options):
        response = await self.call("project_library", operation=operation, options=options, session_id=identifier)
        require(response.get("native") is expected_native and response.get("operation") == operation
            and response.get("session_id") == identifier,
            "Library operation envelope mismatch", response)
        return response["result"]

    async def initialize_plain_ai(self, identifier: str) -> None:
        product = (await self.call("vocaloid_features"))["product"]
        voices = (await self.call("voicebanks"))["voices"]
        voice = next((item for item in voices if item["name"] == "asa" and item["kind"] == "Dnn"
                      and item["available_in_sequence"]), None)
        if voice is None:
            raise Blocked("An installed available asa AI voicebank is required")
        await self.edit(identifier, "track.create", type="MidiAi", name="Plain AI")
        await self.edit(identifier, "part.create", track_index=0, start_tick=0, duration_tick=1920)
        scope = {"scope": "track"} if product == "VOCALOID7" else {}
        await self.edit(identifier, "voice.set", track_index=0, part_index=0,
                        ai_voice_bank_id=voice["comp_id"], **scope)
        await self.edit(identifier, "note.add", track_index=0, part_index=0, start_tick=0,
                        duration_tick=480, number=60, lyric="あ", phonemes="a", lang_id=0)

    async def watch_foreground(self) -> None:
        import win32gui
        import win32process
        import pywintypes
        previous = self.foreground_initial
        while True:
            current = win32gui.GetForegroundWindow()
            if current != previous:
                try:
                    pid = win32process.GetWindowThreadProcessId(current)[1] if current else 0
                except pywintypes.error:
                    pid = 0
                if len(self.foreground_changes) < 128 or pid in self.owned_pids:
                    self.foreground_changes.append({"time": datetime.now(timezone.utc).isoformat(), "hwnd": current, "pid": pid})
                previous = current
            await asyncio.sleep(0.1)

    @property
    def owned_foreground_changes(self) -> list[dict[str, Any]]:
        return [event for event in self.foreground_changes if event.get("pid") in self.owned_pids]

    async def execute(self, item: Feature) -> None:
        self.active = {"id": item.identifier, "category": item.category, "run_id": self.run_id,
                       "started_utc": datetime.now(timezone.utc).isoformat(), "status": "failed", "calls": []}
        started = time.monotonic()
        existing = self.sessions.copy()
        try:
            if self.owned_foreground_changes:
                raise Blocked("An owned MCP/native process activated a foreground window; remaining work was stopped")
            missing = set(item.tools) - self.tools.keys()
            if missing:
                raise Blocked("Required MCP tools unavailable: " + ", ".join(sorted(missing)))
            await item.run(self)
            self.active["status"] = "passed"
        except Skipped as error:
            self.active.update(status="skipped", reason=str(error))
        except Blocked as error:
            self.active.update(status="blocked", reason=str(error))
        except ToolFailure as error:
            unsupported = re.search(
                r"NotSupportedException: VOCALOID7 (?:removed (?:MediaManager|the managed MediaManager API|the native VOCALO CHANGER renderer)|does not support part audio effects)",
                str(error),
            )
            unavailable = re.search(
                r"Unknown RPC method|Unknown audio operation|Unsupported score operation|Unknown library operation|"
                r"DllNotFoundException|DirectoryNotFoundException|FileNotFoundException|missing_classic_bank:|license.*unavailable|not available for native VOCALO CHANGER",
                str(error), re.IGNORECASE,
            )
            self.active.update(status="unsupported" if unsupported else "blocked" if unavailable else "failed", reason=str(error))
        except Exception as error:
            self.active.update(status="failed", reason=f"{type(error).__name__}: {error}")
        finally:
            for identifier in sorted(self.sessions - existing):
                try:
                    await self.close(identifier)
                except Exception as error:
                    self.active.update(status="failed", reason="Session cleanup failed: " + str(error))
            if self.owned_foreground_changes:
                self.active.update(status="failed", reason="Owned MCP/native foreground activation; see recorded HWND/PID observations")
            self.active["duration_seconds"] = round(time.monotonic() - started, 3)
            self.record(self.active)
            self.active = None


@feature("lifecycle.roundtrip", "lifecycle", "vocaloid_status", "project_create", "project_status",
         "project_get", "project_set", "project_save", "project_open", "project_close")
async def lifecycle_roundtrip(check: Acceptance) -> None:
    status = await check.call("vocaloid_status")
    require(status["backend"] == "native-vsm", "Unexpected synthesis backend", status)
    require(status["desktop"] == status["isolation_desktop_expected"], "Native host is not on its private desktop", status)
    async with check.project() as identifier:
        title = "Acceptance " + check.run_id
        await check.call("project_set", session_id=identifier, member="Title", value=title)
        require((await check.call("project_get", session_id=identifier, member="Title"))["value"] == title, "Title readback mismatch")
        _, path = await check.save(identifier, "lifecycle")
        original = path.read_bytes()
        await check.close(identifier, discard=False)
        opened = await check.call("project_open", path=str(path))
        reopened = opened["session_id"]
        require(opened["dirty"] is False, "Reopened project is dirty", opened)
        require((await check.call("project_status", session_id=reopened))["session_id"] == reopened, "Session status mismatch")
        require((await check.call("project_get", session_id=reopened, member="Title"))["value"] == title, "Saved title was lost")
        await check.call("project_set", session_id=reopened, member="Title", value=title + " copy")
        await check.rejected("project_save", "original|source", session_id=reopened, output_name=path.name, overwrite=True)
        await check.save(reopened, "lifecycle-copy")
        require(path.read_bytes() == original, "Opening or editing modified the original VPR")
        await check.close(reopened)
        await check.rejected("project_get", "session|closed|unknown|not found", session_id=reopened, member="Title")


@feature("lifecycle.guards", "lifecycle", "project_create", "project_save", "project_close")
async def lifecycle_guards(check: Acceptance) -> None:
    async with check.project() as identifier:
        await check.rejected("project_close", "unsaved|dirty|discard", session_id=identifier)
        _, path = await check.save(identifier, "overwrite")
        original = path.read_bytes()
        await check.rejected("project_save", "exist|overwrite", session_id=identifier, output_name=path.name)
        require(path.read_bytes() == original, "Rejected overwrite changed file")
        await check.rejected("project_save", "path|name|output|travers|relative|filename", session_id=identifier,
                             output_name="../" + check.output("escape"))
        await check.rejected("project_save", "extension|vpr", session_id=identifier, output_name=check.output("bad", ".txt"))
        saved = await check.call("project_save", session_id=identifier, output_name=path.name, overwrite=True)
        read_vpr(saved["path"])


@feature("transport.metadata", "transport", "vocaloid_features")
async def transport_metadata(check: Acceptance) -> None:
    resources = await check.client.list_resources()
    require("vocaloid://workflow" in {str(item.uri) for item in resources.resources}, "Workflow resource not advertised")
    workflow = await check.client.read_resource("vocaloid://workflow")
    description = json.loads(workflow.contents[0].text)
    require("workflow" in description and "rules" in description, "Workflow resource schema mismatch")
    prompts = await check.client.list_prompts()
    require("write_song" in {item.name for item in prompts.prompts}, "Song prompt not advertised")
    prompt = await check.client.get_prompt("write_song", arguments={"brief": "Acceptance marker", "language": "Japanese", "bpm": "120", "key": "C major"})
    require(any("Acceptance marker" in getattr(message.content, "text", "") for message in prompt.messages), "Prompt arguments were not applied")
    features = await check.call("vocaloid_features", include_matrix=True)
    require(features["matrix"] == (ROOT / "docs" / "feature-matrix.md").read_text(encoding="utf-8"), "Feature matrix response is stale")
    check.evidence("tool_names", sorted(check.tools))


@feature("lifecycle.clone_revert", "lifecycle", "project_clone", "project_revert", "project_edit", "project_save", "project_open")
async def lifecycle_clone_revert(check: Acceptance) -> None:
    async with check.project(score=True) as identifier:
        _, source = await check.save(identifier, "clone-source")
        original = source.read_bytes()
        clone = await check.call("project_clone", session_id=identifier, title="Independent clone")
        clone_id = clone["session_id"]
        require(clone_id != identifier, "Clone reused the source session")
        await check.edit(clone_id, "note.update", track_index=0, part_index=0, note_index=0, number=72)
        source_notes = await check.edit(identifier, "note.list", track_index=0, part_index=0)
        require(source_notes["notes"][0]["number"] == 60, "Clone changed its source session")
        await check.save(clone_id, "clone-independent")
        await check.edit(clone_id, "note.update", track_index=0, part_index=0, note_index=0, number=69)
        await check.rejected("project_revert", "discard|dirty|unsaved", session_id=clone_id)
        reverted = await check.call("project_revert", session_id=clone_id, discard_changes=True)
        reverted_id = reverted["session_id"]
        require(reverted_id != clone_id, "Revert did not return a replacement session")
        require((await check.edit(reverted_id, "note.list", track_index=0, part_index=0))["notes"][0]["number"] == 72,
                "Revert did not restore last saved notes")
        await check.rejected("project_status", "session|closed|unknown", session_id=clone_id)
        await check.close(reverted_id)
        require(source.read_bytes() == original, "Clone/revert modified its source VPR")


@feature("interchange.merge", "interchange", "project_merge", "project_edit", "project_save")
async def interchange_merge(check: Acceptance) -> None:
    async with check.project(score=True) as source_id:
        await check.edit(source_id, "tempo.set", start_tick=0, bpm=111)
        await check.edit(source_id, "tempo.set", start_tick=1920, bpm=133)
        _, source = await check.save(source_id, "merge-input")
        original = source.read_bytes()
        async with check.project() as target_id:
            old_count = len((await check.edit(target_id, "track.list"))["tracks"])
            merged = await check.call("project_merge", session_id=target_id, path=str(source), offset_tick=960)
            require(merged["native"] and merged["imported_tracks"] == 1 and merged["track_count"] == old_count + 1,
                    "Native track merge count mismatch", merged)
            parts = (await check.edit(target_id, "part.list"))["parts"]
            require(any(part["track_index"] == old_count and part["start_tick"] == 960 for part in parts), "Merged part offset mismatch", parts)
            await check.call("project_merge", session_id=target_id, path=str(source), include_tracks=False,
                             include_tempo=True, replace_tempo=True, offset_tick=0)
            tempos = (await check.edit(target_id, "tempo.list"))["tempos"]
            require([(entry["start_tick"], entry["bpm"]) for entry in tempos] == [(0, 111), (1920, 133)],
                    "Tempo-only native merge did not replace the map", tempos)
            require(len((await check.edit(target_id, "track.list"))["tracks"]) == old_count + 1, "Tempo-only merge added tracks")
            sequence, _ = await check.save(target_id, "merged")
            require(sequence["tracks"][old_count]["parts"][0]["pos"] == 960, "Merged track offset was not saved")
        require(source.read_bytes() == original, "Native merge modified its source project")


@feature("catalog.browse", "catalog", "native_api_catalog")
async def catalog_browse(check: Acceptance) -> None:
    first = await check.call("native_api_catalog", namespace="Yamaha.VOCALOID.VSM", limit=5,
                             include_excluded=True, include_members=True)
    second = await check.call("native_api_catalog", namespace="Yamaha.VOCALOID.VSM", offset=5, limit=5,
                              include_excluded=True, include_members=False)
    require(first["total"] > 5 and first["has_more"], "Catalog pagination was not exercised", first)
    require(first["assembly"] == second["assembly"], "Catalog assembly changed")
    names = [entry["type"] for entry in first["types"] + second["types"]]
    require(names == sorted(set(names)), "Catalog ordering or page overlap is incorrect", names)
    require(all(not entry["members"] for entry in second["types"]), "include_members=false was ignored")
    exact = await check.call("native_api_catalog", type="Yamaha.VOCALOID.VSM.WIVSMSequence")
    require(len(exact["types"]) == 1 and exact["types"][0]["type"].endswith(".WIVSMSequence"), "Exact type filter failed")
    excluded = [member for member in exact["types"][0]["members"] if not member["supported"]]
    require(excluded and all(member["reason"] for member in excluded), "Excluded members lack reasons")
    allowed = await check.call("native_api_catalog", type="Yamaha.VOCALOID.VSM.WIVSMSequence", include_excluded=False)
    require(all(member["supported"] for member in allowed["types"][0]["members"]), "Excluded member leaked into callable catalog")
    missing = await check.call("native_api_catalog", type="Acceptance.NoSuchType")
    require(missing["total"] == 0 and missing["types"] == [], "Unknown exact type was not empty")
    await check.rejected("native_api_catalog", "offset|limit|range", offset=-1)


@feature("reflection.values_refs_out", "reflection", "project_members", "project_call", "project_value_create",
         "project_items", "project_get", "project_set", "native_api_catalog")
async def reflection_values(check: Acceptance) -> None:
    async with check.project(score=True) as identifier:
        members = await check.call("project_members", session_id=identifier)
        require(any(member["name"] == "Title" and member["can_write"] for member in members["properties"]), "Title is not writable")
        catalog = await check.call("native_api_catalog", type="Yamaha.VOCALOID.VSM.VSMRelTick")
        constructors = [entry for entry in catalog["types"][0]["members"]
                        if entry["kind"] == "constructor" and entry["supported"]
                        and len(entry["parameters"]) == 1
                        and entry["parameters"][0]["value_type"] in ("System.Int32", "System.Int64")]
        require(constructors, "No supported integral tick constructor was advertised")
        constructor = sorted(constructors, key=lambda entry: entry["parameters"][0]["value_type"])[0]
        tick = await check.call("project_value_create", session_id=identifier, type=catalog["types"][0]["type"],
                    args=[240], member_id=constructor["member_id"])
        reference = tick["value"]["$ref"]
        require((await check.call("project_get", session_id=identifier, ref=reference, member="Value"))["value"] == 240,
                "Native struct constructor lost its scalar value")
        track = (await check.method(identifier, "GetTrack", [0]))["value"]
        require("$ref" in track, "Native track was not returned as a session reference")
        collection = (await check.call("project_get", session_id=identifier, member="Tracks"))["value"]
        page = await check.call("project_items", session_id=identifier, ref=collection["$ref"], offset=0, limit=1)
        require(len(page["items"]) == 1 and "$ref" in page["items"][0], "Native collection did not enumerate a track")
        out_method = next((method for method in members["methods"] if method["member_id"].startswith("GetTrackInsertIndex(")
                           and [argument["direction"] for argument in method["parameters"]] == ["in", "out"]), None)
        if out_method is None:
            raise Blocked("GetTrackInsertIndex(bool,out ulong) is not exposed by the installed host")
        response = await check.call("project_call", session_id=identifier, member_id=out_method["member_id"], args=[True, None])
        require(response["value"] is True and len(response["out_args"]) == 1, "Out call did not produce copy-out data", response)
        require(response["out_args"][0]["index"] == 1 and isinstance(response["out_args"][0]["value"], int), "Out scalar schema mismatch", response)
        await check.rejected("project_call", "out|null|placeholder", session_id=identifier,
                             member_id=out_method["member_id"], args=[True, 0])
        async with check.project() as foreign:
            await check.rejected("project_get", "reference|session|expired", session_id=foreign, ref=reference, member="Value")
            await check.rejected("project_set", "string|convert|type", session_id=foreign, member="Title", value=17)
        await check.rejected("project_set", "string|convert|type|identity transaction", session_id=identifier, member="Title", value=17)
        await check.edit(identifier, "sequence.update", title="Reference invalidation")
        await check.rejected("project_get", "reference|expired", session_id=identifier, ref=track["$ref"], member="Name")


@feature("score.performance_catalog", "score", "project_edit", "score_compose", "project_save", "project_open", "vocaloid_features")
async def score_performance_catalog(check: Acceptance) -> None:
    seed = await check.call("score_compose", output_name=check.output("performance-seed"), title="Performance acceptance",
                            bpm=120, notes=[{"start": 0, "duration": 1, "pitch": 60,
                                             "lyric": "\u3042", "phoneme": "a", "lang_id": 0}])
    identifier = seed["native_session"]["session_id"]
    is_v7 = (await check.call("vocaloid_features"))["product"] == "VOCALOID7"
    scope = {"track_index": 0, "part_index": 0, **({"scope": "track"} if is_v7 else {})}
    result = await check.edit(identifier, "performance.get", **scope)
    expected_effects = {"SingingSkill", "VoiceColor", "RobotVoice", "Breath"} | (set() if is_v7 else {"Take"})
    require({item["effect"] for item in result["bypass"]} == expected_effects,
            "Native MIDI effect availability is incomplete", result)
    require(all(entry["setting"]["LowerBoundValue"] <= entry["value"] <= entry["setting"]["UpperBoundValue"]
                for entry in result["voice_colors"] or []), "Native voice-color value exceeds its bounds", result)
    if any(result[name] is None for name in ("robot", "breath", "take", "voice_colors")):
        raise Blocked("The installed AI part lacks one of the required native performance effects")
    invalid_performance = ({"robot_mode": "0"}, {"breath_mode": "0"}, {"breath_type": "0"},
                           {"voice_colors": {"6" if is_v7 else "0": 0}}, {"bypass": {"2": False}})
    for invalid in invalid_performance:
        await check.rejected("project_edit", "one of|Unknown|invalid", session_id=identifier,
                             operation="performance.set", options={**scope, **invalid})
    await check.rejected("project_edit", "controller type", session_id=identifier,
                         operation="controller.list", options={**scope, "type": "1"})
    await check.rejected("project_edit", "controller type", session_id=identifier,
                         operation="controller.list", options={**scope, "type": "dynamics"})
    require((await check.edit(identifier, "controller.list", **scope, type="Dynamics"))["type"] == "Dynamics",
            "Native controller name no longer resolves")
    require(await check.edit(identifier, "performance.get", **scope) == result,
            "Rejected numeric enum names changed the part")
    robot = next(mode for mode in result["robot"]["modes"] if mode != result["robot"]["mode"])
    breath = next(mode for mode in result["breath"]["modes"] if mode != result["breath"]["mode"])
    breath_type = next(value for value in result["breath"]["types"] if value != result["breath"]["type"])
    exhalation = result["breath"]["setting"]["UpperBoundValue"]
    take_key = "take_number" if is_v7 else "take_lane"
    take_value = result["take"]["default_take_number"] if is_v7 else result["take"]["setting"]["LowerBoundValue"]
    color_name = "S5Expression" if is_v7 else "Exciter"
    color = next(entry for entry in result["voice_colors"] if entry["name"] == color_name)
    color_value = color["setting"]["UpperBoundValue"]
    bypass = {entry["effect"]: not entry["bypassed"] for entry in result["bypass"] if entry["available"]}
    requested = {"robot_mode": robot.swapcase(), "breath_mode": breath, "breath_type": breath_type,
                 "breath_exhalation": exhalation, take_key: take_value,
                 "voice_colors": {color_name: color_value}, "bypass": bypass}
    changed = await check.edit(identifier, "performance.set", **scope, **requested)
    require(changed["robot"]["mode"] == robot and changed["breath"]["mode"] == breath
            and changed["breath"]["type"] == breath_type and changed["breath"]["exhalation"] == exhalation
            and changed["take"]["take_number" if is_v7 else "lane"] == take_value, "Native performance settings were not applied", changed)
    require(next(entry for entry in changed["voice_colors"] if entry["name"] == color_name)["value"] == color_value
            and all(entry["bypassed"] == bypass[entry["effect"]] for entry in changed["bypass"] if entry["effect"] in bypass),
            "Native voice color or bypass settings were not applied", changed)
    await check.rejected("project_edit", "exhalation|range", session_id=identifier, operation="performance.set",
                         options={**scope, "robot_mode": result["robot"]["mode"],
                                  "breath_exhalation": exhalation + 1})
    require(await check.edit(identifier, "performance.get", **scope) == changed,
            "Rejected performance update changed the part")
    _, path = await check.save(identifier, "performance")
    reopened = (await check.call("project_open", path=str(path)))["session_id"]
    require(await check.edit(reopened, "performance.get", **scope) == changed,
            "Native performance settings did not survive save/reopen")
    await check.close(reopened)
    check.evidence("installed_performance", result)


@feature("score.automation", "score", "project_edit", "project_create", "project_save", "project_open")
async def score_automation(check: Acceptance) -> None:
    identifier = (await check.call("project_create", title="Automation acceptance", bpm=120))["session_id"]
    await check.edit(identifier, "track.create", type="MidiAi", name="Automation track")
    saved_points = {}
    for scope in ("track_volume", "track_pan", "master_volume"):
        options = {"scope": scope} if scope == "master_volume" else {"scope": scope, "track_index": 0}
        before = await check.edit(identifier, "automation.list", **options)
        first, minimum, maximum = before["default_value"], before["minimum"], before["maximum"]
        points = [{"tick": 0, "value": first}, {"tick": 480, "value": minimum}, {"tick": 960, "value": maximum}]
        result = await check.edit(identifier, "automation.set", **options, points=points, replace=True)
        require([(item["tick"], item["value"]) for item in result["points"]]
            == [(point["tick"], point["value"]) for point in points], "Native automation set did not persist", result)
        result = await check.edit(identifier, "automation.set", **options, points=[{"tick": 480, "value": first}])
        require(next(item for item in result["points"] if item["tick"] == 480)["value"] == first,
            "Native automation upsert did not update the event", result)
        remove_index = next(item["event_index"] for item in result["points"] if item["tick"] == 960)
        result = await check.edit(identifier, "automation.remove", **options, event_index=remove_index)
        require([item["tick"] for item in result["points"]] == [0, 480], "Native automation remove failed", result)
        zero = next(item["event_index"] for item in result["points"] if item["tick"] == 0)
        await check.rejected("project_edit", "zero|retained", session_id=identifier, operation="automation.remove",
                 options={**options, "event_index": zero})
        await check.rejected("project_edit", "value|range", session_id=identifier, operation="automation.set",
                 options={**options, "points": [{"tick": 240, "value": maximum + 1}]})
        require((await check.edit(identifier, "automation.list", **options))["points"] == result["points"],
            "Rejected automation mutation changed the curve")
        saved_points[scope] = result["points"]
    _, path = await check.save(identifier, "automation")
    reopened = (await check.call("project_open", path=str(path)))["session_id"]
    for scope, points in saved_points.items():
        options = {"scope": scope} if scope == "master_volume" else {"scope": scope, "track_index": 0}
        require((await check.edit(reopened, "automation.list", **options))["points"] == points,
            "Automation curve did not survive native save and reopen", scope)
    await check.close(reopened)
    check.evidence("automation_vpr", str(path))


@feature("score.tracks", "score", "project_edit", "score_compose", "project_save")
async def score_tracks(check: Acceptance) -> None:
    async with check.project() as identifier:
        before = (await check.edit(identifier, "track.list"))["tracks"]
        created = await check.edit(identifier, "track.create", type="Midi", name="Acceptance track")
        index = created["track_index"]
        await check.edit(identifier, "track.update", track_index=index, name="Renamed track", color=6, mute=True, solo=False)
        before_invalid = (await check.edit(identifier, "track.list"))["tracks"]
        await check.rejected("project_edit", "color|range|0..15", session_id=identifier, operation="track.update",
                     options={"track_index": index, "color": 16})
        require((await check.edit(identifier, "track.list"))["tracks"] == before_invalid,
            "Rejected palette index changed the native track")
        duplicate = await check.edit(identifier, "track.duplicate", track_index=index, name="Duplicate track")
        await check.edit(identifier, "track.reorder", track_index=duplicate["track_index"], to_index=0)
        listed = (await check.edit(identifier, "track.list"))["tracks"]
        require(listed[0]["name"] == "Duplicate track", "Track reorder did not persist")
        original = next(track for track in listed if track["name"] == "Renamed track")
        require(original["mute"] and not original["solo"] and original["color"] == 6, "Track property readback mismatch", original)
        await check.edit(identifier, "track.remove", track_index=0)
        after = (await check.edit(identifier, "track.list"))["tracks"]
        require(len(after) == len(before) + 1, "Track count mismatch after remove")
        sequence, _ = await check.save(identifier, "tracks")
        require(any(track["name"] == "Renamed track" for track in sequence["tracks"]), "Saved track name missing")


@feature("score.parts", "score", "project_edit", "score_compose", "project_save")
async def score_parts(check: Acceptance) -> None:
    async with check.project(score=True) as identifier:
        kind = (await check.edit(identifier, "track.list"))["tracks"][0]["type"]
        target = await check.edit(identifier, "track.create", type=kind, name="Part destination")
        track = target["track_index"]
        created = await check.edit(identifier, "part.create", track_index=track, start_tick=0, duration_tick=3840, name="New part")
        part = created["part_index"]
        await check.edit(identifier, "part.update", track_index=track, part_index=part, name="Renamed part")
        await check.edit(identifier, "part.resize", track_index=track, part_index=part, duration_tick=5760)
        await check.edit(identifier, "part.duplicate", track_index=track, part_index=part, start_tick=7680)
        await check.edit(identifier, "part.move", track_index=track, part_index=part, start_tick=1920)
        listed = (await check.edit(identifier, "part.list", track_index=track))["parts"]
        require(sorted(item["start_tick"] for item in listed) == [1920, 7680], "Part move/duplicate positions mismatch", listed)
        require(all(item["duration_tick"] == 5760 for item in listed), "Part resize did not survive duplication")
        duplicate = next(item for item in listed if item["start_tick"] == 7680)
        await check.edit(identifier, "part.remove", track_index=track, part_index=duplicate["part_index"])
        require(len((await check.edit(identifier, "part.list", track_index=track))["parts"]) == 1, "Part remove failed")
        sequence, _ = await check.save(identifier, "parts")
        persisted = sequence["tracks"][track]["parts"]
        require(len(persisted) == 1 and persisted[0]["name"] == "Renamed part"
                and persisted[0]["pos"] == 1920 and persisted[0]["duration"] == 5760, "Saved part mismatch", persisted)


@feature("score.notes_voice", "score", "project_edit", "score_compose", "voicebanks", "project_save", "vocaloid_features", "project_inspect", "vocaloid_operations")
async def score_notes(check: Acceptance) -> None:
    async with check.project(score=True) as identifier:
        selected = {"track_index": 0, "part_index": 0}
        is_v7 = (await check.call("vocaloid_features"))["product"] == "VOCALOID7"
        listed = (await check.edit(identifier, "note.list", **selected))["notes"]
        require([note["number"] for note in listed] == [60, 64, 67], "Seed notes mismatch")
        await check.edit(identifier, "note.clear", **selected)
        added = await check.edit(identifier, "note.add", **selected, start_tick=0, duration_tick=240,
                                 number=62, velocity=70, lyric="\u3042", phonemes="a", lang_id=0)
        await check.edit(identifier, "note.update", **selected, note_index=added["note_index"], number=65,
                         velocity=85, duration_tick=360, lyric="\u3044", phonemes="i", is_valid_phonemes=True,
                         expression=added["expression"], ai_expression=added["ai_expression"],
                         is_protected=True, **({} if is_v7 else {"ai_vibrato_enabled": False}))
        await check.edit(identifier, "note.duplicate", **selected, note_index=0, start_tick=480)
        notes = (await check.edit(identifier, "note.list", **selected))["notes"]
        require(len(notes) == 2 and [note["start_tick"] for note in notes] == [0, 480], "Note duplicate mismatch", notes)
        require(all(note["number"] == 65 and note["velocity"] == 85 and note["phonemes"] == "i" for note in notes), "Note fields did not copy")
        inspected = await check.call("project_inspect", session_id=identifier, feature="notes", **selected, note_index=1)
        templates = {item["arguments"]["operation"]: item for item in inspected["contract"]["write_calls"]}
        require({"note.add", "note.update", "note.remove", "note.clear", "note.duplicate", "note.split", "note.join", "note.batch_update"}
            <= templates.keys(), "Note discovery omitted supported operations", templates)
        removal = templates["note.remove"]
        require(removal["tool"] == "project_edit" and removal["arguments"]["session_id"] == identifier
            and removal["arguments"]["options"] == {**selected, "note_index": 1},
            "Inspected removal template did not bind the selected note", removal)
        operation = await check.call("vocaloid_operations", domain="score", operation="note.remove")
        require("notes" in operation["domains"]["score"]["operations"][0]["features"],
            "Note removal operation is not linked to its feature", operation)
        await check.edit(identifier, "note.remove", **removal["arguments"]["options"])
        voices = await check.call("voicebanks")
        require(isinstance(voices["voices"], list) and voices["voices"], "No native voicebanks returned")
        voice_scope = {**selected, **({"scope": "track"} if is_v7 else {})}
        voice = await check.edit(identifier, "voice.get", **voice_scope)
        key = "ai_voice_bank_id" if voice["ai"] else "voice_bank_id"
        require(voice[key], "Seed has no native voice identity")
        changed = await check.edit(identifier, "voice.set", **voice_scope, **{key: voice[key]})
        require(changed[key] == voice[key], "Voice ID readback mismatch")
        sequence, _ = await check.save(identifier, "notes")
        saved = sequence["tracks"][0]["parts"][0]["notes"]
        require(len(saved) == 1 and saved[0]["number"] == 65 and saved[0]["duration"] == 360
                and saved[0]["lyric"] == "\u3044" and saved[0]["phoneme"] == "i", "Saved note mismatch", saved)


@feature("score.tempo_meter", "score", "project_edit", "project_save")
async def score_tempo_meter(check: Acceptance) -> None:
    async with check.project() as identifier:
        await check.edit(identifier, "tempo.list")
        await check.edit(identifier, "tempo.set", start_tick=0, bpm=123.45)
        inserted = await check.edit(identifier, "tempo.set", start_tick=1920, bpm=135)
        tempos = (await check.edit(identifier, "tempo.list"))["tempos"]
        require(any(item["start_tick"] == 1920 and item["bpm"] == 135 for item in tempos), "Tempo insertion mismatch")
        await check.edit(identifier, "tempo.remove", tempo_index=inserted["tempo_index"])
        await check.edit(identifier, "time_signature.list")
        await check.edit(identifier, "time_signature.set", bar=0, numerator=3, denominator=4)
        inserted = await check.edit(identifier, "time_signature.set", bar=2, numerator=5, denominator=8)
        signatures = (await check.edit(identifier, "time_signature.list"))["time_signatures"]
        require(any(item["bar"] == 2 and item["numerator"] == 5 and item["denominator"] == 8 for item in signatures), "Meter insertion mismatch")
        await check.edit(identifier, "time_signature.remove", time_signature_index=inserted["time_signature_index"])
        sequence, _ = await check.save(identifier, "tempo-meter")
        master = sequence["masterTrack"]
        require(master["tempo"]["events"][0]["value"] == 12345, "Saved tempo mismatch", master)
        require(master["timeSig"]["events"][0]["numer"] == 3, "Saved meter mismatch", master)
        await check.rejected("project_edit", "initial|zero", session_id=identifier, operation="tempo.remove", options={"tempo_index": 0})
        await check.rejected("project_edit", "power|denominator", session_id=identifier,
                             operation="time_signature.set", options={"bar": 2, "numerator": 3, "denominator": 3})


@feature("score.curves_pitch", "score", "project_edit", "score_compose", "project_save", "project_open")
async def score_curves(check: Acceptance) -> None:
    async with check.project(score=True) as identifier:
        selected = {"track_index": 0, "part_index": 0}
        types = (await check.edit(identifier, "controller.types", **selected))["types"]
        require(types, "No native controller ranges")
        controller = next((entry for entry in types if entry["type"] == "Dynamics" and entry["maximum"] > entry["minimum"]), None)
        require(controller is not None, "No usable native controller range", types)
        lane = {**selected, "type": controller["type"]}
        value = controller["minimum"] + (controller["maximum"] - controller["minimum"]) // 3
        points = [{"tick": 60, "value": value}, {"tick": 180, "value": controller["default_value"]}]
        await check.edit(identifier, "controller.set", **lane, points=points, replace=True)
        readback = (await check.edit(identifier, "controller.list", **lane))["points"]
        require([(entry["tick"], entry["value"]) for entry in readback] == [(entry["tick"], entry["value"]) for entry in points], "Controller roundtrip mismatch")
        await check.edit(identifier, "controller.remove", **lane, controller_index=0)
        pitch_lane = {**selected, "note_index": 0}
        await check.edit(identifier, "pitch.list", **pitch_lane)
        await check.edit(identifier, "pitch.set", **pitch_lane, points=[{"tick": 0, "value": 60.0}, {"tick": 120, "value": 60.5}], replace=True)
        pitches = (await check.edit(identifier, "pitch.list", **pitch_lane))["points"]
        require(any(point["tick"] == 120 and abs(point["value"] - 60.5) < 0.001 for point in pitches), "Direct pitch readback mismatch")
        _, path = await check.save(identifier, "curves")
        reopened = (await check.call("project_open", path=str(path)))["session_id"]
        persisted = (await check.edit(reopened, "pitch.list", **pitch_lane))["points"]
        require(persisted == pitches, "Direct pitch did not persist to VPR")
        await check.close(reopened)
        await check.edit(identifier, "pitch.clear", **pitch_lane)
        require(not (await check.edit(identifier, "pitch.list", **pitch_lane))["points"], "Direct pitch clear failed")


@feature("score.sequence_history", "score", "project_edit", "project_save", "project_open")
async def score_sequence_history(check: Acceptance) -> None:
    async with check.project() as identifier:
        initial = await check.edit(identifier, "sequence.get")
        await check.edit(identifier, "sequence.update", title="Edited sequence", global_bpm=128, global_tempo_enabled=True)
        sequence = await check.edit(identifier, "sequence.get")
        require(sequence["title"] == "Edited sequence" and sequence["global_bpm"] == 128 and sequence["global_tempo_enabled"], "Sequence settings mismatch")
        await check.edit(identifier, "loop.get")
        await check.edit(identifier, "loop.set", enabled=True, start_tick=480, end_tick=1920)
        loop = await check.edit(identifier, "loop.get")
        require(loop == {"enabled": True, "start_tick": 480, "end_tick": 1920}, "Loop settings mismatch", loop)
        tuning = await check.edit(identifier, "tuning.get")
        target = float(tuning["minimum"] + (tuning["maximum"] - tuning["minimum"]) * 0.6)
        await check.edit(identifier, "tuning.set", value=target)
        require(abs((await check.edit(identifier, "tuning.get"))["value"] - target) < 0.001, "Tuning readback mismatch")
        tracks_before = len((await check.edit(identifier, "track.list"))["tracks"])
        await check.edit(identifier, "track.create", name="Undo marker", type="Audio")
        history = await check.edit(identifier, "history.status")
        require(history["can_undo"], "Native mutation did not create undo history", history)
        await check.edit(identifier, "undo")
        require(len((await check.edit(identifier, "track.list"))["tracks"]) == tracks_before, "Undo did not restore track count")
        await check.edit(identifier, "redo")
        require(len((await check.edit(identifier, "track.list"))["tracks"]) == tracks_before + 1, "Redo did not restore track count")
        _, path = await check.save(identifier, "sequence")
        reopened = (await check.call("project_open", path=str(path)))["session_id"]
        require((await check.edit(reopened, "loop.get")) == loop, "Saved loop settings mismatch")
        require((await check.edit(reopened, "sequence.get"))["title"] != initial["title"], "Saved sequence edits were lost")
        await check.close(reopened)


@feature("score.validation", "score", "project_edit", "score_compose")
async def score_validation(check: Acceptance) -> None:
    async with check.project(score=True) as identifier:
        before = await check.edit(identifier, "note.list", track_index=0, part_index=0)
        await check.rejected("project_edit", "duration_tick|range", session_id=identifier, operation="note.add",
                             options={"track_index": 0, "part_index": 0, "start_tick": 0, "duration_tick": -1, "number": 60})
        await check.rejected("project_edit", "track_index|range", session_id=identifier,
                             operation="track.remove", options={"track_index": 99999})
        await check.rejected("project_edit", "unsupported|unknown|no verified identity transaction", session_id=identifier,
                             operation="Acceptance.Nonexistent", options={})
        require(await check.edit(identifier, "note.list", track_index=0, part_index=0) == before, "Rejected score edit changed notes")


@feature("score.split_join", "score", "project_edit", "score_compose", "project_save")
async def score_split_join(check: Acceptance) -> None:
    async with check.project(score=True) as identifier:
        scope = {"track_index": 0, "part_index": 0}
        before = (await check.edit(identifier, "note.list", **scope))["notes"]
        split = await check.edit(identifier, "note.split", **scope, note_index=0, split_tick=120)
        require(len(split["notes"]) == 2 and sum(note["duration_tick"] for note in split["notes"]) == before[0]["duration_tick"],
            "Native note split lost duration", split)
        await check.edit(identifier, "note.join", **scope, note_indices=[note["note_index"] for note in split["notes"]])
        after = (await check.edit(identifier, "note.list", **scope))["notes"]
        require(len(after) == len(before) and after[0]["duration_tick"] == before[0]["duration_tick"]
            and after[0]["number"] == before[0]["number"], "Note split/join changed pitch or coverage")
        kind = (await check.edit(identifier, "track.list"))["tracks"][0]["type"]
        track = (await check.edit(identifier, "track.create", type=kind, name="Split part track"))["track_index"]
        await check.edit(identifier, "part.create", track_index=track, start_tick=0, duration_tick=3840, name="Split part")
        split = await check.edit(identifier, "part.split", track_index=track, part_index=0, split_tick=1920)
        require(len(split["parts"]) == 2 and sum(part["duration_tick"] for part in split["parts"]) == 3840,
            "Part split lost timeline coverage", split)
        joined = await check.edit(identifier, "part.join", track_index=track, part_indices=[part["part_index"] for part in split["parts"]])
        require(joined["duration_tick"] == 3840 and len((await check.edit(identifier, "part.list", track_index=track))["parts"]) == 1,
            "Part join did not reconstruct the original interval")
        await check.save(identifier, "split-join")


@feature("score.selection_time", "score", "project_edit", "score_compose")
async def score_selection_time(check: Acceptance) -> None:
    async with check.project(score=True) as identifier:
        scope = {"track_index": 0, "part_index": 0}
        dynamics = next(entry for entry in (await check.edit(identifier, "controller.types", **scope))["types"] if entry["type"] == "Dynamics")
        await check.edit(identifier, "controller.set", **scope, type="Dynamics", points=[{"tick": 0, "value": dynamics["default_value"]}])
        for target in ("track", "part", "note", "tempo", "time_signature", "controller"):
            selected = {"target": target, **scope}
            if target == "controller":
                selected["type"] = "Dynamics"
            await check.edit(identifier, "selection.set", **selected, indices=[0], selected=True)
            require((await check.edit(identifier, "selection.get", **selected))["selected_indices"] == [0], "Native selection mismatch: " + target)
            await check.edit(identifier, "selection.set", **selected, indices=[], clear_existing=True)
            require((await check.edit(identifier, "selection.get", **selected))["selected_indices"] == [], "Native selection did not clear: " + target)
        await check.edit(identifier, "part.move", **scope, start_tick=2400)
        await check.edit(identifier, "time.insert", start_tick=0, duration_tick=480, include_tempo=False)
        require((await check.edit(identifier, "part.list", track_index=0))["parts"][0]["start_tick"] == 2880, "Time insertion did not shift the part")
        await check.edit(identifier, "time.delete", start_tick=0, duration_tick=480, include_tempo=False)
        require((await check.edit(identifier, "part.list", track_index=0))["parts"][0]["start_tick"] == 2400, "Time deletion did not restore the part")
        before_parts = (await check.edit(identifier, "part.list", track_index=0))["parts"]
        before_notes = await check.edit(identifier, "note.list", **scope)
        await check.edit(identifier, "time.insert", start_tick=2500, duration_tick=120)
        parts = (await check.edit(identifier, "part.list", track_index=0))["parts"]
        require([(part["start_tick"], part["duration_tick"]) for part in parts] == [(2400, 100), (2620, 7580)],
            "Crossing time insertion did not split and shift the part", parts)
        await check.edit(identifier, "undo")
        require((await check.edit(identifier, "part.list", track_index=0))["parts"] == before_parts
            and await check.edit(identifier, "note.list", **scope) == before_notes,
            "Undo did not restore the crossing part and notes")


def midi_snapshot(path: str | Path) -> dict[str, Any]:
    import mido
    midi = mido.MidiFile(path, charset="utf-8")
    require(midi.type in (0, 1) and midi.ticks_per_beat > 0, "Invalid synchronous MIDI file")
    notes, tempos, meters, lyrics = [], [], [], []
    for track in midi.tracks:
        tick = 0
        active: dict[tuple[int, int], list[int]] = {}
        for message in track:
            tick += message.time
            beat = tick / midi.ticks_per_beat
            if message.type == "note_on" and message.velocity > 0:
                active.setdefault((message.channel, message.note), []).append(tick)
            elif message.type in ("note_on", "note_off"):
                key = (message.channel, message.note)
                require(bool(active.get(key)), "Unmatched MIDI note-off")
                start = active[key].pop(0)
                notes.append((message.note, start / midi.ticks_per_beat, (tick - start) / midi.ticks_per_beat))
            elif message.type == "set_tempo":
                tempos.append((beat, mido.tempo2bpm(message.tempo)))
            elif message.type == "time_signature":
                meters.append((beat, message.numerator, message.denominator))
            elif message.type == "lyrics":
                lyrics.append((beat, message.text))
        require(not any(active.values()), "MIDI contains dangling note-ons")
    return {"notes": sorted(notes), "tempos": sorted(tempos), "meters": sorted(meters), "lyrics": sorted(lyrics)}


async def vsqx_native_notes(check: Acceptance, identifier: str) -> tuple[list[dict[str, Any]], list[tuple[Any, ...]]]:
    tracks = (await check.edit(identifier, "track.list"))["tracks"]
    notes = []
    for track in tracks:
        if track["type"] not in ("Midi", "MidiAi"):
            continue
        for part in (await check.edit(identifier, "part.list", track_index=track["track_index"]))["parts"]:
            current = (await check.edit(identifier, "note.list", track_index=track["track_index"],
                                        part_index=part["part_index"]))["notes"]
            notes.extend((note["start_tick"], note["duration_tick"], note["number"], note["lyric"], note["phonemes"])
                         for note in current)
    return tracks, notes


async def verify_vsqx(check: Acceptance, fixture: Path | None, version: int) -> None:
    import xml.etree.ElementTree as element_tree
    if fixture is None or not fixture.is_file():
        raise Blocked(f"An actual VSQX {version} fixture must be supplied")
    source = fixture.resolve()
    original = source.read_bytes()
    root = element_tree.fromstring(original)
    schema = f"http://www.yamaha.co.jp/vocaloid/schema/vsq{version}/"
    require(root.tag == "{" + schema + f"}}vsq{version}", f"Fixture is not a VSQX {version} project")
    namespace = {"vsq": schema}
    part_name = "vsPart" if version == 4 else "musicalPart"
    fields = ("t", "dur", "n", "y", "p") if version == 4 else ("posTick", "durTick", "noteNum", "lyric", "phnms")
    expected = [(int(note.findtext("vsq:" + fields[0], namespaces=namespace)),
                 int(note.findtext("vsq:" + fields[1], namespaces=namespace)),
                 int(note.findtext("vsq:" + fields[2], namespaces=namespace)),
                 note.findtext("vsq:" + fields[3], namespaces=namespace),
                 note.findtext("vsq:" + fields[4], namespaces=namespace))
                for note in root.findall(".//vsq:" + part_name + "/vsq:note", namespace)]
    require(expected, f"VSQX {version} fixture contains no vocal notes")
    try:
        imported = await check.call("project_import", path=str(source), prefer_ai=False)
    except ToolFailure as error:
        if "missing_classic_bank:" not in str(error):
            raise
        require(source.read_bytes() == original, "Rejected native VSQX import modified its source file")
        installed = (await check.call("voicebanks"))["voices"]
        check.evidence("rejected_classic_import", {"fixture": str(source), "source_unchanged": True,
                                                  "voices": installed, "error": str(error)})
        raise Blocked(str(error)) from error
    identifier = imported["session_id"]
    tracks, actual = await vsqx_native_notes(check, identifier)
    require(actual == expected, "Native VSQX import changed note timing, lyrics, or phonemes", {"expected": expected, "actual": actual})
    is_v7 = (await check.call("vocaloid_features"))["product"] == "VOCALOID7"
    scope = {"scope": "track" if is_v7 else "part"}
    voices = [await check.edit(identifier, "voice.get", **scope, track_index=track["track_index"], part_index=part)
              for track in tracks if track["type"] in ("Midi", "MidiAi") for part in range(track["part_count"])]
    require(source.read_bytes() == original, "Native VSQX import modified its source file")
    if any(track["type"] == "Midi" for track in tracks):
        installed = (await check.call("voicebanks"))["voices"]
        available = [voice for voice in installed if voice["kind"] == "Dse" and voice["available_in_sequence"]]
        check.evidence("classic_requirements", {"tracks": tracks, "identities": voices, "available_dse": available,
                                                "imported_notes_verified": len(actual)})
        if not available:
            raise Blocked("missing_classic_bank: VSQX notes imported unchanged, but classic save/reopen requires an installed available Dse voicebank; no replacement was selected")
    sequence, path = await check.save(identifier, f"vsqx{version}-import")
    reopened = (await check.call("project_open", path=str(path)))["session_id"]
    saved = [note for track in sequence.get("tracks", []) for part in track.get("parts", []) for note in part.get("notes", [])]
    require(len(saved) == len(expected), "Saved VSQX import lost notes", len(saved))
    reopened_tracks, reopened_notes = await vsqx_native_notes(check, reopened)
    reopened_voices = [await check.edit(reopened, "voice.get", **scope, track_index=track["track_index"], part_index=part)
                       for track in reopened_tracks if track["type"] in ("Midi", "MidiAi") for part in range(track["part_count"])]
    require(reopened_voices == voices, "VSQX imported voice identities did not survive save/reopen")
    require(reopened_tracks == tracks and reopened_notes == expected,
            "VSQX imported tracks or notes did not survive save/reopen")
    await check.close(reopened)
    require(source.read_bytes() == original, "Native VSQX import modified its source file")
    check.evidence(f"vsqx{version}_import", {"source": str(source), "vpr": str(path), "notes": len(expected)})


@feature("interchange.vsqx3", "interchange", "project_import", "project_edit", "project_save", "project_open")
async def interchange_vsqx3(check: Acceptance) -> None:
    await verify_vsqx(check, check.arguments.vsqx3_fixture, 3)


@feature("interchange.vsqx4", "interchange", "project_import", "project_edit", "project_save", "project_open")
async def interchange_vsqx4(check: Acceptance) -> None:
    await verify_vsqx(check, check.arguments.vsqx_fixture, 4)


@feature("interchange.ppsf2", "interchange", "project_import", "project_edit", "project_save", "project_open")
async def interchange_ppsf2(check: Acceptance) -> None:
    fixture = check.arguments.ppsf_fixture
    if fixture is None or not fixture.is_file():
        raise Blocked("An actual PPSF V2 fixture must be supplied with --ppsf-fixture")
    source = fixture.resolve()
    original = source.read_bytes()
    require(original.startswith(b"PPSFI") and b"2.0.0" in original[:32], "Fixture is not a PPSF V2 project")
    imported = await check.call("project_import", path=str(source), prefer_ai=False)
    identifier = imported["session_id"]
    tracks, notes = await vsqx_native_notes(check, identifier)
    require(notes, "Native PPSF import contains no vocal notes")
    is_v7 = (await check.call("vocaloid_features"))["product"] == "VOCALOID7"
    scope = {"scope": "track" if is_v7 else "part"}
    voices = [(await check.edit(identifier, "voice.get", **scope, track_index=track["track_index"], part_index=part))
              for track in tracks if track["type"] in ("Midi", "MidiAi") for part in range(track["part_count"])]
    require(source.read_bytes() == original, "Native PPSF import modified its source file")
    if any(track["type"] == "Midi" for track in tracks):
        installed = (await check.call("voicebanks"))["voices"]
        available = [voice for voice in installed if voice["kind"] == "Dse" and voice["available_in_sequence"]]
        check.evidence("classic_requirements", {"tracks": tracks, "identities": voices, "available_dse": available})
        if not available:
            raise Blocked("missing_classic_bank: PPSF classic save/reopen requires an installed available Dse voicebank; no replacement was selected")
    sequence, path = await check.save(identifier, "ppsf2-import")
    saved = [note for track in sequence.get("tracks", []) for part in track.get("parts", []) for note in part.get("notes", [])]
    require(len(saved) == len(notes), "Saved PPSF import lost notes")
    reopened = (await check.call("project_open", path=str(path)))["session_id"]
    reopened_tracks, reopened_notes = await vsqx_native_notes(check, reopened)
    reopened_voices = [(await check.edit(reopened, "voice.get", **scope, track_index=track["track_index"], part_index=part))
                       for track in reopened_tracks if track["type"] in ("Midi", "MidiAi") for part in range(track["part_count"])]
    require(reopened_notes == notes, "PPSF imported note timing, pitch, lyrics or phonemes did not survive save/reopen")
    require(reopened_tracks == tracks and reopened_voices == voices,
            "PPSF traditional track type or voice did not survive save/reopen",
            {"before_tracks": tracks, "after_tracks": reopened_tracks,
             "before_voices": voices, "after_voices": reopened_voices})
    await check.close(reopened)
    require(source.read_bytes() == original, "Native PPSF import modified its source file")
    check.evidence("ppsf2_import", {"source": str(source), "vpr": str(path), "notes": len(notes)})


@feature("interchange.ppsf3", "interchange", "project_import", "project_edit", "project_save", "project_open")
async def interchange_ppsf3(check: Acceptance) -> None:
    fixture = check.arguments.ppsf3_fixture
    if fixture is None or not fixture.is_file():
        raise Blocked("An actual PPSF V3 fixture must be supplied with --ppsf3-fixture")
    source = fixture.resolve()
    original = source.read_bytes()
    with zipfile.ZipFile(source) as archive:
        project = json.loads(archive.read("ppsf.json"))["ppsf"]
    require(str(project["ppsf_ver"]).startswith("3."), "Fixture is not a PPSF V3 project")
    source_tracks = project["project"]["dvl_track"]
    source_notes = sum(len(track["events"]) for track in source_tracks)
    require(source_tracks and source_notes, "PPSF V3 fixture contains no NT tracks or notes")
    imported = await check.call("project_import", path=str(source), prefer_ai=False)
    identifier = imported["session_id"]
    tracks, notes = await vsqx_native_notes(check, identifier)
    require(len(tracks) == len(source_tracks) and len(notes) == source_notes,
            "Native PPSF V3 import changed the NT track or note count",
            {"source_tracks": len(source_tracks), "native_tracks": len(tracks),
             "source_notes": source_notes, "native_notes": len(notes)})
    # PPSF event positions are project-absolute; native note positions are
    # relative to the containing part. NT symbols and bank IDs belong to a
    # different engine and are deliberately not asserted as VOCALOID identity.
    for track, source_track in zip(tracks, source_tracks, strict=True):
        expected_notes = sorted((int(note["pos"]), int(note["length"]), int(note["note_number"]), note["lyric"])
                                for note in source_track["events"])
        actual_notes = []
        parts = (await check.edit(identifier, "part.list", track_index=track["track_index"]))["parts"]
        for part in parts:
            entries = (await check.edit(identifier, "note.list", track_index=track["track_index"],
                                        part_index=part["part_index"]))["notes"]
            actual_notes.extend((part["start_tick"] + note["start_tick"], note["duration_tick"],
                                 note["number"], note["lyric"]) for note in entries)
        require(sorted(actual_notes) == expected_notes, "PPSF V3 source/native note fields differ")
    tempo_source = project["project"]["tempo"]
    meter_source = project["project"]["meter"]
    source_tempos = [(int(item["tick"]), item["value"] / 10000.0)
                     for item in tempo_source.get("sequence", [])] if tempo_source["use_sequence"] else []
    if not any(tick == 0 for tick, _ in source_tempos):
        source_tempos.append((0, tempo_source["const"] / 10000.0))
    source_meters = [(int(item["measure"]), int(item["nume"]), int(item["denomi"]))
                     for item in meter_source.get("sequence", [])] if meter_source["use_sequence"] else []
    if not any(bar == 0 for bar, _, _ in source_meters):
        source_meters.append((0, int(meter_source["const"]["nume"]), int(meter_source["const"]["denomi"])))
    async def timing(session):
        tempos = (await check.edit(session, "tempo.list"))["tempos"]
        meters = (await check.edit(session, "time_signature.list"))["time_signatures"]
        return (sorted((item["start_tick"], item["bpm"]) for item in tempos),
                sorted((item["bar"], item["numerator"], item["denominator"]) for item in meters))
    native_tempos, native_meters = await timing(identifier)
    source_tempos.sort()
    require(len(native_tempos) == len(source_tempos) and all(
        actual_tick == expected_tick and abs(actual_bpm - expected_bpm) <= 0.0051
        for (actual_tick, actual_bpm), (expected_tick, expected_bpm) in zip(native_tempos, source_tempos)),
        "PPSF V3 source/native tempo differs", {"source": source_tempos, "native": native_tempos})
    require(native_meters == sorted(source_meters), "PPSF V3 source/native meter differs",
            {"source": source_meters, "native": native_meters})
    is_v7 = (await check.call("vocaloid_features"))["product"] == "VOCALOID7"
    scope = {"scope": "track" if is_v7 else "part"}
    async def identities(session, entries):
        return [await check.edit(session, "voice.get", **scope, track_index=track["track_index"], part_index=part)
                for track in entries if track["type"] in ("Midi", "MidiAi") for part in range(track["part_count"])]
    voices = await identities(identifier, tracks)
    _, path = await check.save(identifier, "ppsf3-import")
    reopened = (await check.call("project_open", path=str(path)))["session_id"]
    reopened_tracks, reopened_notes = await vsqx_native_notes(check, reopened)
    require(reopened_tracks == tracks and reopened_notes == notes, "PPSF V3 import did not survive save/reopen")
    require(await identities(reopened, reopened_tracks) == voices, "PPSF V3 native voice state changed on reopen")
    require(await timing(reopened) == (native_tempos, native_meters), "PPSF V3 tempo/meter did not survive reopen")
    await check.close(reopened)
    require(source.read_bytes() == original, "Native PPSF V3 import modified its source file")
    check.evidence("ppsf3_import", {"source": str(source), "vpr": str(path), "notes": len(notes),
                                   "tempos": native_tempos, "meters": native_meters,
                                   "not_compared": ["NT symbols versus VOCALOID phonemes", "NT singer versus VOCALOID voicebank identity"]})


@feature("interchange.native_midi", "interchange", "midi_write", "midi_read", "project_import", "project_export_midi", "project_save")
async def interchange_midi(check: Acceptance) -> None:
    written = await check.call("midi_write", output_name=check.output("input", ".mid"), title="Native import acceptance", bpm=120,
                               tracks=[{"name": "Vocal", "channel": 0, "program": 0,
                                        "notes": [{"start": index, "duration": 0.5, "pitch": pitch, "lyric": lyric}
                                                  for index, (pitch, lyric) in enumerate(((60, "a"), (62, "i"), (65, "u")))]}])
    source = Path(written["path"])
    original = source.read_bytes()
    snapshot = midi_snapshot(source)
    parsed = await check.call("midi_read", path=str(source))
    parsed_notes = [note for track in parsed["tracks"] for note in track["notes"]]
    require(len(parsed_notes) == len(snapshot["notes"]), "MIDI reader note count differs from parser")
    require(sorted((note["pitch"], note["start"], note["duration"]) for note in parsed_notes) == snapshot["notes"],
            "MIDI reader note timing/pitch differs from independent parser", parsed_notes)
    imported = await check.call("project_import", path=str(source), code_page=65001, prefer_ai=True)
    identifier = imported["session_id"]
    sequence, _ = await check.save(identifier, "imported-midi")
    persisted = [note for track in sequence["tracks"] for part in track.get("parts", []) for note in part.get("notes", [])]
    require(sorted(note["number"] for note in persisted) == [60, 62, 65], "Native MIDI import lost notes", persisted)
    exported = await check.call("project_export_midi", session_id=identifier, output_name=check.output("native", ".mid"), encoding="Utf8")
    require(exported["native"] and exported["format"] == "midi", "MIDI export did not use native route")
    destination = Path(exported["path"])
    actual = midi_snapshot(destination)
    require(actual["notes"] == snapshot["notes"], "Native MIDI note timing/pitch roundtrip differs", actual)
    require(actual["tempos"] and abs(actual["tempos"][0][1] - 120) < 0.01, "Native MIDI tempo lost")
    require(actual["meters"] and actual["meters"][0][1:] == (4, 4), "Native MIDI meter lost")
    require([text for _, text in actual["lyrics"]] == ["a", "i", "u"], "Native MIDI lyrics lost", actual)
    before = destination.read_bytes()
    await check.rejected("project_export_midi", "exist|overwrite", session_id=identifier, output_name=destination.name)
    require(destination.read_bytes() == before, "Rejected MIDI overwrite changed destination")
    await check.rejected("project_export_midi", "path|name|output|relative|travers", session_id=identifier,
                         output_name="../" + check.output("midi-escape", ".mid"))
    await check.call("project_export_midi", session_id=identifier, output_name=destination.name, overwrite=True)
    require(midi_snapshot(destination)["notes"] == actual["notes"], "Explicit MIDI overwrite corrupted notes")
    require(source.read_bytes() == original, "Native import modified the input MIDI")
    check.evidence("parsed_native_midi", actual)


@feature("interchange.clipboard", "interchange", "project_clipboard", "project_edit", "score_compose",
         "project_create", "project_save", "project_open")
async def interchange_clipboard(check: Acceptance) -> None:
    clipboard_ids: set[str] = set()

    async def clear_owned(clipboard_id: str) -> None:
        cleared = await check.call("project_clipboard", operation="clear", options={"clipboard_id": clipboard_id})
        require(cleared.get("native") is True and cleared["cleared"] is True
            and cleared["clipboard_id"] == clipboard_id, "Private clipboard did not clear", cleared)
        clipboard_ids.remove(clipboard_id)

    try:
        initial = await check.call("project_clipboard", operation="list")
        initial_ids = {entry["clipboard_id"] for entry in initial["clipboards"]}
        async with check.project(score=True) as source:
            scope = {"track_index": 0, "part_index": 0}
            original_notes = (await check.edit(source, "note.list", **scope))["notes"]
            copied = await check.call("project_clipboard", operation="copy", session_id=source,
                          options={"kind": "tracks", "indices": [0]})
            clipboard_ids.add(copied["clipboard_id"])
            require(copied.get("native") is True and copied["kind"] == "tracks" and copied["tracks"] == 1,
                "Native track clipboard was not populated", copied)
            require((await check.edit(source, "note.list", **scope))["notes"] == original_notes,
                "Native copy mutated the source notes")
            cut = await check.call("project_clipboard", operation="cut", session_id=source,
                       options={"kind": "notes", "indices": [1], **scope})
            clipboard_ids.add(cut["clipboard_id"])
            require(cut.get("native") is True and cut["kind"] == "notes" and cut["notes"] == 1,
                "Native note cut did not populate its clipboard", cut)
            remaining = (await check.edit(source, "note.list", **scope))["notes"]
            require([note["number"] for note in remaining] == [original_notes[0]["number"], original_notes[2]["number"]],
                "Native cut removed the wrong notes", remaining)
            listed = await check.call("project_clipboard", operation="list")
            require({entry["clipboard_id"] for entry in listed["clipboards"]} == initial_ids | clipboard_ids,
                "Private clipboard inventory does not match created snapshots", listed)
            await check.close(source)
        async with check.project() as target:
            pasted = await check.call("project_clipboard", operation="paste", session_id=target,
                          options={"clipboard_id": copied["clipboard_id"], "offset_tick": 480})
            require(pasted.get("native") is True and pasted["session_id"] == target and pasted["pasted"] == 1,
                "Track clipboard did not survive source close", pasted)
            parts = (await check.edit(target, "part.list", track_index=0))["parts"]
            require(len(parts) == 1 and parts[0]["start_tick"] == 480, "Clipboard track offset was not applied", parts)
            require((await check.edit(target, "note.list", **scope))["notes"] == original_notes,
                "Copied snapshot changed after the source was cut or closed")
            pasted_note = await check.call("project_clipboard", operation="paste", session_id=target,
                               options={"clipboard_id": cut["clipboard_id"], "offset_tick": 1920, **scope})
            require(pasted_note.get("native") is True and pasted_note["pasted"] == 1, "Cut note did not paste", pasted_note)
            expected = original_notes + [{**original_notes[1], "note_index": len(original_notes),
                             "start_tick": original_notes[1]["start_tick"] + 1920}]
            actual = (await check.edit(target, "note.list", **scope))["notes"]
            require(actual == expected, "Private note clipboard changed timing, pitch or expression", actual)
            for clipboard_id in sorted(clipboard_ids.copy()):
                await clear_owned(clipboard_id)
            listed = await check.call("project_clipboard", operation="list")
            require({entry["clipboard_id"] for entry in listed["clipboards"]} == initial_ids,
                "Cleared private clipboards remain listed", listed)
            await check.rejected("project_clipboard", "clipboard_id|unknown", operation="paste", session_id=target,
                         options={"clipboard_id": copied["clipboard_id"]})
            _, path = await check.save(target, "clipboard-roundtrip")
            reopened = (await check.call("project_open", path=str(path)))["session_id"]
            require((await check.edit(reopened, "note.list", **scope))["notes"] == expected,
                "Clipboard contents did not survive clear and native save/reopen")
            require((await check.edit(reopened, "part.list", track_index=0))["parts"][0]["start_tick"] == 480,
                "Clipboard part offset did not persist")
            await check.close(reopened)
            check.evidence("native_clipboard_roundtrip", {"track_clipboard": copied["clipboard_id"],
                       "note_clipboard": cut["clipboard_id"], "vpr": str(path), "note_count": len(expected)})
    finally:
        for clipboard_id in sorted(clipboard_ids.copy()):
            await clear_owned(clipboard_id)


@feature("interchange.vpr_tools", "interchange", "score_compose", "score_inspect", "score_summary", "score_patch",
         "score_replace_notes", "score_tempo", "score_curve", "project_edit")
async def interchange_vpr(check: Acceptance) -> None:
    async with check.project(score=True) as identifier:
        dynamics = next(entry for entry in (await check.edit(identifier, "controller.types", track_index=0, part_index=0))["types"]
                        if entry["type"] == "Dynamics")
        await check.edit(identifier, "controller.set", track_index=0, part_index=0, type="Dynamics",
                         points=[{"tick": 0, "value": dynamics["default_value"]}], replace=True)
        _, source = await check.save(identifier, "vpr-original")
        original = source.read_bytes()
        sequence, members = read_vpr(source)
        require(await check.call("score_inspect", path=str(source), pointer="/title") == sequence["title"], "JSON pointer inspection mismatch")
        summary = await check.call("score_summary", path=str(source))
        require(summary["note_count"] == 3, "Score summary note count mismatch")
        patched = await check.call("score_patch", path=str(source), output_name=check.output("patched"),
                                   operations=[{"op": "add", "path": "/acceptanceUnknown", "value": {"retained": 17}},
                                               {"op": "replace", "path": "/title", "value": "Patched title"}])
        notes = [{"start": 0, "duration": 1, "pitch": 69, "lyric": "\u3042", "phoneme": "a", "lang_id": 0}]
        replaced = await check.call("score_replace_notes", path=patched["path"], output_name=check.output("replaced"), notes=notes)
        tempo = await check.call("score_tempo", path=replaced["path"], output_name=check.output("tempo-copy"),
                                 events=[{"start": 0, "bpm": 110}, {"start": 4, "bpm": 130}])
        revised, revised_members = read_vpr(tempo["path"])
        require(revised["acceptanceUnknown"] == {"retained": 17}, "Unknown VPR field was discarded")
        require(revised["tracks"][0]["parts"][0]["notes"][0]["number"] == 69, "Structured note replace failed")
        require([entry["value"] for entry in revised["masterTrack"]["tempo"]["events"]] == [11000, 13000], "Structured tempo edit failed")
        for name, payload in members.items():
            if name != "Project/sequence.json":
                require(revised_members.get(name) == payload, "Embedded VPR resource changed", name)
        lanes = revised["tracks"][0]["parts"][0].get("controllers", [])
        lane = next((entry for entry in lanes if entry.get("events")), None)
        require(lane is not None, "Native controller did not persist an editable VPR lane")
        curve = await check.call("score_curve", path=tempo["path"], output_name=check.output("curve-copy"),
                                 controller=lane["name"], events=[{"start": 0, "value": lane["events"][0]["value"]}])
        curve_data, _ = read_vpr(curve["path"])
        require(any(entry["name"] == lane["name"] and len(entry["events"]) == 1
                    for entry in curve_data["tracks"][0]["parts"][0]["controllers"]), "Structured curve edit failed")
        require(source.read_bytes() == original, "Structured VPR tools modified original input")
        await check.rejected("score_replace_notes", "overlap|monophonic", path=str(source), output_name=check.output("invalid-notes"),
                             notes=[{"start": 0, "duration": 2, "pitch": 60}, {"start": 1, "duration": 1, "pitch": 62}])


def read_audio(path: str | Path, *, nonzero: bool = True, max_seconds: int = 30) -> tuple[dict[str, Any], Any]:
    import numpy as np
    import soundfile as sf
    source = Path(path)
    with sf.SoundFile(source) as audio:
        require(audio.format in ("WAV", "WAVEX"), "Expected native WAV output", audio.format)
        require(0 < audio.frames <= audio.samplerate * max_seconds,
            f"Audio must be nonempty and bounded to {max_seconds} seconds", audio.frames)
        require(audio.channels in (1, 2), "Expected mono or stereo WAV", audio.channels)
        samples = audio.read(dtype="float64", always_2d=True)
        metadata = {"frames": audio.frames, "sample_rate": audio.samplerate, "channels": audio.channels,
                    "subtype": audio.subtype, "duration_seconds": audio.frames / audio.samplerate}
    require(np.isfinite(samples).all(), "Audio contains nonfinite samples")
    metadata.update(peak=float(np.max(np.abs(samples))), rms=float(np.sqrt(np.mean(samples * samples))))
    if nonzero:
        require(metadata["peak"] > 0 and metadata["rms"] > 0, "Native WAV is silent")
    return metadata, samples


def compare_audio_reports(native: dict[str, Any], actual: dict[str, Any]) -> None:
    for field in ("frames", "sample_rate", "channels"):
        require(native[field] == actual[field], "Native WAV report differs from independent decoder: " + field)
    require(abs(native["duration_seconds"] - actual["duration_seconds"]) < 1 / actual["sample_rate"], "WAV duration report mismatch")


@feature("synthesis.robot_voice", "synthesis", "project_render_part", "project_audio", "project_edit", "score_compose", "project_save", "project_open", "vocaloid_features")
async def synthesis_robot_voice(check: Acceptance) -> None:
    import numpy as np
    seed = await check.call("score_compose", output_name=check.output("robot-seed"), title="Robot voice acceptance", bpm=120,
                notes=[{"start": index, "duration": 0.6, "pitch": pitch, "lyric": "\u3042", "phoneme": "a", "lang_id": 0}
                   for index, pitch in enumerate((60, 64, 67))])
    identifier = seed["native_session"]["session_id"]
    selected = {"track_index": 0, "part_index": 0}
    is_v7 = (await check.call("vocaloid_features"))["product"] == "VOCALOID7"
    settings_scope = {**selected, **({"scope": "track"} if is_v7 else {})}
    baseline = await check.call("project_render_part", session_id=identifier, output_name=check.output("robot-baseline", ".wav"), **selected)
    baseline_metadata, baseline_pcm = read_audio(baseline["path"])
    changed = await check.edit(identifier, "performance.set", **settings_scope, robot_mode="Hard", bypass={"RobotVoice": False})
    require(changed["robot"]["mode"] == "Hard" and not next(item for item in changed["bypass"]
        if item["effect"] == "RobotVoice")["bypassed"], "Robot Voice was not enabled", changed)
    _, path = await check.save(identifier, "robot-voice")
    await check.close(identifier, discard=False)
    reopened = (await check.call("project_open", path=str(path)))["session_id"]
    restored = await check.edit(reopened, "performance.get", **settings_scope)
    require(restored["robot"]["mode"] == "Hard" and not next(item for item in restored["bypass"]
        if item["effect"] == "RobotVoice")["bypassed"], "Robot Voice settings did not survive reopen", restored)
    rendered = await check.call("project_render_part", session_id=reopened, output_name=check.output("robot-enabled", ".wav"), **selected)
    metadata, samples = read_audio(rendered["path"])
    overlap = min(len(samples), len(baseline_pcm))
    require(samples.shape[1] == baseline_pcm.shape[1] and overlap > 0, "Robot output has an incompatible sample layout")
    difference = float(np.sqrt(np.mean((samples[:overlap] - baseline_pcm[:overlap]) ** 2)))
    require(difference > baseline_metadata["rms"] * 0.01, "Enabled Robot Voice produced unchanged audio", difference)
    await check.close(reopened)
    mixed_session = (await check.call("project_open", path=str(path)))["session_id"]
    mixed = await check.audio(mixed_session, "mixdown", output_name=check.output("robot-mix", ".wav"),
                              sample_rate=44100, channels=1, bits_per_sample=16, bypass_effects=True)
    mixed_metadata, _ = read_audio(mixed["path"])
    await check.close(mixed_session)
    check.evidence("robot_voice_audio", {"baseline": baseline["path"], "rendered": rendered["path"],
                                         "mix": mixed["path"], "mix_audio": mixed_metadata,
                                         "vpr": str(path), "rms_difference": difference, "audio": metadata})


@feature("synthesis.clean_render", "synthesis", "project_render_part", "score_compose", "audio_inspect", "project_save", "project_open")
async def synthesis_render(check: Acceptance) -> None:
    path = await check.render_fixture()
    actual, _ = read_audio(path)
    reported = await check.call("audio_inspect", path=str(path))
    compare_audio_reports(reported, actual)
    require(abs(reported["peak"] - actual["peak"]) < 1e-10 and abs(reported["rms"] - actual["rms"]) < 1e-10,
            "Reported amplitude statistics disagree with sample arrays")
    check.evidence("decoded_native_output", {"path": str(path), **actual})


@feature("synthesis.guards", "synthesis", "project_render_part", "project_create", "score_compose")
async def synthesis_guards(check: Acceptance) -> None:
    async with check.project() as empty:
        await check.rejected("project_render_part", "track|part|range|exist", session_id=empty,
                             output_name=check.output("empty-render", ".wav"))
    async with check.project(score=True) as identifier:
        fixture = await check.render_fixture()
        original = fixture.read_bytes()
        await check.rejected("project_render_part", "exist|overwrite", session_id=identifier, output_name=fixture.name)
        require(fixture.read_bytes() == original, "Rejected render overwrote an existing WAV")
        await check.rejected("project_render_part", "path|output|relative|travers|name", session_id=identifier,
                             output_name="../" + check.output("escape-render", ".wav"))


@feature("synthesis.blank_authoring", "synthesis", "project_create", "project_edit", "voicebanks",
         "project_save", "project_open", "project_render_part", "vocaloid_features")
async def synthesis_blank_authoring(check: Acceptance) -> None:
    async with check.project() as identifier:
        is_v7 = (await check.call("vocaloid_features"))["product"] == "VOCALOID7"
        require((await check.edit(identifier, "track.list"))["tracks"] == [], "Native new project was not blank")
        voices = (await check.call("voicebanks"))["voices"]
        voice = next((entry for entry in voices if entry["name"] == "asa" and entry["kind"] == "Dnn"
                  and entry["synthesizable_version"] and 0 in entry["lang_ids"]), None)
        if voice is None:
            raise Blocked("The installed native asa voice is required for the blank-authoring regression")
        created_track = await check.edit(identifier, "track.create", name="Blank native vocal")
        require(created_track["type"] == "MidiAi", "The default vocal track must use the AI engine", created_track)
        track = created_track["track_index"]
        created = await check.edit(identifier, "part.create", track_index=track, start_tick=0,
                       duration_tick=1920, name="New native notes")
        require(created["note_count"] == 0, "New native part already contains prototype notes", created)
        selected = {"track_index": track, "part_index": created["part_index"]}
        settings_scope = {**selected, **({"scope": "track"} if is_v7 else {})}
        assigned = await check.edit(identifier, "voice.set", **settings_scope, ai_voice_bank_id=voice["comp_id"])
        require(assigned["ai_voice_bank_id"] == voice["comp_id"], "New part did not retain the explicit voice", assigned)
        first = await check.edit(identifier, "note.add", **selected, start_tick=0, duration_tick=480,
                     number=60, lyric="\u3042", phonemes="a", lang_id=0)
        inferred = await check.edit(identifier, "note.add", **selected, start_tick=960, duration_tick=480,
                        number=64, lyric="\u3044")
        require(first["lang_id"] == 0 and first["phonemes"] == "a" and first["is_valid_phonemes"],
            "First native note lost explicit language or phonemes", first)
        require(inferred["lang_id"] == 0 and inferred["phonemes"] == "i" and inferred["is_valid_phonemes"],
            "Omitted language/phonemes did not use the assigned voice and native G2PA", inferred)
        fresh = await check.edit(identifier, "part.create", track_index=track, start_tick=3840,
                     duration_tick=1920, name="Empty-part language inference")
        fresh_selected = {"track_index": track, "part_index": fresh["part_index"]}
        await check.edit(identifier, "voice.set", **fresh_selected, **({"scope": "track"} if is_v7 else {}),
                 ai_voice_bank_id=voice["comp_id"])
        fresh_note = await check.edit(identifier, "note.add", **fresh_selected, start_tick=0, duration_tick=480,
                          number=67, lyric="\u3042", phonemes="a")
        require(fresh["note_count"] == 0 and fresh_note["lang_id"] == 0 and fresh_note["is_valid_phonemes"],
            "An empty native part could not infer the explicitly assigned voice language", fresh_note)
        notes = (await check.edit(identifier, "note.list", **selected))["notes"]
        sequence, path = await check.save(identifier, "blank-authored")
        require(any(entry["compID"] == voice["comp_id"] for entry in sequence.get("voices", [])),
            "Blank-authored VPR did not register its assigned native voice", sequence.get("voices"))
        saved_parts = sequence["tracks"][track]["parts"]
        saved_voice = sequence["tracks"][track]["voice"] if is_v7 else saved_parts[selected["part_index"]]["aiVoice"]
        require(saved_voice["compID"] == voice["comp_id"]
            and [note["phoneme"] for note in saved_parts[selected["part_index"]]["notes"]] == ["a", "i"],
            "Blank-authored VPR lost native voice or generated phonemes", saved_parts)
        await check.close(identifier, discard=False)
        opened = await check.call("project_open", path=str(path))
        reopened = opened["session_id"]
        require(opened["dirty"] is False, "Blank-authored VPR did not reopen cleanly", opened)
        readback = (await check.edit(reopened, "note.list", **selected))["notes"]
        require(readback == notes, "Blank-authored notes did not survive native save/reopen", readback)
        fresh_readback = (await check.edit(reopened, "note.list", **fresh_selected))["notes"]
        require(len(fresh_readback) == 1 and fresh_readback[0]["lang_id"] == 0
            and fresh_readback[0]["phonemes"] == "a", "Empty-part inferred language did not persist", fresh_readback)
        rendered = await check.call("project_render_part", session_id=reopened, **selected,
                        output_name=check.output("blank-singing", ".wav"))
        require(rendered.get("native") is True, "Blank-authored vocal did not use native synthesis", rendered)
        actual, _ = read_audio(rendered["path"])
        compare_audio_reports(rendered["audio"], actual)
        check.evidence("blank_native_authoring", {"voice_id": voice["comp_id"], "vpr": str(path),
                   "wav": rendered["path"], "notes": readback, "audio": actual})
        await check.close(reopened)


@feature("audio.assets", "audio", "project_audio", "project_save", "project_open", "audio_inspect")
async def audio_assets(check: Acceptance) -> None:
    import numpy as np
    source = await check.audio_input()
    original = source.read_bytes()
    source_metadata, source_pcm = read_audio(source)
    async with check.project() as identifier:
        inspected = await check.audio(identifier, "inspect_audio", path=str(source))
        compare_audio_reports(inspected, source_metadata)
        imported = await check.audio(identifier, "import_audio", path=str(source), name="Native singing input", position_tick=0)
        require(imported["name"] == "Native singing input" and imported["position_tick"] == 0
            and imported["duration_seconds"] > 0 and imported["begin_tick"] == 0 and imported["end_tick"] > 0,
            "Native audio import metadata/region mismatch", imported)
        tick_seconds = 60 / (120 * 480)
        duration_tolerance = tick_seconds + 1 / source_metadata["sample_rate"]
        require(abs(imported["duration_seconds"] - source_metadata["duration_seconds"]) <= duration_tolerance,
            "Native audio duration differs from source beyond tick/sample rounding", imported)
        selected = {"track_index": imported["track_index"], "part_index": imported["part_index"]}
        for original_asset in (True, False):
            exported = await check.audio(identifier, "export_audio", **selected, original=original_asset,
                                         output_name=check.output("asset", ".wav"))
            actual, samples = read_audio(exported["path"])
            compare_audio_reports(exported, actual)
            require(samples.shape == source_pcm.shape and np.allclose(samples, source_pcm, atol=2 / 32768, rtol=0),
                    "Exported native asset differs from imported waveform")
        width = imported["end_tick"] - imported["begin_tick"]
        require(width > 4, "Imported audio region is too short")
        new_end = imported["begin_tick"] + width * 3 // 4
        edited = await check.audio(identifier, "edit_audio", **selected, position_tick=240,
                                   end_tick=new_end, name="Trimmed native input")
        require(edited["position_tick"] == 240 and edited["end_tick"] == new_end and edited["name"] == "Trimmed native input",
                "Native audio edit readback mismatch", edited)
        require(edited["duration_seconds"] < imported["duration_seconds"], "Region trim did not shorten native duration")
        unchanged = await check.audio(identifier, "edit_audio", **selected, position_tick=240,
                          end_tick=new_end, name="Trimmed native input")
        require(unchanged["position_tick"] == edited["position_tick"] and unchanged["end_tick"] == edited["end_tick"],
            "Repeating an unchanged audio edit did not preserve state")
        _, path = await check.save(identifier, "audio-assets")
        reopened = (await check.call("project_open", path=str(path)))["session_id"]
        export = await check.audio(reopened, "export_audio", **selected, original=True, output_name=check.output("reopened-asset", ".wav"))
        _, samples = read_audio(export["path"])
        require(samples.shape == source_pcm.shape and np.allclose(samples, source_pcm, atol=2 / 32768, rtol=0), "Saved VPR lost original embedded audio")
        await check.close(reopened)
    require(source.read_bytes() == original, "Native import/edit/export modified original WAV")


def register_offline(action: str) -> None:
    @feature("audio." + action, "audio", "project_audio", "vocaloid_operations", "vocaloid_features")
    async def offline(check: Acceptance) -> None:
        import numpy as np
        source = await check.audio_input()
        original = source.read_bytes()
        before, before_pcm = read_audio(source)
        options: dict[str, Any] = {}
        if action == "time_stretch":
            options["ratio"] = 1.25
        elif action == "pitch_shift":
            options["pitch_cents"] = 300
        async with check.project() as identifier:
            catalog = await check.call("vocaloid_operations", domain="audio", operation="process_audio")
            is_v7 = catalog["product"] == "VOCALOID7"
            if action == "reverse":
                discovery = await check.call("vocaloid_features", feature="reverse")
                feature = discovery["features"]["reverse"]
                require(feature["support"] == "operation_catalog" and any(
                    item["arguments"].get("operation") == "process_audio"
                    and item["arguments"].get("options", {}).get("action") == "reverse"
                    for item in feature["write_calls"]), "Reverse capability is not discoverable", feature)
                require("reverse" in catalog["domains"]["audio"]["operations"][0]["features"],
                        "Reverse operation is not linked to its feature", catalog)
                if is_v7:
                    limitation = catalog["domains"]["audio"]["operations"][0]["action_limitations"]["reverse"]
                    require("smpl loops" in limitation and "cue points" in limitation and "ltxt regions" in limitation
                        and "fractional loops" in limitation,
                        "Reverse discovery does not describe sampler metadata handling", limitation)
            if action == "normalize":
                support = catalog["domains"]["audio"]["operations"][0]["action_support"]
                require(support["voice_change"] == ("unsupported" if is_v7 else "see_contract_and_live_inspect")
                        and all(support[name] == "see_contract_and_live_inspect"
                                for name in ("reverse", "normalize", "time_stretch", "pitch_shift")),
                        "Audio action support does not match the selected product", support)
                effects = await check.call("vocaloid_operations", domain="audio", operation="set_effect")
                require(effects["domains"]["audio"]["operations"][0]["scope_support"]["part"]
                        == ("unsupported" if is_v7 else "see_contract_and_live_inspect"),
                        "Audio effect scope support does not match the selected product", effects)
                if is_v7:
                    for unsupported in ("voice_change",):
                        await check.rejected("project_audio", "VOCALOID7.*(removed|unavailable)", session_id=identifier,
                                             operation="process_audio", options={"action": unsupported, "path": str(source),
                                             "output_name": check.output("unsupported-" + unsupported, ".wav")})
            result = await check.audio(identifier, "process_audio", action=action, path=str(source),
                                       output_name=check.output(action, ".wav"), expected_native=not (is_v7 and action == "reverse"), **options)
            expected_backend = "bridge.pcm_frame_reverse" if is_v7 and action == "reverse" else "WOR." + action
            require(result["backend"] == expected_backend, "Offline renderer used an unexpected backend", result)
            if is_v7 and action == "reverse":
                require("time references are not reversed" in result["metadata_warning"],
                        "Reverse receipt did not disclose unchanged time metadata", result)
            actual, samples = read_audio(result["path"])
            compare_audio_reports(result, actual)
            require(actual["sample_rate"] == before["sample_rate"] and actual["channels"] == before["channels"],
                    "Offline renderer unexpectedly changed sample format")
            if action == "time_stretch":
                expected = before["duration_seconds"] * options["ratio"]
                require(abs(actual["duration_seconds"] - expected) < max(0.12, expected * 0.08),
                    "Native bpmMag did not produce the expected duration", {"expected": expected, "actual": actual})
                check.evidence("native_time_stretch", {"bpm_mag": options["ratio"], "expected_duration_seconds": expected,
                           "actual_duration_ratio": actual["duration_seconds"] / before["duration_seconds"]})
            else:
                require(abs(actual["duration_seconds"] - before["duration_seconds"]) < 0.06,
                        "Length-preserving offline operation changed duration", actual)
                if action == "reverse":
                    require(samples.shape == before_pcm.shape and np.allclose(samples, before_pcm[::-1], atol=2 / 32768, rtol=0),
                            "Reverse WAV is not frame-reversed source PCM")
                    if is_v7:
                        import soundfile as sf
                        import struct
                        stereo = np.array([[32767, -32768], [-12345, 23456], [0, 1], [23, -45]], dtype=np.int16)
                        long_stereo = ((np.arange(80006, dtype=np.int32) % 65536) - 32768).astype(np.int16).reshape(-1, 2)
                        samples_to_check = [
                            ("stereo", stereo, 44100, "WAV", "PCM_16"),
                            ("long", long_stereo, 48000, "WAV", "PCM_16"),
                            ("pcm24", np.array([[0.5, -0.25, 0.125], [-0.75, 0.0, 0.25]]), 48000, "WAVEX", "PCM_24"),
                            ("float", np.array([[0.125, -0.5], [0.75, 0.25], [-0.1, 0.1]]), 96000, "WAV", "FLOAT"),
                            ("float-ext", np.array([[0.125, -0.5], [0.75, 0.25], [-0.1, 0.1]]), 48000, "WAVEX", "FLOAT"),
                            ("pcm8", np.array([[-0.5], [0.0], [0.5]]), 22050, "WAV", "PCM_U8"),
                        ]
                        for label, input_samples, sample_rate, format_name, subtype in samples_to_check:
                            sample_path = ROOT / "output" / check.output("reverse-" + label, ".wav")
                            sf.write(sample_path, input_samples, sample_rate, format=format_name, subtype=subtype)
                            original_bytes = sample_path.read_bytes()
                            expected_samples, _ = sf.read(sample_path, dtype="float64", always_2d=True)
                            sample_result = await check.audio(identifier, "process_audio", action="reverse", path=str(sample_path),
                                                              output_name=check.output("reversed-" + label, ".wav"), expected_native=False)
                            reversed_samples, rate = sf.read(sample_result["path"], dtype="float64", always_2d=True)
                            output_info = sf.info(sample_result["path"])
                            require(rate == sample_rate and output_info.subtype == subtype
                                    and np.array_equal(reversed_samples, expected_samples[::-1])
                                    and sample_path.read_bytes() == original_bytes,
                                    "WAV frame reversal changed samples, format, or source", label)
                        payload = stereo.astype("<i2", copy=False).tobytes()
                        reversed_payload = stereo[::-1].astype("<i2", copy=False).tobytes()
                        fmt = struct.pack("<HHIIHH", 1, 2, 44100, 176400, 4, 16)
                        def chunk(identifier, data):
                            return identifier + struct.pack("<I", len(data)) + data + (b"\x00" if len(data) % 2 else b"")
                        chunks = chunk(b"fmt ", fmt) + chunk(b"data", payload[:8]) + chunk(b"JUNK", b"tag") + chunk(b"data", payload[8:])
                        multi_path = ROOT / "output" / check.output("reverse-multiple-data", ".wav")
                        multi_path.write_bytes(b"RIFF" + struct.pack("<I", len(chunks) + 4) + b"WAVE" + chunks)
                        multi_original = multi_path.read_bytes()
                        multi_result = await check.audio(identifier, "process_audio", action="reverse", path=str(multi_path),
                                                         output_name=check.output("multiple-data-reverse", ".wav"), expected_native=False)
                        expected_chunks = chunk(b"fmt ", fmt) + chunk(b"data", reversed_payload) + chunk(b"JUNK", b"tag")
                        expected_file = b"RIFF" + struct.pack("<I", len(expected_chunks) + 4) + b"WAVE" + expected_chunks
                        decoded, rate = sf.read(multi_result["path"], dtype="int16", always_2d=True)
                        require(Path(multi_result["path"]).read_bytes() == expected_file and multi_path.read_bytes() == multi_original
                            and rate == 44100 and np.array_equal(decoded, stereo[::-1]),
                            "Multichunk reversal produced an unreadable WAV or changed metadata or frame order")
                        sampler_header = struct.pack("<9I", 0, 0, 22675, 60, 0, 0, 0, 3, 0)
                        sampler_loops = [
                            (11, 0, 0, 1, 0, 0),
                            (12, 2, 1, 1, 0, 2),
                            (13, 0, 1, 2, 1, 0),
                        ]
                        sampler_data = sampler_header + b"".join(struct.pack("<6I", *loop) for loop in sampler_loops)
                        sampler_chunks = chunk(b"fmt ", fmt) + chunk(b"data", payload) + chunk(b"smpl", sampler_data)
                        sampler_path = ROOT / "output" / check.output("reverse-sampler", ".wav")
                        sampler_path.write_bytes(b"RIFF" + struct.pack("<I", len(sampler_chunks) + 4) + b"WAVE" + sampler_chunks)
                        sampler_original = sampler_path.read_bytes()
                        sampler_result = await check.audio(identifier, "process_audio", action="reverse", path=str(sampler_path),
                                                           output_name=check.output("reversed-sampler", ".wav"), expected_native=False)
                        expected_loops = [(11, 0, 2, 3, 0, 0), (12, 2, 2, 2, 0, 2), sampler_loops[2]]
                        expected_sampler_data = sampler_header + b"".join(struct.pack("<6I", *loop) for loop in expected_loops)
                        expected_sampler_chunks = chunk(b"fmt ", fmt) + chunk(b"data", reversed_payload) + chunk(b"smpl", expected_sampler_data)
                        expected_sampler_file = b"RIFF" + struct.pack("<I", len(expected_sampler_chunks) + 4) + b"WAVE" + expected_sampler_chunks
                        decoded_sampler, sampler_rate = sf.read(sampler_result["path"], dtype="int16", always_2d=True)
                        require(Path(sampler_result["path"]).read_bytes() == expected_sampler_file
                            and sampler_path.read_bytes() == sampler_original and sampler_rate == 44100
                            and np.array_equal(decoded_sampler, stereo[::-1])
                            and sampler_result.get("sampler_loops_reversed") == 2
                            and sampler_result.get("sampler_loops_unchanged") == 1
                            and sampler_result.get("sampler_chunks_unchanged") == 0,
                            "Sampler loop positions or unchanged-loop receipt are incorrect", sampler_result)
                        extra_sampler_data = struct.pack("<9I", 0, 0, 22675, 60, 0, 0, 0, 1, 3)
                        extra_sampler_data += struct.pack("<6I", *sampler_loops[0]) + b"ext"
                        extra_chunks = chunk(b"fmt ", fmt) + chunk(b"data", payload) + chunk(b"smpl", extra_sampler_data)
                        extra_path = ROOT / "output" / check.output("reverse-sampler-extra", ".wav")
                        extra_path.write_bytes(b"RIFF" + struct.pack("<I", len(extra_chunks) + 4) + b"WAVE" + extra_chunks)
                        extra_result = await check.audio(identifier, "process_audio", action="reverse", path=str(extra_path),
                                                         output_name=check.output("reversed-sampler-extra", ".wav"), expected_native=False)
                        expected_extra_chunks = chunk(b"fmt ", fmt) + chunk(b"data", reversed_payload) + chunk(b"smpl", extra_sampler_data)
                        expected_extra_file = b"RIFF" + struct.pack("<I", len(expected_extra_chunks) + 4) + b"WAVE" + expected_extra_chunks
                        require(Path(extra_result["path"]).read_bytes() == expected_extra_file
                            and extra_result.get("sampler_loops_reversed") == 0
                            and extra_result.get("sampler_loops_unchanged") == 1
                            and extra_result.get("sampler_chunks_unchanged") == 1,
                            "Sampler-specific metadata or its unchanged-loop receipt changed", extra_result)
                        cue_points = [(101, 0, b"data", 0, 0, 0), (102, 1, b"data", 0, 0, 1),
                                      (103, 1, b"data", 0, 0, 2)]
                        cue_data = struct.pack("<I", len(cue_points)) + b"".join(
                            struct.pack("<II4sIII", *point) for point in cue_points)
                        cue_chunks = chunk(b"fmt ", fmt) + chunk(b"data", payload) + chunk(b"cue ", cue_data)
                        cue_path = ROOT / "output" / check.output("reverse-cue", ".wav")
                        cue_path.write_bytes(b"RIFF" + struct.pack("<I", len(cue_chunks) + 4) + b"WAVE" + cue_chunks)
                        cue_original = cue_path.read_bytes()
                        cue_result = await check.audio(identifier, "process_audio", action="reverse", path=str(cue_path),
                                                       output_name=check.output("reversed-cue", ".wav"), expected_native=False)
                        expected_points = [(101, 3, b"data", 0, 0, 3), (102, 2, b"data", 0, 0, 2), cue_points[2]]
                        expected_cue_data = struct.pack("<I", len(expected_points)) + b"".join(
                            struct.pack("<II4sIII", *point) for point in expected_points)
                        expected_cue_chunks = chunk(b"fmt ", fmt) + chunk(b"data", reversed_payload) + chunk(b"cue ", expected_cue_data)
                        expected_cue_file = b"RIFF" + struct.pack("<I", len(expected_cue_chunks) + 4) + b"WAVE" + expected_cue_chunks
                        require(Path(cue_result["path"]).read_bytes() == expected_cue_file and cue_path.read_bytes() == cue_original
                            and cue_result.get("cue_points_reversed") == 2 and cue_result.get("cue_points_unchanged") == 1
                            and cue_result.get("cue_chunks_unchanged") == 0,
                            "Simple cue positions or unchanged-point receipt are incorrect", cue_result)
                        playlist_data = struct.pack("<IIII", 1, cue_points[0][0], 2, 0)
                        playlist_chunks = cue_chunks + chunk(b"plst", playlist_data)
                        playlist_path = ROOT / "output" / check.output("reverse-cue-playlist", ".wav")
                        playlist_path.write_bytes(b"RIFF" + struct.pack("<I", len(playlist_chunks) + 4) + b"WAVE" + playlist_chunks)
                        playlist_result = await check.audio(identifier, "process_audio", action="reverse", path=str(playlist_path),
                                                            output_name=check.output("reversed-cue-playlist", ".wav"), expected_native=False)
                        expected_playlist_chunks = (chunk(b"fmt ", fmt) + chunk(b"data", reversed_payload)
                                                    + chunk(b"cue ", cue_data) + chunk(b"plst", playlist_data))
                        expected_playlist_file = b"RIFF" + struct.pack("<I", len(expected_playlist_chunks) + 4) + b"WAVE" + expected_playlist_chunks
                        require(Path(playlist_result["path"]).read_bytes() == expected_playlist_file
                            and playlist_result.get("cue_points_reversed") == 0
                            and playlist_result.get("cue_points_unchanged") == len(cue_points)
                            and playlist_result.get("cue_chunks_unchanged") == 1,
                            "Playlist-linked cue metadata or its unchanged-point receipt changed", playlist_result)
                        associated_data = (b"adtl" + chunk(b"labl", struct.pack("<I", cue_points[0][0]) + b"cue\x00")
                                           + chunk(b"note", struct.pack("<I", cue_points[1][0]) + b"memo\x00"))
                        labelled_chunks = cue_chunks + chunk(b"LIST", associated_data)
                        labelled_path = ROOT / "output" / check.output("reverse-cue-labelled", ".wav")
                        labelled_path.write_bytes(b"RIFF" + struct.pack("<I", len(labelled_chunks) + 4) + b"WAVE" + labelled_chunks)
                        labelled_result = await check.audio(identifier, "process_audio", action="reverse", path=str(labelled_path),
                                                            output_name=check.output("reversed-cue-labelled", ".wav"), expected_native=False)
                        expected_labelled_chunks = (chunk(b"fmt ", fmt) + chunk(b"data", reversed_payload)
                                                    + chunk(b"cue ", expected_cue_data) + chunk(b"LIST", associated_data))
                        expected_labelled_file = b"RIFF" + struct.pack("<I", len(expected_labelled_chunks) + 4) + b"WAVE" + expected_labelled_chunks
                        require(Path(labelled_result["path"]).read_bytes() == expected_labelled_file
                            and labelled_result.get("cue_points_reversed") == 2
                            and labelled_result.get("cue_points_unchanged") == 1
                            and labelled_result.get("cue_chunks_unchanged") == 0,
                            "Labelled cue positions or unchanged-point receipt are incorrect", labelled_result)
                        region_data = b"adtl" + chunk(b"ltxt", struct.pack("<II4sHHHH", cue_points[0][0], 2, b"rgn ", 0, 0, 0, 0) + b"region\x00")
                        region_chunks = cue_chunks + chunk(b"LIST", region_data)
                        region_path = ROOT / "output" / check.output("reverse-cue-region", ".wav")
                        region_path.write_bytes(b"RIFF" + struct.pack("<I", len(region_chunks) + 4) + b"WAVE" + region_chunks)
                        region_result = await check.audio(identifier, "process_audio", action="reverse", path=str(region_path),
                                                          output_name=check.output("reversed-cue-region", ".wav"), expected_native=False)
                        expected_region_points = [(101, 2, b"data", 0, 0, 2), expected_points[1], cue_points[2]]
                        expected_region_cues = struct.pack("<I", len(expected_region_points)) + b"".join(
                            struct.pack("<II4sIII", *point) for point in expected_region_points)
                        expected_region_chunks = (chunk(b"fmt ", fmt) + chunk(b"data", reversed_payload)
                                                  + chunk(b"cue ", expected_region_cues) + chunk(b"LIST", region_data))
                        expected_region_file = b"RIFF" + struct.pack("<I", len(expected_region_chunks) + 4) + b"WAVE" + expected_region_chunks
                        require(Path(region_result["path"]).read_bytes() == expected_region_file
                            and region_result.get("cue_points_reversed") == 2
                            and region_result.get("cue_points_unchanged") == 1
                            and region_result.get("cue_chunks_unchanged") == 0,
                            "Region cue start was not mapped using its sample length", region_result)
                        for label, lengths in (("conflict", [2, 3]), ("out-of-bounds", [5]), ("zero", [0])):
                            ambiguous_regions = b"adtl" + b"".join(
                                chunk(b"ltxt", struct.pack("<II4sHHHH", cue_points[0][0], length,
                                                           b"rgn ", 0, 0, 0, 0) + b"region\x00") for length in lengths)
                            ambiguous_chunks = cue_chunks + chunk(b"LIST", ambiguous_regions)
                            ambiguous_path = ROOT / "output" / check.output("reverse-cue-" + label, ".wav")
                            ambiguous_path.write_bytes(b"RIFF" + struct.pack("<I", len(ambiguous_chunks) + 4) + b"WAVE" + ambiguous_chunks)
                            ambiguous_result = await check.audio(identifier, "process_audio", action="reverse", path=str(ambiguous_path),
                                                                 output_name=check.output("reversed-cue-" + label, ".wav"), expected_native=False)
                            ambiguous_points = [cue_points[0], expected_points[1], cue_points[2]]
                            ambiguous_cues = struct.pack("<I", len(ambiguous_points)) + b"".join(
                                struct.pack("<II4sIII", *point) for point in ambiguous_points)
                            expected_ambiguous_chunks = (chunk(b"fmt ", fmt) + chunk(b"data", reversed_payload)
                                                         + chunk(b"cue ", ambiguous_cues) + chunk(b"LIST", ambiguous_regions))
                            expected_ambiguous_file = b"RIFF" + struct.pack("<I", len(expected_ambiguous_chunks) + 4) + b"WAVE" + expected_ambiguous_chunks
                            require(Path(ambiguous_result["path"]).read_bytes() == expected_ambiguous_file
                                and ambiguous_result.get("cue_points_reversed") == 1
                                and ambiguous_result.get("cue_points_unchanged") == 2,
                                "Ambiguous region cue was modified", {"context": label, "result": ambiguous_result})
                        duplicate_points = [cue_points[0], (101, 1, b"data", 0, 0, 1), cue_points[1], cue_points[2]]
                        duplicate_cues = struct.pack("<I", len(duplicate_points)) + b"".join(
                            struct.pack("<II4sIII", *point) for point in duplicate_points)
                        duplicate_chunks = chunk(b"fmt ", fmt) + chunk(b"data", payload) + chunk(b"cue ", duplicate_cues) + chunk(b"LIST", region_data)
                        duplicate_path = ROOT / "output" / check.output("reverse-cue-duplicate-id", ".wav")
                        duplicate_path.write_bytes(b"RIFF" + struct.pack("<I", len(duplicate_chunks) + 4) + b"WAVE" + duplicate_chunks)
                        duplicate_result = await check.audio(identifier, "process_audio", action="reverse", path=str(duplicate_path),
                                                             output_name=check.output("reversed-cue-duplicate-id", ".wav"), expected_native=False)
                        expected_duplicate_points = [duplicate_points[0], duplicate_points[1], expected_points[1], cue_points[2]]
                        expected_duplicate_cues = struct.pack("<I", len(expected_duplicate_points)) + b"".join(
                            struct.pack("<II4sIII", *point) for point in expected_duplicate_points)
                        expected_duplicate_chunks = (chunk(b"fmt ", fmt) + chunk(b"data", reversed_payload)
                                                     + chunk(b"cue ", expected_duplicate_cues) + chunk(b"LIST", region_data))
                        expected_duplicate_file = b"RIFF" + struct.pack("<I", len(expected_duplicate_chunks) + 4) + b"WAVE" + expected_duplicate_chunks
                        require(Path(duplicate_result["path"]).read_bytes() == expected_duplicate_file
                            and duplicate_result.get("cue_points_reversed") == 1
                            and duplicate_result.get("cue_points_unchanged") == 3,
                            "Duplicate region cue identity was modified", duplicate_result)
                        for label, associated in (("plain", b""), ("labelled", chunk(b"LIST", associated_data))):
                            duplicate_chunks = chunk(b"fmt ", fmt) + chunk(b"data", payload) + chunk(b"cue ", duplicate_cues) + associated
                            duplicate_path = ROOT / "output" / check.output("reverse-cue-duplicate-" + label, ".wav")
                            duplicate_path.write_bytes(b"RIFF" + struct.pack("<I", len(duplicate_chunks) + 4) + b"WAVE" + duplicate_chunks)
                            duplicate_result = await check.audio(identifier, "process_audio", action="reverse", path=str(duplicate_path),
                                                                 output_name=check.output("reversed-cue-duplicate-" + label, ".wav"), expected_native=False)
                            expected_chunks = chunk(b"fmt ", fmt) + chunk(b"data", reversed_payload) + chunk(b"cue ", expected_duplicate_cues) + associated
                            expected_file = b"RIFF" + struct.pack("<I", len(expected_chunks) + 4) + b"WAVE" + expected_chunks
                            require(Path(duplicate_result["path"]).read_bytes() == expected_file
                                and duplicate_result.get("cue_points_reversed") == 1
                                and duplicate_result.get("cue_points_unchanged") == 3,
                                "Duplicate cue identity was modified", {"context": label, "result": duplicate_result})
                        first_cues = struct.pack("<I", 1) + struct.pack("<II4sIII", *duplicate_points[0])
                        second_cues = struct.pack("<I", 3) + b"".join(struct.pack("<II4sIII", *point) for point in duplicate_points[1:])
                        expected_second_cues = struct.pack("<I", 3) + b"".join(struct.pack("<II4sIII", *point) for point in expected_duplicate_points[1:])
                        split_chunks = chunk(b"fmt ", fmt) + chunk(b"data", payload) + chunk(b"cue ", first_cues) + chunk(b"cue ", second_cues)
                        split_path = ROOT / "output" / check.output("reverse-cue-duplicate-across-chunks", ".wav")
                        split_path.write_bytes(b"RIFF" + struct.pack("<I", len(split_chunks) + 4) + b"WAVE" + split_chunks)
                        split_result = await check.audio(identifier, "process_audio", action="reverse", path=str(split_path),
                                                         output_name=check.output("reversed-cue-duplicate-across-chunks", ".wav"), expected_native=False)
                        expected_split = (chunk(b"fmt ", fmt) + chunk(b"data", reversed_payload)
                                          + chunk(b"cue ", first_cues) + chunk(b"cue ", expected_second_cues))
                        require(Path(split_result["path"]).read_bytes() == b"RIFF" + struct.pack("<I", len(expected_split) + 4) + b"WAVE" + expected_split
                            and split_result.get("cue_points_reversed") == 1 and split_result.get("cue_points_unchanged") == 3,
                            "Duplicate cue identity across chunks was modified", split_result)
                        large_cues = struct.pack("<I", 65537) + b"".join(
                            struct.pack("<II4sIII", point_id, 0, b"data", 0, 0, 0) for point_id in range(65537))
                        large_chunks = chunk(b"fmt ", fmt) + chunk(b"data", payload) + chunk(b"cue ", large_cues)
                        large_path = ROOT / "output" / check.output("reverse-cue-identity-limit", ".wav")
                        large_path.write_bytes(b"RIFF" + struct.pack("<I", len(large_chunks) + 4) + b"WAVE" + large_chunks)
                        large_result = await check.audio(identifier, "process_audio", action="reverse", path=str(large_path),
                                                         output_name=check.output("reversed-cue-identity-limit", ".wav"), expected_native=False)
                        expected_large = chunk(b"fmt ", fmt) + chunk(b"data", reversed_payload) + chunk(b"cue ", large_cues)
                        require(Path(large_result["path"]).read_bytes() == b"RIFF" + struct.pack("<I", len(expected_large) + 4) + b"WAVE" + expected_large
                            and large_result.get("cue_points_reversed") == 0 and large_result.get("cue_points_unchanged") == 65537
                            and large_result.get("cue_chunks_unchanged") == 1,
                            "Cue identity limit did not preserve the metadata", large_result)
                        invalid_label_data = b"adtl" + chunk(b"labl", struct.pack("<I", cue_points[0][0]) + b"unterminated")
                        invalid_region_data = b"adtl" + chunk(b"ltxt", struct.pack("<II", cue_points[0][0], 2))
                        cue_contexts = [
                            ("invalid-label", cue_chunks + chunk(b"LIST", invalid_label_data),
                             chunk(b"fmt ", fmt) + chunk(b"data", reversed_payload) + chunk(b"cue ", cue_data)
                             + chunk(b"LIST", invalid_label_data)),
                            ("invalid-region", cue_chunks + chunk(b"LIST", invalid_region_data),
                             chunk(b"fmt ", fmt) + chunk(b"data", reversed_payload) + chunk(b"cue ", cue_data)
                             + chunk(b"LIST", invalid_region_data)),
                            ("sampler", cue_chunks + chunk(b"smpl", sampler_data),
                             chunk(b"fmt ", fmt) + chunk(b"data", reversed_payload) + chunk(b"cue ", cue_data)
                             + chunk(b"smpl", expected_sampler_data)),
                            ("multiple-data", chunk(b"fmt ", fmt) + chunk(b"data", payload[:8])
                             + chunk(b"cue ", cue_data) + chunk(b"data", payload[8:]),
                             chunk(b"fmt ", fmt) + chunk(b"data", reversed_payload) + chunk(b"cue ", cue_data)),
                        ]
                        for label, input_chunks, expected_chunks in cue_contexts:
                            context_path = ROOT / "output" / check.output("reverse-cue-" + label, ".wav")
                            context_path.write_bytes(b"RIFF" + struct.pack("<I", len(input_chunks) + 4) + b"WAVE" + input_chunks)
                            context_result = await check.audio(identifier, "process_audio", action="reverse", path=str(context_path),
                                                               output_name=check.output("reversed-cue-" + label, ".wav"), expected_native=False)
                            expected_context_file = b"RIFF" + struct.pack("<I", len(expected_chunks) + 4) + b"WAVE" + expected_chunks
                            require(Path(context_result["path"]).read_bytes() == expected_context_file
                                and context_result.get("cue_points_reversed") == 0
                                and context_result.get("cue_points_unchanged") == len(cue_points)
                                and context_result.get("cue_chunks_unchanged") == 1,
                                "Linked cue metadata or its unchanged-point receipt changed", {"context": label, "result": context_result})
                        partial_chunks = chunk(b"fmt ", fmt) + chunk(b"data", payload[:2]) + chunk(b"data", payload[2:])
                        partial_path = ROOT / "output" / check.output("reverse-partial-frame", ".wav")
                        partial_path.write_bytes(b"RIFF" + struct.pack("<I", len(partial_chunks) + 4) + b"WAVE" + partial_chunks)
                        await check.rejected("project_audio", "complete audio frames", session_id=identifier,
                                     operation="process_audio", options={"action": "reverse", "path": str(partial_path),
                                     "output_name": check.output("partial-frame-reverse", ".wav")})
                        compressed_fmt = struct.pack("<HHIIHHHHI", 0xfffe, 2, 44100, 176400, 4, 16, 22, 16, 3)
                        compressed_fmt += uuid.UUID("00000011-0000-0010-8000-00aa00389b71").bytes_le
                        compressed_chunks = chunk(b"fmt ", compressed_fmt) + chunk(b"data", payload)
                        compressed_path = ROOT / "output" / check.output("reverse-compressed", ".wav")
                        compressed_path.write_bytes(b"RIFF" + struct.pack("<I", len(compressed_chunks) + 4) + b"WAVE" + compressed_chunks)
                        await check.rejected("project_audio", "requires PCM or IEEE float", session_id=identifier,
                                             operation="process_audio", options={"action": "reverse", "path": str(compressed_path),
                                             "output_name": check.output("compressed-reverse", ".wav")})
                elif action == "normalize":
                    require(samples.shape == before_pcm.shape, "Normalize changed sample count")
                    gain = float(np.sum(before_pcm * samples) / np.sum(before_pcm * before_pcm))
                    error = float(np.sqrt(np.mean((samples - gain * before_pcm) ** 2)))
                    require(gain > 0 and error < 4 / 32768, "Normalize did not preserve waveform under a scalar gain", {"gain": gain, "rms_error": error})
                    require(actual["peak"] <= 1.0001, "Normalize clipped outside PCM range")
                    check.evidence("normalization", {"gain": gain, "rms_error": error})
                else:
                    overlap = min(len(samples), len(before_pcm))
                    difference = float(np.sqrt(np.mean((samples[:overlap] - before_pcm[:overlap]) ** 2)))
                    require(difference > before["rms"] * 0.01, "Nonzero pitch shift produced unchanged PCM")
                    check.evidence("pitch_pcm_rms_difference", difference)
            check.evidence("decoded_output", {"path": result["path"], **actual})
        require(source.read_bytes() == original, "Offline renderer modified source input")


for offline_action in ("reverse", "normalize", "time_stretch", "pitch_shift"):
    register_offline(offline_action)


@feature("audio.voice_change", "audio", "project_audio", "voicebanks")
async def audio_voice_change(check: Acceptance) -> None:
    import numpy as np
    source = await check.audio_input()
    original = source.read_bytes()
    before, source_pcm = read_audio(source)
    voices = (await check.call("voicebanks"))["voices"]
    eligible = [voice for voice in voices if voice["kind"] == "Dnn" and voice["synthesizable_version"]
                and voice["available_for_voice_changer"]]
    if not eligible:
        raise Blocked("No installed synthesizable Dnn voice is advertised for VOCALO CHANGER")
    voice = next((voice for voice in eligible if voice["available_in_sequence"]), eligible[0])
    async with check.project() as identifier:
        try:
            result = await check.audio(identifier, "process_audio", action="voice_change", path=str(source), voice_id=voice["comp_id"],
                                       output_name=check.output("voice-change", ".wav"), pitch_cents=200)
        except ToolFailure as error:
            if re.search(r"not available for native VOCALO CHANGER|model is missing|license|not found", str(error), re.IGNORECASE):
                raise Blocked(str(error)) from error
            raise
        actual, samples = read_audio(result["path"])
        compare_audio_reports(result, actual)
        require(result["backend"] == "WOR.voice_change", "Wrong VOCALO CHANGER backend")
        require(abs(actual["duration_seconds"] - before["duration_seconds"]) < max(0.2, before["duration_seconds"] * 0.1),
                "Voice conversion duration differs unexpectedly")
        overlap = min(len(samples), len(source_pcm))
        if samples.shape[1] == source_pcm.shape[1]:
            require(not np.allclose(samples[:overlap], source_pcm[:overlap], atol=2 / 32768, rtol=0), "Voice conversion produced unchanged PCM")
        check.evidence("converted_audio", {"voice_id": voice["comp_id"], **actual})
    require(source.read_bytes() == original, "Voice conversion modified its original input")


@feature("audio.guards", "audio", "project_audio")
async def audio_guards(check: Acceptance) -> None:
    fixture = await check.audio_input()
    fixture_original = fixture.read_bytes()
    async with check.project() as identifier:
        imported = await check.audio(identifier, "import_audio", path=str(fixture))
        disposable = await check.audio(identifier, "export_audio", track_index=imported["track_index"],
                                       part_index=imported["part_index"], original=True,
                                       output_name=check.output("guard-input", ".wav"))
        source = Path(disposable["path"])
        original = source.read_bytes()
        await check.rejected("project_audio", "exist|found", session_id=identifier, operation="import_audio",
                             options={"path": str(ROOT / "output" / check.output("missing", ".wav"))})
        await check.rejected("project_audio", "path|absolute", session_id=identifier, operation="import_audio", options={"path": source.name})
        await check.rejected("project_audio", "input|source", session_id=identifier, operation="process_audio",
                             options={"path": str(source), "action": "reverse", "output_name": source.name, "overwrite": True})
        await check.rejected("project_audio", "exist|overwrite", session_id=identifier, operation="process_audio",
                             options={"path": str(source), "action": "reverse", "output_name": source.name})
        await check.rejected("project_audio", "path|output|relative|travers|name", session_id=identifier, operation="process_audio",
                             options={"path": str(source), "action": "reverse", "output_name": "../" + check.output("escape", ".wav")})
        await check.rejected("project_audio", "unknown|unsupported", session_id=identifier, operation="Acceptance.Missing", options={})
        await check.rejected("project_audio", "end_tick|greater|region", session_id=identifier, operation="edit_audio",
                             options={"track_index": imported["track_index"], "part_index": imported["part_index"], "begin_tick": 50, "end_tick": 25})
        output = check.output("explicit-overwrite", ".wav")
        first = await check.audio(identifier, "export_audio", track_index=imported["track_index"], part_index=imported["part_index"],
                                  output_name=output)
        await check.audio(identifier, "export_audio", track_index=imported["track_index"], part_index=imported["part_index"],
                          output_name=output, overwrite=True)
        read_audio(first["path"])
    require(source.read_bytes() == original, "An audio failure case modified original input")
    require(fixture.read_bytes() == fixture_original, "Audio guard verification modified the shared singing fixture")


def register_effect_scope(scope: str) -> None:
    @feature("effects." + scope, "effects", "project_audio", "project_save", "project_open")
    async def effects(check: Acceptance) -> None:
        source = await check.audio_input()
        async with check.project() as identifier:
            imported = await check.audio(identifier, "import_audio", path=str(source))
            selected = {"scope": scope}
            if scope in ("track", "part"):
                selected["track_index"] = imported["track_index"]
            if scope == "part":
                selected["part_index"] = imported["part_index"]
            catalog = await check.audio(identifier, "effects", scope="catalog")
            candidates = [effect for effect in catalog["effects"] if effect["parameter_count"] > 0
                          and not re.search("reverse|pitch", effect["name"], re.IGNORECASE)]
            if len(candidates) < 2:
                raise Blocked("Two installed non-virtual parameterized effects are required for chain ordering")
            candidates.sort(key=lambda effect: ("gain" not in effect["name"].lower(), effect["name"]))
            before = await check.audio(identifier, "effects", **selected)
            start = len(before["effects"])
            metadata = await check.audio(identifier, "effects", scope="catalog", effect_id=candidates[0]["effect_id"])
            require(metadata["parameters"], "Bundled effect has no discoverable parameters")
            parameter = metadata["parameters"][0]
            changed = 0.25 if abs(parameter["normalized"] - 0.25) > 0.05 else 0.75
            await check.audio(identifier, "set_effect", **selected, action="add", effect_id=candidates[0]["effect_id"], bypass=False)
            await check.audio(identifier, "set_effect", **selected, action="set", slot=start,
                              parameters={parameter["name"]: changed}, bypass=True)
            await check.audio(identifier, "set_effect", **selected, action="set", slot=start,
                              parameters={parameter["name"]: changed}, bypass=True)
            chain = await check.audio(identifier, "effects", **selected)
            added = chain["effects"][start]
            require(added["bypass"] is True and added["effect_id"] == candidates[0]["effect_id"], "Effect bypass/identity mismatch")
            persisted_parameter = next(value for value in added["parameters"] if value["name"] == parameter["name"])
            require(abs(persisted_parameter["value"] - changed) < 1e-5, "Effect normalized parameter was not persisted")
            presets = [name for name in metadata["presets"] if name]
            if presets:
                await check.audio(identifier, "set_effect", **selected, action="set", slot=start, preset=presets[0])
            else:
                check.evidence("preset_not_applicable", "Selected native effect advertises no presets; preset application not tested")
            await check.audio(identifier, "set_effect", **selected, action="add", effect_id=candidates[1]["effect_id"])
            await check.audio(identifier, "set_effect", **selected, action="move", slot=start + 1, target_slot=start)
            moved = await check.audio(identifier, "effects", **selected)
            require(moved["effects"][start]["effect_id"] == candidates[1]["effect_id"], "Effect chain reorder failed")
            _, path = await check.save(identifier, "effects-" + scope)
            reopened = (await check.call("project_open", path=str(path)))["session_id"]
            stored = await check.audio(reopened, "effects", **selected)
            require([(entry["effect_id"], entry["bypass"]) for entry in stored["effects"]]
                    == [(entry["effect_id"], entry["bypass"]) for entry in moved["effects"]], "Saved effect chain differs")
            await check.close(reopened)
            await check.rejected("project_audio", "normalized|range|0..1", session_id=identifier, operation="set_effect",
                                 options={**selected, "action": "set", "slot": start + 1, "parameters": {parameter["name"]: 2}})
            await check.audio(identifier, "set_effect", **selected, action="remove", slot=start + 1)
            await check.audio(identifier, "set_effect", **selected, action="remove", slot=start)
            require(len((await check.audio(identifier, "effects", **selected))["effects"]) == start, "Effect removal did not restore chain length")


for effect_scope in ("master", "track", "part"):
    register_effect_scope(effect_scope)


@feature("effects.preset", "effects", "project_audio")
async def effect_preset(check: Acceptance) -> None:
    async with check.project() as identifier:
        catalog = await check.audio(identifier, "effects", scope="catalog")
        selected = None
        for candidate in catalog["effects"][:16]:
            if re.search("reverse|pitch", candidate["name"], re.IGNORECASE):
                continue
            metadata = await check.audio(identifier, "effects", scope="catalog", effect_id=candidate["effect_id"])
            presets = [name for name in metadata["presets"] if name]
            if presets:
                selected = (candidate, presets[0])
                break
        if selected is None:
            raise Blocked("No preset exposed by the first 16 installed non-virtual effects; preset application is unverified")
        candidate, preset = selected
        chain = await check.audio(identifier, "effects", scope="master")
        slot = len(chain["effects"])
        await check.audio(identifier, "set_effect", scope="master", action="add", effect_id=candidate["effect_id"])
        await check.audio(identifier, "set_effect", scope="master", action="set", slot=slot, preset=preset)
        first = (await check.audio(identifier, "effects", scope="master"))["effects"][slot]["parameters"]
        await check.audio(identifier, "set_effect", scope="master", action="set", slot=slot, preset=preset)
        second = (await check.audio(identifier, "effects", scope="master"))["effects"][slot]["parameters"]
        require(first == second and first, "Native preset parameter readback is empty or nondeterministic")
        check.evidence("applied_native_preset", {"effect_id": candidate["effect_id"], "preset": preset, "parameters": first})


@feature("mixdown.automation", "mixdown", "project_audio", "project_edit", "project_create")
async def mixdown_automation(check: Acceptance) -> None:
    import numpy as np
    source = await check.audio_input()
    identifier = (await check.call("project_create", title="Automation audio acceptance", bpm=120))["session_id"]
    imported = await check.audio(identifier, "import_audio", path=str(source))
    track = imported["track_index"]
    master = await check.edit(identifier, "automation.list", scope="master_volume")
    pan = await check.edit(identifier, "automation.list", scope="track_pan", track_index=track)
    options = {"sample_rate": 44100, "channels": 2, "bits_per_sample": 16,
           "bypass_effects": True, "timeout_seconds": 90}
    baseline = await check.audio(identifier, "mixdown", output_name=check.output("automation-baseline", ".wav"), **options)
    _, baseline_pcm = read_audio(baseline["path"])
    attenuation = max(master["minimum"], master["default_value"] - 120)
    await check.edit(identifier, "automation.set", scope="master_volume",
             points=[{"tick": 0, "value": attenuation}], replace=True)
    quiet = await check.audio(identifier, "mixdown", output_name=check.output("automation-master", ".wav"), **options)
    _, quiet_pcm = read_audio(quiet["path"])
    require(quiet_pcm.shape == baseline_pcm.shape, "Master automation changed native mix length")
    baseline_rms = float(np.sqrt(np.mean(baseline_pcm ** 2)))
    quiet_rms = float(np.sqrt(np.mean(quiet_pcm ** 2)))
    expected_gain = 10 ** ((attenuation - master["default_value"]) / 200)
    require(abs(quiet_rms / baseline_rms - expected_gain) < 0.03,
        "Master automation did not affect the native mix as expected", quiet_rms / baseline_rms)
    stems = await check.audio(identifier, "mixdown_stems", output_prefix=check.output("automation-stem", ""),
                  track_indices=[track], **options)
    _, stem_pcm = read_audio(stems["stems"][0]["path"])
    require(stem_pcm.shape == baseline_pcm.shape
        and float(np.sqrt(np.mean((stem_pcm - baseline_pcm) ** 2))) < 0.01,
        "Stem mix did not bypass master volume automation")
    await check.edit(identifier, "automation.set", scope="master_volume",
             points=[{"tick": 0, "value": master["default_value"]}], replace=True)
    volume = await check.edit(identifier, "automation.list", scope="track_volume", track_index=track)
    track_attenuation = max(volume["minimum"], volume["default_value"] - 120)
    await check.edit(identifier, "automation.set", scope="track_volume", track_index=track,
             points=[{"tick": 0, "value": track_attenuation}], replace=True)
    quieter_track = await check.audio(identifier, "mixdown", output_name=check.output("automation-track", ".wav"), **options)
    _, track_pcm = read_audio(quieter_track["path"])
    track_gain = float(np.sqrt(np.mean(track_pcm ** 2))) / baseline_rms
    require(abs(track_gain - 10 ** ((track_attenuation - volume["default_value"]) / 200)) < 0.03,
        "Track volume automation did not affect native output as expected", track_gain)
    await check.edit(identifier, "automation.set", scope="track_volume", track_index=track,
             points=[{"tick": 0, "value": volume["default_value"]}], replace=True)
    await check.edit(identifier, "automation.set", scope="track_pan", track_index=track,
             points=[{"tick": 0, "value": pan["minimum"]}], replace=True)
    panned = await check.audio(identifier, "mixdown", output_name=check.output("automation-pan", ".wav"), **options)
    _, panned_pcm = read_audio(panned["path"])
    channel_rms = np.sqrt(np.mean(panned_pcm ** 2, axis=0))
    require(channel_rms[0] > 0 and channel_rms[1] < channel_rms[0] * 0.05,
        "Track pan automation did not affect native stereo output", channel_rms.tolist())
    check.evidence("automation_audio", {"master_gain": quiet_rms / baseline_rms, "track_gain": track_gain,
                                       "pan_rms": channel_rms.tolist()})


@feature("mixdown.master_stems", "mixdown", "project_audio", "project_edit")
async def mixdown_master(check: Acceptance) -> None:
    import numpy as np
    source = await check.audio_input()
    source_metadata, source_pcm = read_audio(source)
    async with check.project() as identifier:
        first = await check.audio(identifier, "import_audio", path=str(source), position_tick=0, name="Stem one")
        second = await check.audio(identifier, "import_audio", path=str(source), position_tick=480, name="Stem two")
        selected = [first["track_index"], second["track_index"]]
        length = source_metadata["duration_seconds"] + 0.5
        options = {"sample_rate": 44100, "channels": 2, "bits_per_sample": 16,
               "timeout_seconds": 90, "bypass_effects": True}
        master = await check.audio(identifier, "mixdown", output_name=check.output("master", ".wav"), **options)
        actual, master_pcm = read_audio(master["path"])
        compare_audio_reports(master, actual)
        require(master["backend"] == "VAE.Manual+VEM" and actual["sample_rate"] == 44100 and actual["channels"] == 2,
                "Native master mix format mismatch", actual)
        require(abs(actual["duration_seconds"] - length) < 0.08, "Native master range mismatch", actual)
        await check.edit(identifier, "track.update", track_index=second["track_index"], mute=True)
        prefix = check.output("stems", "")
        stems = await check.audio(identifier, "mixdown_stems", output_prefix=prefix, track_indices=selected, **options)
        require(len(stems["stems"]) == 2, "Native stem count mismatch")
        decoded = []
        for index, item in enumerate(stems["stems"]):
            metadata, samples = read_audio(item["path"])
            compare_audio_reports(item, metadata)
            require(Path(item["path"]).name == f"{prefix}-track-{selected[index]}.wav", "Stem filename/track mapping mismatch")
            expected_length = source_metadata["duration_seconds"] + 0.5 * index
            require(abs(metadata["duration_seconds"] - expected_length) < 0.08, "Stem range mismatch")
            decoded.append(samples)
        require(all(samples.shape[1] == master_pcm.shape[1] and len(samples) <= len(master_pcm) for samples in decoded),
                "Native stems exceed the master range or differ in channel count")
        summed = np.zeros_like(master_pcm)
        for samples in decoded:
            summed[:len(samples)] += samples
        unclipped = np.abs(summed) < 0.95
        require(np.count_nonzero(unclipped) > 100, "Insufficient unclipped PCM to compare master and stems")
        error = float(np.sqrt(np.mean((summed[unclipped] - master_pcm[unclipped]) ** 2)))
        require(error < 0.01, "Bypassed native master differs from sum of stems", error)
        overlap = min(len(decoded[0]), len(decoded[1]))
        require(not np.allclose(decoded[0][:overlap], decoded[1][:overlap], atol=2 / 32768, rtol=0),
            "Offset tracks unexpectedly produced identical stems")
        if (await check.call("vocaloid_features"))["product"] == "VOCALOID7":
            await check.edit(identifier, "track.update", track_index=first["track_index"], mute=True, solo=True)
            await check.edit(identifier, "track.update", track_index=second["track_index"], mute=False)
            await check.edit(identifier, "track.update", track_index=second["track_index"], solo_state="Defeat")
            defeat_mix = await check.audio(identifier, "mixdown", output_name=check.output("solo-defeat", ".wav"), **options)
            _, defeat_pcm = read_audio(defeat_mix["path"])
            require(defeat_pcm.shape == master_pcm.shape
                    and float(np.sqrt(np.mean((defeat_pcm - master_pcm) ** 2))) < 0.01,
                    "Solo Defeat did not include the other native track")
            await check.edit(identifier, "track.update", track_index=second["track_index"], solo_state="Off")
            await check.edit(identifier, "track.update", track_index=second["track_index"], mute=True)
            solo_mix = await check.audio(identifier, "mixdown", output_name=check.output("stored-mute-solo", ".wav"), **options)
            _, solo_pcm = read_audio(solo_mix["path"])
            expected_solo = np.zeros_like(solo_pcm)
            overlap = min(len(expected_solo), len(decoded[0]))
            expected_solo[:overlap] = decoded[0][:overlap]
            require(float(np.sqrt(np.mean((solo_pcm - expected_solo) ** 2))) < 0.01,
                "Soloed track with stored mute did not match its native stem")
            await check.edit(identifier, "track.update", track_index=first["track_index"], mute=False, solo=False)
            muted_mix = await check.audio(identifier, "mixdown", output_name=check.output("stored-mute-other", ".wav"), **options)
            _, muted_pcm = read_audio(muted_mix["path"])
            expected_muted = np.zeros_like(muted_pcm)
            overlap = min(len(expected_muted), len(decoded[0]))
            expected_muted[:overlap] = decoded[0][:overlap]
            require(float(np.sqrt(np.mean((muted_pcm - expected_muted) ** 2))) < 0.01,
                "Stored mute was not applied after the other solo ended")
        await check.rejected("project_audio", "exist|overwrite", session_id=identifier, operation="mixdown_stems",
                             options={**options, "output_prefix": prefix, "track_indices": selected})
        check.evidence("master_stems", {"master": actual, "sum_rms_error": error, "input_frames": len(source_pcm)})


@feature("mixdown.guards", "mixdown", "project_audio")
async def mixdown_guards(check: Acceptance) -> None:
    async with check.project() as identifier:
        await check.rejected("project_audio", "track_indices|track|placement|empty", session_id=identifier, operation="mixdown",
                             options={"output_name": check.output("no-input", ".wav")})
        await check.rejected("project_audio", "track_indices|track", session_id=identifier, operation="mixdown_stems",
                             options={"output_prefix": check.output("no-stems", ""), "track_indices": [99999]})
    async with check.project() as identifier:
        await check.audio(identifier, "import_audio", path=str(await check.audio_input()))
        for option in ("start_seconds", "end_seconds", "tail_seconds"):
            await check.rejected("project_audio", "not supported|complete selected tracks", session_id=identifier,
                                 operation="mixdown", options={"output_name": check.output("range-rejected", ".wav"), option: 1})


@feature("mixdown.multiple_parts", "mixdown", "project_audio", "project_edit", "score_compose")
async def mixdown_multiple_parts(check: Acceptance) -> None:
    import numpy as np
    async with check.project(score=True) as identifier:
        await check.edit(identifier, "part.duplicate", track_index=0, part_index=0, start_tick=3840)
        result = await check.audio(identifier, "mixdown", output_name=check.output("multiple-parts", ".wav"),
                                   timeout_seconds=30)
        metadata, samples = read_audio(result["path"])
        compare_audio_reports(result, metadata)
        sample_rate = metadata["sample_rate"]
        require(len(samples) > 5 * sample_rate, "Mixdown omitted the later part", metadata)
        for start_seconds in (0, 4):
            segment = samples[start_seconds * sample_rate:(start_seconds + 2) * sample_rate]
            require(float(np.max(np.abs(segment))) > 0.001, "Mixdown contains a silent part", start_seconds)
        check.evidence("multiple_parts_wave", {"path": result["path"], **metadata})


@feature("mixdown.project_fixture", "mixdown", "project_audio", "project_open", "project_render_part", "project_edit")
async def mixdown_project_fixture(check: Acceptance) -> None:
    import numpy as np
    fixture = check.arguments.mixdown_fixture
    if fixture is None:
        raise Skipped("Supply --mixdown-fixture to verify an existing multi-part project")
    sequence, _ = read_vpr(fixture)
    check.evidence("source", {"path": str(fixture.resolve()), "parts_per_track": [
        len(track.get("parts", [])) for track in sequence["tracks"]]})
    identifier = (await check.call("project_open", path=str(fixture.resolve())))["session_id"]
    try:
        first = next((index for index, track in enumerate(sequence["tracks"])
                      if track.get("type") in (0, 2) and track.get("parts")), None)
        require(first is not None, "Fixture has no vocal part")
        single = await check.call("project_render_part", session_id=identifier, track_index=first, part_index=0,
                                  output_name=check.output("fixture-single", ".wav"))
        read_audio(single["path"], max_seconds=600)
        result = await check.audio(identifier, "mixdown", output_name=check.output("fixture-mix", ".wav"),
                                   timeout_seconds=30)
        metadata, samples = read_audio(result["path"], max_seconds=600)
        compare_audio_reports(result, metadata)
        peaks = []
        for part in sequence["tracks"][first]["parts"]:
            if not part.get("notes"):
                continue
            start = await check.edit(identifier, "time.convert", **{"from": "tick", "value": part["pos"]})
            end = await check.edit(identifier, "time.convert", **{
                "from": "tick", "value": part["pos"] + part["duration"]})
            segment = samples[int(start["seconds"] * metadata["sample_rate"]):
                              int(end["seconds"] * metadata["sample_rate"])]
            require(segment.size > 0, "Mixdown omitted a part", part.get("name"))
            peak = float(np.max(np.abs(segment)))
            require(peak > 0.001, "Mixdown contains a silent part", part.get("name"))
            peaks.append({"name": part.get("name"), "peak": peak})
        check.evidence("fixture_mix", {"path": result["path"], "part_peaks": peaks, **metadata})
    finally:
        if identifier in check.sessions:
            await check.close(identifier)


@feature("mixdown.master_effect", "mixdown", "project_audio")
async def mixdown_master_effect(check: Acceptance) -> None:
    import numpy as np
    source = await check.audio_input()
    source_metadata, _ = read_audio(source)
    async with check.project() as identifier:
        imported = await check.audio(identifier, "import_audio", path=str(source))
        catalog = await check.audio(identifier, "effects", scope="catalog")
        gain = next((item for item in catalog["effects"] if "gain" in item["name"].lower()), None)
        if gain is None:
            raise Blocked("No native gain effect is installed for an observable master/stem comparison")
        metadata = await check.audio(identifier, "effects", scope="catalog", effect_id=gain["effect_id"])
        parameter = next((item for item in metadata["parameters"] if "gain" in item["name"].lower()), None)
        if parameter is None:
            raise Blocked("Native gain effect did not expose a gain parameter")
        options = {"sample_rate": 192000, "channels": 1, "bits_per_sample": 24,
                   "timeout_seconds": 90}
        plain = await check.audio(identifier, "mixdown", output_name=check.output("plain-master", ".wav"), bypass_effects=True, **options)
        _, plain_pcm = read_audio(plain["path"])
        await check.audio(identifier, "set_effect", scope="master", action="add", effect_id=gain["effect_id"],
                          parameters={parameter["name"]: 0.15}, bypass=False)
        processed = await check.audio(identifier, "mixdown", output_name=check.output("processed-master", ".wav"), **options)
        actual, processed_pcm = read_audio(processed["path"])
        compare_audio_reports(processed, actual)
        require(actual["sample_rate"] == 192000 and actual["channels"] == 1 and actual["subtype"] == "PCM_24",
                "192 kHz mono 24-bit export options were not applied", actual)
        require(plain_pcm.shape == processed_pcm.shape, "Master effect changed render duration")
        delta = float(np.sqrt(np.mean((plain_pcm - processed_pcm) ** 2)))
        require(delta > float(np.sqrt(np.mean(plain_pcm ** 2))) * 0.01, "Master gain effect was not audible in rendered PCM")
        stems = await check.audio(identifier, "mixdown_stems", output_prefix=check.output("master-bypassed-stem", ""),
                                  track_indices=[imported["track_index"]], **options)
        _, stem_pcm = read_audio(stems["stems"][0]["path"])
        require(stem_pcm.shape == plain_pcm.shape and np.allclose(stem_pcm, plain_pcm, atol=0.0002, rtol=0),
                "Stem unexpectedly includes master gain processing")
        check.evidence("master_effect_rms_difference", delta)


@feature("library.lyrics", "library", "project_library", "project_edit", "project_save", "score_compose")
async def library_lyrics(check: Acceptance) -> None:
    async with check.project(score=True) as identifier:
        selected = {"track_index": 0, "part_index": 0, "note_index": 0, "language_id": 0}
        convertible = await check.library("lyrics_can_convert", language_id=0, lyrics="\u3044", is_ai=True)
        require(convertible["can_convert"] is True, "Native G2PA rejected a basic Japanese lyric", convertible)
        english = {**selected, "language_id": 1}
        candidates = await check.library("lyrics_candidates", identifier, **english, lyrics="hello")
        require(len(candidates["candidates"]) >= 2 and all(candidate and all(
                isinstance(syllable["lyric"], str) and syllable["lyric"]
                and isinstance(syllable["phonemes"], str) and syllable["phonemes"]
                for syllable in candidate) for candidate in candidates["candidates"]),
            "Native English G2PA did not return nonempty alternatives", candidates)
        alternatives = await check.library("lyrics_candidates", identifier, **english, lyrics="a")
        require({"V", "eI"} <= {syllable["phonemes"] for candidate in alternatives["candidates"] for syllable in candidate},
            "Native English vowel alternatives are missing", alternatives)
        applied = await check.library("lyrics_apply", identifier, **selected, lyrics="\u3044", protect=False)
        require(applied["affected_length"] == 1 and applied["notes"][0]["lyric"] == "\u3044"
            and applied["notes"][0]["phonemes"] == "i" and applied["notes"][0]["valid_phonemes"]
            and applied["notes"][0]["language_id"] == 0,
            "Native Japanese SetLyrics did not produce the expected phonemes", applied)
        phonemes = applied["notes"][0]["phonemes"]
        applied = await check.library("phonemes_apply", identifier, **selected, phonemes=phonemes, protect=True)
        require(applied["notes"][0]["phonemes"] == phonemes and applied["notes"][0]["protected"], "Native phoneme/protection application failed")
        notes = (await check.edit(identifier, "note.list", track_index=0, part_index=0))["notes"]
        require(notes[0]["phonemes"] == phonemes and notes[0]["is_protected"], "Independent native note readback disagrees")
        sequence, _ = await check.save(identifier, "library-lyrics")
        persisted = sequence["tracks"][0]["parts"][0]["notes"][0]
        require(persisted["phoneme"] == phonemes and persisted["isProtected"], "Applied native phonemes were not saved")


@feature("library.resets", "library", "project_library", "project_edit", "score_compose")
async def library_resets(check: Acceptance) -> None:
    async with check.project(score=True) as identifier:
        selected = {"track_index": 0, "part_index": 0, "note_index": 0, "language_id": 0}
        await check.library("lyrics_apply", identifier, **selected, lyrics="\u3044", protect=False)
        reset = await check.library("lyrics_reset", identifier, track_index=0, part_index=0, language_id=0)
        require(reset["affected_length"] > 0 and reset["notes"], "Native lyric reset touched no notes")
        first = (await check.edit(identifier, "note.list", track_index=0, part_index=0))["notes"][0]
        require(first["lyric"] == reset["notes"][0]["lyric"], "Lyric reset readback disagrees")
        await check.library("phonemes_apply", identifier, **selected, phonemes="i", protect=False)
        reset = await check.library("phonemes_reset", identifier, track_index=0, part_index=0, language_id=0)
        first = (await check.edit(identifier, "note.list", track_index=0, part_index=0))["notes"][0]
        require(reset["affected_length"] > 0 and first["phonemes"] == reset["notes"][0]["phonemes"], "Phoneme reset readback disagrees")


@feature("library.guards", "library", "project_library", "score_compose", "vocaloid_features", "project_edit", "project_status")
async def library_guards(check: Acceptance) -> None:
    await check.rejected("project_library", "session_id|required", operation="lyrics_apply", options={"lyrics": "a"})
    await check.rejected("project_library", "language_id|language|JPN", operation="lyrics_can_convert",
                         options={"language_id": 9999, "lyrics": "a"})
    async with check.project(score=True) as identifier:
        before = await check.edit(identifier, "note.list", track_index=0, part_index=0)
        await check.rejected("project_library", "note_index|found", session_id=identifier, operation="lyrics_apply",
                             options={"track_index": 0, "part_index": 0, "note_index": 99999, "lyrics": "a"})
        if (await check.call("vocaloid_features"))["product"] == "VOCALOID7":
            history = await check.edit(identifier, "history.status")
            status = await check.call("project_status", session_id=identifier)
            operations = ("media_list", "media_get", "media_capture", "media_import", "media_update", "media_delete", "media_recovery_list", "media_recovery_resolve")
            for operation in operations:
                await check.rejected("project_library", "VOCALOID7 removed MediaManager", session_id=identifier, operation=operation, options={"track_index": 0, "part_index": 0})
            require(await check.edit(identifier, "history.status") == history
                and (await check.call("project_status", session_id=identifier))["dirty"] == status["dirty"],
                "Unsupported V7 media operation changed history or dirty state")
        require(await check.edit(identifier, "note.list", track_index=0, part_index=0) == before, "Rejected library edit mutated notes")


@feature("library.dvqm_plain_probe", "library", "project_create", "project_edit", "project_library", "project_save", "project_open", "voicebanks", "vocaloid_features", "vocaloid_operations", "project_members", "project_call")
async def library_dvqm_plain_probe(check: Acceptance) -> None:
    catalog = await check.library("dvqm_catalog", is_attack=True, limit=1)
    if not catalog["entries"]:
        raise Blocked("An installed native Attack preset is required")
    entry = catalog["entries"][0]
    product = (await check.call("vocaloid_features"))["product"]
    voices = (await check.call("voicebanks"))["voices"]
    voice = next(item for item in voices if item["name"] == "asa" and item["available_in_sequence"])
    async with check.project() as identifier:
        await check.edit(identifier, "track.create", type="MidiAi", name="DVQM probe")
        await check.edit(identifier, "part.create", track_index=0, start_tick=0, duration_tick=1920)
        scope = {"track_index": 0, "part_index": 0}
        voice_scope = {**scope, **({"scope": "track"} if product == "VOCALOID7" else {})}
        await check.edit(identifier, "voice.set", **voice_scope, ai_voice_bank_id=voice["comp_id"])
        await check.edit(identifier, "note.add", **scope, start_tick=0, duration_tick=480,
                         number=60, lyric="\u3042", phonemes="a", lang_id=0)
        target = {**scope, "note_index": 0, "is_attack": True}
        catalog = await check.call("vocaloid_operations", domain="library", operation="dvqm_set")
        require(catalog["domains"]["library"]["operations"][0]["track_support"]["MidiAi"] == "unsupported",
            "AI DVQM limitation is absent from operation discovery", catalog)
        skill = await check.library("note_skill_get", identifier, **scope, note_index=0)
        history = await check.edit(identifier, "history.status")
        await check.rejected("project_library", "cannot preserve.*undo", session_id=identifier,
                     operation="dvqm_set", options={**target, "db_id": entry["db_id"], "name_id": entry["name_id"]})
        require(await check.library("note_skill_get", identifier, **scope, note_index=0) == skill
            and await check.edit(identifier, "history.status") == history,
            "Rejected Attack assignment changed note skill or history")
        require((await check.library("dvqm_clear", identifier, **target))["is_empty"],
            "Clearing an empty Attack should be a no-op")
        track_ref = (await check.method(identifier, "GetTrack", [0]))["value"]["$ref"]
        part_ref = (await check.method(identifier, "GetPart", [0], track_ref))["value"]["$ref"]
        note_ref = (await check.method(identifier, "GetNote", [0], part_ref))["value"]["$ref"]
        dvqm_ref = (await check.method(identifier, "GetDvqm", [True], note_ref))["value"]["$ref"]
        members = await check.call("project_members", session_id=identifier, ref=dvqm_ref)
        arguments = {"Set": [entry["db_id"], entry["name_id"], False], "Reset": [],
                     "SetDBID": [entry["db_id"]], "SetDBIDByCompID": [entry["component_id"]],
                     "SetNameID": [entry["name_id"]], "SetSpeed": [50], "SetTopFactor": [1.0],
                     "SetProtect": [True], "SetNameIDByLevelNames": [entry["component_id"], entry["level_names"]]}
        exposed = [item for item in members["methods"] if item["member_id"].split("(", 1)[0] in arguments]
        require({item["member_id"].split("(", 1)[0] for item in exposed} == set(arguments),
                "DVQM writable method inventory changed", exposed)
        for item in exposed:
            name = item["member_id"].split("(", 1)[0]
            await check.rejected("project_call", "AI Attack/Release.*cannot preserve", session_id=identifier,
                                 ref=dvqm_ref, member_id=item["member_id"], args=arguments[name])
        require(await check.library("note_skill_get", identifier, **scope, note_index=0) == skill
            and await check.edit(identifier, "history.status") == history,
            "Rejected raw DVQM mutations changed note skill or history")


@feature("library.dvqm_ai_persistence", "library", "project_library", "project_edit", "project_clone", "project_status", "project_inspect", "project_render_part", "score_compose", "score_patch", "project_save", "project_open", "vocaloid_features", "vocaloid_operations")
async def library_dvqm_ai_persistence(check: Acceptance) -> None:
    import numpy as np
    catalogs = {is_attack: await check.library("dvqm_catalog", is_attack=is_attack, limit=1)
                for is_attack in (True, False)}
    if any(not catalog["entries"] for catalog in catalogs.values()):
        raise Blocked("Installed Attack and Release presets are required")
    async with check.project(score=True) as identifier:
        target = {"track_index": 0, "part_index": 0, "note_index": 0}
        feature = (await check.call("vocaloid_features", feature="ai_dvqm_metadata"))["features"]["ai_dvqm_metadata"]
        operation = (await check.call("vocaloid_operations", domain="library", operation="dvqm_set"))["domains"]["library"]["operations"][0]
        inspected = await check.call("project_inspect", session_id=identifier, feature="ai_dvqm_metadata", **target)
        require(feature["support"] == "bridge_contract" and "ai_dvqm_metadata" in operation["features"]
            and "metadata only" in operation["storage_support"]["bridge_metadata"]
            and inspected["readbacks"][0]["result"]["native"] is False,
            "AI bridge metadata feature discovery or binding is incorrect", inspected)
        skill = await check.library("note_skill_get", identifier, **target)
        before_audio = await check.call("project_render_part", session_id=identifier, track_index=0, part_index=0,
                        output_name=check.output("ai-dvqm-before", ".wav"))
        before_info, before_samples = read_audio(before_audio["path"])
        selected = {}
        for is_attack in (True, False):
            entry = catalogs[is_attack]["entries"][0]
            options = {**target, "is_attack": is_attack, "storage": "bridge_metadata"}
            before = await check.library("dvqm_get", identifier, expected_native=False, **options)
            require(before["is_empty"] and before["storage"] == "bridge_metadata",
                    "AI metadata fixture is not empty", before)
            selected[is_attack] = await check.library("dvqm_set", identifier, expected_native=False, **options,
                db_id=entry["db_id"], name_id=entry["name_id"], speed=77 if is_attack else 57,
                top_factor=0.75, is_protected=is_attack)
            value = selected[is_attack]
            require(not value["is_empty"] and value["storage"] == "bridge_metadata"
                    and not value["applicable_to_current_part"] and value["component_id"] == entry["component_id"]
                    and value["level_names"] == entry["level_names"] and value["speed"] == (77 if is_attack else 57)
                    and value["top_factor"] == 0.75 and value["is_protected"] is is_attack,
                    "AI bridge metadata selection differs from requested values", value)
            require((await check.library("dvqm_get", identifier, **target, is_attack=is_attack))["is_empty"]
                    and await check.library("note_skill_get", identifier, **target) == skill,
                    "AI bridge metadata changed native DVQM or Singing Skill")
        await check.edit(identifier, "undo")
        require((await check.library("dvqm_get", identifier, expected_native=False, **target,
                                     is_attack=False, storage="bridge_metadata"))["is_empty"]
                and await check.library("dvqm_get", identifier, expected_native=False, **target,
                                        is_attack=True, storage="bridge_metadata") == selected[True]
                and await check.library("note_skill_get", identifier, **target) == skill,
                "Undo did not restore AI bridge metadata and Singing Skill")
        await check.edit(identifier, "redo")
        require(await check.library("dvqm_get", identifier, expected_native=False, **target,
                                    is_attack=False, storage="bridge_metadata") == selected[False],
                "Redo did not restore AI Release metadata")
        updated_skill = await check.library("note_skill_set", identifier, **target,
                            pre_weight=0 if skill["pre_weight"] else 1)
        require(updated_skill != skill and await check.library("dvqm_get", identifier, expected_native=False,
            **target, is_attack=True, storage="bridge_metadata") == selected[True],
            "Native Singing Skill edit changed AI bridge metadata")
        await check.edit(identifier, "undo")
        require(await check.library("note_skill_get", identifier, **target) == skill
            and await check.library("dvqm_get", identifier, expected_native=False, **target,
                        is_attack=False, storage="bridge_metadata") == selected[False],
            "Undo of native Singing Skill changed AI bridge metadata")
        saved, path = await check.save(identifier, "ai-dvqm-metadata")
        saved_note = saved["tracks"][0]["parts"][0]["notes"][0]
        require("singingSkill" in saved_note and "vocaloid_bridge_ai_dvqm_v1" in saved_note,
                "VPR did not preserve both native skill and bridge metadata", saved_note)
        after_audio = await check.call("project_render_part", session_id=identifier, track_index=0, part_index=0,
                           output_name=check.output("ai-dvqm-after", ".wav"))
        after_info, after_samples = read_audio(after_audio["path"])
        require(before_audio["native"] and after_audio["native"] and before_info["sample_rate"] == after_info["sample_rate"]
            and np.array_equal(before_samples, after_samples),
            "AI bridge metadata changed native synthesized audio")
        before_repeat = await check.edit(identifier, "history.status")
        attack_entry = catalogs[True]["entries"][0]
        repeated = await check.library("dvqm_set", identifier, expected_native=False, **target,
            is_attack=True, storage="bridge_metadata", db_id=attack_entry["db_id"], name_id=attack_entry["name_id"],
            speed=77, top_factor=0.75, is_protected=True)
        require(repeated == selected[True] and await check.edit(identifier, "history.status") == before_repeat
            and not (await check.call("project_status", session_id=identifier))["dirty"],
            "Repeated AI bridge metadata assignment changed history or dirty state")
        clone = (await check.call("project_clone", session_id=identifier))["session_id"]
        reopened = (await check.call("project_open", path=str(path)))["session_id"]
        try:
            for session in (clone, reopened):
                require(await check.library("note_skill_get", session, **target) == skill,
                        "AI metadata reload changed native Singing Skill")
                for is_attack in (True, False):
                    require(await check.library("dvqm_get", session, expected_native=False, **target,
                                                is_attack=is_attack, storage="bridge_metadata") == selected[is_attack],
                            "AI bridge metadata did not survive clone or reopen")
                if session != clone:
                    continue
                frozen = await check.edit(clone, "track.freeze", track_index=0)
                frozen_status = await check.call("project_status", session_id=clone)
                frozen_history = await check.edit(clone, "history.status")
                await check.rejected("project_library", "Unfreeze", session_id=clone, operation="dvqm_clear",
                         options={**target, "is_attack": True, "storage": "bridge_metadata"})
                empty_target = {**target, "note_index": 1, "is_attack": True, "storage": "bridge_metadata"}
                empty_before = await check.library("dvqm_get", clone, expected_native=False, **empty_target)
                empty_after = await check.library("dvqm_clear", clone, expected_native=False, **empty_target)
                require(frozen["frozen"] and empty_before == empty_after and empty_after["is_empty"]
                    and (await check.call("project_status", session_id=clone))["dirty"] == frozen_status["dirty"]
                    and await check.edit(clone, "history.status") == frozen_history
                    and await check.library("dvqm_get", clone, expected_native=False, **target,
                                is_attack=True, storage="bridge_metadata") == selected[True],
                    "Frozen AI bridge metadata changed or rejected an empty clear")
                await check.edit(clone, "track.unfreeze", track_index=0)
                duplicated = await check.edit(clone, "note.duplicate", **target, start_tick=1440)
                duplicate_target = {**target, "note_index": duplicated["note_index"]}
                require(await check.library("dvqm_get", clone, expected_native=False, **duplicate_target,
                                            is_attack=True, storage="bridge_metadata") == selected[True],
                        "Duplicated note lost AI bridge metadata")
                split = await check.edit(clone, "note.split", **target, split_tick=144)
                split_indices = [note["note_index"] for note in split["notes"]]
                for note_index in split_indices:
                    require(await check.library("dvqm_get", clone, expected_native=False, **{**target, "note_index": note_index},
                                                is_attack=True, storage="bridge_metadata") == selected[True],
                            "Split note lost AI bridge metadata")
                await check.edit(clone, "note.join", track_index=0, part_index=0, note_indices=split_indices)
                await check.edit(clone, "undo")
                for note_index in split_indices:
                    require(await check.library("dvqm_get", clone, expected_native=False, **{**target, "note_index": note_index},
                                                is_attack=True, storage="bridge_metadata") == selected[True],
                            "Undo of note join lost AI bridge metadata")
                await check.edit(clone, "redo")
                _, structured_path = await check.save(clone, "ai-dvqm-structured")
                structured = (await check.call("project_open", path=str(structured_path)))["session_id"]
                try:
                    notes = (await check.edit(structured, "note.list", track_index=0, part_index=0))["notes"]
                    copied_index = next(note["note_index"] for note in notes if note["start_tick"] == 1440)
                    for note_index in (0, copied_index):
                        require(await check.library("dvqm_get", structured, expected_native=False, **{**target, "note_index": note_index},
                                                    is_attack=True, storage="bridge_metadata") == selected[True],
                                "Structured note edits lost AI bridge metadata after reopen")
                finally:
                    await check.close(structured)
            await check.edit(reopened, "note.remove", **target)
            await check.edit(reopened, "undo")
            require(await check.library("dvqm_get", reopened, expected_native=False, **target,
                                        is_attack=True, storage="bridge_metadata") == selected[True],
                    "Undo of note removal did not restore bridge metadata")
            cleared = await check.library("dvqm_clear", reopened, expected_native=False, **target,
                                          is_attack=True, storage="bridge_metadata")
            require(cleared["is_empty"] and await check.library("note_skill_get", reopened, **target) == skill,
                    "Clearing AI bridge metadata changed native Singing Skill")
            await check.edit(reopened, "undo")
            require(await check.library("dvqm_get", reopened, expected_native=False, **target,
                                        is_attack=True, storage="bridge_metadata") == selected[True],
                    "Undo did not restore cleared AI bridge metadata")
        finally:
            await check.close(clone)
            await check.close(reopened)
        original = path.read_bytes()
        metadata_path = "/tracks/0/parts/0/notes/0/vocaloid_bridge_ai_dvqm_v1"
        extended = await check.call("score_patch", path=str(path), output_name=check.output("ai-dvqm-unknown"),
                                    operations=[{"op": "add", "path": metadata_path + "/attack/future",
                                                 "value": {"opaque": 17}}])
        extended_session = (await check.call("project_open", path=extended["path"]))["session_id"]
        try:
            extended_history = await check.edit(extended_session, "history.status")
            for operation in ("dvqm_set", "dvqm_clear"):
                await check.rejected("project_library", "unknown fields", session_id=extended_session,
                    operation=operation, options={**target, "is_attack": True, "storage": "bridge_metadata",
                    "db_id": attack_entry["db_id"], "name_id": attack_entry["name_id"]})
            retained, _ = await check.save(extended_session, "ai-dvqm-unknown-retained")
            require(retained["tracks"][0]["parts"][0]["notes"][0]["vocaloid_bridge_ai_dvqm_v1"]["attack"]["future"]
                    == {"opaque": 17} and await check.edit(extended_session, "history.status") == extended_history,
                    "Rejected AI metadata edit lost unknown fields or changed history")
        finally:
            await check.close(extended_session)
        invalid = await check.call("score_patch", path=str(path), output_name=check.output("ai-dvqm-invalid-version"),
                                   operations=[{"op": "replace", "path": metadata_path + "/version", "value": 2}])
        invalid_session = (await check.call("project_open", path=invalid["path"]))["session_id"]
        try:
            await check.rejected("project_library", "invalid version or structure", session_id=invalid_session,
                                 operation="dvqm_get", options={**target, "storage": "bridge_metadata"})
            require(await check.library("note_skill_get", invalid_session, **target) == skill
                    and path.read_bytes() == original,
                    "Invalid AI metadata changed native skill or the source file")
        finally:
            await check.close(invalid_session)


@feature("library.note_skill_persistence", "library", "project_library", "project_edit", "score_compose", "project_save", "project_open")
async def library_note_skill_persistence(check: Acceptance) -> None:
    async with check.project(score=True) as identifier:
        target = {"track_index": 0, "part_index": 0, "note_index": 0}
        initial = await check.library("note_skill_get", identifier, **target)
        value = 0 if initial["pre_weight"] != 0 else 1
        changed = await check.library("note_skill_set", identifier, **target, pre_weight=value)
        require(changed["pre_weight"] == value, "Native note skill update did not persist", changed)
        await check.edit(identifier, "undo")
        require(await check.library("note_skill_get", identifier, **target) == initial,
                "Note skill undo did not restore the original state")
        await check.edit(identifier, "redo")
        _, path = await check.save(identifier, "note-skill")
        reopened = (await check.call("project_open", path=str(path)))["session_id"]
        require(await check.library("note_skill_get", reopened, **target) == changed,
                "Native note skill did not survive save/reopen")
        await check.close(reopened)
        await check.library("note_skill_reset", identifier, **target)


@feature("library.dvqm_guard", "library", "project_library", "score_compose", "vocaloid_features")
async def library_dvqm_guard(check: Acceptance) -> None:
    is_v7 = (await check.call("vocaloid_features"))["product"] == "VOCALOID7"
    seed = await check.call("score_compose", output_name=check.output("dvqm-seed"), title="DVQM acceptance",
                            bpm=120, notes=[{"start": 0, "duration": 1, "pitch": 60,
                                             "lyric": "\u3042", "phoneme": "a", "lang_id": 0}])
    identifier = seed["native_session"]["session_id"]
    for is_attack in (True, False):
        options = {"track_index": 0, "part_index": 0, "note_index": 0, "is_attack": is_attack}
        before = await check.library("dvqm_get", identifier, **options)
        require(before["is_empty"] is True, "DVQM test note is not initially empty", before)
        await check.rejected("project_library", "identity transaction|cannot preserve.*undo", session_id=identifier,
                             operation="dvqm_set", options={**options, "db_id": 2147483647, "name_id": 0})
        require(await check.library("dvqm_get", identifier, **options) == before,
                "Rejected DVQM assignment changed the native note")
        cleared = await check.library("dvqm_clear", identifier, **options)
        require(cleared["is_empty"] is True, "Native empty DVQM clear failed", cleared)


@feature("library.dvqm_roundtrip", "library", "project_library", "project_edit", "score_compose", "project_save", "project_open")
async def library_dvqm_roundtrip(check: Acceptance) -> None:
    import xml.etree.ElementTree as element_tree
    fixture = check.arguments.vsqx_fixture
    if fixture is None or not fixture.is_file():
        raise Blocked("A real VSQX 4 voice fixture must be supplied with --vsqx-fixture")
    namespace = {"vsq": "http://www.yamaha.co.jp/vocaloid/schema/vsq4/"}
    root = element_tree.parse(fixture).getroot()
    voice_id = root.findtext(".//vsq:vVoice/vsq:id", namespaces=namespace)
    note = root.find(".//vsq:vsPart/vsq:note", namespace)
    require(voice_id and note is not None, "VSQX fixture lacks a voice or note")
    is_v7 = (await check.call("vocaloid_features"))["product"] == "VOCALOID7"
    installed = (await check.call("voicebanks"))["voices"]
    available = [voice for voice in installed if voice["kind"] == "Dse" and voice["available_in_sequence"]]
    check.evidence("classic_requirements", {"fixture_voice_id": voice_id, "available_dse": available,
                                            "media_roundtrip": "unsupported on VOCALOID7; not exercised" if is_v7 else "required"})
    if not any(voice["comp_id"] == voice_id for voice in available):
        raise Blocked("missing_classic_bank: DVQM requires the fixture's installed available Dse voicebank " + voice_id + "; no replacement was selected")
    identifier = (await check.call("project_create", title="DVQM roundtrip", bpm=120))["session_id"]
    await check.edit(identifier, "track.create", type="Midi", name="DVQM source")
    await check.edit(identifier, "part.create", track_index=0, start_tick=0, duration_tick=1920)
    await check.edit(identifier, "voice.set", track_index=0, part_index=0,
                     scope="track" if is_v7 else "part", voice_bank_id=voice_id)
    await check.edit(identifier, "note.add", track_index=0, part_index=0, start_tick=0, duration_tick=480,
                     number=int(note.findtext("vsq:n", namespaces=namespace)),
                     lyric=note.findtext("vsq:y", namespaces=namespace), phonemes=note.findtext("vsq:p", namespaces=namespace), lang_id=1)
    assigned = {}
    for is_attack in (True, False):
        catalog = await check.library("dvqm_catalog", is_attack=is_attack, limit=256)
        if not catalog["entries"]:
            raise Blocked("An installed native Attack and Release preset is required")
        entry = next((item for item in catalog["entries"] if item["language_id"] == 1), catalog["entries"][0])
        selected = {"track_index": 0, "part_index": 0, "note_index": 0, "is_attack": is_attack}
        assigned[is_attack] = await check.library("dvqm_set", identifier, **selected, db_id=entry["db_id"],
                                                  name_id=entry["name_id"], speed=45 if is_attack else 55,
                                                  top_factor=0.75 if is_attack else 0.875, is_protected=is_attack)
        require(assigned[is_attack]["component_id"] == entry["component_id"]
                and assigned[is_attack]["level_names"] == entry["level_names"]
                and assigned[is_attack]["speed"] == (45 if is_attack else 55)
                and assigned[is_attack]["top_factor"] == (0.75 if is_attack else 0.875)
                and assigned[is_attack]["is_protected"] is is_attack,
                "Native DVQM assignment did not preserve its database and parameters", assigned[is_attack])
    clip = None
    destination = {"track_index": 0, "part_index": 0, "note_index": 0}
    if not is_v7:
        captured = await check.library("media_capture", identifier, track_index=0, part_index=0, name="DVQM " + check.run_id)
        clip = captured["clip"]
        track = (await check.edit(identifier, "track.create", type="Midi", name="DVQM target"))["track_index"]
        await check.library("media_import", identifier, clip_id=clip["clip_id"], track_index=track, position_tick=0)
        destination["track_index"] = track
    for is_attack in (True, False):
        require(await check.library("dvqm_get", identifier, **destination, is_attack=is_attack) == assigned[is_attack],
                "DVQM data changed before save")
    _, path = await check.save(identifier, "dvqm-media")
    reopened = (await check.call("project_open", path=str(path)))["session_id"]
    for is_attack in (True, False):
        require(await check.library("dvqm_get", reopened, **destination, is_attack=is_attack) == assigned[is_attack],
                "DVQM data did not survive save/reopen")
    cleared = await check.library("dvqm_clear", reopened, **destination, is_attack=True)
    require(cleared["is_empty"] is True, "Nonempty native Attack selection was not cleared", cleared)
    await check.close(reopened)
    if clip is not None:
        await check.library("media_delete", identifier, clip_id=clip["clip_id"])
    check.evidence("dvqm_media", {"clip_id": clip["clip_id"] if clip else None, "vpr": str(path), "selections": assigned,
                                  "media_roundtrip": "unsupported on VOCALOID7; not exercised" if is_v7 else "verified"})


@feature("library.dvqm_catalog", "library", "project_library")
async def library_dvqm_catalog(check: Acceptance) -> None:
    totals = {}
    for is_attack in (True, False):
        catalog = await check.library("dvqm_catalog", is_attack=is_attack, limit=3)
        require(catalog["is_attack"] is is_attack and catalog["total"] >= len(catalog["entries"])
                and len(catalog["entries"]) <= 3, "Native DVQM catalog schema is invalid", catalog)
        for entry in catalog["entries"]:
            require(isinstance(entry["db_id"], int) and isinstance(entry["name_id"], int)
                    and entry["component_id"] and all(entry["level_names"]),
                    "Native DVQM property has no usable component or level names", entry)
        totals["attack" if is_attack else "release"] = catalog["total"]
    await check.rejected("project_library", "limit", operation="dvqm_catalog", options={"limit": 0})
    check.evidence("installed_dvqm_counts", totals)


@feature("library.phoneme_table", "library", "project_library")
async def library_phoneme_table(check: Acceptance) -> None:
    expected = {
        0: r"a i M e o k k' g g' N N' s S z Z dz dZ t t' ts tS d d' n J h h\ C p\ p\' b b' p p' m m' j 4 4' w " + "N\\",
        1: "V e I i: { O: Q U u: @r eI aI OI @U aU I@ e@ U@ O@ Q@ w j b d g bh dh gh dZ v D z Z m n N r l l0 p t k ph th kh tS f T s S h @",
        2: "a ja 7 j7 o jo u ju M i e je oa u7 ue ui Mi g gp n np d dp r l rp m mp b bp s sh N Np c ch k t p h g' d' b' s' sh' c'",
        3: r"a e i o u I U j w p t k b d g B D G tS f T s x m n J l r rr L " + "j\\",
        4: r"a o 7 i u y @` i\ i` aI ei AU @U ia iE_r ua uo yE_r iAU i@U uaI uei a_n @_n i_n iE_n ua_n u@_n y_n y{_n AN @N iN iAN uAN u@N UN iUN p p_h m f t t_h n l k k_h x ts\ ts\_h s\ ts` ts`_h s` z` ts ts_h s",
    }
    manual = check.arguments.phoneme_manual_text
    manual_text = manual.read_text(encoding="utf-8") if manual is not None else None
    for language_id, reference in expected.items():
        response = await check.call("project_library", operation="phoneme_table", options={"language_id": language_id})
        table = response["result"]
        require(response["native"] is False and table["native_enumeration"] is False
                and table["language_id"] == language_id and table["source"] == "VOCALOID6 Reference Manual V6.13.0",
                "Phoneme reference provenance or language is incorrect", response)
        require(table["symbols"] == reference.split() and len(table["symbols"]) == len(set(table["symbols"])),
                "Phoneme reference differs from the manual symbol inventory", table)
        if language_id == 0:
            require(table["ai_unvoiced_symbols"] == ["N", "N'"], "Japanese AI restrictions were lost", table)
        if manual_text is not None:
            first, last = table["source_pages"][0], table["source_pages"][-1]
            start = manual_text.find(f"PAGE {first}\n")
            end = manual_text.find(f"PAGE {last + 1}\n", start + 1)
            require(start >= 0 and end > start, "Phoneme manual page boundaries were not found", [first, last])
            section = manual_text[start:end]
            missing = [symbol for symbol in table["symbols"]
                       if re.search((r"\[" + re.escape(symbol) + r"\]") if language_id == 2
                                    else (r"(?m)^" + re.escape(symbol) + r"\s"), section) is None]
            require(not missing, "Phoneme symbols were absent from their source manual pages", missing)
    if manual is not None:
        check.evidence("phoneme_manual_crosscheck", {"path": str(manual), "languages": len(expected)})
    await check.rejected("project_library", "language_id", operation="phoneme_table", options={"language_id": 99})


@feature("library.languages", "library", "project_library")
async def library_languages(check: Acceptance) -> None:
    languages = await check.library("languages")
    require(isinstance(languages, list) and languages, "Native language catalog is empty")
    require(len({entry["language_id"] for entry in languages}) == len(languages), "Duplicate language IDs")
    require(any(entry["language_id"] == 0 and entry["name"] == "JPN" for entry in languages), "Japanese G2PA language is missing")
    require(all(isinstance(entry["default_lyric"], str) and entry["default_lyric"] for entry in languages), "Language default lyrics are missing")


@feature("library.styles", "library", "project_library", "project_save", "project_open", "score_compose", "vocaloid_features")
async def library_styles(check: Acceptance) -> None:
    is_v7 = (await check.call("vocaloid_features"))["product"] == "VOCALOID7"
    catalog = await check.library("style_list", query="asa" if is_v7 else "")
    require(catalog["total"] == len(catalog["styles"]), "Native style count mismatch")
    if not catalog["styles"]:
        raise Blocked("No installed native styles; style_get/style_apply cannot be verified")
    chosen = next((style for style in catalog["styles"] if "default" in style["name"].lower()), catalog["styles"][0]) if is_v7 else catalog["styles"][0]
    details = await check.library("style_get", style_id=chosen["style_id"])
    require(details["style_id"] == chosen["style_id"] and details["midi_effect_count"] == len(details["midi_effects"]), "Style detail mismatch")
    path = Path(details["path"])
    original = path.read_bytes() if path.is_file() else None
    filtered = await check.library("style_list", query=chosen["name"])
    require(any(style["style_id"] == chosen["style_id"] for style in filtered["styles"]), "Style search lost the selected preset")
    async with check.project(score=True) as identifier:
        applied = await check.library("style_apply", identifier, track_index=0, part_index=0, **({"scope": "track"} if is_v7 else {}),
                                      style_id=chosen["style_id"], include_audio=False)
        require(applied["style_id"] == chosen["style_id"] and
            applied["content_scope" if is_v7 else "scope"] == "midi_only", "Native style application mismatch")
        _, saved = await check.save(identifier, "style")
        reopened = (await check.call("project_open", path=str(saved)))["session_id"]
        sequence, _ = read_vpr(saved)
        owner = sequence["tracks"][0] if is_v7 else sequence["tracks"][0]["parts"][0]
        require(contains_atom(owner, chosen["style_id"]), "Applied style identity did not persist in the native VPR")
        await check.close(reopened)
    if original is not None:
        require(path.read_bytes() == original, "Applying style modified the user's preset file")


@feature("library.media_catalog", "library", "project_library")
async def library_media_catalog(check: Acceptance) -> None:
    catalog = await check.library("media_list", query="")
    require(catalog["total"] == len(catalog["clips"]), "Native media catalog count mismatch")
    require(len({clip["clip_id"] for clip in catalog["clips"]}) == len(catalog["clips"]), "Duplicate native clip IDs")
    if not catalog["clips"]:
        raise Blocked("No installed native media clips; media_get cannot be verified")
    selected = catalog["clips"][0]
    details = await check.library("media_get", clip_id=selected["clip_id"])
    require(details["clip_id"] == selected["clip_id"] and details["part"] is not None, "Media part details missing")
    query = await check.library("media_list", query=selected["name"], genres=selected["genres"][:1], types=selected["types"][:1])
    require(any(clip["clip_id"] == selected["clip_id"] for clip in query["clips"]), "Native media filters lost selected clip")
    await check.rejected("project_library", "clip_id|not found", operation="media_get", options={"clip_id": "acceptance-" + check.run_id})
    external = next((clip for clip in catalog["clips"] if not clip["writable"]), None)
    if external is not None:
        source = Path(external["path"])
        original = source.read_bytes() if source.is_file() else None
        async with check.project() as identifier:
            await check.rejected("project_library", "bridge.owned|private|outside|root|path", session_id=identifier,
                                 operation="media_update", options={"clip_id": external["clip_id"], "name": "Must not be written"})
            await check.rejected("project_library", "bridge.owned|private|outside|root|path", session_id=identifier,
                                 operation="media_delete", options={"clip_id": external["clip_id"]})
        if original is not None:
            require(source.read_bytes() == original, "Rejected external-media edit changed its file")


@feature("library.style_audio", "library", "project_library", "project_audio", "project_edit", "project_status", "project_save", "project_open", "score_compose", "vocaloid_features")
async def library_style_audio(check: Acceptance) -> None:
    is_v7 = (await check.call("vocaloid_features"))["product"] == "VOCALOID7"
    catalog = await check.library("style_list", query="asa" if is_v7 else "")
    candidates = [style for style in catalog["styles"] if style["audio_effect_count"] > 0]
    chosen = next((style for style in candidates if style["name"] == "asa Warm Chorus"), candidates[0] if candidates else None)
    if chosen is None:
        raise Blocked("No installed style containing audio effects; full audio-style application cannot be verified")
    details = await check.library("style_get", style_id=chosen["style_id"])
    async with check.project(score=True) as identifier:
        metadata = [await check.audio(identifier, "effects", scope="catalog", effect_id=effect["id"])
                    for effect in details["audio_effects"]]
        check.evidence("style_effect_metadata", metadata)
        applied = await check.library("style_apply", identifier, track_index=0, part_index=0,
                                      **({"scope": "track"} if is_v7 else {}), style_id=chosen["style_id"], include_audio=True)
        require(applied["content_scope" if is_v7 else "scope"] == "complete" and applied["audio_effects_applied"] is True,
                "Full style request returned only a partial application", applied)
        effect_scope = {"scope": "track" if is_v7 else "part", "track_index": 0, "part_index": 0}
        before_inspection, _ = await check.save(identifier, "style-before-inspection")
        before_status = await check.call("project_status", session_id=identifier)
        before_history = await check.edit(identifier, "history.status")
        chain = await check.audio(identifier, "effects", **effect_scope)
        after_status = await check.call("project_status", session_id=identifier)
        after_inspection, _ = await check.save(identifier, "style-after-inspection")
        require(before_inspection == after_inspection and before_status["dirty"] == after_status["dirty"]
            and before_history == await check.edit(identifier, "history.status"),
            "Effect inspection changed project data, dirty state or history")
        require(len(chain["effects"]) == details["audio_effect_count"], "Full style omitted audio effects")
        require([entry["effect_id"] for entry in chain["effects"]] == [entry["id"] for entry in details["audio_effects"]],
                "Full style audio effect identities/order differ from the preset")
        if chosen["name"] == "asa Warm Chorus":
            chorus = next(effect for effect in chain["effects"] if effect["metadata"]["name"] == "Chorus")
            values = {item["name"]: item["value"] for item in chorus["parameters"]}
            parameter_metadata = {item["name"]: item for item in chorus["metadata"]["parameters"]}
            require(values["Type"] == 0.5 and values["Delay Offset"] == 0
                    and all(abs(parameter_metadata[name]["normalized"] - value) < 1e-6
                            for name, value in values.items() if name in parameter_metadata)
                    and parameter_metadata["Delay Offset"]["plain_min"] == parameter_metadata["Delay Offset"]["plain_max"] == 0,
                    "Chorus metadata differs from the saved mode or parameters", chorus)
            await check.audio(identifier, "set_effect", **effect_scope, action="set", slot=chorus["slot"],
                              parameters={"Dry/Wet": 0.25})
            edited_chain = await check.audio(identifier, "effects", **effect_scope)
            edited = {item["name"]: item["value"] for item in edited_chain["effects"][chorus["slot"]]["parameters"]}
            require(abs(edited["Dry/Wet"] - 0.25) <= 0.01 and all(edited[name] == value for name, value in values.items() if name != "Dry/Wet"),
                    "A single effect parameter update changed unrelated values", {"before": values, "after": edited})
            await check.edit(identifier, "undo")
            chain = await check.audio(identifier, "effects", **effect_scope)
            restored_values = {item["name"]: item["value"] for item in chain["effects"][chorus["slot"]]["parameters"]}
            require(restored_values == values, "Effect parameter undo did not restore the style", restored_values)
        _, saved = await check.save(identifier, "style-audio")
        reopened = (await check.call("project_open", path=str(saved)))["session_id"]
        persisted = await check.audio(reopened, "effects", **effect_scope)
        require([(entry["effect_id"], entry["parameters"]) for entry in persisted["effects"]]
                == [(entry["effect_id"], entry["parameters"]) for entry in chain["effects"]], "Style audio parameters did not survive save/reopen")
        await check.close(reopened)


@feature("library.style_mode_presets", "library", "project_library", "project_audio", "project_edit", "score_compose", "project_save", "project_open", "voicebanks", "vocaloid_features")
async def library_style_mode_presets(check: Acceptance) -> None:
    if (await check.call("vocaloid_features"))["product"] != "VOCALOID7":
        raise Skipped("The selected mode presets are VOCALOID7 voicebank styles")
    voices = (await check.call("voicebanks"))["voices"]
    voice = next((item for item in voices if item["name"] == "asa" and str(item["version"]).startswith("7.")
                  and item["available_in_sequence"]), None)
    if voice is None:
        raise Blocked("An available VOCALOID7 asa voicebank is required")
    styles = (await check.library("style_list", query="asa"))["styles"]
    expected = {"asa Retro (V7)": "Phaser", "asa Lead Vocal (V7)": "Reverb"}
    for style_name, effect_name in expected.items():
        style = next((item for item in styles if item["name"] == style_name), None)
        if style is None:
            raise Blocked("The installed voicebank does not contain " + style_name)
        details = await check.library("style_get", style_id=style["style_id"])
        async with check.project(score=True) as identifier:
            await check.edit(identifier, "voice.set", track_index=0, scope="track", ai_voice_bank_id=voice["comp_id"])
            before = await check.audio(identifier, "effects", scope="track", track_index=0)
            await check.library("style_apply", identifier, track_index=0, scope="track",
                                style_id=style["style_id"], include_audio=True)
            chain = await check.audio(identifier, "effects", scope="track", track_index=0)
            effect = next(item for item in chain["effects"] if item["metadata"]["name"] == effect_name)
            source = next(item for item in details["audio_effects"] if item["id"] == effect["effect_id"])
            plain = next(item["value"] for item in source["parameters"] if item["name"] == "Type")
            mode = next(item for item in effect["metadata"]["parameters"] if item["name"] == "Type")
            expected_value = (plain - mode["plain_min"]) / (mode["plain_max"] - mode["plain_min"])
            require(abs(mode["normalized"] - expected_value) < 1e-6, "Style effect mode was not applied", mode)
            _, path = await check.save(identifier, "style-mode")
            reopened = (await check.call("project_open", path=str(path)))["session_id"]
            try:
                restored = await check.audio(reopened, "effects", scope="track", track_index=0)
                require([(item["effect_id"], item["parameters"]) for item in restored["effects"]]
                        == [(item["effect_id"], item["parameters"]) for item in chain["effects"]],
                        "Style mode effect chain did not survive reopening")
            finally:
                await check.close(reopened)
            await check.edit(identifier, "undo")
            undone = await check.audio(identifier, "effects", scope="track", track_index=0)
            require([(item["effect_id"], item["parameters"]) for item in undone["effects"]]
                    == [(item["effect_id"], item["parameters"]) for item in before["effects"]],
                    "Style mode undo did not restore the previous effect chain")


@feature("library.media_ai_dvqm", "library", "project_library", "project_edit", "score_compose", "project_save", "project_open", "vocaloid_features")
async def library_media_ai_dvqm(check: Acceptance) -> None:
    if (await check.call("vocaloid_features"))["product"] == "VOCALOID7":
        raise Skipped("VOCALOID7 does not expose the native VMM media library")
    seed = await check.call("score_compose", output_name=check.output("ai-dvqm-seed"), title="AI DVQM media acceptance",
                            bpm=120, notes=[{"start": 0, "duration": 1, "pitch": 60,
                                             "lyric": "\u3042", "phoneme": "a", "lang_id": 0}])
    identifier = seed["native_session"]["session_id"]
    sequence, native = await check.save(identifier, "ai-dvqm-native")
    await check.close(identifier)
    _, members = read_vpr(native)
    note = sequence["tracks"][0]["parts"][0]["notes"][0]
    note.pop("singingSkill", None)
    note["dvqm"] = {}
    for is_attack in (True, False):
        catalog = await check.library("dvqm_catalog", is_attack=is_attack, limit=1)
        if not catalog["entries"]:
            raise Blocked("Installed native Attack and Release presets are required")
        entry = catalog["entries"][0]
        note["dvqm"]["attack" if is_attack else "release"] = {
            "compID": entry["component_id"], "levelNames": entry["level_names"],
            "speed": 45 if is_attack else 55, "topFactor": 0.75, "isProtected": is_attack,
        }
    members["Project/sequence.json"] = json.dumps(sequence, ensure_ascii=False).encode("utf-8")
    source = ROOT / "output" / check.output("ai-dvqm-input")
    with zipfile.ZipFile(source, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    original = source.read_bytes()
    identifier = (await check.call("project_open", path=str(source)))["session_id"]
    clip_id = None
    try:
        selected = {"track_index": 0, "part_index": 0, "note_index": 0}
        assigned = {is_attack: await check.library("dvqm_get", identifier, **selected, is_attack=is_attack)
                    for is_attack in (True, False)}
        require(all(not item["is_empty"] for item in assigned.values()), "Synthetic AI DVQM fixture did not load", assigned)
        clip = (await check.library("media_capture", identifier, track_index=0, part_index=0,
                                    name="AI DVQM " + check.run_id))["clip"]
        clip_id = clip["clip_id"]
        require(clip["part"]["bridge_dvqm_metadata"] is True, "AI DVQM bridge metadata was not identified", clip)
        track = (await check.edit(identifier, "track.create", type="MidiAi", name="AI DVQM target"))["track_index"]
        await check.library("media_import", identifier, clip_id=clip_id, track_index=track, position_tick=0)
        destination = {"track_index": track, "part_index": 0, "note_index": 0}
        for is_attack in (True, False):
            require(await check.library("dvqm_get", identifier, **destination, is_attack=is_attack) == assigned[is_attack],
                    "AI DVQM media data changed during import")
        _, path = await check.save(identifier, "ai-dvqm-media")
        reopened = (await check.call("project_open", path=str(path)))["session_id"]
        try:
            for is_attack in (True, False):
                require(await check.library("dvqm_get", reopened, **destination, is_attack=is_attack) == assigned[is_attack],
                        "AI DVQM media data did not survive save/reopen")
        finally:
            await check.close(reopened)
        check.evidence("ai_dvqm_media", {"clip_id": clip_id, "vpr": str(path), "selections": assigned})
    finally:
        if clip_id is not None:
            await check.library("media_delete", identifier, clip_id=clip_id)
        await check.close(identifier)
    require(source.read_bytes() == original, "AI DVQM media fixture was modified")


@feature("library.media_invalid_phoneme", "library", "project_library", "project_edit", "score_compose", "project_save", "project_open")
async def library_media_invalid_phoneme(check: Acceptance) -> None:
    seed = await check.call("score_compose", output_name=check.output("invalid-phoneme-seed"), title="Phoneme validity acceptance",
                bpm=120, notes=[{"start": 0, "duration": 1, "pitch": 60,
                         "lyric": "\u3042", "phoneme": "a", "lang_id": 0}])
    identifier = seed["native_session"]["session_id"]
    selected = {"track_index": 0, "part_index": 0, "note_index": 0}
    original = await check.edit(identifier, "note.update", **selected, phonemes="a", is_valid_phonemes=False)
    require(original["is_valid_phonemes"] is False, "Native note did not retain its invalid phoneme flag", original)
    captured = await check.library("media_capture", identifier, track_index=0, part_index=0, name="Validity " + check.run_id)
    clip = captured["clip"]
    try:
        require(clip["part"]["bridge_validity_metadata"] is True, "Private validity metadata was not identified", clip)
        clip_document = json.loads(Path(clip["path"]).read_text(encoding="utf-8"))
        require(clip_document.get("vocaloid_bridge_phoneme_validity_v1", {}).get("Version") == 1,
                "Phoneme validity metadata is not embedded in the native media file")
        track = (await check.edit(identifier, "track.create", type="MidiAi", name="Validity target"))["track_index"]
        await check.library("media_import", identifier, clip_id=clip["clip_id"], track_index=track, position_tick=0)
        destination = {"track_index": track, "part_index": 0, "note_index": 0}
        notes = (await check.edit(identifier, "note.list", track_index=track, part_index=0))["notes"]
        require(len(notes) == 1 and notes[0]["phonemes"] == "a" and notes[0]["is_valid_phonemes"] is False,
            "Invalid phoneme state did not survive native media import", notes)
        cloned = await check.call("project_clone", session_id=identifier, title="Validity clone")
        clone_notes = (await check.edit(cloned["session_id"], "note.list", track_index=track, part_index=0))["notes"]
        require(len(clone_notes) == 1 and clone_notes[0]["is_valid_phonemes"] is False,
                "Invalid phoneme state did not survive native project clone", clone_notes)
        await check.close(cloned["session_id"])
        _, path = await check.save(identifier, "invalid-phoneme-media")
        reopened = (await check.call("project_open", path=str(path)))["session_id"]
        restored = (await check.edit(reopened, "note.list", track_index=track, part_index=0))["notes"]
        require(len(restored) == 1 and restored[0]["is_valid_phonemes"] is False,
            "Invalid phoneme state did not survive save/reopen", restored)
        await check.close(reopened)
        patched = await check.call("score_patch", path=str(path), output_name=check.output("validity-title-patch"),
                                   operations=[{"op": "replace", "path": "/title", "value": "Patched validity"}])
        patched_session = (await check.call("project_open", path=patched["path"]))["session_id"]
        patched_notes = (await check.edit(patched_session, "note.list", track_index=track, part_index=0))["notes"]
        require(len(patched_notes) == 1 and patched_notes[0]["is_valid_phonemes"] is False,
                "Unrelated VPR edit did not preserve the invalid phoneme flag", patched_notes)
        await check.close(patched_session)
        adjusted = await check.call("score_patch", path=str(path), output_name=check.output("validity-note-patch"),
                                    operations=[{"op": "replace", "path": "/tracks/0/parts/0/notes/0/number", "value": 61}])
        adjusted_session = (await check.call("project_open", path=adjusted["path"]))["session_id"]
        try:
            adjusted_notes = (await check.edit(adjusted_session, "note.list", track_index=0, part_index=0))["notes"]
            other_notes = (await check.edit(adjusted_session, "note.list", track_index=track, part_index=0))["notes"]
            require(len(adjusted_notes) == 1 and adjusted_notes[0]["number"] == 61 and
                    adjusted_notes[0]["is_valid_phonemes"] is False and
                    len(other_notes) == 1 and other_notes[0]["is_valid_phonemes"] is False,
                    "Pitched invalid note or another invalid owner changed", [adjusted_notes, other_notes])
        finally:
            await check.close(adjusted_session)
        await check.rejected("score_patch", "phoneme.validity", path=str(path), output_name=check.output("validity-lyric-patch"),
                             operations=[{"op": "replace", "path": "/tracks/0/parts/0/notes/0/lyric", "value": "い"}])
        check.evidence("invalid_phoneme_media", {"clip_id": clip["clip_id"], "vpr": str(path)})
    finally:
        await check.library("media_delete", identifier, clip_id=clip["clip_id"])


@feature("library.media_secondary_voice", "library", "project_library", "project_edit", "score_compose", "voicebanks", "project_save", "project_open")
async def library_media_secondary_voice(check: Acceptance) -> None:
    await check.library("media_list")
    seed = await check.call("score_compose", output_name=check.output("secondary-seed"), title="Secondary voice acceptance",
                            bpm=120, notes=[{"start": 0, "duration": 1, "pitch": 60,
                                             "lyric": "\u3042", "phoneme": "a", "lang_id": 0}])
    identifier = seed["native_session"]["session_id"]
    selected = {"track_index": 0, "part_index": 0}
    primary = await check.edit(identifier, "voice.get", **selected)
    voices = (await check.call("voicebanks"))["voices"]
    alternative = next((voice for voice in voices if voice["kind"] == "Dnn" and voice["available_in_sequence"]
                        and voice["synthesizable_version"] and 0 in voice["lang_ids"]
                        and voice["comp_id"] != primary["ai_voice_bank_id"]), None)
    if alternative is None:
        raise Blocked("A second installed Japanese-compatible AI voice is needed for secondary-voice capture")
    assigned = await check.edit(identifier, "voice.set", **selected, secondary_ai_voice_bank_id=alternative["comp_id"])
    require(assigned["secondary_ai_voice_bank_id"] == alternative["comp_id"], "Native secondary voice was not assigned", assigned)
    captured = await check.library("media_capture", identifier, **selected, name="Secondary voice " + check.run_id)
    clip = captured["clip"]
    require(clip["part"]["ai_voice_id"] == primary["ai_voice_bank_id"]
            and clip["part"]["secondary_ai_voice_id"] == alternative["comp_id"],
            "Native media did not preserve both voice IDs", clip)
    track = (await check.edit(identifier, "track.create", type="MidiAi", name="Secondary voice target"))["track_index"]
    await check.library("media_import", identifier, clip_id=clip["clip_id"], track_index=track, position_tick=0)
    destination = {"track_index": track, "part_index": 0}
    voice = await check.edit(identifier, "voice.get", **destination)
    require(voice["ai_voice_bank_id"] == primary["ai_voice_bank_id"]
            and voice["secondary_ai_voice_bank_id"] == alternative["comp_id"], "Imported voice IDs differ", voice)
    _, path = await check.save(identifier, "secondary-voice-media")
    reopened = (await check.call("project_open", path=str(path)))["session_id"]
    voice = await check.edit(reopened, "voice.get", **destination)
    require(voice["secondary_ai_voice_bank_id"] == alternative["comp_id"], "Secondary voice did not survive save/reopen", voice)
    await check.close(reopened)
    await check.library("media_delete", identifier, clip_id=clip["clip_id"])
    check.evidence("secondary_voice_media", {"primary": primary["ai_voice_bank_id"], "secondary": alternative["comp_id"], "vpr": str(path)})


@feature("library.media_audio_trim", "library", "project_library", "project_audio", "project_edit", "project_save", "project_open")
async def library_media_audio_trim(check: Acceptance) -> None:
    import numpy as np
    source = await check.audio_input()
    original = source.read_bytes()
    metadata, samples = read_audio(source)
    async with check.project() as identifier:
        await check.edit(identifier, "tempo.set", start_tick=960, bpm=60)
        imported = await check.audio(identifier, "import_audio", path=str(source), position_tick=480)
        selected = {"track_index": imported["track_index"], "part_index": imported["part_index"]}
        trimmed = await check.audio(identifier, "edit_audio", **selected, begin_tick=240, end_tick=1680)
        require(trimmed["begin_tick"] == 240 and trimmed["end_tick"] == 1680, "Audio region was not trimmed", trimmed)
        captured = await check.library("media_capture", identifier, **selected, name="Trim capture " + check.run_id)
        clip = captured["clip"]
        path = Path(clip["part"]["wav_path"])
        actual, clipped = read_audio(path)
        expected = samples[metadata["sample_rate"] // 4:metadata["sample_rate"] * 3]
        require(actual["sample_rate"] == metadata["sample_rate"] and clipped.shape == expected.shape
                and np.allclose(clipped, expected, atol=2 / 32768, rtol=0),
                "Captured audio differs from the native trimmed region", actual)
        track = (await check.edit(identifier, "track.create", type="Audio", name="Trimmed media target"))["track_index"]
        await check.library("media_import", identifier, clip_id=clip["clip_id"], track_index=track, position_tick=0)
        _, saved = await check.save(identifier, "trimmed-media")
        reopened = (await check.call("project_open", path=str(saved)))["session_id"]
        exported = await check.audio(reopened, "export_audio", track_index=track, part_index=0,
                                     output_name=check.output("trimmed-media", ".wav"))
        _, restored = read_audio(exported["path"])
        require(restored.shape == expected.shape and np.allclose(restored, expected, atol=2 / 32768, rtol=0),
                "Trimmed media samples did not survive native import and reopen")
        await check.close(reopened)
        await check.library("media_delete", identifier, clip_id=clip["clip_id"])
        check.evidence("trimmed_audio_media", {"clip_id": clip["clip_id"], "frames": len(clipped), "vpr": str(saved)})
    require(source.read_bytes() == original, "Trimmed media capture changed its input WAV")


@feature("library.media_update", "library", "project_library", "project_edit", "score_compose", "project_save", "project_open")
async def library_media_update(check: Acceptance) -> None:
    await check.library("media_list")
    async with check.project(score=True) as identifier:
        selected = {"track_index": 0, "part_index": 0}
        notes = (await check.edit(identifier, "note.list", **selected))["notes"]
        source_part = (await check.edit(identifier, "part.list", track_index=0))["parts"][0]
        source_voice = await check.edit(identifier, "voice.get", **selected)
        kind = (await check.edit(identifier, "track.list"))["tracks"][0]["type"]
        captured = await check.library("media_capture", identifier, **selected,
                       name="Acceptance capture " + check.run_id, tempo=12000,
                       genres=["Capture"], types=["Roundtrip"])
        clip = captured["clip"]
        private_root = (ROOT / ".runtime" / "library" / "media").resolve()
        capture_path = Path(clip["path"]).resolve()
        require(captured["preview_audio_created"] is False and clip["writable"] is True
            and capture_path.is_relative_to(private_root) and capture_path.is_file()
            and capture_path.stat().st_size > 0, "Native capture did not save a private clip", captured)
        require(clip["part_type"] == kind and clip["part"]["notes"] == len(notes)
            and clip["part"]["duration"] == source_part["duration_tick"]
            and clip["part"]["ai_voice_id"] == source_voice["ai_voice_bank_id"],
            "Captured native MIDI part metadata differs from its source", clip)
        clip_id = check.arguments.owned_media_clip or clip["clip_id"]
        original = await check.library("media_get", clip_id=clip_id)
        source = Path(original["path"]).resolve()
        require(original["writable"] is True and source.is_relative_to(private_root) and source.is_file(),
            "Media fixture is not bridge-owned private media", original)
        original_bytes = source.read_bytes()
        property_path = source.with_name("property.json")
        original_properties = property_path.read_bytes()
        title = "Acceptance media " + check.run_id
        changed = await check.library("media_update", identifier, clip_id=clip_id, name=title,
                      tempo=12345, add_genres=["Acceptance"], add_types=["Acceptance"])
        require(changed["clip"]["clip_id"] == clip_id and changed["clip"]["name"] == title
            and changed["clip"]["tempo"] == 12345, "Native media property update failed", changed)
        require(set(original["genres"]) | {"Acceptance"} <= set(changed["clip"]["genres"])
            and set(original["types"]) | {"Acceptance"} <= set(changed["clip"]["types"]),
            "Native media tags were not appended without loss", changed)
        persisted = await check.library("media_get", clip_id=clip_id)
        require(persisted["name"] == title and persisted["tempo"] == 12345
            and persisted["part"] == original["part"] and source.read_bytes() == original_bytes,
            "Updated private media was not persisted or its part changed", persisted)
        saved_properties = property_path.read_bytes()
        properties = json.loads(saved_properties)
        require(saved_properties != original_properties and properties["name"] == title
            and properties["part"]["tempo"] == 12345,
            "Private media property file did not persist the update", properties)
        filtered = await check.library("media_list", query=title, genres=["Acceptance"], types=["Acceptance"])
        require(any(entry["clip_id"] == clip_id for entry in filtered["clips"]), "Updated clip cannot be found by its tags")
        target = (await check.edit(identifier, "track.create", type=kind, name="Native media destination"))["track_index"]
        imported = await check.library("media_import", identifier, clip_id=clip["clip_id"], track_index=target,
                       position_tick=2400, name="Imported acceptance media")
        require(imported["clip_id"] == clip["clip_id"] and imported["track_index"] == target
            and imported["position_tick"] == 2400 and imported["duration"] == source_part["duration_tick"]
            and len(imported["notes"]) == len(notes), "Native media import metadata mismatch", imported)
        destination = {"track_index": target, "part_index": 0}
        readback = (await check.edit(identifier, "note.list", **destination))["notes"]
        require(readback == notes, "Native media capture/import changed notes, phonemes, language or expression", readback)
        imported_voice = await check.edit(identifier, "voice.get", **destination)
        require(imported_voice["ai_voice_bank_id"] == source_voice["ai_voice_bank_id"],
            "Native media import lost the assigned voice", imported_voice)
        sequence, saved = await check.save(identifier, "media-roundtrip")
        saved_part = sequence["tracks"][target]["parts"][0]
        require(saved_part["pos"] == 2400 and saved_part["duration"] == source_part["duration_tick"]
            and len(saved_part["notes"]) == len(notes), "Saved media part lost its position, duration or notes", saved_part)
        reopened = (await check.call("project_open", path=str(saved)))["session_id"]
        require((await check.edit(reopened, "note.list", **destination))["notes"] == notes,
            "Captured/imported media notes did not survive native save/reopen")
        require((await check.edit(reopened, "voice.get", **destination))["ai_voice_bank_id"] == source_voice["ai_voice_bank_id"],
            "Captured/imported media voice did not survive native save/reopen")
        await check.close(reopened)
        deleted = await check.library("media_delete", identifier, clip_id=clip["clip_id"])
        require(deleted["deleted"] is True and deleted["clip_id"] == clip["clip_id"] and not capture_path.exists(),
            "Native private-media deletion did not remove its owned file", deleted)
        await check.rejected("project_library", "clip_id|not found", operation="media_get", options={"clip_id": clip["clip_id"]})
        require(not any(entry["clip_id"] == clip["clip_id"] for entry in
                (await check.library("media_list", query=clip["clip_id"]))["clips"]),
            "Deleted private media remains in the native catalog")
        check.evidence("disposable_media_roundtrip", {"clip_id": clip["clip_id"], "capture_path": str(capture_path),
                   "updated_clip_id": clip_id, "updated_path": str(source), "vpr": str(saved),
                   "note_count": len(notes), "captured_clip_deleted": True})


def coverage_report(check: Acceptance) -> dict[str, Any]:
    passed = [receipt for receipt in check.results if receipt["status"] == "passed"]
    calls = [call for receipt in passed for call in receipt.get("calls", []) if not call["is_error"]]
    covered = {call["tool"] for call in calls}
    operations: dict[str, list[str]] = {}
    for name in EXPECTED_OPERATIONS:
        operations[name] = sorted({call["arguments"]["operation"] for call in calls if call["tool"] == name})
    operations["offline_audio_actions"] = sorted({call["arguments"]["options"]["action"] for call in calls
                                                 if call["tool"] == "project_audio" and call["arguments"]["operation"] == "process_audio"})
    all_cases = {case.identifier for case in CASES}
    selected = {case.identifier for case in check.arguments.selected}
    return {"selection_is_full_suite": selected == all_cases, "passed_case_ids": [receipt["id"] for receipt in passed],
            "not_selected_case_ids": sorted(all_cases - selected),
            "tools_with_positive_calls_in_passing_cases": sorted(covered),
            "advertised_tools_not_positively_verified": sorted(check.tools.keys() - covered),
            "operations_in_passing_cases": operations,
            "operations_not_positively_verified": {name: sorted(expected - set(operations[name]))
                                                   for name, expected in EXPECTED_OPERATIONS.items()},
            "not_claimed": "Uncalled native members, metadata-only entries, and unimplemented matrix rows are not functionally verified."}


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--category", action="append", help="Run a category; repeat or use comma-separated names")
    parser.add_argument("--case", action="append", help="Run an exact feature ID; repeat as needed")
    parser.add_argument("--list", action="store_true", help="List planned cases without starting MCP or the host")
    parser.add_argument("--audio-fixture", type=Path, help="Existing native singing WAV; never substituted with generated fake audio")
    parser.add_argument("--mixdown-fixture", type=Path, help="Existing multi-part VPR; opened privately and never overwritten")
    parser.add_argument("--phoneme-manual-text", type=Path, help="Optional extracted official manual to cross-check phoneme symbols")
    parser.add_argument("--vsqx-fixture", type=Path, help="Actual VSQX 4 file for native legacy-format verification")
    parser.add_argument("--vsqx3-fixture", type=Path, help="Actual VSQX 3 file for native legacy-format verification")
    parser.add_argument("--ppsf-fixture", type=Path, help="Actual PPSF V2 file for native legacy-format verification")
    parser.add_argument("--ppsf3-fixture", type=Path, help="Actual PPSF V3 file for native legacy-format verification")
    parser.add_argument("--owned-media-clip", help="Optional disposable bridge-owned clip ID to update; otherwise capture a native fixture")
    arguments = parser.parse_args()
    categories = {category for value in arguments.category or [] for category in value.split(",")}
    unknown = categories - {item.category for item in CASES}
    if unknown:
        parser.error("Unknown categories: " + ", ".join(sorted(unknown)))
    unknown_ids = set(arguments.case or []) - {item.identifier for item in CASES}
    if unknown_ids:
        parser.error("Unknown feature IDs: " + ", ".join(sorted(unknown_ids)))
    arguments.selected = [item for item in CASES if (not categories or item.category in categories)
                          and (not arguments.case or item.identifier in arguments.case)]
    if not arguments.selected:
        parser.error("No cases selected")
    return arguments


async def run(arguments: argparse.Namespace) -> int:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    import win32gui

    check = Acceptance(arguments)
    check.foreground_initial = win32gui.GetForegroundWindow()
    check.monitor = asyncio.create_task(check.watch_foreground())
    parameters = StdioServerParameters(command=sys.executable, args=["-m", "vocaloid_bridge"], cwd=str(ROOT),
        env={**os.environ, "VOCALOID_WORKSPACE": str(ROOT), "PYTHONUTF8": "1", "VOCALOID_TEMP_CLEANUP": "0"})
    try:
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=240)) as client:
                check.client = client
                await client.initialize()
                listed = await client.list_tools()
                check.tools = {item.name: item for item in listed.tools}
                for item in arguments.selected:
                    await check.execute(item)
                cleanup = {"id": "transport.cleanup", "category": "transport", "status": "passed", "run_id": check.run_id}
                check.active = cleanup
                for identifier in sorted(check.sessions.copy()):
                    try:
                        await check.close(identifier)
                    except Exception as error:
                        cleanup.update(status="failed", reason=str(error))
                try:
                    final_status = await check.call("vocaloid_status")
                    require(final_status["sessions"] == 0, "Native sessions remain", final_status)
                    require(not check.owned_foreground_changes, "An owned MCP/native process activated a foreground window")
                except Exception as error:
                    cleanup.update(status="failed", reason=str(error))
                check.record(cleanup)
                check.active = None
    except Exception as error:
        check.transport_error = f"{type(error).__name__}: {error}"
    finally:
        check.monitor.cancel()
        try:
            await check.monitor
        except asyncio.CancelledError:
            pass
    completed = {result["id"] for result in check.results}
    for item in arguments.selected:
        if item.identifier not in completed:
            check.record({"id": item.identifier, "category": item.category, "run_id": check.run_id,
                          "status": "blocked", "reason": "MCP transport unavailable: " + str(check.transport_error)})
    counts = Counter(result["status"] for result in check.results)
    report = {"run_id": check.run_id, "transport": "mcp-stdio", "host_built_by_runner": False,
              "counts": dict(counts), "selected_feature_ids": [item.identifier for item in arguments.selected],
              "foreground_before": check.foreground_initial, "foreground_after": win32gui.GetForegroundWindow(),
              "foreground_changes": check.foreground_changes, "transport_error": check.transport_error,
              "owned_foreground_changes": check.owned_foreground_changes, "owned_pids": sorted(check.owned_pids),
              "remaining_owned_sessions": sorted(check.sessions), "results": check.results,
              "coverage_claim": "Only passing case IDs have runtime evidence; metadata availability is not functional verification."}
    report["coverage"] = coverage_report(check)
    destination = check.directory / "summary.json"
    destination.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps({"summary": str(destination), "counts": dict(counts), "transport_error": check.transport_error,
                      "coverage": report["coverage"]}), flush=True)
    if counts["failed"] or check.transport_error or check.owned_foreground_changes:
        return 1
    incomplete = report["coverage"]["selection_is_full_suite"] and (
        report["coverage"]["advertised_tools_not_positively_verified"]
        or any(report["coverage"]["operations_not_positively_verified"].values()))
    return 2 if counts["blocked"] or counts["skipped"] or counts["unsupported"] or incomplete else 0


def main() -> int:
    arguments = parse_arguments()
    if arguments.list:
        for item in arguments.selected:
            print(f"{item.category:14} {item.identifier}")
        return 0
    try:
        return asyncio.run(run(arguments))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
