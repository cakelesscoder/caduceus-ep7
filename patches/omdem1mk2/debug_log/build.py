#!/usr/bin/env python3
"""Build declarative edits.json for E-M1 Mark II Diagnostic Debug Logger.

Non-invasive: does not touch existing patches.
Caves in Section 4 free tail (0x6078e900..0x6078f000).
Hooks shutter TRIG event junction at 0x6023d10a.
"""
import json
import struct
import subprocess
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
TC = Path('/home/hertzel/ep7fw-toolchains/mn10300/bin')
AS = TC / 'mn10300-elf-as'
LD = TC / 'mn10300-elf-ld'
OBJCOPY = TC / 'mn10300-elf-objcopy'

CAVE_ADDR = 0x6078e8c0
S4_LOAD_END = 0x6078f000
HOOK_ADDR = 0x6023d10a
HOOK_STOCK_HEX = 'fcac2e0d046018'  # movhu (0x60040d2e),d0; exth d0 (7 bytes)

SYMBOLS = {
    'em1_malloc': 0x600231fe,
    'em1_free': 0x6002323d,
    'em1_fopen': 0x6062ce6a,
    'em1_fclose': 0x6062ce73,
    'em1_fwrite': 0x6062ceef,
    'em1_fread': 0x6062cff9,
    'em1_trig_ret': 0x6023d111,
}


def main():
    version = sys.argv[1] if len(sys.argv) > 1 else 'v0.3b5'
    here = Path(__file__).parent

    # Write version include
    (here / 'lgver.inc').write_text(f'lg_ver:\n    .asciz "{version}"\n')

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        obj = tmp / 'debug_log.o'
        elf = tmp / 'debug_log.elf'
        bin_out = tmp / 'debug_log.bin'

        # Assemble
        src = here / 'debug_log.s'
        inc_dir = here.parent
        subprocess.run([AS, '-I', str(inc_dir), '-I', str(here), '-o', str(obj), str(src)], check=True)

        # Link
        ld_cmd = [LD, '-Ttext', f'{CAVE_ADDR:#x}', '-e', '_start']
        for k, v in SYMBOLS.items():
            ld_cmd.append(f'--defsym={k}={v:#x}')
        ld_cmd.extend(['-o', str(elf), str(obj)])
        subprocess.run(ld_cmd, check=True)

        # Extract binary
        subprocess.run([OBJCOPY, '-O', 'binary', str(elf), str(bin_out)], check=True)
        code = bin_out.read_bytes()

        cave_end = CAVE_ADDR + len(code)
        assert cave_end <= S4_LOAD_END, f"debug_log cave overflow: {cave_end:#x} > {S4_LOAD_END:#x}"

        # Hook instruction: jmp CAVE_ADDR (dc d32) + nop nop (cb cb) = 7 bytes
        # AM33 jmp (d32,PC): the displacement is relative to the jmp's own address (as `dc 1f e8 aa ff` at the cave's
        # exit shows). v0.4/v0.4b1 used HOOK_ADDR + 1 and jumped to 0x6078e8bf, an 0xFF `break` byte: restart at the shutter.
        disp = CAVE_ADDR - HOOK_ADDR
        hook_bytes = b'\xdc' + struct.pack('<i', disp) + b'\xcb\xcb'
        assert len(hook_bytes) == 7, f"Hook must be 7 bytes, got {len(hook_bytes)}"
        assert HOOK_ADDR + struct.unpack('<i', hook_bytes[1:5])[0] == CAVE_ADDR

        edits = [
            {
                "kind": "0x100",
                "addr": f"{HOOK_ADDR:#x}",
                "expect": HOOK_STOCK_HEX,
                "new": hook_bytes.hex(),
                "why": "Hook shutter TRIG junction to diagnostic debug logger"
            },
            {
                "kind": "0x100",
                "addr": f"{CAVE_ADDR:#x}",
                "expect": "ff" * len(code),
                "new": code.hex(),
                "why": f"Diagnostic debug logger cave routine ({len(code)} bytes in Section 4)"
            }
        ]

        out_json = here / 'edits.json'
        out_json.write_text(json.dumps({"patch": "debug_log", "components": ["0x100"], "edits": edits}, indent=2) + '\n')
        print(f"Generated {out_json} ({len(code)} bytes cave routine, {len(hook_bytes)} bytes hook)")


if __name__ == '__main__':
    main()
