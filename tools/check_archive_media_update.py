"""Private native media property save and locked-file failure probe."""
import json
import sys
import tempfile
import zipfile
from check_archive_audio_transfer import make_wave
from pathlib import Path
import win32con
import win32file
import verify_features as v

@v.feature('preservation.media_update_probe', 'preservation', 'score_compose', 'project_library', 'project_edit', 'project_save', 'project_open')
async def media_update_probe(check):
    async with check.project(score=True) as sid:
        clip = (await check.library('media_capture', sid, track_index=0, part_index=0, name='Probe ' + check.run_id, tempo=12000))['clip']
        clip_id = clip['clip_id']
        path = Path(clip['path']).resolve()
        root = (v.ROOT / '.runtime' / 'library' / 'media').resolve()
        v.require(path.is_relative_to(root) and path.name == clip_id + '.vsclip', 'Unexpected private clip path')
        prop = path.with_name('property.json')
        try:
            original_clip, original_prop = path.read_bytes(), prop.read_bytes()
            history = await check.edit(sid, 'history.status')
            updated = (await check.library('media_update', sid, clip_id=clip_id, name='Updated ' + check.run_id, tempo=12345, add_genres=['Probe'], add_types=['Probe']))['clip']
            saved_clip, saved_prop = path.read_bytes(), prop.read_bytes()
            v.require(saved_clip == original_clip and saved_prop != original_prop, 'Unexpected file changes')
            v.require(updated['clip_id'] == clip_id and updated['name'] == 'Updated ' + check.run_id and updated['tempo'] == 12345 and 'Probe' in updated['genres'] and 'Probe' in updated['types'], 'Update readback differs', updated)
            v.require(await check.library('media_get', clip_id=clip_id) == updated, 'media_get differs')
            v.require(await check.edit(sid, 'history.status') == history, 'Update changed project history')
            _, project = await check.save(sid, 'media-update-probe')
            reopened = (await check.call('project_open', path=str(project)))['session_id']
            try:
                v.require(await check.library('media_get', clip_id=clip_id) == updated, 'Readback after reopen differs')
            finally:
                await check.close(reopened)
            handle = win32file.CreateFile(str(prop), win32con.GENERIC_READ, win32con.FILE_SHARE_READ, None, win32con.OPEN_EXISTING, win32con.FILE_ATTRIBUTE_NORMAL, None)
            try:
                result = await check.raw('project_library', {'session_id': sid, 'operation': 'media_update', 'options': {'clip_id': clip_id, 'name': 'Locked ' + check.run_id, 'tempo': 13579}})
                response = ' '.join(getattr(item, 'text', str(item)) for item in result.content)
            finally:
                handle.Close()
            after_clip, after_prop = path.read_bytes(), prop.read_bytes()
            after = await check.library('media_get', clip_id=clip_id)
            evidence = {'clip_id': clip_id, 'success_property_changed': saved_prop != original_prop, 'success_clip_unchanged': saved_clip == original_clip, 'locked_request_error': result.isError, 'locked_response': response, 'locked_clip_unchanged': after_clip == saved_clip, 'locked_property_unchanged': after_prop == saved_prop, 'locked_catalog_unchanged': after == updated, 'locked_history_unchanged': await check.edit(sid, 'history.status') == history, 'property_after_lock': json.loads(after_prop), 'catalog_after_lock': after}
            check.evidence('media_update_probe', evidence)
            v.require(result.isError and evidence['locked_clip_unchanged'] and evidence['locked_property_unchanged'] and evidence['locked_catalog_unchanged'] and evidence['locked_history_unchanged'], 'Locked property failure was not atomic', evidence)
        finally:
            await check.library('media_delete', sid, clip_id=clip_id)

