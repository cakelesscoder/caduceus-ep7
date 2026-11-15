#!/usr/bin/env python3
"""Japanese guide labels: when the camera's menu language is 日本語, Caduceus's own editor labels show in Japanese.
Layer after look_hw_ui (and so after i18n_zh, which patches/v032/build.py applies); offline. ja.s.in has the contract,
docs/I18N_JA.md the label table and the glyph substitutions. Same table format and matching rules as patches/i18n_zh.

  .venv/bin/python -I patches/i18n_ja/build.py <spec with look_hw_ui> --out <edits.json>
  (release chain: patches/v032/build.py ... --extra look_hw_ui=... --extra i18n_ja=patches/i18n_ja/build.py)

apply(spec, version) -> spec. Edits:
  - guide part word 0x6025aa98 (whoever holds it: lu_guide with look_hw_ui) -> ja_gd, which runs that chain first.
    ja_gd starts with the section-7 gate (as i18n_zh: section 7 not loaded -> jmp the stock guide part 0x60decbfc);
  - code + label table in a sec-5 claim of the dead `sdk api` shell handlers (CODE_SPACE_SURVEY section 2), inside a run
    into which no reference from outside the dead code points. Needs the three `sdk` sub-command words already cut.
The table is LABELS below, keyed by the English text our layers write (look_hw_ui writes English unless the table is
Chinese, so its labels are translated here too). Every Japanese character is checked against the font the camera loads
for Japanese (language value 0 -> string res 17 -> font res 51; tools/zh_glyphs.py --font 51).
"""
import argparse, copy, importlib.util, json, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SRC = 'patches/i18n_ja'


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


ZH = _load('ep7_zh_build_ja', ROOT / 'patches/i18n_zh/build.py')
XP, ST, KH, LE, B3 = ZH.XP, ZH.ST, ZH.KH, ZH.LE, ZH.B3
BASE, STOCK, GUIDE_WORD, BAD = ZH.BASE, ZH.STOCK, ZH.GUIDE_WORD, ZH.BAD
SECT, STOCK_GD = ZH.SECT, ZH.STOCK_GD
# Two sec-5 claims in the dead sdk-api handlers, each inside a run into which no reference from outside the dead code points
# (full scan of 0x607c9c20..0x607e87c5 on the v0.35a image, all four aliases + d16 / d32 call / calls / jmp, false
# positives included, so nothing needs pinning): 0x607e1add..0x607e21dc and 0x607ccf61..0x607cd660.
CLAIM = (0x607e1b00, 0x607e2100)          # code + whole-label table
TCLAIM = (0x607ccf62, 0x607cd660)         # token table (data only): the whole run less its first byte (2-aligned)
GUARD = 16
AT, TAT = CLAIM[0] + GUARD, TCLAIM[0] + GUARD
FONT_RES, STRING_RES, LANG_VALUE = 51, 17, 0
JA_134 = (0x30d0, 0x30fc)                 # string 134 of res 17 starts L"バー" (バージョン); no other table's 134 does

