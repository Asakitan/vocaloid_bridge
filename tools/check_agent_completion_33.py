"""Focused contracts for Agent-facing recovery, voices and archive mutations."""
import copy
import json
from pathlib import Path
import shutil
import sys
import wave
import zipfile

import win32con
import win32event
import win32process
import verify_features as v

sys.path.insert(0, str(v.ROOT))
from vocaloid_bridge.native_client import IsolatedProcess

KEY = 'x_agent33'
SCOPE = {'track_index': 0, 'part_index': 0}
PWSH = r'C:\Program Files\PowerShell\7\pwsh.exe'


def fixture(check, sequence, members, label):
    path = v.ROOT / 'output' / check.output(label)
    with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, json.dumps(sequence, ensure_ascii=False).encode('utf-8')
                             if name == 'Project/sequence.json' else data)
    return path


@v.feature('library.recovery_resolution_33', 'library', 'score_compose', 'project_library')
async def recovery_resolution(check):
    async with check.project(score=True) as sid:
        clip = (await check.library('media_capture', sid, **SCOPE, name='Recovery32-' + check.run_id))['clip']
        clip_id = clip['clip_id']
        path = Path(clip['path']).resolve()
        prop = path.with_name('property.json')
        clip_bytes = path.read_bytes()
        report = []
        check.evidence('decisions', report)
        for choice in ('keep_current', 'restore_original'):
            original = prop.read_bytes()
            candidate = check.directory / (choice + '.json')
            data = json.loads(original)
            data['name'] = 'Recovery32-candidate'
            candidate.write_text(json.dumps(data), encoding='utf-8')
            child = IsolatedProcess([PWSH, '-NoProfile', '-File', str(v.ROOT / 'tools/media_journal_child_32.ps1'),
                                     '-ClipId', clip_id, '-Candidate', str(candidate), '-PauseAt', 'detached'], v.ROOT)
            try:
                ready = json.loads(child.read_line(30))
                check.evidence('conflict_stage', ready)
                v.require(ready['phase'] == 'detached', 'Missing durable detached boundary', ready)
                data['name'] = 'Recovery32-external'
                data[KEY] = {'decision': choice}
                with prop.open('x', encoding='utf-8') as stream:
                    json.dump(data, stream)
                child.stdin.write(b'continue\n')
                outcome = json.loads(child.read_line(30))
                v.require(not outcome['ok'] and outcome['recovery_pending'], 'Conflict was not retained', outcome)
                v.require(win32event.WaitForSingleObject(child.process, 5000) == win32con.WAIT_OBJECT_0, 'Helper did not exit')
            finally:
                child.close()
            pending = (await check.library('media_recovery_list'))['journals']
            journal = next(item for item in pending if item.get('clip_id') == clip_id)
            data[KEY]['newer'] = True
            prop.write_text(json.dumps(data), encoding='utf-8')
            await check.rejected('project_library', 'revision changed', operation='media_recovery_resolve', options={
                'journal_token': journal['token'], 'choice': choice, 'expected_revision': journal['revision']})
            journal = next(item for item in (await check.library('media_recovery_list'))['journals'] if item.get('clip_id') == clip_id)
            accepted = prop.read_bytes()
            if choice == 'restore_original':
                child = IsolatedProcess([PWSH, '-NoProfile', '-File', str(v.ROOT / 'tools/media_resolution_child_33.ps1'),
                                         '-Token', journal['token'], '-Revision', journal['revision']], v.ROOT)
                try:
                    decision = json.loads(child.read_line(30))
                    v.require(decision['phase'] == 'decision', 'Decision was not durable', decision)
                    win32process.TerminateProcess(child.process, 98)
                    v.require(win32event.WaitForSingleObject(child.process, 5000) == win32con.WAIT_OBJECT_0, 'Decision helper remained live')
                finally:
                    child.close()
            else:
                await check.library('media_recovery_resolve', journal_token=journal['token'], choice=choice,
                                    expected_revision=journal['revision'])
            await check.library('media_get', clip_id=clip_id)
            v.require(prop.read_bytes() == (accepted if choice == 'keep_current' else original), 'Wrong conflict decision applied')
            v.require(path.read_bytes() == clip_bytes, 'Clip bytes changed during resolution')
            archive = (v.ROOT / '.runtime/media-recovery-history' / journal['token']).resolve()
            v.require(archive.is_relative_to((v.ROOT / '.runtime/media-recovery-history').resolve()), 'History escaped workspace')
            v.require(any(item.read_bytes() == accepted for item in archive.glob('accepted-current-*.json')), 'Accepted bytes were not retained')
            report.append({'choice': choice, 'stale_revision_rejected': True, 'decision_crash': choice == 'restore_original'})
            shutil.rmtree(archive)  # Only this synthetic conflict's validated archive.
        await check.library('media_delete', sid, clip_id=clip_id)


