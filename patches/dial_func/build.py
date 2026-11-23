#!/usr/bin/env python3
"""Dial function choices (issue #60): Custom Menu B > Dial Function offers ISO and flash comp on the front dial. Data only.

  .venv/bin/python -I patches/v032/build.py releases/v0.31d/edits.json --out generated/v035c/edits.json --version 0.35c \\
      ... (the v0.35b --extra list, patches/page_wheel/build.py header) ... --extra dial_func=patches/dial_func/build.py

Mechanism [V code, docs/DIAL_FUNC.md]: the four Dial Function popups (screens 8/152..155, sids 70 P, 74 A, 72 S, 76 M) walk
the sid's validator record (type 6, 64-B elements {u32 main/rear fn, u32 sub/front fn, 0 x 14}) and its alt list of GUI codes
(0x604ade64: P {11, 1}, A {12, 5}, S {13, 9}, M {4, 8}). Set / get map code <-> element generically over bytes / elem
(0x602b9deb, 0x602b9e7e, 0x602b9f26). The popup's view (create 0x60e95999) labels each column from its record in the table
0x611d714c (20 B: u16 param, u16 count, title, list1 = rear labels, list2 = front labels, guide) by code (0x60df250b).
The dial routine 0x60cdc82c already handles fn 6 (ISO: its own branches 0x60cdc976 / 0x60cdca2c, the one mdial uses on
camera) and fn 17 (flash comp: rule table 0x60f38dd4 {86:68, 2:69, 4:70, 3:71, 17:72}, generic step of sid 17).

Edits: one 1472-B data block in a sec-5 dead `sdk api` claim (new element lists, alt lists, label lists); per mode the
validator record's list / alt / byte count (128 -> 256) and the view record's count (2 -> 4) / list1 / list2.
Each mode keeps its two current entries (read from the image, so mdial's M entry {Shutter, Exp comp} is kept) and adds
{rear stays, front ISO} and {rear stays, front flash comp}. Unknown codes fall back to index 0 (0x602b9f26).
"""
import argparse, copy, importlib.util, json, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = 'patches/dial_func'


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


JA = _load('ep7_ja_build_df', ROOT / 'patches/i18n_ja/build.py')
ST, BASE, STOCK = JA.ST, JA.BASE, JA.STOCK

CLAIM = (0x607deb00, 0x607df100)          # 1536 B in the dead sdk-api handlers; no outside reference into it on v0.35b (JA.check_claim)
GUARD = 16
AT = CLAIM[0] + GUARD
VREC = 0x604cc98c                          # validator, 1333 x 20 B
VIEW = 0x611d714c                          # view-56 records, 20 B, param 0..9
TEXT = 0x611d6bb8                          # the text word every stock kind-4 entry of these lists carries
ISO, FEC = 6, 17                           # dial function = target sid: 6 ISO, 17 flash comp
LABEL = {ISO: 153, FEC: 525}               # 'ISO', '@A00A@' (the flash-comp icon of Shooting Menu 2 row 17)
# mode: (param, sid, validator record, stock list, stock alt, rear fn, rear label, new codes)
MODES = {'P': (0, 70, 0x604ccd38, 0x604bb2bc, 0x604ade64, 86, 1716, (40, 41)),
         'A': (1, 74, 0x604ccd4c, 0x604bb33c, 0x604ade6c, 3, 659, (42, 43)),
         'S': (2, 72, 0x604ccd60, 0x604bb3bc, 0x604ade74, 4, 660, (44, 45)),
         'M': (3, 76, 0x604ccd74, 0x604bb43c, 0x604ade7c, 4, 660, (46, 47))}
STOCK_CODES = {'P': (11, 1), 'A': (12, 5), 'S': (13, 9), 'M': (4, 8)}
N = 4
ELEM = 64


def u16(b, a):
    return struct.unpack_from('<H', b, a - BASE)[0]


def u32(b, a):
    return struct.unpack_from('<I', b, a - BASE)[0]


