#!/usr/bin/env python3
"""Extras wheel pages: Effects and Colour & Light (layer on v0.32 after split_tone). Offline. docs/EXTRAS_MENU_V2.md
option B, "Build log"; xp.s.in has the contract.

  .venv/bin/python -I patches/extras_pages/build.py <spec after split_tone> --out <edits.json>

apply(spec, version) -> spec. Edits (every old word is checked to hold what the v0.31d / v0.32 chain put there):
  - facade +8 GetValue 0x60acb0e4 (ap_xg) -> xp_get, +152 GetDefault 0x60acb174 (mv_def) -> xp_def,
    +24 count 0x60acb0f4, +28 value by index 0x60acb0f8, +36 available 0x60acb100 (stock) -> xp_cnt / xp_val / xp_av;
  - GUI setter 0x607fa355 `call ap_xs,[d2,d3,a2],16` -> `call xp_set`;
  - guide part word 0x6025aa98 (ap_gd) -> xp_guide;
  - ed_info k_step 0x601e3059 (`movbu (684,a2),d0; mov 2,d1`, 6 B) -> `jmp xp_step; nop`;
  - code in a sec-5 claim of the dead `sdk api` shell handlers (CODE_SPACE_SURVEY §2), with the three `sdk` sub-command
    words api / starttimer / stoptimer -> xp_ret0 (`clr d0; rets`) so no console input reaches the claim.
No slot-format change: old fields keep their bytes; split tone is slot +62/+63 as patches/split_tone reads it.
"""
import argparse, copy, importlib.util, json, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SRC = 'patches/extras_pages'


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


ST = _load('ep7_st_build_xp', ROOT / 'patches/split_tone/build.py')
KH = _load('ep7_kh_build_xp', ROOT / 'patches/keyhook/build.py')     # its claim checks only (the keyhook layer is not applied)
LE = _load('ep7_le_build_xp', ROOT / 'patches/look_editor/build.py')
SB3, B3 = ST.SB3, LE.B3
BASE, STOCK = 0x60020020, ST.STOCK

CLAIM = (0x607c9420, 0x607c9c20)          # sec 5, 2 KB of the dead sdk-api handlers, past the (unbuilt) overlay claim
# naive scan hit into the claim, dis-checked: byte offset 3 inside the aligned sec-5 pointer table 0x60b814e0.. (words
# 0x60a07d13 / 0x60a07c97), not an address use
PINS = {0x60b814f3: '60977ca0'}
GUARD = 16
AT = CLAIM[0] + GUARD
W_GET, W_DEF, W_CNT, W_VAL, W_AV = 0x60acb0e4, 0x60acb174, 0x60acb0f4, 0x60acb0f8, 0x60acb100
STOCK_CNT, STOCK_VAL, STOCK_AV = 0x607f95dc, 0x607f9912, 0x607f90f9
SET_SITE = 0x607fa355
GUIDE_WORD = 0x6025aa98
K_STEP, K_BACK, K_SET = 0x601e3059, 0x601e305f, 0x601e308a
K_OLD = bytes.fromhex('fa42ac028502')     # movbu (684,a2),d0; mov 2,d1
POLY_RET = 0x601e313f                     # ed_poly: return address of its `calls (a2)` on the GetValue word
POLY_CALL = bytes.fromhex('fca2e4b0ac60f0f2')   # mov (0x60acb0e4),a2; calls (a2)
SUB = 687                                 # heap P+687: bit 0 sub-page, bits 4..7 guide cursor override
SGET, MANAGER, FACADE = 0x602af887, 0x60827440, 0x607f9062
ALL0, ALL1 = 0x61fc3800, 0x61fc3804
BAD = {'mulu', 'div', 'divu', 'mul', 'setlb', 'llt', 'lne', 'leq', 'lra', 'lcc', 'lcs', 'trap'}
MAP = [0, 1, 10, 4, 9, 8, 7, 0x20, 0x20, 0x20, 0x20, 0x20,
       2, 3, 5, 6, 0x10, 0x11, 0x12, 0x13, 0x20, 0x20, 0x20, 0x20]
PAGES = {'Effects': ['Grain', 'Glow/Clarity', 'Halo', 'Art', 'Sharp', 'NR', 'VigFix'],
         'Colour & Light': ['WB A-B', 'WB G-M', 'Blacks', 'Whites', 'Shadow colour', 'Shadow strength',
                            'Highlight colour', 'Highlight strength']}


