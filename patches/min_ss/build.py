#!/usr/bin/env python3
"""Minimum shutter speed (ISO-Auto "Lowest S/S Setting"), test m4. Offline. docs/MIN_SHUTTER.md.

  .venv/bin/python -I patches/v029a/build.py releases/v0.28/edits.json --out generated/min_ss/v029a.json
  .venv/bin/python -I patches/min_ss/build.py generated/min_ss/v029a.json --out generated/min_ss/m4/edits.json
  .venv/bin/python -I tools/build_package.py generated/min_ss/m4/edits.json --out generated/min_ss/m4/rel
  .venv/bin/python -I patches/min_ss/verify.py generated/min_ss/v029a.json generated/min_ss/m4/edits.json generated/min_ss/m4/rel

apply(spec, version='0.30m4') -> spec. Data plus one in-place rewrite, no new code path.

m1 (re-pointing ISO-Auto Set at the OM submenu) failed on camera: the submenu can't be entered without a SET key.
m3 (0.30b8) showed the row, but its inline value column (40 values) ran off the screen. m4 drops the inline column
and opens the stock "Lowest S/S Setting" picker screen instead (group 8 state 0x1aa: type-5 list on sid 1147, generic
scrolling list viewer 0x19, its own label table entry 0x75 at 0x611dd314: title 3067, 55 stock shutter labels
0x611d8b24 keyed by Tv, help 3068):
  * OK on row 1147 -> (8, 0x1aa): both OK tables shared by kinds 0x4b / 0x4c are copied with one entry appended
    {1, 1147, 0, 8, 0x1aa, 0}; the kinds' items lists are stock again (no inline column)
  * the picker's label for value 0 ("1''", Tv 0 = 1 s) -> string 71 "Auto", in place (0 = Auto in m2's builder)
m2 added the row's record and inline item but no row appeared on camera (0.30b7): the rows the E-P7 draws come
from the Custom Menu page column's row list, not from the record array. m3 = m2 + that list:
  * E1 "Exp/ISO/BULB" rows = column mode 93 (2CNL kind 0x4b), record 0x61150b7c {key 0, count 4, RAM .data list
    0x61fc1f3e = [273, 112, 143, 35]} read by the row builder 0x60de276f (memcpy only; CANEXEC greys, never hides).
    m3: count 4 -> 5, list -> a read-only copy [273, 112, 1147, 143, 35] in our data block
  * row info (label / help / list by sid) = page 0x13cc's 36-B record array, where m2 put the 1147 record:
  * D1 "Exp/ISO/BULB" (both menu trees): the 7 stock row records are copied into dead EVF table space with an 8th
    record after ISO-Auto Set: sid 1147, "Lowest S/S Setting" (3067), help 3068, 40-value label list; count 7 -> 8
  * the Custom Menu page kinds 0x4b / 0x4c share an items list (rows that open an inline value column); a copy with
    1147 appended (10 -> 11)
  * sid 1147 validator record 1061: list = the stock list from value 0 on, [0, 85 .. 3328] (40 values, no new data)
  * AE record builder 0x604279c9..f5 (44 B, in place): +30 = (sid 1147 == 0) ? 0x7eee : sid 1147. Sid 1146 is no
    longer read: 0 = Auto (stock limit), any speed = on. 1147 starts at 0, so a fresh flash is stock; stock firmware
    still reads 1146 (still 0), so a downgrade is stock too.
"""
import argparse, copy, importlib.util, json, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = 'patches/min_ss'
STOCK = ROOT / 'analysis/ep7_1100/00_0100_406a0020.decoded.bin'
BASE = 0x60020020


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


FV = _load('fw_version_build', ROOT / 'patches/fw_version/build.py')

