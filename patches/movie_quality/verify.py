#!/usr/bin/env python3
"""movie_quality checks (emulator, real code from the built packages). Offline. Minimal + anti-brick.

  .venv/bin/python -I patches/movie_quality/verify.py BASE.json NEW.json [PKGDIR]

BASE = the same chain without the layer, NEW = with it, PKGDIR = tools/build_package.py output.

  Q  recorder quality getter: the real 0x6031bf37 (NEW: its jmp + mq_get) through the real property getter 0x6005e971 over a
     synthetic registry (keys 0xf031 / 0xf041, 9 slots), every slot, every size 3/4/6/8/9 x quality 1/2/5/6: NEW = BASE
     except size 8, where NEW returns the slot's quality (5 -> 6) and BASE 1; d2 d3 a2 a3 sp pc as BASE.
  K  slot editor cursor predicates 0x60e1e8fd / 0x60e1e92d on a fake editor (+0x58 column, +0x5c size column whose vtable +4 /
     +0x10 return the size): "skip the bit-rate column" for size 8 (BASE yes, NEW no) and 9 (both yes), not for 3 / 4 / 6;
     column != 0 / 2 never. The three drawers: the compare decodes as `cmp 9,d1` with the stock branch after it.
  S  split and estimate inputs (0x6031f454, 0x6031f33f, as movie_bitrate S) for 4K q 6 / 1 / 2 / 5 at 30/25/24p: SF 150 M ->
     19 504 500 B/s, 200-s files; F stock; N 60 M -> 7 917 000 B/s, 520-s files; buffer reserve column as F; every
     non-4K mode equal to BASE.
  E  encoder block (0x603d132c, as movie_bitrate E, through mq_ceil) for 4K SF / F / N: word 24 = 150 / 100 / 60 M, word 25
     157.5 / 105 / 105 M, word 17 the file time; picture type 3, CABAC 1, initial complexity 0x180 (as F); 4K F and every
     FHD / HD / C4K / small / HS block byte-identical to BASE.
  P  anti-brick: package = stock + edits, restore == stock, files on disk match; every main byte that differs from BASE is
     inside this layer's edits (13 + the mq_get bytes); the OSD equals BASE.
"""
import json, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'external/oly_fw_analysis/tools'))
import importlib.util  # noqa: E402


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


MV = _load('movie_bitrate_verify_mq', ROOT / 'patches/movie_bitrate/verify.py')
W = _load('ep7_wb_v_mq', ROOT / 'tools/ep7_verify_wb.py')
Region, execute, BP, oc = MV.Region, MV.execute, MV.BP, MV.oc
BASE, CALLER, STACK, SP0 = MV.BASE, MV.CALLER, MV.STACK, MV.SP0
M32 = 0xffffffff
MQREG = ()


def sl(im, lo, hi):
    return im[lo - BASE:hi - BASE]


# ------------------------------------------------------------------ Q
def qget(im, slot, sizes, quals, mq):
    pr = {0xf031: bytes(sizes), 0xf041: bytes(quals)}
    rg = [MV.caller(0x6031bf37, 0x80, 8), Region('stack', STACK, bytes([0xa5] * 0x2000), 'rw', True),
          Region('qg', 0x6031bf30, sl(im, 0x6031bf30, 0x6031bf70), 'rx'),
          Region('getter', W.GETTER_CODE[0], sl(im, *W.GETTER_CODE), 'rx'), Region('xlate', W.XLATE[0], sl(im, *W.XLATE)),
          Region('cpuid', W.CPUID, bytes(4)), *W.registry(pr)]
    if mq:
        rg.append(Region('mq', mq[0], sl(im, mq[0], mq[1]), 'rx'))
    r = execute(rg, dict(pc=CALLER, sp=SP0, d0=slot, d2=0x2222, d3=0x3333, a2=0xa2a2, a3=0xa3a3), CALLER + 7, limit=20000)
    st = {m['name']: bytes.fromhex(m['hex']) for m in r['memory']}['stack'][SP0 - STACK:]
    return r['fault'], r['registers']['d0'] & 0xff, {k: r['registers'][k] for k in ('d2', 'd3', 'a2', 'a3', 'sp', 'pc')}, st


def t_q(old, new, mq):
    bad, n = [], 0
    for size in (3, 4, 6, 8, 9):
        for q in (1, 2, 5, 6):
            for slot in (0, 3, 7, 8):
                sizes, quals = [6] * 9, [1] * 9
                sizes[slot], quals[slot] = size, q
                fa, va, ra, sa = qget(old, slot, sizes, quals, None)
                fb, vb, rb, sb = qget(new, slot, sizes, quals, mq)
                n += 1
                want_old = 1 if size in (8, 9) else q
                want_new = 1 if size == 9 else (6 if (size == 8 and q == 5) else q)
                if fa or fb or va != want_old or vb != want_new or ra != rb or sa != sb:
                    bad.append((size, q, slot, fa, fb, va, vb))
    return not bad, f'{n} cases; bad {bad[:3]}'


