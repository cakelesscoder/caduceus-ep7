#!/usr/bin/env python3
"""Emulator checks for recview r1 (real firmware code from the decoded package). Offline. Minimal + anti-brick.

  .venv/bin/python -I patches/recview/verify.py releases/v0.30/edits.json generated/recview/edits.json [generated/recview/rel]

  R  converter flag code 0x603eabd7 -> 0x603eabdd (gc_flag -> bloom_flag -> Art stub -> rv_gate) on v0.30 vs r1 vs stock:
     key-11 bloom / clarity / Star Light / grain+Art flags are cleared exactly on capture kinds the stock mapper 0x603ea909 types
     0x1xx (0x2001 / 0x2006), and the result then equals stock; type 0x1000 / 0 jobs, other keys, plain looks and a missing
     source == v0.30. Registers, sp, MDR and the Z flag at the resume point == v0.30.
  G  (r2, patches/grain_kind) gc_flag with a heap block and the SD look table, v0.30 vs r2, every kind: the pending grain level
     handed to gc_wl (block +95) == v0.30 in every case (the photo job's grain is decided by it); grain + Art Effect keeps
     forced 0x80 on type-0x1000 kinds; guards 05..08 fire on 0x2001 / 0x2006 / 0x1008 / 0x1006 only when the forced branch
     runs and the mapped type is not 0x1000; record +58 = the source Mode.
  P  anti-brick: package decodes to stock + edits (the image R ran), restore == stock, bytes differing from v0.30 are only
     the rv_gate block, the bloom tail jmp and the fw_version label.
"""
import json, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'external/oly_fw_analysis/tools'))
import build_package as BP  # noqa: E402
import oly_container as oc  # noqa: E402
from penf_emulator import Region, execute  # noqa: E402

BASE = 0x60020020
FLAG_SITE, FLAG_RET = 0x603eabd7, 0x603eabdd
STK, CAP, PAR, SRCR = 0x18010000, 0x1e000000, 0x1d000000, 0x1c000000
SF_KEY = 0x01010065
REGS0 = {'d2': 0x2222, 'd3': 0x3333}


def image(spec):
    pkg, rst, info = BP.build(spec, BP.STOCK.read_bytes())
    return [b for b in oc.parse(pkg) if b.kind == 0x100][0].payload, pkg, rst, info


def table(slots):
    """slots: {slot: (effect, strength, art, grain)}."""
    t = bytearray(8 * 64)
    for i, (eff, st, art, gr) in slots.items():
        t[i * 64 + 28], t[i * 64 + 29], t[i * 64 + 46], t[i * 64 + 50] = eff, st, art, gr
    return bytes(t)


TABLE = table({0: (1, 3, 0, 0), 1: (3, 3, 0, 0), 2: (0, 0, 0, 0), 3: (0, 0, 1, 0)})          # bloom, clarity, plain, Star Light
TABLE_G = table({0: (1, 3, 0, 2), 1: (0, 0, 2, 2), 2: (0, 0, 0, 2), 3: (0, 0, 1, 2)})        # + grain: bloom, Pin Hole, plain, Star Light


