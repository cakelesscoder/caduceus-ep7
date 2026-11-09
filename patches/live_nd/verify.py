#!/usr/bin/env python3
"""Emulator + static checks for live_nd 0.31n1 (real firmware code at every hooked site; the getters are stubbed). Offline.

  .venv/bin/python -I patches/live_nd/verify.py generated/v029a/edits.json generated/live_nd/edits.json [generated/live_nd/pkg]

  H  hooks: all 12 sites, from the argument setup to just after the call, new image vs v0.29a, frames (267) 0..4 x
     user Auto Gain 0 / 1 x sid 24 211 / 1: Auto Gain 1 when frames >= 3; frame reads 2 when frames < 2 and
     sid 24 == 211; everything else == v0.29a; d2, d3, a2, a3, sp == v0.29a, stop reached, no fault
  D  data: validator record 438 -> {0, 2, 3, 4}; both Number of Frames descriptors -> 4-entry lists, 4-aligned, values in
     validator order, ND3 / ND4 kind 5 with in-block NUL-terminated text; AP Multiple Exposure preset block = stock
     minus the 267 pair, same order, count 226
  P  anti-brick: package reparses, decoded == stock + edits, restore == stock, only our bytes (and the version label)
     differ from v0.29a
Not emulated: the ME sequencer and combine at 3/4 frames, the menu screens. See docs/LIVE_ND.md.
"""
import importlib.util, json, struct, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools')); sys.path.insert(0, str(ROOT / 'external/oly_fw_analysis/tools'))
from penf_emulator import Region, execute  # noqa: E402
import build_package as BP, oly_container as oc  # noqa: E402


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


LN = _load('live_nd_build', ROOT / 'patches/live_nd/build.py')
SB3, BASE = LN.SB3, LN.BASE
STK = 0x18010000


def image(spec):
    pkg, rst, info = BP.build(spec, BP.STOCK.read_bytes())
    return [b for b in oc.parse(pkg) if b.kind == 0x100][0].payload, pkg, rst, info


def R(q, name, lo, hi, perm='rx'):
    return Region(name, lo, q[lo - BASE:hi - BASE], perm)


def stub(at, table, ret):
    """d0 -> value from table (else 0x7777), returning like the real function."""
    lines = [f' cmp {k},d0\n bne 1{i}f\n mov {v},d0\n {ret}\n1{i}:' for i, (k, v) in enumerate(table.items())]
    src = ' .am33_2\n .text\n .global _start\n_start:\n' + '\n'.join(lines) + f'\n mov 0x7777,d0\n {ret}\n'
    return SB3.assemble(src, at, {})[0]


def site_run(q, site, pre, f, g, s24, c=0):
    """Run from the argument setup before the call at `site` to the instruction after it."""
    rg = [R(q, 'site', site - 0x40, site + 0x40), R(q, 'lnd', LN.AT, LN.END),
          Region('get', LN.GET, stub(LN.GET, {267: f, 24: s24, 1487: c}, 'ret [],4'), 'rx'),
          Region('prop', LN.PROP, stub(LN.PROP, {0x1841: f, 0x1851: g}, 'ret [d2,d3],12'), 'rx'),
          Region('app', LN.APPGET, stub(LN.APPGET, {267: f}, 'ret [d2,a2],24'), 'rx'),
          Region('stk', STK, bytes(0x2000), 'rw')]
    regs = {'pc': site - pre, 'sp': STK + 0x1000, 'd2': 0x2222, 'd3': 0x3333, 'a2': 0x4444, 'a3': 0x5555}
    r = execute(rg, regs, site + 7, limit=400)
    rr = r['registers']
    return (rr['pc'] == site + 7 and not r['fault'], rr['d0'], tuple(rr[k] for k in ('d2', 'd3', 'a2', 'a3', 'sp')))


def t_hooks(old, new):
    bad, n = [], 0
    for site, tgt, fr, stb, why in LN.SITES:
        if tgt not in (LN.GET, LN.PROP, LN.APPGET):
            continue                       # preset apply / mode save sites: t_cont
        pre = len(LN.PRE[site])
        for f in (0, 1, 2, 3, 4):
            for g in (0, 1):
                for s24 in (211, 1):
                    c = g                          # 1487 (stock continuous flag) follows g in these runs
                    a, b = site_run(old, site, pre, f, g, s24, c), site_run(new, site, pre, f, g, s24, c)
                    if stb == 'lnd_kg':
                        want, stock_v = (1 if f >= 3 and s24 == 211 else g), g
                    elif s24 == 211:
                        want, stock_v = (2 if f < 2 else f), f          # AP ME: Off -> 2, ND3/ND4 as is
                    else:
                        want, stock_v = (2 if f >= 3 else f), f         # elsewhere ND is AP-only: 3/4 -> 2
                    n += 1
                    if not a[0] or not b[0] or a[1] != stock_v or b[1] != want or b[2] != a[2]:
                        bad.append((hex(site), stb, f, g, s24, a, b, want))
    return bad, n


