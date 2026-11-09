#!/usr/bin/env python3
"""AP Custom checks (emulator only, offline): each new hook works on the AP slot and is v0.29a without it, plus anti-brick.
  .venv/bin/python -I patches/ap_custom/verify.py generated/v029a/edits.json generated/ap_custom/edits.json
G capture-population reads (real sites, real getter). X tbl_idx / tbl_off. B a WB read end to end (mv_wb -> wb_get -> wb_prop -> tbl_off).
K live view job key (real mapper). L the real Live Control INFO handler. C Color Creator guard. F AP.BIN load / save / triggers. N label builders.
D image differs from v0.29a only at our sites. A package anti-brick.
"""
import hashlib, importlib.util, json, struct, sys, zlib
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


V = _load('ep7_v026_movie_verify', ROOT / 'patches/v026_movie/verify.py')
A = _load('ep7_ap_custom_build', ROOT / 'patches/ap_custom/build.py')
Bd, W, Region, execute, img, stub, caller = V.Bd, V.W, V.Region, V.execute, V.img, V.stub, V.caller
BASE, HANDLE, POOL = 0x60020020, V.HANDLE, V.POOL
P_AT, P2_AT = V.P_AT, V.P2_AT
P3_AT = P_AT + 0x1000
H3 = HANDLE + 0x1000
STK = V.STK
SLOT = bytearray(64)
SLOT[:24] = bytes((i * 3) % 8 for i in range(24)); SLOT[24] = 2; SLOT[25:28] = bytes([1, 4, 0xfd]); SLOT[33:45] = bytes(x & 255 for x in (-5, 5, -4, 4, -3, 3, -2, 2, -1, 1, 0, 3)); SLOT[49:52] = bytes([1, 2, 1])
SLOT = bytes(SLOT)
PEND = False
ARMED = False
ARMED = False
PROBE = None
EFF = struct.pack('<12h', *range(0x10, 0x1c))


def heap(kind, swapped=False, p2=False, rw=False, table=None):
    """kind: none (state 0), p (BUNDLES only), ap (P + published P3). -> regions"""
    if kind == 'none':
        return [Region('state', 0x622cbcc0, bytes(8), 'r')]
    t = bytes(table or bytes(512))
    p = bytearray(V.block(t, HANDLE, p2))
    rg = []
    if kind == 'ap':
        p[A.AM:A.AM + 4] = b'EP7A'; struct.pack_into('<I', p, A.AP3, P3_AT)
        q = bytearray(V.block(t, HANDLE, True)); q[224:288] = SLOT; q[592:597] = b'APslt'
        struct.pack_into('<3I', q, Bd.VM, Bd.VMAGIC, P3_AT, HANDLE)
        if PEND:
            q[A.PEND] = 1
        if ARMED:
            q[A.ARM] = 1
        rg.append(Region('pool3', P3_AT, bytes(q), 'rw' if rw else 'r', rw))
    if p2:
        q2 = bytearray(V.block(t, HANDLE, True)); q2[224:288] = bytes(64)
        rg.append(Region('pool2', P2_AT, bytes(q2), 'r'))
    return [Region('state', 0x622cbcc0, struct.pack('<HHI', 0, H3 if swapped else HANDLE, 0), 'rw' if rw else 'r', rw), Region('pool', P_AT, bytes(p), 'rw' if rw else 'r', rw)] + rg


def props(s44, s24, pm, extra=None):
    d = {0x8551: bytes([s44]), 0xc011: bytes([s24]), 0x9481: bytes([pm]), 0xf6b1: bytes([0]), 0xf6ea: EFF}
    d.update(extra or {})
    return d


def getter(m, pr):
    return V.getter(m, pr)


def apc(m):
    return img(m, A.AT, A.END, 'ap')


CASES = [(k, s44, s24, pm) for k in ('none', 'p', 'ap') for s44 in (0, 1) for s24 in (211, 209, 14, 216, 3, 217, 208) for pm in (1, 3)]


def on(k, s44, s24, pm):
    return k == 'ap' and s44 == 0 and (s24 == 14 or 209 <= s24 <= 216) and pm == 1


def t_cap(new, base):
    bad, n = [], 0
    for i, s in enumerate(A.CAP_SITES):
        if i not in (0, 1, 2, 7, 13):
            continue
        key, idx = {0: (38017, 0), 1: (63153, 0)}.get(i, (63210, i - 2))
        for k, s44, s24, pm in CASES:
            res = []
            for m in (base, new):
                rg = [img(m, s - 16, s + 16, 'site'), apc(m), *getter(m, props(s44, s24, pm)), *heap(k), Region('stack', W.STACK, bytes([W.STACK_FILL] * 0x2000), 'rw')]
                r = execute(rg, dict(pc=s, sp=W.SP0, d0=key, d1=idx, a0=0, d2=0x1111, d3=0x2222, a2=0x3333, a3=0x4444), s + 7, limit=20000)
                res.append((r['fault'], r['registers']))
            n += 1
            hit = on(k, s44, s24, pm)
            want = ({0: 11, 1: 4}.get(i, (SLOT[33 + idx] ^ 0x80) - 0x80)) if hit else res[0][1]['d0']
            rr = res[1][1]
            if res[1][0] or res[0][0] or rr['d0'] & 0xffffffff != want & 0xffffffff or any(rr[x] != res[0][1][x] for x in ('d1', 'd2', 'd3', 'a2', 'a3', 'sp')):
                bad.append((hex(s), k, s44, s24, pm, res[1][0], hex(rr['d0']), hex(want & 0xffffffff)))
    return n, bad