def spans_of(spec):
    return [(int(e['addr'], 16), int(e['addr'], 16) + len(e['new']) // 2) for e in spec['edits']
            if e['kind'] == '0x100' and not e['addr'].startswith('off:')]


def build_block(im):
    """-> (block bytes, {mode: (elems at, alt at, list1 at, list2 at)})"""
    blk = bytearray()
    at = {}
    for m, (p, sid, rec, lst, alt, rear, rl, new) in MODES.items():
        cur = im[lst - BASE:lst - BASE + 2 * ELEM]
        el = bytearray(cur)
        for fn in (ISO, FEC):
            e = bytearray(ELEM)
            struct.pack_into('<II', e, 0, rear, fn)
            el += e
        at[m] = [AT + len(blk)]
        blk += el
    for m, (p, sid, rec, lst, alt, rear, rl, new) in MODES.items():
        at[m].append(AT + len(blk))
        blk += struct.pack('<4I', *STOCK_CODES[m], *new)
    for m, (p, sid, rec, lst, alt, rear, rl, new) in MODES.items():
        vr = VIEW + 20 * p
        for col in (0, 1):
            old = u32(im, vr + 8 + 4 * col)
            at[m].append(AT + len(blk))
            blk += im[old - BASE:old - BASE + 24]                        # the two current entries, as the image has them
            for code, fn in zip(new, (ISO, FEC)):
                blk += struct.pack('<IHHI', code, 4, rl if col == 0 else LABEL[fn], TEXT)
    return bytes(blk), at


def check(im, stock):
    for m, (p, sid, rec, lst, alt, rear, rl, new) in MODES.items():
        if im[rec - BASE:rec - BASE + 20] != stock[rec - BASE:rec - BASE + 20]:
            raise SystemExit(f'{m}: validator record {rec:#x} already edited')
        s, attr, l, a, nb, el, sub, typ = struct.unpack_from('<HHIIHHBB', stock, rec - BASE)
        if (s, l, a, nb, el, typ) != (sid, lst, alt, 2 * ELEM, ELEM, 6):
            raise SystemExit(f'{m}: validator record {rec:#x} not as studied')
        if tuple(struct.unpack_from('<2I', im, alt - BASE)) != STOCK_CODES[m]:
            raise SystemExit(f'{m}: alt list {alt:#x} not as studied')
        vr = VIEW + 20 * p
        if im[vr - BASE:vr - BASE + 20] != stock[vr - BASE:vr - BASE + 20] or u16(stock, vr) != p or u16(stock, vr + 2) != 2:
            raise SystemExit(f'{m}: view record {vr:#x} edited or not as studied')
        for col in (0, 1):
            lab = u32(stock, vr + 8 + 4 * col)
            codes = [u32(im, lab + 12 * i) for i in range(2)]
            if sorted(codes) != sorted(STOCK_CODES[m]) or any(u32(im, lab + 12 * i + 8) != TEXT for i in range(2)):
                raise SystemExit(f'{m}: label list {lab:#x} not as studied')
        el = im[lst - BASE:lst - BASE + 2 * ELEM]
        for i in range(2):
            w = struct.unpack_from('<16I', el, ELEM * i)
            if any(w[2:]) or w[0] != rear and w[1] != rear and m != 'M':
                raise SystemExit(f'{m}: element {i} {w[:2]} not as studied')
        if set(new) & set(STOCK_CODES[m]):
            raise SystemExit('code clash')
    # stock control-flow facts the layer relies on (no code edited, but refuse a different firmware)
    if stock[0x60cdc976 - BASE:0x60cdc978 - BASE] != bytes.fromhex('bf06'):
        raise SystemExit('ISO branch of the dial routine not at 0x60cdc976')
    if struct.unpack_from('<10I', stock, 0x60f38dd4 - BASE) != (86, 68, 2, 69, 4, 70, 3, 71, 17, 72):
        raise SystemExit('dial rule table 0x60f38dd4 not as studied')
    if u32(stock, 0x60e959e9) != VIEW:
        raise SystemExit('view create does not read 0x611d714c')


def apply(spec, version='0.35c'):
    stock = STOCK.read_bytes()
    spec = copy.deepcopy(spec)
    if 'dial_func' in spec:
        raise SystemExit('dial_func already applied')
    if 'extras_pages' not in spec:
        raise SystemExit('needs extras_pages (the sdk sub-command cut that makes the claim dead)')
    im = ST.img_of(spec, stock)
    check(im, stock)
    JA.check_claim(spec, stock, im, CLAIM)
    blk, at = build_block(im)
    if AT + len(blk) > CLAIM[1] - GUARD:
        raise SystemExit(f'{len(blk)} B does not fit')
    sp = spans_of(spec)
    edits = [dict(kind='0x100', addr=hex(AT), expect=stock[AT - BASE:AT - BASE + len(blk)].hex(), new=blk.hex(), source=SRC,
                  why=f'dial_func {version}: element / alt / label lists ({len(blk)} B; sec-5 dead sdk-api handlers, '
                      f'claim {CLAIM[0]:#x}..{CLAIM[1]:#x})')]
    for m, (p, sid, rec, lst, alt, rear, rl, new) in MODES.items():
        ea, aa, l1, l2 = at[m]
        r = stock[rec + 4 - BASE:rec + 14 - BASE]
        nr = struct.pack('<IIH', ea, aa, N * ELEM)
        edits.append(dict(kind='0x100', addr=hex(rec + 4), expect=r.hex(), new=nr.hex(), source=SRC,
                          why=f'dial_func {version}: validator sid {sid} (Dial {m}) list {lst:#x} -> {ea:#x}, '
                              f'alt {alt:#x} -> {aa:#x}, 128 -> {N * ELEM} B'))
        vr = VIEW + 20 * p
        edits.append(dict(kind='0x100', addr=hex(vr + 2), expect=stock[vr + 2 - BASE:vr + 4 - BASE].hex(),
                          new=struct.pack('<H', N).hex(), source=SRC, why=f'dial_func {version}: Dial {m} view count 2 -> {N}'))
        edits.append(dict(kind='0x100', addr=hex(vr + 8), expect=stock[vr + 8 - BASE:vr + 16 - BASE].hex(),
                          new=struct.pack('<II', l1, l2).hex(), source=SRC,
                          why=f'dial_func {version}: Dial {m} label lists -> {l1:#x} / {l2:#x}'))
    for e in edits:
        a, n = int(e['addr'], 16), len(e['new']) // 2
        if any(x < a + n and a < y for x, y in sp):
            raise SystemExit(f'{e["addr"]}: already edited by another layer')
    spec['edits'] += edits
    spec['dial_func'] = dict(built_by=SRC, version=version, claim=[hex(CLAIM[0]), hex(CLAIM[1])], block=[hex(AT), len(blk)],
                             modes={m: dict(sid=MODES[m][1], elems=hex(v[0]), alt=hex(v[1]), labels=[hex(v[2]), hex(v[3])],
                                            codes=list(STOCK_CODES[m]) + list(MODES[m][7])) for m, v in at.items()},
                             added='front dial ISO (6), flash comp (17); rear dial unchanged')
    return spec


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--version', default='0.35c')
    a = ap.parse_args()
    spec = apply(json.loads(a.spec.read_text()), a.version)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(spec, indent=1))
    print(json.dumps(spec['dial_func']))
