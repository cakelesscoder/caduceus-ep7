#!/usr/bin/env python3
"""plugin_loader checks (emulator, offline): the SD plugin layer v1 against v0.32 without it. Minimal + anti-brick.

  .venv/bin/python -I patches/plugin_loader/verify.py releases/v0.31d/edits.json generated/v032/edits.json \
      [generated/v032/rel] [generated/v032/test_plugin/EP7MOD/PLUGIN.BIN]

BASE = patches/v032 apply(v0.31d, plugins=False); NEW = the built spec (must equal plugin_loader.apply(BASE)).
Runs use the whole patched main image (rx: any store into the image faults) with jmp trampolines at the file services,
malloc / free and 0x602af887 to stubs that count calls. ap_post 0x601df6e5 runs from entry on a half-press event to its
tail jmp 0x605b7340: ap_P, ap_load (real AP.BIN parse, real CRC) and pl_ap / pl_chk / init, all real code.
  S  static: NEW differs from BASE only inside the plugin_loader edits; the placements are stock bytes in BASE.
  N  no PLUGIN.BIN (AP.BIN present / absent; class-2 malloc failing): registers, stack, P, the AP heap and the stock
     services' call counts == BASE; new: one 16 KB malloc and one free of that block (none when malloc fails).
  R  rejected files (magic, ABI, flags, firmware id, size field, CRC, 33 B, 16385 B, short read, seek failure): no
     init, the block freed once, fopen / fclose balanced, P+852 / P+856 untouched, everything else == BASE.
  V  valid file (count plugin, also at exactly 16384 B): init once, from the cached alias (the uncached block is not
     executable here), a0 = API table v1, d0 = B; accept -> P+852 'EP7K', P+856 = B, B never freed; decline -> nothing
     published, B not freed. AP.BIN result == BASE. A second ap_post from that state: no malloc, no fopen, no init.
  F  Firmware screen (both Body value sites, real view code + pl_fw + fw_val, setter stubbed to capture): no looks,
     no plugin, ready plugin with hook word 0, and the hello state loaded by the real loader: "0.32" == BASE in the first
     three, "0.32P" with hello; an empty field passes through; widget, callee-saved registers, caller frame == BASE.
  P  anti-brick: package decodes to stock + edits, restore == stock, decoded main == the emulated image, files on disk
     match; hello's PLUGIN.BIN rebuilds byte for byte.
"""
import hashlib, importlib.util, json, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'external/oly_fw_analysis/tools'))
import build_package as BP  # noqa: E402
import oly_container as oc  # noqa: E402
from penf_emulator import Region, execute  # noqa: E402


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


PL = _load('ep7_pl_build_v', ROOT / 'patches/plugin_loader/build.py')
V32 = _load('ep7_v032_build_v', ROOT / 'patches/v032/build.py')
HB = _load('ep7_hello_build_v', ROOT / 'tools/plugins/hello/build.py')
FV = _load('ep7_fwv_verify_v', ROOT / 'patches/fw_version/verify.py')
AV = _load('ep7_apc_verify_v', ROOT / 'patches/ap_custom/verify.py')
SB3 = PL.SB3
BASE = 0x60020020
STOCK = PL.STOCK.read_bytes()

AP_POST, AP_TAIL, EV_PRESS = 0x601df6e5, 0x605b7340, 0x02000100
HANDLE, POOL = 0x41, 0xa1f8d800
P_AT = POOL + HANDLE - 1
VT = 980                                    # P+980 'EP7T' (looks loaded): ap_post's gate
ATR = PL.ATR
BLK = 0xa1dd8d40 + 0x4040 * 9               # the class-2 block (uncached); cached alias BLK - 0x40000000
BLKC = BLK - 0x40000000
STKR, STK = 0x18010000, 0x18010800
HEAP = P_AT + 0x1000                        # bump heap for ap_load's 1 KB mallocs: P3 must be a valid pool handle (ap_load checks)
STUBS, LOG, FSC, FSAP, FSPL = 0x18100000, 0x18110000, 0x18110100, 0x18120000, 0x18130000
H_AP, H_PL = 0x41, 0x51
SGET = 0x602af887
REGS0 = dict(d0=1, d1=2, a0=3, a1=4, d2=0x1111, d3=0x2222, a2=0x3333, a3=0x4444, mdr=0x6d6d)
KEEP = ('d0', 'd1', 'd2', 'd3', 'a0', 'a1', 'a2', 'a3', 'sp', 'pc')   # mdr: already clobbered in v0.32-without (last inner call's return)
# LOG words: 0 big mallocs, 1 frees, 2 last freed a0, 3 fopen PLUGIN.BIN, 4 fclose, 5 inits, 6 init d0, 7 init a0,
#            8 frees of the block, 9 fopen AP.BIN, 10 small mallocs