W, T, F = 1, 0, 2                         # whole label / token / token that also applies at the Film-page label start
# English (as our layers write it) -> (Japanese, flags). Vocabulary follows the camera's own Japanese strings where it has
# the term (彩度, 階調, 調色, 効果, 静止画, 粒状, 標準, 強/中/弱, 明部/暗部, マゼンタ, シアン, 黄緑, オート);
# 'Off' stays 'Off' as in the camera's own Japanese UI. Substitutions for missing glyphs: docs/I18N_JA.md section 3.
LABELS = {
    # whole labels
    'Stock': ('標準', W), 'Custom': ('カスタム', W),
    'Extras: 1-5 only': ('詳細設定: 1-5のみ', W), 'Extras: 1-9 only': ('詳細設定: 1-9のみ', W),
    'Extras: 1-10 only': ('詳細設定: 1-10のみ', W), 'Extras: 1-11 only': ('詳細設定: 1-11のみ', W),
    'Extras: no All': ('詳細設定: 全色なし', W),
    'Effects: 1-7': ('効果: 1-7', W), 'Colour: 1-8': ('カラー: 1-8', W), 'Colour: 1-11': ('カラー: 1-11', W),
    'Split: COLOR 1-4': ('調色: COLOR 1-4', W), 'Curve: COLOR 1-4': ('階調: COLOR 1-4', W),
    'Mix: COLOR 1-4': ('配色: COLOR 1-4', W),
    'Grain: stills': ('粒状: 静止画のみ', W), 'Glow: stills': ('グロー: 静止画のみ', W),
    'Art: stills': ('アート: 静止画のみ', W), 'Halo: stills': ('ハロー: 静止画のみ', W),
    # tokens (matched longest first, at word starts)
    'Saturation': ('彩度', T), 'Hue': ('色合い', T), 'Light': ('明度', T), 'All': ('全色', T),
    'Film': ('フィルム', F), 'Extras': ('詳細設定', T),
    'Grain': ('粒状', T), 'Low': ('弱', T), 'Medium': ('中', T), 'Med': ('中', T),
    'Grain High': ('粒状 強', T), 'Halo High': ('ハロー 強', T),
    'Art': ('アート', T), 'Star Light': ('スターライト', T), 'Pin Hole': ('ピンホール', T), 'Blur': ('ぼかし', T),
    'Glow': ('グロー', T), 'Clarity': ('鮮明度', T), 'Clarity/Glow': ('鮮明度/グロー', T),
    'Amber': ('アンバー', T), 'Amber/Blue': ('アンバー/ブルー', T), 'Green/Mag.': ('グリーン/マゼンタ', T),
    'WB Blue': ('WB ブルー', T), 'WB Green': ('WB グリーン', T),          # WB axis: the camera's A / B, G / M words
    'WB Amber/Blue': ('WB アンバー/ブルー', T), 'WB Green/Mag.': ('WB グリーン/マゼンタ', T),
    'Blacks': ('黒レベル', T), 'Whites': ('白レベル', T), 'NR': ('ノイズ低減', T), 'Camera': ('本体設定', T),
    'Std': ('標準', T), 'VigFix': ('減光補正', T), 'Sharp': ('シャープ', T), 'Halo': ('ハロー', T),
    'Shadow': ('暗部', T), 'High': ('明部', T),          # split tone: the camera's own Hi. & Sh. words (明部&暗部)
    '5 Shadow': ('5 暗部色', T), '6 Shadow': ('6 暗部強度', T),                  # colour vs strength
    '7 High': ('7 明部色', T), '8 High': ('8 明部強度', T),
    'Yellow': ('黄', T), 'Orange': ('オレンジ', T), 'Or-Red': ('赤オレンジ', T), 'Red': ('赤', T),
    'Magenta': ('マゼンタ', T), 'Violet': ('紫', T), 'Blue': ('青', T), 'Bl-Cyan': ('青シアン', T),
    'Cyan': ('シアン', T), 'Gr-Cyan': ('緑シアン', T), 'Green': ('緑', T), 'Yl-Green': ('黄緑', T),
    # look_hw_ui (Colour & Light 9 Curve / 10 Mix / 11 Strength and their values)
    'Curve': ('階調', T), 'Mix': ('配色', T), 'Strength': ('配色強度', T),
    'Standard': ('標準', T), 'Auto': ('オート', T), 'Pale': ('ペール', T), 'Curve Light': ('階調 ライト', T),
    'Pop': ('ポップ', T), 'Flat': ('フラット', T),
    'From look': ('ルックのまま', T), 'Warm film': ('暖色フィルム', T), 'Cool sep.': ('クール分離', T),
    'Muted': ('穏やか', T), 'Punchy': ('鮮やか', T),
}


def u32(im, a):
    return struct.unpack_from('<I', im, a - BASE)[0]


def glyphs():
    sys.path.insert(0, str(ROOT / 'tools'))
    import zh_glyphs
    return zh_glyphs.available(res=FONT_RES)


def entries(labels=LABELS):
    """-> ordered [(en, ja, flags)]: whole entries first (table order), then tokens longest first."""
    w = [(e, j, f) for e, (j, f) in labels.items() if f & W]
    t = sorted(((e, j, f) for e, (j, f) in labels.items() if not f & W), key=lambda x: (-len(x[0]), x[0]))
    return w + t


