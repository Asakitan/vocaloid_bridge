"""Structured edits for editor-authored VOCALOID6 VPR ZIP projects."""

from __future__ import annotations

from contextlib import contextmanager
from copy import copy, deepcopy
import json
import math
import msvcrt
import os
from pathlib import Path
from typing import Any
import zipfile

import jsonpatch
import jsonpointer
import win32con
import win32file

from .music import PPQ, _exclusive_output, _integer, _notes, _number, _source, _ticks, _workspace


SEQUENCE_MEMBER = "Project/sequence.json"
PHONEME_VALIDITY_MEMBER = "vocaloid_bridge/phoneme-validity-v1.json"
_EDITOR_AI_NOTE = {
    "lyric": "\u3042", "phoneme": "a", "langID": 0,
    "isProtected": False, "isAiVibratoEnabled": True,
    "pos": 480, "duration": 240, "number": 59, "velocity": 64,
    "exp": {"accent": 50, "decay": 50, "bendDepth": 0, "bendLength": 0, "opening": 127},
    "aiExp": {name: 0.5 for name in (
        "pitchFine", "pitchDriftStart", "pitchDriftEnd", "pitchScalingCenter",
        "pitchScalingOrigin", "pitchTransitionStart", "pitchTransitionEnd",
        "amplitudeWhole", "amplitudeStart", "amplitudeEnd",
        "vibratoLeadingDepth", "vibratoFollowingDepth",
    )},
    "singingSkill": {"duration": 80, "weight": {"pre": 64, "post": 64}},
    "vibrato": {"type": 0, "duration": 160, "depths": [{"pos": 0, "value": 0}],
                "rates": [{"pos": 0, "value": 50}]},
}
_NOTE_FIELDS = {"pos", "duration", "number", "lyric", "phoneme", "velocity", "langID"}


@contextmanager
def _source_archive(workspace: Path, path: str | Path):
    """Hold one read-only source handle against concurrent writes and replacement."""
    source = _source(workspace, path)
    handle = win32file.CreateFile(str(source), win32con.GENERIC_READ, win32con.FILE_SHARE_READ,
                                  None, win32con.OPEN_EXISTING, win32con.FILE_ATTRIBUTE_NORMAL, None)
    try:
        descriptor = msvcrt.open_osfhandle(int(handle), os.O_RDONLY | os.O_BINARY)
        handle.Detach()
        try:
            stream = os.fdopen(descriptor, "rb")
        except BaseException:
            os.close(descriptor)
            raise
        with stream, zipfile.ZipFile(stream, "r") as archive:
            yield archive
    finally:
        handle.Close()


def _invalid_constant(value: str) -> None:
    raise ValueError(f"nonfinite JSON number: {value}")


def _validate_phoneme_validity(data: dict, payload: bytes,
                               note_origins: tuple[int, int, list[int | None]] | None = None) -> None:
    try:
        metadata = json.loads(payload, parse_constant=_invalid_constant)
        if (not isinstance(metadata, dict) or metadata.get("Format") != "vocaloid-bridge-phoneme-validity"
                or metadata.get("Version") != 1 or not isinstance(metadata.get("Notes"), list)
                or len(metadata["Notes"]) > 65536):
            raise ValueError("invalid metadata format")
        seen = set()
        for entry in metadata["Notes"]:
            indices = tuple(entry[name] for name in ("TrackIndex", "PartIndex", "NoteIndex"))
            if any(isinstance(index, bool) or not isinstance(index, int) or index < 0 for index in indices) or indices in seen:
                raise ValueError("invalid or duplicate note reference")
            seen.add(indices)
            expected = entry["Note"]
            if expected["IsValid"] is not False:
                raise ValueError("invalid note validity")
            track_index, part_index, note_index = indices
            if note_origins is not None and (track_index, part_index) == note_origins[:2]:
                origins = note_origins[2]
                if note_index >= len(origins) or origins[note_index] != note_index:
                    raise ValueError("referenced note identity changed")
            note = data["tracks"][track_index]["parts"][part_index]["notes"][note_index]
            fields = (("pos", "Position"), ("duration", "Duration"), ("number", "Number"),
                      ("lyric", "Lyric"), ("phoneme", "Phonemes"), ("langID", "LanguageId"))
            if any(not _note_snapshot_equal(note[native], expected[saved]) for native, saved in fields):
                raise ValueError("referenced note changed")
    except (KeyError, IndexError, TypeError, ValueError, UnicodeError) as error:
        raise ValueError("VPR phoneme-validity metadata conflicts with this edit; use native project_edit for affected notes") from error


