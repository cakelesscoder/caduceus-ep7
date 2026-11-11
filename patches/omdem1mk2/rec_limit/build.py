#!/usr/bin/env python3
"""E-M1 Mark II Video recording limit patch (extends 29-minute and 2-hour limits to 9 hours).

Sites:
  0x603549d7: 1740s (0x06cc) -> 32400s (0x7e90)
  0x603549dc: 7200s (0x1c20) -> 32400s (0x7e90)
"""
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import container as oc

MAIN_BASE = 0x60021020
SITES = [
    (0x603549d7, 1740, 32400),
    (0x603549dc, 7200, 32400),
]


def main():
    stock_bytes = (ROOT / 'E1259999.BIN').read_bytes()
    blocks = oc.parse(stock_bytes)
    main_pay = blocks[0].payload

    edits = []
    for addr, old_val, new_val in SITES:
        off = addr - MAIN_BASE
        old_hex = struct.pack('<H', old_val).hex()
        new_hex = struct.pack('<H', new_val).hex()
        actual = main_pay[off:off + 2].hex()
        assert actual == old_hex, f"Expected {old_hex} at {hex(addr)}, got {actual}"
        edits.append({
            "kind": "0x100",
            "addr": hex(addr),
            "expect": old_hex,
            "new": new_hex,
            "why": f"Video record limit {old_val}s -> {new_val}s"
        })

    out_file = Path(__file__).parent / 'edits.json'
    spec = {
        "patch": "rec_limit",
        "components": ["0x100"],
        "edits": edits
    }
    out_file.write_text(json.dumps(spec, indent=1) + '\n')
    print(f"Generated {out_file} with {len(edits)} edit(s).")


if __name__ == '__main__':
    main()

