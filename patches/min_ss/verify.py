#!/usr/bin/env python3
"""Checks for min_ss m4 (real firmware code in the emulator, on the image decoded from the built package). Offline.

  .venv/bin/python -I patches/min_ss/verify.py generated/min_ss/v029a.json generated/min_ss/m4/edits.json [generated/min_ss/m4/rel]

  R  E1 page rows (native readers 0x60de2ef0 count/list and 0x60de2eb8 row by index, mode 93): patched
     [273, 112, 1147, 143, 35]; stock (RAM .data seeded from its init image) [273, 112, 143, 35]; other modes same
  K  OK router 0x60ddc1f1 (native) over the new OK tables of kinds 0x4b / 0x4c: row 1147 -> (8, 0x1aa), every stock
     entry -> its stock (group, state); picker label table: every 1147 value labelled, 0 = Auto, rest = real speeds
  B  AE record builder 0x604279c9 (patched, native, getter stubbed): sid 1147 = 0 -> +30 = 0x7eee (Auto), a speed ->
     that speed; the stock builder with 1146 = 0 gives 0x7eee too (Auto == stock)
  A  AE predicate 0x603fe925 (stock code): 0 for 0x7eee, 1 for a speed in P/A-type modes
  V  native validator (sid 1147): count/values = [0, 85 .. 3328] (40); neighbours 1140..1150 unchanged
  D  data: both D1 pages -> 8 rows (7 stock records byte-equal, then the 1147 row), label list values == validator
     values with Auto + kind-5 speed texts, items lists = stock + 1147, 4-byte alignment, block inside its claim
  L  version label;  P  anti-brick: decoded == stock + edits, restore == stock, only our sites differ from v0.29a
"""
import importlib.util, json, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import ep7_buttons_verify as V  # noqa: E402  (validator harness; puts the emulator on sys.path)
import build_package as BP  # noqa: E402
import oly_container as oc  # noqa: E402
from penf_emulator import Region, execute  # noqa: E402


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


MS = _load('min_ss_build', ROOT / 'patches/min_ss/build.py')
B = MS.BASE
STACK, SP0, REC = 0x18010000, 0x18011800, 0x19200000
PRED, PRED_END, P2, P2_END = 0x603fe925, 0x603fe960, 0x60420199, 0x604201aa
REG_RAM = 0x622a0b00


def sl(m, lo, hi):
    return m[lo - B:hi - B]


def builder(m, ret_1146, ret_1147):
    """Run 0x604279c9..0x604279f8 with the property getter stubbed by key (d0): returns record +30."""
    # stub: cmp 0x5351,d0 ; beq +n ; mov ret_1147,d0 ; ret ; mov ret_1146,d0 ; ret   ([d2,d3],12 frame)
    ret = b'\xdf\xc0\x0c'
    tail_a = b'\x2c' + struct.pack('<H', ret_1147 & 0xffff) + ret
    stub = b'\xfa\xc8' + struct.pack('<H', 0x5351) + b'\xc8' + bytes([2 + len(tail_a)]) + tail_a + \
           b'\x2c' + struct.pack('<H', ret_1146 & 0xffff) + ret
    regions = [Region('code', MS.BLD, sl(m, MS.BLD, MS.BLD_END + 3), 'rx'), Region('getter', MS.PROP, stub, 'rx'),
               Region('stack', STACK, bytes(0x2000), 'rw'), Region('rec', REC, bytes(96), 'rw', True),
               Region('regram', REG_RAM, bytes(0x100), 'rw')]
    r = execute(regions, {'pc': MS.BLD, 'sp': SP0, 'a3': REC}, MS.BLD_END + 3, limit=10_000)
    assert not r['fault'] and r['registers']['sp'] == SP0, ('builder', r['fault'])
    rec = bytes.fromhex(next(x for x in r['memory'] if x['name'] == 'rec')['hex'])
    return struct.unpack_from('<H', rec, 30)[0]


