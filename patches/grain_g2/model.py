#!/usr/bin/env python3
"""grain g3: the host model of the pass, integer for integer (patches/grain_g2/g3.s.in). docs/GRAIN_PORT.md "g3". Offline.

  .venv/bin/python -I patches/grain_g2/model.py --stats                      # the statistics table: r2, g2, g3
  .venv/bin/python -I patches/grain_g2/model.py --preview generated/grain_g3/preview.png

g3 is r2's noise (patches/grain_cpu, model verify_s1.py expected()) with the ring in ROM:
  ring    16384 B, r2's own fill from RING_SEED: v = low + high nibble of a random byte (xorshift32, four bytes a step, low byte
          first), ring[x] = (v[x] + v[x-1] + 1) >> 1, v[-1] = 15. r2 fills it per photo from the photo's generator; g3 never does.
  rows    r = record +44 (0 -> 0x12345678). One step gives the offset before row 0, then one step a row:
          o = ((r >> 8) & 0xffff) * (16383 - Hw) >> 16. The end state goes back to +44. These are gc_next's steps.
  pixel   s = ring[o + x] + ring[o_prev + x] (0..60), Y' = T2[Y][s] with T2[Y][s] = T[Y][(s + 1) >> 1], T as gc_tbl builds it
          for 23 / 55 / 91, centre 991. So Y' = r2's T[Y][(ring[o + x] + ring[o_prev + x] + 1) >> 1].
The fill used to take 4096 generator steps before the first offset. So g3 started at F = fill_end(RING_SEED) is r2 started at
RING_SEED, pixel for pixel and with the same end state (verify R runs both in the emulator).
g2 (v0.32b: a 128 x 128 tile read in 64 x 64 blocks) is in model_g2.py; it is here only for the statistics and the preview.
"""
import argparse, importlib.util
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
C = 991                                     # centre, r2
S = {1: 23, 2: 55, 3: 91}                   # Low / Med / High, r2
SEED0 = 0x12345678                          # the photo generator when record +44 is 0, r2
RING_SEED = 3201                            # of the seeds 1..60000, a ring whose moments at the three levels are within 0.3 % of
#                                             r2's exact ones and whose lag-1 correlation is the exact one, for 5184-px rows (which use
#                                             the middle of the ring more than its ends), 3888-px rows and narrow ones
RING = 16384


def xs(r):
    r ^= (r << 13) & 0xffffffff; r ^= r >> 17; r ^= (r << 5) & 0xffffffff
    return r


def weights():
    """gc_G, as patches/grain_cpu/build.py weights()."""
    ss = lambda t: (lambda t: t * t * (3 - 2 * t))(min(max(t, 0.0), 1.0))
    return [round(255 * (0.08 + 0.92 * ss((y - 25) / 75)) * (1 - 0.25 * ss((y - 200) / 55))) for y in range(256)]


def table(level):
    """r2's T[Y][n] for one level, 256 x 32 u8: the bytes gc_tbl builds, index (Y << 5) | n."""
    g = np.array(weights(), dtype=np.int64)[:, None]
    y = np.arange(256)[:, None]; n = np.arange(32)[None, :]
    return np.clip(y + (((64 * n - C) * g * S[level] + 131072) >> 18), 0, 255).astype(np.uint8)


def table2(level):
    """g3's T2[Y][s], 256 x 64 u8, index (Y << 6) | s: T[Y][(s + 1) >> 1]. s never passes 60; 61..63 repeat n = 31."""
    return table(level)[:, np.minimum((np.arange(64) + 1) >> 1, 31)]


