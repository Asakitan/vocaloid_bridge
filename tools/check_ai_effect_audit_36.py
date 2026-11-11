"""Measure which expressive controls change native VOCALOID:AI synthesis.

Each control is applied to a freshly reopened copy of one styled AI phrase and
the dry part render is compared sample by sample with a reference render.
This is an observation of audible effect, not a quality judgement.
"""
import sys
from pathlib import Path

import numpy as np
import verify_features as v


NOTES = ((0, 900, 60, 'ら'), (960, 900, 64, 'り'), (1920, 1800, 67, 'る'))
SCOPE = {'track_index': 0, 'part_index': 0}


def _target(minimum, maximum, default):
    for candidate in (maximum, minimum, (minimum + maximum) / 2):
        if candidate != default:
            return candidate
    return None


RATE = 44100


def _difference(reference, samples):
    if reference.shape != samples.shape:
        return {'changed': True, 'frames': [int(reference.shape[0]), int(samples.shape[0])]}
    delta = samples - reference
    peak = float(np.max(np.abs(delta)))
    result = {'changed': peak > 0, 'max_abs_diff': peak, 'rms_diff': float(np.sqrt(np.mean(delta * delta)))}
    differing = np.flatnonzero(np.max(np.abs(delta), axis=1) > 0)
    if differing.size:
        result.update(first_diff_seconds=round(float(differing[0]) / RATE, 3),
                      last_diff_seconds=round(float(differing[-1]) / RATE, 3))
    return result


@v.feature('agent.ai_effect_audit_36', 'agent', 'project_create', 'project_edit', 'project_library',
           'project_render_part', 'project_save', 'project_open', 'project_close', 'voicebanks')
