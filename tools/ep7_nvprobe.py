#!/usr/bin/env python3
"""Decode EP7MOD/NVPROBE.BIN, the settings-memory probe of patches/nv_store (docs/INTERNAL_STORAGE.md, steps S0 and S1).
Offline, reads the file only.

  .venv/bin/python -I tools/ep7_nvprobe.py /path/to/NVPROBE.BIN [--version 0.34]

The camera writes the file at the first half-press of a power-on, when BUNDLES.BIN has loaded. It holds what that power-on
found in the camera's settings image (S0: reads only) and what the layer then did with its 16-byte marker (S1). This tool
prints both in plain terms, with pass or STOP for each condition the marker write depends on, and one line at the end that
says whether the round can go on. The layout constants below are the format: patches/nv_store/build.py takes them from here.
"""
import argparse, struct, sys, zlib
from pathlib import Path

# ---------------------------------------------------------------- the file (version 1), 128 bytes, little-endian words
FILE_MAGIC, FILE_VERSION, FILE_LEN = b'NVP1', 1, 128
O_MAGIC, O_VERLEN = 0, 4                   # 'NVP1'; version | length << 16
O_FLAGS = 8                                # the F_ bits | action << 24
O_CPU = 12                                 # (0x8050): the CPU the half-press ran on (low half)
O_BANK, O_BRAM, O_BSIZE, O_BID = 16, 20, 24, 28   # MODE bank object pointer; its RAM (+16), size (+20), id | copy << 16 (+0), 0 if the pointer was refused
O_RHDR, O_RGEN = 32, 36                    # RAM image: id | checksum << 16; generation
O_SHDR, O_SGEN = 40, 44                    # the shadow (what the boot read from flash): the same two words
O_SLOT = 48                                # MODE flash slot | EEROM slot << 8 | "MODE image refused at boot" flag << 16
O_TNZ, O_TFIRST = 52, 56                   # non-zero words in the tail outside the reserve; image offset of the first (0 = none)
O_RNZ = 60                                 # non-zero words in the reserve after its first 16 bytes
O_CU, O_CS = 64, 68                        # words of the reserve that differ: cached against uncached, cached against shadow
O_PRE = 72                                 # the reserve's first 16 bytes as found (cached)
O_SHD = 88                                 # the same 16 bytes in the shadow
O_POST0, O_POST1, O_UPOST1 = 104, 108, 112 # after the action: marker word 0 and counter (cached), counter (uncached)
O_STAGE = O_POST0                          # (in the camera only: the 16 bytes to store are built here, then overwritten by 104..119)
O_BUILD = 116                              # zlib.crc32 of the firmware version string
O_NEW = 120                                # the counter the layer meant to write (0 = none)
O_CRC = 124                                # CRC-32 (zlib) of bytes 0..123

F_CPU0, F_BANK, F_ID, F_GEN, F_TAIL, F_REST, F_CU, F_CS = (1 << i for i in range(8))
F_ALL = 0xff                               # every one of these is needed before anything is written
F_ABSENT, F_VALID, F_OURS, F_FORGET, F_READBACK, F_LOCK = (1 << i for i in range(8, 14))
A_NONE, A_WRITTEN, A_CLEARED, A_FORGET_EMPTY, A_SAVE, A_CHANGED, A_FOREIGN, A_DAMAGED = range(8)

# ---------------------------------------------------------------- the marker: 16 bytes at the start of the reserve
M_MAGIC, M_VERSION, M_LEN = b'EP7R', 1, 16  # 'EP7R', u32 counter, u32 version, u32 CRC-32 (zlib) of bytes 0..11

# ---------------------------------------------------------------- where (E-P7 1.1; docs/INTERNAL_STORAGE.md sections 2 and 3.1)
MODE_RAM, MODE_SIZE, MODE_ID = 0x624ea400, 0x40000, 7
MODE_SHADOW = 0xa2a78000
MODE_OBJ = 0xa26ff994                      # the fourth bank object (prm_banks 0xa26ff940 + 3 * 28), as prm_banks_init makes it
TAIL, RESERVE, RESERVE_LEN, TAIL_END = 0x255b0, 0x3a000, 0x1000, 0x3fffc


