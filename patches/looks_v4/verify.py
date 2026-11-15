#!/usr/bin/env python3
"""looks_v4 checks (emulator, offline). The whole patched image runs read/execute; the file API (malloc, free, fopen,
fclose, fread, fseek, ftell) is replaced by patches/film_menu_v2/verify.py's logging stubs over an in-memory file.

  .venv/bin/python -I patches/looks_v4/verify.py <spec without looks_v4> <spec with looks_v4>

E  end to end, real code from fm_load (entered by `calls`, as ed_trig does) to the Film pick (u_apply -> fm_post):
   - a v4 file (curve + mix on two looks) loads: EP7F, L = the file's v3 part with a v3 header (what fm_check accepts),
     P+872 = the block ('EP7H', P, 8 B per look); picks write slot +53..+60 from the look (+60 = 0), a look without
     fields writes zeros, Own / Stock put the snapshot's +53..+59 back and leave +60;
   - a v4 file with a bad extension CRC loads as v3 (P+872 = 0, block freed); a bad header CRC is rejected (EP7X, L and
     block freed);
   - v3 files (2112 B, and 384 B, a size v4 can also have) load and pick exactly as on the image without looks_v4: same
     d0 and callee-saved registers, same L and P after the load, same slot after each pick.
K  anti-brick: package parses, decoded main == the emulated image, restore == stock, and every byte that differs from
   the spec without looks_v4 lies inside a looks_v4 edit.
"""
import hashlib, importlib.util, json, struct, sys, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools')); sys.path.insert(0, str(ROOT / 'external/oly_fw_analysis/tools'))
from penf_emulator import Region, execute  # noqa: E402


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


LX = _load('ep7_lx_build_v', ROOT / 'patches/looks_v4/build.py')
FV = _load('ep7_fmv2_verify_lx', ROOT / 'patches/film_menu_v2/verify.py')
LB = FV.LB
LS, FB, ST = LX.LS, LX.FB, LX.ST
BASE = LX.BASE
POOL, H = LX.POOL1, 0x41
P = POOL + H - 1
EXT_AT = POOL + 0x1000                 # second malloc: the extension block (class-1 pool)
L_AT = FB.POOL2 + 0x4040 * 7 + 0x40
STATE = 0x622cbcc0
STK, SP0 = 0x18000000, 0x18001800
DRV = 0x18100000
FSC = FV.FSC
U_APPLY, FM_LOAD = 0x601e2e28, 0x6143a410
NMAGIC = 0x4e375045
SNAP = bytes(range(101 + 53, 101 + 60)) + bytes([61])   # snapshot +53..+59 (101 + i), slot +60 kept (1 + 60)
SENT = dict(d2=0x22222222, d3=0x33333333, a3=0xa3a3a3a3)

# malloc stub: (C+4) first, then (C+0x24); fread moves the file position
STUB = FV.FS_STUB.replace(""" LOG 1
 mov (C+4),a0
""", """ LOG 1
 mov (C+4),a0
 mov (C+0x24),d0
 mov d0,(C+4)
""")
STUB = STUB.replace("""2:
 mov d2,d0
 cmp 0,d2""", """2:
 mov d2,d0
 mov (C+0x20),d1                  /* fread advances the position (the film_menu_v2 stub reads once only) */
 add d2,d1
 mov d1,(C+0x20)
 cmp 0,d2""")
assert STUB.count('fread advances') == 1 and STUB.count('(C+0x24)') == 1


def image(spec):
    return ST.img_of(spec, LX.STOCK.read_bytes())


def mem(r, name):
    return next(bytes.fromhex(x['hex']) for x in r['memory'] if x['name'] == name)


def p_block():
    b = bytearray(0x2000)
    b[H - 1:H + 3] = b'EP7B'
    struct.pack_into('<I', b, H - 1 + 672, NMAGIC)
    return b


def with_stubs(im):
    code, sy = FV.asm(STUB, 0x18d80000)
    m = bytearray(im)
    for k, a in FV.TRAMPS.items():
        m[a - BASE:a - BASE + 5] = b'\xdc' + struct.pack('<i', sy['s_' + k] - a)
    return bytes(m), code


def regions(im, code, L, Pb, data=None):
    c = bytearray(0x1000 + 0x1000)
    struct.pack_into('<IIIIIIIII', c, 0, FSC + 0x100, L_AT, 0 if data is None else 0x18e00000, 0, len(data or b''), 0,
                     0x7fffffff, 0, 0)
    struct.pack_into('<I', c, 0x24, EXT_AT)
    c[0x1000:0x1000 + len(data or b'')] = data or b''
    return [Region('main', BASE, im, 'rx'), Region('fstub', 0x18d80000, code, 'rx'), Region('fsc', FSC, bytes(c), 'rw', True),
            Region('L', L_AT, bytes(L), 'rw', True), Region('P', POOL, bytes(Pb), 'rw', True),
            Region('state', STATE, struct.pack('<HHI', 0, H, 0), 'r'), Region('stk', STK, bytes(0x2000), 'rw', True)]


