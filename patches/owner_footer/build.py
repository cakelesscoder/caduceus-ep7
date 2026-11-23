#!/usr/bin/env python3
"""Owner footer: one line of owner text (name + phone, typed at build time) at the bottom of every main-menu page.
docs/OWNER_FOOTER.md; of.s.in has the contract. Offline, a layer like the others:

  .venv/bin/python -I patches/owner_footer/build.py <spec> --out <edits.json>
  (release chain: patches/v032/build.py ... --extra i18n_ja=... --extra owner_footer=patches/owner_footer/build.py)

apply(spec, version) -> spec. Edits:
  - code + style + rect + an all-zero owner block in a sec-5 claim of the dead `sdk api` shell handlers
    (CODE_SPACE_SURVEY section 2; needs extras_pages' sub-command cut), inside a run into which no reference from outside
    the dead code points (same scan as i18n_ja's claims);
  - the GE window paint routine's children call 0x60d005fb `mov (160,a2),a2; calls (a2)` -> `jmp of_paint` + nop.
The owner block stays zero here: caduceus.py writes it (owner_block() below is the format) when the user builds.
"""
import argparse, copy, importlib.util, json, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SRC = 'patches/owner_footer'


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


JA = _load('ep7_ja_build_of', ROOT / 'patches/i18n_ja/build.py')
ST, KH, B3, BASE, STOCK, BAD = JA.ST, JA.KH, JA.B3, JA.BASE, JA.STOCK, JA.BAD

CLAIM = (0x607e2200, 0x607e2600)          # 1 KB; scan of 0x607c9c20..0x607e87c5 on the v0.34a image: no reference into it
GUARD = 16
AT = CLAIM[0] + GUARD
SITE, BACK = 0x60d005fb, 0x60d00601       # GE paint 0x60d00506: mov (160,a2),a2; calls (a2) -> children paint
SITE_OLD = bytes.fromhex('fa2aa000f0f2')
ALIVE = 0x61fb828c                        # 2CNL page panel: set by vtbl +364 0x60d82a4c / +400 0x60d82b93, cleared by +0 dtor
CURWIN = 0x61fb3138                       # current window (getter 0x60d3379b)
REGION = 1428 + 36                        # window+1428 + 36 * (layer - 1): layer 2's dirty region (paint layer loop)
OMAGIC = 0x4f375045                       # 'EP7O'
OMAX = 46                                 # text units (name <= 24, two spaces, phone <= 20)
OTEXT = 2 * (OMAX + 1) + 2                # 96 B: text + NUL, 4-aligned
RECT = (40, 434, 680, 474)                # below the page frame (y 55..425), inside 720 x 480
TSTYLE = 1                                # text-style id of every menu label (descriptor +48)
FUNCS = dict(ep7_paint_back=BACK, ep7_setlayer=0x60d061ec, ep7_setfont=0x60d0fce0, ep7_setmode=0x60d0fd83,
             ep7_clip=0x60d0618c, ep7_drawtext=0x60d075a7, ep7_frel=0x60d10708)
HEADS = {0x60d061e7: 'cfb0f8fef8', 0x60d0fce0: '921ccda60e8008', 0x60d0fd83: 'f87034de0000',
         0x60d0618c: 'f82008dd54970000', 0x60d10708: 'b000c80e'}
# Host-side text limits (caduceus.py repeats them): ASCII glyph widths of the camera's text font (all 34 language fonts
# share these ASCII metrics; tools/zh_glyphs.py), advance taken as width + 3, the whole line within MAXPX.
WIDTHS = (10, 5, 8, 18, 15, 22, 19, 3, 8, 8, 12, 15, 4, 10, 4, 11, 18, 10, 17, 17, 18, 17, 18, 17, 19, 18, 4, 4, 12, 15, 12,
          15, 22, 19, 16, 17, 18, 15, 14, 19, 17, 4, 9, 17, 13, 21, 17, 19, 16, 19, 17, 16, 15, 17, 18, 23, 17, 17, 16, 7,
          11, 7, 13, 14, 8, 15, 14, 14, 14, 14, 9, 15, 13, 4, 7, 14, 3, 20, 13, 15, 14, 15, 8, 13, 9, 14, 14, 21, 14, 15, 13,
          8, 3, 8, 14)
MAXPX = 620


def owner_line(name, phone):
    return '  '.join(x for x in (name.strip(), phone.strip()) if x)


def owner_block(text, size=8 + OTEXT):
    """The bytes caduceus.py writes over the zero block. '' -> all zero (feature off)."""
    if not text:
        return bytes(size)
    if not (0 < len(text) <= OMAX and all(0x20 <= ord(c) <= 0x7e for c in text)):
        raise ValueError('owner text: 1..46 printable ASCII characters')
    b = struct.pack('<IHH', OMAGIC, len(text), 0) + text.encode('utf-16-le')
    return b + bytes(size - len(b))


def u32(im, a):
    return struct.unpack_from('<I', im, a - BASE)[0]