def stub_src(pl_path, ap_path):
    L = lambda i: f'({4 * i},a1)'
    inc = lambda i: f' mov {LOG:#x},a1\n mov {L(i)},d1\n inc d1\n mov d1,{L(i)}\n'
    return f""" .am33_2
 .text
 .global _start
_start:
s_malloc:                          /* call ..,[],4 */
 cmp 16384,d0
 bne 1f
{inc(0)} mov {FSC:#x},a1
 mov (16,a1),a0
 mov a0,d0
 ret [],4
1:
{inc(10)} mov {FSC:#x},a1
 mov (28,a1),a0
 mov a0,d1
 add 0x400,d1
 mov d1,(28,a1)
 mov a0,d0
 ret [],4
 .balign 4
s_free:                            /* call ..,[],4 */
{inc(1)} mov a0,(8,a1)
 cmp {BLK:#x},a0
 bne 1f
 mov (32,a1),d1
 inc d1
 mov d1,(32,a1)
1:
 ret [],4
 .balign 4
s_fopen:                           /* call ..,[],4: a0 path -> a0 handle or 0 */
 cmp {pl_path:#x},a0
 bne 1f
{inc(3)} mov {FSC:#x},a1
 mov (20,a1),a0
 mov a0,d0
 ret [],4
1:
 cmp {ap_path:#x},a0
 bne 2f
{inc(9)} mov {FSC:#x},a1
 mov (24,a1),a0
 mov a0,d0
 ret [],4
2:
 mov 0,a0
 clr d0
 ret [],4
 .balign 4
s_fclose:                          /* call ..,[d2,a2,a3],16 */
{inc(4)} clr d0
 ret [d2,a2,a3],16
 .balign 4
s_fseek:                           /* call ..,[d2,d3,a2,a3],20 */
 mov {FSC:#x},a2
 mov (8,a2),d0
 ret [d2,d3,a2,a3],20
 .balign 4
s_ftell:                           /* call ..,[d2,a2,a3],16: a0 handle */
 mov {FSC:#x},a2
 cmp {H_PL},a0
 bne 1f
 mov (4,a2),d0
 ret [d2,a2,a3],16
1:
 mov (a2),d0
 ret [d2,a2,a3],16
 .balign 4
s_fread:                           /* call ..,[d2,d3,a2,a3],24: a0 dst, d0 1, d1 count, a1 handle */
 mov {FSC:#x},a2
 cmp {H_PL},a1
 bne 1f
 mov (4,a2),d2
 mov {FSPL:#x},a3
 cmp d1,d2
 bls 3f
 mov d1,d2
3:
 mov (12,a2),d3                    /* short read of PLUGIN.BIN */
 cmp 0,d3
 beq 4f
 add -1,d2
 bra 4f
1:
 mov (a2),d2
 mov {FSAP:#x},a3
 cmp d1,d2
 bls 4f
 mov d1,d2
4:
 mov d2,d3
 cmp 0,d2
 beq 6f
5:
 movbu (a3),d0
 movbu d0,(a0)
 inc a0
 inc a3
 add -1,d2
 bne 5b
6:
 mov d3,d0
 ret [d2,d3,a2,a3],24
 .balign 4
s_sget:                            /* 0x602af887, as ap_custom's verifier */
 mov 3,d0
 ret [],4
"""


def tramp(at, tgt):
    return b'\xdc' + struct.pack('<i', tgt - at)


