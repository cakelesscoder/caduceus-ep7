#!/usr/bin/env python3
"""overlay_probe checks (emulator, real code from the built package). Offline. Minimal + anti-brick.

  .venv/bin/python -I patches/overlay_probe/verify.py generated/v032/edits.json generated/v032ov/edits.json [DIR]

  OFF  flag = 0: ov_post is the stock empty +164 method. From an identical entry it leaves d2/d3/a2/a3/sp/mdr and
       the stack exactly as stock 0x60cfe263 (`retf [],0`) does, and returns to the same address. (d0/a0 are scratch
       the paint routine reloads.) Image mapped read-only: a store into it faults.
  UPD  ov_upd runs the (mocked) view body, sets the flag = 1, and returns the body's d0 with the body's frame.
  DRAW flag = 1, valid card table P, editor on the Extras page: ov_post clears the flag, calls the colour setter 4x
       (values 1,2,4,6) and the text drawer 4x (gc = the window gc, strings = the four rows, style/rect in-frame),
       restores mdr, writes only the flag/counter .bss and the gc, and returns. No store lands in the image.
  MISS flag = 1 but axis != Extras (or P invalid): no draw, flag cleared, returns clean.
  P    package decodes to the image DRAW ran, restore == stock, and every byte differing from the base build is ours.
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


OV = _load('ov_probe_v', ROOT / 'patches/overlay_probe/build.py')
SB3 = OV.SB3
BASE = 0x60020020
AT, CLAIM = OV.AT, OV.CLAIM
VIEW_W, WIN_W, VIEW_BODY = OV.VIEW_W, OV.WIN_W, OV.VIEW_BODY
DRAWTEXT, SETCOL, WIN_STOCK = OV.DRAWTEXT, OV.SETCOL, OV.WIN_STOCK
FLAG, CNT = OV.FLAG, OV.CNT
POOL, STATE, LIM, MAGIC = SB3.POOL, SB3.STATE, SB3.LIM, SB3.MAGIC
EP7E = int.from_bytes(b'EP7E', 'little')

STACK, SP0, FILL = 0x18010000, 0x18011800, 0xa5
GC = 0x16000000                                   # mock graphics context (rw)
REC = 0x13000000                                  # capture: +0 drawtext count, +0x20.. strings, +0x40 setcol count, +0x44.. colours
BSS = 0x622ab790                                  # the .bss pad (cached); flag at +2, counter at +3
BSSU = 0xa22ab790                                 # uncached alias the code uses
HANDLE = 0x41
P = POOL + HANDLE - 1
REGS = dict(d0=0xd0d0, d1=0xd1d1, d2=0x2222, d3=0x3333, a0=0xa0a0, a1=0xa1a1, a2=0xa2a2, a3=0xa3a3, mdr=0x6d6d6d6d)
KEEP = ('d2', 'd3', 'a2', 'a3', 'sp', 'mdr')


def image(spec):
    pkg, rst, info = BP.build(spec, BP.STOCK.read_bytes())
    return bytearray([b for b in oc.parse(pkg) if b.kind == 0x100][0].payload), pkg, rst, info


def asm(src, at):
    code, _, sy, _ = SB3.assemble(src, at, {})
    return code, sy


DRAW_STUB = """ .am33_2
 .text
 .global _start
_start:
 mov 0x13000000,a2          /* REC */
 movbu (a2),d2             /* count n */
 mov d1,(4,a2)             /* last string */
 mov a0,(8,a2)             /* last gc */
 mov d0,(12,a2)            /* last style */
 mov a1,(16,a2)            /* last rect */
 mov d2,d0
 asl2 d0
 mov a2,a3
 add 32,a3
 add d0,a3
 mov d1,(a3)              /* string[n] at REC+0x20+4n */
 inc d2
 movbu d2,(a2)
 retf [d2,d3,a2,a3],252
"""
SETCOL_STUB = """ .am33_2
 .text
 .global _start
_start:
 mov 0x13000040,a2         /* REC+0x40 */
 movbu (a2),d2
 mov d2,d0
 asl2 d0
 mov a2,a3
 add 4,a3
 add d0,a3
 mov d1,(a3)              /* note: colour is in d0 of the caller; we moved it - capture original below */
 ret [d2,d3,a2,a3],16
"""
# setcol is called with the colour in d0; capture it before clobbering
SETCOL_STUB = """ .am33_2
 .text
 .global _start
_start:
 mov d0,d1                /* colour */
 mov 0x13000040,a2
 movbu (a2),d2
 mov d2,d0
 asl2 d0
 mov a2,a3
 add 4,a3
 add d0,a3
 mov d1,(a3)
 inc d2
 movbu d2,(a2)
 retf [d2,d3,a2,a3],16
