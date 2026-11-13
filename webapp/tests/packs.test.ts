// Preset packs (src/packs.ts, docs/PACKS.md): each one exports valid card files; origins keep old saves working.
import { describe, expect, it } from 'vitest';
import { checkBundlesBin, checkLooksBin, encodeBundlesBin, encodeLooksBin, validatePack } from '../src/format';
import { DEFAULT_PRESET, PRESETS, presetOf, presetsOfKind } from '../src/packs';
import { libraryOrigin, resetLook, standardPack } from '../src/reset';
import { targetById } from '../src/targets';

describe('preset packs', () => {
  it('ids are unique and the default is Standard 1.1', () => {
    expect(new Set(PRESETS.map((p) => p.id)).size).toBe(PRESETS.length);
    expect(DEFAULT_PRESET).toBe('standard-1.1');
    expect(presetsOfKind('library').map((p) => p.label)).toEqual(['Standard 1.1', 'Standard 1.0']);
    expect(presetsOfKind('mood').map((p) => p.name)).toEqual(['Tokyo Nights', 'Tokyo Days', 'Autumn', 'Summer', 'Winter', 'Film Noir']);
  });

  for (const p of presetsOfKind('mood')) it(`${p.label}: a small themed pack with starter slots, no profile settings`, () => {
    expect(p.notes.length).toBeGreaterThan(0);
    expect(p.pack.looks.length).toBeGreaterThanOrEqual(4);
    expect(p.pack.looks.length).toBeLessThanOrEqual(8);
    expect(Object.keys(p.pack.slots).length).toBeGreaterThan(0);
    expect(p.pack.profiles).toBeUndefined();
    for (const l of p.pack.looks) expect((l as { film_grain?: unknown }).film_grain).toBeUndefined();
  });

  for (const p of PRESETS) it(`${p.label}: valid LOOKS.BIN, BUNDLES.BIN and OM-3 export`, () => {
    expect(validatePack(p.pack)).toEqual([]);
    expect(checkLooksBin(encodeLooksBin(p.pack))).toEqual([]);
    expect(checkBundlesBin(encodeBundlesBin(p.pack))).toEqual([]);
    expect(targetById('om3-caduceus').export(p.pack)[0].data.length).toBeGreaterThan(0);
  });

  it('a look added from 1.1 resets to 1.1; a pre-pack save (plain origin) stays Standard 1.0', () => {
    const p11 = PRESETS.find((p) => p.id === 'standard-1.1')!, p10 = PRESETS.find((p) => p.id === 'standard-1.0')!;
    const mine = standardPack(p11.pack);
    const l = mine.looks.find((x) => x.name === 'Polaroid')!;
    expect(presetOf(l)?.id).toBe('standard-1.1');
    expect(libraryOrigin(l, p10.pack)).toBeUndefined();
    l.hue[0] = 3;
    expect(resetLook(l, p11.pack).split).toEqual(p11.pack.looks.find((x) => x.name === 'Polaroid')!.split);
    const old = { ...standardPack(p10.pack).looks[0], origin: 'Velvia' };
    expect(presetOf(old)?.id).toBe('standard-1.0');
  });
});
