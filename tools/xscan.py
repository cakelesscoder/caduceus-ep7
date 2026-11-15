"""Fast, cached reference scans of a main image, shared by the patch layers' build-time safety checks.

The layers prove that nothing lands inside a hook site or a claimed range: an abs32 word at any byte offset (on any
alias), or a d16 / d32 call / calls / jmp whose target falls in the range. The old per-layer scans rebuilt full-length
int64 arrays of every byte for every call (a full chain build spent ~70 % of 14 minutes there). This module computes,
once per distinct image, the abs32 word at every offset (uint32) and, per branch encoding, only the positions where the
opcode occurs plus their targets. Results are identical to the old scans: same positions, same order before the
callers' own filtering. Our own code (Caduceus repo, Apache-2.0).

  abs32_hits(im, base, lo, hi)              -> sorted np.int64 file offsets i with lo <= u32(im, i) < hi (unsigned)
  rel_hits(im, base, lo, hi, encodings)     -> sorted np.int64 file offsets x of a branch whose target is in [lo, hi)
encodings: tuples (opcode bytes, displacement offset, displacement size), e.g. ((0xdd,), 1, 4). A branch's target is
its own address (base + x) plus the signed displacement, as in the stock scans. Positions x run over
range(len(im) - 8) and i over range(len(im) - 3), as before.
"""
import hashlib

import numpy as np

STD = (((0xdd,), 1, 4), ((0xdc,), 1, 4), ((0xcd,), 1, 2), ((0xcc,), 1, 2), ((0xfa, 0xff), 2, 2), ((0xfc, 0xff), 2, 4))

_cache = {}


def _entry(im):
    key = (len(im), hashlib.blake2b(bytes(im), digest_size=16).digest())
    e = _cache.get(key)
    if e is None:
        if len(_cache) > 6:                               # a build touches a handful of image states; keep memory bounded
            _cache.clear()
        d = np.frombuffer(bytes(im), np.uint8)
        e = {'d': d, 'w': None, 'rel': {}}
        _cache[key] = e
    return e


def _words(e):
    if e['w'] is None:
        d = e['d'].astype(np.uint32)
        e['w'] = d[:-3] | (d[1:-2] << 8) | (d[2:-1] << 16) | (d[3:] << 24)
    return e['w']


def abs32_hits(im, base, lo, hi):
    """Offsets i (0 <= i < len-3) whose little-endian u32 is in [lo, hi), compared as unsigned 32-bit."""
    w = _words(_entry(im))
    lo &= 0xffffffff
    hi &= 0xffffffff
    return np.nonzero((w >= np.uint32(lo)) & (w < np.uint32(hi)))[0].astype(np.int64)


def _rel_table(e, base, enc):
    k = (base, enc)
    t = e['rel'].get(k)
    if t is None:
        op, at_, n = enc
        d = e['d']
        N = len(d) - 8
        m = d[:N] == op[0]
        if len(op) == 2:
            m &= d[1:N + 1] == op[1]
        x = np.nonzero(m)[0].astype(np.int64)
        dd = d.astype(np.int64)
        disp = dd[x + at_] | (dd[x + at_ + 1] << 8)
        if n == 4:
            disp |= (dd[x + at_ + 2] << 16) | (dd[x + at_ + 3] << 24)
        disp = np.where(disp >= (1 << (8 * n - 1)), disp - (1 << (8 * n)), disp)
        t = (x, x + base + disp)
        e['rel'][k] = t
    return t


def rel_hits(im, base, lo, hi, encodings=STD):
    """Per encoding, offsets x whose branch target (base + x + disp) is in [lo, hi); concatenated in encoding order."""
    e = _entry(im)
    out = []
    for enc in encodings:
        x, tgt = _rel_table(e, base, (tuple(enc[0]), enc[1], enc[2]))
        out.append(x[(tgt >= lo) & (tgt < hi)])
    return out