def run(im, key, mode, prof, kind, src, t, ed45=False, has_src=True, flags=0x80000):
    cap = bytearray(27300)
    cap[24053], cap[24083] = mode, prof
    if ed45:
        cap[27285] = 1
    s = bytearray(300)
    struct.pack_into('<I', s, 28, CAP)
    struct.pack_into('<H', s, 194, kind)
    struct.pack_into('<H', s, 206, src)
    struct.pack_into('<H', s, 262, 0x2000 if ed45 else 0)
    par = bytearray(32)
    struct.pack_into('<I', par, 4, SRCR if has_src else 0)
    par[8:12] = bytes(((key >> 24) & 255, (key >> 16) & 255)) + struct.pack('<H', key & 0xffff)
    struct.pack_into('<I', par, 12, flags)
    q = bytearray(im)
    q[0x60210900 - BASE:0x60210900 - BASE + len(t)] = t
    q = bytes(q)
    sl = lambda lo, hi, n: Region(n, lo, q[lo - BASE:hi - BASE], 'rx')
    rg = [sl(0x601de000, 0x601e4000, 'blk'), sl(0x60210000, 0x60211000, 'sec1'), sl(0x603ea900, 0x603ed600, 'conv'), sl(0x6055e000, 0x6055f000, 'sec2'),
          Region('stk', STK, bytes(0x4000), 'rw', True), Region('cap', CAP, bytes(cap), 'rw', True), Region('src', SRCR, bytes(s), 'r'),
          Region('par', PAR, bytes(par), 'rw', True), Region('st', 0x622cbcc0, bytes(8), 'r')]
    r = execute(rg, {'pc': FLAG_SITE, 'sp': STK + 0x3000, 'a2': PAR + 12, 'a3': CAP, 'mdr': 0x603e6161, **REGS0}, FLAG_RET, limit=6000)
    m = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}
    rr = r['registers']
    ctx = (rr['d2'], rr['d3'], rr['a2'], rr['a3'], rr['sp'], rr['mdr'], rr['psw'] & 0xf)   # Z N C V
    return (not r['fault'] and rr['pc'] == FLAG_RET), struct.unpack_from('<I', m['par'], 12)[0], ctx, m['cap'] == bytes(cap)


# (kind, src, ed45) -> stock type 0x603ea909
KINDS = [(0x1001, 1, False, 0x1000), (0x100a, 1, False, 0x1000), (0x2001, 1, False, 0x110), (0x2006, 2, False, 0x120), (0x2006, 1, False, 0x110),
         (0x2001, 1, True, 0x1000), (0x1006, 1, False, 0), (0x1008, 2, False, 0)]


def t_gate(stock, base, new, gk=False):
    bad, rows, n, n_strip = [], [], 0, 0
    cases = []
    for t, tn in ((TABLE, 'T'), (TABLE_G, 'G')):
        for prof in (1, 2, 3, 4):
            for kind, src, ed45, ty in KINDS:
                cases.append((t, tn, 11, 11, prof, kind, src, ed45, ty, True))
    for kind, src, ed45, ty in KINDS[:4]:
        cases += [(TABLE, 'T', 12, 12, 1, kind, src, ed45, ty, True), (TABLE, 'T', SF_KEY, 11, 1, kind, src, ed45, ty, True),
                  (TABLE, 'T', 11, 12, 1, kind, src, ed45, ty, True), (TABLE, 'T', 11, 11, 1, kind, src, ed45, ty, False),
                  (TABLE, 'T', 11, 11, 0, kind, src, ed45, ty, True)]
    for t, tn, key, mode, prof, kind, src, ed45, ty, hs in cases:
        rs, rb, rn = (run(im, key, mode, prof, kind, src, t, ed45, hs) for im in (stock, base, new))
        strip = key == 11 and hs and (ty & 0xf00 == 0x100 or ty & 0xf0 == 0x40) and bool(rb[1] & 0xc0)
        want = rb[1] & ~0xc0 if strip else rb[1]
        if gk and tn == 'G' and key == 11 and mode == 11 and hs and prof in (2, 4) and kind in (0x1006, 0x1008):
            want = rb[1] & ~0x80                                # grain_kind: no forced 0x80 on type-0 kinds (guards 07/08)
        good = rs[0] and rb[0] and rn[0] and rn[1] == want and rn[2] == rb[2] and rn[3]
        if strip:
            n_strip += 1
            good &= rn[1] == (rs[1] | (rb[1] & 0x400))          # back to stock flags (Pin Hole is not stripped, as stock)
        if not ((rb[1] ^ rs[1]) & 0xc0) and key == 11 and want == rb[1]:
            good &= rn[1] == rb[1]                              # plain looks: == v0.30
        n += 1
        if not good:
            bad.append((tn, hex(key), mode, prof, hex(kind), src, ed45, hs, hex(rs[1]), hex(rb[1]), hex(rn[1]), rb[2] == rn[2]))
        if tn == 'T' and key == 11 and mode == 11 and hs and prof in (1, 2, 3) and kind in (0x1001, 0x2001, 0x2006) and not ed45:
            rows.append(f'COLOR{prof} kind {kind:#06x} src {src} type {ty:#06x}: stock {rs[1]:#x} v0.30 {rb[1]:#x} r1 {rn[1]:#x}')
    if n_strip == 0:
        bad.append('no strip case')
    return bad, n, rows