@v.feature('library.voices_phrases_33', 'library', 'voicebanks', 'project_create', 'project_edit', 'project_library', 'project_save', 'project_open')
async def voices_phrases(check):
    voices = [item for item in (await check.call('voicebanks'))['voices']
              if item['kind'] == 'Dnn' and item['available_in_sequence']]
    v.require(voices, 'No AI voices installed')
    async with check.project() as sid:
        await check.edit(sid, 'track.create', type='MidiAi', name='AI voices')
        for index, voice in enumerate(voices):
            scope = {'track_index': 0, 'part_index': index}
            await check.edit(sid, 'part.create', track_index=0, start_tick=index * 3840, duration_tick=2880, name=voice['name'])
            await check.edit(sid, 'voice.set', **scope, ai_voice_bank_id=voice['comp_id'])
            note = await check.edit(sid, 'note.add', **scope, start_tick=0, duration_tick=240, number=60, lyric='い', lang_id=0)
            v.require(note['is_valid_phonemes'] and note['phonemes'], 'Voice produced no valid first note', voice['name'])
        for index in range(1, 6):
            await check.edit(sid, 'note.add', **SCOPE, start_tick=index * 480, duration_tick=240, number=60,
                             lyric='あ', phonemes='a', lang_id=0)
        for language, phrase in ((0, 'こんにちは'), (1, 'hello'), (4, 'ni hao')):
            before = await check.edit(sid, 'note.list', **SCOPE)
            applied = await check.library('lyrics_apply', sid, **SCOPE, note_index=0, language_id=language, lyrics=phrase)
            v.require(applied['affected_length'] > 0, 'Phrase was not applied', applied)
            after = await check.edit(sid, 'note.list', **SCOPE)
            await check.edit(sid, 'undo')
            v.require(await check.edit(sid, 'note.list', **SCOPE) == before, 'Phrase undo differs')
            await check.edit(sid, 'redo')
            v.require(await check.edit(sid, 'note.list', **SCOPE) == after, 'Phrase redo differs')
        before = await check.edit(sid, 'note.list', **SCOPE)
        history = await check.edit(sid, 'history.status')
        await check.rejected('project_library', 'phrase|truncated|candidate', session_id=sid, operation='lyrics_apply',
                             options={**SCOPE, 'note_index': 5, 'language_id': 0, 'lyrics': 'こんにちは'})
        v.require(await check.edit(sid, 'note.list', **SCOPE) == before and await check.edit(sid, 'history.status') == history,
                  'Truncated phrase changed state')
        _, saved = await check.save(sid, 'all-ai-voices')
    reopened = (await check.call('project_open', path=str(saved)))['session_id']
    try:
        for index, voice in enumerate(voices):
            actual = await check.edit(reopened, 'voice.get', track_index=0, part_index=index)
            v.require(actual['ai_voice_bank_id'] == voice['comp_id'], 'Voice identity did not roundtrip', voice['name'])
    finally:
        await check.close(reopened)
    check.evidence('voices', [item['name'] for item in voices])


