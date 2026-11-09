#!/usr/bin/env python3
"""Rec View fix (issue #19), test r2 (r1 + patches/grain_kind): COLOR bloom / clarity / Star Light flags stay off the small 0x1xx developments. Offline.
docs/ISSUES_19_20.md "As built (recview r1)".

  .venv/bin/python -I patches/recview/build.py releases/v0.30/edits.json --out generated/recview/edits.json
  .venv/bin/python -I tools/build_package.py generated/recview/edits.json --out generated/recview/rel
  .venv/bin/python -I patches/recview/verify.py releases/v0.30/edits.json generated/recview/edits.json generated/recview/rel

apply(spec, version='0.31r2') -> spec. r2 first applies patches/grain_kind. One stub (rv_gate) in dead EVF gamma table space; one edit inside the bloom block:
bloom_flag's tail `jmp 0x603eabdd` -> `jmp rv_gate`. rv_gate clears 0x40 / 0x80 on key-11 jobs whose type (stock mapper
0x603ea909, the call the builder makes next) is 0x1xx or 0x4x, the rule stock 0x60353b15 applies to art keys, then
replays the tail.
"""
import argparse, copy, importlib.util, json, re, struct
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
BASE, SRC = 0x60020020, 'patches/recview'

AT, END = 0x601de780, 0x601de800                    # dead EVF gamma table space (CODE_SPACE_MAP: free 0x601de780..0x601dea4c)
STEP_LO, STEP_HI = 0x601e3b40, 0x601e3d6c           # EVF step-table words: the only allowed refs into the block
SEC1, SEC1_SRC = 0x600d7800, 0x40757800             # descriptor 0x60027068 entry 0: flash source alias
FALSE_POS = {}
CONV_BACK = 0x603eabdd                              # 0x603eab39: bne 0x603eabe7 after movbu (24054,a3),d0; cmp 0,d0
TYPE_FN = 0x603ea909                                # job type from the source request (builders: 0x603e619a, 0x603e8ae2)
BLOOM_LO, BLOOM_HI = 0x6055e5c0, 0x6055e700         # bloom + clarity block (section 2)
TAIL = bytes.fromhex('fa43f65da000')                # movbu (24054,a3),d0; cmp 0,d0
BAD = {'mul', 'mulu', 'div', 'divu', 'setlb', 'llt', 'lne', 'leq', 'lra', 'lcc', 'lcs', 'trap'}


def u32(b, a):
    return struct.unpack_from('<I', b, a - BASE)[0]


def rel(at, dst):
    return struct.pack('<i', dst - at)


def img_of(spec, stock):
    im = bytearray(stock)
    for e in spec['edits']:
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            a = int(e['addr'], 16) - BASE; n = bytes.fromhex(e['new']); im[a:a + len(n)] = n
    return bytes(im)


def check_free(spec, stock):
    """No edit in the block, no data word pointing into it except EVF step-table words, no call/jmp into it."""
    for e in spec['edits']:
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            a, n = int(e['addr'], 16), len(e['new']) // 2
            if a < END and AT < a + n:
                raise SystemExit(f'code block overlaps edit {e["addr"]}')
    d = np.frombuffer(stock, np.uint8).astype(np.int64)
    w = d[:-3] | (d[1:-2] << 8) | (d[2:-1] << 16) | (d[3:] << 24)
    for off in (0, 0x40000000, SEC1_SRC - SEC1):
        lo, hi = (AT + off) & 0xffffffff, (END + off) & 0xffffffff
        for i in np.nonzero((w >= lo) & (w < hi))[0]:
            at = int(i) + BASE
            if STEP_LO <= at < STEP_HI and (u32(stock, at) - 0x601de13c) % 0x100 == 0:
                continue
            if at in FALSE_POS and stock[at - BASE:at - BASE + 4].hex() == FALSE_POS[at]:
                continue
            raise SystemExit(f'reference into {AT:#x}..{END:#x} at {at:#x}')
    im = np.frombuffer(img_of(spec, stock), np.uint8).astype(np.int64)
    same = im == d
    pc = np.arange(len(im) - 8, dtype=np.int64) + BASE
    evf = (pc >= 0x601de13c) & (pc < 0x601e3b3c) & same[:-8] & same[1:-7] & same[2:-6] & same[3:-5] & same[4:-4]
    for op, n in ((0xdd, 4), (0xdc, 4), (0xcd, 2), (0xcc, 2)):
        m = (im[:-8] == op) & ~evf
        disp = im[1:-7] | (im[2:-6] << 8) if n == 2 else im[1:-7] | (im[2:-6] << 8) | (im[3:-5] << 16) | (im[4:-4] << 24)
        disp = np.where(disp >= (1 << (8 * n - 1)), disp - (1 << (8 * n)), disp)
        bad = np.nonzero(m & (pc + disp >= AT) & (pc + disp < END))[0]
        if len(bad):
            raise SystemExit(f'branch into the block from {hex(int(bad[0]) + BASE)}')


def find_tail(im):
    """bloom_flag's tail in the bloom block: movbu (24054,a3),d0; cmp 0,d0; jmp 0x603eabdd. Exactly one."""
    hits = []
    for a in range(BLOOM_LO, BLOOM_HI - 11):
        o = a - BASE
        if im[o:o + 6] == TAIL and im[o + 6] == 0xdc and struct.unpack_from('<i', im, o + 7)[0] == CONV_BACK - (a + 6):
            hits.append(a + 6)
    if len(hits) != 1:
        raise SystemExit(f'bloom tail jmp: {len(hits)} matches')
    return hits[0]


