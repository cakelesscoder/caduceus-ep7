// Vendored from androidfanman/caduceus-om3 @ c209b69 (Apache-2.0, see NOTICE), unchanged. Update by copying; our glue is in ./targets/om3.ts.
import { parseSplit, splitCode, splitFromCode, splitOk, toSteps } from './split';
// OM SYSTEM OM-3 with Caduceus for OM-3 (androidfanman/caduceus-om3): the profile bank and its card files.
// The camera has 5 looks for each of COLOR 1-4 (its Film page, dial 0-5). A look holds the wheels (Saturation, Hue,
// Light), the tone (Shadows / Midtones / Highlights on the camera's own tone settings, Blacks / Whites on the Extras
// page), the camera's Contrast, Sharpness and Shading and, from v0.20, the Extras page: NR (the camera's stills Noise
// Filter: Camera / Std / Low / Off), Glow (-5..-1) / Clarity (1..5), WB A-B / G-M and an Art Effect (Star Light, Pin
// Hole, White Edge, Frame), and from v0.21 VigFix (the lens vignette correction off for the look, as Caduceus v0.25:
// off unless the look keeps it, `lens_correction`) and Grain (`film_grain` 1..3, the camera's own grain), and from v0.22
// Sharp (`advice.sharpness`, -5..+2 in the camera's own numbers: 0 its normal, -5 Off; v0.22 takes the stock Sharpness
// row off the COLOR screen). Colour only: no glow colour (tint) and no monochrome looks.
//
// Card files (C:\OM3MOD\, little-endian):
//   PROFILES.BIN v1, 1632 B: 'OM3P' | 1632 | crc32(12..) | u16 1 | u16 20 | sel[4] | 12 zero | 20 x 64-B records
//     (COLOR k profile v at 5k + v - 1: hue[12] +0, light[12] +12, sat[12] +24, +36 WB on, +37 A-B, +38 G-M,
//     +39 Blacks, +40 Whites, +41 Contrast, +42 Sharpness, +43 Shading, +44 Shadows, +45 Midtones, +46 Highlights,
//     v0.20: +47 Glow (-5..-1) / Clarity (1..5), +48 Art Effect (0 Off, 1 Star Light, 2 Pin Hole, 4 White Edge, 5 Frame:
//     the Caduceus ids), +49 NR (0 Camera, 1 Std, 2 Low, 3 Off); zero before v0.20, so older files read as before),
//     v0.21: +50 VigFix (0 Camera: keep the lens vignette correction, 1 Off), +51 Grain (0 Off, 1 Low, 2 Med, 3 High);
//     v0.20 and older reject a file with either non-zero, so the v0.20 export leaves both at 0;
//     v0.22: +52 Sharp (-5..+2, -5 Off) with +42 left at 0; v0.21 and older reject a non-zero +52, so their export puts
//     the look's sharpness in +42 (-2..+2, softer values as -2)
//     v0.26: +53..+56 split toning (Shadows colour, strength, Highlights colour, strength; minus = the opposite colour),
//     v0.28: +54 / +56 a code for 0..10 half steps (splitCode), +39 / +40 Blacks / Whites -7..7, +57 Halation 0..5,
//     +58 Tone Balance -5..5, +59..+62 film WB (balanced base-11 pairs: Custom WB Kelvin, mode index); firmware before
//     v0.28 refuses a file with +57..+62 set or Blacks / Whites past 5, so the older exports leave them out
//     | 20 x 16-B names at 1312. Written with sel = 0 so the camera never saves its own settings over these profiles.
//   NAMES.BIN v1: the name pictures for the Film page (./om3names.ts).
import { ARTS, KELVIN, LOOK_SCHEMA, WB_MODES, blankLook, cloneLook, parseFilmWb, toneIsZero, zeroTone, type Grain, type Look, type Pack } from './pack';
import { crc32, type Problem } from './format';
import { CAMERA_FILMS, filmByName, filmLook } from './om3films';

