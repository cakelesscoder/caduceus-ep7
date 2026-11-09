#!/usr/bin/env python3
"""Emulated load check of card files with the h2 image's own loader checks (sd_check for BUNDLES.BIN, fm_check for
LOOKS.BIN), plus negative controls. Offline. The name section of BUNDLES.BIN is checked by tools/ep7_bundles_bin.py.

  .venv/bin/python -I patches/halation/check_card.py generated/halation/h2/edits.json generated/halation/h2/card/EP7MOD
"""
import importlib.util, json, struct, sys, zlib
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'external/oly_fw_analysis/tools'))
from penf_emulator import Region, execute  # noqa: E402


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


MV = _load('mv', ROOT / 'patches/v026_movie/build.py')
BASE, CALLER, STK, BUF = 0x60020020, 0x18000000, 0x18010000, 0x1d000000
FM_CHECK = 0x6143a5a6          # fm_core fm_check (a3 = file, d3 = size -> d0), found by its body in sec 9


def run(im, entry, frame, regs, data):
    wr = b'\xdd' + struct.pack('<i', entry - CALLER) + frame + b'\xcb'
    rg = [Region('sec3', 0x605b7000, im[0x605b7000 - BASE:0x605b7800 - BASE], 'rx'), Region('sec9', 0x6143a000, im[0x6143a000 - BASE:0x6143a800 - BASE], 'rx'),
          Region('low', 0x60020020, im[:0x60100000 - BASE], 'rx'), Region('c', CALLER, wr, 'rx'), Region('stk', STK, bytes(0x4000), 'rw'),
          Region('buf', BUF, bytes(data) + bytes(4096 - len(data)), 'rw')]
    r = execute(rg, dict(dict(pc=CALLER, sp=STK + 0x3000), **regs), CALLER + 7, limit=400000, timeout=120)
    return r['fault'], r['registers']['d0'] if r['registers']['pc'] == CALLER + 7 else 'no return'


def sd(im, d):
    return run(im, int(SPEC['sd_bundles_v3']['symbols']['sd_check'], 16), b'\xf0\x10', {'a0': BUF}, d)


def fm(im, d):
    return run(im, FM_CHECK, b'\xf0\x14', {'a3': BUF, 'd3': len(d)}, d)


def recrc_b(d):
    d = bytearray(d); struct.pack_into('<I', d, 16, zlib.crc32(bytes(d[:16]) + bytes(d[20:544])) & 0xffffffff); return bytes(d)


def recrc_l(d):
    d = bytearray(d); struct.pack_into('<I', d, 16, zlib.crc32(bytes(d[:16]) + bytes(d[20:])) & 0xffffffff); return bytes(d)


SPEC = json.loads(Path(sys.argv[1]).read_text())
card = Path(sys.argv[2])
im = MV.img_of(SPEC, MV.STOCK.read_bytes())
assert im[FM_CHECK - BASE:FM_CHECK - BASE + 2] == b'\xfc\xdd', 'fm_check moved'
B, L = (card / 'BUNDLES.BIN').read_bytes(), (card / 'LOOKS.BIN').read_bytes()
ok = True
for name, fn, data, want in (
        ('BUNDLES.BIN', sd, B, 0),
        ('BUNDLES.BIN COLOR2 +52 = 4 (High)', sd, recrc_b(B[:32 + 64 + 52] + b'\x04' + B[32 + 64 + 53:]), 0),
        ('BUNDLES.BIN COLOR2 +52 = 5 (rejected)', sd, recrc_b(B[:32 + 64 + 52] + b'\x05' + B[32 + 64 + 53:]), 1),
        ('BUNDLES.BIN bad CRC (rejected)', sd, B[:16] + bytes([B[16] ^ 1]) + B[17:], 1),
        ('LOOKS.BIN', fm, L, 0),
        ('LOOKS.BIN look 0 tint 5 (rejected)', fm, recrc_l(L[:64 + 47] + b'\x05' + L[64 + 48:]), 1),
        ('LOOKS.BIN bad CRC (rejected)', fm, L[:16] + bytes([L[16] ^ 1]) + L[17:], 1)):
    f, d0 = fn(im, data)
    good = f is None and d0 == want
    ok &= good
    print(f"{'PASS' if good else 'FAIL'} {name}: d0 {d0}{'' if f is None else f' fault {f}'}")
print('ALL PASS' if ok else 'FAILURES')
sys.exit(0 if ok else 1)
