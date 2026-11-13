#!/usr/bin/env python3
"""split_tone checks (emulator, real code from the built package, v0.31d vs the new build). Offline. Minimal + anti-brick,
plus the boot-path no-op (the tone hook runs on every live-view pass from the first frame).

  .venv/bin/python -I patches/split_tone/verify.py releases/v0.31d/edits.json generated/v032/edits.json [generated/v032/rel]

Run: from the hook 0x603b14ff (the v0.19 `call tone`) to tone's entry 0x601e103c, real sec-1 / sec-2 tail / sec-4/5/7 code
(st, ap_P, tbl_idx -> ap_tx), mocks for the property getter 0x6005e971 (by key), malloc / free. Stock gamma row 0
0x604ede78 is the source curve. Fixture: job / request / record (the tone job guard), context C, output O, heap P, block S.
  N  no-op: no card table (handle 0 / bad / wrong magic): registers, flags, stack above sp and every fixture byte == v0.31d.
     Card table, slot +62/+63 = 0: the same, and no malloc.
  C  capture COLOR1 +62 0x58 (Cyan +5) / +63 0x51 (Orange +5): O+2596/2600/2604 -> S set 0 R/G/B, the three curves ==
     the Python model of the OM-3 integer bend (t clamp) bit for bit, all differ, C+108 bit 0 set, S tagged, P+848 = S,
     registers / stack == v0.31d at tone's entry. Repeat pass from that state stores nothing. A new word rebuilds set 0.
     Split back to 0 with our curve in the slots: base in all three + C+108 bit 0.
  L  live view (no capture marker): getter 0xF6B1 = 1 -> set 1; = 0 (movie / AP Vivid) -> stock.
  G  gates: invalid fields (colour 12, strength +-6) = off; COLOR profile 5 (MONO) and 0; gamma off (O+4 bit 12); R != G
     (three-curve art keys); key != 11; malloc failure: all == v0.31d.
  P  anti-brick: package decodes to stock + edits, restore == stock, bytes differing from v0.31d only inside this build's
     edits (scp_name, split_tone, lv_grid, fw_version), OSD component == stock + its edits.
"""
import json, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'external/oly_fw_analysis/tools'))
import build_package as BP  # noqa: E402
import oly_container as oc  # noqa: E402
from penf_emulator import Region, execute  # noqa: E402
import importlib.util  # noqa: E402


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


SB3 = _load('ep7_sdb3_stv', ROOT / 'patches/sd_bundles_v3/build.py')
STB = _load('ep7_st_build_v', ROOT / 'patches/split_tone/build.py')
BASE, HOOK, TONE = 0x60020020, 0x603b14ff, 0x601e103c
ROW0 = 0x604ede78
STACK, SP0, FILL = 0x18010000, 0x18011800, 0xa5
POOL, HANDLE = 0xa1f8d800, 0x41
P = POOL + HANDLE - 1
SBLK = 0xa1dd8d40 + 0x4040 * 5
J = 0x13000000
R = J + 11364
C, O = 0x13010000, 0x13020000
KEEP = ('d0', 'd1', 'd2', 'd3', 'a0', 'a1', 'a2', 'a3', 'sp', 'pc', 'mdr', 'lir', 'lar')   # psw: dead at a function entry (tone starts with movm)
ST_K = STB.ST_K


def image(spec):
    pkg, rst, info = BP.build(spec, BP.STOCK.read_bytes())
    return {b.kind: b.payload for b in oc.parse(pkg)}, pkg, rst, info


def mocks(prof, malloc_ok):
    src = f""" .am33_2
 .text
 .global _start
_start:
getter:                           /* call ..,[d2,d3],12 */
 cmp 0xf6b1,d0
 bne 1f
 mov {prof},d0
 ret [d2,d3],12
1:
 clr d0
 ret [d2,d3],12
 .balign 16
malloc:                           /* call ..,[],4 */
 mov {SBLK if malloc_ok else 0:#x},a0
 ret [],4
 .balign 16
free:
 ret [],4
"""
    code, _, s, _ = SB3.assemble(src, 0x13100000, {})
    return code, s


