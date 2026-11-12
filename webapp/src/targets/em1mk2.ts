// Olympus OM-D E-M1 Mark II with Caduceus: exports EM1MOD/LOOKS.BIN.
// Since firmware v0.3 the E-M1 II reads the E-P7 LOOKS.BIN v3 file unchanged (it ignores the E-P7-only header
// fields), so this target uses the shared encoder: one look format and one file for both cameras.
// v0.1-v0.2 firmware read a different 'EM1B' file (128-byte slots + Color Creator vivid/hue); that format is retired.
//
// What the firmware applies (v0.3b5, camera-confirmed): 12-sector saturation, per-sector hue and light (E-P7 COLOR
// engine behind Color Creator) and the tone block's highlights / midtones / shadows. Not yet: WB shift, effects,
// vignette, grain, blacks/whites, and true B&W for mono looks (they render as low-vividness Color Creator).
// toEm1() translates a look to what the camera renders, for the preview only; the look itself is never changed.
import { encodeLooksBin } from '../format';
import type { Pack, Look } from '../pack';
import type { Target } from './types';

export const EM1_REPO_DOC = 'docs/PORT_EM1MK2.md';

export function encodeEm1LooksBin(pack: Pack): Uint8Array {
  return encodeLooksBin(pack);
}

/** The parts of a look the E-M1 II firmware ignores today (for help text). */
export function em1Dropped(l: Look): string[] {
  const out: string[] = [];
  if (l.kind === 'mono') out.push('black & white (renders as low-saturation colour)');
  if (l.wb && (l.wb.a_b || l.wb.g_m)) out.push('WB shift');
  if (l.effect) out.push('effect');
  if (l.vignette) out.push('vignette');
  if (l.grain && l.grain !== 'off') out.push('grain / NR');
  if (l.kind === 'colour' && (l.tone?.blacks || l.tone?.whites)) out.push('blacks / whites');
  return out;
}

/** The look as the E-M1 II renders it (preview only). */
export function toEm1(l: Look): Look {
  const z = new Array<number>(12).fill(0);
  if (l.kind === 'mono') {
    // Color Creator vividness -4: strongly desaturated colour, no tone block (mono looks carry none in LOOKS.BIN)
    return { ...l, kind: 'colour', sat: new Array<number>(12).fill(-5), hue: z, light: z.slice(), wb: null, effect: null,
      vignette: 0, grain: 'off', tone: { ...l.tone, highlights: 0, midtones: 0, shadows: 0, blacks: 0, whites: 0 } };
  }
  return { ...l, wb: null, effect: null, vignette: 0, grain: 'off', tone: { ...l.tone, blacks: 0, whites: 0 } };
}

export const em1mk2: Target = {
  id: 'em1mk2-caduceus',
  label: 'Olympus OM-D E-M1 Mark II (Caduceus)',
  status: 'ready',
  note: 'EM1MOD/LOOKS.BIN (same file as the E-P7); needs E-M1 II firmware v0.3 or later.',
  supports(_look) {
    return true;
  },
  export: (pack) => [{ name: 'EM1MOD/LOOKS.BIN', data: encodeEm1LooksBin(pack) }],
};
