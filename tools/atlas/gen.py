import json, re, struct, os
here = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(here, 'atlas_data.py')).read())
import glob
for _f in sorted(glob.glob(os.path.join(here, 'new_*.py'))):  # round outputs (docs/RE_ROUNDS.md)
    exec(open(_f).read())
REPO = os.path.abspath(os.path.join(here, '..', '..'))
d = open(REPO + '/analysis/ep7_1100/00_0100_406a0020.decoded.bin', 'rb').read()
B = 0x60020020
# task tables from bytes
names = {}
p = 0x613ff240 - B
while True:
    nm = d[p:p+24].split(b'\0')[0]
    if not re.fullmatch(rb'[A-Z0-9_]{2,23}', nm): break
    names[struct.unpack_from('<H', d, p+24)[0]] = nm.decode(); p += 26
tasks = []
for tid in sorted(names):
    w = struct.unpack_from('<7I', d, 0x600389d0 + tid*28 - B)
    tasks.append((tid, names[tid], w[3], w[4], w[5]) if w[0] == tid else (tid, names[tid], None, None, None))
have = {e['addr'] for e in S}
syms = [dict(e) for e in S]
for tid, nm, ent, pr, st in tasks:
    if ent and ent not in have:
        syms.append(dict(addr=ent, name='task_' + nm, kind='func', subsystem='rtos', confidence='V',
                         sig='task %d entry' % tid, notes='prio %d, stack 0x%x' % (pr, st),
                         source='docs/ATLAS.md §2.1 (descriptor 0x600389d0)'))
        have.add(ent)
syms.sort(key=lambda e: e['addr'])
out = []
for e in syms:
    e = dict(e); e['addr'] = '0x%08x' % e['addr']; out.append(e)
meta = dict(firmware='Olympus PEN E-P7 1.1 (build 1100), main component 0x100', cpu_base='0x60020020',
            generated='2026-11-12', confidence={'V': 'code/bytes/emulator', 'C': 'camera-proven', 'I': 'inference'},
            note='Stock symbols only; Caduceus code-space claims are in docs/CODE_SPACE_MAP.md. Human-readable: docs/ATLAS.md',
            symbols=out)
json.dump(meta, open(REPO + '/docs/atlas.json', 'w'), indent=1, ensure_ascii=False)
open(REPO + '/docs/atlas.json', 'a').write('\n')

def esc(s): return s.replace('|', '\\|')
def table(sub):
    rows = [e for e in S if e['subsystem'] == sub]
    rows.sort(key=lambda e: e['addr'])
    L = ['| Address | Name | Kind | Tag | Signature / layout | Notes | Source |', '|---|---|---|---|---|---|---|']
    for e in rows:
        L.append('| `0x%08x` | %s | %s | %s | %s | %s | %s |' % (e['addr'], esc(e['name']), e['kind'], e['confidence'],
                 esc(e['sig']), esc(e['notes']), esc(e['source'])))
    return '\n'.join(L)
def tasktab():
    L = ['| Id | Task | Entry | Prio | Stack | Id | Task | Entry | Prio | Stack |', '|---:|---|---|---:|---:|---:|---|---|---:|---:|']
    half = (len(tasks) + 1) // 2
    def cell(t):
        tid, nm, ent, pr, st = t
        if ent is None: return '%d | %s | – | – | –' % (tid, nm)
        return '%d | %s | `0x%08x` | %d | 0x%x' % (tid, nm, ent, pr, st)
    for i in range(half):
        a = cell(tasks[i]); b = cell(tasks[i+half]) if i + half < len(tasks) else ' | | | | '
        L.append('| %s | %s |' % (a, b))
    return '\n'.join(L)
t = open(os.path.join(here, 'ATLAS.tmpl.md')).read()
t = re.sub(r'\{\{TABLE:(\w+)\}\}', lambda m: table(m.group(1)), t)
t = t.replace('{{TASKS}}', tasktab()).replace('{{NSYM}}', str(len(out))).replace('{{NTASK}}', str(sum(1 for x in tasks if x[2])))
assert '{{' not in t
open(REPO + '/docs/ATLAS.md', 'w').write(t)
import collections
print(len(out), collections.Counter(e['subsystem'] for e in out))