def prepare(m, spec):
    """Image copy with trampolines + the stub region."""
    pl_path = int(spec['plugin_loader']['symbols']['pl_path'], 16) if 'plugin_loader' in spec else 0xfffffff0
    ap_path = int(spec['ap_custom']['symbols']['ap_pbin'], 16)
    code, _, sy, _ = SB3.assemble(stub_src(pl_path, ap_path), STUBS, {})
    im = bytearray(m)
    for svc, k in (('ep7_malloc', 's_malloc'), ('ep7_free', 's_free'), ('ep7_fopen', 's_fopen'), ('ep7_fclose', 's_fclose'),
                   ('ep7_fseek', 's_fseek'), ('ep7_ftell', 's_ftell'), ('ep7_fread', 's_fread')):
        a = PL.SYMS[svc]
        im[a - BASE:a - BASE + 5] = tramp(a, sy[k])
    im[SGET - BASE:SGET - BASE + 5] = tramp(SGET, sy['s_sget'])
    return bytes(im), code


def pblock(ps=0, pb=0, atr=False):
    p = bytearray(1024); p[:4] = b'EP7B'; p[VT:VT + 4] = b'EP7T'
    struct.pack_into('<II', p, PL.PS, ps, pb)
    if atr:
        p[ATR:ATR + 4] = b'EP7U'
    return bytes(p)


def run_post(prep, ap=None, plugin=None, p=None, blk=None, big_ok=True, seek_fail=0, short=0, ev=EV_PRESS, log=None):
    im, code = prep
    fsc = struct.pack('<8I', len(ap or b''), len(plugin or b''), seek_fail, short, BLK if big_ok else 0,
                      H_PL if plugin is not None else 0, H_AP if ap is not None else 0, HEAP)
    stk = bytearray(0x1000); struct.pack_into('<I', stk, 0x800 + 16, ev)
    b = blk or bytes(16384)
    rg = [Region('img', BASE, im, 'rx'), Region('stubs', STUBS, code, 'rx'),
          Region('state', 0x622cbcc0, struct.pack('<HHI', 0, HANDLE, 0), 'rw', True),
          Region('pool', P_AT, p or pblock(), 'rw', True),
          Region('heap', HEAP, bytes(0x2000), 'rw', True),
          Region('blk', BLK, b, 'rw', True), Region('blkc', BLKC, b, 'rx', alias_of='blk'),
          Region('log', LOG, log or bytes(0x100), 'rw', True), Region('fsc', FSC, fsc, 'rw', True),
          Region('fsap', FSAP, (ap or b'').ljust(0x400, b'\0'), 'r'),
          Region('fspl', FSPL, (plugin or b'').ljust(0x4800, b'\0'), 'r'),
          Region('boot', 0x6203c8b0, bytes(16), 'rw', True),
          Region('stack', STKR, bytes(stk), 'rw', True)]
    r = execute(rg, dict(REGS0, pc=AP_POST, sp=STK), AP_TAIL, limit=2_000_000, timeout=120)
    mem = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}
    lg = struct.unpack_from('<11I', mem['log'])
    return r, mem, lg


def ok_run(r):
    return not r['fault'] and r['registers']['pc'] == AP_TAIL


def same_as_base(rb, rn, skip_pool=()):
    """registers, stack above sp, P (minus skip), state, heap identical."""
    (r0, m0, _), (r1, m1, _) = rb, rn
    if not (ok_run(r0) and ok_run(r1)):
        return False
    g0, g1 = r0['registers'], r1['registers']
    sp = g1['sp'] - STKR
    p0, p1 = bytearray(m0['pool']), bytearray(m1['pool'])
    for o in skip_pool:
        p0[o:o + 4] = p1[o:o + 4] = bytes(4)
    return (all(g0[k] == g1[k] for k in KEEP) and m0['stack'][sp:] == m1['stack'][sp:] and p0 == p1
            and m0['heap'] == m1['heap'] and m0['state'] == m1['state'] and m0['boot'] == m1['boot'])


def stock_counts(lg):
    return lg[1] - lg[8], lg[4], lg[9], lg[10]      # frees of other blocks, fcloses, AP opens, small mallocs


def count_plugin(ret=0, pad=0):
    src = f""" .am33_2
 .text
 .global _start
_start:
 .space 32
 mov {LOG + 20:#x},a1
 mov (a1),d1
 inc d1
 mov d1,(a1)
 mov d0,(4,a1)
 mov a0,(8,a1)
 mov {ret},d0
 rets
"""
    code, _ = HB.assemble(src)
    return HB.make(code + bytes(pad))


