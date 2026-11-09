import json, subprocess, sys, uuid
from pathlib import Path
import pywintypes, win32con, win32file
ROOT = Path(__file__).resolve().parents[1]
BASE = (ROOT / 'artifacts').resolve()
def validate(p):
    p = Path(p).resolve(strict=True)
    if p.parent.parent != BASE or not p.parent.name.startswith('media-atomic-25-') or p.name not in ('property.json', 'candidate.json'):
        raise ValueError('synthetic fixture required')
    return p
def child(action, target, candidate):
    target, candidate = validate(target), validate(candidate)
    try:
        if action == 'read': result = target.read_text(encoding='utf-8')
        elif action == 'write': target.write_text('{"name":"external"}', encoding='utf-8'); result = None
        elif action == 'replace': win32file.MoveFileEx(str(candidate), str(target), win32con.MOVEFILE_REPLACE_EXISTING); result = None
        else: raise ValueError(action)
        return {'ok': True, 'value': result}
    except Exception as e:
        return {'ok': False, 'error': str(e), 'winerror': getattr(e, 'winerror', None)}
if len(sys.argv) > 1:
    print(json.dumps(child(*sys.argv[1:]))); sys.exit()
out = BASE / ('media-atomic-25-' + uuid.uuid4().hex)
out.mkdir(parents=True)
target, candidate = out/'property.json', out/'candidate.json'
receipt = {'directory': str(out), 'cases': {}, 'native_refresh': 'not tested'}
for case in ('overlap_lock', 'deny_write_delete'):
    target.write_text('{"name":"original"}', encoding='utf-8')
    candidate.write_text('{"name":"candidate"}', encoding='utf-8')
    share = (win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE) if case == 'overlap_lock' else win32con.FILE_SHARE_READ
    handle = win32file.CreateFile(str(target), win32con.GENERIC_READ | win32con.GENERIC_WRITE, share, None, win32con.OPEN_EXISTING, 0, None)
    ov = pywintypes.OVERLAPPED()
    locked = False
    try:
        if case == 'overlap_lock':
            win32file.LockFileEx(handle, win32con.LOCKFILE_EXCLUSIVE_LOCK | win32con.LOCKFILE_FAIL_IMMEDIATELY, 0, 1, ov); locked = True
        results = {}
        for action in ('read', 'write', 'replace'):
            p = subprocess.run([sys.executable, __file__, action, str(target), str(candidate)], capture_output=True, text=True, timeout=20, check=True)
            results[action] = json.loads(p.stdout)
        receipt['cases'][case] = results
    finally:
        if locked: win32file.UnlockFileEx(handle, 0, 1, ov)
        handle.Close()
    receipt['cases'][case]['after_release'] = target.read_text(encoding='utf-8')
receipt['child_cleanup'] = 'subprocess.run waited for each direct child'
(out/'receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
print(json.dumps(receipt, indent=2))
