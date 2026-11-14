#!/usr/bin/env python3
"""Simplified Chinese guide labels (issue #46). Layer on v0.32 (plugins=False) after extras_pages; offline. zh.s.in has
the contract, docs/I18N_ZH.md the research and the label table.

  .venv/bin/python -I patches/i18n_zh/build.py <v0.32 spec> --out <edits.json>

apply(spec, version) -> spec. Edits:
  - guide part word 0x6025aa98 (whoever holds it: xp_guide in v0.32) -> i18n_gd, which runs that chain first;
  - code + label table in a sec-5 claim of the dead `sdk api` shell handlers (CODE_SPACE_SURVEY §2), after
    extras_pages' claim. Needs the three `sdk` sub-command words already cut (extras_pages / keyhook do it).
The table is LABELS below, keyed by the English text our layers write. Every Chinese character is checked against the
font the camera loads for Simplified Chinese (tools/zh_glyphs.py, font resource 36).
"""
import argparse, copy, importlib.util, json, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SRC = 'patches/i18n_zh'


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


XP = _load('ep7_xp_build_zh', ROOT / 'patches/extras_pages/build.py')
ST, KH, LE, B3 = XP.ST, XP.KH, XP.LE, XP.B3
BASE, STOCK = XP.BASE, XP.STOCK
GUIDE_WORD = XP.GUIDE_WORD
CLAIM = (0x607d4200, 0x607d5000)          # sec 5 dead sdk-api handlers, past extras_pages' 0x607c9420..0x607c9c20. The
# largest run of the shell range 0x607c9c20.. with no abs32 / rel hit into it (instruction-byte false positives included,
# so nothing needs pinning): 0x607d41f9..0x607d50dd, 3812 B (also clear of the 0x40e4ab40 double alias 0x607cab40)
GUARD = 16
AT = CLAIM[0] + GUARD
BAD = XP.BAD
LANG_BANK, STR_TABLES, ZH_134 = 0x61fb2818, 0x61fc1530, (0x56fa, 0x4ef6)   # stock getter 0x60d10bf2 / 0x60d10c09; L"固件"

# English (as our layers write it) -> (Simplified Chinese, whole label only?). '?' in the doc = native review wanted.
LABELS = {
    # whole labels
    'Stock': ('标准', True), 'Custom': ('自定义', True),
    'Extras: 1-5 only': ('更多设置: 仅 1-5', True), 'Extras: 1-9 only': ('更多设置: 仅 1-9', True),
    'Extras: 1-10 only': ('更多设置: 仅 1-10', True), 'Extras: 1-11 only': ('更多设置: 仅 1-11', True),
    'Extras: no All': ('更多设置: 全部不可用', True),
    'Effects: 1-7': ('效果: 1-7', True), 'Colour: 1-8': ('色彩: 1-8', True), 'Split: COLOR 1-4': ('分离色调: COLOR 1-4', True),
    'Grain: stills': ('颗粒: 仅照片', True), 'Glow: stills': ('柔和: 仅照片', True),
    'Art: stills': ('艺术: 仅照片', True), 'Halo: stills': ('光环: 仅照片', True),
    # tokens (matched longest first, at word starts)
    'Saturation': ('饱和度', False), 'Hue': ('色相', False), 'Light': ('亮度', False), 'All': ('全部', False),
    'Film': ('胶片', False), 'Extras': ('更多设置', False),
    'Grain': ('颗粒', False), 'Off': ('关', False), 'Low': ('低', False), 'Medium': ('中', False), 'Med': ('中', False),
    'Grain High': ('颗粒 高', False), 'Halo High': ('光环 高', False),
    'Art': ('艺术', False), 'Star Light': ('星光', False), 'Pin Hole': ('针孔', False), 'Blur': ('模糊', False),
    'Glow': ('柔和', False), 'Clarity': ('清晰度', False), 'Clarity/Glow': ('清晰/柔和', False),
    'WB': ('白平衡', False), 'Amber': ('黄', False), 'Amber/Blue': ('黄/蓝', False),
    'Green/Mag.': ('绿/品红', False),
    'Blacks': ('黑色色阶', False), 'Whites': ('白色色阶', False), 'NR': ('降噪', False), 'Camera': ('默认', False),
    'Std': ('标准', False), 'VigFix': ('暗角校正', False), 'Sharp': ('锐化', False), 'Halo': ('光环', False),
    'Shadow': ('阴影', False), 'High': ('高光', False),
    '5 Shadow': ('5 阴影色调', False), '6 Shadow': ('6 阴影强度', False),       # #46: colour vs strength
    '7 High': ('7 高光色调', False), '8 High': ('8 高光强度', False),
    'Yellow': ('黄', False), 'Orange': ('橙', False), 'Or-Red': ('橙红', False), 'Red': ('红', False),
    'Magenta': ('品红', False), 'Violet': ('紫', False), 'Blue': ('蓝', False), 'Bl-Cyan': ('蓝青', False),
    'Cyan': ('青', False), 'Gr-Cyan': ('绿青', False), 'Green': ('绿', False), 'Yl-Green': ('黄绿', False),
}


