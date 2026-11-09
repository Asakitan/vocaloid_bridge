"""Generate a disposable native clip and observe an independent VMM property editor."""
import json, sys, zipfile, shutil
from pathlib import Path
import verify_features as v
sys.path.insert(0, str(v.ROOT))
from vocaloid_bridge.native_client import IsolatedProcess

@v.feature('preservation.media_process_20', 'preservation', 'score_compose', 'project_open', 'project_save', 'project_library')
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
        fixture_id = clip_id
        clip_path = Path(clip['path']).resolve()
        v.require(clip_path.is_relative_to((v.ROOT/'.runtime/library/media').resolve()) and clip_path.name == clip_id+'.vsclip', 'Unexpected clip path')
        v.require('vocaloid_bridge_archive_entities_v1' not in json.loads(clip_path.read_bytes()), 'Not ordinary')
        root = check.directory / 'media20-private'
        root.mkdir()
        shutil.copytree(clip_path.parent, root / clip_id)
        copied_property = root / fixture_id / 'property.json'
        property_data = json.loads(copied_property.read_text(encoding='utf-8-sig'))
        property_data['x_media19_property'] = {'nested': [True, None, {'value': 'synthetic'}]}
        copied_property.write_text(json.dumps(property_data, ensure_ascii=False), encoding='utf-8')
        await check.library('media_delete', sid, clip_id=clip_id)
        clip_id = None
        stage = check.directory / 'media20-stage'
        shutil.copytree(root, stage)
        live_prop = root / fixture_id / 'property.json'
        stage_prop = stage / fixture_id / 'property.json'
        original = live_prop.read_bytes()
        exe = r'C:\Program Files\PowerShell\7\pwsh.exe'
        script = str(v.ROOT/'tools/probe_media_process_20.ps1')
        def start(path, mode):
            return IsolatedProcess([exe, '-NoProfile', '-File', script, '-Root', str(path), '-ClipId', fixture_id, '-Mode', mode], v.ROOT)
        live = start(root, 'live')
        stage_process = None
        try:
            ready = json.loads(live.read_line(120))
            stage_process = start(stage, 'stage')
            stage_result = json.loads(stage_process.read_line(120))
            stage_process.close(); stage_process = None
            v.require(live_prop.read_bytes() == original, 'Stage altered live file')
            live.stdin.write(b'read\n'); before = json.loads(live.read_line(120))
            staged_json = json.loads(stage_prop.read_bytes())
            old_json = json.loads(original)
            staged_json['x_media19_property'] = old_json['x_media19_property']
            temp = live_prop.with_name('property-20.tmp')
            temp.write_text(json.dumps(staged_json, ensure_ascii=False), encoding='utf-8')
            import win32con, win32file
            handle = win32file.CreateFile(str(live_prop), win32con.GENERIC_READ, win32con.FILE_SHARE_READ, None, win32con.OPEN_EXISTING, win32con.FILE_ATTRIBUTE_NORMAL, None)
            try:
                try: win32file.MoveFileEx(str(temp), str(live_prop), win32con.MOVEFILE_REPLACE_EXISTING); lock_failed=False
                except Exception: lock_failed=True
                locked_unchanged = live_prop.read_bytes() == original
                live.stdin.write(b'read\n'); locked_cache=json.loads(live.read_line(120))
            finally: handle.Close()
            win32file.MoveFileEx(str(temp), str(live_prop), win32con.MOVEFILE_REPLACE_EXISTING)
            live.stdin.write(b'read\n'); stale=json.loads(live.read_line(120))
            live.stdin.write(b'refresh\n'); refresh=json.loads(live.read_line(120))
            final=json.loads(live_prop.read_bytes())
            observation={'ready':ready,'stage':stage_result,'before':before,'lock_failed':lock_failed,'locked_unchanged':locked_unchanged,'locked_cache':locked_cache,'stale':stale,'refresh':refresh,'unknown':final.get('x_media19_property')}
            check.evidence('media_process20', observation)
            v.require(stage_result['name']=='Media20 staged' and before['name']==ready['name'] and lock_failed and locked_unchanged and locked_cache==before and stale==before and refresh['status']=='None' and refresh['name']=='Media20 staged' and final['x_media19_property']==old_json['x_media19_property'], 'Process isolation/commit observation differs', observation)
        finally:
            if stage_process: stage_process.close()
            live.close()
    finally:
        if clip_id: await check.library('media_delete', sid, clip_id=clip_id)
        await check.close(sid)

if __name__ == '__main__':
    sys.argv.extend(['--case', 'preservation.media_process_20'])
    raise SystemExit(v.main())
