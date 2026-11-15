#!/usr/bin/env python3
"""Write / check the look-picker card files EP7MOD/LOOKS.BIN and EP7MOD/SLOTS.BIN (offline desktop tool, no camera).

  .venv/bin/python -I tools/ep7_looks_bin.py bundles/library_v1.json --out generated/look_picker/card
      -> <out>/EP7MOD/LOOKS.BIN (and SLOTS.BIN with --slots COLOR1=velvia,MONO2=stock,...)
  .venv/bin/python -I tools/ep7_looks_bin.py --check <dir>/EP7MOD/LOOKS.BIN [--slots-file <dir>/EP7MOD/SLOTS.BIN]

Design: docs/LOOK_PICKER.md. The looks come from the same library JSON as tools/ep7_library.py (LIBRARY.BIN
v2): same recipes, same names, same canonical bundle and the same placement rule P(look, slot). LOOKS.BIN is the
compact v3 form the camera keeps in one heap block (at most 32 looks; v0.15: a class-2 block, was 20 in one 2048-B block):

  header 64 B: 'EP7B', u16 version 3, u16 64, u32 1100, u32 payload (= 64 n), u32 CRC-32 (zlib over bytes 0..15
               then 20..end, the v1 rule), SHA prefix of the decoded main (4 B), u16 n (1..32), u16 64,
               u32 layout_crc (tools/ep7_library.layout_crc), 32 zero bytes
  record 64 B: +0..44 canonical bundle bytes 0..44 (layout.json ABI; bundle bytes 46..63 are always 0),
               +45 class (0 colour, 1 mono), +46 slot mask (bit0 COLOR, bit1 MONO; colour 1 or 3, mono 2),
               +47 bloom_tint 0..4 (test13b; placed at bundle +45; 0 in older files), +48 name[16] (1..15 printable ASCII except '@', NUL-padded, byte 15 NUL)
  v0.32 split toning (still version 3, same size): names are at most 12 characters, so the name ends by +60 and
               +61 Shadows / +62 Highlights carry the slot +62/+63 packing (low nibble colour 0..11, high nibble
               strength s4 -5..5; 0 = none). A Film pick copies them to the profile's slot +62/+63 (0 clears).
               Firmware before v0.32 rejects a record with +61/+62 non-zero (bytes after the name's NUL).
  v0.34e base curve and colour mix (version 4, docs/LOOK_FORMAT_V4.md): header +4 = 4, +32 u32 CRC-32 (zlib) of the
               extension, +36 u16 16; after the n v3 records, n 16-byte extension records in the same order: +0 curve
               (slot +53: 0 the camera's own, 1.. = CURVES index + 1), +1..+6 matrix s8 -64..64 (slot +54..+59), +7..+15 0.
               The +16 CRC is the v3 rule over the v3 part (bytes 0..15, then 20..63+64n) as the file has it. Written only
               with --fw 0.34 or later and only when a look sets curve or matrix; otherwise v3 byte for byte. A Film pick
               (looks_v4 firmware) copies the curve and matrix to slot +53..+59 and clears +60. Older firmware rejects v4.
  v0.19 look tone (still version 3, same size): a COLOR look with "tone" in the library has +32 = 1 (tone flag),
               +33 Blacks, +34 Whites (s8 -5..5), +35 Highlights, +36 Midtones, +37 Shadows (s8 -7..7), +38..44 = 0,
               and slot mask 1 (COLOR only: +33..44 no longer hold MONO saturation advice). A Film pick (v0.19
               firmware) puts Blacks/Whites in slot +47/+48 and sets the profile's stock H/M/S settings; older
               firmware and records with +32 = 0 ignore it. The camera range for +35..37 is -7..7.

SLOTS.BIN (20 B) is what the camera writes back when the picker changes a slot (and what it reads at power-on):
  'EP7S', u32 LOOKS.BIN CRC (binds the map to one library), assign[8] (COLOR1-4, MONO1-4: 0..n-1 = look,
  0xFF = stock (all-zero entry), 0xFE = untouched (keep BUNDLES.BIN's slot)), u32 CRC-32 (zlib) of bytes 0..15.
An invalid assign byte is treated as 0xFE by the camera; a bad SLOTS.BIN is ignored as a whole.
Never writes into DCOLYMP/ and never writes an SD-update name.
"""
import argparse, importlib.util, json, struct, sys, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


