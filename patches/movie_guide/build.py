#!/usr/bin/env python3
"""Movie / AP Extras labels (issue #54). Offline. Layer it with --extra after look_hw_ui (and before fw_version):

  .venv/bin/python -I patches/v032/build.py releases/v0.31d/edits.json --out generated/fix54/edits.json --version 0.35a \\
      --extra grain_g2=patches/grain_g2/build.py --extra halation_h6=patches/halation_h6/build.py \\
      --extra crash_log=patches/crash_log/build.py --extra clean_boot=patches/clean_boot/build.py \\
      --extra v033b=patches/v033b/build.py --extra look_hw=patches/look_hw/build.py \\
      --extra look_hw_ui=patches/look_hw_ui/build.py --extra movie_quality=patches/movie_quality/build.py \\
      --extra looks_v4=patches/looks_v4/build.py --extra i18n_ja=patches/i18n_ja/build.py \\
      --extra movie_guide=patches/movie_guide/build.py

Cause [V emulator, patches/movie_guide/verify.py G]: on the Movie wheel (P2 swapped in) and the AP wheel (P3), the GUI picture
mode (111) is Vivid. v0.26 `mv_get` answers 64 (COLOR4) only at a list of return addresses (mv_ra: 13 stock sites, ed_guide
0x60b9ddba, ex_guide 0x601e34ee). The two guide fronts added later, xp_guide (patches/extras_pages, v0.32) and lu_guide
(patches/look_hw_ui, v0.34), read 111 themselves and are not in the list. They get Vivid, so on the Movie / AP wheel:
  - xp_guide sets no cursor override and does not renumber: the old v0.31 chain labels the OLD sector at the cursor's number
    (cursor 5 Sharp shows old sector 5 "Art: stills", 6 NR shows old 6, ...), and no label follows the setting being changed;
  - lu_guide keeps the chain's text on Colour & Light 9..12.
The writes themselves were never blocked: xp_set translates the id and the Movie slot byte changes (verify.py U).

Fix: two more words in mv_get's return-address list. The list is scanned as one run from mv_ra; it ends at mv_ra2 (3 words,
the 15272 sites), and the v0.26 block keeps 8 zero bytes after mv_ra2 inside its own claim (0x601e2318..0x601e2320, dead EVF
table, the block's padding). So:
  N  mv_get's `mov 15,d3` (0x601e1fde, imm8 at 0x601e1fdf) -> 20: the scan covers mv_ra (15), mv_ra2 (3, return addresses of
     GetValue(15272) calls, never 111, so they can't match) and the two new words;
  W  0x601e2318 = xp_guide's GetValue(111) return address, 0x601e231c = lu_guide's.
mv_get answers 64 only with a swapped slot (mv_sw), so COLOR1-4 and stock movie are unchanged. Both edits go into the
v026_movie edit (amended in place, as v033b does). 9 bytes differ from v0.34a.
"""
import argparse, copy, importlib.util, json, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = 'patches/movie_guide'


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


CL = _load('crash_log_build_mg', ROOT / 'patches/crash_log/build.py')
ST, KH = CL.ST, CL.KH
BASE, STOCK = CL.BASE, CL.STOCK
MV = _load('v026_movie_build_mg', ROOT / 'patches/v026_movie/build.py')

SCAN = 0x601e1fd8                         # mov mv_ra,a0 (fc dc imm32); mov 15,d3; loop: mov (a0),d2; cmp d2,d1; beq g_64 ...
N_IMM, N_OLD, N_NEW = 0x601e1fdf, 15, 20
FREE = (0x601e2318, 0x601e2320)           # inside the v026_movie edit, after mv_ra2
CALL111 = bytes.fromhex('806ff0f2')       # mov 111,d0; calls (a2)


def u32(m, a):
    return struct.unpack_from('<I', m, a - BASE)[0]


def ra_of(im, lo, hi, what):
    """The return address of the one `mov 111,d0; calls (a2)` in [lo, hi)."""
    b = im[lo - BASE:hi - BASE]
    at = [i for i in range(len(b) - 3) if b[i:i + 4] == CALL111]
    if len(at) != 1:
        raise SystemExit(f'{what}: {len(at)} GetValue(111) calls')
    ra = lo + at[0] + 4
    ins = CL.B3.disasm(im[lo - BASE:hi - BASE], lo, hi)
    if (ra - 2, 'calls', '(a2)') not in [(a, op, args) for a, op, args in ins] or (ra - 4, 'mov', '111,d0') not in [(a, op, args) for a, op, args in ins]:
        raise SystemExit(f'{what}: the call is not a whole instruction pair')
    return ra


