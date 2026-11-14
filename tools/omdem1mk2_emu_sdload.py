#!/usr/bin/env python3
"""E-M1 Mark II: emulate the LOOKS.BIN loader (patches/omdem1mk2/sd_loader) through real half-presses, on a release spec.

    python3 tools/omdem1mk2_emu_sdload.py releases/em1mk2/<ver>/edits.json

Each event enters at the firmware's own hook site 0x602f7bf7 (HLS event loop 0x602f7b11, event at (52,sp)) and must come
back at 0x602f7bff with d0 = the event and the Z flag of stock's `btst 0x02000000,d0` (the beq there), d2/d3/a2/a3 kept.
v0.4c15 moved the hook here; 0x6023d0db (v0.4c14 and older) never runs on a half-press (camera: C0.0).
The camera's file / heap calls (fopen 0x6062ce6a, fseek, ftell, fread, fclose, malloc 0x600231fe, free) are replaced by
emulator-only stand-ins (tools/emu_fixtures/em1_fs_stubs.s, same call frames). P is pre-created (handle at 0x621e24ae).
Scenarios (state = P+6: 0 not yet, 1 loaded, 0xFFFF CF; tries = P+82):
  ready3  fopen succeeds from its 4th call (press 2, slot D:) -> press 1 retry (0), press 2 loaded (1), look count = the file's
  none    no file ever -> 0 for 7 presses, CF (0xFFFF) at the 8th, no more attempts after
  badcrc  file opens but its CRC is wrong -> CF at once
  events  other events (button / dial / 0x02000101 half-press release / ...) -> no attempt, flags as stock
  nosect  half-press before all sections are loaded (0xa2767afc & 0x1ff != 0x1ff) -> no attempt
Not emulated: the real card driver (whether fopen on a not-ready card returns 0 quickly -- it does in stock use).
"""
import json, struct, subprocess, sys, tempfile, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'external/oly_fw_analysis/tools'))
import omdem1mk2_emu_validator as V  # noqa: E402
from penf_emulator import Region, execute  # noqa: E402

SECS = [(0x60021020, 0x600de000), (0x600de000, 0x60257800), (0x602ae000, 0x60580800), (0x60591800, 0x605d3000),
        (0x605d5000, 0x6078f000), (0x60796000, 0x60bc8800), (0x60bf1000, 0x612e7000), (0x61300000, 0x613ed000),
        (0x613f6800, 0x6146d000)]
FUNCS = {'s_fopen': 0x6062ce6a, 's_fclose': 0x6062ce73, 's_fread': 0x6062cff9, 's_fseek': 0x6062d0f1,
         's_ftell': 0x6062d087, 's_malloc': 0x600231fe, 's_free': 0x6002323d}
STUB, CTL, FILE, HEAP, STK = 0x9e000000, 0x9e100000, 0x9e200000, 0x9e400000, 0x9f000000
HOOK, BACK = 0x602f7bf7, 0x602f7bff
HALF = 0x02000100
SECBITS = 0xa2767afc
HANDLE = 0x20
P = 0xa1b00000 + (HANDLE << 7)
P_RAM = 0x621e2000
TC = Path('/home/hertzel/ep7fw-toolchains/mn10300/bin')


def stubs():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        subprocess.run([str(TC / 'mn10300-elf-as'), str(ROOT / 'tools/emu_fixtures/em1_fs_stubs.s'), '-o', str(t / 'o')], check=True)
        subprocess.run([str(TC / 'mn10300-elf-ld'), f'--section-start=.text={STUB:#x}', '-e', '_start', str(t / 'o'),
                        '-o', str(t / 'e'), f'--defsym=CTL={CTL:#x}'], check=True)
        subprocess.run([str(TC / 'mn10300-elf-objcopy'), '-O', 'binary', str(t / 'e'), str(t / 'b')], check=True)
        nm = subprocess.run([str(TC / 'mn10300-elf-nm'), str(t / 'e')], capture_output=True, text=True).stdout
        syms = {p[2]: int(p[0], 16) for p in (l.split() for l in nm.splitlines()) if len(p) == 3}
        return (t / 'b').read_bytes(), syms


def image_with_stubs(img, syms):
    m = bytearray(img)
    for name, a in FUNCS.items():
        j = b'\xdc' + struct.pack('<i', syms[name] - a)
        m[a - V.B:a - V.B + 5] = j
    return bytes(m)


def looks_file(bad=False):
    f = bytearray((ROOT / 'releases/em1mk2/v0.4c13/card/EM1MOD/LOOKS.BIN').read_bytes())
    if bad:
        f[100] ^= 0xff
    return bytes(f)


