"""Fetch either the pinned UtaFormatix test fixture or the author's Monologue.

The UtaFormatix JSON is packaged as a ZIP; it is not native-editor-authored.
Monologue is downloaded as-is from the public author's Drive; its app version
is only the project's self-declared metadata. No downloaded program is executed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REVISION = "91d0aeb994bc846e380ea98cd4c6f75c5ea7c6ae"
BASE = f"https://raw.githubusercontent.com/sdercolin/utaformatix3/{REVISION}/"
SOURCE = "src/jsTest/resources/fixtures/ppsf_inner.txt"
MONOLOGUE_PAGE = "https://javawock7618.blogspot.com/2021/11/5ep-2nd11111-feat-hatsune-miku111.html"
MONOLOGUE_FOLDER = "https://drive.google.com/drive/folders/12A0GeYGkXnaF6wyi5q-R7sdlKkZ4WQ5E"
MONOLOGUE_URL = "https://drive.google.com/uc?export=download&id=17mE6HJxDNiTHLe3u_HW0u6NYICvwbo-x"


def download(path: str) -> bytes:
    request = urllib.request.Request(BASE + path, headers={"User-Agent": "VOCALOID-MCP-fixture-check"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024:
        raise ValueError("Public fixture exceeds the expected size limit")
    return data


def fetch_utaformatix() -> None:
    raw = download(SOURCE)
    document = json.loads(raw)
    if document["ppsf"]["ppsf_ver"] != "3.0":
        raise ValueError("The source is not the pinned PPSF3 fixture")
    license_data = download("LICENSE.md")
    destination = ROOT / ".runtime" / "public-ppsf3-utaformatix"
    destination.mkdir(parents=True, exist_ok=True)
    project = destination / "sample.ppsf"
    with zipfile.ZipFile(project, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ppsf.json", raw)
    (destination / "LICENSE.md").write_bytes(license_data)
    (destination / "source.json").write_text(json.dumps({
        "repository": "https://github.com/sdercolin/utaformatix3", "revision": REVISION,
        "source": BASE + SOURCE, "license": "Apache-2.0", "native_editor_authored": False,
        "packaging": "Verbatim JSON under ppsf.json, matching the upstream PpsfSnapshotTest",
        "project": str(project),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(project)


def fetch_monologue() -> None:
    request = urllib.request.Request(MONOLOGUE_URL, headers={"User-Agent": "VOCALOID-MCP-fixture-check"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(20 * 1024 * 1024 + 1)
    if len(data) > 20 * 1024 * 1024:
        raise ValueError("Monologue download exceeds the 20 MiB limit")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entry = archive.getinfo("ppsf.json")
        if entry.file_size > 16 * 1024 * 1024:
            raise ValueError("Monologue ppsf.json exceeds the 16 MiB limit")
        project_data = json.loads(archive.read(entry))["ppsf"]
        if str(project_data["ppsf_ver"]) != "3.2":
            raise ValueError("Downloaded file is not the identified PPSF 3.2 project")
        tracks = project_data["project"]["dvl_track"]
        notes = sum(len(track["events"]) for track in tracks)
        if notes != 190:
            raise ValueError(f"Unexpected Monologue note count: {notes}")
    destination = ROOT / ".runtime" / "public-ppsf3-javawock-download"
    destination.mkdir(parents=True, exist_ok=True)
    project = destination / "Monologue.ppsf"
    with project.open("xb") as file:
        file.write(data)
    provenance = {
        "author_page": MONOLOGUE_PAGE, "public_folder": MONOLOGUE_FOLDER, "download": MONOLOGUE_URL,
        "original_filename": "Monologue.ppsf", "downloaded_utc": datetime.now(timezone.utc).isoformat(),
        "ppsf_version": project_data["ppsf_ver"], "declared_app_version": project_data.get("app_ver"),
        "note_count": notes, "packaging": "Downloaded original archive without repackaging",
        "native_editor_authored": "Not independently verified; app version is self-declared metadata",
        "license": "Not established by this script", "project": str(project),
        "purpose": "Private compatibility testing; do not redistribute the source or generated music",
    }
    (destination / "source.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
    print(project)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("utaformatix", "monologue"), default="utaformatix")
    args = parser.parse_args()
    if args.source == "monologue":
        fetch_monologue()
    else:
        fetch_utaformatix()


if __name__ == "__main__":
    main()
