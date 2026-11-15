#!/usr/bin/env python3
"""v0.33b checks over v0.33a (emulator, real code from the built packages). Offline. Minimal + anti-brick.

  .venv/bin/python -I patches/v033b/verify.py releases/v0.33a/edits.json generated/v033b/edits.json [generated/v033b/rel]

  T  rec_limit estimate: the real clamp 0x603185e1..0x603185ec, (a2) = x -> min(x, 1740) on v0.33a and min(x, 32400) on
     v0.33b (unsigned, as `bcc`); d2 d3 a2 a3 sp kept; the cap 0x60319157 / 0x6031915c is 32400 in both
  M  min_ss: both trees' D1 entry {3327, n 8, rows -> the copy}: 7 stock rows then the 1147 row (stock 8th: 239); the D2 entry
     {5068, n 7} is byte-equal to stock (v0.33a: n 8)
  S  RAW Data Edit Sharpness: the real site 0x60c67072..0x60c67086 (cap in a3) through the real getter: v0.33b gives -5 at
     cap+24010 for COLOR k with slot +51 == 1 in the card table, else the same value as v0.33a; registers and the stack from
     sp up == v0.33a (only the dead area below sp, where the calls put their frames, differs)
  P  anti-brick: v0.33b package decodes to stock + edits, restore == stock, files on disk match; every byte that differs
     from v0.33a is inside one of the intended edits (listed), the crash_log build tag being the only change in cl_nmi
"""
import json, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'external/oly_fw_analysis/tools'))
import build_package as BP  # noqa: E402
import oly_container as oc  # noqa: E402
import importlib.util  # noqa: E402


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


W = _load('ep7_wb_v_033b', ROOT / 'tools/ep7_verify_wb.py')
VB = _load('v033b_build_v', ROOT / 'patches/v033b/build.py')
F = VB.CL.F
Region, execute = W.Region, W.execute
BASE = 0x60020020
POOL, HANDLE = 0xa1f8d800, 0x41
P = POOL + HANDLE - 1
PM, PM6, COL, SHARP = 38017, 40209, 63153, 0x8119
CAP = 0x13000000
REGS0 = dict(d2=0x2222, d3=0x3333, a1=0xa1a1, a2=0xa2a2)
REG = ('d2', 'd3', 'a1', 'a2', 'a3', 'sp', 'pc')


def image(spec):
    pkg, rst, info = BP.build(spec, BP.STOCK.read_bytes())
    return [b for b in oc.parse(pkg) if b.kind == 0x100][0].payload, pkg, rst, info


def mem(r):
    return {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}


# ------------------------------------------------------------------ T
def clamp(im, x):
    st = bytearray(0x2000)
    rg = [Region('code', 0x603185e0, im[0x603185e0 - BASE:0x603185f0 - BASE], 'rx'), Region('ctx', 0x13100000, struct.pack('<I', x), 'rw', True),
          Region('stack', W.STACK, bytes(st), 'rw')]
    r = execute(rg, dict(pc=0x603185e1, sp=W.SP0, d0=x, d2=0x2222, a2=0x13100000, a3=0xa3a3), 0x603185ec, limit=50)
    return r['fault'], r['registers'], struct.unpack('<I', mem(r)['ctx'])[0]


def t_est(old, new):
    bad, n = [], 0
    for x in (0, 1, 1739, 1740, 1741, 5000, 32399, 32400, 32401, 0x7fffffff, 0xffffffff):
        f0, r0, v0 = clamp(old, x)
        f1, r1, v1 = clamp(new, x)
        n += 1
        if f0 or f1 or v0 != min(x, 1740) or v1 != min(x, 32400) or any(r0[k] != r1[k] for k in ('d2', 'a2', 'a3', 'sp', 'pc')):
            bad.append((x, f0, f1, v0, v1))
    for a in (0x60319157, 0x6031915c):
        n += 1
        if struct.unpack_from('<h', new, a - BASE)[0] != 32400 or struct.unpack_from('<h', old, a - BASE)[0] != 32400:
            bad.append(('cap', hex(a)))
    return not bad, f'{n} cases; bad {bad[:3]}'


