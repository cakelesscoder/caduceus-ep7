// The E-M1 Mark II export target (src/targets/em1mk2.ts): same LOOKS.BIN as the E-P7, plus the preview translation.
import { describe, expect, it } from 'vitest';
import libraryJson from '../src/data/library.json';
import { checkLooksBin, decodeLooksBin, encodeLooksBin } from '../src/format';
import { blankLook, parsePack, type Pack } from '../src/pack';
import { em1Dropped, em1mk2, toEm1 } from '../src/targets/em1mk2';
import { CAMERAS } from '../src/cameras';

const LIB = parsePack(libraryJson);
const pack = (looks: Pack['looks']): Pack => ({ ...LIB, looks: looks.slice(0, 32), slots: {} });

describe('E-M1 II export', () => {
  it('writes EM1MOD/LOOKS.BIN byte-identical to the E-P7 file', () => {
    const p = pack(LIB.looks);
    const [f] = em1mk2.export(p) as { name: string; data: Uint8Array }[];
    expect(f.name).toBe('EM1MOD/LOOKS.BIN');
    expect(Array.from(f.data)).toEqual(Array.from(encodeLooksBin(p)));
    expect(checkLooksBin(f.data)).toEqual([]);
  });

  it('round-trips through the shared decoder', () => {
    const p = pack(LIB.looks.slice(0, 16));
    const back = decodeLooksBin((em1mk2.export(p) as { data: Uint8Array }[])[0].data);
    expect(back.looks.map((l) => l.name)).toEqual(p.looks.map((l) => l.name));
  });

  it('has a camera profile', () => {
    expect(CAMERAS.em1mk2.short).toBe('E-M1 II');
  });
});

describe('E-M1 II preview translation', () => {
  it('keeps colour, hue, light and H/M/S; drops WB, effect, vignette, grain, blacks/whites', () => {
    const l = { ...blankLook('colour', 'T'), sat: new Array(12).fill(3), hue: new Array(12).fill(2), light: new Array(12).fill(-1),
      wb: { a_b: 2, g_m: -1 }, vignette: -3, grain: 'film' as const,
      tone: { highlights: 1, midtones: -2, shadows: -4, blacks: 2, whites: -1 } };
    const e = toEm1(l);
    expect(e.sat).toEqual(l.sat);
    expect(e.hue).toEqual(l.hue);
    expect(e.light).toEqual(l.light);
    expect([e.tone.highlights, e.tone.midtones, e.tone.shadows]).toEqual([1, -2, -4]);
    expect([e.tone.blacks, e.tone.whites]).toEqual([0, 0]);
    expect(e.wb).toBeNull();
    expect(e.vignette).toBe(0);
    expect(e.grain).toBe('off');
    expect(em1Dropped(l)).toEqual(['WB shift', 'vignette', 'grain / NR', 'blacks / whites']);
    expect(l.wb).toEqual({ a_b: 2, g_m: -1 });   // the look itself is untouched
  });

  it('shows mono looks as desaturated colour (no B&W path yet)', () => {
    const e = toEm1(blankLook('mono', 'M'));
    expect(e.kind).toBe('colour');
    expect(e.sat.every((v) => v === -5)).toBe(true);
    expect(em1Dropped(blankLook('mono', 'M'))[0]).toMatch(/black & white/);
  });
});