@v.feature('preservation.agent_mutations_33', 'preservation', 'score_compose', 'project_edit', 'project_open', 'project_save',
           'project_clipboard', 'project_merge', 'project_library', 'project_audio')
async def agent_mutations(check):
    async with check.project(score=True) as seed:
        await check.edit(seed, 'pitch.set', **SCOPE, note_index=0, points=[{'tick': 100, 'value': 60}])
        await check.edit(seed, 'controller.set', **SCOPE, type='Dynamics', replace=True,
                         points=[{'tick': 60, 'value': 30}, {'tick': 180, 'value': 64}])
        for lane in ('track_volume', 'track_pan'):
            spec = await check.edit(seed, 'automation.list', scope=lane, track_index=0)
            await check.edit(seed, 'automation.set', scope=lane, track_index=0, points=[{'tick': 480, 'value': spec['minimum']}])
        sequence, native = await check.save(seed, 'mixed-native')
    _, members = v.read_vpr(native)
    track = sequence['tracks'][0]
    for lane in ('volume', 'panpot'):
        for item in track[lane]['events']:
            item[KEY] = {'lane': lane, 'tick': item['pos']}
    part = track['parts'][0]
    part[KEY] = {'owner': 'part'}
    for lane in part['controllers']:
        if lane['name'] == 'dynamics':
            for item in lane['events']:
                item[KEY] = {'lane': 'dynamics', 'tick': item['pos']}
    part['notes'][0]['directPitches'][0][KEY] = {'owner': 'pitch'}
    path = fixture(check, sequence, members, 'mixed-extensions')
    sid = (await check.call('project_open', path=str(path)))['session_id']
    clipboard = None
    try:
        await check.edit(sid, 'note.add', **SCOPE, start_tick=1680, duration_tick=240, number=70, lyric='い', lang_id=0)
        await check.edit(sid, 'note.update', **SCOPE, note_index=1, number=65)
        await check.library('lyrics_apply', sid, **SCOPE, note_index=1, language_id=0, lyrics='い')
        stable, _ = await check.save(sid, 'mixed-edits')
        v.require(stable['tracks'][0]['volume'] == track['volume'] and stable['tracks'][0]['panpot'] == track['panpot'] and
                  stable['tracks'][0]['parts'][0]['controllers'] == part['controllers'] and
                  stable['tracks'][0]['parts'][0]['notes'][0]['directPitches'] == part['notes'][0]['directPitches'],
                  'Ordinary mutation changed extended curves')
        for operation in ('note.remove', 'note.clear', 'part.remove', 'track.remove'):
            options = dict(SCOPE, note_index=0) if operation == 'note.remove' else dict(SCOPE)
            await check.edit(sid, operation, **options)
            await check.save(sid, 'deleted-' + operation)
            await check.edit(sid, 'undo')
            restored, _ = await check.save(sid, 'restored-' + operation)
            v.require(restored['tracks'] == stable['tracks'], 'Deletion undo lost metadata', operation)
        await check.edit(sid, 'part.split', **SCOPE, split_tick=450)
        divided, _ = await check.save(sid, 'mixed-part-split')
        v.require(divided['tracks'][0]['parts'][0]['notes'][0]['directPitches'] == part['notes'][0]['directPitches'],
                  'Part split lost pitch metadata')
        await check.edit(sid, 'part.join', track_index=0, part_indices=[0, 1])
        joined, _ = await check.save(sid, 'mixed-part-join')
        v.require(joined['tracks'][0]['parts'][0]['notes'][0]['directPitches'] == part['notes'][0]['directPitches'],
                  'Part join lost pitch metadata')
        await check.edit(sid, 'undo')
        await check.edit(sid, 'undo')
        await check.edit(sid, 'track.duplicate', track_index=0)
        duplicated, _ = await check.save(sid, 'mixed-duplicate')
        v.require(duplicated['tracks'][1] == duplicated['tracks'][0], 'Track duplicate lost extended fields')
        await check.edit(sid, 'undo')
        cut = (await check.call('project_clipboard', session_id=sid, operation='cut',
                               options={'kind': 'parts', 'track_index': 0, 'indices': [0]}))['clipboard_id']
        try:
            await check.edit(sid, 'undo')
            restored, _ = await check.save(sid, 'mixed-cut-undo')
            v.require(restored['tracks'] == stable['tracks'], 'Cut undo lost metadata')
        finally:
            await check.call('project_clipboard', operation='clear', options={'clipboard_id': cut})
        clipboard = (await check.call('project_clipboard', session_id=sid, operation='copy', options={'kind': 'tracks', 'indices': [0]}))['clipboard_id']
        async with check.project() as target:
            await check.call('project_clipboard', session_id=target, operation='paste', options={'clipboard_id': clipboard, 'offset_tick': 3840})
            moved, _ = await check.save(target, 'mixed-transfer')
            v.require(moved['tracks'][0]['parts'][0]['notes'] == stable['tracks'][0]['parts'][0]['notes'], 'Transfer lost note or pitch fields')
            v.require(moved['tracks'][0]['parts'][0]['controllers'] == stable['tracks'][0]['parts'][0]['controllers'], 'Transfer lost controllers')
            v.require(moved['tracks'][0]['volume']['events'][1]['pos'] == 4320 and
                      moved['tracks'][0]['volume']['events'][1][KEY]['tick'] == 480, 'Automation offset lost event identity')
            await check.call('project_merge', session_id=target, path=str(path), include_tempo=False, offset_tick=7680)
            merged, saved = await check.save(target, 'mixed-merge')
            v.require(len(merged['tracks']) == 2 and merged['tracks'][1]['parts'][0]['notes'][0]['directPitches'][0][KEY] == {'owner': 'pitch'},
                      'Merge lost pitch owner')
            await check.edit(target, 'undo')
            await check.edit(target, 'redo')
        reopened = (await check.call('project_open', path=str(saved)))['session_id']
        await check.close(reopened)
        wav = check.directory / 'import.wav'
        with wave.open(str(wav), 'wb') as stream:
            stream.setparams((1, 2, 44100, 4410, 'NONE', 'not compressed'))
            stream.writeframes(b'\x00\x00' * 4410)
        await check.audio(sid, 'import_audio', path=str(wav), position_tick=4000, name='Imported')
        await check.audio(sid, 'edit_audio', track_index=1, part_index=0, name='Edited')
        effects = (await check.audio(sid, 'effects', scope='catalog'))['effects']
        gain = next(item for item in effects if item['name'].casefold() == 'gain')
        await check.audio(sid, 'set_effect', action='add', effect_id=gain['effect_id'])
        v.require(len((await check.audio(sid, 'effects', scope='master'))['effects']) == 1, 'Effect was not added')
        await check.edit(sid, 'undo')
        v.require((await check.audio(sid, 'effects', scope='master'))['effects'] == [], 'Effect undo failed')
        with_audio, _ = await check.save(sid, 'mixed-audio')
        v.require(with_audio['tracks'][0] == stable['tracks'][0] and with_audio['tracks'][1]['parts'][0]['name'] == 'Edited',
                  'Audio operation changed unrelated extensions')
    finally:
        if clipboard is not None:
            await check.call('project_clipboard', operation='clear', options={'clipboard_id': clipboard})
        await check.close(sid)
    plain = copy.deepcopy(sequence)
    for lane in ('volume', 'panpot'):
        for item in plain['tracks'][0][lane]['events']:
            item.pop(KEY, None)
    for lane in plain['tracks'][0]['parts'][0]['controllers']:
        for item in lane['events']:
            item.pop(KEY, None)
    plain['tracks'][0]['parts'][0]['notes'][0]['directPitches'][0].pop(KEY, None)
    sid = (await check.call('project_open', path=str(fixture(check, plain, members, 'media-extensions'))))['session_id']
    clip_id = None
    try:
        clip = (await check.library('media_capture', sid, **SCOPE, name='Archived33'))['clip']
        clip_id = clip['clip_id']
        source = Path(clip['path'])
        before = source.read_bytes()
        await check.library('media_update', sid, clip_id=clip_id, name='Archived33-updated', tempo=12345)
        v.require(source.read_bytes() == before, 'Media update changed immutable archive metadata')
    finally:
        if clip_id is not None:
            await check.library('media_delete', sid, clip_id=clip_id)
        await check.close(sid)


