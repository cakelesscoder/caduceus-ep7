#!/usr/bin/env python3
"""E-M1 Mark II: emulate the Super Control Panel aspect value cell on a release spec, against stock.

    python3 tools/omdem1mk2_emu_scp.py releases/em1mk2/<ver>/edits.json

Checks (docs/OMD-EM1-II/ASPECT.md §6.6):
  C  native runs of both cell builders (0x60e6a0e7 -> 0x60e6a0fc, 0x60e70c1e -> 0x60e70c33): GetValue(270) result on
     the stack, run the firmware's lookup 0x60e59f44, read the cell index. Values 0..12, stock vs patched.
  W  index - 2 -> part of widget record 0x611329f8 (count, parts list) -> bitmap id.
  G  the firmware's bitmap getter 0x60d76dc9 run with the table pointer (0x61fbc3e0) set, OSD bank 0 (with the spec's
     0x101 edits, if any; none since v0.4c9) mapped at its runtime address 0xa2c91000 and the main image under both
     aliases (0x60.. cached, 0xa0.. uncached); the returned entry -> descriptor -> payload are read through the
     emulator's memory map and decoded. v0.4c9 hook route: 6668 / 7086 must come from the main-image entries
     (aspect/build.py ICON_ENTRY), and 400 other ids must return the same entry as the stock image.
  R  SCP option row (OK on the aspect tile; v0.4c10): native runs of the item-record search 0x60f36a43 -> 0x60f36a6a
     (tables 0x612e3040 / 0x612e311c, items 0x1ff / 0x200 -> n, A, B) and of the row builder's per-option bitmap search
     0x60f36cd3 -> 0x60f36d0b (value -> white id obj+232[k], green id obj+228[k]) for values 1,2,3,4,9,6,7.
  L  option screen 57's label source (v0.4c13): option-label record key 16 (0x6123e194) -> A / B lists; the firmware's
     resolver 0x60e59f78 run natively (caller stub, frame 24) for values 1,2,3,4,9,6,7 -> {kind, id}.
Not emulated: the widget draw / blitter (0x60d7aaea -> 0x60d7909a) and whether the camera writes the OSD component.
"""
import json, os, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'external/oly_fw_analysis/tools'))
sys.path.insert(0, str(ROOT / 'patches/omdem1mk2/aspect_icons'))
import omdem1mk2_emu_validator as V  # noqa: E402
from penf_emulator import Region, execute  # noqa: E402

SECS = [(0x60021020, 0x600de000), (0x600de000, 0x60257800), (0x602ae000, 0x60580800), (0x60591800, 0x605d3000),
        (0x605d5000, 0x6078f000), (0x60796000, 0x60bc8800), (0x60bf1000, 0x612e7000), (0x61300000, 0x613ed000),
        (0x613f6800, 0x6146d000)]
SITES = {0x60e6a0ed: (0x60e6a0e7, 0x60e6a0fc), 0x60e70c24: (0x60e70c1e, 0x60e70c33)}
STK, OUT, SELF = 0x9f000000, 0x9f100000, 0x9f200000
SCP_REC = 0x611329f8
TILE_REC = 0x611771d8          # the SCP tile's boxed text labels (v0.4c11)
GETTER, TABLE_PTR = 0x60d76dc9, 0x61fbc3e0
OSD_BASE0 = 0xa2c91000


def main_regions(img, perm='rx'):
    out = []
    for i, (lo, hi) in enumerate(SECS):
        out.append(Region(f's{i}', lo, img[lo - V.B:hi - V.B], perm))
        out.append(Region(f'u{i}', lo + 0x40000000, img[lo - V.B:hi - V.B], 'r'))   # uncached alias 0xa0..
    return out


def cell(img, site, v):
    start, stop = SITES[site]
    stk = bytearray(0x2000)
    struct.pack_into('<I', stk, 0x1000 + 8, v)
    rg = main_regions(img) + [Region('stk', STK, bytes(stk), 'rw', True), Region('out', OUT, bytes(8), 'rw', True),
                              Region('self', SELF, bytes(0x1000), 'rw')]
    regs = {'pc': start, 'sp': STK + 0x1000, 'a3': OUT, 'd2': SELF, 'd3': SELF}
    r = execute(rg, regs, 0xfffffff0, limit=5000, breakpoints=[stop])
    if r['status'] != 'breakpoint' or r['fault']:
        return ('fault', r['status'], r['fault'])
    m = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}
    return struct.unpack_from('<H', m['out'], 0)[0]