def t_data(new, s):
    bad, n = [], 0
    d = {k: int(v, 16) for k, v in s['live_nd']['data'].items()}
    end = int(s['live_nd']['block_end'], 16)
    u32 = lambda a: struct.unpack_from('<I', new, a - BASE)[0]
    n += 1
    rec = struct.unpack_from('<HHIIHH', new, LN.VAL_REC - BASE)
    if rec[0] != LN.SID_N or rec[2:5] != (d['val'], 0, 4) or list(new[d['val'] - BASE:d['val'] + 4 - BASE]) != LN.VALUES:
        bad.append(('validator', rec))
    for i, (m, lo) in enumerate([(m, 12) for m in LN.MENUS] + [(m, 28) for m in LN.MENUS]):
        n += 1
        lp, cnt = u32(m + lo), u32(m + lo + 4)
        vals = [u32(lp + 12 * k) for k in range(cnt)]
        if u32(m) != LN.SID_N or lp != d[f'list{i}'] or lp % 4 or cnt != 4 or vals != LN.VALUES:
            bad.append(('menu', hex(m), hex(lp), cnt, vals))
            continue
        for k in range(cnt):
            v, kind, sid_id, txt = struct.unpack_from('<IHHI', new, lp + 12 * k - BASE)
            if v in LN.LABELS:
                n += 1
                t = new[txt - BASE:new.index(b'\0', txt - BASE)]
                if kind != 5 or sid_id != LN.LABELS[v][1] or not (LN.AT <= txt < end) or t.decode() != LN.LABELS[v][0]:
                    bad.append(('label', hex(m), v, kind, hex(txt), t))
    n += 1
    sid, cnt = struct.unpack_from('<HH', new, LN.ROW_SUM - BASE)
    lp = u32(LN.ROW_SUM + 4)
    if sid != LN.SID_N or cnt != 4 or lp != d['list_row'] or lp % 4 or [u32(lp + 12 * k) for k in range(4)] != LN.VALUES:
        bad.append(('row summary', sid, cnt, hex(lp)))
    n += 1
    stk = LN.STOCK.read_bytes()
    nc, sc = list(new[LN.CX_CONDS - BASE:LN.CX_CONDS + LN.CX_N - BASE]), list(stk[LN.CX_CONDS - BASE:LN.CX_CONDS + LN.CX_N - BASE])
    diff = [i for i in range(LN.CX_N) if nc[i] != sc[i]]
    if LN.CX_APME in nc or len(diff) != 1 or sc[diff[0]] != LN.CX_APME or nc[diff[0]] != LN.CX_DUP or set(nc) != set(sc) - {LN.CX_APME}:
        bad.append(('grey-out conds', diff))
    n += 1
    st = LN.STOCK.read_bytes()
    pr = lambda img, k: struct.unpack_from('<II', img, LN.ME_BLOCK + 8 * k - BASE)
    sp = [pr(st, k) for k in range(LN.ME_COUNT)]
    npairs = [pr(new, k) for k in range(struct.unpack_from('<H', new, LN.PRESET_IDX + 8 - BASE)[0])]
    if npairs != [x for x in sp if x[0] != LN.SID_N] or len(npairs) != LN.ME_COUNT - 1 or u32(LN.PRESET_IDX + 4) != LN.ME_BLOCK:
        bad.append(('preset block', len(npairs)))
    return bad, n


GX_CODE = (0x60829000, 0x6082b500)
GX_DATA = (0x60ade000, 0x60ae0000)
GX_RAM = 0x622d6000
PRED_TBL, PRED_N = 0x60ade144, 136


def greyout(q, iid, true_idx):
    """Real grey-out evaluator 0x608290c8 for item `iid`; every predicate is a stub true only for index true_idx."""
    code = bytearray(q[GX_CODE[0] - BASE:GX_CODE[1] - BASE])
    data = bytearray(q[GX_DATA[0] - BASE:GX_DATA[1] - BASE])
    pred = 0x18100000
    pred_src = f""" .am33_2
 .text
 .global _start
_start:
 cmp {4 * true_idx},d0                   /* d0 = index * 4 at the calls (asl2 before the table read) */
 bne 1f
 mov 1,d0
 rets
1:
 clr d0
 rets
"""
    pcode = SB3.assemble(pred_src, pred, {})[0]
    for i in range(PRED_N):
        struct.pack_into('<I', data, PRED_TBL - GX_DATA[0] + 4 * i, pred)
    for at, src in ((0x6082b1d7, ' clr d0\n ret [],4\n'), (0x6082b227, ' clr d0\n ret [d2,d3,a2],16\n')):
        b = SB3.assemble(' .am33_2\n .text\n .global _start\n_start:\n' + src, at, {})[0]
        code[at - GX_CODE[0]:at - GX_CODE[0] + len(b)] = b
    log = SB3.assemble(' .am33_2\n .text\n .global _start\n_start:\n ret [d2,a2],12\n', 0x60767ee5, {})[0]
    g478 = SB3.assemble(' .am33_2\n .text\n .global _start\n_start:\n clr d0\n ret [],4\n', 0x602afa81, {})[0]
    caller = SB3.assemble(f""" .am33_2
 .text
 .global _start
_start:
 mov 255,d0
 mov d0,(4,sp)
 mov {iid},d0
 clr d1
 mov 0,a0
 mov 0,a1
""", 0x18000000, {})[0]
    at = 0x18000000 + len(caller)
    caller += b'\xdd' + struct.pack('<i', 0x608290c8 - at) + b'\xf0\x2c\xcb'   # call 0x608290c8,[d2,d3,a2,a3],44; nop
    stop = at + 7
    rg = [Region('call', 0x18000000, caller, 'rx'), Region('code', GX_CODE[0], bytes(code), 'rx'), Region('data', GX_DATA[0], bytes(data), 'r'),
          Region('pred', pred, pcode, 'rx'), Region('log', 0x60767ee5, log, 'rx'), Region('g478', 0x602afa81, g478, 'rx'),
          Region('ram', GX_RAM, bytes(0x1000), 'rw'), Region('stk', STK, bytes(0x2000), 'rw')]
    r = execute(rg, {'pc': 0x18000000, 'sp': STK + 0x1000, 'd2': 0x2222, 'd3': 0x3333, 'a2': 0x4444, 'a3': 0x5555}, stop, limit=20000)
    rr = r['registers']
    return rr['pc'] == stop and not r['fault'], rr['d0'] & 0xffff, tuple(rr[k] for k in ('d2', 'd3', 'a2', 'a3', 'sp'))


