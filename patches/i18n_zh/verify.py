#!/usr/bin/env python3
"""i18n_zh checks (emulator, real code from the built package). Offline. Minimal + anti-brick.

  .venv/bin/python -I patches/i18n_zh/verify.py <v0.32 spec> <v0.32 + i18n_zh spec>

  Z  caller stub -> calls the guide word 0x6025aa98 (from the package) -> i18n_gd -> a mock at the old chain's address
     (writes a kind-5/4 label with the case's text, d0 = 0x1234) -> back. Chinese string table loaded: the label text is
     the host model's translation (build.translate), zero-padded to 33 units; Film page (axis 3): whole entries only.
     English table / kind 4 / no table pointer: the label is exactly what the mock wrote. Every case: d0 = the mock's,
     d2 d3 a2 a3 sp kept, no fault, the stack above the caller's sp untouched.
  P  anti-brick: package decodes to stock + edits (the image Z ran), restore == stock, bytes differing from the base
     spec are only the claim's code and the guide word.
"""
import json, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'external/oly_fw_analysis/tools'))
import build_package as BP  # noqa: E402
import oly_container as oc  # noqa: E402
import importlib.util  # noqa: E402


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


W = _load('ep7_wb_v_zh', ROOT / 'tools/ep7_verify_wb.py')
ZB = _load('ep7_zh_build_v', ROOT / 'patches/i18n_zh/build.py')
SB3 = ZB.B3
Region, execute = W.Region, W.execute
BASE, GD_WORD = 0x60020020, 0x6025aa98
POOL, HANDLE = 0xa1f8d800, 0x41
P = POOL + HANDLE - 1
VIEW, STUB, STRS = 0x13000000, 0x13200000, 0x13300000
REGS0 = dict(d1=0xd1d1, d2=0x2222, d3=0x3333, a1=0xa1a1, a2=0xa2a2, mdr=0x6d6d)
KEEP = ('d2', 'd3', 'a2', 'a3', 'sp')


def image(spec):
    pkg, rst, info = BP.build(spec, BP.STOCK.read_bytes())
    return [b for b in oc.parse(pkg) if b.kind == 0x100][0].payload, pkg, rst, info


def mock(at, kind, text):
    u = list(text.encode('utf-16-le')) + [0, 0]
    src = [' .am33_2', ' .text', ' .global _start', '_start:', f' mov {kind},d0', ' movhu d0,(44,a0)']
    for i in range(0, len(u), 2):
        src += [f' mov {u[i] | u[i + 1] << 8},d0', f' movhu d0,({52 + i},a0)']
    src += [' mov 0x1234,d0', ' mov 0xdead1111,d1', ' mov 0xdead2222,a1', ' rets']
    return SB3.assemble('\n'.join(src) + '\n', at, {})[0]


def stub(word):
    src = f""" .am33_2
 .text
 .global _start
_start:
 mov {VIEW:#x},a0
 mov ({word:#x}),a1
 calls (a1)
 nop
"""
    code = SB3.assemble(src, STUB, {})[0]
    return code, STUB + len(code) - 1


def strings(lang):
    """Fake string memory: (bank 0) table pointer at 0x61fc1530 -> table; string 134."""
    t = bytearray(0x1000)
    s134 = {'zh': '固件', 'en': 'Firmware'}[lang].encode('utf-16-le') + b'\0\0'
    struct.pack_into('<I', t, 536, STRS + 0x800)
    t[0x800:0x800 + len(s134)] = s134
    return bytes(t)


def run(im, text, kind=5, lang='zh', axis=4, table=True):
    sl = lambda lo, hi: im[lo - BASE:hi - BASE]
    zh = json.loads(Path(sys.argv[2]).read_text())['i18n_zh']
    chain = int(zh['chain'], 16)                      # the old chain entry (xp_guide); the word now holds i18n_gd
    at = int(zh['code'][0], 16)
    code, stop = stub(GD_WORD)
    p = bytearray(1024); p[0:4] = b'EP7B'; p[680:684] = b'EP7E'; p[684] = axis
    view = bytearray(b'\xee' * 140)
    rg = [Region('stub', STUB, code, 'rx'),
          Region('zh', at & ~0xfff, sl(at & ~0xfff, (at & ~0xfff) + 0x1000), 'rx'),
          Region('gdw', 0x6025aa80, sl(0x6025aa80, 0x6025aac0), 'r'),
          Region('bank', 0x61fb2800, bytes(0x40), 'r'),
          Region('tabs', 0x61fc1500, struct.pack('<48xI', STRS if table else 0) + bytes(0x30), 'r'),
          Region('strs', STRS, strings(lang), 'r'),
          Region('state', 0x622cbcc0, struct.pack('<HHI', 0, HANDLE, 0), 'r'),
          Region('pool', P, bytes(p), 'r'),
          Region('stack', W.STACK, bytes([W.STACK_FILL] * 0x2000), 'rw', True),
          Region('view', VIEW, bytes(view), 'rw', True),
          Region('mock', chain, mock(chain, kind, text), 'rx')]
    r = execute(rg, dict(pc=STUB, sp=W.SP0, d0=0, a0=0, a3=0x3a3a, **REGS0), stop, limit=200000, trace_limit=1000)
    m = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}
    return r, m, stop


