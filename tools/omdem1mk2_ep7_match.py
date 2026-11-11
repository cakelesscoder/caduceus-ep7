#!/usr/bin/env python3
"""Find the E-M1 Mark II equivalent of an E-P7 1.1 code address by masked signature.

Disassembles a window of the E-P7 main around ADDR, wildcards PC-relative call/jump/branch
displacements and absolute 0x6xxxxxxx / 0xaxxxxxxx constants, and searches the E-M1 II main
for the rest. Read-only.

  em1mk2/scripts/ep7_match.py 0x603b02d9 [--before 40] [--after 40]
"""
import argparse, re, subprocess, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OBJ = Path.home() / 'ep7fw-toolchains/mn10300/bin/mn10300-elf-objdump'
EP7 = ROOT / 'analysis/ep7_1100/00_0100_406a0020.decoded.bin'
EM1 = ROOT / 'em1mk2/extracted/00_0100_40560020.decoded.bin'
EP7_BASE, EM1_BASE = 0x60020020, 0x60021020


def insns(start, stop):
    out = subprocess.check_output([str(OBJ), '-b', 'binary', '-m', 'am33-2', '-D',
                                   f'--adjust-vma={EP7_BASE:#x}', f'--start-address={start:#x}',
                                   f'--stop-address={stop:#x}', str(EP7)]).decode()
    res = []
    for line in out.splitlines():
        m2 = re.match(r'\s*([0-9a-f]{8}):\t((?:[0-9a-f]{2} ?)+)\s*$', line)
        if m2 and res:  # continuation line of a long instruction (no mnemonic)
            res[-1][1] += bytes.fromhex(m2.group(2).replace(' ', ''))
            continue
        m = re.match(r'\s*([0-9a-f]{8}):\t((?:[0-9a-f]{2} )+)\s*\t(.*)', line)
        if m:
            res.append([int(m.group(1), 16), bytes.fromhex(m.group(2).replace(' ', '')), m.group(3)])
    return res


def mask(b, text):
    m = [True] * len(b)
    op = b[0]
    if op in (0xdd, 0xdc) and len(b) >= 5:          # call/jmp d32
        for i in range(1, 5): m[i] = False
    elif op in (0xcd, 0xcc) and len(b) >= 3:        # call/jmp d16
        for i in range(1, 3): m[i] = False
    elif 0xc0 <= op <= 0xcb and len(b) == 2:        # bcc d8
        m[1] = False
    # any 4-byte little-endian constant in code/RAM ranges
    for i in range(len(b) - 3):
        v = struct.unpack_from('<I', b, i)[0]
        if (0x60000000 <= v < 0x63000000) or (0xa0000000 <= v < 0xa3000000):
            for k in range(i, i + 4): m[k] = False
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('addr', type=lambda x: int(x, 16))
    ap.add_argument('--before', type=int, default=40)
    ap.add_argument('--after', type=int, default=40)
    a = ap.parse_args()
    ins = insns(a.addr - a.before - 8, a.addr + a.after + 8)
    # trim to instruction boundaries inside the window
    ins = [i for i in ins if a.addr - a.before <= i[0] <= a.addr + a.after]
    pat = b''; off_site = None; nbytes = 0
    for addr, b, t in ins:
        if addr == a.addr: off_site = nbytes
        nbytes += len(b)
        mk = mask(b, t)
        for byte, keep in zip(b, mk):
            pat += re.escape(bytes([byte])) if keep else b'.'
    assert off_site is not None, 'ADDR is not an instruction start in the E-P7 disassembly'
    em1 = EM1.read_bytes()
    hits = [m.start() for m in re.finditer(pat, em1, re.S)]
    print(f'E-P7 {a.addr:#x}: {len(ins)} insns, {len(hits)} hit(s)')
    for h in hits[:8]:
        print(f'  E-M1 II {h + off_site + EM1_BASE:#x}')


if __name__ == '__main__':
    main()