def t_tbl(new, base):
    bad, n = [], 0
    for entry, d0, off in ((0x6055e7b0, 3, 192), (0x6055e7b6, 192 + 25, 192 + 25), (0x6055e7b0, 2, 128), (0x6055e7b6, 255, 255), (0x6055e7b6, 256, 256)):
        for k, s44, s24, pm in CASES[::3]:
            res = []
            for m in (base, new):
                rg = [img(m, 0x6055e700, 0x6055e800, 'sec2'), apc(m), *getter(m, props(s44, s24, pm)), *heap(k), Region('stack', 0x18010000, bytes(0x1000), 'rw'), caller(entry, '[d2,d3],8')]
                r = execute(rg, dict(pc=0x18040000, sp=STK, d0=d0, d1=0x77, a1=0x88, d2=0x1111, d3=0x2222, a2=0x3333, a3=0x4444), 0x18040007, limit=20000)
                res.append((r['fault'], r['registers']))
            n += 1
            hit = on(k, s44, s24, pm) and 192 <= off < 256
            rr = res[1][1]
            want = P3_AT + 32 + off if hit else res[0][1]['a0']
            if res[1][0] or rr['a0'] != want or any(rr[x] != res[0][1][x] for x in ('d0', 'd1', 'a1', 'd2', 'd3', 'a2', 'a3', 'sp')):
                bad.append((hex(entry), d0, k, s44, s24, pm, res[1][0], hex(rr['a0']), hex(want)))
    return n, bad


def t_wb(new, base):
    """Record-path compact WB read 0x6030bb5b in AP live view: mv_wb misses (not movie), wb_get -> wb_prop (ap_get) -> tbl_off -> ap_tx."""
    bad, n = [], 0
    s, key = 0x6030bb5b, 0x84f9
    for k, s44, s24, pm in CASES[::2]:
        res = []
        for m in (base, new):
            rec = bytearray(980); rec[294] = 1
            pr = props(s44, s24, pm, {key: bytes([2, 2]), 0x9d11: bytes([0]), 33057 & 0xffff: bytes([1]), 0xf731: bytes([0])})
            rg = [img(m, s - 16, s + 16, 'site'), *V.code(m), apc(m), *getter(m, pr), Region('rec', V.REC, bytes(rec), 'r'), Region('stack', W.STACK, bytes([W.STACK_FILL] * 0x2000), 'rw'), *heap(k)]
            r = execute(rg, dict(pc=s, sp=W.SP0, d0=key, d1=0, a0=0, a2=V.REC + 698, a3=0x3333, d2=0x1111, d3=0x2222), s + 7, limit=40000)
            res.append((r['fault'], r['registers']))
        n += 1
        rr = res[1][1]
        want = 4 if on(k, s44, s24, pm) else res[0][1]['d0']
        if res[1][0] or rr['d0'] != want or any(rr[x] != res[0][1][x] for x in ('d2', 'd3', 'a2', 'a3', 'sp')):
            bad.append((k, s44, s24, pm, res[1][0], hex(rr['d0']), hex(res[0][1]['d0'])))
    return n, bad


def t_key(new, base):
    bad, n = [], 0
    for k, s44, s24, pm in CASES[::2]:
        for rpm in (1, 3):
            res = []
            for m in (base, new):
                rec = bytearray(980); rec[294] = rpm
                stack = bytearray(0x1000); struct.pack_into('<I', stack, 0x804, V.OUT)
                call = Region('call', V.FS, b'\xdd' + struct.pack('<i', 0x60316bc7 - V.FS) + b'\xb0\x18', 'rx')
                rg = [call, img(m, 0x60316bc7, 0x60316c4d, 'f1'), img(m, 0x60324d6b, 0x60324dc1, 'f2'), img(m, 0x60349297, 0x603494d7, 'map'),
                      img(m, 0x604f8a78 - 0x1000, 0x604f8a78, 'tbl', 'r'), img(m, 0x601e25ec, 0x601e283c, 'mv'), Region('ms', 0x4700115e, bytes.fromhex('dea008'), 'rx'), apc(m), *getter(m, props(s44, s24, pm)),
                      Region('stack', 0x18010000, bytes(stack), 'rw'), Region('rec', V.REC, bytes(rec), 'rw', True), Region('out', V.OUT, bytes(8), 'rw', True), *heap(k)]
                r = execute(rg, dict(pc=V.FS, sp=0x18010800, a0=V.REC + 292, a1=V.REC, d0=0, d1=0), V.FS + 7, limit=40000)
                mem = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}
                res.append((r['fault'], mem['out'], mem['rec'], {x: r['registers'][x] for x in ('sp', 'd3', 'a2')}))
            n += 1
            hit = on(k, s44, s24, pm) and rpm == 1
            want = bytes.fromhex('00000b00') + res[0][1][4:] if hit else res[0][1]
            if res[1][0] or res[1][1] != want or res[1][2] != res[0][2] or res[1][3] != res[0][3]:
                bad.append((k, s44, s24, pm, rpm, res[1][0], res[1][1].hex(), res[0][1].hex()))
    return n, bad


