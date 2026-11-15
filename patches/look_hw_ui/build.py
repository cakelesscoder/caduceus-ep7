#!/usr/bin/env python3
"""look_hw_ui: base curve and named colour mixes on the Extras Colour & Light page (layer after look_hw). Offline.
lu.s.in has the contract; docs/LOOK_FORMAT_V4.md section 2 the slot bytes, docs/EXTRAS_MENU_V2.md what the user sees.

  .venv/bin/python -I patches/v032/build.py releases/v0.31d/edits.json --out generated/v034b_ui/edits.json --version 0.34b \\
      --extra grain_g2=... --extra look_hw=patches/look_hw/build.py ... --extra look_hw_ui=patches/look_hw_ui/build.py

apply(spec, version) -> spec. Edits (every old word is checked to hold what the v0.34a chain put there):
  - facade +8 GetValue 0x60acb0e4 (xp_get) -> lu_get, +24 count 0x60acb0f4 (xp_cnt) -> lu_cnt, +28 value by index
    0x60acb0f8 (xp_val) -> lu_val, +36 available 0x60acb100 (xp_av) -> lu_av;
  - GUI setter 0x607fa355 `call xp_set,[d2,d3,a2],16` -> `call lu_set`;
  - guide part word 0x6025aa98 (i18n_gd, or xp_guide without i18n_zh) -> lu_guide;
  - SD loader v3 range: slot +60 span 0 -> 84 (lo stays 0): the camera saves +60 and must load it again;
  - code + tables in a section-5 claim of the dead `sdk api` handlers (CODE_SPACE_SURVEY section 2).
The named mixes are MIXES below (in 1/128, slot order m01 m02 m10 m12 m20 m21); the table lu_tab is made from them.
"""
import argparse, copy, importlib.util, json, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SRC = 'patches/look_hw_ui'


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


XP = _load('ep7_xp_build_lu', ROOT / 'patches/extras_pages/build.py')
LH = _load('ep7_lh_build_lu', ROOT / 'patches/look_hw/build.py')
CL, KH, LE, B3 = LH.CL, XP.KH, XP.LE, XP.B3
BASE, STOCK = XP.BASE, XP.STOCK

# ---- the named mixes (starting values from a mock-up, not tuned looks: keep them modest). Order = the dial order 1..4.
MIXES = [('Warm film', 'Warm film', '暖色胶片', (6, -10, 4, -6, -8, 4)),
         ('Cool separation', 'Cool sep.', '冷色分离', (-8, 4, -4, 6, 6, -8)),
         ('Muted', 'Muted', '柔和', (14, 10, 10, 8, 10, 12)),
         ('Punchy', 'Punchy', '鲜艳', (-12, -6, -8, -6, -6, -10))]
STEPS = 10                                # strength 0..10 = 0..100 %
CURVES_EN = ['Camera', 'Standard', 'Auto', 'Pale', 'Light', 'Pop', 'Flat', 'Log']
CURVES_ZH = ['默认', '标准', '自动', '淡化', '柔光', '浓郁', '平实', 'Log']   # stock zh: 灰阶 (Gradation), 淡化及增亮, 柔光效果, 浓郁色调, 平实及柔和
LABELS = {  # index: (en, zh)
    0: ('9 Curve ', '9 灰阶 '), 1: ('10 Mix ', '10 配色 '), 2: ('11 Strength ', '11 配色强度 '),
    3: ('Colour: 1-11', '色彩: 1-11'), 4: ('Curve: COLOR 1-4', '灰阶: COLOR 1-4'), 5: ('Mix: COLOR 1-4', '配色: COLOR 1-4'),
    **{6 + i: (e, z) for i, (e, z) in enumerate(zip(CURVES_EN, CURVES_ZH))},
    14: ('From look', '原有'), 15: ('Off', '关'), **{16 + i: (m[1], m[2]) for i, m in enumerate(MIXES)},
    **{20 + s: (f'{10 * s}%', f'{10 * s}%') for s in range(STEPS + 1)},
}
N_LABELS = 31
LIST_LO, LIST_N = (0, -1, 0), (8, 6, 11)  # curve 0..7, mix -1..4, strength 0..10
SLOT60_SPAN = 8 * STEPS + len(MIXES)      # +60 = 8 (10 - strength) + mix: 0..84