def put(spec, stock, addr, old, new, why):
    """Into the edit that covers addr (chaining another layer's bytes). old = the bytes there now (checked)."""
    im = img_of(spec, stock)
    if im[addr - BASE:addr - BASE + len(old)] != old:
        raise SystemExit(f'{addr:#x}: {im[addr - BASE:addr - BASE + len(old)].hex()} != {old.hex()} ({why})')
    for e in spec['edits']:
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            a, n = int(e['addr'], 16), len(e['new']) // 2
            if a <= addr and addr + len(new) <= a + n:
                b = bytearray.fromhex(e['new']); b[addr - a:addr - a + len(new)] = new; e['new'] = b.hex()
                e['why'] += f' [recview: {why}]'
                return
    raise SystemExit(f'{addr:#x}: not inside an existing edit')


def apply(spec, version='0.31r2', grain_kind=True):
    """r2 = patches/grain_kind (gc_flag kind guards) + rv_gate. grain_kind=False gives r1's edits."""
    stock = STOCK.read_bytes()
    spec = copy.deepcopy(spec)
    if 'recview' in spec:
        raise SystemExit('recview already applied')
    if grain_kind:
        spec = _load('grain_kind_build', ROOT / 'patches/grain_kind/build.py').apply(spec)
    spec = FV.apply(spec, version)
    im = img_of(spec, stock)
    check_free(spec, stock)
    if stock[CONV_BACK - 6 - BASE:CONV_BACK - BASE] != TAIL or stock[CONV_BACK - BASE:CONV_BACK + 2 - BASE] != b'\xc9\x0a':
        raise SystemExit('converter tail 0x603eabd7 differs from stock')
    if stock[TYPE_FN - BASE:TYPE_FN + 4 - BASE] != bytes.fromhex('92fa62c2'):
        raise SystemExit('type mapper 0x603ea909 differs')
    for c in (0x603e619a, 0x603e8ae2):                # the builders' own call: call 0x603ea909,[d2,a2],12
        if stock[c - BASE] != 0xcd or struct.unpack_from('<h', stock, c + 1 - BASE)[0] != TYPE_FN - c or stock[c + 3 - BASE:c + 5 - BASE] != b'\xa0\x0c':
            raise SystemExit(f'builder type call {c:#x} differs')
    for c, st in ((0x603e614a, 0x603e615c), (0x603e8aab, 0x603e8abd)):   # params+4 = source; then call 0x603eab39 with a1 = params+12
        if stock[c - BASE:c + 3 - BASE] != bytes.fromhex('f83e04') or stock[st - BASE] != 0xcd:
            raise SystemExit(f'builder {c:#x}: mov a3,(4,a2) not found')
    tail_jmp = find_tail(im)
    src = (HERE / 'rv.s.in').read_text()
    syms = dict(ep7_conv_back=CONV_BACK, ep7_type=TYPE_FN)
    code, lst, s, _ = SB3.assemble(src, AT, syms)
    if AT + len(code) > END:
        raise SystemExit(f'{len(code)} B does not fit {END - AT}')
    ins = SB3.disasm(code, AT, s['rv_end'])
    if (any(op in BAD for _, op, _ in ins) or any(k == 'abs' for _, _, k, _ in SB3.store_audit(ins))
            or any(code[a - AT] == 0xfb for a, _, _ in ins) or AT % 4):
        raise SystemExit('forbidden instruction, fb-prefixed form, absolute store or misaligned block')
    if [t for _, t, k, _ in SB3.store_audit(ins) if k == 'ind'] != ['mov d0,(a2)']:
        raise SystemExit(f'unexpected stores: {SB3.store_audit(ins)}')
    spec['edits'].append(dict(kind='0x100', addr=hex(AT), expect=stock[AT - BASE:AT - BASE + len(code)].hex(), new=code.hex(), source=SRC,
                              why=f'recview r1 rv_gate ({len(code)} B, dead EVF gamma table)'))
    put(spec, stock, tail_jmp, b'\xdc' + rel(tail_jmp, CONV_BACK), b'\xdc' + rel(tail_jmp, s['rv_gate']),
        'bloom_flag tail jmp 0x603eabdd -> rv_gate (key-11 0x40/0x80 off job types 0x1xx/0x4x)')
    spec['recview'] = dict(built_by=SRC, test='r2' if grain_kind else 'r1', grain_kind=grain_kind, version=version, code_at=hex(AT), code_len=len(code), claim=[hex(AT), hex(END)],
                           site=hex(tail_jmp), type_fn=hex(TYPE_FN), conv_back=hex(CONV_BACK),
                           symbols={k: hex(v) for k, v in s.items() if k.startswith('rv_')})
    return spec


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--version', default='0.31r2')
    ap.add_argument('--no-grain-kind', action='store_true', help='r1: rv_gate only')
    a = ap.parse_args()
    spec = apply(json.loads(a.spec.read_text()), a.version, not a.no_grain_kind)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(spec, indent=1))
    print(json.dumps({k: v for k, v in spec['recview'].items() if k != 'symbols'}), spec['recview']['symbols'])