export const COLORS = 4, PER = 5;
export const OM3 = { hl: 5, sat: 5, wb: 7, contrast: 2, sharpness: 2, shading: 5, hsm: 7, bw: 7, fx: 5, grain: 3, halation: 5, balance: 5 } as const;
/** v0.22 Sharp (Extras sector 10): the camera's own numbers, 0 = its normal; -3..-4 softer than its menu goes, -5 = Off. */
export const SHARP = { lo: -5, hi: 2 } as const;
export const sharpLabel = (v: number) => (v <= SHARP.lo ? 'Off' : v > 0 ? `+${v}` : String(v));
/** Firmware the LOOKS.BIN is for: 24 = v0.25 and later (fast colour grain with everything; Art Effect = Frame only),
 * 23 = v0.24.1 (NR High; Shading saved as 0: the row is hidden there), 22 = v0.22 (Sharp), 21 (Grain, VigFix),
 * 20 = v0.20 and older / PROFILES.BIN. */
export type Fw = 20 | 21 | 22 | 23 | 24 | 25 | 26 | 28;   // 25 = v0.26 (split toning, record +53..+56); 26 = v0.26.1 (WB -7..7); 28 = v0.28 (+57..+62, half steps, Blacks / Whites -7..7)
/** WB shift that firmware `fw` accepts in LOOKS.BIN: v0.26 and older refuse the whole file beyond -5..5. */
export const wbMax = (fw: Fw) => (fw >= 26 ? 7 : 5);
/** Blacks / Whites that firmware `fw` accepts in LOOKS.BIN: before v0.28 it refuses the whole file beyond -5..5. */
export const bwMax = (fw: Fw) => (fw >= 28 ? 7 : 5);
/** Caduceus release names of the Fw values (the export menu's). */
export const FW_NAME: Record<Fw, string> = { 20: '0.20', 21: '0.21', 22: '0.22', 23: '0.24.1', 24: '0.25', 25: '0.26', 26: '0.26.1', 28: '0.28' };
/** What in this look needs v0.28 (Halation, Tone Balance, film WB, Blacks / Whites past ±5, a half step of split toning). */
export function v28Parts(l: Look): string[] {
  const p: string[] = [];
  if (l.halation) p.push('Halation');
  if (l.split && (toSteps(l.split.sh) % 2 || toSteps(l.split.hl) % 2)) p.push('split toning in half steps');
  if (l.tone_balance) p.push('Tone Balance');
  if (l.film_wb) p.push('WB mode');
  if (Math.abs(l.tone.blacks) > 5 || Math.abs(l.tone.whites) > 5) p.push('Blacks / Whites past ±5');
  return p;
}
/** The oldest firmware that carries everything in this look (worked out from its settings, never read from a file):
 *  Halation, Tone Balance, film WB, Blacks / Whites past ±5 or a half step of split toning v0.28, WB shift past ±5
 *  v0.26.1, split toning v0.26, Noise Filter High v0.24.1, Sharp below -2 v0.22, Film Grain or the lens vignette
 *  correction off v0.21; anything else v0.20. */
export function minFw(l: Look): Fw {
  if (v28Parts(l).length) return 28;
  if (Math.abs(l.wb?.a_b ?? 0) > 5 || Math.abs(l.wb?.g_m ?? 0) > 5) return 26;
  if (l.split) return 25;
  if (OM3_NR.indexOf(l.grain) === 4) return 23;
  if ((l.advice.sharpness ?? 0) < -2) return 22;
  if ((l.film_grain ?? 0) > 0 || l.lens_correction) return 21;
  return 20;
}
/** The newest of the looks' minFw (20 for none). */
export const bankMinFw = (bank: Bank): Fw => bank.flat().reduce<Fw>((m, l) => (l ? Math.max(m, minFw(l)) as Fw : m), 20);
/** A look as it leaves the tool (share links, the .om3.json file): its format version and minimum firmware first, then
 *  the settings, without the app's own bookkeeping. */
export function exportLook(l: Look): Record<string, unknown> {
  const { origin: _o, lib: _l, ...x } = l as Look & { origin?: unknown; lib?: unknown };
  return { schema: LOOK_SCHEMA, min_fw: FW_NAME[minFw(l)], ...x };
}
/** v0.25: Grain is as fast as normal with every setting, except Glow / Clarity and Frame together (the slower route,
 * about 3 s per photo). */
