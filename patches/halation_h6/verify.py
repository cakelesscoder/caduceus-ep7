#!/usr/bin/env python3
"""Emulator checks for halation h6 (real firmware code: gc_gs, hl_lvl, hl_grain, h6_*, ap_P, gc_open, lock, mapper, lookup,
grain; malloc, free, blend setup and flush stubbed as in patches/halation/verify.py). Offline. docs/HALATION_RED.md "h6".

  .venv/bin/python -I patches/halation_h6/verify.py BASE NEW [PKG] [--frames]

BASE is the same chain without the layer (the shipped h2 halation), NEW the chain with it.
  M  model: the photo == patches/halation/verify.py model(), bit for bit: three tints, direct and through a window, the grid in
     the LOOKS.BIN block and from malloc; and BASE gives the same bytes on the same inputs
  E  the real 5184-wide rows across 0xd0000000 (a row in two pieces), window mode restored; a pair across the edge is left alone
  S  odd sizes: one strip, a last strip cut short, less than a band of rows
  G  gate: Halo Off, looks without halation, MONO, no record -> photo, result and mallocs == BASE (untouched);
     halation + Grain == BASE's bytes (halation first, then the same grain)
  C  the coverage cap and an empty grid: photo untouched
  F  memory: with a LOOKS.BIN block no malloc and nothing written outside L+5824..16383; without one (EP7X, wrong tag, wrong
     back pointer, misplaced L, a grid too big for the tail) one malloc, freed, L untouched; a failed malloc and bad records:
     photo untouched, nothing to free
  A  alignment: every word and halfword access the new code makes in a traced run is aligned (the camera faults, the emulator doesn't)
  I  instructions, locks and flushes per pass, BASE and NEW; the interrupt-masked run of one lock at its worst (every pair of a row
     glows and both chroma bytes clamp; every pass A sample adds): NEW within HL_CAP, and not above BASE's for the same row
  N  the pinned scan hits of the claim re-derived by disassembly
  P  anti-brick: package reparses, restore == stock, decoded == stock + edits, only our bytes differ from BASE
  R  (--frames, slow) three camera frames from testdata (night with lights, daylight under the cap, dense) and a thin LED line:
     BASE == NEW == the model, with the per-pass table
"""
import dataclasses, importlib.util, json, struct, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


HV = _load('hl_verify_h6', ROOT / 'patches/halation/verify.py')
H6 = _load('h6_build_v', ROOT / 'patches/halation_h6/build.py')
V, B, D, HB, ST = HV.V, HV.B, HV.D, HV.HB, H6.ST
Region, execute = V.Region, V.execute
BASE, CALLER, STK, JOB, ALLOC, HEAP_U, HEAP_C = V.BASE, V.CALLER, V.STK, V.JOB, V.ALLOC, V.HEAP_U, V.HEAP_C
P_AT, H = D.P_AT, D.H
P = P_AT + H
L_AT = ST.POOL2 + 5 * ST.BLOCK2                   # a class-2 block start, as fm_load's malloc returns
LOCK, UNLOCK = 0x6006a922, 0x6006a96b
PROBE = 0x18020000                                # emulator only: counts gc_open's locks (ALLOC+64); the one that takes ALLOC+68 to 0 passes `hit`
REAL_BUS, PITCH = 0xce9d4b80, 10368               # the camera's 0x0302 buffer (docs/GRAIN_PORT.md)
FRAMES = (('night with lights', 'testdata/camera_v025/PB061747.JPG'), ('daylight under the cap', 'testdata/PA211016*.JPG'), ('dense', 'testdata/PA211062*.JPG'))   # by camera file number


