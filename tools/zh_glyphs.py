#!/usr/bin/env python3
"""Which characters can the E-P7 1.1 draw when the menu language is Simplified Chinese? (docs/I18N_ZH.md)

Reads the stock OSD component (kind 0x101, hash-checked by tools/osd_extract.py). Language 5 (Simplified Chinese,
sid 3009 value 5) loads string resource 2 and font resource 36 (main tables 0x611f0c5c / 0x611f0d7c, loader
0x60eac6f2). A font resource holds one or more fonts. Each is a two-level code-point map:

  dir  u32[256]   indexed by the code point's high byte -> page pointer (0 = no page)
  page {u16 w, u16 h, u32 glyph}[256] indexed by the low byte; glyph = mode-9 stream pointer (0 = no glyph)

Pointers are runtime addresses (font base 0xa3fb7540, OSD.md). The dir pointers sit in the 32 B before the font
header (*(res+0)); a candidate that fails the page/glyph checks (res 36 +0x53d80) is not a dir. Res 36 has two fonts: dir +0x54580 (636 glyphs,
37 px: U+30xx punctuation and CJK) and dir +0x54980 (133 glyphs, 40 px: Latin page 0x00 and full-width page 0xFF).
Stock Chinese strings mix both (e.g. string 2749 '色彩配置文件 1'), so the renderer falls back per character.

  .venv/bin/python -I tools/zh_glyphs.py                    # summary + the character list
  .venv/bin/python -I tools/zh_glyphs.py --check 颗粒 暗角校正  # glyphs OK / missing per argument
  .venv/bin/python -I tools/zh_glyphs.py --json out.json
"""
import argparse, json, struct, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from osd_extract import OSD, decode_rle, FormatError  # noqa: E402

FONT_RES, STRING_RES = 36, 2     # Simplified Chinese (language value 5)


def fonts(o, res=FONT_RES):
    """-> list of (dir_offset, {codepoint: (w, h, glyph_offset)}) for every code-point dir in the resource."""
    r = o.resources[res]
    blob = o.data[r['offset']:r['offset'] + r['size']]
    base, n = o.FONT_BASE, len(blob)
    p0, = struct.unpack_from('<I', blob, 0)
    head = p0 - base                    # font header; the dir pointers are the words just before it (res 36: +0x54d7c)
    cands = []
    for k in range(head - 0x20, head, 4):
        v, = struct.unpack_from('<I', blob, k)
        if v and 0 <= v - base <= n - 1024:
            cands.append(v - base)
    out = []
    for d in cands:
        ents = struct.unpack_from('<256I', blob, d)
        if not any(ents) or any(e and not (0 <= e - base <= n - 2048) for e in ents):
            continue
        cmap, ok = {}, True
        for hi, e in enumerate(ents):
            if not e:
                continue
            pg = e - base
            for lo in range(256):
                w, h, g = struct.unpack_from('<HHI', blob, pg + 8 * lo)
                if not g:
                    continue
                q = g - base
                if not (0 <= q < n - 4 and blob[q + 3] == 9):
                    ok = False
                    break
                try:
                    _px, gw, gh, _m, _u = decode_rle(blob[q:], exact_extent=False)
                except FormatError:
                    ok = False
                    break
                if (gw, gh) != (w, h):
                    ok = False
                    break
                cmap[hi << 8 | lo] = (w, h, q)
            if not ok:
                break
        if ok and cmap:
            out.append((d, cmap))
    return out


def available(o=None):
    o = o or OSD()
    cps = set()
    for _d, cmap in fonts(o):
        cps |= set(cmap)
    return {chr(c) for c in cps}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', nargs='*', help='strings to test against the glyph set')
    ap.add_argument('--json', type=Path)
    a = ap.parse_args()
    o = OSD()
    fl = fonts(o)
    have = set()
    for d, cmap in fl:
        hs = sorted({v[1] for v in cmap.values()})
        print(f'font dir res{FONT_RES}+{d:#x}: {len(cmap)} glyphs, height {hs}, pages '
              + ' '.join(f'{p:02x}' for p in sorted({c >> 8 for c in cmap})))
        have |= {chr(c) for c in cmap}
    _b, strs = o.strings(STRING_RES)
    used = {ch for s in strs if s for ch in s if ord(ch) > 0x7e}
    cjk = sorted(c for c in have if ord(c) > 0x7e)
    print(f'{len(have)} characters; {len(cjk)} beyond ASCII. String table {STRING_RES} uses {len(used)} beyond ASCII, '
          f'{len(used - have)} of them without a glyph (shared table text this body does not draw).')
    if a.check:
        bad = 0
        for s in a.check:
            miss = [c for c in s if c not in have and c != ' ']
            bad += bool(miss)
            print(f'{s}\t{"OK" if not miss else "MISSING " + "".join(miss)}')
        sys.exit(1 if bad else 0)
    if a.json:
        a.json.write_text(json.dumps(dict(font_res=FONT_RES, chars=''.join(sorted(have))), ensure_ascii=False) + '\n')
    else:
        print(''.join(cjk))


if __name__ == '__main__':
    main()
