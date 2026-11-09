"""Synthetic audio mutation regression; requires a rebuilt native host."""
import json
import sys
import tempfile
import zipfile
from pathlib import Path
import verify_features as v
from check_archive_audio_transfer import make_wave


async def exported(check, session, track, part, original):
    result = await check.call('project_audio', session_id=session, operation='export_audio', options={
        'track_index': track, 'part_index': part, 'original': original,
        'output_name': check.output('mutation-asset', '.wav')})
    return Path(result['path']).read_bytes()


@v.feature('preservation.audio_mutation_ordinary', 'preservation', 'project_audio', 'project_save')
async def audio_mutation_ordinary(check):
    with tempfile.TemporaryDirectory(prefix='bridge-audio-ordinary-') as temp:
        wave = Path(temp) / 'ordinary.wav'
        make_wave(wave, .03)
        original = wave.read_bytes()
        session = (await check.call('project_create', title='Ordinary audio transaction'))['session_id']
        try:
            await check.audio(session, 'import_audio', path=str(wave))
            await check.audio(session, 'edit_audio', track_index=0, part_index=0, name='ordinary edit')
            await check.edit(session, 'undo')
            await check.edit(session, 'redo')
            seq, path = await check.save(session, 'ordinary-audio-redo')
            v.require(seq['tracks'][0]['parts'][0]['name'] == 'ordinary edit', 'Ordinary redo failed')
            reopened = (await check.call('project_open', path=str(path)))['session_id']
            try:
                v.require(await exported(check, reopened, 0, 0, True) == original, 'Ordinary asset mismatch')
            finally:
                await check.close(reopened)
            v.require(wave.read_bytes() == original, 'Ordinary source changed')
        finally:
            await check.close(session)


@v.feature('preservation.audio_mutation', 'preservation', 'project_audio', 'project_save')
async def audio_mutation(check):
    with tempfile.TemporaryDirectory(prefix='bridge-audio-mutation-') as temp:
        root = Path(temp)
        source = root / 'source.wav'; make_wave(source, .03)
        processed = root / 'processed.wav'; make_wave(processed, .07)
        new_track = root / 'new-track.wav'; make_wave(new_track, .11)
        existing = root / 'existing-track.wav'; make_wave(existing, .13)
        inputs = {path: path.read_bytes() for path in (source, processed, new_track, existing)}
        seed = (await check.call('project_create', title='Audio mutation fixture'))['session_id']
        try:
            await check.audio(seed, 'import_audio', path=str(source))
            _, seed_path = await check.save(seed, 'audio-mutation-seed')
        finally:
            await check.close(seed)
        seq, members = v.read_vpr(seed_path)
        seq['tracks'][0]['x_track'] = 'track'
        part = seq['tracks'][0]['parts'][0]
        part['x_part'] = 'part'
        part['wav']['processedName'] = 'mutation-processed.wav'
        members['Project/Audio/mutation-processed.wav'] = inputs[processed]
        members['Project/opaque-audio-mutation.bin'] = b'opaque-audio-resource'
        members['Project/sequence.json'] = json.dumps(seq, ensure_ascii=False).encode()
        fixture = v.ROOT / 'output' / check.output('audio-mutation-fixture')
        with zipfile.ZipFile(fixture, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in members.items(): archive.writestr(name, data)
        fixture_bytes = fixture.read_bytes()
        session = (await check.call('project_open', path=str(fixture)))['session_id']
        try:
            v.require(await exported(check, session, 0, 0, True) == inputs[source], 'Original fixture mismatch')
            v.require(await exported(check, session, 0, 0, False) == inputs[processed], 'Processed fixture mismatch')
            await check.audio(session, 'edit_audio', track_index=0, part_index=0,
                              name='edited', position_tick=1920)
            await check.edit(session, 'undo')
            undone, _ = await check.save(session, 'audio-mutation-edit-undo')
            v.require(undone['tracks'][0]['parts'][0]['name'] != 'edited', 'Edit undo failed')
            await check.edit(session, 'redo')
            redone, _ = await check.save(session, 'audio-mutation-edit-redo')
            v.require(redone['tracks'][0]['parts'][0]['name'] == 'edited', 'Edit redo failed')
            await check.audio(session, 'import_audio', path=str(new_track))
            await check.edit(session, 'undo')
            undone, _ = await check.save(session, 'audio-mutation-new-track-undo')
            v.require(len(undone['tracks']) == 1, 'New-track import undo failed')
            await check.edit(session, 'redo')
            await check.audio(session, 'import_audio', path=str(existing), track_index=0, position_tick=9600)
            await check.edit(session, 'undo')
            undone, _ = await check.save(session, 'audio-mutation-existing-undo')
            v.require(len(undone['tracks'][0]['parts']) == 1, 'Existing-track import undo failed')
            await check.edit(session, 'redo')
            before, before_path = await check.save(session, 'audio-mutation-before-invalid')
            history = await check.edit(session, 'history.status')
            collision = v.ROOT / 'output' / check.output('audio-collision', '.wav')
            make_wave(collision, .19)
            collision_bytes = collision.read_bytes()
            try:
                await check.rejected('project_audio', 'overwrite its source', session_id=session,
                                     operation='process_audio', options={'path': str(collision),
                                     'output_name': collision.name, 'overwrite': True, 'action': 'reverse'})
                v.require(collision.read_bytes() == collision_bytes, 'Collision changed source WAV')
            finally:
                collision.unlink(missing_ok=True)
            await check.rejected('project_audio', 'end_tick', session_id=session, operation='edit_audio',
                                 options={'track_index': 0, 'part_index': 0, 'begin_tick': 10, 'end_tick': 10})
            after, after_path = await check.save(session, 'audio-mutation-after-invalid')
            v.require(before == after and v.read_vpr(before_path)[1] == v.read_vpr(after_path)[1],
                      'Rejected edit changed archive')
            v.require(history == await check.edit(session, 'history.status'), 'Rejected edit changed history')
            v.require(after['tracks'][0]['x_track'] == 'track' and after['tracks'][0]['parts'][0]['x_part'] == 'part',
                      'Mutation lost extensions')
            v.require(v.read_vpr(after_path)[1]['Project/opaque-audio-mutation.bin'] == b'opaque-audio-resource',
                      'Opaque resource lost')
            reopened = (await check.call('project_open', path=str(after_path)))['session_id']
            try:
                for track, part, original, expected in ((0, 0, True, source), (0, 0, False, processed),
                                                        (0, 1, True, existing), (1, 0, True, new_track)):
                    v.require(await exported(check, reopened, track, part, original) == inputs[expected],
                              'Reopened native audio asset differs')
            finally:
                await check.close(reopened)
            v.require(fixture.read_bytes() == fixture_bytes, 'Source archive changed')
            v.require(all(path.read_bytes() == data for path, data in inputs.items()), 'Input WAV changed')
        finally:
            await check.close(session)


if __name__ == '__main__':
    if '--case' not in sys.argv:
        sys.argv.extend(['--case', 'preservation.audio_mutation_ordinary', '--case', 'preservation.audio_mutation'])
    raise SystemExit(v.main())
