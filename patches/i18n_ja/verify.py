#!/usr/bin/env python3
"""i18n_ja checks (emulator, real code from the built image). Offline. Minimal + anti-brick.

  .venv/bin/python -I patches/i18n_ja/verify.py <spec without i18n_ja> <spec with i18n_ja> [package dir] [--v034 releases/v0.34/edits.json]

Every run enters through the real guide part word 0x6025aa98 (it now holds ja_gd) with the language's string 134 in a
fake string table: ja L"バージョン", zh L"固件", en L"Firmware".
  Z  chain labels: ja_gd -> the real lu_guide (ALL word set, so it keeps the chain's text) -> the real i18n_gd -> a mock at
     i18n_zh's old chain entry (xp_guide) that writes the case's label (kind 5 / 4), d0 = 0x1234. Japanese: the label is
     build.translate (zero-padded to 33 units; Film page: whole entries and the "Film" prefix only); Chinese: i18n_zh's
     translation, untouched by ja_gd; English, kind 4, no table: exactly what the mock wrote. d0 = the mock's, d2 d3 a2 a3
     sp kept, nothing written above the caller's sp.
  L  look_hw_ui labels: ja_gd -> the real lu_guide with look_hw_ui verify's facade / heap stand-ins (Colour & Light sectors
     9..12, every slot set, Movie lock). Japanese: translate(English model text); Chinese: lu_guide's own zh text; English:
     its English text. d0 = the stand-in chain's 0x5a5a, callee-saved registers kept.
  G  section-7 gate: sections word without bit 6 -> the stock guide part runs (mock there), label and d0 unchanged.
  P  anti-brick: package decodes to stock + edits (the image Z ran), restore == stock, every byte differing from the base
     spec is in this layer's two edits or the guide word; with --v034, every byte differing from v0.34 is listed by owner.
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
    s = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(s)
    sys.modules[name] = m; s.loader.exec_module(m); return m


JA = _load('ep7_ja_build_v', ROOT / 'patches/i18n_ja/build.py')
ZB = JA.ZH
LUV = _load('ep7_lu_verify_ja', ROOT / 'patches/look_hw_ui/verify.py')
EV, LU = LUV.EV, LUV.LU
W = _load('ep7_wb_v_ja', ROOT / 'tools/ep7_verify_wb.py')
Region, execute = W.Region, W.execute
BASE, GD_WORD, STOCK_GD = 0x60020020, 0x6025aa98, 0x60decbfc
POOL, HANDLE = 0xa1f8d800, 0x41
P = POOL + HANDLE - 1
VIEW, STUB, STRS = 0x13000000, 0x13200000, 0x13300000
REGS0 = dict(d1=0xd1d1, d2=0x2222, d3=0x3333, a1=0xa1a1, a2=0xa2a2, mdr=0x6d6d)
KEEP = ('d2', 'd3', 'a2', 'a3', 'sp')
S134 = {'ja': 'バージョン', 'zh': '固件', 'en': 'Firmware'}
G = {}


def image(spec):
    pkg, rst, info = BP.build(spec, BP.STOCK.read_bytes())
    return [b for b in oc.parse(pkg) if b.kind == 0x100][0].payload, pkg, rst, info


def sl(im, lo, hi):
    return im[lo - BASE:hi - BASE]


def ja_regions(im):
    x = G['spec']['i18n_ja']
    (c0, c1), (t0, t1) = [[int(v, 16) for v in c] for c in x['claims']]
    return [Region('ja', c0, sl(im, c0, c1), 'rx'), Region('jt', t0, sl(im, t0, t1), 'r')]


def mock(at, kind, text):
    u = list(text.encode('utf-16-le')) + [0, 0]
    src = [' .am33_2', ' .text', ' .global _start', '_start:', f' mov {kind},d0', ' movhu d0,(44,a0)']
    for i in range(0, len(u), 2):
        src += [f' mov {u[i] | u[i + 1] << 8},d0', f' movhu d0,({52 + i},a0)']
    src += [' mov 0x1234,d0', ' mov 0xdead1111,d1', ' mov 0xdead2222,a1', ' rets']
    return ZB.B3.assemble('\n'.join(src) + '\n', at, {})[0]


def stub():
    src = f""" .am33_2
 .text
 .global _start