def g_run(im, kind, src, ed45, grain, art, eff=0):
    GS = _gs()
    cap = bytearray(27300); cap[24053], cap[24083] = 11, 2
    if ed45:
        cap[27285] = 1
    s = bytearray(300)
    struct.pack_into('<I', s, 28, CAP); struct.pack_into('<H', s, 194, kind); struct.pack_into('<H', s, 206, src)
    struct.pack_into('<H', s, 262, 0x2000 if ed45 else 0)
    par = bytearray(32); struct.pack_into('<I', par, 4, SRCR); struct.pack_into('<H', par, 10, 11); struct.pack_into('<I', par, 12, 0x80000)
    pr = GS.pool_regions(9)
    pp = bytearray(pr[0].data); pp[32:32 + 512] = GS.slot_table((0, grain, 0, 0), art=art, effect=eff, strength=3 if eff else 0)
    sl = lambda lo, hi, n: Region(n, lo, im[lo - BASE:hi - BASE], 'rx')
    rg = [sl(0x601de000, 0x601e4000, 'blk'), sl(0x60210000, 0x60211000, 'sec1'), sl(0x603ea900, 0x603ed600, 'conv'), sl(0x6055e000, 0x6055f000, 'sec2'),
          Region('stk', STK, bytes(0x4000), 'rw', True), Region('cap', CAP, bytes(cap), 'rw', True), Region('src', SRCR, bytes(s), 'r'),
          Region('par', PAR, bytes(par), 'rw', True), Region('pool', pr[0].address, bytes(pp), 'rw', True), pr[1], pr[2]]
    r = execute(rg, {'pc': FLAG_SITE, 'sp': STK + 0x3000, 'a2': PAR + 12, 'a3': CAP, **REGS0}, FLAG_RET, limit=8000)
    m = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}
    rr = r['registers']
    b = m['heapu']
    return (not r['fault'] and rr['pc'] == FLAG_RET and rr['d2'] == 0x2222 and rr['d3'] == 0x3333 and rr['a2'] == PAR + 12 and rr['a3'] == CAP and rr['sp'] == STK + 0x3000,
            struct.unpack_from('<I', m['par'], 12)[0], b[95], b[4], struct.unpack_from('<H', b, 58)[0])


_GS = []


def _gs():
    if not _GS:
        import importlib.util as u
        sp_ = u.spec_from_file_location('gc_verify_s1', ROOT / 'patches/grain_cpu/verify_s1.py'); m = u.module_from_spec(sp_); sp_.loader.exec_module(m)
        _GS.append(m)
    return _GS[0]


