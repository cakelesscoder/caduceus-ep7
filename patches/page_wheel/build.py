#!/usr/bin/env python3
"""Page wheel (issue #52): the COLOR wheel reached from the full Colour Profile page opens as the SCP's does. Offline layer:

  .venv/bin/python -I patches/v032/build.py releases/v0.31d/edits.json --out generated/v035b/edits.json --version 0.35b \\
      --extra grain_g2=patches/grain_g2/build.py --extra halation_h6=patches/halation_h6/build.py \\
      --extra crash_log=patches/crash_log/build.py --extra clean_boot=patches/clean_boot/build.py \\
      --extra v033b=patches/v033b/build.py --extra look_hw=patches/look_hw/build.py \\
      --extra look_hw_ui=patches/look_hw_ui/build.py --extra movie_quality=patches/movie_quality/build.py \\
      --extra looks_v4=patches/looks_v4/build.py --extra i18n_ja=patches/i18n_ja/build.py \\
      --extra movie_guide=patches/movie_guide/build.py --extra owner_footer=patches/owner_footer/build.py \\
      --extra mdial=patches/mdial/build.py --extra page_wheel=patches/page_wheel/build.py

Cause [V code; the repaint itself is camera-observed, #52]: the Shortcut button (and the profile lever) open SsMenuLv state 29
(ID_ST_PROFILE_SELECT_MENU; entry 0x60e5dae9 = screen_open(8, 463) -> 0x61fc436c, exit 0x60e5db01 closes it). Its screen is
actuator kind 52 (create 0x60e260c7, vtable 0x6118957c) + viewer 0x84. The actuator has a row column at +76 and, after each
row change, rebuilds its +80 child (0x60e266a9): row 1 with picture mode 54 / 55 / 56 / 64 is a Plural_Direct column for
the COLOR wheel key (table 0x61189278: 0x13b3 / 0x13b4 / 0x13b5 / 0x140c). So on that route the wheel is a part of the page,
and the page's viewer redraws the whole page on every edit. From the SCP the wheel is its own screen: OK puts the cell's sid in
0x61fc4370 and returns (4, 7); state 7 (entry 0x60e590bd) opens screen (18, key) over live view.

Fix: state 29's only handler (word 137 at 0x611a2e2c, 0x60e5da87; the matrix uses it in state 29 only, for its 31 events) ->
pw_h (pw.s.in). pw_h runs the stock handler; if that stays in state 29 after a key / dial event and the page's column is on row
1 with a COLOR picture mode, it stores the wheel key in 0x61fc4370 and returns (4, 7) instead of 0, as the SCP's OK does. The
page closes (its exit), and state 7 opens the same wheel record as its own screen. Leaving it is state 7's: OK -> (18, 3) to
the camera app (the message the page itself sends when OK closes it) and live view, MENU -> (18, 7).
MONO rows, rows 0 / 2 / 3, every other event, other states: stock. Code (142 B) in a sec-5 dead `sdk api` claim.
"""
import argparse, copy, importlib.util, json, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SRC = 'patches/page_wheel'


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


JA = _load('ep7_ja_build_pw', ROOT / 'patches/i18n_ja/build.py')
ST, KH, B3, BASE, STOCK, BAD = JA.ST, JA.KH, JA.B3, JA.BASE, JA.STOCK, JA.BAD

CLAIM = (0x607e5200, 0x607e5400)          # first 512-B run past mdial's claim with no reference into it (JA.check_claim)
GUARD = 16
AT = CLAIM[0] + GUARD
WORD, STOCK_H = 0x611a2e2c, 0x60e5da87    # SsMenuLv handler word 137 (state 29's handler for every event)
DESC, NST, MATRIX, HWORDS, NEV = 0x611a3bc8, 29, 0x611a2e30, 0x611a2c08, 112
PAGE_SCR, KEY_W, PAGE_VT, FACADE = 0x61fc436c, 0x61fc4370, 0x6118957c, 0x607f9062
KEYS = {54: 0x13b3, 55: 0x13b4, 56: 0x13b5, 64: 0x140c}
CHECKS = {   # stock bytes the design reads (address: hex)
    0x60e5dae9: 'f8fefc8008' + '2dcf01' + 'ddb7f3feff' + 'f034' + 'fc806c43fc61',  # state 29 entry: screen_open(8, 463) -> PAGE_SCR
    0x60e5da90: 'fca06c43fc61',                         # stock handler: screen = (PAGE_SCR)
    0x60e5dada: '8f018a04',                             # ... its close rc (1, 4)
    0x60e2611f: 'fccc7c951861',                         # kind-52 ctor stores vtable PAGE_VT
    0x60e266dd: 'f1e8f000f004f82504f0f1',               # page: (+76)->vtbl+4 = row
    0x60e26701: 'aa01c827',                             # row 1 ->
    0x60e26735: 'fcd078921861',                         # ... key table 0x61189278
    0x60e590d7: 'fcad7043fc61',                         # state 7 entry reads the key word
    0x60e56aae: 'fc837043fc61',                         # SCP OK stores the key word
}


def u32(im, a):
    return struct.unpack_from('<I', im, a - BASE)[0]


