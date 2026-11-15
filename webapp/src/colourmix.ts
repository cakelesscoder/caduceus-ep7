// Colour mix editor maths (look editor "Colour mix" group). The look keeps the shared `matrix` field unchanged
// (docs/LOOK_FORMAT_V4.md: [m01, m02, m10, m12, m20, m21] in 1/128, absent = identity); this only arranges it as
// three output rows and the full 3 x 3 the camera uses (each row's own amount = 128 minus its two entries).
import { MATRIX_MAX, NAMED_MIXES, matrixIsZero, mixRow, namedMix } from './pack';

export const MIX_ONE = 128;
/** One editor row per output colour: its two "from" inputs and their index in the shared field. */
export const MIX_ROWS: { out: string; key: 'r' | 'g' | 'b'; from: [string, number][] }[] = [
  { out: 'Red', key: 'r', from: [['Green', 0], ['Blue', 1]] },
  { out: 'Green', key: 'g', from: [['Red', 2], ['Blue', 3]] },
  { out: 'Blue', key: 'b', from: [['Red', 4], ['Green', 5]] },
];

/** The full matrix in 1/128 (rows R G B out, columns R G B in); every row sums to 128. */
export function fullMatrix(m?: number[]): number[][] {
  const [a, b, c, d, e, f] = m ?? [0, 0, 0, 0, 0, 0];
  return [[MIX_ONE - a - b, a, b], [c, MIX_ONE - c - d, d], [e, f, MIX_ONE - e - f]];
}
/** Back to the shared field from a full matrix (diagonals are implied); undefined = identity. */
export function offDiagonals(M: number[][]): number[] | undefined {
  const m = [M[0][1], M[0][2], M[1][0], M[1][2], M[2][0], M[2][1]];
  return matrixIsZero(m) ? undefined : m;
}
/** Row r's own amount (greyed in the editor). */
export const rowSelf = (m: number[] | undefined, r: number) => fullMatrix(m)[r][r];

/** The matrix with entry i set to v (clamped to the format's range); undefined = identity (field left out). */
export function setMixEntry(m: number[] | undefined, i: number, v: number): number[] | undefined {
  const out = [...(m ?? [0, 0, 0, 0, 0, 0])];
  out[i] = Math.max(-MATRIX_MAX, Math.min(MATRIX_MAX, Math.round(v)));
  return matrixIsZero(out) ? undefined : out;
}

/** Strength steps the camera offers for a named mix (10 % .. 100 %). */
export const MIX_STRENGTHS = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100] as const;
/** A named mix at a strength (10..100 %, the camera's rounding); 'off' or 0 % = identity. */
export function applyMix(name: string, pct = 100): number[] | undefined {
  const x = NAMED_MIXES.find((n) => n.name === name);
  if (!x || pct <= 0) return undefined;
  const m = mixRow(x.m, Math.max(1, Math.min(10, Math.round(pct / 10))));
  return matrixIsZero(m) ? undefined : m;
}
/** Which named mix (and strength) the matrix holds. `prefer` (the preset the user last picked) wins when it also fits,
 *  so a weak step that two mixes share keeps the user's name. null = off or the look's own numbers. */
export function mixState(m: number[] | undefined, prefer?: string): { name: string; pct: number } | null {
  if (matrixIsZero(m)) return null;
  if (prefer) for (let s = 10; s >= 1; s--) {
    const v = applyMix(prefer, 10 * s);
    if (v && v.every((x, i) => x === m![i])) return { name: prefer, pct: 10 * s };
  }
  return namedMix(m);
}

/** Optional preview source: hue sweep, saturation steps, colour-checker style patches and a grey ramp (sRGB RGBA). */
export function testChart(W = 900, H = 600): Uint8ClampedArray<ArrayBuffer> {
  const px = new Uint8ClampedArray(new ArrayBuffer(W * H * 4));
  const hsv = (hh: number, s: number, v: number) => {
    const f = (n: number) => { const k = (n + hh / 60) % 6; return v - v * s * Math.max(0, Math.min(k, 4 - k, 1)); };
    return [f(5) * 255, f(3) * 255, f(1) * 255];
  };
  const checker = [[115, 82, 68], [194, 150, 130], [98, 122, 157], [87, 108, 67], [133, 128, 177], [103, 189, 170],
    [214, 126, 44], [80, 91, 166], [193, 90, 99], [94, 60, 108], [157, 188, 64], [224, 163, 46],
    [56, 61, 150], [70, 148, 73], [175, 54, 60], [231, 199, 31], [187, 86, 149], [8, 133, 161]];
  const y1 = H * 0.25, y2 = H * 0.383, y3 = H * 0.867, cw = W / 6, ch = (y3 - y2) / 3, sw = W / 12;
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    let c: number[];
    if (y < y1) c = hsv((x / W) * 360, 1 - (y / y1) * 0.45, 0.92);
    else if (y < y2) c = hsv(Math.floor(x / sw) * 30 + 15, ((x % sw) / sw) * 0.9 + 0.1, 0.85);
    else if (y < y3) {
      const col = Math.floor(x / cw), row = Math.min(2, Math.floor((y - y2) / ch)), ix = x % cw, iy = (y - y2) % ch;
      c = ix > 8 && ix < cw - 8 && iy > 8 && iy < ch - 8 ? checker[row * 6 + col] : [40, 40, 40];
    } else { const g = Math.round((Math.floor(x / (W / 16)) * 255) / 15); c = [g, g, g]; }
    const i = (y * W + x) * 4;
    px[i] = c[0]; px[i + 1] = c[1]; px[i + 2] = c[2]; px[i + 3] = 255;
  }
  return px;
}
