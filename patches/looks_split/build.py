#!/usr/bin/env python3
"""Split toning in LOOKS.BIN (v0.32). Layer on v0.32 (plugins=False) after split_tone and extras_pages, before i18n_zh.
Offline. ls.s.in has the contract; docs/PACKS.md "Split tone on the E-P7" the format.

  .venv/bin/python -I patches/looks_split/build.py <v0.32 spec> --out <edits.json>

Record +61 Shadows / +62 Highlights = slot +62/+63 packing, valid only when the name ends by +60 (at most 12
characters). Edits:
  - fm_load `call fm_check` 0x6143a4ed (5 B) -> `jmp ls_chk` (stash + clean + CRC, then the real fm_check, jmp back);
  - fm_load `mov 2560,d0` (the L malloc) -> 2640 (stash at L+2560..2631, past the 2560 B the Movie / AP pages copy);
  - sl_pick's tail `jmp fm_post` 0x601e3a16 -> `jmp ls_pick` (slot +62/+63 on a Film pick, then fm_post);
  - code in a sec-5 claim of the dead `sdk api` shell handlers (CODE_SPACE_SURVEY §2), after i18n_zh's claim.
"""
import argparse, copy, importlib.util, json, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SRC = 'patches/looks_split'


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


XP = _load('ep7_xp_build_ls', ROOT / 'patches/extras_pages/build.py')
FB = _load('ep7_fmv2_build_ls', ROOT / 'patches/film_menu_v2/build.py')
ST, KH, B3 = XP.ST, XP.KH, XP.B3
BASE, STOCK = XP.BASE, XP.STOCK
BAD = XP.BAD

CLAIM = (0x607d5500, 0x607d5900)      # sec 5 dead sdk-api handlers; inside the hit-free run 0x607d54de..0x607d59cd (scan
GUARD = 16                            # of 0x607c9c20..0x607e87c5, instruction-byte false positives included), after
AT = CLAIM[0] + GUARD                 # i18n_zh's 0x607d4200..0x607d5000
FM_CALL, FM_AFTER = 0x6143a4ed, 0x6143a4f2     # fm_load: call fm_check,[d2,d3,a2,a3],20 (cd b9 00 f0 14)
FM_CHECK, FM_CRC = 0x6143a5a6, 0x6143a688
FM_LOAD = 0x6143a410
MALLOC = 0x60022782
PICK_TAIL, FM_POST, SL_PICK = 0x601e3a16, 0x601e37b4, 0x601e39aa
AP_P = ST.AP_P
L_OLD, L_NEW = FB.L_SIZE, 2640
STASH, TAG, TAGP = 2568, 2560, 2564
WMAGIC = struct.unpack('<I', b'EP7W')[0]
LLIM = FB.POOL2_END - FB.POOL2 - L_NEW + 1
SYMS = dict(ep7_fm_check=FM_CHECK, ep7_fm_crc=FM_CRC, ep7_fm_after=FM_AFTER, ep7_fm_post=FM_POST, ep7_ap_p=AP_P)
STORES = {'mov d0,(2560,a3)', 'mov d0,(16,a3)', 'mov a2,(2564,a3)', 'movbu d0,(a0)', 'movbu d0,(1,a0)',
          'movbu d0,(61,a1)', 'movbu d0,(62,a1)', 'movbu d0,(94,a1)', 'movbu d1,(95,a1)'}


def u32(b, a):
    return struct.unpack_from('<I', b, a - BASE)[0]


