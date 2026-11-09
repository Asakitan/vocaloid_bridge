"""Historical 0.18.0 copy-validity observation; not a current release gate."""
import json, sys
from pathlib import Path
import verify_features as v
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vocaloid_bridge.projects import PHONEME_VALIDITY_MEMBER, _guard_note_replacement

def contains_direct(value):
    return (isinstance(value, dict) and ('directPitches' in value or any(contains_direct(x) for x in value.values())) or isinstance(value, list) and any(contains_direct(x) for x in value))

@v.feature('patch_copy_validity27', 'patch_copy_validity27', 'score_compose', 'score_patch', 'project_edit', 'project_open', 'project_save')
async def probe(check):
    evidence = {}; check.evidence('observation', evidence); sid = None
    try:
        seed = await check.call('score_compose', output_name=check.output('copy-validity-seed'), title='Synthetic copy validity', bpm=120, notes=[{'start':0,'duration':1,'pitch':60,'lyric':'あ','phoneme':'a','lang_id':0}])
        sid = seed['native_session']['session_id']
        seed_seq, _ = v.read_vpr(seed['path']); _guard_note_replacement(seed_seq)
        v.require(not contains_direct(seed_seq), 'Seed contains directPitches')
        v.require('aiVoice' in seed_seq['tracks'][0]['parts'][0], 'Not AI')
        evidence['set_invalid'] = await check.edit(sid, 'note.update', track_index=0, part_index=0, note_index=0, phonemes='a', is_valid_phonemes=False)
        v.require(evidence['set_invalid']['is_valid_phonemes'] is False, 'Flag did not set')
        seq, source = await check.save(sid, 'copy-validity-source'); await check.close(sid); sid = None
        _, members = v.read_vpr(source); before=source.read_bytes(); side=members[PHONEME_VALIDITY_MEMBER]
        evidence['source_sidecar']=json.loads(side); evidence['source_path']=str(source)
        _guard_note_replacement(seq); v.require(not contains_direct(seq), 'Saved source contains directPitches')
        path='/tracks/0/parts/0/notes'
        patched=await check.call('score_patch', path=str(source), output_name=check.output('copy-validity-patched'), operations=[{'op':'copy','from':path+'/0','path':path+'/-'},{'op':'replace','path':path+'/1/pos','value':960}])
        evidence['patched_path']=patched['path']
        patched_seq, patched_members=v.read_vpr(patched['path']); notes=patched_seq['tracks'][0]['parts'][0]['notes']
        v.require(len(notes)==2 and notes[0]==seq['tracks'][0]['parts'][0]['notes'][0] and notes[1]['pos']==960 and patched_members[PHONEME_VALIDITY_MEMBER]==side and source.read_bytes()==before, 'Fixture invariants failed')
        evidence['patch_invariants']={'original_note_unchanged':True,'source_unchanged':True,'sidecar_bytes_unchanged':True,'copy_position':notes[1]['pos']}
        sid=(await check.call('project_open',path=patched['path']))['session_id']
        evidence['opened']=(await check.edit(sid,'note.list',track_index=0,part_index=0))['notes']
        saved, saved_path=await check.save(sid,'copy-validity-saved'); evidence['saved_path']=str(saved_path)
        _, saved_members=v.read_vpr(saved_path); evidence['saved_sidecar']=json.loads(saved_members[PHONEME_VALIDITY_MEMBER]) if PHONEME_VALIDITY_MEMBER in saved_members else None
        await check.close(sid); sid=None
        sid=(await check.call('project_open',path=str(saved_path)))['session_id']
        evidence['reopened']=(await check.edit(sid,'note.list',track_index=0,part_index=0))['notes']
        v.require(len(evidence['opened'])==2 and len(evidence['reopened'])==2, 'Unexpected native note count')
        evidence['status']='observed'
    except Exception as error:
        evidence['error']=f'{type(error).__name__}: {error}'; raise
    finally:
        if sid: await check.close(sid)

if __name__=='__main__':
    if not any(x in ('--case','--category') for x in sys.argv[1:]): sys.argv.extend(['--case','patch_copy_validity27'])
    sys.exit(v.main())
