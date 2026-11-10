// The E-P7-convention pack -> OM-3 card files translation (src/targets/om3.ts).
import { describe, expect, it } from 'vitest';
import libraryJson from '../src/data/library.json';
import { COLORS, PER, profilesBin, readProfiles, validateBank } from '../src/om3';
import { blankLook, parseLook, parsePack, type Pack } from '../src/pack';
import { looksBinToPack, packToBank } from '../src/targets/om3';
import { CAMERAS } from '../src/cameras';
import { encodeLooksBin, lookRecord, validateLook } from '../src/format';
import { decodeLookCode, decodePackCode, encodeLookCode, encodePackCode } from '../src/sharecode';
import { OM3_FW_LATEST, om3 } from '../src/targets/om3';

const LIB = parsePack(libraryJson);
const pack = (looks: Pack['looks']): Pack => ({ ...LIB, looks, slots: {} });

describe('OM-3 export', () => {
  it('the standard library fills 20 valid looks in list order', () => {
    const r = packToBank(LIB), colour = LIB.looks.filter((l) => l.kind === 'colour');
    expect(r.placed).toHaveLength(COLORS * PER);
    expect(validateBank(r.bank)).toEqual([]);
    expect(r.bank[0][0]!.name).toBe(colour[0].name);
    expect(r.bank[1][0]!.name).toBe(colour[5].name);
    expect(r.extra).toEqual(colour.slice(20).map((l) => l.name));
    expect(r.mono).toBe(LIB.looks.length - colour.length);
  });

  it('copies hue as it is, limits ranges and reports what changed', () => {
    const l = blankLook('colour', 'X');
    l.hue[0] = 2; l.hue[3] = 7; l.lens_correction = true; l.art_effect = 'blur';
    const r = packToBank(pack([l, blankLook('mono', 'M')]));
    expect(r.bank[0][0]!.hue[0]).toBe(2);
    expect(r.bank[0][0]!.hue[3]).toBe(5);
    expect(r.bank[0][1]).toBeNull();
    expect(r.placed[0].changed).toContain('Hue/Light');
    expect(r.placed[0].dropped).toEqual(['Blur']);
    expect([r.mono, r.lens]).toEqual([1, 1]);
  });

  it('a card file opens back to the same look values', () => {
    const src = LIB.looks.filter((l) => l.kind === 'colour' && l.hue.every((v) => Math.abs(v) <= 5)).slice(0, 3);
    const back = looksBinToPack(profilesBin(packToBank(pack(src)).bank), 'x');
    expect(back.looks.map((l) => l.hue)).toEqual(src.map((l) => l.hue));
    expect(back.looks.map((l) => l.name)).toEqual(src.map((l) => l.name));
    expect(readProfiles(profilesBin(packToBank(pack(src)).bank))[0][3]).toBeNull();
  });

  it('editor limits match what each camera accepts', () => {
    const l = blankLook('colour', 'X'), c = CAMERAS.om3;
    l.hue[0] = c.hl; l.light[0] = -c.hl; l.sat[0] = c.sat; l.wb = { a_b: c.wb, g_m: -c.wb };
    c.arts.forEach((a) => { l.art_effect = a; expect(validateBank([[l]])).toEqual([]); });
    expect(CAMERAS.ep7.hl).toBe(7);
  });

  it('leaves the E-P7 export alone', () => {
    const before = encodeLooksBin(LIB);
    packToBank(LIB);
    expect(encodeLooksBin(LIB)).toEqual(before);
  });

  // Caduceus for OM-3 v0.26.1 fields (resync at 87b3e6f).
  const om3Look = () => {
    const l = blankLook('colour', 'Om');
    l.grain = 'high'; l.film_grain = 2; l.split = { sh_color: 7, sh: 2, hl_color: 1, hl: -1 };
    l.lens_correction = true; l.advice = { sharpness: -5 }; l.wb = { a_b: 7, g_m: -6 };
    return l;
  };

  it('reads NR High, film_grain and split from an OM-3 look', () => {
    const l = parseLook(JSON.parse(JSON.stringify(om3Look())), 'look');
    expect(l.grain).toBe('high');
    expect(l.film_grain).toBe(2);
    expect(l.split).toEqual({ sh_color: 7, sh: 2, hl_color: 1, hl: -1 });
    expect(parseLook({ ...l, split: { sh_color: 12, sh: 1, hl_color: 0, hl: 0 }, film_grain: 0 }, 'look')).not.toHaveProperty('split');
  });

  it('writes lens correction, Sharp, Grain, split, NR High and WB ±7 into the v0.26.1 LOOKS.BIN', () => {
    const [f] = om3.export(pack([om3Look()]));
    expect(f.name).toBe('OM3MOD/LOOKS.BIN');
    const o = 32, b = f.data as Uint8Array, s8 = (i: number) => (b[o + i] << 24) >> 24;
    expect([s8(37), s8(38)]).toEqual([7, -6]);
    expect(b[o + 49]).toBe(4);          // NR High
    expect(b[o + 50]).toBe(0);          // keep the lens correction
    expect(b[o + 51]).toBe(2);          // Grain Med
    expect([s8(42), s8(52)]).toEqual([0, -5]);
    expect([b[o + 53], s8(54), b[o + 55], s8(56)]).toEqual([7, 2, 1, -1]);
    const back = looksBinToPack(b, 'x').looks[0];
    expect([back.grain, back.film_grain, back.lens_correction, back.advice.sharpness]).toEqual(['high', 2, true, -5]);
    expect(back.split).toEqual(om3Look().split);
    expect(OM3_FW_LATEST).toBe(26);
  });

  it('older OM-3 firmware gets a file it accepts', () => {
    const b = profilesBin(packToBank(pack([om3Look()])).bank, 20), o = 32;
    expect([...b.subarray(o + 50, o + 64)].every((x) => x === 0)).toBe(true);
    expect((b[o + 37] << 24) >> 24).toBe(5);
  });

  it('the E-P7 ignores the OM-3-only fields; NR High becomes Standard', async () => {
    const l = om3Look(), plain = { ...om3Look(), grain: 'standard' as const };
    delete (plain as Partial<typeof plain>).film_grain; delete (plain as Partial<typeof plain>).split;
    expect(validateLook(l)).toEqual([]);
    expect(lookRecord(l)).toEqual(lookRecord(plain));
    expect(lookRecord(l)[24]).toBe(6);
    expect(encodeLookCode(l)).toBe(encodeLookCode(plain));
    expect(decodeLookCode(encodeLookCode(l)).grain).toBe('standard');
    const p = await decodePackCode(await encodePackCode(pack([l])));
    expect([p.looks[0].grain, p.looks[0].film_grain, p.looks[0].split]).toEqual(['high', 2, l.split]);
  });
});
