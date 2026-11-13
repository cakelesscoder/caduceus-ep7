#!/usr/bin/env python3
"""OM-D E-M1 Mark II still-aspect patch: repurpose hidden ids 6 (7:6) -> XPan 65:24 and 7 (6:5) -> 21:9.

Ports the Caduceus E-P7 aspect ratio pipeline to OM-D E-M1 Mark II firmware (v3.70):
  1. Per-aspect size & geometry tables: 46 tables updated across binary.
  2. Split capture tables: W (0x60556cc4) and H (0x60556e62) across 23 size classes.
  3. ORF AspectFrame: jump table (0x60556c24) redirects ids 6/7 to width-limited frame case (0x604240b1).
  4. Rec-view 640-class tables: W (0x605570dc) and H (0x605570ee) updated to 640x240 / 640x272.
  5. Ratio tables: RATIO_U8 (0x6026e524, copied to RAM 0x61f93a64) and RATIO_U16 (0x60502192) updated to (65,24)/(21,9).
  6. AF window tables: AFWIN_1 (0x607483b8) and AFWIN_2 (0x607483e4) ids 6/7 set to 16:9 dimensions.
  7. Setting validator: Sid 270 record (0x604f07cc) expanded to 7-entry list [1, 3, 2, 4, 9, 6, 7].
  8. Menu option list: Image Aspect descriptor (0x6124ea1c) expanded to 8 entries with Panorama (241) and Wide (2661).
  9. SCP option strip: Lv_Control descriptor (0x6124aea4) expanded to 7 entries in both white and green lists.
 10. CapThr Live View & Playback switches: S7 (0x60b2f8ec), S8 (0x60b2f918), S9 (0x60b2f944), S10 (0x60b4cedc),
     S_alt (0x60b3bd68) jump table targets redirected to custom 640x240 / 640x272 case blocks.
 11. Pixel-size readout: table (0x612c74fc) cloned to 7-column table with recorded L/M/S sizes and getter (0x60f13985) updated.

All code and allocated lists live safely in Section 1 loaded FF tail (0x60257580..0x602577f4, 628 of 640 bytes).
"""

import json
import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BIN_PATH = ROOT / "em1mk2/extracted/00_0100_40560020.decoded.bin"
OUT_PATH = Path(__file__).resolve().parent / "edits.json"

B = 0x60021020
HEIGHT_ALIGN = 16

NEW = {
    6: ('XPan 65:24', 65, 24),
    7: ('21:9', 21, 9)
}
CODE = {i: (h << 8) | w for i, (_, w, h) in NEW.items()}
STR_LABEL = {6: 241, 7: 2661}  # 'Panorama', 'Wide' (stock strings, shared with other lists: not edited)
# Owner (2026-11-12): use the ratio as the name. Kind 5 = text from a char* (FIRMWARE_GUIDE "Labels"; the resolver
# 0x60e59f78 copies it), so no stock string changes. The text lives in the last 12 bytes of the section-1 cave.
SHORT_TEXT = {6: b'65:24\0', 7: b'21:9\0'}
# Real icons (patches/omdem1mk2/aspect_icons): {id: (normal, selected)}. The release builder adds those edits whenever
# aspect is in; EM1_ASPECT_PLACEHOLDER_ICONS=1 falls back to the 16:9 / 3:2 icons. Since v0.4c6 only the white 50x38
# icons exist (stored in main-image free space, which has no room for the 64x48 green ones), so the selected state
# shows the white icon too.
ICON_IDS = {6: (6668, 6668), 7: (7086, 7086)}
SHORT_TEXT_ADDR = {6: 0x602577f4, 7: 0x602577fa}

# Section 1 free space: 0x60257580..0x60257800 (640 bytes)
CAVE_BASE = 0x60257580
CAVE_MAX = 0x60257800

# Subsystem addresses
VAL_REC = 0x604f07cc
VAL_LIST = 0x604ed6fa

MENU_DESC = 0x6124ea1c
MENU_COND = 0x6124d8b0

SCP_DESC = 0x6124aea4
SCP_A = 0x61249554
SCP_COND = 0x61247d80
SCP_ICONS_A = {1: 477, 3: 476, 2: 478, 4: 2422, 9: 479}
SCP_ICONS_B = {1: 472, 3: 471, 2: 473, 4: 2421, 9: 475}

WH_W = 0x60556cc4
WH_H = 0x60556e62
WH_CLASSES = 23

FRAME_JT = 0x60556c24
FRAME_WIDE = 0x604240b1
FRAME_TALL = 0x604240da

REC640_W = 0x605570dc
REC640_H = 0x605570ee

RATIO_U8 = 0x6026e524
RATIO_U16 = 0x60502192

AFWIN_1 = 0x607483b8
AFWIN_2 = 0x607483e4

SW_S7_JT = 0x60b2f8ec
SW_S8_JT = 0x60b2f918
SW_S9_JT = 0x60b2f944
SW_S10_JT = 0x60b4cedc
SW_SALT_JT = 0x60b3bd68

PIX_TAB = 0x612c74fc
PIX_FN = 0x60f13985

TABLES = [
    (0x6021b1b0, 'u16wh'),
    (0x6021b1e4, 'u16wh'),
    (0x6021b218, 'u16wh'),
    (0x60280038, 'u16wh'),
    (0x60280060, 'u16wh'),
    (0x60280088, 'u16wh'),
    (0x602800b0, 'u16wh'),
    (0x602800d8, 'u16wh'),
    (0x60280128, 'u16wh'),
    (0x60280150, 'u16wh'),
    (0x60280178, 'u16wh'),
    (0x602801a0, 'u16wh'),
    (0x602801c8, 'u16wh'),
    (0x602801f0, 'u16wh'),
    (0x60280560, 'u16wh'),
    (0x60280584, 'u16wh'),
    (0x6053c050, 'u16wh'),
    (0x6054d2ec, 'rect16'),
    (0x6054d39c, 'rect16'),
    (0x6027a824, 'u16id0wh'),
    (0x6027a87c, 'u16id0wh'),
    (0x60b3812c, 'u16id0wh'),
    (0x60b3817c, 'u16id0wh'),
    (0x60b381cc, 'u16id0wh'),
    (0x60b3821c, 'u16id0wh'),
    (0x60b382bc, 'u16id0wh'),
    (0x60b3835c, 'u16id0wh'),
    (0x60b3844c, 'u16id0wh'),
    (0x60b384ec, 'u16id0wh'),
    (0x60b3853c, 'u16id0wh'),
    (0x60b3858c, 'u16id0wh'),
    (0x6050acee, 'u16whcode'),
    (0x6053bd62, 'u16whcode'),
    (0x6053bfae, 'u16whcode'),
    (0x60bb6da8, 'u32idwh'),
    (0x60bb6e20, 'u32idwh'),
    (0x60bb6e98, 'u32idwh'),
    (0x60bb7000, 'u32idwh'),
    (0x60bb70f0, 'u32idwh'),
    (0x60bb7258, 'u32idwh'),
    (0x60bb7348, 'u32idwh'),
    (0x60bb73c0, 'u32idwh'),
    (0x60bb7438, 'u32idwh'),
    (0x60bb74b0, 'u32idwh'),
    (0x60bb75c8, 'u32idwh'),
    (0x60bb7640, 'u32idwh'),
]

