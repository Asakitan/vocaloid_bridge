"""Read-only reflection checks; never creates an EngineHost or native sequence."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", type=Path)
    parser.add_argument("--expect-baseline-failure", action="store_true")
    args = parser.parse_args()
    candidates = list((ROOT / "native" / "bin").glob("**/VOCALOID7/**/VocaloidBridge.Host.dll"))
    if args.host is None:
        candidates = [path for path in candidates if "ref" not in path.parts]
        if len(candidates) != 1:
            parser.error("Supply --host with the existing VOCALOID7 host DLL path")
    host = (args.host or candidates[0]).resolve()
    script = r'''
$ErrorActionPreference = 'Stop'
$assembly = [Reflection.Assembly]::LoadFrom($env:INTEGRITY_HOST)
$engine = $assembly.GetType('EngineHost', $true)
$method = $engine.GetMethod('ArchiveValidateUnambiguous', [Reflection.BindingFlags]'Static,NonPublic')
$baseline = $env:INTEGRITY_BASELINE -eq '1'
function Assert-Tracks([string] $json, [bool] $reject) {
    $tracks = [System.Text.Json.Nodes.JsonNode]::Parse($json)
    try {
        $method.Invoke($null, [object[]](,$tracks))
    } catch {
        $failure = $_.Exception
        while ($failure.InnerException) { $failure = $failure.InnerException }
        if ($reject -and $failure.Message.Contains('indistinguishable track identities')) { return }
        throw
    }
    if ($reject) { throw 'Ambiguous opaque payload was accepted' }
}
Assert-Tracks '[{"type":2,"name":"Lead","voice":{"compID":"BANK_A"},"parts":[],"x_owner":"A"},{"type":2,"name":"Lead","voice":{"compID":"BANK_B"},"parts":[],"x_owner":"B"}]' $baseline
Assert-Tracks '[{"type":2,"name":"Lead","voice":{"compID":"BANK_A"},"secondaryVoice":{"compID":"BANK_B"},"parts":[],"x_owner":"A"},{"type":2,"name":"Lead","voice":{"compID":"BANK_A"},"secondaryVoice":{"compID":"BANK_C"},"parts":[],"x_owner":"B"}]' $baseline
Assert-Tracks '[{"type":2,"name":"Lead","voice":{"compID":"BANK_A"},"parts":[],"x_owner":"A"},{"type":2,"name":"Lead","voice":{"compID":"BANK_A"},"parts":[],"x_owner":"B"}]' $true
Assert-Tracks '[{"type":2,"name":"Lead","voice":{"compID":"BANK_A","x_voice":"A"},"parts":[]},{"type":2,"name":"Lead","voice":{"compID":"BANK_A","x_voice":"B"},"parts":[]}]' $true
$voiceMethod = $engine.GetMethod('ValidateVoiceIdentity', [Reflection.BindingFlags]'Static,NonPublic')
function Assert-Voice([string] $serialized, [string] $native, [string[]] $ids, [bool] $reject) {
    $table = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach ($identifier in $ids) { [void]$table.Add($identifier) }
    try {
        $voiceMethod.Invoke($null, [object[]]@($serialized, $native, $true, $table, 'fixture'))
    } catch {
        $failure = $_.Exception
        while ($failure.InnerException) { $failure = $failure.InnerException }
        if ($reject -and $failure.Message.StartsWith('project_integrity:')) { return }
        throw
    }
    if ($reject) { throw 'Invalid voice identity was accepted' }
}
Assert-Voice 'BANK_A' 'BANK_A' @('BANK_A') $false
Assert-Voice 'BANK_A' 'BANK_B' @('BANK_A', 'BANK_B') $true
Assert-Voice 'BANK_A' 'BANK_A' @() $true
if ($baseline) {
    Write-Output 'V7_INTEGRITY_BASELINE_REPRODUCED checks=7 native_host_started=false fixed_assembly_verified=false'
} else {
    Write-Output 'V7_INTEGRITY_OFFLINE_OK checks=7 native_host_started=false'
}
'''
    environment = dict(os.environ, INTEGRITY_HOST=str(host),
                       INTEGRITY_BASELINE="1" if args.expect_baseline_failure else "0")
    return subprocess.run(
        ["pwsh", "-NoProfile", "-NonInteractive", "-Command", script],
        env=environment,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())