def t_builder(S, P):
    bad, n = [], 0
    for v, want in ((0, 0x7eee), (2048, 2048), (85, 85), (3328, 3328), (1024, 1024)):
        n += 1
        if builder(P, 0, v) != want or builder(P, 1, v) != want:       # 1146 no longer matters
            bad.append(('m2', v))
    n += 1
    if builder(S, 0, 2048) != 0x7eee or builder(S, 1, 2048) != 2048:   # stock semantics, for reference
        bad.append('stock')
    return bad, n


def pred(m, mode, tv):
    rec = bytearray(96); rec[2] = mode
    struct.pack_into('<H', rec, 30, tv)
    regions = [Region('pred', PRED, sl(m, PRED, PRED_END), 'rx'), Region('p2', P2, sl(m, P2, P2_END), 'rx'),
               Region('rec', REC, bytes(rec), 'rw'), Region('oth', 0x19300000, bytes(16), 'rw')]
    r, good = V.run(regions, {'a0': REC, 'a1': 0x19300000}, 0x80, 8, PRED)
    assert good, ('pred', r['fault'])
    return r['registers']['d0'] & 0xff


ROWS_CODE = (0x60de2eb8, 0x60de2f1e)
DATA_RAM = (0x61fc1d00, 0x61fc2700)


def ram_data(m):
    lo, hi = DATA_RAM
    return sl(m, lo - MS.DATA_DELTA, hi - MS.DATA_DELTA)


def rows(m, mode):
    regions = [Region('code', ROWS_CODE[0], sl(m, *ROWS_CODE), 'rx'), Region('tbl', 0x61150a00, sl(m, 0x61150a00, 0x61150c40)),
               Region('ram', DATA_RAM[0], ram_data(m), 'rw'), Region('lists', MS.AT, sl(m, MS.AT, MS.END)),
               Region('out', 0x19400000, bytes(8), 'rw', True)]
    r, good = V.run(regions, {'a0': 0x19400000, 'd0': mode}, 0xf0, 16, 0x60de2ef0)
    assert good, ('rows', r['fault'])
    n = struct.unpack_from('<H', bytes.fromhex(next(x for x in r['memory'] if x['name'] == 'out')['hex']), 0)[0]
    out = []
    for i in range(n):
        r, good = V.run(regions, {'a0': 0x19400000, 'd0': mode, 'd1': i}, 0xf0, 20, 0x60de2eb8)
        assert good, ('row', r['fault'])
        out.append(r['registers']['d0'] & 0xffff)
    return out


def t_rows(S, P):
    bad = []
    if rows(S, 93) != MS.ROWS_E1:
        bad.append(('stock', rows(S, 93)))
    if rows(P, 93) != [273, 112, MS.SID_TV, 143, 35]:
        bad.append(('patched', rows(P, 93)))
    for mode in (87, 90, 91, 92, 94, 97, 100, 101, 102, 104):
        if rows(S, mode) != rows(P, mode):
            bad.append(('mode', mode))
    return bad, 12


ROUTER, ROUTER_END, NEXT, NEXT_END, NEXT_RAM = 0x60ddc1f1, 0x60ddc305, 0x60dd5125, 0x60dd5134, 0x61fc1b00
OBJ, C1, C2, STUB = 0x19000000, 0x19000400, 0x19000500, 0x19100000


def route(m, table, n, depth, item, sub):
    obj = bytearray(0x100)
    struct.pack_into('<H', obj, 80, depth)
    struct.pack_into('<II', obj, 88, C1, C2)
    kids, code = bytearray(0x200), bytearray(0x200)
    for base, val in ((0, item), (0x100, sub)):
        vt = base + 0x40
        struct.pack_into('<I', kids, base, STUB + vt)
        struct.pack_into('<IIIII', code, vt, 0, STUB + vt + 0x20, 0, 0, STUB + vt + 0x28)
        code[vt + 0x20:vt + 0x25] = b'\x2c\0\0\xf0\xfc'
        code[vt + 0x28:vt + 0x2d] = b'\x2c' + struct.pack('<H', val) + b'\xf0\xfc'
    regions = [Region('router', ROUTER, sl(m, ROUTER, ROUTER_END), 'rx'), Region('next', NEXT, sl(m, NEXT, NEXT_END), 'rx'),
               Region('table', table, sl(m, table, table + 24 * n)), Region('obj', OBJ, bytes(obj), 'rw'),
               Region('kids', C1, bytes(kids), 'rw'), Region('stubs', STUB, bytes(code), 'rx'),
               Region('nextram', NEXT_RAM, bytes(0x100), 'rw', True)]
    r, good = V.run(regions, {'a0': OBJ, 'a1': table, 'd0': n}, 0xf0, 48, ROUTER)
    assert good, ('router', r['fault'])
    ram = bytes.fromhex(next(x for x in r['memory'] if x['name'] == 'nextram')['hex'])
    return r['registers']['d0'] & 0xffffffff, *struct.unpack_from('<HH', ram, 0xb0)


