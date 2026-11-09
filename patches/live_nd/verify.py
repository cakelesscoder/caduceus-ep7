#!/usr/bin/env python3
"""Emulator + static checks for live_nd n8 (real firmware code at every hooked site; the getters are stubbed). Offline.

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


def burst_run(q, s24, f, key, busy, rel):
    """Real ME continuous frame-done tail 0x6096b012..0x6096b020 with stand-ins: flag (d3 |= 1), key state, release
    check, sendTakePictureContinue (d3 |= 2). Returns (ok, d3 marks, d2, a2, sp)."""
    obj = bytearray(1024)
    struct.pack_into('<I', obj, 212, busy)
    rg = [R(q, 'site', 0x6096afc0, 0x6096b040), R(q, 'lnd', LN.AT, LN.END), Region('obj', 0x1a000000, bytes(obj), 'r'),
          Region('get', LN.GET, stub(LN.GET, {267: f, 24: s24}, 'ret [],4'), 'rx'),
          Region('flag', LN.FLAG, _asm(LN.FLAG, ' or 1,d3\n ret [d2],4\n'), 'rx'),
          Region('key', LN.KEYST, _asm(LN.KEYST, f' mov {key},d0\n retf [],0\n'), 'rx'),
          Region('rel', LN.RELCHK, _asm(LN.RELCHK, f' mov {rel},d0\n ret [d2,d3,a2,a3],56\n'), 'rx'),
          Region('cont', LN.CONT, _asm(LN.CONT, ' cmp 0x1a000000,a0\n bne 1f\n mov 0x1b000000,a1\n mov 2,d0\n mov d0,(a1)\n1:\n ret [d2,d3,a2,a3],20\n'), 'rx'),
          Region('mark', 0x1b000000, bytes(16), 'rw', True), Region('stk', STK, bytes(0x2000), 'rw')]
    r = execute(rg, {'pc': 0x6096b012, 'sp': STK + 0x1000, 'a2': 0x1a000000, 'd2': 0x2222, 'd3': 0}, 0x6096b020, limit=800)
    rr = r['registers']
    mark = struct.unpack_from('<I', {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}['mark'], 0)[0]
    return rr['pc'] == 0x6096b020 and not r['fault'], rr['d3'] | mark, rr['d2'], rr['a2'], rr['sp']


def t_burst(old, new):
    bad, n = [], 0
    for s24 in (211, 1):
        for f in (2, 3, 4):
            for key in (4, 2):
                for busy in (0, 1):
                    for rel in (1, 0):
                        if (busy or not rel) and (s24 != 211 or f == 2 or key != 4):
                            continue           # keep the run count small: busy / release-check cases only where they matter
                        a, b = burst_run(old, s24, f, key, busy, rel), burst_run(new, s24, f, key, busy, rel)
                        go = s24 == 211 and f in (3, 4) and key == 4 and not busy and rel == 1
                        n += 1
                        if not (a[0] and b[0] and a[1] == 1 and b[1] == (3 if go else 1) and a[2:] == b[2:]):
                            bad.append((s24, f, key, busy, rel, a, b))
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
    diff = [BASE + i for i in range(len(old)) if old[i] != new[i]]
    stray = [hex(a) for a in diff if not any(s_ <= a < s_ + k for s_, k in ours)]
    good &= not stray
    base_ids = {(e['addr'], e['new']) for e in base_s['edits'] if e.get('source') != 'patches/fw_version'}
    new_ids = {(e['addr'], e['new']) for e in new_s['edits'] if e.get('source') not in ('patches/fw_version', 'patches/live_nd')}
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
    for name, fn in (('H hooks', lambda: t_hooks(old, new)), ('G grey-out', lambda: t_greyout(old, new)), ('F safe floor', lambda: t_floor(new)), ('B burst continue', lambda: t_burst(old, new)), ('D data', lambda: t_data(new, new_s))):
        bad, n = fn(); ok &= not bad
        print(f"{'PASS' if not bad else 'FAIL'} {name}: {n - len(bad)}/{n}", bad[:4] if bad else '', flush=True)
    good, txt = t_pkg(base_s, new_s, old, new, pkg, rst, info, disk); ok &= good
    print(f"{'PASS' if good else 'FAIL'} P anti-brick: {txt}")
    print('ALL PASS' if ok else 'FAILURES')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
