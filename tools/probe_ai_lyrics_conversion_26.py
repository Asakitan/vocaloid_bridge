"""Observe native lyric conversion in independent ordinary synthetic AI projects."""
import sys
import verify_features as v

def has_pitch(x):
    return (isinstance(x, dict) and ('directPitches' in x or any(has_pitch(y) for y in x.values()))
            or isinstance(x, list) and any(has_pitch(y) for y in x))

@v.feature('ai_lyrics26', 'ai_lyrics26', 'score_compose', 'project_library', 'project_edit', 'project_save', 'project_open', 'voicebanks')
async def probe(check):
    report = {}
    check.evidence('conversion', report)
    report['installed_voicebanks'] = await check.call('voicebanks')
    for label, language, lyric in [('japanese', 0, 'い'), ('english', 1, 'hello'), ('chinese', 4, '你'), ('unconvertible', 0, '😀')]:
        record = report[label] = {'language_id': language, 'lyric': lyric}
        sid = None
        try:
            seed = await check.call('score_compose', output_name=check.output('lyrics26-'+label), title='Synthetic lyrics conversion', bpm=120,
                                    notes=[{'start': 0, 'duration': 1, 'pitch': 60, 'lyric': 'あ', 'phoneme': 'a', 'lang_id': 0}])
            sid = seed['native_session']['session_id']
            seq, _ = v.read_vpr(seed['path'])
            v.require(not has_pitch(seq), 'Seed has directPitches')
            record['voice'] = await check.edit(sid, 'voice.get', track_index=0, part_index=0)
            record['seed_ai_voice'] = seq['tracks'][0]['parts'][0].get('aiVoice')
            record['before'] = await check.edit(sid, 'note.list', track_index=0, part_index=0)
            record['can_convert'] = await check.library('lyrics_can_convert', language_id=language, lyrics=lyric, is_ai=True)
            selected = {'track_index': 0, 'part_index': 0, 'note_index': 0, 'language_id': language}
            record['candidates'] = await check.library('lyrics_candidates', sid, **selected, lyrics=lyric)
            try:
                record['apply'] = await check.library('lyrics_apply', sid, **selected, lyrics=lyric, protect=False)
                record['apply_status'] = 'completed'
            except Exception as error:
                record['apply_status'] = 'error'
                record['apply_error'] = f'{type(error).__name__}: {error}'
            record['after'] = await check.edit(sid, 'note.list', track_index=0, part_index=0)
            saved, path = await check.save(sid, 'lyrics26-saved-'+label)
            record['saved_notes'] = saved['tracks'][0]['parts'][0]['notes']
            await check.close(sid); sid = None
            opened = await check.call('project_open', path=str(path))
            sid = opened['session_id']
            record['reopened'] = await check.edit(sid, 'note.list', track_index=0, part_index=0)
            record['status'] = 'observed'
        except Exception as error:
            record['status'] = 'error'
            record['error'] = f'{type(error).__name__}: {error}'
        finally:
            if sid:
                await check.close(sid)
    v.require(all(report[x]['status'] == 'observed' for x in ('japanese','english','chinese','unconvertible')), 'Observation incomplete', report)

if __name__ == '__main__':
    if not any(x in ('--case', '--category') for x in sys.argv[1:]):
        sys.argv.extend(['--case', 'ai_lyrics26'])
    sys.exit(v.main())
