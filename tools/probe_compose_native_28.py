"""Observe native omitted-phoneme composition prerequisites; no production changes."""
import sys
import verify_features as v

@v.feature('compose_native28', 'compose_native28', 'score_compose', 'project_edit', 'project_save', 'project_open')
async def probe(check):
    cases = [('empty_jp', [], {'lyric':'い','lang_id':0}), ('jp_context', [('あ','a',0)], {'lyric':'い','lang_id':0}), ('en_context', [('hello','h @ l oU',1)], {'lyric':'hello','lang_id':1}), ('zh_context', [('ni','n i',4)], {'lyric':'hao','lang_id':4}), ('jp_phrase', [('あ','a',0)], {'lyric':'こんにちは','lang_id':0}), ('bad', [('あ','a',0)], {'lyric':'','lang_id':0})]
    results = {}; check.evidence('cases', results)
    for label, context, fields in cases:
        rec = results[label] = {'input':fields}; sid = None
        try:
            notes = [{'start':i,'duration':1,'pitch':60+i,'lyric':ly,'phoneme':ph,'lang_id':lang} for i,(ly,ph,lang) in enumerate(context)]
            seed = await check.call('score_compose', output_name=check.output('compose28-'+label), title='Independent AI template', bpm=120, notes=notes)
            sid = seed['native_session']['session_id']; rec['source_path'] = seed['path']
            rec['voice'] = await check.edit(sid, 'voice.get', track_index=0, part_index=0)
            rec['before'] = await check.edit(sid, 'note.list', track_index=0, part_index=0)
            rec['before_status'] = await check.call('project_status', session_id=sid)
            rec['before_history'] = await check.edit(sid, 'history.status')
            try:
                rec['add'] = await check.edit(sid, 'note.add', track_index=0, part_index=0, start_tick=1920, duration_tick=480, number=64, **fields)
                rec['add_status'] = 'completed'
            except Exception as e:
                rec['add_status'] = 'error'; rec['add_error'] = f'{type(e).__name__}: {e}'
            rec['after'] = await check.edit(sid, 'note.list', track_index=0, part_index=0)
            rec['after_status'] = await check.call('project_status', session_id=sid)
            rec['after_history'] = await check.edit(sid, 'history.status')
            saved, path = await check.save(sid, 'compose28-saved-'+label)
            rec['saved_path'] = str(path); rec['saved_notes'] = saved['tracks'][0]['parts'][0].get('notes', [])
            rec['source_notes'] = v.read_vpr(seed['path'])[0]['tracks'][0]['parts'][0].get('notes', [])
            await check.close(sid); sid = None
            sid = (await check.call('project_open', path=str(path)))['session_id']
            rec['reopened'] = await check.edit(sid, 'note.list', track_index=0, part_index=0)
            rec['status'] = 'observed'
        except Exception as e:
            rec['status'] = 'error'; rec['error'] = f'{type(e).__name__}: {e}'
        finally:
            if sid: await check.close(sid)
    v.require(all(r['status']=='observed' for r in results.values()), 'Observation incomplete', results)

if __name__ == '__main__':
    if not any(x in ('--case','--category') for x in sys.argv[1:]): sys.argv.extend(['--case','compose_native28'])
    sys.exit(v.main())
