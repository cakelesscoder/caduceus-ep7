#!/usr/bin/env python3
"""v0.33b fixes over the v0.33a chain (bugs only, no feature). Offline. Layer it with --extra after crash_log:

  .venv/bin/python -I patches/v032/build.py releases/v0.31d/edits.json --out generated/v033b/edits.json --version 0.33b \\
      --extra grain_g2=patches/grain_g2/build.py --extra halation_h6=patches/halation_h6/build.py \\
      --extra crash_log=patches/crash_log/build.py --extra clean_boot=patches/clean_boot/build.py --extra v033b=patches/v033b/build.py

The two other v0.33b fixes live in their own layers, which the chain rebuilds: patches/crash_log (cl_gate, the NMI hook's
section-1 test) and patches/i18n_zh (the section-7 test at the head of the Colour Profile guide chain). This layer amends edits
of layers that are baked into releases/v0.31d/edits.json, so it cannot live in them:

  E  exif_name (docs/RE_BOOT_MEMORY.md "Follow-up"): the capture-setup call 0x6030288d (section 2) reached ex_get in section 7
     with no test. Its rel32 now points at ex_gate (19 B, section 1: r2 bytes that grain_g2 lists as unused, as crash_log does):
     `btst 64,(0xa272e420)` (bit 6 = section 7 copied, section_load 0x600457e7); clear -> `jmp 0x6005e971`, the call's stock
     target (no name, stock blanks); set -> `jmp ex_get` as before. Only PSW differs from stock on the stock path.
  T  rec_limit (docs/RE_MOVIE.md section 4.3): the remaining-time estimate 0x603183a9 clamps its seconds term with
     `mov 1740,d1` at 0x603185e3, the stock 29-min cap that rec_limit raised to 32400 s at 0x60319157 / 0x6031915c. imm16
     0x603185e4 1740 -> 32400 (fits the signed imm16; the products after it are 64-bit, 0x600dbc2f / 0x600dbec4).
  M  min_ss (docs/MIN_SHUTTER.md, docs/RE_MENUS.md "Follow-up"): the "count 7 -> 8" edits at 0x61160fc2 / 0x6117ea5e are the
     n of the D2 letter entry ({u16 id, u16 n, label 8 B, u32 rows, u32 help}, reader 0x60e1060c), not D1's. Dropped: D2 is
     stock again. D1 keeps its stock n = 8 and reads min_ss's record copy (7 stock rows + the 1147 row in place of 239).
  S  sharp_off (docs/RE_PLAYBACK.md section 5): RAW Data Edit reads Sharpness (0x8119) at its own getter call 0x60c6707b, the
     same `mov 0x8119,d0; mov 0,a0; clr d1; call 0x6005e971,[d2,d3],12; movhu d0,(24010,cap)` as the capture site 0x602a7eda
     that sharp_off sends to sh_get. Its rel32 -> sh_get too (section 1, called from section 6). sh_get keys on the current
     profile (sc_slot, global 0x9481 / 0xF6B1), as exif_name and WB do on this path. NR and WB stay as patches/v025 and
     patches/wb left them.
"""
import argparse, copy, hashlib, importlib.util, json, re, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SRC = 'patches/v033b'


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


CL = _load('crash_log_build_v033b', ROOT / 'patches/crash_log/build.py')
ST, KH, B3 = CL.ST, CL.KH, CL.B3
BASE, STOCK = CL.BASE, CL.STOCK
SECT = CL.SECT                                   # 0xa272e420, bit n-1 = section n copied
GETTER = 0x6005e971
BAD = CL.BAD | {'call', 'ret'}

# ---- E
EX_SITE = 0x6030288d                             # call 0x6005e971,[d2,d3],12 (key 0x5ef1) in capture setup 0x603017f3
EX_FN = (0x603017f3, 0x60303200)                 # capture setup, decoded linearly for the branch scan
EX_HOLE, EX_HOLE_SHA = ('0x601e05c3', '0x601e06c2'), '88602b95a933bb6f'   # r2 gc_fill.. (grain_g2 unused_r2), bytes as in v0.33a
EX_PINS = {0x6062097d: ('dd051ea0', '`call malloc,[],4` at 0x6062097d: its bytes read as 0xa01e05dd'),
           0x601e0df7: ('cc03f8fe', 'inside v026_movie `mov d0,(972,a3)` (fa 13 cc 03) at 0x601e0df5, read as jmp d16')}