def t_greyout(old, new):
    bad, n = [], 0
    for iid, idx, want_old, want_new in ((267, 24, 1, 0), (267, 23, 1, 1), (267, 7, 1, 1), (267, 0, 1, 1), (267, 200, 0, 0),
                                         (472, 24, None, None), (472, 23, None, None)):
        a, b = greyout(old, iid, idx), greyout(new, iid, idx)
        n += 1
        ok = a[0] and b[0] and a[2] == b[2]
        if want_old is None:
            ok &= a[1] == b[1]
        else:
            ok &= (a[1] != 0) == bool(want_old) and (b[1] != 0) == bool(want_new)
        if not ok:
            bad.append((iid, idx, a, b))
    return bad, n


def off_run(q, f, s24):
    """calls through the ME parts vtable word 0x60b4ffac; a stand-in at the stock handler records its entry registers."""
    vt = struct.unpack_from('<I', q, LN.VT_OFF - BASE)[0]
    stock_stub = SB3.assemble(' .am33_2\n .text\n .global _start\n_start:\n mov d0,d2\n mov d1,d3\n mov a0,a2\n mov 0x5151,d0\n rets\n', LN.OFF, {})[0]
    caller = SB3.assemble(f' .am33_2\n .text\n .global _start\n_start:\n mov {vt},a1\n mov 0x1d00,d0\n mov 0x1d11,d1\n mov 0x1a000000,a0\n calls (a1)\n nop\n', 0x18000000, {})[0]
    stop = 0x18000000 + len(caller) - 1
    rg = [Region('call', 0x18000000, caller, 'rx'), Region('lnd', LN.AT, q[LN.AT - BASE:LN.END - BASE], 'rx'),
          Region('get', LN.GET, stub(LN.GET, {267: f, 24: s24}, 'ret [],4'), 'rx'), Region('off', LN.OFF, stock_stub, 'rx'),
          Region('stk', STK, bytes(0x2000), 'rw')]
    r = execute(rg, {'pc': 0x18000000, 'sp': STK + 0x1000, 'd2': 0, 'd3': 0, 'a2': 0}, stop, limit=400)
    rr = r['registers']
    reached = rr['d0'] == 0x5151 and (rr['d2'], rr['d3'], rr['a2']) == (0x1d00, 0x1d11, 0x1a000000)
    return rr['pc'] == stop and not r['fault'] and rr['sp'] == STK + 0x1000, reached, vt


def t_off(old, new):
    bad, n = [], 0
    for f in (0, 2, 3, 4):
        for s24 in (211, 1):
            a, b = off_run(old, f, s24), off_run(new, f, s24)
            nd = s24 == 211 and f in (3, 4)
            n += 1
            if not (a[0] and b[0] and a[1] and b[1] == (not nd) and a[2] == LN.OFF and b[2] != LN.OFF):
                bad.append((f, s24, a, b))
    return bad, n


def _asm(at, body):
    return SB3.assemble(' .am33_2\n .text\n .global _start\n_start:\n' + body, at, {})[0]


def pw_run(q, pair, f):
    """Real apply-loop instructions 0x602b9b85..0x602b9b91 with a0 = pair; the write stand-in returns d0 = d1, d2 = d0."""
    rg = [R(q, 'site', 0x602b9b40, 0x602b9bc0), R(q, 'lnd', LN.AT, LN.END), R(q, 'presets', 0x60475000, 0x6047b000, 'r'),
          Region('get', LN.GET, stub(LN.GET, {267: f, 24: 1}, 'ret [],4'), 'rx'),
          Region('wr', LN.WR, _asm(LN.WR, ' mov d0,d2\n mov d1,d0\n ret [],4\n'), 'rx'), Region('stk', STK, bytes(0x2000), 'rw')]
    r = execute(rg, {'pc': 0x602b9b85, 'sp': STK + 0x1000, 'a0': pair, 'a3': 0x4444}, 0x602b9b91, limit=400)
    rr = r['registers']
    return rr['pc'] == 0x602b9b91 and not r['fault'], rr['d2'], rr['d0'], rr['a3']


def sv_run(q, k0, k1, sid):
    """Real save-loop instructions 0x602b985d..0x602b9866 (a3 = list entry, a2 = memory entry + 8)."""
    ram = bytearray(64)
    struct.pack_into('<HH', ram, 0, k0, k1)
    struct.pack_into('<HB', ram, 32, sid, 1)
    rg = [R(q, 'site', 0x602b9820, 0x602b98a0), R(q, 'lnd', LN.AT, LN.END), Region('ram', 0x1c000000, bytes(ram), 'r'),
          Region('rd', LN.RD, _asm(LN.RD, ' mov 0x77,d0\n ret [],4\n'), 'rx'), Region('stk', STK, bytes(0x2000), 'rw')]
    r = execute(rg, {'pc': 0x602b985d, 'sp': STK + 0x1000, 'a3': 0x1c000020, 'a2': 0x1c000008}, 0x602b9866, limit=400)
    rr = r['registers']
    return rr['pc'] == 0x602b9866 and not r['fault'], rr['d0'], rr['sp']


