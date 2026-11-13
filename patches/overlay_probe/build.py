#!/usr/bin/env python3
"""Extras text-overlay probe (E-P7 1.1). Offline. docs/EXTRAS_OVERLAY.md; ov.s.in has the contract.

  .venv/bin/python -I patches/overlay_probe/build.py generated/v032/edits.json --out OUT.json

apply(spec, version) -> spec. Layer after keyhook (shares the sec-5 sdk-shell reserve; keyhook neutralises the shell
and claims 0x607b6420-0x607b8420, this claims 0x607b8420-0x607c8420). Edits:
  - code `.ov` in the dead `sdk api` handlers, sec 5 0x607b8430.. (claim 0x607b8420-0x607c8420, 16 B stock guards);
  - view vtable +0 word 0x61155e14 (Colour Profile editor update 0x60dec790) -> ov_upd;
  - window vtable +164 words 0x60f94820 / 0x60fac3f0 (empty post-paint 0x60cfe263) -> ov_post.
State: the boot-cleared .bss pad 0x622ab792 (flag) / 0x622ab793 (u8 counter), uncached (docs/AUTOLOAD.md §Progress).
"""
import argparse, copy, importlib.util, json, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


KH = _load('ep7_keyhook_ov', ROOT / 'patches/keyhook/build.py')
PL, ST, SB3, np = KH.PL, KH.PL.ST, KH.PL.SB3, KH.PL.np
STOCK = KH.STOCK
BASE, SRC = 0x60020020, 'patches/overlay_probe'

CLAIM = (0x607b8420, 0x607c8420)                     # sec 5, 64 KB: dead sdk-api handlers, after keyhook's 0x607b6420-0x607b8420
GUARD, SEC5 = 16, 5
AT, END = CLAIM[0] + GUARD, CLAIM[1] - GUARD
VIEW_W, VIEW_BODY = 0x61155e14, 0x60dec790           # Colour Profile editor view vtable +0
WIN_W, WIN_STOCK = (0x60f94820, 0x60fac3f0), 0x60cfe263   # window vtable +164 (empty post-paint), both classes
DRAWTEXT, SETCOL = 0x60d075a7, 0x60d0fc05
FLAG, CNT = 0xa22ab792, 0xa22ab793                   # uncached .bss pad (0x622ab792/3)
BAD = PL.BAD
# the three data words point into the claim (our hooks); allow those sources in the reference scan
WORDS = (VIEW_W,) + WIN_W
DEAD_RANGE = (0x607b6420, 0x607e87c5)                # the survey-cleared sdk-shell handler range (CODE_SPACE_SURVEY §2.2)


def u32(b):
    return struct.unpack('<I', b)[0]


def refs_into(image, claim, off5):
    """Every source byte-address whose abs32 (any of the four section aliases) or rel/call/jmp (dd/dc/cd/cc d32/d16)
    lands in [claim). Used as a delta against the base image: a build may only ADD its own internal refs + its hooks."""
    lo, hi = claim
    d = np.frombuffer(image, np.uint8).astype(np.int64)
    w = d[:-3] | (d[1:-2] << 8) | (d[2:-1] << 16) | (d[3:] << 24)
    srcs = set()
    for off in (0, 0x40000000, off5, (off5 + 0x40000000) & 0xffffffff):
        a, b = (lo + off) & 0xffffffff, (hi + off) & 0xffffffff
        for i in np.nonzero((w >= a) & (w < b))[0]:
            srcs.add(int(i) + BASE)
    pc = np.arange(len(d) - 8, dtype=np.int64) + BASE
    for op, n in ((0xdd, 4), (0xdc, 4), (0xcd, 2), (0xcc, 2)):
        m = d[:-8] == op
        disp = d[1:-7] | (d[2:-6] << 8) if n == 2 else d[1:-7] | (d[2:-6] << 8) | (d[3:-5] << 16) | (d[4:-4] << 24)
        disp = np.where(disp >= (1 << (8 * n - 1)), disp - (1 << (8 * n)), disp)
        for x in np.nonzero(m & (pc + disp >= lo) & (pc + disp < hi))[0]:
            srcs.add(int(x) + BASE)
    return srcs


