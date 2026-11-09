"""Observe G2PA conversion on isolated synthetic AI projects."""
import sys
import verify_features as v


def has_pitch(x):
    return (isinstance(x, dict) and ('directPitches' in x or any(has_pitch(y) for y in x.values()))
            or isinstance(x, list) and any(has_pitch(y) for y in x))


@v.feature('g2pa_native28', 'g2pa_native28', 'score_compose', 'project_library', 'project_edit', 'project_save', 'project_open')
async def probe(check):
    report = {}
    check.evidence('conversion', report)
    cases = [('jpn_kana', 0, 'か'), ('jpn_katakana', 0, 'カ'), ('jpn_multisyllable', 0, 'こんにちは'),
             ('eng_one', 1, 'cat'), ('eng_upper', 1, 'CAT'), ('eng_multi', 1, 'hello'),
             ('chs_one', 4, 'ni'), ('chs_upper', 4, 'NI'), ('chs_tone', 4, 'ni3'),
             ('chs_hanzi', 4, '你'), ('chs_two', 4, 'ni hao'), ('eng_unknown', 1, '😀')]
    for label, language, lyric in cases:
        record = report[label] = {'language_id': language, 'lyric': lyric}
        sid = None
        try:
            seed = await check.call('score_compose', output_name=check.output('g2pa28-'+label), title='Synthetic lyrics', bpm=120,
                notes=[{'start': n, 'duration': 1, 'pitch': 60+n, 'lyric': 'あ', 'phoneme': 'a', 'lang_id': 0} for n in range(2)])
            sid = seed['native_session']['session_id']
            seq, _ = v.read_vpr(seed['path'])
            v.require(not has_pitch(seq), 'Seed has directPitches')
            record['voice'] = await check.edit(sid, 'voice.get', track_index=0, part_index=0)
            record['before'] = await check.edit(sid, 'note.list', track_index=0, part_index=0)
            record['status_before'] = await check.call('project_status', session_id=sid)
            record['history_before'] = await check.edit(sid, 'history.status')
            selected = {'track_index': 0, 'part_index': 0, 'note_index': 0, 'language_id': language}
            record['queries'] = {}
            for extension in (False, True):
                record['queries'][str(extension)] = {
                    'can_ai': await check.library('lyrics_can_convert', language_id=language, lyrics=lyric, is_ai=True, use_extension_dictionary=extension),
                    'can_non_ai': await check.library('lyrics_can_convert', language_id=language, lyrics=lyric, is_ai=False, use_extension_dictionary=extension),
                    'candidates': await check.library('lyrics_candidates', sid, **selected, lyrics=lyric, use_extension_dictionary=extension)}
            try:
                record['apply'] = await check.library('lyrics_apply', sid, **selected, lyrics=lyric, protect=False)
                record['apply_status'] = 'completed'
            except Exception as error:
                record['apply_status'] = 'error'
                record['apply_error'] = f'{type(error).__name__}: {error}'
            record['after'] = await check.edit(sid, 'note.list', track_index=0, part_index=0)
            record['status_after'] = await check.call('project_status', session_id=sid)
            record['history_after'] = await check.edit(sid, 'history.status')
            if label == 'eng_unknown':
                try:
                    await check.library('lyrics_apply', sid, **selected, lyrics='い', protect='invalid')
                    record['failure'] = 'unexpected success'
                except Exception as error:
                    record['failure'] = f'{type(error).__name__}: {error}'
                record['after_failure'] = await check.edit(sid, 'note.list', track_index=0, part_index=0)
                record['status_after_failure'] = await check.call('project_status', session_id=sid)
                record['history_after_failure'] = await check.edit(sid, 'history.status')
            saved, path = await check.save(sid, 'g2pa28-saved-'+label)
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
    v.require(all(report[label]['status'] == 'observed' for label, _, _ in cases), 'Observation incomplete', report)


if __name__ == '__main__':
    if not any(x in ('--case', '--category') for x in sys.argv[1:]):
        sys.argv.extend(['--case', 'g2pa_native28'])
    sys.exit(v.main())