_start:
 mov {VIEW:#x},a0
 mov ({GD_WORD:#x}),a1
 calls (a1)
 nop
"""
    code = ZB.B3.assemble(src, STUB, {})[0]
    return code, STUB + len(code) - 1


def strings(lang):
    t = bytearray(0x1000)
    s = S134[lang].encode('utf-16-le') + b'\0\0'
    struct.pack_into('<I', t, 536, STRS + 0x800)
    t[0x800:0x800 + len(s)] = s
    return bytes(t)


def run_z(text, kind=5, lang='ja', axis=4, table=True, sect=0x1ff):
    im = G['new']
    zh_chain = int(G['spec']['i18n_zh']['chain'], 16)              # xp_guide: i18n_gd's inner chain, mocked
    code, stop = stub()
    p = bytearray(1024); p[0:4] = b'EP7B'; p[680:684] = b'EP7E'; p[684] = axis
    rg = [Region('stub', STUB, code, 'rx'), *ja_regions(im),
          Region('lu', 0x607d9300, sl(im, 0x607d9300, 0x607da1c0), 'rx'),
          Region('zh', 0x607d4200, sl(im, 0x607d4200, 0x607d5000), 'rx'),
          Region('gdw', 0x6025aa80, sl(im, 0x6025aa80, 0x6025aac0), 'r'),
          Region('bank', 0x61fb2800, bytes(0x40), 'r'),
          Region('tabs', 0x61fc1500, struct.pack('<48xI', STRS if table else 0) + bytes(0x30), 'r'),
          Region('allf', 0x61fc3800, struct.pack('<II', 1, 0), 'r'),           # ALL on: lu_guide keeps the chain's text
          Region('strs', STRS, strings(lang), 'r'),
          Region('state', 0x622cbcc0, struct.pack('<HHI', 0, HANDLE, 0), 'r'),
          Region('pool', P, bytes(p), 'r'),
          Region('stack', W.STACK, bytes([W.STACK_FILL] * 0x2000), 'rw', True),
          Region('view', VIEW, b'\xee' * 140, 'rw', True),
          Region('sect', 0xa272e420, struct.pack('<I', sect), 'r')]
    if sect & 0x40:
        rg.append(Region('mock', zh_chain, mock(zh_chain, kind, text), 'rx'))
    else:
        rg.append(Region('stockgd', STOCK_GD, mock(STOCK_GD, 4, 'STOCK ' + text), 'rx'))
    r = execute(rg, dict(pc=STUB, sp=W.SP0, d0=0, a0=0, a3=0x3a3a, **REGS0), stop, limit=400000, trace_limit=1000)
    return r, {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}, stop


def label(m):
    t = m['view'][52:52 + 66]
    return t.decode('utf-16-le').split('\0')[0], t


CASES = [('1 Grain High', {}), ('3 Halo Med', {}), ('5 Shadow Yellow', {}), ('7 High +3', {}), ('6 Shadow -2', {}),
         ('Saturation - All', {}), ('Hue', {}), ('Light', {}), ('2 Clarity/Glow 0', {}), ('2 Glow 3', {}),
         ('1 WB Amber/Blue', {}), ('2 WB Green/Mag.', {}), ('2 WB Magenta +2', {}), ('7 VigFix Camera', {}),
         ('6 NR Std', {}), ('5 Sharp Off', {}), ('4 Art Star Light', {}), ('3 Blacks -2', {}), ('7 High Or-Red', {}),
         ('Extras: 1-11 only', {}), ('Extras: no All', {}), ('Effects: 1-7', {}), ('Colour: 1-8', {}),
         ('Split: COLOR 1-4', {}), ('Grain: stills', {}), ('Halo: stills', {}),
         ('Stock', dict(axis=3)), ('Custom', dict(axis=3)), ('Film: Velvia*', dict(axis=3)), ('Film Kodachrome1', dict(axis=3)),
         ('Velvia Off', dict(axis=3)), ('Portra 400 High', dict(axis=3)), ('Film: Grain High', dict(axis=3)),
         ('Velvia Off', {}), ('Star Light Lightx', {})]
LANGS = ('ja', 'zh', 'en')


def t_z():
    bad, n, shown = [], 0, []
    cases = [(t, dict(kw, lang=l)) for t, kw in CASES for l in LANGS]
    cases += [('1 Grain High', dict(kind=4)), ('1 Grain High', dict(table=False)), ('Stock', dict(axis=3, kind=4))]
    for text, kw in cases:
        r, m, stop = run_z(text, **kw)
        g = r['registers']
        lang, film = kw.get('lang', 'ja'), kw.get('axis') == 3
        on = kw.get('kind', 5) == 5 and kw.get('table', True)
        want = JA.translate(text, film=film) if on and lang == 'ja' else ZB.translate(text, film=film) if on and lang == 'zh' else text
        got, raw = label(m)
        ok = not r['fault'] and g['pc'] == stop and got == want and g['d0'] == 0x1234
        ok &= all(g[k] == {'d2': 0x2222, 'd3': 0x3333, 'a2': 0xa2a2, 'a3': 0x3a3a, 'sp': W.SP0}[k] for k in KEEP)
        rewritten = on and (lang == 'ja' or (lang == 'zh' and not (film and want == text)))
        if rewritten:
            ok &= raw[len(want) * 2:] == bytes(66 - len(want) * 2)
        else:
            ok &= m['view'][52 + len(text) * 2 + 2:] == b'\xee' * (140 - 52 - len(text) * 2 - 2)
        ok &= set(m['stack'][W.SP0 - W.STACK + 4:]) == {W.STACK_FILL}
        n += 1
        shown.append(f'   [{lang}{" film" if film else ""}{"" if on else " off"}] {text!r} -> {got!r}')
        if not ok:
            bad.append((text, kw, r['fault'], got, want, {k: hex(g[k]) for k in KEEP + ('d0',)}))
    print('\n'.join(shown))
    return not bad, f'{n} cases; bad {bad[:3]}'


def t_gate():
    bad, n = [], 0
    for sect in (0, 0x3f, 0x7f, 0x1ff):
        for text, kw in (('1 Grain High', {}), ('Film: Velvia', dict(axis=3)), ('1 Grain High', dict(lang='en')),
                         ('1 Grain High', dict(lang='zh'))):
            r, m, stop = run_z(text, sect=sect, **kw)
            g = r['registers']
            lang = kw.get('lang', 'ja')
            if sect & 0x40:
                want = JA.translate(text, film=kw.get('axis') == 3) if lang == 'ja' else ZB.translate(text) if lang == 'zh' else text
            else:
                want = 'STOCK ' + text
            got, _ = label(m)
            ok = not r['fault'] and g['pc'] == stop and got == want and g['d0'] == 0x1234 and bool(sect & 0x40 or m['view'][44] == 4)
            ok &= all(g[k] == {'d2': 0x2222, 'd3': 0x3333, 'a2': 0xa2a2, 'a3': 0x3a3a, 'sp': W.SP0}[k] for k in KEEP)
            ok &= set(m['stack'][W.SP0 - W.STACK + 4:]) == {W.STACK_FILL}
            n += 1
            if not ok:
                bad.append((hex(sect), text, kw, r['fault'], got, want))
    return not bad, f'{n} cases; bad {bad[:3]}'


# ------------------------------------------------------------------ L (look_hw_ui's own labels, real lu_guide)
def lu_case(st, pm, cursor, lang):
    lab, h, blk, hit, movie = st
    im = G['new']
    code, sy = EV.asm(f' mov {EV.VOBJ:#x},a0\n mov 0x6025aa98,a2\n mov (a2),a2\n mov {EV.SENT["a3"]:#x},a3\n calls (a2)\n', EV.DRV)
    rg = LUV.guide_regions(pm, cursor, 5, lang == 'zh')
    lang_b = bytearray(0x1100)
    struct.pack_into('<I', lang_b, 536, LUV.LANG + 0x1000)
    s = S134[lang].encode('utf-16-le') + b'\0\0'
    lang_b[0x1000:0x1000 + len(s)] = s
    rg = [Region('lang', LUV.LANG, bytes(lang_b), 'r') if r.name == 'lang' else r for r in rg]
    regions = [Region('drv', EV.DRV, code, 'rx'), Region('view', EV.VOBJ, bytes(0x100), 'rw', True),
               EV.img(im, 0x6025aa90, 0x6025aaa0, 'gw', 'r'), LUV.allf(0)] + rg + LUV.code_regions(im) + ja_regions(im) \
        + EV.state_regions(h, blk, 'r')
    tag = f'lu {lab} pm {pm} cursor {cursor} {lang}'
    p = EV.run(regions, {'pc': EV.DRV}, sy['done'])
    if not LUV.ok_run(p, sy['done']):
        return tag, None, f'no stop: {p["fault"]} pc {p["registers"]["pc"]:#x}'
    if p['registers']['d0'] != 0x5a5a or any(p['registers'][k] != EV.SENT[k] for k in ('d2', 'd3', 'a3')):
        return tag, None, f'registers {p["registers"]}'
    k = {54: 0, 55: 1, 56: 2, 64: 3}.get(pm)
    ours = hit and k is not None and 9 <= cursor <= 12
    en = LUV.model_text(blk, k, cursor, 0, movie) if ours else 'Colour: 1-8'      # the stand-in chain writes "Colour: 1-8"
    want = LUV.model_text(blk, k, cursor, 1, movie) if ours and lang == 'zh' else JA.translate(en) if lang == 'ja' else en
    vp = EV.mem(p, 'view')
    got = vp[52:52 + 66].decode('utf-16-le').split('\0')[0]
    if struct.unpack_from('<H', vp, 44)[0] != 5 or got != want:
        return tag, got, f'label {got!r}, want {want!r}'
    if (ours or lang == 'ja') and vp[52 + 2 * len(want):52 + 66] != bytes(66 - 2 * len(want)):
        return tag, got, 'not zero-padded'
    return tag, got, None


def t_l():
    fails, n, seen = [], 0, {}
    sts = [s for s in LUV.states() if s[0] in ('zero', 'stored', 'panel', 'stale', 'movie', 'axis 3')]
    for st in sts:
        for pm in (54, 55, 56, 64, 57):
            for cursor in (8, 9, 10, 11, 12):
                for lang in LANGS:
                    if st[0] not in ('stored', 'movie') and (lang == 'zh' or pm in (55, 56, 57)):
                        continue
                    n += 1
                    tag, got, e = lu_case(st, pm, cursor, lang)
                    if got is not None:
                        seen.setdefault((lang, got), tag)
                    if e:
                        fails.append((tag, e))
    print('\n'.join(f'   [{l}] {g!r}' for (l, g) in sorted(seen)))
    return not fails, f'{n} cases' + (f'; {fails[:4]}' if fails else '')


# ------------------------------------------------------------------ P
def t_pkg(base_s, new_s, base, new, pkg, rst, info, disk, v034):
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
    x = new_s['i18n_ja']
    ours = [(int(x['code'][0], 16), x['code'][1]), (int(x['tokens'][0], 16), x['tokens'][1]), (GD_WORD, 4)]
    diff = [BASE + i for i in range(len(base)) if base[i] != new[i]]
    stray = [hex(a) for a in diff if not any(s_ <= a < s_ + k for s_, k in ours)]
    good &= not stray and len(new_s['edits']) == len(base_s['edits']) + 2
    if disk:
        good &= (disk / 'patched.pkg.bin').read_bytes() == pkg and (disk / 'restore-stock.pkg.bin').read_bytes() == rst
    txt = f'{info["edits"]} edits, {info["changed_payload_bytes"]} B; {len(diff)} B differ from base; stray {stray[:6]}'
    if v034:
        old, *_ = image(v034)
        dv = [BASE + i for i in range(len(old)) if old[i] != new[i]]
        own = {}
        for a in dv:
            src = next((e for e in new_s['edits'] if e['kind'] == '0x100' and not e['addr'].startswith('off:')
                        and int(e['addr'], 16) <= a < int(e['addr'], 16) + len(e['new']) // 2), None)
            k = 'guide word' if GD_WORD <= a < GD_WORD + 4 else (src or {}).get('source', '?')
            own[k] = own.get(k, 0) + 1
        other = {b.kind for b in oc.parse(pkg)} - {0x100}
        txt += f'; vs v0.34: {len(dv)} B in main by owner {own}'
        good &= '?' not in own
    return good, txt


def main():
    args = sys.argv[1:]
    v034 = None
    if '--v034' in args:
        i = args.index('--v034'); v034 = json.loads(Path(args[i + 1]).read_text()); del args[i:i + 2]
    base_s, new_s = (json.loads(Path(p).read_text()) for p in args[:2])
    disk = Path(args[2]) if len(args) > 2 else None
    G['spec'] = new_s
    base, *_ = image(base_s)
    new, pkg, rst, info = image(new_s)
    G['new'] = new
    LUV.G['new'] = new
    ok = True
    for tag, f in (('Z', t_z), ('L', t_l), ('G', t_gate),
                   ('P', lambda: t_pkg(base_s, new_s, base, new, pkg, rst, info, disk, v034))):
        g, txt = f()
        print(f"{'PASS' if g else 'FAIL'} {tag} {txt}", flush=True)
        ok &= g
    print('ALL PASS' if ok else 'FAILURES')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
