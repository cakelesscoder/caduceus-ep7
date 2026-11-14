#!/usr/bin/env python3
"""The verifier of grain g2 as released in v0.32b, kept as the record (verify.py is g3's). Needs a g2 spec (build.py REV = 'g2').

Emulator checks for grain g2 (real firmware code: gc_ob / gc_gs, lock, mapper, lookup; malloc, free, blend setup and flush stubbed,
as in the grain verifiers). Offline. docs/GRAIN_PORT.md "g2".

  .venv/bin/python -I patches/grain_g2/verify.py BASE.json NEW.json [PKGDIR]
  BASE = the same chain without the layer (patches/v032/build.py ... --version 0.33), NEW = with `--extra grain_g2=...`.

  T  ROM: the three tables == what the emulated gc_tbl builds for 23 / 55 / 91; the tile == model.tile()
  M  the pass == model.expected(), bit-exact: plain and blend routes, three levels, widths that aren't a multiple of 64, 4 px and
     5460 px (86 blocks), a block-row change, a carried seed, window classes, the real 0xd0000000 edge residue (a row in two pieces);
     record as r2 (stage 7, rows, split, seed), window mode restored, no malloc, no free
  K  rows per lock 1 and 2 give the pixels and the seed of 4
  H  a halation look with Grain: g2's grain over the halation model; the heap serves halation's three blocks only
  G  Grain Off, an unmarked job, no card table, no record: image untouched, stock pass still runs; failed guards (and a level
     outside 1..3): image untouched, guard id in the record, registers and stack as found
  I  instructions per pixel r2 -> g2; malloc / free calls; locks and flushes r2 == g2; instructions under one lock, K = 4, 2, 1
  X  every word / halfword access the block makes in the traced runs is aligned (the camera faults where the emulator doesn't)
  S  statistics on flat Y 128, 5184 x 3888 (models): r2 against g2
  P  anti-brick: package reparses, decoded == stock + edits, restore == stock, only our sites differ from BASE
"""
import importlib.util, json, re, struct, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


B = _load('gc_verify_s1_g2', ROOT / 'patches/grain_cpu/verify_s1.py')
GB = _load('grain_g2_build_v', HERE / 'build_g2.py')
M = GB.M
V, D = B.V, B.D
Region, execute = V.Region, V.execute
BASE, CALLER, STK, JOB, ALLOC, HEAP_U, HEAP_C = V.BASE, V.CALLER, V.STK, V.JOB, V.ALLOC, V.HEAP_U, V.HEAP_C
P_AT, H = D.P_AT, D.H
CLAIM, AT = GB.CLAIM, GB.AT
LOCK, MASK, UNMASK, V_UNLOCK = 0x6006a922, 0x60054d9f, 0x60054dc0, 0x6006a96b      # cpu_lock; its PSW mask leaf; cpu_unlock's PSW restore; cpu_unlock
REGS = {'d2': 0x2222, 'd3': 0x3333, 'a2': 0xa2a2, 'a3': 0xa3a3}
ALIGN = []                                                   # (code image, traced result)
TRAMP = CALLER + 0x20
TR = [b'']


