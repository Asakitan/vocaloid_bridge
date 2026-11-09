"""Observe synthetic timeline native identities on a private Windows desktop."""
import argparse
import json
from pathlib import Path
import sys
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vocaloid_bridge.native_client import IsolatedProcess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--fixture', required=True, type=Path, help='Synthetic boundary-before or delete-native-before VPR in output')
parser.add_argument('--omit-end-tempo', action='store_true', help='Generate a synthetic variant without a tick-1500 tempo event')
parser.add_argument('--start-tick', type=int, default=1000)
parser.add_argument('--end-tick', type=int, default=1500)
parser.add_argument('--operation', choices=('insert', 'delete'), help='Run one native timeline operation')
args = parser.parse_args()
fixture = args.fixture.resolve(strict=True)
if (fixture.parent != (ROOT / 'output').resolve() or not fixture.name.startswith('feature-') or
    not fixture.name.endswith(('-boundary-before.vpr', '-delete-native-before.vpr'))):
    parser.error('Use a synthetic boundary-before or delete-native-before fixture in workspace output')
if args.start_tick < 0 or args.end_tick <= args.start_tick:
    parser.error('Ticks must form a nonempty nonnegative range')
if args.omit_end_tempo:
    variant = ROOT / 'output' / f'feature-{uuid.uuid4().hex[:12]}-boundary-before.vpr'
    with zipfile.ZipFile(fixture) as source, zipfile.ZipFile(variant, 'x', zipfile.ZIP_DEFLATED) as target:
        for entry in source.infolist():
            payload = source.read(entry.filename)
            if entry.filename == 'Project/sequence.json':
                sequence = json.loads(payload)
                events = sequence['masterTrack']['tempo']['events']
                if not any(item['pos'] == 1500 for item in events):
                    raise ValueError('Synthetic fixture lacks tick-1500 tempo event')
                sequence['masterTrack']['tempo']['events'] = [item for item in events if item['pos'] != 1500]
                payload = json.dumps(sequence, ensure_ascii=False).encode('utf-8')
            target.writestr(entry, payload)
    fixture = variant
command = [r'C:\Program Files\PowerShell\7\pwsh.exe', '-NoProfile', '-File',
           str(ROOT / 'tools' / 'probe_timeline_identity.ps1'), '-Fixture', str(fixture),
           '-StartTick', str(args.start_tick), '-EndTick', str(args.end_tick)]
if args.operation:
    command.extend(['-Operations', args.operation])
process = IsolatedProcess(command, ROOT)
try:
    result = json.loads(process.read_line(120))
    result['desktop'] = process.desktop_name
    result['fixture'] = str(fixture)
    output = ROOT / 'artifacts' / f'timeline-identity-probe-{uuid.uuid4().hex[:12]}.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(output)
finally:
    process.close()