# ------------------------------------------------------------------ the model, vectorised for whole frames (== HV.model, checked in M)
def model_np(pic, w, h, st, tint, gmax):
    a = np.frombuffer(pic, dtype=np.uint8).reshape(h, st * 2)
    gw, gh = (w + 63) >> 6, (h + 63) >> 6
    ys = np.arange(2, h, 4)
    e = np.maximum(a[2:h:4, 0:2 * w:4].astype(np.int64) - HB.THR, 0) >> 2
    tmp = np.zeros((len(ys), gw), dtype=np.int64)
    np.add.at(tmp, (slice(None), np.arange(0, w, 2) >> 6), e)
    g = np.zeros((gh, gw), dtype=np.int64)
    np.add.at(g, (ys >> 6, slice(None)), tmp)
    g = np.minimum(g, 248)
    for axis in (1, 0):
        for _ in range(2):
            t = np.pad(g, [(0, 0), (1, 1)] if axis else [(1, 1), (0, 0)])
            g = (t[:, :-2] + 2 * t[:, 1:-1] + t[:, 2:] + 2) >> 2 if axis else (t[:-2] + 2 * t[1:-1] + t[2:] + 2) >> 2
    u = np.minimum(255, (21 * g) >> 3)
    g = (((u * (511 - u)) >> 8) * gmax) >> 8
    cnt = int((g >= 16).sum())
    if cnt == 0 or 3 * cnt > gw * gh:
        return pic, cnt, None
    fy = np.arange(h) - 32
    g0 = np.where(fy >= 0, fy >> 6, 0); t = np.where(fy >= 0, fy & 63, 0); g1 = np.minimum(g0 + 1, gh - 1)
    lv = (64 * g[g0] + (g[g1] - g[g0]) * t[:, None]) >> 6
    A, Bv = lv[:, np.clip(np.arange(gw + 1) - 1, 0, gw - 1)], lv[:, np.clip(np.arange(gw + 1), 0, gw - 1)]
    v = 64 * A[:, :, None] + 2 * (Bv - A)[:, :, None] * np.arange(32)[None, None, :]
    gp = ((v >> 6) & 0xff).reshape(h, (gw + 1) * 32)[:, 16:16 + w // 2].astype(np.int32)
    rowany = g.any(axis=1)
    gp = np.where((rowany[g0] | rowany[g1])[:, None], gp, 0)
    dy, d0, d1 = tint
    out = a.copy()
    y0 = a[:, 0:2 * w:4].astype(np.int32); c0 = a[:, 1:2 * w:4].astype(np.int32)
    y1 = a[:, 2:2 * w:4].astype(np.int32); c1 = a[:, 3:2 * w:4].astype(np.int32)
    t0 = (255 - y0) * gp
    out[:, 0:2 * w:4] = y0 + ((dy * t0) >> 16)
    out[:, 2:2 * w:4] = y1 + ((dy * ((255 - y1) * gp)) >> 16)
    out[:, 1:2 * w:4] = np.clip(c0 + ((d0 * t0) >> 16), 0, 255)
    out[:, 3:2 * w:4] = np.clip(c1 + ((d1 * t0) >> 16), 0, 255)
    return out.tobytes(), cnt, gp


def frame_from_jpeg(path, w=5184, h=3888):
    """A camera JPEG as the 0x0302 buffer (Y0 Cb Y1 Cr per pixel pair, pitch 2 w)."""
    from PIL import Image
    im = Image.open(path).convert('YCbCr')
    if im.size != (w, h):
        raise SystemExit(f'{path}: {im.size}')
    a = np.asarray(im).astype(np.int64)
    out = np.empty((h, w * 2), dtype=np.uint8)
    out[:, 0::2] = a[:, :, 0]
    out[:, 1::4] = (a[:, 0::2, 1] + a[:, 1::2, 1] + 1) // 2
    out[:, 3::4] = (a[:, 0::2, 2] + a[:, 1::2, 2] + 1) // 2
    return out.tobytes()


def led_frame(w=5184, h=3888):
    """A thin LED strip on a dark, noisy wall: a 3 px line at a slant, clipped, with a 1 px soft edge."""
    rng = np.random.default_rng(11)
    y = 28 + rng.integers(-6, 7, size=(h, w))
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.abs((yy - 1500) - 0.18 * (xx - 800))
    on = (xx > 800) & (xx < 4300)
    y = np.where(on & (d <= 1.5), 255, np.where(on & (d <= 2.5), 150, y))
    a = np.empty((h, w * 2), dtype=np.uint8)
    a[:, 0::2] = np.clip(y, 0, 255)
    a[:, 1::4] = 128 + rng.integers(-3, 4, size=(h, w // 2))
    a[:, 3::4] = 128 + rng.integers(-3, 4, size=(h, w // 2))
    return a.tobytes()


# ------------------------------------------------------------------ the run
def probed(q, gc):
    """gc_open's `call ep7_lock,[d2],8` goes through a counter first (the photo locks of halation and grain; not the ones nested in the mode restore)."""
    code, _, sy, _ = HB.SB3.assemble(f''' .global _start
_start:
 mov ({ALLOC + 64:#x}),d1
 inc d1
 mov d1,({ALLOC + 64:#x})
 mov ({ALLOC + 68:#x}),d1
 add -1,d1
 mov d1,({ALLOC + 68:#x})
 bne 1f
hit:
 nop
1:
 jmp ep7_lock
''', PROBE, dict(ep7_lock=LOCK))
    at = int(gc['gc_open'], 16) + 3
    if q[at - BASE:at - BASE + 7] != b'\xdd' + struct.pack('<i', LOCK - at) + b'\x80\x08':
        raise SystemExit('gc_open: call ep7_lock,[d2],8 not found')
    q = bytearray(q)
    q[at + 1 - BASE:at + 5 - BASE] = struct.pack('<i', PROBE - at)
    return bytes(q), code, sy['hit']


def stub(im, gc):
    return probed(HV.wdt_stub(HV.dly_stub(B.stubbed(im, gc, B.slot_table()))), gc)


def regions(q, gc, j, bus, pic, tbl, fail=0, block=True, looks='ok', l_at=L_AT, capture_pic=True):
    """As patches/halation/verify.py regions(), with section 5, the LOOKS.BIN block and every writable region captured (a run can
    then go on from a stop). looks: 'ok', None (fm_load never ran), 'x' (EP7X), 'badtag', 'badback'; l_at: what P+1016 holds."""
    qq, probe, _ = q
    wr = b'\xfc\xff' + struct.pack('<i', int(gc['gc_gs'], 16) - CALLER) + b'\xcb'
    p = bytearray(2048); p[0:4] = b'EP7B'; p[32:32 + 512] = tbl
    if block:
        struct.pack_into('<I', p, 1000, HEAP_U)
    lb = bytearray(struct.pack('<I', 0x5a5a0000) * (ST.BLOCK2 // 4))
    if looks:
        struct.pack_into('<II', p, 1016, l_at, ST.XMAGIC if looks == 'x' else ST.FMAGIC)
        struct.pack_into('<II', lb, ST.LTAG, ST.LMAGIC if looks != 'badtag' else ST.LMAGIC ^ 1, P if looks != 'badback' else P + 4)
    st = bytearray(8); struct.pack_into('<H', st, 2, H + 1)
    hu = bytearray(0x100000)
    if block:
        struct.pack_into('<I', hu, 0, HV.GDIA)
    sl = lambda lo, hi, name: Region(name, lo, qq[lo - BASE:hi - BASE], 'rx')
    r = [sl(0x60020020, 0x60100000, 'low'), sl(0x601de000, 0x601df000, 'blk0'), sl(0x601df000, 0x601e4000, 'blk'), sl(0x60350000, 0x60360000, 'isp'),
         sl(0x60210000, 0x60211000, 'sec1'), sl(0x6055e000, 0x6055f000, 'sec2'), sl(0x605b7000, 0x605b8000, 'sec3'), sl(0x61242000, 0x61243000, 'sec6'),
         sl(0x607b6000, 0x607c9000, 'sec5'), Region('probe', PROBE, probe, 'rx'),
         Region('caller', CALLER, wr, 'rx'), Region('stk', STK, bytes(0x4000), 'rw', True), Region('job', JOB, bytes(j), 'rw', True),
         Region('alloc', ALLOC, struct.pack('<IIIIII', HEAP_U + 0x10000, fail, 0, 0, 0, 0) + bytes(64), 'rw', True), Region('heap', HEAP_C, bytes(0x100000), 'rw', True),
         Region('heapu', HEAP_U, bytes(hu), 'rw', True), Region('pool', P, bytes(p), 'rw', True), Region('st', 0x622cbcc0, bytes(st), 'rw', True),
         Region('lblk', L_AT, bytes(lb), 'rw', True), Region('cpu', 0x8000, bytes(0x100), 'rw', True), Region('magic', 0x8ff00000, bytes(0x1000), 'rw', True),
         Region('c0', 0x28900000, bytes(0x1000), 'rw', True), Region('c1', 0x28980000, bytes(0x1000), 'rw', True), Region('c2', 0x28a00000, bytes(0x1000), 'rw', True),
         Region('c3', 0x28a80000, bytes(0x1000), 'rw', True), Region('win', 0x98100000, bytes(0x1000), 'rw', True), Region('modes', V.MODES & ~0xff, bytes(0x100), 'rw', True),
         Region('wdtf', 0x6203ba00, struct.pack('<8xH6x', 1), 'r')]
    if bus < 0xb0000000:
        r.append(Region('pic', bus - 0x40000000, bytes(pic), 'rw', capture_pic))
    else:
        base = lambda b: (0x78000000 if (b >> 27) in (0x17, 0x1b) else 0x70000000) | (b & 0x07ffffff)   # gc_btab
        cut = min(len(pic), ((bus >> 27) + 1 << 27) - bus)
        r.append(Region('pic', base(bus), bytes(pic[:cut]), 'rw', capture_pic))
        if cut < len(pic):
            r.append(Region('pic2', base(bus + cut), bytes(pic[cut:]), 'rw', capture_pic))
    return r


def go(rg, regs, stop, breakpoints=(), trace=False, limit=4_000_000_000):
    """The engine across its 100 M limit, to the stop address, a breakpoint or a fault -> (regions as they are now, registers, result, instructions)."""
    n = 0
    while True:
        r = execute(rg, regs, stop, limit=min(100_000_000, limit - n) if not trace else 100_000, timeout=3600, breakpoints=list(breakpoints),
                    changed_captures=True, trace_limit=100_000 if trace else 0)
        n += r['attempted']
        got = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}
        rg = [dataclasses.replace(x, data=got[x.name]) if x.name in got else x for x in rg]
        regs = dict(r['registers'])
        if r['status'] != 'instruction_limit' or n >= limit or trace:
            return rg, regs, r, n


def run(q, gc, pic, w, h, st, tbl, bus=0xa4000000, phases=(), traces=None, jkw=None, **kw):
    """One capture job through gc_gs. phases: addresses that split the count (each is passed once). -> dict."""
    rg = regions(q, gc, HV.job(bus, w, h, st, **(jkw or {})), bus, pic, tbl, **kw)
    regs = {'pc': CALLER, 'sp': STK + 0x3000, 'a0': JOB, 'd2': 0x2222, 'd3': 0x3333, 'a2': 0xa2a2, 'a3': 0xa3a3}
    left, n, marks = list(phases), 0, []
    lblk0 = next(x for x in rg if x.name == 'lblk').data

    def cnt(rg_):
        al_ = next(x for x in rg_ if x.name == 'alloc').data
        return struct.unpack_from('<I', al_, 64)[0], struct.unpack_from('<I', al_, 20)[0]
    while True:
        rg, regs, r, k = go(rg, regs, CALLER + 6, breakpoints=left, trace=traces is not None)
        n += k
        if traces is not None:
            traces.append(r['trace'])
            if r['status'] == 'instruction_limit':
                continue
        if r['status'] == 'breakpoint' and regs['pc'] in left:
            left.remove(regs['pc'])
            marks.append((n,) + cnt(rg))
            continue
        break
    m = {x.name: x.data for x in rg}
    al = struct.unpack('<IIIIII', m['alloc'][:24])
    marks.append((n, struct.unpack_from('<I', m['alloc'], 64)[0], al[5]))
    ok = not r['fault'] and r['status'] == 'returned' and regs['pc'] == CALLER + 6 and regs['sp'] == STK + 0x3000 and \
        (regs['d2'], regs['d3'], regs['a2'], regs['a3']) == (0x2222, 0x3333, 0xa2a2, 0xa3a3)
    per = [(b[0] - a[0], b[1] - a[1], b[2] - a[2]) for a, b in zip([(0, 0, 0)] + marks[:-1], marks)]     # instructions, locks, flushes
    return dict(ok=ok, fault=r['fault'], status=r['status'], d0=regs['d0'], pic=m['pic'] + m.get('pic2', b''), m=m, lblk0=lblk0, mallocs=(al[0] - HEAP_U - 0x10000) // 0x10000,
                frees=al[2], flushes=al[5], locks=marks[-1][1], n=n, per=per, modes=struct.unpack_from('<I', m['modes'], V.MODES & 0xff)[0])


def masked(q, gc, pic, w, h, st, tbl, at, nth, **kw):
    """The run of one lock, in instructions: the nth lock taken after the address `at` is reached, up to its unlock (direct buffer: no nested lock)."""
    rg = regions(q, gc, HV.job(0xa4000000, w, h, st), 0xa4000000, pic, tbl, capture_pic=True, **kw)
    regs = {'pc': CALLER, 'sp': STK + 0x3000, 'a0': JOB, 'd2': 0x2222, 'd3': 0x3333, 'a2': 0xa2a2, 'a3': 0xa3a3}
    rg, regs, r, _ = go(rg, regs, CALLER + 6, breakpoints=[at])
    if r['status'] != 'breakpoint':
        return None
    al = bytearray(next(x for x in rg if x.name == 'alloc').data); struct.pack_into('<I', al, 68, nth)
    rg = [dataclasses.replace(x, data=bytes(al)) if x.name == 'alloc' else x for x in rg]
    rg, regs, r, _ = go(rg, regs, CALLER + 6, breakpoints=[q[2]])
    if r['status'] != 'breakpoint':
        return None
    rg, regs, r, k = go(rg, regs, CALLER + 6, breakpoints=[UNLOCK])
    return k if r['status'] == 'breakpoint' else None


TINT = HV.TINT
slots, gm, scene, model = HV.slots, HV.gm, HV.scene, HV.model
LIGHTS = [(300, 260, 6), (1400, 800, 14), (840, 1300, 3)]


def t_model(qo, q, gc):
    bad, n = [], 0
    w, h, st = 2048, 1536, 2064
    pic = scene(w, h, st, LIGHTS)
    for cls, looks, (tint, strength, eff), old in (('direct', 'ok', (1, 4, 1), True), ('c8', None, (0, 2, 2), True), ('direct', 'ok', (4, 5, 2), False), ('d8', 'ok', (2, 3, 2), False)):
        bus = V.CLASSES[cls][0]
        want, cnt = model(pic, w, h, st, TINT[HB.ORDER[max(tint, 1) - 1]], gm(eff, strength, tint))
        r = run(q, gc, pic, w, h, st, slots(eff, strength, tint), bus=bus, looks=looks)
        n += 1
        good = r['ok'] and r['pic'] == want and want != pic and (r['mallocs'], r['frees']) == ((0, 0) if looks else (1, 1)) and r['modes'] == 0
        if good and cls == 'direct' and tint == 1:
            good = model_np(pic, w, h, st, TINT['red'], gm(eff, strength, tint))[0] == want                    # the whole-frame model R uses
        if good and old:
            a = run(qo, gc, pic, w, h, st, slots(eff, strength, tint), bus=bus, looks=looks)
            good = a['ok'] and a['pic'] == r['pic'] and a['d0'] == r['d0'] and a['mallocs'] == 3
        if not good:
            bad.append((cls, looks, tint, r['fault'], r['status'], r['pic'] == want, r['mallocs'], r['frees']))
    return bad, n


def t_edge(qo, q, gc):
    bad, n = [], 0
    edge = 0xd0000000
    k = (edge - REAL_BUS) % PITCH
    bus = edge - k - 64 * PITCH
    rows, st = 70, 5184
    pic = scene(5184, rows, st, [(2600, 64, 10), (5100, 30, 20)], seed=5)
    want, cnt = model(pic, 5184, rows, st, TINT['red'], gm(2, 4, 1))
    r = run(q, gc, pic, 5184, rows, st, slots(2, 4, 1), bus=bus)
    a = run(qo, gc, pic, 5184, rows, st, slots(2, 4, 1), bus=bus)
    n += 1
    if not (r['ok'] and r['pic'] == want and want != pic and r['modes'] == 0 and r['mallocs'] == 0 and a['pic'] == r['pic']):
        bad.append(('edge', r['fault'], r['pic'] == want, a['pic'] == r['pic'], r['modes']))
    # rows 2 bytes off a 4-byte boundary: on row 64 one pair lies across the edge and stays as it was; every other pair is the model's
    pair = (k - 2) >> 2
    pic = scene(5184, rows, st, [(2 * pair + 32, 60, 10), (5100, 30, 20)], seed=5)    # a light 32 px from it: the model changes that pair
    want, cnt = model(pic, 5184, rows, st, TINT['red'], gm(2, 4, 1))
    o = 64 * PITCH + 4 * pair
    exp = bytearray(want); exp[o:o + 4] = pic[o:o + 4]
    r = run(q, gc, pic, 5184, rows, st, slots(2, 4, 1), bus=bus + 2)
    n += 1
    if not (r['ok'] and r['pic'] == bytes(exp) and want[o:o + 4] != pic[o:o + 4] and r['modes'] == 0):
        bad.append(('pair across the edge', r['fault'], r['pic'] == bytes(exp), want[o:o + 4] != pic[o:o + 4]))
    return bad, n


def t_sizes(qo, q, gc):
    bad, n = [], 0
    for w, h, st, lights in ((64, 1, 64, []), (64, 2, 64, []), (64, 40, 64, [(30, 10, 6)]), (68, 40, 80, [(40, 20, 9)]), (1000, 130, 1004, [(500, 70, 12), (990, 100, 8), (6, 3, 5)]),
                             (132, 97, 140, [(66, 50, 10)]), (192, 33, 192, [(100, 30, 8)]), (8192, 8, 8192, [(4000, 2, 9)])):
        pic = scene(w, h, st, lights, seed=w + h)
        want, cnt = model(pic, w, h, st, TINT['amber'], HB.GMAX[2])
        r = run(q, gc, pic, w, h, st, slots(0, 0, 2, halo=4))
        n += 1
        if not (r['ok'] and r['pic'] == want and r['mallocs'] == 0):
            bad.append((w, h, r['fault'], r['status'], r['pic'] == want, cnt))
        if h > 2:                                                 # h2 samples row 2 whatever the height (outside a 1- or 2-row image); h6 does not
            a = run(qo, gc, pic, w, h, st, slots(0, 0, 2, halo=4))
            if not (a['ok'] and a['pic'] == r['pic'] and a['d0'] == r['d0']):
                bad.append((w, h, 'BASE', a['fault'], a['pic'] == r['pic']))
    return bad, n


def t_gate(qo, q, gc):
    bad, n = [], 0
    w, h, st = 768, 512, 768
    pic = scene(w, h, st, [(330, 250, 10)], seed=9)
    off = [('Halo Off on CineStill', slots(1, 4, 1, halo=1), {}, True), ('bad +52', slots(2, 3, 1, halo=9), {}, True), ('none', slots(0, 0), {}, True), ('glow', slots(1, 3), {}, True),
           ('clarity', slots(3, 3, 1), {}, True), ('tint 5', slots(2, 3, 5), {}, True), ('MONO', slots(2, 4, 1), dict(mode=12, key=12), True), ('no record', slots(2, 3, 1), {}, False)]
    for name, tb, jkw, block in off:
        a = run(qo, gc, pic, w, h, st, tb, jkw=jkw, block=block)
        b = run(q, gc, pic, w, h, st, tb, jkw=jkw, block=block)
        n += 1
        if not (a['ok'] and b['ok'] and a['pic'] == b['pic'] == pic and a['d0'] == b['d0'] and b['mallocs'] == a['mallocs'] and b['frees'] == a['frees'] and b['locks'] == a['locks'] == 0
                and b['m']['lblk'] == a['m']['lblk']):
            bad.append((name, b['fault'], a['pic'] == b['pic'], b['mallocs'], a['mallocs'], b['locks']))
    for name, tb, looks, own in (('Med red + Grain Med', slots(2, 3, 1, grain=2), 'ok', 0), ('High amber + Grain High, no LOOKS.BIN', slots(2, 5, 2, grain=3), None, 1),
                                 ('Low on a plain look', slots(0, 0, 0, halo=2), 'ok', 0)):
        a = run(qo, gc, pic, w, h, st, tb, looks=looks)
        b = run(q, gc, pic, w, h, st, tb, looks=looks)
        n += 1
        if not (a['ok'] and b['ok'] and a['pic'] == b['pic'] != pic and a['d0'] == b['d0'] and b['mallocs'] == a['mallocs'] - 3 + own and b['frees'] == a['frees'] - 3 + own):
            bad.append((name, b['fault'], a['pic'] == b['pic'], a['mallocs'], b['mallocs'], a['frees'], b['frees']))
    return bad, n


def t_cover(qo, q, gc):
    bad, n = [], 0
    w, h, st = 256, 192, 256
    for name, pic in (('daylight', scene(w, h, st, [], wall=0.6, seed=4)), ('no highlights', scene(w, h, st, [], seed=6))):
        r = run(q, gc, pic, w, h, st, slots(2, 5, 1))
        a = run(qo, gc, pic, w, h, st, slots(2, 5, 1))
        n += 1
        if not (r['ok'] and r['pic'] == pic == a['pic'] and r['mallocs'] == 0 and r['m']['lblk'][:H6.L_LO] == a['m']['lblk'][:H6.L_LO]):
            bad.append((name, r['fault'], r['pic'] == pic))
    return bad, n


def t_memory(qo, q, gc):
    bad, n = [], 0
    w, h, st = 768, 512, 768
    pic = scene(w, h, st, [(330, 250, 10)], seed=9)
    want, _ = model(pic, w, h, st, TINT['red'], gm(2, 3, 1))
    a = run(qo, gc, pic, w, h, st, slots(2, 3, 1))
    base = a['m']['lblk']                                                      # h2 never touches L
    if base != a['lblk0']:
        bad.append(('BASE wrote L',))
    cells = ((w + 63) >> 6) * ((h + 63) >> 6)
    for name, kw, mallocs in (('LOOKS.BIN block', dict(looks='ok'), 0), ('EP7X', dict(looks='x'), 1), ('fm_load not run', dict(looks=None), 1), ('wrong tag', dict(looks='badtag'), 1),
                              ('wrong back pointer', dict(looks='badback'), 1), ('L off by 2', dict(l_at=L_AT + 2), 1), ('L outside the pool', dict(l_at=HEAP_U + 0x80000), 1),
                              ('L at the pool end', dict(l_at=ST.POOL2_END - H6.L_HI + 4), 1)):
        r = run(q, gc, pic, w, h, st, slots(2, 3, 1), **kw)
        lb, l0 = r['m']['lblk'], r['lblk0']
        n += 1
        kept = lb[:H6.L_LO] == l0[:H6.L_LO] and lb[H6.L_HI:] == l0[H6.L_HI:] and (mallocs or lb[H6.L_LO + (cells + 3 & ~3):H6.L_HI] == l0[H6.L_LO + (cells + 3 & ~3):H6.L_HI])
        if not (r['ok'] and r['pic'] == want != pic and (r['mallocs'], r['frees']) == (mallocs, mallocs) and kept and (not mallocs or lb == l0) and (mallocs or lb != l0)):
            bad.append((name, r['fault'], r['pic'] == want, r['mallocs'], r['frees'], kept))
    r = run(q, gc, pic, w, h, st, slots(2, 3, 1), looks=None, fail=1)            # the one malloc fails
    n += 1
    if not (r['ok'] and r['pic'] == pic and r['frees'] == 0 and r['locks'] == 0):
        bad.append(('malloc fails', r['fault'], r['pic'] == pic, r['frees']))
    for name, jkw, bus in (('format', dict(fmt=0x0305), 0xa4000000), ('x', dict(x=4), 0xa4000000), ('size', dict(size=100), 0xa4000000), ('bus', {}, 0x90000000), ('bus c0', {}, 0xc1000000)):
        rg = regions(q, gc, HV.job(bus, w, h, st, **jkw), 0xa4000000, pic, slots(2, 3, 1))
        rg, regs, r, _ = go(rg, {'pc': CALLER, 'sp': STK + 0x3000, 'a0': JOB, 'd2': 0x2222, 'd3': 0x3333, 'a2': 0xa2a2, 'a3': 0xa3a3}, CALLER + 6)
        m = {x.name: x.data for x in rg}
        n += 1
        if not (not r['fault'] and r['status'] == 'returned' and m['pic'] == pic and m['lblk'] == base and struct.unpack_from('<I', m['alloc'], 0)[0] == HEAP_U + 0x10000 and
                struct.unpack_from('<I', m['alloc'], 64)[0] == 0):
            bad.append((name, r['fault'], m['pic'] == pic))
    # a grid that does not fit the tail (128 x 83 cells > 10560): malloc, as without a LOOKS.BIN
    w, h = 8192, 5249
    pic = bytes(2 * w * h)
    rg = regions(q, gc, HV.job(0xa8000000, w, h, w), 0xa8000000, pic, slots(2, 3, 1), capture_pic=False)
    rg, regs, r, _ = go(rg, {'pc': CALLER, 'sp': STK + 0x3000, 'a0': JOB, 'd2': 0x2222, 'd3': 0x3333, 'a2': 0xa2a2, 'a3': 0xa3a3}, CALLER + 6)
    m = {x.name: x.data for x in rg}
    al = struct.unpack('<IIIIII', m['alloc'][:24])
    n += 1
    if not (not r['fault'] and r['status'] == 'returned' and ((al[0] - HEAP_U - 0x10000) // 0x10000, al[2]) == (1, 1) and m['lblk'] == base):
        bad.append(('grid over the tail', r['fault'], r['status'], al[0], al[2]))
    return bad, n


def t_align(new, q, gc, sy):
    """Every load and store of a word or halfword in the new code, in whole traced runs, checked for natural alignment."""
    import re
    code = new[H6.AT - BASE:sy['h6_tint'] - BASE]
    ins = {a: (op, args) for a, op, args in H6.B3.disasm(code, H6.AT, sy['h6_tint'])}
    bad, n, seen = [], 0, set()
    for w, h, st, lights, bus, looks in ((196, 200, 200, [(100, 100, 3)], 0xa4000000, 'ok'), (448, 136, 448, [(200, 70, 4)], 0xd0000000 - 70 * 896 - 400, None)):
        pic = scene(w, h, st, lights, seed=6)                    # the second one crosses 0xd0000000 inside row 70
        tr = []
        r = run(q, gc, pic, w, h, st, slots(2, 5, 1), bus=bus, looks=looks, traces=tr)
        if not (r['ok'] and r['pic'] == model(pic, w, h, st, TINT['red'], HB.GMAX[2])[0] != pic):
            bad.append(('run', w, h, r['fault'], r['status']))
        for chunk in tr:
            for row in chunk:
                pc = row['pc']
                if pc not in ins:
                    continue
                seen.add(pc)
                op, args = ins[pc]
                size = {'mov': 4, 'movhu': 2}.get(op)
                m = re.search(r'\(([^)]*)\)', args)
                if not size or not m:
                    continue
                addr = sum(row[p_] if p_ in row else int(p_, 0) for p_ in (x.strip() for x in m.group(1).split(',')))
                n += 1
                if addr % size:
                    bad.append((hex(pc), op, args, hex(addr & 0xffffffff)))
    never = sorted(a for a, (op, args) in ins.items() if a not in seen and op in ('mov', 'movhu') and '(' in args and 'sp)' not in args)
    return bad, n, len(seen), len(ins), never


def worst_c(w=5184, h=1280):
    """Every pair of the rows around a lit strip glows, and both chroma bytes clamp (red: C0 at 0 goes down, C1 at 255 goes up)."""
    a = np.zeros((h, 2 * w), np.uint8); a[:, 3::4] = 255
    a[608:672, 0::2] = 255
    return a.tobytes()


def t_table(qo, q, gc, so, sn, cap):
    w, h, st = 2048, 1536, 2064
    pic = scene(w, h, st, LIGHTS)
    out, rows = [], []
    for name, qq, ph in (('BASE', qo, [so[k] for k in ('hl_pa', 'hl_pb', 'hl_pc', 'hl_x98')]), ('NEW', q, [sn[k] for k in ('h6_pa', 'h6_pb', 'h6_pc', 'h6_exit')])):
        r = run(qq, gc, pic, w, h, st, slots(2, 5, 1), phases=ph)
        rows.append(r)
        out.append(f'      {name:4s} 2048 x 1536, three lights: ' + ', '.join(f'{p} {i:,} / {l} / {f}' for p, (i, l, f) in zip('ABC', r['per'][1:4])) + f'; total {r["n"]:,} (instructions / locks / flushes)')
    good = rows[0]['pic'] == rows[1]['pic'] and all(b[0] <= 0.7 * a[0] for a, b in zip((rows[0]['per'][1], rows[0]['per'][3]), (rows[1]['per'][1], rows[1]['per'][3])))
    # one lock at its worst: pass C, every pair of the row glows and clamps; pass A, every sample adds
    W = 5184
    pc = worst_c()
    pa = (np.zeros((64, 2 * W), np.uint8) + np.tile(np.array([229, 128], np.uint8), W)).tobytes()
    mo = masked(qo, gc, pc, W, 1280, W, slots(2, 5, 1), so['hl_pc'], 120)
    mn = masked(q, gc, pc, W, 1280, W, slots(2, 5, 1), sn['h6_pc'], 120)
    ao = masked(qo, gc, pa, W, 64, W, slots(2, 5, 1), so['hl_pa'], 1)
    an = masked(q, gc, pa, W, 64, W, slots(2, 5, 1), sn['h6_pa'], 1)
    out.append(f'      one lock at its worst, instructions masked: pass C (a row, every pair glows and clamps) BASE {mo} NEW {mn}; pass A (every sample adds) BASE {ao} (1 row) NEW {an} (the rows of one lock); cap {cap}')
    good = good and None not in (mo, mn, ao, an) and mn <= cap and an <= cap and mn <= mo
    return good, out


def t_frames(qo, q, gc, so, sn):
    """--frames: the camera frames at the camera's bus address, High red, LOOKS.BIN loaded."""
    out, good = [], True
    frames = [(n_, next(iter(sorted(ROOT.glob(f))), ROOT / f)) for n_, f in FRAMES] + [('thin LED line', None)]
    for name, path in frames:
        if path is not None and not path.exists():
            out.append(f'      {name}: {path.name} not here, skipped'); continue
        pic = frame_from_jpeg(path) if path else led_frame()
        want, cnt, gp = model_np(pic, 5184, 3888, 5184, TINT['red'], HB.GMAX[2])
        res = []
        for tag, qq, ph in (('BASE', qo, [so[k] for k in ('hl_pa', 'hl_pb', 'hl_pc', 'hl_x98')]), ('NEW', q, [sn[k] for k in ('h6_pa', 'h6_pb', 'h6_pc', 'h6_exit')])):
            r = run(qq, gc, pic, 5184, 3888, 5184, slots(2, 5, 1), bus=REAL_BUS, phases=ph)
            res.append(r)
            out.append(f'      {name}, {tag}: ' + ', '.join(f'{p} {i:,} / {l} / {f}' for p, (i, l, f) in zip('ABC', r['per'][1:4])) + f'; total {r["n"]:,}; mallocs {r["mallocs"]}')
        same = res[0]['ok'] and res[1]['ok'] and res[0]['pic'] == res[1]['pic'] == want and want != pic and res[1]['mallocs'] == 0
        out.append(f'      {name}: BASE == NEW == model: {same} ({0 if gp is None else int((gp > 0).sum()):,} pairs with glow)')
        good &= same
    return good, out


def t_pkg(base_s, new_s, new, pkg, rst, info, disk, old, sy):
    sb = {b.kind: b for b in V.oc.parse(V.BP.STOCK.read_bytes())}
    good = True
    for b in V.oc.parse(pkg):
        exp = bytearray(sb[b.kind].payload)
        for e in new_s['edits']:
            if int(e['kind'], 16) == b.kind:
                o = V.BP.resolve(b.kind, e['addr']); nb = bytes.fromhex(e['new']); exp[o:o + len(nb)] = nb
        good &= bytes(exp) == b.payload
        if b.kind == 0x100:
            good &= b.payload == new
    for b in V.oc.parse(rst):
        good &= b.payload == sb[b.kind].payload
    ours = [(H6.AT, sy['h6_end'] - H6.AT), (H6.HL_RUN, 5)] + [(int(e['addr'], 16), len(e['new']) // 2) for s_ in (base_s, new_s) for e in s_['edits']
                                                                 if e.get('source') == 'patches/fw_version']          # the version text, if BASE has another
    diff = [BASE + i for i in np.nonzero(np.frombuffer(old, np.uint8) != np.frombuffer(new, np.uint8))[0]]
    stray = [hex(a) for a in diff if not any(s_ <= a < s_ + k for s_, k in ours)]
    good &= not stray and new[H6.CLAIM[0] - BASE:H6.AT - BASE] == old[H6.CLAIM[0] - BASE:H6.AT - BASE] and new[H6.CLAIM[1] - H6.GUARD - BASE:H6.CLAIM[1] - BASE] == old[H6.CLAIM[1] - H6.GUARD - BASE:H6.CLAIM[1] - BASE]
    if disk:
        good &= (disk / 'patched.pkg.bin').read_bytes() == pkg and (disk / 'restore-stock.pkg.bin').read_bytes() == rst
    return good, f'{info["edits"]} edits, {info["changed_payload_bytes"]} B; {len(diff)} B differ from BASE; stray {stray[:6]}'


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    base_s, new_s = (json.loads(Path(p).read_text()) for p in args[:2])
    disk = Path(args[2]) if len(args) > 2 else None
    if 'halation_h6' in base_s or 'halation_h6' not in new_s:
        raise SystemExit('BASE without the layer, NEW with it')
    old, *_ = V.image(base_s)
    new, pkg, rst, info = V.image(new_s)
    gc = new_s['grain_cpu']['symbols']
    so = {k: int(v, 16) for k, v in base_s['halation']['symbols'].items()}
    sn = {k: int(v, 16) for k, v in new_s['halation_h6']['symbols'].items()}
    qo, q = stub(old, gc), stub(new, gc)
    ok = True
    for name, fn in (('M model, and BASE the same bytes', lambda: t_model(qo, q, gc)), ('E 0xd0000000 edge, 5184 x 70', lambda: t_edge(qo, q, gc)), ('S odd sizes', lambda: t_sizes(qo, q, gc)),
                     ('G gate, halation + grain', lambda: t_gate(qo, q, gc)), ('C coverage', lambda: t_cover(qo, q, gc)), ('F memory and failures', lambda: t_memory(qo, q, gc))):
        bad, n = fn(); ok &= not bad
        print(f"{'PASS' if not bad else 'FAIL'} {name}: {n - len(bad)}/{n}", bad[:5] if bad else '', flush=True)
    bad, n, seen, total, never = t_align(new, q, gc, sn); ok &= not bad
    print(f"{'PASS' if not bad else 'FAIL'} A alignment: {n} word / halfword accesses, {seen} of {total} instructions run", bad[:5] if bad else '',
          f'; never run: {[hex(a) for a in never]}' if never else '', flush=True)
    good, out = t_table(qo, q, gc, so, sn, new_s['halation_h6']['cap']); ok &= good
    print(f"{'PASS' if good else 'FAIL'} I instructions / locks / flushes per pass; the masked run of a lock"); print('\n'.join(out), flush=True)
    if '--frames' in sys.argv:
        good, out = t_frames(qo, q, gc, so, sn); ok &= good
        print(f"{'PASS' if good else 'FAIL'} R camera frames"); print('\n'.join(out), flush=True)
    bad = H6.pin_reasons(new); ok &= not bad
    print(f"{'PASS' if not bad else 'FAIL'} N pinned scan hits: {len(H6.PINS) - len(bad)}/{len(H6.PINS)}", bad or '', flush=True)
    good, txt = t_pkg(base_s, new_s, new, pkg, rst, info, disk, old, sn); ok &= good
    print(f"{'PASS' if good else 'FAIL'} P anti-brick: {txt}")
    print('ALL PASS' if ok else 'FAILURES')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