def apply(spec, version='0.34b'):
    stock = STOCK.read_bytes()
    spec = copy.deepcopy(spec)
    if 'movie_guide' in spec:
        raise SystemExit('movie_guide already applied')
    for k in ('v026_movie', 'extras_pages', 'look_hw_ui'):
        if k not in spec:
            raise SystemExit(f'needs {k}')
    im = ST.img_of(spec, stock)
    w = {k: int(v, 16) for k, v in spec['v026_movie']['wheel_symbols'].items()}
    ra, ra2 = w['mv_ra'], w['mv_ra2']
    want = MV.RA + MV.RA_G
    if ra2 != ra + 4 * len(want) or [u32(im, ra + 4 * i) for i in range(len(want))] != want \
            or [u32(im, ra2 + 4 * i) for i in range(len(MV.CC_RA))] != MV.CC_RA or ra2 + 4 * len(MV.CC_RA) != FREE[0] \
            or w['mvw_data_end'] != FREE[0]:
        raise SystemExit('mv_ra / mv_ra2 layout differs from v0.26 wheel4')
    if im[SCAN - BASE:SCAN - BASE + 2] != b'\xfc\xdc' or u32(im, SCAN + 2) != ra or im[N_IMM - 1 - BASE] != 0x8f or im[N_IMM - BASE] != N_OLD:
        raise SystemExit('mv_get scan is not `mov mv_ra,a0; mov 15,d3`')
    if not (w['mv_get'] < SCAN < w['mv_def']):
        raise SystemExit('scan site outside mv_get')
    if im[FREE[0] - BASE:FREE[1] - BASE] != bytes(8):
        raise SystemExit('the 8 bytes after mv_ra2 are not free (0)')
    blk = int(spec['v026_movie']['wheel_at'], 16), int(spec['v026_movie']['wheel_at'], 16) + spec['v026_movie']['wheel_len']
    if not (blk[0] <= SCAN and FREE[1] == blk[1]):
        raise SystemExit('the free words are not the v026 wheel block tail')
    bad = CL.refs(im, FREE[0], FREE[1], KH.sec(stock, 1)[2], allow=[CL.STEP_WORDS])
    if bad:
        raise SystemExit(f'references into {FREE[0]:#x}..{FREE[1]:#x}: {[(k, hex(a)) for k, a in bad[:6]]}')
    xs, ls = spec['extras_pages']['symbols'], spec['look_hw_ui']['symbols']
    xra = ra_of(im, int(xs['xp_guide'], 16), int(xs['xp_map'], 16), 'xp_guide')
    lra = ra_of(im, int(ls['lu_guide'], 16), int(ls['lu_end'], 16), 'lu_guide')
    why = 'movie_guide #54: mv_get 111 list += xp_guide / lu_guide return addresses'
    put = lambda a, old, new: CL.put(spec, stock, a, old, new, why)
    put(N_IMM, bytes([N_OLD]), bytes([N_NEW]))
    put(FREE[0], bytes(8), struct.pack('<2I', xra, lra))
    for e in spec['edits']:                              # CL.put tags crash_log; name ours
        e['why'] = e['why'].replace(f' [crash_log: {why}]', f' [{why}]')
    im2 = ST.img_of(spec, stock)
    diff = [a + BASE for a in range(len(im)) if im[a] != im2[a]]
    if not (set(diff) <= {N_IMM} | set(range(FREE[0], FREE[1]))) or len(diff) != 1 + sum(1 for b in struct.pack('<2I', xra, lra) if b):
        raise SystemExit(f'unexpected diff {[hex(a) for a in diff]}')
    spec['movie_guide'] = dict(built_by=SRC, version=version, scan_imm=hex(N_IMM), count=[N_OLD, N_NEW], words=hex(FREE[0]),
                               ra=dict(xp_guide=hex(xra), lu_guide=hex(lra)), why='Movie / AP wheel: xp_guide and lu_guide read 111 = COLOR4')
    return spec


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--version', default='0.34b')
    a = ap.parse_args()
    spec = apply(json.loads(a.spec.read_text()), a.version)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(spec, indent=1))
    print(json.dumps(spec['movie_guide']))
