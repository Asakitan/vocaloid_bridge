"""Beat-based note validation and Standard MIDI File interchange."""

from __future__ import annotations

from collections import defaultdict, deque
from contextlib import contextmanager
from copy import deepcopy
from decimal import Decimal
import math
from pathlib import Path, PureWindowsPath
import re
import stat
from typing import Any, BinaryIO, Iterator

import mido


PPQ = 480


def _number(value: Any, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(f"{label} must be a finite number") from error
    if not math.isfinite(result) or result < 0 or (positive and result == 0):
        raise ValueError(f"{label} must be finite and {'positive' if positive else 'nonnegative'}")
    return result


def _integer(value: Any, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer in {minimum}..{maximum}")
    return value


def _ticks(value: Any, label: str, *, positive: bool = False) -> int:
    scaled = _number(value, label, positive=positive) * PPQ
    if not math.isfinite(scaled):
        raise ValueError(f"{label} is too large")
    result = math.floor(scaled + 0.5)
    if positive and result == 0:
        raise ValueError(f"{label} must round to at least one tick")
    return result


def _pitch(value: Any) -> int:
    if isinstance(value, str):
        match = re.fullmatch(r"([A-Ga-g])([#b]?)(-?\d+)", value.strip())
        if match is None:
            raise ValueError("pitch must be MIDI 0..127 or a note name such as C4")
        name, accidental, octave = match.groups()
        value = 12 * (int(octave) + 1) + {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}[name.upper()]
        value += {"": 0, "#": 1, "b": -1}[accidental]
    return _integer(value, "pitch", 0, 127)


def _notes(notes: list[dict], *, monophonic: bool = False) -> list[dict]:
    if not isinstance(notes, list):
        raise ValueError("notes must be a list of objects")
    result = []
    for note in notes:
        if not isinstance(note, dict):
            raise ValueError("each note must be an object")
        start = _number(note.get("start"), "note.start")
        duration = _number(note.get("duration"), "note.duration", positive=True)
        lyric = note.get("lyric", "")
        if not isinstance(lyric, str):
            raise ValueError("note.lyric must be a string")
        if "phoneme" in note and not isinstance(note["phoneme"], str):
            raise ValueError("note.phoneme must be a string")
        if "velocity" in note:
            _integer(note["velocity"], "note.velocity", 1, 127)
        if "lang_id" in note:
            _integer(note["lang_id"], "note.lang_id", 0, 127)
        if not isinstance(note.get("raw", {}), dict):
            raise ValueError("note.raw must be an object")
        result.append({**deepcopy(note), "start": start, "duration": duration,
                       "pitch": _pitch(note.get("pitch")), "lyric": lyric,
                       "_pos": _ticks(start, "note.start"),
                       "_duration": _ticks(duration, "note.duration", positive=True)})
    result.sort(key=lambda note: note["_pos"])
    if monophonic:
        for previous, following in zip(result, result[1:]):
            if (previous["_pos"] + previous["_duration"] > following["_pos"]
                    or Decimal(str(previous["start"])) + Decimal(str(previous["duration"])) > Decimal(str(following["start"]))):
                raise ValueError("notes overlap in a monophonic part")
    return result


def _reject_links(path: Path) -> None:
    for component in reversed((path, *path.parents)):
        try:
            metadata = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError(f"symlinks and reparse points are not allowed: {component}")


def _workspace(workspace: Path) -> Path:
    path = Path(workspace).absolute()
    if ".." in path.parts:
        raise ValueError("workspace must not contain parent traversal")
    _reject_links(path)
    path = path.resolve(strict=True)
    if not path.is_dir():
        raise ValueError("workspace must be an existing directory")
    return path


def _source(workspace: Path, path: str | Path) -> Path:
    root = _workspace(workspace)
    candidate = Path(path)
    if ".." in candidate.parts:
        raise ValueError("source must not contain parent traversal")
    relative = not candidate.is_absolute()
    if relative:
        candidate = root / candidate
        if not candidate.is_relative_to(root):
            raise ValueError("relative source must be inside the workspace")
    _reject_links(candidate)
    resolved = candidate.resolve(strict=True)
    if relative and not resolved.is_relative_to(root):
        raise ValueError("relative source must be inside the workspace")
    if not resolved.is_file():
        raise ValueError("source must be a regular file")
    return resolved


def _output_destination(workspace: Path, output_name: str, suffixes: tuple[str, ...]) -> Path:
    root = _workspace(workspace)
    if not isinstance(output_name, str) or not output_name:
        raise ValueError("output_name must be a nonempty relative filename")
    relative = PureWindowsPath(output_name)
    if relative.drive or relative.root or not relative.parts:
        raise ValueError("output_name must be relative to workspace/output")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{index}" for index in range(1, 10)), *(f"LPT{index}" for index in range(1, 10))}
    for part in relative.parts:
        if (part in (".", "..") or part.endswith((".", " "))
                or any(ord(character) < 32 or character in '<>:"|?*' for character in part)
                or part.split(".", 1)[0].upper() in reserved):
            raise ValueError("output_name contains an unsafe path component")
    if not relative.suffix:
        relative = relative.with_suffix(suffixes[0])
    if relative.suffix.lower() not in suffixes:
        raise ValueError(f"output_name must use one of {suffixes}")
    output_root = root / "output"
    destination = output_root.joinpath(*relative.parts)
    _reject_links(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _reject_links(destination)
    if not destination.resolve().is_relative_to(output_root):
        raise ValueError("output_name escapes workspace/output")
    return destination


@contextmanager
def _exclusive_output(workspace: Path, output_name: str, suffixes: tuple[str, ...]) -> Iterator[tuple[Path, BinaryIO]]:
    destination = _output_destination(workspace, output_name, suffixes)
    handle = destination.open("xb")
    try:
        with handle:
            yield destination, handle
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def export_midi(workspace: Path, title: str, bpm: float, tracks: list[dict], output_name: str) -> dict:
    """Write an exclusive UTF-8 type-1 MIDI file under workspace/output."""
    if not isinstance(title, str) or not isinstance(tracks, list):
        raise ValueError("title must be a string and tracks must be a list")
    tempo = mido.bpm2tempo(_number(bpm, "bpm", positive=True))
    _integer(tempo, "MIDI tempo (microseconds per beat)", 1, 0xFFFFFF)
    prepared = []
    for index, track in enumerate(tracks):
        if not isinstance(track, dict) or not isinstance(track.get("name", ""), str):
            raise ValueError("each track must be an object with a string name")
        channel = _integer(track.get("channel", index % 16), "channel", 0, 15)
        program = track.get("program")
        if "program" in track:
            program = _integer(program, "program", 0, 127)
        prepared.append((track.get("name", ""), channel, program, _notes(track.get("notes", []))))
    duration = max((note["_pos"] + note["_duration"] for _, _, _, notes in prepared for note in notes), default=0)
    midi = mido.MidiFile(type=1, ticks_per_beat=PPQ, charset="utf-8")
    midi.tracks.append(mido.MidiTrack([
        mido.MetaMessage("track_name", name=title),
        mido.MetaMessage("set_tempo", tempo=tempo),
        mido.MetaMessage("time_signature", numerator=4, denominator=4),
        mido.MetaMessage("end_of_track", time=duration),
    ]))
    for name, channel, program, notes in prepared:
        track = mido.MidiTrack([mido.MetaMessage("track_name", name=name)])
        if program is not None:
            track.append(mido.Message("program_change", channel=channel, program=program))
        events = []
        for index, note in enumerate(notes):
            velocity = note.get("velocity", 64)
            events.append((note["_pos"], 2, index, mido.Message("note_on", channel=channel, note=note["pitch"], velocity=velocity)))
            events.append((note["_pos"] + note["_duration"], 0, index, mido.Message("note_off", channel=channel, note=note["pitch"], velocity=0)))
            if note["lyric"]:
                events.append((note["_pos"], 1, index, mido.MetaMessage("lyrics", text=note["lyric"])))
        previous = 0
        for position, _, _, message in sorted(events, key=lambda event: event[:3]):
            track.append(message.copy(time=position - previous))
            previous = position
        track.append(mido.MetaMessage("end_of_track", time=duration - previous))
        midi.tracks.append(track)
    with _exclusive_output(workspace, output_name, (".mid", ".midi")) as (destination, handle):
        midi.save(file=handle)
    return {"path": str(destination), "format": "midi", "title": title,
            "ticks_per_beat": PPQ, "bpm": float(bpm), "track_count": len(prepared),
            "note_count": sum(len(notes) for _, _, _, notes in prepared), "duration_beats": duration / PPQ}


def import_midi(path: str | Path) -> dict:
    """Read synchronous MIDI tracks, keeping channel, lyric and tempo information."""
    source = Path(path).absolute()
    _reject_links(source)
    source = source.resolve(strict=True)
    midi = mido.MidiFile(source, charset="utf-8")
    if midi.type == 2 or midi.ticks_per_beat <= 0:
        raise ValueError("only synchronous MIDI type 0/1 with positive PPQ is supported")
    resolution = midi.ticks_per_beat
    result_tracks = []
    tempos = []
    signatures = []
    duration = 0
    for track_index, track in enumerate(midi.tracks):
        position = 0
        active = defaultdict(deque)
        programs = {}
        program_events = []
        notes = []
        lyrics = []
        name = ""
        ordinal = 0
        for message in track:
            position += message.time
            if message.type == "track_name":
                name = message.name
            elif message.type == "set_tempo":
                if message.tempo <= 0:
                    raise ValueError("MIDI tempo must be positive")
                tempos.append({"start": position / resolution, "bpm": mido.tempo2bpm(message.tempo),
                               "microseconds_per_beat": message.tempo, "track_index": track_index})
            elif message.type == "time_signature":
                signatures.append({"start": position / resolution, "numerator": message.numerator,
                                   "denominator": message.denominator, "track_index": track_index})
            elif message.type == "lyrics":
                lyrics.append({"start": position / resolution, "text": message.text, "_pos": position})
            elif message.type == "program_change":
                programs[message.channel] = message.program
                program_events.append({"start": position / resolution, "channel": message.channel, "program": message.program})
            elif message.type == "note_on" and message.velocity > 0:
                active[(message.channel, message.note)].append((position, message.velocity, programs.get(message.channel, 0), ordinal))
                ordinal += 1
            elif message.type in ("note_on", "note_off"):
                pending = active[(message.channel, message.note)]
                if pending:
                    start, velocity, program, order = pending.popleft()
                    notes.append({"start": start / resolution, "duration": (position - start) / resolution,
                                  "pitch": message.note, "velocity": velocity, "lyric": "",
                                  "channel": message.channel, "program": program, "_pos": start, "_order": order})
        if any(active.values()):
            raise ValueError(f"track {track_index} contains unterminated notes")
        notes.sort(key=lambda note: (note["_pos"], note["_order"]))
        by_position = defaultdict(deque)
        for note in notes:
            by_position[note["_pos"]].append(note)
        for lyric in lyrics:
            pending = by_position[lyric["_pos"]]
            if pending:
                pending.popleft()["lyric"] = lyric["text"]
            lyric.pop("_pos")
        for note in notes:
            note.pop("_pos")
            note.pop("_order")
        result_tracks.append({"name": name, "notes": notes, "lyrics": lyrics,
                              "channels": sorted({note["channel"] for note in notes}), "programs": program_events})
        duration = max(duration, position)
    tempos.sort(key=lambda event: (event["start"], event["track_index"]))
    if not tempos or tempos[0]["start"] > 0:
        tempos.insert(0, {"start": 0.0, "bpm": 120.0, "microseconds_per_beat": 500000, "track_index": None})
    return {"path": str(source), "format": "midi", "title": result_tracks[0]["name"] if result_tracks else source.stem,
            "ticks_per_beat": resolution, "duration_beats": duration / resolution,
            "tempos": tempos, "time_signatures": signatures, "tracks": result_tracks}
