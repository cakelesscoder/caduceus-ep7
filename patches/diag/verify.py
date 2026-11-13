#!/usr/bin/env python3
"""diag layer checks (emulator, offline). Minimal + anti-brick, scoped to what the layer changes. docs/PLUGINS.md §10.

  .venv/bin/python -I patches/diag/verify.py BASE.json NEW.json [generated/v032/rel] [PLUGIN.BIN]

BASE = the v0.32 camera spec (diag=False), NEW = the built spec (must equal diag.apply(BASE)). Whole patched main image,
mapped read-only (a store into it faults).
  S  static: every byte NEW changes vs BASE is inside a diag edit; diag.apply(BASE) == NEW.
  L  loader stages: ap_post from entry (real ap_P, ap_load, dg_ap, CRC, init; file services / malloc stubbed as in
     plugin_loader/verify.py) -> L 0..7 in boot byte bits 1-3 for every case; other boot bits kept; a stale 'EP7K'
     from an earlier session is cleared; with no PLUGIN.BIN, registers, stack, P, the AP heap == BASE.
  O  one overlay paint (alive, Extras, log on): four rows, the window's style selected and the font released, gc+0x4c
     and gc+0x34 as found after, PT/PD/PS logged, registers and sp; view not alive (log off / on) == BASE.
  K  key sites 0x60ce011a / 0x60cebc9a / twin 0x60ce0190: 12 sample event codes x 3 CA states, no log and log on,
     == BASE (registers, stack, record, CA, P); log on adds one (site, event, state, record+4) entry.
  H  half-press dump: write path (title, header, entries; fopen "w" TRACE.TXT), two in a row, wrapped ring, fopen
     fail (log kept), log off / other event == BASE.
  F  Firmware screen, both Body sites: "L/OK" for a set of states (K from the keyhook stage byte 0x6203bcb2); an empty field passes through as in BASE.
  P  package anti-brick: decode == stock + edits == the emulated image, restore == stock, files on disk match.
"""
import json, struct, sys, importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'external/oly_fw_analysis/tools'))
import build_package as BP  # noqa: E402
import oly_container as oc  # noqa: E402
from penf_emulator import Region, execute  # noqa: E402


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


DG = _load('ep7_diag_build_v', ROOT / 'patches/diag/build.py')
PLV = _load('ep7_pl_verify_dg', ROOT / 'patches/plugin_loader/verify.py')
OVV = _load('ep7_ov_verify_dg', ROOT / 'patches/overlay_probe/verify.py')
SCB = _load('ep7_sc_build_dg', ROOT / 'tools/plugins/shortcut_cycle/build.py')
PL, SB3 = DG.PL, DG.SB3
BASE = 0x60020020
STOCK = PL.STOCK.read_bytes()
BOOTR = 0x6203c8b0                                   # 16 B region; boot byte at +0xb
BSSR = 0x622ab790                                    # 8 B region; flag at +2, counter at +3
HANDLE, P_AT, BLK = PLV.HANDLE, PLV.P_AT, PLV.BLK
EP7K = int.from_bytes(b'EP7K', 'little')


def img(spec):
    return bytes(PL.ST.img_of(spec, STOCK))


# ---------------------------------------------------------------- L
def run_post(prep, ap=None, plugin=None, p=None, big_ok=True, seek_fail=0, short=0, ev=PLV.EV_PRESS, boot=0):
    im, code = prep
    fsc = struct.pack('<8I', len(ap or b''), len(plugin or b''), seek_fail, short, BLK if big_ok else 0,
                      PLV.H_PL if plugin is not None else 0, PLV.H_AP if ap is not None else 0, PLV.HEAP)
    stk = bytearray(0x1000); struct.pack_into('<I', stk, 0x800 + 16, ev)
    bt = bytearray(16); bt[0xb] = boot
    b = bytes(16384)
    rg = [Region('img', BASE, im, 'rx'), Region('stubs', PLV.STUBS, code, 'rx'),
          Region('state', 0x622cbcc0, struct.pack('<HHI', 0, HANDLE, 0), 'rw', True),
          Region('pool', P_AT, p or PLV.pblock(), 'rw', True),
          Region('heap', PLV.HEAP, bytes(0x2000), 'rw', True),
          Region('blk', BLK, b, 'rw', True), Region('blkc', PLV.BLKC, b, 'rx', alias_of='blk'),
          Region('log', PLV.LOG, bytes(0x100), 'rw', True), Region('fsc', PLV.FSC, fsc, 'rw', True),
          Region('fsap', PLV.FSAP, (ap or b'').ljust(0x400, b'\0'), 'r'),
          Region('fspl', PLV.FSPL, (plugin or b'').ljust(0x4800, b'\0'), 'r'),
          Region('boot', BOOTR, bytes(bt), 'rw', True), Region('logon', 0x6203bcb0, bytes(4), 'rw', True),
          Region('stack', PLV.STKR, bytes(stk), 'rw', True)]
    r = execute(rg, dict(PLV.REGS0, pc=PLV.AP_POST, sp=PLV.STK), PLV.AP_TAIL, limit=2_000_000, timeout=120)
    mem = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}
    return r, mem, struct.unpack_from('<11I', mem['log'])


