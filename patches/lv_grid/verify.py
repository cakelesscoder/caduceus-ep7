#!/usr/bin/env python3
"""lv_grid checks (static, from the built package). Offline. Data-only patch: no code runs differently.

  .venv/bin/python -I patches/lv_grid/verify.py releases/v0.31d/edits.json generated/v032/edits.json

  T  the selector's lookup (0x60e326c3: first row of the class table whose aspect matches, count 6; then the first
     {value, bitmap} of that row's list) replayed on both main payloads for 3 tables x aspects {1,2,3,4,9,6,7,10} x grid
     values {1,5,6,7,8,9}: identical to v0.31d except aspect 6 (now the XPan thirds bitmap, all values) and aspect 3
     value 8 (frame lines); aspect 10 (unreachable here) no longer matches; aspect 7 still finds nothing (no grid).
  O  the patched OSD component parses with tools/osd_extract.py (bank bases unchanged); the six new ids decode (fmt 14,
     8-bit, mode 11) to exactly the build's images, in place; the bitmap table is unchanged; every other RLE bitmap
     decodes byte-identical to v0.31d; resource 69 size unchanged.
"""
import json, struct, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'external/oly_fw_analysis/tools'))
sys.path.insert(0, str(ROOT / 'patches/aspect'))
import build_package as BP  # noqa: E402
import oly_container as oc  # noqa: E402
import osd_extract as X  # noqa: E402
import importlib.util  # noqa: E402

s_ = importlib.util.spec_from_file_location('lvg', ROOT / 'patches/lv_grid/build.py'); G = importlib.util.module_from_spec(s_); s_.loader.exec_module(G)
BASE = 0x60020020


def payloads(spec):
    pkg, rst, info = BP.build(spec, BP.STOCK.read_bytes())
    return {b.kind: b.payload for b in oc.parse(pkg)}


def lookup(m, table, aspect, value):
    u = lambda a: struct.unpack_from('<I', m, a - BASE)[0]
    if m[0x60e326c3 - BASE:0x60e326c5 - BASE] != b'\x90\x06':
        return 'count changed'
    for r in range(6):
        if u(table + 12 * r) == aspect:
            lst, n = u(table + 12 * r + 4), u(table + 12 * r + 8)
            for j in range(n):
                if u(lst + 8 * j) == value:
                    return u(lst + 8 * j + 4)
            return None
    return None


def osd(data):
    with tempfile.NamedTemporaryFile(suffix='.bin') as f:
        f.write(data); f.flush()
        return X.OSD(component=f.name, check_hash=False)


def main():
    base_s, new_s = (json.loads(Path(p).read_text()) for p in sys.argv[1:3])
    b, n = payloads(base_s), payloads(new_s)
    ids = new_s['lv_grid']['ids']
    bad, cnt = [], 0
    for k, t in enumerate(G.TABLES):
        for asp in (1, 2, 3, 4, 9, 6, 7, 10):
            for v in (1, 5, 6, 7, 8, 9):
                x0, x1 = lookup(b[0x100], t, asp, v), lookup(n[0x100], t, asp, v)
                want = x0
                if asp == 6 and v in (1, 5, 6, 7, 8):
                    want = ids[f'xpan{k}']
                elif asp == 3 and v == 8:
                    want = ids[f'frames{k}']
                elif asp == 10:
                    want = None
                cnt += 1
                if x1 != want:
                    bad.append((hex(t), asp, v, x0, x1, want))
    ok_t = not bad
    print(f"{'PASS' if ok_t else 'FAIL'} T {cnt} lookups; changed only aspect 6 (all values) / aspect 3 value 8 / aspect 10 gone; bad {bad[:4]}")
    ob, on = osd(b[0x101]), osd(n[0x101])
    ok = (ob.base0, ob.base69) == (on.base0, on.base69)
    imgs = {f'xpan{k}': G.img_xpan(ob.descriptor(G.THIRDS[k])['width'], ob.descriptor(G.THIRDS[k])['height']) for k in range(3)}
    imgs |= {f'frames{k}': G.img_frames(ob.descriptor(G.DIAG[k])['width'], ob.descriptor(G.DIAG[k])['height']) for k in range(3)}
    for key, i in ids.items():
        r = on.descriptor(i)
        px, mode, data = on.decode_bitmap(r)
        h, w = imgs[key].shape
        ok &= (r['kind'] == 'rle' and r['fmt'] == 14 and (r['width'], r['height']) == (w, h) and r['field6'] == 8 and mode == 11
               and px == imgs[key].tobytes() and r['descriptor_offset'] == ob.descriptor(i)['descriptor_offset'])
    t0 = ob.bitmap_table - ob.base0
    tb = struct.unpack_from(f'<{ob.bitmap_count}I', ob.bank0, t0)
    tn = struct.unpack_from(f'<{on.bitmap_count}I', on.bank0, t0)
    changed = sorted(i for i in range(len(tb)) if tb[i] != tn[i])
    ok &= changed == []
    hosts = set(ids.values())
    others = [i for i in range(1, ob.bitmap_count) if i not in hosts and ob.descriptor(i)['kind'] == 'rle']
    ok &= all(on.decode_bitmap(on.descriptor(i))[2] == ob.decode_bitmap(ob.descriptor(i))[2] for i in others)
    for i in list(G.THIRDS) + list(G.DIAG) + [6004, 6765, 6012]:
        ok &= on.decode_bitmap(on.descriptor(i))[2] == ob.decode_bitmap(ob.descriptor(i))[2]
    r69 = on.resources[69]
    ok &= r69['size'] <= 0xf26140 and on.base69 + r69['size'] <= 0xa3091000 + 0xf26140
    print(f"{'PASS' if ok else 'FAIL'} O hosts {sorted(hosts)} decode to the build images (in place); bitmap table unchanged; "
          f"the other {len(others)} RLE bitmaps byte-identical; resource 69 size {r69['size']:#x} (stock)")
    print('ALL PASS' if ok and ok_t else 'FAILURES')
    sys.exit(0 if ok and ok_t else 1)


if __name__ == '__main__':
    main()