def check_claim(spec, stock, im):
    lo5, hi5, off5 = KH.sec(stock, 5)
    if not (lo5 <= CLAIM[0] and CLAIM[1] <= hi5 and KH.DEAD[1][0] <= CLAIM[0] and CLAIM[1] <= KH.DEAD[1][1]):
        raise SystemExit('claim not inside the dead handler range of section 5')
    for e in spec['edits']:
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            a, n = int(e['addr'], 16), len(e['new']) // 2
            if a < CLAIM[1] and CLAIM[0] < a + n:
                raise SystemExit(f'claim overlaps edit {e["addr"]}')
    if im[CLAIM[0] - BASE:CLAIM[1] - BASE] != stock[CLAIM[0] - BASE:CLAIM[1] - BASE]:
        raise SystemExit('claim not stock')
    if CLAIM[0] <= (KH.DOUBLE_K - off5) & 0xffffffff < CLAIM[1]:
        raise SystemExit('the 0x40e4ab40 double constant aliases into the claim')
    for w, v in KH.SUBCMD.items():
        if u32(im, w) == v:
            raise SystemExit(f'sdk sub-command word {w:#x} still stock: apply extras_pages first')
    KH.pin_fp(stock)
    KH.FALSE_POS.update(XP.PINS)
    bad = KH.scan(im, CLAIM[0], CLAIM[1], off5, KH.DEAD)
    if bad:
        raise SystemExit(f'reference into the claim: {[(k, hex(a)) for k, a in bad[:4]]}')


def malloc_site(im):
    """The one `mov 2560,d0` + `call malloc` in fm_load before the fm_check call."""
    pat = b'\x2c' + struct.pack('<H', L_OLD) + b'\xdd'
    hits = [i for i in range(FM_LOAD, FM_CALL) if im[i - BASE:i - BASE + 4] == pat]
    if len(hits) != 1:
        raise SystemExit(f'fm_load malloc size: {len(hits)} sites')
    c = hits[0] + 3
    if c + struct.unpack_from('<i', im, c + 1 - BASE)[0] != MALLOC:
        raise SystemExit('fm_load: the 2560 is not the malloc argument')
    return hits[0]


def check_sites(spec, im):
    if im[FM_CALL - BASE:FM_CALL + 5 - BASE] != b'\xcd' + struct.pack('<h', FM_CHECK - FM_CALL) + b'\xf0\x14':
        raise SystemExit('fm_load call fm_check differs')
    if im[FM_CHECK - BASE:FM_CHECK + 2 - BASE] != b'\xfc\xdd' or im[FM_CRC - BASE:FM_CRC + 2 - BASE] != b'\xf0\x48':
        raise SystemExit('fm_check / fm_crc moved')
    if im[FM_AFTER - BASE:FM_AFTER + 2 - BASE] != b'\xa0\x00':
        raise SystemExit('fm_load after fm_check is not cmp 0,d0')
    if spec['v025']['symbols']['sl_pick'] != hex(SL_PICK):
        raise SystemExit('sl_pick moved')
    if im[PICK_TAIL - BASE:PICK_TAIL + 5 - BASE] != b'\xdc' + struct.pack('<i', FM_POST - PICK_TAIL):
        raise SystemExit('sl_pick tail is not jmp fm_post')
    if spec['ap_custom']['symbols'].get('ap_P') != hex(AP_P) or im[AP_P - BASE:AP_P + 3 - BASE] != bytes.fromhex('fcaec2'):
        raise SystemExit('ap_P moved')
    if (FB.OFF['ltag'], FB.OFF['lback'], FB.OFF['n'], FB.OFF['pos'], FB.OFF['snap'], FB.OFF['snaps']) != (2112, 2116, 2120, 2121, 2125, 2132):
        raise SystemExit('L layout differs')
    if not (FB.OFF['stage'] + 81 <= TAG and STASH + 64 <= L_NEW <= 16384):
        raise SystemExit('stash does not fit L')