LISTING = ['']


def u32(im, a):
    return struct.unpack_from('<I', im, a - BASE)[0]


def subst():
    s = LE.sub(probe=False)
    return dict(state=s['state'], lim=s['lim'], pool=s['pool'], bmagic=s['bmagic'], emark=s['emark'], emagic=s['emagic'],
                axis=s['axis'], dirty=s['dirty'], sub=SUB, x_axis=4, poly_ret=hex(POLY_RET))


def build_code(syms):
    src = B3.subst((HERE / 'xp.s.in').read_text(), subst())
    code, lst, sy, dis = B3.assemble(src, AT, syms)
    if sy['xp_ret0'] != AT or code[:3] != bytes.fromhex('00f0fc'):
        raise SystemExit('xp_ret0 is not clr d0; rets at the claim start')
    if AT + len(code) > CLAIM[1] - GUARD:
        raise SystemExit(f'{len(code)} B does not fit')
    ins = B3.disasm(code, AT, sy['xp_map'])
    if any(op in BAD for _, op, _ in ins) or any(op.startswith('.') or op == '(bad)' for _, op, _ in ins):
        raise SystemExit('forbidden or undecodable instruction')
    if any(code[a - AT] == 0xfb for a, _, _ in ins):
        raise SystemExit('fb-prefixed form')
    ok_ind = {'mov d0,(a1)', f'movbu d0,({SUB},a2)', f'movbu d1,({SUB},a2)', 'movbu d0,(94,a2)', 'movbu d2,(685,a2)',
              'movhu d0,(44,a3)', 'movhu d0,(52,a3)', 'movhu d0,(a1)', 'movhu d0,(a0)'}
    for a, txt, kd, tg in B3.store_audit(ins):
        if kd == 'abs' or (kd == 'ind' and txt.replace(' ', ' ') not in ok_ind) or kd not in ('sp', 'ind'):
            raise SystemExit(f'store at {a:#x}: {txt} ({kd})')
    want = {('call', t) for t in (SGET, FACADE, syms['ep7_xb'], syms['ep7_set_next'], sy['xp_find'], sy['xp_sw'], sy['xp_sv'])}
    want |= {('jmp', syms[k]) for k in ('ep7_get_next', 'ep7_def_next', 'ep7_cnt', 'ep7_val', 'ep7_av', 'ep7_set_next',
                                         'ep7_manager', 'ep7_k_set', 'ep7_k_back')}
    want |= {('calls', syms['ep7_guide_in'])}
    seen = {(op, int(args.split(',')[0], 16)) for _, op, args in ins if op in ('call', 'jmp', 'calls') and args.startswith('0x')
            and not AT <= int(args.split(',')[0], 16) < AT + len(code) or (op == 'call' and args.startswith('0x'))}
    if seen != want:
        raise SystemExit(f'call / jmp targets {sorted((o, hex(t)) for o, t in seen)}')
    if list(code[sy['xp_map'] - AT:sy['xp_map'] - AT + 24]) != MAP:
        raise SystemExit('map table')
    return code, sy, lst


def put(spec, stock, addr, old, new, why):
    """Into the edit that covers addr (layered sites), else a new edit (as patches/split_tone)."""
    im = ST.img_of(spec, stock)
    if im[addr - BASE:addr - BASE + len(old)] != old:
        raise SystemExit(f'{addr:#x}: {im[addr - BASE:addr - BASE + len(old)].hex()} != {old.hex()} ({why})')
    for e in spec['edits']:
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            a, n = int(e['addr'], 16), len(e['new']) // 2
            if a <= addr and addr + len(new) <= a + n:
                b = bytearray.fromhex(e['new']); b[addr - a:addr - a + len(new)] = new; e['new'] = b.hex()
                e['why'] += f' [extras_pages: {why}]'
                return
            if a < addr + len(new) and addr < a + n:
                raise SystemExit(f'{addr:#x}: straddles edit {e["addr"]}')
    spec['edits'].append(dict(kind='0x100', addr=hex(addr), expect=stock[addr - BASE:addr - BASE + len(new)].hex(), new=new.hex(),
                              source=SRC, why=f'extras_pages: {why}'))