def t_lv(new, base, spec):
    """Live view record path: message +20 (ap_msg -> sh_msg -> mv_msg), effective S (ap_s -> mv_s), lv / tone slot read with mv_prof's mark (ap_tb -> mv_tbl)."""
    bad, n = [], 0
    sh = img(new, 0x601de13c, 0x601de280, 'sh'), img(base, 0x601de13c, 0x601de280, 'sh')
    for k, s44, s24, pm in CASES[::2]:
        for rpm in (1, 3):
            res = []
            for j, m in enumerate((base, new)):
                rec = bytearray(980); rec[294] = rpm; rec[944] = 3
                rg = [img(m, 0x60315900, 0x60315918, 'site'), img(m, 0x601e25ec, 0x601e283c, 'mv'), sh[1 - j], apc(m), *getter(m, props(s44, s24, pm)), Region('rec', V.REC, bytes(rec), 'r'), Region('msg', V.MSG, bytes(64), 'rw', True),
                      Region('stack', W.STACK, bytes([W.STACK_FILL] * 0x2000), 'rw'), *heap(k, p2=True)]
                r = execute(rg, dict(pc=0x60315900, sp=W.SP0, a0=V.REC + 941, a1=V.MSG, d3=V.REC + 941, d1=0, d2=0, a2=0x2222, a3=0x3333), 0x60315908, limit=20000)
                res.append((r['fault'], bytes.fromhex(r['memory'][0]['hex'])[16:24], {x: r['registers'][x] for x in ('a1', 'a2', 'a3', 'd1', 'd2', 'd3', 'sp')}))
            n += 1
            hit = on(k, s44, s24, pm) and rpm == 1
            want = res[0][1][:4] + bytes([4]) + res[0][1][5:] if hit else res[0][1]
            if res[1][0] or res[1][1] != want or res[1][2] != res[0][2]:
                bad.append(('msg', k, s44, s24, pm, rpm, res[1][0], res[1][1].hex(), res[0][1].hex()))
            for i in (0, 7, 11):
                res = []
                for m in (base, new):
                    rec = bytearray(980); rec[294] = rpm
                    s_ = Bd.S_SITE
                    rg = [img(m, s_ - 16, s_ + 16, 'site'), img(m, 0x601e25ec, 0x601e283c, 'mv'), img(m, Bd.W_AT, Bd.W_END, 'mvw'), apc(m), *getter(m, props(s44, s24, pm)), Region('rec', V.REC, bytes(rec), 'r'),
                          Region('stack', W.STACK, bytes([W.STACK_FILL] * 0x2000), 'rw'), *heap(k, p2=True)]
                    r = execute(rg, dict(pc=s_, sp=W.SP0, d0=0xf6ea, d1=i, a0=0, a2=0x2222, a3=V.REC + 704, d2=0x1111, d3=0x3333), s_ + 7, limit=20000)
                    res.append((r['fault'], r['registers']))
                n += 1
                rr = res[1][1]
                want = ((SLOT[33 + i] ^ 0x80) - 0x80) & 0xffffffff if hit else res[0][1]['d0']
                if res[1][0] or rr['d0'] != want or any(rr[x] != res[0][1][x] for x in ('d2', 'd3', 'a2', 'a3', 'sp')):
                    bad.append(('s', k, s44, s24, pm, rpm, i, res[1][0], hex(rr['d0']), hex(want)))
        for d1 in (Bd.PMARK, 0):
            res = []
            for m in (base, new):
                t = A.tgt(m, Bd.TBL_SITES[0])
                rg = [img(m, 0x6055e700, 0x6055e800, 'sec2'), img(m, Bd.W_AT, Bd.W_END, 'mvw'), apc(m), *getter(m, props(s44, s24, pm)), *heap(k, p2=True), Region('stack', 0x18010000, bytes(0x1000), 'rw'), caller(t, '[d2,d3],8')]
                r = execute(rg, dict(pc=0x18040000, sp=STK, d0=3, d1=d1, a1=0x88, d2=0x1111, d3=0x2222, a2=0x3333, a3=0x4444), 0x18040007, limit=20000)
                res.append((r['fault'], r['registers']))
            n += 1
            rr = res[1][1]
            want = P3_AT + 224 if on(k, s44, s24, pm) else res[0][1]['a0']
            if res[1][0] or rr['a0'] != want or any(rr[x] != res[0][1][x] for x in ('d0', 'd1', 'a1', 'd2', 'd3', 'a2', 'a3', 'sp')):
                bad.append(('tbl', k, s44, s24, pm, hex(d1), res[1][0], hex(rr['a0']), hex(want)))
    return n, bad


def t_scr(new, base):
    """Screen lookup entries: group 0x12 key 0x77 in AP + Vivid -> swap to P3 (pending), key 0x140c at the resume; otherwise as v0.29a."""
    global PEND
    bad, n = [], 0
    for entry, res in ((A.SCR, A.SCR_RES), (A.SCR2, A.SCR2_RES)):
        for grp, key, gui, armed in ((0x12, 0x77, 0, False), (0x12, 0x77, 1, False), (0x12, 0x6f, 0, False), (0x12, 0x6f, 0, True), (0x12, 0x13b3, 0, True), (0x14, 0x77, 0, False)):
            for k, s44, s24, pm in CASES[::4]:
                out = []
                for m in (base, new):
                    global ARMED
                    ARMED = armed
                    try:
                        hp = heap(k, rw=True)
                    finally:
                        ARMED = False
                    rg = [img(m, entry - 8, entry + 16, 'site'), apc(m), *getter(m, props(s44, s24, pm)), V.sget(s44, gui), *hp, Region('stack', 0x18010000, bytes(0x1000), 'rw', True)]
                    r = execute(rg, dict(pc=entry, sp=STK, d0=grp, d1=key, a0=0x5555, a1=0x6666, d2=0x1111, d3=0x2222, a2=0x3333, a3=0x4444), res, limit=20000)
                    mem = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}
                    out.append((r['fault'], r['registers'], mem))
                n += 1
                hit = grp == 0x12 and on(k, s44, s24, pm) and ((key == 0x77 and gui == 0) or (key == 0x6f and armed))
                rn, rb = out[1][1], out[0][1]
                st_ = struct.unpack_from('<H', out[1][2]['state'], 2)[0] if 'state' in out[1][2] else None
                ok = not out[1][0] and not out[0][0] and all(rn[x] == rb[x] for x in ('d0', 'd2', 'd3', 'a0', 'a1', 'a2', 'a3', 'sp', 'mdr') if x in rn)
                stk_n, stk_b = out[1][2]['stack'], out[0][2]['stack']
                kn = struct.unpack_from('<H', stk_n, STK - 0x18010000 + 32)[0]; kb = struct.unpack_from('<H', stk_b, STK - 0x18010000 + 32)[0]
                if hit:
                    ok = ok and (kn == 0x140c if entry == A.SCR else rn['d1'] == 0x140c) and st_ == H3 and out[1][2]['pool3'][A.PEND] == 1
                else:
                    ok = ok and rn['d1'] == rb['d1'] and kn == kb and st_ in (None, HANDLE, 0)
                if not ok:
                    bad.append((hex(entry), hex(grp), hex(key), k, s44, s24, pm, out[1][0], hex(rn['d1']), st_))
    return n, bad