R_RATIOS = [4/3, 3/2, 16/9, 1, 5/4, 7/6, 6/5, 7/5, 3/4]
LAYOUTS = [
    ('u16wh', 4, '<HH', 0, 1),
    ('rect16', 16, '<8H', 2, 3),
    ('u16id0wh', 8, '<4H', 2, 3),
    ('u16whcode', 6, '<3H', 0, 1),
    ('u32idwh', 12, '<3I', 1, 2)
]
LAY = {name: (st, fmt, iw, ih) for name, st, fmt, iw, ih in LAYOUTS}


def new_first(ents):
    """EM1_ASPECT_NEW_FIRST=1 (camera probe): put ids 6/7 at the front of an option list. Shows whether the menu and
    strip stop after a stock row count (6/7 then appear) or drop 6/7 by value (they still don't)."""
    if os.environ.get('EM1_ASPECT_NEW_FIRST') != '1':
        return ents
    return [e for e in ents if e[0] in (6, 7)] + [e for e in ents if e[0] not in (6, 7)]


def strip_entry(i, icons):
    """Live Control strip entry for id 6/7. The strip draws icons (type 3) only: on v0.4c1 (type 4 text) the 6/7 cells were
    blank (camera 2026-11-12), and the Image Aspect option list showed no rows for them. Placeholder icons until XP / 21:9
    bitmaps exist: 6 -> the 16:9 icon, 7 -> the 3:2 icon. EM1_ASPECT_STRIP_TEXT=1 restores the text entries."""
    if os.environ.get('EM1_ASPECT_STRIP_TEXT') == '1':
        return (i, 4, STR_LABEL[i], SCP_COND)
    if os.environ.get('EM1_ASPECT_PLACEHOLDER_ICONS') == '1':
        return (i, 3, icons[{6: 3, 7: 2}[i]], SCP_COND)
    return (i, 3, ICON_IDS[i][0 if icons is SCP_ICONS_A else 1], SCP_COND)



# Icon entry words written by patches/omdem1mk2/aspect_icons/build.py (ENTRY_AT): the getter hook gt returns these.
ICON_ENTRY = {6668: 0x605d2dcc, 7086: 0x605d2dd0, 6669: 0x605d2dd4, 7087: 0x605d2dd8}


def assemble_af(at):
    """Assemble af.s at `at` with mn10300-elf-as/ld; T_<hex> jump targets and E_<id> icon entries become --defsym.
    Returns (code, symbols)."""
    import re, subprocess, tempfile
    tc = Path('/home/hertzel/ep7fw-toolchains/mn10300/bin')
    src = (Path(__file__).resolve().parent / 'af.s').read_text()
    targets = sorted(set(re.findall(r'\bT_([0-9a-f]{8})\b', src)))
    with tempfile.TemporaryDirectory() as td:
        s, o, elf, bn = (Path(td) / n for n in ('af.s', 'af.o', 'af.elf', 'af.bin'))
        s.write_text(src)
        subprocess.run([str(tc / 'mn10300-elf-as'), str(s), '-o', str(o)], check=True)
        subprocess.run([str(tc / 'mn10300-elf-ld'), f'--section-start=.text={at:#x}', '-e', '_start', str(o), '-o', str(elf)]
                       + [f'--defsym=T_{t}=0x{t}' for t in targets]
                       + [f'--defsym=E_{i}={a:#x}' for i, a in ICON_ENTRY.items()], check=True)
        subprocess.run([str(tc / 'mn10300-elf-objcopy'), '-O', 'binary', str(elf), str(bn)], check=True)
        nm = subprocess.run([str(tc / 'mn10300-elf-nm'), str(elf)], capture_output=True, text=True, check=True).stdout
        syms = {p[2]: int(p[0], 16) for p in (l.split() for l in nm.splitlines()) if len(p) == 3}
        return bn.read_bytes(), syms