def part_bitmap(img, index, rec=SCP_REC):
    n = img[rec + 0x35 - V.B]
    parts = struct.unpack_from('<I', img, rec + 0x38 - V.B)[0]
    p = index - 2
    if not 0 <= p < n:
        return None
    return struct.unpack_from('<4I', img, parts + 16 * p - V.B)[3]


def osd_component(spec):
    import build as IC                      # aspect_icons build (OSD parser with E-M1 II constants)
    o = IC.load()
    osd = bytearray(o.data)
    if spec:
        for e in json.loads(Path(spec).read_text())['edits']:
            if e['kind'] == '0x101':
                off, old = int(e['addr'][4:], 16), bytes.fromhex(e['expect'])
                assert osd[off:off + len(old)] == old
                osd[off:off + len(old)] = bytes.fromhex(e['new'])
    return o, bytes(osd)


def getter(img, o, osd, bid):
    """Run 0x60d76dc9(bid) and follow entry -> descriptor -> payload through the same memory map."""
    r0 = o.resources[0]
    bank0 = osd[r0['offset']:r0['offset'] + r0['size']]
    tab = o.bitmap_table
    data_img = bytearray(img[0x60258000 - V.B:0x602ae000 - V.B])
    struct.pack_into('<I', data_img, TABLE_PTR - 0x61f7d540, tab)
    rg = main_regions(img) + [Region('bank0', OSD_BASE0, bank0, 'r'), Region('data', 0x61f7d540, bytes(data_img), 'rw'),
                              Region('stk', STK, bytes(0x2000), 'rw'), Region('caller', 0x9f300000, b'\xcb', 'rx')]
    # retf returns through mdr: set it to a stop address
    r = execute(rg, {'pc': GETTER, 'sp': STK + 0x1000, 'd0': bid, 'mdr': 0x9f300000}, 0x9f300000, limit=200)
    if r['fault'] or r['registers']['pc'] != 0x9f300000:
        return ('fault', r['registers']['pc'], r['fault'])
    entry = r['registers']['a0']

    def rd(addr, n):
        for reg in rg:
            if reg.address <= addr and addr + n <= reg.address + len(reg.data):
                return bytes(reg.data[addr - reg.address:addr - reg.address + n])
        raise KeyError(hex(addr))
    if entry == 0:
        return dict(entry=0)
    try:
        desc = struct.unpack('<I', rd(entry, 4))[0]
        fmt, w, h, b8, _, _, ln, pay, key = struct.unpack('<6H3I', rd(desc, 24))
    except KeyError:                        # descriptor in a bank this harness doesn't map (e.g. bank 69)
        return dict(entry=entry)
    stream = rd(pay, ln) if ln else b''
    return dict(entry=entry, desc=desc, fmt=fmt, w=w, h=h, len=ln, payload=pay, stream=stream)


SENT = 0x5a5a5a5a


def row_record(img, table, item):
    stk = bytearray(0x2000)
    ob = bytearray(0x400)
    struct.pack_into('<H', ob, 186, item)
    rg = main_regions(img) + [Region('stk', STK, bytes(stk), 'rw', True), Region('obj', SELF, bytes(ob), 'rw', True)]
    r = execute(rg, {'pc': 0x60f36a43, 'sp': STK + 0x1000, 'a0': SELF + 186, 'd1': SELF + 186, 'a2': table, 'd2': 0, 'd0': 0},
                0xfffffff0, limit=2000, breakpoints=[0x60f36a6a])
    if r['status'] != 'breakpoint' or r['fault']:
        return ('fault', r['status'], r['fault'])
    g = r['registers']
    return g['d0'] & 0xffff, g['d1'], g['a1'], struct.unpack_from('<I', img, g['a3'] + 4 - V.B)[0]


