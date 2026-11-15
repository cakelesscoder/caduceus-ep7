#!/usr/bin/env python3
"""look_hw checks (emulator: real code of v0.33b and of the new build). Offline. Minimal + anti-brick.

  .venv/bin/python -I patches/look_hw/verify.py <v0.33b spec> <new spec> [package dir]

Runs the stock request path req_kind_dispatch 0x60334ba8 -> kind handler -> program builder -> (hook) on a synthetic COLOR
request embedded in a job (the tone / split-tone job guard), with heap P and its slot table. Emulation-only changes (never
written anywhere): boot-ROM memcpy / memset stubs, the one bsch helper 0x603b5d3b -> `clr d0; rets`, pipe_hw_write
0x603450dd -> a capture stub (copies the bank at each write and returns), pipe_hw_start 0x603451d3 -> `ret [],4`, and
lk_get's getter call -> a mock (live view profile). Unmapped RAM reads as zero pages.
  S  stock look (slot +53..+59 = 0), and no P: bank at every write == v0.33b, single pass (1920 x 1080) and split
     (5184 x 3888, both halves).
  K  curve k = 1..7: only the three gamma pointer words (bank+0x10c0..0x10c8) and the words the stage derives from the
     curve differ; the pointers are the curve the stock row pick gives (rows) or flat / log.
  M  matrix: bank+0x6ec..0x6fc == pack(L M) of the Python model, rows sum to 0x80, nothing else differs; both halves.
  L  live view (no capture marker, getter 0xF6B1 = 1): applied; the same request run twice on one bank gives the same
     words (no compounding); getter 0 (movie / AP): stock.
  F  Film pick: library look clears +53..+59, Own / Stock restore the snapshot, without one nothing; registers as v0.33b.
  G  gates: section 5 not loaded, MONO key, profile 5, out-of-range byte, kind 3, class 3 input: == v0.33b.
  P  anti-brick: package = stock + edits, restore == stock, every byte differing from v0.33b is inside this layer's edits.
"""
import json, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'external/oly_fw_analysis/tools'))
import importlib.util  # noqa: E402


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


LH = _load('ep7_lh_build_v', ROOT / 'patches/look_hw/build.py')
ST, B3 = LH.ST, LH.B3
BASE = LH.BASE
from penf_emulator import Region, execute  # noqa: E402

PAGE = 0x1000
J = 0x13000000                              # job (15512 B), request at J + 11364
R = J + LH.REQ_IN_JOB
CAPBUF, CAPN = 0x14000000, 4                # capture: u32 count, then CAPN banks of BANK B
BANK = 0x2580
STUB = 0x13800000                           # stubs (capture, getter mock)
CALLER = 0x13900000
STACK, SP0 = 0x18000000, 0x1800f000
SECT = LH.SECT
HANDLE = 0x41
POOL = 0xa1f8d800
P = POOL + HANDLE - 1
DISPATCH = 0x60334ba8
ROM = 0x47001000


def stubs_code():
    src = f""" .am33_2
 .text
 .global _start
_start:
cap:                              /* pipe_hw_write stand-in: call cap,[d2,d3,a2,a3],28; a0 = ctx */
 mov ({CAPBUF:#x}),d0
 cmp {CAPN},d0
 bcc 9f
 mov d0,d1
 inc d1
 mov d1,({CAPBUF:#x})
 mov {BANK},d1
 mulu d1,d0
 mov d0,a1
 add {CAPBUF + 16:#x},a1
 mov (8,a0),a2
 mov {BANK // 4},d2
1:
 mov (a2),d1
 mov d1,(a1)
 inc4 a1
 inc4 a2
 add -1,d2
 bne 1b
9:
 clr d0
 ret [d2,d3,a2,a3],28
 .balign 16
getter:
 mov (getv),d0
 ret [d2,d3],12
 .balign 4
getv:
 .long 1
"""
    code, _, sy, _ = B3.assemble(src, STUB, {})
    return code, sy