def load(im, code, data):
    drv, sy = FV.asm(f' mov {FM_LOAD:#x},a1\n mov {P:#x},a2\n calls (a1)\n', DRV)
    L = b'\xee' * 0x4000
    r = execute(regions(im, code, L, p_block(), data) + [Region('drv', DRV, drv, 'rx')],
                dict(pc=DRV, sp=SP0, d0=0, d1=0, a0=0, a1=0, **SENT), sy['done'], limit=20_000_000)
    rg = r['registers']
    ok = not r['fault'] and rg['pc'] == sy['done'] and all(rg[k] == v for k, v in SENT.items()) and rg['sp'] == SP0
    return ok, mem(r, 'L'), mem(r, 'P'), [x[0] for x in FV.fs_log(r)], r


def pick(im, code, L, Pb, k, pos, slot=None, snap=None):
    """State fm_up leaves before u_apply (as patches/looks_split/verify.py): pos, snapshot, staging T. Records get +32 = 0
    there (no tone block: lt_tone's facade calls stay out; this layer does not read record bytes)."""
    L, Pb = bytearray(L), bytearray(Pb)
    n = L[2120]
    for j in range(n):
        L[64 + 64 * j + 32] = 0
    L[2121 + k], L[2125 + k] = pos, 1
    e = H - 1 + 32 + 64 * k
    Pb[e:e + 64] = slot or bytes(range(1, 65))
    sn = bytearray(snap or bytes(range(101, 165))) + bytearray(16)
    L[2132 + 80 * k:2212 + 80 * k] = sn
    T = bytearray(80)
    if pos == 0:
        T[:] = sn
    elif pos <= n:
        r = L[64 * pos:64 * pos + 64]
        T[:32] = r[:32]; T[64:80] = r[48:64]; T[45] = r[47]
    L[2456:2536] = T
    r = execute(regions(im, code, L, Pb), dict(pc=U_APPLY, sp=SP0, d0=0, d1=0, a0=L_AT, a1=0, d2=0x2222, d3=k, a2=P, a3=0x3333),
                LS.FM_POST, limit=100_000)
    rg = r['registers']
    ok = not r['fault'] and rg['pc'] == LS.FM_POST and (rg['d3'], rg['a2'], rg['a3'], rg['sp']) == (k, P, 0x3333, SP0)
    return ok, mem(r, 'P')[e:e + 64]


def files():
    v3 = (ROOT / 'releases/v0.31d/card/EP7MOD/LOOKS.BIN').read_bytes()
    n = (len(v3) - 64) // 64
    recs = [v3[64 + 64 * j:128 + 64 * j] for j in range(n)]
    ext = [bytes(16)] * n
    ext[0] = LB.ext_record('auto', [6, -10, 4, -6, -8, 4])
    ext[3] = LB.ext_record('log', [-64, 64, 0, 1, -1, 2])
    v4 = LB.make_file(recs, ext)
    assert v4[:4] == b'EP7B' and LB.is_v4(v4) and not LB.check_file(v4) and v4[64:64 + 64 * n] == v3[64:]
    bad_ext = bytearray(v4); bad_ext[-5] ^= 1                    # extension byte: its CRC fails, the header CRC holds
    bad_hdr = bytearray(v4); bad_hdr[100] ^= 2                   # record byte: the header CRC fails
    v3_5 = LB.make_file(recs[:5])                                # 384 B = 64 + 80 * 4: H1 reads its header, falls back
    assert len(v3_5) == 384 and not LB.check_file(v3_5)
    return v3, v4, bytes(bad_ext), bytes(bad_hdr), v3_5, ext


def v3_view(v4):
    """What fm_check sees in L for a good v4 file: the v3 part with a v3 header (lx_hdr)."""
    n = struct.unpack_from('<H', v4, 24)[0]
    d = bytearray(v4[:64 + 64 * n])
    d[4], d[32:38] = 3, bytes(6)
    struct.pack_into('<I', d, 16, zlib.crc32(bytes(d[:16]) + bytes(d[20:])) & 0xffffffff)
    return bytes(d)