def cb_run(q, w, s24, f):
    """calls through the sid-267 descriptor word w; stand-ins: stock callback (marks d3), write (records d0/d1 in d2/a3)."""
    tgt = struct.unpack_from('<I', q, w - BASE)[0]
    caller = _asm(0x18000000, f' mov {tgt},a0\n mov 0x1111,d2\n mov 0x2222,a3\n clr d3\n calls (a0)\n nop\n')
    stop = 0x18000000 + len(caller) - 1
    rg = [Region('call', 0x18000000, caller, 'rx'), R(q, 'lnd', LN.AT, LN.END),
          Region('cb', LN.CB, _asm(LN.CB, ' add -4,sp\n mov 0x5c,d3\n clr d0\n ret [],4\n'), 'rx'),
          Region('get', LN.GET, stub(LN.GET, {267: f, 24: s24}, 'ret [],4'), 'rx'),
          Region('wr', LN.WR, _asm(LN.WR, ' mov d0,d2\n mov d1,a3\n ret [],4\n'), 'rx'), Region('stk', STK, bytes(0x2000), 'rw')]
    r = execute(rg, {'pc': 0x18000000, 'sp': STK + 0x1000}, stop, limit=600)
    rr = r['registers']
    return rr['pc'] == stop and not r['fault'] and rr['sp'] == STK + 0x1000, rr['d3'], rr['d2'], rr['a3'], rr['d0']


def t_cont(old, new):
    bad, n = [], 0
    blk = LN.ME_BLOCK
    me = [blk + 8 * k for k in range(LN.ME_COUNT - 1) if struct.unpack_from('<I', new, blk + 8 * k - BASE)[0] == 1487]
    other = [a for a in range(0x604765a0, 0x60476ca8, 8) if struct.unpack_from('<I', new, a - BASE)[0] == 1487]
    non = blk                                     # first AP ME pair (sid 0)
    if len(me) != 1 or not other:
        return [('pairs', me, other)], 1
    for pair, nd_ok in ((me[0], True), (other[0], False), (non, False)):
        for f in (0, 2, 3, 4):
            a, b = pw_run(old, pair, f), pw_run(new, pair, f)
            sid, val = struct.unpack_from('<II', new, pair - BASE)
            osid, oval = struct.unpack_from('<II', old, pair - BASE)   # v0.29a's block is not shifted
            want = (1 if f in (3, 4) else val) if nd_ok else val
            n += 1
            if not (a[0] and b[0] and a[1:] == (osid, oval, 0x4444) and b[1:] == (sid, want, 0x4444)):
                bad.append(('W', hex(pair), f, a, b, want))
    for k0, k1, sid, want in ((211, 0, 1487, 0), (212, 0, 1487, 0x77), (211, 1, 1487, 0x77), (211, 0, 267, 0x77), (3, 0, 1487, 0x77)):
        a, b = sv_run(old, k0, k1, sid), sv_run(new, k0, k1, sid)
        n += 1
        if not (a[0] and b[0] and a[1] == 0x77 and b[1] == want and a[2] == b[2]):
            bad.append(('S', k0, k1, sid, a, b))
    for w in LN.CB_WORDS:
        for s24 in (211, 1):
            for f in (0, 2, 3, 4):
                a, b = cb_run(old, w, s24, f), cb_run(new, w, s24, f)
                n += 1
                wrote = s24 == 211
                ok = a[0] and b[0] and a[1] == 0x5c and b[1] == 0x5c and a[2:4] == (0x1111, 0x2222) and b[4] == 0
                ok &= b[2:4] == ((1487, 1 if f in (3, 4) else 0) if wrote else (0x1111, 0x2222))
                if not ok:
                    bad.append(('C', hex(w), s24, f, a, b))
    return bad, n


def t_floor(new):
    """n7 safe floor: nothing of ours touches continuous drive, the sequencer's release handler or the 267 callbacks."""
    stk = LN.STOCK.read_bytes()
    bad, n = [], 0
    for a, k, why in ((LN.VT_OFF, 4, 'ME parts release-in-CONT vtable word'), (0x604345b4, 4, '267 callback 1'), (0x6043ad10, 4, '267 callback 2'),
                      (0x602b9b8a, 7, 'preset apply write'), (0x602b985f, 7, 'mode-save read'),
                      (0x609351bd, 7, 'judgeSeqATT 1487'), (0x60935636, 7, 'sequence log 1487'), (0x6094b00c, 7, 'shoot-info 1487'), (0x60965c37, 7, 'parts continuous setup 1487')):
        n += 1
        if new[a - BASE:a + k - BASE] != stk[a - BASE:a + k - BASE]:
            bad.append((why, hex(a)))
    n += 1
    cnt = struct.unpack_from('<H', new, LN.PRESET_IDX + 8 - BASE)[0]
    pairs = dict(struct.unpack_from('<II', new, LN.ME_BLOCK + 8 * j - BASE) for j in range(cnt))
    if pairs.get(1487) != 0 or LN.SID_N in pairs:
        bad.append(('AP ME preset', pairs.get(1487), LN.SID_N in pairs))
    return bad, n


POOL, STATE, BLK_AT, P_AT = SB3.POOL, SB3.STATE, 0xa1f90000, 0xa1f8d800
OBJ = 0x1a000000
RN = LN.LOG_RN
BLKN = 16 + 24 * RN


def mem(r, name):
    return {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}[name]


