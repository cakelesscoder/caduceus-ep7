#!/usr/bin/env python3
"""look_hw: per-look base curve and colour matrix (COLOR profiles, stills and live view), on a register-image hook.
Development layer on the v0.33b chain, after v033b. Offline. lh.s.in has the contract, docs/LOOK_FORMAT_V4.md the format.

  .venv/bin/python -I patches/v032/build.py releases/v0.31d/edits.json --out generated/v034_lookhw/edits.json --version 0.34a \\
      --extra grain_g2=patches/grain_g2/build.py --extra halation_h6=patches/halation_h6/build.py \\
      --extra crash_log=patches/crash_log/build.py --extra clean_boot=patches/clean_boot/build.py \\
      --extra v033b=patches/v033b/build.py --extra look_hw=patches/look_hw/build.py

apply(spec, version) -> spec. Edits:
  A  0x603b149f `call mono_selector,[d2,d3,a2,a3],84` (call16, 5 B, dev_stage_list) -> `jmp mx_e` (jmp d32, 5 B) (v0.34c; v0.34a
     hooked pipe_hw_write's three callers, which showed no effect on the camera);
  B  0x603ae82b `call gamma_select,[d2,d3,a2,a3],28` (call16, 5 B) -> `jmp gm_e` (jmp d32, 5 B);
  P  rel32 of sl_pick's tail `jmp ls_pick` (0x601e3a16, looks_split's edit) -> lh_pick;
  R  SD loader v3 range bytes: slot +53 lo 0 span 7, +54..+59 lo -64 span 128 (BUNDLES.BIN carries the fields, and the
     camera's own save of them loads again);
  code: mx_e / gm_e (40 B) in r2 bytes grain_g2 lists as unused (section 1, inside the grain_cpu edit), the rest in a
  section-5 claim of the dead `sdk api` handlers (CODE_SPACE_SURVEY section 2).
Slot bytes: +53 base curve 0..7, +54..+59 matrix s8 -64..64 (1/128). docs/LOOK_FORMAT_V4.md.
"""
import argparse, copy, importlib.util, json, re, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SRC = 'patches/look_hw'


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


V3B = _load('ep7_v033b_build_lh', ROOT / 'patches/v033b/build.py')
LS = _load('ep7_ls_build_lh', ROOT / 'patches/looks_split/build.py')
CL, ST, KH, B3 = V3B.CL, V3B.ST, V3B.KH, V3B.B3
BASE, STOCK = V3B.BASE, V3B.STOCK
SECT = V3B.SECT                                   # 0xa272e420, bit n-1 = section n copied