def regions(q, wr, j, cached, pic, *, tbl=None, pool=True, block=True, pic2=None, seed=0):
    p = bytearray(2048); p[0:4] = b'EP7B'; p[32:32 + 512] = tbl or B.slot_table()
    hu = bytearray(0x400)
    if block:                                                # the record exists, as after any earlier capture
        struct.pack_into('<I', p, 1000, HEAP_U); hu[:4] = b'GDIA'; struct.pack_into('<I', hu, 44, seed)
    st = bytearray(8); struct.pack_into('<H', st, 2, H + 1 if pool else 0)
    first = HEAP_U + 0x10000 if block else HEAP_U
    r = [Region('low', 0x60020020, q[:0x60100000 - BASE], 'rx'), Region('s1', 0x601de000, q[0x601de000 - BASE:0x601e4000 - BASE], 'rx'),
         Region('isp', 0x60350000, q[0x60350000 - BASE:0x60360000 - BASE], 'rx'), Region('sec1', 0x60210000, q[0x60210000 - BASE:0x60211000 - BASE], 'rx'),
         Region('sec2', 0x6055e000, q[0x6055e000 - BASE:0x6055f000 - BASE], 'rx'), Region('g2', CLAIM[0], q[CLAIM[0] - BASE:CLAIM[1] - BASE], 'rx'),
         Region('caller', CALLER, wr.ljust(0x20, b'\xcb') + TR[0], 'rx'), Region('stk', STK, bytes(0x4000), 'rw', True), Region('job', JOB, bytes(j), 'rw', True),
         Region('alloc', ALLOC, struct.pack('<IIIIIII', first, 0, 0, 0, 0, 0, 0) + bytes(64), 'rw', True), Region('heap', HEAP_C, bytes(0x40000), 'rw'),
         Region('heapu', HEAP_U, bytes(hu), 'rw', True), Region('pool', P_AT + H, bytes(p), 'rw', True), Region('st', 0x622cbcc0, bytes(st), 'rw'),
         Region('pic', cached, bytes(pic), 'rw', True), Region('cpu', 0x8000, bytes(0x100), 'rw'), Region('magic', 0x8ff00000, bytes(0x1000), 'rw'),
         Region('c0', 0x28900000, bytes(0x1000), 'rw'), Region('c1', 0x28980000, bytes(0x1000), 'rw'), Region('c2', 0x28a00000, bytes(0x1000), 'rw'),
         Region('c3', 0x28a80000, bytes(0x1000), 'rw'), Region('win', 0x98100000, bytes(0x1000), 'rw', True), Region('modes', V.MODES & ~0xff, bytes(0x100), 'rw', True)]
    if pic2:
        r.append(Region('pic2', pic2[0], pic2[1], 'rw', True))
    return r, first


def run(q, entry, j, cached, pic, *, direct=None, trace=False, stop=None, limit=30000000, **kw):
    """entry = a work-list word (`calls`, a0 = job); direct = (level): `call gc_grain,[d2,d3,a2,a3],144` with a0 = the record."""
    if direct is None:
        wr, end, regs = b'\xfc\xff' + struct.pack('<i', entry - CALLER) + b'\xcb', CALLER + 6, {'a0': JOB}
    else:
        wr, end, regs = b'\xdd' + struct.pack('<i', entry - CALLER) + b'\xf0\x90\xcb', CALLER + 7, {'a0': JOB + 6592 + 88 * 3, 'd0': direct}
    rg, first = regions(q, wr, j, cached, pic, **kw)
    r = execute(rg, dict(REGS, pc=CALLER, sp=STK + 0x3000, **regs), end, limit=limit, timeout=600, trace_limit=100000 if trace else 0,
                breakpoints=list(stop) if stop else ())
    if trace:
        ALIGN.append((q, r))
    m = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}
    rr = r['registers']
    al = struct.unpack('<IIIIIII', m['alloc'][:28])
    return dict(ok=not r['fault'] and rr['pc'] == end and rr['sp'] == STK + 0x3000 and all(rr[k] == v for k, v in REGS.items()), fault=r['fault'], pc=rr['pc'],
                m=m, pic=m['pic'] + m.get('pic2', b''), frees=al[2], mallocs=(al[0] - first) // 0x10000, flushes=al[5], locks=al[6], n=r['attempted'],
                f=D.fields(m['heapu'][:80]), mode=struct.unpack_from('<I', m['modes'], V.MODES & 0xff)[0])


def count_locks(q, g):
    """Count the pass's lock windows: gc_open's first three instructions (mov d0,a3; clr d0; call cpu_lock,[d2],8) go through a
    counter in the caller region (alloc +24), then back. The lock itself stays the real one."""
    at = g['gc_open']
    if q[at - BASE:at - BASE + 4] != b'\xf1\xe3\x00\xdd' or q[at + 8 - BASE:at + 10 - BASE] != b'\x80\x08':
        raise SystemExit('gc_open entry differs')
    q = bytearray(q); q[at - BASE:at - BASE + 10] = b'\xdc' + struct.pack('<i', TRAMP - at) + b'\xcb' * 5
    return bytes(q)


def tramp(g):
    code, _, _, _ = GB.B3.assemble(f''' mov ({ALLOC + 24:#x}),d1
 inc d1
 mov d1,({ALLOC + 24:#x})
 mov d0,a3
 clr d0
 call ep7_lock,[d2],8
 jmp gc_open_back
''', TRAMP, dict(ep7_lock=LOCK, gc_open_back=g['gc_open'] + 10))
    return code


def with_k(q, g, k):
    code = GB.build_code(g, k)[0]
    assert len(code) == len(GB.build_code(g)[0])
    q = bytearray(q); q[AT - BASE:AT - BASE + len(code)] = code
    return bytes(q)


