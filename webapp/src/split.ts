// Vendored from androidfanman/caduceus-om3 @ 9fc2dc1 (Apache-2.0, see NOTICE), unchanged. Update by copying; our glue is in ./targets/om3.ts.
// Split toning (Caduceus for OM-3 v0.26): a Shadows and a Highlights tint, each one of the camera wheel's 12 colours
// with a strength. The camera bends its R, G and B gamma curves (firmware st_run, research/splittone/model.py); this
// module holds the same numbers for the preview and the editor.
// v0.28: the wheels run 0..10 in half the v0.26 step and only add a colour; a Tone Balance (-5..+5) moves the point
// where the shadow tint hands over to the highlight tint. In a look, `sh` / `hl` stay in v0.26 steps, now in halves
// (0, 0.5 .. 5): the camera's 0..10 is twice that, so a v0.26 look keeps its strength. v0.26's minus (the opposite
// colour) is read as the opposite colour of the wheel with a plus.
import type { Look } from './pack';
import { CHANNELS, curveDelta, type RgbCurves } from './curves';

export interface Split { sh_color: number; sh: number; hl_color: number; hl: number }
/** The wheel's colours, clockwise from 12 o'clock, as on the camera (and their swatch colours for the editor). */
export const SPLIT_COLOURS: [string, string][] = [
  ['Yellow', '#f2d600'], ['Orange', '#f59a00'], ['Orange-red', '#f05a00'], ['Red', '#e0102a'], ['Magenta', '#d4157a'], ['Violet', '#7a33cc'],
  ['Blue', '#1f5fe0'], ['Blue-cyan', '#1d96e0'], ['Cyan', '#16c0d0'], ['Green-cyan', '#18b583'], ['Green', '#2fae3a'], ['Yellow-green', '#9cc414'],
];
/** K per strength step (R, G, B) for each colour: the firmware's st_k table (4.8 Cb/Cr units at the weight peak per step). */
export const SPLIT_K: [number, number, number][] = [
  [7, 7, -57], [26, -4, -47], [37, -12, -33], [43, -18, -18], [39, -26, 29], [17, -19, 53],
  [-11, -5, 56], [-33, 9, 39], [-43, 18, 18], [-45, 24, -5], [-36, 25, -36], [-13, 17, -55],
];
export const SPLIT_MAX = 5;
/** v0.28: the camera's 0..10 (half steps) <-> a look's 0..5. */
export const SPLIT_STEPS = 10;
export const toSteps = (v: number) => Math.round(2 * v);
export const fromSteps = (n: number) => Math.max(0, Math.min(SPLIT_STEPS, Math.round(n))) / 2;
/** v0.28 LOOKS.BIN strength code (record +54 / +56, -5..5): even steps n -> n / 2, odd -> -(n + 1) / 2; and back. */
export const splitCode = (v: number) => { const n = toSteps(v); return n % 2 ? -(n + 1) / 2 : n / 2; };
export const splitFromCode = (c: number) => (c >= 0 ? 2 * c : -2 * c - 1) / 2;
/** Tone Balance: -5 (the shadow colour reaches further) .. +5 (the highlight colour). */
export const BALANCE_MAX = 5;
export const hasSplit = (l: Look) => !!l.split && (l.split.sh !== 0 || l.split.hl !== 0);
const ok = (c: number, s: number) => Number.isInteger(c) && c >= 0 && c < 12 && Number.isInteger(2 * s) && s >= 0 && s <= SPLIT_MAX;
export const splitOk = (s: Split) => ok(s.sh_color, s.sh) && ok(s.hl_color, s.hl);
/** A parsed `split` field, or undefined when it is missing, off or malformed. A v0.26 minus (the opposite colour)
 *  becomes the opposite colour of the wheel (6 colours on) with a plus. */
export function parseSplit(v: unknown): Split | undefined {
  if (!v || typeof v !== 'object') return undefined;
  const o = v as Record<string, unknown>, n = (x: unknown) => (typeof x === 'number' ? x : NaN);
  const s = { sh_color: n(o.sh_color), sh: n(o.sh), hl_color: n(o.hl_color), hl: n(o.hl) };
  if (s.sh < 0) { s.sh_color = (s.sh_color + 6) % 12; s.sh = -s.sh; }
  if (s.hl < 0) { s.hl_color = (s.hl_color + 6) % 12; s.hl = -s.hl; }
  return splitOk(s) && (s.sh || s.hl) ? s : undefined;
}
/** The curve bend on [0,1] RGB in place (img: n x 3 floats), as the camera does it on its 12-bit gamma output
 *  (research/splittone/model.py bend28): `balance` moves the hand-over point c = 2048 - 256 b. `curves` (the RGB row)
 *  add their change in the same pass, as st_run does. */
export function bendSplit(img: Float32Array, n: number, s: Split | undefined, scale = 1, balance = 0, curves?: RgbCurves) {
  const ks = s ? SPLIT_K[s.sh_color].map((k) => k * s.sh * scale) : [0, 0, 0], kh = s ? SPLIT_K[s.hl_color].map((k) => k * s.hl * scale) : [0, 0, 0];
  const cd = CHANNELS.map((c) => curveDelta(curves?.[c] ?? [0, 0, 0, 0, 0]));   // RGB curves: added in the same pass (st_run), then the clamp and running max
  const b = Math.max(-BALANCE_MAX, Math.min(BALANCE_MAX, Math.round(balance) || 0)), c = 2048 - 256 * b;
  const lut = [0, 1, 2].map((ch) => {
    const out = new Float32Array(256); let max = 0;
    for (let i = 0; i < 256; i++) {
      const t = i * 4095 / 255, u = t < c ? t * 2048 / c : 2048 + (t - c) * 2047 / (4095 - c);
      const r = 4095 - u, ws = u * r / 4096 * r / 4096, wh = u * u / 4096 * r / 4096;
      max = Math.max(max, Math.min(4095, Math.max(0, t + (ks[ch] * ws + kh[ch] * wh) / 256 + cd[ch](t))));
      out[i] = max / 4095;
    }
    return out;
  });
  for (let i = 0; i < n * 3; i += 3) for (let c = 0; c < 3; c++) {
    const x = Math.min(255, Math.max(0, img[i + c] * 255)), a = Math.floor(x), f = x - a;
    img[i + c] = a >= 255 ? lut[c][255] : lut[c][a] * (1 - f) + lut[c][a + 1] * f;
  }
}