CLAIM = (0x607d9300, 0x607d9b00)          # sec 5, 2 KB code, inside the run 0x607d92dc..0x607d9bcc into which nothing outside the dead code points
DCLAIM = (0x607d9be0, 0x607da1c0)         # sec 5, 1504 B tables / strings, inside the next such run 0x607d9bcd..0x607da1dc
GUARD = 16
AT, DAT = CLAIM[0] + GUARD, DCLAIM[0] + GUARD
W_GET, W_CNT, W_VAL, W_AV = XP.W_GET, XP.W_CNT, XP.W_VAL, XP.W_AV
SET_SITE, GUIDE_WORD = XP.SET_SITE, XP.GUIDE_WORD
LO, SPAN = LH.LO, LH.SPAN
SGET, MANAGER, FACADE = XP.SGET, XP.MANAGER, XP.FACADE
SECT = LH.SECT
BAD = XP.BAD | {'ext', 'trap', 'rti'}
STORES = {'mov d0,(a1)', 'movhu d0,(a1)', 'movhu d0,(44,a3)', 'movbu d1,(53,a2)', 'movbu d2,(60,a2)',
          *{f'movbu d3,({54 + i},a2)' for i in range(6)}}
LISTING = ['']


def u32(im, a):
    return struct.unpack_from('<I', im, a - BASE)[0]