@v.feature('preservation.media_update_entities', 'preservation', 'score_compose', 'project_open', 'project_save', 'project_clone', 'project_edit', 'project_library')
async def media_update_entities(check):
    seed = await check.call('score_compose', output_name=check.output('media-entities-seed'), title='Media entities', bpm=120,
        notes=[{'start': 0, 'duration': 1, 'pitch': 60, 'lyric': 'あ', 'phoneme': 'a', 'lang_id': 0}])
    sid = seed['native_session']['session_id']
    await check.edit(sid, 'controller.set', track_index=0, part_index=0, type='Dynamics', points=[{'tick': 60, 'value': 30}], replace=True)
    seq, path = await check.save(sid, 'media-entities-seed')
    await check.close(sid)
    _, members = v.read_vpr(path)
    part = seq['tracks'][0]['parts'][0]
    part['x_media_part'] = {'nested': [True, None, 7]}
    part['notes'][0]['x_media_note'] = {'origin': 'synthetic'}
    members['Project/sequence.json'] = json.dumps(seq, ensure_ascii=False).encode()
    source = v.ROOT / 'output' / check.output('media-entities-input')
    with zipfile.ZipFile(source, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items(): archive.writestr(name, data)
    original = source.read_bytes()
    controller_seq = json.loads(json.dumps(seq))
    controller = next(c for c in controller_seq['tracks'][0]['parts'][0]['controllers'] if c['name'] == 'dynamics')
    controller['events'][0]['x_media_controller'] = 'guarded'
    controller_members = dict(members)
    controller_members['Project/sequence.json'] = json.dumps(controller_seq, ensure_ascii=False).encode()
    controller_path = v.ROOT / 'output' / check.output('media-controller-input')
    with zipfile.ZipFile(controller_path, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in controller_members.items(): archive.writestr(name, data)
    sid = (await check.call('project_open', path=str(source)))['session_id']
    clip_id = None
    try:
        captured = (await check.library('media_capture', sid, track_index=0, part_index=0, name='Entity ' + check.run_id))['clip']
        clip_id = captured['clip_id']
        clip_path = Path(captured['path']).resolve()
        root = (v.ROOT / '.runtime' / 'library' / 'media').resolve()
        v.require(clip_path.is_relative_to(root) and clip_path.name == clip_id + '.vsclip', 'Unexpected clip path')
        property_path = clip_path.with_name('property.json')
        before_clip, before_property = clip_path.read_bytes(), property_path.read_bytes()
        before_history = await check.edit(sid, 'history.status')
        updated = (await check.library('media_update', sid, clip_id=clip_id, name='Updated entities ' + check.run_id,
                                      tempo=12345, add_genres=['EntityProbe'], add_types=['EntityProbe']))['clip']
        v.require(updated['clip_id'] == clip_id and updated['name'] == 'Updated entities ' + check.run_id and
                  updated['tempo'] == 12345 and updated['key'] == captured['key'] and
                  'EntityProbe' in updated['genres'] and 'EntityProbe' in updated['types'], 'Updated properties differ', updated)
        v.require(clip_path.read_bytes() == before_clip and property_path.read_bytes() != before_property,
                  'Update changed clip bytes or failed to change properties')
        updated_property = property_path.read_bytes()
        handle = win32file.CreateFile(str(property_path), win32con.GENERIC_READ, win32con.FILE_SHARE_READ,
                                      None, win32con.OPEN_EXISTING, win32con.FILE_ATTRIBUTE_NORMAL, None)
        try:
            result = await check.raw('project_library', {'session_id': sid, 'operation': 'media_update',
                'options': {'clip_id': clip_id, 'name': 'Locked entities ' + check.run_id, 'tempo': 13579}})
            response = ' '.join(getattr(item, 'text', str(item)) for item in result.content)
        finally:
            handle.Close()
        observed = {'locked_request_error': result.isError, 'locked_response': response,
                    'clip_unchanged': clip_path.read_bytes() == before_clip,
                    'property_unchanged': property_path.read_bytes() == updated_property,
                    'catalog_unchanged': await check.library('media_get', clip_id=clip_id) == updated,
                    'history_unchanged': await check.edit(sid, 'history.status') == before_history}
        check.evidence('archive_media_update', observed)
        v.require(result.isError and all(observed[key] for key in ('clip_unchanged', 'property_unchanged', 'catalog_unchanged', 'history_unchanged')),
                  'Locked archive media update changed state', observed)
        controller_target = (await check.call('project_open', path=str(controller_path)))['session_id']
        try:
            controller_history = await check.edit(controller_target, 'history.status')
            await check.rejected('project_library', 'controller|archive', session_id=controller_target,
                                 operation='media_capture', options={'track_index': 0, 'part_index': 0, 'name': 'guarded controller'})
            await check.rejected('project_library', 'controller|identity transaction', session_id=controller_target,
                                 operation='media_import', options={'clip_id': clip_id, 'track_index': 0, 'position_tick': 15360})
            v.require(await check.edit(controller_target, 'history.status') == controller_history,
                      'Controller guard changed target history')
        finally: await check.close(controller_target)
        async with check.project(score=True) as ordinary:
            plain = (await check.library('media_capture', ordinary, track_index=0, part_index=0, name='Plain ' + check.run_id))['clip']['clip_id']
            try:
                control_clone = (await check.call('project_clone', session_id=ordinary))['session_id']
                try:
                    await check.library('media_import', control_clone, clip_id=plain, track_index=0, position_tick=15360)
                finally: await check.close(control_clone)
                await check.library('media_import', ordinary, clip_id=plain, track_index=0, position_tick=15360)
                await check.edit(ordinary, 'undo')
                await check.library('media_import', sid, clip_id=plain, track_index=0, position_tick=15360)
                plain_result, _ = await check.save(sid, 'media-plain-import')
                v.require(len(plain_result['tracks'][0]['parts']) == 2 and plain_result['tracks'][0]['parts'][0]['x_media_part'] == {'nested': [True, None, 7]}, 'Plain import changed extensions')
                await check.edit(sid, 'undo')
            finally: await check.library('media_delete', ordinary, clip_id=plain)
        with tempfile.TemporaryDirectory(prefix='bridge-media-guard-') as temp:
            wave_path = Path(temp) / 'fixture.wav'
            make_wave(wave_path, .03)
            source_history = await check.edit(sid, 'history.status')
            await check.rejected('project_audio', 'identity transaction|preservation', session_id=sid,
                                 operation='import_audio', options={'path': str(wave_path)})
            await check.rejected('project_audio', 'identity transaction|preservation', session_id=sid,
                                 operation='edit_audio', options={'track_index': 0, 'part_index': 0, 'name': 'guarded'})
            v.require(await check.edit(sid, 'history.status') == source_history,
                      'Audio guard changed target history')
            async with check.project() as audio:
                await check.call('project_audio', session_id=audio, operation='import_audio', options={'path': str(wave_path)})
                audio_clip = (await check.library('media_capture', audio, track_index=0, part_index=0, name='Audio ' + check.run_id))['clip']['clip_id']
                try:
                    await check.rejected('project_library', 'identity transaction|preservation', session_id=sid, operation='media_import',
                                         options={'clip_id': audio_clip, 'track_index': 0, 'position_tick': 0})
                finally: await check.library('media_delete', audio, clip_id=audio_clip)
        clip_path = Path(captured['path'])
        clip_bytes = clip_path.read_bytes()
        async with check.project() as target:
            await check.edit(target, 'track.create', type='MidiAi', name='Media target')
            await check.library('media_import', target, clip_id=clip_id, track_index=0, position_tick=0)
            cross, _ = await check.save(target, 'media-cross-target')
            cross_part = cross['tracks'][0]['parts'][0]
            v.require(cross_part.get('x_media_part') == {'nested': [True, None, 7]} and cross_part['notes'][0].get('x_media_note') == {'origin': 'synthetic'}, 'Cross-target payload changed')
            await check.edit(target, 'undo')
            undone, _ = await check.save(target, 'media-cross-undo')
            v.require(undone['tracks'][0].get('parts', []) == [], 'Cross-target undo retained the imported part')
            await check.edit(target, 'undo')
            prior, _ = await check.save(target, 'media-cross-prior')
            v.require(prior.get('tracks', []) == [], 'Pre-import history was lost')
            await check.edit(target, 'redo')
            await check.edit(target, 'redo')
            restored, _ = await check.save(target, 'media-cross-redo')
            v.require(restored['tracks'][0]['parts'][0].get('x_media_part') == {'nested': [True, None, 7]} and
                      restored['tracks'][0]['parts'][0]['notes'][0].get('x_media_note') == {'origin': 'synthetic'},
                      'Cross-target redo lost extensions')
        # Tamper only the disposable private clip and restore it before cleanup.
        try:
            data = json.loads(clip_bytes)
            metadata = data['vocaloid_bridge_archive_entities_v1']
            metadata['Notes'][0]['Number'] += 1
            clip_path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            await check.rejected('project_library', 'identity|metadata', session_id=sid, operation='media_import', options={'clip_id': clip_id, 'track_index': 0, 'position_tick': 15360})
            data = json.loads(clip_bytes)
            data['vocaloid_bridge_archive_entities_v1']['PartExtra']['/controllers'] = []
            clip_path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            await check.rejected('project_library', 'native field', session_id=sid, operation='media_import', options={'clip_id': clip_id, 'track_index': 0, 'position_tick': 15360})
            data = json.loads(clip_bytes)
            data['vocaloid_bridge_archive_entities_v1']['PartExtra']['/wav/x_missing'] = 1
            clip_path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            await check.rejected('project_library', 'parent is absent', session_id=sid, operation='media_import', options={'clip_id': clip_id, 'track_index': 0, 'position_tick': 15360})
        finally:
            clip_path.write_bytes(clip_bytes)
        unchanged, _ = await check.save(sid, 'media-rejected')
        v.require(len(unchanged['tracks'][0]['parts']) == 1, 'Rejected import changed target')
        await check.library('media_import', sid, clip_id=clip_id, track_index=0, position_tick=15360)
        before_conflict, _ = await check.save(sid, 'media-conflict-before')
        await check.rejected('project_library', 'ambiguous|insertion failed', session_id=sid, operation='media_import',
                             options={'clip_id': clip_id, 'track_index': 0, 'position_tick': 15360})
        after_conflict, _ = await check.save(sid, 'media-conflict-after')
        v.require(before_conflict == after_conflict, 'Conflicting import changed target')
        async def saved(label): return (await check.save(sid, label))[0]
        def verify(sequence, count):
            parts = sequence['tracks'][0]['parts']
            v.require(len(parts) == count, 'Unexpected part count')
            for item in parts:
                v.require(item.get('x_media_part') == {'nested': [True, None, 7]} and item['notes'][0].get('x_media_note') == {'origin': 'synthetic'}, 'Media extensions changed')
        verify(await saved('media-import'), 2)
        await check.edit(sid, 'undo'); verify(await saved('media-undo'), 1)
        await check.edit(sid, 'redo'); verify(await saved('media-redo'), 2)
        clone = (await check.call('project_clone', session_id=sid))['session_id']
        try: verify((await check.save(clone, 'media-clone'))[0], 2)
        finally: await check.close(clone)
        _, path = await check.save(sid, 'media-reopen')
        reopened = (await check.call('project_open', path=str(path)))['session_id']
        try: verify((await check.save(reopened, 'media-reopened'))[0], 2)
        finally: await check.close(reopened)
        v.require(source.read_bytes() == original, 'Source project changed')
    finally:
        if clip_id: await check.library('media_delete', sid, clip_id=clip_id)
        await check.close(sid)


if __name__ == '__main__':
    if '--case' not in sys.argv:
        sys.argv.extend(['--case', 'preservation.media_update_probe', '--case', 'preservation.media_update_entities'])
    raise SystemExit(v.main())
