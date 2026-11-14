#!/usr/bin/env python3
"""E-M1 Mark II: emulate the code-space probe sp1 (patches/omdem1mk2/space_probe) on a release spec.

    python3 tools/omdem1mk2_emu_space.py releases/em1mk2/<ver>/edits.json

E  the loader's end getter 0x60042b35 for section 5 (d0 = 6), stock vs patched: 0x612e7000 -> 0x61300000; and the flash
   span it implies ends at section 6's source (contiguous copy).
P  the probe stub natively, on three region states: as built -> " S+", all 0xFF (not loaded) -> " S0", one word changed
   (overwritten at runtime) -> " S!"; a2 advanced by 6 characters, d2/d3/a3 and sp unchanged.
C  from the look editor's own call instruction (`call SPROBE,[],4`) through the stub and back to the next instruction.
Not emulated: the loader's flash-to-RAM copy itself (flash mapping 0x6006884b / copy 0x6005ae5b) -- that is what the
camera probe shows.
"""
import json, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'external/oly_fw_analysis/tools'))
import omdem1mk2_emu_validator as V  # noqa: E402
from penf_emulator import Region, execute  # noqa: E402

SECS = [(0x60021020, 0x600de000), (0x600de000, 0x60257800), (0x602ae000, 0x60580800), (0x60591800, 0x605d3000),
        (0x605d5000, 0x6078f000), (0x60796000, 0x60bc8800), (0x60bf1000, 0x612e7000), (0x61300000, 0x613ed000),
        (0x613f6800, 0x6146d000)]
SP = json.loads((ROOT / 'patches/omdem1mk2/space_probe/exports.json').read_text())
STK, TXT = 0x9f000000, 0x9f100000


def regions(img, region=None):
    rg = [Region(f's{i}', lo, img[lo - V.B:hi - V.B], 'rx') for i, (lo, hi) in enumerate(SECS)]
    if region is not None:
        rg.append(Region('probe', SP['REGION'], region, 'rw'))
    return rg + [Region('stk', STK, bytes(0x2000), 'rw', True), Region('txt', TXT, bytes(0x40), 'rw', True)]


def run(img, pc, stop, regs, region=None):
    r = execute(regions(img, region), dict({'pc': pc, 'sp': STK + 0x1000}, **regs), 0xfffffff0, limit=400000,
                breakpoints=[stop])
    if r['status'] != 'breakpoint' or r['fault']:
        return None, r
    return r['registers'], {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}


def text(mem, n):
    return mem['txt'][:2 * n].decode('utf-16le')


def main():
    old, new = V.image(None), V.image(sys.argv[1])
    fails = 0
    print('E  loader end getter 0x60042b35, section 5 (d0 = 6)')
    ends = []
    for im in (old, new):
        regs, _ = run(im, 0x60042b35, 0x60042b94, {'d0': 6})
        ends.append(regs['d0'] if regs else None)
    src5 = struct.unpack_from('<I', new, 0x60027450 + 12 * 5 + 4 - V.B)[0]
    src6 = struct.unpack_from('<I', new, 0x60027450 + 12 * 6 + 4 - V.B)[0]
    st5 = struct.unpack_from('<I', new, 0x60027450 + 12 * 5 - V.B)[0]
    span_end = src5 + (ends[1] - st5) if ends[1] else None
    ok = ends == [0x612e7000, 0x61300000] and span_end == src6
    fails += not ok
    print(f'   stock {ends[0]:#x} patched {ends[1]:#x}; flash span ends {span_end:#x} (section 6 source {src6:#x})' + ('' if ok else '  !'))
    built = new[SP['REGION'] - V.B:SP['REGION_END'] - V.B]
    bad = bytearray(built); bad[0x8000] ^= 1
    print('P  probe stub', hex(SP['SPROBE']))
    for name, reg, want in (('as built', built, ' S+'), ('not loaded (0xFF)', b'\xff' * len(built), ' S0'),
                            ('one word changed', bytes(bad), ' S!')):
        # as after `call SPROBE,[],4`: return address at (4,sp) (the call stores it, then sp -= 4)
        stk = bytearray(0x2000); struct.pack_into('<I', stk, 0x1004, 0x9f300000)
        rg = regions(new, reg)
        rg[-2] = Region('stk', STK, bytes(stk), 'rw', True)
        rg.append(Region('ret', 0x9f300000, b'\xcb', 'rx'))
        r = execute(rg, {'pc': SP['SPROBE'], 'sp': STK + 0x1000, 'a2': TXT, 'd2': 0x11, 'd3': 0x22, 'a3': 0x33},
                    0xfffffff0, limit=400000, breakpoints=[0x9f300000])
        regs, mem = r['registers'], {x['name']: bytes.fromhex(x['hex']) for x in r['memory']}
        okr = r['status'] == 'breakpoint' and not r['fault'] and regs['sp'] == STK + 0x1004
        got = text(mem, 3)
        ok = okr and got == want and regs['a2'] == TXT + 6 and (regs['d2'], regs['d3'], regs['a3']) == (0x11, 0x22, 0x33)
        fails += not ok
        print(f'   {name:18s} -> {got!r} a2+{regs["a2"] - TXT}' + ('' if ok else '  !'))
    print('C  editor call site')
    site = None
    for e in json.load(open(sys.argv[1]))['edits']:
        if e['addr'] == '0x612e6900':
            b = bytes.fromhex(e['new'])
            for i in range(len(b) - 6):
                if b[i] == 0xdd and (0x612e6900 + i + struct.unpack_from('<i', b, i + 1)[0]) & 0xffffffff == SP['SPROBE']:
                    site = 0x612e6900 + i
    if site is None:
        fails += 1
        print('   no `call SPROBE` in the look editor (build with EM1_SPACE_PROBE=1)  !')
    else:
        regs, mem = run(new, site, site + 7, {'a2': TXT}, built)
        ok = regs is not None and text(mem, 3) == ' S+' and regs['sp'] == STK + 0x1000
        fails += not ok
        print(f'   call at {site:#x} -> back at {site + 7:#x}, text {text(mem, 3) if regs else None!r}, sp restored {regs and regs["sp"] == STK + 0x1000}' + ('' if ok else '  !'))
    print('RESULT', 'PASS' if not fails else f'FAIL ({fails})')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