def rnd(v, s):
    """v * s / 10, rounded half away from zero (the firmware's table)."""
    q = (abs(v) * s + STEPS // 2) // STEPS
    return q if v >= 0 else -q


def row(mix, s):
    """mix 0 Off, 1..4 MIXES; s 0..10 -> the six slot bytes +54..+59 (signed)."""
    return (0,) * 6 if mix == 0 else tuple(rnd(v, s) for v in MIXES[mix - 1][3])


def decode(b):
    """Host model of lu_dec: 64-B slot -> (mix -1..4, strength 0..10)."""
    m = tuple(x - 256 if x >= 128 else x for x in b[54:60])
    mix, h = b[60] & 7, b[60] >> 3
    if mix > 4 or h > STEPS:
        mix, h = 0, 0
    s = STEPS - h
    if row(mix, s) == m:
        return mix, s
    if m == (0,) * 6:
        return 0, s
    for s2 in range(STEPS, 0, -1):
        for k in range(1, len(MIXES) + 1):
            if row(k, s2) == m:
                return k, s2
    return -1, STEPS


def check_mixes():
    seen = {}
    for k, (name, en, zh, v) in enumerate(MIXES, 1):
        if len(v) != 6 or any(not -64 <= x <= 64 for x in v):
            raise SystemExit(f'{name}: six values in -64..64')
        for s in range(1, STEPS + 1):
            r = row(k, s)
            if r == (0,) * 6:
                raise SystemExit(f'{name} at {10 * s} % rounds to zero')
            if r in seen:
                raise SystemExit(f'{name} at {10 * s} % equals {seen[r]}: the camera could not tell them apart')
            seen[r] = f'{name} {10 * s} %'
    import re
    ts = (ROOT / 'webapp/src/pack.ts').read_text()
    web = [(n, tuple(int(x) for x in v.split(','))) for n, v in re.findall(r"\{ name: '([^']+)', m: \[([-0-9, ]+)\] \}", ts)]
    if web != [(m[0], m[3]) for m in MIXES]:
        raise SystemExit(f'webapp/src/pack.ts NAMED_MIXES differ from MIXES: {web}')
    if len(MIXES) != 4 or SLOT60_SPAN > 127:
        raise SystemExit('four mixes; +60 must stay below 128 (the loader reads it signed)')


def check_labels():
    if sorted(LABELS) != list(range(N_LABELS)):
        raise SystemExit('label indices')
    for i, (en, zh) in LABELS.items():
        if not en.isascii():
            raise SystemExit(f'label {i} not ASCII')
    pairs = [(0, j) for j in range(6, 14)] + [(1, j) for j in range(14, 20)] + [(2, j) for j in range(20, N_LABELS)]
    for i, j in pairs:
        for lang in (0, 1):
            t = LABELS[i][lang] + LABELS[j][lang]
            if len(t) > 16:
                raise SystemExit(f'label {t!r} longer than 16')
    for i in (3, 4, 5):
        if any(len(x) > 16 for x in LABELS[i]):
            raise SystemExit(f'label {LABELS[i]} longer than 16')
    sys.path.insert(0, str(ROOT / 'tools'))
    import zh_glyphs
    have = zh_glyphs.available()
    miss = {z: ''.join(c for c in z if ord(c) > 127 and c not in have) for _, z in LABELS.values()}
    miss = {z: m for z, m in miss.items() if m}
    if miss:
        raise SystemExit(f'no glyph in font res 36: {miss}')


def data_src():
    out = [' .balign 4', 'lu_tab:']
    for mix in range(len(MIXES) + 1):
        for s in range(STEPS + 1):
            out.append(' .byte ' + ','.join(str(x) for x in row(mix, s)))
    out += ['lu_n:', ' .byte ' + ','.join(str(x) for x in LIST_N), 'lu_lo:', ' .byte ' + ','.join(str(x) for x in LIST_LO)]
    strs = {}
    for i in range(N_LABELS):
        for t in LABELS[i]:
            strs.setdefault(t, f'lu_s{len(strs)}')
    out.append(' .balign 4')
    for lang, name in ((0, 'lu_en'), (1, 'lu_zh')):
        out.append(f'{name}:')
        out += [f' .long {strs[LABELS[i][lang]]}' for i in range(N_LABELS)]
    for t, lab in strs.items():
        out += [' .balign 2', f'{lab}:', ' .hword ' + ','.join(str(ord(c)) for c in t) + ',0']
    return '\n'.join(out), strs


def subst():
    s = LE.sub(probe=False)
    return dict(state=s['state'], lim=s['lim'], pool=s['pool'], bmagic=s['bmagic'], emark=s['emark'], emagic=s['emagic'],
                axis=s['axis'], dirty=s['dirty'], sub=XP.SUB, x_axis=4, poly_ret=hex(XP.POLY_RET), sect=hex(SECT))


REGIONS = {'.luc': (AT, CLAIM[1] - GUARD), '.lud': (DAT, DCLAIM[1] - GUARD)}


def build_code(syms):
    """-> ({'.luc': code, '.lud': data}, symbols, listing)."""
    data, strs = data_src()
    src = B3.subst((HERE / 'lu.s.in').read_text(), dict(subst(), lu_data=data))
    out, sy, lst = XP.ST.assemble(src, syms, {k: (v[0], v[1]) for k, v in REGIONS.items()})
    code, dat = out['.luc'], out['.lud']
    if sy['lu_get'] != AT or sy['lu_tab'] != DAT:
        raise SystemExit('entry layout')
    for k, (lo, hi) in REGIONS.items():
        if lo + len(out[k]) > hi:
            raise SystemExit(f'{k}: {len(out[k])} B does not fit {hi - lo}')
    for k in ('lu_en', 'lu_zh'):
        if sy[k] % 4:
            raise SystemExit(f'{k} not 4-aligned')
    if any(sy[l] % 2 for l in strs.values()):
        raise SystemExit('string not 2-aligned')
    ins = B3.disasm(code, AT)
    if any(op in BAD for _, op, _ in ins) or any(op.startswith('.') or op == '(bad)' for _, op, _ in ins):
        raise SystemExit(f'forbidden or undecodable instruction {[x for x in ins if x[1] in BAD or x[1] == "(bad)"][:3]}')
    if any(code[a - AT] == 0xfb for a, _, _ in ins):
        raise SystemExit('fb-prefixed form')
    dirty = f'movbu d2,({subst()["dirty"]},a2)'
    for a, txt, kd, tg in B3.store_audit(ins):
        if kd not in ('sp', 'ind') or (kd == 'ind' and txt not in STORES | {dirty}):
            raise SystemExit(f'store at {a:#x}: {txt} ({kd})')
    want = {('call', t) for t in (SGET, FACADE, syms['ep7_xp_find'], syms['ep7_xp_sw'], sy['lu_dec'], sy['lu_eq'], sy['lu_put'], sy['lu_lang'])}
    want |= {('jmp', syms[k]) for k in ('ep7_xp_get', 'ep7_xp_cnt', 'ep7_xp_val', 'ep7_xp_av', 'ep7_xp_set', 'ep7_manager', 'ep7_guide_in')}
    want |= {('calls', syms['ep7_guide_in'])}
    seen = {(op, int(args.split(',')[0], 16)) for _, op, args in ins if op in ('call', 'jmp', 'calls') and args.startswith('0x')
            and (op == 'call' or not AT <= int(args.split(',')[0], 16) < AT + len(code))}
    if seen != want:
        raise SystemExit(f'call / jmp targets {sorted((o, hex(t)) for o, t in seen ^ want)}')
    tab = bytes(x & 0xff for mix in range(5) for s in range(STEPS + 1) for x in row(mix, s))
    if dat[:len(tab)] != tab:
        raise SystemExit('mix table')
    return out, sy, lst


def put(spec, stock, addr, old, new, why):
    """Into the edit that covers addr (layered sites), else a new edit (as patches/extras_pages put())."""
    im = XP.ST.img_of(spec, stock)
    if im[addr - BASE:addr - BASE + len(old)] != old:
        raise SystemExit(f'{addr:#x}: {im[addr - BASE:addr - BASE + len(old)].hex()} != {old.hex()} ({why})')
    for e in spec['edits']:
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            a, n = int(e['addr'], 16), len(e['new']) // 2
            if a <= addr and addr + len(new) <= a + n:
                b = bytearray.fromhex(e['new']); b[addr - a:addr - a + len(new)] = new; e['new'] = b.hex()
                e['why'] += f' [look_hw_ui: {why}]'
                return
            if a < addr + len(new) and addr < a + n:
                raise SystemExit(f'{addr:#x}: straddles edit {e["addr"]}')
    spec['edits'].append(dict(kind='0x100', addr=hex(addr), expect=stock[addr - BASE:addr - BASE + len(new)].hex(), new=new.hex(),
                              source=SRC, why=f'look_hw_ui: {why}'))


def check_claim(spec, stock, im, CLAIM):
    lo5, hi5, off5 = KH.sec(stock, 5)
    if not (lo5 <= CLAIM[0] and CLAIM[1] <= hi5 and KH.DEAD[1][0] <= CLAIM[0] and CLAIM[1] <= KH.DEAD[1][1]):
        raise SystemExit('claim not inside the dead handler range of section 5')
    if LH.V3B.overlaps(spec, *CLAIM) or im[CLAIM[0] - BASE:CLAIM[1] - BASE] != stock[CLAIM[0] - BASE:CLAIM[1] - BASE]:
        raise SystemExit('claim is edited / not stock')
    if CLAIM[0] <= (KH.DOUBLE_K - off5) & 0xffffffff < CLAIM[1]:
        raise SystemExit('the 0x40e4ab40 double constant aliases into the claim')
    for w, v in KH.SUBCMD.items():
        if u32(im, w) == v:
            raise SystemExit(f'sdk sub-command word {w:#x} still stock: the shell can reach the claim')
    bad = CL.refs(im, CLAIM[0], CLAIM[1], off5, allow=list(KH.DEAD))
    if bad:
        raise SystemExit(f'reference into the claim: {[(k, hex(a)) for k, a in bad[:6]]}')


def apply(spec, version='0.34b'):
    stock = STOCK.read_bytes()
    spec = copy.deepcopy(spec)
    if 'look_hw_ui' in spec:
        raise SystemExit('look_hw_ui already applied')
    for need in ('extras_pages', 'look_hw'):
        if need not in spec:
            raise SystemExit(f'needs {need}')
    check_mixes()
    check_labels()
    im = XP.ST.img_of(spec, stock)
    xp = {k: int(v, 16) for k, v in spec['extras_pages']['symbols'].items()}
    nxt = dict(ep7_xp_get=u32(im, W_GET), ep7_xp_cnt=u32(im, W_CNT), ep7_xp_val=u32(im, W_VAL), ep7_xp_av=u32(im, W_AV),
               ep7_guide_in=u32(im, GUIDE_WORD))
    if (nxt['ep7_xp_get'], nxt['ep7_xp_cnt'], nxt['ep7_xp_val'], nxt['ep7_xp_av']) != (xp['xp_get'], xp['xp_cnt'], xp['xp_val'], xp['xp_av']):
        raise SystemExit('facade +8 / +24 / +28 / +36 are not xp_get / xp_cnt / xp_val / xp_av')
    gd = nxt['ep7_guide_in']
    zh = spec.get('i18n_zh', {}).get('symbols', {}).get('i18n_gd')
    if gd not in (xp['xp_guide'], int(zh, 16) if zh else None):
        raise SystemExit(f'guide word -> {gd:#x}: not i18n_gd / xp_guide')
    site = im[SET_SITE - BASE:SET_SITE + 7 - BASE]
    if site[0] != 0xdd or site[5:] != b'\xe0\x10' or SET_SITE + struct.unpack('<i', site[1:5])[0] != xp['xp_set']:
        raise SystemExit(f'setter site {site.hex()} is not call xp_set,[d2,d3,a2],16')
    mp = im[xp['xp_map'] - BASE:xp['xp_map'] + 24 - BASE]
    if list(mp) != XP.MAP or any(mp[12 + n] != 0x20 for n in range(8, 12)):
        raise SystemExit('extras_pages map: Colour & Light sectors 9..12 are not empty')
    if im[LO + 60 - BASE] != 0 or im[SPAN + 60 - BASE] != 0 or (im[LO + 53 - BASE], im[SPAN + 53 - BASE]) != (0, 7):
        raise SystemExit('loader range +60 is not 0 / 0 (or look_hw +53 not 0 / 7)')
    if im[MANAGER - BASE] != 0x87:
        raise SystemExit('manager entry')
    for c in (CLAIM, DCLAIM):
        check_claim(spec, stock, im, c)
    syms = dict(nxt, ep7_xp_find=xp['xp_find'], ep7_xp_sw=xp['xp_sw'], ep7_xp_set=xp['xp_set'], ep7_sget=SGET,
                ep7_manager=MANAGER, ep7_facade=FACADE)
    out, sy, lst = build_code(syms)
    LISTING[0] = lst
    code, dat = out['.luc'], out['.lud']
    spec['edits'].append(dict(kind='0x100', addr=hex(AT), expect=stock[AT - BASE:AT - BASE + len(code)].hex(), new=code.hex(),
                              source=SRC, why=f'look_hw_ui {version}: curve / mix / strength on Extras Colour & Light 9..11 '
                                              f'({len(code)} B code, sec-5 dead sdk-api handlers, claim {CLAIM[0]:#x}..{CLAIM[1]:#x})'))
    spec['edits'].append(dict(kind='0x100', addr=hex(DAT), expect=stock[DAT - BASE:DAT - BASE + len(dat)].hex(), new=dat.hex(),
                              source=SRC, why=f'look_hw_ui {version}: mix table lu_tab, list bounds, label tables and strings '
                                              f'({len(dat)} B, sec-5 dead sdk-api handlers, claim {DCLAIM[0]:#x}..{DCLAIM[1]:#x})'))
    p32 = lambda v: struct.pack('<I', v)
    put(spec, stock, W_GET, p32(nxt['ep7_xp_get']), p32(sy['lu_get']), 'facade +8 GetValue -> lu_get (then xp_get)')
    put(spec, stock, W_CNT, p32(nxt['ep7_xp_cnt']), p32(sy['lu_cnt']), 'facade +24 count -> lu_cnt (then xp_cnt)')
    put(spec, stock, W_VAL, p32(nxt['ep7_xp_val']), p32(sy['lu_val']), 'facade +28 value by index -> lu_val (then xp_val)')
    put(spec, stock, W_AV, p32(nxt['ep7_xp_av']), p32(sy['lu_av']), 'facade +36 available -> lu_av (then xp_av)')
    put(spec, stock, SET_SITE + 1, site[1:5], struct.pack('<i', sy['lu_set'] - SET_SITE), 'GUI setter call xp_set -> call lu_set')
    put(spec, stock, GUIDE_WORD, p32(gd), p32(sy['lu_guide']), 'guide part word -> lu_guide (runs the chain first)')
    put(spec, stock, SPAN + 60, b'\0', bytes([SLOT60_SPAN]), f'SD loader v3 range slot +60 span {SLOT60_SPAN} (mix memory)')
    spec['look_hw_ui'] = dict(
        built_by=SRC, version=version, claims=[[hex(CLAIM[0]), hex(CLAIM[1])], [hex(DCLAIM[0]), hex(DCLAIM[1])]], code=[hex(AT), len(code)], data=[hex(DAT), len(dat)],
        page='Colour & Light (sub-page 1)', sectors={'9': 'curve (+53, list 0..7)', '10': 'mix (list -1..4)',
                                                       '11': 'strength (list 0..10 = 0..100 %)', '12': 'empty, label Colour: 1-11'},
        slot60='8 * (10 - strength) + mix (0 Off, 1..4 named); loader lo 0 span 84',
        mixes={m[0]: list(m[3]) for m in MIXES}, rounding='v * s / 10, half away from zero',
        labels={str(k): list(v) for k, v in LABELS.items()},
        next={k: hex(v) for k, v in syms.items()}, symbols={k: hex(v) for k, v in sy.items() if k.startswith('lu_')})
    return spec


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--version', default='0.34b')
    ap.add_argument('--listing', type=Path)
    a = ap.parse_args()
    spec = apply(json.loads(a.spec.read_text()), a.version)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(spec, indent=1))
    if a.listing:
        a.listing.write_text(LISTING[0])
    print(json.dumps({k: v for k, v in spec['look_hw_ui'].items() if k not in ('symbols', 'next', 'labels')}, ensure_ascii=False))
