#!/usr/bin/env python3
"""mdial checks (emulator, offline). Minimal + anti-brick. Port of phocean/omsystem-ep7 dial_iso + dial_expcomp (Apache-2.0);
their verify.py runs the real dial routine (E1/E2/M); this one checks the relocated stub and the package.

  .venv/bin/python -I patches/mdial/verify.py BASE.json NEW.json [PKGDIR]

BASE = the spec without the layer, NEW = mdial.apply(BASE) (or the chain output).
  S  every byte NEW changes vs BASE is inside an mdial edit; mdial.apply(BASE) == NEW (edits); the stub equals phocean's
     76 B except for the call / jmp displacements.
  E  hook site 0x60cdc837 -> resume 0x60cdc840 with the getter (sid 109 / 24), the lens predicate 0x602ea74c and the rule
     0x60cc8be9 stubbed: NEW(fn) == BASE(fn') in d0..a3, sp and the live stack, with fn' = 6 for (fn 3, M, no contact lens),
     3 for (fn 2, M, contact lens), else fn. Cases: fn {2, 3, 4} x mode {M via sid 109, M via sid 24, A} x lens {0, 1}.
  P  package: decode == stock + edits == image, restore == stock.
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


MD = _load('ep7_md_build_v', ROOT / 'patches/mdial/build.py')
B3, BASE = MD.B3, MD.BASE
STOCK = MD.STOCK.read_bytes()
# phocean's stub as published (patches/dial_iso/edits.json, at 0x60210900) and its four displacement fields
PHOCEAN = bytes.fromhex('f1e3a003c806a002c938806ddde7f0ab00a018a000c90b8018dddaf0ab00a018a006c91cdd289e0d00801c1ca000c90abf03'
                        'c90c9f06ca08bf02c9049f03f1dcdda982ab00c008dcf9beac00')
REC = 0x13000000
STK, SP0 = 0x18010000, 0x18011800
HDR = ' .am33_2\n .text\n .global _start\n_start:\n'
STUBS = {
    MD.GETSID: """ cmp 109,d0                 /* getsid: sid 109 -> REC+0, else REC+4 */
 bne 1f
 mov (0x13000000),d0
 bra 2f
1:
 mov (0x13000004),d0
2:
 mov 0x1d1d,d1
 ret [d2,a2],24
""",
    MD.LENS: """ mov (0x13000008),d0       /* lens predicate: REC+8 */
 mov 0x1d1d,d1
 ret [d2],28
""",
    MD.RULE: """ mov 0x13000010,a0          /* rule: REC+0x10 = d0, +0x14 calls */
 mov d0,(a0)
 mov (4,a0),d1
 inc d1
 mov d1,(4,a0)
 mov a3,(8,a0)
 mov 0x77,d0
 ret [d2,d3],8
""",
}


def with_stubs(im):
    b = bytearray(im)
    for at, s in STUBS.items():
        c = B3.assemble(HDR + s, at, {})[0]
        b[at - BASE:at - BASE + len(c)] = c
    return bytes(b)


def run(im, fn, s109, s24, lens):
    rec = struct.pack('<3I', s109, s24, lens) + bytes(0x40)
    rg = [Region('img', BASE, im, 'rx'), Region('rec', REC, rec, 'rw', True),
          Region('stack', STK, bytes([0xa5] * 0x2000), 'rw', True)]
    regs = dict(d0=fn, d1=0x1111, d2=0x2222, d3=0x3333, a0=0xa0a0, a1=0xa1a1, a2=0xa2a2, a3=0xa3a3, mdr=0x6d6d, pc=MD.HOOK, sp=SP0)
    r = execute(rg, regs, MD.RESUME, limit=20000, timeout=30)
    return r, {m['name']: bytes.fromhex(m['hex']) for m in r['memory']}


def img(spec):
    return bytes(MD.ST.img_of(spec, STOCK))


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

    mine = [e for e in new_s['edits'] if e.get('source') == MD.SRC]
    spans = [(int(e['addr'], 16), int(e['addr'], 16) + len(e['new']) // 2) for e in mine]
    diff = [i + BASE for i in range(len(base)) if base[i] != new[i]]
    re_s = MD.apply(base_s, new_s['mdial']['version'])
    at = int(new_s['mdial']['code'][0], 16)
    stub = new[at - BASE:at - BASE + 76]
    disp = {13, 14, 15, 16, 26, 27, 28, 29, 37, 38, 39, 40, 65, 66, 67, 68, 72, 73, 74, 75}
    good = (all(any(x <= d < y for x, y in spans) for d in diff) and len(mine) == 6
            and [e for e in re_s['edits'] if e.get('source') == MD.SRC] == mine
            and all(stub[i] == PHOCEAN[i] for i in range(76) if i not in disp))
    rep('S', good, f'{len(diff)} B differ, all inside the 6 mdial edits; rebuild == NEW; stub == phocean\'s but the displacements')

    bb, nb = with_stubs(base), with_stubs(new)
    bad, n, seen = [], 0, []
    for fn in (2, 3, 4):
        for mode, (s109, s24) in (('M109', (6, 0)), ('M24', (0, 6)), ('A', (5, 0))):
            for lens in (0, 1):
                m_ = mode.startswith('M')
                want = 6 if (fn == 3 and m_ and not lens) else 3 if (fn == 2 and m_ and lens) else fn
                r0, m0 = run(bb, want, s109, s24, lens)
                r1, m1 = run(nb, fn, s109, s24, lens)
                g0, g1 = r0['registers'], r1['registers']
                ks = ('d0', 'd2', 'd3', 'a2', 'a3', 'sp', 'pc')
                sp = g1['sp'] - STK + 4
                good = (not r0['fault'] and not r1['fault'] and all(g0[k] == g1[k] for k in ks)
                        and m0['stack'][sp:] == m1['stack'][sp:] and m1['rec'][0x10:0x1c] == m0['rec'][0x10:0x1c]
                        and struct.unpack_from('<I', m1['rec'], 0x10)[0] == want and g1['a3'] == want)
                n += 1
                if want != fn:
                    seen.append(f'fn{fn} {mode} lens{lens} -> {want}')
                if not good:
                    bad.append((fn, mode, lens, r1['fault'], {k: (hex(g0[k]), hex(g1[k])) for k in ks if g0[k] != g1[k]}))
    rep('E', not bad, f'{n} cases == BASE(fn\'); remapped: {seen}; bad {bad[:2]}')

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
    txt = f'decode == stock + {info["edits"]} edits == image, restore == stock'
    if disk:
        good &= (disk / 'patched.pkg.bin').read_bytes() == pkg and (disk / 'restore-stock.pkg.bin').read_bytes() == rst
        txt += f'; {disk} matches (sha256 {hashlib.sha256(pkg).hexdigest()[:16]})'
    rep('P', good, txt)
    print('ALL PASS' if ok else 'FAILURES')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