# ---- T
EST_IMM, EST_OLD, EST_NEW = 0x603185e4, 1740, 32400
EST_CTX = (0x603185e1, '627e2dcc0684a7c6037262')  # mov d0,(a2); mov (a2),d3; mov 1740,d1; mov d1,d0; cmp d1,d3; bcc; mov (a2),d0; ..
EST_FN = (0x603183a9, 0x603186fb)                # the estimate, one function (ret [d2,d3,a2,a3],128 at 0x603186f8)
REC_CAP = ((0x60319157, 32400), (0x6031915c, 32400))   # rec_limit's two imm16 (v0.33a)
# ---- M
D2_COUNT = ('0x61160fc2', '0x6117ea5e')
D_ENTRIES = ((0x61160fac, 0x61160fc0), (0x6117ea48, 0x6117ea5c))   # (D1, D2) letter entries of the two trees
D1_ID, D2_ID, D1_N, D2_N, ROW, SID_TV, SID_239 = 3327, 5068, 8, 7, 36, 1147, 239
# ---- S
SH_SITE = 0x60c6707b
SH_CTX = (0x60c67072, 'fccc198100009000 04'.replace(' ', ''), 0x60c67082, 'fa73ca5d')
SH_FN = (0x60c66da7, 0x60c67900)                 # play_exif_get_default_raw .. (linear decode for the branch scan)


def u16(m, a):
    return struct.unpack_from('<H', m, a - BASE)[0]


def u32(m, a):
    return struct.unpack_from('<I', m, a - BASE)[0]


def edit_at(spec, addr):
    for e in spec['edits']:
        if e['kind'] == '0x100' and not e['addr'].startswith('off:') and int(e['addr'], 16) == addr:
            return e
    return None


