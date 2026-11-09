"""Read-only, version-specific VSM x64 rate-branch diagnostic; does not start VOCALOID."""
from pathlib import Path
import json
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".tools" / "analysis"))
import capstone
import pefile

DLL = Path(r"C:\Program Files\VOCALOID6\Editor\VSM.dll")
ENUM = ROOT / ".runtime/decompiled-audio/Yamaha.VOCALOID.VSM/VSMResult.cs"
CANCEL = ROOT / ".runtime/decompiled-audio/Yamaha.VOCALOID.VSM/VSMRenderCancelReason.cs"

def enum_items(path):
    text = path.read_text(encoding="utf-8")
    return [line.strip().rstrip(",") for line in text.split("{", 1)[1].split("}", 1)[0].splitlines() if line.strip()]

def main():
    pe = pefile.PE(str(DLL))
    base = pe.OPTIONAL_HEADER.ImageBase
    engine = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    sections = {"async_guard": (0x60b0e, 0x60bba), "sync_guard": (0x59ed8, 0x59f79),
                "sequence_rate_setter": (0x8e670, 0x8e6bb)}
    output = {"dll": str(DLL), "bytes": DLL.stat().st_size, "pe_timestamp": pe.FILE_HEADER.TimeDateStamp,
              "image_base": hex(base), "result_enum_73": enum_items(ENUM)[73],
              "cancel_enum_16": enum_items(CANCEL)[16], "sequences": {}}
    for name, (start, end) in sections.items():
        output["sequences"][name] = [{"rva": hex(i.address - base), "bytes": i.bytes.hex(), "mnemonic": i.mnemonic,
                                      "operands": i.op_str} for i in engine.disasm(pe.get_data(start, end - start), base + start)]
    async_guard = output["sequences"]["async_guard"]
    sync_guard = output["sequences"]["sync_guard"]
    output["matches_expected_build"] = (
        any(i["rva"] == "0x60b18" and i["mnemonic"] == "cmp" and "0xac44" in i["operands"] for i in async_guard)
        and any(i["rva"] == "0x60b49" and i["mnemonic"] == "mov" and "0x10" in i["operands"] for i in async_guard)
        and any(i["rva"] == "0x59ed8" and i["mnemonic"] == "cmp" and "0xac44" in i["operands"] for i in sync_guard)
        and any(i["rva"] == "0x59f6e" and i["mnemonic"] == "mov" and "0x49" in i["operands"] for i in sync_guard)
        and output["result_enum_73"] == output["cancel_enum_16"] == "FailedToCreateDseWaveBuffer")
    output["interpretation_boundary"] = "Instruction patterns are build-specific; +0x28 object provenance and full dynamic call chain are not proven by this scan."
    path = ROOT / "artifacts" / ("internal-rate-static-" + uuid.uuid4().hex[:12] + ".json")
    path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps({"receipt": str(path), "matches_expected_build": output["matches_expected_build"]}))
    return 0 if output["matches_expected_build"] else 1

if __name__ == "__main__":
    sys.exit(main())