def u32(im, a):
    return struct.unpack_from('<I', im, a - BASE)[0]


def glyphs():
    sys.path.insert(0, str(ROOT / 'tools'))
    import zh_glyphs
    return zh_glyphs.available()


def entries(labels=LABELS):
    """-> ordered [(en, zh, whole)]: whole entries first (table order), then tokens longest first."""
    w = [(e, z, 1) for e, (z, wh) in labels.items() if wh]
    t = sorted(((e, z, 0) for e, (z, wh) in labels.items() if not wh), key=lambda x: (-len(x[0]), x[0]))
    return w + t


def table_bytes(labels=LABELS):
    out = bytearray()
    for e, z, f in entries(labels):
        if not e.isascii() or not 0 < len(e) <= 32 or not 0 < len(z) <= 32 or '\0' in e + z:
            raise SystemExit(f'label {e!r} -> {z!r}: ASCII English and 1..32 units each')
        out += struct.pack('<3H', len(e), len(z), f) + e.encode('utf-16-le') + z.encode('utf-16-le')
    return bytes(out + b'\0\0')


def check_labels(labels=LABELS):
    have = glyphs()
    miss = {e: ''.join(c for c in z if c not in have and c != ' ') for e, (z, _) in labels.items()}
    miss = {e: m for e, m in miss.items() if m}
    if miss:
        raise SystemExit(f'no glyph in font res 36: {miss}')


def translate(text, labels=LABELS, film=False):
    """Host model of i18n_gd (same rules), for the verifier and the doc."""
    ents = entries(labels)
    for e, z, f in ents:
        if f and text == e:
            return z
    if film:
        return text
    out, i = [], 0
    while i < len(text) and i < 32:
        hit = None
        if i == 0 or text[i - 1] in ' /':
            for e, z, f in ents:
                if not f and text.startswith(e, i) and (i + len(e) == len(text) or text[i + len(e)] in ' /:'):
                    hit = (e, z)
                    break
        if hit:
            out += list(hit[1]); i += len(hit[0])
        else:
            out.append(text[i]); i += 1
    return ''.join(out)[:32]


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
            raise SystemExit(f'sdk sub-command word {w:#x} still stock: the shell can reach the claim (apply extras_pages first)')
    KH.pin_fp(stock)
    KH.FALSE_POS.update(XP.PINS)
    bad = KH.scan(im, CLAIM[0], CLAIM[1], off5, KH.DEAD)
    if bad:
        raise SystemExit(f'reference into the claim: {[(k, hex(a)) for k, a in bad[:4]]}')