def overlaps(spec, lo, hi):
    return [e['addr'] for e in spec['edits'] if e['kind'] == '0x100' and not e['addr'].startswith('off:')
            and int(e['addr'], 16) < hi and lo < int(e['addr'], 16) + len(e['new']) // 2]


def branch_scan(im, fn, site, n):
    """Linear decode of fn: site must be an instruction start, and no decoded branch / call / jmp may land on site+1..site+n-1.
    Plus the image-wide d16 / d32 / abs32 scan into those bytes (crash_log refs, both aliases + the section's flash alias)."""
    ins = B3.disasm(im[fn[0] - BASE:fn[1] - BASE], fn[0], fn[1])
    at = {a for a, _, _ in ins}
    if site not in at or any(site < a < site + n for a in at):
        raise SystemExit(f'{site:#x}: not a whole instruction in the linear decode of {fn[0]:#x}')
    hits = [(a, op, args) for a, op, args in ins for t in re.findall(r'0x([0-9a-f]{8})', args)
            if (op[0] in 'bjl' or op.startswith('call')) and site < int(t, 16) < site + n]
    sec = next(k for k in range(1, 10) if KH.sec(STOCK.read_bytes(), k)[0] <= site < KH.sec(STOCK.read_bytes(), k)[1])
    far = CL.refs(im, site + 1, site + n, KH.sec(STOCK.read_bytes(), sec)[2])
    if hits or far:
        raise SystemExit(f'{site:#x}: references into the edited bytes: {hits[:4]} {[(k, hex(a)) for k, a in far[:4]]}')
    return len(ins)


# ------------------------------------------------------------------ E
def fix_exif(spec, stock, im):
    x = spec['exif_name']
    ex_get = int(x['symbols']['ex_get'], 16)
    e = edit_at(spec, EX_SITE + 1)
    if e is None or e.get('source') != 'patches/exif_name' or e['new'] != struct.pack('<i', ex_get - EX_SITE).hex() \
            or stock[EX_SITE - BASE] != 0xdd or stock[EX_SITE + 1 - BASE:EX_SITE + 5 - BASE] != struct.pack('<i', GETTER - EX_SITE):
        raise SystemExit('exif_name site edit is not the v0.31d rel32 -> ex_get')
    if list(EX_HOLE) not in spec['grain_g2']['unused_r2']:
        raise SystemExit('the r2 hole is no longer listed unused')
    lo, hi = (int(v, 16) for v in EX_HOLE)
    if hashlib.sha256(im[lo - BASE:hi - BASE]).hexdigest()[:16] != EX_HOLE_SHA:
        raise SystemExit('the r2 hole bytes changed: another layer uses them')
    at = (lo + 3) & ~3
    code, _, sy, _ = B3.assemble(B3.subst((HERE / 'exg.s.in').read_text(), dict(sect=hex(SECT))), at,
                                 dict(ep7_getter=GETTER, ep7_ex_get=ex_get))
    end = at + len(code)
    claim = (lo, (end + 15) & ~15)
    if sy['ex_gate'] != at or claim[1] > hi:
        raise SystemExit('ex_gate layout')
    ins = B3.disasm(code, at, end)
    got = [(op, args) for _, op, args in ins]
    if got != [('btst', f'64,({SECT:#x})'), ('bne', hex(ins[3][0])), ('jmp', hex(GETTER)), ('jmp', hex(ex_get))] \
            or any(code[a - at] == 0xfb for a, _, _ in ins) or B3.store_audit(ins):
        raise SystemExit(f'ex_gate: {got}')
    dead = [(int(a, 16), int(b, 16)) for a, b in spec['grain_g2']['unused_r2']]
    bad = [r for r in CL.refs(im, claim[0], claim[1], KH.sec(stock, 1)[2], allow=[CL.STEP_WORDS] + dead)
           if not (r[1] in EX_PINS and im[r[1] - BASE:r[1] - BASE + 4].hex() == EX_PINS[r[1]][0])]
    if bad:
        raise SystemExit(f'reference into the ex_gate claim: {[(k, hex(a)) for k, a in bad[:6]]}')
    n = branch_scan(im, EX_FN, EX_SITE, 7)
    why = f'v0.33b ex_gate ({len(code)} B) over r2\'s unused gc_fill bytes'
    CL.put(spec, stock, at, im[at - BASE:end - BASE], code, why)           # into the grain_cpu block, as crash_log does
    g = next(e for e in spec['edits'] if e['why'].endswith(f' [crash_log: {why}]'))
    g['why'] = g['why'][:-len(f' [crash_log: {why}]')] + f' [v033b: {why}]'
    e['new'] = struct.pack('<i', at - EX_SITE).hex()
    e['why'] += ' [v0.33b: -> ex_gate (section-7 test, then ex_get; else the stock getter)]'
    spec['grain_g2']['unused_r2'] = [[hex(claim[1]), hex(hi)] if r == list(EX_HOLE) else r for r in spec['grain_g2']['unused_r2']]
    x['gate'] = dict(built_by=SRC, code=[hex(at), len(code)], claim=[hex(claim[0]), hex(claim[1])], test=f'btst 64,({SECT:#x})',
                     stock=hex(GETTER), site_scan=f'{n} instructions of {EX_FN[0]:#x}', pins={hex(k): v[1] for k, v in EX_PINS.items()})
    x['symbols']['ex_gate'] = hex(at)


# ------------------------------------------------------------------ T
def fix_estimate(spec, stock, im):
    if stock[EST_CTX[0] - BASE:EST_CTX[0] - BASE + len(EST_CTX[1]) // 2].hex() != EST_CTX[1] or u16(stock, EST_IMM) != EST_OLD:
        raise SystemExit('estimate site differs from stock')
    for a, v in REC_CAP:
        e = edit_at(spec, a)
        if e is None or e['new'] != struct.pack('<h', v).hex() or v != EST_NEW:
            raise SystemExit(f'rec_limit edit {a:#x} is not {EST_NEW}')
    if overlaps(spec, EST_IMM - 1, EST_IMM + 2):
        raise SystemExit('estimate site overlaps an edit')
    n = branch_scan(im, EST_FN, EST_IMM - 1, 3)
    spec['edits'].append(dict(kind='0x100', addr=hex(EST_IMM), expect=struct.pack('<h', EST_OLD).hex(), new=struct.pack('<h', EST_NEW).hex(),
                              source='patches/rec_limit', why=f'v0.33b rec_limit: remaining-time estimate 0x603185e3 mov {EST_OLD},d1 -> {EST_NEW} (the cap of 0x60319157)'))
    spec['rec_limit_estimate'] = dict(built_by=SRC, site=hex(EST_IMM - 1), imm=hex(EST_IMM), old=EST_OLD, new=EST_NEW, site_scan=f'{n} instructions of {EST_FN[0]:#x}')


# ------------------------------------------------------------------ M
def fix_min_ss(spec, stock):
    drop = []
    for a in D2_COUNT:
        e = edit_at(spec, int(a, 16))
        if e is None or e.get('source') != 'patches/min_ss' or (e['expect'], e['new']) != ('0700', '0800'):
            raise SystemExit(f'min_ss count edit {a} not found')
        drop.append(e)
    spec['edits'] = [e for e in spec['edits'] if not any(e is d for d in drop)]
    im = ST.img_of(spec, stock)
    m = spec['min_ss']
    for d1, d2 in D_ENTRIES:
        if (u16(stock, d1), u16(stock, d1 + 2), u16(stock, d2), u16(stock, d2 + 2)) != (D1_ID, D1_N, D2_ID, D2_N):
            raise SystemExit('letter entries differ from stock')
        if (u16(im, d1), u16(im, d1 + 2), u16(im, d2), u16(im, d2 + 2)) != (D1_ID, D1_N, D2_ID, D2_N) or im[d2 - BASE:d2 + 20 - BASE] != stock[d2 - BASE:d2 + 20 - BASE]:
            raise SystemExit('D1 / D2 entries after the drop')
        rows, srows = u32(im, d1 + 12), u32(stock, d1 + 12)
        if rows == srows or rows not in [int(r, 16) for r in m['layout']['rows']]:
            raise SystemExit('D1 rows are not min_ss\'s copy')
        cp, sk = im[rows - BASE:rows + ROW * D1_N - BASE], stock[srows - BASE:srows + ROW * D1_N - BASE]
        if cp[:ROW * 7] != sk[:ROW * 7] or struct.unpack_from('<H', cp, ROW * 7)[0] != SID_TV or struct.unpack_from('<H', sk, ROW * 7)[0] != SID_239:
            raise SystemExit('D1 copy: 7 stock rows then 1147 (stock 8th = 239)')
    m['sites'] = [s for s in m['sites'] if s not in D2_COUNT]
    spec['min_ss']['v033b'] = dict(built_by=SRC, dropped=list(D2_COUNT), why='count edits were D2\'s n; D1 n = 8 stock reads the copy (7 stock rows + 1147)')


# ------------------------------------------------------------------ S
def fix_sharp(spec, stock, im):
    sh_get = int(spec['sharp_off']['symbols']['sh_get'], 16)
    if stock[SH_CTX[0] - BASE:SH_CTX[0] - BASE + len(SH_CTX[1]) // 2].hex() != SH_CTX[1] or stock[SH_SITE - BASE] != 0xdd \
            or stock[SH_SITE + 1 - BASE:SH_SITE + 7 - BASE] != struct.pack('<i', GETTER - SH_SITE) + b'\xc0\x0c' \
            or stock[SH_CTX[2] - BASE:SH_CTX[2] + 4 - BASE].hex() != SH_CTX[3]:
        raise SystemExit('RAW-edit sharpness site differs from stock')
    cap = edit_at(spec, 0x602a7edb)
    if cap is None or cap.get('source') != 'patches/sharp_off' or cap['new'] != struct.pack('<i', sh_get - 0x602a7eda).hex():
        raise SystemExit('the capture site is not sharp_off\'s sh_get')
    if overlaps(spec, SH_SITE, SH_SITE + 7) or im[sh_get - BASE:sh_get - BASE + 3] != bytes.fromhex('86f1d3'):   # mov d1,d2; mov a0,d3
        raise SystemExit('RAW-edit site overlaps an edit / sh_get entry')
    n = branch_scan(im, SH_FN, SH_SITE, 7)
    spec['edits'].append(dict(kind='0x100', addr=hex(SH_SITE + 1), expect=struct.pack('<i', GETTER - SH_SITE).hex(),
                              new=struct.pack('<i', sh_get - SH_SITE).hex(), source='patches/sharp_off',
                              why='v0.33b sharp_off: RAW Data Edit Sharpness read 0x60c6707b (key 0x8119) -> sh_get, as the capture site'))
    spec['sharp_off']['raw_edit_site'] = dict(built_by=SRC, site=hex(SH_SITE), target=hex(sh_get), site_scan=f'{n} instructions of {SH_FN[0]:#x}')


def apply(spec, version='0.33b'):
    stock = STOCK.read_bytes()
    spec = copy.deepcopy(spec)
    if 'v033b' in spec:
        raise SystemExit('v033b already applied')
    if 'crash_log' not in spec or 'gate' not in spec['crash_log'] or 'exif_name' not in spec:
        raise SystemExit('needs the v0.33b crash_log (cl_gate) and exif_name')
    im = ST.img_of(spec, stock)
    fix_exif(spec, stock, im)
    fix_estimate(spec, stock, im)
    fix_sharp(spec, stock, im)
    fix_min_ss(spec, stock)
    spec['v033b'] = dict(built_by=SRC, version=version, fixes=['exif_name ex_gate', 'rec_limit estimate', 'sharp_off RAW edit', 'min_ss D2 count dropped'])
    return spec


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--version', default='0.33b')
    a = ap.parse_args()
    spec = apply(json.loads(a.spec.read_text()), a.version)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(spec, indent=1))
    print(json.dumps(spec['v033b']))
