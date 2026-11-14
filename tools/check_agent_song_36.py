"""Agent-facing song workflow: guidance, lyric conversion, applicability and a full song pass."""
import json
import re
import sys
from pathlib import Path

import verify_features as v

sys.path.insert(0, str(v.ROOT))
from vocaloid_bridge import __version__


SCOPE = {'track_index': 0, 'part_index': 0}
SUNG_BY_AI = {'Dynamics', 'PitchBend', 'PitchBendSens', 'Expression', 'S5Air', 'S5Character'}
LINE = (('yue', 60), ('liang', 62), ('sheng', 64), ('qi', 67), ('lai', 64), ('zhao', 62), ('zhe', 60), ('wo', 60))


def _ai_voices(voices):
    return [item for item in voices if item['kind'] == 'Dnn' and item['available_in_sequence']
            and item['synthesizable_version']]


async def _ai_part(check, voice, duration=3840, bpm=120):
    session = (await check.call('project_create', title='Agent song 36', bpm=bpm))['session_id']
    await check.edit(session, 'track.create', name='Lead')
    await check.edit(session, 'part.create', track_index=0, start_tick=0, duration_tick=duration)
    assigned = await check.edit(session, 'voice.set', **SCOPE, ai_voice_bank_id=voice['comp_id'])
    return session, assigned


def _sung(note):
    return note['lyric'], note['phonemes'], note['is_valid_phonemes']


@v.feature('agent.guidance_36', 'agent', 'vocaloid_workflow', 'vocaloid_operations', 'vocaloid_status')
async def guidance(check):
    required = {'vocaloid_workflow', 'vocaloid_operations', 'vocaloid_status', 'project_create',
                'project_edit', 'project_library', 'project_render_part', 'project_audio', 'score_compose'}
    v.require(required <= check.tools.keys(), 'Agent guidance tools are missing', sorted(required - check.tools.keys()))
    described = {name: tool.description or '' for name, tool in check.tools.items()}
    for name, phrase in (('vocaloid_workflow', 'Read this first'), ('project_create', '44100'),
                         ('project_edit', 'pinyin'), ('project_edit', '480'), ('project_library', 'Default'),
                         ('project_library', 'standard VOCALOID parts'), ('project_render_part', 'mixdown'),
                         ('project_audio', '192000'), ('score_compose', 'pinyin')):
        v.require(phrase in described[name], 'Tool description lacks agent guidance', (name, phrase))
    guide = await check.call('vocaloid_workflow')
    text = (v.ROOT / 'docs' / 'song-workflow.md').read_text(encoding='utf-8')
    v.require(guide['guide'] == text and guide['ticks_per_quarter'] == 480 and guide['mcp_version'] == __version__,
              'Workflow tool does not return the current guide', {key: guide[key] for key in guide if key != 'guide'})
    status = await check.call('vocaloid_status')
    v.require(status['mcp_version'] == __version__, 'Unexpected server version', status)
    resource = json.loads((await check.client.read_resource('vocaloid://workflow')).contents[0].text)
    v.require(resource['guide'] == text and resource['ticks_per_quarter'] == 480, 'Workflow resource is stale')
    prompt = await check.client.get_prompt('write_song', arguments={'brief': 'marker'})
    v.require(any('vocaloid_workflow' in getattr(message.content, 'text', '') for message in prompt.messages),
              'Song prompt does not point at the workflow')

    index = await check.call('vocaloid_operations')
    known = {entry['operation'] for domain in index['domains'].values() for entry in domain['operations']}
    quoted = set(re.findall(r'`([a-z_]+(?:\.[a-z_]+)?)`', text))
    dotted = {name for name in quoted if '.' in name}
    v.require(dotted <= known, 'The guide names an unknown score operation', sorted(dotted - known))
    for name in ('style_list', 'style_apply', 'lyrics_apply', 'dvqm_set', 'dvqm_clear', 'note_skill_set',
                 'singing_skill_set', 'mixdown', 'mixdown_stems', 'effects', 'set_effect', 'import_audio'):
        v.require(name in quoted and name in known, 'The guide and the catalog disagree on an operation', name)
    await check.rejected('vocaloid_operations', 'include_documentation needs a domain', include_documentation=True)
    detail = await check.call('vocaloid_operations', domain='score', operation='note.update', include_documentation=True)
    v.require('regenerates' in detail['domains']['score']['documentation_text'], 'Score contract lacks the lyric rule')
    check.evidence('tool_count', len(check.tools))
    check.evidence('guide_characters', len(text))


