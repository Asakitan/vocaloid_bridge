"""Historical 0.19.0 transaction observation; not a current release gate."""
import sys
import verify_features as v

@v.feature('lyrics_transaction28', 'lyrics_transaction28', 'score_compose', 'project_get', 'project_set', 'project_items', 'project_library', 'project_edit', 'project_status')
async def probe(check):
    report = {}
    check.evidence('transactions', report)
    async def snapshot(sid):
        return {'status': await check.call('project_status', session_id=sid),
                'history': await check.edit(sid, 'history.status'),
                'tempo': await check.edit(sid, 'tempo.list'),
                'notes': await check.edit(sid, 'note.list', track_index=0, part_index=0)}
    for label, lyric in [('success', 'い'), ('empty', ''), ('spaces', '   '), ('newline', '\n')]:
        record = report[label] = {'input': lyric}
        sid = None
        try:
            seed = await check.call('score_compose', output_name=check.output('lyric-transaction-'+label), title='Transaction fixture', bpm=120,
                                    notes=[{'start': 0, 'duration': 1, 'pitch': 60, 'lyric': 'あ', 'phoneme': 'a', 'lang_id': 0}])
            sid = seed['native_session']['session_id']
            sequence, _ = v.read_vpr(seed['path'])
            def has_extension(x):
                return isinstance(x, dict) and ('directPitches' in x or any(has_extension(y) for y in x.values())) or isinstance(x, list) and any(has_extension(y) for y in x)
            v.require(not has_extension(sequence), 'Fixture has directPitches')
            record['before'] = await snapshot(sid)
            tempos = (await check.call('project_get', session_id=sid, member='Tempos'))['value']
            tempo = (await check.call('project_items', session_id=sid, ref=tempos['$ref']))['items'][0]
            old = (await check.call('project_get', session_id=sid, ref=tempo['$ref'], member='Value'))['value']
            record['set_tempo'] = await check.call('project_set', session_id=sid, ref=tempo['$ref'], member='Value', value=old+100)
            record['staged'] = await snapshot(sid)
            try:
                record['apply'] = await check.library('lyrics_apply', sid, track_index=0, part_index=0, note_index=0, language_id=0, lyrics=lyric, protect=False)
                record['apply_outcome'] = 'success'
            except Exception as error:
                record['apply_outcome'] = 'error'
                record['apply_error'] = f'{type(error).__name__}: {error}'
            record['after'] = await snapshot(sid)
            record['rollback'] = await check.edit(sid, 'history.rollback')
            record['after_rollback'] = await snapshot(sid)
            record['status'] = 'observed'
        except Exception as error:
            record['status'] = 'error'
            record['error'] = f'{type(error).__name__}: {error}'
        finally:
            if sid:
                await check.close(sid)
    v.require(all(r['status'] == 'observed' for r in report.values()), 'Observation incomplete', report)

if __name__ == '__main__':
    if not any(x in ('--case', '--category') for x in sys.argv[1:]):
        sys.argv.extend(['--case', 'lyrics_transaction28'])
    sys.exit(v.main())