LIB = _load('ep7_library', ROOT / 'tools/ep7_library.py')
SB = LIB.SB
MAGIC, VERSION, HDR_LEN, REC_LEN, MAX_LOOKS = b'EP7B', 3, 64, 64, 32
# v4 (looks_v4, firmware v0.34e): the extension after the v3 part
VERSION4, EXT_LEN, EXT_CRC_OFF, EXT_LEN_OFF, EXT_USED = 4, 16, 32, 36, 7
CURVES = ('standard', 'auto', 'pale', 'light', 'pop', 'flat', 'log')   # slot +53 = index + 1 (0 = the camera's own)
MATRIX_MAX = 64
V4_FW = (0, 34)                                                       # first firmware that reads v4: v0.34
BUNDLE_USED = 45
CLASS_OFF, MASK_OFF, NAME_OFF, NAME_LEN = 45, 46, 48, 16
# test13b: record +47 = bloom_tint (0..4; old files have 0 = neutral), placed at bundle byte +45 (layout.json bloom_tint)
TINT_OFF, TINT_BUNDLE, TINT_MAX = 47, 45, 4
TONE_FLAG, TONE_OFF, TONE_KEYS = 32, 33, ('blacks', 'whites', 'highlights', 'midtones', 'shadows')
TONE_RANGE = {33: (-5, 10), 34: (-5, 10), 35: (-7, 14), 36: (-7, 14), 37: (-7, 14)}   # +off: (lo, span)
# v0.24: a tone record carries sat[12] as nibbles at +38..43 (low first, two's complement) with marker +44 = 1; a Film
# pick sets the profile's stock saturation from it. Older firmware rejects such a file.
SAT_OFF, SAT_MARK = 38, 44
SAT_RANGE = {o: (-128, 255) for o in range(38, 44)}             # +44 keeps -5..5: marker only counts with the tone flag
SMAGIC, SLOTS_LEN = b'EP7S', 20
STOCK, UNTOUCHED = 0xFF, 0xFE
PATH_LOOKS, PATH_SLOTS = 'C:\\EP7MOD\\LOOKS.BIN', 'C:\\EP7MOD\\SLOTS.BIN'
SLOTS = LIB.SLOTS


def header(n, crc=0, ext_crc=None):
    """v3 header, or v4 (version 4, +32 extension CRC, +36 extension record length) when ext_crc is given."""
    h = MAGIC + struct.pack('<HHII', VERSION if ext_crc is None else VERSION4, HDR_LEN, SB.FW_BUILD, REC_LEN * n) + struct.pack('<I', crc)
    h += SB.SHA_PREFIX + struct.pack('<HHI', n, REC_LEN, LIB.layout_crc())
    if ext_crc is not None:
        h += struct.pack('<IH', ext_crc, EXT_LEN)
    return h + bytes(HDR_LEN - len(h))


def ext_record(curve=None, matrix=None):
    """The shared look fields -> the 16-byte v4 extension record (+0 slot +53, +1..+6 slot +54..+59)."""
    e = bytearray(EXT_LEN)
    if curve is not None:
        if curve not in CURVES:
            raise ValueError(f'curve {curve!r}: one of {", ".join(CURVES)}')
        e[0] = CURVES.index(curve) + 1
    if matrix is not None:
        if not isinstance(matrix, list) or len(matrix) != 6 or not all(
                isinstance(v, int) and not isinstance(v, bool) and -MATRIX_MAX <= v <= MATRIX_MAX for v in matrix):
            raise ValueError(f'matrix: 6 integers in -{MATRIX_MAX}..{MATRIX_MAX}')
        e[1:7] = struct.pack('<6b', *matrix)
    return bytes(e)


def ext_of(data, j):
    """-> (curve name or None, matrix list or None) of look j of a v4 file (None, None for v3)."""
    if not is_v4(data):
        return None, None
    n = struct.unpack_from('<H', data, 24)[0]
    e = data[HDR_LEN + REC_LEN * n + EXT_LEN * j:][:EXT_LEN]
    m = list(struct.unpack('<6b', e[1:7]))
    return (CURVES[e[0] - 1] if e[0] else None), (m if any(m) else None)