def build_code(chain):
    s = LE.sub(probe=False)
    sub = dict(state=s['state'], lim=s['lim'], pool=s['pool'], bmagic=s['bmagic'], emark=s['emark'], emagic=s['emagic'],
               axis=s['axis'])
    tb = table_bytes()
    sub['table'] = '\n'.join(' .byte ' + ','.join(str(x) for x in tb[i:i + 16]) for i in range(0, len(tb), 16))
    src = B3.subst((HERE / 'zh.s.in').read_text(), sub)
    code, lst, sy, _ = B3.assemble(src, AT, dict(ep7_guide_in=chain))
    if sy['i18n_gd'] != AT or AT + len(code) > CLAIM[1] - GUARD:
        raise SystemExit(f'{len(code)} B does not fit')
    if code[sy['z_tab'] - AT:sy['z_tab'] - AT + len(tb)] != tb or sy['z_tab'] % 2:
        raise SystemExit('table')
    ins = B3.disasm(code, AT, sy['z_tab'])
    if any(op in BAD for _, op, _ in ins) or any(op.startswith('.') or op == '(bad)' for _, op, _ in ins):
        raise SystemExit('forbidden or undecodable instruction')
    if any(code[a - AT] == 0xfb for a, _, _ in ins):
        raise SystemExit('fb-prefixed form')
    for a, txt, kd, _ in B3.store_audit(ins):
        if kd == 'abs' or (kd == 'ind' and txt not in ('movhu d0,(a1)', 'movhu d0,(a0)')):
            raise SystemExit(f'store at {a:#x}: {txt} ({kd})')
    tg = {(op, int(args.split(',')[0], 16)) for _, op, args in ins if op in ('call', 'calls', 'jmp') and args.startswith('0x')}
    tg = {(o, t) for o, t in tg if not (o == 'jmp' and AT <= t < sy['z_tab'])}     # long internal branches
    if tg != {('calls', chain), ('call', sy['z_adv'])}:
        raise SystemExit(f'call targets {sorted((o, hex(t)) for o, t in tg)}')
    return code, sy, lst


def apply(spec, version='0.32'):
    stock = STOCK.read_bytes()
    spec = copy.deepcopy(spec)
    if 'i18n_zh' in spec:
        raise SystemExit('i18n_zh already applied')
    check_labels()
    im = ST.img_of(spec, stock)
    chain = u32(im, GUIDE_WORD)
    if chain == XP.u32(stock, GUIDE_WORD) or im[chain - BASE:chain - BASE + 2] != bytes.fromhex('cff0'):
        raise SystemExit(f'guide word -> {chain:#x}: not a layer chain entry (movm [d2,d3,a2,a3],(sp))')
    check_claim(spec, stock, im)
    code, sy, lst = build_code(chain)
    spec['edits'].append(dict(kind='0x100', addr=hex(AT), expect=stock[AT - BASE:AT - BASE + len(code)].hex(), new=code.hex(),
                              source=SRC, why=f'i18n_zh {version}: i18n_gd + {len(LABELS)}-entry label table ({len(code)} B, '
                                              f'sec-5 dead sdk-api handlers, claim {CLAIM[0]:#x}..{CLAIM[1]:#x})'))
    old, new = struct.pack('<I', chain), struct.pack('<I', sy['i18n_gd'])
    for e in spec['edits']:                    # the word lives in an earlier layer's edit: update it in place
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            a, n = int(e['addr'], 16), len(e['new']) // 2
            if a <= GUIDE_WORD and GUIDE_WORD + 4 <= a + n:
                b = bytearray.fromhex(e['new'])
                if b[GUIDE_WORD - a:GUIDE_WORD - a + 4] != old:
                    raise SystemExit('guide word edit differs')
                b[GUIDE_WORD - a:GUIDE_WORD - a + 4] = new; e['new'] = b.hex()
                e['why'] += ' [i18n_zh: guide part word -> i18n_gd]'
                break
            if a < GUIDE_WORD + 4 and GUIDE_WORD < a + n:
                raise SystemExit('guide word straddles an edit')
    else:
        raise SystemExit('no edit holds the guide word')
    spec['i18n_zh'] = dict(built_by=SRC, version=version, claim=[hex(CLAIM[0]), hex(CLAIM[1])], code=[hex(AT), len(code)],
                           chain=hex(chain), labels=len(LABELS), lang_check=dict(bank=hex(LANG_BANK), tables=hex(STR_TABLES),
                                                                                  string=134, starts=[hex(x) for x in ZH_134]),
                           symbols={k: hex(v) for k, v in sy.items() if k.startswith(('i18n_', 'z_', 'w_', 't_'))})
    return spec


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--version', default='0.32')
    a = ap.parse_args()
    spec = apply(json.loads(a.spec.read_text()), a.version)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(spec, indent=1))
    print(json.dumps({k: v for k, v in spec['i18n_zh'].items() if k != 'symbols'}))