SID_TV = 1147
STR_LABEL, STR_HELP, STR_AUTO = 3067, 3068, 71
# D1 page entries (20 B {label, rec, 0x6117b5b0/.., u16 page, u16 count}) and their tree's label-source word
PAGES = [(0x6117ea4c, 0x6117df2c, 0x611799dc), (0x61160fb0, 0x61160430, 0x6115d8b8)]
PAGE_ID, PAGE_N, ROW_SZ = 0x13cc, 7, 36
LAST_SID = 112                                   # ISO-Auto Set: the new row goes right after it
ROWREC, ROWS_E1 = 0x61150b7c, [273, 112, 143, 35]  # E1 column (mode 93) row-list record {u16 key, u16 count, u32 list}
DATA_DELTA = 0x61fc27d0 - 0x6025aa90             # .data RAM - flash init image (LOOK_EDITOR: 0x61fc27d0 <- 0x6025aa90)
KINDS = [0x6114c27c, 0x6114c2a0]                 # 2CNL kinds 0x4b / 0x4c: +12 items ptr, +16 items count
ITEMS, ITEMS_N = 0x6114ae6c, 10
OKT = [(0x6114882c, 8), (0x611488ec, 7)]         # OK tables shared by kinds 0x4b / 0x4c (+20/+24, +28/+32)
PICK_STATE = 0x1aa                               # stock Lowest S/S picker (type 5, sid 1147)
PICK_LBL, PICK_N, PICK_IDX = 0x611dd314, 55, 0x75   # its label-table entry {idx, title, n, labels, help, ..}
VREC = 0x604d1c70                                # validator record 1061 (sid 1147): +4 list, +12 u16 bytes
VLIST, VLIST_N, V_FROM = 0x604cc34c, 55, 15      # stock list index 15 = value 0
SLOW_LIST, SLOW_N = 0x6117c134, 42               # flash Slow Limit labels, kind 5 text, 1/400 .. 30"
II_LIST = 0x611b9a10                             # item-info list of sid 1146: entry k = text of 1147 index k - 1
BLD, BLD_END = 0x604279c9, 0x604279f5            # AE record builder: 1146 / 1147 -> record +30
PROP, BLD_STOCK = 0x6005e971, ('2c5153fca0a00b2a6204dd9e6fc3ffc00c14a000c9072cee7eca132c6a53fca0a40b2a6204dd836fc3ffc00c')

# code space: dead EVF gamma tables in section 1 (E-P7 has no EVF); only refs = step-table words to table starts
AT, END = 0x601dea50, 0x601df020                 # tables 0x601dea3c..0x601df03c; FF-free guards are stock bytes
STEP_LO, STEP_HI = 0x601e3b40, 0x601e3d6c
SEC1, SEC1_SRC = 0x600d7800, 0x40757800
FALSE_POS = {0x60596053: 'a2ec1da0',   # cmp d0,d2; add d3,d0; exthu d1 (instruction bytes, dis-checked)
             0x608ebe15: 'b4ec1da0',   # inside mov (7660,sp),d0 at 0x608ebe14
             0x60324c71: 'f1ec8540',   # mov d3,a0; mov 64,d1 (flash-alias read)
             0x606d9c29: 'ddef1da0'}   # inside mov d0,(0xefdd) at 0x606d9c28 (odd address)


def u16(m, a):
    return struct.unpack_from('<H', m, a - BASE)[0]


def u32(m, a):
    return struct.unpack_from('<I', m, a - BASE)[0]


def s16(m, a):
    return struct.unpack_from('<h', m, a - BASE)[0]


def image(spec, stock):
    im = bytearray(stock)
    for e in spec['edits']:
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            a = int(e['addr'], 16) - BASE; nb = bytes.fromhex(e['new']); im[a:a + len(nb)] = nb
    return bytes(im)


def values(m):
    return [s16(m, VLIST + 2 * i) for i in range(V_FROM, VLIST_N)]


