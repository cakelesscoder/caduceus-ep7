#!/usr/bin/env python3
"""look_hw_ui checks (emulator: the real code of v0.34a and of the new build). Offline. Minimal + anti-brick.

  .venv/bin/python -I patches/look_hw_ui/verify.py <v0.34a spec> <new spec> [package dir]

Every run enters through the real edited word or site (facade vtable +8 / +24 / +28 / +36, the GUI setter call, the guide
part word) with heap P (card table + editor marker) and the real extras_pages / ap_custom code mapped; image slices are
read-only. Stand-ins: the settings getter 0x602af887 (S(id) = (id & 7) - 3), the facade object 0x607f9062 (picture mode
and cursor), and the guide chain (i18n_gd's address: writes "Colour: 1-8", kind 5, as xp_guide does for an empty sector).
  G  GetValue: Colour & Light sectors 9..11 -> the model (curve, mix -1..4, strength 0..10; 0 on Movie / AP); polygon <= 5;
     every other id, page, axis, card state reaches xp_get with v0.34a's registers, stack and MDR.
  L  count / value by index / available: our three lists; misses reach xp_cnt / xp_val / xp_av as in v0.34a.
  W  setter: heap == model (+53, +54..+59 = the scaled row, +60, dirty), strength 0 -> +54..+59 zero, -1 / the look's own
     strength write nothing; the state entering the stock manager == v0.34a's (its empty-sector redraw); ALL and Movie
     == v0.34a; misses reach xp_set as in v0.34a.
  V  guide label: English / Chinese text of each item and value, sector 12, the Movie lock; else == v0.34a.
  R  card round trip: the real SD loader check (sd_check) accepts every slot the UI can write (and the new image only:
     v0.34a rejects +60 != 0); +60 = 85 is rejected.
  P  anti-brick: package = stock + edits, restore == stock, every byte differing from v0.34a is inside this layer's edits.
"""
import json, struct, sys, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import importlib.util  # noqa: E402


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(s)
    sys.modules[name] = m; s.loader.exec_module(m); return m


EV = _load('ep7_verify_look_editor_lu', ROOT / 'tools/ep7_verify_look_editor.py')
LU = _load('ep7_lu_build_v', ROOT / 'patches/look_hw_ui/build.py')
Region, asm, run, img, mem = EV.Region, EV.asm, EV.run, EV.img, EV.mem
BASE, SENT, SP0, DRV, OUT, VOBJ, FACR = EV.BASE, EV.SENT, EV.SP0, EV.DRV, EV.OUT, EV.VOBJ, EV.FACR
H_OK, P_OK, AXIS, DIRTY = EV.H_OK, EV.P_OK, EV.AXIS, EV.DIRTY
SUB = LU.XP.SUB
POLY_RET = LU.XP.POLY_RET
GD_IN = 0x607d4210                         # i18n_gd: the chain the guide word held (stubbed)
SGET, MANAGER, FACADE = LU.SGET, LU.MANAGER, LU.FACADE
LANG = 0x18c00000
G = {}


def ids(k, n):
    return 927 + 12 * k + n if k < 3 else 1655 + n


def code_regions(im, poly=False):
    s1 = [img(im, 0x601de000, 0x601e3100, 's1a'), img(im, 0x601e3150, 0x601e4000, 's1b')] if poly else [img(im, 0x601de000, 0x601e4000, 's1')]
    return s1 + [img(im, 0x607c9400, 0x607c9c20, 'xp'), img(im, 0x607d9300, 0x607da1c0, 'lu'),
                 img(im, 0x60acb0d0, 0x60acb180, 'vt', 'r')]


def allf(on):
    return Region('allf', 0x61fc3800, struct.pack('<II', on, 0), 'r')


def block(axis=4, sub=1, slots=None, movie=False):
    b = EV.card_block(axis=axis)
    b[SUB] = sub
    for k, v in (slots or {}).items():
        b[32 + 64 * k + 53:32 + 64 * k + 61] = bytes(x & 0xff for x in v)
    if movie:
        b[960:964] = b'EP7V'
        b[964:968] = struct.pack('<I', P_OK)
    return b


