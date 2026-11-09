"""Independent native AI note initialization observations."""
import sys
import verify_features as v

@v.feature('native_note27', 'native_note27', 'score_compose', 'project_edit', 'project_save', 'project_open', 'project_render_part')
async def probe(check):
    report = {}
    check.evidence('cases', report)
    for label, fields in [('default', {}), ('jp', {'lyric':'い'}), ('explicit', {'lyric':'い','phonemes':'i'}), ('empty', {'lyric':''}), ('phrase', {'lyric':'こんにちは'}), ('english', {'lyric':'hello','lang_id':1}), ('chinese', {'lyric':'你','lang_id':4}), ('emoji', {'lyric':'😀'})]:
        rec = report[label] = {'input': fields}; sid = None
        try:
            seed = await check.call('score_compose', output_name=check.output('note27-'+label), title='Synthetic native note', bpm=120, notes=[{'start':0,'duration':1,'pitch':60,'lyric':'あ','phoneme':'a','lang_id':0}])
            sid = seed['native_session']['session_id']
            seq, _ = v.read_vpr(seed['path'])
            def forbidden(x):
                return isinstance(x, dict) and (any(k in x for k in ('directPitches','controllers','automations')) or any(forbidden(y) for y in x.values())) or isinstance(x, list) and any(forbidden(y) for y in x)
            v.require(not forbidden(seq), 'Fixture contains forbidden extension')
            rec['before_history'] = await check.edit(sid, 'history.status')
            rec['before'] = await check.edit(sid, 'note.list', track_index=0, part_index=0)
            try:
                rec['add'] = await check.edit(sid, 'note.add', track_index=0, part_index=0, start_tick=1920, duration_tick=480, number=64, **fields)
                rec['add_status'] = 'completed'
            except Exception as e:
                rec['add_status'] = 'error'; rec['add_error'] = f'{type(e).__name__}: {e}'
            rec['after'] = await check.edit(sid, 'note.list', track_index=0, part_index=0)
            rec['after_history'] = await check.edit(sid, 'history.status')
            if rec['add_status'] == 'completed':
                saved, path = await check.save(sid, 'note27-saved-'+label)
                rec['saved_notes'] = saved['tracks'][0]['parts'][0]['notes']
                await check.close(sid); sid = None
                sid = (await check.call('project_open', path=str(path)))['session_id']
                rec['reopened'] = await check.edit(sid, 'note.list', track_index=0, part_index=0)
                wav = await check.call('project_render_part', session_id=sid, track_index=0, part_index=0, output_name=check.output('note27-'+label,'.wav'))
                meta, samples = v.read_audio(wav['path'], nonzero=False)
                import numpy as np
                window = samples[int(2.6*meta['sample_rate']):int(2.9*meta['sample_rate'])]
                rec['wav'] = {'path':wav['path'], **meta, 'window_peak':float(np.max(np.abs(window))), 'window_rms':float(np.sqrt(np.mean(window*window)))}
            rec['status']='observed'
        except Exception as e:
            rec['status']='error'; rec['error']=f'{type(e).__name__}: {e}'
        finally:
            if sid: await check.close(sid)
    v.require(all(r['status']=='observed' for r in report.values()), 'Incomplete observation', report)

if __name__ == '__main__':
    if not any(x in ('--case','--category') for x in sys.argv[1:]): sys.argv.extend(['--case','native_note27'])
    sys.exit(v.main())