def fill(seed):
    """r2's gc_fill -> (ring[16384], the generator after it)."""
    ring = np.zeros(RING, dtype=np.int64); prev, r, i = 15, seed, 0
    for _ in range(RING // 4):
        r = xs(r); x = r
        for _ in range(4):
            v = (x & 15) + ((x >> 4) & 15)
            ring[i] = (v + prev + 1) >> 1; prev = v; i += 1; x >>= 8
    return ring, r


_ROM = []


def ring():
    if not _ROM:
        _ROM.append(fill(RING_SEED)[0])
    return _ROM[0]


def fill_end():
    """F: r2's generator after it filled the ring from RING_SEED."""
    return fill(RING_SEED)[1]


def rows(rg, w, h, r):
    """gc_next's offsets over a ring -> (s[h][w] = ring[o + x] + ring[o_prev + x], the generator after the photo)."""
    span = RING - 1 - w
    out = np.empty((h, w), dtype=np.uint8)
    r = xs(r); po = (((r >> 8) & 0xffff) * span) >> 16
    for y in range(h):
        r = xs(r); o = (((r >> 8) & 0xffff) * span) >> 16
        out[y] = rg[o:o + w] + rg[po:po + w]
        po = o
    return out, r


def sums(w, h, seed=SEED0):
    return rows(ring(), w, h, seed or SEED0)


def noise(w, h, seed=SEED0):
    s, r = sums(w, h, seed)
    return (s + 1) >> 1, r


def expected(pic, w, h, stride, level, seed=SEED0):
    """The buffer after the pass (format 0x0302: 2 B/px, Y in the even bytes; odd bytes and the row padding stay) -> (bytes, generator)."""
    s, r = sums(w, h, seed)
    a = np.frombuffer(pic, dtype=np.uint8).copy().reshape(h, stride * 2)
    a[:, 0:2 * w:2] = table2(level)[a[:, 0:2 * w:2], s]
    return a.tobytes(), r


def r2_noise(w, h, seed=SEED0):
    """r2's n: its ring filled from the photo's generator, then the rows (the integers of verify_s1.py expected())."""
    rg, r = fill(seed or SEED0)
    s, r = rows(rg, w, h, r)
    return (s + 1) >> 1, r


def g2_noise(w, h, seed=SEED0):
    s = importlib.util.spec_from_file_location('grain_g2_model_g2', HERE / 'model_g2.py')
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m.noise(w, h, seed)


# ---------------------------------------------------------------- statistics
def seam(o):
    """Mean step |a - b| between neighbours that lie across a 64-px grid line, over the mean step elsewhere: (along x, along y)."""
    o = o.astype(np.float64)
    dx = np.abs(np.diff(o, axis=1)).mean(axis=0); dy = np.abs(np.diff(o, axis=0)).mean(axis=1)
    ex = np.arange(dx.size) % 64 == 63; ey = np.arange(dy.size) % 64 == 63
    return float(dx[ex].mean() / dx[~ex].mean()), float(dy[ey].mean() / dy[~ey].mean())


def copies(o, shift=6, level=0.75, step=1):
    """Share of neighbouring 64 x 64 blocks (left / right and up / down, on the 64-px grid) where one is nearly a copy of the other:
    the normalised cross-correlation, over shifts up to `shift` px each way, reaches `level`. -> (share, the largest peak)."""
    o = o.astype(np.float64)
    hh, ww = o.shape[0] // 64, o.shape[1] // 64
    b = o[:hh * 64, :ww * 64].reshape(hh, 64, ww, 64).transpose(0, 2, 1, 3)
    b = b - b.mean(axis=(2, 3), keepdims=True)
    f = np.fft.rfft2(b, s=(128, 128))
    e = np.sqrt((b * b).sum(axis=(2, 3)))
    peaks = []
    for a, c, ea, ec in ((f[:, :-1], f[:, 1:], e[:, :-1], e[:, 1:]), (f[:-1], f[1:], e[:-1], e[1:])):
        x = np.fft.irfft2(a[::step, ::step] * np.conj(c[::step, ::step]), s=(128, 128))
        x = np.concatenate([x[..., -shift:, :], x[..., :shift + 1, :]], axis=-2)
        x = np.concatenate([x[..., -shift:], x[..., :shift + 1]], axis=-1)
        peaks.append((x.max(axis=(-2, -1)) / (ea[::step, ::step] * ec[::step, ::step])).ravel())
    p = np.concatenate(peaks)
    return float((p >= level).mean()), float(p.max())


def stats(o, full=True):
    """Grain statistics of a flat-field result o[h][w]."""
    o = o.astype(np.float64); m = o.mean(); d = o - m; v = (d * d).mean()
    c = lambda dy, dx: float((d[:d.shape[0] - dy, :d.shape[1] - dx] * d[dy:, dx:]).mean() / v)
    out = dict(mean=float(m), std=float(np.sqrt(v)), right=c(0, 1), down=c(1, 0), down2=c(2, 0), diag=c(1, 1))
    if full:
        out['seam'] = seam(o); out['copies'] = copies(o)
    return out


def population(level, y=128):
    """r2's exact mean shift and std at one Y: n = average of two ring bytes, a ring byte = average of two nibble sums."""
    pb = np.bincount(np.add.outer(np.arange(16), np.arange(16)).ravel(), minlength=31) / 256
    avg = lambda p: np.bincount(((np.add.outer(np.arange(31), np.arange(31)) + 1) >> 1).ravel(), weights=np.outer(p, p).ravel(), minlength=31)
    pn = avg(avg(pb))
    t = table(level)[y, :31].astype(np.float64) - y
    m = float((pn * t).sum())
    return m, float(np.sqrt((pn * t * t).sum() - m * m))


SEEDS = (1, 2, 3, 0xdeadbeef, 0x0badf00d, 0x2026, 77, 0xcafe)


def stats_table(w=5184, h=3888, y=128):
    """-> [(level name, r2 exact (mean, std), {'r2': stats, 'g2': stats, 'g3': stats}, r2 over SEEDS and g3 over SEEDS: lists of stats)]."""
    fields = dict(r2=r2_noise(w, h)[0], g2=g2_noise(w, h)[0], g3=noise(w, h)[0])
    more = dict(r2=[r2_noise(w, h // 6, s)[0] for s in SEEDS], g3=[noise(w, h // 6, s)[0] for s in SEEDS])
    out = []
    for lv, name in ((1, 'Low'), (2, 'Med'), (3, 'High')):
        t = table(lv)[y].astype(np.float64) - y
        out.append((name, population(lv, y), {k: stats(t[n], lv == 3) for k, n in fields.items()}, {k: [stats(t[n], False) for n in v] for k, v in more.items()}))
    return out


def stats_lines(tab=None):
    out = ['flat Y 128, 5184 x 3888 | mean shift | std | corr right / down / 2 down / diagonal | step across 64-px lines, x / y | near-copy blocks (largest peak)']
    rng = lambda v, k: f"{min(s[k] for s in v):+.3f} .. {max(s[k] for s in v):+.3f}"
    for name, pop, one, more in tab or stats_table():
        out.append(f'{name:4} r2, exact | {pop[0]:+.3f} | {pop[1]:.3f} |')
        for tag in ('r2', 'g3'):
            v = more[tag]
            out.append(f"{name:4} {tag}, 8 more seeds | {rng(v, 'mean')} | {rng(v, 'std')[1:].replace('+', '')} | {rng(v, 'right')[1:].replace('+', '')} / {rng(v, 'down')[1:].replace('+', '')}")
        for tag in ('r2', 'g2', 'g3'):
            s = one[tag]
            out.append(f"{name:4} {tag} | {s['mean']:+.3f} | {s['std']:.3f} | {s['right']:.4f} / {s['down']:.4f} / {s['down2']:+.4f} / {s['diag']:.4f}"
                       + (f" | {s['seam'][0]:.2f} / {s['seam'][1]:.2f} | {100 * s['copies'][0]:.1f} % ({s['copies'][1]:.2f})" if 'seam' in s else ''))
    return out


# ---------------------------------------------------------------- the owner's preview
def preview(out, level=3, y=128, size=(448, 336)):
    """Flat grey with Grain High: r2 | g2 | g3. Top row at 100 %. Bottom row at quarter size (4 x 4 averages) with contrast x 4."""
    from PIL import Image, ImageDraw
    w, h = size
    t = table(level)[y].astype(np.float64)
    gap, top = 8, 18
    sheet = Image.new('L', (3 * w + 2 * gap, 2 * (h + top) + gap), 24)
    d = ImageDraw.Draw(sheet)
    for i, (name, fn) in enumerate((('r2 (v0.27 .. v0.32a)', r2_noise), ('g2 (v0.32b)', g2_noise), ('g3', noise))):
        f = t[fn(4 * w, 4 * h)[0]]
        full = np.clip(f[:h, :w], 0, 255)
        q = f.reshape(h, 4, w, 4).mean(axis=(1, 3))
        q = np.clip(y + 4 * (q - q.mean()), 0, 255)
        x0 = i * (w + gap)
        for j, (img, label) in enumerate(((full, '100 %'), (q, 'quarter size, contrast x 4'))):
            y0 = j * (h + top + gap)
            sheet.paste(Image.fromarray(img.astype(np.uint8)), (x0, y0 + top))
            d.text((x0 + 4, y0 + 3), f'{name}, Grain High, flat grey, {label}', fill=230)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return sheet.size


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--stats', action='store_true')
    ap.add_argument('--preview', type=Path)
    a = ap.parse_args()
    if a.stats:
        print('\n'.join(stats_lines()))
    if a.preview:
        print(a.preview, preview(a.preview))
