#!/usr/bin/env python3
"""Colour Profile page guide label (issue #41): the full Colour Profile page shows the same page/look label as the
SCP-opened wheel. Offline. sn.s.in has the contract.

  .venv/bin/python -I patches/scp_name/build.py releases/v0.31d/edits.json --out generated/v031e_scp/edits.json [--version 0.31e]

apply(spec, version) -> spec. One jmp stub: 0x60e2757d (12 B, the Profile view COLOR page's guide label write, section 6) ->
sn_gd in the section-6 FF tail 0x61242c40.. (look editor ed_ui's released tail, CODE_SPACE_MAP "Released (0.31b4)"
0x61242c30-0x61242ce0). sn_gd calls the guide part word 0x6025aa98 (ap_gd, section 7, loads earlier) on a stack fake view.

The SCP "Color Profile n" text (task 1) is not built: see the reply / sn.s.in. The SCP current-value cell is a 4-byte
{u16 string id, u8 kind, u8 state} (builder 0x60e00c1b, list 0x6116e21c: 54/55/56/64 -> ids 2859/2860/2861/3640),
with no text field, so a name needs a hook in the string-id renderer.
"""
import argparse, copy, importlib.util, json, struct
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


SB3 = _load('ep7_sd_bundles_v3_build_sn', ROOT / 'patches/sd_bundles_v3/build.py')
FV = _load('fw_version_build_sn', ROOT / 'patches/fw_version/build.py')
STOCK = ROOT / 'analysis/ep7_1100/00_0100_406a0020.decoded.bin'
BASE, SRC = 0x60020020, 'patches/scp_name'

AT, END = 0x61242c40, 0x61242cd0          # sec-6 FF tail (ed_ui ends 0x61242c25; hookA 0x61242d10); 16 B guards checked
SEC6 = (0x60ba7000, 0x61243000)
SITE, SITE_LEN, BACK = 0x60e2757d, 12, 0x60e27589
SITE_BYTES = bytes.fromhex('f87304 8004 f073 8002 f87306'.replace(' ', ''))   # movhu d0,(4,a3); mov 4,d0; movhu d0,(a3); mov 2,d0; movhu d0,(6,a3)
SITE_PRE = {0x60e27564: bytes.fromhex('2cc40a'), 0x60e2757a: bytes.fromhex('2cc30a')}  # mov 2756,d0 (bra) / mov 2755,d0
BACK_BYTES = bytes.fromhex('5c08')        # 0x60e27589: mov (8,sp),a0 (then call 0x60e27950)
GD_WORD = 0x6025aa98                      # Colour view part 3 init word (stock 0x60decbfc)
GD_STOCK = 0x60decbfc
BAD = {'mul', 'mulu', 'div', 'divu', 'setlb', 'llt', 'lne', 'leq', 'lra', 'lcc', 'lcs', 'trap'}


def img_of(spec, stock):
    im = bytearray(stock)
    for e in spec['edits']:
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            a = int(e['addr'], 16) - BASE; n = bytes.fromhex(e['new']); im[a:a + len(n)] = n
    return bytes(im)


def check_stock(stock):
    if stock[SITE - BASE:SITE + SITE_LEN - BASE] != SITE_BYTES or stock[BACK - BASE:BACK + 2 - BASE] != BACK_BYTES:
        raise SystemExit('hook site 0x60e2757d differs from stock')
    for a, b in SITE_PRE.items():
        if stock[a - BASE:a + len(b) - BASE] != b:
            raise SystemExit(f'label id load at {a:#x} differs')
    if stock[0x60e27567 - BASE:0x60e27569 - BASE] != bytes.fromhex('ca16'):   # bra 0x60e2757d
        raise SystemExit('2756 branch differs')
    if struct.unpack_from('<I', stock, GD_WORD - BASE)[0] != GD_STOCK:
        raise SystemExit('guide init word differs')


def no_refs(im, lo, hi, what):
    d = np.frombuffer(im, np.uint8).astype(np.int64)
    w = d[:-3] | (d[1:-2] << 8) | (d[2:-1] << 16) | (d[3:] << 24)
    for off in (0, 0x40000000):
        hits = np.nonzero((w >= lo + off) & (w < hi + off))[0]
        if len(hits):
            raise SystemExit(f'abs32 reference into {what} at {hex(int(hits[0]) + BASE)}')
    pc = np.arange(len(d) - 8, dtype=np.int64) + BASE
    for op, n in ((0xdd, 4), (0xdc, 4), (0xcd, 2), (0xcc, 2)):
        m = d[:-8] == op
        disp = d[1:-7] | (d[2:-6] << 8) if n == 2 else d[1:-7] | (d[2:-6] << 8) | (d[3:-5] << 16) | (d[4:-4] << 24)
        disp = np.where(disp >= (1 << (8 * n - 1)), disp - (1 << (8 * n)), disp)
        bad = np.nonzero(m & (pc + disp >= lo) & (pc + disp < hi))[0]
        if len(bad):
            raise SystemExit(f'branch into {what} from {hex(int(bad[0]) + BASE)}')


