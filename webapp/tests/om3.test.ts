// From androidfanman/caduceus-om3 @ c209b69 (Apache-2.0, see NOTICE), unchanged except the library import path
// (ours: data/packs/) and three cases skipped (it.skip, marked SKIP-HERE): they test that project's own pack.ts look JSON
// (schema field, Halation / Tone Balance / film WB / v0.28 split kept in looks), which is not the shared format here;
// targets/om3.ts translates at the boundary instead (tests/om3-target.test.ts).
// OM-3 mode (Caduceus for OM-3): the profile bank and PROFILES.BIN.
// The byte check against card/mkprofiles.py runs when the caduceus-om3 repo is the parent folder (skipped otherwise).
import { execFileSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import libraryJson from '../src/data/packs/standard-1.0.json';
import { blankLook, parsePack, type Look } from '../src/pack';
import { fromLibrary } from '../src/reset';
import { COLORS, PER, defaultBank, emptyBank, parseBank, monoGrain, profilesBin, readProfiles, slowGrain, toOm3, validateBank, type Bank } from '../src/om3';
import { parseLook } from '../src/pack';
import { FILMS, FILM_GROUPS, filmByName, filmLook } from '../src/om3films';
import { validateProfile, exportLook, minFw, bankMinFw, FW_NAME } from '../src/om3';
import { LOOK_SCHEMA } from '../src/pack';

const LIB = parsePack(libraryJson);
const MK = join(__dirname, '../../card/mkprofiles.py');
const hex = (b: Uint8Array) => Buffer.from(b).toString('hex');

/** The bank in mkprofiles.py's input format. */
const pyJson = (bank: Bank) => ({
  sel: [0, 0, 0, 0],
  prof: bank.map((row) => row.map((l) => l && {
    name: l.name, hue: l.hue, light: l.light, sat: l.sat, wb: !!(l.wb && (l.wb.a_b || l.wb.g_m)), ab: l.wb?.a_b ?? 0, gm: l.wb?.g_m ?? 0,
    blacks: l.tone.blacks, whites: l.tone.whites, contrast: l.advice.contrast ?? 0, sharp: 0, sharp22: l.advice.sharpness ?? 0, shading: l.vignette,
    sh: l.tone.shadows, mid: l.tone.midtones, hi: l.tone.highlights,
    fx: !l.effect ? 0 : l.effect.type === 'clarity' ? l.effect.strength : -l.effect.strength,
    art: ['off', 'star_light', 'pin_hole', 'blur', 'white_edge', 'frame'].indexOf(l.art_effect), nr: ['off', 'standard', 'fine', 'film'].indexOf(l.grain),
    vig: l.lens_correction ? 0 : 1, grain: l.film_grain ?? 0,
  })),
});
function rnd(seed: number) { let s = seed; return (n: number) => { s = (s * 1103515245 + 12345) & 0x7fffffff; return (s % (2 * n + 1)) - n; }; }
function randomBank(seed: number): Bank {
  const r = rnd(seed), b = emptyBank();
  for (let k = 0; k < COLORS; k++) for (let v = 0; v < PER; v++) {
    if (r(1) === 0) continue;
    const l = blankLook('colour', `P${k}${v} ${seed}`.slice(0, 12));
    l.hue = l.hue.map(() => r(5)); l.light = l.light.map(() => r(5)); l.sat = l.sat.map(() => r(5));
    l.wb = r(1) ? { a_b: r(5), g_m: r(5) } : null;
    l.tone = { highlights: r(7), shadows: r(7), midtones: r(7), blacks: r(5), whites: r(5) };
    l.advice = { contrast: r(2), sharpness: Math.max(-5, Math.min(2, r(5))) }; l.vignette = r(5);
    const fx = r(5); l.effect = fx < 0 ? { type: 'bloom', strength: -fx } : fx > 0 ? { type: 'clarity', strength: fx } : null;
    l.art_effect = (['off', 'star_light', 'pin_hole', 'white_edge', 'frame'] as const)[Math.abs(r(4))];
    l.grain = (['off', 'standard', 'fine', 'film'] as const)[Math.abs(r(3))];
    if (r(1)) l.lens_correction = true;
    const g = Math.abs(r(3)); if (g) l.film_grain = g;
    b[k][v] = l;
  }
  return b;
}

describe('OM-3 profile bank', () => {
  it('first visit: the 20 films in the owner\'s FILM 1-20 order, all valid for the camera', () => {
    const b = defaultBank(LIB, fromLibrary);
    expect(b.flat().filter(Boolean)).toHaveLength(20);
    expect(validateBank(b)).toEqual([]);
    expect(b.map((r) => r.map((l) => l!.name))).toEqual([
      ['Portra 400', 'Portra 160', 'Portra 800', 'Gold 200', 'ColorPlus 200'],
      ['Ektar 100', 'Ektachrome E100', 'Kodachrome 64', 'CineStill 800T', 'Velvia 50'],
      ['Provia 100F', 'Pro 400H', 'Pro 160S', 'NPS 160', 'NHG II 800'],
      ['Superia 400', 'Fuji C200', 'Fujifilm 200', 'Fujifilm 400', 'Natura 1600'],
    ]);
    expect(b[0][0]!.origin).toBe('film:Portra 400');
    expect(filmByName('Fuji 400H')!.name).toBe('Pro 400H');   // renamed films keep older looks' film
    for (const l of b.flat()) {   // no grain, Glow / Clarity or Art Effect in the start-up looks
      expect(l!.effect).toBeNull(); expect(l!.art_effect).toBe('off'); expect(l!.film_grain).toBeUndefined();
    }
  });

  it('toOm3: mono refused, ranges limited, v0.20 Extras kept (glow without colour, no Blur)', () => {
    expect(toOm3(blankLook('mono')).look).toBeNull();
    const l = blankLook('colour', 'X');
    l.hue[0] = 7; l.light[3] = -6; l.wb = { a_b: 8, g_m: -1 }; l.grain = 'film'; l.effect = { type: 'halation', strength: 2, tint: 'red' }; l.art_effect = 'pin_hole';
    const c = toOm3(l);
    expect(c.look!.hue[0]).toBe(5); expect(c.look!.light[3]).toBe(-5); expect(c.look!.wb).toEqual({ a_b: 7, g_m: -1 });
    expect(c.look!.grain).toBe('film'); expect(c.look!.effect).toEqual({ type: 'bloom', strength: 2 }); expect(c.look!.art_effect).toBe('pin_hole');
    expect(c.changed).toEqual(['Hue/Light', 'WB', 'halation as glow']);
    expect(c.dropped).toEqual([]);
    const b = blankLook('colour', 'Y'); b.art_effect = 'blur'; b.effect = { type: 'clarity', strength: 3 };
    const d = toOm3(b);
    expect(d.look!.art_effect).toBe('off'); expect(d.dropped).toEqual(['Blur']); expect(d.look!.effect).toEqual({ type: 'clarity', strength: 3 });
    expect(validateBank([[c.look, d.look]])).toEqual([]);
  });

  it('PROFILES.BIN round-trips', () => {
    for (const seed of [1, 2, 3]) {
      const b = randomBank(seed), back = readProfiles(profilesBin(b));
      for (let k = 0; k < COLORS; k++) for (let v = 0; v < PER; v++) {
        const a = b[k][v], z = back[k][v];
        if (!a) { expect(z).toBeNull(); continue; }
        expect(z!.name).toBe(a.name);
        for (const f of ['hue', 'light', 'sat', 'tone', 'vignette', 'effect', 'art_effect', 'grain', 'lens_correction', 'film_grain'] as const) expect(z![f]).toEqual(a[f]);
        expect(z!.advice).toEqual(a.advice);
        expect(z!.wb && (z!.wb.a_b || z!.wb.g_m) ? z!.wb : null).toEqual(a.wb && (a.wb.a_b || a.wb.g_m) ? a.wb : null);
      }
    }
  });

  it('LOOKS.BIN for firmware v0.21 puts Sharp in the stock Sharpness byte', () => {
    const b = randomBank(6), f21 = profilesBin(b, 21), f22 = profilesBin(b);
    let soft = 0;
    b.forEach((row, k) => row.forEach((l, v) => {
      const o = 32 + 64 * (5 * k + v), s = l?.advice.sharpness ?? 0, i8 = (x: number) => (x << 24) >> 24;
      expect(f21[o + 52]).toBe(0); expect(i8(f21[o + 42])).toBe(Math.max(-2, Math.min(2, s)));
      expect(f22[o + 42]).toBe(0); expect(i8(f22[o + 52])).toBe(s);
      if (s < -2) soft++;
    }));
    expect(soft).toBeGreaterThan(0);
    const back = readProfiles(f21);
    expect(back.flat().map((l) => l?.advice.sharpness)).toEqual(b.flat().map((l) => (l ? Math.max(-2, l.advice.sharpness ?? 0) : undefined)));
  });

  it('Sharp: -5..+2, a v0.21 card file reads as before', () => {
    const l = blankLook('colour', 'S'); l.advice = { sharpness: -5 }; expect(validateProfile(l)).toEqual([]);
    l.advice.sharpness = 3; expect(validateProfile(l).map((p) => p.field)).toEqual(['sharpness']);
    l.advice.sharpness = -6; expect(validateProfile(l).map((p) => p.field)).toEqual(['sharpness']);
    const t = blankLook('colour', 'T'); t.advice = { sharpness: -9 }; expect(toOm3(t).look!.advice.sharpness).toBe(-5);
  });

  it('LOOKS.BIN for firmware v0.20 leaves VigFix out', () => {
    const b = randomBank(4), old = profilesBin(b, 20), cur = profilesBin(b);
    for (let r = 0; r < 20; r++) { expect(old[32 + 64 * r + 50]).toBe(0); expect(old[32 + 64 * r + 51]).toBe(0); }
    expect(b.flat().some((l) => l && !l.lens_correction)).toBe(true);
    expect([...cur].some((x, i) => i >= 32 && i < 1312 && (i - 32) % 64 === 50 && x === 1)).toBe(true);
  });

  it('bank files parse back', () => {
    const b = defaultBank(LIB, fromLibrary);
    const f = parseBank(JSON.parse(JSON.stringify({ schema: 'caduceus-om3-bank/1', name: 'x', bank: b })), parseLook);
    expect(hex(profilesBin(f.bank))).toBe(hex(profilesBin(b)));
    const r = randomBank(5), g = parseBank(JSON.parse(JSON.stringify({ schema: 'caduceus-om3-bank/1', name: 'x', bank: r })), parseLook);
    expect(hex(profilesBin(g.bank))).toBe(hex(profilesBin(r)));          // VigFix and Grain survive a looks file
  });

  it('v0.25: only Grain with Glow / Clarity and Frame together is the slow kind', () => {
    const l = blankLook('colour', 'G'); expect(slowGrain(l)).toBe(false);
    l.film_grain = 2; expect(slowGrain(l)).toBe(false);
    l.art_effect = 'frame'; expect(slowGrain(l)).toBe(false);
    l.effect = { type: 'clarity', strength: 1 }; expect(slowGrain(l)).toBe(false);   // v0.25: no Art Effect, never slow
    l.art_effect = 'off'; expect(slowGrain(l)).toBe(false);
    l.art_effect = 'frame'; delete l.film_grain; expect(slowGrain(l)).toBe(false);
  });

  it('v0.25 export: Shading kept, Art Effect always Off', () => {
    const l = blankLook('colour', 'F'); l.vignette = -2; l.film_grain = 3; l.art_effect = 'pin_hole';
    const b25 = readProfiles(profilesBin([[l]], 24))[0][0]!, b24 = readProfiles(profilesBin([[l]], 23))[0][0]!;
    expect(b25.vignette).toBe(-2); expect(b25.art_effect).toBe('off');
    expect(b24.vignette).toBe(0); expect(b24.art_effect).toBe('pin_hole');
    l.art_effect = 'frame'; expect(readProfiles(profilesBin([[l]], 24))[0][0]!.art_effect).toBe('off');   // owner: Frame removed
  });

  it('v0.24.1: Shading is saved as 0 (with grain it turns the photo mono); older firmware keeps it', () => {
    const l = blankLook('colour', 'S'); l.vignette = -3; l.film_grain = 1;
    expect(monoGrain(l)).toBe(true);
    expect(readProfiles(profilesBin([[l]], 23))[0][0]!.vignette).toBe(0);
    expect(readProfiles(profilesBin([[l]], 22))[0][0]!.vignette).toBe(-3);
    l.film_grain = 0; expect(monoGrain(l)).toBe(false);
  });

  it('v0.24.1: Shading is saved as 0 (with grain it turns the photo mono); older firmware keeps it', () => {
    const l = blankLook('colour', 'S'); l.vignette = -3; l.film_grain = 1;
    expect(monoGrain(l)).toBe(true);
    expect(readProfiles(profilesBin([[l]], 23))[0][0]!.vignette).toBe(0);
    expect(readProfiles(profilesBin([[l]], 22))[0][0]!.vignette).toBe(-3);
    l.film_grain = 0; expect(monoGrain(l)).toBe(false);
  });

  it.skipIf(!existsSync(MK))('PROFILES.BIN is byte-identical to card/mkprofiles.py', () => {
    const dir = mkdtempSync(join(tmpdir(), 'om3-'));
    for (const [i, b] of [defaultBank(LIB, fromLibrary), randomBank(7), randomBank(8), emptyBank()].entries()) {
      writeFileSync(join(dir, `in${i}.json`), JSON.stringify(pyJson(b)));
      execFileSync('python3', ['-I', MK, join(dir, `in${i}.json`), join(dir, `out${i}.bin`)]);
      expect(hex(profilesBin(b))).toBe(hex(new Uint8Array(readFileSync(join(dir, `out${i}.bin`)))));
    }
  });

  it('film sims: every one is a valid OM-3 look with a unique camera name', () => {
    expect(FILMS.length).toBeGreaterThan(40);
    const names = new Set<string>();
    for (const f of FILMS) {
      expect(FILM_GROUPS.map(([g]) => g)).toContain(f.group);
      expect(f.desc.length).toBeGreaterThan(20);
      const l = filmLook(f);
      expect(validateProfile(l)).toEqual([]);
      expect(names.has(f.name.toLowerCase())).toBe(false); names.add(f.name.toLowerCase());
      const back = readProfiles(profilesBin([[l]]))[0][0]!;
      expect(back.hue).toEqual(l.hue); expect(back.tone).toEqual(l.tone); expect(back.advice.contrast).toBe(f.contrast);
      expect(back.advice.sharpness).toBe(f.sharp); expect(f.sharp).toBeGreaterThan(-5);   // v0.22 Sharp, never Off
      expect(l.effect).toBeNull(); expect(l.art_effect).toBe('off'); expect(l.film_grain).toBeUndefined();
    }
    expect(new Set(FILMS.map((f) => f.film)).size).toBe(FILMS.length);   // one look per film
    expect(filmByName('Portra 400 PV')?.name).toBe('Portra 400');        // older names map to their film
    expect(filmByName('Polaroid 690')?.name).toBe('Polaroid 600');
    expect(filmLook(filmByName('Polaroid 600')!).advice.sharpness).toBe(-3);
    expect(filmLook(filmByName('Velvia 50')!).advice.sharpness).toBe(1);
  });
});

export type { Look };

describe('split toning (v0.26)', () => {
  it('writes and reads record +53..+56 only for v0.26 exports', async () => {
    const { profilesBin, readProfiles, emptyBank, blankProfile } = await import('../src/om3');
    const b = emptyBank(); const l = blankProfile('Tone test'); l.split = { sh_color: 8, sh: 3, hl_color: 1, hl: 2 }; b[0][0] = l;
    const f25 = profilesBin(b, 25), f24 = profilesBin(b, 24);
    expect([...f25.subarray(32 + 53, 32 + 57)]).toEqual([8, 3, 1, 2]);
    expect([...f24.subarray(32 + 53, 32 + 57)]).toEqual([0, 0, 0, 0]);
    expect(readProfiles(f25)[0][0]!.split).toEqual({ sh_color: 8, sh: 3, hl_color: 1, hl: 2 });
    expect(readProfiles(f24)[0][0]!.split).toBeUndefined();
  });
  /* SKIP-HERE */ it.skip('a v0.26 minus (the opposite colour) reads as the opposite colour of the wheel', async () => {
    const { profilesBin, readProfiles, emptyBank, blankProfile } = await import('../src/om3');
    const b = emptyBank(); const l = blankProfile('Old tone'); l.split = { sh_color: 8, sh: 3, hl_color: 1, hl: 2 }; b[0][0] = l;
    const f = profilesBin(b, 26); f[32 + 56] = 254;                       // hl -2, as a v0.26 Control Panel wrote it
    const { crc32 } = await import('../src/format'); new DataView(f.buffer).setUint32(8, crc32(f.subarray(12)), true);
    expect(readProfiles(f)[0][0]!.split).toEqual({ sh_color: 8, sh: 3, hl_color: 7, hl: 2 });
    expect(parseLook({ ...l, split: { sh_color: 2, sh: -1, hl_color: 0, hl: 0 } }).split).toEqual({ sh_color: 8, sh: 1, hl_color: 0, hl: 0 });
  });
  it('the preview bend matches the firmware model at the curve ends', async () => {
    const { bendSplit } = await import('../src/split');
    const img = new Float32Array([0, 0, 0, 1, 1, 1, 0.3, 0.3, 0.3]);
    bendSplit(img, 3, { sh_color: 8, sh: 5, hl_color: 1, hl: 5 });
    expect([...img.subarray(0, 6)].map((x) => Math.round(x * 1000))).toEqual([0, 0, 0, 1000, 1000, 1000]);
    expect(img[6]).toBeLessThan(img[7]);   // cyan shadows: red down, green up
  });
});

describe('WB -7..7 (v0.26.1)', () => {
  it('saves ±7 only for v0.26.1; older firmware gets ±5 (it refuses the file beyond)', async () => {
    const { profilesBin, emptyBank, blankProfile } = await import('../src/om3');
    const b = emptyBank(); const l = blankProfile('WB test'); l.wb = { a_b: 7, g_m: -6 }; b[0][0] = l;
    expect([...profilesBin(b, 26).subarray(32 + 37, 32 + 39)]).toEqual([7, 250]);
    expect([...profilesBin(b, 25).subarray(32 + 37, 32 + 39)]).toEqual([5, 251]);
  });
});

describe('look format version and minimum firmware (2026-11-09)', () => {
  const base = (): Look => blankLook('colour', 'Test');
  it('works out the minimum firmware from the settings', () => {
    expect(FW_NAME[minFw(base())]).toBe('0.20');
    expect(FW_NAME[minFw({ ...base(), film_grain: 1 })]).toBe('0.21');
    expect(FW_NAME[minFw({ ...base(), lens_correction: true })]).toBe('0.21');
    expect(FW_NAME[minFw({ ...base(), advice: { sharpness: -4 } })]).toBe('0.22');
    expect(FW_NAME[minFw({ ...base(), grain: 'high' })]).toBe('0.24.1');
    expect(FW_NAME[minFw({ ...base(), split: { sh_color: 6, sh: 2, hl_color: 0, hl: 0 } })]).toBe('0.26');
    expect(FW_NAME[minFw({ ...base(), wb: { a_b: 6, g_m: 0 } })]).toBe('0.26.1');
    expect(FW_NAME[minFw({ ...base(), wb: { a_b: -5, g_m: 5 }, film_grain: 2 })]).toBe('0.21');
    expect(FW_NAME[bankMinFw([[base(), null], [{ ...base(), wb: { a_b: 0, g_m: -7 } }]])]).toBe('0.26.1');
  });
  it('exports schema and min_fw first, and reads them back', () => {
    const l = { ...base(), split: { sh_color: 6, sh: 2, hl_color: 0, hl: 0 } }, x = exportLook(l);
    expect(Object.keys(x).slice(0, 2)).toEqual(['schema', 'min_fw']);
    expect(x.schema).toBe(LOOK_SCHEMA); expect(x.min_fw).toBe('0.26');
    const back = parseLook(JSON.parse(JSON.stringify(x)));
    expect(back).toEqual(parseLook(JSON.parse(JSON.stringify(l))));
    expect(back).not.toHaveProperty('min_fw');
  });
  /* SKIP-HERE */ it.skip('ignores a wrong min_fw, reads old looks without the fields, refuses newer and unknown formats', () => {
    const l = { ...base(), wb: { a_b: 7, g_m: 0 } };
    expect(FW_NAME[minFw(parseLook({ ...exportLook(l), min_fw: '0.20' }))]).toBe('0.26.1');
    expect(() => parseLook(JSON.parse(JSON.stringify(l)))).not.toThrow();
    expect(() => parseLook({ ...exportLook(l), schema: 'caduceus-om3-look/2' })).toThrow(/newer version/);
    expect(() => parseLook({ ...exportLook(l), schema: 'something-else' })).toThrow(/unknown format/);
  });
});

describe('Cuban Negative replaces the starter look Cuban Neg (owner, 2026-11-11)', () => {
  it('a look taken from the old starter look resets to the film', async () => {
    const { filmOf } = await import('../src/om3films');
    const { blankLook } = await import('../src/pack');
    const l = blankLook('colour', 'Cuban Neg'); l.origin = 'Cuban Neg';
    expect(filmOf(l)?.name).toBe('Cuban Negative');
  });
});

describe('v0.28: Halation, Tone Balance, film WB, half steps, Blacks / Whites ±7', () => {
  const v28 = (): Look => ({ ...blankLook('colour', 'v28 test'), halation: 4, tone_balance: -3, film_wb: { mode: 'custom', kelvin: 3200 },
    split: { sh_color: 8, sh: 1.5, hl_color: 1, hl: 5 }, tone: { highlights: 0, shadows: 0, midtones: 0, blacks: -7, whites: 6 } });
  it('the split code: 0..10 half steps <-> -5..5 (firmware strength()), both ways', async () => {
    const { splitCode, splitFromCode } = await import('../src/split');
    const codes = Array.from({ length: 11 }, (_, n) => splitCode(n / 2));
    expect(codes).toEqual([0, -1, 1, -2, 2, -3, 3, -4, 4, -5, 5]);
    expect(codes.map(splitFromCode)).toEqual(Array.from({ length: 11 }, (_, n) => n / 2));
  });
  it('writes record +39 / +40 and +54..+62 for v0.28 and reads them back', async () => {
    const { profilesBin, readProfiles, emptyBank } = await import('../src/om3');
    const b = emptyBank(); b[0][0] = v28();
    const f = profilesBin(b, 28), r = f.subarray(32, 96), s8 = (i: number) => (r[i] << 24) >> 24;
    expect([s8(39), s8(40)]).toEqual([-7, 6]);
    expect([r[53], s8(54), r[55], s8(56)]).toEqual([8, -2, 1, 5]);            // 3 half steps -> -2, 10 -> 5
    expect([s8(57), s8(58)]).toEqual([4, -3]);
    expect([s8(59), s8(60), s8(61), s8(62)]).toEqual([-4, -4, 1, 1]);        // (3200 - 2000) / 100 - 60 = -48 = -4 + 11 (-4); Custom = 12 = 1 + 11
    for (let i = 39; i < 63; i++) if (i !== 52) expect(Math.abs(s8(i))).toBeLessThanOrEqual(i === 53 || i === 55 ? 11 : 7);
    const back = readProfiles(f)[0][0]!;
    expect(back.halation).toBe(4); expect(back.tone_balance).toBe(-3); expect(back.film_wb).toEqual({ mode: 'custom', kelvin: 3200 });
    expect(back.split).toEqual({ sh_color: 8, sh: 1.5, hl_color: 1, hl: 5 }); expect([back.tone.blacks, back.tone.whites]).toEqual([-7, 6]);
  });
  it('older exports leave v0.28 out: +57..+62 zero, Blacks / Whites ±5, whole steps', async () => {
    const { profilesBin, emptyBank } = await import('../src/om3');
    const b = emptyBank(); b[0][0] = v28();
    const r = profilesBin(b, 26).subarray(32, 96), s8 = (i: number) => (r[i] << 24) >> 24;
    expect([s8(39), s8(40)]).toEqual([-5, 5]);
    expect([s8(54), s8(56)]).toEqual([2, 5]);
    expect([...r.subarray(57, 63)]).toEqual([0, 0, 0, 0, 0, 0]);
  });
  it('every WB mode round-trips (index in the camera table 0x615d1944)', async () => {
    const { profilesBin, readProfiles, emptyBank, filmWbBytes } = await import('../src/om3');
    const { WB_MODES } = await import('../src/pack');
    WB_MODES.forEach((m, i) => {
      const l = blankLook('colour', 'wb'); if (m !== 'auto') l.film_wb = m === 'custom' ? { mode: m, kelvin: 14000 } : { mode: m };
      const [, , lo, hi] = filmWbBytes(l); expect(lo + 11 * hi).toBe(i);
      const b = emptyBank(); b[0][0] = l;
      expect(readProfiles(profilesBin(b, 28))[0][0]!.film_wb).toEqual(l.film_wb);
    });
    expect(filmWbBytes({ ...blankLook('colour', 'k'), film_wb: { mode: 'custom', kelvin: 2000 } }).slice(0, 2)).toEqual([-5, -5]);
  });
  it('needs v0.28; a whole-step split tone still needs only v0.26', () => {
    expect(FW_NAME[minFw(v28())]).toBe('0.28');
    expect(FW_NAME[minFw({ ...blankLook('colour', 'x'), halation: 1 })]).toBe('0.28');
    expect(FW_NAME[minFw({ ...blankLook('colour', 'x'), split: { sh_color: 0, sh: 2, hl_color: 0, hl: 0 } })]).toBe('0.26');
    expect(FW_NAME[minFw({ ...blankLook('colour', 'x'), split: { sh_color: 0, sh: 2.5, hl_color: 0, hl: 0 } })]).toBe('0.28');
    expect(validateProfile(v28())).toEqual([]);
  });
  /* SKIP-HERE */ it.skip('looks files keep the new fields', () => {
    const l = v28(), back = parseLook(JSON.parse(JSON.stringify(exportLook(l))));
    expect(back.halation).toBe(4); expect(back.tone_balance).toBe(-3); expect(back.film_wb).toEqual({ mode: 'custom', kelvin: 3200 });
    expect(back.split).toEqual(l.split);
    expect(parseLook({ ...exportLook(l), film_wb: { mode: 'custom', kelvin: 3249 } }).film_wb).toEqual({ mode: 'custom', kelvin: 3200 });
    expect(parseLook({ ...exportLook(l), film_wb: { mode: 'auto' } }).film_wb).toBeUndefined();
  });
});
