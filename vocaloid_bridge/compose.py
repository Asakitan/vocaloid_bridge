"""Resolve omitted AI-note phonemes with the installed native G2PA managers."""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import tempfile
from typing import Any

from .music import _notes, _output_destination, _reject_links
from .native_client import NativeClient
from .projects import PHONEME_VALIDITY_MEMBER, ProjectStore, _ai_voice, _part, _validate_phoneme_validity


# First two default lyric/phoneme pairs from the installed editor's
# DefaultLyricManager.  Different seed phonemes expose stale empty-candidate output.
_SEEDS = {
    0: (("あ", "a"), ("い", "i")),
    1: (("Ooh", "u:"), ("a", "V")),
    2: (("아", "a"), ("야", "ja")),
    3: (("a", "a"), ("e", "e")),
    4: (("a", "a"), ("o", "o")),
}


# Written forms the installed converters accept; the same wording as the native note.add error.
_LYRIC_FORMS = {
    0: "Japanese lyrics are kana, one mora or syllable per note, for example ら.",
    1: "English lyrics are plain words, one syllable per note.",
    4: "Chinese lyrics are unmarked pinyin, one syllable per note, for example wo; "
       "Han characters and tone numbers are not accepted.",
}


def _native_result(client: NativeClient, method: str, **parameters: Any) -> dict:
    return client.request(method, parameters)["result"]


def _notes_in_session(client: NativeClient, session: str, scope: dict) -> list[dict]:
    return _native_result(client, "score_edit", session_id=session, operation="note.list", options=scope)["notes"]


def _verify_loaded(expected: list[dict], actual: list[dict]) -> None:
    fields = (("pos", "start_tick"), ("duration", "duration_tick"), ("number", "number"),
              ("velocity", "velocity"), ("lyric", "lyric"), ("phoneme", "phonemes"),
              ("langID", "lang_id"))
    if len(expected) != len(actual) or any(
            any(source.get(a) != loaded.get(b) for a, b in fields)
            for source, loaded in zip(expected, actual)):
        raise ValueError("Native loading changed or discarded an authored note.")


def _verify_conversion(before: list[dict], after: list[dict], index: int, lyric: str,
                       language: int, affected: int) -> dict:
    if len(before) != len(after) or affected != 1:
        raise ValueError("Native G2PA did not resolve exactly one note.")
    for position, (old, current) in enumerate(zip(before, after)):
        ignored = {"lyric", "phonemes", "is_valid_phonemes"} if position == index else set()
        if {k: v for k, v in old.items() if k not in ignored} != {k: v for k, v in current.items() if k not in ignored}:
            raise ValueError("Native G2PA changed another note or a non-lyric field.")
    result = after[index]
    if (result["lyric"] != lyric or result["lang_id"] != language or
            not result["phonemes"] or not result["is_valid_phonemes"]):
        raise ValueError("Native G2PA did not resolve the complete requested lyric.")
    return result


def _resolve(client: NativeClient, session: str, scope: dict, index: int,
             lyric: str, language: int) -> str:
    query = {"language_id": language, "lyrics": lyric, "use_extension_dictionary": False}
    convertible = _native_result(client, "library_op", session_id=None, operation="lyrics_can_convert",
                                 options={**query, "is_ai": True})
    if not convertible["can_convert"]:
        form = _LYRIC_FORMS.get(language, "Use a written form that the native converter of this language accepts.")
        raise ValueError(f"Native G2PA does not accept lyric at note {index}. {form} "
                         "To keep any other lyric text, give the note an explicit phoneme.")
    target = {**scope, "note_index": index, **query}
    candidates = _native_result(client, "library_op", session_id=session, operation="lyrics_candidates",
                                options=target)["candidates"]
    before = _notes_in_session(client, session, scope)
    applied = _native_result(client, "library_op", session_id=session, operation="lyrics_apply", options=target)
    after = _notes_in_session(client, session, scope)
    first = _verify_conversion(before, after, index, lyric, language, applied["affected_length"])
    if candidates:
        if not any(len(candidate) == 1 and candidate[0].get("lyric") == first["lyric"] and
                   candidate[0].get("phonemes") == first["phonemes"] for candidate in candidates):
            raise ValueError(f"Native G2PA did not return a matching single-syllable candidate for note {index}.")
    else:
        seed_lyric, seed_phoneme = _SEEDS[language][1]
        _native_result(client, "score_edit", session_id=session, operation="note.update", options={
            **scope, "note_index": index, "lyric": seed_lyric, "phonemes": seed_phoneme,
            "is_valid_phonemes": True, "lang_id": language,
        })
        before_second = _notes_in_session(client, session, scope)
        if (before_second[index]["lyric"] != seed_lyric or before_second[index]["phonemes"] != seed_phoneme or
                any(before_second[i] != after[i] for i in range(len(after)) if i != index)):
            raise ValueError("Native G2PA seed did not preserve the surrounding notes.")
        applied_second = _native_result(client, "library_op", session_id=session, operation="lyrics_apply", options=target)
        after_second = _notes_in_session(client, session, scope)
        second = _verify_conversion(before_second, after_second, index, lyric, language, applied_second["affected_length"])
        if first["phonemes"] != second["phonemes"]:
            raise ValueError(f"Native G2PA retained inconsistent seed phonemes for note {index}.")
    return first["phonemes"]


def compose(store: ProjectStore, client: NativeClient, template: str, output_name: str,
            title: str, bpm: float, notes: list[dict], track_index: int, part_index: int,
            voice_comp_id: str | None) -> dict:
    """Create the score and return its opened native session, publishing after conversion."""
    preparation = store.prepare_compose(template, title, bpm, notes, track_index, part_index, voice_comp_id)
    return _write_prepared(store, client, preparation, output_name, notes, retain_session=True)


