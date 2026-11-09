"""Historical 0.18.0 red observation; not a current release gate."""
from pathlib import Path
from copy import deepcopy
import json, sys, uuid, zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vocaloid_bridge.projects import ProjectStore, _EDITOR_AI_NOTE, SEQUENCE_MEMBER, PHONEME_VALIDITY_MEMBER
root=Path(__file__).resolve().parents[1]; run=root/'artifacts'/('patch-sidecar-27-'+uuid.uuid4().hex); run.mkdir(parents=True)
a=deepcopy(_EDITOR_AI_NOTE); a['marker']='A'; b=deepcopy(a); b['marker']='B'
part={'notes':[a,b]}; data={'title':'fixture','tracks':[{'name':'A','parts':[part]},{'name':'B','parts':[deepcopy(part)]}]}
metadata={'Format':'vocaloid-bridge-phoneme-validity','Version':1,'Notes':[{'TrackIndex':0,'PartIndex':0,'NoteIndex':0,'Note':{'IsValid':False,'Position':a['pos'],'Duration':a['duration'],'Number':a['number'],'Lyric':a['lyric'],'Phonemes':a['phoneme'],'LanguageId':a['langID']}}]}
source=run/'source.vpr'
with zipfile.ZipFile(source,'w') as z:
 z.writestr(SEQUENCE_MEMBER,json.dumps(data)); z.writestr(PHONEME_VALIDITY_MEMBER,json.dumps(metadata)); z.writestr('fixture-resource.txt','preserve')
p='/tracks/0/parts/0/notes'
cases={'test_field':[{'op':'test','path':p+'/0/marker','value':'A'},{'op':'replace','path':p+'/0/velocity','value':72}],'insert':[{'op':'add','path':p+'/0','value':b}],'remove':[{'op':'remove','path':p+'/0'}],'move':[{'op':'move','from':p+'/1','path':p+'/0'}],'copy':[{'op':'copy','from':p+'/1','path':p+'/0'}],'replace':[{'op':'replace','path':p+'/0','value':b}],'ancestor_move':[{'op':'move','from':'/tracks/1','path':'/tracks/0'}],'unrelated':[{'op':'replace','path':'/title','value':'updated'}],'failed_atomic':[{'op':'replace','path':'/title','value':'updated'},{'op':'test','path':p+'/0/marker','value':'wrong'}],'field_conflict':[{'op':'replace','path':p+'/0/lyric','value':'different'}]}
store=ProjectStore(root); results={}; before=source.read_bytes()
for name,ops in cases.items():
 output=f'{run.name}-{name}.vpr'
 try:
  result=store.patch(str(source),ops,output); path=Path(result['path'])
  with zipfile.ZipFile(path) as z:
   out=json.loads(z.read(SEQUENCE_MEMBER)); side=json.loads(z.read(PHONEME_VALIDITY_MEMBER)); ref=side['Notes'][0]; track=out['tracks'][ref['TrackIndex']]; note=track['parts'][ref['PartIndex']]['notes'][ref['NoteIndex']]; resource=z.read('fixture-resource.txt').decode()
  results[name]={'status':'accepted','track':track['name'],'marker':note['marker'],'velocity':note['velocity'],'resource':resource,'output':str(path)}
 except Exception as e: results[name]={'status':'rejected','error':f'{type(e).__name__}: {e}','output_exists':(root/'output'/output).exists()}
assert source.read_bytes()==before
assert all(results[k]['status']=='accepted' and results[k]['marker']=='B' for k in ('insert','remove','move','copy','replace'))
assert results['ancestor_move']['track']=='B'
assert results['unrelated']['status']=='accepted' and results['test_field']['status']=='accepted'
assert all(results[k]['status']=='rejected' and not results[k]['output_exists'] for k in ('failed_atomic','field_conflict'))
(run/'receipt.json').write_text(json.dumps({'source':str(source),'source_unchanged':True,'results':results},indent=2),encoding='utf-8')
print(run/'receipt.json'); print(json.dumps(results,indent=2))