export const slowGrain = (_l: Look) => false;   // v0.25: no Art Effect (Frame removed), so grain is fast with everything
/** v0.24.1 only: Shading with grain turned the photo black and white (so that version hides Shading). */
export const monoGrain = (l: Look) => !!l.film_grain && !!l.vignette;
/** v0.25 shows Frame as its only Art Effect (Star Light, Pin Hole and White Edge are ignored there). */
export const v25Art = (_l: Look) => 'off';      // v0.25 (owner): no Art Effect at all; Frame caused too many issues
/** v0.20 Extras: NR byte <-> the Caduceus look's noise reduction (grain field), Art Effects the OM-3 renders. */
export const OM3_NR: Grain[] = ['off', 'standard', 'fine', 'film', 'high'];  // 0 Camera, 1 Std, 2 Low, 3 Off, 4 High (v0.23)
export const OM3_ARTS = ['off', 'star_light', 'pin_hole', 'white_edge', 'frame'] as const;
export type Bank = (Look | null)[][];          // [COLOR 0..3][profile 0..4]
export interface BankFile { schema: 'caduceus-om3-bank/1'; name: string; bank: Bank }
export const BANK_SCHEMA = 'caduceus-om3-bank/1';
/** The camera keeps 15 characters per profile name (Caduceus looks: 12). */
export const OM3_NAME_MAX = 15;
export function om3NameProblem(name: string): string | null {
  if (name.length === 0) return 'Name is empty.';
  if (name !== name.trim()) return 'No spaces at the start or end of the name.';
  if (name.length > OM3_NAME_MAX) return `At most ${OM3_NAME_MAX} characters (${name.length}).`;
  if (!/^[\x20-\x7e]+$/.test(name)) return 'Plain ASCII letters, digits, spaces and punctuation only.';
  return null;
}

export const emptyBank = (): Bank => Array.from({ length: COLORS }, () => new Array<Look | null>(PER).fill(null));
const clampI = (v: unknown, n: number) => Math.max(-n, Math.min(n, Math.round(Number(v) || 0)));

/** A look as an OM-3 profile, and what had to change. Mono looks cannot be OM-3 profiles (null). */
export function toOm3(src: Look): { look: Look | null; changed: string[]; dropped: string[] } {
  if (src.kind === 'mono') return { look: null, changed: [], dropped: ['monochrome'] };
  const l = cloneLook(src), changed: string[] = [], dropped: string[] = [];
  const lim = (a: number[]) => a.map((v) => clampI(v, OM3.hl));
  if (l.hue.some((v) => Math.abs(v) > OM3.hl) || l.light.some((v) => Math.abs(v) > OM3.hl)) changed.push('Hue/Light');
  l.hue = lim(l.hue); l.light = lim(l.light); l.sat = l.sat.map((v) => clampI(v, OM3.sat));
  if (l.wb) {
    if (Math.abs(l.wb.a_b) > OM3.wb || Math.abs(l.wb.g_m) > OM3.wb) changed.push('WB');
    l.wb = { a_b: clampI(l.wb.a_b, OM3.wb), g_m: clampI(l.wb.g_m, OM3.wb) };
  }
  if (l.effect) {                                   // v0.20: glow (bloom) and clarity, 1..5, no colour
    if (l.effect.type === 'halation') { l.effect = { type: 'bloom', strength: l.effect.strength }; changed.push('halation as glow'); }
    else if (l.effect.tint && l.effect.tint !== 'neutral') { changed.push('glow colour'); }
    if (l.effect.tint !== undefined) delete l.effect.tint;
    l.effect.strength = Math.max(1, Math.min(OM3.fx, Math.round(l.effect.strength)));
  }
  if (l.art_effect === 'blur') { dropped.push('Blur'); l.art_effect = 'off'; }
  if (toneIsZero(l.tone) && l.advice.tone) {        // older looks: the recipe's tone advice becomes the profile's tone
    l.tone = { ...l.tone, highlights: l.advice.tone.highlights, shadows: l.advice.tone.shadows, midtones: l.advice.tone.midtones };
  }
  l.tone = { highlights: clampI(l.tone.highlights, OM3.hsm), shadows: clampI(l.tone.shadows, OM3.hsm), midtones: clampI(l.tone.midtones, OM3.hsm),
    blacks: clampI(l.tone.blacks, OM3.bw), whites: clampI(l.tone.whites, OM3.bw) };
  l.vignette = clampI(l.vignette, OM3.shading);
  const adv = l.advice;
  l.advice = { ...(adv.contrast !== undefined ? { contrast: clampI(adv.contrast, OM3.contrast) } : {}),
    ...(adv.sharpness !== undefined ? { sharpness: Math.max(SHARP.lo, Math.min(SHARP.hi, Math.round(adv.sharpness) || 0)) } : {}) };
  return { look: l, changed, dropped };
}

