"""Focused MCP-owned process lifecycle and non-replayed transport failure."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

import win32api
import win32con
import win32event
import win32process
import verify_features as v

sys.path.insert(0, str(v.ROOT))
from vocaloid_bridge import __version__
from vocaloid_bridge.native_client import NativeClient, NativeError


@v.feature('runtime.lifecycle_35', 'runtime', 'vocaloid_runtime', 'vocaloid_status', 'project_create',
           'project_edit', 'project_save', 'project_open', 'project_close', 'voicebanks')
async def lifecycle(check):
    initial = await check.call('vocaloid_runtime', operation='status')
    if initial['running']:
        v.require(initial['managed_by_mcp'] and initial['sessions'] == 0, 'Runtime fixture is not an idle owned host', initial)
        await check.call('vocaloid_runtime', operation='stop')
    cold = await check.call('vocaloid_runtime', operation='status')
    generation = cold['generation']
    v.require(not cold['running'], 'Status started the engine')
    sid = (await check.call('project_create', title='MCP-owned startup'))['session_id']
    running = await check.call('vocaloid_runtime', operation='status')
    check.owned_pids.add(running['pid'])
    v.require(running['running'] and running['generation'] == generation + 1 and running['mcp_version'] == __version__,
              'Project create did not start the native runtime', running)
    await check.edit(sid, 'track.create', type='MidiAi', name='AI')
    await check.edit(sid, 'part.create', track_index=0, start_tick=0, duration_tick=1920)
    voice = next(item for item in (await check.call('voicebanks'))['voices']
                 if item['kind'] == 'Dnn' and item['available_in_sequence'])
    scope = {'scope': 'track'} if running['product'] == 'VOCALOID7' else {}
    await check.edit(sid, 'voice.set', track_index=0, part_index=0, ai_voice_bank_id=voice['comp_id'], **scope)
    await check.edit(sid, 'note.add', track_index=0, part_index=0, start_tick=0, duration_tick=240, number=60)
    await check.rejected('vocaloid_runtime', 'Close or save', operation='restart')
    state = await check.call('vocaloid_runtime', operation='status')
    v.require(state['pid'] == running['pid'] and state['sessions'] == 1, 'Restart discarded an active project')
    _, saved = await check.save(sid, 'runtime-save')
    await check.close(sid)
    restarted = await check.call('vocaloid_runtime', operation='restart')
    check.owned_pids.add(restarted['pid'])
    v.require(restarted['pid'] != running['pid'] and restarted['generation'] == generation + 2, 'Explicit restart did not replace the owned process')
    sid = (await check.call('project_open', path=str(saved)))['session_id']
    await check.edit(sid, 'note.update', track_index=0, part_index=0, note_index=0, number=64)
    _, edited = await check.save(sid, 'runtime-edited')
    await check.close(sid)
    handle = win32api.OpenProcess(win32con.PROCESS_TERMINATE | win32con.SYNCHRONIZE, False, restarted['pid'])
    try:
        win32process.TerminateProcess(handle, 97)
        v.require(win32event.WaitForSingleObject(handle, 5000) == win32con.WAIT_OBJECT_0, 'Owned crash process remained live')
    finally:
        handle.Close()
    sid = (await check.call('project_open', path=str(edited)))['session_id']
    recovered = await check.call('vocaloid_runtime', operation='status')
    check.owned_pids.add(recovered['pid'])
    v.require(recovered['generation'] == generation + 3 and recovered['pid'] != restarted['pid'], 'Known-exited runtime was not started on demand')
    notes = await check.edit(sid, 'note.list', track_index=0, part_index=0)
    v.require(notes['notes'][0]['number'] == 64, 'Saved project did not reopen after process replacement')
    cache_root = Path(os.environ['LOCALAPPDATA']) / 'VOCALOID6'
    v.require(all(not (cache_root / kind / restarted['cache_namespace']).exists() for kind in ('VSM', 'VSMCaches')),
              'Crash left the owned native cache namespace')
    await check.close(sid)
    stopped = await check.call('vocaloid_runtime', operation='stop')
    v.require(not stopped['running'], 'Stop retained the native runtime')
    started = await check.call('vocaloid_runtime', operation='start')
    check.owned_pids.add(started['pid'])
    v.require(started['generation'] == generation + 4, 'Explicit MCP start did not start a new generation')
    await check.call('vocaloid_runtime', operation='stop')
    check.evidence('generations', [running['pid'], restarted['pid'], recovered['pid'], started['pid']])


@v.feature('runtime.no_replay_35', 'runtime', 'vocaloid_runtime')
async def no_replay(check):
    client = NativeClient(v.ROOT)
    try:
        client.request('ping')
        child = client.child
        with patch.object(child, 'read_line', side_effect=NativeError('injected lost response')) as read:
            try:
                client.request('create', {'title': 'Unknown result', 'bpm': 120, 'sample_rate': 44100})
                raise AssertionError('Injected response loss succeeded')
            except NativeError as error:
                v.require('not replayed' in str(error), 'Lost response was not classified', str(error))
            v.require(read.call_count == 1 and client.child is None, 'Ambiguous request was retried')
        try:
            client.request('session', {'session_id': 'expired'})
            raise AssertionError('Expired session request succeeded')
        except NativeError:
            v.require(client.child is None, 'Expired handle booted a replacement implicitly')
        fresh = client.request('create', {'title': 'Fresh request', 'bpm': 120, 'sample_rate': 44100})
        v.require(client.generation == 2, 'Fresh project did not recover the runtime')
        client.request('close', {'session_id': fresh['session_id'], 'discard': True})
        check.evidence('ambiguous_request_reads', 1)
    finally:
        client.close()


if __name__ == '__main__':
    if '--case' not in sys.argv:
        for name in ('runtime.lifecycle_35', 'runtime.no_replay_35'):
            sys.argv.extend(['--case', name])
    raise SystemExit(v.main())
