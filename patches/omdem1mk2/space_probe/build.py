#!/usr/bin/env python3
"""E-M1 Mark II code-space probe sp1 (docs/OMD-EM1-II/HALATION.md step 1).

    python3 patches/omdem1mk2/space_probe/build.py          -> edits.json, exports.json

Raises section 5's loaded-end word (loader end getter 0x60042b35, stub `mov 0x612e7000,d0` at 0x60042b6b) to 0x61300000,
the start of section 6: flash source 0x41130000 + (0x61300000 - 0x60bf1000) = 0x4183f000 = section 6's own source, so the
loader copies the 100 KB gap 0x612e7000..0x61300000 straight from the package. Only the end word references the gap (code
imm32 / absolute operand scan, 2026-11-13). The region gets a magic word and an LCG pattern; probe.s (section-3 FF tail)
sums it on every look-editor banner draw: " S+" loaded and intact, " S!" loaded but changed, " S0" not loaded.
The editor calls it only when built with EM1_SPACE_PROBE=1 (color_creator_wheel build).
"""
import json, struct, subprocess, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TC = Path('/home/hertzel/ep7fw-toolchains/mn10300/bin')
BIN = ROOT / 'em1mk2/extracted/00_0100_40560020.decoded.bin'
B = 0x60021020
END_IMM, OLD_END, NEW_END = 0x60042b6d, 0x612e7000, 0x61300000
REGION, REGION_END = OLD_END, NEW_END
MAGIC = 0x42525053                       # 'SPRB'
STUB_AT, STUB_LIMIT = 0x605d2f98, 0x605d3000 - 8


def pattern():
    words, x = [MAGIC], 0x2545f491
    for _ in range((REGION_END - REGION) // 4 - 1):
        x = (x * 1103515245 + 12345) & 0xffffffff
        words.append(x)
    blob = struct.pack(f'<{len(words)}I', *words)
    return blob, sum(words) & 0xffffffff


def assemble(expect):
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        subprocess.run([str(TC / 'mn10300-elf-as'), str(HERE / 'probe.s'), '-o', str(t / 'p.o')], check=True)
        syms = dict(REGION=REGION, REGION_END=REGION_END, MAGIC=MAGIC, EXPECT=expect)
        subprocess.run([str(TC / 'mn10300-elf-ld'), f'--section-start=.text={STUB_AT:#x}', '-e', '_start', str(t / 'p.o'),
                        '-o', str(t / 'p.elf')] + [f'--defsym={k}={v:#x}' for k, v in syms.items()], check=True)
        subprocess.run([str(TC / 'mn10300-elf-objcopy'), '-O', 'binary', str(t / 'p.elf'), str(t / 'p.bin')], check=True)
        return (t / 'p.bin').read_bytes()


def build():
    d = BIN.read_bytes()
    assert d[END_IMM - 2 - B:END_IMM + 4 - B] == b'\xfc\xcc' + struct.pack('<I', OLD_END), 'end-word stub changed'
    assert d[REGION - B:REGION_END - B] == b'\xff' * (REGION_END - REGION), 'gap not 0xFF in the image'
    blob, expect = pattern()
    code = assemble(expect)
    assert STUB_AT + len(code) <= STUB_LIMIT, len(code)
    assert d[STUB_AT - B:STUB_AT + len(code) - B] == b'\xff' * len(code)
    e = lambda a, old, new, why: dict(kind='0x100', addr=f'{a:#x}', expect=old.hex(), new=new.hex(), why=why)
    edits = [
        e(END_IMM, d[END_IMM - B:END_IMM + 4 - B], struct.pack('<I', NEW_END),
          'space probe: section 5 loaded end 0x612e7000 -> 0x61300000 (loader copies the 100 KB gap)'),
        e(REGION, d[REGION - B:REGION_END - B], blob, f'space probe: region pattern (magic + LCG, sum {expect:#010x})'),
        e(STUB_AT, d[STUB_AT - B:STUB_AT + len(code) - B], code, f'space probe check (banner " S+/S!/S0", {len(code)} B)'),
    ]
    (HERE / 'edits.json').write_text(json.dumps({'patch': 'space_probe', 'edits': edits}, indent=1) + '\n')
    (HERE / 'exports.json').write_text(json.dumps({'SPROBE': STUB_AT, 'EXPECT': expect, 'MAGIC': MAGIC,
                                                   'REGION': REGION, 'REGION_END': REGION_END}) + '\n')
    print(f'space probe: stub {len(code)} B at {STUB_AT:#x}, region sum {expect:#010x}')


if __name__ == '__main__':
    build()
