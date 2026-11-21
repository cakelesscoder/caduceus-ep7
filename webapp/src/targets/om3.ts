// OM SYSTEM OM-3 with Caduceus for OM-3 (androidfanman/caduceus-om3): translate a pack to its card files on export,
// and its card files and links back to the shared format on import.
// The pack stays the one shared format. The OM-3 has 5 looks for each of COLOR 1-4, so the first 20 colour looks fill
// COLOR 1-5, 2-5... in list order; toOm3 limits ranges (docs/OM3_NOTES.md lists what carries over). Hue numbers copy
// across as they are: the direction on each body is an open question there.
// Since their v0.28 the OM-3 has look settings the shared format doesn't (Tone Balance, a WB mode per film, split
// toning in half steps, Halation as its own row; v0.30 RGB curves and Color Mix; v0.40 Border and Film Grain 1..5 /
// Grain Size): the vendored ../om3.ts keeps them on its bank looks, and only this module turns them into shared fields
// (or reports them as left out). Nothing OM-3-only reaches a pack or share code.
import { COLORS, PER, emptyBank, parseBank, profilesBin, readProfiles, toOm3, type Bank, type Fw } from '../om3';
import { hasCurves, parseCurves, parseMix } from '../curves';
import { parseSplit } from '../split';
import { PACK_SCHEMA, TONE_BW_MAX, lookHalo, matrixIsZero, parseFilmWb, parseLook, type Look, type Pack } from '../pack';
import type { Target } from './types';

export const OM3_REPO = 'https://github.com/androidfanman/caduceus-om3';

/** The OM-3 firmware the LOOKS.BIN is written for (om3.ts `profilesBin(bank, fw)`), labelled as their panel does.
 *  Newer bytes are left out for older firmware, which would refuse the file. v0.29 to v0.40 read the v0.28 file
 *  (v0.40's Border uses +48, which shared looks leave 0). */
export const OM3_FWS: [Fw, string][] = [
  [28, 'v0.28 or later (v0.29 – v0.40 too)'], [26, 'v0.26.1 – v0.27.1'], [25, 'v0.26'], [24, 'v0.25'], [23, 'v0.24.1'],
  [22, 'v0.22'], [21, 'v0.21'], [20, 'v0.20 or older'],
];
export const OM3_FW_LATEST: Fw = 28;
const STORE_OM3_FW = 'caduceus.om3.fw';
export function om3Fw(): Fw {
  try { const v = Number(localStorage.getItem(STORE_OM3_FW)); if (OM3_FWS.some(([f]) => f === v)) return v as Fw; } catch { /* no storage */ }
  return OM3_FW_LATEST;
}
export function setOm3Fw(fw: Fw) { try { localStorage.setItem(STORE_OM3_FW, String(fw)); } catch { /* no storage */ } }
export interface Placed { name: string; k: number; v: number; changed: string[]; dropped: string[] }
export interface Om3Bank { bank: Bank; placed: Placed[]; mono: number; extra: string[]; lens: number }

/** The halo becomes the OM-3's Halation (v0.28): a `halation` effect = Halation alone; a red or amber tinted Glow (the
 *  E-P7 halo on the Glow channel) = Glow plus Halation at the same strength. Cool / warm tints stay a plain Glow. */
const haloOf = (src: Look): number => {
  const e = src.effect, h = lookHalo(src);
  return e && h.stage !== 'off' && (h.tint === 'red' || h.tint === 'amber') ? Math.max(1, Math.min(5, Math.round(e.strength))) : 0;
};

/** One shared look as an OM-3 bank look for firmware `fw`, with what was limited or left out. */
export function lookToOm3(src: Look, fw: Fw = OM3_FW_LATEST): { look: Look | null; changed: string[]; dropped: string[] } {
  const c = toOm3(src), l = c.look;
  if (!l) return c;
  if (src.curve !== undefined) c.dropped.push('Base curve');            // E-P7 v0.34 only: no OM-3 equivalent
  if (!matrixIsZero(src.matrix)) c.dropped.push('Colour mix');
  delete l.curve; delete l.matrix; delete l.tone_balance; delete l.film_wb; delete l.halation;
  delete l.rgb; delete l.mix; delete l.border; delete l.grain_size; delete l.grain_strength;
  if (l.split) {                    // shared: whole steps, minus = opposite colour; OM-3 v0.28: plus only (their parseSplit)
    const sp = parseSplit(l.split);
    if (sp && (sp.sh_color !== l.split.sh_color || sp.hl_color !== l.split.hl_color)) c.changed.push('split toning minus as the opposite colour');
    if (sp) l.split = sp; else delete l.split;
  }
  const halo = haloOf(src);
  if (halo && fw >= 28) {
    l.halation = halo;
    if (src.effect?.type === 'halation') l.effect = null;
    c.changed = c.changed.filter((x) => x !== 'halation as glow' && x !== 'glow colour');
    if (lookHalo(src).tint === 'amber') c.changed.push('halo colour (red on the OM-3)');
  }
  return c;
}