def rom_code():
    src = """ .am33_2
 .text
 .global _start
_start:
 .org 0x52
 cmp 0,d0
 beq 2f
1:
 movbu (a1),d1
 movbu d1,(a0)
 inc a0
 inc a1
 add -1,d0
 bne 1b
2:
 ret [d2,d3,a2,a3],28
 .org 0x15e
 cmp 0,d1
 beq 4f
3:
 movbu d0,(a0)
 inc a0
 add -1,d1
 bne 3b
4:
 ret [d2,a2],8
"""
    return B3.assemble(src, ROM, {})[0]


def emu_image(main, getter_sites, getter_at):
    im = bytearray(main)
    put = lambda a, b: im.__setitem__(slice(a - BASE, a - BASE + len(b)), b)
    put(0x603b5d3b, bytes.fromhex('00f0fc'))                                   # bsch helper: clr d0; rets
    put(LH.HW_WRITE, b'\xdc' + struct.pack('<i', STUB - LH.HW_WRITE))          # -> cap
    put(0x603451d3, bytes.fromhex('df0004'))                                   # pipe_hw_start: ret [],4
    for s in getter_sites:
        put(s + 1, struct.pack('<i', getter_at - s))
    return bytes(im)

REQ_MTX = (206, -92, 14, -34, 194, -32, 10, -74, 192)   # a daylight-like sensor matrix (Q7, rows 128) at request+0x638


def desc(addr, fmt, w, h, n):
    d = bytearray(n)
    struct.pack_into('<IIHHHHHHHH', d, 0, addr, 0, fmt, w, w, h, w, h, 0, 0)
    return d


def fixture(*, w=1920, h=1080, type14=0, kind=0, fmt_in=0x0100, key=0x000b0000, marker=True, profile=1, slot=None, handle=HANDLE,
            sect=0x1ff, mtx=REQ_MTX):
    j = bytearray(15512)
    q = bytearray(0x75c)
    struct.pack_into('<III', q, 0, LH.CALLBACK, J + LH.RECORDS_IN_JOB, key)
    q[16] = kind
    struct.pack_into('<H', q, 14, type14)
    q[20:84] = desc(0x30000000, fmt_in, w, h, 64)
    q[0x394:0x394 + 56] = desc(0x38000000, 0x0302, w, h, 56)
    struct.pack_into('<9h', q, 0x638, *mtx)
    j[LH.REQ_IN_JOB:LH.REQ_IN_JOB + len(q)] = q
    struct.pack_into('<I', j, LH.RECORDS_IN_JOB, J)
    if marker:
        j[15488], j[15489], j[15490] = profile, 11, 0xB2
    p = bytearray(1024); p[0:4] = b'EP7B'
    for k, b in (slot or {}).items():               # {slot index: {byte offset: value}}
        for o, v in b.items():
            p[32 + 64 * k + o] = v & 0xff
    ram = {0x622cbcc0: struct.pack('<HH', 0, handle), SECT: struct.pack('<I', sect), P: bytes(p),
           0xa2731010: b'\xff' * 32, 0x99f00020: b'\xff' * 4}
    return dict(job=bytes(j), ram=ram)


