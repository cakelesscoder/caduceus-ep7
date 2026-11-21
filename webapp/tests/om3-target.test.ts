// The E-P7-convention pack -> OM-3 card files translation (src/targets/om3.ts).
import { describe, expect, it } from 'vitest';
import libraryJson from '../src/data/packs/standard-1.0.json';
import { COLORS, PER, defaultBank, emptyBank, profilesBin, readProfiles, validateBank } from '../src/om3';
import { blankLook, parseLook, parsePack, type Pack } from '../src/pack';
import { looksBinToPack, packToBank } from '../src/targets/om3';
import { CAMERAS } from '../src/cameras';
import { encodeLooksBin, lookRecord, validateLook } from '../src/format';
import { decodeLookCode, decodePackCode, encodeLookCode, encodePackCode } from '../src/sharecode';
import { OM3_FW_LATEST, looksBin, looksBinImport, lookFromOm3, om3, om3LinkBank, om3LinkLook } from '../src/targets/om3';
import { createHash } from 'node:crypto';
import { OM3_V0295_LOOKS_B64 } from './om3-v0.29.5-looks';
import std12Json from '../src/data/packs/standard-1.2.json';
import { lookFromRecord } from '../src/om3';

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
    expect(om3.export(pack([om3Look()]))[0].name).toBe('OM3MOD/LOOKS.BIN');
    const o = 32, b = looksBin(pack([om3Look()]), 26), s8 = (i: number) => (b[o + i] << 24) >> 24;
    expect([s8(37), s8(38)]).toEqual([7, -6]);
    expect(b[o + 49]).toBe(4);          // NR High
    expect(b[o + 50]).toBe(0);          // keep the lens correction
    expect(b[o + 51]).toBe(2);          // Grain Med
    expect([s8(42), s8(52)]).toEqual([0, -5]);
    // c209b69: a minus is written as the opposite wheel colour (1 + 6), which v0.26 and v0.28+ both read as a tint
    expect([b[o + 53], s8(54), b[o + 55], s8(56)]).toEqual([7, 2, 7, 1]);
    const back = looksBinToPack(b, 'x').looks[0];
    expect([back.grain, back.film_grain, back.lens_correction, back.advice.sharpness]).toEqual(['high', 2, true, -5]);
    expect(back.split).toEqual({ sh_color: 7, sh: 2, hl_color: 7, hl: 1 });
    expect(OM3_FW_LATEST).toBe(28);
  });

  it('older OM-3 firmware gets a file it accepts', () => {
    const b = profilesBin(packToBank(pack([om3Look()])).bank, 20), o = 32;
    expect([...b.subarray(o + 50, o + 64)].every((x) => x === 0)).toBe(true);
    expect((b[o + 37] << 24) >> 24).toBe(5);
  });

  it('the E-P7 ignores the OM-3-only fields (split goes to record +61/+62 for v0.32); NR High becomes Standard', async () => {
    const l = om3Look(), plain = { ...om3Look(), grain: 'standard' as const };
    delete (plain as Partial<typeof plain>).film_grain; delete (plain as Partial<typeof plain>).split;
    expect(validateLook(l)).toEqual([]);
    const r = lookRecord(l), s = l.split!;
    expect([r[61], r[62]]).toEqual([s.sh_color | ((s.sh & 15) << 4), s.hl_color | ((s.hl & 15) << 4)]);
    r[61] = r[62] = 0;
    expect(r).toEqual(lookRecord(plain));
    expect(lookRecord(l)[24]).toBe(6);
    expect(encodeLookCode(l)).toBe(encodeLookCode(plain));
    expect(decodeLookCode(encodeLookCode(l)).grain).toBe('standard');
    const p = await decodePackCode(await encodePackCode(pack([l])));
    expect([p.looks[0].grain, p.looks[0].film_grain, p.looks[0].split]).toEqual(['high', 2, l.split]);
  });
});

