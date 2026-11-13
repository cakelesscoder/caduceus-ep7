#!/usr/bin/env python3
"""Run the E-M1 Mark II's own setting-validator code in the MN103 emulator (external/oly_fw_analysis).

    python3 tools/omdem1mk2_emu_validator.py releases/em1mk2/v0.4b5/edits.json [--sid 270 --sid 511 --sid 512]

Builds the patched main image (stock + spec edits), runs the firmware's validator hash init 0x602e6ba4 into mapped RAM,
then for each sid calls the real count 0x602e6588 and value-by-index 0x602e65f3 functions and prints what they return.
Only section 1/2 code, the hash RAM and a stack are mapped: any other access stops the run and is reported.
Read-only; needs the built engine (external/oly_fw_analysis/toolchains/mn103-gnu-build/penf-mn103).
"""
import argparse, json, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'external/oly_fw_analysis/tools'))
from penf_emulator import Region, execute  # noqa: E402

B = 0x60021020
STOCK = ROOT / 'em1mk2/extracted/00_0100_40560020.decoded.bin'
SEC1 = (0x600de000, 0x60257800)
SEC2 = (0x602ae000, 0x60580800)
HASH_RAM = (0x62254000, 0x62257000)       # buckets 0x622540f4 (128 x 4) + nodes 0x622542f4 (1215 x 8)
STACK, SP = 0x18010000, 0x18010f00
CALLER = 0x18020000
HASH_INIT, COUNT, VALUE = 0x602e6ba4, 0x602e6588, 0x602e65f3


def image(spec):
    d = bytearray(STOCK.read_bytes())
    if spec:
        for e in json.load(open(spec))['edits']:
            if e.get('kind', '0x100') == '0x100':
                a = int(e['addr'], 16) - B
                n = bytes.fromhex(e['new'])
                d[a:a + len(n)] = n
    return bytes(d)


def call(img, ram, target, mask, frame, regs):
    code = b'\xdd' + struct.pack('<i', target - CALLER) + bytes([mask, frame]) + b'\xcb'
    regions = [Region('caller', CALLER, code, 'rx'),
               Region('sec1', SEC1[0], img[SEC1[0] - B:SEC1[1] - B], 'rx'),
               Region('sec2', SEC2[0], img[SEC2[0] - B:SEC2[1] - B], 'rx'),
               Region('hash', HASH_RAM[0], ram, 'rw', capture=True),
               Region('stack', STACK, bytes(0x1000), 'rw')]
    r = execute(regions, dict({'sp': SP, 'pc': CALLER}, **regs), CALLER + 7, limit=2_000_000)
    if r['fault'] or r['registers']['pc'] != CALLER + 7:
        raise SystemExit(f'emulation stopped at {r["registers"]["pc"]:#x}: {r["fault"]}')
    new_ram = next(c for c in r['memory'] if c['name'] == 'hash')
    return r['registers'], bytes.fromhex(new_ram['hex'])


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('spec', nargs='?')
    p.add_argument('--sid', type=int, action='append')
    a = p.parse_args()
    img = image(a.spec)
    _, ram = call(img, bytes(HASH_RAM[1] - HASH_RAM[0]), HASH_INIT, 0xb0, 12, {})
    for sid in a.sid or [270, 511, 512]:
        regs, _ = call(img, ram, COUNT, 0x80, 8, {'d0': sid})
        n = regs['d0'] & 0xffff
        vals = []
        for i in range(n):
            r, _ = call(img, ram, VALUE, 0x80, 8, {'d0': sid, 'd1': i})
            vals.append(r['d0'] & 0xffff)
        print(f'sid {sid}: count {n} values {vals}')


if __name__ == '__main__':
    main()
