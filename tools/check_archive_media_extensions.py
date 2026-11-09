"""Synthetic AI VMM archive entity round-trip acceptance against the native host."""
import json
import sys
import tempfile
from pathlib import Path
import zipfile
import verify_features as v
from check_archive_audio_transfer import make_wave

@v.feature('preservation.media_entities', 'preservation', 'score_compose', 'project_open', 'project_save', 'project_clone', 'project_edit', 'project_library')
async def media_entities(check):
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
        before_clip = Path(captured['path']).read_bytes()
        await check.library('media_update', sid, clip_id=clip_id, name='Updated ' + check.run_id)
        v.require(Path(captured['path']).read_bytes() == before_clip, 'Property edit changed archived clip bytes')
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
            # Extended import/edit success is covered by agent_mutations_33.
            await check.rejected('project_audio', 'audio|track', session_id=sid,
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
    sys.argv.extend(['--case', 'preservation.media_entities'])
    raise SystemExit(v.main())