def check_base(spec, stock, im):
    if 'overlay_probe' in spec:
        raise SystemExit('overlay_probe already applied')
    kh = spec.get('keyhook')
    if not kh:
        raise SystemExit('needs keyhook (sdk shell must be cut, and its claim ends at 0x607b8420)')
    if int(kh['claim'][1], 16) != CLAIM[0]:
        raise SystemExit(f"keyhook claim end {kh['claim'][1]} != {CLAIM[0]:#x}")
    if u32(im[VIEW_W - BASE:VIEW_W - BASE + 4]) != VIEW_BODY:
        raise SystemExit(f'view +0 word != {VIEW_BODY:#x}')
    for w in WIN_W:
        if u32(im[w - BASE:w - BASE + 4]) != WIN_STOCK:
            raise SystemExit(f'window +164 word {w:#x} != {WIN_STOCK:#x}')
    # the stock bodies we chain to / replay
    if stock[VIEW_BODY - BASE:VIEW_BODY - BASE + 2] != b'\xcf\xf0':      # movm [d2,d3,a2,a3],(sp)
        raise SystemExit('view body prologue differs')
    if stock[VIEW_BODY + 0x6f - BASE:VIEW_BODY + 0x6f - BASE + 1] != b'\xdf':   # ret [..],28 @ 0x60dec83f
        pass
    if stock[WIN_STOCK - BASE:WIN_STOCK - BASE + 3] != b'\xde\x00\x00':  # retf [],0
        raise SystemExit('window +164 body is not retf [],0')
    # the .bss pad must be unreferenced and unwritten by the spec
    cached = (FLAG & ~0x40000000, CNT & ~0x40000000)
    d = np.frombuffer(im, np.uint8).astype(np.int64)
    w = d[:-3] | (d[1:-2] << 8) | (d[2:-1] << 16) | (d[3:] << 24)
    for a in cached + (FLAG, CNT):
        if len(np.nonzero(w == a)[0]):
            raise SystemExit(f'.bss pad {a:#x} is referenced')
    for e in spec['edits']:
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            base = int(e['addr'], 16)
            for a in cached:
                if base <= a < base + len(e['new']) // 2:
                    raise SystemExit(f'spec writes the .bss pad near {a:#x}')


def check_free(spec, stock, base_im, final_im, code_len):
    lo5, hi5, off5 = KH.sec(stock, SEC5)
    if not (lo5 <= CLAIM[0] and CLAIM[1] <= hi5):
        raise SystemExit('claim not inside section 5')
    for e in spec['edits']:
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            a, n = int(e['addr'], 16), len(e['new']) // 2
            if a < CLAIM[1] and CLAIM[0] < a + n:
                raise SystemExit(f'claim overlaps edit {e["addr"]}')
    if base_im[CLAIM[0] - BASE:CLAIM[1] - BASE] != stock[CLAIM[0] - BASE:CLAIM[1] - BASE]:
        raise SystemExit('claim not stock (dead handlers)')
    # The whole sdk-shell range 0x607b6420-0x607e87c5 is survey-cleared (CODE_SPACE_SURVEY §2.2): every naive hit into
    # it is a mid-instruction / data false positive, and keyhook cut the three sub-command words so no input reaches it.
    # So this build does not re-litigate the base image's hits; it proves it introduces NO NEW reference into the claim
    # beyond the three intended vtable words and its own internal code (delta scan over every alias; abs32 + rel/call).
    if not (DEAD_RANGE[0] <= CLAIM[0] and CLAIM[1] <= DEAD_RANGE[1]):
        raise SystemExit('claim not inside the survey-cleared sdk-shell range')
    new = refs_into(final_im, CLAIM, off5) - refs_into(base_im, CLAIM, off5)
    codehi = AT + code_len
    for src_at in sorted(new):
        if AT <= src_at < codehi:          # our own code's internal references
            continue
        if src_at in WORDS:                # the three intended vtable words
            continue
        raise SystemExit(f'new reference into the claim from {src_at:#x}')