"""
VIEW_STUB = """ .am33_2
 .text
 .global _start
_start:
 movm [d2,d3,a2,a3],(sp)
 add -12,sp
 mov 0x1234,d0
 ret [d2,d3,a2,a3],28
"""


def regions(im, *, extra=(), flag=0):
    st = bytearray([FILL] * 0x2000)
    code = bytes(im[CLAIM[0] - BASE:CLAIM[1] - BASE])
    bss = bytearray(8); bss[2] = flag
    rg = [Region('ov', CLAIM[0], code, 'rx'),
          Region('stack', STACK, bytes(st), 'rw', True),
          Region('bss', BSSU, bytes(bss), 'rw', True),
          Region('rec', REC, bytes(0x80), 'rw', True),
          Region('gc', GC, bytes(0x2b0), 'rw', True)]
    rg.extend(extra)
    return rg


CALLER = 0x18000000


def run(target, via, regs, rg, limit=20000):
    """Enter `target` through a synthetic caller (via 'calls' for +164, 'call' for +0), stopping at the return."""
    if via == 'calls':
        src = f" .am33_2\n .text\n .global _start\n_start:\n mov {target:#x},a0\n calls (a0)\nstop:\n jmp stop\n"
    else:
        src = f" .am33_2\n .text\n .global _start\n_start:\n call {target:#x},[],0\nstop:\n jmp stop\n"
    code, sy = asm(src, CALLER)
    r = execute(rg + [Region('caller', CALLER, code, 'rx')], dict(pc=CALLER, sp=SP0, **regs), sy['stop'], limit=limit)
    return r, sy['stop']


def mem(r):
    return {m['name']: bytes.fromhex(m['hex']) for m in r['memory']}


def pget(handle=HANDLE, magic=MAGIC, axis=4):
    p = bytearray(1024)
    struct.pack_into('<I', p, 0, magic)
    struct.pack_into('<I', p, 680, EP7E)
    p[684] = axis
    return p


SY = None


def syms():
    global SY
    if SY is None:
        SY = json.loads(Path(sys.argv[2]).read_text())['overlay_probe']['symbols']
    return {k: int(v, 16) for k, v in SY.items()}


def t_off(base, new):
    """flag 0 -> ov_post returns like the stock empty +164, leaving d2/d3/a2/a3/sp and the stack as stock does."""
    s = syms()
    rg = regions(new)                                   # bss flag byte = 0
    r, stop = run(s['ov_post'], 'calls', dict(**REGS), rg, limit=3000)
    # stock reference: a bare retf [],0 at WIN_STOCK, same caller
    ref = [Region('winstock', WIN_STOCK, bytes(new[WIN_STOCK - BASE:WIN_STOCK - BASE + 8]), 'rx'),
           Region('stack', STACK, bytes([FILL] * 0x2000), 'rw', True)]
    rs, stop2 = run(WIN_STOCK, 'calls', dict(**REGS), ref, limit=50)
    g, st = r['registers'], rs['registers']
    ok = not r['fault'] and not rs['fault'] and g['pc'] == stop == st['pc'] and all(g[k] == st[k] for k in KEEP)
    ok &= mem(r)['stack'] == mem(rs)['stack']
    diff = {k: (hex(st[k]), hex(g[k])) for k in KEEP + ('pc',) if st.get(k) != g.get(k)}
    return ok, f"flag0 == stock retf; fault={r['fault']} {diff}"


def t_upd(new):
    s = syms()
    body, _ = asm(VIEW_STUB, VIEW_BODY)
    rg = regions(new, extra=[Region('vbody', VIEW_BODY, body, 'rx')])
    r, stop = run(s['ov_upd'], 'calls', dict(a0=0x61155e14, **{k: v for k, v in REGS.items() if k != 'a0'}), rg, limit=3000)
    m = mem(r); g = r['registers']
    flag = m['bss'][2]
    keep = [k for k in ('d2', 'd3', 'a2', 'a3', 'sp') if k in REGS]   # mdr is set by the caller's `calls`, not restored
    ok = not r['fault'] and g['pc'] == stop and flag == 1 and (g['d0'] & 0xffff) == 0x1234 and all(g[k] == REGS[k] for k in keep)
    return ok, f"fault={r['fault']} pc_ok={g['pc']==stop} flag={flag} d0={hex(g['d0'])}"


def draw_regions(new, axis=4, handle=HANDLE, magic=MAGIC):
    dt, _ = asm(DRAW_STUB, DRAWTEXT)
    sc, _ = asm(SETCOL_STUB, SETCOL)
    p = pget(handle, magic, axis)
    _flag = 1
    extra = [Region('drawtext', DRAWTEXT, dt, 'rx'),
             Region('setcol', SETCOL, sc, 'rx'),
             Region('state', STATE & ~1, struct.pack('<H', handle), 'r'),
             Region('pool', P, bytes(p), 'rw', True)]
    return regions(new, extra=extra, flag=1)


def t_draw(new):
    s = syms()
    rg = draw_regions(new)
    r, stop = run(s['ov_post'], 'calls', dict(a0=0xa0a0, a1=GC, d0=0xd0d0, d1=0xd1d1,
                                              d2=0x2222, d3=0x3333, a2=0xa2a2, a3=0xa3a3), rg, limit=40000)
    m = mem(r); g = r['registers']
    rec = m['rec']
    ndraw, nset = rec[0], rec[0x40]
    cols = [struct.unpack_from('<I', rec, 0x44 + 4 * i)[0] for i in range(nset)]
    strs = [struct.unpack_from('<I', rec, 0x20 + 4 * i)[0] for i in range(ndraw)]
    want_str = [s['ov_sA'], s['ov_sB'], s['ov_sC']]
    flag, cnt = m['bss'][2], m['bss'][3]
    gc_last = struct.unpack_from('<I', rec, 8)[0]
    ok = (not r['fault'] and g['pc'] == stop and ndraw == 4 and nset == 4
          and cols == [1, 2, 4, 6] and strs[:3] == want_str and gc_last == GC and flag == 0 and cnt == 1)
    return ok, f"fault={r['fault']} ndraw={ndraw} nset={nset} cols={cols} str_ok={strs[:3]==want_str} gc={hex(gc_last)} flag={flag} cnt={cnt}"


def t_miss(new):
    s = syms()
    bad = []
    for c in (dict(axis=0), dict(axis=3), dict(handle=0), dict(magic=0x11111111)):
        rg = draw_regions(new, **c)
        r, stop = run(s['ov_post'], 'calls', dict(a0=0xa0a0, a1=GC, d0=0xd0d0, d1=0xd1d1,
                                                  d2=0x2222, d3=0x3333, a2=0xa2a2, a3=0xa3a3), rg, limit=8000)
        m = mem(r)
        ok = not r['fault'] and r['registers']['pc'] == stop and m['rec'][0] == 0 and m['rec'][0x40] == 0 and m['bss'][2] == 0
        if not ok:
            bad.append((c, r['fault'], m['rec'][0], m['rec'][0x40]))
    return not bad, f'no draw on miss; {bad[:2]}'


def t_pkg(base_s, new_s, base, new, pkg, rst, info, disk):
    # overlay_probe touches only the main image (kind 0x100). Prove: the package's 0x100 payload is the image DRAW ran,
    # every kind restores to stock, and the only bytes changed vs the base build are our code + three vtable words.
    sb = {b.kind: b for b in oc.parse(BP.STOCK.read_bytes())}
    good = True
    for b in oc.parse(pkg):
        if b.kind == 0x100:
            good &= b.payload == bytes(new)
    for b in oc.parse(rst):
        good &= b.payload == sb[b.kind].payload
    x = new_s['overlay_probe']
    ours = [(AT, x['bytes']), (VIEW_W, 4)] + [(w, 4) for w in WIN_W]
    diff = [BASE + i for i in range(len(base)) if base[i] != new[i]]
    stray = [hex(a) for a in diff if not any(s <= a < s + k for s, k in ours)]
    good &= not stray and len(new_s['edits']) == len(base_s['edits']) + 4
    if disk:
        good &= (disk / 'patched.pkg.bin').read_bytes() == pkg and (disk / 'restore-stock.pkg.bin').read_bytes() == rst
    return good, f'{len(diff)} B differ from base (code + 3 words); stray {stray[:6]}; restore ok'


def main():
    base_s, new_s = (json.loads(Path(p).read_text()) for p in sys.argv[1:3])
    disk = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    base, *_ = image(base_s)
    new, pkg, rst, info = image(new_s)
    ok = True
    for tag, fn in (('OFF', lambda: t_off(base, new)), ('UPD', lambda: t_upd(new)), ('DRAW', lambda: t_draw(new)),
                    ('MISS', lambda: t_miss(new)), ('P', lambda: t_pkg(base_s, new_s, base, new, pkg, rst, info, disk))):
        g, txt = fn()
        print(f"{'PASS' if g else 'FAIL'} {tag} {txt}")
        ok &= g
    print('ALL PASS' if ok else 'FAILURES')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
