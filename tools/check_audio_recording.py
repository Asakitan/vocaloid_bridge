"""Read-only audit of installed VAE recording and host bridge surfaces."""
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".tools" / "analysis"))
import pefile

def main():
    editor = Path(r"C:\Program Files\VOCALOID6\Editor")
    dll = editor / "VAE.dll"
    assembly = ROOT / ".runtime/decompiled-audio/Yamaha.VOCALOID.VAE/VEAudioEngine.cs"
    recorder = ROOT / ".runtime/decompiled-audio/Yamaha.VOCALOID/RealtimeRecorder.cs"
    pe = pefile.PE(str(dll))
    exports = sorted(e.name.decode("ascii") for e in pe.DIRECTORY_ENTRY_EXPORT.symbols if e.name)
    source = assembly.read_text(encoding="utf-8").splitlines()
    keys = ("GetAudioDevice", "SetSampleRateFromHost", "SetCurrentPositionFromHost", "SetPlaybackFromHost", "SetLoopFromHost", "RenderWaveDataParams")
    matches = {key: [{"line": n, "text": line.strip()} for n, line in enumerate(source, 1) if key in line] for key in keys}
    input_terms = ("record", "capture", "wavein", "inputdevice")
    input_exports = [name for name in exports if any(term in name.lower() for term in input_terms)]
    files = [Path(r"C:\Program Files\Common Files\VST3\VOCALOIDBridge.vst3"),
             Path(r"C:\Program Files\Common Files\VST3\VOCALOID VSTi.vst3")]
    vst = []
    for plugin in files:
        entry = {"path": str(plugin), "exists": plugin.is_file()}
        if entry["exists"]:
            image = pefile.PE(str(plugin))
            entry["exports"] = sorted(e.name.decode("ascii") for e in image.DIRECTORY_ENTRY_EXPORT.symbols if e.name)
        vst.append(entry)
    cubase = Path(r"C:\Program Files\Steinberg\Cubase 16\Cubase 16.exe")
    result = {"vae": str(dll), "vae_bytes": dll.stat().st_size, "vae_pe_timestamp": pe.FILE_HEADER.TimeDateStamp,
              "all_exports": exports, "record_capture_inputdevice_named_exports": input_exports,
              "managed_file": str(assembly), "managed_api_matches": matches,
              "realtime_recorder_file": str(recorder),
              "realtime_recorder_midi_references": [{"line": n, "text": line.strip()}
                  for n, line in enumerate(recorder.read_text(encoding="utf-8").splitlines(), 1)
                  if "MIDIInputController" in line or "RecNote" in line],
              "installed_vst_files": vst, "cubase": {"path": str(cubase), "exists": cubase.is_file()},
              "scope": "Static names and local managed code only; no device opened, native DLL initialized, DAW hosted, or audio recorded."}
    path = ROOT / "artifacts" / ("audio-recording-static-" + uuid.uuid4().hex[:12] + ".json")
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"receipt": str(path), "input_named_exports": input_exports, "vst_files": result["installed_vst_files"]}))
    return 0

if __name__ == "__main__":
    sys.exit(main())