def t_router(spec, S, P):
    bad, n = [], 0
    for (ptr, cnt), new in zip(MS.OKT, [int(x, 16) for x in spec['min_ss']['layout']['ok']]):
        for j in range(cnt):
            depth, item, si, fn, grp, st = struct.unpack_from('<IHHIII', S, ptr + 24 * j - B)
            if fn:
                continue
            n += 1
            if route(S, ptr, cnt, depth, item, si) != (4, grp, st) or route(P, new, cnt + 1, depth, item, si) != (4, grp, st):
                bad.append((hex(ptr), item))
        n += 1
        if route(P, new, cnt + 1, 1, MS.SID_TV, 0) != (4, 8, MS.PICK_STATE):
            bad.append(('1147', hex(new)))
    lab = struct.unpack_from('<I', P, MS.PICK_LBL + 12 - B)[0]
    ents = {struct.unpack_from('<i', P, lab + 12 * j - B)[0]: struct.unpack_from('<HHI', P, lab + 12 * j + 4 - B) for j in range(MS.PICK_N)}
    for v in MS.values(S):
        n += 1
        k, i, t = ents.get(v, (0, 0, 0))
        if (v == 0 and (k, i) != (4, MS.STR_AUTO)) or (v and not (k == 5 and MS.text(P, t).startswith('1/'))):
            bad.append(('label', v, k, i))
    return bad, n


def t_pred(P):
    bad, n = [], 0
    for mode in (3, 4, 36, 37):
        for tv, want in ((0x7eee, 0), (2048, 1)):
            n += 1
            if pred(P, mode, tv) != want:
                bad.append((mode, tv))
    return bad, n


def t_validator(S, P):
    bad = []
    n, vals = P.listed(MS.SID_TV)
    want = MS.values(S.m)
    if n != 40 or vals[:40] != [v & 0xffff for v in want]:
        bad.append(('1147', n, vals[:4], vals[-3:]))
    for sid in list(range(1140, 1151)) + [174, 112, 239]:
        if sid != MS.SID_TV and S.listed(sid) != P.listed(sid):
            bad.append(('changed', sid))
    return bad, 15


def t_data(spec, S, P):
    bad, n = [], 0
    lay = spec['min_ss']['layout']
    lst = int(lay['list'], 16)
    vals = MS.values(S)
    for i, v in enumerate(vals):
        n += 1
        val, kind, sid, ptr = struct.unpack_from('<IHHI', P, lst + 12 * i - B)
        ok = val == v and ((kind, sid) == (4, MS.STR_AUTO) if v == 0 else kind == 5 and MS.text(P, ptr).startswith('1/'))
        if not ok:
            bad.append(('label', v))
    for (page, rec, cond), rows in zip(MS.PAGES, [int(x, 16) for x in lay['rows']]):
        n += 1
        if struct.unpack_from('<IHH', P, page + 8 - B)[0] != rows or struct.unpack_from('<H', P, page + 18 - B)[0] != 8:
            bad.append(('page', hex(page)))
        if sl(P, rows, rows + 7 * 36) != sl(S, rec, rec + 7 * 36):
            bad.append(('rows', hex(page)))
        r = struct.unpack_from('<HHIHHIHHIIII', P, rows + 7 * 36 - B)
        if r != (MS.SID_TV, 40, 40, 4, MS.STR_LABEL, cond, 4, MS.STR_HELP, cond, lst, 0, lst):
            bad.append(('new row', hex(page), r))
    oks = [int(x, 16) for x in lay['ok']]
    for k in MS.KINDS:
        n += 1
        if struct.unpack_from('<IIIIII', P, k + 12 - B) != (MS.ITEMS, MS.ITEMS_N, oks[0], 9, oks[1], 8):
            bad.append(('kind', hex(k)))
    for (ptr, cnt), new in zip(MS.OKT, oks):
        if sl(P, new, new + 24 * cnt) != sl(S, ptr, ptr + 24 * cnt) or \
                struct.unpack_from('<IHHIIII', P, new + 24 * cnt - B) != (1, MS.SID_TV, 0, 0, 8, MS.PICK_STATE, 0):
            bad.append(('ok table', hex(new)))
    al = [lst, int(lay['e1'], 16)] + oks + [int(x, 16) for x in lay['rows']]
    if any(a % 4 for a in al) or int(spec['min_ss']['data_end'], 16) > MS.END:
        bad.append(('align/claim', [hex(a) for a in al]))
    return bad, n + 1


