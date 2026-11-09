"""Regression for unknown properties on a disposable ordinary AI clip."""
import json, sys
from pathlib import Path
import verify_features as v

@v.feature('preservation.media_property_20', 'preservation', 'score_compose', 'project_library')
async def test(check):
    async with check.project(score=True) as sid:
        clip = (await check.library('media_capture', sid, track_index=0, part_index=0, name='Property20 '+check.run_id))['clip']
        clip_id = clip['clip_id']
        path = Path(clip['path']).resolve()
        try:
            v.require(path.is_relative_to((v.ROOT/'.runtime/library/media').resolve()), 'Unexpected clip path')
            v.require('vocaloid_bridge_archive_entities_v1' not in json.loads(path.read_bytes()), 'Fixture has archive metadata')
            prop = path.with_name('property.json')
            data = json.loads(prop.read_text(encoding='utf-8-sig'))
            marker = {'nested': [True, None, {'value':'synthetic'}]}
            data['x_property20'] = marker
            data['part']['x_property20_nested'] = marker
            prop.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            before = path.read_bytes()
            updated = (await check.library('media_update', sid, clip_id=clip_id, name='Property20 updated', tempo=12345))['clip']
            result = json.loads(prop.read_text(encoding='utf-8-sig'))
            check.evidence('media_property20', {'property':result, 'updated':updated, 'clip_unchanged':path.read_bytes()==before})
            v.require(result.get('x_property20') == marker and result['part'].get('x_property20_nested') == marker, 'Unknown properties lost', result)
            v.require(updated['name']=='Property20 updated' and updated['tempo']==12345 and path.read_bytes()==before, 'Update readback mismatch')
        finally:
            await check.library('media_delete', sid, clip_id=clip_id)

if __name__ == '__main__':
    sys.argv.extend(['--case', 'preservation.media_property_20'])
    raise SystemExit(v.main())