def check_stock(stock, im):
    for a, h in CHECKS.items():
        if h and (stock[a - BASE:a - BASE + len(h) // 2].hex() != h or im[a - BASE:a - BASE + len(h) // 2].hex() != h):
            raise SystemExit(f'{a:#x}: bytes differ from the design')
    if u32(stock, WORD) != STOCK_H or u32(im, WORD) != STOCK_H:
        raise SystemExit('handler word 137 is not the stock state-29 handler (another layer?)')
    d = stock[DESC - BASE:DESC - BASE + 32]
    if (d[0], struct.unpack_from('<I', d, 8)[0], struct.unpack_from('<I', d, 12)[0], d[28]) != (NST, MATRIX, HWORDS, 0):
        raise SystemExit('SsMenuLv descriptor differs')
    mat = im[MATRIX - BASE:MATRIX - BASE + NEV * NST]
    uses = {s + 1 for e in range(NEV) for s in range(NST) if mat[e * NST + s] == 137}
    if uses != {29}:
        raise SystemExit(f'word 137 used by states {sorted(uses)}')
    t = struct.unpack_from('<16I', stock, 0x61189278 - BASE)
    if {t[2 * i]: t[2 * i + 1] for i in range(8)} != {57: 0x13b6, 58: 0x13b7, 59: 0x13b8, 65: 0x140d, **KEYS}:
        raise SystemExit('row-1 key table differs')


def build_code(spec):
    sub = dict(page_scr=hex(PAGE_SCR), key_w=hex(KEY_W), page_vt=hex(PAGE_VT), **{f'k{k}': hex(v) for k, v in KEYS.items()})
    code, lst, sy, _ = B3.assemble(B3.subst((HERE / 'pw.s.in').read_text(), sub), AT, dict(ep7_stock_h=STOCK_H, ep7_facade=FACADE))
    if sy['pw_h'] != AT or AT + len(code) > CLAIM[1] - GUARD or sy['pw_end'] != AT + len(code):
        raise SystemExit('layout')
    ins = B3.disasm(code, AT, AT + len(code))
    if any(op in BAD for _, op, _ in ins) or any(op.startswith('.') or op == '(bad)' for _, op, _ in ins):
        raise SystemExit('forbidden or undecodable instruction')
    if any(code[a - AT] == 0xfb for a, _, _ in ins):
        raise SystemExit('fb-prefixed form')
    st = [(a, txt, kd) for a, txt, kd, _ in B3.store_audit(ins) if kd != 'sp']
    if [(txt, kd) for _, txt, kd in st] != [('movhu d1,(a0)', 'ind')]:
        raise SystemExit(f'stores {st}')
    a_st = st[0][0]
    prev = [x for x in ins if x[0] < a_st][-1]
    if prev[1] != 'mov' or prev[2] not in (f'{KEY_W},a0', f'{KEY_W:#x},a0'):
        raise SystemExit('the one store is not to the key word')
    tg = {(op, args) for _, op, args in ins if op in ('call', 'calls', 'jmp')}
    if tg != {('calls', hex(STOCK_H)), ('calls', '(a1)'), ('calls', '(a2)'), ('call', f'{FACADE:#x},[],4')}:
        raise SystemExit(f'call targets {sorted(tg)}')
    return code, sy, lst


def apply(spec, version='0.35b'):
    stock = STOCK.read_bytes()
    spec = copy.deepcopy(spec)
    if 'page_wheel' in spec:
        raise SystemExit('page_wheel already applied')
    if 'extras_pages' not in spec:
        raise SystemExit('needs extras_pages (the sdk sub-command cut that makes the claim dead)')
    im = ST.img_of(spec, stock)
    check_stock(stock, im)
    JA.check_claim(spec, stock, im, CLAIM)
    code, sy, lst = build_code(spec)
    spec['edits'].append(dict(kind='0x100', addr=hex(AT), expect=stock[AT - BASE:AT - BASE + len(code)].hex(), new=code.hex(),
                              source=SRC, why=f'page_wheel {version}: pw_h ({len(code)} B, sec-5 dead sdk-api handlers, claim '
                                              f'{CLAIM[0]:#x}..{CLAIM[1]:#x})'))
    spec['edits'].append(dict(kind='0x100', addr=hex(WORD), expect=struct.pack('<I', STOCK_H).hex(), new=struct.pack('<I', AT).hex(),
                              source=SRC, why=f'page_wheel {version}: SsMenuLv handler word 137 (state 29) -> pw_h (then {STOCK_H:#x})'))
    spec['page_wheel'] = dict(built_by=SRC, version=version, claim=[hex(CLAIM[0]), hex(CLAIM[1])], code=[hex(AT), len(code)],
                              word=hex(WORD), stock=hex(STOCK_H), key_word=hex(KEY_W), page_screen=hex(PAGE_SCR),
                              keys={str(k): hex(v) for k, v in KEYS.items()}, symbols={k: hex(v) for k, v in sy.items() if k.startswith('p')})
    return spec


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--version', default='0.35b')
    a = ap.parse_args()
    spec = apply(json.loads(a.spec.read_text()), a.version)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(spec, indent=1))
    print(json.dumps(spec['page_wheel']))