def s8(x):
    return x - 256 if x >= 128 else x


W60 = lambda mix, s: 8 * (10 - s) + mix
ROW = LU.row
SLOTSETS = {                                # slot k -> bytes +53..+60
    'zero': {},
    'stored': {0: (3, *ROW(1, 6), W60(1, 6)), 1: (7, *ROW(3, 0), W60(3, 0)), 2: (1, 0, 0, 0, 0, 0, 0, W60(0, 4)), 3: (5, *ROW(4, 10), 0)},
    'panel': {0: (2, *ROW(2, 10), 0), 1: (0, *ROW(4, 7), 0), 2: (6, 32, -20, 5, 1, 0, 9, 0), 3: (9, *ROW(1, 3), 0xff)},
    'stale': {0: (4, 0, 0, 0, 0, 0, 0, W60(2, 3)), 1: (0, *ROW(2, 5), W60(1, 5)), 2: (0x80, 1, 2, 3, 4, 5, 6, W60(4, 2)), 3: (0, 0, 0, 0, 0, 0, 0, 0x55)},
}


def model_get(b, k, f):
    sl = b[32 + 64 * k:32 + 64 * k + 64]
    if f == 0:
        return sl[53] if sl[53] < 8 else 0
    mix, s = LU.decode(sl)
    return mix if f == 1 else s


def states():
    """(label, h, block, hit?, movie?)"""
    out = []
    for nm in SLOTSETS:
        out.append((nm, H_OK, block(slots=SLOTSETS[nm]), True, False))
    st = SLOTSETS['stored']
    out += [('movie', H_OK, block(slots=st, movie=True), True, True), ('sub 0', H_OK, block(sub=0, slots=st), False, False),
            ('sub 1 + cursor bits', H_OK, block(sub=0x31, slots=st), True, False),
            ('axis 1', H_OK, block(axis=1, slots=st), False, False), ('axis 3', H_OK, block(axis=3, slots=st), False, False),
            ('h 0', 0, None, False, False)]
    b = block(slots=st); b[0] ^= 1
    out.append(('no EP7B', H_OK, b, False, False))
    return out


def same(b, p, skip=()):
    for k in EV.REGS:
        if k not in skip and b['registers'][k] != p['registers'][k]:
            return f'{k} {p["registers"][k]:#x} != base {b["registers"][k]:#x}'
    if EV.live_stack(b) != EV.live_stack(p):
        return 'live stack'
    return None


def ok_run(r, stop):
    return not r['fault'] and r['registers']['pc'] == stop