def labels(m):
    """{value: (kind, id, ptr)} for the 40 values: Auto, then kind-5 speed texts."""
    txt = {}
    for i in range(SLOW_N):
        a = SLOW_LIST + 12 * i
        if u16(m, a + 4) == 5:
            txt[struct.unpack_from('<i', m, a - BASE)[0]] = u32(m, a + 8)
    stock_vals = [s16(m, VLIST + 2 * i) for i in range(VLIST_N)]
    for k in range(1, VLIST_N + 1):
        a = II_LIST + 12 * k
        if u32(m, a) != k or u16(m, a + 4) != 1:
            raise SystemExit('item-info speed list not stock')
        txt.setdefault(stock_vals[k - 1], u32(m, a + 8))
    out = {}
    for v in values(m):
        out[v] = (4, STR_AUTO, PAGES[0][2]) if v == 0 else (5, 0, txt[v])
    return out


def text(m, p):
    return m[p - BASE:p - BASE + 12].split(b'\0')[0].decode()


def blob(m):
    """Data block at AT: label list, items copy, then each tree's 8-record D1 array. Returns (bytes, layout)."""
    lab = labels(m)
    vals = values(m)
    if len(vals) != 40 or vals[0] != 0 or vals[1] != 85 or vals[-1] != 3328:
        raise SystemExit(f'1147 list not stock: {vals[:3]}..{vals[-1:]}')
    out = bytearray()
    lay = {'list': AT}
    for v in vals:
        k, i, p = lab[v]
        out += struct.pack('<IHHI', v, k, i, p)
    lay['ok'] = []
    for ptr, n in OKT:
        tbl = m[ptr - BASE:ptr - BASE + 24 * n]
        if any(struct.unpack_from('<IH', tbl, 24 * j)[1] == SID_TV for j in range(n)):
            raise SystemExit('OK table already routes 1147')
        lay['ok'].append(AT + len(out))
        out += tbl + struct.pack('<IHHIIII', 1, SID_TV, 0, 0, 8, PICK_STATE, 0)
    lay['rows'] = []
    for page, rec, cond in PAGES:
        if u32(m, page + 8) != rec or u32(m, page + 16) != (PAGE_N << 16 | PAGE_ID) or u32(m, page + 4) != cond:
            raise SystemExit(f'page {page:#x} not stock')
        rows = m[rec - BASE:rec - BASE + ROW_SZ * PAGE_N]
        if struct.unpack_from('<H', rows, ROW_SZ * (PAGE_N - 1))[0] != LAST_SID:
            raise SystemExit(f'page {page:#x}: ISO-Auto Set is not the last row')
        lay['rows'].append(AT + len(out))
        out += rows + struct.pack('<HHIHHIHHIIII', SID_TV, 40, 40, 4, STR_LABEL, cond, 4, STR_HELP, cond,
                                  lay['list'], 0, lay['list'])
    if u16(m, ROWREC) != 0 or u16(m, ROWREC + 2) != len(ROWS_E1):
        raise SystemExit('E1 row-list record not stock')
    ram = u32(m, ROWREC + 4)
    if [u16(m, ram - DATA_DELTA + 2 * i) for i in range(len(ROWS_E1))] != ROWS_E1:
        raise SystemExit('E1 row list (.data init) not stock')
    rows = ROWS_E1[:ROWS_E1.index(LAST_SID) + 1] + [SID_TV] + ROWS_E1[ROWS_E1.index(LAST_SID) + 1:]
    lay['e1'] = AT + len(out)
    out += struct.pack(f'<{len(rows)}H', *rows)
    out += b'\0' * (-len(out) % 4)
    return bytes(out), lay


