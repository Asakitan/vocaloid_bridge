"""Observe native G2PA candidate validation, without production integration."""
import sys
import verify_features as v

@v.feature('compose_resolver28', 'compose_resolver28', 'score_compose', 'project_library', 'project_edit')
async def probe(check):
    cases=[(0,'い'),(0,'か'),(0,'きゃ'),(0,'こんにちは'),(1,'cat'),(1,'CAT'),(1,'hello'),(4,'ni'),(4,'hao'),(4,'你好'),(4,'ni3')]
    results={}; check.evidence('cases',results)
    for i,(lang,lyric) in enumerate(cases):
        sid=None; rec=results[str(i)]={'language_id':lang,'request':lyric}
        try:
            seed=await check.call('score_compose',output_name=check.output('resolver28-'+str(i)),title='Synthetic resolver',bpm=120,notes=[{'start':n,'duration':1,'pitch':60+n,'lyric':'あ','phoneme':'a','lang_id':0} for n in range(3)])
            sid=seed['native_session']['session_id']
            rec['voice']=await check.edit(sid,'voice.get',track_index=0,part_index=0)
            rec['before']=await check.edit(sid,'note.list',track_index=0,part_index=0)
            rec['can']=await check.library('lyrics_can_convert',language_id=lang,lyrics=lyric,is_ai=True,use_extension_dictionary=False)
            rec['candidates']=await check.library('lyrics_candidates',sid,track_index=0,part_index=0,note_index=1,language_id=lang,lyrics=lyric,use_extension_dictionary=False)
            try:
                rec['apply']=await check.library('lyrics_apply',sid,track_index=0,part_index=0,note_index=1,language_id=lang,lyrics=lyric,protect=False)
            except Exception as e: rec['apply_error']=f'{type(e).__name__}: {e}'
            rec['after']=await check.edit(sid,'note.list',track_index=0,part_index=0)
            target=rec['after']['notes'][1]; candidates=rec['candidates']['candidates']
            single=[c[0] for c in candidates if len(c)==1]
            match=any(c['lyric']==target['lyric'] and c['phonemes']==target['phonemes'] for c in single)
            rec['rule_accept'] = bool(rec['can']['can_convert'] and rec.get('apply',{}).get('affected_length')==1 and target['phonemes'] and target['is_valid_phonemes'] and (match if candidates else target['lyric']==lyric))
            rec['neighbors_changed'] = [n for n in (0,2) if rec['before']['notes'][n] != rec['after']['notes'][n]]
            rec['status']='observed'
        except Exception as e: rec['status']='error'; rec['error']=f'{type(e).__name__}: {e}'
        finally:
            if sid: await check.close(sid)
    v.require(all(r['status']=='observed' for r in results.values()),'Incomplete observations',results)

if __name__=='__main__':
    if not any(x in ('--case','--category') for x in sys.argv[1:]): sys.argv.extend(['--case','compose_resolver28'])
    sys.exit(v.main())