export const blankProfile = (name: string): Look => blankLook('colour', name);

/** The camera's checks, as problems for people. */
export function validateProfile(l: Look, at?: { k: number; v: number }): Problem[] {
  const p: Problem[] = [], add = (field: string, message: string) => p.push({ look: at ? at.k * PER + at.v : undefined, field, message });
  const np = om3NameProblem(l.name); if (np) add('name', np);
  if (l.kind !== 'colour') add('kind', 'OM-3 looks are colour only.');
  const ok = (v: unknown, n: number) => Number.isInteger(v) && Math.abs(v as number) <= n;
  for (const [k, n] of [['hue', OM3.hl], ['light', OM3.hl], ['sat', OM3.sat]] as const)
    if (!l[k].every((v) => ok(v, n))) add(k, `${k}: 12 whole numbers in -${n}..${n} (the OM-3 wheel).`);
  if (l.wb && !(ok(l.wb.a_b, OM3.wb) && ok(l.wb.g_m, OM3.wb))) add('wb', `WB shift: A-B and G-M in -${OM3.wb}..${OM3.wb}.`);
  for (const k of ['highlights', 'shadows', 'midtones'] as const) if (!ok(l.tone[k], OM3.hsm)) add('tone', `${k}: -7..7.`);
  for (const k of ['blacks', 'whites'] as const) if (!ok(l.tone[k], OM3.bw)) add('tone', `${k}: -7..7.`);
  if (!ok(l.advice.contrast ?? 0, OM3.contrast)) add('contrast', 'Contrast: -2..2.');
  const sh = l.advice.sharpness ?? 0;
  if (!(Number.isInteger(sh) && sh >= SHARP.lo && sh <= SHARP.hi)) add('sharpness', 'Sharp: Off (-5) to +2.');
  if (!ok(l.vignette, OM3.shading)) add('shading', 'Shading: -5..5.');
  if (l.effect && !(Number.isInteger(l.effect.strength) && l.effect.strength >= 1 && l.effect.strength <= OM3.fx && (l.effect.type === 'bloom' || l.effect.type === 'clarity')))
    add('effect', 'Glow / Clarity: strength 1..5.');
  if (!(OM3_ARTS as readonly string[]).includes(l.art_effect)) add('art_effect', 'Art Effect: Off, Star Light, Pin Hole, White Edge or Frame.');
  if (!OM3_NR.includes(l.grain)) add('grain', 'NR: Camera, Off, Low, Std or High.');
  if (l.film_grain !== undefined && !(Number.isInteger(l.film_grain) && l.film_grain >= 0 && l.film_grain <= OM3.grain)) add('film_grain', 'Grain: Off, Low, Med or High.');
  if (l.split && !splitOk(l.split)) add('split', 'Split toning: a colour of the wheel and a strength 0..10.');
  if (l.tone_balance !== undefined && !ok(l.tone_balance, OM3.balance)) add('tone_balance', 'Tone Balance: -5..5.');
  if (l.halation !== undefined && !(Number.isInteger(l.halation) && l.halation >= 0 && l.halation <= OM3.halation)) add('halation', 'Halation: 0..5.');
  if (l.film_wb && !parseFilmWb(l.film_wb)) add('film_wb', 'WB mode: one of the camera\'s modes; Custom WB 2000..14000 K.');
  return p;
}
export function validateBank(bank: Bank): Problem[] {
  const p: Problem[] = [];
  bank.forEach((row, k) => row.forEach((l, v) => { if (l) p.push(...validateProfile(l, { k, v })); }));
  return p;
}

// ---- PROFILES.BIN
export const PF_LEN = 1632;
/** fw 20 (firmware v0.20 and older, PROFILES.BIN): +50 (the camera's correction) and +51 (no grain) left at 0 so they accept
 *  the file. fw 21: +52 left at 0, the sharpness in +42 (-2..+2). fw 22: Sharp in +52, +42 at 0. */