@v.feature('agent.lyrics_36', 'agent', 'project_create', 'project_edit', 'project_library', 'score_compose',
           'project_save', 'project_open', 'voicebanks')
async def lyrics(check):
    voices = _ai_voices((await check.call('voicebanks'))['voices'])
    voice = next((item for item in voices if item['name'] == 'asa'), voices[0])
    session, assigned = await _ai_part(check, voice)
    created = []
    try:
        installed = assigned['installed_voice']
        v.require(installed['name'] == voice['name'] and installed['lang_ids'] == voice['lang_ids']
                  and installed['native_lang_id'] == voice['native_lang_id'],
                  'voice.set does not name the installed singer', assigned)
        base = {**SCOPE, 'duration_tick': 400, 'number': 60}
        await check.rejected('project_edit', 'unmarked pinyin', session_id=session, operation='note.add',
                             options={**base, 'start_tick': 0, 'lyric': '我', 'lang_id': 4})
        await check.rejected('project_edit', 'kana', session_id=session, operation='note.add',
                             options={**base, 'start_tick': 0, 'lyric': '😀', 'lang_id': 0})
        await check.rejected('project_edit', 'lyrics_apply spreads', session_id=session, operation='note.add',
                             options={**base, 'start_tick': 0, 'lyric': 'こんにちは', 'lang_id': 0})
        v.require((await check.edit(session, 'note.list', **SCOPE))['notes'] == [], 'A rejected note.add left a note')
        added = await check.edit(session, 'note.add', **base, start_tick=0, lyric='wo', lang_id=4)
        v.require(_sung(added) == ('wo', 'uo', True), 'Pinyin did not convert', added)

        # A lyric edit without phonemes now changes what is sung, in one undoable step.
        relyric = await check.edit(session, 'note.update', **SCOPE, note_index=0, lyric='ai')
        v.require(_sung(relyric) == ('ai', 'aI', True), 'note.update kept stale phonemes', relyric)
        await check.edit(session, 'undo')
        v.require(_sung((await check.edit(session, 'note.list', **SCOPE))['notes'][0]) == ('wo', 'uo', True),
                  'Lyric conversion was not one undo step')
        await check.edit(session, 'redo')
        before = await check.edit(session, 'note.list', **SCOPE)
        v.require(_sung(before['notes'][0]) == ('ai', 'aI', True), 'Redo lost the converted lyric', before)
        history = await check.edit(session, 'history.status')
        for lyric, pattern in (('我', 'unmarked pinyin'), ('ni hao', 'single-syllable'), ('wo3', 'unmarked pinyin')):
            await check.rejected('project_edit', pattern, session_id=session, operation='note.update',
                                 options={**SCOPE, 'note_index': 0, 'lyric': lyric})
            v.require(await check.edit(session, 'note.list', **SCOPE) == before
                      and await check.edit(session, 'history.status') == history,
                      'A rejected lyric edit changed the note or history', lyric)
        shown = await check.edit(session, 'note.update', **SCOPE, note_index=0, lyric='爱', phonemes='aI')
        v.require(_sung(shown) == ('爱', 'aI', True), 'Explicit phonemes did not keep the displayed lyric', shown)
        same = await check.edit(session, 'note.update', **SCOPE, note_index=0, lyric='爱', velocity=70)
        v.require(_sung(same) == ('爱', 'aI', True) and same['velocity'] == 70, 'An unchanged lyric was reconverted', same)
        await check.edit(session, 'note.update', **SCOPE, note_index=0, is_protected=True)
        guarded = await check.edit(session, 'note.update', **SCOPE, note_index=0, lyric='ge')
        v.require(_sung(guarded) == ('ge', 'aI', True) and guarded['is_protected'],
                  'A protected note lost its phonemes', guarded)
        released = await check.edit(session, 'note.update', **SCOPE, note_index=0, lyric='wo', is_protected=False)
        v.require(_sung(released) == ('wo', 'uo', True) and not released['is_protected'],
                  'Removing protection with a new lyric did not convert', released)
        moved = await check.edit(session, 'note.update', **SCOPE, note_index=0, lyric='ら', lang_id=0, number=62)
        v.require(_sung(moved) == ('ら', '4 a', True) and moved['lang_id'] == 0 and moved['number'] == 62,
                  'A lyric and language edit did not convert together', moved)
        second = await check.edit(session, 'note.add', **base, start_tick=480, lyric='cat', lang_id=1)
        english = await check.edit(session, 'note.update', **SCOPE, note_index=1, lyric='dog')
        v.require(english['lyric'] == 'dog' and english['phonemes'] not in ('', second['phonemes'])
                  and english['is_valid_phonemes'], 'English lyric edit did not convert', english)
        first = (await check.edit(session, 'note.list', **SCOPE))['notes'][0]
        v.require(_sung(first) == ('ら', '4 a', True), 'Editing one note changed another', first)

        await check.rejected('project_library', 'unmarked pinyin', session_id=session, operation='lyrics_apply',
                             options={**SCOPE, 'note_index': 0, 'language_id': 4, 'lyrics': '你好'})
        phrase = await check.library('lyrics_apply', session, **SCOPE, note_index=0, language_id=4, lyrics='ni hao')
        v.require([(item['lyric'], item['phonemes']) for item in phrase['notes']] == [('ni', 'n i'), ('hao', 'x AU')],
                  'A pinyin phrase was not spread over the notes', phrase)
        notes = await check.edit(session, 'note.list', **SCOPE)
        _, path = await check.save(session, 'agent-lyrics')
        created.append(path)
        await check.close(session, discard=False)
        session = (await check.call('project_open', path=str(path)))['session_id']
        v.require(await check.edit(session, 'note.list', **SCOPE) == notes, 'Converted lyrics did not survive save and reopen')
        voice_after = await check.edit(session, 'voice.get', **SCOPE)
        v.require(voice_after['installed_voice']['name'] == voice['name'], 'Reopened part lost its singer', voice_after)
    finally:
        await check.close(session)
    rejected = check.output('agent-compose-rejected')
    await check.rejected('score_compose', 'unmarked pinyin', output_name=rejected, title='Rejected', bpm=120,
                         notes=[{'start': 0, 'duration': 1, 'pitch': 60, 'lyric': '我', 'lang_id': 4}])
    v.require(not (v.ROOT / 'output' / rejected).exists(), 'A rejected composition left an output file')
    for path in created:
        path.unlink()