def lreg(q, f, s24, blk, dirty=0, key=4, obj=None):
    """lnd code from the image, getters, heap P (+ block when blk), state / key / take-limit statics, a parts object."""
    heap = bytearray(BLK_AT + BLKN - P_AT)
    struct.pack_into('<I', heap, 0, SB3.MAGIC)
    if blk:
        struct.pack_into('<I', heap, LN.LOG_POFF, BLK_AT)
        struct.pack_into('<IBBH', heap, BLK_AT - P_AT, 0x4c444e4c, 0, dirty, dirty)
    st = bytearray(0x1000); struct.pack_into('<H', st, STATE & 0xfff, 1)
    sv = bytearray(0x1000); struct.pack_into('<I', sv, LN.KEYW & 0xfff, key); struct.pack_into('<H', sv, LN.TAKELIM & 0xfff, 1)
    o = bytearray(1024) if obj is None else obj
    if obj is None:
        for off, v in ((156, 0x00650002), (160, 0x00010001), (464, 0x48000000), (224, f), (212, 0)):
            struct.pack_into('<I', o, off, v)
    return [R(q, 'lnd', LN.AT, LN.END), R(q, 'lnda', LN.LOG_AT, LN.LOG_END), R(q, 'lndb', LN.LOG_B, LN.LOG_B_END),
            Region('get', LN.GET, stub(LN.GET, {267: f, 24: s24, 1487: 0}, 'ret [],4'), 'rx'),
            Region('heap', P_AT, bytes(heap), 'rw', True), Region('st', STATE & ~0xfff, bytes(st), 'r'),
            Region('sv', LN.KEYW & ~0xfff, bytes(sv), 'r'), Region('obj', OBJ, bytes(o), 'r'),
            Region('regd', LN.REGD, _asm(LN.REGD, ' mov 2,d0\n ret [d2,a2],24\n'), 'rx'),
            Region('rel', LN.RELCHK, _asm(LN.RELCHK, ' mov 1,d0\n ret [d2,d3,a2,a3],56\n'), 'rx'),
            Region('stk', STK, bytes(0x2000), 'rw')]


def recs(r):
    h = mem(r, 'heap')[BLK_AT - P_AT:]
    n = struct.unpack_from('<H', h, 6)[0]
    return [struct.unpack_from('<6I', h, 16 + 24 * k) for k in range(min(n, RN))], h


def cap_run(q, f, s24, cap, blk):
    """Real 0x60950cb6..0x60950cc1 (mov d2,a0; exthu d0; clr d1; call 0x6091dbf2 -> +156 value) with the capacity stubbed."""
    rg = [R(q, 'site', 0x60950c80, 0x60950d00)] + lreg(q, f, s24, blk) + [
          Region('capf', LN.CAPF, _asm(LN.CAPF, f' mov {cap},d0\n ret [d2,d3,a2],20\n'), 'rx')]
    r = execute(rg, {'pc': 0x60950cb6, 'sp': STK + 0x1000, 'd0': 0x8888, 'd2': 0x2222, 'd3': 0x3333, 'a2': 0x4444, 'a3': OBJ}, 0x60950cc1, limit=1500)
    rr = r['registers']
    return rr['pc'] == 0x60950cc1 and not r['fault'], rr['d0'] & 0xffff, tuple(rr[k] for k in ('d2', 'd3', 'a2', 'a3', 'sp')), r


def t_cap(old, new, spec):
    """K: no one-press code is left on the capture engine: the +156 source call (0x60950cba), the ME continue
    handler word (0x60b50038) and the frame-done flag call (0x6096b019) are stock (0.31n1's +156 raise crashed Seq H)."""
    stk = LN.STOCK.read_bytes()
    sites = ((0x60950cba, 7), (0x60932170, 7)) + (() if spec['live_nd'].get('log') else ((0x60b50038, 4), (0x6096b019, 7)))
    bad = [hex(a) for a, k in sites if new[a - BASE:a + k - BASE] != stk[a - BASE:a + k - BASE]]
    return bad, len(sites)


def fd_run(q, f, s24, key, blk):
    """Real ME continuous frame-done tail 0x6096b012..0x6096b020 (flag stand-in returns 0x4848)."""
    rg = [R(q, 'site', 0x6096afc0, 0x6096b040)] + lreg(q, f, s24, blk, key=key) + [
          Region('flag', LN.FLAG, _asm(LN.FLAG, ' mov 0x4848,d0\n ret [d2],4\n'), 'rx')]
    r = execute(rg, {'pc': 0x6096b012, 'sp': STK + 0x1000, 'a2': OBJ, 'd2': 3, 'd3': 0x3333, 'a3': 0x5555}, 0x6096b020, limit=1500)
    rr = r['registers']
    return rr['pc'] == 0x6096b020 and not r['fault'], tuple(rr[k] for k in ('d0', 'd2', 'd3', 'a2', 'a3', 'sp')), r


def rem_run(q, f, blk):
    """Real 0x6093216d..0x60932177 (mov (a2),d0; mov d0,a0; call 0x60888d43) with remaining stubbed to 7."""
    o = bytearray(1024)
    struct.pack_into('<I', o, 0x200, OBJ)
    struct.pack_into('<I', o, 156, 0x00000004)
    rg = [R(q, 'site', 0x60932140, 0x609321c0)] + lreg(q, f, 211, blk, obj=o) + [
          Region('remf', LN.REMF, _asm(LN.REMF, ' mov 7,d0\n retf [],0\n'), 'rx')]
    r = execute(rg, {'pc': 0x6093216d, 'sp': STK + 0x1000, 'a2': OBJ + 0x200, 'd2': 0x2222, 'd3': 0x3333, 'a3': OBJ}, 0x60932177, limit=1500)
    rr = r['registers']
    return rr['pc'] == 0x60932177 and not r['fault'], tuple(rr[k] for k in ('d0', 'd2', 'd3', 'a2', 'a3', 'sp')), r