def _merge(destination: dict, extras: dict) -> None:
    for key, value in extras.items():
        if isinstance(value, dict) and isinstance(destination.get(key), dict):
            _merge(destination[key], value)
        else:
            destination[key] = deepcopy(value)


def _part(data: dict, track_index: int, part_index: int) -> tuple[dict, dict]:
    _integer(track_index, "track_index", 0, 2**31 - 1)
    _integer(part_index, "part_index", 0, 2**31 - 1)
    tracks = data.get("tracks")
    if not isinstance(tracks, list) or track_index >= len(tracks) or not isinstance(tracks[track_index], dict):
        raise ValueError("track_index does not select a track")
    track = tracks[track_index]
    parts = track.get("parts")
    if not isinstance(parts, list) or part_index >= len(parts) or not isinstance(parts[part_index], dict):
        raise ValueError("part_index does not select a part")
    return track, parts[part_index]


def _extended_points(value: Any) -> bool:
    return isinstance(value, list) and any(
        isinstance(item, dict) and any(key not in {"pos", "value"} for key in item)
        for item in value)


def _guard_note_replacement(data: dict) -> None:
    """Keep file-level note replacement inside the existing extension boundaries."""
    tracks = data.get("tracks")
    if not isinstance(tracks, list):
        return
    for track in tracks:
        if not isinstance(track, dict):
            continue
        for name in ("volume", "panpot"):
            lane = track.get(name)
            if isinstance(lane, dict) and _extended_points(lane.get("events")):
                raise ValueError("note replacement is guarded for track automation extensions")
        parts = track.get("parts")
        if not isinstance(parts, list):
            continue
        for part in parts:
            if not isinstance(part, dict):
                continue
            controllers = part.get("controllers")
            if isinstance(controllers, list) and any(
                    isinstance(lane, dict) and _extended_points(lane.get("events")) for lane in controllers):
                raise ValueError("note replacement is guarded for controller extensions")
            existing_notes = part.get("notes")
            if isinstance(existing_notes, list) and any(
                    isinstance(note, dict) and _extended_points(note.get("directPitches")) for note in existing_notes):
                raise ValueError("note replacement is guarded for direct pitch item extensions")


def _note_snapshot_equal(expected: Any, actual: Any) -> bool:
    # JSON distinguishes booleans from numbers, unlike Python's ==.
    try:
        options = {"ensure_ascii": False, "allow_nan": False, "sort_keys": True, "separators": (",", ":")}
        return json.dumps(expected, **options) == json.dumps(actual, **options)
    except (TypeError, ValueError):
        return False


