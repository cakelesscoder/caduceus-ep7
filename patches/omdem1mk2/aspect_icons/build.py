#!/usr/bin/env python3
"""E-M1 Mark II: "65:24" and "21:9" aspect icons in the stock aspect-icon style (OSD component 0x101).

    python3 patches/omdem1mk2/aspect_icons/build.py [--previews DIR]

Reuses the E-P7 library patches/aspect/osd_icons.py (decoder via tools/osd_extract.py, byte-exact mode-11 encoder,
glyph extraction, label-free box). The E-M1 II OSD has the same aspect icons and ids as the E-P7 (white 50x38: 477
4:3, 476 16:9, 478 3:2, 2422 1:1, 479 3:4; green 64x48: 472/471/473/2421/475), fmt 14 / 8-bit [V].
  * 21:9  = osd_icons.make_219 (stock '2' of 3:2 + '1' ':' '9' of 16:9, 16:9 spacing).
  * 65:24 = stock '6' and ':' (16:9), '2' (3:2), '4' (4:3) + a '5' rendered from DejaVu Sans Condensed Bold at the stock
            digit band and the width of the stock '6', quantised to the icon's own indices. Spacing = the 16:9 gaps,
            tightened if the label would leave the stock label span.
Placement (v0.4c6, docs/OMD-EM1-II/ASPECT.md §6.3): the white icons' streams and descriptors go into free 0xFF space of
always-loaded main-image sections (0x100), and only two bitmap-table entries in OSD bank 0 change (0x101). The v0.4c5
route (append after OSD resource 69, RAM 0xa3b0e400..) drew blank in the SCP on camera. Bank 69 itself is a resident
bitmap bank (3095 stock table entries point into it); the likely cause is that RAM after it, assumed free, is used at
runtime [I]. Static main-image data avoids the question.
"""
import argparse, os, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'patches/aspect'))
import osd_extract as X  # noqa: E402

OSD_FILE = ROOT / 'em1mk2/extracted/01_0101_42060020.decoded.bin'
MAIN_FILE = ROOT / 'em1mk2/extracted/00_0100_40560020.decoded.bin'
X.COMPONENT_ADDR = 0x42060020
X.MAIN_BASE = 0x60021020
import osd_icons as I  # noqa: E402  (after the E-M1 constants are set)

FONT5 = '/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf'


def load():
    o = X.OSD(OSD_FILE, MAIN_FILE, check_hash=False)
    pals = o.palettes()
    X.DEFAULT_PALETTE8 = pals[0]['address']        # white 4 / grey 5, 6 / black 16 ramp (checked by eye in the previews)
    return o


def glyphs_of(o, kind, icon):
    a = I.bitmap(o, icon)
    m = I.glyph_mask(a, kind)
    return a, m, I.segments(m)


def render_digit(o, kind, ch, width, pal):
    """One font-rendered glyph, cap band = stock digit band, given width; returns (index array, mask) at the band."""
    from PIL import Image, ImageDraw, ImageFont
    s = I.SRC[kind]
    ref = I.bitmap(o, s['box'])
    rm = I.glyph_mask(ref, kind)
    rows = np.nonzero(rm.any(1))[0]
    cy0, cy1 = int(rows[0]), int(rows[-1]) + 1
    SS = 8
    f = ImageFont.truetype(FONT5, size=int((cy1 - cy0) * SS / 0.729))   # DejaVu cap height ~0.729 em
    l, t, r, b = f.getbbox(ch)
    im = Image.new('L', (r - l + 4 * SS, b - t + 4 * SS), 0)
    ImageDraw.Draw(im).text((2 * SS - l, 2 * SS - t), ch, font=f, fill=255)
    im = im.crop(im.getbbox()).resize((width * SS, (cy1 - cy0) * SS), Image.LANCZOS).resize((width, cy1 - cy0), Image.BOX)
    return np.asarray(im, float) / 255, cy0


