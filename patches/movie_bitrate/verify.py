#!/usr/bin/env python3
"""movie_bitrate checks (emulator, real code from the built packages). Offline. Minimal + anti-brick.

  .venv/bin/python -I patches/movie_bitrate/verify.py BASE.json NEW.json [PKGDIR]

BASE = the same chain without the layer (v0.34a: v0.33b + version label), NEW = with it, PKGDIR = tools/build_package.py output.

  E  encoder parameter block: the real builder 0x603d132c (-> 0x603d1372, 0x603d13e4 -> 0x603d14d9, 0x603d1620, 0x603d1b17)
     on a 36-B AVM REC_INIT command for 4K 30/25/24p (also at speed 50 %), C4K, FHD SF/F/N/ALL-I at every fps, HD, the small
     size and high-speed movie. The 284-B block, the path record, the quantiser RAM and d2 d3 a2 a3 sp pc must equal BASE
     except: word 24 ulBitRate (4K: 150 M; x speed % / 100 in 32 bits, which wraps above 28 % as stock 100 M wraps above 42 %,
     only reachable with speed < 100, which the 4K slots' validator does not offer), word 25 ulMaxBitrate (157.5 M wherever BASE has 105 M) and word 17
     ulMaxRecTime (the per-file duration from S, fed in as cmd+0x10). The three `call 0x47001052` (a routine outside main,
     word 11 brand) and the high-speed bundle calls 0x603d8c15 / 0x603d5405 are stubbed to `ret`, the same in both runs.
  S  per-file split: the real 0x6031f454 -> 0x603cfb5b -> 0x603d79b3 (REC_INIT's cmd+0x10 / frames) and 0x6031f33f ->
     0x603cfb48 -> 0x603d79b3 (bytes/s and header reserve for the estimate), every mode of E: 4K gives 200 s per file
     (BASE 320 s), 19 504 500 B/s (BASE 13 067 000), the same reserve; every other mode equals BASE.
  R  remaining time: the estimate 0x603183a9 divides the free sectors by ceil(bytes/s / 512) from S (header and 4 GiB-file
     overhead terms unchanged); printed for a 64 GB card. The per-file seconds term (frames / fps = 200) stays under its clamp.
  P  anti-brick: NEW package decodes to stock + edits, restore == stock, the package files on disk match; every main byte that
     differs from BASE is inside the four edits; the other components equal BASE.
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
STACK, SP0 = 0x18010000, 0x18011800
CALLER = 0x18000000
CMD, PATH, PARAM = 0x13000000, 0x13001000, 0x13002000
QM = (0x62649e00, 0x6264a300)                      # quantiser matrices the setter copies to 0x62649ee2..0x6264a292
CELLS = (0x60539bfc, 0x60539c0c, 0x60539c1c)
CEIL_IMM = 0x603d19dd
NEW_4K, NEW_CEIL, OLD_CEIL = 150_000_000, 157_500_000, 105_000_000
BUDGET = 0xfd7fffff
M32 = 0xffffffff                                      # 0x603d1620 scales by speed as (speed x rate) / 100 in 32 bits (wraps, stock)
SIZE_AVM = {9: 5, 8: 6, 6: 1, 3: 2, 4: 4}             # settings size code -> AVM size code (0x6031f0a3)
QBIT = {5: 1, 6: 2, 1: 4, 2: 8}                       # quality code -> table column bit (0x6031f0a3 / 0x6031f33f)


def sl(im, lo, hi):
    return im[lo - BASE:hi - BASE]


def caller(target, regs, frame):
    return Region('caller', CALLER, b'\xdd' + struct.pack('<i', target - CALLER) + bytes([regs, frame]) + b'\xcb' * 9, 'rx')


def mem(r):
    return {m['name']: bytes.fromhex(m['hex']) for m in r['memory']}


def data_regions(im):
    return [Region('cdata', 0x60536800, sl(im, 0x60536800, 0x6053a300))]


# ------------------------------------------------------------------ S
def split(im, q, size, fps, speed=100):
    rec = bytearray(0x20)
    rec[0] = q; struct.pack_into('<H', rec, 2, size); rec[4] = fps; struct.pack_into('<H', rec, 6, speed)
    rg = [caller(0x6031f454, 0xe0, 60), Region('stack', STACK, bytes(0x2000), 'rw'),
          Region('c1', 0x6031f440, sl(im, 0x6031f440, 0x6031f580), 'rx'), Region('c2', 0x603cfb40, sl(im, 0x603cfb40, 0x603cfc20), 'rx'),
          Region('c3', 0x603d79b0, sl(im, 0x603d79b0, 0x603d7be8), 'rx'), *data_regions(im), Region('rec', 0x13100000, bytes(rec), 'rw', True)]
    r = execute(rg, dict(pc=CALLER, sp=SP0, a0=0x13100000, d2=0x2222, d3=0x3333, a2=0xa2a2), CALLER + 7, limit=20000)
    dur, frames = struct.unpack_from('<II', mem(r)['rec'], 8)
    rg2 = [caller(0x6031f33f, 0xf0, 64), Region('stack', STACK, bytes(0x2000), 'rw'),
           Region('c1', 0x6031f330, sl(im, 0x6031f330, 0x6031f460), 'rx'), Region('c2', 0x603cfb40, sl(im, 0x603cfb40, 0x603cfc20), 'rx'),
           Region('c3', 0x603d79b0, sl(im, 0x603d79b0, 0x603d7be8), 'rx'), *data_regions(im)]
    rec2 = bytearray(0x20)
    struct.pack_into('<H', rec2, 0, size); rec2[2] = fps; rec2[3] = q; struct.pack_into('<H', rec2, 4, speed)
    rg2.append(Region('rec', 0x13100000, bytes(rec2), 'rw', True))
    r2 = execute(rg2, dict(pc=CALLER, sp=SP0, d0=0, a0=0x13100000, d2=0x2222, d3=0x3333, a2=0xa2a2, a3=0xa3a3), CALLER + 7, limit=20000)
    buf, bps = struct.unpack_from('<II', mem(r2)['rec'], 8)
    return dict(fault=r['fault'] or r2['fault'], d0=r['registers']['d0'] & 0xffff, d0b=r2['registers']['d0'] & 0xffff,
                dur=dur, frames=frames, buf=buf, bps=bps)


# ------------------------------------------------------------------ E
def cmd_of(media, size, fps, q, speed=100, rate=None, maxrec=0):
    c = bytearray(36)
    c[0], c[1], c[2], c[3] = 0, media, 1, q
    struct.pack_into('<I', c, 4, 48000)
    struct.pack_into('<HHH', c, 8, rate or fps, fps, speed)
    struct.pack_into('<I', c, 0x10, maxrec)
    c[0x14], c[0x15], c[0x16] = 1, QBIT[q], SIZE_AVM[size]
    c[0x19] = 1 if q == 5 else 3
    c[0x1b], c[0x1c] = 1, 16
    struct.pack_into('<I', c, 0x20, 0x603178ac)
    return bytes(c)


def encode(im, cmd, extra=()):
    path = bytearray(28); struct.pack_into('<I', path, 0x10, PARAM)
    rg = [caller(0x603d132c, 0xb0, 16), Region('stack', STACK, bytes([0xa5] * 0x2000), 'rw'),
          Region('code', 0x603d1300, sl(im, 0x603d1300, 0x603d1b80), 'rx'), *data_regions(im),
          Region('s47', 0x47001040, bytes(0x12) + bytes.fromhex('dff01c') + bytes(13), 'rx'),          # ret [d2,d3,a2,a3],28
          Region('s8c15', 0x603d8c10, bytes(5) + bytes.fromhex('dff018') + bytes(8), 'rx'),           # ret [d2,d3,a2,a3],24
          Region('s5405', 0x603d5400, bytes(5) + bytes.fromhex('dfc00c') + bytes(8), 'rx'),           # ret [d2,d3],12
          Region('qm', QM[0], bytes(QM[1] - QM[0]), 'rw', True),
          Region('cmd', CMD, cmd), Region('path', PATH, bytes(path), 'rw', True), Region('param', PARAM, bytes([0xcc] * 284), 'rw', True),
          *extra]
    r = execute(rg, dict(pc=CALLER, sp=SP0, d0=1, a0=CMD, a1=PATH, d2=0x2222, d3=0x3333, a2=0xa2a2, a3=0xa3a3), CALLER + 7, limit=50000)
    m = mem(r)
    return r['fault'], {k: r['registers'][k] for k in ('d2', 'd3', 'a2', 'a3', 'sp', 'pc')}, m['param'], m['path'], m['qm']


MODES = ([('4K', 1, 8, f, 1, 100) for f in (30, 25, 24)] + [('4K', 1, 8, 30, 1, 50)] + [('C4K', 1, 9, 24, 1, 100)]
         + [('FHD', 1, 6, f, q, 100) for f in (60, 50, 30, 25, 24) for q in (6, 1, 2, 5)]
         + [('HD', 1, 3, f, q, 100) for f in (60, 30) for q in (6, 1, 2)] + [('small', 1, 4, 30, 1, 100)])


def t_split(old, new):
    bad, rows = [], {}
    for name, media, size, fps, q, sp in MODES:
        a, b = split(old, q, size, fps, sp), split(new, q, size, fps, sp)
        rows[(name, size, fps, q, sp)] = (a, b)
        if a['fault'] or b['fault'] or a['d0'] or b['d0'] or a['d0b'] or b['d0b']:
            bad.append((name, fps, q, sp, 'fault/err', a['fault'], b['fault'], a['d0'], b['d0']))
            continue
        is4k = size == 8
        if is4k:
            mb = NEW_4K * sp // 100
            want_bps = (mb // 100 * 103 + 1_536_000) >> 3
            s = (BUDGET - b['buf']) // want_bps // 40 * 40
            k = {30: (30, 1001, 2503), 25: (24, 960, 2880), 24: (24, 1001, 2503)}[fps]
            ok = b['bps'] == want_bps and b['buf'] == a['buf'] and b['frames'] == s * k[0] and b['dur'] == s * k[1] + k[2] \
                and a['bps'] != b['bps']
        else:
            ok = a == b
        if not ok:
            bad.append((name, fps, q, sp, a, b))
    return not bad, rows, bad


def t_encode(old, new, rows):
    bad, n, diffs = [], 0, {}
    for name, media, size, fps, q, sp in MODES:
        a_s, b_s = rows[(name, size, fps, q, sp)]
        fa, ra, pa, qa, ma = encode(old, cmd_of(media, size, fps, q, sp, maxrec=a_s['dur']))
        fb, rb, pb, qb, mb = encode(new, cmd_of(media, size, fps, q, sp, maxrec=b_s['dur']))
        n += 1
        wa, wb = struct.unpack('<71I', pa), struct.unpack('<71I', pb)
        dw = [i for i in range(71) if wa[i] != wb[i]]
        exp = set()
        if size == 8:
            exp |= {24, 17} if a_s['dur'] != b_s['dur'] else {24}
        if wa[25] == OLD_CEIL:
            exp.add(25)
        ok = not fa and not fb and ra == rb and qa == qb and ma == mb and set(dw) == exp and wb[16] == wa[16]
        if size == 8:
            sc = (lambda v: (v * sp & M32) // 100) if sp < 100 else (lambda v: v)
            ok &= wb[24] == sc(NEW_4K) and wa[24] == sc(100_000_000) and wb[17] == b_s['dur']
        if 25 in exp:
            ok &= wb[25] == NEW_CEIL
        else:
            ok &= wa[25] == wb[25] and wa[25] in (250_000_000, 200_000_000)
        diffs[(name, fps, q, sp)] = (wa[24], wb[24], wa[25], wb[25], wa[17], wb[17])
        if not ok:
            bad.append((name, fps, q, sp, fa, fb, dw, sorted(exp)))
    # high-speed movie (media 3, 640 x 360, 120 fps capture at 25 %): table rows 8-10 unchanged, only the ceiling
    for rate, sp in ((120, 25), (240, 12)):
        fa, ra, pa, qa, ma = encode(old, cmd_of(3, 4, 30, 1, sp, rate=rate))
        fb, rb, pb, qb, mb = encode(new, cmd_of(3, 4, 30, 1, sp, rate=rate))
        n += 1
        wa, wb = struct.unpack('<71I', pa), struct.unpack('<71I', pb)
        dw = [i for i in range(71) if wa[i] != wb[i]]
        diffs[('HS', rate, 1, sp)] = (wa[24], wb[24], wa[25], wb[25], wa[17], wb[17])
        if fa or fb or ra != rb or qa != qb or ma != mb or dw != [25] or wb[25] != NEW_CEIL:
            bad.append(('HS', rate, fa, fb, dw))
    return not bad, n, diffs, bad


def t_estimate(rows):
    free = 64_000_000_000 // 512                       # a 64 GB card, free sectors
    out = []
    for fps in (30, 25, 24):
        a, b = rows[('4K', 8, fps, 1, 100)]
        files = -(-free // (1 << 23))
        est = lambda s: (free - (-(-s['buf'] // 512) + 0x14000) * files) // -(-s['bps'] // 512)
        out.append((fps, est(a), est(b), b['frames'] // fps))
    ok = all(e1 < e0 and abs(e1 / e0 - 13_067_000 / 19_504_500) < 0.01 and per < 1740 for _, e0, e1, per in out)
    return ok, out


def image(spec):
    pkg, rst, info = BP.build(spec, BP.STOCK.read_bytes())
    return [b for b in oc.parse(pkg) if b.kind == 0x100][0].payload, pkg, rst, info


def t_pkg(new_s, old, new, pkg, rst, info, opkg, disk):
    import numpy as np
    sb = {b.kind: b for b in oc.parse(BP.STOCK.read_bytes())}
    good = True
    for b in oc.parse(pkg):
        exp = bytearray(sb[b.kind].payload)
        for e in new_s['edits']:
            if int(e['kind'], 16) == b.kind:
                o = BP.resolve(b.kind, e['addr']); nb = bytes.fromhex(e['new']); exp[o:o + len(nb)] = nb
        good &= bytes(exp) == b.payload
        good &= b.payload == new if b.kind == 0x100 else b.payload == [x for x in oc.parse(opkg) if x.kind == b.kind][0].payload
    for b in oc.parse(rst):
        good &= b.payload == sb[b.kind].payload
    ours = [(a, 4) for a in CELLS] + [(CEIL_IMM, 4)]
    diff = [BASE + int(i) for i in np.nonzero(np.frombuffer(old, np.uint8) != np.frombuffer(new, np.uint8))[0]]
    stray = [hex(a) for a in diff if not any(s <= a < s + k for s, k in ours)]
    good &= not stray and len(old) == len(new) and len(diff) > 0
    mine = [e for e in new_s['edits'] if e.get('source') == 'patches/movie_bitrate']
    good &= len(mine) == 4 and sorted(int(e['addr'], 16) for e in mine) == sorted(a for a, _ in ours)
    if disk:
        good &= (disk / 'patched.pkg.bin').read_bytes() == pkg and (disk / 'restore-stock.pkg.bin').read_bytes() == rst
    return good, (f'{info["edits"]} edits, {info["changed_payload_bytes"]} B vs stock; {len(diff)} main bytes differ from BASE, all in the '
                  f'4 edits; stray {stray[:6]}' + ('; package files on disk match' if disk else ''))


def main():
    old_s, new_s = (json.loads(Path(p).read_text()) for p in sys.argv[1:3])
    disk = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    old, opkg, *_ = image(old_s)
    new, pkg, rst, info = image(new_s)
    ok = True
    g, rows, bad = t_split(old, new)
    print(f"{'PASS' if g else 'FAIL'} S {len(rows)} modes; bad {bad[:3]}", flush=True)
    for (name, size, fps, q, sp), (a, b) in rows.items():
        if size == 8:
            print(f'    {name} {fps}p speed {sp}%: B/s {a["bps"]} -> {b["bps"]}, reserve {a["buf"]:#x}, per file {a["dur"]} -> {b["dur"]} ms, '
                  f'{a["frames"]} -> {b["frames"]} frames')
    ok &= g
    g, n, diffs, bad = t_encode(old, new, rows)
    print(f"{'PASS' if g else 'FAIL'} E {n} encoder blocks; bad {bad[:3]}", flush=True)
    for k, v in diffs.items():
        if k[0] in ('4K', 'C4K', 'HS') or (k[0] == 'FHD' and k[1] == 60):
            print(f'    {k}: ulBitRate {v[0]} -> {v[1]}, ulMaxBitrate {v[2]} -> {v[3]}, ulMaxRecTime {v[4]} -> {v[5]}')
    ok &= g
    g, est = t_estimate(rows)
    print(f"{'PASS' if g else 'FAIL'} R 64 GB card, 4K remaining s (fps, BASE, NEW, per-file s): {est}", flush=True)
    ok &= g
    g, txt = t_pkg(new_s, old, new, pkg, rst, info, opkg, disk)
    print(f"{'PASS' if g else 'FAIL'} P {txt}", flush=True)
    ok &= g
    print('ALL PASS' if ok else 'FAILURES')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