def table_bytes(labels=LABELS, part=None):
    """part None: both tables' records (for sizes); 'whole' / 'tok': that table, ended by u16 0."""
    out = bytearray()
    for e, j, f in entries(labels):
        if part is not None and bool(f & W) != (part == 'whole'):
            continue
        if not e.isascii() or not 0 < len(e) <= 32 or not 0 < len(j) <= 32 or '\0' in e + j or f not in (W, T, F):
            raise SystemExit(f'label {e!r} -> {j!r}: ASCII English and 1..32 units each')
        out += struct.pack('<3H', len(e), len(j), f) + e.encode('utf-16-le') + j.encode('utf-16-le')
    return bytes(out + b'\0\0')


def check_labels(labels=LABELS):
    have = glyphs()
    miss = {e: ''.join(c for c in j if c not in have and c != ' ') for e, (j, _) in labels.items()}
    miss = {e: m for e, m in miss.items() if m}
    if miss:
        raise SystemExit(f'no glyph in font res {FONT_RES}: {miss}')


def translate(text, labels=LABELS, film=False):
    """Host model of ja_gd (same rules), for the verifier and the doc."""
    ents = entries(labels)
    for e, j, f in ents:
        if f & W and text == e:
            return j
    out, i = [], 0
    while i < len(text) and i < 32:
        hit = None
        if i == 0 or (not film and text[i - 1] in ' /'):
            for e, j, f in ents:
                if not f & W and (not film or f & F) and text.startswith(e, i) \
                        and (i + len(e) == len(text) or text[i + len(e)] in ' /:'):
                    hit = (e, j)
                    break
        if hit:
            out += list(hit[1]); i += len(hit[0])
        else:
            out.append(text[i]); i += 1
    return ''.join(out)[:32]


def check_claims(spec, stock, im):
    for c in (CLAIM, TCLAIM):
        check_claim(spec, stock, im, c)


def check_claim(spec, stock, im, CLAIM):
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
    bad = _refs(im, CLAIM[0], CLAIM[1], off5)
    if bad:
        raise SystemExit(f'reference into the claim: {[(k, hex(a)) for k, a in bad[:4]]}')


def _refs(im, lo, hi, off5):
    """abs32 (four aliases) + d16 / d32 call / calls / jmp into [lo, hi) from outside the dead ranges, no pins (crash_log refs)."""
    CL = _load('ep7_cl_build_ja', ROOT / 'patches/crash_log/build.py')
    return [(k, a) for k, a in CL.refs(im, lo, hi, off5, allow=list(KH.DEAD))]


def build_code(chain):
    s = LE.sub(probe=False)
    sub = dict(state=s['state'], lim=s['lim'], pool=s['pool'], bmagic=s['bmagic'], emark=s['emark'], emagic=s['emagic'],
               axis=s['axis'], sect=hex(SECT), stock_gd=hex(STOCK_GD), s0=hex(JA_134[0]), s1=hex(JA_134[1]))
    tb = table_bytes(part='whole')
    sub['table'] = '\n'.join(' .byte ' + ','.join(str(x) for x in tb[i:i + 16]) for i in range(0, len(tb), 16))
    src = B3.subst((HERE / 'ja.s.in').read_text(), sub)
    code, lst, sy, _ = B3.assemble(src, AT, dict(ep7_guide_in=chain, ep7_stock_gd=STOCK_GD, ep7_tok=TAT))
    if sy['ja_gd'] != AT or AT + len(code) > CLAIM[1] - GUARD:
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
    if tg != {('calls', chain), ('call', sy['z_adv']), ('jmp', STOCK_GD)}:
        raise SystemExit(f'call targets {sorted((o, hex(t)) for o, t in tg)}')
    head = [(op, args) for _, op, args in ins[:4]]
    if head[0] != ('btst', f'64,({SECT:#x})') or head[1] != ('bne', hex(sy['ja_go'])) or head[2] != ('jmp', hex(STOCK_GD)) \
            or head[3] != ('movm', '[d2,d3,a2,a3],(sp)') or ins[3][0] != sy['ja_go']:
        raise SystemExit(f'ja_gd gate: {head}')
    return code, sy, lst