// Caduceus for OM-3 v0.28 / v0.29.x (resync at c209b69).
describe('OM-3 export for v0.28 and later', () => {
  const STD12 = parsePack(std12Json);
  const REL = new Uint8Array(Buffer.from(OM3_V0295_LOOKS_B64, 'base64'));
  it('the release file is the one their SHA256SUMS lists', () => {
    expect(createHash('sha256').update(REL).digest('hex')).toBe('ee3f1bdef6083ffcfbf88e1c9617adbea10af0594d03424214baf5ed1cd70365');
  });

  it('their v0.29.5 release LOOKS.BIN decodes and re-encodes byte for byte with the vendored code', () => {
    const bank = readProfiles(REL);
    expect(validateBank(bank)).toEqual([]);
    expect(profilesBin(bank, 28)).toEqual(REL);
  });

  it('Standard 1.2 exports a v0.28 LOOKS.BIN their decoder reads back to the same OM-3 looks', () => {
    const r = packToBank(STD12, 28), b = looksBin(STD12, 28);
    expect(validateBank(r.bank)).toEqual([]);
    expect(b.length).toBe(1632);
    const back = readProfiles(b, true);
    const fields = (l: Pack['looks'][number] | null) => l && {
      name: l.name, hue: l.hue, light: l.light, sat: l.sat, wb: l.wb && (l.wb.a_b || l.wb.g_m) ? l.wb : null, tone: l.tone,
      vignette: l.vignette, grain: l.grain, film_grain: l.film_grain, split: l.split, halation: l.halation,
      effect: l.effect ? { type: l.effect.type === 'clarity' ? 'clarity' : 'bloom', strength: l.effect.strength } : null,
      contrast: l.advice.contrast ?? 0, sharp: l.advice.sharpness ?? 0, lens: !!l.lens_correction,
    };
    expect(back.map((row) => row.map(fields))).toEqual(r.bank.map((row) => row.map(fields)));
    // nothing the v0.28 firmware would refuse: +63 zero, film WB / Tone Balance never written from shared looks
    for (let i = 0; i < 20; i++) { const rec = b.subarray(32 + 64 * i, 96 + 64 * i); expect([rec[58], rec[59], rec[60], rec[61], rec[62], rec[63]]).toEqual([0, 0, 0, 0, 0, 0]); }
    // older firmware: no v0.28 bytes at all
    const old = looksBin(STD12, 26);
    for (let i = 0; i < 20; i++) expect([...old.subarray(32 + 64 * i + 57, 32 + 64 * i + 64)].every((x) => x === 0)).toBe(true);
  });

  it('curve and colour matrix (E-P7 v0.34) are left out and reported', () => {
    const l = blankLook('colour', 'Hw'); l.curve = 'pop'; l.matrix = [6, -10, 4, -6, -8, 4];
    const r = packToBank(pack([l]), 28), b = looksBin(pack([l]), 28), plain = looksBin(pack([blankLook('colour', 'Hw')]), 28);
    expect(r.placed[0].dropped).toEqual(['Base curve', 'Colour mix']);
    expect(r.bank[0][0]).not.toHaveProperty('curve');
    expect(b).toEqual(plain);
  });

  it('the halo becomes Halation on v0.28 and Glow on older firmware', () => {
    const h = blankLook('colour', 'H'); h.effect = { type: 'halation', strength: 3 };
    const t = blankLook('colour', 'T'); t.effect = { type: 'bloom', strength: 4, tint: 'red' };
    const b28 = looksBin(pack([h, t]), 28), b26 = looksBin(pack([h, t]), 26), rec = (b: Uint8Array, i: number) => b.subarray(32 + 64 * i, 96 + 64 * i);
    expect([(rec(b28, 0)[47] << 24) >> 24, rec(b28, 0)[57]]).toEqual([0, 3]);     // Halation alone
    expect([(rec(b28, 1)[47] << 24) >> 24, rec(b28, 1)[57]]).toEqual([-4, 4]);    // Glow 4 + Halation 4
    expect([(rec(b26, 0)[47] << 24) >> 24, rec(b26, 0)[57]]).toEqual([-3, 0]);    // older: plain Glow
    expect(packToBank(pack([h]), 28).placed[0].changed).toEqual([]);
    expect(packToBank(pack([h]), 26).placed[0].changed).toContain('halation as glow');
    const back = looksBinToPack(b28, 'x').looks;                                    // and back to the shared look
    expect(back[0].effect).toEqual({ type: 'halation', strength: 3 });
    expect(back[1].effect).toEqual({ type: 'bloom', strength: 4, tint: 'red' });
  });

  it('their v0.28 look settings come in as shared fields or are reported, never kept', () => {
    const rec = new Uint8Array(64);
    rec[53] = 8; rec[54] = 255; rec[55] = 1; rec[56] = 5;          // split codes -1 (0.5) and 5 (5)
    rec[57] = 2; rec[58] = 253; rec[39] = 7;                        // Halation 2, Tone Balance -3, Blacks 7
    rec[59] = 252; rec[60] = 252; rec[61] = 1; rec[62] = 1;         // Custom WB 3200 K
    const { look, changed } = lookFromOm3(lookFromRecord(rec, 'V28', true));
    expect(look.split).toEqual({ sh_color: 8, sh: 1, hl_color: 1, hl: 5 });
    expect(look.effect).toEqual({ type: 'halation', strength: 2 });
    expect(look.tone.blacks).toBe(5);
    for (const k of ['halation', 'tone_balance', 'film_wb']) expect(look).not.toHaveProperty(k);
    expect(changed).toEqual(['Tone Balance left out', 'WB mode left out', 'split toning half steps rounded', 'Blacks / Whites limited to ±5']);
    expect(validateLook(look)).toEqual([]);
    expect(decodeLookCode(encodeLookCode(look)).effect).toEqual(look.effect);
  });

  it('the release LOOKS.BIN opens as a valid pack and says what the shared format leaves out', () => {
    const { pack: p, notes } = looksBinImport(REL, 'rel');
    expect(p.looks).toHaveLength(20);
    expect(notes).toEqual([]);                                     // the release's films use no v0.28-only setting
    // only the names can be too long: the OM-3 allows 15 characters, the shared format 12 (the editor asks to shorten)
    p.looks.forEach((l) => { expect(validateLook(l).filter((x) => x.field !== 'name')).toEqual([]); for (const k of ['halation', 'tone_balance', 'film_wb']) expect(l).not.toHaveProperty(k); });
  });

  it('their op1_ / ob1_ link JSON (caduceus-om3-look/1) reads; a newer format is refused', () => {
    const j = { schema: 'caduceus-om3-look/1', min_fw: '0.28', ...blankLook('colour', 'Link'), halation: 3, tone_balance: 2,
      split: { sh_color: 2, sh: 1.5, hl_color: 0, hl: 0 }, film_wb: { mode: 'shade' } };
    const r = om3LinkLook(JSON.parse(JSON.stringify(j)));
    expect(r.look.effect).toEqual({ type: 'halation', strength: 3 });
    expect(r.look.split).toEqual({ sh_color: 2, sh: 2, hl_color: 0, hl: 0 });
    expect(r.changed).toEqual(['Tone Balance left out', 'WB mode left out', 'split toning half steps rounded']);
    expect(() => om3LinkLook({ ...j, schema: 'caduceus-om3-look/2' })).toThrow(/newer/);
    const old = om3LinkLook({ ...blankLook('colour', 'Old'), split: { sh_color: 2, sh: -1, hl_color: 0, hl: 0 } });   // v0.26-era link
    expect(old.look.split).toEqual({ sh_color: 8, sh: 1, hl_color: 0, hl: 0 });
    const bank = om3LinkBank({ schema: 'caduceus-om3-bank/1', name: 'B', bank: [[j, null], [], [], []] });
    expect(bank.pack.looks.map((l) => l.name)).toEqual(['Link']);
    expect(bank.notes[0]).toMatch(/^Link: Tone Balance left out/);
  });
});