def req_run(q, f, blk):
    """calls through the ME parts vtable +3668 word; a stand-in at the stock handler records its entry registers."""
    vt = struct.unpack_from('<I', q, LN.VT_REQ - BASE)[0]
    caller = _asm(0x18000000, f' mov {vt},a1\n mov 0x1d00,d0\n mov 0x1d11,d1\n mov {OBJ},a0\n mov 0x1d22,a1\n mov {vt},d2\n mov d2,a3\n mov 0x5252,d2\n mov 0x5353,d3\n mov 0x5454,a2\n calls (a3)\n nop\n')
    stop = 0x18000000 + len(caller) - 1
    rg = [Region('call', 0x18000000, caller, 'rx')] + lreg(q, f, 211, blk) + [
          Region('reqf', LN.REQF, _asm(LN.REQF, ' cmp 0x1d00,d0\n bne 1f\n cmp 0x1d11,d1\n bne 1f\n cmp 0x1d22,a1\n bne 1f\n cmp 0x1a000000,a0\n bne 1f\n cmp 0x5252,d2\n bne 1f\n cmp 0x5454,a2\n bne 1f\n mov 0x600d,d0\n rets\n1:\n clr d0\n rets\n'), 'rx')]
    r = execute(rg, {'pc': 0x18000000, 'sp': STK + 0x1000}, stop, limit=1500)
    rr = r['registers']
    return rr['pc'] == stop and not r['fault'] and rr['sp'] == STK + 0x1000 and rr['d0'] == 0x600d and (rr['d2'], rr['d3'], rr['a2']) == (0x5252, 0x5353, 0x5454), vt, r


def trig_run(q, s24, blk, dirty, ev, card=True):
    """Loader sd_back jmp (0x605b7420) -> lnd_trig -> the previous target, with malloc / fopen / fwrite / fclose stand-ins."""
    stk = bytearray(0x2000); struct.pack_into('<I', stk, 0x1010, ev)
    mark = 0x1b000000
    rg = lreg(q, 2, s24, blk, dirty) + [R(q, 'ldr', 0x605b7400, 0x605b7800),
          Region('malloc', LN.LIB['ep7_malloc'], _asm(LN.LIB['ep7_malloc'], f' mov {BLK_AT},a0\n ret [],4\n'), 'rx'),
          Region('fopen', LN.LIB['ep7_fopen'], _asm(LN.LIB['ep7_fopen'], f' mov {0x1d000000 if card else 0},a0\n ret [],4\n'), 'rx'),
          Region('fwrite', LN.LIB['ep7_fwrite'], _asm(LN.LIB['ep7_fwrite'], f' mov {mark},a2\n mov d0,(a2)\n mov d1,(4,a2)\n mov a0,(8,a2)\n mov a1,(12,a2)\n ret [d2,d3,a2,a3],24\n'), 'rx'),
          Region('fclose', LN.LIB['ep7_fclose'], _asm(LN.LIB['ep7_fclose'], f' mov {mark},a2\n mov a0,(16,a2)\n ret [d2,a2,a3],16\n'), 'rx'),
          Region('mark', mark, bytes(32), 'rw', True)]
    rg = [x for x in rg if x.name != 'stk'] + [Region('stk', STK, bytes(stk), 'rw')]
    regs = {'pc': LN.SD_BACK, 'sp': STK + 0x1000, 'd0': 0x10, 'd1': 0x11, 'a0': 0x12, 'a1': 0x13, 'd2': 0x22, 'd3': 0x33, 'a2': 0x42, 'a3': 0x43}
    return rg, regs


def t_log(new, spec):
    if not spec['live_nd'].get('log'):
        return [], 0
    """L: readout hooks keep every stock register and return value; records land in the block; the half-press writes it."""
    bad, n = [], 0
    nd = spec['live_nd']
    nxt = int(nd['trig_next'], 16)
    for f in (2, 4):
        for key in (4, 2):
            for blk in (False, True):
                b = fd_run(new, f, 211, key, blk)
                n += 1
                ok = b[0] and b[1] == (0x4848, 3, 0x3333, OBJ, 0x5555, STK + 0x1000)
                rs, _ = recs(b[2])
                if blk:
                    run = f == 4 and key == 4
                    ok &= len(rs) == 1 and rs[0][0] >> 24 == 0x46 and rs[0][5] == 3 | (2 << 8) | ((1 if run else 0xee) << 16) and rs[0][3] == 0x48000000
                else:
                    ok &= not rs
                if not ok:
                    bad.append(('F', f, key, blk, b[:2], rs))
        for blk in (False, True):
            ok, vt, r = req_run(new, f, blk)
            n += 1
            rs, h = recs(r)
            ok &= vt != LN.REQF and ((len(rs) == 1 and rs[0][0] >> 24 == 0x51 and struct.unpack_from('<H', h, 10)[0] == 1 and rs[0][5] == 0xff | (2 << 8) | (0xee << 16)) if blk else not rs)
            if not ok:
                bad.append(('Q', f, blk, rs))
    # T: half-press -> file; other events / not dirty / no card / no block -> no file; registers intact at the next target
    for s24, blk, dirty, ev, card, want in ((211, True, 1, SB3.EV_PRESS, True, 'write'), (211, True, 0, SB3.EV_PRESS, True, 'none'),
                                            (211, True, 1, SB3.EV_PRESS + 1, True, 'none'), (211, True, 1, SB3.EV_PRESS, False, 'none'),
                                            (211, False, 0, SB3.EV_PRESS, True, 'alloc'), (1, False, 0, SB3.EV_PRESS, True, 'none')):
        rg, regs = trig_run(new, s24, blk, dirty, ev, card)
        r = execute(rg, regs, nxt, limit=5000)
        rr = r['registers']
        mk = mem(r, 'mark'); h = mem(r, 'heap')
        n += 1
        ok = rr['pc'] == nxt and not r['fault'] and all(rr[k] == v for k, v in regs.items() if k != 'pc')
        wrote = struct.unpack_from('<4I', mk, 0)
        if want == 'write':
            ok &= wrote == (1, BLKN, BLK_AT, 0x1d000000) and struct.unpack_from('<I', mk, 16)[0] == 0x1d000000 and h[BLK_AT - P_AT + 5] == 0 and h[BLK_AT - P_AT + 8] == 1
        else:
            ok &= wrote == (0, 0, 0, 0)
        ptr = struct.unpack_from('<I', h, LN.LOG_POFF)[0]
        if want == 'alloc':
            ok &= ptr == BLK_AT and struct.unpack_from('<I', h, BLK_AT - P_AT)[0] == 0x4c444e4c
        elif not blk:
            ok &= ptr == 0
        if not ok:
            bad.append(('T', s24, blk, dirty, ev, card, want, hex(rr['pc']), wrote, r['fault']))
    return bad, n


