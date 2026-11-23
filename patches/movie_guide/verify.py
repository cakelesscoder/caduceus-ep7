#!/usr/bin/env python3
"""movie_guide checks (#54; emulator, real code on the whole built image). Offline. Minimal + anti-brick.

  .venv/bin/python -I patches/movie_guide/verify.py <base spec, e.g. releases/v0.34a/edits.json> <spec with movie_guide> [package dir]

  G  guide labels: the real xp_guide (Effects 5 Sharp, 6 NR) and lu_guide (Colour & Light 9) with the real facade chain
     (lu_get -> xp_get -> ap_xg -> mv_get); stock GetValue stubbed (111 = Vivid in Movie, COLOR4 in stills; cursor 1686), the
     old chain mocked ("10 S", it records the cursor override). Movie (P2 swapped): override = old sector + 1, label renumbered
     ("5 S" / "6 S"), lu_guide's "Curve: COLOR 1-4". Stills: as the base. The base spec must fail the Movie cases.
  U  writes on the Movie wheel through the real GUI setter site 0x607fa355 (lu_set -> xp_set -> ap_xs -> mv_set -> ... ->
     manager, stubbed): Sharp / NR / VigFix change the Movie slot (P2 +224 +51 / +24 / +49) and set dirty; the stills-only
     rows Grain / Glow / Art / Halo write nothing. Stills COLOR4: all seven write.
  P  anti-brick: package = stock + edits, restore == stock, every main byte differing from the base is in this layer's
     9 bytes, the fw_version string or crash_log's version tag.
"""
import importlib.util, json, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'external/oly_fw_analysis/tools'))
import build_package as BP  # noqa: E402
import oly_container as oc  # noqa: E402


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(s)
    sys.modules[name] = m; s.loader.exec_module(m); return m


V = _load('ep7_v026_movie_verify_mg', ROOT / 'patches/v026_movie/verify.py')
Bd, Region, execute = V.Bd, V.Region, V.execute
BASE = 0x60020020
HANDLE, P_AT, P2_AT, SUB = V.HANDLE, V.P_AT, V.P2_AT, 687
OBJ, VIEW, CALLER = 0x1d000000, 0x1e000000, 0x18040000
SGET, MAN, SITE, GETV, FACADE = 0x602af887, 0x60827440, 0x607fa355, 0x607f9549, 0x607f9062
asm = lambda t, at: V.SB3.assemble(' .am33_2\n .text\n .global _start\n_start:\n' + t + '\n', at, {})[0]


def image(spec):
    m = bytearray(V.image(spec))
    put = lambda a, c: m.__setitem__(slice(a - BASE, a - BASE + len(c)), c)
    put(SGET, asm(' clr d0\n ret [],4', SGET))
    put(FACADE, asm(f' mov {OBJ:#x},a0\n ret [],4', FACADE))
    return m


def heap(swapped, sub, slot=bytes(64)):
    p, q = (bytearray(V.block(bytes(512), HANDLE, True)) for _ in range(2))
    q[224:288] = slot
    for b in (p, q):
        b[Bd.EM:Bd.EM + 4] = b'EP7E'; b[Bd.AXIS] = 4; b[SUB] = sub
    h = HANDLE + 0x800 if swapped else HANDLE
    return [Region('state', 0x622cbcc0, struct.pack('<HHI', 0, h, 0), 'r'),
            Region('pool', P_AT, bytes(p), 'rw', True), Region('pool2', P2_AT, bytes(q), 'rw', True)]


def data(im):
    lo, n = 0x61fc1000, 0x4000                          # .data from its init image (string tables), ALL flags off
    d = bytearray(im[lo - 0x01d67d40 - BASE:lo - 0x01d67d40 - BASE + n])
    d[0x2800:0x2808] = bytes(8)
    return bytes(d)