def check_claim(spec, stock, im):
    lo5, hi5, off5 = KH.sec(stock, 5)
    if not (lo5 <= CLAIM[0] and CLAIM[1] <= hi5):
        raise SystemExit('claim not inside section 5')
    if not (KH.DEAD[1][0] <= CLAIM[0] and CLAIM[1] <= KH.DEAD[1][1]):
        raise SystemExit('claim not inside the dead handler range')
    for e in spec['edits']:
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            a, n = int(e['addr'], 16), len(e['new']) // 2
            if a < CLAIM[1] and CLAIM[0] < a + n:
                raise SystemExit(f'claim overlaps edit {e["addr"]}')
    if im[CLAIM[0] - BASE:CLAIM[1] - BASE] != stock[CLAIM[0] - BASE:CLAIM[1] - BASE]:
        raise SystemExit('claim not stock')
    if CLAIM[0] <= (KH.DOUBLE_K - off5) & 0xffffffff < CLAIM[1]:
        raise SystemExit('the 0x40e4ab40 double constant aliases into the claim')
    KH.pin_fp(stock)
    KH.FALSE_POS.update(PINS)
    bad = KH.scan(im, CLAIM[0], CLAIM[1], off5, KH.DEAD)
    if bad:
        raise SystemExit(f'reference into the claim: {[(k, hex(a)) for k, a in bad[:4]]}')
    for w, v in KH.SUBCMD.items():
        if u32(im, w) != v:
            raise SystemExit(f'sdk sub-command word {w:#x} != {v:#x}')