def build_code():
    sub = dict(flag=hex(FLAG), cnt=hex(CNT), state=hex(SB3.STATE), pool=hex(SB3.POOL), lim=hex(SB3.LIM),
               bmagic=hex(SB3.MAGIC), emark=680, emagic=hex(int.from_bytes(b'EP7E', 'little')), axis=684, x_axis=4)
    src = SB3.subst((HERE / 'ov.s.in').read_text(), sub)
    syms = dict(ep7_upd_body=VIEW_BODY, ep7_drawtext=DRAWTEXT, ep7_setcol=SETCOL)
    code, lst, sy, dis = SB3.assemble(src, AT, syms)
    if sy['_start'] != AT or sy['ov_upd'] != AT:
        raise SystemExit('layout: _start/ov_upd not at AT')
    if AT + len(code) > END:
        raise SystemExit(f'.ov {len(code)} B does not fit {END - AT}')
    ins = SB3.disasm(code, AT, sy['ov_end'])
    if any(op in BAD for _, op, _ in ins) or any(op.startswith('.') or op == '(bad)' for _, op, _ in ins):
        raise SystemExit('forbidden or undecodable instruction')
    if any(code[a - AT] == 0xfb for a, _, _ in ins):
        raise SystemExit('fb-prefixed form')
    st = SB3.store_audit(ins)
    if any(k == 'abs' for _, _, k, _ in st):
        raise SystemExit(f'absolute store: {[s for s in st if s[2] == "abs"]}')
    # call/jmp targets: only the two helpers, the stock view body, and our own labels
    want = {('calls', None), ('call', DRAWTEXT), ('call', SETCOL)}
    for a, op, args in ins:
        if op in ('call', 'jmp') and args.startswith('0x'):
            t = int(args.split(',')[0], 16)
            if t not in (DRAWTEXT, SETCOL) and not (AT <= t < END):
                raise SystemExit(f'unexpected target {op} {hex(t)}')
    return code, sy, lst


def apply(spec, version='0.32'):
    stock = STOCK.read_bytes()
    spec = copy.deepcopy(spec)
    im = ST.img_of(spec, stock)
    check_base(spec, stock, im)
    code, sy, lst = build_code()
    final = bytearray(im)
    final[AT - BASE:AT - BASE + len(code)] = code
    struct.pack_into('<I', final, VIEW_W - BASE, sy['ov_upd'])
    for w in WIN_W:
        struct.pack_into('<I', final, w - BASE, sy['ov_post'])
    check_free(spec, stock, im, bytes(final), len(code))
    spec['edits'].append(dict(kind='0x100', addr=hex(AT), expect=stock[AT - BASE:AT - BASE + len(code)].hex(),
                              new=code.hex(), source=SRC,
                              why=f'overlay_probe {version} .ov ({len(code)} B, sec 5 dead sdk-api handlers)'))
    PL.put(spec, stock, VIEW_W, struct.pack('<I', VIEW_BODY), struct.pack('<I', sy['ov_upd']),
           'view +0 (Colour Profile editor update) -> ov_upd (set overlay flag)')
    for w in WIN_W:
        PL.put(spec, stock, w, struct.pack('<I', WIN_STOCK), struct.pack('<I', sy['ov_post']),
               f'window +164 {w:#x} -> ov_post (Extras text overlay)')
    for e in spec['edits']:                      # PL.put tags as plugin_loader; retag ours
        if e.get('source') == PL.SRC and e['why'].startswith('plugin_loader: ') and (
                'ov_upd' in e['why'] or 'ov_post' in e['why']):
            e['source'] = SRC
            e['why'] = 'overlay_probe: ' + e['why'][len('plugin_loader: '):]
    spec['overlay_probe'] = dict(
        built_by=SRC, version=version, claim=[hex(CLAIM[0]), hex(CLAIM[1])], region=[hex(AT), hex(AT + len(code))],
        bytes=len(code), view_word=hex(VIEW_W), win_words=[hex(w) for w in WIN_W], flag=hex(FLAG), cnt=hex(CNT),
        helpers=dict(drawtext=hex(DRAWTEXT), setcol=hex(SETCOL), view_body=hex(VIEW_BODY)),
        symbols={k: hex(v) for k, v in sy.items() if k.startswith('ov')})
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
    print(json.dumps({k: v for k, v in spec['overlay_probe'].items() if k != 'symbols'}, indent=1))