def row_bitmaps(img, n, A, Bl, value, slot=3):
    stk = bytearray(0x2000)
    for off, v in ((4, n), (44, A), (60, value), (40, OUT), (48, OUT + 0x100), (52, Bl)):
        struct.pack_into('<I', stk, 0x1000 + off, v)
    arr = bytearray(struct.pack('<I', SENT) * 0x80)
    struct.pack_into('<II', arr, 0, SELF, 0)              # (40,sp) -> ptr to white array
    struct.pack_into('<I', arr, 0x100, SELF + 0x100)     # (48,sp) -> ptr to green array
    rg = main_regions(img) + [Region('stk', STK, bytes(stk), 'rw', True), Region('out', OUT, bytes(arr), 'rw', True),
                              Region('self', SELF, struct.pack('<I', SENT) * 0x80, 'rw', True)]
    r = execute(rg, {'pc': 0x60f36cd3, 'sp': STK + 0x1000, 'd3': slot * 4, 'a3': 0, 'd2': 0}, 0xfffffff0, limit=2000,
                breakpoints=[0x60f36d0b])
    if r['status'] != 'breakpoint' or r['fault']:
        return ('fault', r['status'], r['fault'])
    m = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}
    return struct.unpack_from('<I', m['self'], slot * 4)[0], struct.unpack_from('<I', m['self'], 0x100 + slot * 4)[0]


def resolve(img, value, n, lst):
    """call 0x60e59f78,[d2,d3,a2,a3],24 with d0 = value, d1 = n, a1 = list, out pointer at the caller's (4,sp)."""
    CALL = 0x9f400000
    code = b'\xdd' + struct.pack('<i', 0x60e59f78 - CALL) + b'\xf0\x18\xcb'
    stk = bytearray(0x2000)
    struct.pack_into('<I', stk, 0x1000 + 4, OUT)
    rg = main_regions(img) + [Region('call', CALL, code, 'rx'), Region('stk', STK, bytes(stk), 'rw'),
                              Region('out', OUT, bytes(0x60), 'rw', True)]
    r = execute(rg, {'pc': CALL, 'sp': STK + 0x1000, 'd0': value, 'd1': n, 'a1': lst, 'a0': 0}, CALL + 7, limit=5000)
    if r['fault'] or r['registers']['pc'] != CALL + 7:
        return ('fault', hex(r['registers']['pc']), r['fault'])
    m = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}
    kind, bid = struct.unpack_from('<HH', m['out'], 0)
    return (kind, bid) if kind else None


