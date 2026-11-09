import json, subprocess, sys, uuid
from pathlib import Path
import pywintypes, win32con, win32file
root = Path(__file__).resolve().parents[1]
if len(sys.argv) > 1:
    action, t, c = sys.argv[1:]
    t, c = Path(t).resolve(strict=True), Path(c).resolve(strict=True)
    if (action not in ('read','write','replace') or t.parent != c.parent or t.parent.parent != (root/'artifacts').resolve() or not t.parent.name.startswith('media-transaction-24-') or t.name != 'target.json' or c.name != 'candidate.json'):
        raise ValueError('synthetic fixture paths required')
    try:
        if action == 'read': value = t.read_text(encoding='utf-8')
        elif action == 'write': t.write_text('external', encoding='utf-8'); value = None
        else: win32file.MoveFileEx(str(c), str(t), win32con.MOVEFILE_REPLACE_EXISTING); value = None
        result = {'ok': True, 'value': value}
    except Exception as e: result = {'ok': False, 'error': str(e), 'winerror': getattr(e,'winerror',None)}
    print(json.dumps(result)); sys.exit(0)
out = root/'artifacts'/('media-transaction-24-'+uuid.uuid4().hex[:12]); out.mkdir(parents=True)
t, c = out/'target.json', out/'candidate.json'
t.write_text('original', encoding='utf-8'); c.write_text('candidate', encoding='utf-8')
h = win32file.CreateFile(str(t), win32con.GENERIC_READ | win32con.GENERIC_WRITE, win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE, None, win32con.OPEN_EXISTING, 0, None)
ov = pywintypes.OVERLAPPED(); ov.Offset = 4096
receipt = {'directory':str(out),'lock_offset':4096,'lock_length':1,'actions':{}}
try:
    win32file.LockFileEx(h, win32con.LOCKFILE_EXCLUSIVE_LOCK | win32con.LOCKFILE_FAIL_IMMEDIATELY, 0, 1, ov)
    try:
        for action in ('read','write','replace'):
            p=subprocess.run([sys.executable,__file__,action,str(t),str(c)],capture_output=True,text=True,timeout=20,check=True)
            receipt['actions'][action]=json.loads(p.stdout)
        receipt['target_after'] = t.read_text(encoding='utf-8')
    finally: win32file.UnlockFileEx(h, 0, 1, ov)
finally: h.Close()
receipt['child_cleanup']='each subprocess.run waited for its direct child'
(out/'receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8'); print(json.dumps(receipt,indent=2))
