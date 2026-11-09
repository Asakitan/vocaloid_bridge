"""Probe native journal behavior for a net-zero metadata-only transaction."""
import json
import sys
import zipfile
import verify_features as v


@v.feature('preservation.metadata_native_marker_probe', 'preservation', 'project_create', 'project_get', 'project_set', 'project_call', 'project_edit', 'project_save')
async def native_marker_probe(check):
    async with check.project() as sid:
        title = (await check.call('project_get', session_id=sid, member='Title'))['value']
        initial = await check.edit(sid, 'history.status')
        await check.call('project_set', session_id=sid, member='Title', value=title + ' (temporary marker)')
        intermediate = await check.edit(sid, 'history.status')
        await check.call('project_set', session_id=sid, member='Title', value=title)
        restored = await check.edit(sid, 'history.status')
        outcome = {'initial': initial, 'intermediate': intermediate, 'restored': restored}
        if restored['staged']:
            outcome['commit'] = await check.method(sid, 'Commit', [True])
            outcome['committed'] = await check.edit(sid, 'history.status')
            if outcome['committed']['can_undo']:
                outcome['undo'] = await check.edit(sid, 'undo')
                outcome['undo_title'] = (await check.call('project_get', session_id=sid, member='Title'))['value']
                if outcome['undo']['can_redo']:
                    outcome['redo'] = await check.edit(sid, 'redo')
                    outcome['redo_title'] = (await check.call('project_get', session_id=sid, member='Title'))['value']
        check.evidence('native_noop_marker', outcome)
        v.require(not initial['can_undo'] and not intermediate['staged'] and not restored['staged'],
                  'Native title staging behavior differs from the observed negative probe', outcome)


@v.feature('preservation.metadata_tempo_marker_probe', 'preservation', 'project_create', 'project_get', 'project_set', 'project_call', 'project_edit', 'project_save')
async def native_tempo_marker_probe(check):
    async with check.project() as sid:
        await check.edit(sid, 'tempo.set', start_tick=1920, bpm=130)
        baseline = (await check.edit(sid, 'tempo.list'))['tempos']
        tempos = (await check.call('project_get', session_id=sid, member='Tempos'))['value']
        item = (await check.call('project_items', session_id=sid, ref=tempos['$ref']))['items'][0]
        value = (await check.call('project_get', session_id=sid, ref=item['$ref'], member='Value'))['value']
        await check.call('project_set', session_id=sid, ref=item['$ref'], member='Value', value=value + 1)
        changed = await check.edit(sid, 'history.status')
        await check.call('project_set', session_id=sid, ref=item['$ref'], member='Value', value=value)
        restored = await check.edit(sid, 'history.status')
        outcome = {'changed': changed, 'restored': restored, 'baseline': baseline}
        if restored['staged']:
            outcome['commit'] = await check.method(sid, 'Commit', [True])
            outcome['committed'] = await check.edit(sid, 'history.status')
            await check.edit(sid, 'undo')
            outcome['first_undo'] = (await check.edit(sid, 'tempo.list'))['tempos']
            await check.edit(sid, 'undo')
            outcome['second_undo'] = (await check.edit(sid, 'tempo.list'))['tempos']
            await check.edit(sid, 'redo')
            await check.edit(sid, 'redo')
            outcome['redo'] = (await check.edit(sid, 'tempo.list'))['tempos']
        check.evidence('native_tempo_marker', outcome)
        v.require(outcome.get('first_undo') == baseline and outcome.get('redo') == baseline and
                  len(outcome.get('second_undo', [])) == len(baseline) - 1,
                  'Native history did not retain a separate net-zero tempo transaction', outcome)