def build_code():
    sub = dict(omagic=hex(OMAGIC), omax=OMAX, alive=hex(ALIVE), curwin=hex(CURWIN), region=REGION, tstyle=TSTYLE,
               otext=OTEXT, rx0=RECT[0], ry0=RECT[1], rx1=RECT[2], ry1=RECT[3])
    src = B3.subst((HERE / 'of.s.in').read_text(), sub)
    code, lst, sy, _ = B3.assemble(src, AT, FUNCS)
    if sy['of_paint'] != AT or AT + len(code) > CLAIM[1] - GUARD or sy['of_end'] != AT + len(code):
        raise SystemExit(f'{len(code)} B does not fit')
    for k in ('of_style', 'of_block'):
        if sy[k] % 4:
            raise SystemExit(f'{k} not 4-aligned')
    if sy['of_text'] != sy['of_block'] + 8 or code[sy['of_block'] - AT:] != bytes(8 + OTEXT):
        raise SystemExit('owner block layout')
    ins = B3.disasm(code, AT, sy['of_style'])
    if any(op in BAD for _, op, _ in ins) or any(op.startswith('.') or op == '(bad)' for _, op, _ in ins):
        raise SystemExit('forbidden or undecodable instruction')
    if any(code[a - AT] == 0xfb for a, _, _ in ins):
        raise SystemExit('fb-prefixed form')
    ok_st = {'mov d0,(4,a3)', 'mov d0,(8,a3)', 'mov d0,(76,a3)', 'movhu d0,(52,a3)'}
    for a, txt, kd, _ in B3.store_audit(ins):
        if kd == 'abs' or (kd == 'ind' and txt not in ok_st):
            raise SystemExit(f'store at {a:#x}: {txt} ({kd})')
    tg = {(op, int(args.split(',')[0], 16)) for _, op, args in ins if op in ('call', 'jmp') and args.startswith('0x')}
    tg = {(o, t) for o, t in tg if not (o == 'jmp' and AT <= t < sy['of_style'])}     # long internal branches
    want = {('jmp', BACK), ('call', sy['of_draw'])} | {('call', v) for k, v in FUNCS.items() if k != 'ep7_paint_back'}
    if tg != want:
        raise SystemExit(f'call targets {sorted((o, hex(t)) for o, t in tg)}')
    return code, sy, lst


def apply(spec, version='0.34a'):
    stock = STOCK.read_bytes()
    spec = copy.deepcopy(spec)
    if 'owner_footer' in spec:
        raise SystemExit('owner_footer already applied')
    if 'extras_pages' not in spec:
        raise SystemExit('needs extras_pages (the sdk sub-command cut that makes the claim dead)')
    im = ST.img_of(spec, stock)
    if im[SITE - BASE:SITE - BASE + 6] != SITE_OLD or stock[SITE - BASE:SITE - BASE + 6] != SITE_OLD:
        raise SystemExit('paint site bytes differ (another layer hooks it?)')
    for a, h in HEADS.items():
        if h and stock[a - BASE:a - BASE + len(h) // 2].hex() != h:
            raise SystemExit(f'function head {a:#x} differs')
    if u32(stock, 0x60d82a56) != ALIVE \
            or u32(stock, 0x60d82b9d) != ALIVE or u32(stock, 0x60d828fb) != ALIVE:
        raise SystemExit('2CNL alive word sites differ')
    if JA._refs(im, SITE + 1, BACK + 1, KH.sec(stock, 5)[2]):
        raise SystemExit('reference into the paint site')
    JA.check_claim(spec, stock, im, CLAIM)
    code, sy, lst = build_code()
    spec['edits'].append(dict(kind='0x100', addr=hex(AT), expect=stock[AT - BASE:AT - BASE + len(code)].hex(), new=code.hex(),
                              source=SRC, why=f'owner_footer {version}: of_paint / of_draw + style, rect, zero owner block '
                                              f'({len(code)} B, sec-5 dead sdk-api handlers, claim {CLAIM[0]:#x}..{CLAIM[1]:#x})'))
    rel = sy['of_paint'] - SITE
    new = b'\xdc' + struct.pack('<i', rel) + b'\xcb'
    spec['edits'].append(dict(kind='0x100', addr=hex(SITE), expect=SITE_OLD.hex(), new=new.hex(), source=SRC,
                              why=f'owner_footer {version}: GE paint children call -> jmp of_paint + nop (back to {BACK:#x})'))
    spec['owner_footer'] = dict(built_by=SRC, version=version, claim=[hex(CLAIM[0]), hex(CLAIM[1])], code=[hex(AT), len(code)],
                                site=hex(SITE), back=hex(BACK), alive=hex(ALIVE), block=hex(sy['of_block']),
                                block_len=8 + OTEXT, magic=hex(OMAGIC), max_units=OMAX, rect=list(RECT), text_style=TSTYLE,
                                symbols={k: hex(v) for k, v in sy.items() if k.startswith(('of_', 'o_'))})
    return spec


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--version', default='0.34a')
    a = ap.parse_args()
    spec = apply(json.loads(a.spec.read_text()), a.version)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(spec, indent=1))
    print(json.dumps({k: v for k, v in spec['owner_footer'].items() if k != 'symbols'}))