def guide(spec, im0, entry, cursor, sub, swapped):
    im = bytearray(im0)
    put = lambda a, c: im.__setitem__(slice(a - BASE, a - BASE + len(c)), c)
    pm = 0 if swapped else 64
    put(GETV, asm(f' cmp 1686,d0\n bne 1f\n mov {cursor},d1\n mov d1,(a1)\n clr d0\n rets\n1:\n cmp 111,d0\n bne 2f\n mov {pm},d1\n'
                  ' mov d1,(a1)\n clr d0\n rets\n2:\n clr d1\n mov d1,(a1)\n clr d0\n rets', GETV))
    blk = P2_AT if swapped else P_AT
    for at in (int(spec['extras_pages']['next']['ep7_guide_in'], 16), int(spec['look_hw_ui']['next']['ep7_guide_in'], 16)):
        put(at, asm(f' mov {blk + SUB:#x},a1\n movbu (a1),d0\n movbu d0,(120,a0)\n mov 5,d0\n movhu d0,(44,a0)\n'
                    ' mov 0x31,d0\n movhu d0,(52,a0)\n mov 0x30,d0\n movhu d0,(54,a0)\n mov 0x20,d0\n movhu d0,(56,a0)\n'
                    ' mov 0x53,d0\n movhu d0,(58,a0)\n clr d0\n movhu d0,(60,a0)\n mov 2,d0\n rets', at))
    c = asm(f' mov {entry:#x},a2\n mov {VIEW:#x},a0\n calls (a2)\n nop\n nop', CALLER)
    rg = [Region('img', BASE, bytes(im), 'rx'), Region('caller', CALLER, c + b'\xcb' * 8, 'rx'), *heap(swapped, sub),
          Region('data', 0x61fc1000, data(im), 'r'), Region('obj', OBJ, struct.pack('<I', 0x60acb0dc), 'r'),
          Region('view', VIEW, bytes(512), 'rw', True), Region('sect', 0xa272e420, struct.pack('<I', 0x1ff), 'r'),
          Region('lang', 0x61fb2000, bytes(0x3000), 'r'), Region('stack', 0x18010000, bytes(0x1000), 'rw')]
    r = execute(rg, dict(pc=CALLER, sp=0x18010800, d2=0x2222, d3=0x3333, a3=0xa3a3), CALLER + len(c) - 2, limit=200000)
    mem = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}
    v = mem['view']
    txt = ''.join(chr(u) for u in struct.unpack_from('<20H', v, 52)).split('\0')[0]
    rr = r['registers']
    kept = (rr['d2'], rr['d3'], rr['a3'], rr['sp']) == (0x2222, 0x3333, 0xa3a3, 0x18010800)
    left = mem['pool2' if swapped else 'pool'][SUB]
    return r['fault'], v[120], txt, kept, left


G_CASES = [  # name, symbol (layer, sym), cursor, sub, movie: (override, label)
    ('Effects 5 Sharp', ('extras_pages', 'xp_guide'), 5, 0, (0xa0, '5 S')),
    ('Effects 6 NR', ('extras_pages', 'xp_guide'), 6, 0, (0x90, '6 S')),
    ('Colour&Light 9 Curve', ('look_hw_ui', 'lu_guide'), 9, 1, (None, 'Curve: COLOR 1-4')),
]


def t_g(spec, im, base_spec, base_im):
    bad, n = [], 0
    for nm, (k, s), cur, sub, (ov, lbl) in G_CASES:
        for sw in (True, False):
            got = guide(spec, im, int(spec[k]['symbols'][s], 16), cur, sub, sw)
            ref = guide(base_spec, base_im, int(base_spec[k]['symbols'][s], 16), cur, sub, sw)
            n += 2
            if sw:
                ok = got[0] is None and got[2] == lbl and got[3] and got[4] == sub and (ov is None or got[1] == ov) and ref[2] != lbl
            else:
                ok = got[0] is None and got[1:] == ref[1:] and ref[0] is None
            if not ok:
                bad.append((nm, 'movie' if sw else 'stills', got, ref))
    return not bad, f'{n} runs; {bad[:3]}'


U_ROWS = [  # name, Effects sector (id 1655 + n - 1), value, slot byte, expect written in Movie
    ('Grain', 1, 2, 50, False), ('Glow', 2, -3, 60, False), ('Halo', 3, 2, 52, False), ('Art', 4, 1, 46, False),
    ('Sharp', 5, 1, 51, True), ('NR', 6, 1, 24, True), ('VigFix', 7, 1, 49, True),
]