def t_init(new):
    """COLOR record +4: a P3 swap without pending is undone, pending is consumed; registers as on entry, then po_init."""
    global PEND
    bad, n = [], 0
    po = A.tgt  # placeholder use
    spec = json.loads(Path(sys.argv[2]).read_text())
    s = int(spec['ap_custom']['symbols']['ap_init'], 16)
    po_init = int(spec['page_order']['po_init'][0], 16)
    for swapped, pend, want in ((True, False, HANDLE), (True, True, H3), (False, False, HANDLE)):
        PEND = pend
        try:
            hp = heap('ap', swapped=swapped, rw=True)
        finally:
            PEND = False
        rg = [apc(new), *hp, Region('stack', 0x18010000, bytes(0x1000), 'rw'), Region('po', po_init, b'\xcb', 'rx')]
        r = execute(rg, dict(pc=s, sp=STK, d0=1, d1=2, a0=3, a1=4, d2=5, d3=6, a2=7, a3=8), po_init, limit=5000); n += 1
        mem = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}
        rr = r['registers']
        if r['fault'] or struct.unpack_from('<H', mem['state'], 2)[0] != want or mem['pool3'][A.PEND] != 0 or (rr['d0'], rr['d1'], rr['a0'], rr['a1'], rr['d2'], rr['d3'], rr['a2'], rr['a3'], rr['sp']) != (1, 2, 3, 4, 5, 6, 7, 8, STK):
            bad.append((swapped, pend, r['fault'], struct.unpack_from('<H', mem['state'], 2)[0]))
    # swapped to P3, dial off AP: the pipeline reads P's table
    for s24, off, want in ((3, 64, P_AT + 32 + 64), (3, 192, P_AT + 32 + 192), (211, 192, P3_AT + 32 + 192), (211, 64, P_AT + 32 + 64)):
        rg = [img(new, 0x6055e700, 0x6055e800, 'sec2'), apc(new), *getter(new, props(0, s24, 1)), *heap('ap', swapped=True), Region('stack', 0x18010000, bytes(0x1000), 'rw'), caller(0x6055e7b6, '[d2,d3],8')]
        r = execute(rg, dict(pc=0x18040000, sp=STK, d0=off, d1=0x77, a1=0x88), 0x18040007, limit=20000); n += 1
        if r['fault'] or r['registers']['a0'] != want or r['registers']['d1'] != 0x77 or r['registers']['a1'] != 0x88:
            bad.append(('tbl-swapped', s24, off, r['fault'], hex(r['registers']['a0'])))
    return n, bad


def t_fsm(new, base, spec):
    """The real SsMenuLv dispatcher 0x60d11448 with a real event and the real (state, event) tables: state 3 (SCP) INFO release ->
    ap_sinfo; cell 111 + AP + Vivid + slot -> rc (4,7), the dispatcher runs state 3's exit (stop there), key word 111, armed.
    Otherwise the stock release handler; other states / events reach the same handler as v0.29a."""
    global ARMED
    bad, n = [], 0
    OBJ, RET = 0x18050200, 0x18040000
    exit3 = struct.unpack_from('<I', new, A.SM_DESC + 24 - BASE)[0]
    exit3 = struct.unpack_from('<I', new, exit3 + 8 - BASE)[0]
    lo, hi = A.SM_EV, A.SM_DESC + 32
    def run(m, state, ev, sid, k, s24, gui, stops):
        obj = bytearray(32); obj[0] = 4; obj[1] = state; struct.pack_into('<I', obj, 4, 0x611317c4); struct.pack_into('<h', obj, 8, -1)
        stk = bytearray(0x1000); struct.pack_into('<I', stk, STK - 0x18010000, RET)
        rg = [img(m, 0x60d11448, 0x60d115e0, 'fsm'), img(m, lo, hi, 'smtab', 'r'), img(m, 0x611317c0, 0x611317f0, 'reg', 'r'), apc(m), *getter(m, props(0, s24, 1)), V.sget(0, gui),
              stub(A.CELL, f' mov {sid},d0\n ret [],4', 'cell'), Region('hold', A.SCP_HOLD & ~0xff, bytes(0x100), 'rw', True), *heap(k, rw=True), Region('obj', OBJ, bytes(obj), 'rw', True),
              Region('stack', 0x18010000, bytes(stk), 'rw'), Region('ret', RET, b'\xcb' * 4, 'rx')] + [Region(f's{i}', a, b'\xcb', 'rx') for i, a in enumerate(sorted(set(stops)))]
        return execute(rg, dict(pc=0x60d11448, sp=STK, d0=ev, d1=0, a0=OBJ, a1=0, d2=5, d3=6, a2=7, a3=8), stops[1], limit=40000)
    fn = lambda m, st, code: struct.unpack_from('<I', m, A.SM_FN + 4 * m[A.SM_MX + [i for i in range(A.SM_NEV) if struct.unpack_from('<I', m, A.SM_EV + 8 * i - BASE)[0] == code][0] * A.SM_NST + st - 1 - BASE] - BASE)[0]
    for state, ev, sid, k, s24, gui in ((3, 0x9015, 111, 'ap', 211, 0), (3, 0x9015, 85, 'ap', 211, 0), (3, 0x9015, 111, 'ap', 3, 0), (3, 0x9015, 111, 'ap', 211, 2),
                                         (3, 0x9015, 111, 'p', 211, 0), (3, 0x9014, 111, 'ap', 211, 0), (3, 0x900c, 111, 'ap', 211, 0), (2, 0x9015, 111, 'ap', 211, 0), (7, 0x9015, 111, 'ap', 211, 0)):
        hit = state == 3 and ev == 0x9015 and sid == 111 and k == 'ap' and s24 == 211 and gui == 0
        want_stop = exit3 if hit else fn(base, state, ev)
        stops = [exit3, want_stop, fn(base, state, ev)]
        r = run(new, state, ev, sid, k, s24, gui, stops); n += 1
        mem = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}
        key = struct.unpack_from('<H', mem['hold'], A.SCP_KEY & 0xff)[0]
        q = mem.get('pool3', bytes(1024))
        ok = not r['fault'] and r['registers']['pc'] == want_stop
        ok = ok and ((key == 111 and q[A.ARM] == 1) if hit else (key == 0 and q[A.ARM] == 0))
        if not ok:
            bad.append((state, hex(ev), sid, k, s24, gui, r['fault'], hex(r['registers']['pc']), hex(want_stop), key))
    return n, bad


