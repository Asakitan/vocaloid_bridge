"""Synthetic AI controller transfer acceptance against the background native host."""
import json
import sys
import zipfile
import verify_features as v

KEY = 'x_transfer_controller'


def lane(part):
    return [(e['pos'], e['value'], e.get(KEY)) for e in next(
        c['events'] for c in part['controllers'] if c['name'] == 'dynamics')]


def marker(owner):
    return [(60, 30, {'owner': owner, 'nested': [True, None]}), (180, 64, None)]


@v.feature('preservation.controller_transfer', 'preservation', 'score_compose', 'project_open', 'project_clipboard', 'project_merge', 'project_save')
async def controller_transfer(check):
    fixtures = []
    for name in ('source', 'target'):
        seed = await check.call('score_compose', output_name=check.output('controller-transfer-seed'),
            title=name, bpm=120, notes=[{'start': 0, 'duration': 1, 'pitch': 60,
            'lyric': 'あ', 'phoneme': 'a', 'lang_id': 0}])
        sid = seed['native_session']['session_id']
        await check.edit(sid, 'controller.set', track_index=0, part_index=0, type='Dynamics',
                         points=[{'tick': 60, 'value': 30}, {'tick': 180, 'value': 64}], replace=True)
        seq, path = await check.save(sid, 'controller-transfer-native')
        await check.close(sid)
        _, members = v.read_vpr(path)
        events = next(c['events'] for c in seq['tracks'][0]['parts'][0]['controllers'] if c['name'] == 'dynamics')
        events[0][KEY] = {'owner': name, 'nested': [True, None]}
        members['Project/sequence.json'] = json.dumps(seq, ensure_ascii=False).encode()
        path = v.ROOT / 'output' / check.output('controller-transfer-input')
        with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
            for member, data in members.items(): archive.writestr(member, data)
        fixtures.append((path, path.read_bytes()))
    source_path, original = fixtures[0]
    clips = []
    target = (await check.call('project_open', path=str(fixtures[1][0])))['session_id']
    try:
        source = (await check.call('project_open', path=str(source_path)))['session_id']
        for kind, op in (('tracks', 'copy'), ('notes', 'copy'), ('parts', 'cut')):
            clip = (await check.call('project_clipboard', session_id=source, operation=op,
                options={'kind': kind, 'track_index': 0, 'part_index': 0, 'indices': [0]}))['clipboard_id']
            clips.append(clip)
        seq, _ = await check.save(source, 'controller-transfer-cut')
        v.require(not seq['tracks'][0].get('parts'), 'Cut retained source part')
        await check.edit(source, 'undo')
        seq, _ = await check.save(source, 'controller-transfer-cut-undo')
        v.require(lane(seq['tracks'][0]['parts'][0]) == marker('source'), 'Cut undo lost source metadata')
        await check.edit(source, 'redo')
        seq, _ = await check.save(source, 'controller-transfer-cut-redo')
        v.require(not seq['tracks'][0].get('parts'), 'Cut redo retained source part')
        await check.close(source)
        await check.call('project_clipboard', session_id=target, operation='paste', options={
            'clipboard_id': clips[1], 'track_index': 0, 'part_index': 0, 'offset_tick': 480})
        seq, _ = await check.save(target, 'controller-transfer-note')
        v.require(lane(seq['tracks'][0]['parts'][0]) == marker('target'), 'Note paste copied parent lane')
        await check.call('project_clipboard', session_id=target, operation='paste', options={
            'clipboard_id': clips[2], 'track_index': 0, 'offset_tick': 1920})
        seq, _ = await check.save(target, 'controller-transfer-part')
        parts = seq['tracks'][0]['parts']
        v.require([lane(p) for p in parts] == [marker('target'), marker('source')], 'Part lane transfer changed')
        v.require(parts[1]['pos'] == 1920, 'Part offset changed')
        await check.edit(target, 'undo')
        seq, _ = await check.save(target, 'controller-transfer-part-undo')
        v.require(len(seq['tracks'][0]['parts']) == 1 and lane(seq['tracks'][0]['parts'][0]) == marker('target'), 'Part undo changed target lane')
        await check.edit(target, 'redo')
        await check.call('project_clipboard', session_id=target, operation='paste', options={
            'clipboard_id': clips[0], 'offset_tick': 3840})
        for clip in clips:
            await check.call('project_clipboard', operation='clear', options={'clipboard_id': clip})
        clips.clear()
        seq, _ = await check.save(target, 'controller-transfer-track')
        v.require(lane(seq['tracks'][1]['parts'][0]) == marker('source') and seq['tracks'][1]['parts'][0]['pos'] == 3840, 'Track transfer changed')
        await check.edit(target, 'undo')
        seq, _ = await check.save(target, 'controller-transfer-track-undo')
        v.require(len(seq['tracks']) == 1, 'Track undo failed')
        await check.edit(target, 'redo')
        seq, path = await check.save(target, 'controller-transfer-track-redo')
        reopened = (await check.call('project_open', path=str(path)))['session_id']
        try:
            seq, _ = await check.save(reopened, 'controller-transfer-reopen')
            v.require([lane(p) for p in seq['tracks'][0]['parts']] == [marker('target'), marker('source')] and
                      lane(seq['tracks'][1]['parts'][0]) == marker('source'), 'Reopen lost controller metadata')
        finally: await check.close(reopened)
        v.require(source_path.read_bytes() == original, 'Source file changed')
    finally:
        for clip in clips: await check.call('project_clipboard', operation='clear', options={'clipboard_id': clip})
        await check.close(target)
    target = (await check.call('project_open', path=str(fixtures[1][0])))['session_id']
    try:
        before, _ = await check.save(target, 'controller-transfer-conflict-before')
        await check.rejected('project_merge', 'ambiguous|indistinguishable', session_id=target,
                             path=str(source_path), include_tracks=True, include_tempo=False, offset_tick=0)
        after, _ = await check.save(target, 'controller-transfer-conflict-after')
        v.require(before == after, 'Rejected merge changed target')
        await check.call('project_merge', session_id=target, path=str(source_path), include_tracks=True,
                         include_tempo=False, offset_tick=1920)
        seq, _ = await check.save(target, 'controller-transfer-merge')
        v.require([lane(t['parts'][0]) for t in seq['tracks']] == [marker('target'), marker('source')] and
                  seq['tracks'][1]['parts'][0]['pos'] == 1920, 'Merge lanes or offset changed')
        await check.edit(target, 'undo')
        seq, _ = await check.save(target, 'controller-transfer-merge-undo')
        v.require(len(seq['tracks']) == 1 and lane(seq['tracks'][0]['parts'][0]) == marker('target'), 'Merge undo changed target')
        await check.edit(target, 'redo')
        seq, path = await check.save(target, 'controller-transfer-merge-redo')
        reopened = (await check.call('project_open', path=str(path)))['session_id']
        try:
            seq, _ = await check.save(reopened, 'controller-transfer-merge-reopen')
            v.require([lane(t['parts'][0]) for t in seq['tracks']] == [marker('target'), marker('source')], 'Merge reopen lost lanes')
        finally: await check.close(reopened)
        await check.edit(target, 'controller.remove', track_index=1, part_index=0,
                         type='Dynamics', controller_index=0)
        await check.edit(target, 'controller.set', track_index=1, part_index=0,
                         type='Dynamics', points=[{'tick': 60, 'value': 30}])
        seq, _ = await check.save(target, 'controller-transfer-recreated')
        v.require(lane(seq['tracks'][1]['parts'][0]) == [(60, 30, None), (180, 64, None)],
                  'Recreated controller retained deleted metadata')
        v.require(source_path.read_bytes() == original and fixtures[1][0].read_bytes() == fixtures[1][1], 'Original fixtures changed')
    finally: await check.close(target)


if __name__ == '__main__':
    sys.argv.extend(['--case', 'preservation.controller_transfer'])
    raise SystemExit(v.main())