def t_e2e(new, base):
    bad, n = [], 0
    v3, v4, bad_ext, bad_hdr, v3_5, ext = files()
    nim, ncode = with_stubs(new)
    bim, bcode = with_stubs(base)
    nl = (len(v3) - 64) // 64
    # v4, good
    ok, L, Pb, calls, r = load(nim, ncode, v4); n += 1
    blk = struct.unpack_from('<I', Pb, H - 1 + 872)[0]
    want_blk = b'EP7H' + struct.pack('<I', P) + b''.join(e[:7] + b'\0' for e in ext)
    if not ok or struct.unpack_from('<I', Pb, H - 1 + 1020)[0] != FB.FMAGIC or L[:len(v3)] != v3_view(v4) \
            or blk != EXT_AT or Pb[EXT_AT - POOL:EXT_AT - POOL + len(want_blk)] != want_blk or 'free' in calls:
        bad.append(('v4 load', ok, hex(blk), calls, r['fault']))
    else:
        cases = [  # label, k, pos, want +53..+60 (None: from the snapshot / unchanged)
            ('look 1: auto + mix', 0, 1, ext[0][:7] + b'\0'), ('look 4 k3: log + mix', 3, 4, ext[3][:7] + b'\0'),
            ('look 2: no fields -> zeros', 1, 2, bytes(8)), ('Own -> snapshot', 2, 0, SNAP),
            ('Stock -> snapshot', 0, nl + 1, SNAP)]
        for lab, k, pos, want in cases:
            ok, s = pick(nim, ncode, L, Pb, k, pos); n += 1
            if not ok or s[53:61] != want:
                bad.append((lab, ok, s[53:61].hex()))
    # v4, bad extension CRC: loads as v3, no block
    ok, L2, Pb2, calls, r = load(nim, ncode, bad_ext); n += 1
    if not ok or struct.unpack_from('<I', Pb2, H - 1 + 1020)[0] != FB.FMAGIC or struct.unpack_from('<I', Pb2, H - 1 + 872)[0] != 0 \
            or L2[:len(v3)] != v3_view(bad_ext) or calls.count('free') != 1:
        bad.append(('v4 bad ext crc', ok, calls))
    else:
        ok, s = pick(nim, ncode, L2, Pb2, 0, 1); n += 1
        if not ok or s[53:61] != bytes(7) + bytes([61]):
            bad.append(('bad ext pick = v3 pick', ok, s[53:61].hex()))
    # v4, bad header CRC: rejected, L and block freed
    ok, L3, Pb3, calls, r = load(nim, ncode, bad_hdr); n += 1
    if not ok or struct.unpack_from('<I', Pb3, H - 1 + 1020)[0] != FB.XMAGIC or struct.unpack_from('<I', Pb3, H - 1 + 872)[0] != 0 \
            or calls.count('free') != 2:
        bad.append(('v4 bad header crc', ok, calls))
    # v3 files: same as the image without looks_v4
    for lab, data in (('v3 2112 B', v3), ('v3 384 B', v3_5)):
        a = load(nim, ncode, data); b = load(bim, bcode, data); n += 1
        same = a[0] and b[0] and a[1] == b[1] and a[2] == b[2] and a[4]['registers']['d0'] == b[4]['registers']['d0']
        if not same or struct.unpack_from('<I', a[2], H - 1 + 1020)[0] != FB.FMAGIC:
            bad.append((lab, 'load differs', a[3], b[3])); continue
        m = a[1][2120]
        for k, pos in ((0, 1), (1, 2), (2, 0), (3, m + 1)):
            x, y = pick(nim, ncode, a[1], a[2], k, pos), pick(bim, bcode, b[1], b[2], k, pos); n += 1
            if not (x[0] and y[0]) or x[1] != y[1]:
                bad.append((lab, 'pick', k, pos, x[1][53:61].hex(), y[1][53:61].hex()))
    return n, bad


def t_package(spec, bsp, new, base):
    BP = _load('ep7_bp_lx', ROOT / 'tools/build_package.py')
    oc = _load('ep7_oc_lx', ROOT / 'external/oly_fw_analysis/tools/oly_container.py')
    stock = LX.STOCK.read_bytes()
    pkg, rst, _ = BP.build(spec, BP.STOCK.read_bytes())
    parts = oc.parse(pkg)
    mine = [(int(e['addr'], 16), int(e['addr'], 16) + len(e['new']) // 2) for e in spec['edits']
            if e['kind'] == '0x100' and not e['addr'].startswith('off:') and 'looks_v4' in e['why']]
    diff = [i + BASE for i in range(len(new)) if new[i] != base[i]] if len(new) == len(base) else None
    stray = None if diff is None else [hex(a) for a in diff if not any(lo <= a < hi for lo, hi in mine)]
    return dict(reparses=[b.kind for b in parts] == [int(x, 16) for x in spec['components']],
                decoded_is_emulated=bytes(parts[0].payload) == new,
                restore_is_stock=hashlib.sha256(oc.parse(rst)[0].payload).hexdigest() == hashlib.sha256(stock).hexdigest(),
                changed_bytes_are_looks_v4=diff is not None and not stray), (len(diff or []), stray[:8] if stray else stray)


def main():
    bsp, spec = json.loads(Path(sys.argv[1]).read_text()), json.loads(Path(sys.argv[2]).read_text())
    new, base = image(spec), image(bsp)
    fails = []
    n, bad = t_e2e(new, base)
    print(f'E end to end: {n - len(bad)}/{n}', bad[:6]); fails += ['E'] * bool(bad)
    k, info = t_package(spec, bsp, new, base)
    print('K', k, 'changed bytes', info[0], 'stray', info[1]); fails += ['K'] * (not all(k.values()))
    if fails:
        sys.exit(f'VERIFY FAILED {fails}')
    print('ALL OK')


if __name__ == '__main__':
    main()
