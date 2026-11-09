#!/usr/bin/env python3
"""Tinted halation on COLOR stills (h1): a CPU pass on the CPU grain route, after the Soft Focus blend and before the grain.
docs/HALATION_RED.md §14-15. Offline.

  .venv/bin/python -I patches/halation/build.py releases/v0.30/edits.json --out generated/halation/h1/edits.json [--version 0.31h1] [--swap]

apply(spec, version='0.31h1', swap=False) -> spec. Layer on v0.30 (needs grain_cpu r2). Two call sites inside gc_gs are re-pointed
(gc_lvl -> hl_lvl, gc_grain -> hl_grain); the code sits in the unused tail of grain's claim (dead EVF gamma tables).
Look fields, no format change: effect_id +28 = 2 (tint +45, 0 = red), or 1 with tint 1..4; strength +29 = 1..5.
--swap: the tint table with C0 / C1 exchanged, if the camera shows a blue halo for red (the Cb / Cr byte order guess is wrong).
"""
import argparse, copy, importlib.util, json, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


R2 = _load('grain_r2_for_hl', ROOT / 'patches/grain_cpu/build_r2.py')
T1, MV, SB3, FV = R2.T1, R2.MV, R2.SB3, R2.FV
BASE, SRC = 0x60020020, 'patches/halation'
# three placements, all dead EVF gamma table space in section 1 (docs/CODE_SPACE_MAP.md "halation")
REGIONS = {'.text': (0x601e0850, 0x601e0b3c),    # pass B, helpers, hot loops, tables: the unused tail of grain r2's claim (grain ends 0x601e084d)
           '.hlb': (0x601de880, 0x601dea3c),     # entries + hl_run checks / buffers: after recview's gk_* claim (to 0x601de880), before min_ss
           '.hlc': (0x601e3ae4, 0x601e3b3c),     # pass A + the exit: the unused tail of the v0.25 claim (dead EVF step-0 B)
           '.hlp': (0x605b7780, 0x605b7800),     # coverage + pass C: section 3 FF tail after the SD loader v3 claim (to 0x605b7780), to the load end
           '.hlf': (0x601de280, 0x601de33c),     # h2 stage / flag hook / pick reset / labels: the unused tail of sharp_off's claim (sh_* end 0x601de280)
           '.hll': (0x601e1e04, 0x601e1e3c),     # h2 Halo labels: dead EVF step-9 R tail after aspect_scp's block (to 0x601e1e00), before mv's claim;
                                                 # from +4 so the byte-table word 0xa01e1e01 at 0x611a5fc4 stays outside
           '.hlx': (0x6143a350, 0x6143a3f0)}     # h2 Extras sector 11: section 9 FF tail before film menu v2's guard (0x6143a400); the 0x613feff6 bound
                                                 # is a wrapping hash-table limit that never reads past 0x6143a350 (HSL_PORT.md section table)
STEP_WORDS = (0x601e3b50, 0x601e3d80)            # the dead tables' step-table words: the only allowed references
TBL_IDX = 0x6055e7b0
FALSE_POS = {0x606c81c5: 'cce21da0',          # jmp 0x606c9fa7 bytes (sharp_off's pinned false positive), dis-checked
             0x613feff8: '50a34361'}          # cmp 0x6143a350,a0: the wrapping hash-table bound, never reads the suffix (HSL_PORT.md)

# the look: threshold on Y, gmax per stage (the coverage cap, a third of the cells, is in hl.s.in)
THR = 224
GMAX = (112, 176, 240)                     # h2 stages Low / Med / High (Med = h1's CineStill 800T, strength 4)
# tint rows at full glow on black: (dY, dC0, dC1); C0 = byte 1 (Cb if the guess is right), C1 = byte 3 (Cr)
TINTS = {'red': (48, -24, 72), 'amber': (56, -48, 48), 'warm': (56, -36, 30), 'cool': (48, 48, -20)}
ORDER = ('red', 'amber', 'warm', 'cool')     # bloom_tint 1..4


def assemble(src, syms):
    """Like SB3.assemble, with one output per placement section -> ({sec: bytes}, symbols, listing)."""
    import subprocess, tempfile
    TC = SB3.TC
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        (t / 'p.s').write_text(src)
        subprocess.run([TC / 'mn10300-elf-as', '-a=' + str(t / 'p.lst'), '-o', t / 'p.o', t / 'p.s'], check=True)
        subprocess.run([TC / 'mn10300-elf-ld', '-e', '0', *[f'--section-start={k}={v[0]:#x}' for k, v in REGIONS.items() if k != '.text'], '-Ttext', hex(REGIONS['.text'][0]),
                        *[f'--defsym={k}={v:#x}' for k, v in syms.items()], '-o', t / 'p.elf', t / 'p.o'], check=True)
        out = {}
        for k in REGIONS:
            subprocess.run([TC / 'mn10300-elf-objcopy', '-O', 'binary', '-j', k, t / 'p.elf', t / f'p{k}.bin'], check=True)
            out[k] = (t / f'p{k}.bin').read_bytes()
        nm = subprocess.run([TC / 'mn10300-elf-nm', t / 'p.elf'], check=True, capture_output=True, text=True).stdout
        sy = {n: int(a, 16) for a, ty, n in (l.split() for l in nm.splitlines() if len(l.split()) == 3) if ty in 'tTdDrR'}
        dis = subprocess.run([TC / 'mn10300-elf-objdump', '-d', *[x for k in REGIONS for x in ('-j', k)], t / 'p.elf'], check=True, capture_output=True, text=True).stdout
        return out, sy, (t / 'p.lst').read_text() + '\n' + dis


