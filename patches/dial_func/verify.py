#!/usr/bin/env python3
"""dial_func checks (emulator, offline). Minimal + anti-brick.

  .venv/bin/python -I patches/dial_func/verify.py NEW.json [PKGDIR]

BASE = NEW less the dial_func edits.
  S  every byte NEW changes vs BASE is inside a dial_func edit; dial_func.apply(BASE) == NEW (edits).
  E  the stock settings manager on the NEW / BASE image: hash build 0x602ba4cc, count 0x602b9f70, code -> element 0x602b9deb,
     element -> index 0x602b9e34, for sids 70 / 74 / 72 / 76 and every code (plus an unknown one). NEW: count 4, each code ->
     its element {rear, front} and back to the index whose alt code it is; unknown code -> element 0. BASE: count 2, stock
     codes -> the same first two elements.
  P  package: decode == stock + edits == image, restore == stock (sha 963f4dfe...2327).
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


DF = _load('ep7_df_build_v', ROOT / 'patches/dial_func/build.py')
B3, BASE = DF.JA.B3, DF.BASE
STOCK = DF.STOCK.read_bytes()
REC, TR, STK, SP0, RAM = 0x13000000, 0x13100000, 0x18010000, 0x18011800, 0x62248000
RESTORE_SHA = '963f4dfe560e29216862c96284c92225f49977fd831a2ed60fa3ebbddf6d2327'
SRC = """ .am33_2
 .text
 .global _start
_start:
 call sm_hash,[d2,a2,a3],12
 mov {sid},d0
 call sm_count,[d2],8
 mov d0,(0x13000000)
 mov {sid},d0
 mov {code},d1
 call sm_store,[d2,d3,a2],16
 mov d0,(0x13000004)
 mov d0,d1
 mov {sid},d0
 call sm_index,[d2],8
 mov d0,(0x13000008)
t_end:
 nop
"""
SYMS = dict(sm_hash=0x602ba4cc, sm_count=0x602b9f70, sm_store=0x602b9deb, sm_index=0x602b9e34)


def img(spec):
    return bytes(DF.ST.img_of(spec, STOCK))


def run(im, sid, code):
    code_b, _, sy, _ = B3.assemble(SRC.format(sid=sid, code=code), TR, SYMS)
    rg = [Region('img', BASE, im, 'rx'), Region('tr', TR, code_b + bytes(16), 'rx'),
          Region('rec', REC, bytes(0x40), 'rw', True), Region('ram', RAM, bytes(0x4000), 'rw'),
          Region('stack', STK, bytes([0xa5] * 0x2000), 'rw')]
    regs = dict(d0=0, d1=0, d2=0, d3=0, a0=0, a1=0, a2=0, a3=0, mdr=0, pc=TR, sp=SP0)
    r = execute(rg, regs, sy['t_end'], limit=2_000_000, timeout=60)
    if r['fault']:
        return None
    m = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}
    return struct.unpack_from('<3I', m['rec'], 0)


def main():
    a = sys.argv[1:]
    new_s = json.loads(Path(a[0]).read_text())
    disk = Path(a[1]) if len(a) > 1 else None
    base_s = {k: v for k, v in new_s.items() if k != 'dial_func'}
    base_s['edits'] = [e for e in new_s['edits'] if e.get('source') != DF.SRC]
    base, new = img(base_s), img(new_s)
    ok = True

    def rep(tag, good, txt):
        nonlocal ok
        print(f"{'PASS' if good else 'FAIL'} {tag} {txt}", flush=True)
        ok &= good

    mine = [e for e in new_s['edits'] if e.get('source') == DF.SRC]
    spans = [(int(e['addr'], 16), int(e['addr'], 16) + len(e['new']) // 2) for e in mine]
    diff = [i + BASE for i in range(len(base)) if base[i] != new[i]]
    re_s = DF.apply(base_s, new_s['dial_func']['version'])
    rep('S', all(any(x <= d < y for x, y in spans) for d in diff) and len(mine) == 13
        and [e for e in re_s['edits'] if e.get('source') == DF.SRC] == mine,
        f'{len(diff)} B differ, all inside the {len(mine)} dial_func edits; rebuild == NEW')

    bad, n = [], 0
    for m, (p, sid, rec, lst, alt, rear, rl, newc) in DF.MODES.items():
        info = new_s['dial_func']['modes'][m]
        codes, ea = info['codes'], int(info['elems'], 16)
        for code in codes + [99]:
            r = run(new, sid, code)
            n += 1
            i = codes.index(code) if code in codes else 0
            want = struct.unpack_from('<2I', new, ea + 64 * i - BASE)
            got = r and struct.unpack_from('<2I', new, r[1] - BASE)
            exp_pair = (tuple(struct.unpack_from('<2I', base, lst + 64 * i - BASE)) if i < 2 else (rear, (DF.ISO, DF.FEC)[i - 2]))
            if not r or r[0] != 4 or r[1] != ea + 64 * i or r[2] != i or got != want or tuple(want) != exp_pair:
                bad.append(('NEW', m, code, r, got))
        for code in DF.STOCK_CODES[m]:
            r = run(base, sid, code)
            n += 1
            i = DF.STOCK_CODES[m].index(code)
            if not r or r[0] != 2 or r[1] != lst + 64 * i or r[2] != i:
                bad.append(('BASE', m, code, r))
    rep('E', not bad, f'{n} settings-manager runs (count / code -> element / element -> index); bad {bad[:3]}')

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
    good &= all(b.payload == sb[b.kind].payload for b in oc.parse(rst)) and hashlib.sha256(rst).hexdigest() == RESTORE_SHA
    txt = f'decode == stock + {info["edits"]} edits == image, restore == stock ({RESTORE_SHA[:8]}...)'
    if disk:
        good &= (disk / 'patched.pkg.bin').read_bytes() == pkg and (disk / 'restore-stock.pkg.bin').read_bytes() == rst
        txt += f'; {disk} matches (sha256 {hashlib.sha256(pkg).hexdigest()[:16]})'
    rep('P', good, txt)
    print('ALL PASS' if ok else 'FAILURES')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