def st_run(q, site, sid, f, s24, drv):
    """Real `mov sid,d0; call 0x602afa81,[],4` at `site`, rules getter and setting getter stubbed."""
    rg = [R(q, 'site', site - 0x40, site + 0x40), R(q, 'lnd', LN.AT, LN.END),
          Region('get', LN.GET, stub(LN.GET, {267: f, 24: s24}, 'ret [],4'), 'rx'),
          Region('rget', LN.RGET, stub(LN.RGET, {469: 7, 470: 20, 471: 10, 3281: drv}, 'ret [],4'), 'rx'),
          Region('stk', STK, bytes(0x2000), 'rw')]
    regs = {'pc': site - 3, 'sp': STK + 0x1000, 'd2': 0x2222, 'd3': 0x3333, 'a2': 0x4444, 'a3': 0x5555}
    r = execute(rg, regs, site + 7, limit=600)
    rr = r['registers']
    return (rr['pc'] == site + 7 and not r['fault'], rr['d0'], tuple(rr[k] for k in ('d2', 'd3', 'a2', 'a3', 'sp')))


def t_st(old, new, spec=None):
    """S: the 10 custom self-timer reads. ND3/ND4 + AP ME + drive Custom Self-timer (24): 469 -> N, 470 -> 5, 471 -> 1;
    anything else: the stock value (7 / 20 / 10). Registers and sp as v0.29a."""
    bad, n = [], 0
    if not spec['live_nd'].get('selftimer'):                 # floor: the 10 sites and the drive rule entry are stock
        stk = LN.STOCK.read_bytes()
        bad = [hex(a) for a, _ in LN.ST_SITES if new[a - BASE:a + 4 - BASE] != stk[a - BASE:a + 4 - BASE]]
        bad += [] if new[LN.DRV_CS - BASE:LN.DRV_CS + 2 - BASE] == b'\0\0' else ['drive rule']
        return bad, len(LN.ST_SITES) + 1
    for site, why in LN.ST_SITES:
        sid = 469 if 'frames' in why else 470 if '470' in why else 471
        stock_v = {469: 7, 470: 20, 471: 10}[sid]
        for f in (2, 3, 4):
            for s24 in (211, 3):
                for drv in (24, 1):
                    a, b = st_run(old, site, sid, f, s24, drv), st_run(new, site, sid, f, s24, drv)
                    on = f in (3, 4) and s24 == 211 and drv == 24
                    want = ({469: f, 470: 5, 471: 1}[sid]) if on else stock_v
                    n += 1
                    if not (a[0] and b[0] and a[1] == stock_v and b[1] == want and a[2] == b[2]):
                        bad.append((hex(site), sid, f, s24, drv, a, b, want))
    return bad, n


RE_FN, RE_END = 0x602b2961, 0x602b2fad
RE_STUBS = {0x602b32ae: ' mov 0x6045eb9c,a0\n retf [],0\n', 0x602ef7d8: ' clr d0\n ret [d2],28\n', 0x602e956c: ' clr d0\n ret [d2],28\n',
            0x602ed31f: ' clr d0\n ret [d2,d3],32\n', 0x602e95ac: ' clr d0\n ret [d2,d3],32\n', 0x602ee8eb: ' clr d0\n ret [d2,d3],32\n',
            0x602cc146: ' clr d0\n retf [],0\n', 0x602d9294: ' clr d0\n ret [d2,d3,a2,a3],48\n', 0x602b6709: ' clr d0\n ret [d2],4\n',
            0x602b1eeb: ' clr d0\n retf [],0\n', 0x602b6668: ' clr d0\n ret [d2],8\n', 0x602b6682: ' clr d0\n ret [d2],8\n',
            0x602b669c: ' clr d0\n ret [d2],8\n', 0x602b66b0: ' clr d0\n ret [d2],20\n'}