def replace_notes(store: ProjectStore, client: NativeClient, source: str, output_name: str,
                  notes: list[dict], track_index: int, part_index: int) -> dict:
    """Create a revised score without retaining a native session in the file-only API."""
    preparation = store.prepare_note_edit(source, notes, track_index, part_index)
    return _write_prepared(store, client, preparation, output_name, notes, retain_session=False)


def _write_prepared(store: ProjectStore, client: NativeClient, preparation, output_name: str,
                    notes: list[dict], *, retain_session: bool) -> dict:
    with preparation as (archive, data, origins):
        track_index, part_index, _ = origins
        track, part = _part(data, track_index, part_index)
        prepared = _notes(notes, monophonic=True)
        pending = []
        for index, (request, note) in enumerate(zip(prepared, part["notes"])):
            if not note["phoneme"]:
                if "phoneme" in request:
                    raise ValueError(f"note {index} has an empty phoneme; provide a nonempty phoneme or omit it.")
                pending.append((index, note["lyric"], note["langID"]))
        if not pending:
            result = store._write_archive(archive, data, output_name, origins)
            if not retain_session:
                return result
            return {**result, "native_session": client.request("open", {"path": result["path"]})}
        if PHONEME_VALIDITY_MEMBER in archive.namelist():
            _validate_phoneme_validity(data, archive.read(PHONEME_VALIDITY_MEMBER), origins)
        assigned_voice = _ai_voice(track, part)
        if assigned_voice is None:
            raise ValueError("Automatic phonemes require an AI voice part.")
        if any(language not in _SEEDS for _, _, language in pending):
            raise ValueError("Automatic phonemes require a supported native G2PA language.")

        destination = _output_destination(store.workspace, output_name, (".vpr",))
        if destination.exists():
            raise FileExistsError(f"Output already exists: {destination}")
        output_root = (store.workspace / "output").resolve(strict=True)
        directory = Path(tempfile.mkdtemp(prefix=".vocaloid-compose-", dir=output_root)).resolve(strict=True)
        if directory.parent != output_root or not directory.name.startswith(".vocaloid-compose-"):
            raise ValueError("Temporary score directory is outside the output root.")
        seed_path, ready_path = directory / "seed.vpr", directory / "ready.vpr"
        stage_session = None
        try:
            candidate = deepcopy(data)
            _, candidate_part = _part(candidate, track_index, part_index)
            for index, _, language in pending:
                candidate_part["notes"][index]["lyric"], candidate_part["notes"][index]["phoneme"] = _SEEDS[language][0]
            store._write_archive(archive, candidate, f"{directory.name}/seed.vpr", origins)
            stage_session = client.request("open", {"path": str(seed_path)})["session_id"]
            scope = {"track_index": track_index, "part_index": part_index}
            voice_scope = {**scope, "scope": "track"} if client.installation.product == "VOCALOID7" else scope
            voice = _native_result(client, "score_edit", session_id=stage_session, operation="voice.get", options=voice_scope)
            voice_id = assigned_voice.get("compID")
            banks = client.request("voices")["voices"]
            bank = next((item for item in banks if item.get("is_ai", item["kind"] == "Dnn") and item["comp_id"] == voice_id), None)
            if (not voice["ai"] or voice["ai_voice_bank_id"] != voice_id or bank is None or
                    not bank["available_in_sequence"] or not bank["synthesizable_version"] or
                    any(language not in bank["lang_ids"] for _, _, language in pending)):
                raise ValueError("The selected installed AI voice does not support the requested languages.")
            _verify_loaded(candidate_part["notes"], _notes_in_session(client, stage_session, scope))
            for index, lyric, language in pending:
                part["notes"][index]["phoneme"] = _resolve(client, stage_session, scope, index, lyric, language)
            resolved_notes = _notes_in_session(client, stage_session, scope)
            _verify_loaded(part["notes"], resolved_notes)
            closing, stage_session = stage_session, None
            client.request("close", {"session_id": closing, "discard": True})
            store._write_archive(archive, data, f"{directory.name}/ready.vpr", origins)
            _reject_links(destination)
            os.link(ready_path, destination)
            published = destination.stat()
            final_session = None
            try:
                final = client.request("open", {"path": str(destination)})
                final_session = final["session_id"]
                if _notes_in_session(client, final_session, scope) != resolved_notes:
                    raise ValueError("Published score differs from the native conversion session.")
                result = {"path": str(destination), "summary": store._summary(destination, data)}
                if retain_session:
                    return {**result, "native_session": final}
                closing, final_session = final_session, None
                client.request("close", {"session_id": closing, "discard": True})
                return result
            except BaseException:
                try:
                    if final_session is not None:
                        client.request("close", {"session_id": final_session, "discard": True})
                finally:
                    current = destination.stat()
                    if (os.path.samefile(destination, ready_path) and
                            (current.st_size, current.st_mtime_ns) == (published.st_size, published.st_mtime_ns)):
                        destination.unlink()
                raise
        finally:
            try:
                if stage_session is not None:
                    client.request("close", {"session_id": stage_session, "discard": True})
            finally:
                _reject_links(directory)
                if directory.resolve(strict=True).parent != output_root:
                    raise ValueError("Temporary score directory moved outside the output root.")
                seed_path.unlink(missing_ok=True)
                ready_path.unlink(missing_ok=True)
                directory.rmdir()