class Run:
    """One emulated dispatch of the fixture's request on an image; zero pages mapped on demand."""
    def __init__(self, image, fx, getv=1, reps=1, limit=30_000_000):
        self.image, self.fx, self.getv, self.reps, self.limit = image, fx, getv, reps, limit

    def regions(self, auto):
        stub = bytearray(STUBS[0]); struct.pack_into('<I', stub, STUBS[1]['getv'] - STUB, self.getv)
        call = b''
        for _ in range(self.reps):                  # mov R,a0; call DISPATCH (d32)
            at = CALLER + len(call)
            call += b'\xfc\xdc' + struct.pack('<I', R) + b'\xdd' + struct.pack('<i', DISPATCH - (at + 6)) + b'\x00\x04'
        call += b'\xcb' * 16
        rg = [Region('main', BASE, self.image, 'rx'), Region('rom', ROM, ROM_CODE.ljust(0x200, b'\0'), 'rx'),
              Region('stub', STUB, bytes(stub), 'rx'), Region('caller', CALLER, call, 'rx'),
              Region('job', J, self.fx['job'], 'rw', True), Region('stack', STACK, bytes(0x10000), 'rw', True),
              Region('cap', CAPBUF, bytes(16 + BANK * CAPN), 'rw', True)]
        for pg in sorted(auto):
            buf = bytearray(PAGE)
            for a, b in self.fx['ram'].items():
                lo, hi = max(a, pg), min(a + len(b), pg + PAGE)
                if lo < hi:
                    buf[lo - pg:hi - pg] = b[lo - a:hi - a]
            rg.append(Region(f'auto_{pg:08x}', pg, bytes(buf), 'rw', True))
        return rg

    def go(self):
        auto = {a & ~(PAGE - 1) for a, b in self.fx['ram'].items() for a in range(a, a + len(b), PAGE)} | \
               {(a + len(b) - 1) & ~(PAGE - 1) for a, b in self.fx['ram'].items()}
        auto |= PAGES
        stop = CALLER + 13 * self.reps
        for _ in range(400):
            r = execute(self.regions(auto), dict(pc=CALLER, sp=SP0), stop, limit=self.limit, timeout=900)
            f = r['fault']
            if not (f and f['kind'] == 1):
                break
            pg = f['address'] & ~(PAGE - 1)
            if pg in auto or STACK <= f['address'] < STACK + 0x10000:
                break
            auto.add(pg)
            end = (f['address'] + max(f['size'], 1) - 1) & ~(PAGE - 1)
            auto.add(end)
        PAGES.update(auto)
        self.r = r
        self.mem = {m['name']: bytes.fromhex(m['hex']) for m in r['memory']}
        c = self.mem['cap']
        self.banks = [c[16 + BANK * i:16 + BANK * (i + 1)] for i in range(struct.unpack_from('<I', c, 0)[0])]
        return self

    @property
    def ok(self):
        return self.r['fault'] is None and self.r['registers']['pc'] == CALLER + 13 * self.reps


PAGES = set()                               # zero pages seen so far (shared by the runs: fewer restarts)
STUBS = stubs_code()
ROM_CODE = rom_code()


def getter_sites(main, spec):
    """lk_get's `call 0x6005e971` (d32) in the new image -> [site]; none in v0.33b."""
    if 'look_hw' not in spec:
        return []
    lo = int(spec['look_hw']['code']['sec5'][0], 16)
    n = spec['look_hw']['code']['sec5'][1]
    out = [lo + i for i in range(n - 5) if main[lo + i - BASE] == 0xdd and lo + i + struct.unpack_from('<i', main, lo + i + 1 - BASE)[0] == ST.GETTER]
    if len(out) != 1:
        raise SystemExit(f'lk_get getter call: {out}')
    return out


def images(base_s, new_s):
    stock = LH.STOCK.read_bytes()
    bm, nm = ST.img_of(base_s, stock), ST.img_of(new_s, stock)
    g = getter_sites(nm, new_s)
    return bm, nm, emu_image(bm, [], 0), emu_image(nm, g, STUBS[1]['getter'])


# ---------------------------------------------------------------- model
def unpack(bank):
    w = struct.unpack_from('<5I', bank, LH.MTX)
    s16 = lambda v: v - 65536 if v & 0x8000 else v
    return [s16(w[0] & 0xffff), s16(w[0] >> 16), s16(w[1] & 0xffff), s16(w[1] >> 16), s16(w[2] & 0xffff), s16(w[2] >> 16),
            s16(w[3] & 0xffff), s16(w[3] >> 16), s16(w[4] & 0xffff)]


def pack(n):
    """The stock packer 0x603ace56 (even LSB of m01, m21, and of m10 / m12 when their sum is odd; diagonals 0x80 - row)."""
    m = list(n)
    m[1] &= ~1
    if (m[3] + m[5]) & 1:
        m[3] &= ~1; m[5] &= ~1
    m[7] &= ~1
    m[0], m[4], m[8] = 128 - m[1] - m[2], 128 - m[3] - m[5], 128 - m[6] - m[7]
    h = [v & 0xffff for v in m]
    return struct.pack('<5I', h[0] | h[1] << 16, h[2] | h[3] << 16, h[4] | h[5] << 16, h[6] | h[7] << 16, h[8])