# ---- sites
MX_SITE, MX_RET, MONO = 0x603b149f, 0x603b14a4, 0x603acfe4
MX_STOCK = 'cd45bbf054'                           # call16 mono_selector,[d2,d3,a2,a3],84
MX_FN = (0x603b1466, 0x603b1517)                  # dev_stage_list
MTX_O = 0x50                                      # O + 0x50 = bank + 0x6ec (mono_selector's a0)
HW_WRITE = 0x603450dd                             # pipe_hw_write
HW_SITES = (0x60334e1b, 0x60335199, 0x60335204)   # call 0x603450dd,[d2,d3,a2,a3],28 (dd rel32 f0 1c), a0 = ctx
HW_FNS = {0x60334e1b: (0x60334db4, 0x60334e63), 0x60335199: (0x6033513d, 0x60335250), 0x60335204: (0x6033513d, 0x60335250)}
HW_OTHER = 0x60334cf9                             # the fourth caller (0x60334c47, red-eye / face lib buffers, no static caller chain into stills): left stock
G_SITE, G_RET, GSEL = 0x603ae82b, 0x603ae830, 0x603ae354
G_STOCK = 'cd29fbf01c'                            # call16 0x603ae354,[d2,d3,a2,a3],28
G_FN = (0x603ae80d, 0x603aea29)                   # gamma_stage (corpus size 540)
G_NEXT = '5c24'                                   # 0x603ae830 movbu d0,(60,sp) is f8 92 3c, then mov (36,sp),a0
ROWPICK, VARIANT, GPT = 0x603ae2fd, 0x603b5606, 0x60530b6c
PACK = 0x603ace56                                 # matrix packer (a0 out 9 x s16, a1 in), retf [d2,a2,a3],12
G0 = 0x604edc78                                   # 97 x u16[256] gamma curves
CURVE = lambda i: G0 + 512 * i
BASE_CURVES = (1, 2, 49, 3, 4, 50)                # gamma_ptr_table rows 0 and 2, every column / variant
ROWS = (0, 2, 3, 4, 8)                            # slot +53 = 1..5
FIXED = (51, 52)                                  # slot +53 = 6 flat (0x604f4278), 7 log (0x604f4478)
MTX = 0x6ec                                       # bank: colour matrix words (registers 0x9f001090..)
PICK_TAIL = 0x601e3a16                            # sl_pick: jmp ls_pick (dc rel32)
LO, SPAN = 0x605b76e1, 0x605b7721                 # SD loader v3 range tables (64 B each)
RANGES = {53: (0, 7), **{k: (-64, 128) for k in range(54, 60)}}
# ---- placements
HOLE = ('0x601e05e0', '0x601e06c2')               # grain_g2 unused_r2 piece (after v033b's ex_gate)
E_AT = 0x601e05e0
CLAIM = (0x607dd300, 0x607ddb00)                  # sec 5, 2 KB: inside the run 0x607dd2f3..0x607ddcfc that no outside reference points into
GUARD = 16
A_AT = CLAIM[0] + GUARD
MOVM = 48                                         # movm [d2,d3,a2,a3,other]: 12 words (emulator: sp - 48)
# ---- job ABI and P (as split_tone / tone_ends)
CALLBACK, REQ_IN_JOB, RECORDS_IN_JOB, REC_STRIDE, N_REC = ST.CALLBACK, ST.REQ_IN_JOB, ST.RECORDS_IN_JOB, ST.REC_STRIDE, ST.N_REC
EXT_PROFILE, EXT_MODE, EXT_MAGIC, MARKER = ST.EXT_PROFILE, ST.EXT_MODE, ST.EXT_MAGIC, ST.MARKER
SYMS = dict(ep7_mono=MONO, ep7_mret=MX_RET, ep7_gsel=GSEL, ep7_gret=G_RET, ep7_rowpick=ROWPICK, ep7_variant=VARIANT, ep7_pack=PACK,
            ep7_getter=ST.GETTER, ep7_tbl_idx=ST.TBL_IDX, ep7_ap_p=ST.AP_P)
BAD = {'mulu', 'div', 'divu', 'ext', 'setlb', 'llt', 'lne', 'leq', 'lra', 'lcc', 'lcs', 'trap', 'rti', 'rets', 'calls'}
STORES = {'mov d0,(a1)', 'mov d0,(4,a1)', 'mov d0,(8,a1)', 'mov d0,(12,a1)', 'mov d0,(16,a1)',       # bank matrix words
          'mov d1,(68,a3)', 'mov d1,(72,a3)', 'mov d1,(76,a3)',                                       # gamma_stage's R/G/B
          *{f'movbu d0,({85 + i},a1)' for i in range(7)}, 'movbu d0,(d2,a1)'}                         # slot +53..+59
# Stock bytes this layer relies on: (address, hex, what)
NEED = (
    (0x60334e1b, 'ddc2020100f01c', 'kind handler: call pipe_hw_write,[d2,d3,a2,a3],28 (single pass)'),
    (0x60335199, 'dd44ff0000f01c', 'pipe_run: left half write'),
    (0x60335204, 'ddd9fe0000f01c', 'pipe_run: right half write'),
    (0x60334e1a, '98', 'kind handler: mov a2,a0 (a0 = ctx) before the write'),
    (0x60334ded, 'cdf048a048', 'kind handler: call pipe_program,[d2,a2],72 before every write'),
    (0x603396eb, 'f82604fcdc804f4e60f8411054f390', 'pipe_program: builder by request kind (table 0x604e4f80)'),
    (G_SITE - 2, '294c' + G_STOCK + 'f8923c' + G_NEXT, 'gamma_stage: add 76,d1; call gamma_select; movbu d0,(60,sp); mov (36,sp),a0'),
    (0x603ae98e, '5c245808f1dd99cd3efea008', 'gamma_stage: R/G/B from (68/72/76,sp) to O+2596.. (0x603ae7d3)'),
    (0x603ae704, '8001dff01c', 'gamma_select default path: d0 = 1, ret [d2,d3,a2,a3],28'),
    (0x603ae6e5, 'cd216f0000f866 0e14fcdc6c0b5360cd09fcc008'.replace(' ', ''), 'default path: variant 0x603b5606, R+14, row pick of 0x60530b6c'),
    (0x603b149f, 'cd45bbf054', 'dev_stage_list: mono_selector first (unconditional)'),
    (0x603ad07c, '3cf1d22a30f1e899cdd2fdb00c', 'mono_selector: pack 0x603ace56 (a0 out, a1 in)'),
    (0x603ad09a, '5c04f8bc30f8bd32f8c110f21460', 'mono_selector: words (m00,m01).. to its bank pointer'),
    (0x603aad07, 'f006f8611cf8c808a001c808a002c80b', 'stage_dispatch: kind 0/16 by input class 1 / 2'),
    (0x60339c27, 'f82418f86108f8c808a001c85fa002c85b', 'program step 6 gate: input class 1 / 2 on'),
)