def bend(src, sh, hl):
    def field(b):
        c, st = b & 15, (b >> 4) & 15
        st = st - 16 if st >= 8 else st
        return (c, st) if c < 12 and st != 0 and -5 <= st <= 5 else (0, 0)
    (cs, ss), (ch, sh2) = field(sh), field(hl)
    out = []
    for c in range(3):
        ks, kh = ST_K[cs][c] * ss, ST_K[ch][c] * sh2
        cur, mx = [], 0
        for t in src:
            t = min(t, 4095)
            s = 4095 - t
            ws = ((t * s >> 12) * s) >> 12
            wh = ((t * t >> 12) * s) >> 12
            v = t + ((ks * ws + kh * wh) >> 8)
            v = max(0, min(4095, v))
            mx = max(mx, v)
            cur.append(mx)
        out.append(cur)
    return out


def fixture(slots=None, handle=HANDLE, magic=b'EP7B', marker=True, profile=1, key=0x000b0000, ptrs=None, o4=0, c108=0x10,
            S=None, pextra=None):
    p = bytearray(1024); p[0:4] = magic
    for k, (a, b) in (slots or {}).items():
        p[32 + 64 * k + 62] = a; p[32 + 64 * k + 63] = b
    if pextra:
        for off, v in pextra.items():
            struct.pack_into('<I', p, off, v)
    j = bytearray(15512)
    struct.pack_into('<III', j, 11364, 0x60355fd4, J + 14576, key)
    struct.pack_into('<I', j, 14576, J)
    if marker:
        j[15488], j[15489], j[15490] = profile, 11, 0xB2
    c = bytearray(256); struct.pack_into('<I', c, 4, R); struct.pack_into('<I', c, 12, O); struct.pack_into('<I', c, 108, c108)
    o = bytearray(2624); struct.pack_into('<I', o, 4, o4)
    struct.pack_into('<III', o, 2596, *(ptrs or (ROW0, ROW0, ROW0)))
    return dict(p=bytes(p), j=bytes(j), c=bytes(c), o=bytes(o), s=S or bytes(4096), state=struct.pack('<HHI', 0, handle, 0))


def run(main, fx, prof=1, malloc_ok=True):
    sl = lambda lo, hi: main[lo - BASE:hi - BASE]
    mk, ms = mocks(prof, malloc_ok)
    rg = [Region('hook', 0x603b14e0, sl(0x603b14e0, 0x603b1520), 'rx'),
          Region('sec1', 0x601de000, sl(0x601de000, 0x601e4000), 'rx'),
          Region('tbl', 0x60210900, sl(0x60210900, 0x60211000), 'rx'),
          Region('sec2', 0x6055e5b0, sl(0x6055e5b0, 0x6055e800), 'rx'),
          Region('sec4', 0x60747f00, sl(0x60747f00, 0x60748000), 'rx'),
          Region('sec5', 0x60b9de00, sl(0x60b9de00, 0x60b9e000), 'rx'),
          Region('sec7', 0x61378e00, sl(0x61378e00, 0x61379000), 'rx'),
          Region('row0', ROW0, sl(ROW0, ROW0 + 1024), 'r'),
          Region('getter', 0x6005e971, b'\xdc' + struct.pack('<i', ms['getter'] - 0x6005e971), 'rx'),
          Region('malloc', 0x60022782, b'\xdc' + struct.pack('<i', ms['malloc'] - 0x60022782), 'rx'),
          Region('free', 0x600227b4, b'\xdc' + struct.pack('<i', ms['free'] - 0x600227b4), 'rx'),
          Region('mocks', 0x13100000, mk, 'rx'),
          Region('state', 0x622cbcc0, fx['state'], 'r'),
          Region('pool', P, fx['p'], 'rw', True),
          Region('S', SBLK, fx['s'], 'rw', True),
          Region('job', J, fx['j'], 'rw', True),
          Region('C', C, fx['c'], 'rw', True),
          Region('O', O, fx['o'], 'rw', True),
          Region('stack', STACK, bytes([FILL] * 0x2000), 'rw', True)]
    r = execute(rg, dict(pc=HOOK, sp=SP0, d3=C, a0=C, d0=0xd0d0, d1=0xd1d1, d2=0x2222, a1=0xa1a1, a2=0xa2a2, a3=0xa3a3, mdr=0x6d6d),
                TONE, limit=400000)
    return r, {m['name']: bytes.fromhex(m['hex']) for m in r['memory']}


