// Vendored from androidfanman/caduceus-om3 @ 9fc2dc1 (Apache-2.0, see NOTICE), unchanged. Update by copying; our glue is in ./targets/om3.ts.
// Per-film R / G / B tone curves (Caduceus for OM-3, branch feature/rgb-curves, camera-tested test 4, 2026-11-15).
// Each channel has 5 points at 0 / 25 / 50 / 75 / 100 % of the camera's 12-bit gamma output, each an offset of
// -7..+7 steps of 48 (1.2 % of full scale). The camera bends its R, G and B gamma tables by a monotone cubic through
// the points (firmware cv_prm / cv_d in st_run, in the same pass as split toning); this is the same integer maths as
// research/rgbcurves/model.py, bit for bit. Not in LOOKS.BIN or the photo code yet: set on the camera's RGB row.
import type { Look } from './pack';

export type Channel = 'r' | 'g' | 'b';
export interface RgbCurves { r: number[]; g: number[]; b: number[] }   // 5 offsets each, -7..7
export const CURVE_POINTS = 5, CURVE_MAX = 7, CURVE_STEP = 48;
export const CHANNELS: Channel[] = ['r', 'g', 'b'];
const X = [0, 1024, 2048, 3072, 4096];
const H = [1024, 1024, 1024, 1024];
const INV = H.map((h) => Math.trunc((1 << 24) / h));

const tdiv = (a: number, b: number) => Math.trunc(a / b);   // the CPU's div: truncates toward zero
export const flatCurves = (): RgbCurves => ({ r: [0, 0, 0, 0, 0], g: [0, 0, 0, 0, 0], b: [0, 0, 0, 0, 0] });
export const curveIsFlat = (v: number[]) => v.every((x) => !x);
export const hasCurves = (l: Look) => !!l.rgb && CHANNELS.some((c) => !curveIsFlat(l.rgb![c]));

/** A channel's 5 offsets -> the firmware's block (Y[5], A[4], B[4]). */
function prm(v: number[]) {
  const Y = v.map((x) => Math.max(-CURVE_MAX, Math.min(CURVE_MAX, x)) * CURVE_STEP);
  const d = [0, 1, 2, 3].map((i) => tdiv((Y[i + 1] - Y[i]) * 4096, H[i]));
  const m = [d[0], 0, 0, 0, d[3]];
  for (let i = 1; i < 4; i++) {
    const a = d[i - 1], b = d[i];
    m[i] = a === 0 || b === 0 || (a < 0) !== (b < 0) ? 0 : tdiv(2 * a * b, a + b);
  }
  return { Y, A: [0, 1, 2, 3].map((i) => (H[i] * m[i]) >> 12), B: [0, 1, 2, 3].map((i) => (H[i] * m[i + 1]) >> 12) };
}

/** The curve's change D(t) at a 12-bit table value t (0..4095), as the camera. */
export function curveDelta(v: number[]): (t: number) => number {
  if (curveIsFlat(v)) return () => 0;
  const { Y, A, B } = prm(v);
  return (t: number) => {
    t = Math.max(0, Math.min(4095, Math.round(t)));
    const i = Math.min(3, t >> 10);
    const s = ((t - X[i]) * INV[i]) >> 12, s2 = (s * s) >> 12, s3 = (s2 * s) >> 12;
    const h00 = 2 * s3 - 3 * s2 + 4096, h10 = s3 - 2 * s2 + s, h01 = 3 * s2 - 2 * s3, h11 = s3 - s2;
    return Math.floor((h00 * Y[i] + h10 * A[i] + h01 * Y[i + 1] + h11 * B[i]) / 4096);   // asr 12
  };
}

/** A parsed `rgb` field, or undefined when missing, flat or malformed. */
export function parseCurves(v: unknown): RgbCurves | undefined {
  if (!v || typeof v !== 'object') return undefined;
  const o = v as Record<string, unknown>, out = flatCurves();
  for (const c of CHANNELS) {
    const a = o[c];
    if (a === undefined) continue;
    if (!Array.isArray(a) || a.length !== CURVE_POINTS || !a.every((x) => Number.isInteger(x) && Math.abs(x) <= CURVE_MAX)) return undefined;
    out[c] = a.slice();
  }
  return CHANNELS.some((c) => !curveIsFlat(out[c])) ? out : undefined;
}

// Colour mix per film (feature/rgb-curves, camera-tested test 6, 2026-11-15): for red, green and blue a hue and a
// strength, -7..+7 each, stored [hue R, strength R, hue G, strength G, hue B, strength B]. Hue moves the colour toward
// the next one (red -> yellow, green -> cyan, blue -> purple), strength makes it stronger. The camera puts a 3 x 3 of
// ours into its own colour matrix (before the gamma stage, so before the curves, split toning and the 12 colours):
// column j: M[next][j] = 8 (h - s) / 256, M[prev][j] = 8 (-h - s) / 256, each diagonal makes its row 1, so greys stay
// grey (firmware mx_go, research/colourmix/model.py). Not in LOOKS.BIN or the photo code yet: set on the camera's Mix row.
export const MIX_N = 6, MIX_MAX = 7, MIX_UNIT = 8;
export const flatMix = (): number[] => [0, 0, 0, 0, 0, 0];
export const mixIsFlat = (v?: number[]) => !v || v.every((x) => !x);
export const hasMix = (l: Look) => !mixIsFlat(l.mix);

/** The mix as the camera's 3 x 3 (rows: output R, G, B; 1.0 = no change). */
export function mixMatrix(v: number[]): number[][] {
  const m = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  for (let j = 0; j < 3; j++) {
    const hh = Math.max(-MIX_MAX, Math.min(MIX_MAX, v[2 * j] | 0)), s = Math.max(-MIX_MAX, Math.min(MIX_MAX, v[2 * j + 1] | 0));
    m[(j + 1) % 3][j] = MIX_UNIT * (hh - s);
    m[(j + 2) % 3][j] = MIX_UNIT * (-hh - s);
  }
  for (let i = 0; i < 3; i++) m[i][i] = 256 - m[i][(i + 1) % 3] - m[i][(i + 2) % 3];
  return m.map((r) => r.map((x) => x / 256));
}

/** A parsed `mix` field, or undefined when missing, flat or malformed. */
export function parseMix(v: unknown): number[] | undefined {
  if (!Array.isArray(v) || v.length !== MIX_N || !v.every((x) => Number.isInteger(x) && Math.abs(x) <= MIX_MAX)) return undefined;
  return mixIsFlat(v) ? undefined : v.slice();
}