def prep_for(m, spec, path):
    s = dict(spec); s['plugin_loader'] = dict(spec['plugin_loader'], symbols=dict(spec['plugin_loader']['symbols'], pl_path=hex(path)))
    return PLV.prepare(m, s)


def t_l(base, new, base_s, new_s, card):
    apf = PLV.AV.apfile()
    pb = PLV.prepare(base, base_s)
    pn = prep_for(new, new_s, int(new_s['diag']['symbols']['dg_path'], 16))
    good = PLV.count_plugin()
    V = {n: (f, kw) for n, f, kw in PLV.variants(good)}
    cases = [('not a half-press', None, dict(ev=0), 0), ('EP7U already set', None, dict(p=PLV.pblock(atr=True)), 0),
             ('no PLUGIN.BIN', None, {}, 1), ('malloc fails', good, dict(big_ok=False), 1)]
    for n, want in (('33 B', 2), ('16385 B', 2), ('short read', 2), ('seek fails', 2), ('magic', 3), ('ABI 2', 3),
                    ('flags 1', 3), ('firmware id', 4), ('size field', 5), ('CRC', 5), ('code byte', 5)):
        f, kw = V[n]
        cases.append((n, f, kw, want))
    cases += [('decline', PLV.count_plugin(ret=1), {}, 6), ('accept', good, {}, 7)]
    if card:
        cases.append(('shortcut_cycle', card, {}, 7))
    bad, seen = [], []
    for name, f, kw, want in cases:
        r, m, lg = run_post(pn, ap=apf, plugin=f, **kw)
        L = (m['boot'][0xb] >> 1) & 7
        p = m['pool']
        ok = not r['fault'] and r['registers']['pc'] == PLV.AP_TAIL and L == want
        if want == 7:
            ok &= p[PL.PS:PL.PS + 4] == b'EP7K' and struct.unpack_from('<I', p, PL.PB)[0] == BLK and lg[8] == 0
        elif want >= 1:
            ok &= p[PL.PS:PL.PS + 4] == bytes(4)
        if want in (2, 3, 4, 5):
            ok &= lg[8] == 1                       # block freed
        seen.append(f'{name}:L{L}')
        if not ok:
            bad.append((name, r['fault'], hex(r['registers']['pc']), L))
    # stale ready mark from an earlier session + boot bits kept + no file == BASE (apart from L and the cleared mark)
    stale = PLV.pblock(EP7K, BLK)
    rb = run_post(pb, ap=apf, p=stale, boot=0x31)
    rn = run_post(pn, ap=apf, p=stale, boot=0x31)
    pB, pN = bytearray(rb[1]['pool']), bytearray(rn[1]['pool'])
    ok = rN_ok = not rn[0]['fault'] and pN[PL.PS:PL.PS + 4] == bytes(4) and rn[1]['boot'][0xb] == 0x33
    pB[PL.PS:PL.PS + 4] = pN[PL.PS:PL.PS + 4]
    ok &= struct.unpack_from('<I', pN, DG.PLOG)[0] == BLK and rn[1]['logon'][3] == 1   # log block taken after the plugin
    pB[DG.PLOG:DG.PCNT + 4] = pN[DG.PLOG:DG.PCNT + 4]
    g0, g1 = rb[0]['registers'], rn[0]['registers']
    sp = g1['sp'] - PLV.STKR
    ok &= all(g0[k] == g1[k] for k in PLV.KEEP) and rb[1]['stack'][sp:] == rn[1]['stack'][sp:] and pB == pN
    ok &= rb[1]['heap'] == rn[1]['heap'] and rb[1]['state'] == rn[1]['state'] and rb[1]['boot'][0xb] == 0x31
    if apf:
        ok &= rn[1]['pool'][PLV.AV.A.AM:PLV.AV.A.AM + 4] == b'EP7A'
    if not ok:
        bad.append(('stale / == BASE', rN_ok, rn[1]['boot'][0xb]))
    return not bad, f"{len(cases)} cases {' '.join(seen)}; stale EP7K cleared, boot 0x31 -> 0x33, rest == BASE; bad {bad[:3]}"


# ---------------------------------------------------------------- shared TRACE fixtures
LOGR = 0x6203bcb0                                    # 4 B: [.., .., kstage, logon]
LOGB = DG.POOL2                                      # the log block (inside the class-2 pool)