def check_refs(stock):
    import numpy as np
    for lo, hi in REGIONS.values():
        for off in range(4):
            w = np.frombuffer(stock[off:off + (len(stock) - off) // 4 * 4], dtype='<u4')
            for k in np.nonzero(((w >= lo) & (w < hi)) | ((w >= lo + 0x40000000) & (w < hi + 0x40000000)))[0]:
                at = BASE + off + 4 * int(k)
                if STEP_WORDS[0] <= at < STEP_WORDS[1]:
                    continue
                if at in R2.FALSE_POS and stock[at - BASE:at - BASE + len(R2.FALSE_POS[at]) // 2].hex() == R2.FALSE_POS[at]:
                    continue
                if at in T1.FALSE_POS and stock[at - BASE:at - BASE + len(T1.FALSE_POS[at]) // 2].hex() == T1.FALSE_POS[at]:
                    continue
                if at in FALSE_POS and stock[at - BASE:at - BASE + len(FALSE_POS[at]) // 2].hex() == FALSE_POS[at]:
                    continue
                raise SystemExit(f'reference into {lo:#x}..{hi:#x} at {at:#x}: {stock[at - BASE - 2:at - BASE + 6].hex()}')


def tint_rows(swap):
    out = []
    for n in ORDER:
        y, c0, c1 = TINTS[n]
        out.append((y, c1, c0) if swap else (y, c0, c1))
    return out


def source(swap):
    s = (HERE / 'hl.s.in').read_text()
    tl = '\n'.join(' .long ' + ','.join(str(v) for v in r) for r in tint_rows(swap))
    return s.replace('{cap_mode}', str(T1.CAP_MODE)).replace('{cap_profile}', str(T1.CAP_PROFILE)).replace('{thr}', str(THR)).replace('{gmax}', ','.join(map(str, GMAX))).replace('{tint}', tl)


SITES = {0x601dfe2a: ('gc_lvl', 'hl_lvl', bytes.fromhex('c010')), 0x601dfe9d: ('gc_grain', 'hl_grain', bytes.fromhex('f090'))}


def apply(spec, version='0.31h2', swap=False):
    stock = T1.STOCK.read_bytes()
    spec = copy.deepcopy(spec)
    if 'halation' in spec:
        raise SystemExit('halation already applied')
    if spec.get('grain_cpu', {}).get('test') != 'r2':
        raise SystemExit('needs grain_cpu r2 (v0.27 or later)')
    spec = FV.apply(spec, version)
    im = MV.img_of(spec, stock)
    g = {k: int(v, 16) for k, v in spec['grain_cpu']['symbols'].items()}
    if g['gc_end'] > REGIONS['.text'][0]:
        raise SystemExit(f'grain block ends at {g["gc_end"]:#x}')
    for e in spec['edits']:
        if not e['addr'].startswith('off:') and e['kind'] == '0x100':
            a, n = int(e['addr'], 16), len(e['new']) // 2
            for lo, hi in REGIONS.values():
                if a < hi and lo < a + n:
                    raise SystemExit(f'overlap with edit {e["addr"]} in {lo:#x}..{hi:#x}')
    check_refs(stock)
    sh = {k: int(v, 16) for k, v in spec['sharp_off']['symbols'].items()}
    syms = dict(T1.SYMS, ep7_tbl_idx=TBL_IDX, ep7_bloom_flag=int(spec['bloom']['symbols']['bloom_flag'], 16), ep7_gc_ua=g['gc_ua'],
                ep7_sh_sg=sh['sh_sg'], ep7_sh_ss=sh['sh_ss'], ep7_sh_su=sh['sh_su'], ep7_sh_def=sh['sh_def'],
                ep7_g_val=0x601e3322, ep7_s_dirty=0x601e3428, ep7_ex_get=0x601e32a3, ep7_q_put0=0x601e35b4, ep7_q_out=0x601e35ea,
                **{k: v for k, v in g.items() if k in ('gc_lvl', 'gc_grain', 'gc_blk', 'gc_open')})
    for lo, hi in (REGIONS['.hlx'], REGIONS['.hlf'], REGIONS['.hlp']):
        if any(b != 0xff for b in stock[lo - BASE:hi - BASE]) and lo != REGIONS['.hlf'][0]:
            raise SystemExit(f'{lo:#x}..{hi:#x} is not FF in stock')
    src = source(swap)
    out, s, lst = assemble(src, syms)
    for k, (lo, hi) in REGIONS.items():
        if lo + len(out[k]) > hi:
            raise SystemExit(f'{k}: {len(out[k])} B does not fit {hi - lo}')
    if s['hl_tint'] % 4:
        raise SystemExit('hl_tint misaligned')
    for k in REGIONS:
        lo = REGIONS[k][0]
        ins = SB3.disasm(out[k], lo, s['hl_tint'] if k == '.text' else s['hl_xl'] if k == '.hlf' else None)
        if k == '.hll':
            continue
        if any(kd == 'abs' for _, _, kd, _ in SB3.store_audit(ins)):
            raise SystemExit(f'{k}: absolute store')
        if any(op in T1.BAD for _, op, _ in ins) or any(out[k][a - lo] == 0xfb for a, _, _ in ins):
            raise SystemExit(f'{k}: forbidden instruction or fb-prefixed form')
    for k, (lo, hi) in REGIONS.items():
        spec['edits'].append(dict(kind='0x100', addr=hex(lo), expect=stock[lo - BASE:lo - BASE + len(out[k])].hex(), new=out[k].hex(), source=SRC,
                                  why=f'halation {version} {k} ({len(out[k])} B, dead EVF gamma table space)'))
    for at, (old, new, tail) in SITES.items():
        cur = im[at - BASE:at - BASE + 5]
        if cur[0] != 0xcd or at + struct.unpack('<h', cur[1:3])[0] != g[old] or cur[3:] != tail:
            raise SystemExit(f'{at:#x}: not `call {old}`: {cur.hex()}')
        d = s[new] - at
        if not -0x8000 <= d < 0x8000:
            raise SystemExit(f'{new} out of rel16 reach')
        MV.put(spec, stock, at + 1, cur[1:3], struct.pack('<h', d), f'halation: gc_gs call {old} -> {new}')
    # h2: Extras sector 11 (+52), flag hook, pick reset, loaders
    sites2 = {}
    def rj(at, old, new, why, op=0xdc):
        cur = im[at - BASE:at - BASE + 5]
        if cur != bytes([op]) + struct.pack('<i', old - at):
            raise SystemExit(f'{at:#x}: {cur.hex()} is not the expected jump to {old:#x} ({why})')
        MV.put(spec, stock, at + 1, cur[1:], struct.pack('<i', s[new] - at), f'halation h2: {why}')
        sites2[hex(at)] = new
    rj(0x601dfdcd, syms['ep7_bloom_flag'], 'hl_flag', 'gc_flag tail jmp bloom_flag -> hl_flag')
    rj(0x601e2e35, g['gc_ua'], 'hl_ua', 'u_apply jmp gc_ua -> hl_ua (a pick resets +52)')
    for at, old, new in ((0x601e1263, 'sh_sg', 'hl_sg'), (0x601e128b, 'sh_ss', 'hl_ss'), (0x601e12ea, 'sh_su', 'hl_su'), (0x601e3348, 'sh_def', 'hl_def')):
        rj(at, sh[old], new, f'{old} -> {new} (sector 11)')
    cur = im[0x601e12a8 - BASE:0x601e12ae - BASE]
    if cur != b'\xfc\xde' + struct.pack('<I', sh['sh_x']):
        raise SystemExit('tone_x label site differs')
    MV.put(spec, stock, 0x601e12a8, cur, b'\xfc\xde' + struct.pack('<I', s['hl_xl']), 'halation h2: sector 12 label "Extras: 1-11 only"')
    RANGE = 0x605b7721
    MV.put(spec, stock, RANGE + 52, b'\x00', b'\x04', 'halation h2: SD loader v3 range slot +52 0..4')
    for at, what in ((0x601e0d10, 'mv_load (MOVIE.BIN)'), (0x601df8e2, 'ap_load (AP.BIN)')):
        cur = im[at - BASE:at - BASE + 7]
        if cur != bytes.fromhex('fad0640380 0c04'.replace(' ', '')):
            raise SystemExit(f'{what} zero check at {at:#x} differs: {cur.hex()}')
        MV.put(spec, stock, at, cur, bytes.fromhex('fad0650380 0b04'.replace(' ', '')), f'halation h2: {what} zero check from +53, 11 B (+52 is the reader\'s to check)')
    spec['halation'] = dict(built_by=SRC, test='h2', version=version, regions={k: [hex(lo), hex(hi), len(out[k])] for k, (lo, hi) in REGIONS.items()}, swap=swap,
                            thr=THR, cover='off when 3 x (cells with g >= 16) > cells', cell=64, gmax=list(GMAX), tints={n: r for n, r in zip(ORDER, tint_rows(swap))},
                            sites={hex(a): v[1] for a, v in SITES.items()}, sites_h2=sites2, slot_byte=52, sector=11,
                            stages={'0': 'look', '1': 'off', '2': 'low', '3': 'med', '4': 'high'}, symbols={k: hex(v) for k, v in s.items() if k.startswith('hl_')})
    return spec


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--version', default='0.31h2')
    ap.add_argument('--swap', action='store_true')
    a = ap.parse_args()
    spec = apply(json.loads(a.spec.read_text()), a.version, a.swap)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(spec, indent=1))
    print(json.dumps({k: v for k, v in spec['halation'].items() if k != 'symbols'}))