def image(spec):
    pkg, rst, info = BP.build(spec, BP.STOCK.read_bytes())
    return [b for b in oc.parse(pkg) if b.kind == 0x100][0].payload, pkg, rst, info


def t_label(spec, new):
    fv = spec['fw_version']
    want = ''.join(f'{ord(c):02x}00' for c in fv['value']) + '0000'
    at = int(fv['code_at'], 16)
    return ([] if fv['value'] == spec['min_ss']['version'] and want in sl(new, at, at + fv['code_len']).hex() else ['label']), 1


def t_pkg(spec, new, pkg, rst, info, disk, old):
    sb = {b.kind: b for b in oc.parse(BP.STOCK.read_bytes())}
    good = True
    for b in oc.parse(pkg):
        exp = bytearray(sb[b.kind].payload)
        for e in spec['edits']:
            if int(e['kind'], 16) == b.kind:
                o = BP.resolve(b.kind, e['addr']); nb = bytes.fromhex(e['new']); exp[o:o + len(nb)] = nb
        good &= bytes(exp) == b.payload
    for b in oc.parse(rst):
        good &= b.payload == sb[b.kind].payload
    ours = [(int(e['addr'], 16), len(e['new']) // 2) for e in spec['edits'] if e.get('source') in (MS.SRC, 'patches/fw_version')]
    diff = [B + i for i in range(len(old)) if old[i] != new[i]]
    stray = [hex(a) for a in diff if not any(s <= a < s + k for s, k in ours)]
    good &= not stray
    if disk:
        good &= (disk / 'patched.pkg.bin').read_bytes() == pkg and (disk / 'restore-stock.pkg.bin').read_bytes() == rst
    return good, f'{info["edits"]} edits, {info["changed_payload_bytes"]} B; {len(diff)} B differ from v0.29a; stray {stray[:6]}'


def main():
    base_s, new_s = (json.loads(Path(p).read_text()) for p in sys.argv[1:3])
    disk = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    old, *_ = image(base_s)
    new, pkg, rst, info = image(new_s)
    stock = [b for b in oc.parse(rst) if b.kind == 0x100][0].payload
    SI, PI = V.Img(stock), V.Img(new)
    ok = True
    for name, fn in (('R rows', lambda: t_rows(stock, new)), ('K router', lambda: t_router(new_s, stock, new)), ('B builder', lambda: t_builder(stock, new)), ('A predicate', lambda: t_pred(new)),
                     ('V validator', lambda: t_validator(SI, PI)), ('D data', lambda: t_data(new_s, stock, new)),
                     ('L label', lambda: t_label(new_s, new))):
        bad, n = fn(); ok &= not bad
        print(f"{'PASS' if not bad else 'FAIL'} {name}: {n - len(bad)}/{n}", bad[:4] if bad else '', flush=True)
    good, txt = t_pkg(new_s, new, pkg, rst, info, disk, old); ok &= good
    print(f"{'PASS' if good else 'FAIL'} P anti-brick: {txt}")
    print('ALL PASS' if ok else 'FAILURES')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