def run_presses(img, code, ready_from, filedata, presses, events=None, secbits=0x1ff):
    ctl = bytearray(0x40)
    struct.pack_into('<IIIIII', ctl, 0, ready_from, 0, len(filedata), FILE, HEAP, 0)
    pblk = bytearray(0x200)
    struct.pack_into('<IH', pblk, 0, 0x50314d45, HANDLE)
    pram = bytearray(0x1000)
    struct.pack_into('<H', pram, 0x4ae, HANDLE)
    heap = bytes(0x4000)
    out = []
    events = events or [HALF] * presses
    for k, ev in enumerate(events):
        rg = [Region(f's{i}', lo, img[lo - V.B:hi - V.B], 'rx') for i, (lo, hi) in enumerate(SECS)]
        rg += [Region('stub', STUB, code, 'rx'), Region('ctl', CTL, bytes(ctl), 'rw', True),
               Region('file', FILE, filedata, 'r'), Region('heap', HEAP, heap, 'rw', True),
               Region('p', 0xa1b00000 + (HANDLE << 7), bytes(pblk), 'rw', True),
               Region('pram', P_RAM, bytes(pram), 'rw', True), Region('stk', STK, bytes(0x2000), 'rw'),
               Region('fh', 0x9e7f0000, bytes(16), 'rw'),
               Region('sec', SECBITS & ~0xff, bytes(0xfc) + struct.pack('<I', secbits), 'r')]
        stk = bytearray(0x2000)
        sp = STK + 0x1000
        struct.pack_into('<I', stk, 0x1000 + 52, ev)          # the loop frame's event word
        rg = [x if x.name != 'stk' else Region('stk', STK, bytes(stk), 'rw') for x in rg]
        regs = {'pc': HOOK, 'sp': sp, 'd2': 0x11112222, 'd3': 0xffff, 'a2': 0x62258d40, 'a3': 0x33334444}
        r = execute(rg, regs, 0xfffffff0, limit=3_000_000, breakpoints=[BACK])
        if r['status'] != 'breakpoint' or r['fault']:
            out.append(('fault', hex(r['registers']['pc']), r['fault']))
            break
        mem = {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}
        ctl, pblk, pram, heap = bytearray(mem['ctl']), bytearray(mem['p']), bytearray(mem['pram']), mem['heap']
        g = r['registers']
        z = (g['psw'] >> 0) & 1                                 # PSW.Z = bit 0
        want_z = int((ev & 0x02000000) == 0)
        if g['d0'] != ev or z != want_z or g['sp'] != sp or any(g[k] != v for k, v in regs.items() if k not in ('pc', 'sp')):
            out.append(('regs', hex(g['d0']), z, want_z))
            break
        state, = struct.unpack_from('<H', pblk, 6)
        nlooks, = struct.unpack_from('<H', pblk, 28)
        out.append((state, pblk[82], struct.unpack_from('<I', ctl, 4)[0], nlooks))
    return out


def main():
    code, syms = stubs()
    new = image_with_stubs(V.image(sys.argv[1]), syms)
    good, bad = looks_file(), looks_file(True)
    n_file = (len(good) - 64) // 64
    fails = 0
    # ready3: fopen succeeds from its 4th call = press 2, slot D: (two fopen calls per attempt: C: then D:)
    cases = [('ready3', new, 4, good, 6,
              lambda o: [x[0] for x in o] == [0, 1, 1, 1, 1, 1] and o[1][3] == n_file and o[-1][2] == 4),
             ('none', new, 0, good, 10,
              lambda o: [x[0] for x in o] == [0] * 7 + [0xffff] * 3 and o[-1][1] == 8 and o[-1][2] == 16),
             ('badcrc', new, 1, bad, 3,
              lambda o: [x[0] for x in o] == [0xffff] * 3 and o[-1][2] == 1)]
    for name, img, ready, data, presses, want in cases:
        o = run_presses(img, code, ready, data, presses)
        ok = all(not (isinstance(x, tuple) and x and x[0] == 'fault') for x in o) and want(o)
        fails += not ok
        print(f'{name:7s} (state, tries, fopen calls, looks) per press: {o}' + ('' if ok else '  !'))
    other = [0x02000101, 0x02010101, 0x04020301, 0x07010001, 0x01000100, 0x02000200, 0, 0xffffffff]
    o = run_presses(new, code, 1, good, 0, events=other)
    ok = len(o) == len(other) and all(x[0] == 0 and x[1] == 0 and x[2] == 0 for x in o)
    fails += not ok
    print(f'events  (no half-press: {[hex(e) for e in other]}): {o}' + ('' if ok else '  !'))
    o = run_presses(new, code, 1, good, 0, events=[HALF] * 3, secbits=0x17f)
    ok = len(o) == 3 and all(x[0] == 0 and x[1] == 0 and x[2] == 0 for x in o)
    fails += not ok
    print(f'nosect  (half-press, section 8 bit clear): {o}' + ('' if ok else '  !'))
    o = run_presses(new, code, 1, good, 0, events=[0x04020301, 0x02010100, 0x02000101])
    ok = len(o) == 3 and [x[0] for x in o] == [0, 1, 1] and o[-1][2] == 1
    fails += not ok
    print(f'mixed   (dial, half-press 0x02010100, release): {o}' + ('' if ok else '  !'))
    print('RESULT', 'PASS' if not fails else f'FAIL ({fails})')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
