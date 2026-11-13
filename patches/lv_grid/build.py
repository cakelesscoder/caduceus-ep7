#!/usr/bin/env python3
"""Framing grid in live view, data only (docs/SPLIT_TONE_G1.md §2, docs/ASPECT.md §7.3). Offline.

  .venv/bin/python -I patches/lv_grid/build.py SPEC.json --out OUT.json [--previews DIR]

The LV grid selector 0x60e32406 picks a display-class table (0x6118cc00 / cc48 / cc90, 6 rows {aspect, list, count},
`mov 6,a0` at 0x60e326c3), then a {grid value, bitmap} pair from the row's list, and draws that OSD bitmap. Its aspect
is 1 or 3 in movie and GetValue(270) for stills, never 10, so row 5 (aspect 10, 17:9) is dead in it.

  A  XPan stills grid: row 5 aspect 10 -> 6 in all three tables; that row's list (0x6118c8e0 / c9d0 / cb10, read only
     through these rows) gets one new bitmap per class for all five grid values: frame lines at the 65:24 band and the
     rule of thirds inside it. Same size as the class's stock 16:9 thirds bitmap (6018 / 6108 / 6052), so it draws where
     the 16:9 grid does.
  B  Frame lines (ASPECT §7.3): in each class's 16:9 list, grid value 8 (diagonal) -> a new bitmap with full-width
     65:24 lines (solid) and 21:9 lines (dashed), same size as the stock diagonal (5998 / 6084 / 6028). Movie always uses
     aspect 3 or 1 here, so movie gets these too (aspect 3).
Switch: the stock Displayed Grid (sid 155 / 447). Off = stock. Stock draws it only in shooting live view.
OSD, in place (the camera-proven aspect_icons method; no directory, bitmap table or bank change): the six images go
into six 17:9 grid bitmaps of the dead row-5 lists (each referenced in main only by those lists), descriptor size and
encoded length rewritten. 17:9 is a movie aspect that this selector never sees (movie forces 3 or 1).
Main: 3 + 15 + 3 = 21 u32 data words. No code.
"""
import argparse, copy, json, struct, sys, tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'patches/aspect'))
import osd_extract as X  # noqa: E402
import osd_icons as OI  # noqa: E402

BASE, SRC = 0x60020020, 'patches/lv_grid'
STOCK = ROOT / 'analysis/ep7_1100/00_0100_406a0020.decoded.bin'
TABLES = (0x6118cc00, 0x6118cc48, 0x6118cc90)
ROW5 = 60                                  # row 5 offset
LISTS_169 = (0x6118c868, 0x6118c958, 0x6118ca98)
LISTS_179 = (0x6118c8e0, 0x6118c9d0, 0x6118cb10)
THIRDS = (6018, 6108, 6052)                # stock 16:9 value-1 bitmaps (size of A)
DIAG = (5998, 6084, 6028)                  # stock 16:9 value-8 bitmaps (size of B)
INK = 124
XPAN, W219 = (16 / 9) / (65 / 24), (16 / 9) / (21 / 9)   # band height / 16:9 height
COUNT_SITE = 0x60e326c3                    # mov 6,a0 (stays)


def line_at(n, f):
    """Stock rule: a 2-px line at round(n f) - 2 .. - 1 (6018 thirds: 131/132, 266/267 of 399)."""
    return int(round(n * f)) - 2


def img_xpan(w, h):
    a = np.zeros((h, w), np.uint8)
    hb = h * XPAN
    y0 = (h - hb) / 2
    top, bot = int(round(y0)), int(round(y0 + hb)) - 2
    a[top:top + 2, :] = INK
    a[bot:bot + 2, :] = INK
    for k in (1, 2):
        y = int(round(y0 + hb * k / 3)) - 1
        a[y:y + 2, :] = INK
        x = line_at(w, k / 3)
        a[top:bot + 2, x:x + 2] = INK
    return a