# ------------------------------------------------------------------ G / L
def vt_case(off, idv, d1, st, poly=False):
    lab, h, blk, hit, movie = st
    if poly:
        src, entry = '', POLY_RET - 2
    else:
        src = (f' mov 0x60acb0dc,a3\n mov ({off},a3),a3\n mov 0x0a0a0a0a,a0\n mov {OUT:#x},a1\n mov {idv:#x},d0\n'
               f' mov {d1 & 0xffffffff:#x},d1\n mov a3,(0x{OUT + 64:x})\n mov {SENT["a3"]:#x},a3\n mov (0x{OUT + 64:x}),a2\n calls (a2)\n')
        entry = DRV
    code, sy = asm(src, DRV)
    done = POLY_RET if poly else sy['done']

    def regions(im):
        r = [Region('drv', DRV, code, 'rx'), Region('out', OUT, b'\x77' * 128, 'rw', True)] + code_regions(im, poly)
        if poly:
            r.append(Region('pc', POLY_RET - 2, b'\xf0\xf2' + b'\xcb' * 8, 'rx'))     # calls (a2); the polygon's return address
        return r + EV.state_regions(h, blk, 'r')
    regs = {'pc': entry}
    if poly:
        regs.update(a2=struct.unpack_from('<I', G['new'], 0x60acb0e4 - BASE)[0], a1=OUT, d0=idv)
    k_n = next(((k, n) for k in range(4) for n in range(12) if ids(k, n) == idv), None)
    ours = hit and k_n and 8 <= k_n[1] <= 10
    nxt = {8: 'xp_get', 24: 'xp_cnt', 28: 'xp_val', 36: 'xp_av'}[off]
    xpa = int(G['spec']['extras_pages']['symbols'][nxt], 16)
    tag = f'{nxt} {lab} id {idv} d1 {d1}'
    if not ours:
        b = run(regions(G['base']), regs, xpa)
        p = run(regions(G['new']), regs, xpa)
        if not ok_run(b, xpa) or not ok_run(p, xpa):
            return tag, f'did not reach {nxt}: base {b["fault"]} new {p["fault"]} pc {p["registers"]["pc"]:#x}'
        e = same(b, p, skip=('a2',))                   # a2 = the calls target (the word's value)
        return tag, (f'miss differs: {e}' if e else None)
    p = run(regions(G['new']), regs, done)
    if not ok_run(p, done):
        return tag, f'hit run {p["fault"]} pc {p["registers"]["pc"]:#x}'
    f = k_n[1] - 8
    pr, o = p['registers'], struct.unpack_from('<i', mem(p, 'out'), 0)[0]
    lo, n = LU.LIST_LO[f], LU.LIST_N[f]
    if off == 8:
        want = 0 if movie else model_get(blk, k_n[0], f)
        if poly:
            want = min(want, 5)
        good = o == want and pr['d0'] == 0 and mem(p, 'out')[4:64] == b'\x77' * 60
    elif off == 24:
        want, good = n, pr['d0'] == n
    elif off == 28:
        want = lo + (d1 & 0xffff)
        good = pr['d0'] & 0xffffffff == want & 0xffffffff and o == want
    else:
        want = int(lo <= d1 < lo + n)
        good = pr['d0'] == want
    if not poly:
        good &= pr['sp'] == SP0 and all(pr[x] == SENT[x] for x in ('d2', 'd3', 'a3'))
    return tag, None if good else f'out {o} d0 {pr["d0"]:#x}, want {want}, regs ' + ' '.join(f'{x}={pr[x]:#x}' for x in ('sp', 'd2', 'd3', 'a3', 'mdr'))


def t_g():
    fails, n = [], 0
    sts = states()
    idl = [ids(k, c) for k in range(4) for c in (8, 9, 10)] + [ids(0, 11), ids(3, 11), ids(1, 0), ids(2, 7), 926, 111, 1091, 1667]
    for st in sts:
        for idv in idl:
            n += 1
            t, e = vt_case(8, idv, 0, st)
            if e:
                fails.append((t, e))
    for idv in (ids(1, 10), ids(2, 8)):                      # the polygon
        for st in sts[:2]:
            n += 1
            t, e = vt_case(8, idv, 0, st, poly=True)
            if e:
                fails.append(('poly ' + t, e))
    return not fails, f'{n} cases' + (f'; {fails[:4]}' if fails else '')


def t_l():
    fails, n = [], 0
    sts = [s for s in states() if s[0] in ('zero', 'stored', 'sub 0', 'axis 1', 'movie')]
    idl = [ids(0, 8), ids(1, 9), ids(3, 10), ids(2, 11), ids(0, 4), 111]
    for st in sts:
        for idv in idl:
            for off, d1s in ((24, (0,)), (28, (0, 5, 10)), (36, (-2, -1, 0, 7, 8, 10, 11))):
                for d1 in d1s:
                    n += 1
                    t, e = vt_case(off, idv, d1, st)
                    if e:
                        fails.append((t, e))
    return not fails, f'{n} cases' + (f'; {fails[:4]}' if fails else '')


