#!/usr/bin/env python3
"""Decode the Live ND 0.31n1 readout, EP7MOD/LNDLOG.BIN (patches/live_nd/lnd_log.s.in, docs/LIVE_ND.md).

  python3 -I tools/lnd_log.py LNDLOG.BIN

One line per record, oldest first. Fields (u16 pairs are lo | hi << 16 in the camera's words):
  +156 = continueMaxShootCount (the burst limit), +158 = its countdown, +160 = continue requests sent,
  +162 = continuous frames counted, flags = sequence +464, key = key state word 0x61facd8c (4 = full press).
  Q lines are the continue requests the ME parts received, in order.
"""
import struct
import sys

RN = 32


def main(path):
    b = open(path, 'rb').read()
    if len(b) < 16 + 24 * RN or b[:4] != b'LNDL':
        sys.exit(f'{path}: not an LNDL block ({len(b)} B)')
    nxt, unwritten, total, press, req = struct.unpack_from('<BBHBxH', b, 4)
    print(f'records {total}, presses {press}, requests since the last press {req}')
    n = min(total, RN)
    first = nxt if total >= RN else 0
    for k in range(n):
        w = struct.unpack_from('<6I', b, 16 + 24 * ((first + k) % RN))
        t, pr, no = chr(w[0] >> 24), (w[0] >> 16) & 0xff, w[0] & 0xffff
        lim, cd = w[1] & 0xffff, w[1] >> 16
        sent, cnt = w[2] & 0xffff, w[2] >> 16
        head = f'#{no:<4} press {pr:<3} {t}  +156 {lim:<5} +158 {cd:<5} +160 {sent:<5} +162 {cnt:<5} flags {w[3]:08x} key {w[4]}'
        x = w[5]
        if t == 'C':
            stock, nd = x & 0xffff, x >> 16
            tail = f'| capacity {stock}, N {nd} -> limit {nd if nd and stock else stock}'
        elif t in 'QF':
            cnt_, reg, rel, busy = x & 0xff, (x >> 8) & 0xff, (x >> 16) & 0xff, x >> 24
            rel_s = 'not run' if rel == 0xee else ('OK' if rel == 1 else f'{rel}')
            tail = (f'| registered {reg}, busy {busy}' if t == 'Q' else
                    f'| frames done {cnt_}, registered {reg}, release check {rel_s}, busy {busy}')
        else:
            tail = f'| {x:08x}'
        print(head, tail)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