def model(M, l):
    """N = L M off-diagonals as lh_m computes them (rounded: +64, arithmetic >> 7), then packed."""
    L = [[0, l[0], l[1]], [l[2], 0, l[3]], [l[4], l[5], 0]]
    Mm = [M[0:3], M[3:6], M[6:9]]
    n = [0] * 9
    for i in range(3):
        a, b = [k for k in range(3) if k != i]
        for j in range(3):
            if j != i:
                n[3 * i + j] = Mm[i][j] + ((L[i][a] * (Mm[a][j] - Mm[i][j]) + L[i][b] * (Mm[b][j] - Mm[i][j]) + 64) >> 7)
    return pack(n)


def slot(curve=0, mtx=(0,) * 6, k=0):
    return {k: {53: curve, **{54 + i: v for i, v in enumerate(mtx)}}}


def diff(a, b):
    return [o for o in range(0, BANK, 4) if a[o:o + 4] != b[o:o + 4]]


def same(eb, en, fx, **kw):
    a, b = Run(eb, fx, **kw).go(), Run(en, fx, **kw).go()
    return a.ok and b.ok and len(a.banks) == len(b.banks) and a.banks == b.banks, a, b


SPLIT = dict(w=5184, h=3888, type14=5)            # pipe_prepare's split rule: type low nibble 5, input >= 3426 x 1927
MTX_T = (32, -32, 16, -8, -24, 40)


def t_s(eb, en):
    bad, n, halves = [], 0, None
    for size in ({}, SPLIT):
        for fx in (fixture(**size), fixture(handle=0, slot=slot(2, MTX_T), **size), fixture(slot=slot(0, (0,) * 6, k=1), **size)):
            ok, a, b = same(eb, en, fx)
            n += 1
            if size:
                halves = len(a.banks)
            if not ok:
                bad.append(n)
    return not bad and halves == 2, f'{n} runs, single pass and split ({halves} writes): banks == base; bad {bad}'


def t_k(eb, en):
    stock = LH.STOCK.read_bytes()
    a = Run(eb, fixture()).go()
    bad = []
    for k in range(1, 8):
        b = Run(en, fixture(slot=slot(k))).go()
        want = LH.GPT + 32 * LH.ROWS[k - 1] if k <= 5 else LH.CURVE(LH.FIXED[k - 6])
        if k <= 5:
            want = struct.unpack_from('<I', stock, want - BASE)[0]   # type 0, variant 0: the row's first word (row pick)
        d = diff(a.banks[0], b.banks[0])
        ptr = {struct.unpack_from('<I', b.banks[0], o)[0] for o in (0x10c0, 0x10c4, 0x10c8)}
        if not b.ok or set(d) - {0x10c0, 0x10c4, 0x10c8} or ptr != {want}:
            bad.append((k, [hex(o) for o in d][:6], [hex(x) for x in ptr]))
    return not bad, f'curves 1..7: only bank+0x10c0..0x10c8 differ, = the expected curve; bad {bad}'


def punchy():
    """The six slot bytes look_hw_ui writes for its last named mix at strength 10 (its own model, row())."""
    lu = ROOT / 'patches/look_hw_ui/build.py'
    if not lu.exists():
        return None
    LU = _load('ep7_lu_build_v', lu)
    return LU.MIXES[-1][0], tuple(LU.row(len(LU.MIXES), LU.STEPS))


def t_m(eb, en):
    bad, info = [], ''
    pn = punchy()
    if pn:
        a = Run(eb, fixture()).go()
        b = Run(en, fixture(slot=slot(0, pn[1]))).go()
        M, N = unpack(a.banks[0]), unpack(b.banks[0])
        if not b.ok or b.banks[0][LH.MTX:LH.MTX + 20] != model(M, pn[1]) or set(diff(a.banks[0], b.banks[0])) - set(range(LH.MTX, LH.MTX + 20, 4)):
            bad.append(pn[0])
        info = f'{pn[0]} 100 % {pn[1]}: N {N}; '
    for size in ({}, SPLIT):
        a = Run(eb, fixture(**size)).go()
        b = Run(en, fixture(slot=slot(0, MTX_T), **size)).go()
        for x, y in zip(a.banks, b.banks):
            M = unpack(x)
            want = model(M, MTX_T)
            got = y[LH.MTX:LH.MTX + 20]
            N = unpack(y)
            rows = [sum(N[3 * i:3 * i + 3]) & 0xffff for i in range(3)]
            if got != want or rows != [128] * 3 or set(diff(x, y)) - set(range(LH.MTX, LH.MTX + 20, 4)):
                bad.append((size and 'split', N, rows))
            info = info.split('; M ')[0] + f'; M {M} -> N {N}'
        if len(a.banks) != len(b.banks) or not b.ok:
            bad.append(('writes', len(a.banks), len(b.banks)))
    return not bad, f'{info}; rows 0x80; only the 5 matrix words; single + both split halves; bad {bad}'