@v.feature('preservation.pitch_split_join_33', 'preservation', 'score_compose', 'project_edit', 'project_open', 'project_save')
async def pitch_split_join(check):
    seed = await check.call('score_compose', output_name=check.output('pitch-seed'), title='Pitch provenance', bpm=120,
                            notes=[{'start': 0, 'duration': 2, 'pitch': 60, 'lyric': 'あ', 'phoneme': 'a', 'lang_id': 0}])
    sid = seed['native_session']['session_id']
    try:
        await check.edit(sid, 'pitch.set', **SCOPE, note_index=0, points=[{'tick': 100, 'value': 60}, {'tick': 300, 'value': 61}])
        data, path = await check.save(sid, 'pitch-native')
    finally:
        await check.close(sid)
    _, members = v.read_vpr(path)
    for point in data['tracks'][0]['parts'][0]['notes'][0]['directPitches']:
        point[KEY] = {'origin': point['pos']}
    source = fixture(check, data, members, 'pitch-extended')
    sid = (await check.call('project_open', path=str(source)))['session_id']
    try:
        await check.edit(sid, 'note.split', **SCOPE, note_index=0, split_tick=480)
        split, split_path = await check.save(sid, 'pitch-split')
        notes = split['tracks'][0]['parts'][0]['notes']
        v.require(len(notes) == 2 and all(sum(KEY in p for p in n['directPitches']) == 2 for n in notes),
                  'Split did not preserve both source trajectories')
        await check.edit(sid, 'note.join', **SCOPE, note_indices=[0, 1])
        joined, _ = await check.save(sid, 'pitch-joined')
        v.require(sum(KEY in p for p in joined['tracks'][0]['parts'][0]['notes'][0]['directPitches']) == 2,
                  'Join lost marked pitch points')
        await check.edit(sid, 'undo')
        undone, _ = await check.save(sid, 'pitch-join-undo')
        v.require(undone['tracks'] == split['tracks'], 'Join undo changed pitch provenance')
    finally:
        await check.close(sid)
    conflicting = copy.deepcopy(split)
    point = next(p for p in conflicting['tracks'][0]['parts'][0]['notes'][1]['directPitches'] if KEY in p)
    point[KEY] = {'conflict': True}
    _, split_members = v.read_vpr(split_path)
    sid = (await check.call('project_open', path=str(fixture(check, conflicting, split_members, 'pitch-conflict'))))['session_id']
    try:
        history = await check.edit(sid, 'history.status')
        await check.rejected('project_edit', 'conflicting pitch provenance', session_id=sid, operation='note.join',
                             options={**SCOPE, 'note_indices': [0, 1]})
        actual, _ = await check.save(sid, 'pitch-conflict-rollback')
        v.require(actual['tracks'] == conflicting['tracks'] and await check.edit(sid, 'history.status') == history,
                  'Pitch conflict did not roll back notes and history')
    finally:
        await check.close(sid)


if __name__ == '__main__':
    if '--case' not in sys.argv:
        for case in ('library.recovery_resolution_33', 'library.voices_phrases_33', 'preservation.agent_mutations_33',
                     'preservation.pitch_split_join_33'):
            sys.argv.extend(['--case', case])
    raise SystemExit(v.main())
