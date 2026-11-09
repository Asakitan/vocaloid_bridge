import json, subprocess, sys, uuid
from pathlib import Path
import win32file, win32con
root = Path(__file__).resolve().parents[1]
if len(sys.argv) > 1:
    action, target, candidate = sys.argv[1:]
    target, candidate = Path(target).resolve(strict=True), Path(candidate).resolve(strict=True)
    artifacts = (root / 'artifacts').resolve()
    if (action not in ('write', 'replace') or target.parent != candidate.parent or
            target.parent.parent != artifacts or not target.parent.name.startswith('media-atomic-23-') or
            not target.name.startswith('target-') or not candidate.name.startswith('candidate-')):
        raise ValueError('Probe child paths must be matching synthetic media-atomic artifacts')
    try:
        if action == 'write': target.write_text('external', encoding='utf-8')
        else: win32file.MoveFileEx(str(candidate), str(target), win32con.MOVEFILE_REPLACE_EXISTING)
        print(json.dumps({'ok': True}))
    except Exception as e: print(json.dumps({'ok': False, 'error': str(e), 'winerror': getattr(e, 'winerror', None)}))
    sys.exit(0)
out = root / 'artifacts' / ('media-atomic-23-' + uuid.uuid4().hex[:12]); out.mkdir(parents=True)
results = {'directory': str(out), 'cases': []}
for share in (win32con.FILE_SHARE_READ, win32con.FILE_SHARE_READ | win32con.FILE_SHARE_DELETE):
    target = out / ('target-%s.json' % share); candidate = out / ('candidate-%s.json' % share)
    target.write_text('original', encoding='utf-8'); candidate.write_text('candidate', encoding='utf-8')
    h = win32file.CreateFile(str(target), win32con.GENERIC_READ, share, None, win32con.OPEN_EXISTING, 0, None)
    try:
        row = {'share': share, 'snapshot_equal': target.read_text(encoding='utf-8') == 'original'}
        for action in ('write', 'replace'):
            p = subprocess.run([sys.executable, __file__, action, str(target), str(candidate)], capture_output=True, text=True, timeout=20, check=True)
            row[action] = json.loads(p.stdout)
        row['target_after'] = target.read_text(encoding='utf-8'); row['candidate_exists'] = candidate.exists(); results['cases'].append(row)
    finally: h.Close()
    p = subprocess.run([sys.executable, __file__, 'replace', str(target), str(candidate)], capture_output=True, text=True, timeout=20, check=True)
    row['replace_after_unlock'] = json.loads(p.stdout)
    row['target_after_unlock'] = target.read_text(encoding='utf-8')
results['child_cleanup'] = 'each subprocess.run waited for its direct child'
(out / 'receipt.json').write_text(json.dumps(results, indent=2), encoding='utf-8'); print(json.dumps(results, indent=2))
