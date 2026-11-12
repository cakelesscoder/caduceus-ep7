#!/usr/bin/env python3
"""Build declarative edits.json for Live View Color Creator Look Selector & Multi-Page Controller.

Implements pure Caduceus architecture (`docs/LOOK_EDITOR.md` & `docs/FIRMWARE_GUIDE.md`)
for Olympus OM-D E-M1 Mark II (firmware v3.70):
1. Places cave in Section 6's loaded 0xFF tail (`0x612e6900`, within `0x612e68c4..0x612e7000`).
2. Replaces 9 function pointers in the Live View Color Creator 56-byte controller record
   at `0x61259c40` (key `0x13a9` = 5033):
   - `0x61259c44` (+04 Create): `0x60e8b9bd` -> `cc_init`
   - `0x61259c4c` (+12 Up):     `0x60e8bda4` -> `cc_up`
   - `0x61259c50` (+16 Down):   `0x60e8bedf` -> `cc_down`
   - `0x61259c54` (+20 Left):   `0x60e8c0f5` -> `cc_left`
   - `0x61259c58` (+24 Right):  `0x60e8c46a` -> `cc_right`
   - `0x61259c5c` (+28 Dial1):  `0x60e8c786` -> `cc_dial1`
   - `0x61259c60` (+32 Dial2):  `0x60e8c9d3` -> `cc_dial2`
   - `0x61259c64` (+36 Event):  `0x60e8cc69` -> `cc_page`
   - `0x61259c6c` (+44 INFO):   `0x60e8d038` -> `cc_info`
3. Replaces Part 3 (Guide Label writer) in the Color Creator View part table ROM image
   at `0x60297fb4` (copied at boot to `.data` `0x61fbd4f4`):
   - `0x60297fb4`: `0x60e543d6` -> `cc_guide`
"""
import json
import struct
import subprocess
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))

TC = Path('/home/hertzel/ep7fw-toolchains/mn10300/bin')
AS = TC / 'mn10300-elf-as'
LD = TC / 'mn10300-elf-ld'
OBJCOPY = TC / 'mn10300-elf-objcopy'
NM = TC / 'mn10300-elf-nm'

STOCK_BIN = ROOT / 'em1mk2' / 'firmware' / 'E1259999.BIN'
DECODED_BIN = ROOT / 'em1mk2' / 'extracted' / '00_0100_40560020.decoded.bin'
BASE = 0x60021020

# Section 6 loaded 0xFF tail: 0x612e68c4 .. 0x61300000 (104,252 bytes)
SECTION6_FF_START = 0x612e68c4
# Real section bounds from the firmware's own loader: descriptor table 0x60027450 ({start, source, dest}),
# end getter 0x60042b35 (mov imm32,d0 stubs). Section 6 = 0x60bf1000..0x612e7000. Bytes past the end are
# NEVER loaded: v0.1-v0.3b1 placed preset tables there (garbage names / wrong looks on camera).
SECTION6_LOAD_END = 0x612e7000
# Built-in looks (16 x 64 B) in the Section 5 FF tail 0x60bc8140..0x60bc8800 (S5 loads before S6). Static
# reference scan (cached, uncached, flash-source aliases): only two call-displacement false positives.
S5_FF_START, S5_LOAD_END = 0x60bc8140, 0x60bc8800
BUILTIN_ADDR = 0x60bc8150
CAVE_ADDR = 0x612e6900