def _replace_notes(data: dict, notes: list[dict], track_index: int, part_index: int) -> list[int | None]:
    track, part = _part(data, track_index, part_index)
    _guard_note_replacement(data)
    prepared = _notes(notes, monophonic=True)
    prototypes = part.get("notes", [])
    if not isinstance(prototypes, list):
        raise ValueError("part.notes must be a list")
    is_ai = track.get("type") == 2 and isinstance(part.get("aiVoice"), dict)
    if not is_ai and prototypes:
        if not isinstance(prototypes[0], dict) or not _NOTE_FIELDS <= prototypes[0].keys():
            raise ValueError("template note lacks the verified native note fields")
        legacy_prototype = prototypes[0]
    elif not is_ai and prepared:
        raise ValueError("no native note prototype; use an editor-authored AI or populated vocal template")
    else:
        legacy_prototype = {}
    available_languages = {entry.get("langID") for entry in part.get("aiVoice", {}).get("langIDs", []) if isinstance(entry, dict)}
    native_notes = []
    origins: list[int | None] = []
    used: set[int] = set()
    for note in prepared:
        extras = note.get("raw", {})
        if _NOTE_FIELDS.intersection(extras):
            raise ValueError("raw extras cannot override timing, pitch, lyric, phoneme, velocity or langID")
        selected = note.get("source")
        source_index = None
        if selected is not None:
            if not is_ai:
                raise ValueError("note source selector requires an AI part")
            if not isinstance(selected, dict) or set(selected) != {"index", "expected"}:
                raise ValueError("note source selector requires index and expected")
            source_index = selected["index"]
            if (isinstance(source_index, bool) or not isinstance(source_index, int) or
                    not 0 <= source_index < len(prototypes) or source_index in used):
                raise ValueError("note source selector index is invalid or repeated")
            source_note = prototypes[source_index]
            if (not isinstance(source_note, dict) or not _NOTE_FIELDS <= source_note.keys() or
                    not isinstance(selected["expected"], dict) or
                    not _note_snapshot_equal(selected["expected"], source_note)):
                raise ValueError("note source selector snapshot is stale or invalid")
            used.add(source_index)
            native = deepcopy(source_note)
        elif is_ai:
            native = deepcopy(_EDITOR_AI_NOTE)
            # Preserve the established part language default, not a note's opaque fields.
            if prototypes and isinstance(prototypes[0], dict):
                native["langID"] = prototypes[0].get("langID", native["langID"])
        else:
            native = deepcopy(legacy_prototype)
        _merge(native, extras)
        native.update(pos=note["_pos"], duration=note["_duration"], number=note["pitch"], lyric=note["lyric"])
        native["velocity"] = _integer(note.get("velocity", native.get("velocity", 64)), "note.velocity", 1, 127)
        native["langID"] = _integer(note.get("lang_id", native.get("langID", 0)), "note.lang_id", 0, 127)
        if available_languages and native["langID"] not in available_languages:
            raise ValueError("note.lang_id is absent from this part's aiVoice.langIDs")
        if ("phoneme" not in note and source_index is not None and
                note["lyric"] == prototypes[source_index]["lyric"] and
                native["langID"] == prototypes[source_index]["langID"]):
            native["phoneme"] = prototypes[source_index]["phoneme"]
        else:
            native["phoneme"] = note.get("phoneme", "")
        native_notes.append(native)
        origins.append(source_index)
    duration = part.get("duration", 0)
    if isinstance(duration, bool) or not isinstance(duration, int) or duration < 0:
        raise ValueError("native part.duration must be a nonnegative integer")
    part["notes"] = native_notes
    part["duration"] = max(duration, max((note["pos"] + note["duration"] for note in native_notes), default=0))
    return origins


def _tempo_events(data: dict, events: list[dict]) -> None:
    if not isinstance(events, list) or not events:
        raise ValueError("tempo events must be a nonempty list beginning at beat zero")
    master = data.get("masterTrack")
    tempo = master.get("tempo") if isinstance(master, dict) else None
    if not isinstance(tempo, dict) or not isinstance(tempo.get("events"), list):
        raise ValueError("project has no native masterTrack.tempo.events structure")
    existing = {}
    for event in tempo["events"]:
        if not isinstance(event, dict) or isinstance(event.get("pos"), bool) or not isinstance(event.get("pos"), int):
            raise ValueError("existing tempo events must have integer positions")
        position = event["pos"]
        if position in existing:
            raise ValueError("existing tempo event positions must be distinct")
        existing[position] = event
    replacements = []
    positions = set()
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("each tempo event must be an object with start and bpm")
        position = _ticks(event.get("start"), "tempo.start")
        scaled = _number(event.get("bpm"), "tempo.bpm", positive=True) * 100
        if not math.isfinite(scaled) or scaled < 0.5:
            raise ValueError("tempo.bpm cannot be represented in hundredths of BPM")
        if position in positions:
            raise ValueError("tempo events collide after tick quantization")
        positions.add(position)
        # The selected tick is the file-level identity policy. A new event
        # starts without another event's unknown fields.
        native = deepcopy(existing.get(position, {}))
        native.update(pos=position, value=math.floor(scaled + 0.5))
        replacements.append(native)
    replacements.sort(key=lambda event: event["pos"])
    if replacements[0]["pos"] != 0:
        raise ValueError("tempo map must begin at beat zero")
    tempo["events"] = replacements
    if isinstance(tempo.get("global"), dict):
        tempo["global"].update(isEnabled=False, value=replacements[0]["value"])