// Caduceus for OM-3 v0.30 (RGB curves, Color Mix) and v0.40 (Border, Film Grain 1..5 / Grain Size), resync at 9fc2dc1 (their v0.40.2).
// Their v0.40 to v0.40.2 ship the same LOOKS.BIN as v0.29.5 (sha256 ee3f1bde…, checked above), so the release tests
// still hold.
describe('OM-3 export for v0.30 and v0.40', () => {
  const STD12 = parsePack(std12Json);
  const rec = (b: Uint8Array, i: number) => b.subarray(32 + 64 * i, 96 + 64 * i);

  it('their 20 films (the vendored om3films, FILM 1-20) make their v0.40.2 release LOOKS.BIN byte for byte', () => {
    const b = profilesBin(defaultBank(LIB, (l) => l), 28);
    expect(createHash('sha256').update(b).digest('hex')).toBe('ee3f1bdef6083ffcfbf88e1c9617adbea10af0594d03424214baf5ed1cd70365');
  });

  it('shared looks never set a v0.40 Border: +48 stays 0 for v0.28 and later', () => {
    const b = looksBin(STD12, 28);
    for (let i = 0; i < 20; i++) expect(rec(b, i)[48]).toBe(0);
  });

  it('a v0.40 Border in a card file comes in reported, never kept, and a white one is not read as an Art Effect', () => {
    const bank = emptyBank(), white = blankLook('colour', 'White'), black = blankLook('colour', 'Black');
    white.border = 3; black.border = -2;
    bank[0][0] = white; bank[0][1] = black;
    const file = profilesBin(bank, 28);
    expect([(rec(file, 0)[48] << 24) >> 24, (rec(file, 1)[48] << 24) >> 24]).toEqual([3, -2]);
    const { pack: p, notes } = looksBinImport(file, 'v040');
    expect(p.looks.map((l) => l.art_effect)).toEqual(['off', 'off']);
    p.looks.forEach((l) => expect(l).not.toHaveProperty('border'));
    expect(notes).toEqual(['White: Border left out', 'Black: Border left out']);
    expect(looksBin(p, 28)).toEqual(looksBin(pack([blankLook('colour', 'White'), blankLook('colour', 'Black')]), 28));
  });

  it('their v0.40 link fields (RGB curves, Color Mix, Border, Film Grain 1..5 / Grain Size) are reported, never kept', () => {
    const j = { schema: 'caduceus-om3-look/1', ...blankLook('colour', 'New'), film_grain: 1, grain_strength: 1, grain_size: 3,
      rgb: { r: [2, 0, 0, 0, -1], g: [0, 0, 0, 0, 0], b: [0, 1, 0, 0, 0] }, mix: [1, -1, 0, -2, 0, 1], border: -3 };
    const r = om3LinkLook(JSON.parse(JSON.stringify(j)));
    expect(r.changed).toEqual(['RGB curves left out', 'Color Mix left out', 'Border left out', 'Film Grain 1 kept as Low', 'Grain Size left out']);
    for (const k of ['rgb', 'mix', 'border', 'grain_size', 'grain_strength']) expect(r.look).not.toHaveProperty(k);
    expect(r.look.film_grain).toBe(1);
    expect(validateLook(r.look)).toEqual([]);
    const flat = om3LinkLook({ ...blankLook('colour', 'Flat'), rgb: { r: [0, 0, 0, 0, 0], g: [0, 0, 0, 0, 0], b: [0, 0, 0, 0, 0] }, mix: [0, 0, 0, 0, 0, 0] });
    expect(flat.changed).toEqual([]);                              // flat curves and an empty mix change nothing
  });
});