# ------------------------------------------------------------------ M
def t_menu(old, new, stock):
    bad, n = [], 0
    u16 = lambda m, a: struct.unpack_from('<H', m, a - BASE)[0]
    u32 = lambda m, a: struct.unpack_from('<I', m, a - BASE)[0]
    for d1, d2 in VB.D_ENTRIES:
        n += 1
        rows = u32(new, d1 + 12)
        cp = new[rows - BASE:rows + 36 * 8 - BASE]
        sr = stock[u32(stock, d1 + 12) - BASE:u32(stock, d1 + 12) + 36 * 8 - BASE]
        ok = (u16(new, d1), u16(new, d1 + 2)) == (3327, 8) and rows != u32(stock, d1 + 12) and cp[:36 * 7] == sr[:36 * 7] \
            and struct.unpack_from('<H', cp, 36 * 7)[0] == 1147 and struct.unpack_from('<H', sr, 36 * 7)[0] == 239
        ok &= new[d1 - BASE:d1 + 20 - BASE] == old[d1 - BASE:d1 + 20 - BASE]               # D1 entry as in v0.33a
        ok &= new[d2 - BASE:d2 + 20 - BASE] == stock[d2 - BASE:d2 + 20 - BASE] and u16(new, d2 + 2) == 7 and u16(old, d2 + 2) == 8
        if not ok:
            bad.append(hex(d1))
    return not bad, f'{n} trees; bad {bad}'


# ------------------------------------------------------------------ S
def p_block(b51):
    p = bytearray(1024)
    p[0:4] = b'EP7B'
    for k in range(8):
        p[32 + 64 * k] = k + 1
        p[32 + 64 * k + 7] = 3
        p[32 + 64 * k + 51] = b51[k % 4]
    return bytes(p)


def raw(im, mode, m6, col, sharp, b51, handle=HANDLE):
    sl = lambda lo, hi: im[lo - BASE:hi - BASE]
    pr = {PM: bytes([mode]), PM6: bytes([m6]), COL: bytes([col]), SHARP: struct.pack('<h', sharp)}
    rg = [Region('site', 0x60c67060, sl(0x60c67060, 0x60c670a0), 'rx'),
          Region('getter', W.GETTER_CODE[0], sl(*W.GETTER_CODE), 'rx'), Region('xlate', W.XLATE[0], sl(*W.XLATE)),
          Region('cpuid', W.CPUID, bytes(4)), *W.registry(pr),
          Region('evf', 0x601de000, sl(0x601de000, 0x601e3d80), 'rx'),
          Region('acc', 0x6055e700, sl(0x6055e700, 0x6055e800), 'rx'),
          Region('flashtab', 0x60210900, bytes(512), 'r'),
          Region('state', 0x622cbcc0, struct.pack('<HHI', 0, handle, 0), 'r'),
          Region('bss', 0x6203c8b8, bytes(8), 'r'),
          Region('pool', P, p_block(b51), 'r'),
          Region('stack', W.STACK, bytes([W.STACK_FILL] * 0x2000), 'rw', True),
          Region('cap', CAP, bytes(24100), 'rw', True)]
    r = execute(rg, dict(pc=0x60c67072, sp=W.SP0, a3=CAP, **REGS0), 0x60c67086, limit=20000)
    m = mem(r)
    return r['fault'], r['registers'], struct.unpack_from('<H', m['cap'], 24010)[0], m['stack'][W.SP0 - W.STACK:]   # the caller's live stack


def t_sharp(old, new):
    bad, n, hits = [], 0, 0
    for mode, m6 in ((11, 0), (6, 11), (12, 0), (2, 0)):
        for col in (0, 1, 2, 3, 4, 5):
            for b51 in ((1, 1, 1, 1), (0, 0, 0, 0), (1, 0, 2, 1)):
                for sharp in (-2, 0, 2):
                    for handle in (HANDLE, 0):
                        f0, r0, v0, s0 = raw(old, mode, m6, col, sharp, b51, handle)
                        f1, r1, v1, s1 = raw(new, mode, m6, col, sharp, b51, handle)
                        hit = (mode == 11 or (mode == 6 and m6 == 11)) and 1 <= col <= 4 and handle == HANDLE and b51[col - 1] == 1
                        hits += hit
                        n += 1
                        if f0 or f1 or v0 != sharp & 0xffff or v1 != (0xfffb if hit else v0) or s0 != s1 or any(r0[k] != r1[k] for k in REG):
                            bad.append((mode, m6, col, b51, sharp, handle, f0, f1, v0, v1))
    return not bad and hits > 0, f'{n} cases, {hits} at -5; bad {bad[:3]}'


