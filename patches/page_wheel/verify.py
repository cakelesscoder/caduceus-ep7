#!/usr/bin/env python3
"""page_wheel checks (#52; emulator, real code on the whole built image). Offline. Minimal + anti-brick.

  .venv/bin/python -I patches/page_wheel/verify.py <base spec (the chain without page_wheel)> <spec> [package dir]

  H  pw_h itself (entered through handler word 137): stock handler stubbed (rc 0 or 0x104), a mock page screen / kind-52
     actuator / row column, the real facade chain for 111 (stock GetValue stubbed). Key / dial event + row 1 + COLOR 54..56 / 64
     -> rc 0x407 and the wheel key in 0x61fc4370; every other case (rows 0 / 2 / 3, MONO 57 / 65, Vivid, stock rc 0x104,
     events 0xf802 / 0x9b01, no screen, another actuator class) -> the stock rc, key word untouched. d2 d3 a2 a3 sp kept.
  E  shortcut route end to end through the real HSM dispatcher 0x60d11448 (SsMenuLv ctx ss 4 / state 29, +4 the ss table 0x611317c4, Down 0x9006 with
     the page on row 1, COLOR2): pw_h -> state 29's exit (stub, recorded) -> ctx state 7 -> state 7's entry (stub, records the
     key word it reads) = 0x13b4. Row 0: state stays 29, no exit, no entry.
  S  SCP regression through the same dispatcher: ctx state 3, OK 0x900c -> the stock SCP OK handler 0x60e56a7f (stub,
     recorded), state 3 kept; state 29's word is the only handler word that differs from the base.
  P  anti-brick: package = stock + edits, restore == stock, every main byte differing from the base is in this layer's two
     edits, the fw_version string or crash_log's version tag.
"""
import importlib.util, json, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'external/oly_fw_analysis/tools'))
import build_package as BP  # noqa: E402
import oly_container as oc  # noqa: E402


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(s)
    sys.modules[name] = m; s.loader.exec_module(m); return m


V = _load('ep7_v026_movie_verify_pw', ROOT / 'patches/v026_movie/verify.py')
PW = _load('ep7_page_wheel_build_v', ROOT / 'patches/page_wheel/build.py')
Region, execute = V.Region, V.execute
BASE = 0x60020020
asm = lambda t, at: V.SB3.assemble(' .am33_2\n .text\n .global _start\n_start:\n' + t + '\n', at, {})[0]
OBJ, MOCK, REC, CTX, CALLER, SP0 = 0x1d000000, 0x1c000000, 0x1f000000, 0x1e000000, 0x18040000, 0x18010800
SCR, ACT, COL, CVT = MOCK, MOCK + 0x100, MOCK + 0x200, MOCK + 0x300
ROWFN, GETV, FACADE = MOCK + 0x400, 0x607f9549, PW.FACADE
EXIT29, ENTRY7, SCP_OK = 0x60e5db01, 0x60e590bd, 0x60e56a7f
KW = PW.KEY_W


def image(spec, stock_rc):
    m = bytearray(V.image(spec))
    put = lambda a, c: m.__setitem__(slice(a - BASE, a - BASE + len(c)), c)
    put(PW.STOCK_H, asm(f' mov {stock_rc:#x},d0\n rets', PW.STOCK_H))
    put(FACADE, asm(f' mov {OBJ:#x},a0\n ret [],4', FACADE))
    put(EXIT29, asm(f' mov {REC:#x},a0\n mov 0x29,d0\n movbu d0,(a0)\n rets', EXIT29))
    put(ENTRY7, asm(f' mov {KW:#x},a0\n movhu (a0),d0\n mov {REC + 4:#x},a0\n movhu d0,(a0)\n rets', ENTRY7))
    put(SCP_OK, asm(f' mov {REC + 8:#x},a0\n mov 3,d0\n movbu d0,(a0)\n clr d0\n rets', SCP_OK))
    return m