def make_6524(o, kind, pal):
    s = I.SRC[kind]
    box = I.clean_box(o, kind)
    a169, m169, g169 = glyphs_of(o, kind, s['box'])          # 1 6 : 9
    a32, m32, g32 = glyphs_of(o, kind, s['three'])           # 3 : 2
    a43, m43, g43 = glyphs_of(o, kind, {'white': 477, 'green': 472}[kind])   # 4 : 3
    assert len(g169) == 4 and len(g32) == 3 and len(g43) == 3, (g169, g32, g43)
    six = (a169, m169, g169[1])
    w5 = g169[1][1] - g169[1][0]
    cov5, cy0 = render_digit(o, kind, '5', w5, pal)
    parts = [six, ('5', cov5, cy0), (a169, m169, g169[2]), (a32, m32, g32[2]), (a43, m43, g43[0])]   # 6 5 : 2 4
    gaps169 = [g169[k + 1][0] - g169[k][1] for k in range(3)]
    gap_d, gap_c = gaps169[0], gaps169[1]                    # digit-digit gap, digit-colon gap
    widths = [w5 if isinstance(p[0], str) else p[2][1] - p[2][0] for p in parts]
    gaps = [gap_d, gap_c, gap_c, gap_d]
    span = (s['x1'] - 2) - (s['x0'] + 2)
    black, aa = pal[16], [i for i in s['text'] if i != 16]
    H = box.shape[0]
    # 1. compose the label at stock size as a coverage map (0 = row background, 1 = text black)
    total = sum(widths) + sum(gaps)
    cov = np.zeros((H, total))
    x = 0
    for k, p in enumerate(parts):
        if isinstance(p[0], str):
            c5, y0 = p[1], p[2]
            cov[y0:y0 + c5.shape[0], x:x + c5.shape[1]] = c5
            x += c5.shape[1]
        else:
            a, m, (b, e) = p
            for y, xx in zip(*np.nonzero(m[:, b:e])):
                bg = pal[box[y, min(max(b + xx, 0), box.shape[1] - 1)]]
                d = ((black - bg) ** 2).sum()
                cov[y, x + xx] = 1.0 if d == 0 else float(np.clip(((pal[a[y, b + xx]] - bg) * (black - bg)).sum() / d, 0, 1))
            x += e - b
        if k < len(gaps):
            x += gaps[k]
    # 2. squeeze horizontally to the stock label span (box filter), only if needed
    if total > span:
        from PIL import Image
        im = Image.fromarray((cov * 255).astype(np.uint8), 'L').resize((span, H), Image.BOX)
        cov = np.asarray(im, float) / 255
    # 3. quantise onto the label-free box with the icon's own indices
    c169 = (g169[0][0] + g169[-1][1]) / 2
    x0 = int(round(c169 - cov.shape[1] / 2))
    out = box.copy()
    for y in range(H):
        for xx in range(cov.shape[1]):
            c = cov[y, xx]
            if c < 0.12:
                continue
            bgi = box[y, x0 + xx]
            want = pal[bgi] * (1 - c) + black * c
            out[y, x0 + xx] = min([bgi, 16] + aa, key=lambda i: ((pal[i] - want) ** 2).sum())
    return out


def build_images(o):
    pal = I.palette(o)
    return {('6524', k): make_6524(o, k, pal) for k in ('white', 'green')} | \
           {('219', k): I.make_219(o, k) for k in ('white', 'green')}