def build_code():
    sub = dict(lmagic=hex(FB.LMAGIC), fmagic=hex(FB.FMAGIC), wmagic=hex(WMAGIC), npool=hex(-FB.POOL2 & 0xffffffff), llim=hex(LLIM))
    src = B3.subst((HERE / 'ls.s.in').read_text(), sub)
    code, lst, sy, _ = B3.assemble(src, AT, SYMS)
    if sy['ls_chk'] != AT or AT + len(code) > CLAIM[1] - GUARD:
        raise SystemExit(f'{len(code)} B does not fit')
    ins = B3.disasm(code, AT, sy['ls_end'])
    if any(op in BAD for _, op, _ in ins) or any(op.startswith('.') or op == '(bad)' for _, op, _ in ins):
        raise SystemExit('forbidden or undecodable instruction')
    if any(code[a - AT] == 0xfb for a, _, _ in ins):
        raise SystemExit('fb-prefixed form')
    for a, txt, kd, _ in B3.store_audit(ins):
        if kd == 'abs' or (kd == 'ind' and txt not in STORES):
            raise SystemExit(f'store at {a:#x}: {txt} ({kd})')
    tg = {(op, int(args.split(',')[0], 16)) for _, op, args in ins if op in ('call', 'calls', 'jmp') and args.startswith('0x')}
    tg = {(o, t) for o, t in tg if not (o == 'jmp' and AT <= t < sy['ls_end'])}     # long internal branches
    want = {('call', sy['ls_sc']), ('call', FM_CHECK), ('jmp', FM_AFTER), ('call', FM_CRC), ('call', sy['ls_pk']),
            ('jmp', FM_POST), ('call', AP_P)}
    if tg != want:
        raise SystemExit(f'call targets {sorted((o, hex(t)) for o, t in tg)}')
    return code, sy, lst


def apply(spec, version='0.32'):
    stock = STOCK.read_bytes()
    spec = copy.deepcopy(spec)
    if 'looks_split' in spec:
        raise SystemExit('looks_split already applied')
    if 'split_tone' not in spec or 'extras_pages' not in spec:
        raise SystemExit('needs split_tone and extras_pages')
    if 'i18n_zh' in spec:
        raise SystemExit('apply before i18n_zh')
    im = ST.img_of(spec, stock)
    check_sites(spec, im)
    ms = malloc_site(im)
    check_claim(spec, stock, im)
    code, sy, lst = build_code()
    spec['edits'].append(dict(kind='0x100', addr=hex(AT), expect=stock[AT - BASE:AT - BASE + len(code)].hex(), new=code.hex(),
                              source=SRC, why=f'looks_split {version}: ls_chk / ls_sc / ls_pick / ls_pk ({len(code)} B, '
                                              f'sec-5 dead sdk-api handlers, claim {CLAIM[0]:#x}..{CLAIM[1]:#x})'))
    ST.put(spec, stock, FM_CALL, im[FM_CALL - BASE:FM_CALL + 5 - BASE], b'\xdc' + struct.pack('<i', sy['ls_chk'] - FM_CALL),
           'looks_split: fm_load call fm_check -> jmp ls_chk')
    ST.put(spec, stock, ms + 1, struct.pack('<H', L_OLD), struct.pack('<H', L_NEW), f'looks_split: L malloc {L_OLD} -> {L_NEW} (split stash)')
    ST.put(spec, stock, PICK_TAIL + 1, struct.pack('<i', FM_POST - PICK_TAIL), struct.pack('<i', sy['ls_pick'] - PICK_TAIL),
           'looks_split: sl_pick tail jmp fm_post -> jmp ls_pick')
    spec['looks_split'] = dict(built_by=SRC, version=version, claim=[hex(CLAIM[0]), hex(CLAIM[1])], code=[hex(AT), len(code)],
                               sites=dict(fm_check_call=hex(FM_CALL), l_malloc=hex(ms), pick_tail=hex(PICK_TAIL)),
                               record=dict(shadows=61, highlights=62, name_end=60), slot=dict(shadows=62, highlights=63),
                               L=dict(size=L_NEW, tag=TAG, magic='EP7W', back=TAGP, stash=STASH),
                               symbols={k: hex(v) for k, v in sy.items() if k.startswith(('ls_', 's_'))})
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
        a.listing.write_text(build_code()[2])
    print(json.dumps({k: v for k, v in spec['looks_split'].items() if k != 'symbols'}))