# Naive-scan hits into edited bytes that are not address uses (each checked with tools/dis.sh): {at: (bytes, why)}
SITE_PINS = {0x60334c80: ('cda00100', 'inside `call 0x6034ed4c,[d2,d3,a2,a3],20` (dd cd a0 01 00 f0 14) at 0x60334c7f, read as call16')}


def branch_scan(im, fn, site, n):
    """patches/v033b branch_scan with this layer's pins: site is a whole instruction of fn's linear decode, no decoded
    branch lands on site+1..site+n-1, and no abs32 / d16 / d32 encoding anywhere points there (except the pins)."""
    ins = B3.disasm(im[fn[0] - BASE:fn[1] - BASE], fn[0], fn[1])
    at = {a for a, _, _ in ins}
    if site not in at or any(site < a < site + n for a in at):
        raise SystemExit(f'{site:#x}: not a whole instruction in the linear decode of {fn[0]:#x}')
    hits = [(a, op, args) for a, op, args in ins for t in re.findall(r'0x([0-9a-f]{8})', args)
            if (op[0] in 'bjl' or op.startswith('call')) and site < int(t, 16) < site + n]
    stock = STOCK.read_bytes()
    sec = next(k for k in range(1, 10) if KH.sec(stock, k)[0] <= site < KH.sec(stock, k)[1])
    far = [r for r in CL.refs(im, site + 1, site + n, KH.sec(stock, sec)[2])
           if not (r[1] in SITE_PINS and im[r[1] - BASE:r[1] - BASE + 4].hex() == SITE_PINS[r[1]][0])]
    if hits or far:
        raise SystemExit(f'{site:#x}: references into the edited bytes: {hits[:4]} {[(k, hex(a)) for k, a in far[:4]]}')
    return len(ins)


def u32(m, a):
    return struct.unpack_from('<I', m, a - BASE)[0]