def builder(at):
    """+30 = (sid 1147 == 0) ? 0x7eee : sid 1147, ending exactly at BLD_END (movhu d0,(30,a3))."""
    call = 0x60  # placeholder, fixed below
    code = bytearray()
    code += bytes.fromhex('2c6a53')                       # mov 0x536a,d0        (key of sid 1147)
    code += bytes.fromhex('fca0a40b2a62')                 # mov (0x622a0ba4),a0  (its stock registry handle)
    code += b'\x04'                                       # clr d1
    code_call_at = len(code)
    code += b'\xdd\0\0\0\0\xc0\x0c'                       # call 0x6005e971,[d2,d3],12
    code += b'\x1c'                                       # exthu d0
    code += bytes.fromhex('a000')                         # cmp 0,d0
    code += bytes.fromhex('c905')                         # bne +5 (skip the mov)
    code += bytes.fromhex('2cee7e')                       # mov 0x7eee,d0 (Auto: AE's unset value)
    pad = (BLD_END - at) - len(code)
    full = b'\xcb' * pad + code                           # nops first, so the code ends at the stock movhu
    ca = at + pad + code_call_at
    full = bytearray(full)
    full[pad + code_call_at + 1:pad + code_call_at + 5] = struct.pack('<i', PROP - ca)
    del call
    return bytes(full)


def check_free(stock, spec, end):
    import numpy as np
    for e in spec['edits']:
        if e['kind'] == '0x100' and not e['addr'].startswith('off:'):
            a, n = int(e['addr'], 16), len(e['new']) // 2
            if a < end + 16 and AT - 16 < a + n:
                raise SystemExit(f'data block overlaps edit {e["addr"]}')
    d = np.frombuffer(stock, np.uint8).astype(np.int64)
    w = d[:-3] | (d[1:-2] << 8) | (d[2:-1] << 16) | (d[3:] << 24)
    for off in (0, 0x40000000, SEC1_SRC - SEC1):
        lo, hi = (AT - 16 + off) & 0xffffffff, (end + 16 + off) & 0xffffffff
        for i in np.nonzero((w >= lo) & (w < hi))[0]:
            at = int(i) + BASE
            if STEP_LO <= at < STEP_HI and (u32(stock, at) - 0x601de13c) % 0x100 == 0:
                continue
            if at in FALSE_POS and stock[at - BASE:at - BASE + 4].hex() == FALSE_POS[at]:
                continue
            raise SystemExit(f'reference into {AT:#x}..{end:#x} at {at:#x} ({stock[at - BASE:at - BASE + 4].hex()})')