export function packToBank(p: Pack, fw: Fw = OM3_FW_LATEST): Om3Bank {
  const bank = emptyBank(), placed: Placed[] = [];
  const colour = p.looks.filter((l) => l.kind === 'colour');
  colour.slice(0, COLORS * PER).forEach((src, i) => {
    const c = lookToOm3(src, fw), k = Math.floor(i / PER), v = i % PER;
    bank[k][v] = c.look;
    placed.push({ name: src.name, k, v, changed: c.changed, dropped: c.dropped });
  });
  return {
    bank, placed, mono: p.looks.length - colour.length,
    extra: colour.slice(COLORS * PER).map((l) => l.name),
    lens: colour.slice(0, COLORS * PER).filter((l) => l.lens_correction).length,
  };
}
/** The OM-3 card's LOOKS.BIN for a pack. */
export const looksBin = (p: Pack, fw: Fw = OM3_FW_LATEST) => profilesBin(packToBank(p, fw).bank, fw);
/** The look as the preview should show it on the OM-3: toOm3's limits, but the halo kept (it becomes Halation). */
export const om3PreviewLook = (l: Look): Look => {
  const o = toOm3(l).look;
  return o && haloOf(l) && l.effect ? { ...o, effect: { ...l.effect } } : o ?? l;
};

/** An OM-3 bank look (from LOOKS.BIN or their links) as a shared look, with what changed. */
export function lookFromOm3(src: Look): { look: Look; changed: string[] } {
  const l: Look = { ...src, tone: { ...src.tone } }, changed: string[] = [];
  const hal = Number.isInteger(l.halation) ? Math.max(0, Math.min(5, l.halation!)) : 0;
  if (hal) {
    if (!l.effect) l.effect = { type: 'halation', strength: hal };
    else if (l.effect.type === 'bloom') {
      l.effect = { type: 'bloom', strength: l.effect.strength, tint: 'red' };
      if (l.effect.strength !== hal) changed.push(`Halation ${hal} as the halo on Glow ${l.effect.strength}`);
    } else changed.push('Halation left out (the look has Clarity)');
  }
  if (l.tone_balance) changed.push('Tone Balance left out');
  if (l.film_wb) changed.push('WB mode left out');
  if (hasCurves(l)) changed.push('RGB curves left out');
  if (l.mix?.some((x) => x)) changed.push('Color Mix left out');
  if (l.border) changed.push('Border left out');
  if (l.film_grain && l.grain_strength) changed.push(`Film Grain ${l.grain_strength} kept as ${l.grain_strength < 3 ? 'Low' : 'High'}`);
  if (l.film_grain && l.grain_size) changed.push('Grain Size left out');
  delete l.halation; delete l.tone_balance; delete l.film_wb;
  delete l.rgb; delete l.mix; delete l.border; delete l.grain_size; delete l.grain_strength;
  if (l.split) {                                    // v0.28 half steps -> whole steps
    const r = (v: number) => Math.min(5, Math.round(v));
    const s = { ...l.split, sh: r(l.split.sh), hl: r(l.split.hl) };
    if (s.sh !== l.split.sh || s.hl !== l.split.hl) changed.push('split toning half steps rounded');
    if (s.sh || s.hl) l.split = s; else delete l.split;
  }
  for (const k of ['blacks', 'whites'] as const) {
    if (Math.abs(l.tone[k]) > TONE_BW_MAX) { l.tone[k] = Math.sign(l.tone[k]) * TONE_BW_MAX; if (!changed.includes('Blacks / Whites limited to ±5')) changed.push('Blacks / Whites limited to ±5'); }
  }
  return { look: l, changed };
}
const notesOf = (rows: { look: Look; changed: string[] }[]) =>
  rows.filter((r) => r.changed.length).map((r) => `${r.look.name}: ${r.changed.join(', ')}`);