# ------------------------------------------------------------------ W
def model_set(b, k, f, v):
    e = bytearray(b)
    o = 32 + 64 * k
    sl = bytes(e[o:o + 64])
    if f == 0:
        e[o + 53] = max(0, min(7, v))
    else:
        mix, s = LU.decode(sl)
        if f == 1:
            if v < 0:
                return e
            mix = min(v, 4)
        else:
            if mix < 0:
                return e
            s = max(0, min(10, v))
        e[o + 54:o + 60] = bytes(x & 0xff for x in ROW(mix, s))
        e[o + 60] = W60(mix, s)
    e[DIRTY] = 1
    return e


def set_case(idv, val, st, all_on=0):
    lab, h, blk, hit, movie = st
    gcode, _ = asm(EV.STUB_SGET, SGET)
    src = f' mov {idv:#x},d0\n mov {val & 0xffffffff:#x},d1\n mov 0x0a0a0a0a,a0\n mov 0x1a1a1a1a,a1\n jmp site\n'
    code = asm(src, DRV, dict(site=LU.SET_SITE))[0]

    def regions(im):
        return [Region('drv', DRV, code, 'rx'), img(im, LU.SET_SITE, LU.SET_SITE + 7, 'site'), img(im, MANAGER, MANAGER + 16, 'mgr'),
                Region('sget', SGET, gcode, 'rx'), allf(all_on)] + code_regions(im) + EV.state_regions(h, blk)
    k_n = next(((k, n) for k in range(4) for n in range(12) if ids(k, n) == idv), None)
    ours = hit and k_n and 8 <= k_n[1] <= 10
    tag = f'set {lab} id {idv} v {val} all {all_on}'
    xps = int(G['spec']['extras_pages']['symbols']['xp_set'], 16)
    stop = MANAGER if ours else xps
    b = run(regions(G['base']), {'pc': DRV}, stop)
    p = run(regions(G['new']), {'pc': DRV}, stop)
    if not ok_run(b, stop) or not ok_run(p, stop):
        return tag, f'no stop {stop:#x}: base {b["fault"]} new {p["fault"]} pc {p["registers"]["pc"]:#x}'
    e = same(b, p, skip=('d2', 'd3', 'a2'))           # saved by the site's call: dead at xp_set / the manager
    if e:
        return tag, f'state differs: {e}'
    if not ours or blk is None:
        return tag, None
    want = bytes(blk) if (all_on or movie) else bytes(model_set(blk, k_n[0], k_n[1] - 8, val))
    if mem(b, 'heap') != bytes(blk):
        return tag, 'v0.34a changed the heap'
    hp = mem(p, 'heap')
    if hp != want:
        return tag, f'heap differs at {[i for i in range(len(hp)) if hp[i] != want[i]][:6]}'
    if k_n[1] == 10 and val == 0 and not (all_on or movie) and LU.decode(blk[32 + 64 * k_n[0]:][:64])[0] >= 0 \
            and hp[32 + 64 * k_n[0] + 54:32 + 64 * k_n[0] + 60] != bytes(6):
        return tag, 'strength 0 left matrix bytes'
    return tag, None


def t_w():
    fails, n = [], 0
    vals = {8: (-1, 0, 1, 5, 7, 8, 200), 9: (-2, -1, 0, 1, 2, 3, 4, 5), 10: (-1, 0, 3, 6, 10, 11)}
    sts = [s for s in states() if s[0] in SLOTSETS]
    for st in sts:
        for k in range(4):
            for c, vs in vals.items():
                for v in vs:
                    n += 1
                    t, e = set_case(ids(k, c), v, st)
                    if e:
                        fails.append((t, e))
    other = [s for s in states() if s[0] not in SLOTSETS and s[1]]
    for st in other:
        for idv in (ids(0, 8), ids(1, 9), ids(3, 10), ids(2, 11), ids(0, 3)):
            n += 1
            t, e = set_case(idv, 2, st)
            if e:
                fails.append((t, e))
    st = states()[1]
    for idv in (ids(0, 8), ids(2, 9), ids(3, 10)):
        n += 1
        t, e = set_case(idv, 1, st, all_on=1)
        if e:
            fails.append((t, e))
    for idv in (111, 926, ids(1, 4)):
        n += 1
        t, e = set_case(idv, 1, st)
        if e:
            fails.append((t, e))
    return not fails, f'{n} cases' + (f'; {fails[:4]}' if fails else '')


