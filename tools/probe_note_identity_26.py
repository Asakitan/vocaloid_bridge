"""Independent file-level identity experiment; no production modification."""
from copy import deepcopy
from pathlib import Path
import sys, json, tempfile, zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vocaloid_bridge.projects import _EDITOR_AI_NOTE, _NOTE_FIELDS, _merge, _validate_phoneme_validity, SEQUENCE_MEMBER
from vocaloid_bridge.music import _notes

def candidate(data, requests):
    old = data['tracks'][0]['parts'][0]['notes']
    allowed = {x['langID'] for x in data['tracks'][0]['parts'][0]['aiVoice']['langIDs']}
    used, out = set(), []
    for item in _notes(requests, monophonic=True):
        ref = item.get('source')
        if ref is None:
            native = deepcopy(_EDITOR_AI_NOTE)
        else:
            if not isinstance(ref, dict) or set(ref) != {'index', 'expected'}:
                raise ValueError('invalid selector')
            i = ref['index']
            if isinstance(i, bool) or not isinstance(i, int) or not 0 <= i < len(old) or i in used or ref['expected'] != old[i]:
                raise ValueError('stale or duplicate selector')
            used.add(i)
            native = deepcopy(old[i])
        raw = item.get('raw', {})
        if _NOTE_FIELDS.intersection(raw):
            raise ValueError('reserved field')
        _merge(native, raw)
        native.update(pos=item['_pos'], duration=item['_duration'], number=item['pitch'], lyric=item['lyric'], phoneme=item.get('phoneme', ''), velocity=item.get('velocity', native['velocity']), langID=item.get('lang_id', native['langID']))
        if native['langID'] not in allowed:
            raise ValueError('unavailable language')
        out.append(native)
    result = deepcopy(data)
    result['tracks'][0]['parts'][0]['notes'] = out
    return result

def error(fn):
    try: fn()
    except ValueError: return
    raise AssertionError('expected ValueError')

def main():
    a, b = deepcopy(_EDITOR_AI_NOTE), deepcopy(_EDITOR_AI_NOTE)
    a.update(pos=0, velocity=70, langID=0, marker={'owner': 'A', 'nested': {'keep': 1}})
    b.update(pos=0, velocity=90, langID=1, marker={'owner': 'B'})
    data = {'tracks': [{'type': 2, 'parts': [{'duration': 1440, 'aiVoice': {'langIDs': [{'langID': 0}, {'langID': 1}]}, 'notes': [a, b]}]}]}
    def req(start, source=None, **extra):
        item = {'start': start, 'duration': .5, 'pitch': 60, 'lyric': 'a', 'phoneme': 'a', **extra}
        if source is not None: item['source'] = {'index': source, 'expected': deepcopy(data['tracks'][0]['parts'][0]['notes'][source])}
        return item
    r = candidate(data, [req(2, 0, raw={'marker': {'nested': {'added': 2}}}), req(0, 1), req(1)])
    n = r['tracks'][0]['parts'][0]['notes']
    assert [(x['pos'], x.get('marker', {}).get('owner'), x['velocity'], x['langID']) for x in n] == [(0, 'B', 90, 1), (480, None, 64, 0), (960, 'A', 70, 0)]
    assert n[2]['marker']['nested'] == {'keep': 1, 'added': 2}
    assert len(candidate(data, [req(0, 1)])['tracks'][0]['parts'][0]['notes']) == 1
    error(lambda: candidate(data, [req(0, 0), req(1, 0)]))
    stale = req(0, 0); stale['source']['expected']['velocity'] = 71
    error(lambda: candidate(data, [stale]))
    error(lambda: candidate(data, [req(0, raw={'pos': 5})]))
    error(lambda: candidate(data, [req(0, lang_id=2)]))
    original = deepcopy(data); original['tracks'][0]['parts'][0]['notes'] = [a]
    validity = {'Format': 'vocaloid-bridge-phoneme-validity', 'Version': 1, 'Notes': [{'TrackIndex': 0, 'PartIndex': 0, 'NoteIndex': 0, 'Note': {'IsValid': False, 'Position': a['pos'], 'Duration': a['duration'], 'Number': a['number'], 'Lyric': a['lyric'], 'Phonemes': a['phoneme'], 'LanguageId': a['langID']}}]}
    payload = json.dumps(validity).encode()
    _validate_phoneme_validity(original, payload)
    error(lambda: _validate_phoneme_validity(r, payload))
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / 'synthetic.vpr'
        with zipfile.ZipFile(path, 'w') as z: z.writestr(SEQUENCE_MEMBER, json.dumps(r))
        with zipfile.ZipFile(path) as z: assert json.loads(z.read(SEQUENCE_MEMBER)) == r
    print('PASS: snapshot identity, defaults, merge, ambiguity and sidecar conflict')
if __name__ == '__main__': main()