def edge_case(rows=6, k=None, w=5184, st=5184):
    """Rows over the 0xd0000000 window edge: k = bytes of row 2 below it (default: the residue of the camera's record, 448 px, a block
    edge). -> (bus, cached, pic, bytes below the edge)."""
    edge, real, pitch = 0xd0000000, D.REAL, 2 * st
    k = (edge - real) % D.PITCH if k is None else k
    bus = edge - k - 2 * pitch
    return bus, 0x70000000 | (bus & 0x07ffffff), V.picture(w, rows, st), edge - bus


EDGES = (('edge, the camera residue (x = 448)', {}, 5184, 5184), ('edge at x = 1237, width 5000', dict(k=2474, w=5000), 5000, 5184))


def run_edge(q, gc, e, **kw):
    name, ekw, w, st = e
    bus, cached, pic, cut = edge_case(6, **ekw)
    r = run(q, int(gc['gc_ob'], 16), B.job(bus, w=w, h=6, stride=st, profile=3), cached, pic[:cut], pic2=(0x70000000, pic[cut:]), **kw)
    want, sd = M.expected(pic, w, 6, st, 2)
    return r, want, sd


# ------------------------------------------------------------------ T
def t_tables(old, new, gc):
    bad, n = [], 0
    tbl, gG = int(gc['gc_tbl'], 16), int(gc['gc_G'], 16)
    wr = b'\xdd' + struct.pack('<i', tbl - CALLER) + b'\xf0\x10\xcb'                 # call gc_tbl,[d2,d3,a2,a3],16
    for lv in (1, 2, 3):
        rg = [Region('s1', 0x601de000, old[0x601de000 - BASE:0x601e4000 - BASE], 'rx'), Region('caller', CALLER, wr, 'rx'), Region('stk', STK, bytes(0x4000), 'rw'),
              Region('t', ALLOC, bytes(8192), 'rw', True)]
        r = execute(rg, {'pc': CALLER, 'sp': STK + 0x3000, 'a0': ALLOC, 'a1': gG, 'd3': M.S[lv]}, CALLER + 7, limit=400000, timeout=120)
        got = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}['t']
        rom = new[GB.T_AT + 8192 * (lv - 1) - BASE:GB.T_AT + 8192 * lv - BASE]
        n += 1
        if r['fault'] or r['registers']['pc'] != CALLER + 7 or got != rom or rom != M.table(lv).tobytes():
            bad.append(('table', lv, r['fault'], got == rom, rom == M.table(lv).tobytes()))
    n += 1
    if new[GB.TILE_AT - BASE:GB.TILE_AT + 16384 - BASE] != M.tile().tobytes() or max(new[GB.TILE_AT - BASE:GB.TILE_AT + 16384 - BASE]) > 30:
        bad.append(('tile',))
    return bad, n


# ------------------------------------------------------------------ M, K
def cases():
    """(name, route, class, w, h, stride, level, seed, trace)"""
    return [('plain Low', 'ob', 'direct', 192, 70, 200, 1, 0, False), ('plain Med', 'ob', 'direct', 192, 70, 200, 2, 0, False), ('plain High', 'ob', 'b0', 192, 70, 200, 3, 0, False),
            ('blend route', 'gs', 'direct', 192, 9, 200, 2, 0, False), ('width 100', 'ob', 'c8', 100, 9, 160, 3, 0, False), ('width 200, rows 66', 'ob', 'direct', 200, 66, 208, 1, 0, True),
            ('width 4', 'ob', 'direct', 4, 5, 32, 2, 0, False), ('width 5460', 'ob', 'd8', 5460, 3, 5472, 3, 0, False), ('seed', 'ob', 'c4', 132, 66, 160, 2, 0xdeadbeef, False),
            ('window d0', 'gs', 'd0', 320, 8, 320, 3, 7, False), ('1000 x 200', 'ob', 'c8', 1000, 200, 1024, 3, 0x77, False)]


def run_case(q, gc, c, **kw):
    name, route, cls, w, h, st, lv, seed, trace = c
    bus, cached, mode = V.CLASSES[cls]
    pic = V.picture(w, h, st)
    r = run(q, int(gc['gc_' + route], 16), B.job(bus, w=w, h=h, stride=st, profile=2), cached, pic, tbl=B.slot_table((0, lv, 0, 0)), seed=seed, trace=trace, **kw)
    want, sd = M.expected(pic, w, h, st, lv, seed or M.SEED0)
    return r, pic, want, sd, (0 if bus < 0xb0000000 else (2 if mode else 1)), mode