export function profilesBin(bank: Bank, fw: Fw = 22): Uint8Array {
  const b = new Uint8Array(PF_LEN), d = new DataView(b.buffer);
  b.set([0x4f, 0x4d, 0x33, 0x50]); d.setUint32(4, PF_LEN, true); d.setUint16(12, 1, true); d.setUint16(14, 20, true);
  bank.forEach((row, k) => row.forEach((l, j) => {
    if (!l) return;
    const r = 5 * k + j, o = 32 + 64 * r, s8 = (at: number, v: number) => d.setInt8(o + at, v);
    for (let i = 0; i < 12; i++) { s8(i, l.hue[i]); s8(12 + i, l.light[i]); s8(24 + i, l.sat[i]); }
    const wm = wbMax(fw), ab = Math.max(-wm, Math.min(wm, l.wb?.a_b ?? 0)), gm = Math.max(-wm, Math.min(wm, l.wb?.g_m ?? 0));
    b[o + 36] = l.wb && (ab || gm) ? 1 : 0; s8(37, ab); s8(38, gm);
    const bm = bwMax(fw); s8(39, Math.max(-bm, Math.min(bm, l.tone.blacks))); s8(40, Math.max(-bm, Math.min(bm, l.tone.whites)));
    const sharp = l.advice.sharpness ?? 0;
    s8(41, l.advice.contrast ?? 0); s8(42, fw >= 22 ? 0 : Math.max(-OM3.sharpness, Math.min(OM3.sharpness, sharp))); s8(43, fw === 23 ? 0 : l.vignette);   // v0.24.1 hides Shading (with grain it turned the photo mono)
    s8(44, l.tone.shadows); s8(45, l.tone.midtones); s8(46, l.tone.highlights);
    s8(47, !l.effect ? 0 : l.effect.type === 'clarity' ? l.effect.strength : -l.effect.strength);
    b[o + 48] = Math.max(0, (ARTS as readonly string[]).indexOf(fw >= 24 ? v25Art(l) : l.art_effect === 'blur' ? 'off' : l.art_effect));
    const nr = Math.max(0, OM3_NR.indexOf(l.grain));
    b[o + 49] = nr === 4 && fw < 23 ? 1 : nr;                                     // High needs v0.23: Standard before
    if (fw >= 21) { b[o + 50] = l.lens_correction ? 0 : 1; b[o + 51] = Math.max(0, Math.min(OM3.grain, l.film_grain ?? 0)); }
    if (fw >= 22) s8(52, Math.max(SHARP.lo, Math.min(SHARP.hi, sharp)));
    if (fw >= 25 && l.split && splitOk(l.split)) {   // v0.26 split toning; v0.28: half steps as a code, before: whole v0.26 steps
      const st = (v: number) => (fw >= 28 ? splitCode(v) : Math.round(v));
      b[o + 53] = l.split.sh_color; s8(54, st(l.split.sh)); b[o + 55] = l.split.hl_color; s8(56, st(l.split.hl));
    }
    if (fw >= 28) {                                   // v0.28: Halation, Tone Balance, film WB
      b[o + 57] = Math.max(0, Math.min(OM3.halation, l.halation ?? 0));
      s8(58, Math.max(-OM3.balance, Math.min(OM3.balance, l.tone_balance ?? 0)));
      const [kl, kh, ml, mh] = filmWbBytes(l);
      s8(59, kl); s8(60, kh); s8(61, ml); s8(62, mh);
    }
    const nm = l.name.replace(/[^\x20-\x7e]/g, '?').slice(0, 15);
    for (let i = 0; i < nm.length; i++) b[1312 + 16 * r + i] = nm.charCodeAt(i);
  }));
  d.setUint32(8, crc32(b.subarray(12)), true);
  return b;
}
/** Balanced base-11 (v = lo + 11 hi, both -5..5: every firmware's -5..5 range check passes; firmware FWENC). */
const b11 = (v: number): [number, number] => { const lo = ((((v + 5) % 11) + 11) % 11) - 5; return [lo, (v - lo) / 11]; };
/** v0.28 record +59..+62: Custom WB Kelvin v = (K - 2000) / 100 - 60 (Custom only, else 0), then the mode index. */
export function filmWbBytes(l: Look): [number, number, number, number] {
  const w = l.film_wb ? parseFilmWb(l.film_wb) : undefined;
  if (!w) return [0, 0, 0, 0];
  const kv = w.mode === 'custom' ? ((w.kelvin ?? KELVIN.dflt) - KELVIN.lo) / KELVIN.step - 60 : 0;
  return [...b11(kv), ...b11(WB_MODES.indexOf(w.mode))] as [number, number, number, number];
}
/** Record +57..+62 set: a v0.28 record (its split toning codes are half steps). */
export const isV28Record = (rec: Uint8Array) => rec.subarray(57, 63).some(Boolean);
/** A camera LOOKS.BIN -> bank. Used numbers without a name (made on the camera) become "Look n". `v28`: read the
 *  split toning codes as v0.28 half steps (also when any record has +57..+62 set); else as v0.26 steps. */