# ------------------------------------------------------------------ V
GD_STUB = f"""
st_gd:
 mov (0x{GD_IN + 0x200:x}),d0
 movhu d0,(44,a0)
 add 52,a0
 mov 0x{GD_IN + 0x210:x},a1
1:
 movhu (a1),d0
 movhu d0,(a0)
 add 2,a0
 add 2,a1
 cmp 0,d0
 bne 1b
 mov 0x5a5a,d0
 rets
"""
FAC = f"""
s_fac:
 mov {FACR:#x},a0
 ret [],4
s_get:
 cmp 111,d0
 bne 1f
 mov ({FACR + 0x80:#x}),d1
 bra 2f
1:
 mov ({FACR + 0x84:#x}),d1
2:
 mov d1,(a1)
 clr d0
 mov 0xbad0a0a0,a0
 rets
"""


def guide_regions(pm, cursor, kind, zh):
    gcode, _ = asm(GD_STUB, GD_IN)
    gd = bytearray(0x300)
    gd[:len(gcode)] = gcode
    struct.pack_into('<I', gd, 0x200, kind)
    t = 'Colour: 1-8'.encode('utf-16-le') + b'\0\0'
    gd[0x210:0x210 + len(t)] = t
    fcode, fsy = asm(FAC, 0x18980000)
    fac = bytearray(0x100)
    struct.pack_into('<I', fac, 0, FACR + 0x40)
    struct.pack_into('<I', fac, 0x48, fsy['s_get'])
    struct.pack_into('<II', fac, 0x80, pm, cursor)
    lang = bytearray(0x1100)
    struct.pack_into('<I', lang, 536, LANG + 0x1000)
    lang[0x1000:0x1006] = ('固件' if zh else 'Fi').encode('utf-16-le')[:4] + b'\0\0'
    return [Region('gd', GD_IN, bytes(gd), 'rx'), Region('facstub', 0x18980000, fcode, 'rx'), Region('fac', FACR, bytes(fac), 'r'),
            Region('t_fac', FACADE, b'\xdc' + struct.pack('<i', fsy['s_fac'] - FACADE), 'rx'),
            Region('lang', LANG, bytes(lang), 'r'), Region('bank', 0x61fb2818, b'\0\0\0\0', 'r'),
            Region('stab', 0x61fc1530, struct.pack('<I', LANG), 'r'), Region('sect', 0xa272e420, struct.pack('<I', 0x1ff), 'r')]


def model_text(blk, k, cursor, zh, movie):
    L = {i: v[1 if zh else 0] for i, v in LU.LABELS.items()}
    f = cursor - 9
    if f == 3:
        return L[3]
    if movie:
        return L[4] if f == 0 else L[5]
    sl = blk[32 + 64 * k:32 + 64 * k + 64]
    if f == 0:
        return L[0] + L[6 + (sl[53] if sl[53] < 8 else 0)]
    mix, s = LU.decode(sl)
    return L[1] + L[15 + mix] if f == 1 else L[2] + L[20 + s]