def img_frames(w, h):
    a = np.zeros((h, w), np.uint8)
    for f, dashed in ((XPAN, False), (W219, True)):
        hb = h * f
        for y in (int(round((h - hb) / 2)), int(round((h + hb) / 2)) - 2):
            if dashed:
                for x in range(0, w, 24):
                    a[y:y + 2, x:x + 12] = INK
            else:
                a[y:y + 2, :] = INK
    return a


HOST = {'xpan0': 6105, 'xpan1': 6099, 'xpan2': 6031, 'frames0': 6001, 'frames1': 6087, 'frames2': 6007}


def o3(o, ids):
    """The host ids: no type-3 entry, no u32 in the sec-6 UI data except the three dead lists, no `mov imm16` in the UI code
    0x60d00000-0x60f00000 (the aspect build's check O3)."""
    m = o.main
    a8 = np.frombuffer(m, np.uint8).astype(np.int64)
    u16 = np.frombuffer(m[:len(m) // 2 * 2], '<u2')
    u32 = np.frombuffer(m[:len(m) // 4 * 4], '<u4')
    p32 = np.arange(len(u32)) * 4 + BASE
    p8 = np.arange(len(a8) - 2) + BASE
    isop = np.isin(a8[:-2], list(range(0x24, 0x28)) + list(range(0x2c, 0x30))) & (p8 >= 0x60d00000) & (p8 < 0x60f00000)
    mvv = set(((a8[1:-1] | (a8[2:] << 8))[isop]).tolist())
    dead = [(l, l + 40) for l in LISTS_179]
    for i in ids:
        k = np.nonzero(u16 == i)[0]
        ui = [int(p) for p in p32[(u32 == i) & (p32 >= 0x61100000) & (p32 < 0x61243000)] if not any(lo <= p < hi for lo, hi in dead)]
        if any(x > 0 and u16[x - 1] == 3 for x in k) or ui or i in mvv:
            raise SystemExit(f'host bitmap {i} has another reference ({ui})')


def apply(spec, previews=None):
    spec = copy.deepcopy(spec)
    if 'lv_grid' in spec:
        raise SystemExit('lv_grid already applied')
    stock = STOCK.read_bytes()
    so = X.OSD()
    oed = [e for e in spec['edits'] if e['kind'] == '0x101']
    cur = OI.apply_osd(so.data, oed)
    with tempfile.NamedTemporaryFile(suffix='.bin') as f:
        f.write(cur)
        f.flush()
        o = X.OSD(component=f.name, check_hash=False)
    # main data: stock words, untouched so far
    words = {}
    for t in TABLES:
        words[t + ROW5] = (10, 6)
    m = {}
    for e in spec['edits']:
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            a, n = int(e['addr'], 16), len(e['new']) // 2
            if a < 0x6118cd20 and 0x6118c818 < a + n:
                raise SystemExit(f'grid tables already edited by {e["addr"]}')
    for t, l in zip(TABLES, LISTS_179):
        if struct.unpack_from('<3I', stock, t + ROW5 - BASE) != (10, l, 5):
            raise SystemExit(f'row 5 of {t:#x} is not {{10, {l:#x}, 5}}')
    for l, d in zip(LISTS_169, DIAG):
        if struct.unpack_from('<2I', stock, l - BASE) != (8, d):
            raise SystemExit(f'{l:#x} entry 0 is not {{8, {d}}}')
    if stock[COUNT_SITE - BASE:COUNT_SITE + 2 - BASE] != bytes.fromhex('9006'):
        raise SystemExit('row count differs')
    # images
    imgs = []
    for k in range(3):
        r = o.descriptor(THIRDS[k])
        imgs.append((f'xpan{k}', img_xpan(r['width'], r['height'])))
    for k in range(3):
        r = o.descriptor(DIAG[k])
        imgs.append((f'frames{k}', img_frames(r['width'], r['height'])))
    # OSD, in place (the aspect_icons / aspect_scp method, camera-proven; no directory, table or bank change): the 17:9
    # grid bitmaps of the dead row-5 lists, each referenced in main only by those lists (check O3 below)
    add, info = [], {}
    used = set()
    for e in oed:
        a0 = int(e['addr'][4:], 16)
        used.update(range(a0, a0 + len(e['new']) // 2))
    for key, a in imgs:
        i = HOST[key]
        r = o.descriptor(i)
        h, w = a.shape
        st = OI.encode(a.tobytes(), w, h)
        px, *_ = X.decode_rle(st, w, h)
        cap = r['encoded_bytes']
        if not (px == a.tobytes() and r['kind'] == 'rle' and r['fmt'] == 14 and r['field6'] == 8 and len(st) <= cap):
            raise SystemExit(f'{key}: host {i} {r["kind"]} {len(st)}/{cap} B')
        po, dp = r['payload_offset'], r['descriptor_offset']
        if used & set(range(po, po + cap)) or used & set(range(dp, dp + 24)):
            raise SystemExit(f'{key}: host {i} already edited')
        add.append(dict(kind='0x101', addr=f'off:{po:#x}', expect=o.data[po:po + cap].hex(), new=(st + bytes(cap - len(st))).hex(), source=SRC,
                        why=f'lv_grid: bitmap {i} (17:9 LV grid, dead list) -> {key} {w}x{h}, in place, {len(st)}/{cap} B'))
        add.append(dict(kind='0x101', addr=f'off:{dp + 2:#x}', expect=o.data[dp + 2:dp + 6].hex(), new=struct.pack('<HH', w, h).hex(), source=SRC,
                        why=f'lv_grid: bitmap {i} descriptor {r["width"]}x{r["height"]} -> {w}x{h}'))
        add.append(dict(kind='0x101', addr=f'off:{dp + 12:#x}', expect=o.data[dp + 12:dp + 16].hex(), new=struct.pack('<I', len(st)).hex(), source=SRC,
                        why=f'lv_grid: bitmap {i} descriptor encoded size {cap} -> {len(st)}'))
        info[key] = (i, dp, len(st), w, h, cap)
    o3(o, set(HOST.values()))
    # main data words
    def put(a, old, new, why):
        add.append(dict(kind='0x100', addr=hex(a), expect=struct.pack('<I', old).hex(), new=struct.pack('<I', new).hex(), source=SRC, why=why))
    for k, t in enumerate(TABLES):
        put(t + ROW5, 10, 6, f'lv_grid A: LV grid table {t:#x} row 5 aspect 10 (17:9, unreachable here) -> 6 (Panorama/XPan)')
        l = LISTS_179[k]
        for j in range(5):
            old = struct.unpack_from('<I', stock, l + 8 * j + 4 - BASE)[0]
            put(l + 8 * j + 4, old, info[f'xpan{k}'][0], f'lv_grid A: list {l:#x} entry {j} bitmap {old} -> XPan thirds {info[f"xpan{k}"][0]}')
        put(LISTS_169[k] + 4, DIAG[k], info[f'frames{k}'][0], f'lv_grid B: 16:9 list {LISTS_169[k]:#x} diagonal {DIAG[k]} -> 65:24 + 21:9 frame lines {info[f"frames{k}"][0]}')
    spec['edits'] += add
    spec['lv_grid'] = dict(built_by=SRC, ids={k: v[0] for k, v in info.items()}, method='in place (17:9 grid bitmaps of the dead lists)',
                           sizes={k: [v[3], v[4], v[2], v[5]] for k, v in info.items()})
    if previews:
        from PIL import Image
        previews.mkdir(parents=True, exist_ok=True)
        for key, a in imgs:
            Image.fromarray(np.where(a > 0, 255, 40).astype(np.uint8)).save(previews / f'{key}.png')
    return spec


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--previews', type=Path)
    a = ap.parse_args()
    spec = apply(json.loads(a.spec.read_text()), a.previews)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(spec, indent=1))
    print(json.dumps(spec['lv_grid']))