def t_s(base, new, base_s, new_s):
    ours = [(int(e['addr'], 16), len(e['new']) // 2) for e in new_s['edits']
            if e['kind'] == '0x100' and not e['addr'].startswith('off:') and (e.get('source') == PL.SRC or '[plugin_loader' in e['why'])]
    import numpy as np
    diff = [BASE + int(i) for i in np.nonzero(np.frombuffer(base, np.uint8) != np.frombuffer(new, np.uint8))[0]]
    stray = [hex(a) for a in diff if not any(s <= a < s + n for s, n in ours)]
    regions = all(base[lo - BASE:hi - BASE] == STOCK[lo - BASE:hi - BASE] for lo, hi in PL.REGIONS.values())
    m = new_s['plugin_loader']
    sites = new[int(m['ap_site'], 16) - BASE:][:5] == PL.call16_bytes(int(m['ap_site'], 16), PL.REGIONS['.pla'][0], 24)
    rebuilt = ST_img(PL.apply(base_s)) == new
    return not stray and regions and sites and rebuilt, \
        f'{len(diff)} B differ from v0.32-without, all inside {len(ours)} plugin edits; placements stock in base; spec reproducible'


def ST_img(spec):
    return PL.ST.img_of(spec, STOCK)


def t_n(pb, pn, apf):
    bad, n = [], 0
    for name, ap, big in (('AP.BIN', apf, True), ('no AP.BIN', None, True), ('malloc fails', apf, False)):
        rb, rn = run_post(pb, ap=ap), run_post(pn, ap=ap, big_ok=big)
        n += 1
        lb, ln = rb[2], rn[2]
        want = (1, 1, 1, 0) if big else (1, 0, 0, 0)      # big mallocs, block frees, PLUGIN opens, inits
        good = same_as_base(rb, rn) and stock_counts(lb) == stock_counts(ln) and (ln[0], ln[8], ln[3], ln[5]) == want
        good &= lb[0] == lb[3] == lb[8] == 0
        good &= rn[1]['pool'][PL.PS:PL.PS + 8] == bytes(8)
        if ap:
            good &= rn[1]['heap'] != bytes(0x2000) and rn[1]['pool'][AV.A.AM:AV.A.AM + 4] == b'EP7A'
        if not good:
            bad.append((name, rn[0]['fault'], hex(rn[0]['registers']['pc']), ln))
    return not bad, f'{n} cases == v0.32-without (AP.BIN loaded the same); bad {bad[:2]}'


def variants(good):
    def hdr(f):
        b = bytearray(good); f(b); return bytes(b)
    def recrc(b):
        struct.pack_into('<I', b, 4, __import__('zlib').crc32(bytes(b[8:])) & 0xffffffff)
    return [('magic', hdr(lambda b: (b.__setitem__(slice(0, 4), b'EP7Q'))), {}),
            ('ABI 2', hdr(lambda b: (struct.pack_into('<H', b, 8, 2), recrc(b))), {}),
            ('flags 1', hdr(lambda b: (struct.pack_into('<H', b, 10, 1), recrc(b))), {}),
            ('firmware id', hdr(lambda b: (b.__setitem__(12, b[12] ^ 1), recrc(b))), {}),
            ('size field', hdr(lambda b: (struct.pack_into('<I', b, 16, len(b) + 4), recrc(b))), {}),
            ('CRC', hdr(lambda b: b.__setitem__(4, b[4] ^ 0x80)), {}),
            ('code byte', hdr(lambda b: b.__setitem__(33, b[33] ^ 1)), {}),
            ('33 B', good[:33], {}),
            ('16385 B', good + bytes(16385 - len(good)), {}),
            ('short read', good, dict(short=1)),
            ('seek fails', good, dict(seek_fail=1))]


def t_r(pb, pn, apf):
    good_f = count_plugin()
    rb = run_post(pb, ap=apf)
    bad, n = [], 0
    for name, f, kw in variants(good_f):
        rn = run_post(pn, ap=apf, plugin=f, **kw)
        n += 1
        ln = rn[2]
        ok = same_as_base(rb, rn) and stock_counts(ln) == (stock_counts(rb[2])[0], stock_counts(rb[2])[1] + 1, *stock_counts(rb[2])[2:])
        ok &= (ln[0], ln[8], ln[3], ln[5], ln[2]) == (1, 1, 1, 0, BLK) and rn[1]['pool'][PL.PS:PL.PS + 8] == bytes(8)
        if not ok:
            bad.append((name, rn[0]['fault'], hex(rn[0]['registers']['pc']), ln))
    return not bad, f'{n} rejected files: no init, block freed once, fopen/fclose balanced, rest == v0.32-without; bad {bad[:2]}'


def t_v(pb, pn, apf):
    rb = run_post(pb, ap=apf)
    api = int(PL_SYMS['pl_api'], 16)
    bad, info = [], []
    full = count_plugin(pad=PL.BSIZE - len(count_plugin()))
    assert len(full) == PL.BSIZE
    for name, f in (('count', count_plugin()), ('count 16384 B', full)):
        rn = run_post(pn, ap=apf, plugin=f)
        ln, p = rn[2], rn[1]['pool']
        ok = same_as_base(rb, rn, skip_pool=(PL.PS, PL.PB)) and stock_counts(ln)[1:] == (stock_counts(rb[2])[1] + 1, *stock_counts(rb[2])[2:])
        ok &= (ln[0], ln[8], ln[3], ln[5], ln[6], ln[7]) == (1, 0, 1, 1, BLK, api)
        ok &= p[PL.PS:PL.PS + 4] == b'EP7K' and struct.unpack_from('<I', p, PL.PB)[0] == BLK and rn[1]['blk'][:len(f)] == f
        # second half-press from that state
        r2 = run_post(pn, ap=apf, plugin=f, p=p, blk=rn[1]['blk'], log=rn[1]['log'])
        ok &= ok_run(r2[0]) and r2[2] == ln and r2[1]['pool'] == p and r2[1]['blk'] == rn[1]['blk']
        if not ok:
            bad.append((name, rn[0]['fault'], hex(rn[0]['registers']['pc']), ln, r2[2]))
    rn = run_post(pn, ap=apf, plugin=count_plugin(ret=1))
    ln = rn[2]
    if not (same_as_base(rb, rn) and (ln[0], ln[8], ln[5]) == (1, 0, 1) and rn[1]['pool'][PL.PS:PL.PS + 8] == bytes(8)):
        bad.append(('decline', rn[0]['fault'], ln))
    # hello, end to end: its state feeds F
    hello, _ = HB.build()
    rh = run_post(pn, ap=apf, plugin=hello)
    ph, bh = rh[1]['pool'], rh[1]['blk']
    hook = struct.unpack_from('<I', bh, 28)[0]
    txt = bh[hook - BLK:hook - BLK + 32].decode('utf-16le').split('\0')[0] if BLK <= hook < BLK + 16384 else None
    if not (same_as_base(rb, rh, skip_pool=(PL.PS, PL.PB)) and ph[PL.PS:PL.PS + 4] == b'EP7K' and txt == '0.32P'):
        bad.append(('hello', rh[0]['fault'], txt))
    info.append(f'hello hook text "{txt}"')
    return not bad, f'init once from the cached alias, published, never freed; 2nd ap_post: nothing; decline: nothing published; {info[0]}; bad {bad[:2]}', (ph, bh)


CAP = FV.CAP
OBJ, OBLK = FV.OBJ, FV.BLK


def fw_run(m, site, field, p=None, blk=None, handle=HANDLE):
    im = bytearray(m)
    c = FV.asm(FV.SETTER_CAP, FV.FB.SETTER)
    im[FV.FB.SETTER - BASE:FV.FB.SETTER - BASE + len(c)] = c
    obj = bytearray(OBLK + 1004)
    w = (field + '\0').encode('utf-16le')
    for off in (940, 300):
        obj[OBLK + off:OBLK + off + len(w)] = w
    stack = bytearray(0x1100); struct.pack_into('<I', stack, 0x1000 + 4, OBJ + OBLK)
    rg = [Region('img', BASE, bytes(im), 'rx'), Region('obj', OBJ, bytes(obj), 'r'),
          Region('stack', FV.STACK, bytes(stack), 'rw', True), Region('cap', CAP, bytes(0x100), 'rw', True),
          Region('state', 0x622cbcc0, struct.pack('<HHI', 0, handle, 0), 'r')]
    if p is not None:
        rg.append(Region('pool', P_AT, p, 'r'))
    if blk is not None:
        rg.append(Region('blk', BLK, blk, 'r'))
    r = execute(rg, {'sp': FV.STACK + 0x1000, 'pc': site - 6, 'a0': 0x5a5a0026, 'a3': 0x44, 'd2': 0x22, 'd3': 0x33, 'a2': 0x55},
                site + 7, limit=200_000, timeout=120)
    mem = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}
    regs = {k: r['registers'][k] for k in ('d2', 'd3', 'a2', 'a3', 'sp', 'pc')}
    return r['fault'], FV.wstr(mem['cap'][:0xfc]), struct.unpack_from('<I', mem['cap'], 0xfc)[0], regs, mem['stack'][0x1000:]