def rule_run(q, s24, value):
    """The real rule engine 0x602b2961 (value check, kind 0) for the drive sid 3281, record 72 from the image; its
    context helpers return 0 and the setting getter gives sid 24 = s24 and 0 for the rest."""
    caller = _asm(0x18000000, f' mov 3281,d0\n clr d1\n mov {value},a0\n mov 0,a1\n')
    at = 0x18000000 + len(caller)
    caller += b'\xdd' + struct.pack('<i', RE_FN - at) + b'\xf0\x5c\xcb'      # call 0x602b2961,[d2,d3,a2,a3],92; nop
    stop = at + 7
    tbl = {24: s24, 44: 0, 478: 0, 1592: 0, 15206: 0, 4: 0, 109: 0, 605: 0, 3020: 0, 3021: 0, 1145: 0}
    rg = [Region('call', 0x18000000, caller, 'rx'), R(q, 're', RE_FN, RE_END), R(q, 'rules', 0x60430000, 0x60446000, 'r'),
          R(q, 'rec', 0x6045e5fc, 0x6045e5fc + 20 * 201, 'r'), Region('stk', STK, bytes(0x2000), 'rw'),
          Region('get', LN.GET, stub(LN.GET, tbl, 'ret [],4').replace(b'', b'') if False else _asm(LN.GET, ''.join(f' cmp {k},d0\n bne 1{i}f\n mov {v},d0\n ret [],4\n1{i}:\n' for i, (k, v) in enumerate(tbl.items())) + ' clr d0\n ret [],4\n'), 'rx')]
    rg += [Region(f's{a:x}', a, _asm(a, src), 'rx') for a, src in RE_STUBS.items()]
    r = execute(rg, {'pc': 0x18000000, 'sp': STK + 0x1000, 'd2': 0x2222, 'd3': 0x3333, 'a2': 0x4444, 'a3': 0x5555}, stop, limit=40000)
    rr = r['registers']
    return rr['pc'] == stop and not r['fault'], rr['d0'] & 0xffff


def t_rule(old, new, spec=None):
    """R: the drive (3281) value check in the real engine. v0.29a: Custom Self-timer (24) allowed in P, greyed (256) in
    AP Multiple Exposure. New: allowed in both; Sequential H (1) and Silent single (30) unchanged."""
    bad, n = [], 0
    st = spec['live_nd'].get('selftimer')
    for s24, value, want_old, want_new in ((3, 24, 0, 0), (211, 24, 256, 0), (211, 1, 0, 0), (211, 30, 256, 256), (3, 30, 0, 0), (210, 24, 256, 256)):
        a, b = rule_run(old, s24, value), rule_run(new, s24, value)
        want_new = want_new if st else want_old
        n += 1
        if not (a[0] and b[0] and a[1] == want_old and b[1] == want_new):
            bad.append((s24, value, a, b, want_old, want_new))
    return bad, n


def t_pkg(base_s, new_s, old, new, pkg, rst, info, disk):
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
    ours = [(int(e['addr'], 16), len(e['new']) // 2) for e in new_s['edits'] if e.get('source') in ('patches/live_nd', 'patches/fw_version')]
    if new_s['live_nd'].get('log'):
        ours.append((LN.SD_BACK + 1, 4))             # readout: sd_back rel32 inside the loader edit
    diff = [BASE + i for i in range(len(old)) if old[i] != new[i]]
    stray = [hex(a) for a in diff if not any(s_ <= a < s_ + k for s_, k in ours)]
    good &= not stray
    base_ids = {(e['addr'], e['new']) for e in base_s['edits'] if e.get('source') != 'patches/fw_version'}
    new_ids = {(e['addr'], e['new']) for e in new_s['edits'] if e.get('source') not in ('patches/fw_version', 'patches/live_nd')}
    if new_s['live_nd'].get('log'):                  # the loader edit differs only in the sd_back rel32
        def unsd(e):
            if e[0].startswith('off:'):
                return e
            a = int(e[0], 16); b = bytearray.fromhex(e[1]); o = LN.SD_BACK + 1 - a
            if 0 <= o < len(b):
                b[o:o + 4] = b'\0\0\0\0'
            return (e[0], b.hex())
        base_ids, new_ids = {unsd(e) for e in base_ids}, {unsd(e) for e in new_ids}
    good &= base_ids == new_ids
    if disk:
        good &= (disk / 'patched.pkg.bin').read_bytes() == pkg and (disk / 'restore-stock.pkg.bin').read_bytes() == rst
    return good, f'{info["edits"]} edits, {info["changed_payload_bytes"]} B; {len(diff)} B differ from v0.29a; stray {stray[:6]}'


def main():
    base_s, new_s = (json.loads(Path(p).read_text()) for p in sys.argv[1:3])
    disk = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    old, *_ = image(base_s)
    new, pkg, rst, info = image(new_s)
    ok = True
    for name, fn in (('H hooks', lambda: t_hooks(old, new)), ('G grey-out', lambda: t_greyout(old, new)), ('F safe floor', lambda: t_floor(new)), ('K no burst-engine hooks', lambda: t_cap(old, new, new_s)), ('S self-timer reads', lambda: t_st(old, new, new_s)), ('R drive rule', lambda: t_rule(old, new, new_s)), ('L readout', lambda: t_log(new, new_s)), ('D data', lambda: t_data(new, new_s))):
        bad, n = fn(); ok &= not bad
        print(f"{'PASS' if not bad else 'FAIL'} {name}: {n - len(bad)}/{n}", bad[:4] if bad else '', flush=True)
    good, txt = t_pkg(base_s, new_s, old, new, pkg, rst, info, disk); ok &= good
    print(f"{'PASS' if good else 'FAIL'} P anti-brick: {txt}")
    print('ALL PASS' if ok else 'FAILURES')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