def lc_run(m, value, s44, s1337, kind, p2):
    """As V.lc_run, plus our code and a getter registry for the raw reads."""
    FAC, GLOB = V.FAC, V.GLOB
    VT = FAC + 0x10; val = {44: s44, 1337: s1337, 9: 0, 111: value}
    fac = struct.pack('<I', VT) + bytes(12) + struct.pack('<4I', FAC + 0x180, 0, FAC + 0x100, 0)
    get = stub(FAC + 0x100, ''.join(f' cmp {k},d0\n bne 1f\n mov {v},d0\n mov d0,(a1)\n clr d0\n rets\n1:\n' for k, v in val.items()) + ' clr d0\n mov d0,(a1)\n rets', 'fget')
    hp = heap(kind, p2=p2, rw=True)
    rg = [img(m, 0x60e593be, 0x60e5990a, 'lc'), img(m, Bd.W_AT, Bd.W_END, 'mvw'), apc(m), *getter(m, props(s44, 211, 1)), V.sget(s44, value), *hp,
          stub(0x60e4d032, ' mov 2,d0\n ret [d2,d3,a2,a3],60', 'scr'), stub(0x4700115e, ' ret [d2,a2],8', 'ms'), stub(0x60cfec91, ' ret [],4', 'c1'),
          stub(0x60cfeca9, ' ret [d2,a2],16', 'c2'), stub(0x60e4d144, ' clr d0\n ret [],4', 'idx'), stub(0x60e4d157, ' mov 111,d0\n ret [d2],8', 'row'),
          stub(0x607f9062, f' mov {FAC},a0\n ret [],4', 'facg'), stub(0x607b3c32, f' mov {FAC},a0\n ret [],4', 'capg'),
          stub(0x60ee01a1, ' ret [d2,d3,a2,a3],20', 'c281'), stub(0x60ee015f, ' mov 1,d0\n ret [d2,d3,a2,a3],20', 'g281'), stub(0x60e9debc, ' ret [a2,a3],8', 'log'),
          stub(0x60ea3a84, ' ret [],0', 'a84'), stub(0x60e4cea8, ' mov 0,a0\n ret [d2,d3,a2,a3],52', 'scrl'), stub(0x60ea114b, ' ret [d2,d3,a2,a3],56', 'ev'), stub(0x60ea12ca, ' ret [d2,d3,a2,a3],100', 'ca'),
          Region('fac', FAC, fac, 'r'), get, stub(FAC + 0x180, ' clr d0\n rets', 'cap'), Region('glob', GLOB, bytes(0x100), 'rw', True), Region('stack', 0x18010000, bytes(0x1000), 'rw')]
    r = execute(rg, dict(pc=0x60e593be, sp=STK, d0=0x9015, a1=0, d2=0x1111, d3=0x2222, a2=0x3333, a3=0x4444), 0x60e59907, limit=40000)
    mem = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}
    g = mem['glob']
    return r['fault'], r['registers']['d0'] & 0xffff, struct.unpack_from('<H', g, 0x70)[0], struct.unpack_from('<I', g, 0x84)[0], struct.unpack_from('<H', mem['state'], 2)[0] if 'state' in mem else None


def t_lc(new, base):
    bad, n = [], 0
    for kind, p2 in (('ap', False), ('ap', True), ('p', True), ('p', False)):
        for s44 in (0, 1):
            for s1337 in (0, 1):
                for value in (0, 1, 64):
                    a = lc_run(new, value, s44, s1337, kind, p2); b = lc_run(base, value, s44, s1337, kind, p2); n += 1
                    if kind == 'ap' and s44 == 0 and value == 0:
                        want = (None, 0x0407, Bd.CKEY, 1, H3)
                    else:
                        want = b
                    if a[0] or b[0] or a != want:
                        bad.append((kind, p2, s44, s1337, value, a, b))
    return n, bad


def t_ccg(new, sym):
    """mv_get, GetValue(15272) from a Color Creator site, not swapped: AP + AP slot -> 1646; otherwise as v0.29a (movie gate)."""
    bad, n = [], 0
    nget = int(json.loads(Path(sys.argv[2]).read_text())['v026_movie']['get_next'], 16)
    ra = Bd.CC_RA[1]
    for kind, s44, s24 in (('ap', 0, 211), ('ap', 0, 3), ('p', 0, 211), ('ap', 1, 211)):
        stk = bytearray(0x1000); struct.pack_into('<I', stk, 0x800, ra)
        rg = [img(new, Bd.W_AT, Bd.W_END, 'mvw'), img(new, Bd.S_AT, Bd.S_END, 'mvs'), apc(new), *getter(new, props(s44, s24, 1)), V.sget(s44, 0), *heap(kind),
              Region('out', V.OUT, bytes(4), 'rw', True), Region('view', 0x18030000, bytes(0x200), 'r'), Region('stack', 0x18010000, bytes(stk), 'rw'), Region('ra', ra & ~3, b'\xcb' * 8, 'rx'), Region('n', nget, b'\xcb', 'rx')]
        hit = kind == 'ap' and s44 == 0 and s24 == 211
        r = execute(rg, dict(pc=int(sym['mv_get'], 16), sp=STK, d0=15272, a0=0xa0a0, a1=V.OUT, d2=0x1111, d3=0x2222, a2=0x3333, a3=0x18030000), ra if hit else nget, limit=20000); n += 1
        v = struct.unpack('<I', bytes.fromhex(r['memory'][0]['hex']))[0]
        if r['fault'] or r['registers']['sp'] != STK or (hit and v != 1646) or (not hit and (v != 0 or r['registers']['d0'] != 15272)):
            bad.append((kind, s44, s24, r['fault'], v, hex(r['registers']['pc'])))
    return n, bad