def check_stock(stock):
    for a, h, what in NEED:
        if stock[a - BASE:a - BASE + len(h) // 2].hex() != h:
            raise SystemExit(f'{a:#x}: stock bytes differ ({what})')
    for s in HW_SITES:
        if s + struct.unpack_from('<i', stock, s + 1 - BASE)[0] != HW_WRITE:
            raise SystemExit(f'{s:#x}: not a call to pipe_hw_write')
    if G_SITE + struct.unpack_from('<h', stock, G_SITE + 1 - BASE)[0] != GSEL:
        raise SystemExit('gamma site is not call16 gamma_select')
    for row in (0, 2):
        w = struct.unpack_from('<8I', stock, GPT + 32 * row - BASE)
        if set(w) - {CURVE(i) for i in BASE_CURVES}:
            raise SystemExit(f'gamma row {row} holds a curve outside the base set')
    for c in (FIXED[0], FIXED[1]):
        if stock[CURVE(c) - BASE:CURVE(c) + 2 - BASE] != b'\0\0':
            raise SystemExit('flat / log curve does not start at 0')


def subst():
    sub = dict(sect=hex(SECT), mtx=hex(MTX), mtx_o=hex(MTX_O), movm=MOVM, callback=hex(CALLBACK), rec_off=RECORDS_IN_JOB - REQ_IN_JOB, n_rec=N_REC,
               stride=REC_STRIDE, req_in_job=REQ_IN_JOB, ext_magic=EXT_MAGIC, ext_mode=EXT_MODE, ext_profile=EXT_PROFILE,
               magic=hex(MARKER), prop_profile=hex(ST.PROP_PROFILE),
               fmagic=hex(LS.FB.FMAGIC), lmagic=hex(LS.FB.LMAGIC), npool=hex(-LS.FB.POOL2 & 0xffffffff), llim=hex(LS.LLIM),
               base_curves=', '.join(hex(CURVE(i)) for i in BASE_CURVES), rows=', '.join(hex(GPT + 32 * r) for r in ROWS),
               fixed=', '.join(hex(CURVE(i)) for i in FIXED))
    s = (HERE / 'lh.s.in').read_text()
    for k, v in sub.items():
        s = s.replace('{' + k + '}', str(v))
    if re.search(r'\{[a-z_0-9]+\}', s.split('*/', 1)[1]):
        raise SystemExit('unfilled placeholder')
    return s


def build_code(syms):
    regions = {'.lhe': (E_AT, int(HOLE[1], 16)), '.lha': (A_AT, CLAIM[1] - GUARD)}
    out, sy, lst = ST.assemble(subst(), syms, regions)
    if sy['mx_e'] != E_AT or sy['lh_a'] != A_AT:
        raise SystemExit('entry layout')
    for k, (lo, hi) in regions.items():
        if lo + len(out[k]) > hi:
            raise SystemExit(f'{k}: {len(out[k])} B does not fit {hi - lo}')
    return out, sy, lst, regions


def audit(out, sy, regions):
    data = {'.lha': sy['gm_base']}
    for k, (lo, hi) in regions.items():
        ins = B3.disasm(out[k], lo, data.get(k))
        if any(op in BAD for _, op, _ in ins) or any(out[k][a - lo] == 0xfb for a, _, _ in ins):
            raise SystemExit(f'{k}: forbidden instruction or fb-prefixed form: {[x for x in ins if x[1] in BAD][:3]}')
        if 'mul' in {op for _, op, _ in ins} and k != '.lha':
            raise SystemExit('mul outside lh_m')
        for a, txt, kind, _ in B3.store_audit(ins):
            if kind == 'abs' or (kind == 'ind' and txt not in STORES):
                raise SystemExit(f'{k}: unexpected store {txt} at {a:#x}')
        if k == '.lhe':
            got = [(op, args) for _, op, args in ins]
            want = [('call', None), ('btst', f'16,({SECT:#x})'), ('bne', None), ('jmp', hex(MX_RET)), ('jmp', hex(sy['lh_a'])),
                    ('call', None), ('btst', f'16,({SECT:#x})'), ('bne', None), ('jmp', hex(G_RET)), ('jmp', hex(sy['gm_b']))]
            if len(got) != len(want) or any(w[0] != g[0] or (w[1] and w[1] != g[1]) for w, g in zip(want, got)) \
                    or not got[0][1].startswith(f'{MONO:#x},[d2,d3,a2,a3],84') or not got[5][1].startswith(f'{GSEL:#x},[d2,d3,a2,a3],28'):
                raise SystemExit(f'.lhe: {got}')
    for t in ('gm_base', 'gm_rows', 'gm_fix'):
        if sy[t] % 4:
            raise SystemExit(f'{t} not 4-aligned')
    lo = regions['.lha'][0]
    tb = out['.lha'][sy['gm_base'] - lo:sy['gm_base'] - lo + 4 * 13]
    if list(struct.unpack('<13I', tb)) != [CURVE(i) for i in BASE_CURVES] + [GPT + 32 * r for r in ROWS] + [CURVE(i) for i in FIXED]:
        raise SystemExit('curve tables differ')


def refs_free(spec, stock, im):
    """Placements: no edit there (sec 5: the claim; sec 1: our piece of the r2 hole), stock / r2 bytes, no reference into
    them from outside (abs32 on four aliases, call / jmp / calls / branch d16 and d32), as patches/v033b checks its piece."""
    if list(HOLE) not in spec['grain_g2']['unused_r2']:
        raise SystemExit('the r2 piece is no longer listed unused')
    lo5, hi5, off5 = KH.sec(stock, 5)
    if not (lo5 <= CLAIM[0] and CLAIM[1] <= hi5 and KH.DEAD[1][0] <= CLAIM[0] and CLAIM[1] <= KH.DEAD[1][1]):
        raise SystemExit('claim not inside the dead handler range of section 5')
    if V3B.overlaps(spec, *CLAIM) or im[CLAIM[0] - BASE:CLAIM[1] - BASE] != stock[CLAIM[0] - BASE:CLAIM[1] - BASE]:
        raise SystemExit('claim is edited / not stock')
    bad = CL.refs(im, CLAIM[0], CLAIM[1], off5, allow=list(KH.DEAD))
    if bad:
        raise SystemExit(f'reference into the sec-5 claim: {[(k, hex(a)) for k, a in bad[:6]]}')
    dead = [(int(a, 16), int(b, 16)) for a, b in spec['grain_g2']['unused_r2']]
    lo1, hi1 = E_AT, int(HOLE[1], 16)
    bad = [r for r in CL.refs(im, lo1, hi1, KH.sec(stock, 1)[2], allow=[CL.STEP_WORDS] + dead)
           if not (r[1] in V3B.EX_PINS and im[r[1] - BASE:r[1] - BASE + 4].hex() == V3B.EX_PINS[r[1]][0])]
    if bad:
        raise SystemExit(f'reference into the r2 piece: {[(k, hex(a)) for k, a in bad[:6]]}')


def apply(spec, version='0.34a'):
    stock = STOCK.read_bytes()
    spec = copy.deepcopy(spec)
    if 'look_hw' in spec:
        raise SystemExit('look_hw already applied')
    for need in ('v033b', 'looks_split', 'split_tone', 'sd_bundles_v3', 'grain_g2'):
        if need not in spec:
            raise SystemExit(f'needs {need}')
    check_stock(stock)
    im = ST.img_of(spec, stock)
    if stock[MX_SITE - BASE:MX_SITE + 5 - BASE].hex() != MX_STOCK or MX_SITE + 5 + struct.unpack_from('<h', stock, MX_SITE + 1 - BASE)[0] - 5 != MONO:
        raise SystemExit('dev_stage_list site is not call16 mono_selector')
    if V3B.overlaps(spec, MX_SITE, MX_SITE + 5):
        raise SystemExit('mono_selector site already edited')
    if V3B.overlaps(spec, G_SITE - 2, G_SITE + 7):
        raise SystemExit('gamma site already edited')
    ls_pick = int(spec['looks_split']['symbols']['ls_pick'], 16) if 'symbols' in spec['looks_split'] and 'ls_pick' in spec['looks_split']['symbols'] else None
    tail = im[PICK_TAIL - BASE:PICK_TAIL + 5 - BASE]
    if tail[0] != 0xdc or (ls_pick is not None and PICK_TAIL + struct.unpack_from('<i', tail, 1)[0] != ls_pick):
        raise SystemExit(f'sl_pick tail is not jmp ls_pick: {tail.hex()}')
    ls_pick = PICK_TAIL + struct.unpack_from('<i', tail, 1)[0]
    if im[ls_pick - BASE] not in (0xcd, 0xdd):
        raise SystemExit('ls_pick does not start with call ls_pk')
    for off, (lo, span) in RANGES.items():
        if im[LO + off - BASE] != 0 or im[SPAN + off - BASE] != 0:
            raise SystemExit(f'loader range +{off} is not 0/0')
    refs_free(spec, stock, im)
    # branch-target scans: sites are whole instructions, nothing lands inside the edited bytes
    scans = {}
    scans[hex(MX_SITE)] = branch_scan(im, MX_FN, MX_SITE, 5)
    scans[hex(G_SITE)] = branch_scan(im, G_FN, G_SITE, 5)
    scans[hex(PICK_TAIL)] = branch_scan(im, (0x601e39aa, 0x601e3a57), PICK_TAIL, 5)
    out, sy, lst, regions = build_code(dict(SYMS, ep7_ls_pick=ls_pick))
    audit(out, sy, regions)
    # sec 1: into the grain_cpu block (r2 bytes), as v033b's ex_gate
    why1 = f'look_hw {version} mx_e / gm_e ({len(out[".lhe"])} B) over r2\'s unused gc_fill bytes'
    CL.put(spec, stock, E_AT, im[E_AT - BASE:E_AT + len(out['.lhe']) - BASE], out['.lhe'], why1)
    g = next(e for e in spec['edits'] if e['why'].endswith(f' [crash_log: {why1}]'))
    g['why'] = g['why'][:-len(f' [crash_log: {why1}]')] + f' [look_hw: {why1}]'
    e1 = (E_AT + len(out['.lhe']) + 15) & ~15
    spec['grain_g2']['unused_r2'] = [[hex(e1), HOLE[1]] if r == list(HOLE) else r for r in spec['grain_g2']['unused_r2']]
    # sec 5
    spec['edits'].append(dict(kind='0x100', addr=hex(A_AT), expect=stock[A_AT - BASE:A_AT - BASE + len(out['.lha'])].hex(),
                              new=out['.lha'].hex(), source=SRC,
                              why=f'look_hw {version} lh_a / lk_get / gm_b / lh_pick ({len(out[".lha"])} B, section 5 dead sdk-api handlers)'))
    spec['edits'].append(dict(kind='0x100', addr=hex(MX_SITE), expect=MX_STOCK, new=('dc' + struct.pack('<i', sy['mx_e'] - MX_SITE).hex()),
                              source=SRC, why='look_hw A: dev_stage_list call16 mono_selector -> jmp mx_e (same call, then lh_a: N = L M; back to 0x603b14a4)'))
    spec['edits'].append(dict(kind='0x100', addr=hex(G_SITE), expect=G_STOCK, new=('dc' + struct.pack('<i', sy['gm_e'] - G_SITE).hex()),
                              source=SRC, why='look_hw B: gamma_stage call16 gamma_select -> jmp gm_e (same call, then gm_b; back to 0x603ae830)'))
    e = V3B.edit_at(spec, PICK_TAIL)
    CL.put(spec, stock, PICK_TAIL + 1, struct.pack('<i', ls_pick - PICK_TAIL), struct.pack('<i', sy['lh_pick'] - PICK_TAIL),
           'look_hw P: sl_pick tail jmp ls_pick -> jmp lh_pick (+53..+59, then ls_pick)')
    for off, (lo, span) in RANGES.items():
        CL.put(spec, stock, LO + off, b'\0', struct.pack('<b', lo), f'look_hw R: SD loader v3 range slot +{off} lo {lo}')
        CL.put(spec, stock, SPAN + off, b'\0', bytes([span]), f'look_hw R: SD loader v3 range slot +{off} span {span}')
    for ed in spec['edits']:
        ed['why'] = ed['why'].replace(' [crash_log: look_hw', ' [look_hw: look_hw')
    spec['look_hw'] = dict(
        built_by=SRC, version=version,
        slot_bytes={'curve': 53, 'matrix': [54, 59], 'curve_values': {'1': 'standard (row 0)', '2': 'auto (row 2)', '3': 'pale (row 3)',
                    '4': 'light (row 4)', '5': 'pop (row 8)', '6': 'flat (curve 51)', '7': 'log (curve 52)'},
                    'matrix_order': 'l01 l02 l10 l12 l20 l21, s8 1/128, -64..64; rows R G B out'},
        hooks=dict(A=hex(MX_SITE), B=hex(G_SITE), P=hex(PICK_TAIL)),
        code=dict(sec1=[hex(E_AT), len(out['.lhe'])], sec5=[hex(A_AT), len(out['.lha'])], claim=[hex(CLAIM[0]), hex(CLAIM[1])],
                  r2_piece=[hex(E_AT), hex(e1)]),
        loader_ranges={str(k): v for k, v in RANGES.items()}, site_scans=scans, ls_pick=hex(ls_pick),
        symbols={k: hex(v) for k, v in sy.items() if not k.startswith('_')})
    return spec


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--version', default='0.34a')
    ap.add_argument('--listing', type=Path)
    a = ap.parse_args()
    spec = apply(json.loads(a.spec.read_text()), a.version)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(spec, indent=1))
    if a.listing:
        a.listing.write_text(build_code(dict(SYMS, ep7_ls_pick=int(spec['look_hw']['ls_pick'], 16)))[2])
    print(json.dumps({k: v for k, v in spec['look_hw'].items() if k != 'symbols'}))
