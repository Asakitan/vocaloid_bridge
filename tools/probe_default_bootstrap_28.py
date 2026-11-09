"""Observe native default-pair bootstrapping in isolated asa AI projects."""
import sys
import verify_features as v

@v.feature('default_bootstrap28', 'default_bootstrap28', 'project_create', 'voicebanks', 'project_library', 'project_edit', 'project_save', 'project_open')
async def probe(check):
    report = {'cases': {}}
    check.evidence('bootstrap', report)
    report['languages'] = await check.library('languages')
    voices = await check.call('voicebanks')
    voice = next(x for x in voices['voices'] if x['name'] == 'asa' and x['kind'] == 'Dnn' and x['synthesizable_version'])
    report['voice'] = voice
    for lang, default, phoneme, target in [(0, 'あ', 'a', 'い'), (1, 'Ooh', 'u:', 'cat'), (4, 'a', 'a', 'ni')]:
        r = report['cases'][str(lang)] = {'editor_first_pair': [default, phoneme], 'target': target}
        sid = None
        try:
            r['native_default'] = next(x for x in report['languages'] if x['language_id'] == lang)
            r['default_matches'] = r['native_default']['default_lyric'] == default
            v.require(r['default_matches'], 'Manager default differs from editor first pair', r)
            sid = (await check.call('project_create', title='Synthetic bootstrap', bpm=120))['session_id']
            track = await check.edit(sid, 'track.create', name='AI bootstrap')
            v.require(track['type'] == 'MidiAi', 'Not AI', track)
            part = await check.edit(sid, 'part.create', track_index=track['track_index'], start_tick=0, duration_tick=1920, name='Empty')
            v.require(part['note_count'] == 0, 'Not empty', part)
            scope = {'track_index': track['track_index'], 'part_index': part['part_index']}
            r['voice_assignment'] = await check.edit(sid, 'voice.set', **scope, ai_voice_bank_id=voice['comp_id'])
            r['initial_notes'] = await check.edit(sid, 'note.list', **scope)
            r['add'] = await check.edit(sid, 'note.add', **scope, start_tick=0, duration_tick=480, number=60, lyric=default, phonemes=phoneme, lang_id=lang)
            r['seed_notes'] = await check.edit(sid, 'note.list', **scope)
            r['can_convert'] = await check.library('lyrics_can_convert', language_id=lang, lyrics=target, is_ai=True, use_extension_dictionary=False)
            try:
                r['apply'] = await check.library('lyrics_apply', sid, **scope, note_index=0, language_id=lang, lyrics=target, protect=False)
            except Exception as e:
                r['apply_error'] = f'{type(e).__name__}: {e}'
            r['after'] = await check.edit(sid, 'note.list', **scope)
            sequence, path = await check.save(sid, 'bootstrap28-'+str(lang))
            r['saved_notes'] = sequence['tracks'][scope['track_index']]['parts'][scope['part_index']]['notes']
            r['path'] = str(path)
            await check.close(sid); sid = None
            sid = (await check.call('project_open', path=str(path)))['session_id']
            r['reopened'] = await check.edit(sid, 'note.list', **scope)
            r['status'] = 'observed'
        except Exception as e:
            r['status'] = 'error'; r['error'] = f'{type(e).__name__}: {e}'
        finally:
            if sid: await check.close(sid)
    v.require(all(x['status'] == 'observed' for x in report['cases'].values()), 'Observation incomplete', report)

if __name__ == '__main__':
    if not any(x in ('--case','--category') for x in sys.argv[1:]): sys.argv.extend(['--case','default_bootstrap28'])
    sys.exit(v.main())
