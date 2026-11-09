"""Bounded synthetic AI-note roundtrip probe using an isolated stdio server."""
from copy import deepcopy
from pathlib import Path
import sys
import verify_features as v
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vocaloid_bridge.projects import _EDITOR_AI_NOTE

@v.feature('ai_defaults26', 'ai_defaults26', 'score_compose', 'score_patch', 'project_open', 'project_save', 'project_render_part')
async def probe(check):
    report = {}
    check.evidence('cases', report)
    seed = await check.call('score_compose', output_name=check.output('ai-defaults-seed'), title='Synthetic AI defaults probe', bpm=120,
                            notes=[{'start': 0, 'duration': 1, 'pitch': 60, 'lyric': 'あ', 'phoneme': 'a', 'lang_id': 0}])
    seed_path = seed['path']
    seed_sid = seed['native_session']['session_id']
    report['lyrics'] = {}
    try:
        for operation, options in [
            ('lyrics_can_convert', {'language_id': 0, 'lyrics': 'あ', 'is_ai': True}),
            ('lyrics_candidates', {'track_index': 0, 'part_index': 0, 'note_index': 0, 'language_id': 0, 'lyrics': 'あ'})]:
            try:
                report['lyrics'][operation] = await check.call('project_library', session_id=seed_sid, operation=operation, options=options)
            except Exception as error:
                report['lyrics'][operation] = {'error': f'{type(error).__name__}: {error}'}
    finally:
        await check.close(seed_sid)
    seq, _ = v.read_vpr(seed_path)
    part = seq['tracks'][0]['parts'][0]
    v.require('aiVoice' in part and part['notes'], 'Seed must have a populated AI part')
    def has_pitch(x):
        return isinstance(x, dict) and ('directPitches' in x or any(has_pitch(y) for y in x.values())) or isinstance(x, list) and any(has_pitch(y) for y in x)
    v.require(not has_pitch(seq), 'Seed contains directPitches; probe stops')
    for label in ('explicit', 'empty_phoneme', 'missing_lang', 'missing_velocity'):
        record = report[label] = {}
        sid = None
        try:
            new = deepcopy(_EDITOR_AI_NOTE)
            new.update(pos=1920, duration=480, number=64, lyric='あ')
            if label == 'explicit':
                new.update(phoneme='a', langID=0, velocity=64)
            elif label == 'empty_phoneme':
                new['phoneme'] = ''
            elif label == 'missing_lang':
                new.pop('langID')
            elif label == 'missing_velocity':
                new.pop('velocity')
            record['input'] = {k: new.get(k, '<absent>') for k in ('lyric', 'phoneme', 'langID', 'velocity')}
            notes = deepcopy(part['notes']) + [new]
            patched = await check.call('score_patch', path=seed_path, output_name=check.output('ai-defaults-'+label), operations=[{'op':'replace','path':'/tracks/0/parts/0/notes','value':notes}])
            opened = await check.call('project_open', path=patched['path'])
            sid = opened['session_id']
            saved, saved_path = await check.save(sid, 'ai-defaults-saved-'+label)
            record['saved_note'] = saved['tracks'][0]['parts'][0]['notes'][1]
            await check.close(sid); sid = None
            reopened = await check.call('project_open', path=str(saved_path))
            sid = reopened['session_id']
            wav = await check.call('project_render_part', session_id=sid, track_index=0, part_index=0, output_name=check.output('ai-defaults-'+label, '.wav'))
            meta, samples = v.read_audio(wav['path'], nonzero=False)
            import numpy as np
            # The new note starts at beat 4; this render has an approximately 0.5 s lead-in.
            interval = samples[int(2.6 * meta['sample_rate']):int(2.9 * meta['sample_rate'])]
            record['wav'] = {'path': wav['path'], **meta,
                             'new_note_window_seconds': [2.6, 2.9],
                             'window_peak': float(np.max(np.abs(interval))),
                             'window_rms': float(np.sqrt(np.mean(interval * interval)))}
            record['status'] = 'roundtrip_and_render_completed'
        except Exception as error:
            record['status'] = 'failed'
            record['error'] = f'{type(error).__name__}: {error}'
        finally:
            if sid:
                await check.close(sid)
    v.require(all(report[x]['status'] == 'roundtrip_and_render_completed' for x in ('explicit', 'empty_phoneme', 'missing_lang', 'missing_velocity')), 'At least one case failed', report)

if __name__ == '__main__':
    if not any(x in ('--case', '--category') for x in sys.argv[1:]):
        sys.argv.extend(['--case', 'ai_defaults26'])
    sys.exit(v.main())