def save_previews(o, imgs, out, scale=8):
    from PIL import Image
    pal = I.palette(o).astype(np.uint8)
    out.mkdir(parents=True, exist_ok=True)
    stock = {('stock169', 'white'): I.bitmap(o, 476), ('stock169', 'green'): I.bitmap(o, 471)}
    for (name, kind), a in (stock | imgs).items():
        rgb = pal[a]
        Image.fromarray(rgb, 'RGB').resize((a.shape[1] * scale, a.shape[0] * scale), Image.NEAREST).save(out / f'{name}_{kind}.png')
    # one sheet: stock 16:9, 65:24, 21:9 for each kind
    rows = []
    for kind in ('white', 'green'):
        tiles = [pal[x] for x in (stock[('stock169', kind)], imgs[('6524', kind)], imgs[('219', kind)])]
        h = max(t.shape[0] for t in tiles)
        rows.append(np.concatenate([np.pad(t, ((0, h - t.shape[0]), (0, 4), (0, 0))) for t in tiles], 1))
    w = max(r.shape[1] for r in rows)
    sheet = np.concatenate([np.pad(r, ((0, 4), (0, w - r.shape[1]), (0, 0))) for r in rows], 0)
    Image.fromarray(sheet.astype(np.uint8), 'RGB').resize((sheet.shape[1] * scale, sheet.shape[0] * scale), Image.NEAREST).save(out / 'sheet.png')
    return out / 'sheet.png'


# New bitmap ids: fmt-1 placeholders with no type-3 option entry, no u32 in the section-6 UI data and no 16-bit
# immediate load in the GUI code 0x60c00000..0x61000000 (214 such ids on this body). Not provably unused [I]: ids can
# be computed. The aspect patch (patches/omdem1mk2/aspect/build.py ICON_IDS) points the 6/7 icon entries at these.
NEW_IDS = {('6524', 'white'): 6668, ('6524', 'green'): 6669, ('219', 'white'): 7086, ('219', 'green'): 7087}
OUT = Path(__file__).resolve().parent / 'edits.json'


# Free 0xFF space in loaded, never-written sections (checked on the v0.4c5 image; omdem1mk2_check_loaded.py rechecks):
#   section 3 tail 0x605d2a6c..0x605d3000 (1428 B; docs/OMD-EM1-II/ARCHITECTURE_AND_MEMORY_MAP.md §6),
#   section 1 linker padding 0x60256ce8..0x60256ff0 (776 B, before the aligned function 0x60256ff0; code/rodata section).
# Pointers: v0.4c6 used cached 0x60.. addresses and drew blank [C]. Every stock descriptor/payload pointer is uncached
# (0xa2../0xa3..); if the graphics path converts by subtracting a base, a cached pointer is garbage. Since v0.4c7 the
# uncached alias (+0x40000000, 0x60.. -> 0xa0..; mapped: stock code passes 0xa0b5ed8d = 0x60b5ed8d at 0x60107df4).
# EM1_ICON_CACHED=1 restores the c6 pointers.
# EM1_ICON_DIAG=1 (v0.4c7 diagnostic): id 7086 (21:9) -> the stock 16:9 white descriptor instead of the new icon, to
# show on camera whether OSD bitmap-table edits take effect at all (16:9 in the 21:9 cell = yes, blank = no).
PLACE = {('6524', 'white'): 0x605d2a6c, ('219', 'white'): 0x60256cf0}
DESC_AT = 0x605d2d9c                     # two 24-B descriptors after the 65:24 stream (section 3 tail)
FREE = [(0x605d2a6c, 0x605d2e00), (0x60256ce8, 0x60256ff0)]   # 0x605d2e00.. = aspect/build.py §16 (SCP value cell)
UNC = 0 if os.environ.get('EM1_ICON_CACHED') == '1' else 0x40000000
DIAG = os.environ.get('EM1_ICON_DIAG') == '1'
# Route (v0.4c9): OSD bitmap-table edits never showed any effect on this body (c5-c8 blank, including c7's 21:9 entry on
# the stock 16:9 descriptor). Default 'hook': no 0x101 edits; two entry words after the descriptors, returned for ids
# 6668 / 7086 by the bitmap-getter hook (aspect/build.py ICON_ENTRY, af.s gt). EM1_ICON_ROUTE=osd = the c6-c8 table edits.
ROUTE = os.environ.get('EM1_ICON_ROUTE', 'hook')
ENTRY_AT = 0x605d2dcc                    # u32 entry per id (6668, 7086, 6669, 7087), = aspect/build.py ICON_ENTRY
# SCP tile labels (v0.4c11, tile.py): 106x31-style boxed text for widget record 0x611771d8, cropped to the box (the tile
# widget aligns its bitmap; record flags 01 01). Free space is short, so 65:24 drops the lightest AA level (24 -> box).
TILE_IDS = {'6524': 6669, '219': 7087}   # fmt-1 placeholders (the green ids, unused since v0.4c6)
TILE_PLACE = {'6524': 0x613ecd9c, '219': 0x6078edfc}   # section 7 tail (612 B), section 4 tail (516 B)
TILE_DESC = {'6524': 0x60256f98, '219': 0x60bc87d0}    # section 1 padding / section 5 tail, 24 B each
TILE_FREE = [(0x613ecd9c, 0x613ed000), (0x6078edfc, 0x6078f000), (0x60256f98, 0x60256ff0), (0x60bc87d0, 0x60bc8800)]
TILE_AA = {'6524': {24: 22}, '219': {}}


