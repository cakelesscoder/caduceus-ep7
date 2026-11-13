#!/usr/bin/env python3
"""scp_name checks (emulator, real code from the built package). Offline. Minimal + anti-brick.

  .venv/bin/python -I patches/scp_name/verify.py releases/v0.31d/edits.json generated/v031e_scp/edits.json [generated/v031e_scp/rel]

  X  the real site 0x60e2757d -> sn_gd -> the guide word 0x6025aa98 -> (a mock in place of ap_gd at the word's target) ->
     back at 0x60e27589, v0.31d vs 0.31e. The mock records the view it was handed and writes a label of kind 5 or 4.
     Card table (h, 'EP7B') valid: the mock runs once, on a 140-B zeroed fake view at the call's sp+4 with +128 = 1; a kind-5
     result replaces the page's 74-B label, a kind-4 result leaves the stock label. No/bad table: the mock never runs, label
     stock. Every case: d0 = 2, d1 d2 d3 a1 a2 a3 sp mdr == v0.31d, the caller's stack above sp == v0.31d, no fault.
  Y  label/stack accesses of sn_gd are aligned (the page's label is 2-aligned like stock's movhu stores).
  P  anti-brick: package decodes to stock + edits (the image X ran), restore == stock, bytes differing from v0.31d are only
     sn_gd, the 12-B site and the fw_version label.
"""
import json, struct, sys, subprocess, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'external/oly_fw_analysis/tools'))
import build_package as BP  # noqa: E402
import oly_container as oc  # noqa: E402
import importlib.util  # noqa: E402


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


W = _load('ep7_wb_v_sn', ROOT / 'tools/ep7_verify_wb.py')
SB3 = _load('ep7_sd_bundles_v3_build_snv', ROOT / 'patches/sd_bundles_v3/build.py')
Region, execute = W.Region, W.execute
BASE, SITE, BACK, GD_WORD = 0x60020020, 0x60e2757d, 0x60e27589, 0x6025aa98
POOL, HANDLE = 0xa1f8d800, 0x41
P = POOL + HANDLE - 1
LBL, REC = 0x13000000, 0x13100000
REGS0 = dict(d1=0xd1d1, d2=0x2222, d3=0x3333, a0=0xa0a0, a1=0xa1a1, a2=0xa2a2, mdr=0x6d6d)
KEEP = ('d1', 'd2', 'd3', 'a1', 'a2', 'a3', 'sp', 'mdr', 'pc')


def image(spec):
    pkg, rst, info = BP.build(spec, BP.STOCK.read_bytes())
    return [b for b in oc.parse(pkg) if b.kind == 0x100][0].payload, pkg, rst, info


def mock(at, kind):
    src = f""" .am33_2
 .text
 .global _start
_start:
 mov a0,d0
 mov {REC:#x},a1
 mov d0,(140,a1)
 mov 35,d1
1:
 mov (a0),d0
 mov d0,(a1)
 add 4,a0
 add 4,a1
 add -1,d1
 bne 1b
 add -140,a0
 mov {kind},d0
 movhu d0,(44,a0)
 mov 777,d0
 movhu d0,(48,a0)
 mov 77,d0
 movhu d0,(52,a0)
 mov 107,d0
 movhu d0,(54,a0)
 mov 0xdead1111,d1
 mov 0xdead2222,a1
 rets
"""
    code, _, _, _ = SB3.assemble(src, at, {})
    return code


def label0(idv):
    return b'\xee' * 80                                              # the page's label before the site (id written by it)


def run(im, idv, handle=HANDLE, magic=b'EP7B', kind=5):
    sl = lambda lo, hi: im[lo - BASE:hi - BASE]
    word = struct.unpack_from('<I', im, GD_WORD - BASE)[0]
    st = bytearray([W.STACK_FILL] * 0x2000)
    p = bytearray(1024); p[0:4] = magic
    rg = [Region('site', 0x60e27540, sl(0x60e27540, 0x60e275c0), 'rx'),
          Region('sn', 0x61242c00, sl(0x61242c00, 0x61242d00), 'rx'),
          Region('gdw', 0x6025aa80, sl(0x6025aa80, 0x6025aac0), 'r'),
          Region('state', 0x622cbcc0, struct.pack('<HHI', 0, handle, 0), 'r'),
          Region('pool', P, bytes(p), 'r'),
          Region('stack', W.STACK, bytes(st), 'rw', True),
          Region('lbl', LBL, label0(idv), 'rw', True),
          Region('rec', REC, b'\x55' * 144, 'rw', True)]
    if word != 0x60decbfc:
        rg.append(Region('mock', word, mock(word, kind), 'rx'))
    r = execute(rg, dict(pc=SITE, sp=W.SP0, d0=idv, a3=LBL, **REGS0), BACK, limit=5000, trace_limit=5000)
    m = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}
    return r, m