def _patch_touches_note_tree(path: str) -> bool:
    parts = jsonpointer.JsonPointer(path).get_parts()
    if not parts:
        return True
    if parts[0] != "tracks":
        return False
    if len(parts) <= 2:
        return True
    if parts[2] != "parts":
        return False
    if len(parts) <= 4:
        return True
    return parts[4] == "notes"


def _tracked_subpaths(value: Any, records: list[tuple[dict, dict]]) -> list[tuple[tuple[Any, ...], dict, dict]]:
    by_identity = {id(note): (note, entry) for note, entry in records}
    result = []
    stack = [(value, ())]
    seen = set()
    while stack:
        current, path = stack.pop()
        if not isinstance(current, (dict, list)):
            continue
        identity = id(current)
        if identity in seen:
            continue
        seen.add(identity)
        found = by_identity.get(identity)
        if found is not None and current is found[0]:
            result.append((path, found[0], found[1]))
        if isinstance(current, dict):
            stack.extend((child, path + (key,)) for key, child in current.items())
        else:
            stack.extend((child, path + (index,)) for index, child in enumerate(current))
    return result


def _patch_validity(data: dict, payload: bytes | None, operations: list[dict]) -> tuple[dict, bytes | None]:
    """Apply RFC 6902 on a private tree while tracking invalid-note provenance."""
    patch = jsonpatch.JsonPatch(deepcopy(operations))
    working = deepcopy(data)
    metadata = None
    records: list[tuple[dict, dict]] = []
    if payload is not None:
        _validate_phoneme_validity(data, payload)
        metadata = json.loads(payload, parse_constant=_invalid_constant)
        for entry in metadata["Notes"]:
            track = working["tracks"][entry["TrackIndex"]]
            part = track["parts"][entry["PartIndex"]]
            note = part["notes"][entry["NoteIndex"]]
            records.append((note, deepcopy(entry)))
    for operation in patch:
        kind = operation["op"]
        if kind != "test" and isinstance(working, dict):
            touches = _patch_touches_note_tree(operation["path"])
            if kind == "move":
                touches = touches or _patch_touches_note_tree(operation["from"])
            if touches:
                _guard_note_replacement(working)

        matches = []
        target_parent = target_key = None
        if kind in ("copy", "move") and records:
            source = jsonpointer.resolve_pointer(working, operation["from"])
            matches = _tracked_subpaths(source, records)
            if kind == "copy" and matches:
                target_parent, target_key = jsonpointer.JsonPointer(operation["path"]).to_last(working)
                if isinstance(target_parent, list) and target_key == "-":
                    target_key = len(target_parent)
        working = jsonpatch.JsonPatch([operation]).apply(working, in_place=True)
        if kind == "copy" and matches:
            copied = working if target_key is None else target_parent[target_key]
            for path, original, entry in matches:
                clone = copied
                for component in path:
                    clone = clone[component]
                if not isinstance(clone, dict) or clone is original:
                    raise ValueError("phoneme-validity copy did not create an independent note")
                records.append((clone, deepcopy(entry)))
            if len(records) > 65536:
                raise ValueError("VPR has too many phoneme-validity note references")
        elif kind == "move" and matches:
            surviving = {id(note) for _, note, _ in _tracked_subpaths(working, records)}
            if any(id(note) not in surviving for _, note, _ in matches):
                raise ValueError("phoneme-validity note identity was lost during patch move")

    if not isinstance(working, dict):
        raise ValueError("project data must be an object")
    if metadata is None:
        return working, None

    wanted = {id(note) for note, _ in records}
    locations: dict[int, tuple[int, int, int]] = {}
    tracks = working.get("tracks")
    if isinstance(tracks, list):
        for track_index, track in enumerate(tracks):
            parts = track.get("parts") if isinstance(track, dict) else None
            if not isinstance(parts, list):
                continue
            for part_index, part in enumerate(parts):
                notes = part.get("notes") if isinstance(part, dict) else None
                if not isinstance(notes, list):
                    continue
                for note_index, note in enumerate(notes):
                    identity = id(note)
                    if identity in wanted:
                        if identity in locations:
                            raise ValueError("phoneme-validity note has ambiguous patch identity")
                        locations[identity] = (track_index, part_index, note_index)
    entries = []
    try:
        for note, previous in records:
            position = locations.get(id(note))
            if position is None:
                continue
            entry = deepcopy(previous)
            expected = entry["Note"]
            for native, saved in (("lyric", "Lyric"), ("phoneme", "Phonemes"), ("langID", "LanguageId")):
                if not _note_snapshot_equal(note[native], expected[saved]):
                    raise ValueError("phoneme-validity lyric, phoneme or language changed during patch")
            for native, saved in (("pos", "Position"), ("duration", "Duration"), ("number", "Number")):
                expected[saved] = note[native]
            entry["TrackIndex"], entry["PartIndex"], entry["NoteIndex"] = position
            entries.append(entry)
    except (KeyError, TypeError) as error:
        raise ValueError("phoneme-validity note fields are missing after patch") from error
    updated = deepcopy(metadata)
    updated["Notes"] = entries
    result_payload = (payload if _note_snapshot_equal(updated, metadata) else
                      json.dumps(updated, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8"))
    _validate_phoneme_validity(working, result_payload)
    return working, result_payload


class ProjectStore:
    """Read VPR sources and create new files under workspace/output."""

    def __init__(self, workspace: Path):
        self.workspace = _workspace(workspace)

    @staticmethod
    def _read_archive(archive: zipfile.ZipFile) -> dict:
        if archive.namelist().count(SEQUENCE_MEMBER) != 1:
            raise ValueError("VPR must contain exactly one Project/sequence.json")
        data = json.loads(archive.read(SEQUENCE_MEMBER).decode("utf-8-sig"), parse_constant=_invalid_constant)
        if not isinstance(data, dict):
            raise ValueError("Project/sequence.json must contain an object")
        return data

    def read(self, path: str | Path) -> dict:
        with _source_archive(self.workspace, path) as archive:
            return self._read_archive(archive)

    def _summary(self, path: Path, data: dict) -> dict:
        tracks = []
        for index, track in enumerate(data.get("tracks", []) if isinstance(data.get("tracks"), list) else []):
            if not isinstance(track, dict):
                continue
            parts = []
            for part_index, part in enumerate(track.get("parts", []) if isinstance(track.get("parts"), list) else []):
                if not isinstance(part, dict):
                    continue
                notes = part.get("notes")
                parts.append({"index": part_index, "pos": part.get("pos"), "duration": part.get("duration"),
                              "note_count": len(notes) if isinstance(notes, list) else 0,
                              "aiVoice": deepcopy(part.get("aiVoice"))})
            tracks.append({"index": index, "name": track.get("name"), "type": track.get("type"), "parts": parts})
        master = data.get("masterTrack")
        tempo = master.get("tempo", {}) if isinstance(master, dict) else {}
        return {"path": str(path), "format": "vpr", "title": data.get("title"), "version": deepcopy(data.get("version")),
                "ticks_per_beat": PPQ, "voices": deepcopy(data.get("voices", [])),
                "tempo": deepcopy(tempo), "track_count": len(tracks),
                "note_count": sum(part["note_count"] for track in tracks for part in track["parts"]), "tracks": tracks}

    def summary(self, path: str | Path) -> dict:
        source = _source(self.workspace, path)
        return self._summary(source, self.read(source))

    def inspect(self, path: str | Path, pointer: str = "") -> Any:
        if not isinstance(pointer, str):
            raise ValueError("pointer must be an RFC 6901 string")
        return jsonpointer.resolve_pointer(self.read(path), pointer)

    def _write_archive(self, archive: zipfile.ZipFile, data: dict, output_name: str,
                       note_origins: tuple[int, int, list[int | None]] | None = None,
                       validity_override: bytes | None = None) -> dict:
        if not isinstance(data, dict):
            raise ValueError("project data must be an object")
        serialized = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        if archive.namelist().count(SEQUENCE_MEMBER) != 1:
            raise ValueError("VPR must contain exactly one Project/sequence.json")
        validity_count = archive.namelist().count(PHONEME_VALIDITY_MEMBER)
        if validity_count > 1:
            raise ValueError("VPR has duplicate phoneme-validity metadata")
        if validity_override is not None and not validity_count:
            raise ValueError("VPR has no phoneme-validity metadata to update")
        if validity_count:
            validity = validity_override if validity_override is not None else archive.read(PHONEME_VALIDITY_MEMBER)
            _validate_phoneme_validity(data, validity, note_origins)
        with _exclusive_output(self.workspace, output_name, (".vpr",)) as (destination, handle):
            with zipfile.ZipFile(handle, "w") as result:
                result.comment = archive.comment
                for member in archive.infolist():
                    if member.filename == SEQUENCE_MEMBER:
                        payload = serialized
                    elif member.filename == PHONEME_VALIDITY_MEMBER and validity_override is not None:
                        payload = validity_override
                    else:
                        payload = archive.read(member)
                    result.writestr(copy(member), payload)
        return {"path": str(destination), "summary": self._summary(destination, data)}

    def write_copy(self, source: str | Path, data: dict, output_name: str) -> dict:
        with _source_archive(self.workspace, source) as archive:
            return self._write_archive(archive, data, output_name)

    def patch(self, source: str, operations: list[dict], output_name: str) -> dict:
        if not isinstance(operations, list) or not all(isinstance(operation, dict) for operation in operations):
            raise ValueError("operations must be a JSON Patch array")
        with _source_archive(self.workspace, source) as archive:
            data = self._read_archive(archive)
            count = archive.namelist().count(PHONEME_VALIDITY_MEMBER)
            if count > 1:
                raise ValueError("VPR has duplicate phoneme-validity metadata")
            validity = archive.read(PHONEME_VALIDITY_MEMBER) if count else None
            data, updated = _patch_validity(data, validity, operations)
            return self._write_archive(archive, data, output_name, validity_override=updated)

    def _read_note_edit_archive(self, archive: zipfile.ZipFile) -> dict:
        data = self._read_archive(archive)
        count = archive.namelist().count(PHONEME_VALIDITY_MEMBER)
        if count > 1:
            raise ValueError("VPR has duplicate phoneme-validity metadata")
        if count:
            _validate_phoneme_validity(data, archive.read(PHONEME_VALIDITY_MEMBER))
        return data

    @contextmanager
    def prepare_compose(self, template: str, title: str, bpm: float, notes: list[dict],
                        track_index: int = 0, part_index: int = 0, voice_comp_id: str | None = None):
        if not isinstance(title, str):
            raise ValueError("title must be a string")
        with _source_archive(self.workspace, template) as archive:
            data = self._read_note_edit_archive(archive)
            _, part = _part(data, track_index, part_index)
            if voice_comp_id is not None:
                if not isinstance(voice_comp_id, str) or not voice_comp_id:
                    raise ValueError("voice_comp_id must be a nonempty string")
                voices = data.get("voices")
                if not isinstance(voices, list) or not any(isinstance(voice, dict) and voice.get("compID") == voice_comp_id for voice in voices):
                    raise ValueError("voice_comp_id must already exist in the project's voices list")
                if not isinstance(part.get("aiVoice"), dict):
                    raise ValueError("selected part has no aiVoice")
                part["aiVoice"]["compID"] = voice_comp_id
            origins = _replace_notes(data, notes, track_index, part_index)
            _tempo_events(data, [{"start": 0, "bpm": bpm}])
            data["title"] = title
            yield archive, data, (track_index, part_index, origins)

    def compose(self, template: str, output_name: str, title: str, bpm: float, notes: list[dict],
                track_index: int = 0, part_index: int = 0, voice_comp_id: str | None = None) -> dict:
        with self.prepare_compose(template, title, bpm, notes, track_index, part_index, voice_comp_id) as (archive, data, origins):
            return self._write_archive(archive, data, output_name, origins)

    @contextmanager
    def prepare_note_edit(self, source: str, notes: list[dict], track_index: int = 0, part_index: int = 0):
        with _source_archive(self.workspace, source) as archive:
            data = self._read_note_edit_archive(archive)
            origins = _replace_notes(data, notes, track_index, part_index)
            yield archive, data, (track_index, part_index, origins)

    def edit_notes(self, source: str, output_name: str, notes: list[dict], track_index: int = 0, part_index: int = 0) -> dict:
        with self.prepare_note_edit(source, notes, track_index, part_index) as (archive, data, origins):
            return self._write_archive(archive, data, output_name, origins)

    def set_curve(self, source: str, output_name: str, controller: str, events: list[dict],
                  track_index: int = 0, part_index: int = 0) -> dict:
        if not isinstance(controller, str) or not controller:
            raise ValueError("controller must be an existing native controller name")
        if not isinstance(events, list):
            raise ValueError("curve events must be a list")
        with _source_archive(self.workspace, source) as archive:
            data = self._read_archive(archive)
            _, part = _part(data, track_index, part_index)
            controllers = part.get("controllers")
            if not isinstance(controllers, list):
                raise ValueError("no observed controller structure in this part; use an editor-authored curve or JSON Patch")
            matches = [entry for entry in controllers if isinstance(entry, dict) and entry.get("name") == controller]
            if len(matches) != 1 or not isinstance(matches[0].get("events"), list) or not matches[0]["events"]:
                raise ValueError("controller must have a unique existing native event prototype")
            target = matches[0]
            prototype = target["events"][0]
            if not isinstance(prototype, dict) or not isinstance(prototype.get("pos"), int) or isinstance(prototype.get("pos"), bool):
                raise ValueError("controller has no verified pos/value event structure")
            prototype_value = prototype.get("value")
            if isinstance(prototype_value, bool) or not isinstance(prototype_value, (int, float)):
                raise ValueError("controller prototype value must be numeric")
            existing = {}
            for old in target["events"]:
                if not isinstance(old, dict) or isinstance(old.get("pos"), bool) or not isinstance(old.get("pos"), int):
                    raise ValueError("existing controller events must have integer positions")
                position = old["pos"]
                if position in existing:
                    raise ValueError("existing controller event positions must be distinct")
                existing[position] = old
            replacements = []
            positions = set()
            for event in events:
                if not isinstance(event, dict):
                    raise ValueError("each curve event must be an object with start and value")
                position = _ticks(event.get("start"), "curve.start")
                value = event.get("value")
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError("curve.value must be a finite number")
                try:
                    finite = math.isfinite(value)
                except OverflowError:
                    finite = False
                if not finite or (isinstance(prototype_value, int) and not isinstance(value, int)):
                    raise ValueError("curve.value must be finite and match the native numeric type")
                if position in positions:
                    raise ValueError("curve events collide after tick quantization")
                positions.add(position)
                # Keep unknown fields only on an event at the selected source tick.
                native = deepcopy(existing.get(position, {}))
                native.update(pos=position, value=value)
                replacements.append(native)
            target["events"] = sorted(replacements, key=lambda event: event["pos"])
            return self._write_archive(archive, data, output_name)

    def set_tempo(self, source: str, output_name: str, events: list[dict]) -> dict:
        with _source_archive(self.workspace, source) as archive:
            data = self._read_archive(archive)
            _tempo_events(data, events)
            return self._write_archive(archive, data, output_name)
