"""Private synthetic audio archive transfer acceptance; run with the built native host."""
import json
import math
import struct
import sys
import tempfile
import wave
import zipfile
from pathlib import Path
import verify_features as v


def make_wave(path, frequency):
    with wave.open(str(path), 'wb') as out:
        out.setparams((1, 2, 44100, 44100, 'NONE', 'not compressed'))
        out.writeframes(b''.join(struct.pack('<h', int(7000 * math.sin(i * frequency))) for i in range(44100)))


@v.feature('preservation.audio_clipboard_transfer', 'preservation', 'project_audio', 'project_clipboard', 'project_merge', 'project_save')
async def audio_transfer(check):
    clips = []
    with tempfile.TemporaryDirectory(prefix='bridge-audio-transfer-') as temp:
        base = Path(temp)
        sources = []
        for index, freq in enumerate((.03, .07)):
            folder = base / str(index); folder.mkdir()
            wav = folder / 'same-name.wav'; make_wave(wav, freq)
            processed = folder / 'processed.wav'; make_wave(processed, freq * 1.3)
            session = (await check.call('project_create', title='Audio fixture'))['session_id']
            await check.call('project_audio', session_id=session, operation='import_audio', options={'path': str(wav)})
            await check.edit(session, 'track.update', track_index=0, name='Audio fixture ' + str(index))
            seq, saved = await check.save(session, 'audio-seed')
            await check.close(session)
            seq, members = v.read_vpr(saved)
            track = seq['tracks'][0]; part = track['parts'][0]
            track['x_audio_track'] = index; part['x_audio_part'] = index
            # Explicit native archive processed asset, distinct from the original.
            part['wav']['processedName'] = 'processed-' + str(index) + '.wav'
            members['Project/Audio/' + part['wav']['processedName']] = processed.read_bytes()
            members['Project/opaque-' + str(index) + '.bin'] = bytes([index, 42])
            members['Project/sequence.json'] = json.dumps(seq, ensure_ascii=False).encode()
            fixture = v.ROOT / 'output' / check.output('audio-source')
            with zipfile.ZipFile(fixture, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
                for name, data in members.items(): archive.writestr(name, data)
            sources.append((fixture, fixture.read_bytes(), wav.read_bytes(), processed.read_bytes()))
        target = (await check.call('project_create', title='Audio destination'))['session_id']
        try:
            for index, (fixture, original, wavbytes, processedbytes) in enumerate(sources):
                src = (await check.call('project_open', path=str(fixture)))['session_id']
                # Verify that this archive fixture really exposes both native assets.
                for is_original, expected in ((True, wavbytes), (False, processedbytes)):
                    result = await check.call('project_audio', session_id=src, operation='export_audio', options={
                        'track_index': 0, 'part_index': 0, 'original': is_original,
                        'output_name': check.output('source-asset', '.wav')})
                    v.require(Path(result['path']).read_bytes() == expected, 'Native source asset mismatch')
                kind = 'tracks' if index == 0 else 'parts'
                clip = (await check.call('project_clipboard', session_id=src, operation='cut', options={
                    'kind': kind, 'track_index': 0, 'indices': [0]}))['clipboard_id']
                clips.append(clip)
                cut, _ = await check.save(src, 'audio-cut')
                v.require(not cut.get('tracks') if index == 0 else not cut['tracks'][0].get('parts'),
                          'Cut retained the selected audio entity')
                await check.edit(src, 'undo')
                restored, _ = await check.save(src, 'audio-cut-undo')
                v.require(restored['tracks'][0]['parts'][0]['x_audio_part'] == index, 'Cut undo lost extension')
                await check.edit(src, 'redo')
                redone, _ = await check.save(src, 'audio-cut-redo')
                v.require(not redone.get('tracks') if index == 0 else not redone['tracks'][0].get('parts'),
                          'Cut redo retained entity')
                await check.close(src)
                opts = {'clipboard_id': clip, 'offset_tick': index * 1920}
                if index: opts['track_index'] = 0
                await check.call('project_clipboard', session_id=target, operation='paste', options=opts)
                await check.call('project_clipboard', operation='clear', options={'clipboard_id': clip}); clips.remove(clip)
                v.require(fixture.read_bytes() == original, 'Source VPR changed')
            # A distinct source with a conflicting opaque member must fail before
            # changing the target. Keep both target archive bytes and history intact.
            conflict_seq, conflict_members = v.read_vpr(sources[1][0])
            conflict_members['Project/opaque-0.bin'] = b'different'
            conflict_path = v.ROOT / 'output' / check.output('audio-conflict')
            with zipfile.ZipFile(conflict_path, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
                for name, data in conflict_members.items(): archive.writestr(name, data)
            conflict_src = (await check.call('project_open', path=str(conflict_path)))['session_id']
            conflict_clip = (await check.call('project_clipboard', session_id=conflict_src, operation='copy',
                                               options={'kind': 'tracks', 'indices': [0]}))['clipboard_id']
            clips.append(conflict_clip)
            await check.close(conflict_src)
            before, before_path = await check.save(target, 'audio-before-conflict')
            await check.rejected('project_clipboard', 'opaque member conflict', session_id=target,
                                 operation='paste', options={'clipboard_id': conflict_clip})
            after, after_path = await check.save(target, 'audio-after-conflict')
            v.require(before == after and v.read_vpr(before_path)[1] == v.read_vpr(after_path)[1],
                      'Conflict changed target archive')
            await check.call('project_clipboard', operation='clear', options={'clipboard_id': conflict_clip})
            clips.remove(conflict_clip)
            seq, _ = await check.save(target, 'audio-pasted')
            v.require(seq['tracks'][0]['x_audio_track'] == 0, 'Track extension lost')
            v.require([p['x_audio_part'] for p in seq['tracks'][0]['parts']] == [0, 1], 'Part extensions lost')
            await check.edit(target, 'undo')
            undone, _ = await check.save(target, 'audio-undo')
            v.require(len(undone['tracks'][0]['parts']) == 1, 'Undo failed')
            await check.edit(target, 'redo')
            _, path = await check.save(target, 'audio-redo')
            reopened = (await check.call('project_open', path=str(path)))['session_id']
            try:
                for index, (_, _, wavbytes, processedbytes) in enumerate(sources):
                    for is_original, expected in ((True, wavbytes), (False, processedbytes)):
                        result = await check.call('project_audio', session_id=reopened, operation='export_audio', options={
                            'track_index': 0, 'part_index': index, 'original': is_original,
                            'output_name': check.output('reopened-asset', '.wav')})
                        v.require(Path(result['path']).read_bytes() == expected, 'Reopened asset mismatch')
            finally: await check.close(reopened)
        finally:
            for clip in clips:
                await check.call('project_clipboard', operation='clear', options={'clipboard_id': clip})
            await check.close(target)
        target = (await check.call('project_create', title='Audio merge destination'))['session_id']
        try:
            for index, (fixture, original, _, _) in enumerate(sources):
                await check.call('project_merge', session_id=target, path=str(fixture), include_tracks=True,
                                 include_tempo=False, offset_tick=index * 1920)
                v.require(fixture.read_bytes() == original, 'Audio merge changed original source')
            merged, _ = await check.save(target, 'audio-merge')
            v.require([t['x_audio_track'] for t in merged['tracks']] == [0, 1] and
                      [t['parts'][0]['x_audio_part'] for t in merged['tracks']] == [0, 1],
                      'Merged audio extensions changed')
            await check.edit(target, 'undo')
            undone, _ = await check.save(target, 'audio-merge-undo')
            v.require(len(undone['tracks']) == 1, 'Audio merge undo failed')
            await check.edit(target, 'redo')
            _, path = await check.save(target, 'audio-merge-redo')
            reopened = (await check.call('project_open', path=str(path)))['session_id']
            try:
                for index, (_, _, wavbytes, processedbytes) in enumerate(sources):
                    for is_original, expected in ((True, wavbytes), (False, processedbytes)):
                        result = await check.call('project_audio', session_id=reopened, operation='export_audio', options={
                            'track_index': index, 'part_index': 0, 'original': is_original,
                            'output_name': check.output('merged-asset', '.wav')})
                        v.require(Path(result['path']).read_bytes() == expected, 'Merged reopened asset mismatch')
            finally:
                await check.close(reopened)
        finally:
            await check.close(target)


if __name__ == '__main__':
    sys.argv.extend(['--case', 'preservation.audio_clipboard_transfer'])
    raise SystemExit(v.main())