def main():
    spec = sys.argv[1]
    old, new = V.image(None), V.image(spec)
    fails = 0
    print('C  cell builders, values 0..12 (stock -> patched index)')
    for site in SITES:
        row = []
        for v in range(13):
            a, b = cell(old, site, v), cell(new, site, v)
            want = {6: 8, 7: 9}.get(v, a)
            ok = b == want and not isinstance(a, tuple)
            fails += not ok
            row.append(f'{v}:{a}->{b}' + ('' if ok else '!'))
        print(f'   {site:#x}', ' '.join(row))
    print('W  index -> part -> bitmap, record A 0x611329f8 (strip icons) | record B 0x611771d8 (tile labels); stock | patched')
    for v, idx in ((1, 2), (2, 3), (9, 4), (4, 5), (3, 6), (10, 7), (6, 8), (7, 9)):
        row = []
        for rec, want6, want7 in ((SCP_REC, 6668, 7086), (TILE_REC, 6669, 7087)):
            a, b = part_bitmap(old, idx, rec), part_bitmap(new, idx, rec)
            want = {6: want6, 7: want7}.get(v, a if v != 10 or rec == TILE_REC else 476)
            fails += b != want
            row.append(f'{a} | {b}' + ('' if b == want else ' !'))
        print(f'   value {v} index {idx}: ' + '   '.join(row))
    print('R  SCP option row: item record -> lists; value -> (white, green) bitmap ids (stock | patched)')
    for table, item in ((0x612e3040, 0x1ff), (0x612e311c, 0x200)):
        recs = [row_record(x, table, item) for x in (old, new)]
        if any(isinstance(x, tuple) and x and x[0] == 'fault' for x in recs):
            fails += 1; print('   ', hex(item), recs, '!'); continue
        print(f'   item {item:#x}: n/A/B/screen stock {recs[0][0]} {recs[0][1]:#x} {recs[0][2]:#x} {recs[0][3]:#x}'
              f' | patched {recs[1][0]} {recs[1][1]:#x} {recs[1][2]:#x} {recs[1][3]:#x}')
        want_t = int(os.environ.get('EM1_SCP_ROW_TYPE', '0x39'), 16)   # = aspect/build.py default (stock screen 57 since c13)
        fails += recs[1][3] != want_t
        row = []
        for v in (1, 2, 3, 4, 9, 6, 7):
            a, b = row_bitmaps(old, *recs[0][:3], v), row_bitmaps(new, *recs[1][:3], v)
            want = {6: (476, 476) if os.environ.get('EM1_SCP_ROW_DIAG') == '1' else (6668, 6668), 7: (7086, 7086)}.get(v, a)
            ok = b == want and (v not in (6, 7) or a == (SENT, SENT))
            fails += not ok
            fmt = lambda t: 'none' if t == (SENT, SENT) else f'{t[0]}/{t[1]}'
            row.append(f'{v}:{fmt(a)}|{fmt(b)}' + ('' if ok else '!'))
        print('     ', ' '.join(row))
    print('L  option screen 57 labels: record key 16 -> resolver 0x60e59f78 -> {kind, id} (stock | patched)')
    for half, off in (('white', 4), ('green', 8)):
        row = []
        for v in (1, 2, 3, 4, 9, 6, 7):
            res = []
            for im in (old, new):
                lst, n = struct.unpack_from('<I', im, 0x6123e194 + off - V.B)[0], struct.unpack_from('<I', im, 0x6123e194 + 12 - V.B)[0]
                res.append(resolve(im, v, n, lst))
            a, b = res
            want = {6: (3, 6668), 7: (3, 7086)}.get(v, a)
            ok = b == want and (v not in (6, 7) or a is None)
            fails += not ok
            row.append(f'{v}:{a[1] if a else "none"}|{b[1] if b else "none"}' + ('' if ok else '!'))
        print(f'   {half}: ' + ' '.join(row))
    print('G  bitmap getter 0x60d76dc9 -> descriptor -> payload (patched OSD + main)')
    import build as IC
    from osd_extract import decode_rle
    o, osd = osd_component(spec)
    imgs = IC.build_images(o)
    sys.path.insert(0, str(ROOT / 'patches/omdem1mk2/aspect'))
    import importlib.util
    spec_a = importlib.util.spec_from_file_location('aspect_build', ROOT / 'patches/omdem1mk2/aspect/build.py')
    AB = importlib.util.module_from_spec(spec_a); spec_a.loader.exec_module(AB)
    hook = not any(e['kind'] == '0x101' for e in json.loads(Path(spec).read_text())['edits'])
    diag = os.environ.get('EM1_ICON_DIAG') == '1'
    if hook:
        same = 0
        others = [b for b in list(range(0, 7408, 19)) + [6667, 6670, 7085, 7088, 65535] if b not in AB.ICON_ENTRY]
        for bid in others:
            a, b = getter(old, o, osd, bid), getter(new, o, osd, bid)
            same += (not isinstance(a, tuple)) and a == b
        n = len(others)
        fails += same != n
        print(f'   other ids: patched getter = stock for {same}/{n}' + ('' if same == n else '  !'))
    tiles = IC.tile_labels(o)
    for bid, ref in ((476, None), (5866, None), (6668, ('6524', 'white')), (7086, None if diag else ('219', 'white')),
                     (6669, ('tile', '6524')), (7087, ('tile', '219'))):
        g = getter(new, o, osd, bid)
        if isinstance(g, tuple):
            fails += 1
            print(f'   id {bid}: {g}  !')
            continue
        px, *_ = decode_rle(g['stream'], g['w'], g['h'])
        want_px = None if ref is None else (tiles[ref[1]] if ref[0] == 'tile' else imgs[ref]).astype('uint8').tobytes()
        ok = g['fmt'] == 14 and (want_px is None or px == want_px)
        if hook and bid in AB.ICON_ENTRY:
            ok = ok and g['entry'] == AB.ICON_ENTRY[bid]
        if diag and bid == 7086:
            ok = ok and g['desc'] == getter(new, o, osd, 476)['desc']
        fails += not ok
        print(f"   id {bid}: entry {g['entry']:#x} desc {g['desc']:#x} fmt {g['fmt']} {g['w']}x{g['h']} payload {g['payload']:#x}"
              f" ({g['len']} B) decodes {'as built' if ref else 'ok'}" + ('' if ok else '  !'))
    print('RESULT', 'PASS' if not fails else f'FAIL ({fails})')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