def is_v4(data):
    return len(data) >= 6 and struct.unpack_from('<H', data, 4)[0] == VERSION4


def fw_tuple(s):
    """'0.34', '0.34e', 'v0.34' -> (0, 34); None -> None."""
    if s is None:
        return None
    import re
    m = re.fullmatch(r'v?(\d+)\.(\d+)[a-z]?\d*', s.strip())
    if not m:
        raise ValueError(f'--fw {s!r}: like 0.34')
    return int(m.group(1)), int(m.group(2))


def record(rec96):
    """LIBRARY v2 96-byte record -> 64-byte LOOKS.BIN record."""
    b = rec96[:64]
    if any(b[TINT_BUNDLE + 1:]):
        raise ValueError('canonical bundle uses bytes 46..63 (layout.json grew: LOOKS.BIN v3 must be revised)')
    name = rec96[LIB.NAME_OFF:LIB.NAME_OFF + 16]
    return bytes(b[:BUNDLE_USED]) + bytes([rec96[LIB.CLASS_OFF], rec96[LIB.MASK_OFF], b[TINT_BUNDLE]]) + name


def to_rec96(rec64):
    """Back to the v2 form (for LIB.place())."""
    r = bytearray(LIB.LOOK_LEN)
    r[:BUNDLE_USED] = rec64[:BUNDLE_USED]
    r[TINT_BUNDLE] = rec64[TINT_OFF]
    r[LIB.NAME_OFF:LIB.NAME_OFF + 16] = rec64[NAME_OFF:NAME_OFF + 16]
    r[LIB.CLASS_OFF], r[LIB.MASK_OFF] = rec64[CLASS_OFF], rec64[MASK_OFF]
    return bytes(r)


def has_tone(rec64):
    return rec64[CLASS_OFF] == 0 and rec64[TONE_FLAG] == 1


def tone_of(rec64):
    """-> dict blacks/whites/highlights/midtones/shadows, or None (no tone: a pick leaves tone alone)."""
    if not has_tone(rec64):
        return None
    return {k: (v - 256 if v >= 128 else v) for k, v in zip(TONE_KEYS, rec64[TONE_OFF:TONE_OFF + 5])}


