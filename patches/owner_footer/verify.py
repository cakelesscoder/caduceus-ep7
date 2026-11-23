#!/usr/bin/env python3
"""owner_footer checks (emulator, offline). Minimal + anti-brick. docs/OWNER_FOOTER.md.

  .venv/bin/python -I patches/owner_footer/verify.py BASE.json NEW.json [PKGDIR]

BASE = the spec without the layer (releases/v0.34a/edits.json), NEW = owner_footer.apply(BASE) (or the chain output).
The stock functions the hook calls are replaced by logging stubs in both images; the paint is run from the site
0x60d005fb to the resume point 0x60d00601 (children-paint stub at vtbl +160 sets d0/d1).
  S  static: every byte NEW changes vs BASE is inside an owner_footer edit; owner_footer.apply(BASE) == NEW (edits).
  E  empty owner block (the release image), menu page open: registers, stack, gc, painter, window == BASE.
  C  valid dummy owner block, menu page closed (alive word 0): == BASE.
  D  valid dummy owner block, menu page open, 2 dirty rects on layer 2: layer 2 selected then the old layer put back,
     style 1 selected, gc+0x34 = 2 while drawing, one text draw per rect with clip = that rect, our text / style / rect,
     the font released, gc clip / font / mode as found, d0..a3 / sp == BASE.
  P  package: decode == stock + edits, restore == stock; a personalised package (caduceus.py owner_patch) differs from
     the empty one only inside the owner block, and caduceus.py's empty-owner path gives the empty package.
"""
import hashlib, json, struct, sys, importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'external/oly_fw_analysis/tools'))
import build_package as BP  # noqa: E402
import oly_container as oc  # noqa: E402
from penf_emulator import Region, execute  # noqa: E402


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


OF = _load('ep7_of_build_v', ROOT / 'patches/owner_footer/build.py')
CAD = _load('ep7_caduceus_v', ROOT / 'caduceus.py')
B3, BASE = OF.B3, OF.BASE
STOCK = OF.STOCK.read_bytes()
DUMMY = OF.owner_line('A. Owner', '+61 400 000 000')
REC = 0x13000000
STK, SP0 = 0x18010000, 0x18011800
WIN, VT, PNT, GC, FST = 0x17000000, 0x17001000, 0x16000000, 0x16001000, 0x15000000
REGS = dict(d0=0xd0d0, d1=0xd1d1, d2=0x2222, d3=WIN, a0=WIN, a1=PNT, a2=VT, a3=0xa3a3, mdr=0x6d6d6d6d)

STUBS = {
    0x60d061ec: """ mov 0x13000000,a2      /* setlayer: REC+0 count, REC+0x10.. layer values */
 movbu (a2),d2
 mov d2,d1
 asl2 d1
 mov a2,a3
 add 16,a3
 add d1,a3
 mov d0,(a3)
 inc d2
 movbu d2,(a2)
 movhu d0,(4,a0)
 mov (8,a0),a3
 mov 0x5eeee,d1
 mov d1,(4,a3)              /* clobber the gc clip like a real layer switch might */
 ret [d2,a2,a3],20
""",
    0x60d0fce0: """ mov 0x13000040,a1      /* setfont: +0 style id, +4 calls */
 mov d0,(a1)
 mov (4,a1),d0
 inc d0
 mov d0,(4,a1)
 mov 0x16200000,d0
 mov d0,(76,a0)
 mov d0,a0
 ret [a2],8
""",
    0x60d0618c: """ mov (8,a0),a0          /* clip: gc+4 = the rect pointer (so the draw stub can log it) */
 mov a1,(4,a0)
 ret [],4
""",
    0x60d075a7: """ mov 0x13000020,a2      /* drawtext: +0 count; entries 16 B at REC+0x80: style, text, rect, clip, mode */
 movbu (a2),d2
 mov d2,d3
 asl 4,d3
 mov a2,a3
 add 0x60,a3
 add d3,a3
 mov d0,(a3)
 mov d1,(4,a3)
 mov a1,(8,a3)
 mov (4,a0),d0
 mov d0,(12,a3)
 inc d2
 movbu d2,(a2)
 movhu (52,a0),d0
 mov 0x13000024,a2
 movhu d0,(a2)
 ret [d2,d3,a2,a3],252
""",
    0x60d10708: """ mov 0x13000030,a1      /* frel: +0 font, +4 calls */
 mov a0,(a1)
 mov (4,a1),d0
 inc d0
 mov d0,(4,a1)
 ret [],4
""",
}
HDR = ' .am33_2\n .text\n .global _start\n_start:\n'
CHILDREN = HDR + ' mov 0x1234,d0\n mov 0x5678,d1\n retf [],0\n'      # vtbl +160 (calls target)
MULTI = HDR + ' mov 1,d0\n retf [],0\n'                                # window vtbl +680


