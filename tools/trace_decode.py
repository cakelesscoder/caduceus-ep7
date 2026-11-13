#!/usr/bin/env python3
"""Decode an EP7MOD/TRACE.TXT dump from the Caduceus diag layer (docs/PLUGINS.md §13).

The diag layer (patches/diag) keeps a 16 KB ring log of raw key-event records and editor paints, and writes it to the
card on a shutter half-press. Each line is four 32-bit words in hex: `TAG W1 W2 W3`. The first line is a header
(TAG = ffffffff): build id, L<<16 | overlay flag byte<<8 | keyhook stage byte, and the number of entries ever logged
(more than 1024 = the ring wrapped; the oldest are gone). A title line "CADUCEUS TRACE 1" comes first.

This tool turns that into readable rows, naming known addresses and event codes from docs/atlas.json. Nothing here
touches the camera; run it on the TRACE.TXT you copied off the card.

  tools/trace_decode.py EP7MOD/TRACE.TXT [--atlas docs/atlas.json]

Entry tags (set by patches/diag/build.py; this tool reads them from the diag spec if --spec is given, else the
built-in defaults):
  K0  key event at site 0 (0x60ce0108, the shooting-state hook)    W1 event code  W2 CA state (record+196)  W3 record+4
  K1  key event at site 1 (0x60cebc89, the select-state hook)      same
  KT  key event at the unhooked twin (0x60ce017e)                  same
  D0/D1  the plugin handled that event at site 0 / 1               same words, read after the plugin ran
  PT  paint while the Colour Profile view is alive (capped)        W1 window      W2 its vtable  W3 painter
      tag bits 8-15: overlay flag byte
  PD  our overlay draw                                             W1 gc  W2 gc+0x4c before  W3 gc+0x4c after
      tag bit 8: we selected a style; bits 12-15 rows drawn; 16-23 gc+0x34 before; 24-31 after
  PS  after the draw                                               W1 sp on entry  W2 sp on exit  W3 draw's d0
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Default tag map (keep in sync with patches/diag/build.py T_KEY0/T_KEY1/T_KEYT/T_PAINT).
TAGS = {0: 'K0', 1: 'K1', 2: 'KT', 3: 'PT', 4: 'PD', 5: 'PS', 6: 'D0', 7: 'D1'}
HEADER = 0xffffffff

# A few event codes the readout is about (docs/PLUGINS.md §9, §12). Not authoritative for the physical "Shortcut"
# button -- that is exactly what a dump is meant to reveal -- so unknown codes are shown as-is.
EVENTS = {
    0x0100002e: 'KEY_PRESS (Fn family)',
    0x0100002f: 'KEY_RELEASE (Fn family)',
    0x02000100: 'HALF_PRESS',
}


def load_atlas(path):
    try:
        a = json.loads(Path(path).read_text())
    except OSError:
        return {}
    return {int(e['addr'], 16): e['name'] for e in a.get('symbols', []) if 'addr' in e}


def name_addr(atlas, v):
    """Name an address-like word: exact atlas hit, or the nearest symbol at/just below it."""
    if v in atlas:
        return atlas[v]
    below = [a for a in atlas if a <= v and v - a < 0x400]
    if below:
        a = max(below)
        return f'{atlas[a]}+{v - a:#x}'
    return ''


def word(atlas, v, kind):
    s = f'{v:08x}'
    if kind == 'event':
        if v in EVENTS:
            return f'{s} {EVENTS[v]}'
        rel = v >> 24
        return f'{s}' + (f' (class {rel:#x})' if 0 < rel < 0x10 else '')
    if kind == 'addr' and 0x60000000 <= v < 0x62000000:
        n = name_addr(atlas, v)
        return f'{s} {n}' if n else s
    return s


def parse(path):
    rows = []
    for ln in Path(path).read_text(errors='replace').splitlines():
        parts = ln.split()
        if len(parts) != 4 or not all(len(p) == 8 for p in parts):
            continue
        try:
            rows.append(tuple(int(p, 16) for p in parts))
        except ValueError:
            continue
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('file', type=Path)
    ap.add_argument('--atlas', type=Path, default=ROOT / 'docs/atlas.json')
    ap.add_argument('--spec', type=Path, help='a built spec (generated/v032/edits.json) to read the diag tag map from')
    a = ap.parse_args()
    atlas = load_atlas(a.atlas)
    tags = dict(TAGS)
    if a.spec and a.spec.exists():
        t = json.loads(a.spec.read_text()).get('diag', {}).get('trace', {}).get('tags', {})
        tags = {v: k for k, v in t.items() if isinstance(v, int) and v >= 0} or tags

    rows = parse(a.file)
    if not rows:
        print('no decodable lines (expected four hex words per line)', file=sys.stderr)
        return 1

    n_key = n_paint = 0
    seen_codes = {}
    for i, (tag, w1, w2, w3) in enumerate(rows):
        if tag == HEADER:
            L, O, K = (w2 >> 16) & 7, (w2 >> 8) & 0xff, w2 & 0xff
            print(f'# TRACE build {w1:08x}  L={L}  flag={O:#04x}  kstage={K:#04x}  {w3} entries logged'
                  + ('  (ring wrapped: oldest lost)' if w3 > 1024 else ''))
            continue
        label = tags.get(tag & 0xff, f'?{tag:#x}')
        if label in ('K0', 'K1', 'KT', 'D0', 'D1'):
            if label[0] == 'K':
                n_key += 1
                seen_codes[(label, w1)] = seen_codes.get((label, w1), 0) + 1
            print(f'{i:4}  {label}  ev={word(atlas, w1, "event"):<34}  state={w2:#06x}  rec+4={w3:08x}')
        elif label == 'PT':
            n_paint += 1
            print(f'{i:4}  PT  flag={(tag >> 8) & 0xff:#04x}  window={w1:08x}  vt={word(atlas, w2, "addr"):<28}  '
                  f'painter={w3:08x}')
        elif label == 'PD':
            print(f'{i:4}  PD  gc={w1:08x}  font {w2:08x} -> {w3:08x}  selected={(tag >> 8) & 1}  rows={(tag >> 12) & 15}  '
                  f'gc+0x34 {(tag >> 16) & 0xff:#04x} -> {(tag >> 24) & 0xff:#04x}')
        elif label == 'PS':
            print(f'{i:4}  PS  sp {w1:08x} -> {w2:08x}' + ('' if w1 == w2 else '  MISMATCH') + f'  draw d0={w3:08x}')
        else:
            print(f'{i:4}  {label}  {w1:08x} {w2:08x} {w3:08x}')

    print(f'\n# {n_key} key events, {n_paint} paints')
    if seen_codes:
        print('# event codes seen at the key sites (code: count):')
        for (site, code), c in sorted(seen_codes.items(), key=lambda kv: -kv[1]):
            tag = EVENTS.get(code, '')
            print(f'#   {site} {code:08x}  x{c}' + (f'  {tag}' if tag else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