def t_u(im):
    bad, n = [], 0
    for nm, sect, val, off, mv in U_ROWS:
        for sw in (True, False):
            rg = [Region('img', BASE, bytes(im), 'rx'), *heap(sw, 0), Region('all', 0x61fc3800, bytes(16), 'r'),
                  Region('stack', 0x18010000, bytes(0x1000), 'rw')]
            r = execute(rg, dict(pc=SITE, sp=0x18010800, d0=1654 + sect, d1=val & 0xffffffff, a0=0x1234, a1=0x5678, d2=1, d3=2, a2=3),
                        MAN, limit=20000)
            mem = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}
            blk = mem['pool2' if sw else 'pool']
            row = blk[224:288]
            wrote = any(row) or blk[Bd.DIRTY] == 1          # Art's stills write stops at lv_art_refresh's first manager call
            n += 1
            want = mv if sw else True
            if r['fault'] or r['registers']['pc'] != MAN or wrote != want or (want and nm == 'Sharp' and row[off] != 1):
                bad.append((nm, 'movie' if sw else 'stills', r['fault'], hex(r['registers']['pc']), [(i, row[i]) for i in range(64) if row[i]], blk[Bd.DIRTY]))
    return not bad, f'{n} runs (Movie: Sharp/NR/VigFix write, Grain/Glow/Halo/Art locked); {bad[:3]}'


def t_p(spec, base_spec, disk):
    stock = BP.STOCK.read_bytes()
    pkg, rst, info = BP.build(spec, stock)
    sb = {b.kind: b for b in oc.parse(stock)}
    good = True
    for b in oc.parse(pkg):
        exp = bytearray(sb[b.kind].payload)
        for e in spec['edits']:
            if int(e['kind'], 16) == b.kind:
                o = BP.resolve(b.kind, e['addr']); nb = bytes.fromhex(e['new']); exp[o:o + len(nb)] = nb
        good &= bytes(exp) == b.payload
    for b in oc.parse(rst):
        good &= b.payload == sb[b.kind].payload
    new = [b for b in oc.parse(pkg) if b.kind == 0x100][0].payload
    old = V.image(base_spec)
    mg, fw = spec['movie_guide'], spec['fw_version']
    ours = [(int(mg['scan_imm'], 16), 1), (int(mg['words'], 16), 8), (int(fw['str_at'], 16), 32), (int(fw['code_at'], 16), fw['code_len'])]
    F = _load('ep7_crash_fmt_mg', ROOT / 'tools/ep7_crash.py')          # crash_log's build tag (an imm32 of the version)
    t_old, t_new = (struct.pack('<I', F.build_tag(x['crash_log']['version'])) for x in (base_spec, spec))
    at = [i for i in range(len(new) - 3) if new[i:i + 4] == t_new and old[i:i + 4] == t_old]
    ours += [(BASE + i, 4) for i in at]
    diff = [BASE + i for i in range(len(old)) if old[i] != new[i]]
    stray = [hex(a) for a in diff if not any(s <= a < s + k for s, k in ours)]
    good &= not stray and sum(1 for a in diff if int(mg['words'], 16) <= a < int(mg['words'], 16) + 8 or a == int(mg['scan_imm'], 16)) == 9
    if disk:
        good &= (disk / 'patched.pkg.bin').read_bytes() == pkg and (disk / 'restore-stock.pkg.bin').read_bytes() == rst
    return good, f'{info["edits"]} edits, {info["changed_payload_bytes"]} B; {len(diff)} main B differ from base; stray {stray[:6]}'


def main():
    base_spec, spec = (json.loads(Path(p).read_text()) for p in sys.argv[1:3])
    disk = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    im, base_im = image(spec), image(base_spec)
    ok = True
    for tag, f in (('G', lambda: t_g(spec, im, base_spec, base_im)), ('U', lambda: t_u(im)), ('P', lambda: t_p(spec, base_spec, disk))):
        g, txt = f()
        print(f"{'PASS' if g else 'FAIL'} {tag} {txt}", flush=True)
        ok &= g
    print('ALL PASS' if ok else 'FAILURES')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