def asm(src, at):
    return B3.assemble(src, at, {})[0]


def with_stubs(im, block=None, spec=None):
    b = bytearray(im)
    for at, s in STUBS.items():
        c = asm(HDR + s, at)
        b[at - BASE:at - BASE + len(c)] = c
    if block is not None:
        a = int(spec['owner_footer']['block'], 16)
        b[a - BASE:a - BASE + len(block)] = block
    return bytes(b)


def regions(im, alive, nrect=2):
    stk = bytearray([0xa5] * 0x2000); struct.pack_into('<I', stk, SP0 - STK + 4, PNT)   # paint's (4,sp) = painter
    vt = bytearray(0x300); struct.pack_into('<I', vt, 160, FST); struct.pack_into('<I', vt, 680, FST + 0x40)
    pnt = bytearray(0x40); struct.pack_into('<HHI', pnt, 4, 3, 0, GC); struct.pack_into('<H', pnt, 20, 3)
    gc = bytearray(0x100); struct.pack_into('<II', gc, 4, 0x00110022, 0x00330044)
    struct.pack_into('<I', gc, 76, 0x16100000); struct.pack_into('<H', gc, 52, 0x7777)
    win = bytearray(0x600); struct.pack_into('<I', win, 0, VT)
    for i in range(nrect):
        struct.pack_into('<4h', win, 1464 + 8 * i, 0, 400 + 20 * i, 719, 479)
    struct.pack_into('<I', win, 1464 + 24, nrect)
    fst = bytearray(0x80); c = asm(CHILDREN, FST); fst[:len(c)] = c; c = asm(MULTI, FST + 0x40); fst[0x40:0x40 + len(c)] = c
    return [Region('img', BASE, im, 'rx'), Region('stack', STK, bytes(stk), 'rw', True),
            Region('rec', REC, bytes(0x200), 'rw', True), Region('pnt', PNT, bytes(pnt), 'rw', True),
            Region('gc', GC, bytes(gc), 'rw', True), Region('win', WIN, bytes(win), 'rw', True),
            Region('vt', VT, bytes(vt), 'r'), Region('fst', FST, bytes(fst), 'rx'),
            Region('alive', OF.ALIVE, struct.pack('<I', alive), 'r'),
            Region('curwin', OF.CURWIN, struct.pack('<I', WIN), 'r')]


def paint(im, alive=1):
    r = execute(regions(im, alive), dict(REGS, pc=OF.SITE, sp=SP0), OF.BACK, limit=200000, timeout=60)
    return r, {m['name']: bytes.fromhex(m['hex']) for m in r['memory']}


KS = ('d0', 'd1', 'd2', 'd3', 'a2', 'a3', 'sp', 'pc')


def same(a, b, mems=('gc', 'pnt', 'win', 'rec')):
    (r0, m0), (r1, m1) = a, b
    g0, g1 = r0['registers'], r1['registers']
    sp = g1['sp'] - STK + 4        # the live stack: below sp is scratch, (0,sp) is the call slot `calls` writes
    return (not r0['fault'] and not r1['fault'] and all(g0[k] == g1[k] for k in KS)
            and all(m0[k] == m1[k] for k in mems) and m0['stack'][sp:] == m1['stack'][sp:], {k: (hex(g0[k]), hex(g1[k])) for k in KS if g0[k] != g1[k]})


def img(spec):
    return bytes(OF.ST.img_of(spec, STOCK))