export function readProfiles(b: Uint8Array, v28 = false): Bank {
  const d = new DataView(b.buffer, b.byteOffset, b.byteLength);
  if (b.length !== PF_LEN || String.fromCharCode(...b.subarray(0, 4)) !== 'OM3P' || d.getUint32(4, true) !== PF_LEN) throw new Error('This is not a LOOKS.BIN (wrong size or header).');
  if (crc32(b.subarray(12)) !== d.getUint32(8, true)) throw new Error('This LOOKS.BIN is damaged (checksum).');
  if (d.getUint16(12, true) !== 1 || d.getUint16(14, true) !== 20) throw new Error('This LOOKS.BIN has an unknown version.');
  const bank = emptyBank();
  for (let r = 0; r < 20 && !v28; r++) v28 = isV28Record(b.subarray(32 + 64 * r, 96 + 64 * r));
  for (let r = 0; r < 20; r++) {
    const o = 32 + 64 * r;
    let name = ''; for (let i = 0; i < 15; i++) { const c = b[1312 + 16 * r + i]; if (!c) break; name += String.fromCharCode(c); }
    if (!name && !b.subarray(o, o + 57).some(Boolean)) continue;
    bank[Math.floor(r / 5)][r % 5] = lookFromRecord(b.subarray(o, o + 64), name || `Look ${(r % 5) + 1}`, v28);
  }
  return bank;
}
/** One 64-byte LOOKS.BIN record (+ its name) -> a look. `v28` (or +57..+62 set): split toning codes are v0.28's.
 *  `photo`: an om3.1 photo code's record: split toning in v0.26 steps with byte 63's half steps (bit 0 Shadows,
 *  bit 1 Highlights; firmware v0.28 pc1), never v0.28 codes. */
export function lookFromRecord(rec: Uint8Array, name: string, v28 = false, photo = false): Look {
  v28 = !photo && (v28 || isV28Record(rec));
  const d = new DataView(rec.buffer, rec.byteOffset, rec.byteLength), b = rec, o = 0;
  {
    const s = (i: number) => d.getInt8(o + i), a = (at: number) => Array.from({ length: 12 }, (_, i) => s(at + i));
    const l = blankLook('colour', name.slice(0, OM3_NAME_MAX).trim() || 'Look');
    l.hue = a(0); l.light = a(12); l.sat = a(24);
    l.wb = b[o + 36] & 1 ? { a_b: s(37), g_m: s(38) } : null;
    l.tone = { ...zeroTone(), blacks: s(39), whites: s(40), shadows: s(44), midtones: s(45), highlights: s(46) };
    l.advice = { contrast: s(41), sharpness: s(52) || s(42) }; l.vignette = s(43);      // v0.22 Sharp (+52), else the stock one
    const fx = s(47);
    l.effect = fx < 0 ? { type: 'bloom', strength: Math.min(OM3.fx, -fx) } : fx > 0 ? { type: 'clarity', strength: Math.min(OM3.fx, fx) } : null;
    const art = ARTS[b[o + 48]] ?? 'off';
    l.art_effect = art === 'blur' ? 'off' : art;
    l.grain = OM3_NR[b[o + 49]] ?? 'off';
    if (b[o + 50] === 0) l.lens_correction = true;
    if (b[o + 51] >= 1) l.film_grain = Math.min(OM3.grain, b[o + 51]);
    const st = (c: number) => (v28 ? splitFromCode(c) : c);
    const half = (bit: number, c: number) => (photo && c >= 0 && (b[o + 63] >> bit) & 1 ? 0.5 : 0);
    const sp = parseSplit({ sh_color: b[o + 53], sh: st(s(54)) + half(0, s(54)), hl_color: b[o + 55], hl: st(s(56)) + half(1, s(56)) });
    if (sp) l.split = sp;
    const hal = s(57), bal = s(58);                     // v0.28
    if (hal > 0) l.halation = Math.min(OM3.halation, hal);
    if (bal) l.tone_balance = Math.max(-OM3.balance, Math.min(OM3.balance, bal));
    const kv = s(59) + 11 * s(60), mi = s(61) + 11 * s(62);
    if (mi >= 1 && mi < WB_MODES.length) {
      const mode = WB_MODES[mi] as Exclude<(typeof WB_MODES)[number], 'auto'>;
      l.film_wb = mode === 'custom' ? { mode, kelvin: Math.max(KELVIN.lo, Math.min(KELVIN.hi, KELVIN.lo + KELVIN.step * (kv + 60))) } : { mode };
    }
    return l;
  }
}