def apply(spec, version='0.32'):
    stock = STOCK.read_bytes()
    spec = copy.deepcopy(spec)
    if 'extras_pages' in spec:
        raise SystemExit('extras_pages already applied')
    for k in ('keyhook', 'overlay_probe', 'diag', 'plugin_loader'):
        if k in spec:
            raise SystemExit(f'{k} is in the spec: plugins are shelved; build without them')
    if 'split_tone' not in spec:
        raise SystemExit('layer after split_tone')
    im = ST.img_of(spec, stock)
    ap = {k: int(v, 16) for k, v in spec['ap_custom']['symbols'].items()}
    mv = {k: int(v, 16) for k, v in spec['v026_movie']['wheel_symbols'].items()}
    le = {k: int(v, 16) for k, v in spec['look_editor']['symbols'].items()}
    nxt = dict(ep7_get_next=u32(im, W_GET), ep7_def_next=u32(im, W_DEF), ep7_cnt=u32(im, W_CNT), ep7_val=u32(im, W_VAL),
               ep7_av=u32(im, W_AV), ep7_guide_in=u32(im, GUIDE_WORD))
    if (nxt['ep7_get_next'], nxt['ep7_def_next']) != (ap['ap_xg'], mv['mv_def']):
        raise SystemExit('facade +8 / +152 are not ap_xg / mv_def')
    if (nxt['ep7_cnt'], nxt['ep7_val'], nxt['ep7_av']) != (STOCK_CNT, STOCK_VAL, STOCK_AV):
        raise SystemExit('facade +24 / +28 / +36 are not stock')
    for w in (W_CNT, W_VAL, W_AV):
        if any(e['kind'] == '0x100' and not e['addr'].startswith('off:') and int(e['addr'], 16) < w + 4
               and w < int(e['addr'], 16) + len(e['new']) // 2 for e in spec['edits']):
            raise SystemExit(f'{w:#x} already edited')
    gd = nxt['ep7_guide_in']
    if im[gd - BASE:gd - BASE + 6] != bytes.fromhex('cff0f8fef493') or im[gd + 6 - BASE] != 0xfc:
        raise SystemExit(f'guide word -> {gd:#x}, not ap_gd (movm; add -12,sp; mov a0,a3; calls)')
    site = im[SET_SITE - BASE:SET_SITE + 7 - BASE]
    if site[0] != 0xdd or site[5:] != b'\xe0\x10' or SET_SITE + struct.unpack('<i', site[1:5])[0] != ap['ap_xs']:
        raise SystemExit(f'setter site {site.hex()} is not call ap_xs,[d2,d3,a2],16')
    if (le['k_step'], le['k_set']) != (K_STEP, K_SET) or im[K_STEP - BASE:K_STEP + 6 - BASE] != K_OLD:
        raise SystemExit('k_step bytes differ')
    if im[POLY_RET - 8 - BASE:POLY_RET - BASE] != POLY_CALL or le['p_chain'] != 0x601e3124:
        raise SystemExit('ed_poly GetValue call differs')
    if im[ap['ap_xb'] - BASE:ap['ap_xb'] + 6 - BASE] != bytes.fromhex('821efac289f9'):
        raise SystemExit('ap_xb entry differs')
    if u32(im, 0x60acb0dc) != 0x607fa129:
        raise SystemExit('facade vtable base differs')
    for a, b in ((SGET, None), (MANAGER, '87'), (FACADE, None)):
        if b and im[a - BASE:a - BASE + len(b) // 2].hex() != b:
            raise SystemExit(f'{a:#x} entry')
    check_claim(spec, stock, im)
    syms = dict(nxt, ep7_set_next=ap['ap_xs'], ep7_xb=ap['ap_xb'], ep7_sget=SGET, ep7_manager=MANAGER, ep7_facade=FACADE,
                ep7_k_set=K_SET, ep7_k_back=K_BACK)
    code, sy, lst = build_code(syms)
    LISTING[0] = lst
    spec['edits'].append(dict(kind='0x100', addr=hex(AT), expect=stock[AT - BASE:AT - BASE + len(code)].hex(), new=code.hex(),
                              source=SRC, why=f'extras_pages {version}: page remap front, split fields, list hooks, INFO step, '
                                              f'guide ({len(code)} B, sec-5 dead sdk-api handlers, claim {CLAIM[0]:#x}..{CLAIM[1]:#x})'))
    p32 = lambda v: struct.pack('<I', v)
    put(spec, stock, W_GET, p32(nxt['ep7_get_next']), p32(sy['xp_get']), 'facade +8 GetValue -> xp_get (then ap_xg)')
    put(spec, stock, W_DEF, p32(nxt['ep7_def_next']), p32(sy['xp_def']), 'facade +152 GetDefault -> xp_def (then mv_def)')
    put(spec, stock, W_CNT, p32(STOCK_CNT), p32(sy['xp_cnt']), 'facade +24 count -> xp_cnt (split colour: 13)')
    put(spec, stock, W_VAL, p32(STOCK_VAL), p32(sy['xp_val']), 'facade +28 value by index -> xp_val (split colour: -6..6)')
    put(spec, stock, W_AV, p32(STOCK_AV), p32(sy['xp_av']), 'facade +36 available -> xp_av (split colour: -6..6)')
    put(spec, stock, SET_SITE + 1, site[1:5], struct.pack('<i', sy['xp_set'] - SET_SITE), 'GUI setter call ap_xs -> call xp_set')
    put(spec, stock, GUIDE_WORD, p32(gd), p32(sy['xp_guide']), 'guide part word ap_gd -> xp_guide')
    put(spec, stock, K_STEP, K_OLD, b'\xdc' + struct.pack('<i', sy['xp_step'] - K_STEP) + b'\xcb', 'k_step -> jmp xp_step (Effects -> Colour & Light)')
    for w, v in KH.SUBCMD.items():
        put(spec, stock, w, p32(v), p32(sy['xp_ret0']), 'sdk sub-command word -> xp_ret0 (the shell reaches no claim code)')
    spec['extras_pages'] = dict(built_by=SRC, version=version, claim=[hex(CLAIM[0]), hex(CLAIM[1])], code=[hex(AT), len(code)],
                                heap=dict(sub=SUB, bits='bit 0 sub-page (0 Effects, 1 Colour & Light); bits 4..7 guide cursor override'),
                                pages=PAGES, map=MAP, split=dict(bytes=[62, 63], colour_list='-6..6 (0 Off, +n colour n-1, -n colour 12-n)',
                                                                 strength='-5..5', default_strength=3),
                                next={k: hex(v) for k, v in syms.items()}, symbols={k: hex(v) for k, v in sy.items() if k.startswith('xp_')})
    return spec


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--version', default='0.32')
    ap.add_argument('--listing', type=Path)
    a = ap.parse_args()
    spec = apply(json.loads(a.spec.read_text()), a.version)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(spec, indent=1))
    if a.listing:
        a.listing.write_text(LISTING[0])
    print(json.dumps({k: v for k, v in spec['extras_pages'].items() if k not in ('symbols', 'next')}))
