"""Generate a disposable native clip and observe an independent VMM property editor."""
import json, sys, zipfile, shutil
from pathlib import Path
import verify_features as v
sys.path.insert(0, str(v.ROOT))
from vocaloid_bridge.native_client import IsolatedProcess

@v.feature('preservation.media_native_20', 'preservation', 'score_compose', 'project_open', 'project_save', 'project_library')
async def probe(check):
    seed = await check.call('score_compose', output_name=check.output('media19-seed'), title='Synthetic media 19', bpm=120, notes=[{'start': 0, 'duration': 1, 'pitch': 60, 'lyric': 'あ', 'phoneme': 'a', 'lang_id': 0}])
    sid = seed['native_session']['session_id']
    seq, path = await check.save(sid, 'media19-seed')
    await check.close(sid)
    _, members = v.read_vpr(path)
    part = seq['tracks'][0]['parts'][0]
    # Plain fixture
    # No archive extensions
    members['Project/sequence.json'] = json.dumps(seq, ensure_ascii=False).encode()
    source = v.ROOT / 'output' / check.output('media19-input')
    with zipfile.ZipFile(source, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items(): archive.writestr(name, data)
    sid = (await check.call('project_open', path=str(source)))['session_id']
    clip_id = None
    try:
        clip = (await check.library('media_capture', sid, track_index=0, part_index=0, name='Media19 '+check.run_id))['clip']
        clip_id = clip['clip_id']
        clip_path = Path(clip['path']).resolve()
        v.require(clip_path.is_relative_to((v.ROOT/'.runtime/library/media').resolve()) and clip_path.name == clip_id+'.vsclip', 'Unexpected clip path')
        v.require('vocaloid_bridge_archive_entities_v1' not in json.loads(clip_path.read_bytes()), 'Not ordinary')
        root = check.directory / 'media20-private'
        root.mkdir()
        shutil.copytree(clip_path.parent, root / clip_id)
        copied_property = root / clip_id / 'property.json'
        property_data = json.loads(copied_property.read_text(encoding='utf-8-sig'))
        property_data['x_media19_property'] = {'nested': [True, None, {'value': 'synthetic'}]}
        copied_property.write_text(json.dumps(property_data, ensure_ascii=False), encoding='utf-8')
        await check.library('media_delete', sid, clip_id=clip_id)
        clip_id = None
        process = IsolatedProcess([r'C:\Program Files\PowerShell\7\pwsh.exe', '-NoProfile', '-File', str(v.ROOT/'tools/probe_media_native_20.ps1'), '-Root', str(root), '-ClipId', clip['clip_id']], v.ROOT)
        try:
            observation = json.loads(process.read_line(120))
        finally:
            process.close()
        check.evidence('native_media19', observation)
        v.require(observation['committed_name'] == 'Media20 staged', 'Staged commit failed', observation)
    finally:
        if clip_id: await check.library('media_delete', sid, clip_id=clip_id)
        await check.close(sid)

if __name__ == '__main__':
    sys.argv.extend(['--case', 'preservation.media_native_20'])
    raise SystemExit(v.main())