def same(base, new, fx, **kw):
    r0, m0 = run(base, fx, **kw)
    r1, m1 = run(new, fx, **kw)
    g0, g1 = r0['registers'], r1['registers']
    sp = g1['sp'] - STACK
    ok = not r0['fault'] and not r1['fault'] and g0['pc'] == TONE == g1['pc'] and all(g0[k] == g1[k] for k in KEEP)
    ok &= m0['stack'][sp:] == m1['stack'][sp:] and all(m0[k] == m1[k] for k in ('pool', 'S', 'job', 'C', 'O'))
    return ok, (r1, m1), (r0, m0)


def regs_ok(r0, r1):
    g0, g1 = r0[0]['registers'], r1[0]['registers']
    sp = g1['sp'] - STACK
    return (not r1[0]['fault'] and g1['pc'] == TONE and all(g0[k] == g1[k] for k in KEEP)
            and r0[1]['stack'][sp:] == r1[1]['stack'][sp:])


def slots_of(m):
    return struct.unpack_from('<III', m['O'], 2596)


def curves(m, base_addr):
    off = base_addr - SBLK
    return [list(struct.unpack_from('<256H', m['S'], off + 512 * c)) for c in range(3)]


def state_from(m, fx):
    return dict(fx, p=m['pool'], s=m['S'], c=m['C'], o=m['O'], j=m['job'])


def t_n(base, new):
    bad, n = [], 0
    for fx in (fixture(handle=0), fixture(handle=0xffff), fixture(handle=HANDLE + 2), fixture(magic=b'EP7Q'),
               fixture(), fixture(marker=False), fixture(slots={1: (0x58, 0x51)})):
        for prof in (0, 1):
            ok, (r1, m1), _ = same(base, new, fx, prof=prof)
            n += 1
            if not ok:
                bad.append((n, r1['fault'], r1['registers']['pc']))
    return not bad, f'{n} cases (no table, table with split 0, split on another slot); bad {bad[:3]}'


def t_c(base, new):
    src = list(struct.unpack_from('<256H', new, ROW0 - BASE))
    info, ok = [], True
    fx = fixture(slots={0: (0x58, 0x51)})
    r0 = run(base, fx)
    r1 = run(new, fx)
    m = r1[1]
    sl = slots_of(m)
    s0 = SBLK + 32                    # set 0 R (S+16 set, +16 R)
    want = bend(src, 0x58, 0x51)
    got = curves(m, s0)
    ok &= regs_ok(r0, r1) and sl == (s0, s0 + 512, s0 + 1024)
    ok &= got == want and len({tuple(x) for x in got}) == 3 and got[1] != src
    ok &= struct.unpack_from('<I', m['C'], 108)[0] == 0x11 and m['S'][0:4] == b'EP7S' and struct.unpack_from('<I', m['S'], 4)[0] == P
    ok &= struct.unpack_from('<I', m['pool'], 848)[0] == SBLK
    info.append(f'bend {"==" if got == want else "!="} model, max |dR| {max(abs(a - b) for a, b in zip(got[0], src))}')
    # repeat pass: nothing stored
    fx2 = state_from(m, fx)
    r2 = run(new, fx2)
    ok &= regs_ok(r0, r2) and all(r2[1][k] == fx2[{'pool': 'p', 'S': 's', 'job': 'j', 'C': 'c', 'O': 'o'}[k]] for k in ('pool', 'S', 'job', 'C', 'O'))
    # new word -> rebuild set 0
    p3 = bytearray(m['pool']); p3[32 + 62], p3[32 + 63] = 0x26, 0x13
    fx3 = dict(fx2, p=bytes(p3), c=fx['c'])
    r3 = run(new, fx3)
    ok &= regs_ok(r0, r3) and slots_of(r3[1]) == (s0, s0 + 512, s0 + 1024) and curves(r3[1], s0) == bend(src, 0x26, 0x13)
    ok &= struct.unpack_from('<I', r3[1]['C'], 108)[0] & 1 == 1
    # split back to 0 with our curve in the slots -> base again
    p4 = bytearray(m['pool']); p4[32 + 62] = p4[32 + 63] = 0
    fx4 = dict(fx2, p=bytes(p4), c=fx['c'])
    r4 = run(new, fx4)
    ok &= regs_ok(r0, r4) and slots_of(r4[1]) == (ROW0, ROW0, ROW0) and struct.unpack_from('<I', r4[1]['C'], 108)[0] & 1 == 1
    return ok, '; '.join(info) + ', repeat stores nothing, rebuild on a new word, restore on 0'