def apply(spec, version='0.35a'):
    stock = STOCK.read_bytes()
    spec = copy.deepcopy(spec)
    if 'i18n_ja' in spec:
        raise SystemExit('i18n_ja already applied')
    if 'look_hw_ui' not in spec:
        raise SystemExit('i18n_ja goes after look_hw_ui (it translates its labels)')
    check_labels()
    im = ST.img_of(spec, stock)
    chain = u32(im, GUIDE_WORD)
    if XP.u32(stock, GUIDE_WORD) != STOCK_GD or stock[STOCK_GD - BASE:STOCK_GD - BASE + 2] != bytes.fromhex('cff0'):
        raise SystemExit('stock guide word / part differ')
    if chain != int(spec['look_hw_ui']['symbols']['lu_guide'], 16):
        raise SystemExit(f'guide word -> {chain:#x}, not look_hw_ui lu_guide (a guide-word layer after look_hw_ui?)')
    check_claims(spec, stock, im)
    code, sy, lst = build_code(chain)
    tok = table_bytes(part='tok')
    if TAT + len(tok) > TCLAIM[1] - GUARD:
        raise SystemExit(f'token table {len(tok)} B does not fit {TCLAIM[1] - GUARD - TAT}')
    spec['edits'].append(dict(kind='0x100', addr=hex(AT), expect=stock[AT - BASE:AT - BASE + len(code)].hex(), new=code.hex(),
                              source=SRC, why=f'i18n_ja {version}: ja_gd + {len(LABELS)}-entry Japanese label table ({len(code)} B, '
                                              f'sec-5 dead sdk-api handlers, claim {CLAIM[0]:#x}..{CLAIM[1]:#x})'))
    spec['edits'].append(dict(kind='0x100', addr=hex(TAT), expect=stock[TAT - BASE:TAT - BASE + len(tok)].hex(), new=tok.hex(),
                              source=SRC, why=f'i18n_ja {version}: Japanese token table ({len(tok)} B, '
                                              f'sec-5 dead sdk-api handlers, claim {TCLAIM[0]:#x}..{TCLAIM[1]:#x})'))
    old, new = struct.pack('<I', chain), struct.pack('<I', sy['ja_gd'])
    for e in spec['edits']:                    # the word lives in an earlier layer's edit: update it in place
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            a, n = int(e['addr'], 16), len(e['new']) // 2
            if a <= GUIDE_WORD and GUIDE_WORD + 4 <= a + n:
                b = bytearray.fromhex(e['new'])
                if b[GUIDE_WORD - a:GUIDE_WORD - a + 4] != old:
                    raise SystemExit('guide word edit differs')
                b[GUIDE_WORD - a:GUIDE_WORD - a + 4] = new; e['new'] = b.hex()
                e['why'] += ' [i18n_ja: guide part word -> ja_gd]'
                break
            if a < GUIDE_WORD + 4 and GUIDE_WORD < a + n:
                raise SystemExit('guide word straddles an edit')
    else:
        raise SystemExit('no edit holds the guide word')
    spec['i18n_ja'] = dict(built_by=SRC, version=version, claims=[[hex(CLAIM[0]), hex(CLAIM[1])], [hex(TCLAIM[0]), hex(TCLAIM[1])]],
                           code=[hex(AT), len(code)], tokens=[hex(TAT), len(tok)], chain=hex(chain), labels=len(LABELS),
                           lang_check=dict(value=LANG_VALUE, string_res=STRING_RES, font_res=FONT_RES, bank=hex(ZH.LANG_BANK),
                                           tables=hex(ZH.STR_TABLES), string=134, starts=[hex(x) for x in JA_134]),
                           symbols={k: hex(v) for k, v in sy.items() if k.startswith(('ja_', 'z_', 'w_', 't_'))})
    return spec


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--version', default='0.35a')
    a = ap.parse_args()
    spec = apply(json.loads(a.spec.read_text()), a.version)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(spec, indent=1))
    print(json.dumps({k: v for k, v in spec['i18n_ja'].items() if k != 'symbols'}))
