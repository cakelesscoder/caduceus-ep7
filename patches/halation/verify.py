#!/usr/bin/env python3
"""Emulator checks for halation h1 (real firmware code: gc_gs, gc_lvl, gc_grain, lock, mapper, lookup; malloc, free, blend setup and flush
stubbed as in the grain verifiers). Offline. docs/HALATION_RED.md §15.

  .venv/bin/python -I patches/halation/verify.py releases/v0.30/edits.json generated/halation/h1/edits.json [generated/halation/h1/pkg]

  M  model: the photo == model() below, bit-exact, red and cool, direct and through a window; buffers freed
  E  the real 5184-wide row crossing 0xd0000000 (two pieces per row), window mode restored
  G  gate: no halation, Glow, Clarity, bloom without tint, strength 0 / 6, tint 5, MONO, no record -> photo and result == v0.30;
     bloom + tint and halation -> model; halation + Grain -> v0.30's grain over the model's halation (halation first)
  C  coverage cap and an empty grid: photo == v0.30 (no write pass)
  F  malloc failures: photo untouched, every block freed
  P  anti-brick: package reparses, restore == stock, decoded == stock + edits, only our sites differ from v0.30
"""
import importlib.util, json, struct, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


B = _load('gc_verify_s1', ROOT / 'patches/grain_cpu/verify_s1.py')
HB = _load('hl_build', ROOT / 'patches/halation/build.py')
V, D = B.V, B.D
Region, execute = V.Region, V.execute
BASE, CALLER, STK, JOB, ALLOC, HEAP_U, HEAP_C = V.BASE, V.CALLER, V.STK, V.JOB, V.ALLOC, V.HEAP_U, V.HEAP_C
P_AT, H = D.P_AT, D.H
GDIA = 0x41494447