def t_model(q, gc, k=GB.K):
    bad, n = [], 0
    for c in cases():
        r, pic, want, sd, cl, mode = run_case(q, gc, c)
        f = r['f']; h = c[4]; n += 1
        locks = -(-h // k)
        if not (r['ok'] and r['pic'] == want and want != pic and (f['stage'], f['guard']) == (7, 0) and f['seed'] == sd and f['rows'] == h and f['split'] == 0 and f['cls'] & 15 == cl
                and r['mallocs'] == 0 and r['frees'] == 0 and r['mode'] == 0 and r['flushes'] == locks * (2 if mode else 1) + 2 and (f['hw'], f['n'], f['fmt']) == (c[3], h, 0x0302)):
            bad.append((c[0], r['fault'], r['pic'] == want, f['stage'], hex(f['guard']), f['rows'], r['mallocs'], r['frees'], r['flushes'], r['mode']))
    for e in EDGES:
        r, want, sd = run_edge(q, gc, e, trace=True)
        f = r['f']; n += 1
        if not (r['ok'] and r['pic'] == want and f['rows'] == 6 and f['split'] == 1 and f['seed'] == sd and r['mode'] == 0 and r['mallocs'] == 0 and (f['stage'], f['guard']) == (7, 0)):
            bad.append((e[0], r['fault'], r['pic'] == want, f['rows'], f['split'], r['mode']))
    return bad, n


def t_k(q, g, gc):
    bad, n = [], 0
    for k in (1, 2):
        qk = with_k(q, g, k)
        for c in (cases()[1], cases()[5], cases()[8]):
            r, pic, want, sd, cl, mode = run_case(qk, gc, c)
            n += 1
            if not (r['ok'] and r['pic'] == want and r['f']['seed'] == sd and r['f']['rows'] == c[4] and r['flushes'] == -(-c[4] // k) * (2 if mode else 1) + 2):
                bad.append((k, c[0], r['fault'], r['pic'] == want, r['flushes']))
        for e in EDGES:
            r, want, sd = run_edge(qk, gc, e)
            n += 1
            if not (r['ok'] and r['pic'] == want and r['f']['seed'] == sd and r['f']['split'] == 1 and r['mode'] == 0):
                bad.append((k, e[0], r['fault'], r['pic'] == want))
    return bad, n


# ------------------------------------------------------------------ H
def t_halo(q, gc):
    """A halation look with Grain: halation's hl_grain runs its pass, then jumps to gc_grain. The photo == g2's grain over the
    halation model (patches/halation/verify.py model()), and only halation's own three blocks come from the heap."""
    HV = _load('hl_verify_g2', ROOT / 'patches/halation/verify.py')
    w, h, st = 768, 512, 768
    bus, cached, _ = V.CLASSES['direct']
    pic = HV.scene(w, h, st, [(330, 250, 10)], seed=9)
    hal, _ = HV.model(pic, w, h, st, HV.TINT['red'], HV.gm(2, 3, 1))
    want, sd = M.expected(hal, w, h, st, 2)
    rg = HV.regions(q, gc, HV.job(bus, w, h, st), cached, pic, HV.slots(2, 3, 1, grain=2)) + [
        Region('g2', CLAIM[0], q[CLAIM[0] - BASE:CLAIM[1] - BASE], 'rx'), Region('wdtf', 0x6203ba00, struct.pack('<8xH6x', 1), 'r')]
    r = execute(rg, dict(REGS, pc=CALLER, sp=STK + 0x3000, a0=JOB), CALLER + 6, limit=60000000, timeout=1200)
    m = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}
    rr = r['registers']
    al = struct.unpack('<IIIIII', m['alloc'][:24])
    ok = (not r['fault'] and rr['pc'] == CALLER + 6 and rr['sp'] == STK + 0x3000 and all(rr[k] == v for k, v in REGS.items()) and m['pic'] == want and hal != pic and want != hal
          and al[2] == 3 and (al[0] - HEAP_U - 0x10000) // 0x10000 == 3 and D.fields(m['heapu'][:80])['seed'] == sd and D.fields(m['heapu'][:80])['stage'] == 7)
    return ([] if ok else [(r['fault'], m['pic'] == want, hal != pic, al[2], (al[0] - HEAP_U - 0x10000) // 0x10000)]), 1


# ------------------------------------------------------------------ G
def t_guards(q, gc):
    bad, n = [], 0
    ob, gs, gr = (int(gc[k], 16) for k in ('gc_ob', 'gc_gs', 'gc_grain'))
    w, h, st, bus, c = 192, 9, 200, 0xa4000000, 0x64000000
    pic = V.picture(w, h, st)
    off = (('Grain Off', dict(tbl=B.slot_table((0, 0, 0, 0))), {}, (ob, gs)), ('COLOR1 off', {}, dict(profile=1), (ob, gs)), ('live view job', {}, dict(jtype=0x30), (ob, gs)),
           ('job not marked plain', {}, dict(marked=False), (ob,)), ('no card table', dict(pool=False, block=False), {}, (ob, gs)))
    for name, kw, jkw, entries in off:
        for entry in entries:
            r = run(q, entry, B.job(bus, **dict(dict(w=w, h=h, stride=st, profile=2), **jkw)), c, pic, **kw)
            n += 1
            if not (r['ok'] and r['pic'] == pic and r['frees'] == 0 and r['flushes'] == 0 and r['locks'] == 0 and r['f']['stage'] < 4):
                bad.append((name, hex(entry), r['fault'], r['pic'] == pic, r['flushes'], r['f']['stage']))
    for gid, kw in ((0x20, dict(fmt=0x0305)), (0x21, dict(x=4)), (0x24, dict(w=5464, stride=5472)), (0x25, dict(w=190)), (0x26, dict(stride=64)), (0x29, dict(size=100)),
                    (0x2a, dict(bus=0x90000000)), (0x2d, dict(bus=0xc1000000)), (0x32, dict(bus=0xdfffff00))):
        kw = dict(dict(w=w, h=h, stride=st, bus=bus, profile=2), **kw); b = kw.pop('bus')
        r = run(q, ob, B.job(b, **kw), c, pic)
        n += 1
        if not (r['ok'] and r['pic'] == pic and (r['f']['stage'], r['f']['guard']) == (4, gid) and r['flushes'] == 0 and r['mallocs'] == 0):
            bad.append((hex(gid), r['fault'], r['pic'] == pic, r['f']['stage'], hex(r['f']['guard'])))
    for lv, good in ((0, False), (4, False), (200, False), (2, True)):                # the entry itself, with r2's frame
        r = run(q, gr, B.job(bus, w=w, h=h, stride=st), c, pic, direct=lv)
        n += 1
        if good:
            ok = r['ok'] and r['pic'] == M.expected(pic, w, h, st, lv)[0] and r['f']['stage'] == 7
        else:
            ok = r['ok'] and r['pic'] == pic and (r['f']['stage'], r['f']['guard']) == (4, 0x33) and r['flushes'] == 0
        if not ok:
            bad.append(('level', lv, r['fault'], hex(r['pc']), r['f']['stage'], hex(r['f']['guard'])))
    return bad, n


# ------------------------------------------------------------------ I
def t_cost(oldq, q, g, gc_old, gc):
    """-> (bad, n, report lines)."""
    bad, n, out = [], 0, []
    bus, c = 0xa4000000, 0x64000000
    w = 5184

    def strip(img, sym, rows, cls='direct', **kw):
        b, cc, _ = V.CLASSES[cls]
        return run(count_locks(img, g), int(sym['gc_ob'], 16), B.job(b, w=w, h=rows, stride=w, profile=2), cc, V.picture(w, rows, w), tbl=B.slot_table((0, 3, 0, 0)), **kw)
    a64, a128 = strip(oldq, gc_old, 64), strip(oldq, gc_old, 128)
    b64, b128 = strip(q, gc, 64), strip(q, gc, 128)
    per_old, per_new = (a128['n'] - a64['n']) / (64 * w), (b128['n'] - b64['n']) / (64 * w)
    out.append(f'instructions per pixel (5184-px rows, slope 64 -> 128 rows, flush stubbed): r2 {per_old:.2f}, g2 {per_new:.2f}; a 5184 x 3888 photo: {per_old * w * 3888 / 1e6:.0f} M -> {per_new * w * 3888 / 1e6:.0f} M')
    for k in (2, 1):
        qk = with_k(q, g, k)
        per_k = (strip(qk, gc, 128)['n'] - strip(qk, gc, 64)['n']) / (64 * w)
        out.append(f'  g2 with K = {k}: {per_k:.2f} per pixel, {per_k * w * 3888 / 1e6:.0f} M a photo')
        n += 1
        if per_k > 7.0:
            bad.append(('cost', k, per_k))
    out.append(f'setup before the first row (128-row strip minus rows): r2 {a128["n"] - per_old * 128 * w:.0f}, g2 {b128["n"] - per_new * 128 * w:.0f} instructions')
    out.append(f'malloc / free calls in the pass: r2 {a128["mallocs"]} / {a128["frees"]}, g2 {b128["mallocs"]} / {b128["frees"]}')
    n += 1
    if not (a128['ok'] and b128['ok'] and b128['mallocs'] == 0 and b128['frees'] == 0 and a128['mallocs'] == 2 and a128['frees'] == 2 and per_new <= 7.0 and per_old > 14):
        bad.append(('cost', a128['fault'], b128['fault'], per_old, per_new))
    for cls in ('direct', 'c8'):
        a, b_ = (strip(oldq, gc_old, 64, cls), strip(q, gc, 64, cls)) if cls != 'direct' else (a64, b64)
        out.append(f'locks / flushes, 64 rows, class {cls}: r2 {a["locks"]} / {a["flushes"]}, g2 {b_["locks"]} / {b_["flushes"]}')
        n += 1
        if (a['locks'], a['flushes']) != (b_['locks'], b_['flushes']) or a['locks'] != 16:
            bad.append(('locks', cls, a['locks'], a['flushes'], b_['locks'], b_['flushes']))
    ebus, ecached, epic, cut = edge_case(8)                                           # the camera's residue
    counts = {}
    for name, img, sym in (('r2', oldq, gc_old), ('g2', q, gc)):
        r = run(count_locks(img, g), int(sym['gc_ob'], 16), B.job(ebus, w=w, h=8, stride=w, profile=3), ecached, epic[:cut], pic2=(0x70000000, epic[cut:]))
        counts[name] = (r['locks'], r['flushes'], r['ok'])
    out.append(f'locks / flushes, 8 rows over the 0xd0000000 edge: r2 {counts["r2"][0]} / {counts["r2"][1]}, g2 {counts["g2"][0]} / {counts["g2"][1]}')
    n += 1
    if counts['r2'] != counts['g2'] or counts['g2'][0] != 2 + 4:                      # the pass with the edge: its 4 rows, one in two pieces
        bad.append(('edge locks', counts))

    def unlock_sites(img, lo, hi):
        """The pass's own `call cpu_unlock` instructions: where a lock window ends (the mapper and the mode getter lock on their own inside it)."""
        return [a for a, op, args in GB.B3.disasm(img[lo - BASE:hi - BASE], lo) if op == 'call' and args.startswith(hex(V_UNLOCK))]

    def masked(img, sym, cls, sites):
        b, cc, _ = V.CLASSES[cls]
        kw = dict(tbl=B.slot_table((0, 3, 0, 0)))
        j = B.job(b, w=w, h=8, stride=w, profile=2)
        r1 = run(img, int(sym['gc_ob'], 16), j, cc, V.picture(w, 8, w), stop=[MASK], **kw)
        r2 = run(img, int(sym['gc_ob'], 16), j, cc, V.picture(w, 8, w), stop=sites, **kw)
        return (r2['n'] - r1['n']) if r1['pc'] == MASK and r2['pc'] in sites else None
    old_sites = unlock_sites(oldq, g['gc_grain'], g['gc_cls'])
    new_sites = unlock_sites(q, AT, AT + len(GB.build_code(g)[0]))
    n += 1
    if len(old_sites) != 3 or len(new_sites) != 3:
        bad.append(('unlock sites', old_sites, new_sites))
    for img, sym in ((oldq, gc_old), (q, gc)):                                         # nothing but the pass reaches the two PSW leaves on this route
        for leaf in (MASK, UNMASK):
            r = run(img, int(sym['gc_ob'], 16), B.job(bus, w=192, h=9, stride=200, profile=1), c, V.picture(192, 9, 200), stop=[leaf])
            n += 1
            if not r['ok']:
                bad.append(('leaf reached with Grain Off', hex(leaf), hex(r['pc'])))
    for cls in ('direct', 'c8'):
        row = [f'r2 K 4: {masked(oldq, gc_old, cls, old_sites)}']
        for k in (4, 2, 1):
            v = masked(with_k(q, g, k), gc, cls, new_sites); row.append(f'g2 K {k}: {v}')
            n += 1
            if v is None or v > 6.5 * w * k:
                bad.append(('masked', cls, k, v))
        out.append(f'instructions under one lock (PSW mask to the unlock call, 5184-px rows, class {cls}): ' + ', '.join(row))
    for k in (4, 2, 1):                                                               # per photo, the camera's record: the edge is in row 2242
        r = run(count_locks(with_k(q, g, k), g), int(gc['gc_ob'], 16), B.job(ebus, w=w, h=8, stride=w, profile=3), ecached, epic[:cut], pic2=(0x70000000, epic[cut:]))
        cl = strip(with_k(q, g, k), gc, 16, 'c8')
        dl = strip(with_k(q, g, k), gc, 16, 'd0')
        per = (cl['flushes'] - 2) // cl['locks']
        locks = 3888 // k - 1 + k + 1
        n += 1
        if not (r['ok'] and cl['ok'] and dl['ok'] and r['locks'] == 8 // k - 1 + k + 1 and cl['locks'] == 16 // k and (cl['flushes'] - 2) % cl['locks'] == 0
                and (dl['locks'], dl['flushes']) == (cl['locks'], cl['flushes']) and r['flushes'] == r['locks'] * per + 2):
            bad.append(('photo', k, r['locks'], r['flushes'], cl['locks'], cl['flushes'], dl['locks'], dl['flushes']))
        out.append(f'5184 x 3888 at bus {D.REAL:#x}, K = {k}: {locks} locks ({3888 // k - 1} passes of {k} rows + the edge pass row by row, one row split), {locks * per + 2} flushes ({per} a lock + 2)')
    return bad, n, out


# ------------------------------------------------------------------ X
def t_align(g):
    """Every word / halfword load and store of the block in the traced runs: its address must be a multiple of its size."""
    bad, n = [], 0
    for main, x in ALIGN:
        code = GB.build_code(g)[0]
        code = main[AT - BASE:AT - BASE + len(code)]
        ins = {a: (op, args) for a, op, args in GB.B3.disasm(code, AT)}
        for row in x['trace']:
            if row['pc'] not in ins:
                continue
            op, args = ins[row['pc']]
            size = {'mov': 4, 'movhu': 2}.get(op)
            m = re.search(r'\(([^)]*)\)', args)
            if not size or not m:
                continue
            addr = sum(row[p_] if p_ in row else int(p_, 0) for p_ in (p_.strip() for p_ in m.group(1).split(',')))
            n += 1
            if addr % size:
                bad.append((hex(row['pc']), op, args, hex(addr & 0xffffffff)))
    return bad, n


# ------------------------------------------------------------------ S
def t_stats():
    bad, out = [], ['flat Y 128, 5184 x 3888 | mean shift | std | corr right / down / 2 down / diagonal | other lags, max | std of 64 x 64 block means']
    w, h = 96, 70                                              # the reference is r2's own model (camera-tested as s3)
    pic = V.picture(w, h, 100)
    a, _ = B.expected(pic, w, h, 100, M.S[3], M.SEED0)
    n2, _ = M.r2_noise(w, h)
    c = np.frombuffer(pic, dtype=np.uint8).copy().reshape(h, 200); c[:, 0:2 * w:2] = M.table(3)[c[:, 0:2 * w:2], n2]
    if c.tobytes() != a:
        bad.append(('model.r2_noise differs from verify_s1.expected',))
    for name, pop, r2, rng, g2 in M.stats_table():
        out.append(f'{name:4} r2, exact      | {pop[0]:+.3f} | {pop[1]:.3f} |')
        out.append(f'{name:4} r2, 8 more seeds | {rng[0]:+.3f} .. {rng[1]:+.3f} | {rng[2]:.3f} .. {rng[3]:.3f} |')
        for tag, s in (('r2, seed 12345678', r2), ('g2, seed 12345678', g2)):
            out.append(f"{name:4} {tag} | {s['mean']:+.3f} | {s['std']:.3f} | {s['right']:.4f} / {s['down']:.4f} / {s['down2']:+.4f} / {s['diag']:.4f} | {s['far']:.4f} | {s['block']:.3f}")
        rel = lambda k_: abs(g2[k_] - r2[k_]) / r2[k_]
        if not (abs(g2['std'] - pop[1]) / pop[1] < 0.02 and abs(g2['mean'] - pop[0]) < 0.02 * pop[1] and rel('right') < 0.02 and rel('down') < 0.02 and rel('diag') < 0.02
                and abs(g2['down2']) < 0.01 and g2['far'] < 0.01 and g2['block'] < 1.2 * r2['block']):
            bad.append((name, g2))
    return bad, 3, out


# ------------------------------------------------------------------ P
def t_pkg(new_s, new, pkg, rst, info, disk, old, g):
    sb = {b.kind: b for b in V.oc.parse(V.BP.STOCK.read_bytes())}
    good = True
    for b in V.oc.parse(pkg):
        exp = bytearray(sb[b.kind].payload)
        for e in new_s['edits']:
            if int(e['kind'], 16) == b.kind:
                o = V.BP.resolve(b.kind, e['addr']); nb = bytes.fromhex(e['new']); exp[o:o + len(nb)] = nb
        good &= bytes(exp) == b.payload
    for b in V.oc.parse(rst):
        good &= b.payload == sb[b.kind].payload
    s = new_s['grain_g2']
    ours = [(int(s['code'][0], 16), s['code'][1]), (int(s['tile'][0], 16), s['tile'][1] + s['tables'][1]), (int(s['site'], 16), 6)]
    diff = [BASE + i for i in np.nonzero(np.frombuffer(old, np.uint8) != np.frombuffer(new, np.uint8))[0]]
    stray = [hex(a) for a in diff if not any(s_ <= a < s_ + k for s_, k in ours)]
    good = bool(good) and not stray and len(old) == len(new)
    site = int(s['site'], 16)
    good &= new[site - BASE:site - BASE + 6] == b'\xdc' + struct.pack('<i', int(s['symbols']['g2_grain'], 16) - site) + b'\xcb'
    good &= new[site + 6 - BASE:g['gc_cls'] - BASE] == old[site + 6 - BASE:g['gc_cls'] - BASE]
    if disk:
        good &= (disk / 'patched.pkg.bin').read_bytes() == pkg and (disk / 'restore-stock.pkg.bin').read_bytes() == rst
    return good, f'{info["edits"]} edits, {info["changed_payload_bytes"]} B; {len(diff)} B differ from BASE; stray {stray[:6]}'


def main():
    base_s, new_s = (json.loads(Path(p).read_text()) for p in sys.argv[1:3])
    disk = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    if 'grain_g2' in base_s or 'grain_g2' not in new_s:
        raise SystemExit('BASE must lack the layer, NEW must have it')
    old, *_ = V.image(base_s)
    new, pkg, rst, info = V.image(new_s)
    gc, gc_old = new_s['grain_cpu']['symbols'], base_s['grain_cpu']['symbols']
    g = {k: int(v, 16) for k, v in gc.items()}
    q, oldq = B.stubbed(new, gc, B.slot_table()), B.stubbed(old, gc_old, B.slot_table())
    TR[0] = tramp(g)
    ok = True
    for name, fn in (('T tables and tile', lambda: t_tables(old, new, gc)), ('M model', lambda: t_model(q, gc)), ('K rows per lock 1, 2', lambda: t_k(q, g, gc)),
                     ('H halation, then grain', lambda: t_halo(q, gc)), ('G off and guards', lambda: t_guards(count_locks(q, g), gc))):
        bad, n = fn(); ok &= not bad
        print(f"{'PASS' if not bad else 'FAIL'} {name}: {n - len(bad)}/{n}", bad[:5] if bad else '', flush=True)
    bad, n, out = t_cost(oldq, q, g, gc_old, gc); ok &= not bad
    print(f"{'PASS' if not bad else 'FAIL'} I cost: {n - len(bad)}/{n}", bad[:5] if bad else '')
    print('\n'.join('  ' + x for x in out), flush=True)
    bad, n = t_align(g); ok &= not bad and n > 0
    print(f"{'PASS' if not bad and n else 'FAIL'} X alignment: {n - len(bad)}/{n}", bad[:5] if bad else '', flush=True)
    bad, n, out = t_stats(); ok &= not bad
    print(f"{'PASS' if not bad else 'FAIL'} S statistics: {n - len(bad)}/{n}", bad[:5] if bad else '')
    print('\n'.join('  ' + x for x in out), flush=True)
    good, txt = t_pkg(new_s, new, pkg, rst, info, disk, old, g); ok &= good
    print(f"{'PASS' if good else 'FAIL'} P anti-brick: {txt}")
    print('ALL PASS' if ok else 'FAILURES')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