def t_x(base, new):
    n, bad, hits = 0, [], 0
    for idv in (2755, 2756):
        for c in (dict(), dict(kind=4), dict(handle=0), dict(handle=0xffff), dict(handle=HANDLE + 2), dict(magic=b'EP7Q')):
            r0, m0 = run(base, idv, **c)
            r1, m1 = run(new, idv, **c)
            g0, g1 = r0['registers'], r1['registers']
            on = c.get('handle', HANDLE) == HANDLE and c.get('magic', b'EP7B') == b'EP7B'
            stock_lbl = bytearray(label0(idv)); struct.pack_into('<HHHH', stock_lbl, 0, 4, 0xeeee, idv, 2)
            want = bytearray(stock_lbl)
            ok = not r0['fault'] and not r1['fault'] and g0['pc'] == BACK == g1['pc'] and m0['lbl'] == bytes(stock_lbl)
            ok &= all(g0[k] == g1[k] for k in KEEP) and g1['d0'] == 2 == g0['d0']
            sp = g1['sp'] - W.STACK
            ok &= m0['stack'][sp:] == m1['stack'][sp:]
            if on:
                rec = m1['rec']
                fake = struct.unpack_from('<I', rec, 140)[0]
                # the fake sat at (call sp)+4: inside our frame, below the caller's sp
                ok &= fake % 4 == 0 and W.SP0 - 16 - 156 + 4 == fake
                exp = bytearray(140); exp[128] = 1
                ok &= rec[:140] == bytes(exp)
                hits += 1
                if c.get('kind', 5) == 5:
                    f = bytearray(140); f[128] = 1
                    struct.pack_into('<H', f, 44, 5); struct.pack_into('<H', f, 48, 777)
                    struct.pack_into('<HH', f, 52, 77, 107)
                    want[0:74] = f[44:118]
            else:
                ok &= m1['rec'] == b'\x55' * 144
            ok &= m1['lbl'] == bytes(want)
            n += 1
            if not ok:
                bad.append((idv, c, r1['fault'], {k: (hex(g0[k]), hex(g1[k])) for k in KEEP + ('d0',) if g0[k] != g1[k]}, m1['lbl'][:16].hex()))
    return not bad and hits == 4, f'{n} cases, {hits} chain runs; bad {bad[:3]}'


def t_y(new):
    r, m = run(new, 2755)
    bad = []
    # static: every memory operand of sn_gd is sp-relative with a 4-multiple offset, (a0)/(a1) word/half loops, or (k,a3)
    s = json.loads(Path(sys.argv[2]).read_text())['scp_name']
    at = int(s['code_at'], 16)
    code = new[at - BASE:at - BASE + s['code_len']]
    ins = SB3.disasm(code, at, int(s['symbols']['sn_end'], 16))
    import re
    for a, op, args in ins:
        for mm in re.finditer(r'\((-?\d+),sp\)', args):
            if int(mm.group(1)) % 4:
                bad.append((hex(a), op, args))
        for mm in re.finditer(r'\((\d+),a3\)', args):
            if int(mm.group(1)) % 2:
                bad.append((hex(a), op, args))
    return not bad and not r['fault'], f'{len(ins)} instructions, misaligned {bad}'


def t_pkg(base_s, new_s, base, new, pkg, rst, info, disk):
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
    for b in oc.parse(rst):
        good &= b.payload == sb[b.kind].payload
    x = new_s['scp_name']
    ours = [(int(x['code_at'], 16), x['code_len']), (int(x['site'], 16), 12)] + \
        [(int(e['addr'], 16), len(e['new']) // 2) for e in new_s['edits'] if e.get('source') == 'patches/fw_version']
    diff = [BASE + i for i in range(len(base)) if base[i] != new[i]]
    stray = [hex(a) for a in diff if not any(s_ <= a < s_ + k for s_, k in ours)]
    good &= not stray and len(new_s['edits']) == len(base_s['edits']) + 2
    if disk:
        good &= (disk / 'patched.pkg.bin').read_bytes() == pkg and (disk / 'restore-stock.pkg.bin').read_bytes() == rst
    return good, f'{info["edits"]} edits, {info["changed_payload_bytes"]} B; {len(diff)} B differ from v0.31d; stray {stray[:6]}'


def main():
    base_s, new_s = (json.loads(Path(p).read_text()) for p in sys.argv[1:3])
    disk = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    base, *_ = image(base_s)
    new, pkg, rst, info = image(new_s)
    ok = True
    for tag, (g, txt) in (('X', t_x(base, new)), ('Y', t_y(new)), ('P', t_pkg(base_s, new_s, base, new, pkg, rst, info, disk))):
        print(f"{'PASS' if g else 'FAIL'} {tag} {txt}")
        ok &= g
    print('ALL PASS' if ok else 'FAILURES')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
