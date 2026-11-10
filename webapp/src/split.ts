// Vendored from androidfanman/caduceus-om3 @ 87b3e6f (Apache-2.0, see NOTICE), unchanged. Update by copying; our glue is in ./targets/om3.ts.
// Split toning (Caduceus for OM-3 v0.26): a Shadows and a Highlights tint, each one of the camera wheel's 12 colours
// with a strength -5..5 (minus = the opposite colour). The camera bends its R, G and B gamma curves (firmware st_run,
// research/splittone/model.py); this module holds the same numbers for the preview and the editor.
import type { Look } from './pack';

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
export const hasSplit = (l: Look) => !!l.split && (l.split.sh !== 0 || l.split.hl !== 0);
const ok = (c: number, s: number) => Number.isInteger(c) && c >= 0 && c < 12 && Number.isInteger(s) && Math.abs(s) <= SPLIT_MAX;
export const splitOk = (s: Split) => ok(s.sh_color, s.sh) && ok(s.hl_color, s.hl);
/** A parsed `split` field, or undefined when it is missing, off or malformed. */
export function parseSplit(v: unknown): Split | undefined {
  if (!v || typeof v !== 'object') return undefined;
  const o = v as Record<string, unknown>, n = (x: unknown) => (typeof x === 'number' ? x : NaN);
  const s = { sh_color: n(o.sh_color), sh: n(o.sh), hl_color: n(o.hl_color), hl: n(o.hl) };
  return splitOk(s) && (s.sh || s.hl) ? s : undefined;
}
/** The curve bend on [0,1] RGB in place (img: n x 3 floats), as the camera does it on its 12-bit gamma output. */
export function bendSplit(img: Float32Array, n: number, s: Split) {
  const ks = SPLIT_K[s.sh_color].map((k) => k * s.sh), kh = SPLIT_K[s.hl_color].map((k) => k * s.hl);
  const lut = [0, 1, 2].map((c) => {
    const out = new Float32Array(256); let max = 0;
    for (let i = 0; i < 256; i++) {
      const t = i * 4095 / 255, r = 4095 - t, ws = t * r / 4096 * r / 4096, wh = t * t / 4096 * r / 4096;
      max = Math.max(max, Math.min(4095, Math.max(0, t + (ks[c] * ws + kh[c] * wh) / 256)));
      out[i] = max / 4095;
    }
    return out;
  });
  for (let i = 0; i < n * 3; i += 3) for (let c = 0; c < 3; c++) {
    const x = Math.min(255, Math.max(0, img[i + c] * 255)), a = Math.floor(x), f = x - a;
    img[i + c] = a >= 255 ? lut[c][255] : lut[c][a] * (1 - f) + lut[c][a + 1] * f;
  }
}