def main():
    a = sys.argv[1:]
    base_s, new_s = (json.loads(Path(p).read_text()) for p in a[:2])
    disk = Path(a[2]) if len(a) > 2 else None
    base, new = img(base_s), img(new_s)
    ok = True

    def rep(tag, good, txt):
        nonlocal ok
        print(f"{'PASS' if good else 'FAIL'} {tag} {txt}", flush=True)
        ok &= good

    # S
    mine = [e for e in new_s['edits'] if e.get('source') == OF.SRC]
    spans = [(int(e['addr'], 16), int(e['addr'], 16) + len(e['new']) // 2) for e in mine]
    diff = [i + BASE for i in range(len(base)) if base[i] != new[i]]
    re_s = OF.apply(base_s, new_s['owner_footer']['version'])
    good = all(any(x <= d < y for x, y in spans) for d in diff) and \
        [e for e in re_s['edits'] if e.get('source') == OF.SRC] == mine and len(mine) == 2
    rep('S', good, f'{len(diff)} B differ, all inside the 2 owner_footer edits; rebuild == NEW')

    blk = OF.owner_block(DUMMY)
    bb, nb, nd = with_stubs(base), with_stubs(new), with_stubs(new, blk, new_s)
    b1 = paint(bb, 1)
    g, d = same(b1, paint(nb, 1))
    rep('E', g, f'empty owner block, menu open == BASE {d}')
    g, d = same(paint(bb, 0), paint(nd, 0))
    rep('C', g, f'dummy owner block, menu closed == BASE {d}')

    r, m = paint(nd, 1)
    rec, gr = m['rec'], r['registers']
    sy = {k: int(v, 16) for k, v in new_s['owner_footer']['symbols'].items()}
    layers = [struct.unpack_from('<I', rec, 0x10 + 4 * i)[0] & 0xffff for i in range(rec[0])]
    sid, nsel = struct.unpack_from('<2I', rec, 0x40)
    font, nrel = struct.unpack_from('<2I', rec, 0x30)
    draws = [struct.unpack_from('<4I', rec, 0x80 + 16 * i) for i in range(rec[0x20])]
    text = nd[sy['of_text'] - BASE:sy['of_text'] - BASE + 2 * len(DUMMY)].decode('utf-16-le')
    rects = [WIN + 1464, WIN + 1472]
    good = (not r['fault'] and gr['pc'] == OF.BACK and layers == [2, 3] and (sid, nsel) == (1, 1)
            and (font, nrel) == (0x16200000, 1) and len(draws) == 2
            and all(x[:3] == (sy['of_style'], sy['of_text'], sy['of_rect']) for x in draws)
            and [x[3] for x in draws] == rects and struct.unpack_from('<H', rec, 0x24)[0] == 2
            and m['gc'] == regions(nd, 1)[4].data and text == DUMMY
            and struct.unpack_from('<H', m['pnt'], 4)[0] == 3
            and gr['d0'] == 0x1234 and gr['d1'] == 0x5678
            and all(gr[k] == b1[0]['registers'][k] for k in ('d2', 'd3', 'a2', 'a3', 'sp'))
            and m['stack'][gr['sp'] - STK + 4:] == b1[1]['stack'][gr['sp'] - STK + 4:])
    st = nd[sy['of_style'] - BASE:sy['of_style'] - BASE + 24]
    rc = struct.unpack_from('<4h', nd, sy['of_rect'] - BASE)
    rep('D', good, f'draw: layers {layers}, style id {sid}, {len(draws)} text draws (clips {[hex(x[3]) for x in draws]}), '
                   f'text {text!r}, style {st.hex()}, rect {rc}, font released {nrel}x, gc/painter as found, '
                   f'fault {r["fault"]}')

    # P
    stock_pkg = BP.STOCK.read_bytes()
    pkg, rst, info = BP.build(new_s, stock_pkg)
    sb = {b.kind: b for b in oc.parse(stock_pkg)}
    good = True
    for b in oc.parse(pkg):
        exp = bytearray(sb[b.kind].payload)
        for e in new_s['edits']:
            if int(e['kind'], 16) == b.kind:
                o = BP.resolve(b.kind, e['addr']); n_ = bytes.fromhex(e['new']); exp[o:o + len(n_)] = n_
        good &= bytes(exp) == b.payload
    good &= {b.kind: b for b in oc.parse(pkg)}[0x100].payload == new
    good &= all(b.payload == sb[b.kind].payload for b in oc.parse(rst))
    pers, _ = CAD.apply_edits(CAD.owner_spec(new_s, DUMMY), stock_pkg)
    emp, _ = CAD.apply_edits(CAD.owner_spec(new_s, ''), stock_pkg)
    pm, em = ({b.kind: b for b in oc.parse(x)}[0x100].payload for x in (pers, emp))
    blo = int(new_s['owner_footer']['block'], 16) - BASE
    dd = [i for i in range(len(pm)) if pm[i] != em[i]]
    good &= emp == pkg and dd and blo <= dd[0] and dd[-1] < blo + len(blk) and pm[blo:blo + len(blk)] == blk
    good &= CAD.owner_unpatch(pers, new_s) == pkg
    txt = (f'decode == stock + {info["edits"]} edits == emulated image, restore == stock; personalised main differs from '
           f'the empty one in {len(dd)} B, all inside the owner block; owner_unpatch(personalised) == empty package')
    if disk:
        good &= (disk / 'patched.pkg.bin').read_bytes() == pkg and (disk / 'restore-stock.pkg.bin').read_bytes() == rst
        txt += f'; {disk} matches (sha256 {hashlib.sha256(pkg).hexdigest()[:16]})'
    rep('P', good, txt)
    print('ALL PASS' if ok else 'FAILURES')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
