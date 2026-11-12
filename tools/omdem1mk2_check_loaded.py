#!/usr/bin/env python3
"""Check that every main-image (0x100) edit of an E-M1 II release lies inside bytes the camera really loads.

Section ranges come from the firmware's own loader: descriptor table 0x60027450 ({start, source, dest}),
end getter 0x60042b35 (mov imm32,d0 stubs), plus the resident base 0x60021020..first section start.
Anything outside is never copied to RAM (the v0.1-v0.3b1 preset-table bug).

  em1mk2/scripts/check_loaded.py releases/em1mk2/v0.3b2/edits.json
"""
import json, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
B = 0x60021020
D = (ROOT / 'em1mk2/extracted/00_0100_40560020.decoded.bin').read_bytes()
w = lambda a: struct.unpack_from('<I', D, a - B)[0]

# Edits outside section loads that are known to reach RAM another way.
KNOWN = {
    # .data initial image word: copied to .data 0x61fbd4f4 at boot by the data initialiser, not a section
    # load. Camera-proven: the guide label hook it installs has drawn banners since v0.1.
    0x60297fb4: '.data init image (camera-proven)',
}

ends = []
jt = 0x6004354c  # jump table loaded at 0x60042b41 (mov 0x6004354c,a0)
for i in range(9):
    t = w(jt + 4 * i)
    assert D[t - B] == 0xfc and D[t - B + 1] == 0xcc, 'end getter stub layout changed'
    ends.append(struct.unpack_from('<I', D, t - B + 2)[0])
ranges = [(B, w(0x60027450))]  # resident base
for i in range(9):
    st = w(0x60027450 + 12 * i)
    if ends[i] > st:
        ranges.append((st, ends[i]))

bad = 0
for e in json.load(open(sys.argv[1]))['edits']:
    if e['kind'] != '0x100':
        continue
    a = int(e['addr'], 16); n = len(e['new']) // 2
    ok = any(lo <= a and a + n <= hi for lo, hi in ranges)
    if not ok and a in KNOWN:
        print(f'known       {a:#x}  {KNOWN[a]}')
        continue
    if not ok:
        bad += 1
        print(f'NOT LOADED  {a:#x}..{a + n:#x}  {e["why"][:70]}')
print('ranges', [(hex(lo), hex(hi)) for lo, hi in ranges])
print('OK' if not bad else f'{bad} edit(s) outside loaded sections')
sys.exit(1 if bad else 0)