def osd_edits(o, imgs):
    """White 65:24 / 21:9 streams + descriptors in main-image free space; bitmap-table entries of ids 6668 / 7086
    (fmt-1 placeholders) -> those descriptors. The selected (green) lists use the same white ids (aspect/build.py)."""
    import struct
    main = Path(MAIN_FILE).read_bytes()
    MB = X.MAIN_BASE
    edits, info, used = [], {}, []
    for n, key in enumerate((('6524', 'white'), ('219', 'white'))):
        a = imgs[key].astype(np.uint8)
        h, w = a.shape
        st = I.encode(a.ravel().tolist(), w, h)
        px, *_ = X.decode_rle(st, w, h)
        assert px == a.tobytes(), key
        pay, desc = PLACE[key], DESC_AT + 24 * n
        dblob = struct.pack('<6H3I', 14, w, h, 8, 0, 0, len(st), pay + UNC, 0)
        for addr, blob, what in ((pay, st, 'stream'), (desc, dblob, 'descriptor')):
            assert addr % 4 == 0 and any(lo <= addr and addr + len(blob) <= hi for lo, hi in FREE), (key, what, hex(addr))
            assert all(addr + len(blob) <= u0 or addr >= u1 for u0, u1 in used), (key, what, 'overlap')
            old = main[addr - MB:addr - MB + len(blob)]
            assert old == b'\xff' * len(blob), (key, what, 'not free')
            used.append((addr, addr + len(blob)))
            edits.append(dict(kind='0x100', addr=f'{addr:#x}', expect=old.hex(), new=blob.hex(),
                              why=f'aspect icon {key[0]} {key[1]} {w}x{h} {what} ({len(blob)} B, free 0xFF space)'))
        i = NEW_IDS[key]
        if ROUTE == 'hook':
            if DIAG and key[0] == '219':
                desc = o.descriptor(476)['descriptor'] - UNC
                edits = [e for e in edits if '219' not in e['why']]
            ent, eb = ENTRY_AT + 4 * n, struct.pack('<I', desc + UNC)
            assert main[ent - MB:ent - MB + 4] == b'\xff' * 4 and any(lo <= ent and ent + 4 <= hi for lo, hi in FREE)
            edits.append(dict(kind='0x100', addr=f'{ent:#x}', expect='ff' * 4, new=eb.hex(),
                              why=f'bitmap entry for id {i} (returned by the getter hook gt) -> ' +
                                  (f'stock 16:9 descriptor {desc + UNC:#x} (DIAG)' if DIAG and key[0] == '219'
                                   else f'{key[0]} {key[1]} descriptor {desc + UNC:#x}')))
            info[key] = (i, desc + UNC, pay + UNC, len(st))
            continue
        if DIAG and key[0] == '219':
            desc = o.descriptor(476)['descriptor'] - UNC     # stock 16:9 white (already an uncached 0xa2.. address)
            edits = [e for e in edits if '219' not in e['why']]
        row = o.descriptor(i)
        assert row['kind'] == 'placeholder', (i, row)
        tab = o.bitmap_table - o.base0 + o.resources[0]['offset']
        off = tab + 4 * i
        old = o.data[off:off + 4]
        assert struct.unpack('<I', old)[0] == row['descriptor']
        edits.append(dict(kind='0x101', addr=f'off:{off:#x}', expect=bytes(old).hex(), new=struct.pack('<I', desc + UNC).hex(),
                          why=f'bitmap table id {i} (placeholder) -> ' + (f'stock 16:9 descriptor {desc + UNC:#x} (DIAG)' if DIAG and key[0] == '219'
                              else f'{key[0]} {key[1]} descriptor {desc + UNC:#x} (main image)')))
        info[key] = (i, desc + UNC, pay + UNC, len(st))
    if ROUTE == 'hook':
        edits += tile_edits(o, main, info)
    return edits, info