def check_free(spec, im):
    for e in spec['edits']:
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            a, n = int(e['addr'], 16), len(e['new']) // 2
            if a < END + 16 and AT - 16 < a + n:
                raise SystemExit(f'claim overlaps edit {e["addr"]}')
            if a < SITE + SITE_LEN and SITE < a + n:
                raise SystemExit(f'hook site overlaps edit {e["addr"]}')
    if set(im[AT - 16 - BASE:END + 16 - BASE]) != {0xff}:
        raise SystemExit('claim (with guards) is not FF')
    if not (SEC6[0] <= AT - 16 and END + 16 <= SEC6[1]):
        raise SystemExit('claim not inside the section-6 load')
    no_refs(im, AT - 16, END + 16, 'the claim')
    no_refs(im, SITE + 1, SITE + SITE_LEN, 'the hook site body')      # nothing may land on bytes +1..+11


def apply(spec, version='0.31e'):
    stock = STOCK.read_bytes()
    spec = copy.deepcopy(spec)
    if 'scp_name' in spec:
        raise SystemExit('scp_name already applied')
    spec = FV.apply(spec, version)
    im = img_of(spec, stock)
    check_stock(stock)
    if im[SITE - BASE:SITE + SITE_LEN - BASE] != SITE_BYTES:
        raise SystemExit('hook site already patched')
    word = struct.unpack_from('<I', im, GD_WORD - BASE)[0]
    owner = [e for e in spec['edits'] if e['kind'] == '0x100' and not e['addr'].startswith('off:')
             and int(e['addr'], 16) == word and e.get('source') == 'patches/ap_custom']
    if word == GD_STOCK or not owner:
        raise SystemExit(f'guide word {word:#x} is not the ap_custom chain (ap_gd)')
    if im[word - BASE:word - BASE + 2] != bytes.fromhex('cff0'):
        raise SystemExit('guide chain entry is not movm [d2,d3,a2,a3],(sp)')
    check_free(spec, im)
    sub = dict(state=hex(SB3.STATE), lim=hex(SB3.LIM), pool=hex(SB3.POOL), bmagic=hex(SB3.MAGIC))
    src = SB3.subst((HERE / 'sn.s.in').read_text(), sub)
    code, lst, s, _ = SB3.assemble(src, AT, dict(ep7_gd_word=GD_WORD, ep7_back=BACK))
    if s['sn_gd'] != AT or AT + len(code) > END:
        raise SystemExit(f'{len(code)} B does not fit {END - AT}')
    ins = SB3.disasm(code, AT, s['sn_end'])
    if any(op in BAD for _, op, _ in ins) or any(code[a - AT] == 0xfb for a, _, _ in ins):
        raise SystemExit('forbidden instruction or fb-prefixed form')
    st = SB3.store_audit(ins)
    if any(k == 'abs' for _, _, k, _ in st):
        raise SystemExit(f'absolute store: {st}')
    ind = sorted({t for _, t, k, _ in st if k == 'ind'})
    if ind != ['mov d0,(a0)', 'movhu d0,(4,a3)', 'movhu d0,(6,a3)', 'movhu d0,(a1)', 'movhu d0,(a3)']:
        raise SystemExit(f'unexpected stores: {ind}')
    jmp = ins[-1]
    if jmp[1] != 'jmp' or int(jmp[2].split()[0], 16) != BACK:
        raise SystemExit(f'exit is not jmp {BACK:#x}: {jmp}')
    rel = AT - SITE
    site_new = bytes([0xdc]) + struct.pack('<i', rel) + bytes([0xcb]) * (SITE_LEN - 5)
    spec['edits'].append(dict(kind='0x100', addr=hex(AT), expect=stock[AT - BASE:AT - BASE + len(code)].hex(), new=code.hex(), source=SRC,
                              why=f'scp_name {version} sn_gd ({len(code)} B, section-6 FF tail): Colour Profile page guide label through the guide part chain'))
    spec['edits'].append(dict(kind='0x100', addr=hex(SITE), expect=SITE_BYTES.hex(), new=site_new.hex(), source=SRC,
                              why='scp_name: Profile view COLOR page guide label write 0x60e2757d (12 B) -> jmp sn_gd + 7 nop (issue #41)'))
    spec['scp_name'] = dict(built_by=SRC, version=version, code_at=hex(AT), code_len=len(code), claim=[hex(AT), hex(END)],
                            guards=[hex(AT - 16), hex(END + 16)], site=hex(SITE), back=hex(BACK), guide_word=hex(GD_WORD), chain=hex(word),
                            symbols={k: hex(v) for k, v in s.items() if k.startswith('sn_')})
    return spec


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--version', default='0.31e')
    a = ap.parse_args()
    spec = apply(json.loads(a.spec.read_text()), a.version)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(spec, indent=1))
    print(json.dumps({k: v for k, v in spec['scp_name'].items() if k != 'symbols'}), spec['scp_name']['symbols'])