def t_grain(base, new):
    bad, n, fired = [], 0, set()
    ids = {0x2001: 5, 0x2006: 6, 0x1008: 7, 0x1006: 8}
    for kind, src, ed45, ty in KINDS + [(0x1001, 2, False, 0x1000)]:
        for grain, art, eff in ((2, 0, 0), (3, 0, 0), (2, 1, 0), (2, 2, 0), (2, 0, 1), (0, 1, 0)):
            ob, nw = g_run(base, kind, src, ed45, grain, art, eff), g_run(new, kind, src, ed45, grain, art, eff)
            forced = grain and art in (1, 2)
            skip = forced and kind in ids and ty != 0x1000
            want_flags = ob[1] & ~0xc0 if ty & 0xf00 == 0x100 else (ob[1] & ~0x80 if skip else ob[1])
            good = ob[0] and nw[0] and nw[2] == ob[2] and nw[1] == want_flags and nw[4] == kind and ob[3] == (4 if not grain else 0)
            good &= nw[3] == (ids[kind] if skip else ob[3])
            if forced and ty == 0x1000:
                good &= bool(nw[1] & 0x80)                     # grain + Art on a photo-type job keeps its Soft Focus passes
            if skip:
                fired.add(kind)
            n += 1
            if not good:
                bad.append((hex(kind), src, ed45, grain, art, eff, ob[0], nw[0], hex(ob[1]), hex(nw[1]), ob[2], nw[2], ob[3], nw[3], hex(nw[4])))
    if fired != set(ids):
        bad.append(('guards fired', sorted(map(hex, fired))))
    return bad, n


def t_pkg(base_s, new_s, base, new, pkg, rst, info, disk):
    sb = {b.kind: b for b in oc.parse(BP.STOCK.read_bytes())}
    good = True
    for b in oc.parse(pkg):
        exp = bytearray(sb[b.kind].payload)
        for e in new_s['edits']:
            if int(e['kind'], 16) == b.kind:
                o = BP.resolve(b.kind, e['addr']); nb = bytes.fromhex(e['new']); exp[o:o + len(nb)] = nb
        good &= bytes(exp) == b.payload
        if b.kind == 0x100:
            good &= b.payload == new                            # the image R ran
    for b in oc.parse(rst):
        good &= b.payload == sb[b.kind].payload
    r = new_s['recview']
    ours = [(int(r['code_at'], 16), r['code_len']), (int(r['site'], 16), 5)] + \
        ([(int(new_s['grain_kind']['code_at'], 16), new_s['grain_kind']['code_len'])] + [(int(x, 16), 7) for x in new_s['grain_kind']['sites']] if 'grain_kind' in new_s else []) + \
        [(int(e['addr'], 16), len(e['new']) // 2) for e in new_s['edits'] if e.get('source') == 'patches/fw_version']
    diff = [BASE + i for i in range(len(base)) if base[i] != new[i]]
    stray = [hex(a) for a in diff if not any(s_ <= a < s_ + k for s_, k in ours)]
    good &= not stray and len(new_s['edits']) == len(base_s['edits']) + 1 + ('grain_kind' in new_s)
    if disk:
        good &= (disk / 'patched.pkg.bin').read_bytes() == pkg and (disk / 'restore-stock.pkg.bin').read_bytes() == rst
    return good, f'{info["edits"]} edits, {info["changed_payload_bytes"]} B; {len(diff)} B differ from v0.30; stray {stray[:6]}'


def main():
    base_s, new_s = (json.loads(Path(p).read_text()) for p in sys.argv[1:3])
    disk = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    stock = BP.STOCK.read_bytes()
    stock_main = [b for b in oc.parse(stock) if b.kind == 0x100][0].payload
    base, *_ = image(base_s)
    new, pkg, rst, info = image(new_s)
    ok = True
    bad, n, rows = t_gate(stock_main, base, new, 'grain_kind' in new_s); ok &= not bad
    print(f"{'PASS' if not bad else 'FAIL'} R gate: {n - len(bad)}/{n}", bad[:6] if bad else '')
    for x in rows:
        print('   ', x)
    if 'grain_kind' in new_s:
        bad, n = t_grain(base, new); ok &= not bad
        print(f"{'PASS' if not bad else 'FAIL'} G grain kind guard: {n - len(bad)}/{n}", bad[:6] if bad else '')
    good, txt = t_pkg(base_s, new_s, base, new, pkg, rst, info, disk); ok &= good
    print(f"{'PASS' if good else 'FAIL'} P anti-brick: {txt}")
    print('ALL PASS' if ok else 'FAILURES')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
