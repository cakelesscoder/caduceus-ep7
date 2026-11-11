#!/usr/bin/env python3
"""Look name in the JPEG's EXIF (ImageDescription + UserComment, the Caduceus for OM-3 text layout, name only). Offline.
docs/FEATURE_GAPS.md "1. Look name in EXIF"; ex.s.in has the contract.

  .venv/bin/python -I patches/exif_name/build.py releases/v0.31c/edits.json --out generated/exif_name/edits.json [--version 0.31d]

apply(spec, version) -> spec. One rel32 retarget (capture setup 0x6030288d, the copyright-enable getter call) -> ex_get in the
section-7 FF tail (loads 2nd, before section 2 that holds the site). ex_get calls v0.25's sc_slot (section 1).
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


SB3 = _load('ep7_sd_bundles_v3_build', ROOT / 'patches/sd_bundles_v3/build.py')
FV = _load('fw_version_build', ROOT / 'patches/fw_version/build.py')
STOCK = ROOT / 'analysis/ep7_1100/00_0100_406a0020.decoded.bin'
BASE, SRC = 0x60020020, 'patches/exif_name'

AT, END = 0x61378d80, 0x61378f00        # section-7 FF tail: after ap_custom's ap_gd claim (to 0x61378d40) + guard; before the aperture-ring claim 0x61378f8c
SEC7, SEC7_SRC = 0x612c7000, 0x41947000  # descriptor 0x60027068 entry 6
SITE = 0x6030288d                        # call 0x6005e971,[d2,d3],12 (key 0x5ef1) in capture setup 0x603017f3
GETTER = 0x6005e971
SITE_BYTES = bytes.fromhex('dd') + struct.pack('<i', GETTER - SITE) + bytes.fromhex('c00c')
SITE_PRE = bytes.fromhex('2cf15e900004')          # mov 24305,d0; mov 0,a0; clr d1
CAP_USE = bytes.fromhex('5c08')                    # 0x60302898: mov (8,sp),a0 (cap; same sp as the site)
TAGS = {0x010e: (2, 32, 0x5a8), 0x9286: (7, 125, 0x67c)}
TAG_TABLE = (0x604dadf0, 0x604db200)
UC_FILL = 0x60301252                               # mov 1668,a0; add d3,a0; mov 32,d1 ... cmp 117,d0
BAD = {'mul', 'mulu', 'div', 'divu', 'setlb', 'llt', 'lne', 'leq', 'lra', 'lcc', 'lcs', 'trap'}


def img_of(spec, stock):
    im = bytearray(stock)
    for e in spec['edits']:
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            a = int(e['addr'], 16) - BASE; n = bytes.fromhex(e['new']); im[a:a + len(n)] = n
    return bytes(im)


def check_stock(stock):
    if stock[SITE - 6 - BASE:SITE - BASE] != SITE_PRE or stock[SITE - BASE:SITE + 7 - BASE] != SITE_BYTES:
        raise SystemExit('hook site 0x6030288d differs from stock')
    if stock[SITE + 11 - BASE:SITE + 13 - BASE] != CAP_USE:
        raise SystemExit('cap read after the site differs')
    if stock[UC_FILL - BASE:UC_FILL + 3 - BASE] != bytes.fromhex('248406'):
        raise SystemExit('UserComment space fill 0x60301252 differs')
    found = {}
    for a in range(TAG_TABLE[0], TAG_TABLE[1], 12):
        tag, typ, cnt, off = struct.unpack_from('<HHII', stock, a - BASE)
        if tag in TAGS and tag not in found:
            found[tag] = (typ, cnt, off)
    if found != TAGS:
        raise SystemExit(f'tag table: {found}')
    s, src, dst = struct.unpack_from('<3I', stock, 0x60027068 + 12 * 6 - BASE)
    if (s, src, dst) != (SEC7, SEC7_SRC, SEC7):
        raise SystemExit('section-7 descriptor differs')


def check_free(spec, stock, im):
    for e in spec['edits']:
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            a, n = int(e['addr'], 16), len(e['new']) // 2
            if a < END + 16 and AT - 16 < a + n:
                raise SystemExit(f'claim overlaps edit {e["addr"]}')
            if a < SITE + 5 and SITE + 1 < a + n:
                raise SystemExit(f'hook site overlaps edit {e["addr"]}')
    if set(im[AT - 16 - BASE:END + 16 - BASE]) != {0xff}:
        raise SystemExit('claim (with guards) is not FF')
    d = np.frombuffer(im, np.uint8).astype(np.int64)
    w = d[:-3] | (d[1:-2] << 8) | (d[2:-1] << 16) | (d[3:] << 24)
    for off in (0, 0x40000000, SEC7_SRC - SEC7):
        lo, hi = (AT - 16 + off) & 0xffffffff, (END + 16 + off) & 0xffffffff
        hits = np.nonzero((w >= lo) & (w < hi))[0]
        if len(hits):
            raise SystemExit(f'abs32 reference into the claim at {hex(int(hits[0]) + BASE)}')
    pc = np.arange(len(d) - 8, dtype=np.int64) + BASE
    for op, n in ((0xdd, 4), (0xdc, 4), (0xcd, 2), (0xcc, 2)):
        m = d[:-8] == op
        disp = d[1:-7] | (d[2:-6] << 8) if n == 2 else d[1:-7] | (d[2:-6] << 8) | (d[3:-5] << 16) | (d[4:-4] << 24)
        disp = np.where(disp >= (1 << (8 * n - 1)), disp - (1 << (8 * n)), disp)
        bad = np.nonzero(m & (pc + disp >= AT - 16) & (pc + disp < END + 16))[0]
        if len(bad):
            raise SystemExit(f'branch into the claim from {hex(int(bad[0]) + BASE)}')


def apply(spec, version='0.31d'):
    stock = STOCK.read_bytes()
    spec = copy.deepcopy(spec)
    if 'exif_name' in spec:
        raise SystemExit('exif_name already applied')
    sc_slot = int(spec['v025']['symbols']['sc_slot'], 16)
    spec = FV.apply(spec, version)
    im = img_of(spec, stock)
    check_stock(stock)
    if im[SITE - BASE:SITE + 7 - BASE] != SITE_BYTES:
        raise SystemExit('hook site already patched')
    if im[sc_slot - BASE:sc_slot + 6 - BASE] != bytes.fromhex('fccc81940000'):
        raise SystemExit('sc_slot entry differs')
    check_free(spec, stock, im)
    if SB3.HDR_LEN != 32 or (SB3.NAMES_LO, SB3.MARK_OFF) != (544, 672):
        raise SystemExit('P layout differs')
    sub = dict(state=hex(SB3.STATE), lim=hex(SB3.LIM), pool=hex(SB3.POOL), bmagic=hex(SB3.MAGIC), hdr_len=SB3.HDR_LEN,
               names=SB3.NAMES_LO, nmark=SB3.MARK_OFF, nmagic=hex(SB3.NMAGIC))
    src = SB3.subst((HERE / 'ex.s.in').read_text(), sub)
    cfg_fm = int(spec['look_editor']['symbols']['ed_cfg_fm'], 16)
    lt_mod = int(spec['look_tone']['symbols']['lt_mod'], 16)
    if struct.unpack_from('<I', im, cfg_fm - BASE)[0] != lt_mod or im[lt_mod - BASE:lt_mod - BASE + 3] != bytes.fromhex('cfc087'):
        raise SystemExit('ed_cfg_fm is not lt_mod (movm [d2,d3],(sp); mov d1,d3)')
    code, lst, s, _ = SB3.assemble(src, AT, dict(ep7_getter=GETTER, ep7_sc_slot=sc_slot, ep7_cfg_fm=cfg_fm))
    if s['ex_get'] != AT or AT + len(code) > END:
        raise SystemExit(f'{len(code)} B does not fit {END - AT}')
    ins = SB3.disasm(code, AT, s['ex_end'])
    if any(op in BAD for _, op, _ in ins) or any(code[a - AT] == 0xfb for a, _, _ in ins):
        raise SystemExit('forbidden instruction or fb-prefixed form')
    st = SB3.store_audit(ins)
    if any(k == 'abs' for _, _, k, _ in st) or {t for _, t, k, _ in st if k == 'ind'} != {'movbu d0,(a0)'}:
        raise SystemExit(f'unexpected stores: {st}')
    spec['edits'].append(dict(kind='0x100', addr=hex(AT), expect=stock[AT - BASE:AT - BASE + len(code)].hex(), new=code.hex(), source=SRC,
                              why=f'exif_name {version} ex_get ({len(code)} B, section-7 FF tail): look name -> ImageDescription / UserComment'))
    spec['edits'].append(dict(kind='0x100', addr=hex(SITE + 1), expect=stock[SITE + 1 - BASE:SITE + 5 - BASE].hex(),
                              new=struct.pack('<i', AT - SITE).hex(), source=SRC,
                              why='exif_name: capture setup call 0x6005e971 (key 0x5ef1) -> ex_get'))
    spec['exif_name'] = dict(built_by=SRC, version=version, code_at=hex(AT), code_len=len(code), claim=[hex(AT), hex(END)], site=hex(SITE),
                             fields={'ImageDescription': 'cap+1448, 32 B: name, NUL-filled', 'UserComment': 'cap+1668, 117 B: "Caduceus <name>", spaces'},
                             symbols={k: hex(v) for k, v in s.items() if k.startswith('ex_')})
    return spec


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--version', default='0.31d')
    a = ap.parse_args()
    spec = apply(json.loads(a.spec.read_text()), a.version)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(spec, indent=1))
    print(json.dumps({k: v for k, v in spec['exif_name'].items() if k != 'symbols'}), spec['exif_name']['symbols'])