async def ai_effect_audit(check):
    banks = [item for item in (await check.call('voicebanks'))['voices']
             if item['kind'] == 'Dnn' and item['available_in_sequence'] and item['synthesizable_version']]
    v.require(banks, 'No installed AI voice is available')
    voice = next((item for item in banks if item['name'] == 'asa'), banks[0])
    styles = (await check.library('style_list', query=voice['name']))['styles']
    default_style = next((item for item in styles if 'default' in item['name'].lower()), None)
    v.require(default_style is not None, 'The voice has no default style in the native catalog', [s['name'] for s in styles])
    created: list[Path] = []

    async def author(label, duration, notes, styled):
        session = (await check.call('project_create', title='AI effect audit', bpm=120))['session_id']
        await check.edit(session, 'track.create', type='MidiAi', name='Audit')
        await check.edit(session, 'part.create', track_index=0, start_tick=0, duration_tick=duration)
        await check.edit(session, 'voice.set', **SCOPE, ai_voice_bank_id=voice['comp_id'])
        for start, length, number, lyric in notes:
            await check.edit(session, 'note.add', **SCOPE, start_tick=start, duration_tick=length,
                             number=number, lyric=lyric, lang_id=0)
        state = {'performance_before_style': await check.edit(session, 'performance.get', **SCOPE)}
        if styled:
            state['applied'] = await check.library('style_apply', session, **SCOPE,
                                                   style_id=default_style['style_id'], include_audio=True)
            state['performance'] = await check.edit(session, 'performance.get', **SCOPE)
            state['bounds'] = await check.edit(session, 'note.expression_bounds', **SCOPE)
            state['controller_types'] = (await check.edit(session, 'controller.types', **SCOPE))['types']
        _, path = await check.save(session, label)
        created.append(path)
        await check.close(session)
        return path, state

    bare_path, _ = await author('audit-bare', 3840, NOTES, False)
    base_path, base = await author('audit-base', 3840, NOTES, True)
    long_path, _ = await author('audit-long', 7680, ((0, 7200, 64, 'あ'),), True)
    bounds, controller_types = base['bounds'], base['controller_types']

    async def render(source, mutate=None):
        session = (await check.call('project_open', path=str(source)))['session_id']
        try:
            if mutate is not None:
                try:
                    await mutate(session)
                except v.ToolFailure as error:
                    return {'status': 'rejected', 'error': str(error)[:400]}
            result = await check.call('project_render_part', session_id=session,
                                      output_name=check.output('audit', '.wav'), track_index=0, part_index=0)
            path = Path(result['path'])
            metadata, samples = v.read_audio(path)
            path.unlink()
            v.require(metadata['sample_rate'] == RATE, 'Unexpected dry render rate', metadata)
            return samples
        finally:
            await check.close(session)

    reference = await render(base_path)
    noise = _difference(reference, await render(base_path))
    v.require(not noise['changed'], 'Native synthesis of the unchanged phrase is not repeatable', noise)
    long_reference = await render(long_path)
    long_noise = _difference(long_reference, await render(long_path))
    v.require(not long_noise['changed'], 'Native synthesis of the unchanged long note is not repeatable', long_noise)

    results: dict[str, dict] = {}

    async def measure(name, mutate, source=base_path, against=None):
        outcome = await render(source, mutate)
        if isinstance(outcome, dict):
            results[name] = outcome
        else:
            results[name] = {'status': 'rendered', **_difference(reference if against is None else against, outcome)}

    def note(index=2, **fields):
        return lambda session: check.edit(session, 'note.update', **SCOPE, note_index=index, **fields)

    def all_notes(**fields):
        async def mutate(session):
            for index in range(len(NOTES)):
                await check.edit(session, 'note.update', **SCOPE, note_index=index, **fields)
        return mutate

    def sequence(*steps):
        async def mutate(session):
            for step in steps:
                await step(session)
        return mutate

    def controller(kind, value):
        return lambda session: check.edit(session, 'controller.set', **SCOPE, type=kind,
                                          points=[{'tick': 0, 'value': value}])

    def vibrato(**fields):
        return lambda session: check.edit(session, 'vibrato.set', **SCOPE, note_index=2, **fields)

    await measure('bare_part_without_style', None, bare_path)
    await measure('note_number_control', note(number=69))
    await measure('note.update_lyric_only', note(lyric='ら'))
    await measure('lyrics_apply', lambda s: check.library('lyrics_apply', s, **SCOPE, note_index=2, lyrics='ら', language_id=0))

    maximum_ai = bounds['ai_expression']['maximum']
    for group in ('ai_expression', 'expression'):
        low, high, default = (bounds[group][key] for key in ('minimum', 'maximum', 'defaults'))
        for field, value in default.items():
            target = (not value) if isinstance(value, bool) else _target(low[field], high[field], value)
            if target is None:
                results[f'note.{group}.{field}'] = {'status': 'skipped', 'reason': 'no alternative native value'}
                continue
            if isinstance(value, int) and not isinstance(value, bool):
                target = int(target)
            await measure(f'note.{group}.{field}', all_notes(**{group: {field: target}}))

    await measure('note.velocity', all_notes(velocity=127))
    await measure('note.ai_vibrato_enabled_false', all_notes(ai_vibrato_enabled=False))

    events = {'depth': [{'tick': 0, 'value': 127}], 'rate': [{'tick': 0, 'value': 127}]}
    shaped = {'type': 'Normal_1', 'duration_tick': 1800}
    await measure('vibrato.type_duration_only', vibrato(type='Extreme_1', duration_tick=1800))
    await measure('vibrato.depth_rate_events', vibrato(**shaped, **events))
    await measure('vibrato.events_without_type', vibrato(**events))
    await measure('vibrato.depth_events_only', vibrato(**shaped, depth=events['depth']))
    await measure('vibrato.rate_events_only', vibrato(**shaped, rate=events['rate']))
    with_vibrato = await render(base_path, vibrato(**shaped, **events))
    v.require(not isinstance(with_vibrato, dict), 'The vibrato reference was rejected', with_vibrato)
    await measure('vibrato_events+ai_vibrato_enabled_false',
                  sequence(vibrato(**shaped, **events), note(ai_vibrato_enabled=False)), against=with_vibrato)
    for field in ('VibratoLeadingDepth', 'VibratoFollowingDepth'):
        await measure('vibrato_events+ai_expression.' + field,
                      sequence(vibrato(**shaped, **events), note(ai_expression={field: maximum_ai[field]})),
                      against=with_vibrato)

    depth_only = await render(base_path, vibrato(**shaped, depth=events['depth']))
    v.require(not isinstance(depth_only, dict), 'The depth-only vibrato reference was rejected', depth_only)
    await measure('vibrato.rate_events_added_to_depth', vibrato(**shaped, **events), against=depth_only)

    await measure('long_note.ai_vibrato_enabled_false', note(0, ai_vibrato_enabled=False), long_path, long_reference)
    for field in ('VibratoLeadingDepth', 'VibratoFollowingDepth'):
        await measure('long_note.ai_expression.' + field, note(0, ai_expression={field: maximum_ai[field]}),
                      long_path, long_reference)

    # Where a vibrato sits in a 7200-tick note that lasts 7.5 seconds at 120 BPM.
    def long_vibrato(duration, tick):
        return lambda session: check.edit(session, 'vibrato.set', **SCOPE, note_index=0, type='Normal_1',
                                          duration_tick=duration, depth=[{'tick': tick, 'value': 127}])

    await measure('long_note.vibrato_3600_event_0', long_vibrato(3600, 0), long_path, long_reference)
    await measure('long_note.vibrato_3600_event_1800', long_vibrato(3600, 1800), long_path, long_reference)
    await measure('long_note.vibrato_7200_event_3600', long_vibrato(7200, 3600), long_path, long_reference)
    # A depth step from 0 to 127 at event tick 1800 shows what the event ticks count from.
    await measure('long_note.vibrato_3600_depth_step_at_1800', lambda session: check.edit(
        session, 'vibrato.set', **SCOPE, note_index=0, type='Normal_1', duration_tick=3600,
        depth=[{'tick': 0, 'value': 0}, {'tick': 1799, 'value': 0}, {'tick': 1800, 'value': 127}]),
        long_path, long_reference)
    await measure('long_note.vibrato_3600_depth_zero', lambda session: check.edit(
        session, 'vibrato.set', **SCOPE, note_index=0, type='Normal_1', duration_tick=3600,
        depth=[{'tick': 0, 'value': 0}]), long_path, long_reference)
    constant = await render(long_path, long_vibrato(3600, 0))
    v.require(not isinstance(constant, dict), 'The constant vibrato reference was rejected', constant)
    await measure('long_note.vibrato_3600_other_type_name', lambda session: check.edit(
        session, 'vibrato.set', **SCOPE, note_index=0, type='Extreme_1', duration_tick=3600,
        depth=[{'tick': 0, 'value': 127}]), long_path, constant)
    await measure('long_note.vibrato_3600_later_depth_event_added', lambda session: check.edit(
        session, 'vibrato.set', **SCOPE, note_index=0, type='Normal_1', duration_tick=3600,
        depth=[{'tick': 0, 'value': 127}, {'tick': 1800, 'value': 0}]), long_path, constant)
    await measure('long_note.vibrato_3600_later_rate_event_added', lambda session: check.edit(
        session, 'vibrato.set', **SCOPE, note_index=0, type='Normal_1', duration_tick=3600,
        depth=[{'tick': 0, 'value': 127}], rate=[{'tick': 0, 'value': 64}, {'tick': 1800, 'value': 127}]),
        long_path, await render(long_path, lambda session: check.edit(
            session, 'vibrato.set', **SCOPE, note_index=0, type='Normal_1', duration_tick=3600,
            depth=[{'tick': 0, 'value': 127}], rate=[{'tick': 0, 'value': 64}])))

    await measure('pitch.set', lambda s: check.edit(
        s, 'pitch.set', **SCOPE, note_index=2,
        points=[{'tick': 0, 'value': 67}, {'tick': 600, 'value': 69}, {'tick': 1200, 'value': 67}]))
    await measure('dvqm.attack', lambda s: check.library(
        'dvqm_set', s, **SCOPE, note_index=1, is_attack=True, db_id=0, name_id=0))
    await measure('dvqm.release', lambda s: check.library(
        'dvqm_set', s, **SCOPE, note_index=2, is_attack=False, db_id=0, name_id=4))
    await measure('note_skill.weights', lambda s: check.library(
        'note_skill_set', s, **SCOPE, note_index=2, pre_weight=127, post_weight=127))
    await measure('singing_skill.set', lambda s: check.library('singing_skill_set', s, **SCOPE, skill=100, amount=100))

    targets = {}
    for item in controller_types:
        target = _target(item['minimum'], item['maximum'], item['default_value'])
        if target is None:
            results['controller.' + item['type']] = {'status': 'skipped', 'reason': 'no alternative native value'}
            continue
        targets[item['type']] = int(target)
        await measure('controller.' + item['type'], controller(item['type'], int(target)))
    if {'PitchBend', 'PitchBendSens'} <= targets.keys():
        bent = await render(base_path, controller('PitchBend', targets['PitchBend']))
        v.require(not isinstance(bent, dict), 'The pitch-bend reference was rejected', bent)
        await measure('controller.PitchBend+PitchBendSens',
                      sequence(controller('PitchBend', targets['PitchBend']),
                               controller('PitchBendSens', targets['PitchBendSens'])), against=bent)

    colors = base['performance']['voice_colors'] or []
    unbypassed = await render(base_path, lambda s: check.edit(s, 'performance.set', **SCOPE, bypass={'VoiceColor': False}))
    v.require(not isinstance(unbypassed, dict), 'VoiceColor could not be enabled', unbypassed)
    results['voice_color.enable_effect_only'] = {'status': 'rendered', **_difference(reference, unbypassed)}
    for color in colors:
        setting = color['setting']
        target = int(_target(setting['LowerBoundValue'], setting['UpperBoundValue'], color['value']))
        await measure('voice_color.' + color['name'] + '_while_bypassed', lambda s, name=color['name'], value=target: check.edit(
            s, 'performance.set', **SCOPE, voice_colors={name: value}))
        await measure('voice_color.' + color['name'] + '_enabled', lambda s, name=color['name'], value=target: check.edit(
            s, 'performance.set', **SCOPE, voice_colors={name: value}, bypass={'VoiceColor': False}), against=unbypassed)

    for path in created:
        path.unlink()

    def names(predicate):
        return sorted(name for name, item in results.items() if predicate(item))

    check.evidence('voice', {key: voice[key] for key in ('name', 'comp_id', 'native_lang_id', 'lang_ids')})
    check.evidence('default_style', {'name': default_style['name'], 'applied': base['applied']})
    check.evidence('bypass_before_style', base['performance_before_style']['bypass'])
    check.evidence('bypass_after_style', base['performance']['bypass'])
    check.evidence('voice_colors_after_style', colors)
    check.evidence('controller_types', controller_types)
    check.evidence('expression_bounds', bounds)
    check.evidence('baseline_repeat', {'phrase': noise, 'long_note': long_noise})
    check.evidence('results', results)
    check.evidence('changed', names(lambda item: item.get('changed') is True))
    check.evidence('unchanged', names(lambda item: item.get('status') == 'rendered' and item.get('changed') is False))
    check.evidence('rejected', {name: item['error'] for name, item in results.items() if item.get('status') == 'rejected'})
    check.evidence('skipped', names(lambda item: item.get('status') == 'skipped'))
    check.evidence('removed_files', 'rendered WAVs and the three base VPRs created by this case')
    control = results['note_number_control']
    v.require(control.get('changed') is True, 'The note-number control did not change synthesis', control)


if __name__ == '__main__':
    if '--case' not in sys.argv:
        sys.argv.extend(['--case', 'agent.ai_effect_audit_36'])
    raise SystemExit(v.main())