def apfile(slot=SLOT, name=b'AP look', crc_bad=False):
    body = bytes(slot) + name.ljust(16, b'\0')
    return b'EP7V' + struct.pack('<III', 1, 80, zlib.crc32(body) ^ (1 if crc_bad else 0)) + body


def t_file(new, spec):
    bad, n = [], 0
    s = {k: int(v, 16) for k, v in spec['ap_custom']['symbols'].items()}
    le = spec['look_editor']['symbols']; stock = spec['look_editor']['stock']
    u = lambda k: int(le[k], 16); Sk = lambda k: int(stock[k], 16)
    FREED, FS2, heapb, RET = 0x18060000, 0x18070000, 0x18080000, 0x18040007
    code = [apc(new), img(new, Bd.L_AT, Bd.L_END, 'mvl'), img(new, u('ed_crc'), u('ed_crc') + 110, 'crc'), img(new, u('ed_wfile'), u('ed_crc'), 'wf')]
    def io(present):
        mvb = int(spec['v026_movie']['wheel_symbols']['mv_pbin'], 16)
        fo = (f' cmp {mvb},a0\n beq 1f\n mov 0x41,d0\n mov d0,a0\n ret [],4\n1:\n mov 0,a0\n ret [],4\n') if present else ' mov 0,a0\n ret [],4\n'
        rd = f' mov {FREED + 4},a1\n mov (a1),d2\n cmp d1,d2\n bls 1f\n mov d1,d2\n1:\n mov d2,d3\n mov {FS2},a1\n cmp 0,d2\n beq 3f\n2:\n movbu (a1),d0\n movbu d0,(a0)\n inc a0\n inc a1\n add -1,d2\n bne 2b\n3:\n mov d3,d0\n ret [d2,d3,a2,a3],24'
        wr = f' mov {FREED + 4},a1\n mov d1,(a1)\n mov d1,d2\n mov d1,d3\n mov {FS2},a1\n1:\n movbu (a0),d0\n movbu d0,(a1)\n inc a0\n inc a1\n add -1,d2\n bne 1b\n mov d3,d0\n ret [d2,d3,a2,a3],24'
        FO2 = 0x180a0000
        jc, _, _, _ = V.SB3.assemble(' .am33_2\n .text\n .global _start\n_start:\n jmp tgt\n', Sk('ep7_fopen'), dict(tgt=FO2))
        return [Region('fo', Sk('ep7_fopen'), jc, 'rx'), stub(FO2, fo, 'fo2'), stub(Sk('ep7_fclose'), ' clr d0\n ret [d2,a2,a3],16', 'fc'), stub(Sk('ep7_free'), f' mov {FREED},a1\n mov 1,d0\n mov d0,(a1)\n ret [],4', 'frs'),
                stub(0x602af887, ' mov 3,d0\n ret [],4', 'sg'), stub(Sk('ep7_fread'), rd, 'fr2'), stub(Sk('ep7_fwrite'), wr, 'fw')]
    picked = bytearray(SLOT); picked[50] = 3; picked[51] = 1; picked[24] = 6; picked[49] = 1
    hue = bytearray(SLOT); hue[5] = 8
    tail = bytearray(SLOT); tail[60] = 1
    # ap_load direct
    for name, f, ok in (('good', apfile(), True), ('ui-bytes', apfile(bytes(picked)), True), ('nofile', None, False), ('crc', apfile(crc_bad=True), False), ('hue', apfile(bytes(hue)), False), ('tail', apfile(bytes(tail)), False)):
        pb = bytearray(V.block(bytes(512), HANDLE, True)); pb[560:565] = b'Other'
        rg = [*code, caller(s['ap_load']), *io(f is not None), stub(Sk('ep7_malloc'), f' mov {P3_AT},a0\n ret [],4', 'ma'), Region('state', 0x622cbcc0, struct.pack('<HHI', 0, HANDLE, 0), 'r'),
              Region('pool', P_AT, bytes(pb), 'rw', True), Region('pool3', P3_AT, bytes(1024), 'rw', True), Region('fr', FREED, bytes(4) + struct.pack('<I', len(f or b'')), 'rw', True), Region('fs', FS2, (f or b'').ljust(0x100, b'\0'), 'rw'),
              Region('stack', 0x18010000, bytes(0x1000), 'rw')]
        r = execute(rg, dict(pc=0x18040000, sp=STK, a2=P_AT, a3=0x4444, d2=0x1111, d3=0x2222), RET, limit=300000); n += 1
        p, q, fr = [bytes.fromhex(x['hex']) for x in r['memory'][:3]]
        pub = p[A.AM:A.AM + 4] == b'EP7A'
        good = not r['fault'] and pub == ok and (fr[0] == 1) == (not ok) and r['registers']['a2'] == P_AT and p[Bd.VM:Bd.VM + 12] == pb[Bd.VM:Bd.VM + 12]
        if ok:
            good = good and struct.unpack_from('<I', p, A.AP3)[0] == P3_AT and q[224:288] == f[16:80] and q[592:608] == f[80:96] and q[560:565] == b'Other' and q[Bd.VM:Bd.VM + 4] == b'EP7V' \
                and struct.unpack_from('<2I', q, Bd.VP) == (P3_AT, HANDLE) and p[224:288] == bytes(64) and q[:4] == b'EP7B'
        if not good:
            bad.append(('load', name, r['fault'], pub, fr[:4].hex(), hex(r['registers']['pc'])))
    # ap_pre / ap_post end to end
    FL = 0x18090000
    for name, ev, start, dirty, f, swapped in (('other', 0, 'ap', 1, None, False), ('dirty', Bd.SB3.EV_PRESS, 'ap', 1, None, False), ('dirty-swapped', Bd.SB3.EV_PRESS, 'ap', 1, None, True),
                                               ('clean', Bd.SB3.EV_PRESS, 'ap', 0, None, False), ('first', Bd.SB3.EV_PRESS, 'fresh', 0, apfile(), False), ('first-nofile', Bd.SB3.EV_PRESS, 'fresh', 0, None, False),
                                               ('stale', Bd.SB3.EV_PRESS, 'stale', 0, apfile(), False)):
        pb = bytearray(V.block(bytes(512), HANDLE, False)); qb = bytearray(V.block(bytes(512), HANDLE, True)); qb[224:288] = SLOT; qb[592:599] = b'AP look'
        struct.pack_into('<3I', qb, Bd.VM, Bd.VMAGIC, P3_AT, HANDLE); qb[Bd.DIRTY] = dirty; qb[Bd.VT:Bd.VT + 4] = b'EP7T'
        if start in ('ap', 'stale'):
            pb[Bd.VT:Bd.VT + 4] = b'EP7T'; pb[A.AM:A.AM + 4] = b'EP7A'; struct.pack_into('<I', pb, A.AP3, P3_AT); pb[A.ATR:A.ATR + 4] = b'EP7U'
        if start == 'stale':                  # a previous session's marks in a fresh P, P3 gone (its block reused)
            struct.pack_into('<3I', pb, Bd.VM, Bd.VMAGIC, P2_AT, HANDLE)
        stk = bytearray(0x1000); struct.pack_into('<I', stk, 0x800 + 16, ev)
        rg = [*code, *io(f is not None or start == 'ap'), stub(Sk('ep7_malloc'), f' mov {P3_AT if start in ("fresh", "stale") else heapb},a0\n ret [],4', 'ma'), Region('state', 0x622cbcc0, struct.pack('<HHI', 0, H3 if swapped else HANDLE, 0), 'r'),
              Region('pool', P_AT, bytes(pb), 'rw', True), Region('pool3', P3_AT, bytes(qb) if start == 'ap' else bytes(1024), 'rw', True), Region('fs', FS2, (f or bytes(0x400)).ljust(0x400, b'\0'), 'rw', True),
              Region('boot', A.BOOT & ~0xf, bytes(16) if start in ('fresh', 'stale') else bytes([1] * 16), 'rw', True), Region('pool2', P2_AT, bytes(1024), 'rw'),
              Region('fr', FREED, bytes(4) + struct.pack('<I', len(f or b'')), 'rw'), Region('heap', heapb, bytes(2048), 'rw'), Region('stack', 0x18010000, bytes(stk), 'rw'),
              Region('cfg', u('ed_cfg_fl') & ~3, struct.pack('<I', FL), 'r'), stub(FL, ' mov 0x5a,d0\n rets', 'fl'), Region('t', u('ed_trig'), b'\xcb', 'rx'),
              img(new, Bd.S_AT, Bd.S_END, 'mvs'), *getter(new, props(0, 211, 1))]
        r = execute(rg, dict(pc=s['ap_pre'], sp=STK, d0=1, d1=2, a0=3, a1=4, a2=0x3333, a3=0x4444, d2=0x1111, d3=0x2222), u('ed_trig'), limit=800000); n += 1
        p_, q_, fs = [bytes.fromhex(x['hex']) for x in r['memory'][:3]]; rr = r['registers']
        good = not r['fault'] and rr['sp'] == STK and (rr['d0'], rr['d1'], rr['a0'], rr['a1'], rr['a2'], rr['a3'], rr['d2'], rr['d3']) == (1, 2, 3, 4, 0x3333, 0x4444, 0x1111, 0x2222)
        exp = {'other': q_[Bd.DIRTY] == 1 and fs[:4] == bytes(4),
               'dirty': fs[:96] == apfile(qb[224:288], b'AP look') and q_[Bd.DIRTY] == 0 and q_[Bd.STATUS] == 1,
               'dirty-swapped': fs[:96] == apfile(qb[224:288], b'AP look') and q_[Bd.DIRTY] == 0 and q_[Bd.STATUS] == 1,
               'clean': fs[:4] == bytes(4),
               'first': p_[A.AM:A.AM + 4] == b'EP7A' and p_[A.ATR:A.ATR + 4] == b'EP7U' and p_[Bd.VT:Bd.VT + 4] == b'EP7T' and q_[224:288] == SLOT and q_[Bd.VM:Bd.VM + 4] == b'EP7V',
               'first-nofile': p_[A.AM:A.AM + 4] == bytes(4) and p_[A.ATR:A.ATR + 4] == b'EP7U',
               'stale': p_[A.AM:A.AM + 4] == b'EP7A' and p_[Bd.VT:Bd.VT + 4] == b'EP7T' and q_[224:288] == SLOT and q_[Bd.VM:Bd.VM + 4] == b'EP7V' and p_[Bd.VM:Bd.VM + 4] == bytes(4)}[name]
        bt = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}.get('boot', b'')
        if start in ('fresh', 'stale') and bt[A.BOOT & 0xf] != 1:
            exp = False
        if not (good and exp):
            bad.append(('trig', name, r['fault'], hex(rr['pc']), good, exp))
    return n, bad


