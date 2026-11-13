#!/usr/bin/env python3
"""Emulate the E-M1 Mark II's per-value availability check (interlock rules) for a setting, on a release spec.

    python3 tools/omdem1mk2_emu_rules.py releases/em1mk2/v0.4c1/edits.json [--sid 270] [--values 1-10]
    python3 tools/omdem1mk2_emu_rules.py -            # stock

Why: the menu / SCP / Live Control option builders (e.g. 0x60e4a59c) call facade slot +36 (0x60836357 ->
0x6086333c) for every value the validator offers, and hide the ones it rejects. 0x6086333c ends in the interlock rule
engine (0x602da752 -> 0x602de6a7 -> 0x602de667), whose rules live in a RAM hash built at boot by 0x602de9c9 from the
ROM rule table 0x604a8408 (324 x 20 B). This tool runs the firmware's own validator hash init (0x602e6ba4) and rule
init, then the rule check and the facade worker for each value.

Fixtures (emulator only, never part of a build), each the minimum the code touched:
  .bss 0x621c0000..0x62800000 zeroed (+ uncached alias 0xa2..), .data from its initial image (flash 0x60258000 ->
  RAM 0x61f7d540), CPU id 0x8050 = 0, the E-P7 verifiers' task-table fixture at 0x8ff00000, boot-ROM memcpy/memset
  stand-ins at 0x4700106b / 0x47001177, and the semaphore signal 0x6005e6cf (cross-core IPC) stubbed to return.
Limits: every other setting reads 0 (all zero RAM), so rules that depend on the camera's current state are evaluated
for that state only. Needs the built engine (external/oly_fw_analysis, see WORKLOG 2026-11-11).
"""
import argparse, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'external/oly_fw_analysis/tools'))
import omdem1mk2_emu_validator as V  # noqa: E402
from penf_emulator import Region, execute  # noqa: E402

SECS = [(0x60021020, 0x600de000), (0x600de000, 0x60257800), (0x602ae000, 0x60580800), (0x60591800, 0x605d3000),
        (0x605d5000, 0x6078f000), (0x60796000, 0x60bc8800), (0x60bf1000, 0x612e7000)]
RAM = (0x621c0000, 0x62800000)
KERN = 0x1c400000
STUBS = {0x6005e6cf: bytes.fromhex('00dfc00c')}            # semaphore signal: clr d0; ret [d2,d3],12
ROM_MEMCPY = (0x4700106b, '92a000c80cf045f056454928ffcaf4dff01c')   # a0 dst, a1 src, d0 n; ret [d2,d3,a2,a3],28
ROM_MEMSET = (0x47001177, 'a500c809f0504129ffcaf7dfa008')           # a0 dst, d0 byte, d1 n; ret [d2,a2],8


def kern(tid=5):
    """E-P7 verifier fixture (ep7_verify_sd_bundles_v2.kern): an ordinary task, tid 5."""
    k = bytearray(0x100)
    struct.pack_into('<I', k, 28, KERN + 0x40)
    struct.pack_into('<I', k, 96, KERN + 0x80)
    struct.pack_into('<I', k, 0x80, KERN + 0xa0)
    struct.pack_into('<H', k, 0xa0 + 16, tid)
    return bytes(k)


class Emu:
    def __init__(self, spec):
        img = bytearray(V.image(spec))
        for a, b in STUBS.items():
            img[a - V.B:a - V.B + len(b)] = b
        self.img = bytes(img)
        self.ram = bytes(RAM[1] - RAM[0])
        self.call(0x602e6ba4, 0xb0, 12, {})     # validator hash init
        self.call(0x602de9c9, 0xb0, 12, {})     # interlock rule hash init

    def call(self, target, mask, frame, regs):
        img = self.img
        code = b'\xdd' + struct.pack('<i', target - V.CALLER) + bytes([mask, frame]) + b'\xcb'
        regions = [Region('caller', V.CALLER, code, 'rx'), Region('stack', V.STACK, bytes(0x1000), 'rw')]
        regions += [Region(f's{i}', lo, img[lo - V.B:hi - V.B], 'rx') for i, (lo, hi) in enumerate(SECS)]
        regions += [Region('ram', RAM[0], self.ram, 'rw', capture=True),
                    Region('ram_unc', RAM[0] + 0x40000000, self.ram, 'rw', alias_of='ram'),
                    Region('rom_memcpy', ROM_MEMCPY[0], bytes.fromhex(ROM_MEMCPY[1]), 'rx'),
                    Region('rom_memset', ROM_MEMSET[0], bytes.fromhex(ROM_MEMSET[1]), 'rx'),
                    Region('tcbtab', 0x8ff00000, bytes(4) + struct.pack('<I', KERN) + bytes(8), 'r'),
                    Region('kern', KERN, kern(), 'r'),
                    Region('cpuid', 0x8050, bytes(4), 'r'),
                    Region('data', 0x61f7d540, img[0x60258000 - V.B:0x602ae000 - V.B], 'rw')]
        r = execute(regions, dict({'sp': V.SP, 'pc': V.CALLER}, **regs), V.CALLER + 7, limit=5_000_000)
        if r['fault'] or r['registers']['pc'] != V.CALLER + 7:
            raise SystemExit(f'emulation stopped at {r["registers"]["pc"]:#x}: {r["fault"]}')
        self.ram = bytes.fromhex(r['memory'][0]['hex'])
        return r['registers']


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('spec', help="release edits.json, or '-' for stock")
    p.add_argument('--sid', type=int, default=270)
    p.add_argument('--values', default='1-10')
    a = p.parse_args()
    lo, hi = (int(x) for x in a.values.split('-'))
    emu = Emu(None if a.spec == '-' else a.spec)
    rule = [(v, emu.call(0x602da752, 0x80, 8, {'d0': a.sid, 'd1': 0, 'a0': v})['d0']) for v in range(lo, hi + 1)]
    shown = [(v, emu.call(0x6086333c, 0xe0, 16, {'d0': a.sid, 'd1': v, 'a0': 0})['d0']) for v in range(lo, hi + 1)]
    print(f'sid {a.sid} interlock rule 0x602da752 (0 = allowed): {rule}')
    print(f'sid {a.sid} facade +36 worker 0x6086333c (1 = offered): {shown}')
    print('offered values:', [v for v, s in shown if s == 1])


if __name__ == '__main__':
    main()