POINTER_HOOKS = [
    {
        'name': 'cc_init',
        'addr': 0x61259c44,
        'stock_target': 0x60e8b9bd,
        'sym': 'cc_init',
        'why': 'Color Creator record+04 (Create): initialize children, page=0, load/apply active look'
    },
    {
        'name': 'cc_up',
        'addr': 0x61259c4c,
        'stock_target': 0x60e8bda4,
        'sym': 'cc_up',
        'why': 'Color Creator record+12 (Up / Dial1+): step look (P0 arrow), wheel vivid (P0 dial), shadows (P2)'
    },
    {
        'name': 'cc_down',
        'addr': 0x61259c50,
        'stock_target': 0x60e8bedf,
        'sym': 'cc_down',
        'why': 'Color Creator record+16 (Down / Dial1-): step look (P0 arrow), wheel vivid (P0 dial), shadows (P2)'
    },
    {
        'name': 'cc_left',
        'addr': 0x61259c54,
        'stock_target': 0x60e8c0f5,
        'sym': 'cc_left',
        'why': 'Color Creator record+20 (Left / Dial2+): step look (P0 arrow), wheel hue (P0 dial), chroma (P1), highlights (P2), midtones (P3)'
    },
    {
        'name': 'cc_right',
        'addr': 0x61259c58,
        'stock_target': 0x60e8c46a,
        'sym': 'cc_right',
        'why': 'Color Creator record+24 (Right / Dial2-): step look (P0 arrow), wheel hue (P0 dial), chroma (P1), highlights (P2), midtones (P3)'
    },
    {
        'name': 'cc_dial1',
        'addr': 0x61259c5c,
        'stock_target': 0x60e8c786,
        'sym': 'cc_dial1',
        'why': 'Color Creator record+28 (Rear Dial): set dial_active flag so Page 0 dials adjust Color Wheel'
    },
    {
        'name': 'cc_dial2',
        'addr': 0x61259c60,
        'stock_target': 0x60e8c9d3,
        'sym': 'cc_dial2',
        'why': 'Color Creator record+32 (Front Dial): set dial_active flag so Page 0 dials adjust Color Wheel'
    },
    {
        'name': 'cc_page',
        'addr': 0x61259c64,
        'stock_target': 0x60e8cc69,
        'sym': 'cc_page',
        'why': 'Color Creator record+36 (Other Event): cycle pages on TRASH (0x9016)'
    },
    {
        'name': 'cc_info',
        'addr': 0x61259c6c,
        'stock_target': 0x60e8d038,
        'sym': 'cc_info',
        'why': 'Color Creator record+44 (INFO 0x9014): cycle pages 0..3 instead of closing editor'
    },
    {
        'name': 'cc_guide',
        'addr': 0x60297fb4,
        'stock_target': 0x60e543d6,
        'sym': 'cc_guide',
        'why': 'Color Creator View Part 3 (Guide Label): display look name / live page values in bottom banner'
    },
]

SYMBOLS = {
    'em1_cc_init': 0x60e8b9bd,
    'em1_cc_up': 0x60e8bda4,
    'em1_cc_down': 0x60e8bedf,
    'em1_cc_left': 0x60e8c0f5,
    'em1_cc_right': 0x60e8c46a,
    'em1_cc_dial1': 0x60e8c786,
    'em1_cc_dial2': 0x60e8c9d3,
    'em1_cc_page': 0x60e8cc69,
    'em1_cc_info': 0x60e8d038,
    'em1_cc_guide': 0x60e543d6,
    'em1_child_sync': 0x60e4a59c,
    'em1_get_facade': 0x608362c5,
    'em1_scp_stock_format': 0x60ee8cd1,
    'em1_scp_text': 0x60db275e,
    'em1_getter': 0x6005e6cf,       # property getter (d0 key, d1 index, a0 0), [d2,d3],12
}


def get_main_payload() -> bytes:
    if DECODED_BIN.exists():
        return DECODED_BIN.read_bytes()
    try:
        import oly_container as oc
    except ImportError:
        sys.path.insert(0, str(ROOT))
        import caduceus as oc
    blocks = oc.parse(STOCK_BIN.read_bytes())
    b100 = [b for b in blocks if b.kind == 0x100][0]
    return b100.payload


