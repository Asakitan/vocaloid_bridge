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


def _validate_phoneme_validity(data: dict, payload: bytes) -> None:
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
            note = data["tracks"][track_index]["parts"][part_index]["notes"][note_index]
            fields = (("pos", "Position"), ("duration", "Duration"), ("number", "Number"),
                      ("lyric", "Lyric"), ("phoneme", "Phonemes"), ("langID", "LanguageId"))
            if any(note[native] != expected[saved] for native, saved in fields):
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


def _replace_notes(data: dict, notes: list[dict], track_index: int, part_index: int) -> None:
    track, part = _part(data, track_index, part_index)
    prepared = _notes(notes, monophonic=True)
    prototypes = part.get("notes", [])
    if not isinstance(prototypes, list):
        raise ValueError("part.notes must be a list")
    if prototypes:
        if not isinstance(prototypes[0], dict) or not _NOTE_FIELDS <= prototypes[0].keys():
            raise ValueError("template note lacks the verified native note fields")
        prototype = prototypes[0]
    elif track.get("type") == 2 and isinstance(part.get("aiVoice"), dict):
        prototype = _EDITOR_AI_NOTE
    elif prepared:
        raise ValueError("no native note prototype; use an editor-authored AI or populated vocal template")
    else:
        prototype = {}
    available_languages = {entry.get("langID") for entry in part.get("aiVoice", {}).get("langIDs", []) if isinstance(entry, dict)}
    native_notes = []
    for note in prepared:
        extras = note.get("raw", {})
        if _NOTE_FIELDS.intersection(extras):
            raise ValueError("raw extras cannot override timing, pitch, lyric, phoneme, velocity or langID")
        native = deepcopy(prototype)
        _merge(native, extras)
        native.update(pos=note["_pos"], duration=note["_duration"], number=note["pitch"],
                      lyric=note["lyric"], phoneme=note.get("phoneme", ""))
        native["velocity"] = _integer(note.get("velocity", native.get("velocity", 64)), "note.velocity", 1, 127)
        native["langID"] = _integer(note.get("lang_id", native.get("langID", 0)), "note.lang_id", 0, 127)
        if available_languages and native["langID"] not in available_languages:
            raise ValueError("note.lang_id is absent from this part's aiVoice.langIDs")
        native_notes.append(native)
    duration = part.get("duration", 0)
    if isinstance(duration, bool) or not isinstance(duration, int) or duration < 0:
        raise ValueError("native part.duration must be a nonnegative integer")
    part["notes"] = native_notes
    part["duration"] = max(duration, max((note["pos"] + note["duration"] for note in native_notes), default=0))


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

    def _write_archive(self, archive: zipfile.ZipFile, data: dict, output_name: str) -> dict:
        if not isinstance(data, dict):
            raise ValueError("project data must be an object")
        serialized = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        if archive.namelist().count(SEQUENCE_MEMBER) != 1:
            raise ValueError("VPR must contain exactly one Project/sequence.json")
        validity_count = archive.namelist().count(PHONEME_VALIDITY_MEMBER)
        if validity_count > 1:
            raise ValueError("VPR has duplicate phoneme-validity metadata")
        if validity_count:
            _validate_phoneme_validity(data, archive.read(PHONEME_VALIDITY_MEMBER))
        with _exclusive_output(self.workspace, output_name, (".vpr",)) as (destination, handle):
            with zipfile.ZipFile(handle, "w") as result:
                result.comment = archive.comment
                for member in archive.infolist():
                    payload = serialized if member.filename == SEQUENCE_MEMBER else archive.read(member)
                    result.writestr(copy(member), payload)
        return {"path": str(destination), "summary": self._summary(destination, data)}

    def write_copy(self, source: str | Path, data: dict, output_name: str) -> dict:
        with _source_archive(self.workspace, source) as archive:
            return self._write_archive(archive, data, output_name)

    def patch(self, source: str, operations: list[dict], output_name: str) -> dict:
        if not isinstance(operations, list) or not all(isinstance(operation, dict) for operation in operations):
            raise ValueError("operations must be a JSON Patch array")
        with _source_archive(self.workspace, source) as archive:
            data = jsonpatch.JsonPatch(deepcopy(operations)).apply(self._read_archive(archive), in_place=False)
            return self._write_archive(archive, data, output_name)

    def compose(self, template: str, output_name: str, title: str, bpm: float, notes: list[dict],
                track_index: int = 0, part_index: int = 0, voice_comp_id: str | None = None) -> dict:
        if not isinstance(title, str):
            raise ValueError("title must be a string")
        with _source_archive(self.workspace, template) as archive:
            data = self._read_archive(archive)
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
            _replace_notes(data, notes, track_index, part_index)
            _tempo_events(data, [{"start": 0, "bpm": bpm}])
            data["title"] = title
            return self._write_archive(archive, data, output_name)

    def edit_notes(self, source: str, output_name: str, notes: list[dict], track_index: int = 0, part_index: int = 0) -> dict:
        with _source_archive(self.workspace, source) as archive:
            data = self._read_archive(archive)
            _replace_notes(data, notes, track_index, part_index)
            return self._write_archive(archive, data, output_name)

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