# ------------------------------------------------------------------ P
def t_pkg(old_s, new_s, old, new, pkg, rst, info, disk, opkg):
    sb = {b.kind: b for b in oc.parse(BP.STOCK.read_bytes())}
    good = True
    for b in oc.parse(pkg):
        exp = bytearray(sb[b.kind].payload)
        for e in new_s['edits']:
            if int(e['kind'], 16) == b.kind:
                o = BP.resolve(b.kind, e['addr']); nb = bytes.fromhex(e['new']); exp[o:o + len(nb)] = nb
        good &= bytes(exp) == b.payload
        if b.kind == 0x100:
            good &= b.payload == new
        else:
            good &= b.payload == [x for x in oc.parse(opkg) if x.kind == b.kind][0].payload      # OSD as in v0.33a
    for b in oc.parse(rst):
        good &= b.payload == sb[b.kind].payload
    cl, ex, zh = new_s['crash_log'], new_s['exif_name'], new_s['i18n_zh']
    tag_new, tag_old = struct.pack('<I', int(cl['build_tag'], 16)), struct.pack('<I', int(old_s['crash_log']['build_tag'], 16))
    cl_lo, cl_n = int(cl['code'][0], 16), cl['code'][1]
    t_at = [cl_lo + i for i in range(cl_n - 3) if new[cl_lo + i - BASE:cl_lo + i + 4 - BASE] == tag_new]
    ours = {'crash_log NMI site -> cl_gate': (int(cl['site'], 16), 6), 'crash_log cl_gate': (int(cl['gate']['code'][0], 16), cl['gate']['code'][1]),
            'crash_log build tag': (t_at[0] if len(t_at) == 1 else 0, 4),
            'exif_name site rel32 -> ex_gate': (VB.EX_SITE + 1, 4), 'v033b ex_gate': (int(ex['gate']['code'][0], 16), ex['gate']['code'][1]),
            'rec_limit estimate imm16': (VB.EST_IMM, 2), 'i18n_zh i18n_gd + table': (int(zh['code'][0], 16), zh['code'][1]),
            'sharp_off RAW-edit rel32': (VB.SH_SITE + 1, 4), 'min_ss D2 n (tree 1)': (0x61160fc2, 2), 'min_ss D2 n (tree 2)': (0x6117ea5e, 2)}
    fv = [e for e in new_s['edits'] if e.get('source') == 'patches/fw_version']
    for e in fv:
        ours[f'fw_version {e["addr"]}'] = (int(e['addr'], 16), len(e['new']) // 2)
    good &= len(t_at) == 1 and old[t_at[0] - BASE:t_at[0] + 4 - BASE] == tag_old
    good &= new[cl_lo - BASE:cl_lo + cl_n - BASE] == old[cl_lo - BASE:t_at[0] - BASE] + tag_new + old[t_at[0] + 4 - BASE:cl_lo + cl_n - BASE]
    import numpy as np
    diff = [BASE + int(i) for i in np.nonzero(np.frombuffer(old, np.uint8) != np.frombuffer(new, np.uint8))[0]]
    stray = [hex(a) for a in diff if not any(s_ <= a < s_ + k for s_, k in ours.values())]
    hit = {name for name, (s_, k) in ours.items() if any(s_ <= a < s_ + k for a in diff)}
    good &= not stray and len(old) == len(new)
    if disk:
        good &= (disk / 'patched.pkg.bin').read_bytes() == pkg and (disk / 'restore-stock.pkg.bin').read_bytes() == rst
    return good, (f'{info["edits"]} edits, {info["changed_payload_bytes"]} B; {len(diff)} B differ from v0.33a, in: {sorted(hit)}; stray {stray[:6]}'
                  + ('; package files on disk match' if disk else ''))


def main():
    old_s, new_s = (json.loads(Path(p).read_text()) for p in sys.argv[1:3])
    disk = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    stock = [b for b in oc.parse(BP.STOCK.read_bytes()) if b.kind == 0x100][0].payload
    old, opkg, *_ = image(old_s)
    new, pkg, rst, info = image(new_s)
    ok = True
    for tag, f in (('T', lambda: t_est(old, new)), ('M', lambda: t_menu(old, new, stock)), ('S', lambda: t_sharp(old, new)),
                   ('P', lambda: t_pkg(old_s, new_s, old, new, pkg, rst, info, disk, opkg))):
        g, txt = f()
        print(f"{'PASS' if g else 'FAIL'} {tag} {txt}", flush=True)
        ok &= g
    print('ALL PASS' if ok else 'FAILURES')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