/** v0.27: the code the camera writes into a JPEG's UserComment ("Caduceus FILM n Name om3.1.<43>"; firmware ex_cd1,
 *  reference firmware/photocode.py, spec docs/PHOTO_CODE.md): a 64-byte record, one nibble each, two to a byte,
 *  base64url. v0.28: the film as set when the photo was taken; bytes 57..62 Halation 0..5, Tone Balance, the WB
 *  (signed -5..5 pairs); split toning still in v0.26 steps, its half steps in byte 63 (unsigned). */
export const PHOTO_RE = /om3\.1\.([A-Za-z0-9_-]{43})(?![A-Za-z0-9_-])/;
const PHOTO_UNSIGNED = new Set([36, 48, 49, 50, 51, 53, 55, 57, 63]);
export function recordFromPhotoCode(code: string): Uint8Array {
  const m = PHOTO_RE.exec(code);
  if (!m) throw new Error('No om3.1. code found.');
  const bin = atob(m[1].replace(/-/g, '+').replace(/_/g, '/') + '=');
  const rec = new Uint8Array(64);
  for (let i = 0; i < 64; i++) {
    const byte = bin.charCodeAt(i >> 1), v = i & 1 ? byte & 15 : byte >> 4;
    rec[i] = PHOTO_UNSIGNED.has(i) || v < 8 ? v : (v - 16) & 255;
  }
  return rec;
}
/** A look from a photo's UserComment (or any text holding it): the name after "FILM n", else "From photo". */
export function lookFromPhotoCode(text: string): Look {
  const rec = recordFromPhotoCode(text);
  const nm = /FILM \d+ (.*?) om3\.1\./.exec(text)?.[1]?.trim();
  return lookFromRecord(rec, nm || 'From photo', false, true);
}
/** A look's recipe code, as the camera (v0.28) writes it into a photo: its v0.28 LOOKS.BIN record with split toning
 *  in v0.26 steps and the half steps in byte 63 (firmware ex_cd1). lookFromPhotoCode reads it back. */
