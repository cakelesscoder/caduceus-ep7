#!/usr/bin/env python3
"""E-M1 Mark II Focus Stacking with non-PRO Olympus & third-party lenses.

Patches 0x60656a4a: `bne` (c9 04) -> `nop nop` (cb cb).
Allows focus stacking on all lenses.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import container as oc

MAIN_BASE = 0x60021020
ADDR = 0x60656a4a
OLD_HEX = "c904"
NEW_HEX = "cbcb"


def main():
    stock_bytes = (ROOT / 'E1259999.BIN').read_bytes()
    blocks = oc.parse(stock_bytes)
    main_pay = blocks[0].payload
    off = ADDR - MAIN_BASE
    actual = main_pay[off:off + len(bytes.fromhex(OLD_HEX))].hex()
    assert actual == OLD_HEX, f"Expected {OLD_HEX} at {hex(ADDR)}, got {actual}"

    edits = [
        {
            "kind": "0x100",
            "addr": hex(ADDR),
            "expect": OLD_HEX,
            "new": NEW_HEX,
            "why": "Focus stacking on all lenses (bne -> nop nop)"
        }
    ]

    out_file = Path(__file__).parent / 'edits.json'
    spec = {
        "patch": "focus_stacking",
        "components": ["0x100"],
        "edits": edits
    }
    out_file.write_text(json.dumps(spec, indent=1) + '\n')
    print(f"Generated {out_file} with {len(edits)} edit(s).")


if __name__ == '__main__':
    main()