def p_with_log(p, head=0, pcnt=0, base=LOGB):
    p = bytearray(p)
    struct.pack_into('<III', p, DG.PLOG, base, head, pcnt)
    return bytes(p)


def logon_region(on, kst=0):
    return Region('logon', LOGR, bytes([0, 0, kst, 1 if on else 0]), 'rw', True)


def log_entries(m, n):
    return [struct.unpack_from('<4I', m['logb'], 16 * i) for i in range(n)]


# ---------------------------------------------------------------- O (one paint check + not-alive == BASE)
STK, SP0 = 0x18010000, 0x18011800
WIN, VT, GC, CALLER = 0x17000000, 0x17001000, 0x16000000, 0x18000000
REGS = dict(d0=0xd0d0, d1=0xd1d1, d2=0x2222, d3=WIN, a0=WIN, a1=GC, a2=VT, a3=0xa3a3, mdr=0x6d6d6d6d)
DRAW_STUB = OVV.DRAW_STUB.replace(" mov d1,(a3)              /* string[n] at REC+0x20+4n */",
                                  " mov d1,(a3)              /* string[n] at REC+0x20+4n */\n"
                                  " mov (12,a2),a1\n mov (a1),d1\n mov d1,(64,a3)           /* style +0 at REC+0x60+4n */")
assert DRAW_STUB != OVV.DRAW_STUB
FONT_STUB = """ .am33_2
 .text
 .global _start
_start:
 mov 0x13000050,a1         /* REC+0x50: style id, +0x54 calls, +0x58 font to return */
 mov d0,(a1)
 mov (4,a1),d0
 inc d0
 mov d0,(4,a1)
 mov (8,a1),d0
 cmp 0,d0
 beq 1f
 mov d0,(76,a0)            /* gc+0x4c = font, as 0x60d0fd74 */
1:
 mov d0,a0
 ret [a2],8
"""
FREL_STUB = """ .am33_2
 .text
 .global _start
_start:
 mov 0x13000070,a1         /* REC+0x70: released font, +0x74 calls */
 mov a0,(a1)
 mov (4,a1),d0
 inc d0
 mov d0,(4,a1)
 ret [],4
"""
GCR = GC + 0x1000                                    # the real gc = *(painter+8); the painter is at GC
FSTUB = 0x15000000                                   # window +488 stub


def with_stubs(im, extra=()):
    b = bytearray(im)
    for at, src in ((DG.OV.DRAWTEXT, DRAW_STUB), (DG.OV.SETCOL, OVV.SETCOL_STUB), (DG.SETFONT, FONT_STUB),
                    (DG.FREL, FREL_STUB)) + tuple(extra):
        c, _ = OVV.asm(src, at)
        b[at - BASE:at - BASE + len(c)] = c
    return bytes(b)


def o_regions(im, flag=0, axis=4, font=0x16100000, mode=0x7777, setfont_ret=0x16200000, logon=False):
    bss = bytearray(8); bss[2] = flag
    stk = bytearray([0xa5] * 0x2000); struct.pack_into('<I', stk, SP0 - STK + 4, GC)    # paint's (4,sp) = painter
    vt = bytearray(0x300); struct.pack_into('<I', vt, 164, DG.WIN_STOCK); struct.pack_into('<I', vt, 488, FSTUB)
    gc = bytearray(0x2000); struct.pack_into('<I', gc, 8, GCR); struct.pack_into('<I', gc, 0x1000 + 76, font)
    struct.pack_into('<H', gc, 0x1000 + 52, mode)
    rec = bytearray(0x80); struct.pack_into('<I', rec, 0x58, setfont_ret)
    win = bytearray(0x600); struct.pack_into('<I', win, 0, VT); win[108] = 7
    w488, _ = OVV.asm(" .am33_2\n .text\n .global _start\n_start:\n movhu (108,a0),d0\n retf [],0\n", FSTUB)
    pool = p_with_log(OVV.pget(HANDLE, SB3.MAGIC, axis))
    return [Region('img', BASE, im, 'rx'), Region('stack', STK, bytes(stk), 'rw', True),
            Region('bss', BSSR, bytes(bss), 'rw', True), Region('rec', OVV.REC, bytes(rec), 'rw', True),
            Region('gc', GC, bytes(gc), 'rw', True), Region('win', WIN, bytes(win), 'rw', True),
            Region('vt', VT, bytes(vt), 'r'), Region('fstub', FSTUB, w488, 'rx'),
            Region('curwin', DG.CURWIN, struct.pack('<I', WIN), 'r'),
            Region('state', 0x622cbcc0, struct.pack('<HHI', 0, HANDLE, 0), 'r'),
            Region('pool', OVV.P, pool, 'rw', True), Region('logb', LOGB, bytes(0x4000), 'rw', True),
            logon_region(logon)]