BANKS = [0x6225f5cc + 0x257c * k for k in range(2)] + [0x62641210 + 0x257c * k for k in range(2)] + \
        [0x6266a848 + 0x257c * k for k in range(3)]   # the ISP bank pool (0x60532c80), cached and uncached alias
SENT = 0x2560                                         # a bank word no build step writes (0 in every run): marks a pre-filled bank


def prefilled(fx, bank):
    """Every pool bank pre-filled with `bank` (an earlier pass's register image, our edit included) up to its state words."""
    img = bytearray(bank[:9584]); struct.pack_into('<I', img, SENT, 0x5a5a5a5a)
    for b in BANKS:
        for a in (b, b + 0x40000000):
            fx['ram'][a] = bytes(img)
    return fx


def t_l(eb, en):
    lv = lambda: fixture(marker=False, slot=slot(6, MTX_T))
    one = Run(en, lv(), getv=1).go()
    base = Run(eb, fixture(marker=False)).go()
    want = model(unpack(base.banks[0]), MTX_T)
    ok = one.ok and one.banks[0][LH.MTX:LH.MTX + 20] == want and struct.unpack_from('<I', one.banks[0], 0x10c0)[0] == LH.CURVE(51)
    # live view reuses its bank: the next pass starts from this pass's edited image; the result must be the same words
    two = Run(en, prefilled(lv(), one.banks[0]), getv=1).go()
    reused = two.ok and struct.unpack_from('<I', two.banks[0], SENT)[0] == 0x5a5a5a5a
    nocomp = reused and two.banks[0][:SENT] == one.banks[0][:SENT] and two.banks[0][SENT + 4:9584] == one.banks[0][SENT + 4:9584]
    off, _, _ = same(eb, en, fixture(marker=False, slot=slot(6, MTX_T)), getv=0)
    return ok and nocomp and off, (f'live view: applied {ok}; next pass on the same (pre-filled, already edited) bank: bank reused {reused}, '
                                   f'identical words (no compounding) {nocomp}; getter 0 (movie / AP) == v0.33b {off}')


def t_g(eb, en):
    cases = {'section 5 not loaded': dict(sect=0x0f), 'MONO key': dict(key=0x000c0000), 'profile 5': dict(profile=5),
             'byte 65': dict(slot={0: {53: 0, 54: 65, 55: 1}}), 'curve 8': dict(slot={0: {53: 8}}),
             'class 3 input': dict(fmt_in=0x0302), 'kind 16, MONO slot': dict(kind=16, profile=5)}
    bad = []
    for name, kw in cases.items():
        kw.setdefault('slot', slot(2, MTX_T))
        ok, a, b = same(eb, en, fixture(**kw))
        if not ok:
            bad.append(name)
    return not bad, f'{len(cases)} gate cases == v0.33b; bad {bad}'


