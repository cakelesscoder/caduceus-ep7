// The released v0.24 card LOOKS.BIN plus the 0.31h2 preset halation (bundles/library_v3.json): Portra 400 and
// Polaroid get a warm halo (bloom tint +47 = 3), Gold 200 a Low amber halo (bloom 1, tint 2). Everything else is the
// released file byte for byte, so the old file stays the reference for every other look.
import { readFileSync } from 'node:fs';
import { crc32 } from '../src/format';

export const HALATION_EDITS: Record<string, [number, number][]> = {
  'Portra 400': [[47, 3]],
  'Gold 200': [[28, 1], [29, 1], [47, 2]],
  Polaroid: [[47, 3]],
};

export function releaseLooksWithHalation(path: string): Uint8Array {
  const d = new Uint8Array(readFileSync(path));
  const n = (d.length - 64) / 64;
  for (let j = 0; j < n; j++) {
    const r = d.subarray(64 + 64 * j, 128 + 64 * j);
    const name = new TextDecoder().decode(r.subarray(48, 48 + r.subarray(48).indexOf(0)));
    for (const [o, v] of HALATION_EDITS[name] ?? []) r[o] = v;
  }
  new DataView(d.buffer, d.byteOffset).setUint32(16, crc32(d.subarray(0, 16), d.subarray(20)), true);
  return d;
}