@v.feature('agent.applicability_36', 'agent', 'project_create', 'project_edit', 'project_library', 'voicebanks')
async def applicability(check):
    voices = _ai_voices((await check.call('voicebanks'))['voices'])
    voice = next((item for item in voices if item['name'] == 'asa'), voices[0])
    session, _ = await _ai_part(check, voice)
    try:
        await check.edit(session, 'note.add', **SCOPE, start_tick=0, duration_tick=960, number=60, lyric='ら', lang_id=0)
        types = (await check.edit(session, 'controller.types', **SCOPE))['types']
        v.require({item['type'] for item in types if item['applicable_to_current_part']} == SUNG_BY_AI,
                  'AI controller applicability differs from the measured set', types)
        v.require({item['type']: item['applies_to'] for item in types if item['type'] in SUNG_BY_AI} == {
            'Dynamics': 'Midi+MidiAi', 'PitchBend': 'Midi+MidiAi', 'PitchBendSens': 'Midi+MidiAi',
            'Expression': 'MidiAi', 'S5Air': 'MidiAi', 'S5Character': 'MidiAi'}, 'Unexpected controller mapping', types)
        vibrato = await check.edit(session, 'vibrato.get', **SCOPE, note_index=0)
        v.require('Normal_1' in vibrato['types'] and 'None' in vibrato['types']
                  and all(vibrato[key]['minimum'] < vibrato[key]['maximum'] for key in ('depth_range', 'rate_range')),
                  'vibrato.get does not expose its types and ranges', vibrato)
        low, high = vibrato['depth_range']['minimum'], vibrato['depth_range']['maximum']
        await check.rejected('project_edit', 'value', session_id=session, operation='vibrato.set',
                             options={**SCOPE, 'note_index': 0, 'depth': [{'tick': 0, 'value': high + 1}]})
        shaped = await check.edit(session, 'vibrato.set', **SCOPE, note_index=0, type='Normal_1', duration_tick=480,
                                  depth=[{'tick': 0, 'value': low}, {'tick': 240, 'value': high}])
        v.require(shaped['type'] == 'Normal_1' and len(shaped['depth']) == 2, 'Vibrato bounds were not accepted', shaped)
        attack = await check.library('dvqm_get', session, **SCOPE, note_index=0, is_attack=True)
        v.require(attack['applies_to'] == 'Midi' and attack['applicable_to_current_part'] is False,
                  'Attack/Release is not marked as a standard-part function on an AI note', attack)
        colors = (await check.edit(session, 'performance.get', **SCOPE))['voice_colors']
        v.require({item['name'] for item in colors if item['applicable_to_current_part']}
                  == {'S5Expression', 'S5Air', 'S5Character'}, 'Unexpected AI voice colours', colors)
        await check.edit(session, 'track.create', type='Midi', name='Standard')
        await check.edit(session, 'part.create', track_index=1, start_tick=0, duration_tick=1920)
        standard = (await check.edit(session, 'controller.types', track_index=1, part_index=0))['types']
        v.require({item['type'] for item in standard if not item['applicable_to_current_part']}
                  == {'Expression', 'S5Air', 'S5Character'}, 'Standard-part controller mapping is wrong', standard)
        check.evidence('vibrato_ranges', {key: vibrato[key] for key in ('types', 'depth_range', 'rate_range')})
    finally:
        await check.close(session)