# ------------------------------------------------------------------ K
def pred(im, fn, col, size):
    ed, colo, vt, fns = 0x13200000, 0x13201000, 0x13202000, 0x13203000
    edb = bytearray(0x100); struct.pack_into('<H', edb, 0x58, col); struct.pack_into('<I', edb, 0x5c, colo)
    vtb = bytearray(0x20); struct.pack_into('<I', vtb, 4, fns); struct.pack_into('<I', vtb, 0x10, fns + 8)
    code = bytes.fromhex('8007f0fc') + bytes(4) + bytes([0x80, size]) + bytes.fromhex('f0fc') + bytes(4)   # mov 7,d0; rets / mov size,d0; rets
    rg = [MV.caller(fn, 0x30, 12), Region('stack', STACK, bytes(0x2000), 'rw'), Region('fn', fn - 0x10, sl(im, fn - 0x10, fn + 0x40), 'rx'),
          Region('ed', ed, bytes(edb)), Region('col', colo, struct.pack('<I', vt) + bytes(12)), Region('vt', vt, bytes(vtb)),
          Region('fns', fns, code, 'rx')]
    r = execute(rg, dict(pc=CALLER, sp=SP0, a0=ed, a2=0xa2a2, a3=0xa3a3, d2=0x2222), CALLER + 7, limit=2000)
    return r['fault'], r['registers']['d0'], (r['registers']['a2'], r['registers']['a3'], r['registers']['sp'])


def t_k(old, new):
    bad, n = [], 0
    for fn, col_hit in ((0x60e1e8fd, 0), (0x60e1e92d, 2)):
        for col in (0, 1, 2):
            for size in (3, 4, 6, 8, 9):
                fa, va, ra = pred(old, fn, col, size)
                fb, vb, rb = pred(new, fn, col, size)
                n += 1
                skip_old = int(col == col_hit and size in (8, 9))
                skip_new = int(col == col_hit and size == 9)
                if fa or fb or va != skip_old or vb != skip_new or ra != rb or ra != (0xa2a2, 0xa3a3, SP0):
                    bad.append((hex(fn), col, size, fa, fb, va, vb))
    B3 = MV_B.B3
    for lo, hi, imm, ctx in MQ.DRAW:
        ins = B3.disasm(new[lo - BASE:hi - BASE], lo, hi)
        k = next(i for i, (a, _, _) in enumerate(ins) if a == imm - 1)
        n += 1
        if (ins[k][1], ins[k][2]) != ('cmp', '9,d1') or ins[k + 1][1] not in ('bne', 'beq') or \
                B3.disasm(old[lo - BASE:hi - BASE], lo, hi)[k][2] != '8,d1':
            bad.append(('drawer', hex(lo), ins[k]))
    return not bad, f'{n} cases; bad {bad[:3]}'


# ------------------------------------------------------------------ S / E
FOURK = [(f, q) for f in (30, 25, 24) for q in (6, 1, 2, 5)]