def guide_case(st, pm, cursor, zh, kind=5, all_on=0):
    lab, h, blk, hit, movie = st
    code, sy = asm(f' mov {VOBJ:#x},a0\n mov 0x6025aa98,a2\n mov (a2),a2\n mov {SENT["a3"]:#x},a3\n'
                   f' calls (a2)\n', DRV)

    def regions(im):
        return ([Region('drv', DRV, code, 'rx'), Region('view', VOBJ, bytes(0x100), 'rw', True), img(im, 0x6025aa90, 0x6025aaa0, 'gw', 'r'),
                 allf(all_on)] + guide_regions(pm, cursor, kind, zh) + code_regions(im) + EV.state_regions(h, blk, 'r'))
    tag = f'guide {lab} pm {pm} cursor {cursor} zh {zh} kind {kind} all {all_on}'
    b = run(regions(G['base']), {'pc': DRV}, sy['done'])
    p = run(regions(G['new']), {'pc': DRV}, sy['done'])
    if not ok_run(b, sy['done']) or not ok_run(p, sy['done']):
        return tag, f'no stop: base {b["fault"]} new {p["fault"]} pc {p["registers"]["pc"]:#x}'
    e = same(b, p, skip=('a0', 'a1', 'd1', 'a2', 'mdr'))   # scratch, the calls target, the link register
    if e or p['registers']['d0'] != 0x5a5a:
        return tag, f'registers: {e} d0 {p["registers"]["d0"]:#x}'
    k = {54: 0, 55: 1, 56: 2, 64: 3}.get(pm)
    ours = hit and k is not None and 9 <= cursor <= 12 and kind == 5 and not all_on
    vb, vp = mem(b, 'view'), mem(p, 'view')
    if not ours:
        return tag, None if vb == vp else 'label differs from v0.34a'
    want = model_text(blk, k, cursor, zh, movie)
    got = vp[52:52 + 66].decode('utf-16-le').split('\0')[0]
    if struct.unpack_from('<H', vp, 44)[0] != 5 or got != want or vp[52 + 2 * len(want):52 + 66] != bytes(66 - 2 * len(want)) \
            or vp[:44] != vb[:44] or vp[46:52] != vb[46:52] or vp[118:] != vb[118:]:
        return tag, f'label {got!r}, want {want!r}'
    return tag, None


def t_v():
    fails, n = [], 0
    for st in states():
        for pm in (54, 55, 56, 64, 57):
            for cursor in (1, 8, 9, 10, 11, 12):
                for zh in (0, 1):
                    if st[0] not in SLOTSETS and (zh or pm in (55, 56)):
                        continue
                    n += 1
                    t, e = guide_case(st, pm, cursor, zh)
                    if e:
                        fails.append((t, e))
    st = states()[1]
    for kw in (dict(kind=4), dict(all_on=1)):
        for cursor in (9, 11):
            n += 1
            t, e = guide_case(st, 54, cursor, 0, **kw)
            if e:
                fails.append((t, e))
    return not fails, f'{n} cases' + (f'; {fails[:4]}' if fails else '')


# ------------------------------------------------------------------ R
def sd_case(im, data):
    at = int(G['spec']['sd_bundles_v3']['symbols']['sd_check'], 16)
    code, sy = asm(f' mov {OUT:#x},a0\n call chk,[d2,d3,a2,a3],16\n', DRV, dict(chk=at))
    r = run([Region('drv', DRV, code, 'rx'), Region('out', OUT, bytes(data), 'r'), img(im, 0x605b7400, 0x605b7800, 's3')],
            {'pc': DRV}, sy['done'])
    return r['registers']['d0'] if ok_run(r, sy['done']) else f'fault {r["fault"]}'


def card(slots):
    d = bytearray(EV.card_block(axis=4)[:544])
    for k, v in slots.items():
        d[32 + 64 * k + 53:32 + 64 * k + 61] = bytes(x & 0xff for x in v)
    struct.pack_into('<I', d, 16, zlib.crc32(bytes(d[:16] + d[20:544])) & 0xffffffff)
    return d