def t_label(new, base):
    bad, n = [], 0
    A_, B_ = 0x60df250b, 0x60df25b5
    LBL, LIST, SRC_ = 0x18060000, 0x18061000, 0x18061100
    want = b'INFO Custom'
    def run(im, build_a, kind, s44, s24, sid_id):
        ent = struct.pack('<IHHI', 0, 4, sid_id, 0x61163e78)
        code = [img(im, 0x60df2400, 0x60df2700, 'bld'), img(im, 0x61242d00, 0x61242f00, 'fh'), img(im, Bd.H_AT, Bd.H_END, 'h'), stub(0x602af887, f' mov {s44},d0\n ret [],4', 'sg'), apc(im), *getter(im, props(s44, s24, 3))]
        cl = (f' .am33_2\n .text\n .global _start\n_start:\n mov {LBL},d0\n mov d0,(4,sp)\n mov 0,d0\n mov 1,d1\n mov {LIST},a1\n call tgt,[d2,d3,a2,a3],24\n nop\n nop\n'
              if build_a else f' .am33_2\n .text\n .global _start\n_start:\n mov {LBL},d0\n mov {SRC_},a1\n call tgt,[d2,a2,a3],20\n nop\n nop\n')
        c, _, _, _ = V.SB3.assemble(cl, 0x18040000, dict(tgt=A_ if build_a else B_))
        rg = [*code, Region('caller', 0x18040000, c, 'rx'), Region('label', LBL, bytes(80), 'rw', True), Region('list', LIST, ent + bytes(4), 'r'), Region('src', SRC_, ent[4:], 'r'),
              *heap(kind), Region('stack', 0x18010000, bytes(0x1000), 'rw')]
        return execute(rg, dict(pc=0x18040000, sp=STK, a0=0x77, d2=0x1111, d3=0x2222, a3=0x3333), 0x18040000 + len(c) - 2, limit=20000)
    for build_a in (True, False):
        for kind, s44, s24, sid_id in (('ap', 0, 211, 1657), ('ap', 0, 14, 1657), ('ap', 0, 3, 1657), ('p', 0, 211, 1657), ('ap', 0, 211, 1658), ('none', 0, 211, 1657)):
            r = run(new, build_a, kind, s44, s24, sid_id); n += 1
            l = bytes.fromhex(r['memory'][0]['hex'])
            if kind == 'ap' and s24 in (211, 14) and sid_id == 1657:
                ok = not r['fault'] and l[0] == 5 and l[8:8 + 2 * len(want)] == b''.join(bytes([c, 0]) for c in want) and r['registers']['d0'] == len(want)
            else:
                b = run(base, build_a, kind, s44, s24, sid_id)
                ok = not r['fault'] and not b['fault'] and l == bytes.fromhex(b['memory'][0]['hex']) and {k: r['registers'][k] for k in ('d0', 'd1', 'd2', 'd3', 'a0', 'a1', 'a2', 'a3', 'sp', 'pc')} == {k: b['registers'][k] for k in ('d0', 'd1', 'd2', 'd3', 'a0', 'a1', 'a2', 'a3', 'sp', 'pc')}
            if not ok:
                bad.append(('AB'[not build_a], kind, s24, sid_id, r['fault'], hex(r['registers']['pc']), l[:12].hex()))
    return n, bad


