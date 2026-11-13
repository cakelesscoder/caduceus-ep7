// From androidfanman/caduceus-om3 @ 87b3e6f (Apache-2.0, see NOTICE), unchanged.
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
import { validateProfile } from '../src/om3';

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
      ['Portra 400', 'Gold 200', 'Kodachrome 64', 'Portra 800', 'CineStill 800T'],
      ['Ektar 100', 'Ultramax 400', 'Pro 400H', 'Velvia 50', 'Superia 400'],
      ['ColorPlus 200', 'CineStill 400D', 'Fuji C200', 'Ektachrome E100', 'Reala 100'],
      ['Provia 100F', 'Vision3 250D', 'Fuji Eterna', 'Astia 100F', 'Agfa Ultra 100'],
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
    const b = emptyBank(); const l = blankProfile('Tone test'); l.split = { sh_color: 8, sh: 3, hl_color: 1, hl: -2 }; b[0][0] = l;
    const f25 = profilesBin(b, 25), f24 = profilesBin(b, 24);
    expect([...f25.subarray(32 + 53, 32 + 57)]).toEqual([8, 3, 1, 254]);
    expect([...f24.subarray(32 + 53, 32 + 57)]).toEqual([0, 0, 0, 0]);
    expect(readProfiles(f25)[0][0]!.split).toEqual({ sh_color: 8, sh: 3, hl_color: 1, hl: -2 });
    expect(readProfiles(f24)[0][0]!.split).toBeUndefined();
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
