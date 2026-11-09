"""Two necessary native contracts for timeline, media and nested-array completion."""
import copy
import json
from pathlib import Path
import sys
import wave
import zipfile
import verify_features as v

KEY = 'x_completion34'
SCOPE = {'track_index': 0, 'part_index': 0}


def write_fixture(check, data, members, label):
    path = v.ROOT / 'output' / check.output(label)
    with zipfile.ZipFile(path, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name, content in members.items():
            archive.writestr(name, json.dumps(data, ensure_ascii=False).encode() if name == 'Project/sequence.json' else content)
    return path


async def source_fixture(check):
    composed = await check.call('score_compose', output_name=check.output('source'), title='Completion 34', bpm=120,
        notes=[{'start': 0, 'duration': 2, 'pitch': 60, 'lyric': 'あ', 'phoneme': 'a', 'lang_id': 0},
               {'start': 2.5, 'duration': 1, 'pitch': 64, 'lyric': 'い', 'phoneme': 'i', 'lang_id': 0},
               {'start': 4, 'duration': 1, 'pitch': 67, 'lyric': 'う', 'phoneme': 'M', 'lang_id': 0}])
    sid = composed['native_session']['session_id']
    wav = check.directory / 'source.wav'
    with wave.open(str(wav), 'wb') as out:
        out.setparams((1, 2, 44100, 88200, 'NONE', 'not compressed'))
        out.writeframes(b'\0\0' * 88200)
    try:
        await check.edit(sid, 'pitch.set', **SCOPE, note_index=0, points=[{'tick': 100, 'value': 60}, {'tick': 600, 'value': 61}])
        await check.edit(sid, 'controller.set', **SCOPE, type='Dynamics', replace=True,
                         points=[{'tick': 100, 'value': 40}, {'tick': 800, 'value': 65}, {'tick': 1800, 'value': 50}])
        await check.edit(sid, 'vibrato.set', **SCOPE, note_index=1, type='Normal_1', duration_tick=240,
                         depth=[{'tick': 0, 'value': 50}, {'tick': 200, 'value': 60}])
        for lane in ('master_volume', 'track_volume', 'track_pan'):
            kwargs = {} if lane == 'master_volume' else {'track_index': 0}
            spec = await check.edit(sid, 'automation.list', scope=lane, **kwargs)
            await check.edit(sid, 'automation.set', scope=lane, **kwargs,
                             points=[{'tick': 200, 'value': spec['minimum']}, {'tick': 900, 'value': spec['maximum']}])
        await check.audio(sid, 'import_audio', path=str(wav), position_tick=0, name='Audio')
        effects = (await check.audio(sid, 'effects', scope='catalog'))['effects']
        gain = next(item for item in effects if item['name'].casefold() == 'gain')
        await check.audio(sid, 'set_effect', action='add', effect_id=gain['effect_id'])
        data, native = await check.save(sid, 'native')
    finally:
        await check.close(sid)
    _, members = v.read_vpr(native)
    for item in data['voices']:
        item[KEY] = {'voice': item['compID']}
    for lane in (data['masterTrack']['volume'], data['tracks'][0]['volume'], data['tracks'][0]['panpot']):
        for item in lane['events']:
            item[KEY] = {'origin': item['pos']}
    midi = data['tracks'][0]['parts'][0]
    midi[KEY] = 'midi-part'
    for lane in midi['controllers']:
        for item in lane['events']:
            item[KEY] = {'controller': item['pos']}
    for item in midi['notes'][0]['directPitches']:
        item[KEY] = {'pitch': item['pos']}
    for item in midi['notes'][1]['vibrato']['depths']:
        item[KEY] = {'vibrato': item['pos']}
    for item in midi.get('aiVoice', {}).get('langIDs', []):
        item[KEY] = {'language': item['langID']}
    audio = data['tracks'][1]['parts'][0]
    audio[KEY] = 'audio-part'; audio['region'][KEY] = 'audio-region'
    for effect in data['masterTrack']['audioEffects']:
        effect[KEY] = 'effect'
        for parameter in effect['parameters']:
            parameter[KEY] = {'parameter': parameter['name']}
    return data, members, write_fixture(check, data, members, 'extended')


@v.feature('completion.timeline_34', 'preservation', 'project_edit', 'project_open', 'project_save', 'score_compose', 'project_audio')
async def timeline(check):
    data, members, source = await source_fixture(check)
    sid = (await check.call('project_open', path=str(source)))['session_id']
    try:
        before, _ = await check.save(sid, 'before-time')
        await check.edit(sid, 'time.insert', start_tick=480, duration_tick=240, include_tempo=True)
        after, saved = await check.save(sid, 'inserted-time')
        v.require(len(after['tracks'][0]['parts']) >= 2 and len(after['tracks'][1]['parts']) == 2, 'Crossing parts were not divided')
        v.require(all(part.get(KEY) == 'midi-part' for part in after['tracks'][0]['parts']), 'MIDI split lost part metadata')
        v.require(all(part.get(KEY) == 'audio-part' and part['region'][KEY] == 'audio-region'
                      for part in after['tracks'][1]['parts']), 'Audio split lost metadata')
        v.require(any(item.get(KEY) == {'origin': 900} and item['pos'] == 1140
                      for item in after['masterTrack']['volume']['events']), 'Master curve identity was not shifted')
        await check.edit(sid, 'undo')
        actual, _ = await check.save(sid, 'undo-time')
        v.require(actual == before, 'Time insertion undo differs')
        await check.edit(sid, 'redo')
        await check.edit(sid, 'time.delete', start_tick=480, duration_tick=240, include_tempo=True)
        removed, _ = await check.save(sid, 'removed-time')
        v.require(any(item.get(KEY) == {'origin': 900} and item['pos'] == 900
                      for item in removed['masterTrack']['volume']['events']), 'Time deletion lost curve identity')
        await check.edit(sid, 'time.delete', start_tick=0, duration_tick=120, include_tempo=True)
        _, saved = await check.save(sid, 'delete-initial-tempo')
    finally:
        await check.close(sid)
    reopened = (await check.call('project_open', path=str(saved)))['session_id']
    await check.close(reopened)


@v.feature('completion.media_arrays_34', 'preservation', 'project_edit', 'project_open', 'project_save', 'project_library', 'project_audio', 'score_compose')
async def media_arrays(check):
    data, members, source = await source_fixture(check)
    sid = (await check.call('project_open', path=str(source)))['session_id']
    clips = []
    try:
        await check.edit(sid, 'vibrato.set', **SCOPE, note_index=1, depth=[{'tick': 0, 'value': 55}, {'tick': 200, 'value': 60}])
        changed, _ = await check.save(sid, 'array-edited')
        depths = changed['tracks'][0]['parts'][0]['notes'][1]['vibrato']['depths']
        v.require(depths[0][KEY] == {'vibrato': 0} and depths[0]['value'] == 55, 'Vibrato metadata did not follow its selected point')
        effect = (await check.audio(sid, 'effects', scope='master'))['effects'][0]
        meta = await check.audio(sid, 'effects', scope='catalog', effect_id=effect['effect_id'])
        name = meta['parameters'][0]['name']
        await check.audio(sid, 'set_effect', action='set', slot=0, parameters={name: .25})
        edited, _ = await check.save(sid, 'parameter-edited')
        v.require(all(KEY in item for item in edited['masterTrack']['audioEffects'][0]['parameters']), 'Effect parameter metadata lost')
        for index in (0, 1):
            clip = (await check.library('media_capture', sid, track_index=index, part_index=0, name='Complete34'))['clip']
            clips.append(clip['clip_id'])
        await check.edit(sid, 'track.create', type='MidiAi', name='MIDI target')
        await check.edit(sid, 'track.create', type='Audio', name='Audio target')
        await check.library('media_import', sid, clip_id=clips[0], track_index=2, position_tick=3840)
        await check.library('media_import', sid, clip_id=clips[1], track_index=3, position_tick=3840)
        after, saved = await check.save(sid, 'media-imported')
        original = edited['tracks'][0]['parts'][0]
        imported = after['tracks'][2]['parts'][0]
        v.require(imported[KEY] == original[KEY] and imported['controllers'] == original['controllers'] and
                  imported['notes'][0]['directPitches'] == original['notes'][0]['directPitches'] and
                  imported['notes'][1]['vibrato']['depths'] == original['notes'][1]['vibrato']['depths'], 'MIDI media metadata lost')
        v.require(after['tracks'][3]['parts'][0][KEY] == 'audio-part' and
                  after['tracks'][3]['parts'][0]['region'][KEY] == 'audio-region', 'Audio media metadata lost')
        await check.edit(sid, 'undo')
        await check.edit(sid, 'redo')
    finally:
        for clip in clips: await check.library('media_delete', sid, clip_id=clip)
        await check.close(sid)
    reopened = (await check.call('project_open', path=str(saved)))['session_id']
    try:
        final, _ = await check.save(reopened, 'roundtrip')
        v.require(final['tracks'] == after['tracks'], 'Media metadata changed after reopen')
    finally:
        await check.close(reopened)


@v.feature('completion.transactions_34', 'preservation', 'score_compose', 'project_open', 'project_save', 'project_merge', 'project_edit')
async def transactions(check):
    seed = await check.call('score_compose', output_name=check.output('transaction-seed'), title='Transactions', bpm=120,
                            notes=[{'start': 0, 'duration': 1, 'pitch': 60, 'lyric': 'あ', 'phoneme': 'a', 'lang_id': 0}])
    await check.close(seed['native_session']['session_id'])
    data, members = v.read_vpr(seed['path'])
    data['masterTrack']['tempo']['events'][0][KEY] = 'target'
    target_path = write_fixture(check, data, members, 'tempo-target')
    source = copy.deepcopy(data)
    source['masterTrack']['tempo']['events'][0][KEY] = 'source'
    source_path = write_fixture(check, source, members, 'tempo-source')
    sid = (await check.call('project_open', path=str(target_path)))['session_id']
    try:
        await check.call('project_merge', session_id=sid, path=str(source_path), include_tracks=False, include_tempo=True, replace_tempo=True)
        after, _ = await check.save(sid, 'metadata-only-merged')
        v.require(after['masterTrack']['tempo']['events'][0][KEY] == 'source', 'Metadata-only tempo merge failed')
        await check.edit(sid, 'undo')
        undone, _ = await check.save(sid, 'metadata-only-undo')
        v.require(undone['masterTrack']['tempo']['events'][0][KEY] == 'target', 'Metadata merge undo failed')
        await check.edit(sid, 'redo')
        history = await check.edit(sid, 'history.status')
        await check.call('project_merge', session_id=sid, path=str(source_path), include_tracks=False, include_tempo=True, replace_tempo=True)
        v.require(await check.edit(sid, 'history.status') == history, 'Equal map merge changed history')
    finally:
        await check.close(sid)
    from vocaloid_bridge.native_client import IsolatedProcess
    work = check.directory / 'readback'; work.mkdir()
    process = IsolatedProcess([r'C:\Program Files\PowerShell\7\pwsh.exe', '-NoProfile', '-File',
        str(v.ROOT / 'tools/check_transaction_readback_34.ps1'), '-Root', str(work), '-Source', seed['path']], v.ROOT)
    try:
        result = json.loads(process.read_line(60))
    finally:
        process.close()
    check.evidence('readback_failure', result)
    v.require(result['staged_change_observed'] and result['mutation_observed'] and result['restored'], 'Readback failure escaped rollback')


if __name__ == '__main__':
    if '--case' not in sys.argv:
        for name in ('completion.timeline_34', 'completion.media_arrays_34', 'completion.transactions_34'): sys.argv.extend(['--case', name])
    raise SystemExit(v.main())
