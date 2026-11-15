// Colour mix editor maths (src/colourmix.ts): the editor arranges the shared `matrix` field, it never changes it.
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { MIX_ROWS, applyMix, fullMatrix, mixState, offDiagonals, rowSelf, setMixEntry, testChart } from '../src/colourmix';
import { NAMED_MIXES, mixRow, parsePack } from '../src/pack';

const std12 = parsePack(JSON.parse(readFileSync(new URL('../src/data/packs/standard-1.2.json', import.meta.url), 'utf8')));

describe('colour mix editor', () => {
  it('row diagonal = 128 minus the row, every row sums to 128; identity when absent', () => {
    const m = [32, -32, 16, -8, -24, 40];
    const M = fullMatrix(m);
    expect(M).toEqual([[128, 32, -32], [16, 120, -8], [-24, 40, 112]]);
    for (const r of M) expect(r.reduce((a, b) => a + b, 0)).toBe(128);
    expect([0, 1, 2].map((r) => rowSelf(m, r))).toEqual([128, 120, 112]);
    expect(fullMatrix(undefined)).toEqual([[128, 0, 0], [0, 128, 0], [0, 0, 128]]);
    expect(offDiagonals(fullMatrix(undefined))).toBeUndefined();
  });

  it('rows map to the shared field order m01 m02 m10 m12 m20 m21', () => {
    expect(MIX_ROWS.flatMap((r) => r.from.map(([, i]) => i))).toEqual([0, 1, 2, 3, 4, 5]);
    expect(MIX_ROWS.map((r) => r.from.map(([s]) => s))).toEqual([['Green', 'Blue'], ['Red', 'Blue'], ['Red', 'Green']]);
  });

  it('slider edits: one entry, clamped to ±64, back to absent at identity', () => {
    expect(setMixEntry(undefined, 3, 12)).toEqual([0, 0, 0, 12, 0, 0]);
    expect(setMixEntry([0, 0, 0, 12, 0, 0], 3, 0)).toBeUndefined();
    expect(setMixEntry(undefined, 0, 99)).toEqual([64, 0, 0, 0, 0, 0]);
    expect(setMixEntry(undefined, 5, -99)).toEqual([0, 0, 0, 0, 0, -64]);
  });

  it('presets: 100 % is the camera numbers, Off is identity', () => {
    for (const x of NAMED_MIXES) {
      expect(applyMix(x.name)).toEqual(x.m);
      expect(mixState(applyMix(x.name))).toEqual({ name: x.name, pct: 100 });
    }
    expect(applyMix('off')).toBeUndefined();
    expect(mixState(undefined)).toBeNull();
  });

  it('strength scales a named mix as the camera does (10..100 %)', () => {
    for (const x of NAMED_MIXES) for (let s = 1; s <= 10; s++) {
      expect(applyMix(x.name, s * 10) ?? [0, 0, 0, 0, 0, 0]).toEqual(mixRow(x.m, s));
      const st = mixState(applyMix(x.name, s * 10), x.name);
      if (applyMix(x.name, s * 10)) expect(st).toEqual({ name: x.name, pct: s * 10 });
    }
    expect(applyMix('Warm film', 50)).toEqual([3, -5, 2, -3, -4, 2]);
    expect(applyMix('Warm film', 0)).toBeUndefined();
  });

  it('own numbers are not a named mix', () => {
    expect(mixState([32, -20, 5, 1, 0, 9])).toBeNull();
  });

  it('Standard 1.2 matrices round-trip through the editor unchanged', () => {
    const looks = std12.looks.filter((l) => l.matrix);
    expect(looks.length).toBeGreaterThan(5);
    for (const l of looks) {
      expect(offDiagonals(fullMatrix(l.matrix))).toEqual(l.matrix);
      let m: number[] | undefined;   // rebuilt slider by slider, as the editor does
      MIX_ROWS.forEach((r) => r.from.forEach(([, i]) => { m = setMixEntry(m, i, l.matrix![i]); }));
      expect(m).toEqual(l.matrix);
      for (const row of fullMatrix(l.matrix)) expect(row.reduce((a, b) => a + b, 0)).toBe(128);
    }
  });

  it('test chart: grey ramp is neutral', () => {
    const W = 90, H = 60, px = testChart(W, H);
    expect(px.length).toBe(W * H * 4);
    for (let x = 0; x < W; x += 7) { const i = ((H - 1) * W + x) * 4; expect(px[i]).toBe(px[i + 1]); expect(px[i + 1]).toBe(px[i + 2]); }
  });
});
