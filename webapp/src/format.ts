// Card-file encoders: EP7MOD/LOOKS.BIN (v3, or v4 for v0.34 with curve / matrix: the 32-look picker file) and EP7MOD/BUNDLES.BIN (v1 + name section).
// Byte-for-byte ports of the desktop tools:
//   tools/ep7_looks_bin.py   header / record / with_tone / place / make_file / check_file (v0.19: per-look tone)
//   tools/ep7_library.py     look_record (canonical bundle), place (look -> slot entry), name rules
//   patches/bundles/build.py slot_entry (field encoding), patches/sd_bundles/build.py RANGES + header
//   tools/ep7_bundles_bin.py name_section / check_names / check_file(tone=True)
// v0.19 look tone (LOOKS.BIN stays version 3, 64-byte records): a COLOR look with a tone has +32 = 1 (tone flag),
// +33 Blacks, +34 Whites (s8 -5..5), +35 Highlights, +36 Midtones, +37 Shadows (s8 -7..7), +38..44 = 0 and slot
// mask 1 (COLOR only: +33..44 no longer carry the MONO saturation advice). In BUNDLES.BIN its COLOR slots get
// Blacks/Whites at +47/+48 (MONO slots keep 0). The app writes the tone block when the look's tone is not all zero,
// and from v0.24 for every colour look (#56), so a Film pick always sets tone and saturation.
// tests/encoder.test.ts checks the output against the Python tools and the released card files.
import {
  ARTS, CURVES, MATRIX_MAX, matrixIsZero, EFFECTS, FILM_GRAINS, GRAINS, GRAIN_BYTE, grainFromByte, defaultProfile, profileOf, MAX_LOOKS, NAME_MAX, NOTE_MAX, PACK_SCHEMA, SLOT_NAMES, TINTS, TONE_BW_MAX, TONE_KEYS,
  HALOS, blankLook, lookSplitOk, toneIsZero, toneLimit, zeroTone, type Look, type Pack, type ProfileSettings,
} from './pack';
import { hasSplit } from './split';

