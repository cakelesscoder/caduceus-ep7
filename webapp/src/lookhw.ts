// v0.34 base curve and colour matrix (docs/LOOK_FORMAT_V4.md) for the preview. The preview works on rendered JPEGs, which
// already carry the camera's standard curve, so a look's curve is drawn as standard^-1 then the look's curve, per channel.
// Curves: 17 points (inputs 0, 16, .., 240, 255 of the 256-entry tables, output 0..1), our rounding of the E-P7 1.1 gamma
// tables 1, 3, 5, 7, 15, 51, 52 (RE_RESOURCES F.6); linear between points.
import type { Curve } from './pack';

const X = [...Array.from({ length: 16 }, (_, i) => i * 16 / 255), 1];
export const CURVE_PTS: Record<Curve, number[]> = {
  standard: [0, 0.274, 0.461, 0.583, 0.673, 0.743, 0.8, 0.846, 0.883, 0.912, 0.935, 0.953, 0.97, 0.984, 0.994, 1, 1],
  auto: [0, 0.287, 0.461, 0.584, 0.673, 0.743, 0.8, 0.846, 0.883, 0.911, 0.935, 0.953, 0.97, 0.984, 0.994, 1, 1],
  pale: [0, 0.292, 0.432, 0.537, 0.627, 0.701, 0.767, 0.827, 0.877, 0.916, 0.945, 0.966, 0.981, 0.992, 0.998, 1, 1],
  light: [0, 0.369, 0.525, 0.633, 0.718, 0.782, 0.834, 0.879, 0.914, 0.94, 0.959, 0.973, 0.984, 0.992, 0.998, 1, 1],
  pop: [0, 0.154, 0.301, 0.422, 0.525, 0.614, 0.691, 0.758, 0.814, 0.859, 0.895, 0.925, 0.952, 0.975, 0.993, 1, 1],
  flat: [0, 0.461, 0.599, 0.68, 0.737, 0.781, 0.819, 0.849, 0.876, 0.902, 0.926, 0.949, 0.969, 0.985, 0.994, 1, 1],
  log: [0, 0.51, 0.634, 0.708, 0.76, 0.801, 0.834, 0.863, 0.888, 0.908, 0.927, 0.944, 0.961, 0.979, 0.992, 1, 1],
};

function lerp(xs: number[], ys: number[], x: number): number {
  if (x <= xs[0]) return ys[0];
  for (let i = 1; i < xs.length; i++) if (x <= xs[i]) {
    const t = xs[i] === xs[i - 1] ? 0 : (x - xs[i - 1]) / (xs[i] - xs[i - 1]);
    return ys[i - 1] + t * (ys[i] - ys[i - 1]);
  }
  return ys[ys.length - 1];
}

/** 1025-entry LUT on display values 0..1: the standard curve undone, then `c`. */
export function curveLut(c: Curve): Float32Array {
  const std = CURVE_PTS.standard, pts = CURVE_PTS[c], out = new Float32Array(1025);
  for (let i = 0; i <= 1024; i++) out[i] = lerp(X, pts, lerp(std, X, i / 1024));
  return out;
}

/** The look matrix L (rows R G B out) from the shared field [m01, m02, m10, m12, m20, m21] in 1/128. */
export function lookMatrix(m: number[]): number[][] {
  const [a, b, c, d, e, f] = m.map((v) => v / 128);
  return [[1 - a - b, a, b], [c, 1 - c - d, d], [e, f, 1 - e - f]];
}