def build():
    src = Path(__file__).parent / 'color_creator_wheel.s'
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        obj = tmp / 'wheel.o'
        elf = tmp / 'wheel.elf'
        bin_out = tmp / 'wheel.bin'

        # Built-in looks: the same 64-byte records as the card file (sd_loader/make_looks_bin.py)
        import importlib.util
        spec = importlib.util.spec_from_file_location('mlb', Path(__file__).parent.parent / 'sd_loader' / 'make_looks_bin.py')
        mlb = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mlb)
        builtin = mlb.build_builtin_looks()
        assert len(builtin) == 1024
        subprocess.run([AS, '-I', str(Path(__file__).parent.parent), '-I', str(Path(__file__).parent),
                        '-o', str(obj), str(src)], check=True)

        ld_cmd = [LD, '-Ttext', f'{CAVE_ADDR:#x}', '-e', '_start']
        # Shared-state routines live in sd_loader (Section 2); build it first.
        exports = json.loads((Path(__file__).parent.parent / 'sd_loader' / 'exports.json').read_text())
        for k in ('p_get', 'p_ensure', 'look_fill'):
            ld_cmd.append(f'--defsym={k}={exports[k]}')
        ld_cmd.append(f'--defsym=builtin_looks={BUILTIN_ADDR:#x}')
        for k, v in SYMBOLS.items():
            ld_cmd.append(f'--defsym={k}={v:#x}')
        ld_cmd.extend(['-o', str(elf), str(obj)])
        subprocess.run(ld_cmd, check=True)

        subprocess.run([OBJCOPY, '-O', 'binary', '-j', '.text', str(elf), str(bin_out)], check=True)
        cave_payload = bin_out.read_bytes()

        nm_out = subprocess.check_output([NM, str(elf)]).decode()
        sym_map = {}
        for line in nm_out.splitlines():
            parts = line.split()
            if len(parts) >= 3:
                sym_map[parts[2]] = int(parts[0], 16)

    # Verify cave bounds inside Section 6's loaded 0xFF tail with >=16B guards
    assert CAVE_ADDR >= SECTION6_FF_START + 16, "Cave starts too close to Section 6 code end!"
    cave_end = CAVE_ADDR + len(cave_payload)
    assert cave_end <= SECTION6_LOAD_END - 16, (
        f"Cave end {cave_end:#x} exceeds Section 6 loaded end {SECTION6_LOAD_END:#x} - 16!"
    )

    main = get_main_payload()

    # Verify cave region (plus 16-byte guards) is all 0xFF in stock
    guard_start = CAVE_ADDR - 16 - BASE
    guard_end = cave_end + 16 - BASE
    assert all(b == 0xFF for b in main[guard_start:guard_end]), "Target cave or 16B guard contains non-0xFF bytes!"

    edits_list = []

    # Emit pointer table edits
    for h in POINTER_HOOKS:
        hook_off = h['addr'] - BASE
        actual_stock = main[hook_off:hook_off + 4]
        expected_stock = struct.pack('<I', h['stock_target'])
        assert actual_stock == expected_stock, (
            f"Pointer mismatch at {h['addr']:#x}: expected {expected_stock.hex()}, got {actual_stock.hex()}"
        )
        new_ptr = struct.pack('<I', sym_map[h['sym']])
        edits_list.append({
            'kind': '0x100',
            'addr': f"{h['addr']:#x}",
            'expect': expected_stock.hex(),
            'new': new_ptr.hex(),
            'why': h['why']
        })

    # Emit SCP Color Creator cell text hook (7 bytes)
    scp_hook_addr = 0x60e25ec8
    target_addr = sym_map['scp_cc_label']
    disp = target_addr - scp_hook_addr
    new_call = b'\xdd' + struct.pack('<i', disp) + b'\xf0\x88'
    stock_call = main[scp_hook_addr - BASE:scp_hook_addr - BASE + 7]
    assert stock_call == bytes.fromhex('dd092e0c00f088'), (
        f"Stock mismatch at {scp_hook_addr:#x}: got {stock_call.hex()}"
    )
    edits_list.append({
        'kind': '0x100',
        'addr': f"{scp_hook_addr:#x}",
        'expect': stock_call.hex(),
        'new': new_call.hex(),
        'why': 'SCP Color Creator cell text hook: display active look name & mode/page'
    })

    # Built-in looks table (data) in the Section 5 tail
    assert BUILTIN_ADDR >= S5_FF_START + 16 and BUILTIN_ADDR + len(builtin) <= S5_LOAD_END - 16
    assert BUILTIN_ADDR % 4 == 0
    boff = BUILTIN_ADDR - BASE
    assert all(b == 0xFF for b in main[boff - 16:boff + len(builtin) + 16]), 'S5 tail not free'
    edits_list.append({
        'kind': '0x100',
        'addr': f'{BUILTIN_ADDR:#x}',
        'expect': 'ff' * len(builtin),
        'new': builtin.hex(),
        'why': 'Built-in looks: 16 x 64-byte look records (same bytes as the card file) in the Section 5 FF tail',
    })

    # Emit cave payload
    edits_list.append({
        'kind': '0x100',
        'addr': f'{CAVE_ADDR:#x}',
        'expect': bytes([0xFF] * len(cave_payload)).hex(),
        'new': cave_payload.hex(),
        'why': f'Live View Color Creator Caduceus Look Selector & Guide Label ({len(cave_payload)} bytes)'
    })

    edits = {
        'components': ['0x100'],
        'edits': edits_list
    }

    out_file = Path(__file__).parent / 'edits.json'
    out_file.write_text(json.dumps(edits, indent=2) + '\n')
    print(
        f'Generated {out_file} ({len(cave_payload)} bytes cave at {CAVE_ADDR:#x}..{cave_end:#x}, '
        f'{len(POINTER_HOOKS)} pointer hooks)'
    )


if __name__ == '__main__':
    build()