def tile_labels(o):
    import tile as T
    out = {}
    for w in ('6524', '219'):
        a = T.compose(o, I.bitmap, w)
        for k, v in TILE_AA[w].items():
            a[a == k] = v
        cols, rows = np.nonzero((a != 0).any(0))[0], np.nonzero((a != 0).any(1))[0]
        out[w] = a[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1].copy()
    return out


def tile_edits(o, main, info):
    import struct
    MB = X.MAIN_BASE
    edits = []
    for n, (w, a) in enumerate(tile_labels(o).items()):
        h, wd = a.shape
        st = I.encode(a.ravel().tolist(), wd, h)
        px, *_ = X.decode_rle(st, wd, h)
        assert px == a.tobytes(), w
        pay, desc = TILE_PLACE[w], TILE_DESC[w]
        dblob = struct.pack('<6H3I', 14, wd, h, 8, 0, 0, len(st), pay + UNC, 7)     # colour key 7 = stock tile labels
        ent, eb = ENTRY_AT + 8 + 4 * n, struct.pack('<I', desc + UNC)
        for addr, blob, what, free in ((pay, st, 'stream', TILE_FREE), (desc, dblob, 'descriptor', TILE_FREE),
                                       (ent, eb, 'entry', FREE)):
            assert addr % 4 == 0 and any(lo <= addr and addr + len(blob) <= hi for lo, hi in free), (w, what, hex(addr), len(blob))
            old = main[addr - MB:addr - MB + len(blob)]
            assert old == b'\xff' * len(blob), (w, what, 'not free')
            edits.append(dict(kind='0x100', addr=f'{addr:#x}', expect=old.hex(), new=blob.hex(),
                              why=f'SCP tile label {w} {wd}x{h} {what} ({len(blob)} B)' + (f' for id {TILE_IDS[w]}' if what == 'entry' else '')))
        info[('tile', w)] = (TILE_IDS[w], desc + UNC, pay + UNC, len(st))
    return edits


def main():
    import json
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--previews', type=Path, default=ROOT / 'generated/em1mk2_aspect_icons')
    a = p.parse_args()
    o = load()
    imgs = build_images(o)
    for (name, kind), arr in imgs.items():
        stream = I.encode(arr.ravel().tolist(), arr.shape[1], arr.shape[0])
        print(f'{name:5s} {kind:5s} {arr.shape[1]}x{arr.shape[0]}  mode-11 stream {len(stream)} B')
    print('previews:', save_previews(o, imgs, a.previews))
    edits, info = osd_edits(o, imgs)
    OUT.write_text(json.dumps({'patch': 'aspect_icons', 'components': ['0x100'] if ROUTE == 'hook' else ['0x100', '0x101'],
                               'edits': edits}, indent=2) + '\n')
    for k, (i, desc, pay, n) in info.items():
        print(f'  id {i}: {k} descriptor {desc:#x} payload {pay:#x} ({n} B)')
    print(f'Wrote {len(edits)} edits (main + OSD) to {OUT}')


if __name__ == '__main__':
    main()