@v.feature('agent.song_flow_36', 'agent', 'project_create', 'project_edit', 'project_library', 'project_audio',
           'project_render_part', 'audio_inspect', 'project_save', 'project_open', 'voicebanks')
async def song_flow(check):
    voices = _ai_voices((await check.call('voicebanks'))['voices'])
    defaults = {}
    for item in voices:
        styles = (await check.library('style_list', query=item['name']))['styles']
        match = next((style for style in styles if style['name'] == item['name'] + ' Default'), None)
        v.require(match is not None, 'A singer has no "<name> Default" style', (item['name'], [s['name'] for s in styles]))
        defaults[item['name']] = match['style_id']
    voice = next((item for item in voices if item['name'] != 'asa'), voices[0])
    last = len(LINE) - 1
    duration = (len(LINE) + 2) * 480
    session, _ = await _ai_part(check, voice, duration, bpm=100)
    created = []
    try:
        bare = await check.edit(session, 'performance.get', **SCOPE)
        applied = await check.library('style_apply', session, **SCOPE, style_id=defaults[voice['name']])
        styled = await check.edit(session, 'performance.get', **SCOPE)
        v.require(applied['audio_effect_count'] > 0 and bare['bypass'] != styled['bypass'],
                  'The default style did not change the part effects', applied)
        for index, (lyric, number) in enumerate(LINE):
            note = await check.edit(session, 'note.add', **SCOPE, start_tick=index * 480, duration_tick=480,
                                    number=number, lyric=lyric, lang_id=4)
            v.require(note['lyric'] == lyric and note['phonemes'] and note['is_valid_phonemes'], 'Pinyin note failed', note)
        await check.edit(session, 'note.update', **SCOPE, note_index=last, duration_tick=960)
        vibrato = await check.edit(session, 'vibrato.set', **SCOPE, note_index=last, type='Normal_1', duration_tick=600,
                                   depth=[{'tick': 0, 'value': 70}], rate=[{'tick': 0, 'value': 60}])
        await check.edit(session, 'note.update', **SCOPE, note_index=3, ai_expression={'AmplitudeWhole': 0.7})
        await check.edit(session, 'controller.set', **SCOPE, type='Dynamics',
                         points=[{'tick': 0, 'value': 70}, {'tick': 1920, 'value': 96}, {'tick': 3840, 'value': 64}])
        await check.edit(session, 'performance.set', **SCOPE, voice_colors={'S5Air': 20}, bypass={'VoiceColor': False})
        dry = await check.call('project_render_part', session_id=session, output_name=check.output('agent-dry', '.wav'))
        created.append(Path(dry['path']))
        v.require(dry['audio']['sample_rate'] == 44100 and dry['audio']['channels'] == 1 and dry['audio']['peak'] > 0,
                  'Unexpected dry part render', dry['audio'])
        mixed = await check.audio(session, 'mixdown', output_name=check.output('agent-mix', '.wav'),
                                  sample_rate=48000, bits_per_sample=24, channels=2)
        created.append(Path(mixed['path']))
        report = await check.call('audio_inspect', path=mixed['path'])
        seconds = duration / 480 * 60 / 100
        v.require(report['sample_rate'] == 48000 and report['channels'] == 2 and report['subtype'] == 'PCM_24'
                  and report['peak'] > 0 and abs(report['duration_seconds'] - seconds) < 0.05,
                  'The mixdown is not the requested deliverable', report)
        notes = await check.edit(session, 'note.list', **SCOPE)
        _, path = await check.save(session, 'agent-song')
        created.append(path)
        await check.close(session, discard=False)
        session = (await check.call('project_open', path=str(path)))['session_id']
        v.require(await check.edit(session, 'note.list', **SCOPE) == notes
                  and await check.edit(session, 'vibrato.get', **SCOPE, note_index=last) == vibrato,
                  'The song did not survive save and reopen')
        check.evidence('voice', voice['name'])
        check.evidence('default_styles', sorted(defaults))
        check.evidence('phonemes', [(item['lyric'], item['phonemes']) for item in notes['notes']])
        check.evidence('mixdown', report)
    finally:
        await check.close(session)

    for rate in (48000, 96000):
        wrong_rate = (await check.call('project_create', title='Other project rate', bpm=120, sample_rate=rate))['session_id']
        try:
            await check.edit(wrong_rate, 'track.create', name='Lead')
            await check.edit(wrong_rate, 'part.create', track_index=0, start_tick=0, duration_tick=1920)
            await check.edit(wrong_rate, 'voice.set', **SCOPE, ai_voice_bank_id=voice['comp_id'])
            await check.edit(wrong_rate, 'note.add', **SCOPE, start_tick=0, duration_tick=480, number=60, lyric='wo', lang_id=4)
            sequence = await check.edit(wrong_rate, 'sequence.get')
            v.require(sequence['sample_rate'] == rate, 'The project rate was not stored', sequence)
            name = check.output('agent-rate', '.wav')
            await check.rejected('project_render_part', 'requires a 44100 Hz project', session_id=wrong_rate, output_name=name)
            await check.rejected('project_audio', 'requires a 44100 Hz project', session_id=wrong_rate, operation='mixdown',
                                 options={'output_name': check.output('agent-rate-mix', '.wav')})
            await check.edit(wrong_rate, 'sequence.update', sample_rate=44100)
            recovered = await check.call('project_render_part', session_id=wrong_rate, output_name=name)
            created.append(Path(recovered['path']))
            v.require(recovered['audio']['peak'] > 0, 'Rendering did not recover at 44100 Hz', recovered['audio'])
        finally:
            await check.close(wrong_rate)
    for path in created:
        path.unlink()


if __name__ == '__main__':
    if '--case' not in sys.argv:
        for name in ('agent.guidance_36', 'agent.lyrics_36', 'agent.applicability_36', 'agent.song_flow_36'):
            sys.argv.extend(['--case', name])
    raise SystemExit(v.main())