# ------------------------------------------------------------------ the model (hl.s.in, integer for integer)
def model(pic, w, h, st, tint, gmax):
    a = np.frombuffer(pic, dtype=np.uint8).copy().reshape(h, st * 2).astype(np.int64)
    gw, gh = (w + 63) >> 6, (h + 63) >> 6
    g = np.zeros((gh, gw), dtype=np.int64)
    for y in range(2, h, 4):
        for x in range(0, w, 2):
            e = a[y, 2 * x] - HB.THR
            if e > 0:
                c = g[y >> 6, x >> 6] + (e >> 2)
                g[y >> 6, x >> 6] = min(c, 248)

    def box(v):
        for _ in range(2):
            t = np.concatenate([[0], v, [0]])
            v = (t[:-2] + 2 * t[1:-1] + t[2:] + 2) >> 2
        return v
    for r in range(gh):
        g[r] = box(g[r])
    for c in range(gw):
        g[:, c] = box(g[:, c])
    u = np.minimum(255, (21 * g) >> 3)
    g = (((u * (511 - u)) >> 8) * gmax) >> 8
    cnt = int((g >= 16).sum())
    if cnt == 0 or 3 * cnt > gw * gh:
        return pic, cnt
    dy, d0, d1 = tint
    for y in range(h):
        fy = y - 32
        g0, t = (fy >> 6, fy & 63) if fy >= 0 else (0, 0)
        g1 = min(g0 + 1, gh - 1)
        if not (g[g0].any() or g[g1].any()):
            continue
        li = lambda c: (64 * g[g0, min(max(c, 0), gw - 1)] + (g[g1, min(max(c, 0), gw - 1)] - g[g0, min(max(c, 0), gw - 1)]) * t) >> 6
        gp = []
        for k in range(gw + 1):
            aa, bb = li(k - 1), li(k)
            v, step, n = 64 * aa, 2 * (bb - aa), 32
            if k == 0:
                v += 16 * step; n = 16
            if k == gw:
                n = 16
            for _ in range(n):
                gp.append((v >> 6) & 0xff); v += step
        row = a[y]
        for p in range(w // 2):
            gg = gp[p]
            if not gg:
                continue
            y0, c0, y1, c1 = row[4 * p:4 * p + 4]
            t0 = (255 - y0) * gg
            row[4 * p] = y0 + ((dy * t0) >> 16)
            row[4 * p + 2] = y1 + ((dy * ((255 - y1) * gg)) >> 16)
            row[4 * p + 1] = min(255, max(0, c0 + ((d0 * t0) >> 16)))
            row[4 * p + 3] = min(255, max(0, c1 + ((d1 * t0) >> 16)))
    return a.astype(np.uint8).tobytes(), cnt


def scene(w, h, st, lights, seed=3, base=40, wall=None):
    """Dark noisy frame, random chroma, clipped discs at lights [(x, y, r)]; wall = fraction of rows that are clipped (daylight)."""
    rng = np.random.default_rng(seed)
    a = rng.integers(0, 256, size=(h, st * 2), dtype=np.int64)
    yy, xx = np.mgrid[0:h, 0:w]
    Y = base + rng.integers(-20, 20, size=(h, w))
    for x0, y0, r in lights:
        Y = np.where((xx - x0) ** 2 + (yy - y0) ** 2 <= r * r, 255, Y)
    if wall:
        Y[: int(h * wall)] = 250
    a[:, 0:2 * w:2] = np.clip(Y, 0, 255)
    a[:, 1:2 * w:4] = rng.integers(100, 156, size=(h, w // 2))
    a[:, 3:2 * w:4] = rng.integers(100, 156, size=(h, w // 2))
    return a.astype(np.uint8).tobytes()


def slots(effect, strength, tint=0, grain=0, art=0, halo=0):
    t = bytearray(512)
    for i in range(4):
        t[i * 64 + 28] = effect; t[i * 64 + 29] = strength; t[i * 64 + 45] = tint; t[i * 64 + 50] = grain; t[i * 64 + 46] = art; t[i * 64 + 52] = halo
    return bytes(t)


def stage(effect, strength, tint, halo=0):
    """hl_stg: +52 1..4 = Off/Low/Med/High; 0 = the look's (effect 2, or 1 with tint 1..4; strength 1-2 Low, 3-4 Med, 5 High)."""
    if halo:
        return halo - 1 if halo <= 4 else 0
    if not (effect == 2 or (effect == 1 and tint)) or tint > 4 or not 1 <= strength <= 5:
        return 0
    return (strength - 1) // 2 + 1


def gm(effect, strength, tint, halo=0):
    return HB.GMAX[stage(effect, strength, tint, halo) - 1]


# ------------------------------------------------------------------ the run
def regions(q, gc, j, cached, pic, tbl, fail=0, pic2=None, block=True):
    wr = b'\xfc\xff' + struct.pack('<i', int(gc['gc_gs'], 16) - CALLER) + b'\xcb'
    p = bytearray(2048); p[0:4] = b'EP7B'; p[32:32 + 512] = tbl
    if block:
        struct.pack_into('<I', p, 1000, HEAP_U)
    st = bytearray(8); struct.pack_into('<H', st, 2, H + 1)
    hu = bytearray(0x100000)
    if block:
        struct.pack_into('<I', hu, 0, GDIA)
    r = [Region('low', 0x60020020, q[:0x60100000 - BASE], 'rx'), Region('blk0', 0x601de000, q[0x601de000 - BASE:0x601df000 - BASE], 'rx'),
         Region('blk', 0x601df000, q[0x601df000 - BASE:0x601e4000 - BASE], 'rx'), Region('isp', 0x60350000, q[0x60350000 - BASE:0x60360000 - BASE], 'rx'),
         Region('sec1', 0x60210000, q[0x60210000 - BASE:0x60211000 - BASE], 'rx'), Region('sec2', 0x6055e000, q[0x6055e000 - BASE:0x6055f000 - BASE], 'rx'),
         Region('sec3', 0x605b7000, q[0x605b7000 - BASE:0x605b8000 - BASE], 'rx'), Region('sec6', 0x61242000, q[0x61242000 - BASE:0x61243000 - BASE], 'rx'),
         Region('caller', CALLER, wr, 'rx'), Region('stk', STK, bytes(0x4000), 'rw', True), Region('job', JOB, bytes(j), 'rw', True),
         Region('alloc', ALLOC, struct.pack('<IIIIII', HEAP_U + 0x10000, fail, 0, 0, 0, 0) + bytes(64), 'rw', True), Region('heap', HEAP_C, bytes(0x100000), 'rw'),
         Region('heapu', HEAP_U, bytes(hu), 'rw', True), Region('pool', P_AT + H, bytes(p), 'rw', True), Region('st', 0x622cbcc0, bytes(st), 'rw'),
         Region('pic', cached, bytes(pic), 'rw', True), Region('cpu', 0x8000, bytes(0x100), 'rw'), Region('magic', 0x8ff00000, bytes(0x1000), 'rw'),
         Region('c0', 0x28900000, bytes(0x1000), 'rw'), Region('c1', 0x28980000, bytes(0x1000), 'rw'), Region('c2', 0x28a00000, bytes(0x1000), 'rw'), Region('c3', 0x28a80000, bytes(0x1000), 'rw'),
         Region('win', 0x98100000, bytes(0x1000), 'rw', True), Region('modes', V.MODES & ~0xff, bytes(0x100), 'rw', True)]
    if pic2:
        r.append(Region('pic2', pic2[0], pic2[1], 'rw', True))
    return r


def run(q, gc, j, cached, pic, tbl, **kw):
    wdt_on = kw.pop('wdt', 1)
    rgs = regions(q, gc, j, cached, pic, tbl, **kw) + [Region('wdtf', 0x6203ba00, struct.pack('<8xH6x', wdt_on), 'r')]
    r = execute(rgs, {'pc': CALLER, 'sp': STK + 0x3000, 'a0': JOB, 'd2': 0x2222, 'd3': 0x3333, 'a2': 0xa2a2, 'a3': 0xa3a3},
                CALLER + 6, limit=60000000, timeout=1200)
    m = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}
    rr = r['registers']
    al = struct.unpack('<IIIIII', m['alloc'][:24])
    ok = not r['fault'] and rr['pc'] == CALLER + 6 and rr['sp'] == STK + 0x3000 and (rr['d2'], rr['d3'], rr['a2'], rr['a3']) == (0x2222, 0x3333, 0xa2a2, 0xa3a3)
    nw = struct.unpack_from('<I', m['alloc'], 32)[0]
    return dict(ok=ok, fault=r['fault'], d0=rr['d0'], pic=m['pic'], m=m, mallocs=(al[0] - HEAP_U - 0x10000) // 0x10000, frees=al[2], sf=al[4], n=r['attempted'], dly=struct.unpack_from('<I', m['alloc'], 24)[0],
                wdt=[struct.unpack_from('<I', m['alloc'], 36 + 4 * i)[0] for i in range(min(nw, 6))],
                modes=m['modes'], hl=struct.unpack_from('<H', m['heapu'], 96)[0])


def job(bus, w, h, st, profile=2, **kw):
    return D.jb(bus, w=w, h=h, stride=st, profile=profile, **kw)


TINT = dict(zip(HB.ORDER, HB.tint_rows(False)))


def t_model(q, gc):
    bad, n = [], 0
    w, h, st = 2048, 1536, 2064                         # b3: big enough that three lights stay under the 30 % work cap
    pic = scene(w, h, st, [(300, 260, 6), (1400, 800, 14), (840, 1300, 3)])
    for cls in ('direct', 'c8'):
        bus, cached, _ = V.CLASSES[cls]
        for tint, strength, eff in ((1, 4, 1), (0, 2, 2), (4, 5, 2)):
            want, cnt = model(pic, w, h, st, TINT[HB.ORDER[max(tint, 1) - 1]], gm(eff, strength, tint))
            r = run(q, gc, job(bus, w, h, st), cached, pic, slots(eff, strength, tint))
            n += 1
            if not (r['ok'] and r['pic'] == want and want != pic and r['mallocs'] == 3 and r['frees'] == 3 and r['sf'] == 1 and r['hl'] == 0):
                diff = int((np.frombuffer(r['pic'], np.uint8) != np.frombuffer(want, np.uint8)).sum())
                bad.append((cls, tint, strength, eff, r['fault'], diff, want != pic, cnt, r['mallocs'], r['frees'], r['sf']))
    return bad, n


def t_edge(q, gc):
    edge, real, pitch = 0xd0000000, 0xce9d4b80, 10368
    k = (edge - real) % pitch
    bus = edge - k - 64 * pitch
    rows, st = 70, 5184
    pic = scene(5184, rows, st, [(2600, 64, 10), (5100, 30, 20)], seed=5)
    cut = edge - bus
    want, cnt = model(pic, 5184, rows, st, TINT['red'], gm(2, 4, 1))
    r = run(q, gc, job(bus, 5184, rows, st), 0x70000000 | (bus & 0x07ffffff), pic[:cut], slots(2, 4, 1), pic2=(0x70000000, pic[cut:]))
    got = r['m']['pic'] + r['m']['pic2']
    ok = r['ok'] and got == want and want != pic and struct.unpack_from('<I', r['modes'], V.MODES & 0xff)[0] == 0 and r['frees'] == 3
    return ([] if ok else [(r['fault'], got == want, want != pic, cnt, r['frees'])]), 1, r['n']


def t_gate(old, q, gc):
    """Against v0.30 on the same inputs: off cases identical; on cases = model; halation + grain = v0.30 grain over the model."""
    bad, n = [], 0
    w, h, st = 768, 512, 768
    bus, cached, _ = V.CLASSES['direct']
    pic = scene(w, h, st, [(330, 250, 10)], seed=9)
    qo = B.stubbed(old, {k: v for k, v in gc.items()}, B.slot_table())
    off = [('h2 Off on CineStill', slots(1, 4, 1, halo=1)), ('h2 bad value', slots(2, 3, 1, halo=9)), ('none', slots(0, 0)), ('glow', slots(1, 3)), ('clarity', slots(3, 3, 1)), ('bloom no tint', slots(1, 3, 0)), ('strength 0', slots(2, 0)),
           ('strength 6', slots(2, 6)), ('tint 5', slots(2, 3, 5)), ('effect 4', slots(4, 3, 1))]
    for name, tb in off:
        for kw in (dict(), dict(mode=12, key=12)):
            a = run(qo, gc, job(bus, w, h, st, **kw), cached, pic, tb)
            b = run(q, gc, job(bus, w, h, st, **kw), cached, pic, tb)
            n += 1
            if not (b['ok'] and a['pic'] == b['pic'] == pic and a['d0'] == b['d0'] and b['mallocs'] == 0):
                bad.append((name, kw, b['fault'], a['pic'] == b['pic'], b['mallocs']))
    for name, tb, tint, g_ in (('bloom red', slots(1, 4, 1), 'red', gm(1, 4, 1)), ('halation', slots(2, 2, 0), 'red', gm(2, 2, 0)), ('amber', slots(2, 5, 2), 'amber', gm(2, 5, 2)),
                               ('h2 High on a plain look', slots(0, 0, 0, halo=4), 'red', HB.GMAX[2]), ('h2 Low on CineStill', slots(1, 4, 1, halo=2), 'red', HB.GMAX[0]),
                               ('h2 Med, amber look', slots(3, 3, 2, halo=3), 'amber', HB.GMAX[1])):
        want, _ = model(pic, w, h, st, TINT[tint], g_)
        b = run(q, gc, job(bus, w, h, st), cached, pic, tb)
        n += 1
        if not (b['ok'] and b['pic'] == want != pic):
            bad.append((name, b['fault'], b['pic'] == want))
    a = run(q, gc, job(bus, w, h, st), cached, pic, slots(2, 3, 1), block=False)   # no record: stock
    n += 1
    if not (a['ok'] and a['pic'] == pic and a['frees'] == 0 and a['mallocs'] <= 1):
        bad.append(('no record', a['fault'], a['mallocs'], a['frees']))
    for lv in (1, 3):                                                          # halation, then the grain
        hal, _ = model(pic, w, h, st, TINT['red'], gm(2, 3, 1))
        a = run(qo, gc, job(bus, w, h, st), cached, hal, slots(2, 3, 1, grain=lv))
        b = run(q, gc, job(bus, w, h, st), cached, pic, slots(2, 3, 1, grain=lv))
        n += 1
        if not (b['ok'] and b['pic'] == a['pic'] and b['pic'] != hal and b['d0'] == a['d0'] and b['frees'] == 5):
            bad.append(('grain', lv, b['fault'], b['pic'] == a['pic'], b['frees']))
    return bad, n


def t_cover(old, q, gc):
    bad, n = [], 0
    w, h, st = 256, 192, 256
    bus, cached, _ = V.CLASSES['direct']
    for name, pic in (('daylight', scene(w, h, st, [], wall=0.6, seed=4)), ('no highlights', scene(w, h, st, [], seed=6))):
        r = run(q, gc, job(bus, w, h, st), cached, pic, slots(2, 5, 1))
        want, cnt = model(pic, w, h, st, TINT['red'], gm(2, 5, 1))
        n += 1
        if not (r['ok'] and r['pic'] == pic == want and r['frees'] == 3):
            bad.append((name, r['fault'], r['pic'] == pic, cnt, r['frees']))
    return bad, n


def t_fail(q, gc):
    bad, n = [], 0
    w, h, st = 768, 512, 768
    bus, cached, _ = V.CLASSES['direct']
    pic = scene(w, h, st, [(330, 250, 10)], seed=9)
    for fail, frees in ((1, 0), (2, 1), (3, 2)):            # the n-th malloc of ours fails
        r = run(q, gc, job(bus, w, h, st), cached, pic, slots(2, 3, 1), fail=fail)
        n += 1
        if not (r['ok'] and r['pic'] == pic and r['frees'] == frees):
            bad.append((fail, r['fault'], r['pic'] == pic, r['frees']))
    for name, kw in (('format', dict(fmt=0x0305)), ('x', dict(x=4)), ('size', dict(size=100)), ('bus', dict(bus=0x90000000)), ('bus c0', dict(bus=0xc1000000))):
        kw = dict(dict(bus=bus), **kw); b_ = kw.pop('bus')
        r = run(q, gc, job(b_, w, h, st, **kw), cached, pic, slots(2, 3, 1))
        n += 1
        if not (r['ok'] and r['pic'] == pic and r['mallocs'] == 0):
            bad.append((name, r['fault'], r['pic'] == pic, r['mallocs']))
    return bad, n


# ------------------------------------------------------------------ h2: flag hook, Extras sector 11, pick reset, loaders
def xr(q):
    return [Region('blk0', 0x601de000, q[0x601de000 - BASE:0x601df000 - BASE], 'rx'), Region('sec9', 0x6143a000, q[0x6143a000 - BASE:0x6143a800 - BASE], 'rx')]


def flag_run(im, key, mode, profile, kind, table):
    cap = bytearray(24100)
    cap[24053] = mode; cap[24083] = profile
    struct.pack_into('<H', cap, 194, kind)
    par = bytearray(32)
    par[8:12] = bytes(((key >> 24) & 255, (key >> 16) & 255)) + struct.pack('<H', key & 0xffff)
    struct.pack_into('<I', par, 12, 0x80000)
    q = bytearray(im); q[0x60210900 - BASE:0x60210900 - BASE + len(table)] = table; q = bytes(q)
    rg = [V.slice_(q, 0x601df000, 0x601e4000, 'blk'), V.slice_(q, 0x60210000, 0x60211000, 'sec1'), V.slice_(q, 0x603ea900, 0x603eae00, 'conv'), V.slice_(q, 0x6055e000, 0x6055f000, 'sec2'),
          Region('stk', STK, bytes(0x4000), 'rw', True), Region('cap', JOB, bytes(cap), 'rw'), Region('par', ALLOC, bytes(par), 'rw', True), Region('st', 0x622cbcc0, bytes(8), 'r')] + xr(q)
    r = execute(rg, {'pc': V.FLAG_SITE, 'sp': STK + 0x3000, 'a2': ALLOC + 12, 'a3': JOB}, V.FLAG_RET, limit=6000)
    m = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}
    return r['fault'], r['registers']['pc'] == V.FLAG_RET, struct.unpack_from('<I', m['par'], 12)[0]


def t_flag(old, new):
    """The Soft Focus flag 0x80 is added exactly when a COLOR still (ordinary kinds) has a stage; everything else == v0.30 r2."""
    bad, n = [], 0
    for eff, st_, tint, halo in ((0, 0, 0, 0), (0, 0, 0, 3), (0, 0, 0, 1), (0, 0, 0, 9), (1, 4, 1, 0), (1, 4, 1, 1), (3, 3, 0, 4), (1, 3, 0, 0)):
        for grain in (0, 2):
            for key, mode, prof, kind in ((11, 11, 2, 0x1001), (11, 11, 4, 0), (12, 12, 2, 0x1001), (11, 11, 2, 0x2001), (11, 11, 2, 0x1006)):
                t = slots(eff, st_, tint, grain=grain, halo=halo) + bytes(256)
                a = flag_run(old, key, mode, prof, kind, t); b = flag_run(new, key, mode, prof, kind, t)
                force = stage(eff, st_, tint, halo) > 0 and key == 11 and mode == 11 and kind not in (0x2001, 0x2006, 0x1008, 0x1006)
                n += 1
                if a[0] or b[0] or not b[1] or b[2] != (a[2] | 0x80 if force else a[2]):
                    bad.append((eff, st_, tint, halo, grain, key, hex(kind), b[0], hex(a[2]), hex(b[2])))
    return bad, n


def t_extras(old, new):
    """Sector 11 (index 10): get shows the stage (+52 override, else the look's), set writes 1 + clamp(v, 0, 3), default answers the look's;
    sectors 1..10 and 12 == v0.30 r2; labels."""
    bad, n = [], 0
    get, dflt = 0x601e32a3, 0x601e3333
    sets = next(a for a in range(0x601e3340, 0x601e3366) if new[a - BASE:a - BASE + 3] == b'\xf8\xfe\xfc')
    eg = lambda q, sym, sec, p: _ex(q, sym, sec, p)
    for eff, st_, tint, halo in ((1, 4, 1, 0), (2, 1, 0, 0), (2, 5, 2, 0), (0, 0, 0, 0), (1, 4, 1, 1), (0, 0, 0, 4), (2, 3, 0, 3), (2, 3, 0, 7), (1, 2, 0, 0)):
        s_ = bytearray(64); s_[28] = eff; s_[29] = st_; s_[45] = tint; s_[52] = halo
        f, v = _ex(new, get, 10, B.p_block(s_)); n += 1
        if f or v != stage(eff, st_, tint, halo):
            bad.append(('get', eff, st_, tint, halo, f, v))
        f, v = _ex(new, dflt, 10, B.p_block(s_)); n += 1
        if f or v != stage(eff, st_, tint, 0):
            bad.append(('default', eff, st_, tint, halo, f, v))
    for sec in (0, 1, 2, 4, 5, 6, 7, 8, 9, 11):
        s_ = bytearray(64); s_[24] = 6; s_[28] = 1; s_[29] = 4; s_[45] = 1; s_[50] = 2; s_[51] = 1; s_[52] = 3; s_[47] = 1
        for sym in (get, dflt):
            a, b = _ex(old, sym, sec, B.p_block(s_)), _ex(new, sym, sec, B.p_block(s_)); n += 1
            if a != b:
                bad.append(('other', sec, hex(sym), a, b))
    for val, want in ((-3, 1), (0, 1), (1, 2), (2, 3), (3, 4), (6, 4)):
        s_ = bytearray(64); s_[51] = 1; s_[50] = 2
        f, m, ok = _set(new, sets, 10, val, B.p_block(s_)); n += 1
        if f or not ok or m[32 + 64 + 52] != want or m[32 + 64 + 51] != 1 or m[32 + 64 + 50] != 2 or m[B.DIRTY] != 1:
            bad.append(('set', val, f, ok, m[32 + 64 + 52]))
    for sec in (9, 11):
        s_ = bytearray(64); s_[52] = 3
        a, b = _set(old, sets, sec, 1, B.p_block(s_)), _set(new, sets, sec, 1, B.p_block(s_)); n += 1
        if a[0] or b[0] or a[1] != b[1]:
            bad.append(('set other', sec, a[0], b[0]))
    txt = lambda a: new[a - BASE:a - BASE + 20].split(b'\0')[0]
    lab = 0x601e1e04
    n += 1
    if [txt(lab + 13 * i) for i in range(4)] != [b'11 Halo Off', b'11 Halo Low', b'11 Halo Med', b'11 Halo High'] or txt(struct.unpack_from('<I', new, 0x601e12aa - BASE)[0]) != b'Extras: 1-11 only':
        bad.append(('labels', [txt(lab + 13 * i) for i in range(4)]))
    return bad, n


def _ex(q, sym, sector, p):
    wr = b'\xfc\xff' + struct.pack('<i', sym - CALLER) + b'\xcb'
    r = execute(B.ex_regions(q, p, [Region('c', CALLER, wr, 'rx')] + xr(q)), {'pc': CALLER, 'sp': STK + 0x3000, 'd0': 939 + sector, 'a1': ALLOC}, CALLER + 6, limit=3000)
    return r['fault'], struct.unpack_from('<I', {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}['out'], 0)[0]


def _set(q, sym, sector, val, p):
    wr = b'\xdd' + struct.pack('<i', sym - CALLER) + b'\xe0\x10'
    ex = [Region('c', CALLER, wr, 'rx'), Region('sget', 0x602af887, b'\x80\x00\xdf\x00\x04', 'rx'), Region('mgr', 0x60827440, b'\xdf\xe0\x10', 'rx'),
          Region('sec3', 0x605b7000, q[0x605b7000 - BASE:0x605b7800 - BASE], 'rx'), Region('sec6', 0x61242000, q[0x61242000 - BASE:0x61243000 - BASE], 'rx')] + xr(q)
    r = execute(B.ex_regions(q, p, ex), {'pc': CALLER, 'sp': STK + 0x3000, 'd0': 939 + sector, 'd1': val & 0xffffffff, 'a0': 0x11, 'a1': 0x22}, CALLER + 7, limit=3000)
    return r['fault'], {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}['pool'], r['registers']['pc'] == CALLER + 7


def t_pick(new):
    """u_apply (Film pick, Own, Stock) with the real bytes: +52 back to 0 (the look's), Grain +50 / Sharp +51 / NR +24 kept."""
    bad, n = [], 0
    for name, T in (('look', bytes((i * 7 + 3) & 0x7f for i in range(64))), ('Stock', bytes(64))):
        slot = bytearray(64); slot[24] = 2; slot[50] = 3; slot[51] = 1; slot[52] = 4
        rg = [Region('a', 0x601e2e00, new[0x601e2e00 - BASE:0x601e2e4f - BASE], 'rx'), Region('b', 0x601e3700, new[0x601e3700 - BASE:0x601e3800 - BASE], 'rx'),
              Region('c', 0x601df000, new[0x601df000 - BASE:0x601e0b3c - BASE], 'rx'), Region('t', ALLOC, bytes(T) + bytes(64), 'rw', True), Region('s', JOB, bytes(slot), 'rw', True),
              Region('tail', 0x601e2e4f, b'\xcb\xcb', 'rx'), Region('stk', STK, bytes(0x4000), 'rw')] + xr(new)[:1]
        r = execute(rg, {'pc': 0x601e2e35, 'sp': STK + 0x3000, 'a1': ALLOC, 'd0': JOB}, 0x601e2e4f, limit=3000)
        s2 = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}['s']
        n += 1
        if r['fault'] or s2[52] != 0 or s2[24] != 2 or s2[50] != 3 or s2[51] != 1:
            bad.append((name, r['fault'], s2[52], s2[24], s2[50], s2[51]))
    return bad, n


def t_loaders(new):
    """Every value the UI saves loads: SD loader v3 span for +52 = 4; MOVIE.BIN and AP.BIN zero checks start at +53 (11 B)."""
    ok = new[0x605b7721 + 52 - BASE] == 4 and new[0x605b7721 + 51 - BASE] == 1
    for at in (0x601e0d10, 0x601df8e2):
        ok &= new[at - BASE:at - BASE + 7] == bytes.fromhex('fad06503800b04')
    return ([] if ok else ['loader bytes']), 1


def wdt_stub(im):
    """SYS_WDT request 0x60054b33 (needs the kernel) -> a stub: count at ALLOC+32, log d1 (0 off / 1 on) at ALLOC+36.., return 0."""
    code, _, _, _ = HB.SB3.assemble(f''' mov ({ALLOC + 32:#x}),d0
 mov d0,a0
 add a0,a0
 add a0,a0
 add {ALLOC + 36:#x},a0
 mov d1,(a0)
 inc d0
 mov d0,({ALLOC + 32:#x})
 clr d0
 ret [d2,d3,a2,a3],72
''', HB.WDTMSG, {})
    q = bytearray(im); q[HB.WDTMSG - BASE:HB.WDTMSG - BASE + len(code)] = code
    return bytes(q)


def dly_stub(im):
    """dly_tsk (needs the kernel) -> a stub that counts at ALLOC+24 and returns 0, same frame as the callers."""
    code, _, _, _ = HB.SB3.assemble(f''' mov ({ALLOC + 24:#x}),d0
 inc d0
 mov d0,({ALLOC + 24:#x})
 clr d0
 ret [d2,a2,a3],16
''', HB.DLY, {})
    q = bytearray(im); q[HB.DLY - BASE:HB.DLY - BASE + len(code)] = code
    return bytes(q)


def t_yield(new, q, gc):
    """b4: no pauses and no watchdog requests from the passes (dly_tsk and 0x60054b33 never called); the watchdog's run-time timeout
    is 30 s at both stock settings (0x6005b23a, 0x6005bcff: mov 30,d0)."""
    bad, n = [], 0
    w, h, st = 768, 512, 768
    bus, cached, _ = V.CLASSES['direct']
    pic = scene(w, h, st, [(330, 250, 10)], seed=9)
    for name, tb in (('halation', slots(2, 4, 1)), ('halation + grain', slots(2, 4, 1, grain=2)), ('glow + grain', slots(1, 3, 0, grain=2))):
        r = run(q, gc, job(bus, w, h, st), cached, pic, tb)
        n += 1
        if not (r['ok'] and r['dly'] == 0 and r['wdt'] == []):
            bad.append((name, r['fault'], r['dly'], r['wdt']))
    n += 1
    if [new[a - BASE:a - BASE + 2] for a in HB.WDT_SITES] != [bytes([0x80, HB.WDT_SECONDS])] * 2:
        bad.append(('timeout bytes', [new[a - BASE:a - BASE + 2].hex() for a in HB.WDT_SITES]))
    return bad, n


def t_pkg(new_s, new, pkg, rst, info, disk, old):
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
    hl = new_s['halation']
    ours = [(int(lo, 16), n_) for lo, hi, n_ in hl['regions'].values()] + [(int(a, 16) + 1, 2) for a in hl['sites']] + [(int(a, 16) + 1, 4) for a in hl['sites_h2']] + \
        [(int(a, 16) + 1, 4) for a in hl.get('sites_h3', [])] + [(int(a, 16), 2) for a in hl.get('wdt', {}).get('sites', [])] + \
        [(0x601e12aa, 4), (0x605b7721 + 52, 1), (0x601e0d12, 1), (0x601e0d15, 1), (0x601df8e4, 1), (0x601df8e7, 1)] + \
        [(int(e['addr'], 16), len(e['new']) // 2) for e in new_s['edits'] if e.get('source') == 'patches/fw_version']
    diff = [BASE + i for i in range(len(old)) if old[i] != new[i]]
    stray = [hex(a) for a in diff if not any(s_ <= a < s_ + k for s_, k in ours)]
    good &= not stray
    if disk:
        good &= (disk / 'patched.pkg.bin').read_bytes() == pkg and (disk / 'restore-stock.pkg.bin').read_bytes() == rst
    return good, f'{info["edits"]} edits, {info["changed_payload_bytes"]} B; {len(diff)} B differ from the base; stray {stray[:6]}'


def main():
    base_s, new_s = (json.loads(Path(p).read_text()) for p in sys.argv[1:3])
    disk = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    old, *_ = V.image(base_s)
    new, pkg, rst, info = V.image(new_s)
    gc = new_s['grain_cpu']['symbols']
    q = wdt_stub(dly_stub(B.stubbed(new, gc, B.slot_table())))
    ok = True
    for name, fn in (('M model', lambda: t_model(q, gc)), ('G gate', lambda: t_gate(old, q, gc)), ('C coverage', lambda: t_cover(old, q, gc)), ('F failures', lambda: t_fail(q, gc)),
                     ('W no pauses, watchdog 30 s', lambda: t_yield(new, q, gc)), ('A flag hook', lambda: t_flag(old, new)), ('X Extras sector 11', lambda: t_extras(old, new)), ('K pick resets +52', lambda: t_pick(new)), ('L loaders', lambda: t_loaders(new))):
        bad, n = fn(); ok &= not bad
        print(f"{'PASS' if not bad else 'FAIL'} {name}: {n - len(bad)}/{n}", bad[:5] if bad else '', flush=True)
    bad, n, ins = t_edge(q, gc); ok &= not bad
    print(f"{'PASS' if not bad else 'FAIL'} E 0xd0000000 edge, 5184 x 70: {n - len(bad)}/{n}, {ins} instructions", bad[:3] if bad else '', flush=True)
    good, txt = t_pkg(new_s, new, pkg, rst, info, disk, old); ok &= good
    print(f"{'PASS' if good else 'FAIL'} P anti-brick: {txt}")
    print('ALL PASS' if ok else 'FAILURES')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