def t_f(base, new, hello_state):
    ph, bh = hello_state
    blk0 = bytes(16384)
    ready0 = bytearray(pblock(int.from_bytes(b'EP7K', 'little'), BLK))
    cases = [('no looks', None, None, 0, '1.1', '0.32'), ('no plugin', pblock(), None, HANDLE, '1.1', '0.32'),
             ('hook word 0', bytes(ready0), blk0, HANDLE, '1.1', '0.32'), ('hello', ph, bh, HANDLE, '1.1', '0.32P'),
             ('hello, empty field', ph, bh, HANDLE, '', '')]
    bad, shown = [], []
    for site in PL.FW_SITES:
        for name, p, b, h, field, want in cases:
            fb, tb, wb, rb, kb = fw_run(base, site, field, p, b, h)
            fn, tn, wn, rn, kn = fw_run(new, site, field, p, b, h)
            exp_base = '0.32' if field else ''
            ok = not fb and not fn and tb == exp_base and tn == want and wb == wn == 0x5a5a0026 and rb == rn and kb == kn
            if not ok:
                bad.append((hex(site), name, fn, tn, tb))
            if name == 'hello':
                shown.append(f'{site:#x} "{tn}"')
    return not bad, f'{len(cases) * 2} runs; base "0.32", hello {", ".join(shown)}; bad {bad[:2]}'


