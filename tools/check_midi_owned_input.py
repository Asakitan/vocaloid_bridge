"""Exercise WinMM recording using a uniquely owned teVirtualMIDI input."""
import asyncio
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from ctypes import wintypes

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
DLL = Path(os.environ['SystemRoot']) / 'System32' / 'teVirtualMIDI64.dll'


async def main():
    run = uuid.uuid4().hex[:12]
    name = 'VB-' + run
    fixture = ROOT / 'vocaloid_bridge/templates/ai-starter.vpr'
    original = fixture.read_bytes()
    receipt = {'port_name': name, 'source': 'owned virtual MIDI input', 'physical_input': False,
               'events': [], 'winmm_output_opened': False}
    vm = ctypes.WinDLL(str(DLL), use_last_error=True)
    vm.virtualMIDICreatePortEx2.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD]
    vm.virtualMIDICreatePortEx2.restype = ctypes.c_void_p
    vm.virtualMIDISendData.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ubyte), wintypes.DWORD]
    vm.virtualMIDISendData.restype = wintypes.BOOL
    vm.virtualMIDIClosePort.argtypes = [ctypes.c_void_p]
    vm.virtualMIDIClosePort.restype = None
    port = None
    session = None
    recording = False
    params = StdioServerParameters(command=sys.executable, args=['-m', 'vocaloid_bridge'], cwd=str(ROOT),
        env={**os.environ, 'VOCALOID_WORKSPACE': str(ROOT), 'PYTHONUTF8': '1'})
    try:
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as client:
                await client.initialize()
                async def call(tool, **args):
                    result = await client.call_tool(tool, args)
                    if result.isError or result.structuredContent is None:
                        raise RuntimeError(f'{tool}: {result.content}')
                    return result.structuredContent
                async def midi(op, **options):
                    return (await call('project_midi', session_id=session, operation=op, options=options))['result']
                async def edit(op, **options):
                    return (await call('project_edit', session_id=session, operation=op, options=options))['result']
                try:
                    before = (await call('project_midi', operation='devices', options={}))['result']['devices']
                    assert not any(d['name'] == name for d in before)
                    port = vm.virtualMIDICreatePortEx2(name, None, None, 65535, 8)
                    if not port:
                        raise ctypes.WinError(ctypes.get_last_error())
                    receipt['events'].append('created owned input-only virtual endpoint')
                    for _ in range(50):
                        devices = (await call('project_midi', operation='devices', options={}))['result']['devices']
                        matches = [d for d in devices if d['name'] == name]
                        if matches:
                            break
                        await asyncio.sleep(.1)
                    assert len(matches) == 1, matches
                    receipt['owned_device'] = matches[0]
                    session = (await call('project_open', path=str(fixture)))['session_id']
                    await edit('note.clear', track_index=0, part_index=0)
                    await edit('track.update', track_index=0, midi_recording=True)
                    receipt['start'] = await midi('start', mode='device', device_id=matches[0]['device_id'],
                        device_name=name, track_index=0, part_index=0, start_tick=0, lyric='あ', phonemes='a', lang_id=0)
                    recording = True
                    receipt['events'].append('opened and started owned WinMM input')
                    for msg in ([0x90, 60, 91], [0x80, 60, 0]):
                        data = (ctypes.c_ubyte * len(msg))(*msg)
                        if not vm.virtualMIDISendData(port, data, len(msg)):
                            raise ctypes.WinError(ctypes.get_last_error())
                        receipt['events'].append('virtualMIDISendData ' + bytes(msg).hex())
                        await asyncio.sleep(.25)
                    receipt['status_before_stop'] = await midi('status')
                    assert receipt['status_before_stop']['event_count'] == 2, receipt['status_before_stop']
                    receipt['stop'] = await midi('stop')
                    recording = False
                    receipt['events'].append('stopped and closed owned WinMM input; committed notes')
                    assert receipt['stop']['inserted'] == 1, receipt['stop']
                    notes = (await edit('note.list', track_index=0, part_index=0))['notes']
                    assert len(notes) == 1 and notes[0]['number'] == 60 and notes[0]['velocity'] == 91, notes
                    receipt['notes'] = notes
                    await edit('note.update', track_index=0, part_index=0, note_index=0, number=62)
                    notes = (await edit('note.list', track_index=0, part_index=0))['notes']
                    assert notes[0]['number'] == 62
                    receipt['edited_notes'] = notes
                    saved = await call('project_save', session_id=session, output_name=f'midi-owned-{run}.vpr')
                    await call('project_close', session_id=session, discard_changes=True)
                    session = None
                    session = (await call('project_open', path=saved['path']))['session_id']
                    assert (await edit('note.list', track_index=0, part_index=0))['notes'] == notes
                    receipt['save_reopen'] = True
                    receipt['source_unchanged'] = fixture.read_bytes() == original
                    assert receipt['source_unchanged']
                finally:
                    if session:
                        try:
                            if recording:
                                await midi('cancel')
                        finally:
                            await call('project_close', session_id=session, discard_changes=True)
                    receipt['sessions_after_close'] = (await call('vocaloid_status'))['sessions']
                    assert receipt['sessions_after_close'] == 0
                    receipt['events'].append('closed owned project session')
                    if port:
                        vm.virtualMIDIClosePort(port)
                        port = None
                        receipt['events'].append('closed owned virtual endpoint')
                    # WinMM device enumeration may be cached in the existing host.
                    # Verify disappearance in a newly launched process instead.
                    if 'owned_device' in receipt:
                        probe = """import ctypes,json
w=ctypes.WinDLL('winmm'); b=ctypes.create_string_buffer(128); names=[]
for i in range(w.midiInGetNumDevs()):
 r=w.midiInGetDevCapsW(i,b,128)
 if r: raise RuntimeError(r)
 names.append(bytes(b)[8:72].decode('utf-16le').split('\\0')[0])
print(json.dumps(names))"""
                        after = json.loads(subprocess.check_output([sys.executable, '-c', probe], text=True))
                        receipt['fresh_process_port_absent'] = name not in after
                        assert receipt['fresh_process_port_absent'], after
        receipt['status'] = 'passed'
    except BaseException as error:
        receipt['status'] = 'failed'
        receipt['error'] = repr(error)
        raise
    finally:
        if port:
            vm.virtualMIDIClosePort(port)
        destination = ROOT / 'artifacts' / f'midi-owned-{run}.json'
        destination.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'Receipt: {destination}', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
