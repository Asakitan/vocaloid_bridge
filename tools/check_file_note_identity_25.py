"""Historical red probe for an unadopted tick-identity policy; not a release gate."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vocaloid_bridge.projects import ProjectStore, _EDITOR_AI_NOTE, SEQUENCE_MEMBER

def main():
    with tempfile.TemporaryDirectory(prefix='file-notes-25-') as directory:
        root = Path(directory)
        a, b = deepcopy(_EDITOR_AI_NOTE), deepcopy(_EDITOR_AI_NOTE)
        a.update(pos=0, duration=240, number=60, velocity=70, langID=0, x_identity_25={'owner': 'A'})
        b.update(pos=480, duration=240, number=62, velocity=90, langID=1, x_identity_25={'owner': 'B'})
        sequence = {'tracks': [{'type': 2, 'parts': [{'duration': 1440, 'aiVoice': {'compID': 'synthetic', 'langIDs': [{'langID': 0}, {'langID': 1}]}, 'notes': [a, b]}]}]}
        source = root / 'synthetic.vpr'
        with zipfile.ZipFile(source, 'w') as archive:
            archive.writestr(SEQUENCE_MEMBER, json.dumps(sequence))
            archive.writestr('synthetic-resource.bin', b'fixture')
        before = source.read_bytes()
        notes = [{'start': 2, 'duration': .5, 'pitch': 64, 'lyric': 'u', 'phoneme': 'u', 'lang_id': 0}, {'start': 1, 'duration': .5, 'pitch': 63, 'lyric': 'i', 'phoneme': 'i', 'lang_id': 1}, {'start': 0, 'duration': .5, 'pitch': 60, 'lyric': 'a', 'phoneme': 'a', 'lang_id': 0}]
        store = ProjectStore(root)
        output = Path(store.edit_notes(str(source), 'result.vpr', notes)['path'])
        result = store.read(output)['tracks'][0]['parts'][0]['notes']
        actual = [(n['pos'], n.get('x_identity_25'), n['velocity'], n['langID'], n['phoneme']) for n in result]
        expected = [(0, {'owner': 'A'}), (480, {'owner': 'B'}), (960, None)]
        assert source.read_bytes() == before
        with zipfile.ZipFile(output) as archive:
            assert archive.read('synthetic-resource.bin') == b'fixture'
        print('actual:', json.dumps(actual, ensure_ascii=False))
        print('candidate tick-policy expected:', json.dumps(expected))
        if [(n['pos'], n.get('x_identity_25')) for n in result] != expected:
            print('RED: retained B lost identity; new note inherited A')
            return 1
        print('PASS: candidate tick-policy markers')
        return 0
if __name__ == '__main__':
    raise SystemExit(main())
