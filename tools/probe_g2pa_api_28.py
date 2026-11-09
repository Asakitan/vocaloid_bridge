"""Extract previously decompiled editor G2PA API and default lyric pairs; read only."""
from pathlib import Path
import json, re
root = Path(__file__).resolve().parents[1] / '.runtime' / 'decompiled-audio'
def read(p): return (root / p).read_text(encoding='utf-8-sig')
def signatures(s): return [line.strip() for line in s.splitlines() if re.match(r'\s*public (?:static )?(?!class|enum)', line)]
defaults = read('Yamaha.VOCALOID/DefaultLyricManager.cs')
lists = {}
for name, body in re.findall(r'private static ReadOnlyCollection<DefaultLyrics> (\w+)DefaultLyrics.*?\{(.*?)\}\);', defaults, re.S):
    lists[name] = [{'lyric': a, 'phoneme': b} for a, b in re.findall(r'new DefaultLyrics\("([^"\n]*)", "([^"\n]*)"\)', body)]
print(json.dumps({'source':str(root), 'manager':signatures(read('Yamaha.VOCALOID.G2PA/G2PAManager.cs')), 'factory':signatures(read('Yamaha.VOCALOID.G2PA/G2PAManagerIF.cs')), 'editor_default_methods':signatures(defaults), 'editor_default_pairs':lists}, ensure_ascii=False, indent=2))