def main():
    base_p, new_p = sys.argv[1:3]
    bsp, spec = json.loads(Path(base_p).read_text()), json.loads(Path(new_p).read_text())
    base, new = V.image(bsp), V.image(spec)
    fails = []
    def rep(tag, n, bad):
        print(f'{tag}: {n - len(bad)}/{n}', bad[:6]); fails.extend([tag] * bool(bad))
    rep('G capture reads', *t_cap(new, base))
    rep('X tbl_idx / tbl_off', *t_tbl(new, base))
    rep('B WB end to end', *t_wb(new, base))
    rep('K live view job key', *t_key(new, base))
    rep('V live view message / S / slot', *t_lv(new, base, spec))
    rep('S screen lookups (SCP route)', *t_scr(new, base))
    rep('T SCP INFO through the real dispatcher', *t_fsm(new, base, spec))
    rep('I editor init / swapped table', *t_init(new))
    rep('L Live Control INFO (real handler)', *t_lc(new, base))
    rep('C Color Creator guard', *t_ccg(new, spec['v026_movie']['wheel_symbols']))
    rep('F AP.BIN load / save / triggers', *t_file(new, spec))
    rep('N label builders', *t_label(new, base))
    # D: only our sites differ from v0.29a (fw_version's label included)
    al = [(A.AT, A.AT + spec['ap_custom']['code_len']), (A.TBLX, A.TBLX + 5), (A.SCR, A.SCR + 6), (A.SCR2, A.SCR2 + 7), (A.SM_FN + 4 * 24, A.SM_FN + 4 * 24 + 4)] + [(w, w + 4) for w in A.INIT_WORDS] + [(int(a, 16) + 1, int(a, 16) + 5) for a in spec['ap_custom']['sites']]
    al += [(int(e['addr'], 16), int(e['addr'], 16) + len(e['new']) // 2) for e in spec['edits'] if e.get('source') == A.FV.SRC]
    diff = [i + BASE for i in range(len(new)) if new[i] != base[i]]
    rest = [hex(a) for a in diff if not any(x <= a < y for x, y in al)]
    print('D', len(diff), 'bytes differ; outside our sites:', rest[:10]); fails += ['D'] * bool(rest)
    pkg, rst, info = V.BP.build(spec, V.BP.STOCK.read_bytes())
    parts = V.oc.parse(pkg)
    stock = (ROOT / 'analysis/ep7_1100/00_0100_406a0020.decoded.bin').read_bytes()
    k = dict(reparses=[b.kind for b in parts] == [int(x, 16) for x in spec['components']],
             restore_is_stock=hashlib.sha256(V.oc.parse(rst)[0].payload).hexdigest() == hashlib.sha256(stock).hexdigest(),
             decoded_is_emulated=bytes(parts[0].payload) == new)
    print('A', k, info['changed_payload_bytes']); fails += ['A'] * (not all(k.values()))
    if fails:
        sys.exit(f'VERIFY FAILED {fails}')
    print('ALL OK')


if __name__ == '__main__':
    main()