def regions(im, pm, row, vt=PW.PAGE_VT, scr=True, ctx=None):
    im = bytearray(im)
    g = asm(f' cmp 111,d0\n bne 1f\n mov {pm},d1\n mov d1,(a1)\n clr d0\n rets\n1:\n clr d1\n mov d1,(a1)\n clr d0\n rets', GETV)
    im[GETV - BASE:GETV - BASE + len(g)] = g
    mock = bytearray(0x500)
    struct.pack_into('<I', mock, ACT - MOCK, vt); struct.pack_into('<I', mock, ACT - MOCK + 76, COL)
    struct.pack_into('<I', mock, 0, ACT)
    struct.pack_into('<I', mock, COL - MOCK, CVT); struct.pack_into('<I', mock, CVT - MOCK + 4, ROWFN)
    r = asm(f' mov {row},d0\n rets', ROWFN); mock[ROWFN - MOCK:ROWFN - MOCK + len(r)] = r
    data = bytearray(0x100)                                   # 0x61fc4300..: page screen word +0x6c, key word +0x70
    struct.pack_into('<I', data, PW.PAGE_SCR - 0x61fc4300, SCR if scr else 0)
    struct.pack_into('<H', data, KW - 0x61fc4300, 0x7777)
    rg = [Region('img', BASE, bytes(im), 'rx'), Region('mock', MOCK, bytes(mock), 'rx'), Region('gdata', 0x61fc4300, bytes(data), 'rw', True),
          Region('obj', OBJ, struct.pack('<I', 0x60acb0dc), 'r'), Region('rec', REC, bytes(16), 'rw', True),
          Region('state', 0x622cbcc0, bytes(8), 'r'), Region('stack', 0x18010000, bytes(0x1000), 'rw')]
    if ctx is not None:
        rg.append(Region('ctx', CTX, bytes(ctx), 'rw', True))
    return rg


def mem(r):
    return {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}


def t_h(spec):
    bad, n = [], 0
    ims = {rc: image(spec, rc) for rc in (0, 0x104)}
    at = int(spec['page_wheel']['code'][0], 16)
    cases = [(ev, row, pm, rc, vt, scr) for ev in (0x9006, 0x9007, 0x9031, 0xf802, 0x9b01) for row in (0, 1, 2, 3)
             for pm in (54, 55, 56, 64, 57, 65, 0) for rc in (0, 0x104) for vt, scr in ((PW.PAGE_VT, True), (0x61155a7c, True), (PW.PAGE_VT, False))
             if not (vt != PW.PAGE_VT and (row != 1 or pm != 55)) and not (not scr and (row != 1 or pm != 55))]
    c = asm(f' mov {at:#x},a2\n calls (a2)\n nop\n nop', CALLER)
    for ev, row, pm, rc, vt, scr in cases:
        rg = regions(ims[rc], pm, row, vt, scr) + [Region('caller', CALLER, c + b'\xcb' * 8, 'rx')]
        r = execute(rg, dict(pc=CALLER, sp=SP0, d0=ev, a1=0x1234, d2=0x2222, d3=0x3333, a3=0xa3a3), CALLER + len(c) - 2, limit=50000)
        n += 1
        rr, mm = r['registers'], mem(r)
        kw = struct.unpack_from('<H', mm['gdata'], KW - 0x61fc4300)[0]
        hit = rc == 0 and 0x9000 <= ev < 0x9040 and row == 1 and pm in PW.KEYS and vt == PW.PAGE_VT and scr
        want = (0x407, PW.KEYS[pm]) if hit else (rc, 0x7777)
        if r['fault'] or (rr['d0'] & 0xffff, kw) != want or (rr['d2'], rr['d3'], rr['a3'], rr['sp']) != (0x2222, 0x3333, 0xa3a3, SP0):
            bad.append((hex(ev), row, pm, hex(rc), hex(vt), scr, r['fault'], hex(rr['d0']), hex(kw)))
    return not bad, f'{n} runs; {bad[:3]}'


def dispatch(spec, state, ev, row, pm):
    im = image(spec, 0)
    ctx = bytearray(32); ctx[0], ctx[1], ctx[2] = 4, state, 19
    struct.pack_into('<H', ctx, 8, 0xffff); struct.pack_into('<I', ctx, 4, 0x611317c4)   # +4 ss table
    c = asm(f' mov {CTX:#x},a0\n mov {0x60d11448:#x},a2\n calls (a2)\n nop\n nop', CALLER)
    rg = regions(im, pm, row, ctx=ctx) + [Region('caller', CALLER, c + b'\xcb' * 8, 'rx')]
    r = execute(rg, dict(pc=CALLER, sp=SP0, d0=ev, d1=0, a1=0), CALLER + len(c) - 2, limit=100000)
    mm = mem(r)
    return r['fault'], mm['ctx'][0], mm['ctx'][1], mm['rec'][0], struct.unpack_from('<H', mm['rec'], 4)[0], mm['rec'][8]


