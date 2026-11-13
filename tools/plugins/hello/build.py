#!/usr/bin/env python3
"""Build the "hello" plugin -> PLUGIN.BIN (Caduceus plugin ABI v1, E-P7 1.1). Offline. docs/PLUGINS.md.

  .venv/bin/python -I tools/plugins/hello/build.py --out generated/v032/plugin_card/EP7MOD/PLUGIN.BIN [--suffix P]

The camera then shows "Caduceus: 0.32P" on Setup > Firmware after the first half-press. The Firmware value box is
narrow ("v0.16" clipped slightly, "0.31d" fitted), so the default suffix is one character.

Also importable: make(code) wraps any ABI-v1 plugin image (linked at 0, header space at 0..31, init at 32) in a header.
"""
import argparse, struct, subprocess, tempfile, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
TC = Path.home() / 'ep7fw-toolchains/mn10300/bin'
MAGIC = b'EP7P'
ABI, FLAGS = 1, 0
FW_ID = bytes.fromhex('5dd9af16')           # stock E-P7 1.1 main (decoded) SHA-256 bytes 0..3, as in BUNDLES.BIN
HDR, MAX = 32, 16384
MAXC = 10                                   # wide chars copied from the resident version string


def assemble(src, defs=None):
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        (t / 'p.s').write_text(''.join(f' .set {k}, {v}\n' for k, v in (defs or {}).items()) + src)
        subprocess.run([TC / 'mn10300-elf-as', '-o', t / 'p.o', t / 'p.s'], check=True)
        subprocess.run([TC / 'mn10300-elf-ld', '-Ttext', '0', '-e', '_start', '-o', t / 'p.elf', t / 'p.o'], check=True)
        subprocess.run([TC / 'mn10300-elf-objcopy', '-O', 'binary', '-j', '.text', t / 'p.elf', t / 'p.bin'], check=True)
        dis = subprocess.run([TC / 'mn10300-elf-objdump', '-d', t / 'p.elf'], check=True, capture_output=True, text=True).stdout
        return (t / 'p.bin').read_bytes(), dis


def make(code, abi=ABI, flags=FLAGS, fw_id=FW_ID):
    """code: the linked image (its first 32 bytes are header space). -> PLUGIN.BIN bytes."""
    if len(code) < HDR + 2 or len(code) > MAX:
        raise ValueError(f'plugin size {len(code)} outside {HDR + 2}..{MAX}')
    if any(code[:HDR]):
        raise ValueError('header space must be zero')
    b = bytearray(code)
    b[0:4] = MAGIC
    struct.pack_into('<HH', b, 8, abi, flags)
    b[12:16] = fw_id
    struct.pack_into('<I', b, 16, len(b))
    struct.pack_into('<I', b, 4, zlib.crc32(bytes(b[8:])) & 0xffffffff)
    return bytes(b)


def check(code, dis):
    """Plugin rules the loader can't enforce: no fb-prefixed forms, no mul/div/setlb, no absolute address operands."""
    import re
    bad = []
    for line in dis.splitlines():
        m = re.match(r'\s*([0-9a-f]+):\s+((?:[0-9a-f]{2} )+)\s*(\S+)\s*(.*)', line)
        if not m:
            continue
        a, by, op, args = int(m.group(1), 16), m.group(2).split(), m.group(3), m.group(4)
        if a < HDR:
            continue
        if by[0] == 'fb' or op in ('mul', 'mulu', 'div', 'divu', 'setlb', 'trap') or re.search(r'\(0x[0-9a-f]{5,}\)', args):
            bad.append(line.strip())
    if bad:
        raise SystemExit('plugin rule violations:\n' + '\n'.join(bad))


def build(suffix='P'):
    if len(suffix) != 1 or not 0x20 < ord(suffix) < 0x7f:
        raise SystemExit('suffix: one printable ASCII character')
    code, dis = assemble((HERE / 'hello.s').read_text(), dict(MAXC=MAXC, SUFFIX=ord(suffix)))
    check(code, dis)
    return make(code), dis


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--suffix', default='P')
    a = ap.parse_args()
    data, _ = build(a.suffix)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(data)
    print(f'{a.out}: {len(data)} B, crc {struct.unpack_from("<I", data, 4)[0]:#010x}')