def t_r():
    bad = []
    n = 0
    files = [card({k: (c, *ROW(mix, s), W60(mix, s)) for k in range(4)}) for c in range(8) for mix in range(5) for s in (0, 1, 5, 10)]
    for d in files:
        n += 1
        if sd_case(G['new'], d) != 0:
            bad.append(('new rejects', d[32 + 53:32 + 61].hex()))
    for d in (files[1], files[-1]):
        if d[32 + 60] and sd_case(G['base'], d) != 1:
            bad.append(('v0.34a accepts +60', d[32 + 53:32 + 61].hex()))
    for v in (85, 127, 128, 0xff):
        n += 1
        if sd_case(G['new'], card({1: (0, 0, 0, 0, 0, 0, 0, v)})) != 1:
            bad.append(('new accepts +60', v))
    n += 1
    if sd_case(G['new'], card({})) != 0:
        bad.append('plain file')
    return not bad, f'{n} files' + (f'; {bad[:4]}' if bad else '')


# ------------------------------------------------------------------ P
def t_p(base_s, new_s, disk):
    import build_package as BP
    sys.path.insert(0, str(ROOT / 'external/oly_fw_analysis/tools'))
    import oly_container as oc
    stock_pkg = BP.STOCK.read_bytes()
    pkg, rst, _ = BP.build(new_s, stock_pkg)
    bpkg, _, _ = BP.build(base_s, stock_pkg)
    sb = {b.kind: b for b in oc.parse(stock_pkg)}
    good = True
    for b in oc.parse(pkg):
        exp = bytearray(sb[b.kind].payload)
        for e in new_s['edits']:
            if int(e['kind'], 16) == b.kind:
                o = BP.resolve(b.kind, e['addr']); nb = bytes.fromhex(e['new']); exp[o:o + len(nb)] = nb
        good &= bytes(exp) == b.payload
    good &= all(b.payload == sb[b.kind].payload for b in oc.parse(rst))
    bp = {b.kind: b.payload for b in oc.parse(bpkg)}
    good &= all(b.payload == bp[b.kind] for b in oc.parse(pkg) if b.kind != 0x100)
    ours = [(int(e['addr'], 16), len(e['new']) // 2) for e in new_s['edits']
            if e['kind'] == '0x100' and not e['addr'].startswith('off:') and (e.get('source') == LU.SRC or '[look_hw_ui' in e['why'])]
    ours += [(int(e['addr'], 16), len(e['new']) // 2) for e in new_s['edits'] if e.get('source') == 'patches/fw_version']
    CF = _load('ep7_crash_fmt_lu', ROOT / 'tools/ep7_crash.py')    # crash_log's build tag word follows the version string
    tb, tn = (struct.pack('<I', CF.build_tag(x['fw_version']['mod_version'])) for x in (base_s, new_s))
    bm, nm = G['base'], G['new']
    tags = [BASE + i for i in range(len(nm) - 3) if nm[i:i + 4] == tn and bm[i:i + 4] == tb]
    ours += [(a, 4) for a in tags]
    diffs = [BASE + i for i in range(len(bm)) if bm[i] != nm[i]]
    stray = [hex(a) for a in diffs if not any(s <= a < s + k for s, k in ours)]
    good &= not stray
    if disk:
        good &= (disk / 'patched.pkg.bin').read_bytes() == pkg and (disk / 'restore-stock.pkg.bin').read_bytes() == rst
    return good, f'{len(new_s["edits"])} edits; build tag words {[hex(a) for a in tags]}; main {len(diffs)} B differ from v0.34a, stray {stray[:6]}; other components == v0.34a; restore == stock'


def main():
    base_s, new_s = (json.loads(Path(p).read_text()) for p in sys.argv[1:3])
    disk = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    G['base'] = EV.images(base_s)[1]
    G['new'] = EV.images(new_s)[1]
    G['spec'] = new_s
    ok = True
    for tag, f in (('G', t_g), ('L', t_l), ('W', t_w), ('V', t_v), ('R', t_r), ('P', lambda: t_p(base_s, new_s, disk))):
        g, txt = f()
        print(f"{'PASS' if g else 'FAIL'} {tag} {txt}", flush=True)
        ok &= g
    print('ALL PASS' if ok else 'FAILURES')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