def apply(spec, version='0.30m2'):
    stock = STOCK.read_bytes()
    spec = copy.deepcopy(spec)
    if spec.get('fw_version', {}).get('value') != '0.29a':
        raise SystemExit('base is not v0.29a')
    if any(e.get('source') == SRC for e in spec['edits']):
        raise SystemExit('base already has min_ss edits')
    if stock[BLD - BASE:BLD_END - BASE].hex() != BLD_STOCK:
        raise SystemExit('AE record builder not stock')
    data, lay = blob(stock)
    end = AT + len(data)
    if end > END or any(a % 4 for a in [lay['list'], lay['e1']] + lay['ok'] + lay['rows']):
        raise SystemExit(f'data block {len(data)} B / alignment')
    check_free(stock, spec, end)
    spec = FV.apply(spec, version)
    im = image(spec, stock)
    if im[BLD - BASE:BLD_END - BASE] != stock[BLD - BASE:BLD_END - BASE] or blob(im)[0] != data:
        raise SystemExit('base changed our sources')

    def put(at, new, why):
        exp = im[at - BASE:at - BASE + len(new)]
        for o in spec['edits']:
            if not o['addr'].startswith('off:'):
                oa, on = int(o['addr'], 16), len(o['new']) // 2
                if oa < at + len(new) and at < oa + on:
                    raise SystemExit(f'{at:#x} overlaps edit {o["addr"]}')
        spec['edits'].append(dict(kind='0x100', addr=hex(at), expect=exp.hex(), new=new.hex(), why='min_ss: ' + why, source=SRC))

    put(AT, data, f'data ({len(data)} B, dead EVF gamma tables): 1147 label list (40), 2 OK tables + 1147 -> picker, '
                  'D1 row arrays of both menu trees + "Lowest S/S Setting" row (8 each)')
    for (page, rec, cond), rows in zip(PAGES, lay['rows']):
        put(page + 8, struct.pack('<I', rows), f'D1 page {page:#x} rows -> copy with the Lowest S/S row')
        put(page + 18, struct.pack('<H', PAGE_N + 1), f'D1 page {page:#x} row count 7 -> 8')
    for k in KINDS:
        if u32(im, k + 12) != ITEMS or u32(im, k + 16) != ITEMS_N or [(u32(im, k + 20), u32(im, k + 24)), (u32(im, k + 28), u32(im, k + 32))] != OKT:
            raise SystemExit(f'kind entry {k:#x} not stock')
        put(k + 20, struct.pack('<IIII', lay['ok'][0], OKT[0][1] + 1, lay['ok'][1], OKT[1][1] + 1),
            f'Custom Menu kind {u32(im, k):#x} OK tables -> copies + row 1147 -> state 0x1aa (stock Lowest S/S picker)')
    st = [u32(im, 0x6119a31c + 24 * j + 4 * q) for j in range(429) for q in range(3) if u32(im, 0x6119a31c + 24 * j) == PICK_STATE]
    if st != [PICK_STATE, 5, SID_TV] or u32(im, PICK_LBL) != PICK_IDX or u32(im, PICK_LBL + 8) != PICK_N:
        raise SystemExit('picker state / label table not stock')
    lab = u32(im, PICK_LBL + 12)
    z = [lab + 12 * j for j in range(PICK_N) if u32(im, lab + 12 * j) == 0]
    if len(z) != 1 or u16(im, z[0] + 4) != 5:
        raise SystemExit('picker label for value 0 not stock')
    tvs = {struct.unpack_from('<i', im, lab + 12 * j - BASE)[0] for j in range(PICK_N)}
    if not set(values(im)) <= tvs:
        raise SystemExit('picker labels do not cover the 1147 values')
    put(z[0] + 4, struct.pack('<HHI', 4, STR_AUTO, u32(im, u32(im, PICK_LBL + 4) + 4)),
        'stock Lowest S/S picker: label of value 0 ("1s") -> string 71 "Auto" (0 = Auto)')
    put(ROWREC + 2, struct.pack('<HI', len(ROWS_E1) + 1, lay['e1']),
        f'E1 (Exp/ISO/BULB) column rows: count 4 -> 5, list -> [273, 112, 1147, 143, 35] (adds Lowest S/S under ISO-Auto Set)')
    if u32(im, VREC + 4) != VLIST or u16(im, VREC + 12) != 2 * VLIST_N or u16(im, VREC) != SID_TV:
        raise SystemExit('validator record 1061 not stock')
    put(VREC + 4, struct.pack('<I', VLIST + 2 * V_FROM), 'sid 1147 validator list -> stock list from value 0 (Auto, 1/1.3 .. 1/8000)')
    put(VREC + 12, struct.pack('<H', 2 * (VLIST_N - V_FROM)), 'sid 1147 validator bytes 110 -> 80 (40 values)')
    put(BLD, builder(BLD), 'AE record builder: +30 = (1147 == 0) ? 0x7eee : 1147 (1146 not read; 0 = Auto = stock)')
    spec['min_ss'] = dict(built_by=SRC, test='m4', version=version, data_at=hex(AT), data_end=hex(end), layout={k: (hex(v) if isinstance(v, int) else [hex(x) for x in v]) for k, v in lay.items()},
                          sites=[e['addr'] for e in spec['edits'] if e.get('source') == SRC], sid=SID_TV,
                          labels=[text(stock, p) if kd == 5 else 'Auto' for kd, _, p in labels(stock).values()])
    return spec


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--version', default='0.30m4')
    a = ap.parse_args()
    spec = apply(json.loads(a.spec.read_text()), a.version)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(spec, indent=1))
    print(json.dumps(spec['min_ss']))