def build_tag(version):
    """The word the firmware build `version` leaves at O_BUILD."""
    return zlib.crc32(str(version).encode())


def marker(counter):
    b = M_MAGIC + struct.pack('<II', counter, M_VERSION)
    return b + struct.pack('<I', zlib.crc32(b))


def marker_state(b):
    """16 bytes -> ('absent' | 'valid' | 'damaged' | 'foreign', counter or None)."""
    if b == bytes(M_LEN):
        return 'absent', None
    if b[:4] != M_MAGIC:
        return 'foreign', None
    c, v, crc = struct.unpack_from('<3I', b, 4)
    return ('valid', c) if v == M_VERSION and crc == zlib.crc32(b[:12]) else ('damaged', None)


def u32(b, o):
    return struct.unpack_from('<I', b, o)[0]


def decode(d, version=None):
    """-> (lines, verdict). verdict: 'go', 'stop' or 'bad file'."""
    if len(d) != FILE_LEN or d[:4] != FILE_MAGIC or u32(d, O_VERLEN) != FILE_VERSION | FILE_LEN << 16:
        return [f'Not an NVPROBE.BIN of this format ({len(d)} bytes).'], 'bad file'
    if u32(d, O_CRC) != zlib.crc32(d[:O_CRC]):
        return ['The file\'s own CRC is wrong: it was cut short or changed on the card.'], 'bad file'
    fl = u32(d, O_FLAGS)
    act = fl >> 24
    out, stop = [], []

    def cond(bit, ok_text, bad_text):
        good = bool(fl & bit)
        out.append(f"  {'pass' if good else 'STOP'}  {ok_text if good else bad_text}")
        if not good:
            stop.append(bad_text)

    tag = u32(d, O_BUILD)
    out.append(f'Firmware build tag {tag:#010x}' + ('' if version is None else f" ({'matches' if tag == build_tag(version) else 'does NOT match'} version {version})"))
    out.append('')
    out.append('What this power-on found (reads only):')
    cond(F_CPU0, 'the half-press ran on CPU 0', f'the half-press ran on CPU {u32(d, O_CPU) & 0xffff}, not CPU 0')
    cond(F_BANK, f'the settings bank is where the firmware map says (object {u32(d, O_BANK):#x}, RAM {u32(d, O_BRAM):#x}, size {u32(d, O_BSIZE):#x}, id {u32(d, O_BID) & 0xffff})',
         f'the settings bank object is not as mapped (pointer {u32(d, O_BANK):#x}, RAM {u32(d, O_BRAM):#x}, size {u32(d, O_BSIZE):#x}, id word {u32(d, O_BID):#x})')
    cond(F_ID, 'the settings image carries id 7', f'the settings image carries id {u32(d, O_RHDR) & 0xffff}, not 7')
    cond(F_GEN, f'generation {u32(d, O_RGEN)} in RAM and in the saved copy: no save was running',
         f'generation {u32(d, O_RGEN)} in RAM but {u32(d, O_SGEN)} in the saved copy: a save was running, or the camera changed its image without saving')
    cond(F_TAIL, 'the unused tail outside our 4 KB is all zero',
         f'{u32(d, O_TNZ)} non-zero words in the tail outside our 4 KB, the first at image offset {u32(d, O_TFIRST):#x}: something else uses it')
    cond(F_REST, 'our 4 KB is zero after its first 16 bytes', f'{u32(d, O_RNZ)} non-zero words in our 4 KB after its first 16 bytes')
    cond(F_CU, 'the cached and the uncached view of our 4 KB agree', f'{u32(d, O_CU)} words of our 4 KB differ between the cached and the uncached view')
    cond(F_CS, 'our 4 KB in RAM equals the copy the boot read from flash', f'{u32(d, O_CS)} words of our 4 KB differ from the copy the boot read from flash')
    sl = u32(d, O_SLOT)
    out.append(f'  note  settings flash slot {sl & 0xff}, EEROM slot {sl >> 8 & 0xff}' + ('; the camera REFUSED its settings image at this start and rebuilt it' if sl >> 16 else ''))
    out.append('')
    pre, shd = d[O_PRE:O_PRE + M_LEN], d[O_SHD:O_SHD + M_LEN]
    st, cnt = marker_state(pre)
    sst, scnt = marker_state(shd)
    flash = {'absent': 'no marker', 'valid': f'marker, counter {scnt}', 'damaged': 'a damaged marker', 'foreign': 'bytes that are not ours'}[sst]
    out.append('The marker at the start of this power-on:')
    out.append({'absent': '  none (16 zero bytes)', 'valid': f'  present, counter {cnt}, CRC right', 'damaged': f'  our magic, but version or CRC wrong: {pre.hex()}',
                'foreign': f'  bytes that are not ours: {pre.hex()}'}[st])
    out.append(f"  in the copy read from flash: {flash}" + (' (the same bytes: it came from flash, not from RAM that was kept)' if shd == pre and st == 'valid' else
                                                              '' if shd == pre else ' (DIFFERENT from RAM)'))
    if (st == 'absent') != bool(fl & F_ABSENT) or (st == 'valid') != bool(fl & F_VALID) or (st in ('valid', 'damaged')) != bool(fl & F_OURS):
        out.append('  STOP  the camera judged these 16 bytes differently from this tool')
        stop.append('marker judged differently')
    out.append('')
    out.append('What the layer did:' + (' (FORGET.BIN is on the card)' if fl & F_FORGET else ''))
    new = u32(d, O_NEW)
    post = (u32(d, O_POST0), u32(d, O_POST1), u32(d, O_UPOST1))
    rb = bool(fl & F_READBACK)
    if act == A_NONE:
        out.append('  nothing written: a condition above did not hold')
    elif act == A_WRITTEN:
        out.append(f"  marker written, counter {new}; read back {'right on both views' if rb else 'WRONG'}")
        if not rb or post != (u32(M_MAGIC, 0), new, new):
            stop.append('marker read back wrong')
    elif act == A_CLEARED:
        out.append(f"  marker cleared (FORGET.BIN); read back {'zero on both views' if rb else 'WRONG'}")
        if not rb or post != (0, 0, 0):
            stop.append('clear read back wrong')
    elif act == A_FORGET_EMPTY:
        out.append('  nothing to clear (FORGET.BIN, no marker)')
    elif act == A_SAVE:
        out.append(f'  put off: the camera began a save between the check and the lock (meant to write counter {new})')
    elif act == A_CHANGED:
        out.append('  put off: the 16 bytes changed between the check and the lock')
        stop.append('the reserve changed under us')
    elif act == A_FOREIGN:
        out.append('  nothing written: the 16 bytes are not ours')
        stop.append('foreign bytes in the reserve')
    elif act == A_DAMAGED:
        out.append('  nothing written: a damaged marker is left as found (FORGET.BIN clears it)')
        stop.append('damaged marker')
    else:
        out.append(f'  unknown action {act}')
        stop.append('unknown action')
    if act in (A_WRITTEN, A_CLEARED, A_SAVE, A_CHANGED) and not fl & F_LOCK or act in (A_WRITTEN, A_CLEARED) and fl & F_ALL != F_ALL:
        stop.append('action without its conditions')
    if act == A_NONE and fl & F_ALL == F_ALL:
        stop.append('nothing done although every condition held')
    out.append(f'  now in RAM: word 0 {post[0]:#010x}, counter {post[1]} (cached), {post[2]} (uncached)')
    out.append('')
    if stop:
        out.append('STOP: ' + '; '.join(dict.fromkeys(stop)) + '. Do not go on to the next step; send this file.')
    else:
        out.append('GO: every condition held' + {A_WRITTEN: f' and marker {new} is in RAM. It reaches flash when the camera is switched off or sleeps.',
                                                  A_CLEARED: ' and the marker is cleared in RAM. The zeros reach flash when the camera is switched off or sleeps.',
                                                  A_FORGET_EMPTY: '; nothing of ours is in the settings image.', A_SAVE: '; the write waits for the next power-on.'}.get(act, '.'))
    return out, 'stop' if stop else 'go'


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('file', type=Path)
    ap.add_argument('--version', help='the firmware version the file should come from, e.g. 0.34')
    a = ap.parse_args()
    lines, verdict = decode(a.file.read_bytes(), a.version)
    print('\n'.join(lines))
    sys.exit({'go': 0, 'stop': 1, 'bad file': 2}[verdict])


if __name__ == '__main__':
    main()