export function photoCodeOf(l: Look): string {
  const bank = emptyBank(); bank[0][0] = l;
  const rec = profilesBin(bank, 28).slice(32, 96);
  let half = 0;
  for (const [at, bit] of [[54, 1], [56, 2]] as const) {
    const v = (rec[at] << 24) >> 24;
    if (v < 0) { rec[at] = ~v & 255; half |= bit; }
  }
  rec[63] = half;
  return encodePhotoCode(rec);
}
/** The text the camera writes into a photo's UserComment, for sharing: "Caduceus FILM n Name om3.1.<43>". */
export const recipeText = (l: Look, film: number) => `Caduceus FILM ${film} ${l.name.replace(/[^\x20-\x7e]/g, '?')} ${photoCodeOf(l)}`;
export function encodePhotoCode(rec: Uint8Array): string {
  const nib = Array.from(rec.subarray(0, 64), (v) => v & 15);
  let bin = ''; for (let k = 0; k < 32; k++) bin += String.fromCharCode((nib[2 * k] << 4) | nib[2 * k + 1]);
  return 'om3.1.' + btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

// ---- first visit: the 20 films (FILM 1-20). `film:` = a film sim, otherwise a library look (a process rather
// than a film).
// owner 2026-11-08: the 20 film sims in the camera's FILM 1-20 order (scripts/films.py CAMERA).
const DEFAULT_NAMES = Array.from({ length: COLORS }, (_, k) => CAMERA_FILMS.slice(PER * k, PER * k + PER).map((f) => `film:${f.name}`));
/** Start-up looks carry no grain, Glow / Clarity or Art Effect: those stay the user's choice. */
const plain = (l: Look | null): Look | null => { if (l) { l.effect = null; l.art_effect = 'off'; delete l.film_grain; } return l; };
export function defaultBank(library: Pack, fromLib: (l: Look) => Look): Bank {
  const colour = library.looks.filter((l) => l.kind === 'colour');
  const used = new Set<string>(), bank = emptyBank();
  DEFAULT_NAMES.forEach((row, k) => row.forEach((n, v) => {
    if (n.startsWith('film:')) { const f = filmByName(n.slice(5)); if (f) bank[k][v] = filmLook(f); return; }
    const src = colour.find((l) => l.name === n && !used.has(l.name));
    if (src) { used.add(src.name); bank[k][v] = plain(toOm3(fromLib(src)).look); }
  }));
  for (let k = 0; k < COLORS; k++) for (let v = 0; v < PER; v++) {      // looks renamed in a newer library: fill gaps
    if (bank[k][v]) continue;
    const src = colour.find((l) => !used.has(l.name));
    if (src) { used.add(src.name); bank[k][v] = plain(toOm3(fromLib(src)).look); }
  }
  return bank;
}

/** The older single-page Look Lab (androidfanman/caduceus-om3 looklab/, localStorage 'om3-looklab'): its profiles. */
export function fromOldLookLab(raw: string | null): Bank | null {
  if (!raw) return null;
  try {
    const s = JSON.parse(raw);
    if (!s || s.v !== 3 || !Array.isArray(s.prof) || s.prof.length !== 4) return null;
    const bank = emptyBank();
    s.prof.forEach((list: unknown[], k: number) => (Array.isArray(list) ? list : []).slice(0, PER).forEach((o: any, v: number) => {
      const l = blankLook('colour', String(o?.name || `Look ${v + 1}`).slice(0, OM3_NAME_MAX).trim() || 'Look');
      const a = (x: unknown, n: number) => (Array.isArray(x) && x.length === 12 ? x.map((y) => clampI(y, n)) : new Array(12).fill(0));
      l.hue = a(o.hue, 5); l.light = a(o.light, 5); l.sat = a(o.sat, 5);
      l.wb = o.ab || o.gm ? { a_b: clampI(o.ab, 5), g_m: clampI(o.gm, 5) } : null;
      l.tone = { highlights: clampI(o.hl, 7), shadows: clampI(o.sh, 7), midtones: clampI(o.mid, 7), blacks: clampI(o.blacks, 5), whites: clampI(o.whites, 5) };
      l.advice = { contrast: clampI(o.contrast, 2), sharpness: clampI(o.sharp, 2) }; l.vignette = clampI(o.shading, 5);
      l.notes = String(o.blurb || '').slice(0, 200);
      bank[k][v] = l;
    }));
    return bank.some((r) => r.some(Boolean)) ? bank : null;
  } catch { return null; }
}

/** Parse a saved / opened bank file. */
export function parseBank(v: unknown, parseLook: (x: unknown, what: string) => Look): BankFile {
  const o = v as { schema?: unknown; name?: unknown; bank?: unknown };
  if (!o || o.schema !== BANK_SCHEMA || !Array.isArray(o.bank)) throw new Error('Not an OM-3 look bank file.');
  const bank = emptyBank();
  (o.bank as unknown[]).slice(0, COLORS).forEach((row, k) => (Array.isArray(row) ? row : []).slice(0, PER).forEach((x, j) => {
    if (x) bank[k][j] = parseLook(x, `COLOR ${k + 1} look ${j + 1}`);
  }));
  return { schema: BANK_SCHEMA, name: typeof o.name === 'string' ? o.name : 'OM-3 looks', bank };
}