def t_f(bm, nm, new_s):
    """Film pick: from sl_pick's tail jump to ls_pick's entry, k = 1 (COLOR2), the slot holding curve / matrix bytes."""
    ls_pick = int(new_s['look_hw']['ls_pick'], 16)
    L = LH.LS.FB.POOL2 + 0x4040 * 5
    def fx(pos, snap):
        pp = bytearray(1024); pp[0:4] = b'EP7B'
        struct.pack_into('<I', pp, 1016, L); pp[1020:1024] = b'EP7F'
        for o in range(53, 60):
            pp[32 + 64 + o] = 0x11 + o
        lb = bytearray(0x4040); lb[2112:2116] = b'EP7L'; struct.pack_into('<I', lb, 2116, P)
        lb[2120] = 10; lb[2121 + 1] = pos; lb[2125 + 1] = snap
        for o in range(53, 60):
            lb[2132 + 80 + o] = 0x40 + o
        return pp, lb
    res, ok = [], True
    for pos, snap, want in ((3, 1, [0] * 7), (0, 1, [0x40 + o for o in range(53, 60)]), (11, 1, [0x40 + o for o in range(53, 60)]),
                            (0, 0, [0x11 + o for o in range(53, 60)])):
        pp, lb = fx(pos, snap)
        outs = []
        for im in (bm, nm):
            rg = [Region('main', BASE, im, 'rx'), Region('state', 0x622cbcc0, struct.pack('<HH', 0, HANDLE), 'r'),
                  Region('P', P, bytes(pp), 'rw', True), Region('L', L, bytes(lb), 'rw', True),
                  Region('stack', STACK, bytes(0x10000), 'rw', True)]
            r = execute(rg, dict(pc=LH.PICK_TAIL, sp=SP0, a2=P, d3=1, a3=0x1234), ls_pick, limit=100000)
            outs.append((r, {m['name']: bytes.fromhex(m['hex']) for m in r['memory']}))
        (r0, m0), (r1, m1) = outs
        g0, g1 = r0['registers'], r1['registers']
        got = list(m1['P'][32 + 64 + 53:32 + 64 + 60])
        good = not r1['fault'] and g1['pc'] == ls_pick and all(g0[k] == g1[k] for k in ('d2', 'd3', 'a2', 'a3', 'sp')) and got == want
        good &= m1['L'] == m0['L'] and m1['P'][:32 + 64 + 53] == m0['P'][:32 + 64 + 53] and m1['P'][32 + 64 + 60:] == m0['P'][32 + 64 + 60:]
        ok &= good
        res.append(f'pos {pos} snap {snap}: {"ok" if good else got}')
    return ok, 'Film pick (library clears, Own / Stock from the snapshot, no snapshot: kept), registers at ls_pick == v0.33b: ' + '; '.join(res)


def t_p(base_s, new_s, bm, nm, disk):
    import build_package as BP
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
            if e['kind'] == '0x100' and not e['addr'].startswith('off:') and (e.get('source') == LH.SRC or '[look_hw' in e['why'])]
    ours += [(int(e['addr'], 16), len(e['new']) // 2) for e in new_s['edits'] if e.get('source') == 'patches/fw_version']
    diffs = [BASE + i for i in range(len(bm)) if bm[i] != nm[i]]
    stock_m = LH.STOCK.read_bytes()
    back = [a for a in diffs if nm[a - BASE] == stock_m[a - BASE]]          # bytes this layer's revision put back to stock
    stray = [hex(a) for a in diffs if not any(s <= a < s + k for s, k in ours) and a not in back]
    good &= not stray
    if disk:
        good &= (disk / 'patched.pkg.bin').read_bytes() == pkg and (disk / 'restore-stock.pkg.bin').read_bytes() == rst
    return good, f'{len(new_s["edits"])} edits; main {len(diffs)} B differ from the base ({len(back)} back to stock), stray {stray[:6]}; other components == base; restore == stock'


def main():
    base_s, new_s = (json.loads(Path(p).read_text()) for p in sys.argv[1:3])
    disk = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    bm, nm, eb, en = images(base_s, new_s)
    ok = True
    for tag, f in (('S', lambda: t_s(eb, en)), ('K', lambda: t_k(eb, en)), ('M', lambda: t_m(eb, en)), ('L', lambda: t_l(eb, en)),
                   ('G', lambda: t_g(eb, en)), ('F', lambda: t_f(bm, nm, new_s)), ('P', lambda: t_p(base_s, new_s, bm, nm, disk))):
        g, txt = f()
        print(f"{'PASS' if g else 'FAIL'} {tag} {txt}", flush=True)
        ok &= g
    print('ALL PASS' if ok else 'FAILURES')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