def t_s(old, new):
    bad, rows = [], {}
    for f, q in FOURK:
        if q == 5:              # the split / estimate take the quality code from the getter: mq_get never hands them 5 for 4K
            continue
        a, b = MV.split(old, q, 8, f), MV.split(new, q, 8, f)
        rows[(f, q)] = (a, b)
        qe = 6 if q == 5 else q
        if q != 1 and b['d0']:
            bad.append((f, q, 'err', b)); continue
        rate = {6: 150_000_000, 1: 100_000_000, 2: 60_000_000}[qe]
        bps = (rate // 100 * 103 + 1_536_000) >> 3
        s = (MV.BUDGET - b['buf']) // bps // 40 * 40
        k = {30: (30, 1001, 2503), 25: (24, 960, 2880), 24: (24, 1001, 2503)}[f]
        fbuf = MV.split(old, 1, 8, f)['buf']
        if b['fault'] or b['bps'] != bps or b['frames'] != s * k[0] or b['dur'] != s * k[1] + k[2] or b['buf'] != fbuf:
            bad.append((f, q, a, b))
        if q == 1 and a != b:
            bad.append((f, 'F differs', a, b))
    for name, media, size, fps, q, sp in MV.MODES:
        if size != 8:
            a, b = MV.split(old, q, size, fps, sp), MV.split(new, q, size, fps, sp)
            if a != b:
                bad.append((name, fps, q, a, b))
    return not bad, rows, bad


def t_e(old, new, rows):
    bad, n, out = [], 0, {}
    for f, q in FOURK:
        if q == 5:
            continue
        a_s, b_s = rows[(f, q)]
        fa, ra, pa, qa, ma = MV.encode(old, MV.cmd_of(1, 8, f, 1, 100, maxrec=a_s['dur']))     # BASE: the getter gave F
        fb, rb, pb, qb, mb = MV.encode(new, MV.cmd_of(1, 8, f, q, 100, maxrec=b_s['dur']), MQREG)
        n += 1
        wa, wb = struct.unpack('<71I', pa), struct.unpack('<71I', pb)
        rate = {6: 150_000_000, 1: 100_000_000, 2: 60_000_000}[q]
        dw = sorted(i for i in range(71) if wa[i] != wb[i])
        ceil = MV.NEW_CEIL if rate > 100_000_000 else MV.OLD_CEIL
        exp = ({25} if ceil != MV.OLD_CEIL else set()) | ({24} if q != 1 else set()) | ({17} if a_s['dur'] != b_s['dur'] else set())
        ok = not fa and not fb and ra == rb and qa == qb and ma == mb and wb[24] == rate and wb[25] == ceil and wa[25] == MV.OLD_CEIL \
            and wb[51] == 3 and wb[52] == 1 and wb[57] == 0x180 and wb[17] == b_s['dur'] and set(dw) == exp
        out[(f, q)] = (wb[24], wb[25], wb[17])
        if not ok:
            bad.append((f, q, fa, fb, dw, sorted(exp), wb[24], wb[51], wb[52], wb[57]))
    for name, media, size, fps, q, sp in MV.MODES:
        if size == 8:
            continue
        fa, ra, pa, qa, ma = MV.encode(old, MV.cmd_of(media, size, fps, q, sp))
        fb, rb, pb, qb, mb = MV.encode(new, MV.cmd_of(media, size, fps, q, sp), MQREG)
        n += 1
        wa, wb = struct.unpack('<71I', pa), struct.unpack('<71I', pb)
        dw = [i for i in range(71) if wa[i] != wb[i]]
        if fa or fb or ra != rb or qa != qb or ma != mb or dw:            # every stock level: the block is byte-identical
            bad.append((name, fps, q, dw))
    return not bad, n, out, bad


def t_p(new_s, old, new, pkg, rst, info, opkg, disk):
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
    mq = new_s['movie_quality']
    ours = [(int(e['addr'], 16), len(e['new']) // 2) for e in new_s['edits'] if e.get('source') == 'patches/movie_quality']
    ours.append((int(mq['code'][0], 16), mq['code'][1]))
    diff = [BASE + int(i) for i in np.nonzero(np.frombuffer(old, np.uint8) != np.frombuffer(new, np.uint8))[0]]
    stray = [hex(a) for a in diff if not any(s <= a < s + k for s, k in ours)]
    good &= not stray and len(old) == len(new) and len(ours) == 14
    if disk:
        good &= (disk / 'patched.pkg.bin').read_bytes() == pkg and (disk / 'restore-stock.pkg.bin').read_bytes() == rst
    return good, (f'{info["edits"]} edits, {info["changed_payload_bytes"]} B vs stock; {len(diff)} main bytes differ from BASE, all in '
                  f'the layer\'s {len(ours)} ranges; stray {stray[:6]}' + ('; package files on disk match' if disk else ''))


MV_B = _load('movie_bitrate_build_mqv', ROOT / 'patches/movie_bitrate/build.py')
MQ = _load('movie_quality_build_v', ROOT / 'patches/movie_quality/build.py')


def main():
    old_s, new_s = (json.loads(Path(p).read_text()) for p in sys.argv[1:3])
    disk = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    old, opkg, *_ = MV.image(old_s)
    new, pkg, rst, info = MV.image(new_s)
    at, n = int(new_s['movie_quality']['code'][0], 16), new_s['movie_quality']['code'][1]
    global MQREG
    MQREG = (Region('mqc', at - 0x10, sl(new, at - 0x10, at + n + 0x10), 'rx'),)
    ok = True
    g, txt = t_q(old, new, (at - 0x10, at + n + 0x10))
    print(f"{'PASS' if g else 'FAIL'} Q {txt}", flush=True); ok &= g
    g, txt = t_k(old, new)
    print(f"{'PASS' if g else 'FAIL'} K {txt}", flush=True); ok &= g
    g, rows, bad = t_s(old, new)
    print(f"{'PASS' if g else 'FAIL'} S 4K + {len(MV.MODES)} modes; bad {bad[:3]}", flush=True); ok &= g
    for (f, q), (a, b) in rows.items():
        if True:
            print(f'    4K {f}p q{q}: B/s {b["bps"]}, reserve {b["buf"]:#x}, per file {b["dur"]} ms / {b["frames"]} frames (BASE, same code: {a["dur"]} ms; 0 = the stock empty cell)')
    g, n, out, bad = t_e(old, new, rows)
    print(f"{'PASS' if g else 'FAIL'} E {n} encoder blocks; 4K (fps, q) -> (ulBitRate, ulMaxBitrate, ulMaxRecTime) {out}; bad {bad[:3]}", flush=True); ok &= g
    g, txt = t_p(new_s, old, new, pkg, rst, info, opkg, disk)
    print(f"{'PASS' if g else 'FAIL'} P {txt}", flush=True); ok &= g
    print('ALL PASS' if ok else 'FAILURES')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
