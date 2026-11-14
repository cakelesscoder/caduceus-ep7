#!/usr/bin/env python3
"""grain g2 (v0.32b), kept as the record; model.py is g3's.

grain g2: the host model of the pass, integer for integer (patches/grain_g2/g2.s.in). docs/GRAIN_PORT.md "g2". Offline.

  .venv/bin/python -I patches/grain_g2/model.py --stats                      # the statistics table, r2 against g2
  .venv/bin/python -I patches/grain_g2/model.py --preview generated/grain_g2/preview.png

The pass is r2's (patches/grain_cpu, model verify_s1.py expected()): Y' = T[Y][n], T as gc_tbl builds it for strengths
23 / 55 / 91, centre 991. Only the source of n changes:
  tile    128 x 128 u8, built once from TILE_SEED the way r2 fills its ring: b = low + high nibble of a random byte
          (xorshift32, four bytes a step, low byte first, row-major), h(x, y) = (b(x, y) + b(x-1, y) + 1) >> 1,
          tile(x, y) = (h(x, y) + h(x, y-1) + 1) >> 1, both wrapping. Values 0..30.
  blocks  64 x 64 px. For every block row, each block in turn draws tx, then ty, = ((r >> 8) & 0xffff) * 65 >> 16
          (0..64) from the photo's xorshift32 r. r starts as record +44 (0 -> 0x12345678) and goes back there.
  pixel   n = tile[ty[b] + (y & 63)][tx[b] + (x & 63)], b = x >> 6, x and y counted in the active image.
So n depends only on (x, y) and the photo's seed: rows per lock and rows split at a slice edge can't change a pixel.
"""
import argparse
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
C = 991                                     # centre, r2
S = {1: 23, 2: 55, 3: 91}                   # Low / Med / High, r2
SEED0 = 0x12345678                          # the photo generator when record +44 is 0, r2
TILE_SEED = 4880                            # of the xorshift seeds 1..120000, the tile whose statistics in a photo (moments
#                                             at the three levels, lags to 3, the loss at block edges counted) are nearest r2's
TW, BL, NOFF = 128, 64, 65


def xs(r):
    r ^= (r << 13) & 0xffffffff; r ^= r >> 17; r ^= (r << 5) & 0xffffffff
    return r


def weights():
    """gc_G, as patches/grain_cpu/build.py weights()."""
    ss = lambda t: (lambda t: t * t * (3 - 2 * t))(min(max(t, 0.0), 1.0))
    return [round(255 * (0.08 + 0.92 * ss((y - 25) / 75)) * (1 - 0.25 * ss((y - 200) / 55))) for y in range(256)]


def table(level):
    """T[Y][n] for one level, 256 x 32 u8: the bytes gc_tbl builds, index (Y << 5) | n."""
    g = np.array(weights(), dtype=np.int64)[:, None]
    y = np.arange(256)[:, None]; n = np.arange(32)[None, :]
    return np.clip(y + (((64 * n - C) * g * S[level] + 131072) >> 18), 0, 255).astype(np.uint8)


