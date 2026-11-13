#!/usr/bin/env python3
"""looks_split checks (emulator only, offline). The whole patched image is mapped read/execute; the heap P, L, the
bundles state word and a stack are the only RAM.

  .venv/bin/python -I patches/looks_split/verify.py <spec before looks_split> <v0.32 spec>

L  fm_load's fm_check call site (0x6143a4ed -> 0x6143a4f2) on L: a v3 file without split (accepted, records unchanged,
   stash 0, tag), the same file with split on three looks (accepted, records cleaned, CRC of the cleaned file, stash),
   a bad colour, a bad strength, split behind a 13-character name, a bad CRC (all rejected, L as read). The base image:
   the plain file accepted, the split file rejected (why the panel writes split only for v0.32).
P  Film pick from u_apply to fm_post: library look with split -> slot +62/+63; library look without -> cleared;
   Own / Stock -> the snapshot's +62/+63; a swapped-in P2, L without the tag, no snapshot -> slot untouched.
   The base image: every pick leaves +62/+63 as they were (today's behaviour).
K  anti-brick: package parses, restore == stock, decoded main == the emulated image.
"""
import hashlib, importlib.util, json, struct, sys, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools')); sys.path.insert(0, str(ROOT / 'external/oly_fw_analysis/tools'))
from penf_emulator import Region, execute  # noqa: E402


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


LS = _load('ep7_ls_build_v', ROOT / 'patches/looks_split/build.py')
FB, ST = LS.FB, LS.ST
BASE = LS.BASE
POOL, H = 0xa1f8d800, 0x41
P = POOL + H - 1
L_AT = FB.POOL2 + 0x4040 * 7 + 0x40
STATE = 0x622cbcc0                    # u16 at +2 = handle
STK, SP0 = 0x18000000, 0x18001800
U_APPLY = 0x601e2e28
NMAGIC = 0x4e375045
REGS = dict(d2=0x2222, d3=0, a2=P, a3=0x3333)


def image(spec):
    return ST.img_of(spec, LS.STOCK.read_bytes())


def mem(r, name):
    return next(bytes.fromhex(x['hex']) for x in r['memory'] if x['name'] == name)


def regions(im, L, Pb):
    return [Region('main', BASE, im, 'rx'), Region('L', L_AT, bytes(L), 'rw', True), Region('P', POOL, bytes(Pb), 'rw', True),
            Region('state', STATE, struct.pack('<HHI', 0, H, 0), 'r'), Region('stk', STK, bytes(0x2000), 'rw', True)]


def p_block():
    b = bytearray(0x1000 + H - 1)
    b[H - 1:H + 3] = b'EP7B'
    struct.pack_into('<I', b, H - 1 + 672, NMAGIC)
    struct.pack_into('<II', b, H - 1 + 1016, L_AT, FB.FMAGIC)
    return b


def refile(d):
    d = bytearray(d)
    struct.pack_into('<I', d, 16, zlib.crc32(bytes(d[:16]) + bytes(d[20:])) & 0xffffffff)
    return bytes(d)


SPLIT = {3: (0x13, 0xf6), 13: (0x5a, 0x02), 26: (0x37, 0x1b)}   # Classic Neg / CineStill800 (12 chars) / Polaroid


def with_split(d, sp=SPLIT):
    d = bytearray(d)
    for j, (a, b) in sp.items():
        d[64 + 64 * j + 61], d[64 + 64 * j + 62] = a, b
    return refile(d)


def load_run(im, data):
    L = bytearray(b'\xee' * 0x4000)
    L[:len(data)] = data
    r = execute(regions(im, L, p_block()), dict(pc=LS.FM_CALL, sp=SP0, d0=0xd0d0, d1=0xd1d1, d2=len(data), d3=len(data), a2=P,
                                                a3=L_AT, a0=0xa0a0, a1=0xa1a1), LS.FM_AFTER, limit=2_000_000)
    return r, mem(r, 'L')