@v.feature('preservation.metadata_only_merge', 'preservation', 'project_create', 'project_merge', 'project_edit', 'project_save', 'project_open')
async def metadata_only_merge(check):
    async with check.project() as seed:
        source_json, source_path = await check.save(seed, 'metadata-only-seed')
    _, source_members = v.read_vpr(source_path)
    source_json['x_metadata_only'] = {'source': [1, None, True]}
    source_json['masterTrack']['loop']['x_metadata_only'] = 'loop'
    source_members['Project/sequence.json'] = json.dumps(source_json, ensure_ascii=False).encode('utf-8')
    source_members['Extras/metadata-only.bin'] = b'metadata-only-resource'
    source = v.ROOT / 'output' / check.output('metadata-only-source')
    with zipfile.ZipFile(source, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in source_members.items():
            archive.writestr(name, data)
    original = source.read_bytes()
    async with check.project() as unchanged_target:
        await check.edit(unchanged_target, 'track.create', type='MidiAi', name='Existing track')
        dirty_status = await check.call('project_status', session_id=unchanged_target)
        dirty_history = await check.edit(unchanged_target, 'history.status')
        await check.call('project_merge', session_id=unchanged_target, path=str(source_path),
                         include_tracks=True, include_tempo=False)
        v.require(await check.call('project_status', session_id=unchanged_target) == dirty_status and
                  await check.edit(unchanged_target, 'history.status') == dirty_history,
                  'Empty ordinary merge changed dirty target status or history')
        await check.save(unchanged_target, 'empty-merge-target')
        before_status = await check.call('project_status', session_id=unchanged_target)
        before_history = await check.edit(unchanged_target, 'history.status')
        await check.call('project_merge', session_id=unchanged_target, path=str(source_path),
                         include_tracks=True, include_tempo=False)
        v.require(await check.call('project_status', session_id=unchanged_target) == before_status and
                  await check.edit(unchanged_target, 'history.status') == before_history,
                  'Empty ordinary merge changed target status or history')
    async with check.project() as target:
        await check.edit(target, 'track.create', type='MidiAi', name='Existing history')
        before, before_path = await check.save(target, 'metadata-only-before')
        await check.call('project_merge', session_id=target, path=str(source), include_tracks=True, include_tempo=False)
        merged, merged_path = await check.save(target, 'metadata-only-merged')
        v.require(merged['x_metadata_only'] == {'source': [1, None, True]} and
                  merged['masterTrack']['loop']['x_metadata_only'] == 'loop' and
                  v.read_vpr(merged_path)[1]['Extras/metadata-only.bin'] == b'metadata-only-resource' and
                  merged['tracks'] == before['tracks'] and merged['masterTrack']['tempo'] == before['masterTrack']['tempo'],
                  'Metadata-only merge changed native content or lost metadata')
        history = await check.edit(target, 'history.status')
        status = await check.call('project_status', session_id=target)
        await check.call('project_merge', session_id=target, path=str(source), include_tracks=True, include_tempo=False)
        v.require(await check.edit(target, 'history.status') == history and
                  await check.call('project_status', session_id=target) == status,
                  'Equal metadata merge changed history or project status')
        await check.edit(target, 'undo')
        undone, undone_path = await check.save(target, 'metadata-only-undo')
        v.require(undone == before and v.read_vpr(undone_path)[1] == v.read_vpr(before_path)[1],
                  'Metadata-only undo did not restore target')
        await check.edit(target, 'undo')
        older, _ = await check.save(target, 'metadata-only-old-undo')
        v.require(older.get('tracks', []) == [], 'Earlier native history was lost')
        await check.edit(target, 'redo')
        await check.edit(target, 'redo')
        redone, redone_path = await check.save(target, 'metadata-only-redo')
        v.require(redone == merged and v.read_vpr(redone_path)[1]['Extras/metadata-only.bin'] == b'metadata-only-resource',
                  'Metadata-only redo lost content')
        reopened = (await check.call('project_open', path=str(redone_path)))['session_id']
        try:
            check_json, check_path = await check.save(reopened, 'metadata-only-reopened')
            v.require(check_json == merged and v.read_vpr(check_path)[1]['Extras/metadata-only.bin'] == b'metadata-only-resource',
                      'Reopened metadata-only result differs')
        finally:
            await check.close(reopened)
        await check.edit(target, 'undo')
        await check.edit(target, 'track.create', type='MidiAi', name='New branch')
        branched, branched_path = await check.save(target, 'metadata-only-branch')
        v.require('x_metadata_only' not in branched and 'Extras/metadata-only.bin' not in v.read_vpr(branched_path)[1] and
                  not (await check.edit(target, 'history.status'))['can_redo'], 'New history branch resurrected metadata')

    seed = await check.call('score_compose', output_name=check.output('metadata-extended-seed'),
                            title='Metadata extended target', bpm=120,
                            notes=[{'start': 0, 'duration': .5, 'pitch': 60,
                                    'lyric': 'あ', 'phoneme': 'a', 'lang_id': 0}])
    await check.close(seed['native_session']['session_id'])
    extended, members = v.read_vpr(seed['path'])
    extended['x_target'] = 'existing-root'
    extended['tracks'][0]['parts'][0]['notes'][0]['x_target'] = 'existing-note'
    members['Project/sequence.json'] = json.dumps(extended, ensure_ascii=False).encode('utf-8')
    extended_path = v.ROOT / 'output' / check.output('metadata-extended-target')
    with zipfile.ZipFile(extended_path, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    extended_original = extended_path.read_bytes()
    target = (await check.call('project_open', path=str(extended_path)))['session_id']
    try:
        await check.edit(target, 'note.update', track_index=0, part_index=0, note_index=0, number=61)
        before, _ = await check.save(target, 'metadata-extended-before')
        await check.call('project_merge', session_id=target, path=str(source), include_tracks=True, include_tempo=False)
        merged, merged_path = await check.save(target, 'metadata-extended-merged')
        v.require(merged['x_target'] == 'existing-root' and merged['x_metadata_only'] == {'source': [1, None, True]} and
                  merged['tracks'][0]['parts'][0]['notes'][0]['x_target'] == 'existing-note' and
                  merged['tracks'][0]['parts'][0]['notes'][0]['number'] == 61 and
                  v.read_vpr(merged_path)[1]['Extras/metadata-only.bin'] == b'metadata-only-resource',
                  'Metadata-only merge lost existing target extensions')
        await check.edit(target, 'undo')
        undone, _ = await check.save(target, 'metadata-extended-undo')
        v.require(undone == before, 'Metadata-only undo changed the extended target')
        await check.edit(target, 'undo')
        old, _ = await check.save(target, 'metadata-extended-old-undo')
        v.require(old['tracks'][0]['parts'][0]['notes'][0]['number'] == 60 and
                  old['tracks'][0]['parts'][0]['notes'][0]['x_target'] == 'existing-note',
                  'Metadata-only merge lost earlier extended history')
        await check.edit(target, 'redo')
        await check.edit(target, 'redo')
        redone, _ = await check.save(target, 'metadata-extended-redo')
        v.require(redone == merged, 'Metadata-only redo changed extended target')
    finally:
        await check.close(target)
    v.require(extended_path.read_bytes() == extended_original, 'Extended target source file changed')

    conflict = json.loads(json.dumps(extended))
    conflict['x_metadata_only'] = 'conflicting-value'
    members['Project/sequence.json'] = json.dumps(conflict, ensure_ascii=False).encode('utf-8')
    conflict_path = v.ROOT / 'output' / check.output('metadata-only-conflict')
    with zipfile.ZipFile(conflict_path, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    conflict_session = (await check.call('project_open', path=str(conflict_path)))['session_id']
    try:
        before, _ = await check.save(conflict_session, 'metadata-conflict-before')
        history = await check.edit(conflict_session, 'history.status')
        await check.rejected('project_merge', 'extension conflicts', session_id=conflict_session,
                             path=str(source), include_tracks=True, include_tempo=False)
        after, _ = await check.save(conflict_session, 'metadata-conflict-after')
        v.require(after == before and await check.edit(conflict_session, 'history.status') == history,
                  'Rejected metadata conflict changed target or history')
    finally:
        await check.close(conflict_session)
    async with check.project() as limit_target:
        maximum = (await check.method(limit_target, 'GetMaxTempoValue', []))['value']
        await check.edit(limit_target, 'tempo.set', start_tick=0, bpm=maximum / 100)
        before = (await check.edit(limit_target, 'tempo.list'))['tempos']
        await check.call('project_merge', session_id=limit_target, path=str(source), include_tracks=True, include_tempo=False)
        v.require((await check.edit(limit_target, 'tempo.list'))['tempos'] == before,
                  'Metadata history marker changed maximum native tempo')
        await check.edit(limit_target, 'undo')
        v.require((await check.edit(limit_target, 'tempo.list'))['tempos'] == before,
                  'Metadata undo changed maximum native tempo')
        await check.edit(limit_target, 'redo')
        v.require((await check.edit(limit_target, 'tempo.list'))['tempos'] == before,
                  'Metadata redo changed maximum native tempo')
    v.require(source.read_bytes() == original, 'Metadata-only source file changed')


if __name__ == '__main__':
    if '--case' not in sys.argv:
        sys.argv.extend(['--case', 'preservation.metadata_only_merge'])
    raise SystemExit(v.main())