def t_p(new_s, new, disk, card_plugin):
    pkg, rst, info = BP.build(new_s, STOCK_PKG)
    sb = {b.kind: b for b in oc.parse(STOCK_PKG)}
    good = True
    parts = oc.parse(pkg)
    for b in parts:
        exp = bytearray(sb[b.kind].payload)
        for e in new_s['edits']:
            if int(e['kind'], 16) == b.kind:
                o = BP.resolve(b.kind, e['addr']); nb = bytes.fromhex(e['new']); exp[o:o + len(nb)] = nb
        good &= bytes(exp) == b.payload
    good &= {b.kind: b for b in parts}[0x100].payload == new
    for b in oc.parse(rst):
        good &= b.payload == sb[b.kind].payload
    txt = f'decode == stock + {info["edits"]} edits, decoded main == emulated image, restore == stock'
    if disk:
        good &= (disk / 'patched.pkg.bin').read_bytes() == pkg and (disk / 'restore-stock.pkg.bin').read_bytes() == rst
        txt += f', {disk} matches (sha256 {hashlib.sha256(pkg).hexdigest()[:16]})'
    if card_plugin:
        good &= card_plugin.read_bytes() == HB.build()[0]
        txt += f', {card_plugin.name} == hello rebuild'
    return good, txt


STOCK_PKG = BP.STOCK.read_bytes()
PL_SYMS = {}


def main():
    v031d, new_s = (json.loads(Path(p).read_text()) for p in sys.argv[1:3])
    disk = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    card = Path(sys.argv[4]) if len(sys.argv) > 4 else None
    base_s = V32.apply(v031d, plugins=False)
    PL_SYMS.update(new_s['plugin_loader']['symbols'])
    base, new = ST_img(base_s), ST_img(new_s)
    pb, pn = prepare(base, base_s), prepare(new, new_s)
    apf = AV.apfile()
    ok = True
    hello_state = None
    for tag, f in (('S', lambda: t_s(base, new, base_s, new_s)), ('N', lambda: t_n(pb, pn, apf)), ('R', lambda: t_r(pb, pn, apf)),
                   ('V', lambda: t_v(pb, pn, apf)), ('F', lambda: t_f(base, new, hello_state)),
                   ('P', lambda: t_p(new_s, new, disk, card))):
        res = f()
        if tag == 'V':
            hello_state = res[2]
        g, txt = res[0], res[1]
        print(f"{'PASS' if g else 'FAIL'} {tag} {txt}", flush=True)
        ok &= g
    print('ALL PASS' if ok else 'FAILURES')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