def t_load(new, base, looks):
    bad, n = [], 0
    sp = with_split(looks)
    cases = [('plain', looks, 0), ('split', sp, 0),
             ('bad colour', with_split(looks, {3: (0x0c, 0)}), 1), ('bad strength', with_split(looks, {3: (0x63, 0)}), 1),
             ('bad strength hl', with_split(looks, {5: (0, 0xa0)}), 1), ('bad crc', sp[:17] + bytes([sp[17] ^ 1]) + sp[18:], 1)]
    long = bytearray(looks)                # look 0 named 13 characters, split on it
    long[64 + 48:64 + 64] = b'ABCDEFGHIJKLM'.ljust(16, b'\0')
    cases.append(('13-char name + split', with_split(refile(long), {0: (0x13, 0)}), 1))
    cases.append(('13-char name, no split', refile(long), 0))
    for lab, data, want in cases:
        r, L = load_run(new, data)
        rg = r['registers']; n += 1
        if r['fault'] or rg['pc'] != LS.FM_AFTER or (rg['d2'], rg['d3'], rg['a2'], rg['a3'], rg['sp']) != (len(data), len(data), P, L_AT, SP0):
            bad.append((lab, 'run', r['fault'], hex(rg['pc']))); continue
        if rg['d0'] != want:
            bad.append((lab, 'd0', rg['d0'])); continue
        tag = struct.unpack_from('<II', L, LS.TAG)
        if want == 0:
            clean = bytearray(data)
            for j in range((len(data) - 64) // 64):
                clean[64 + 64 * j + 61:64 + 64 * j + 63] = b'\0\0'
            clean = refile(clean)
            stash = bytes(x for j in range((len(data) - 64) // 64) for x in data[64 + 64 * j + 61:64 + 64 * j + 63])
            if L[:len(data)] != clean or tag != (LS.WMAGIC, P) or L[LS.STASH:LS.STASH + len(stash)] != stash:
                bad.append((lab, 'L', tag))
        elif L[:len(data)] != data or tag[0] != 0:
            bad.append((lab, 'L changed on reject', tag))
    for lab, data, want in (('base plain', looks, 0), ('base split', sp, 1)):
        r, L = load_run(base, data); n += 1
        if r['fault'] or r['registers']['pc'] != LS.FM_AFTER or r['registers']['d0'] != want:
            bad.append((lab, r['fault'], r['registers']['d0']))
    return n, bad


def pick_run(im, looks, k, pos, slot62, snap62=(0x44, 0x55), snap=1, tag=True, swapped=False):
    """State fm_up leaves before u_apply: pos, snapshot, staging T (a record's 0..31 + name, or zero / snapshot)."""
    n = (len(looks) - 64) // 64
    L = bytearray(b'\xee' * 0x4000)
    L[:len(looks)] = looks
    for j in range(n):
        L[64 + 64 * j + 32] = 0           # no tone block: lt_tone's facade calls stay out of this test
    struct.pack_into('<II', L, 2112, FB.LMAGIC, P)
    L[2120] = n
    L[2121:2129] = bytes(8)
    L[2121 + k], L[2125 + k] = pos, snap
    Pb = p_block()
    e = H - 1 + 32 + 64 * k
    Pb[e:e + 64] = bytes(range(1, 65))
    Pb[e + 62], Pb[e + 63] = slot62
    sn = bytearray(Pb[e:e + 64]) + bytearray(16)
    sn[62], sn[63] = snap62
    L[2132 + 80 * k:2212 + 80 * k] = sn
    T = bytearray(80)
    if pos == 0:
        T[:] = sn
    elif pos <= n:
        r = L[64 * pos:64 * pos + 64]
        T[:32] = r[:32]; T[64:80] = r[48:64]; T[45] = r[47]
    L[2456:2536] = T
    if tag:
        stash = bytes(x for j in range(n) for x in SPLIT.get(j, (0, 0)))
        struct.pack_into('<II', L, LS.TAG, LS.WMAGIC, P)
        L[LS.STASH:LS.STASH + len(stash)] = stash
    if swapped:                           # the editor runs on a P2 whose handle points back at P
        struct.pack_into('<III', Pb, H - 1 + 960, 0x56375045, P, 0x801)   # vm 'EP7V', vp = itself, vh -> the real P
        Pb[0x800:0x804] = b'EP7B'
    r = execute(regions(im, L, Pb), dict(pc=U_APPLY, sp=SP0, d0=0, d1=0, a0=L_AT, a1=0, **dict(REGS, d3=k)), LS.FM_POST, limit=50_000)
    return r, mem(r, 'P')[e + 62:e + 64]


def t_pick(new, base, looks):
    bad, n = [], 0
    nl = (len(looks) - 64) // 64
    cases = [  # label, k, pos, kwargs, want (None = untouched)
        ('look with split', 0, 4, {}, SPLIT[3]), ('look with split k3', 3, 14, {}, SPLIT[13]),
        ('look without split clears', 1, 1, {}, (0, 0)), ('Own -> snapshot', 2, 0, {}, (0x44, 0x55)),
        ('Stock -> snapshot', 0, nl + 1, {}, (0x44, 0x55)), ('no snapshot', 0, nl + 1, dict(snap=0), None),
        ('L without tag', 0, 4, dict(tag=False), None), ('P2 swapped in', 0, 4, dict(swapped=True), None)]
    for lab, k, pos, kw, want in cases:
        r, s = pick_run(new, looks, k, pos, (0x21, 0x32), **kw); n += 1
        rg = r['registers']
        if r['fault'] or rg['pc'] != LS.FM_POST or (rg['d3'], rg['a2'], rg['a3'], rg['sp']) != (k, P, 0x3333, SP0):
            bad.append((lab, 'run', r['fault'], hex(rg['pc']))); continue
        if tuple(s) != (want or (0x21, 0x32)):
            bad.append((lab, s.hex()))
    for lab, k, pos in (('base look', 0, 4), ('base clear?', 1, 1), ('base Own', 2, 0), ('base Stock', 0, nl + 1)):
        r, s = pick_run(base, looks, k, pos, (0x21, 0x32)); n += 1
        if r['fault'] or r['registers']['pc'] != LS.FM_POST or tuple(s) != (0x21, 0x32):
            bad.append((lab, r['fault'], s.hex()))
    return n, bad


def main():
    base_p, new_p = sys.argv[1], sys.argv[2]
    bsp, spec = json.loads(Path(base_p).read_text()), json.loads(Path(new_p).read_text())
    new, base = image(spec), image(bsp)
    looks = (ROOT / 'releases/v0.31d/card/EP7MOD/LOOKS.BIN').read_bytes()
    fails = []
    n, bad = t_load(new, base, looks)
    print(f'L load: {n - len(bad)}/{n}', bad[:6]); fails += ['L'] * bool(bad)
    n, bad = t_pick(new, base, looks)
    print(f'P pick: {n - len(bad)}/{n}', bad[:6]); fails += ['P'] * bool(bad)
    if '--no-package' not in sys.argv:
        BP = _load('ep7_bp_ls', ROOT / 'tools/build_package.py')
        oc = _load('ep7_oc_ls', ROOT / 'external/oly_fw_analysis/tools/oly_container.py')
        stock = LS.STOCK.read_bytes()
        pkg, rst, _ = BP.build(spec, BP.STOCK.read_bytes())
        parts = oc.parse(pkg)
        k = dict(reparses=[b.kind for b in parts] == [int(x, 16) for x in spec['components']],
                 restore_is_stock=hashlib.sha256(oc.parse(rst)[0].payload).hexdigest() == hashlib.sha256(stock).hexdigest(),
                 decoded_is_emulated=bytes(parts[0].payload) == new)
        print('K', k); fails += ['K'] * (not all(k.values()))
    if fails:
        sys.exit(f'VERIFY FAILED {fails}')
    print('ALL OK')


if __name__ == '__main__':
    main()
