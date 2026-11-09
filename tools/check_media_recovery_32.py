"""One focused case for native media publication, real process death and conflicts."""
import json
from pathlib import Path
import sys

import pywintypes
import win32con
import win32event
import win32file
import win32process
import verify_features as v

sys.path.insert(0, str(v.ROOT))
from vocaloid_bridge.native_client import IsolatedProcess


@v.feature('library.media_recovery_32', 'library', 'score_compose', 'project_library')
async def media_recovery(check, phases=('prepared', 'detached', 'published', 'committed')):
    async with check.project(score=True) as sid:
        clip = (await check.library('media_capture', sid, track_index=0, part_index=0,
                                    name='Recovery32-' + check.run_id))['clip']
        clip_id = clip['clip_id']
        path = Path(clip['path']).resolve()
        prop = path.with_name('property.json')
        original_clip = path.read_bytes()
        report = []
        check.evidence('media_journal_cases', report)
        failed = False
        try:
            initial = json.loads(prop.read_text('utf-8-sig'))
            marker = {'preserved': [True, None, {'value': check.run_id}]}
            initial['x_recovery32'] = marker
            initial['part']['x_recovery32'] = marker
            prop.write_text(json.dumps(initial), encoding='utf-8')
            changed = (await check.library('media_update', sid, clip_id=clip_id, name='Recovery32-normal', tempo=12600))['clip']
            v.require(changed['name'] == 'Recovery32-normal' and changed['tempo'] == 12600,
                      'Native publication did not complete', changed)
            v.require(json.loads(prop.read_text('utf-8'))['x_recovery32'] == marker, 'Unknown property lost')
            for number, phase in enumerate(phases):
                before = prop.read_bytes()
                request = json.loads(before)
                request['name'] = 'Recovery32-' + phase
                candidate = check.directory / f'candidate-{number}.json'
                candidate.write_text(json.dumps(request), encoding='utf-8')
                pause = 'detached' if phase == 'foreign' else phase
                child = IsolatedProcess([r'C:\Program Files\PowerShell\7\pwsh.exe', '-NoProfile', '-File',
                                         str(v.ROOT / 'tools/media_journal_child_32.ps1'), '-ClipId', clip_id,
                                         '-Candidate', str(candidate), '-PauseAt', pause], v.ROOT)
                try:
                    ready = json.loads(child.read_line(30))
                    check.evidence('current_child', ready)
                    v.require(ready.get('phase') == pause, 'Child did not reach the requested durable phase', ready)
                    stage = Path(ready['stage'])
                    if phase == 'prepared':
                        try:
                            handle = win32file.CreateFile(str(prop), win32con.GENERIC_WRITE,
                                                         win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE,
                                                         None, win32con.OPEN_EXISTING, 0, None)
                        except pywintypes.error as error:
                            v.require(error.winerror in (5, 32), 'Unexpected writer failure', str(error))
                        else:
                            handle.Close()
                            raise AssertionError('Competing writer acquired the exclusively bound original')
                        await check.rejected('project_library', 'busy', session_id=sid, operation='media_update',
                                             options={'clip_id': clip_id, 'name': 'Recovery32-competing'})
                        child.stdin.write(b'fail\n')
                        outcome = json.loads(child.read_line(30))
                        check.evidence('current_outcome', outcome)
                        v.require(outcome.get('ok') is False and not outcome['recovery_pending'], 'Exception rollback failed', outcome)
                    elif phase == 'foreign':
                        foreign = dict(request, name='Recovery32-external')
                        foreign_bytes = json.dumps(foreign).encode('utf-8')
                        with prop.open('xb') as stream:
                            stream.write(foreign_bytes)
                        child.stdin.write(b'continue\n')
                        outcome = json.loads(child.read_line(30))
                        check.evidence('current_outcome', outcome)
                        v.require(outcome.get('ok') is False and outcome['recovery_pending'], 'Foreign entry was overwritten', outcome)
                        v.require(prop.read_bytes() == foreign_bytes, 'Competing entry changed')
                        v.require(win32event.WaitForSingleObject(child.process, 5000) == win32con.WAIT_OBJECT_0,
                                  'Conflict helper did not release its library lease')
                        await check.rejected('project_library', 'conflict', session_id=sid, operation='media_get', options={'clip_id': clip_id})
                        v.require(prop.read_bytes() == foreign_bytes, 'Recovery overwrote the foreign entry')
                        prop.unlink()  # Explicitly remove only this test's own competing entry.
                    else:
                        win32process.TerminateProcess(child.process, 97)
                        v.require(win32event.WaitForSingleObject(child.process, 5000) == win32con.WAIT_OBJECT_0,
                                  'Owned crash-test process remained live')
                finally:
                    child.close()
                observed = await check.library('media_get', sid, clip_id=clip_id)
                expected = candidate.read_bytes() if phase == 'committed' else before
                v.require(prop.read_bytes() == expected, 'Recovery selected the wrong durable state', phase)
                v.require(observed['name'] == json.loads(expected)['name'], 'Native cache did not follow recovery', observed)
                v.require(not stage.exists() and not stage.with_name('completed-' + stage.name).exists(), 'Resolved journal was not cleaned')
                v.require(path.read_bytes() == original_clip, 'Recovery modified the clip payload')
                report.append({'phase': phase, 'name': observed['name'], 'resolved': True})
        except BaseException as error:
            failed = True
            check.evidence('failure_before_cleanup', str(error))
            raise
        finally:
            if not failed:
                await check.library('media_delete', sid, clip_id=clip_id)


@v.feature('library.media_conflict_32', 'library', 'score_compose', 'project_library')
async def media_conflict(check):
    await media_recovery(check, ('foreign',))


if __name__ == '__main__':
    if '--case' not in sys.argv:
        sys.argv.extend(['--case', 'library.media_recovery_32'])
    raise SystemExit(v.main())