def with_tone(rec64, tone):
    """COLOR record + library tone dict -> record with the tone block (+32 flag, +33..37, mask 1)."""
    if rec64[CLASS_OFF] != 0:
        raise ValueError('tone block: COLOR looks only')
    if set(tone) - set(TONE_KEYS):
        raise ValueError(f'tone: unknown keys {sorted(set(tone) - set(TONE_KEYS))}')
    r = bytearray(rec64)
    sat = [v - 256 if v >= 128 else v for v in r[33:45]]          # the look's sat[12], still in the bundle bytes
    r[TONE_FLAG:BUNDLE_USED] = bytes(BUNDLE_USED - TONE_FLAG)
    r[TONE_FLAG] = 1
    for i, v in enumerate(sat):
        if not -5 <= v <= 5:
            raise ValueError(f'sat[{i}] = {v} outside -5..5')
        r[SAT_OFF + i // 2] |= (v & 15) << (4 * (i & 1))
    r[SAT_MARK] = 1
    for i, k in enumerate(TONE_KEYS):
        v = tone.get(k, 0)
        lo, sp = TONE_RANGE[TONE_OFF + i]
        if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= lo + sp:
            raise ValueError(f'tone {k} = {v!r} outside {lo}..{lo + sp}')
        r[TONE_OFF + i] = v & 0xff
    r[MASK_OFF] = 1
    return bytes(r)


def place(rec64, k):
    """P(look, slot k) -> 64-byte table entry (raises if the look may not go in that slot). v0.19: a tone record
    puts its Blacks/Whites at entry +47/+48 (its H/M/S go to the profile's stock settings, not the entry)."""
    e = bytearray(LIB.place(to_rec96(rec64), SLOTS[k]))
    if k < 4 and has_tone(rec64):
        e[47], e[48] = rec64[TONE_OFF], rec64[TONE_OFF + 1]
    return bytes(e)


def allowed(rec64, k):
    return bool(rec64[MASK_OFF] & (1 if k < 4 else 2))


def make_file(recs, exts=None):
    """v3 file, or v4 with exts (one 16-byte extension record per look)."""
    n = len(recs)
    if not 1 <= n <= MAX_LOOKS:
        raise ValueError(f'LOOKS.BIN holds 1..{MAX_LOOKS} looks (the camera L block, film_menu_v2 MAX_LOOKS), got {n}')
    body = b''.join(recs)
    ext, ec = b'', None
    if exts is not None:
        if len(exts) != n or any(len(e) != EXT_LEN for e in exts):
            raise ValueError('v4: one 16-byte extension record per look')
        ext = b''.join(exts)
        ec = zlib.crc32(ext) & 0xffffffff
    raw = header(n, 0, ec) + body
    crc = zlib.crc32(raw[:16] + raw[20:]) & 0xffffffff
    return header(n, crc, ec) + body + ext


def compile_looks(cfg, fw=None):
    """Library JSON (tools/ep7_library.py input) -> (LOOKS.BIN bytes, look keys, names). fw (e.g. (0, 34)): the firmware
    the file is for; v0.34 or later and a look with curve / matrix -> v4, else v3 (curve / matrix left out)."""
    recipes = LIB.BB.load_recipes()
    cfg = dict(cfg)
    cfg.pop('slots', None)
    looks = dict(cfg.get('looks', {}))
    inc = cfg.get('include_recipes', [])
    inc = list(recipes) if inc == 'all' else inc
    for r in inc:
        looks.setdefault(r, {'recipe': r})
    recs, keys, names, exts = [], [], [], []
    for k, v in looks.items():
        tone = v.get('tone') if isinstance(v, dict) else None
        hw = {kk: v[kk] for kk in ('curve', 'matrix') if isinstance(v, dict) and kk in v}
        if tone is not None or hw:
            v = {kk: vv for kk, vv in v.items() if kk not in ('tone', 'curve', 'matrix')}
        r96, meta = LIB.look_record(k, v, recipes)
        r = record(r96)
        if tone is not None and r[CLASS_OFF] == 0:       # mono looks: the Film page never places them; no block
            r = with_tone(r, tone)
        try:
            e = ext_record(hw.get('curve'), hw.get('matrix'))
        except ValueError as ex:
            raise ValueError(f'look {k}: {ex}')
        if any(e) and r[CLASS_OFF] != 0:
            raise ValueError(f'look {k}: curve / matrix are COLOR-only (the Film page places colour looks only)')
        recs.append(r)
        exts.append(e)
        keys.append(k)
        names.append(meta['name'])
    v4 = fw is not None and fw >= V4_FW and any(any(e) for e in exts)
    if any(any(e) for e in exts) and not v4:
        print(f'note: curve / matrix left out (LOOKS.BIN v4 needs --fw 0.34 or later)', file=sys.stderr)
    data = make_file(recs, exts if v4 else None)
    probs = check_file(data)
    if probs:
        raise ValueError(f'built LOOKS.BIN fails the camera rules: {probs}')
    return data, keys, names


def file_crc(data):
    return struct.unpack_from('<I', data, 16)[0]


def make_slots(lib_crc, assign):
    if len(assign) != 8 or not all(0 <= a <= 255 for a in assign):
        raise ValueError('assign: 8 bytes')
    b = SMAGIC + struct.pack('<I', lib_crc) + bytes(assign)
    return b + struct.pack('<I', zlib.crc32(b) & 0xffffffff)


SPLIT_SH, SPLIT_HL = 61, 62                                     # v0.32: record +61/+62 (name bytes 13/14)


def split_ok(b):
    """One split byte as v0.32 fm_load (ls_sc) and the split_tone reader check it."""
    return (b & 15) < 12 and (((b >> 4) + 5) & 15) < 11


def _name_ok(nm, split=True):
    """Camera rule: first byte non-zero, 0..15 chars 0x20..0x7e except '@', then NUL to byte 15. split (v0.32): with the
    name ended by byte 12, bytes 13/14 may carry split toning (each split_ok)."""
    if len(nm) != 16 or nm[0] == 0 or nm[15] != 0:
        return False
    if split and nm[12] == 0 and (nm[13] or nm[14]):
        if not (split_ok(nm[13]) and split_ok(nm[14])):
            return False
        nm = bytes(nm[:13]) + b'\0\0\0'
    seen = False
    for c in nm:
        if c == 0:
            seen = True
        elif seen or c == 0x40 or not 0x20 <= c <= 0x7e:
            return False
    return True


def check_ext(data):
    """v4 extension as looks_v4 (lx_ext) checks it -> problems. The camera then loads the looks without curve / matrix."""
    n = struct.unpack_from('<H', data, 24)[0]
    ext = data[HDR_LEN + REC_LEN * n:]
    p = []
    if zlib.crc32(ext) & 0xffffffff != struct.unpack_from('<I', data, EXT_CRC_OFF)[0]:
        return ['extension crc']
    for j in range(n):
        e = ext[EXT_LEN * j:EXT_LEN * (j + 1)]
        if e[0] > len(CURVES) or any(not -MATRIX_MAX <= v <= MATRIX_MAX for v in struct.unpack('<6b', e[1:7])) or any(e[EXT_USED:]):
            p.append(f'look {j} extension out of range')
    return p


def check_file(data, split=True):
    """Python mirror of the camera's pk_check -> list of problems (empty = accepted). split=False: firmware before v0.32.
    v4 (looks_v4): the v4 header and the extension are checked too, then the v3 part as v3."""
    p = []
    if is_v4(data):
        n = struct.unpack_from('<H', data, 24)[0] if len(data) >= 26 else 0
        if not 1 <= n <= MAX_LOOKS or len(data) != HDR_LEN + (REC_LEN + EXT_LEN) * n:
            return [f'v4 size {len(data)}']
        v3 = data[:HDR_LEN + REC_LEN * n]
        want = header(n, 0, struct.unpack_from('<I', data, EXT_CRC_OFF)[0])
        if v3[:16] != want[:16] or v3[20:HDR_LEN] != want[20:HDR_LEN]:
            return ['header']
        if zlib.crc32(v3[:16] + v3[20:]) & 0xffffffff != file_crc(v3):
            return ['crc']
        h = bytearray(header(n))                          # the firmware's v3 view of the file (lx_hdr)
        body = v3[HDR_LEN:]
        struct.pack_into('<I', h, 16, zlib.crc32(bytes(h[:16]) + bytes(h[20:]) + body) & 0xffffffff)
        return check_ext(data) + check_file(bytes(h) + body, split)
    size = len(data)
    if size < HDR_LEN + REC_LEN or size > HDR_LEN + REC_LEN * MAX_LOOKS or size % REC_LEN:
        return [f'size {size}']
    n = (size - HDR_LEN) // REC_LEN
    want = header(n)
    if data[:16] != want[:16] or data[20:HDR_LEN] != want[20:HDR_LEN]:
        p.append('header')
    if zlib.crc32(data[:16] + data[20:]) & 0xffffffff != file_crc(data):
        p.append('crc')
    lo, span, _ = SB.range_table(SB.layout())
    lo, span = list(lo), list(span)
    for o, (l, sp) in {**TONE_RANGE, **SAT_RANGE}.items():  # v0.19 / v0.24 camera table (fm_check)
        lo[o], span[o] = l, sp
    for j in range(n):
        r = data[HDR_LEN + REC_LEN * j:HDR_LEN + REC_LEN * (j + 1)]
        for k in range(BUNDLE_USED):
            v = r[k] - 256 if r[k] >= 128 else r[k]
            if not 0 <= v - lo[k] <= span[k]:
                p.append(f'look {j} byte {k} = {v} out of range')
                break
        cls, mask = r[CLASS_OFF], r[MASK_OFF]
        if not (cls == 0 and mask in (1, 3) or cls == 1 and mask == 2) or r[TINT_OFF] > TINT_MAX:
            p.append(f'look {j} class/mask/tint {cls}/{mask}/{r[TINT_OFF]}')
        if not _name_ok(r[NAME_OFF:NAME_OFF + 16], split):
            p.append(f'look {j} name')
    return p


def check_slots(slots, looks):
    """-> (valid, effective assign[8]) as the camera derives it (0xFE for anything it would not apply)."""
    if len(slots) < SLOTS_LEN or slots[:4] != SMAGIC or struct.unpack_from('<I', slots, 4)[0] != file_crc(looks) or \
            zlib.crc32(slots[:16]) & 0xffffffff != struct.unpack_from('<I', slots, 16)[0]:
        return False, [UNTOUCHED] * 8
    n = n_looks(looks)
    out = []
    for k in range(8):
        a = slots[8 + k]
        if a == STOCK:
            out.append(STOCK)
        elif a < n and allowed(looks[HDR_LEN + REC_LEN * a:HDR_LEN + REC_LEN * (a + 1)], k):
            out.append(a)
        else:
            out.append(UNTOUCHED)
    return True, out


def rec(looks, j):
    return looks[HDR_LEN + REC_LEN * j:HDR_LEN + REC_LEN * (j + 1)]


def n_looks(looks):
    return struct.unpack_from('<H', looks, 24)[0] if is_v4(looks) else (len(looks) - HDR_LEN) // REC_LEN


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('library', nargs='?', type=Path)
    ap.add_argument('--out', type=Path)
    ap.add_argument('--slots', help='write SLOTS.BIN too: COLOR1=<look key>|stock,... (others untouched)')
    ap.add_argument('--check', type=Path)
    ap.add_argument('--slots-file', type=Path)
    ap.add_argument('--fw', help='firmware the file is for, e.g. 0.34: v0.34 or later writes v4 when a look sets curve / matrix')
    a = ap.parse_args()
    try:
        if a.check:
            data = a.check.read_bytes()
            probs = check_file(data)
            print('LOOKS.BIN', f'v{VERSION4 if is_v4(data) else VERSION}', 'OK' if not probs else f'REJECTED {probs}')
            if not probs:
                n = n_looks(data)
                for j in range(n):
                    r = rec(data, j)
                    cv, mx = ext_of(data, j)
                    print(f'  {j:2d} {r[NAME_OFF:NAME_OFF + 16].split(b"\0")[0].decode():15s} '
                          f'{"mono" if r[CLASS_OFF] else "colour"} slots {"C" if r[MASK_OFF] & 1 else "-"}{"M" if r[MASK_OFF] & 2 else "-"}'
                          + (f' curve {cv}' if cv else '') + (f' matrix {mx}' if mx else ''))
            if a.slots_file:
                ok, eff = check_slots(a.slots_file.read_bytes(), data)
                print('SLOTS.BIN', 'OK' if ok else 'IGNORED', eff)
            sys.exit(1 if probs else 0)
        if not a.library or not a.out:
            ap.error('library and --out are required (or --check)')
        data, keys, names = compile_looks(json.loads(a.library.read_text()), fw_tuple(a.fw))
        if 'DCOLYMP' in str(a.out).upper():
            raise ValueError('refusing to write into DCOLYMP/')
        d = a.out / 'EP7MOD'
        d.mkdir(parents=True, exist_ok=True)
        (d / 'LOOKS.BIN').write_bytes(data)
        print(f'LOOKS.BIN v{VERSION4 if is_v4(data) else VERSION} {len(data)} B, {len(keys)} looks: ' + ', '.join(names))
        if a.slots:
            assign = [UNTOUCHED] * 8
            for item in a.slots.split(','):
                s, v = item.split('=')
                k = SLOTS.index(s.strip())
                if v.strip() == 'stock':
                    assign[k] = STOCK
                else:
                    j = keys.index(v.strip())
                    if not allowed(rec(data, j), k):
                        raise ValueError(f'{v} cannot go in {s}')
                    assign[k] = j
            (d / 'SLOTS.BIN').write_bytes(make_slots(file_crc(data), assign))
            print('SLOTS.BIN', assign)
    except ValueError as e:
        sys.exit(f'error: {e}')


if __name__ == '__main__':
    main()