// ---- CRC-32 (zlib)
const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();
export function crc32(...parts: Uint8Array[]): number {
  let c = 0xffffffff;
  for (const p of parts) for (let i = 0; i < p.length; i++) c = CRC_TABLE[(c ^ p[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

// ---- firmware the card files are made for (Control Panel selector). 34 = v0.34 or later (base curve +53, colour matrix
// +54..+59 in COLOR slots of BUNDLES.BIN; docs/LOOK_FORMAT_V4.md). 32 = v0.32 or later (split toning +62/+63), 31 = v0.31
// (Halo +52), 28 = v0.28..v0.30 (Sharp +51), 27 = v0.27, 25 = v0.25 / v0.26.
export type Fw = 34 | 32 | 31 | 28 | 27 | 25 | 24 | 23;
export const FW_LATEST: Fw = 34;
let FW: Fw = FW_LATEST;
export const setFirmware = (f: Fw) => { FW = f; };
export const firmware = () => FW;

// ---- constants (Python names in comments)
const MAGIC = [0x45, 0x50, 0x37, 0x42];                 // 'EP7B'
const FW_BUILD = 1100;                                  // SB.FW_BUILD
const SHA_PREFIX = [0x5d, 0xd9, 0xaf, 0x16];            // SB.SHA_PREFIX: decoded main SHA-256 5dd9af16...
export const LAYOUT_CRC = 0x68068776;                   // ep7_library.layout_crc() of patches/bundles/layout.json
export const HL_MAX = 7;                                // v0.16 firmware: hue/light -7..7 (RANGES_LEGACY)
export const SAT_MAX = 5, WB_MAX = 7, VIG_MAX = 5, STRENGTH_MAX = 5;
const LOOKS_VERSION = 3, HDR_LEN = 64, REC_LEN = 64;
// v0.34 LOOKS.BIN v4 (patches/looks_v4, tools/ep7_looks_bin.py): header +4 = 4, +32 CRC-32 of the extension, +36 = 16;
// after the n v3 records, n 16-byte extension records: +0 curve (slot +53), +1..+6 matrix s8 (slot +54..+59), +7..15 = 0.
// The +16 CRC is the v3 rule over the v3 part. Written only for v0.34 or later and only when a colour look sets a field.
const LOOKS_V4 = 4, EXT_LEN = 16, EXT_CRC = 32, EXT_LEN_OFF = 36;
// v0.19 tone block in a COLOR record: +32 flag, then the values at these offsets
const TONE_FLAG = 32;
const TONE_OFF = { blacks: 33, whites: 34, highlights: 35, midtones: 36, shadows: 37 } as const;
const B_BLACKS = 47, B_WHITES = 48, B_SHADING = 49, B_GRAIN = 50, B_NR = 24, B_SHARP = 51, B_HALO = 52;
// v0.32 split toning (COLOR slots): +62 Shadows, +63 Highlights, each low nibble colour 0..11, high nibble strength s4 -5..5
const B_SPLIT_SH = 62, B_SPLIT_HL = 63;
// v0.34 (patches/look_hw): +53 base curve (0 = the camera's own, 1.. = CURVES index + 1), +54..+59 matrix s8 (1/128)
const B_CURVE = 53, B_MTX = 54, B_MIXMEM = 60;
// v0.32 LOOKS.BIN: the same two bytes in the record's name tail, +61 Shadows / +62 Highlights (names end by +60: at most
// 12 characters). A Film pick copies them to slot +62/+63 (0 clears). Older firmware rejects a record with them non-zero.
const R_SPLIT_SH = 61, R_SPLIT_HL = 62;
const packSplit = (c: number, v: number) => c | ((v & 15) << 4);
const splitByteOk = (b: number) => (b & 15) < 12 && (((b >> 4) + 5) & 15) < 11;
const unpackSplit = (b: number): [number, number] => [b & 15, (b >> 4) > 7 ? (b >> 4) - 16 : b >> 4];
const MASK_KEEP_CORRECTION = 4;                         // v0.25 record slot mask bit 2
const BUNDLE_USED = 45, CLASS_OFF = 45, MASK_OFF = 46, TINT_OFF = 47, NAME_OFF = 48;
const B_TINT = 45, B_ART = 46, B_COLOUR = 32, B_SAT = 33, B_FLAGS = 31;
const FLAG_RENDER_COLOUR = 1, FLAG_HL = 2;
const BUNDLES_VERSION = 1, B_HDR_LEN = 32, B_PAYLOAD = 512, B_FILE = 544, B_FILE_N = 680;
const NMAGIC = [0x45, 0x50, 0x37, 0x4e];                // 'EP7N'
export const SLOT_NAME_MAX = 15;

// Per-byte loader ranges of the 64-byte bundle ABI (sd_bundles RANGES_LEGACY over layout.json fields).
const FIELDS: [number, number, number, number][] = [   // off, len, lo, hi
  [0, 12, -HL_MAX, HL_MAX], [12, 12, -HL_MAX, HL_MAX], [24, 1, 0, 6], [25, 1, 0, 1], [26, 1, -WB_MAX, WB_MAX],
  [27, 1, -WB_MAX, WB_MAX], [28, 1, 0, 3], [29, 1, 0, 5], [30, 1, -VIG_MAX, VIG_MAX], [31, 1, 0, 3], [32, 1, 0, 1],
  [33, 12, -SAT_MAX, SAT_MAX], [45, 1, 0, 4], [46, 1, 0, 5],
  [B_BLACKS, 1, -TONE_BW_MAX, TONE_BW_MAX], [B_WHITES, 1, -TONE_BW_MAX, TONE_BW_MAX], [B_SHADING, 1, 0, 1], [B_GRAIN, 1, 0, 3],
  [B_SHARP, 1, 0, 1], [B_HALO, 1, 0, 4], [B_SPLIT_SH, 2, -128, 127], [B_CURVE, 1, 0, CURVES.length], [B_MTX, 6, -MATRIX_MAX, MATRIX_MAX],
  [B_MIXMEM, 1, 0, 84]];   // v0.34b: +60 the camera's Mix / Strength choice (8 (10 - strength) + mix); the panel writes 0
export const RANGE_LO = new Int8Array(64), RANGE_HI = new Int8Array(64);   // unclaimed bytes: 0..0
for (const [off, n, lo, hi] of FIELDS) for (let k = off; k < off + n; k++) { RANGE_LO[k] = lo; RANGE_HI[k] = hi; }
const s8 = (b: number) => (b >= 128 ? b - 256 : b);
const u8 = (v: number) => v & 0xff;

// ---- validation (same rules and limits as the tools; messages are for people)
export interface Problem { look?: number; field: string; message: string }

const NAME_RE = /^[\x20-\x3f\x41-\x7e]{1,12}$/;          // printable ASCII except '@' (OSD symbol escape)
export function nameProblem(name: string): string | null {
  if (name.length === 0) return 'Name is empty.';
  if (name !== name.trim()) return 'No spaces at the start or end of the name.';
  if (name.length > NAME_MAX) return `At most ${NAME_MAX} characters (${name.length}).`;
  if (name.includes('@')) return '"@" is not allowed (the camera uses it for symbols).';
  if (!NAME_RE.test(name)) return 'Plain ASCII letters, digits, spaces and punctuation only.';
  return null;
}

const intIn = (v: unknown, lo: number, hi: number) => Number.isInteger(v) && (v as number) >= lo && (v as number) <= hi;

export function validateLook(l: Look, i?: number): Problem[] {
  const p: Problem[] = [];
  const add = (field: string, message: string) => p.push({ look: i, field, message });
  const np = nameProblem(l.name);
  if (np) add('name', np);
  if (new TextEncoder().encode(l.notes).length > NOTE_MAX) add('notes', `Notes: at most ${NOTE_MAX} bytes.`);
  if (l.kind !== 'colour' && l.kind !== 'mono') add('kind', 'Kind must be colour or mono.');
  for (const [k, lim] of [['hue', HL_MAX], ['light', HL_MAX], ['sat', SAT_MAX]] as const) {
    const a = l[k];
    if (!Array.isArray(a) || a.length !== 12 || !a.every((v) => intIn(v, -lim, lim)))
      add(k, `${k}: 12 whole numbers in -${lim}..${lim} (v0.16/v0.17 firmware).`);
  }
  if (!(GRAINS as readonly string[]).includes(l.grain) && l.grain !== 'high') add('grain', 'Noise reduction: off (Camera), standard, fine (Low) or film (Off).');
  if (l.wb && !(intIn(l.wb.a_b, -WB_MAX, WB_MAX) && intIn(l.wb.g_m, -WB_MAX, WB_MAX)))
    add('wb', `WB shift: A-B and G-M in -${WB_MAX}..${WB_MAX}.`);
  if (l.effect) {
    const e = l.effect;
    if (!EFFECTS.includes(e.type) || e.type === ('none' as string)) add('effect', 'Effect: bloom, halation or clarity.');
    else if (!intIn(e.strength, 1, STRENGTH_MAX)) add('effect', `Effect strength: 1..${STRENGTH_MAX}.`);
    if (e.tint !== undefined && (!TINTS.includes(e.tint) || (e.type !== 'bloom' && e.type !== 'halation')))
      add('effect', 'Glow colour only goes with bloom or halation.');
  }
  if (!intIn(l.vignette, -VIG_MAX, VIG_MAX)) add('vignette', `Vignette: -${VIG_MAX}..${VIG_MAX}.`);
  if (!l.tone || typeof l.tone !== 'object') add('tone', 'Tone: missing.');
  else for (const k of TONE_KEYS) {
    const lim = toneLimit(k);
    if (!intIn(l.tone[k], -lim, lim)) add('tone', `Tone ${k}: a whole number in -${lim}..${lim}.`);
  }
  if (l.curve !== undefined && !CURVES.includes(l.curve)) add('curve', 'Unknown base curve.');
  if (l.matrix !== undefined && (!Array.isArray(l.matrix) || l.matrix.length !== 6 || !l.matrix.every((v) => intIn(v, -MATRIX_MAX, MATRIX_MAX))))
    add('matrix', `Colour matrix: 6 whole numbers in -${MATRIX_MAX}..${MATRIX_MAX}.`);
  if (!ARTS.includes(l.art_effect)) add('art_effect', 'Unknown Art Effect.');
  else if (l.art_effect !== 'off' && l.kind === 'mono') add('art_effect', 'Art Effects are for colour looks (COLOR slots).');
  return p;
}

export function validatePack(pack: Pack): Problem[] {
  const p: Problem[] = [];
  const n = pack.looks.length;
  if (n < 1) p.push({ field: 'looks', message: 'A pack needs at least one look.' });
  if (n > MAX_LOOKS) p.push({ field: 'looks', message: `At most ${MAX_LOOKS} looks (the camera's limit); this pack has ${n}.` });
  pack.looks.forEach((l, i) => p.push(...validateLook(l, i)));
  const seen = new Map<string, number>();
  pack.looks.forEach((l, i) => {
    const k = l.name.toLowerCase();
    if (seen.has(k)) p.push({ look: i, field: 'name', message: `Same name as look ${seen.get(k)! + 1} ("${l.name}").` });
    else seen.set(k, i);
  });
  for (const [s, i] of Object.entries(pack.slots)) {
    if (i === undefined) continue;
    const l = pack.looks[i];
    if (!l) p.push({ field: 'slots', message: `${s}: no look ${i + 1}.` });
    else if (s.startsWith('COLOR') && l.kind === 'mono') p.push({ field: 'slots', message: `${s}: a mono look can only go in a MONO slot.` });
    else if (s.startsWith('MONO') && hasTone(l)) p.push({ field: 'slots', message: `${s}: "${l.name}" has a tone, so it can only go in a COLOR slot.` });
  }
  return p;
}

// ---- LOOKS.BIN
/** A colour look with a non-zero tone gets the v0.19 tone block (and becomes COLOR-only). */
export const hasTone = (l: Look) => l.kind === 'colour' && !!l.tone && !toneIsZero(l.tone);
/** From v0.24 every colour look gets the tone block, even with a neutral tone, so a Film pick always sets its tone and
 *  saturation (#56: a neutral-tone look used to keep the previous pick's saturation). Its LOOKS.BIN mask is then 1. */
export const writesToneBlock = (l: Look) => l.kind === 'colour' && (hasTone(l) || FW >= 24);

/** The look's 64-byte LOOKS.BIN record (bundle bytes 0..44 or the tone block, class, slot mask, bloom tint, name[16]). */
export function lookRecord(l: Look): Uint8Array {
  const r = new Uint8Array(REC_LEN);
  for (let k = 0; k < 12; k++) { r[k] = u8(l.hue[k]); r[12 + k] = u8(l.light[k]); }
  r[24] = GRAIN_BYTE[l.grain];
  if (l.wb) { r[25] = 1; r[26] = u8(l.wb.a_b); r[27] = u8(l.wb.g_m); }
  if (l.effect) {
    r[28] = EFFECTS.indexOf(l.effect.type);
    r[29] = l.effect.strength;
    if (l.effect.tint) r[TINT_OFF] = TINTS.indexOf(l.effect.tint);
  }
  r[30] = u8(l.vignette);
  const mono = l.kind === 'mono';
  r[B_FLAGS] = mono ? 0 : FLAG_HL;
  r[CLASS_OFF] = mono ? 1 : 0;
  if (writesToneBlock(l)) {             // ep7_looks_bin.with_tone
    r[TONE_FLAG] = 1;
    for (const k of TONE_KEYS) r[TONE_OFF[k]] = u8(l.tone?.[k] ?? 0);
    r[MASK_OFF] = 1;
    if (FW >= 24) {
      for (let k = 0; k < 12; k++) r[38 + (k >> 1)] |= (l.sat[k] & 15) << (4 * (k & 1));   // v0.24: a Film pick sets saturation
      r[44] = 1;
    }
  } else {
    if (!mono) for (let k = 0; k < 12; k++) r[B_SAT + k] = u8(l.sat[k]);
    r[MASK_OFF] = mono ? 2 : 3;         // colour looks without tone carry sat (-5..5), so they may go in MONO slots
  }
  if (!mono && l.lens_correction && FW >= 25) r[MASK_OFF] |= MASK_KEEP_CORRECTION;
  const nm = new TextEncoder().encode(l.name);
  r.set(nm.subarray(0, NAME_MAX), NAME_OFF);
  if (FW >= 32 && !mono && l.split && hasSplit(l) && lookSplitOk(l.split)) {   // v0.32: a Film pick sets the profile's split
    r[R_SPLIT_SH] = packSplit(l.split.sh_color, l.split.sh);
    r[R_SPLIT_HL] = packSplit(l.split.hl_color, l.split.hl);
  }
  return r;
}

function looksHeader(n: number, crc: number, extCrc?: number): Uint8Array {
  const h = new Uint8Array(HDR_LEN);
  const v = new DataView(h.buffer);
  h.set(MAGIC, 0);
  v.setUint16(4, extCrc === undefined ? LOOKS_VERSION : LOOKS_V4, true); v.setUint16(6, HDR_LEN, true);
  v.setUint32(8, FW_BUILD, true); v.setUint32(12, REC_LEN * n, true); v.setUint32(16, crc, true);
  h.set(SHA_PREFIX, 20);
  v.setUint16(24, n, true); v.setUint16(26, REC_LEN, true); v.setUint32(28, LAYOUT_CRC, true);
  if (extCrc !== undefined) { v.setUint32(EXT_CRC, extCrc, true); v.setUint16(EXT_LEN_OFF, EXT_LEN, true); }
  return h;
}

/** The look's 16-byte v4 extension record (zeros for a mono look or a look without curve / matrix). */
export function lookExt(l: Look): Uint8Array {
  const e = new Uint8Array(EXT_LEN);
  if (l.kind !== 'colour') return e;
  if (l.curve) e[0] = CURVES.indexOf(l.curve) + 1;
  if (!matrixIsZero(l.matrix)) l.matrix!.forEach((v, i) => { e[1 + i] = u8(v); });
  return e;
}

const isV4 = (d: Uint8Array) => d.length >= 6 && (d[4] | (d[5] << 8)) === LOOKS_V4;

export class PackError extends Error {
  constructor(public problems: Problem[]) { super(problems.map((p) => (p.look !== undefined ? `look ${p.look + 1}: ` : '') + p.message).join('\n')); }
}

/** Validated LOOKS.BIN bytes for the pack (throws PackError). */
export function encodeLooksBin(pack: Pack): Uint8Array {
  const probs = validatePack({ ...pack, slots: {} });
  if (probs.length) throw new PackError(probs);
  const n = pack.looks.length;
  const exts = pack.looks.map(lookExt);
  const v4 = FW >= 34 && exts.some((e) => e.some((b) => b !== 0));
  const v3len = HDR_LEN + REC_LEN * n;
  const out = new Uint8Array(v3len + (v4 ? EXT_LEN * n : 0));
  pack.looks.forEach((l, j) => out.set(lookRecord(l), HDR_LEN + REC_LEN * j));
  let extCrc: number | undefined;
  if (v4) {
    exts.forEach((e, j) => out.set(e, v3len + EXT_LEN * j));
    extCrc = crc32(out.subarray(v3len));
  }
  out.set(looksHeader(n, 0, extCrc), 0);
  const crc = crc32(out.subarray(0, 16), out.subarray(20, v3len));
  new DataView(out.buffer).setUint32(16, crc, true);
  const chk = checkLooksBin(out);
  if (chk.length) throw new PackError(chk.map((m) => ({ field: 'file', message: m })));
  return out;
}

function nameOk(nm: Uint8Array, split = false): boolean {   // camera rule (_name_ok): 1..15 printable non-'@' then NUL to byte 15
  if (nm.length !== 16 || nm[0] === 0 || nm[15] !== 0) return false;
  // v0.32 (ls_sc): with the name ended by byte 12, bytes 13/14 (record +61/+62) may carry split toning instead
  if (split && nm[12] === 0 && (nm[13] || nm[14])) {
    if (!splitByteOk(nm[13]) || !splitByteOk(nm[14])) return false;
    nm = Uint8Array.from(nm); nm[13] = nm[14] = 0;
  }
  let seen = false;
  for (const c of nm) {
    if (c === 0) seen = true;
    else if (seen || c === 0x40 || c < 0x20 || c > 0x7e) return false;
  }
  return true;
}

// v0.19 camera table (fm_check): +33/+34 -5..5, +35..37 -7..7 (a superset of the sat range those bytes had)
const LOOK_LO = Int8Array.from(RANGE_LO), LOOK_HI = Int8Array.from(RANGE_HI);
LOOK_LO[33] = LOOK_LO[34] = -5; LOOK_HI[33] = LOOK_HI[34] = 5;
for (const o of [35, 36, 37]) { LOOK_LO[o] = -7; LOOK_HI[o] = 7; }
for (let o = 38; o < 44; o++) { LOOK_LO[o] = -128; LOOK_HI[o] = 127; }   // v0.24: sat[12] as nibbles

/** Mirror of the camera's pk_check (tools/ep7_looks_bin.py check_file): [] = accepted. `split`: record +61/+62 may
 *  carry split toning (v0.32 firmware; older firmware rejects such a file). */
export function checkLooksBin(d: Uint8Array, split = FW >= 32): string[] {
  if (isV4(d)) {                       // v0.34 (looks_v4): v4 header and extension, then the v3 part as the camera sees it
    const n = d.length >= 26 ? d[24] | (d[25] << 8) : 0;
    if (n < 1 || n > MAX_LOOKS || d.length !== HDR_LEN + (REC_LEN + EXT_LEN) * n) return [`v4 size ${d.length}`];
    const dv = new DataView(d.buffer, d.byteOffset, d.byteLength), v3len = HDR_LEN + REC_LEN * n;
    const want = looksHeader(n, 0, dv.getUint32(EXT_CRC, true));
    for (let i = 0; i < HDR_LEN; i++) if ((i < 16 || i >= 20) && d[i] !== want[i]) return ['header'];
    if (crc32(d.subarray(0, 16), d.subarray(20, v3len)) !== dv.getUint32(16, true)) return ['crc'];
    const p: string[] = [];
    const ext = d.subarray(v3len);
    if (crc32(ext) !== dv.getUint32(EXT_CRC, true)) p.push('extension crc');
    else for (let j = 0; j < n; j++) {
      const e = ext.subarray(EXT_LEN * j, EXT_LEN * (j + 1));
      if (e[0] > CURVES.length || e.subarray(1, 7).some((b) => Math.abs(s8(b)) > MATRIX_MAX) || e.subarray(7).some((b) => b !== 0))
        p.push(`look ${j} extension out of range`);
    }
    const v3 = d.slice(0, v3len), h = looksHeader(n, 0);
    v3.set(h.subarray(0, 16), 0); v3.set(h.subarray(20), 20);
    new DataView(v3.buffer).setUint32(16, crc32(v3.subarray(0, 16), v3.subarray(20)), true);
    return p.concat(checkLooksBin(v3, split));
  }
  const p: string[] = [];
  const size = d.length;
  if (size < HDR_LEN + REC_LEN || size > HDR_LEN + REC_LEN * MAX_LOOKS || size % REC_LEN) return [`size ${size}`];
  const n = (size - HDR_LEN) / REC_LEN;
  const want = looksHeader(n, 0);
  for (let i = 0; i < HDR_LEN; i++) if ((i < 16 || i >= 20) && d[i] !== want[i]) { p.push('header'); break; }
  const crc = new DataView(d.buffer, d.byteOffset, d.byteLength).getUint32(16, true);
  if (crc32(d.subarray(0, 16), d.subarray(20)) !== crc) p.push('crc');
  for (let j = 0; j < n; j++) {
    const r = d.subarray(HDR_LEN + REC_LEN * j, HDR_LEN + REC_LEN * (j + 1));
    for (let k = 0; k < BUNDLE_USED; k++) {
      const v = s8(r[k]);
      if (v < LOOK_LO[k] || v > LOOK_HI[k]) { p.push(`look ${j} byte ${k} = ${v} out of range`); break; }
    }
    const cls = r[CLASS_OFF], mask = r[MASK_OFF];
    if (!((cls === 0 && ((mask & ~MASK_KEEP_CORRECTION) === 1 || (mask & ~MASK_KEEP_CORRECTION) === 3)) || (cls === 1 && mask === 2)) || r[TINT_OFF] > 4)
      p.push(`look ${j} class/mask/tint ${cls}/${mask}/${r[TINT_OFF]}`);
    if (!nameOk(r.subarray(NAME_OFF, NAME_OFF + 16), split)) p.push(`look ${j} name`);
  }
  return p;
}

/** LOOKS.BIN (checked like the camera) -> pack. LOOKS.BIN has no notes, Art Effect or advice; mono looks get the
 *  "no filter" advice; looks without a tone block get tone 0. Throws with a readable message. */
export function decodeLooksBin(d: Uint8Array, name = 'Imported LOOKS.BIN'): Pack {
  const ver = d.length >= 6 ? d[4] | (d[5] << 8) : 0;
  if (ver !== LOOKS_VERSION && ver !== LOOKS_V4) throw new Error(`LOOKS.BIN version ${ver}: only versions 3 and 4 are camera files`);
  const probs = checkLooksBin(d, true);
  if (probs.length) throw new Error(`LOOKS.BIN rejected (${probs.slice(0, 3).join('; ')})`);
  const n = ver === LOOKS_V4 ? d[24] | (d[25] << 8) : (d.length - HDR_LEN) / REC_LEN;
  const looks: Look[] = [];
  for (let j = 0; j < n; j++) {
    const r = d.subarray(HDR_LEN + REC_LEN * j, HDR_LEN + REC_LEN * (j + 1));
    const mono = r[CLASS_OFF] === 1;
    const nm = r.subarray(NAME_OFF, NAME_OFF + 16);
    const l = blankLook(mono ? 'mono' : 'colour', String.fromCharCode(...nm.subarray(0, nm.indexOf(0))));
    const tone = !mono && r[TONE_FLAG] === 1;
    for (let k = 0; k < 12; k++) { l.hue[k] = s8(r[k]); l.light[k] = s8(r[12 + k]); if (!mono && !tone) l.sat[k] = s8(r[B_SAT + k]); }
    l.grain = grainFromByte(r[24]);
    if (r[25]) l.wb = { a_b: s8(r[26]), g_m: s8(r[27]) };
    if (r[28]) {
      l.effect = { type: EFFECTS[r[28]] as Exclude<(typeof EFFECTS)[number], 'none'>, strength: r[29] };
      if (r[TINT_OFF]) l.effect.tint = TINTS[r[TINT_OFF]];
    }
    l.vignette = s8(r[30]);
    if (!mono && r[MASK_OFF] & MASK_KEEP_CORRECTION) l.lens_correction = true;
    l.tone = zeroTone();
    if (tone) for (const k of TONE_KEYS) l.tone[k] = s8(r[TONE_OFF[k]]);
    if (tone && r[44] === 1) for (let k = 0; k < 12; k++) { const v = (r[38 + (k >> 1)] >> (4 * (k & 1))) & 15; l.sat[k] = v > 7 ? v - 16 : v; }
    if (!mono && r[NAME_OFF + 12] === 0 && (r[R_SPLIT_SH] || r[R_SPLIT_HL])) {   // v0.32 split toning in the name tail
      const [sh_color, sh] = unpackSplit(r[R_SPLIT_SH]), [hl_color, hl] = unpackSplit(r[R_SPLIT_HL]);
      if (sh || hl) l.split = { sh_color, sh, hl_color, hl };
    }
    if (ver === LOOKS_V4 && !mono) {    // v0.34 extension: base curve and colour matrix
      const e = d.subarray(HDR_LEN + REC_LEN * n + EXT_LEN * j, HDR_LEN + REC_LEN * n + EXT_LEN * (j + 1));
      if (e[0]) l.curve = CURVES[e[0] - 1];
      const m = Array.from(e.subarray(1, 7), s8);
      if (!matrixIsZero(m)) l.matrix = m;
    }
    looks.push(l);
  }
  return { schema: PACK_SCHEMA, name, looks, slots: {} };
}

// ---- BUNDLES.BIN (starter slot file)
/** P(look, slot): the 64-byte table entry a slot gets (tools/ep7_library.place) + the COLOR-slot Art Effect and
 *  Blacks/Whites (+47/+48; MONO slots keep 0). NR (+24) and Grain (+50) are the profile's own settings, never the
 *  look's: `prof` for a COLOR slot (default NR Camera, Grain Off), Camera for a MONO slot. Grain needs v0.27. */
export function placeLook(l: Look, slot: string, prof: ProfileSettings = defaultProfile()): Uint8Array {
  const rec = lookRecord(l);         // with a tone block, +32..44 are cleared below (COLOR) like LIB.place
  const b = new Uint8Array(64);
  b.set(rec.subarray(0, BUNDLE_USED));
  b[B_NR] = 0;
  b[B_TINT] = rec[TINT_OFF];
  if (slot.startsWith('COLOR')) {
    if (l.kind === 'mono') throw new Error(`${slot}: a mono look cannot go in a COLOR slot`);
    b.fill(0, B_SAT, B_SAT + 12);
    b[B_COLOUR] = 0;
    b[B_FLAGS] = FLAG_HL;
    b[B_ART] = ARTS.indexOf(l.art_effect);
    if (FW >= 25 && !l.lens_correction) b[B_SHADING] = 1;   // v0.25: lens vignette correction off, as a Film pick does
    if (hasTone(l)) { b[B_BLACKS] = u8(l.tone.blacks); b[B_WHITES] = u8(l.tone.whites); }
    if (FW >= 32 && l.split && hasSplit(l) && lookSplitOk(l.split)) {   // the shared `split` field, packed for the E-P7 slot
      b[B_SPLIT_SH] = packSplit(l.split.sh_color, l.split.sh);
      b[B_SPLIT_HL] = packSplit(l.split.hl_color, l.split.hl);
    }
    if (FW >= 34) {                    // v0.34: base curve and colour matrix (COLOR slots only)
      if (l.curve) b[B_CURVE] = CURVES.indexOf(l.curve) + 1;
      if (!matrixIsZero(l.matrix)) l.matrix!.forEach((v, i) => { b[B_MTX + i] = u8(v); });
    }
    profileBytes(b, prof);
  } else if (l.kind === 'colour') {
    if (hasTone(l)) throw new Error(`${slot}: a look with a tone cannot go in a MONO slot`);
    for (let k = 0; k < 12; k++) b[B_SAT + k] = u8(l.sat[k]);   // the record may hold the (zero) tone block here (#56)
    b[B_COLOUR] = 1;
    b[B_FLAGS] = FLAG_HL | FLAG_RENDER_COLOUR;
  } else {
    b[B_FLAGS] = 0;
  }
  return b;
}

/** The COLOR profile's own bytes (never the look's): NR +24, Grain +50 (v0.27), Sharp +51 (v0.28), Halo +52 (v0.31; 0 = follow the look). */
function profileBytes(b: Uint8Array, prof: ProfileSettings): Uint8Array {
  b[B_NR] = GRAIN_BYTE[prof.nr] ?? 0;
  if (FW >= 27) b[B_GRAIN] = Math.max(0, FILM_GRAINS.indexOf(prof.grain));
  if (FW >= 28) b[B_SHARP] = prof.sharp === 'off' ? 1 : 0;
  if (FW >= 31) b[B_HALO] = Math.max(0, HALOS.indexOf(prof.halo ?? 'look'));
  return b;
}

/** BUNDLES.BIN for the pack's slot assignment (680 B with the look names as slot names; empty slot = stock). */
export function encodeBundlesBin(pack: Pack, withNames = true): Uint8Array {
  const probs = validatePack(pack).filter((p) => p.field === 'slots' || (p.look !== undefined && Object.values(pack.slots).includes(p.look)));
  if (probs.length) throw new PackError(probs);
  const out = new Uint8Array(withNames ? B_FILE_N : B_FILE);
  const dv = new DataView(out.buffer);
  out.set(MAGIC, 0);
  dv.setUint16(4, BUNDLES_VERSION, true); dv.setUint16(6, B_HDR_LEN, true);
  dv.setUint32(8, FW_BUILD, true); dv.setUint32(12, B_PAYLOAD, true);
  out.set(SHA_PREFIX, 20);
  SLOT_NAMES.forEach((s, k) => {
    const i = pack.slots[s], o = B_HDR_LEN + 64 * k;
    if (i !== undefined) out.set(placeLook(pack.looks[i], s, profileOf(pack, s)), o);
    else if (k < 4) {                  // an empty COLOR slot (stock rendering) still carries its profile's Grain / NR
      out.set(profileBytes(new Uint8Array(64), profileOf(pack, s)), o);
    }
  });
  dv.setUint32(16, crc32(out.subarray(0, 16), out.subarray(20, B_FILE)), true);
  if (withNames) {
    SLOT_NAMES.forEach((s, k) => {
      const i = pack.slots[s];
      if (i !== undefined) out.set(new TextEncoder().encode(pack.looks[i].name).subarray(0, SLOT_NAME_MAX), B_FILE + 16 * k);
    });
    out.set(NMAGIC, B_FILE + 128);
    dv.setUint32(B_FILE + 132, crc32(out.subarray(B_FILE, B_FILE + 132)), true);
  }
  const chk = checkBundlesBin(out);
  if (chk.length) throw new PackError(chk.map((m) => ({ field: 'file', message: m })));
  return out;
}

/** Mirror of tools/ep7_bundles_bin.py check_file (+ check_names for a 680-byte file): [] = accepted. */
export function checkBundlesBin(d: Uint8Array): string[] {
  if (d.length !== B_FILE && d.length !== B_FILE_N) return [`size ${d.length}`];
  const p: string[] = [];
  const dv = new DataView(d.buffer, d.byteOffset, d.byteLength);
  const want = new Uint8Array(B_HDR_LEN);
  want.set(MAGIC, 0);
  new DataView(want.buffer).setUint16(4, BUNDLES_VERSION, true);
  new DataView(want.buffer).setUint16(6, B_HDR_LEN, true);
  new DataView(want.buffer).setUint32(8, FW_BUILD, true);
  new DataView(want.buffer).setUint32(12, B_PAYLOAD, true);
  want.set(SHA_PREFIX, 20);
  for (let i = 0; i < B_HDR_LEN; i++) if ((i < 16 || i >= 20) && d[i] !== want[i]) { p.push(`header byte ${i}`); break; }
  if (crc32(d.subarray(0, 16), d.subarray(20, B_FILE)) !== dv.getUint32(16, true)) p.push('crc32');
  for (let k = 0; k < B_PAYLOAD; k++) {
    const v = s8(d[B_HDR_LEN + k]);
    if (v < RANGE_LO[k % 64] || v > RANGE_HI[k % 64]) { p.push(`slot ${k >> 6} byte ${k % 64} = ${v} out of range`); break; }
  }
  if (FW < 27) for (let k = 0; k < 8; k++) if (d[B_HDR_LEN + 64 * k + B_GRAIN]) { p.push(`slot ${k}: Grain needs v0.27 or later`); break; }
  if (FW < 28) for (let k = 0; k < 8; k++) if (d[B_HDR_LEN + 64 * k + B_SHARP]) { p.push(`slot ${k}: Sharp needs v0.28 or later`); break; }
  if (FW < 31) for (let k = 0; k < 8; k++) if (d[B_HDR_LEN + 64 * k + B_HALO]) { p.push(`slot ${k}: Halo needs v0.31 or later`); break; }
  if (FW < 32) for (let k = 0; k < 8; k++) if (d[B_HDR_LEN + 64 * k + B_SPLIT_SH] || d[B_HDR_LEN + 64 * k + B_SPLIT_HL]) { p.push(`slot ${k}: split toning needs v0.32 or later`); break; }
  for (let k = 4; k < 8; k++) if (d[B_HDR_LEN + 64 * k + B_SPLIT_SH] || d[B_HDR_LEN + 64 * k + B_SPLIT_HL]) { p.push(`slot ${k}: split toning is COLOR-only`); break; }
  const lookHw = (k: number) => d.subarray(B_HDR_LEN + 64 * k + B_CURVE, B_HDR_LEN + 64 * k + B_MTX + 6).some((v) => v !== 0);
  if (FW < 34) for (let k = 0; k < 8; k++) if (lookHw(k)) { p.push(`slot ${k}: base curve / colour matrix need v0.34 or later`); break; }
  for (let k = 4; k < 8; k++) if (lookHw(k)) { p.push(`slot ${k}: base curve / colour matrix are COLOR-only`); break; }
  for (let k = 4; k < 8; k++) if (d[B_HDR_LEN + 64 * k + B_BLACKS] || d[B_HDR_LEN + 64 * k + B_WHITES]) { p.push(`slot ${k}: Blacks/Whites are COLOR-only`); break; }
  if (d.length === B_FILE_N) {
    if (!NMAGIC.every((c, i) => d[B_FILE + 128 + i] === c)) p.push('name marker');
    else if (crc32(d.subarray(B_FILE, B_FILE + 132)) !== dv.getUint32(B_FILE + 132, true)) p.push('name crc');
    else for (let k = 0; k < 8; k++) {
      let nul = false;
      for (let i = 0; i < 16; i++) {
        const c = d[B_FILE + 16 * k + i];
        if (c === 0) nul = true;
        else if (nul || i === 15 || c === 0x40 || c < 0x20 || c > 0x7e) { p.push(`slot ${k} name`); break; }
      }
    }
  }
  return p;
}
