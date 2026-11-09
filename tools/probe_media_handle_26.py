import ctypes, json, subprocess, sys, uuid
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path
import pywintypes, win32con, win32file

BASE = (Path(__file__).resolve().parents[1] / 'artifacts').resolve()
PREFIX = 'media-handle-26-'
READ = win32con.FILE_SHARE_READ
DELETE = 0x10000
kernel = ctypes.WinDLL('kernel32', use_last_error=True)
kernel.SetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
kernel.SetFileInformationByHandle.restype = wintypes.BOOL
class Rename(ctypes.Structure):
    _fields_ = [('replace', wintypes.BOOL), ('root', wintypes.HANDLE), ('length', wintypes.DWORD), ('name', wintypes.WCHAR * 1)]
def validate(path):
    p = Path(path).resolve(strict=False)
    if p.parent.parent != BASE or not p.parent.name.startswith(PREFIX) or p.name not in ('property.json', 'candidate.json', 'moved.json'):
        raise ValueError('synthetic fixture required')
    return p
def rename(handle, dst, replace=False):
    dst = str(validate(dst)); raw = dst.encode('utf-16-le')
    buf = ctypes.create_string_buffer(Rename.name.offset + len(raw) + 2)
    info = Rename.from_buffer(buf); info.replace = replace; info.root = None; info.length = len(raw)
    ctypes.memmove(ctypes.addressof(buf) + Rename.name.offset, raw, len(raw))
    if not kernel.SetFileInformationByHandle(int(handle), 3, buf, len(buf)):
        raise ctypes.WinError(ctypes.get_last_error())
def openfile(path, access, share):
    return win32file.CreateFile(str(validate(path)), access, share, None, win32con.OPEN_EXISTING, 0, None)
def result(fn):
    try:
        value = fn(); return {'ok': True, 'value': value}
    except (OSError, pywintypes.error) as e:
        return {'ok': False, 'error': str(e), 'winerror': getattr(e, 'winerror', None)}
@contextmanager
def opened(path, access, share):
    handle = openfile(path, access, share)
    try:
        yield handle
    finally:
        handle.Close()
def child(action, target):
    target = validate(target)
    def run():
        if action == 'read': return target.read_text(encoding='utf-8')
        if action == 'write':
            with opened(target, win32con.GENERIC_WRITE, READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE) as h:
                win32file.WriteFile(h, b'external')
            return None
        raise ValueError(action)
    return result(run)
if len(sys.argv) > 1:
    print(json.dumps(child(*sys.argv[1:]))); sys.exit()
out = BASE / (PREFIX + uuid.uuid4().hex); out.mkdir(parents=True)
target, candidate, moved = (out / x for x in ('property.json', 'candidate.json', 'moved.json'))
def init():
    target.write_text('original', encoding='utf-8'); candidate.write_text('candidate', encoding='utf-8')
def invoke(action):
    p = subprocess.run([sys.executable, __file__, action, str(target)], capture_output=True, text=True, timeout=20, check=True)
    return json.loads(p.stdout)
receipt = {'directory': str(out), 'cases': {}}
init()
with opened(target, win32con.GENERIC_READ | DELETE, READ) as h:
    receipt['cases']['held_target'] = {'read': invoke('read'), 'writer': invoke('write'), 'own_rename': result(lambda: rename(h, moved))}
receipt['cases']['held_target']['moved_content'] = moved.read_text(encoding='utf-8') if moved.exists() else None
init()
with opened(target, win32con.GENERIC_READ | DELETE, READ) as held:
    with opened(candidate, DELETE, READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE) as replacement:
        receipt['cases']['candidate_replace'] = result(lambda: rename(replacement, target, True))
receipt['cases']['candidate_replace_contents'] = {'target': target.read_text(encoding='utf-8'), 'candidate_exists': candidate.exists()}
init()
with opened(target, win32con.GENERIC_WRITE, READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE) as writer:
    receipt['cases']['existing_writer'] = result(lambda: openfile(target, win32con.GENERIC_READ | DELETE, READ).Close())
    win32file.WriteFile(writer, b'external')
receipt['cases']['existing_writer_content'] = target.read_text(encoding='utf-8')
init()
try:
    with opened(target, win32con.GENERIC_READ | DELETE, READ):
        raise RuntimeError('injected exception')
except RuntimeError:
    pass
receipt['cases']['after_exception'] = {'writer': invoke('write'), 'content': target.read_text(encoding='utf-8')}
receipt['limits'] = 'Controlled local fixture only; native refresh, general identity, and crash durability not tested. All direct child processes waited.'
(out / 'receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
print(json.dumps(receipt, indent=2))