def label(m):
    t = m['view'][52:52 + 66]
    s = t.decode('utf-16-le')
    return s.split('\0')[0], t


CASES = [('1 Grain High', {}), ('3 Halo Med', {}), ('5 Shadow Yellow', {}), ('7 High +3', {}), ('Saturation - All', {}),
         ('2 Clarity/Glow 0', {}), ('4 WB Green/Mag.', {}), ('7 VigFix Camera', {}), ('Extras: 1-11 only', {}),
         ('Split: COLOR 1-4', {}), ('Stock', dict(axis=3)), ('Velvia Off', dict(axis=3)), ('Velvia Off', {}),
         ('Star Light Lightx', {}), ('1 Grain High', dict(lang='en')), ('1 Grain High', dict(kind=4)),
         ('1 Grain High', dict(table=False))]


def t_z(new):
    bad, n = [], 0
    for text, kw in CASES:
        r, m, stop = run(new, text, **kw)
        g = r['registers']
        on = kw.get('lang', 'zh') == 'zh' and kw.get('kind', 5) == 5 and kw.get('table', True)
        want = ZB.translate(text, film=kw.get('axis') == 3) if on else text
        got, raw = label(m)
        ok = not r['fault'] and g['pc'] == stop
        ok &= got == want and g['d0'] == 0x1234
        ok &= all(g[k] == {'d2': 0x2222, 'd3': 0x3333, 'a2': 0xa2a2, 'a3': 0x3a3a, 'sp': W.SP0}[k] for k in KEEP)
        if on and not (kw.get('axis') == 3 and want == text):     # rewritten: zero-padded
            ok &= raw[len(want) * 2:] == bytes(66 - len(want) * 2)
        else:
            ok &= m['view'][52 + len(text) * 2 + 2:] == b'\xee' * (140 - 52 - len(text) * 2 - 2)
        ok &= set(m['stack'][W.SP0 - W.STACK + 4:]) == {W.STACK_FILL}   # (SP0) = the stub's own calls return word
        n += 1
        print(f'   {text!r} {kw} -> {got!r}')
        if not ok:
            bad.append((text, kw, r['fault'], got, want, {k: hex(g[k]) for k in KEEP + ('d0',)}))
    return not bad, f'{n} cases; bad {bad[:3]}'


def t_pkg(base_s, new_s, base, new, pkg, rst, info):
    sb = {b.kind: b for b in oc.parse(BP.STOCK.read_bytes())}
    good = True
    for b in oc.parse(pkg):
        exp = bytearray(sb[b.kind].payload)
        for e in new_s['edits']:
            if int(e['kind'], 16) == b.kind:
                o = BP.resolve(b.kind, e['addr']); nb = bytes.fromhex(e['new']); exp[o:o + len(nb)] = nb
        good &= bytes(exp) == b.payload
        if b.kind == 0x100:
            good &= b.payload == new
    for b in oc.parse(rst):
        good &= b.payload == sb[b.kind].payload
    x = new_s['i18n_zh']
    ours = [(int(x['code'][0], 16), x['code'][1]), (GD_WORD, 4)]
    diff = [BASE + i for i in range(len(base)) if base[i] != new[i]]
    stray = [hex(a) for a in diff if not any(s_ <= a < s_ + k for s_, k in ours)]
    good &= not stray and len(new_s['edits']) == len(base_s['edits']) + 1
    return good, f'{info["edits"]} edits, {info["changed_payload_bytes"]} B; {len(diff)} B differ from base; stray {stray[:6]}'


def main():
    base_s, new_s = (json.loads(Path(p).read_text()) for p in sys.argv[1:3])
    base, *_ = image(base_s)
    new, pkg, rst, info = image(new_s)
    ok = True
    for tag, (g, txt) in (('Z', t_z(new)), ('P', t_pkg(base_s, new_s, base, new, pkg, rst, info))):
        print(f"{'PASS' if g else 'FAIL'} {tag} {txt}")
        ok &= g
    print('ALL PASS' if ok else 'FAILURES')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