def t_e(spec):
    a = dispatch(spec, 29, 0x9006, 1, 55)
    b = dispatch(spec, 29, 0x9006, 0, 55)
    ok = a == (None, 4, 7, 0x29, 0x13b4, 0) and b == (None, 4, 29, 0, 0, 0)
    return ok, f'row 1 COLOR2: {a}; row 0: {b}'


def t_s(spec, base_spec):
    a = dispatch(spec, 3, 0x900c, 1, 55)
    im, bi = V.image(spec), V.image(base_spec)
    words = [i for i in range(PW.NEV + 30) if i < 138 and im[PW.HWORDS - BASE + 4 * i:PW.HWORDS - BASE + 4 * i + 4] != bi[PW.HWORDS - BASE + 4 * i:PW.HWORDS - BASE + 4 * i + 4]]
    mat = im[PW.MATRIX - BASE:PW.MATRIX - BASE + PW.NEV * PW.NST] == bi[PW.MATRIX - BASE:PW.MATRIX - BASE + PW.NEV * PW.NST]
    ok = a == (None, 4, 3, 0, 0, 3) and words == [137] and mat
    return ok, f'SCP OK: {a}; handler words changed {words}; matrix same {mat}'


def t_p(spec, base_spec, disk):
    stock = BP.STOCK.read_bytes()
    pkg, rst, info = BP.build(spec, stock)
    sb = {b.kind: b for b in oc.parse(stock)}
    good = True
    for b in oc.parse(pkg):
        exp = bytearray(sb[b.kind].payload)
        for e in spec['edits']:
            if int(e['kind'], 16) == b.kind:
                o = BP.resolve(b.kind, e['addr']); nb = bytes.fromhex(e['new']); exp[o:o + len(nb)] = nb
        good &= bytes(exp) == b.payload
    for b in oc.parse(rst):
        good &= b.payload == sb[b.kind].payload
    new = [b for b in oc.parse(pkg) if b.kind == 0x100][0].payload
    old = V.image(base_spec)
    pw, fw = spec['page_wheel'], spec['fw_version']
    ours = [(int(pw['code'][0], 16), pw['code'][1]), (PW.WORD, 4), (int(fw['str_at'], 16), 32), (int(fw['code_at'], 16), fw['code_len'])]
    F = _load('ep7_crash_fmt_pw', ROOT / 'tools/ep7_crash.py')
    t_old, t_new = (struct.pack('<I', F.build_tag(x['crash_log']['version'])) for x in (base_spec, spec))
    ours += [(BASE + i, 4) for i in range(len(new) - 3) if new[i:i + 4] == t_new and old[i:i + 4] == t_old]
    diff = [BASE + i for i in range(len(old)) if old[i] != new[i]]
    stray = [hex(a) for a in diff if not any(s <= a < s + k for s, k in ours)]
    good &= not stray and len(spec['edits']) == len(base_spec['edits']) + 2
    if disk:
        good &= (disk / 'patched.pkg.bin').read_bytes() == pkg and (disk / 'restore-stock.pkg.bin').read_bytes() == rst
    return good, f'{info["edits"]} edits, {info["changed_payload_bytes"]} B; {len(diff)} main B differ from base; stray {stray[:6]}'


def main():
    base_spec, spec = (json.loads(Path(p).read_text()) for p in sys.argv[1:3])
    disk = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    ok = True
    for tag, f in (('H', lambda: t_h(spec)), ('E', lambda: t_e(spec)), ('S', lambda: t_s(spec, base_spec)),
                   ('P', lambda: t_p(spec, base_spec, disk))):
        g, txt = f()
        print(f"{'PASS' if g else 'FAIL'} {tag} {txt}", flush=True)
        ok &= g
    print('ALL PASS' if ok else 'FAILURES')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