def tile(seed=None):
    r, b = TILE_SEED if seed is None else seed, []
    for _ in range(TW * TW // 4):
        r = xs(r); x = r
        for _ in range(4):
            b.append((x & 15) + ((x >> 4) & 15)); x >>= 8
    b = np.array(b, dtype=np.int64).reshape(TW, TW)
    h = (b + np.roll(b, 1, axis=1) + 1) >> 1
    return ((h + np.roll(h, 1, axis=0) + 1) >> 1).astype(np.uint8)


def draw(r):
    r = xs(r)
    return r, (((r >> 8) & 0xffff) * NOFF) >> 16


def noise(w, h, seed=SEED0, t=None):
    """-> (n[h][w] u8, the generator after the photo)."""
    t = tile() if t is None else t
    out = np.empty((h, w), dtype=np.uint8)
    r = seed or SEED0
    for y0 in range(0, h, BL):
        hh = min(BL, h - y0)
        for x0 in range(0, w, BL):
            r, tx = draw(r); r, ty = draw(r)
            ww = min(BL, w - x0)
            out[y0:y0 + hh, x0:x0 + ww] = t[ty:ty + hh, tx:tx + ww]
    return out, r


def expected(pic, w, h, stride, level, seed=SEED0):
    """The buffer after the pass (format 0x0302: 2 B/px, Y in the even bytes) -> (bytes, generator)."""
    n, r = noise(w, h, seed)
    a = np.frombuffer(pic, dtype=np.uint8).copy().reshape(h, stride * 2)
    a[:, 0:2 * w:2] = table(level)[a[:, 0:2 * w:2], n]
    return a.tobytes(), r


def r2_noise(w, h, seed=SEED0):
    """r2's n, the integers of patches/grain_cpu/verify_s1.py expected() (verify.py checks they agree)."""
    ring = np.zeros(16384, dtype=np.int64); prev, r, i = 15, seed or SEED0, 0
    for _ in range(4096):
        r = xs(r); x = r
        for _ in range(4):
            v = (x & 15) + ((x >> 4) & 15)
            ring[i] = (v + prev + 1) >> 1; prev = v; i += 1; x >>= 8
    span = 16383 - w
    out = np.empty((h, w), dtype=np.uint8)
    r = xs(r); po = (((r >> 8) & 0xffff) * span) >> 16
    for y in range(h):
        r = xs(r); o = (((r >> 8) & 0xffff) * span) >> 16
        out[y] = (ring[o:o + w] + ring[po:po + w] + 1) >> 1
        po = o
    return out, r


def stats(o):
    """Grain statistics of a flat-field result o[h][w] (float): mean, std, lag correlations, 64 x 64 block means."""
    o = o.astype(np.float64); m = o.mean(); d = o - m; v = (d * d).mean()
    c = lambda dy, dx: float((d[:d.shape[0] - dy, :d.shape[1] - dx] * d[dy:, dx:]).mean() / v)
    hh, ww = o.shape[0] // BL * BL, o.shape[1] // BL * BL
    bm = o[:hh, :ww].reshape(hh // BL, BL, ww // BL, BL).mean(axis=(1, 3))
    return dict(mean=float(m), std=float(np.sqrt(v)), right=c(0, 1), down=c(1, 0), down2=c(2, 0), diag=c(1, 1),
                far=max(abs(c(dy, dx)) for dy, dx in ((0, 2), (0, 3), (2, 1), (1, 2), (2, 2), (3, 0), (0, 64), (64, 0), (0, 63), (0, 65))),
                block=float(bm.std()))


def population(level, y=128):
    """r2's exact mean shift and std at one Y: n = average of two ring bytes, a ring byte = average of two nibble sums."""
    pb = np.bincount(np.add.outer(np.arange(16), np.arange(16)).ravel(), minlength=31) / 256
    avg = lambda p: np.bincount(((np.add.outer(np.arange(31), np.arange(31)) + 1) >> 1).ravel(), weights=np.outer(p, p).ravel(), minlength=31)
    pn = avg(avg(pb))
    t = table(level)[y, :31].astype(np.float64) - y
    m = float((pn * t).sum())
    return m, float(np.sqrt((pn * t * t).sum() - m * m))


def stats_table(w=5184, h=3888, y=128, seeds=(1, 2, 3, 0xdeadbeef, 0x0badf00d, 0x2026, 77, 0xcafe)):
    """-> [(level name, r2 population (mean, std), r2 at SEED0, r2's range over other photos (mean lo, hi, std lo, hi), g2 at SEED0)]."""
    n2, _ = r2_noise(w, h); ng, _ = noise(w, h)
    more = [r2_noise(w, h // 6, s)[0] for s in seeds]
    rows = []
    for lv, name in ((1, 'Low'), (2, 'Med'), (3, 'High')):
        t = table(lv)[y].astype(np.float64) - y
        ms = [(float(t[n].mean()), float(t[n].std())) for n in more]
        rows.append((name, population(lv, y), stats(t[n2]), (min(a for a, _ in ms), max(a for a, _ in ms), min(b for _, b in ms), max(b for _, b in ms)), stats(t[ng])))
    return rows


def preview(out, photo, crop=(2400, 600, 256, 256), level=3, zoom=2):
    """r2 model | g2 model on a crop of a camera JPEG (its luma; the camera adds the grain before the JPEG encoder)."""
    from PIL import Image, ImageDraw
    im = Image.open(photo).convert('YCbCr')
    yy, cb, cr = (np.array(c) for c in im.split())
    h, w = yy.shape
    t = table(level)
    x0, y0, cw, ch = crop
    tiles = []
    for name, n in (('r2', r2_noise(w, h)[0]), ('g2', noise(w, h)[0])):
        g = t[yy, n]
        c = Image.merge('YCbCr', [Image.fromarray(a[y0:y0 + ch, x0:x0 + cw]) for a in (g, cb, cr)]).convert('RGB')
        tiles.append((name, c.resize((cw * zoom, ch * zoom), Image.NEAREST)))
    gap, top = 8, 18
    sheet = Image.new('RGB', (2 * cw * zoom + gap, ch * zoom + top), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    for i, (name, c) in enumerate(tiles):
        sheet.paste(c, (i * (cw * zoom + gap), top))
        d.text((i * (cw * zoom + gap) + 4, 3), f'{name} model, Grain {("Low", "Med", "High")[level - 1]}, {zoom}x', fill=(230, 230, 230))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return sheet.size


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--stats', action='store_true')
    ap.add_argument('--preview', type=Path)
    ap.add_argument('--photo', type=Path, default=ROOT / 'testdata/camera_grain_s3/PB071876.JPG')
    a = ap.parse_args()
    if a.stats:
        print('flat Y 128, 5184 x 3888 | mean shift | std | corr right / down / 2 down / diagonal | other lags, max | std of 64 x 64 block means')
        for name, pop, r2, rng, g2 in stats_table():
            print(f"{name:4} r2, exact | {pop[0]:+.3f} | {pop[1]:.3f} |")
            print(f"{name:4} r2, 8 more seeds | {rng[0]:+.3f} .. {rng[1]:+.3f} | {rng[2]:.3f} .. {rng[3]:.3f} |")
            for tag, s in (('r2', r2), ('g2', g2)):
                print(f"{name:4} {tag} | {s['mean']:+.3f} | {s['std']:.3f} | {s['right']:.4f} / {s['down']:.4f} / {s['down2']:+.4f} / {s['diag']:.4f} | {s['far']:.4f} | {s['block']:.3f}")
    if a.preview:
        print(a.preview, preview(a.preview, a.photo))