def t_l(base, new):
    src = list(struct.unpack_from('<256H', new, ROW0 - BASE))
    fx = fixture(slots={0: (0x58, 0x51)}, marker=False)
    r0 = run(base, fx, prof=1)
    r1 = run(new, fx, prof=1)
    s1 = SBLK + 32 + 1552
    ok = regs_ok(r0, r1) and slots_of(r1[1]) == (s1, s1 + 512, s1 + 1024) and curves(r1[1], s1) == bend(src, 0x58, 0x51)
    okm, _, _ = same(base, new, fx, prof=0)
    return ok and okm, 'live view -> set 1; getter 0 (movie / AP Vivid) -> stock'


def t_g(base, new):
    bad, n = [], 0
    cases = [(fixture(slots={0: (0x5c, 0x61)}), {}), (fixture(slots={0: (0x58, 0x51)}, profile=5), {}),
             (fixture(slots={0: (0x58, 0x51)}, profile=0), {}), (fixture(slots={0: (0x58, 0x51)}, o4=0x1000), {}),
             (fixture(slots={0: (0x58, 0x51)}, ptrs=(ROW0, ROW0 + 512, ROW0)), {}), (fixture(slots={0: (0x58, 0x51)}, key=0x01010079), {}),
             (fixture(slots={0: (0x58, 0x51)}), dict(malloc_ok=False))]
    for fx, kw in cases:
        ok, (r1, _), _ = same(base, new, fx, **kw)
        n += 1
        if not ok:
            bad.append((n, r1['fault']))
    return not bad, f'{n} gate cases == v0.31d; bad {bad}'


def t_pkg(base_s, new_s, base, new_p, pkg, rst, disk):
    sb = {b.kind: b for b in oc.parse(BP.STOCK.read_bytes())}
    good = True
    for b in oc.parse(pkg):
        exp = bytearray(sb[b.kind].payload)
        for e in new_s['edits']:
            if int(e['kind'], 16) == b.kind:
                o = BP.resolve(b.kind, e['addr']); nb = bytes.fromhex(e['new']); exp[o:o + len(nb)] = nb
        good &= bytes(exp) == b.payload
    for b in oc.parse(rst):
        good &= b.payload == sb[b.kind].payload
    srcs = {'patches/scp_name', 'patches/split_tone', 'patches/lv_grid', 'patches/fw_version'}
    ours = [(int(e['addr'], 16), len(e['new']) // 2) for e in base_s['edits'] if e.get('source') == 'patches/fw_version'] + \
        [(int(e['addr'], 16), len(e['new']) // 2) for e in new_s['edits']
            if e['kind'] == '0x100' and not e['addr'].startswith('off:') and (e.get('source') in srcs or '[split_tone' in e['why'])]
    nm, bm = new_p[0x100], base[0x100]
    diff = [BASE + i for i in range(len(bm)) if bm[i] != nm[i]]
    stray = [hex(a) for a in diff if not any(s_ <= a < s_ + k for s_, k in ours)]
    good &= not stray
    if disk:
        good &= (disk / 'patched.pkg.bin').read_bytes() == pkg and (disk / 'restore-stock.pkg.bin').read_bytes() == rst
    return good, f'{len(new_s["edits"])} edits; main {len(diff)} B differ from v0.31d; stray {stray[:6]}; restore == stock'


def main():
    base_s, new_s = (json.loads(Path(p).read_text()) for p in sys.argv[1:3])
    disk = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    bp, *_ = image(base_s)
    np_, pkg, rst, info = image(new_s)
    base, new = bp[0x100], np_[0x100]
    ok = True
    for tag, f in (('N', lambda: t_n(base, new)), ('C', lambda: t_c(base, new)), ('L', lambda: t_l(base, new)),
                   ('G', lambda: t_g(base, new)), ('P', lambda: t_pkg(base_s, new_s, bp, np_, pkg, rst, disk))):
        g, txt = f()
        print(f"{'PASS' if g else 'FAIL'} {tag} {txt}", flush=True)
        ok &= g
    print('ALL PASS' if ok else 'FAILURES')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