/** An OM-3 bank as a pack (empty numbers close up, so re-exporting can move looks), with what changed per look. */
export function bankImport(bank: Bank, name: string): { pack: Pack; notes: string[] } {
  const rows = bank.flat().filter((l): l is Look => !!l).map(lookFromOm3);
  return { pack: { schema: PACK_SCHEMA, name, looks: rows.map((r) => r.look), slots: {} }, notes: notesOf(rows) };
}
export const bankToPack = (bank: Bank, name: string): Pack => bankImport(bank, name).pack;
/** As their panel opens a card file: read for the firmware chosen under Export (v0.28 or later by default), so a v0.40
 *  white Border (+48 > 0) reads as a Border, not as an old Art Effect number. */
export const looksBinImport = (b: Uint8Array, name: string) => bankImport(readProfiles(b, om3Fw() >= 28), name);
export const looksBinToPack = (b: Uint8Array, name: string): Pack => looksBinImport(b, name).pack;

// Links from the OM-3 panel: op1_ one look, ob1_ a bank, base64url(deflate(JSON)).
export const isOm3Code = (t: string) => /(^|#)\s*o[pb]1_/.test(t.trim());
export async function decodeOm3Code(t: string): Promise<unknown> {
  const s = t.trim().replace(/^.*#/, '').replace(/\s+/g, '').slice(4);
  try {
    const bytes = Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/')), (c) => c.charCodeAt(0));
    const out = new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('deflate')));
    return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(await out.arrayBuffer()));
  } catch { throw new Error('This link is damaged or incomplete: copy it again.'); }
}
/** One look of their link JSON ("caduceus-om3-look/1", or older without the field) as a bank look: our parse for the
 *  shared fields, then their v0.28 / v0.30 / v0.40 fields as their panel reads them (so lookFromOm3 can report them). */
function om3JsonLook(v: unknown, what: string): Look {
  const o = (v && typeof v === 'object' ? v : {}) as Record<string, unknown>;
  if (o.schema !== undefined) {
    const m = typeof o.schema === 'string' ? /^caduceus-om3-look\/(\d+)$/.exec(o.schema) : null;
    if (!m) throw new Error(`${what}: unknown format ${JSON.stringify(o.schema)}`);
    if (Number(m[1]) > 1) throw new Error(`${what} was made with a newer OM-3 Control Panel (format ${m[1]}): it can't be opened here yet.`);
  }
  const l = parseLook(v, what), sp = parseSplit(o.split), wb = parseFilmWb(o.film_wb);
  if (sp) l.split = sp; else delete l.split;
  if (Number.isInteger(o.halation) && (o.halation as number) > 0) l.halation = Math.min(5, o.halation as number);
  if (Number.isInteger(o.tone_balance) && o.tone_balance !== 0) l.tone_balance = Math.max(-5, Math.min(5, o.tone_balance as number));
  if (wb) l.film_wb = wb;
  const rgb = parseCurves(o.rgb), mix = parseMix(o.mix);
  if (rgb) l.rgb = rgb;
  if (mix) l.mix = mix;
  if (Number.isInteger(o.border) && o.border !== 0) l.border = Math.max(-5, Math.min(5, o.border as number));
  if (o.grain_size === 1 || o.grain_size === 3) l.grain_size = o.grain_size;
  if (o.grain_strength === 1 || o.grain_strength === 4) l.grain_strength = o.grain_strength;
  return l;
}
/** A decoded op1_ link as a shared look. */
export const om3LinkLook = (v: unknown) => lookFromOm3(om3JsonLook(v, 'look'));
/** A decoded ob1_ link as a pack. */
export function om3LinkBank(v: unknown): { pack: Pack; notes: string[] } {
  const b = parseBank(v, om3JsonLook);
  return bankImport(b.bank, b.name);
}

export const om3: Target = {
  id: 'om3-caduceus',
  label: 'OM SYSTEM OM-3 (Caduceus for OM-3)',
  status: 'ready',
  doc: OM3_REPO,
  note: 'LOOKS.BIN and NAMES.BIN for the Film page (Caduceus for OM-3 v0.28 or later, v0.40 too; older versions under Export).',
  supports: (l) => (l.kind === 'colour' ? true : 'OM-3 looks are colour only.'),
  export: (pack) => [{ name: 'OM3MOD/LOOKS.BIN', data: looksBin(pack, OM3_FW_LATEST) }],
};