def build_edits():
    d = BIN_PATH.read_bytes()
    edits = []

    def edit(addr, old_bytes, new_bytes, desc):
        assert len(old_bytes) == len(new_bytes), f"Mismatched length at {addr:#x}: {len(old_bytes)} != {len(new_bytes)}"
        off = addr - B
        actual = d[off:off + len(old_bytes)]
        assert actual == old_bytes, f"Byte mismatch at {addr:#x} ({desc}): expected {old_bytes.hex()}, actual {actual.hex()}"
        edits.append({
            "kind": "0x100",
            "addr": f"{addr:#x}",
            "expect": old_bytes.hex(),
            "new": new_bytes.hex(),
            "why": desc
        })

    # 1. Update all 46 per-aspect size and geometry tables
    for a1, lay in TABLES:
        st, fmt, iw, ih = LAY[lay]
        rows = [list(struct.unpack_from(fmt, d, a1 + k * st - B)) for k in range(9)]
        assert abs(rows[5][iw] / rows[5][ih] - 7 / 6) < 0.035, f"id6 ratio mismatch at {a1:#x}"
        assert abs(rows[6][iw] / rows[6][ih] - 6 / 5) < 0.035, f"id7 ratio mismatch at {a1:#x}"
        W = max(rows[0][iw], rows[2][iw])
        for i, (name, rw, rh) in NEW.items():
            r = list(rows[i - 1])
            h = round(W * rh / rw / HEIGHT_ALIGN) * HEIGHT_ALIGN
            r[iw], r[ih] = W, h
            if lay == 'u16whcode':
                r[2] = CODE[i]
            if lay in ('u32idwh', 'u16id0wh'):
                assert r[0] == i
            if lay == 'rect16':
                x0, y0r = rows[0][0], rows[0][1]
                r[0] = x0
                r[1] = y0r + (rows[0][3] - h) // 2
                orgx = rows[0][0] - rows[0][4]
                orgy = rows[0][1]
                c0, c1 = rows[0][5], rows[0][7]
                r[4] = r[0] - orgx
                r[5] = max(r[1] - orgy, c0)
                r[6] = r[0] + W - 1 - orgx
                r[7] = min(r[1] + h - 1 - orgy, c1)
            addr = a1 + (i - 1) * st
            old = struct.pack(fmt, *rows[i - 1])
            new = struct.pack(fmt, *r)
            if old != new:
                edit(addr, old, new, f"{lay}@{a1:#x} id{i} -> {W}x{h}")

    # 2. Split capture tables (W and H) across 23 size classes
    w1 = struct.unpack_from(f'<{WH_CLASSES}H', d, WH_W - B)
    w3 = struct.unpack_from(f'<{WH_CLASSES}H', d, WH_W + 2 * WH_CLASSES * 2 - B)

    def wh_row(i, k):
        old = struct.unpack_from(f'<{WH_CLASSES}H', d, (WH_W, WH_H)[k] + 2 * WH_CLASSES * (i - 1) - B)
        ow = struct.unpack_from(f'<{WH_CLASSES}H', d, WH_W + 2 * WH_CLASSES * (i - 1) - B)
        _, rw, rh = NEW[i]
        out = []
        for c in range(WH_CLASSES):
            if ow[c] == 0:
                out.append(old[c])
                continue
            W = max(w1[c], w3[c])
            out.append(W if k == 0 else round(W * rh / rw / HEIGHT_ALIGN) * HEIGHT_ALIGN)
        return struct.pack(f'<{WH_CLASSES}H', *out)

    for base, k in ((WH_W, 0), (WH_H, 1)):
        for i in (6, 7):
            addr = base + 2 * WH_CLASSES * (i - 1)
            old = d[addr - B:addr + 2 * WH_CLASSES - B]
            new = wh_row(i, k)
            edit(addr, old, new, f'Capture size table {"WH"[k]}@{base:#x} id{i}')

    # 3. ORF AspectFrame: jump table entries for id 6 and id 7
    for i in (6, 7):
        ea = FRAME_JT + 4 * (i - 1)
        old = d[ea - B:ea - B + 4]
        assert struct.unpack('<I', old)[0] == FRAME_TALL
        edit(ea, old, struct.pack('<I', FRAME_WIDE), f"AspectFrame JT id{i} -> wide case")

    # 4. Rec-view 640-class tables
    edit(REC640_W + 10, d[REC640_W + 10 - B:REC640_W + 14 - B], struct.pack('<2H', 640, 640), "rec-view 640 W ids 6,7 -> 640")
    edit(REC640_H + 10, d[REC640_H + 10 - B:REC640_H + 14 - B], struct.pack('<2H', 240, 272), "rec-view 640 H ids 6,7 -> 240, 272")

    # 5. Ratio tables
    edit(RATIO_U8 + 12, d[RATIO_U8 + 12 - B:RATIO_U8 + 16 - B], bytes([65, 24, 21, 9]), "RATIO_U8 ids 6,7 -> (65,24), (21,9)")
    edit(RATIO_U16 + 20, d[RATIO_U16 + 20 - B:RATIO_U16 + 28 - B], struct.pack('<4H', 65, 24, 21, 9), "RATIO_U16 ids 6,7 -> (65,24), (21,9)")

    # 6. AF window tables (ids 6, 7 -> 16:9 values)
    edit(AFWIN_1 + 24, d[AFWIN_1 + 24 - B:AFWIN_1 + 32 - B], struct.pack('<4H', 43, 27, 43, 27), "AFWIN_1 ids 6,7 -> (43,27)")
    edit(AFWIN_2 + 24, d[AFWIN_2 + 24 - B:AFWIN_2 + 32 - B], struct.pack('<4H', 84, 52, 84, 52), "AFWIN_2 ids 6,7 -> (84,52)")

    # 7. Layout Cave in Section 1 FF tail (0x60257580)
    cave = bytearray()
    cave_addr = CAVE_BASE

    # (a) VAL_NEW: 7-byte list
    val_new_addr = cave_addr + len(cave)
    # EM1_ASPECT_VAL overrides the validator list for camera probes (e.g. "1,3,2,9,6,7": does dropping 1:1 hide it?)
    val_list = [int(x) for x in os.environ.get('EM1_ASPECT_VAL', '1,3,2,4,9,6,7').split(',')]
    assert 1 <= len(val_list) <= 8   # 8 bytes reserved at the cave start
    cave += bytes(val_list + [0] * (8 - len(val_list)))  # padded to 8 bytes

    # (b) MENU_NEW: 8 entries of 12 bytes
    menu_new_addr = cave_addr + len(cave)
    menu_ents = [
        (1, 4, 292, MENU_COND),
        (3, 4, 291, MENU_COND),
        (2, 4, 293, MENU_COND),
        (4, 4, 1786, MENU_COND),
        (9, 4, 295, MENU_COND),
        (6, 5, 0, SHORT_TEXT_ADDR[6]),
        (7, 5, 0, SHORT_TEXT_ADDR[7]),
        (10, 4, 3261, MENU_COND)
    ]
    for val, typ, str_id, cond in new_first(menu_ents):
        cave += struct.pack('<IHHI', val, typ, str_id, cond)

    # (c) SCP_NEWB: 7 entries of 12 bytes (green list)
    scp_newb_addr = cave_addr + len(cave)
    scp_b_ents = [
        (1, 3, SCP_ICONS_B[1], SCP_COND),
        (3, 3, SCP_ICONS_B[3], SCP_COND),
        (2, 3, SCP_ICONS_B[2], SCP_COND),
        (4, 3, SCP_ICONS_B[4], SCP_COND),
        (9, 3, SCP_ICONS_B[9], SCP_COND),
        strip_entry(6, SCP_ICONS_B),
        strip_entry(7, SCP_ICONS_B)
    ]
    for val, typ, str_or_icon, cond in new_first(scp_b_ents):
        cave += struct.pack('<IHHI', val, typ, str_or_icon, cond)

    # (d) Case blocks for S7, S8, S9, S10, S_alt
    def jmp32(src, dst):
        return b'\xdc' + struct.pack('<i', dst - src)

    sw_cases = {}
    h640 = {6: 240, 7: 272}

    # S7: mov 640, d0; mov d0, (40, sp); mov H, d0; jmp 0x608bb796
    for i in (6, 7):
        sw_cases[('S7', i)] = cave_addr + len(cave)
        block = bytes([0x2c, 0x80, 0x02, 0x42, 0x28, 0x2c, h640[i] & 0xff, (h640[i] >> 8) & 0xff])
        block += jmp32(cave_addr + len(cave) + len(block), 0x608bb796)
        cave += block

    # S8: mov 640, d0; mov d0, (40, sp); mov H, d0; jmp 0x608bb9a6
    for i in (6, 7):
        sw_cases[('S8', i)] = cave_addr + len(cave)
        block = bytes([0x2c, 0x80, 0x02, 0x42, 0x28, 0x2c, h640[i] & 0xff, (h640[i] >> 8) & 0xff])
        block += jmp32(cave_addr + len(cave) + len(block), 0x608bb9a6)
        cave += block

    # S9: mov 640, d0; mov d0, (36, sp); mov H, d0; jmp 0x608bbd2e
    for i in (6, 7):
        sw_cases[('S9', i)] = cave_addr + len(cave)
        block = bytes([0x2c, 0x80, 0x02, 0x42, 0x24, 0x2c, h640[i] & 0xff, (h640[i] >> 8) & 0xff])
        block += jmp32(cave_addr + len(cave) + len(block), 0x608bbd2e)
        cave += block

    # S10: mov 640, a0; mov H, d3; jmp 0x60911f49
    for i in (6, 7):
        sw_cases[('S10', i)] = cave_addr + len(cave)
        block = bytes([0x24, 0x80, 0x02, 0x2f, h640[i] & 0xff, (h640[i] >> 8) & 0xff])
        block += jmp32(cave_addr + len(cave) + len(block), 0x60911f49)
        cave += block

    # S_alt: mov 640, d0; mov H, d1; jmp 0x608d411e
    for i in (6, 7):
        sw_cases[('SALT', i)] = cave_addr + len(cave)
        block = bytes([0x2c, 0x80, 0x02, 0x2d, h640[i] & 0xff, (h640[i] >> 8) & 0xff])
        block += jmp32(cave_addr + len(cave) + len(block), 0x608d411e)
        cave += block

    # Align to 4 bytes for PIX_NEW
    while len(cave) % 4 != 0:
        cave.append(0)

    # (e) PIX_NEW: 7-column pixel-size table
    pix_new_addr = cave_addr + len(cave)
    pix_ids = [1, 3, 2, 4, 9, 6, 7]
    cave += struct.pack('<7H', *pix_ids)  # 14 bytes

    # 10 rows: key (u16), w[7] (7*u16), h[7] (7*u16) = 30 bytes per row
    stock_pix_rows = [
        (0,  5184, 1920, 2224),
        (13, 3200, 1184, 1376),
        (11, 2560,  944, 1104),
        (8,  1600,  592,  688),
        (7,  1280,  480,  544),
        (6,  1024,  384,  432),
        (5,   640,  240,  272),
        (3,  1920,  704,  816),
        (20, 8160, 3008, 3504),
        (21, 5760, 2128, 2464)
    ]
    # Read stock rows to preserve stock columns (1, 3, 2, 4, 9)
    stock_rows_off = PIX_TAB + 10 - B
    for r_idx, (key, exp_w, h6, h7) in enumerate(stock_pix_rows):
        stock_row = d[stock_rows_off + r_idx * 22: stock_rows_off + (r_idx + 1) * 22]
        s_key, = struct.unpack_from('<H', stock_row, 0)
        assert s_key == key
        s_w = list(struct.unpack_from('<5H', stock_row, 2))
        s_h = list(struct.unpack_from('<5H', stock_row, 12))
        row_w = s_w + [exp_w, exp_w]
        row_h = s_h + [h6, h7]
        cave += struct.pack('<H7H7H', key, *row_w, *row_h)

    # Emit the Section 1 cave edit
    cave_end = cave_addr + len(cave)
    assert cave_end <= min(SHORT_TEXT_ADDR.values()), f"Cave overflow into the label text: {cave_end:#x}"
    assert cave_end <= CAVE_MAX, f"Cave overflow: {cave_end:#x} > {CAVE_MAX:#x}"
    edit(cave_addr, d[cave_addr - B:cave_end - B], bytes(cave), f"Section 1 Aspect cave ({len(cave)} bytes at {cave_addr:#x}..{cave_end:#x})")
    txt_lo = min(SHORT_TEXT_ADDR.values())
    txt = SHORT_TEXT[6] + SHORT_TEXT[7]
    assert SHORT_TEXT_ADDR[7] == txt_lo + len(SHORT_TEXT[6]) and txt_lo + len(txt) <= CAVE_MAX
    edit(txt_lo, d[txt_lo - B:txt_lo + len(txt) - B], txt, 'menu label text "65:24" / "21:9" (kind-5 char* labels)')

    # 8. Setting Validator edits (VAL_REC = 0x604f07cc)
    edit(VAL_REC + 4, d[VAL_REC + 4 - B:VAL_REC + 8 - B], struct.pack('<I', val_new_addr), "VAL_REC list pointer -> VAL_NEW")
    edit(VAL_REC + 12, d[VAL_REC + 12 - B:VAL_REC + 14 - B], struct.pack('<H', len(val_list)), f"VAL_REC count 5 -> {len(val_list)}")
    # Sids 511/512 (= the SCP aspect items 0x1ff/0x200) have their own validator records on a stock 1,3,2,4,9 list
    # (0x604edb06). The SCP option row takes its slot values from a list object (+56 count, +64 values; 0x60f35214
    # returns 2000 past the count) -> with 5 values the two extra slots had no value, so no bitmap (v0.4c5-c10 camera:
    # empty, selectable slots). Default since v0.4c11; EM1_ASPECT_511=0 restores the stock lists.
    if os.environ.get('EM1_ASPECT_511', '1') == '1':
        for rec, sid in ((0x604f162c, 511), (0x604f1640, 512)):
            assert struct.unpack_from('<HH', d, rec - B) == (sid, 0x80)
            edit(rec + 4, d[rec + 4 - B:rec + 8 - B], struct.pack('<I', val_new_addr), f"sid {sid} validator list -> VAL_NEW")
            edit(rec + 12, d[rec + 12 - B:rec + 14 - B], struct.pack('<H', len(val_list)), f"sid {sid} validator count 5 -> {len(val_list)}")
    if True:   # default since v0.4c4 (was under EM1_ASPECT_511): SCP / info icons for 6/7
        # Strip icons: display resources 0x1ff/0x200 ({u32 id, A, B, u32 count}, 0x612e1f08 / 0x612e1fb8) map value ->
        # bitmap through two 5-entry {u32 value, u32 bitmap} lists (A white 0x612e1dc8, B green 0x612e1df0). With 511/512
        # at 7 the strip shows 7 slots, 6/7 blank and not selectable (camera, v0.4b9-probe). New 7-entry lists in the
        # section-5 FF tail; 6/7 borrow the 16:9 / 3:2 icons until real ones exist (placeholder). b9/b10 showed no effect only
        # because the interlock rules still hid 6/7; v0.4c3 camera: 6/7 missing from the SCP, which these tables may feed [I].
        RES_A, RES_B, RES_NEW = 0x612e1dc8, 0x612e1df0, 0x60bc8760   # after the AF lists (§14)
        A = [struct.unpack_from('<II', d, RES_A + 8 * k - B) for k in range(5)]
        Bl = [struct.unpack_from('<II', d, RES_B + 8 * k - B) for k in range(5)]
        assert [v for v, _ in A] == [1, 3, 2, 9, 4] and [v for v, _ in Bl] == [1, 3, 2, 9, 4]
        ia, ib = dict(A), dict(Bl)
        if os.environ.get('EM1_ASPECT_PLACEHOLDER_ICONS') == '1':
            newA = A + [(6, ia[3]), (7, ia[2])]
            newB = Bl + [(6, ib[3]), (7, ib[2])]
        elif os.environ.get('EM1_SCP_ROW_DIAG') == '1':
            # v0.4c12d camera diagnostic: 6 -> stock 16:9 id 476 (no hook, OSD data); 7 stays 7086 (with EM1_ICON_DIAG=1
            # its hook entry points at the stock 16:9 descriptor). Separates "row cells not drawn" / "new id rejected" /
            # "main-image bitmap data not drawn" in the SCP option row (ASPECT.md §6.11).
            newA = A + [(6, ia[3]), (7, ICON_IDS[7][0])]
            newB = Bl + [(6, ia[3]), (7, ICON_IDS[7][1])]
        else:
            newA = A + [(6, ICON_IDS[6][0]), (7, ICON_IDS[7][0])]
            newB = Bl + [(6, ICON_IDS[6][1]), (7, ICON_IDS[7][1])]
        blob = b''.join(struct.pack('<II', v, bm) for v, bm in newA + newB)
        edit(RES_NEW, d[RES_NEW - B:RES_NEW + len(blob) - B], blob, "display-resource icon lists A/B with ids 6/7")
        for rec, rid in ((0x612e1f08, 0x1ff), (0x612e1fb8, 0x200)):
            assert struct.unpack_from('<IIII', d, rec - B) == (rid, RES_A, RES_B, 5)
            edit(rec + 4, d[rec + 4 - B:rec + 16 - B], struct.pack('<III', RES_NEW, RES_NEW + 8 * len(newA), len(newA)),
                 f"display resource {rid:#x}: icon lists -> 7 entries")
        # SCP option row (OK on the aspect tile), v0.4c10: a second item table 0x612e3040 (22 x 20-B records
        # {u32 item, u32 type, A, B, u32 n}, 11 per SCP mode 215/216, read at 0x60f3699b) has its own 0x1ff/0x200
        # records with the same 5-entry lists (copies at 0x612e2eb0 / 0x612e2ed8). The row builder 0x60f36b24 searches
        # A (n entries) for each offered value and writes the white / green bitmap ids into obj+232 / obj+228; 6/7 never
        # matched, so their slots were selectable and blank whatever the bitmap (c5-c9d). Same 7-entry lists as above.
        for rec, rid in ((0x612e307c, 0x1ff), (0x612e3158, 0x200)):
            assert struct.unpack_from('<5I', d, rec - B) == (rid, 0x39, 0x612e2eb0, 0x612e2ed8, 5)
            assert d[0x612e2eb0 - B:0x612e2eb0 + 40 - B] == d[RES_A - B:RES_A + 40 - B]
            assert d[0x612e2ed8 - B:0x612e2ed8 + 40 - B] == d[RES_B - B:RES_B + 40 - B]
            edit(rec + 8, d[rec + 8 - B:rec + 20 - B], struct.pack('<III', RES_NEW, RES_NEW + 8 * len(newA), len(newA)),
                 f"SCP option-row item {rid:#x} (table 0x612e3040): icon lists -> 7 entries")
            # v0.4c12: the record's type (+4) is the option screen pushed on OK: 0x39 = screen 57, aspect-only, whose
            # layout draws 5 cells (c12d camera: cells 6/7 never drawn although the row data is complete). 0x3e = the
            # generic scrolling row used by items with 2, 4 and 41 values (0x201/0x203/0x1f9/0x2ae). Aspect-specific
            # behaviour of screen 57 (checks at 0x60f37808 / 0x60f37ac8, likely the pixel-size line) is lost.
            # EM1_SCP_ROW_TYPE=0x39 keeps stock.
            typ = int(os.environ.get('EM1_SCP_ROW_TYPE', '0x39'), 16)   # default stock since c13: screen 57 shows 7 cells (owner, c12)
            if typ != 0x39:
                edit(rec + 4, d[rec + 4 - B:rec + 8 - B], struct.pack('<I', typ), f"SCP option-row item {rid:#x}: screen 0x39 -> {typ:#x} (generic row)")
        # 18. SCP option screen 57's own label source (v0.4c13). Owner, c12: screen 57 already lays out 7 cells; only
        # the icons in cells 6/7 are missing, and c12d showed stock ids/data placed in the row data above don't reach
        # them. Option-label provider 0x60e65473 (directory 0x6123ee2c: key 0 -> 78 x 52-B records 0x6123de54
        # {u32 key, A, B, u32 n, ...}) has record key 16 = aspect (0x6123e194): label lists {u32 value, u16 kind, u16 id,
        # u32 cond} A white 0x6123a174 / B green 0x6123a1b0, n 5 (values 1,3,2,9,4) -- the one aspect list never
        # extended (ASPECT.md §6.9 / §6.13). New 7-entry lists (+ 6/7, kind 3, the white icon ids, stock cond) in the
        # section-2 FF tail (0x60580780 / 0x6058018c), n 5 -> 7.
        LBL_REC, LBL_A, LBL_B = 0x6123e194, 0x6123a174, 0x6123a1b0
        LBL_NEW_A, LBL_NEW_B = 0x60580780, 0x6058018c
        assert struct.unpack_from('<4I', d, LBL_REC - B) == (16, LBL_A, LBL_B, 5)
        la = [struct.unpack_from('<IHHI', d, LBL_A + 12 * k - B) for k in range(5)]
        lb = [struct.unpack_from('<IHHI', d, LBL_B + 12 * k - B) for k in range(5)]
        assert [r[:3] for r in la] == [(1, 3, 477), (3, 3, 476), (2, 3, 478), (9, 3, 479), (4, 3, 2422)], la
        assert [r[:3] for r in lb] == [(1, 3, 472), (3, 3, 471), (2, 3, 473), (9, 3, 475), (4, 3, 2421)], lb
        cond = la[0][3]
        assert all(r[3] == cond for r in la + lb)
        for new, rows, what in ((LBL_NEW_A, la, 'white'), (LBL_NEW_B, lb, 'green (white ids for 6/7)')):
            rows = rows + [(6, 3, ICON_IDS[6][0], cond), (7, 3, ICON_IDS[7][0], cond)]
            blob = b''.join(struct.pack('<IHHI', *r) for r in rows)
            assert d[new - B:new + len(blob) - B] == b'\xff' * len(blob), hex(new)
            edit(new, d[new - B:new + len(blob) - B], blob, f'SCP option screen 57 label list {what}: stock 5 + 65:24 / 21:9')
        edit(LBL_REC + 4, d[LBL_REC + 4 - B:LBL_REC + 16 - B], struct.pack('<III', LBL_NEW_A, LBL_NEW_B, 7),
             'option-label record key 16 (aspect): lists -> 7 entries')

    # 9. Menu Option List descriptor (MENU_DESC = 0x6124ea1c)
    edit(MENU_DESC + 2, d[MENU_DESC + 2 - B:MENU_DESC + 4 - B], struct.pack('<H', 8), "MENU_DESC count 6 -> 8")
    edit(MENU_DESC + 4, d[MENU_DESC + 4 - B:MENU_DESC + 8 - B], struct.pack('<I', menu_new_addr), "MENU_DESC list pointer -> MENU_NEW")

    # 10. SCP Option Strip (SCP_DESC = 0x6124aea4)
    # Expand List A in place at 0x61249554
    scp_a_ents = [
        (1, 3, SCP_ICONS_A[1], SCP_COND),
        (3, 3, SCP_ICONS_A[3], SCP_COND),
        (2, 3, SCP_ICONS_A[2], SCP_COND),
        (4, 3, SCP_ICONS_A[4], SCP_COND),
        (9, 3, SCP_ICONS_A[9], SCP_COND),
        strip_entry(6, SCP_ICONS_A),
        strip_entry(7, SCP_ICONS_A)
    ]
    new_scp_a = bytearray()
    for val, typ, str_or_icon, cond in new_first(scp_a_ents):
        new_scp_a += struct.pack('<IHHI', val, typ, str_or_icon, cond)
    edit(SCP_A, d[SCP_A - B:SCP_A + len(new_scp_a) - B], bytes(new_scp_a), "SCP List A expanded in-place to 7 entries")

    edit(SCP_DESC + 2, d[SCP_DESC + 2 - B:SCP_DESC + 4 - B], struct.pack('<H', 7), "SCP_DESC count 5 -> 7")
    edit(SCP_DESC + 8, d[SCP_DESC + 8 - B:SCP_DESC + 12 - B], struct.pack('<I', scp_newb_addr), "SCP_DESC List B pointer -> SCP_NEWB")

    # 11. CapThr jump table edits
    for name, jt in [('S7', SW_S7_JT), ('S8', SW_S8_JT), ('S9', SW_S9_JT), ('S10', SW_S10_JT), ('SALT', SW_SALT_JT)]:
        for i in (6, 7):
            ea = jt + 4 * i
            old = d[ea - B:ea - B + 4]
            new = struct.pack('<I', sw_cases[(name, i)])
            edit(ea, old, new, f"{name} JT id{i} -> case block at {sw_cases[(name, i)]:#x}")

    # 12. PIX_FN edits (0x60f13985)
    # row 0 width: movhu (PIX_NEW + 14, d0)
    edit(0x60f13992, d[0x60f13992 - B:0x60f13998 - B], b'\xfc\xac' + struct.pack('<I', pix_new_addr + 14 + 2), "PIX_FN row0 w pointer")
    # row 0 height: movhu (PIX_NEW + 14 + 14, d0)
    edit(0x60f1399a, d[0x60f1399a - B:0x60f139a0 - B], b'\xfc\xac' + struct.pack('<I', pix_new_addr + 14 + 16), "PIX_FN row0 h pointer")
    # rows start: mov PIX_NEW + 14, a0
    edit(0x60f139cf, d[0x60f139cf - B:0x60f139d5 - B], b'\xfc\xdc' + struct.pack('<I', pix_new_addr + 14), "PIX_FN rows start pointer")
    # ids list: mov PIX_NEW, a1
    edit(0x60f139e2, d[0x60f139e2 - B:0x60f139e8 - B], b'\xfc\xdd' + struct.pack('<I', pix_new_addr), "PIX_FN ids pointer")
    # layout immediates:
    edit(0x60f139f7, b'\x20\x0c', b'\x20\x10', "PIX_FN h offset (a0) 12 -> 16")
    edit(0x60f13a06, b'\xa5\x05', b'\xa5\x07', "PIX_FN aspect count 5 -> 7")
    edit(0x60f13a0c, b'\x20\x16', b'\x20\x1e', "PIX_FN row stride (a0) 22 -> 30")
    edit(0x60f13a12, b'\xf9\x02\x16', b'\xf9\x02\x1e', "PIX_FN debug udf00 stride 22 -> 30")
    edit(0x60f13a17, d[0x60f13a17 - B:0x60f13a1d - B], b'\xfc\xd2' + struct.pack('<I', pix_new_addr + 14), "PIX_FN rows start debug pointer")
    edit(0x60f13a2b, b'\x22\x0c', b'\x22\x10', "PIX_FN debug h offset (a2) 12 -> 16")

    # 13. Interlock rules: the real filter (found in emulation 2026-11-11, tools/omdem1mk2_emu_rules.py).
    # The option builder 0x60e4a59c asks facade slot +36 (0x60836357 -> 0x6086333c -> 0x602da752 -> rule engine
    # 0x602de6a7/0x602de667) whether each value is available. The engine's rule for sid 270 (ROM rule table 0x604a8408,
    # record 179 {270, 2000, list 0x604a0578, n 13}) and the continuation entries 0x604a05e0..0x604a0640 point at four
    # {u16 value, u16 result} tables that list only 1,3,2,4,9,10, so 5..8 are rejected (emulated: 1-4,9 -> 0, others 256).
    # Copies with 6/7 appended go in the section-2 FF tail (same section as the rules); every reference is repointed.
    RULE_NEW = 0x60580700
    assert d[RULE_NEW - B:0x60580800 - B] == b'\xff' * (0x60580800 - RULE_NEW)
    tables = {0x604a0518: {6: 3, 7: 3},      # value -> 3
              0x604a0530: {6: 1, 7: 1},      # value -> 1
              0x604a0548: {6: 10, 7: 10},    # value -> 10
              0x604a0560: {6: 6, 7: 7}}      # identity (stock maps 10 -> 1)
    new_addr, blob = {}, b''
    for old, extra in tables.items():
        rows = [struct.unpack_from('<HH', d, old + 4 * k - B) for k in range(6)]
        assert [v for v, _ in rows] == [1, 3, 2, 4, 9, 10], f'rule table {old:#x} changed'
        new_addr[old] = RULE_NEW + len(blob)
        blob += b''.join(struct.pack('<HH', v, r) for v, r in rows + sorted(extra.items()))
    edit(RULE_NEW, d[RULE_NEW - B:RULE_NEW + len(blob) - B], blob, 'aspect interlock value tables with ids 6/7 (4 x 8 rows)')
    for ent in [0x604a0580 + 16 * k for k in range(6)] + list(range(0x604a05e0, 0x604a0648, 8)):
        ptr, n = struct.unpack_from('<II', d, ent - B)
        if ptr in tables:
            assert n == 6
            edit(ent, d[ent - B:ent + 8 - B], struct.pack('<II', new_addr[ptr], 8),
                 f'aspect interlock entry {ent:#x}: table {ptr:#x} -> {new_addr[ptr]:#x}, 6 -> 8 rows')

    # 14. AF target selector (E-P7 issue #23 equivalent). AF_Target_Actuator (0x60e3a9c6..) reads four headers
    # {u32 flag, u32 list, u32 count 6} at 0x61212d34 (refs 0x60e3ad52/0x60e3adb5); each list maps the aspect value
    # (1,3,2,4,9,10) to {style, 242-byte point mask, 121}. On the E-P7 a missing 6/7 left the mask pointer stale and
    # crashed in the selector. Lists copied with 6/7 rows = the 16:9 (value 3) row, as the E-P7 af_sel fix; section-5 tail.
    AF_HDR, AF_NEW = 0x61212d34, 0x60bc8560
    assert d[AF_NEW - B:AF_NEW + 4 * 128 - B] == b'\xff' * (4 * 128)
    blob = b''
    for k in range(4):
        hdr = AF_HDR + 12 * k
        flag, lst, n = struct.unpack_from('<III', d, hdr - B)
        assert n == 6, f'AF header {hdr:#x} count {n}'
        rows = [list(struct.unpack_from('<IIII', d, lst + 16 * j - B)) for j in range(6)]
        assert [r[0] for r in rows] == [1, 3, 2, 4, 9, 10]
        # v0.4c6 (16:9 rows) on camera: the selector opens with the 4:3 layout and no cursor. The layout chains
        # (0x60e3be0f, 0x60e3c9d2) test 9/4/3/2/1/10 and send any other value to the 4:3 default table 0x612141a0, so
        # 6/7 get the 4:3 layout. v0.4c7 tried the 4:3 rows: no change on camera (cursor still missing). Since v0.4c8:
        # the E-P7 aspect_fix policy, 16:9 everywhere: 16:9 rows here and the layout chains remapped by §17 (ch1/ch2).
        # EM1_ASPECT_AF43=1 builds the 4:3 rows.
        src = next(r for r in rows if r[0] == (1 if os.environ.get('EM1_ASPECT_AF43') == '1' else 3))
        rows += [[6] + src[1:], [7] + src[1:]]
        new = AF_NEW + len(blob)
        blob += b''.join(struct.pack('<IIII', *r) for r in rows)
        edit(hdr + 4, d[hdr + 4 - B:hdr + 12 - B], struct.pack('<II', new, 8), f'AF target header {hdr:#x}: list -> {new:#x}, 6 -> 8')
    edit(AF_NEW, d[AF_NEW - B:AF_NEW + len(blob) - B], blob, 'AF target aspect lists with ids 6/7 (= 16:9 mask/style, E-P7 aspect_fix policy)')

    # 16. SCP current-value cell (port of the E-P7 aspect_scp fix, camera-proven there in v0.29; E-P7 ASPECT.md §1j).
    # Cell builders 0x60e6a0b9 (cell self+2096) and 0x60e70bf0 (self+2100) clear the cell {u16 index, u8 kind, u8 state},
    # read GetValue(270) and look it up with 0x60e59f44 in 6-entry {u32 value, u32 index} lists 0x612413f4 / 0x612449d0
    # (1,3,2,4,9,10 -> 2,6,3,5,4,7). Index - 2 = part of the tile's widget record (type 0xe2), setPart 0x60daecb8 ignores
    # part >= count. Two records: 0x611329f8 (white strip icons 477,478,479,2422,476; 5 parts) and 0x611771d8 (the SCP
    # tile's boxed text labels 5871..5866 = 4:3,3:2,3:4,1:1,16:9,17:9; 6 parts; the one on camera, v0.4c10 photo).
    # v0.4c8-c10 gave 6/7 indices 7/8: index 7 is 17:9 (value 10), so 65:24 showed "17:9" [C v0.4c10]. Since v0.4c11:
    # 6 -> 8, 7 -> 9 (unused), both records -> 8 parts: parts 6 / 7 = 65:24 / 21:9 (record A: strip icons 6668 / 7086,
    # part 5 = 476 filler for 17:9, never offered for stills; record B: tile labels 6669 / 7087, aspect_icons/tile.py).
    # Shared zero u16[8] array. Record A block in the section-3 tail, record B parts + u16 in the section-9 tail.
    SCP_REC, CELL_NEW = 0x611329f8, 0x605d2e00
    PARTS_NEW, IDX_NEW = CELL_NEW, CELL_NEW + 0x80
    TILE_REC, TILE_PARTS, U16_NEW = 0x611771d8, 0x6146cf54, 0x6146cfd4
    assert d[CELL_NEW - B:CELL_NEW + 0xc0 - B] == b'\xff' * 0xc0
    assert d[TILE_PARTS - B:U16_NEW + 16 - B] == b'\xff' * (U16_NEW + 16 - TILE_PARTS)
    assert d[SCP_REC + 0x34 - B:SCP_REC + 0x36 - B] == bytes([2, 5])
    assert d[TILE_REC + 0x34 - B:TILE_REC + 0x36 - B] == bytes([2, 6])
    assert d[SCP_REC - B:SCP_REC + 4 - B] == d[TILE_REC - B:TILE_REC + 4 - B] == bytes.fromhex('0380e200')
    parts_old = struct.unpack_from('<I', d, SCP_REC + 0x38 - B)[0]
    parts = [struct.unpack_from('<4I', d, parts_old + 16 * k - B) for k in range(5)]
    assert [p[:3] for p in parts] == [(0xffff, 7, 7)] * 5 and [p[3] for p in parts] == [477, 478, 479, 2422, 476]
    parts += [(0xffff, 7, 7, 476), (0xffff, 7, 7, ICON_IDS[6][0]), (0xffff, 7, 7, ICON_IDS[7][0])]
    edit(PARTS_NEW, d[PARTS_NEW - B:PARTS_NEW + 0x80 - B], b''.join(struct.pack('<4I', *q) for q in parts),
         'SCP value cell record A parts: stock 5 + 476 (17:9 slot filler) + 65:24 / 21:9 strip icons')
    tparts_old = struct.unpack_from('<I', d, TILE_REC + 0x38 - B)[0]
    tparts = [struct.unpack_from('<4I', d, tparts_old + 16 * k - B) for k in range(6)]
    assert [p[:3] for p in tparts] == [(0xffff, 7, 7)] * 6 and [p[3] for p in tparts] == [5871, 5870, 5869, 5868, 5867, 5866]
    tparts += [(0xffff, 7, 7, 6669), (0xffff, 7, 7, 7087)]
    edit(TILE_PARTS, d[TILE_PARTS - B:TILE_PARTS + 0x80 - B], b''.join(struct.pack('<4I', *q) for q in tparts),
         'SCP tile record B parts: stock 6 + 65:24 / 21:9 tile labels')
    edit(U16_NEW, d[U16_NEW - B:U16_NEW + 16 - B], bytes(16), 'SCP tile records u16[8] (zeros, as stock; shared)')
    idx_rows = None
    for site, lst in ((0x60e6a0ed, 0x612413f4), (0x60e70c24, 0x612449d0)):
        assert d[site - B:site + 8 - B] == b'\xfc\xdd' + struct.pack('<I', lst) + b'\x85\x06', hex(site)
        rows = [struct.unpack_from('<II', d, lst + 8 * k - B) for k in range(6)]
        assert rows == [(1, 2), (3, 6), (2, 3), (4, 5), (9, 4), (10, 7)], rows
        idx_rows = rows + [(6, 8), (7, 9)]
        edit(site + 2, d[site + 2 - B:site + 8 - B], struct.pack('<I', IDX_NEW) + b'\x85\x08', f'SCP value cell builder {site:#x}: list -> {IDX_NEW:#x}, 6 -> 8 entries')
    edit(IDX_NEW, d[IDX_NEW - B:IDX_NEW + 64 - B], b''.join(struct.pack('<II', *r) for r in idx_rows), 'SCP value cell index list (stock + 6 -> 8, 7 -> 9)')
    for rec, pa, what in ((SCP_REC, PARTS_NEW, 'A'), (TILE_REC, TILE_PARTS, 'B')):
        edit(rec + 0x34, d[rec + 0x34 - B:rec + 0x40 - B], bytes([2, 8]) + d[rec + 0x36 - B:rec + 0x38 - B] + struct.pack('<II', pa, U16_NEW),
             f'SCP tile widget record {what} {rec:#x}: count -> 8, parts / u16 array -> new block')

    # 17. AF / AE display lookups (port of E-P7 aspect_fix t1: sv, ag1/ag2, mt + the E-M1 II selector layout chains).
    # Stubs in af.s (6/7 -> 3 in a register only, no stores), assembled at AF_AT in the section-3 FF tail after §16.
    AF_AT, AF_END = 0x605d2ec0, 0x605d3000
    HOOKS = {0x60ea25e2: ('5d0804f80904', 'sv'), 0x60e5f5d7: ('0408fa0ff800', 'ag1'), 0x60e5f823: ('0408fa0ff800', 'ag2'),
             0x60e99d28: ('95000858 28'.replace(' ', ''), 'mt'), 0x60e3be27: ('5838a009c94c', 'ch1'), 0x60e3c9d7: ('5834a009c94c', 'ch2'),
             0x60d76dc9: ('811da500c906', 'gt')}   # bitmap getter (v0.4c9): icons 6668 / 7086 from main-image entries
    code, syms = assemble_af(AF_AT)
    assert AF_AT + len(code) <= AF_END, f'af stubs {len(code)} B'
    assert d[AF_AT - B:AF_AT + len(code) - B] == b'\xff' * len(code)
    edit(AF_AT, d[AF_AT - B:AF_AT + len(code) - B], code, f'AF/AE display stubs sv/ag1/ag2/mt/ch1/ch2 + bitmap getter gt ({len(code)} B)')
    for site, (old, sym) in HOOKS.items():
        old = bytes.fromhex(old)
        assert d[site - B:site + len(old) - B] == old, (hex(site), d[site - B:site + len(old) - B].hex())
        new = b'\xdc' + struct.pack('<i', syms[sym] - site) + b'\xcb' * (len(old) - 5)
        edit(site, old, new, f'{"bitmap getter" if sym == "gt" else "AF/AE"} hook {sym}: jmp {syms[sym]:#x}')

    # 15. Image Aspect detail screen (OK on the menu row): screen record 0x612abd20 (64-B table, ref 0x60efa4f4).
    # Its draw function 0x60efa603 resolves the selected value through 0x60e59f78 with count = u16 record+2 (6) in the
    # label list +28 (box text: 1,2,3,4,9,10) and the size-text lists +32 RAW, +36 Large, +52 50M, +56 25M, and through
    # the size-class table +44 (7 x {class, list}) for Middle/Small. No list had 6/7: empty box, blank sizes (camera
    # v0.4c3). All 12 lists copied as 8-row lists with 6/7 (sizes from the pixel table below), count 6 -> 8.
    # Placed in the section-4 FF tail (0x6078e8c0..0x6078f000), free while debug_log is out of the builds.
    SCR, SCR_NEW, SCR_END = 0x612abd20, 0x6078e8c0, 0x6078f000
    assert struct.unpack_from('<HH', d, SCR - B) == (0, 6)
    assert d[SCR_NEW - B:SCR_END - B] == b'\xff' * (SCR_END - SCR_NEW)
    size_by_key = {key: (w, h6, h7) for key, w, h6, h7 in stock_pix_rows}
    NOMATCH = (0xffffffff, 0, 0, 0)
    lists_blob, text_blob = bytearray(), bytearray()
    lists_size = 12 * 8 * 12
    text_at = SCR_NEW + lists_size

    def text_ptr(t):
        nonlocal text_blob
        a = text_at + len(text_blob)
        text_blob += t.encode() + b'\0'
        return a

    def put_list(rows):
        a = SCR_NEW + len(lists_blob)
        assert len(rows) == 8
        for r in rows:
            lists_blob.extend(struct.pack('<IHHI', *r))
        return a

    def stock_rows(p, n):
        return [struct.unpack_from('<IHHI', d, p + 12 * k - B) for k in range(n)]

    # label list +28
    old28 = struct.unpack_from('<I', d, SCR + 28 - B)[0]
    rows = stock_rows(old28, 6)
    assert [r[0] for r in rows] == [1, 2, 3, 4, 9, 10]
    new28 = put_list(rows + [(6, 5, 0, SHORT_TEXT_ADDR[6]), (7, 5, 0, SHORT_TEXT_ADDR[7])])
    edit(SCR + 28, d[SCR + 28 - B:SCR + 32 - B], struct.pack('<I', new28), 'detail screen label list -> 8 rows (65:24, 21:9)')

    def size_list(old, key):
        rows = stock_rows(old, 5)
        assert [r[0] for r in rows] == [1, 2, 3, 4, 9] and all(r[1] == 5 for r in rows), f'size list {old:#x}'
        if key is None:      # RAW: the full sensor for every aspect (stock: 5184x3888 for all)
            extra = [(6, 5, 0, rows[0][3]), (7, 5, 0, rows[0][3])]
        else:
            w, h6, h7 = size_by_key[key]
            extra = [(6, 5, 0, text_ptr(f'{w}x{h6}')), (7, 5, 0, text_ptr(f'{w}x{h7}'))]
        return put_list(rows + extra + [NOMATCH])

    for off, key, name in ((32, None, 'RAW'), (36, 0, 'Large'), (52, 20, '50M'), (56, 21, '25M')):
        old = struct.unpack_from('<I', d, SCR + off - B)[0]
        new = size_list(old, key)
        edit(SCR + off, d[SCR + off - B:SCR + off + 4 - B], struct.pack('<I', new), f'detail screen {name} size list -> 8 rows')
    cls_tab = struct.unpack_from('<I', d, SCR + 44 - B)[0]
    for k in range(7):
        key, old = struct.unpack_from('<II', d, cls_tab + 8 * k - B)
        new = size_list(old, key)
        a = cls_tab + 8 * k + 4
        edit(a, d[a - B:a + 4 - B], struct.pack('<I', new), f'detail screen class {key} size list -> 8 rows')
    assert len(lists_blob) == lists_size
    blob = bytes(lists_blob + text_blob)
    assert SCR_NEW + len(blob) <= SCR_END
    edit(SCR_NEW, d[SCR_NEW - B:SCR_NEW + len(blob) - B], blob, f'detail screen lists + size text ({len(blob)} B)')
    edit(SCR + 2, d[SCR + 2 - B:SCR + 4 - B], struct.pack('<H', 8), 'detail screen list count 6 -> 8')

    print(f"Total edits generated: {len(edits)}")
    return edits


def main():
    edits = build_edits()
    spec = {
        "camera": "em1mk2",
        "description": "Aspect ratio mod: X-Pan 65:24 (id 6) and 21:9 (id 7)",
        "edits": edits
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(spec, indent=2))
    print(f"Wrote {len(edits)} edits to {OUT_PATH}")


if __name__ == "__main__":
    main()