def mem(r):
    return {m['name']: bytes.fromhex(m['hex']) for m in r['memory']}


def paint(im, **kw):
    r = execute(o_regions(im, **kw), dict(REGS, pc=DG.PAINT, sp=SP0), DG.PAINT_BACK, limit=80000)
    return r, mem(r)


def t_o(base, new, new_s):
    sy = {k: int(v, 16) for k, v in new_s['diag']['symbols'].items()}
    bad, info = [], []
    nb, ns = with_stubs(base), with_stubs(new)
    ks = ('d0', 'd1', 'd2', 'd3', 'a1', 'a2', 'a3', 'sp', 'pc')
    for fl, lo in ((0, False), (0x70, True)):          # view not alive (with and without the log): == BASE
        r0, m0 = paint(nb, flag=fl, logon=lo)
        r1, m1 = paint(ns, flag=fl, logon=lo)
        g0, g1 = r0['registers'], r1['registers']
        ok = not r0['fault'] and not r1['fault'] and all(g0[k] == g1[k] for k in ks)
        ok &= m0['stack'][g1['sp'] + 4 - STK:] == m1['stack'][g1['sp'] + 4 - STK:]
        ok &= all(m0[k] == m1[k] for k in ('bss', 'rec', 'gc', 'pool', 'logb', 'logon'))
        if not ok:
            bad.append(('paint off', fl, r1['fault'], {k: (hex(g0[k]), hex(g1[k])) for k in ks if g0[k] != g1[k]}))
    info.append('paint, view not alive (log off / on) == BASE')
    # the one overlay paint: alive, Extras page, log on. gc+0x4c / gc+0x34 as found after, font selected and released
    r, m = paint(ns, flag=0x11, logon=True)
    rec, g = m['rec'], r['registers']
    cols = [struct.unpack_from('<I', rec, 0x60 + 4 * i)[0] for i in range(rec[0])]
    font, mode = struct.unpack_from('<I', m['gc'], 0x1000 + 76)[0], struct.unpack_from('<H', m['gc'], 0x1000 + 52)[0]
    sid, nsel = struct.unpack_from('<2I', rec, 0x50)
    rel, nrel = struct.unpack_from('<2I', rec, 0x70)
    head = struct.unpack_from('<I', m['pool'], DG.PHEAD)[0]
    e = log_entries(m, head // 16)
    ok = (not r['fault'] and g['pc'] == DG.PAINT_BACK and rec[0] == 4 and cols == [1, 2, 4, 6]
          and font == 0x16100000 and mode == 0x7777 and (sid, nsel) == (7, 1) and (rel, nrel) == (0x16200000, 1)
          and m['gc'][:0x1000] == o_regions(ns)[4].data[:0x1000] and m['bss'][2] == 0x73
          and g['sp'] == SP0 and g['d0'] == 0xd0d0 and g['d1'] == 0xd1d1 and all(g[k] == REGS[k] for k in ('d2', 'd3', 'a3'))
          and head == 48 and [x[0] & 0xff for x in e] == [DG.T_PAINT, DG.T_PD, DG.T_PS]
          and e[0][1:] == (WIN, VT, GC) and e[1][1:] == (GCR, 0x16100000, 0x16100000) and (e[1][0] >> 8) & 1 == 1
          and (e[1][0] >> 12) & 15 == 4 and e[1][0] >> 16 == 0x7777 and e[2][1] == SP0 and e[2][2] == SP0
          and struct.unpack_from('<I', m['pool'], DG.PCNT)[0] == 1)
    if not ok:
        bad.append(('paint draw', r['fault'], hex(g['pc']), rec[0], cols, hex(font), hex(mode), (sid, nsel), (hex(rel), nrel),
                    hex(m['bss'][2]), head, [tuple(hex(v) for v in x) for x in e]))
    info.append(f'one overlay paint: 4 rows, style 7 selected + released, gc+0x4c / +0x34 as found, PT/PD/PS logged, '
                f'sp {g["sp"]:#x} in = out')
    return not bad, '; '.join(info) + f'; bad {bad[:2]}'


# ---------------------------------------------------------------- K (key sites: sample events x CA states)
K_EVENTS = (0x0100002e, 0x0100002f, 0x02000100, 0x01040000, 0x01040001, 0x01050000, 0x01050001,
            0x01000000, 0x01000001, 0x01000002, 0x01000003, 0x01000037)
K_STATES = (0x5100, 0x5800, 0x5a03)
CA, RECK, KSTK, KSP = 0x17800000, 0x17900000, 0x18100000, 0x18100800
KMAP_STUB = """ .am33_2
 .text
 .global _start
_start:
 mov 0x13000000,a1         /* REC+0: kmap args d0, a0, a1(in), d1, calls */
 mov d0,(a1)
 mov a0,(4,a1)
 mov d1,(12,a1)
 mov (16,a1),d0
 inc d0
 mov d0,(16,a1)
 mov 0x77,d0
 ret [d2],4
"""


def k_run(im, site, resume, ev, st, logon, frame=28):
    rec = bytearray(0x200)
    struct.pack_into('<6I', rec, 0, ev, 0x98, 0x1111, 0x2222, 0x3333, 0x4444); struct.pack_into('<I', rec, 196, st)
    stk = bytearray(0x1000)
    o = KSP - KSTK
    stk[o + 4:o + 28] = rec[:24]
    struct.pack_into('<I', stk, o + frame + 16, 0xc0dec0de)
    rg = [Region('img', BASE, im, 'rx'), Region('rec', OVV.REC, bytes(0x40), 'rw', True),
          Region('state', 0x622cbcc0, struct.pack('<HHI', 0, HANDLE, 0), 'rw', True),
          Region('pool', P_AT, p_with_log(PLV.pblock()), 'rw', True), Region('logb', LOGB, bytes(0x4000), 'rw', True),
          Region('ca', CA, bytes(0x400), 'rw', True), Region('krec', RECK, bytes(rec), 'rw', True),
          Region('stack', KSTK, bytes(stk), 'rw', True), logon_region(logon, 0x5a)]
    regs = dict(d0=struct.unpack_from('<I', rec, 20)[0], d1=0, d2=0xd2d2, d3=0xd3d3, a0=KSP + 28, a1=RECK + 24,
                a2=RECK, a3=CA, mdr=0x6d6d, pc=site, sp=KSP)
    r = execute(rg, regs, resume, limit=20000, timeout=60)
    return r, mem(r)


def t_k(base, new):
    nb, ns = (with_stubs(x, ((DG.KMAP, KMAP_STUB),)) for x in (base, new))
    sites = (('K0', DG.SITE0, 0x60ce0121, DG.T_KEY0), ('K1', DG.SITE1, 0x60cebca1, DG.T_KEY1),
             ('KT', DG.TWIN, DG.TWIN_BACK, DG.T_KEYT))
    ks = ('d0', 'd1', 'd2', 'd3', 'a0', 'a1', 'a2', 'a3', 'sp', 'pc')
    bad, n = [], 0
    for name, site, resume, tag in sites:
        for ev in K_EVENTS:
            for st in K_STATES:
                r0, m0 = k_run(nb, site, resume, ev, st, False)
                for lo in (False, True):
                    r1, m1 = k_run(ns, site, resume, ev, st, lo)
                    n += 1
                    g0, g1 = r0['registers'], r1['registers']
                    sp = g1['sp'] - KSTK + 4                      # (0,sp) = the kmap call slot (return address)
                    ok = not r0['fault'] and not r1['fault'] and all(g0[k] == g1[k] for k in ks)
                    ok &= m0['stack'][sp:] == m1['stack'][sp:] and m0['rec'] == m1['rec']
                    ok &= all(m0[k] == m1[k] for k in ('state', 'ca', 'krec'))
                    ok &= lo or m1['logon'] == m0['logon']
                    head = struct.unpack_from('<I', m1['pool'], DG.PHEAD)[0]
                    if lo:
                        ok &= head == 16 and log_entries(m1, 1)[0] == (tag, ev, st, 0x98)
                        p0, p1 = bytearray(m0['pool']), bytearray(m1['pool'])
                        p1[DG.PHEAD:DG.PHEAD + 4] = p0[DG.PHEAD:DG.PHEAD + 4]
                        ok &= p0 == p1
                    else:
                        ok &= m0['pool'] == m1['pool'] and m1['logb'] == bytes(0x4000)
                    if not ok:
                        bad.append((name, hex(ev), hex(st), lo, r1['fault'], hex(g1['pc']), head,
                                    {k: (hex(g0[k]), hex(g1[k])) for k in ks if g0[k] != g1[k]}))
    return not bad, (f'{n} runs: 3 sites x {len(K_EVENTS)} events x {len(K_STATES)} CA states x (no log, log) == BASE '
                     f'(registers, stack, record, CA, P); log on -> one (site, event, state, record+4) entry; bad {bad[:2]}')


# ---------------------------------------------------------------- H (half-press dump)
CTL, OUT, FH = 0x13100000, 0x13200000, 0x4400
FOPEN_STUB = f""" .am33_2
 .text
 .global _start
_start:
 mov a1,d1
 mov {CTL:#x},a1
 mov a0,(a1)               /* +0 path, +4 fail flag, +8 opens, +12 mode */
 mov d1,(12,a1)
 mov (8,a1),d0
 inc d0
 mov d0,(8,a1)
 mov (4,a1),d0
 cmp 0,d0
 bne 1f
 mov {FH:#x},a0
 ret [],4
1:
 mov 0,a0
 ret [],4
"""
FWRITE_STUB = f""" .am33_2
 .text
 .global _start
_start:
 mov {CTL:#x},a2
 mov a1,(16,a2)            /* +16 handle, +20 calls, +24 d0, +28 bytes so far, +36 bad args */
 mov (20,a2),d2
 inc d2
 mov d2,(20,a2)
 mov d0,(24,a2)
 cmp 1,d0
 beq 3f
 mov 1,d2
 mov d2,(36,a2)
3:
 mov {OUT:#x},a3
 mov (28,a2),d2
 add d2,a3
 add d1,d2
 mov d2,(28,a2)
1:
 cmp 0,d1
 beq 2f
 movbu (a0),d2
 movbu d2,(a3)
 inc a0
 inc a3
 add -1,d1
 bra 1b
2:
 ret [d2,d3,a2,a3],24
"""
FCLOSE_STUB = f""" .am33_2
 .text
 .global _start
_start:
 mov {CTL:#x},a1
 mov a0,(40,a1)            /* +40 handle, +32 closes */
 mov (32,a1),d0
 inc d0
 mov d0,(32,a1)
 clr d0
 ret [d2,a2,a3],16
"""


def h_run(im, head=0, logon=True, fail=0, entries=b'', ev=PLV.EV_PRESS, boot=0x0e, flag=0x71, kst=0x15):
    ctl = bytearray(0x40); struct.pack_into('<I', ctl, 4, fail)
    stk = bytearray(0x1000); struct.pack_into('<I', stk, 0x800 + 16, ev)
    bt = bytearray(16); bt[0xb] = boot
    bss = bytearray(8); bss[2] = flag
    rg = [Region('img', BASE, im, 'rx'), Region('fst', FST, fst_code(), 'rx'),
          Region('state', 0x622cbcc0, struct.pack('<HHI', 0, HANDLE, 0), 'rw', True),
          Region('pool', P_AT, p_with_log(PLV.pblock(atr=True), head, 5), 'rw', True),
          Region('logb', LOGB, entries.ljust(0x4000, b'\0'), 'rw', True),
          Region('ctl', CTL, bytes(ctl), 'rw', True), Region('out', OUT, bytes(0x10000), 'rw', True),
          Region('boot', BOOTR, bytes(bt), 'r'), Region('bss', BSSR, bytes(bss), 'r'),
          logon_region(logon, kst), Region('stack', PLV.STKR, bytes(stk), 'rw', True)]
    r = execute(rg, dict(PLV.REGS0, pc=PLV.AP_POST, sp=PLV.STK), PLV.AP_TAIL, limit=3_000_000, timeout=300)
    m = mem(r)
    c = struct.unpack_from('<11I', m['ctl'])
    return r, m, c, m['out'][:c[7]]


def want_text(bid, lok, total, ents):
    line = lambda w: ' '.join(f'{x:08X}' for x in w) + '\n'
    return (DG.TITLE + line((0xffffffff, bid, lok, total)).encode() + b''.join(line(e).encode() for e in ents))


FST = 0x13300000                                    # file-service stubs (fopen / fclose are 9 B thunks: trampolines)


def file_stubs(im):
    b = bytearray(im)
    for i, (at, src) in enumerate(((PL.SYMS['ep7_fopen'], FOPEN_STUB), (DG.FWRITE, FWRITE_STUB),
                                   (PL.SYMS['ep7_fclose'], FCLOSE_STUB))):
        b[at - BASE:at - BASE + 5] = PLV.tramp(at, FST + 0x100 * i)
    return bytes(b)


def fst_code():
    c = bytearray(0x300)
    for i, src in enumerate((FOPEN_STUB, FWRITE_STUB, FCLOSE_STUB)):
        x, _ = OVV.asm(src, FST + 0x100 * i)
        c[0x100 * i:0x100 * i + len(x)] = x
    return bytes(c)


def t_h(base, new, new_s):
    nb, ns = (file_stubs(x) for x in (base, new))
    bid = int(new_s['diag']['trace']['build_id'], 16)
    lok = (7 << 16) | (0x71 << 8) | 0x15
    ents = [(i % 8, 0x01000000 + i, 0x5800 + i, 0x98 + i) for i in range(3)]
    raw = b''.join(struct.pack('<4I', *e) for e in ents)
    bad, info = [], []
    ks = ('d0', 'd1', 'd2', 'd3', 'a0', 'a1', 'a2', 'a3', 'sp', 'pc')
    # write path: 3 entries -> title, header, 3 lines; one open ("w", TRACE.TXT), one close; head and paint cap reset
    r0, m0, c0, _ = h_run(nb, 48, entries=raw)
    r, m, c, txt = h_run(ns, 48, entries=raw)
    ok = not r['fault'] and r['registers']['pc'] == PLV.AP_TAIL and txt == want_text(bid, lok, 3, ents)
    ok &= c[2] == 1 and c[3] == DG.WMODE and c[8] == 1 and c[4] == FH and c[10] == FH and c[9] == 0
    ok &= c[0] == int(new_s['diag']['symbols']['dg_tpath'], 16)
    ok &= struct.unpack_from('<2I', m['pool'], DG.PHEAD) == (0, 0)
    ok &= all(r0['registers'][k] == r['registers'][k] for k in ks) and c0[2] == 0
    if not ok:
        bad.append(('write', r['fault'], hex(r['registers']['pc']), c, txt[:120]))
    info.append(f'write: {len(txt)} B, title + header + 3 lines, 1 fopen "w" / {c[5]} fwrite / 1 fclose, log reset, '
                f'registers at the ap_post tail == BASE')
    # second half-press, nothing new: no open; then a new entry: written again
    r2, m2, c2, _ = h_run(ns, 0, entries=raw)
    r3, m3, c3, t3 = h_run(ns, 16, entries=raw)
    ok = not r2['fault'] and c2[2] == 0 and not r3['fault'] and c3[2] == 1 and t3 == want_text(bid, lok, 1, ents[:1])
    if not ok:
        bad.append(('two dumps', c2[2], c3[2], t3[:80]))
    info.append('two in a row: nothing new -> no open; one new entry -> written again')
    # wrapped ring: oldest first from head & mask
    big = bytearray(0x4000)
    for i in range(1024):
        struct.pack_into('<4I', big, 16 * i, 0, i, 0, 0)
    head = 0x4000 + 32
    r4, m4, c4, t4 = h_run(ns, head, entries=bytes(big))
    order = [(0, (i + 2) % 1024, 0, 0) for i in range(1024)]
    ok = not r4['fault'] and t4 == want_text(bid, lok, head // 16, order)
    if not ok:
        bad.append(('wrap', r4['fault'], len(t4)))
    info.append('wrapped ring: 1024 lines, oldest first')
    # fopen fails: no write, no close, log kept for the next half-press
    r5, m5, c5, t5 = h_run(ns, 48, fail=1, entries=raw)
    ok = not r5['fault'] and c5[2] == 1 and c5[5] == 0 and c5[8] == 0 and t5 == b''
    ok &= struct.unpack_from('<I', m5['pool'], DG.PHEAD)[0] == 48 and all(r0['registers'][k] == r5['registers'][k] for k in ks)
    if not ok:
        bad.append(('fopen fail', c5))
    info.append('fopen fails: no fwrite / fclose, log kept')
    # log off / not a half-press: == BASE, no file call
    for kw in (dict(logon=False), dict(ev=0)):
        ra, ma, ca, _ = h_run(nb, 48, entries=raw, **kw)
        rb, mb, cb, _ = h_run(ns, 48, entries=raw, **kw)
        ok = not rb['fault'] and all(ra['registers'][k] == rb['registers'][k] for k in ks) and cb[2] == 0
        ok &= ma['pool'] == mb['pool'] and ma['stack'][rb['registers']['sp'] - PLV.STKR:] == mb['stack'][rb['registers']['sp'] - PLV.STKR:]
        if not ok:
            bad.append(('off', kw, rb['fault']))
    info.append('log off / other event == BASE')
    return not bad, '; '.join(info) + f'; bad {bad[:2]}'


# ---------------------------------------------------------------- F
def fw_run(m, site, field, boot=0, flag=0, kst=0):
    FV = PLV.FV
    im = bytearray(m)
    c = FV.asm(FV.SETTER_CAP, FV.FB.SETTER)
    im[FV.FB.SETTER - BASE:FV.FB.SETTER - BASE + len(c)] = c
    obj = bytearray(PLV.OBLK + 1004)
    w = (field + '\0').encode('utf-16le')
    for off in (940, 300):
        obj[PLV.OBLK + off:PLV.OBLK + off + len(w)] = w
    stack = bytearray(0x1100); struct.pack_into('<I', stack, 0x1000 + 4, PLV.OBJ + PLV.OBLK)
    bt = bytearray(16); bt[0xb] = boot
    bss = bytearray(8); bss[2] = flag
    rg = [Region('img', BASE, bytes(im), 'rx'), Region('obj', PLV.OBJ, bytes(obj), 'r'),
          Region('stack', FV.STACK, bytes(stack), 'rw', True), Region('cap', PLV.CAP, bytes(0x100), 'rw', True),
          Region('boot', BOOTR, bytes(bt), 'r'), Region('bss', BSSR, bytes(bss), 'r'),
          Region('kst', DG.KSTAGE & ~3, bytes([0, 0, kst, 0]), 'r'),
          Region('state', 0x622cbcc0, bytes(8), 'r')]               # no looks: BASE's pl_fw -> fw_val
    r = execute(rg, {'sp': FV.STACK + 0x1000, 'pc': site - 6, 'a0': 0x5a5a0026, 'a3': 0x44, 'd2': 0x22, 'd3': 0x33, 'a2': 0x55},
                site + 7, limit=200_000, timeout=120)
    mm = mem(r)
    regs = {k: r['registers'][k] for k in ('d2', 'd3', 'a2', 'a3', 'sp', 'pc')}
    return r['fault'], FV.wstr(mm['cap'][:0xfc]), struct.unpack_from('<I', mm['cap'], 0xfc)[0], regs, mm['stack'][0x1000:]


def t_f(base, new):
    cases = [(0, 0, 0, '0/00'), (2, 0x10, 0x15, '1/12'), (0x31 | 4, 0x31, 0x1a, '2/26'), (0xfe, 0x71, 0x12, '7/34'),
             (0x0d, 0x50, 0x09, '6/33'), (0x0a, 0x20, 0x11, '5/21'), (0xfe, 0x39, 0xf6, '7/45'), (0xfe, 0x79, 0x00, '7/30'),
             (0xfe, 0x73, 0xfa, '7/56')]
    bad = []
    for site in PL.FW_SITES:
        for bt, fl, ks, want in cases:
            f1, t1, w1, r1, k1 = fw_run(new, site, '1.1', bt, fl, ks)
            f0, t0, w0, r0, k0 = fw_run(base, site, '1.1', bt, fl, ks)
            if f1 or f0 or t1 != want or t0 != '0.32' or w1 != 0x5a5a0026 or r1 != r0 or k1 != k0:
                bad.append((hex(site), want, f1, t1))
        f1, t1, w1, r1, k1 = fw_run(new, site, '', 0xfe, 0x71, 0x1a)
        f0, t0, w0, r0, k0 = fw_run(base, site, '', 0xfe, 0x71, 0x1a)
        if f1 or t1 != t0 or r1 != r0 or k1 != k0:
            bad.append((hex(site), 'empty', f1, t1, t0))
    return not bad, f'{len(cases) * 2 + 2} runs: ' + ', '.join(w for *_, w in cases) + f'; empty == BASE; bad {bad[:2]}'


# ---------------------------------------------------------------- S, P
def t_s(base, new, base_s, new_s):
    import numpy as np
    ours = [(int(e['addr'], 16), len(e['new']) // 2) for e in new_s['edits']
            if e['kind'] == '0x100' and not e['addr'].startswith('off:') and (e.get('source') == DG.SRC or 'diag:' in e['why'])]
    ours += [(w, 4) for w in DG.WIN_W]
    diff = [BASE + int(i) for i in np.nonzero(np.frombuffer(base, np.uint8) != np.frombuffer(new, np.uint8))[0]]
    stray = [hex(a) for a in diff if not any(s <= a < s + n for s, n in ours)]
    rebuilt = img(DG.apply(base_s)) == new
    wins = all(new[w - BASE:w + 4 - BASE] == STOCK[w - BASE:w + 4 - BASE] for w in DG.WIN_W)
    return not stray and rebuilt and wins, f'{len(diff)} B differ, all in diag edits; window words stock; rebuilt == NEW; stray {stray[:4]}'


def t_p(new_s, new, disk, card):
    good, txt = PLV.t_p(new_s, new, disk, None)           # decode == stock + edits == image, restore == stock, disk
    if card:
        good &= SCB.build()[0] == card
        txt += ', PLUGIN.BIN == shortcut_cycle rebuild'
    return good, txt


def main():
    a = sys.argv[1:]
    base_s, new_s = (json.loads(Path(p).read_text()) for p in a[:2])
    disk = Path(a[2]) if len(a) > 2 and a[2] else None
    card = Path(a[3]).read_bytes() if len(a) > 3 else None
    base, new = img(base_s), img(new_s)
    ok = True
    for tag, fn in (('S', lambda: t_s(base, new, base_s, new_s)), ('L', lambda: t_l(base, new, base_s, new_s, card)),
                    ('O', lambda: t_o(base, new, new_s)), ('K', lambda: t_k(base, new)), ('H', lambda: t_h(base, new, new_s)),
                    ('F', lambda: t_f(base, new)),
                    ('P', lambda: t_p(new_s, new, disk, card))):
        g, txt = fn()
        print(f"{'PASS' if g else 'FAIL'} {tag} {txt}", flush=True)
        ok &= g
    print('ALL PASS' if ok else 'FAILURES')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
