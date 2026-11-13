// Preset look packs: one data file each in ./data/packs (docs/PACKS.md). A preset pack is camera-neutral, in the
// shared pack format (caduceus-pack/1) plus id / name / version; each export target translates it like any other pack.
// A new pack = one more JSON file, imported and listed here. Packs are frozen once released: a revision is a new file
// (a new version), so looks people saved from an older pack keep their values and their Reset look.
import std10 from './data/packs/standard-1.0.json';
import std11 from './data/packs/standard-1.1.json';
import tokyoNights from './data/packs/tokyo-nights-1.0.json';
import tokyoDays from './data/packs/tokyo-days-1.0.json';
import autumn from './data/packs/autumn-1.0.json';
import summer from './data/packs/summer-1.0.json';
import winter from './data/packs/winter-1.0.json';
import filmNoir from './data/packs/film-noir-1.0.json';
import { parsePack } from './pack';
import { LEGACY_PACK, originRef, type Library } from './reset';
import type { Look } from './pack';

/** 'library': a full look library (Standard). 'mood': a small themed collection (4-8 looks) with ready starter slots. */
export type PresetKind = 'library' | 'mood';

export interface PresetPack {
  id: string;          // stable: written into the origin of looks added from it ("pack:<id>:<name>")
  name: string;        // "Standard"
  version: string;     // "1.1"
  label: string;       // "Standard 1.1"
  kind: PresetKind;    // pack file `kind`, default 'library'
  notes: string;       // one-line description
  stamp?: string;      // Standard 1.0 only: the old library build stamp (src/main.ts migration of pre-pack saves)
  pack: Library;
}

function preset(j: unknown): PresetPack {
  const m = j as { id: string; name: string; version: string; kind?: PresetKind; notes?: string; stamp?: string };
  const p = parsePack(j);
  return { id: m.id, name: m.name, version: m.version, label: `${m.name} ${m.version}`, kind: m.kind === 'mood' ? 'mood' : 'library',
    notes: m.notes ?? '', stamp: m.stamp,
    pack: { ...p, name: `${m.name} ${m.version}`, id: m.id } };
}

/** The order of the pickers: libraries newest first, then the mood packs (docs/PACKS.md "Mood packs"). */
export const PRESETS: PresetPack[] = [preset(std11), preset(std10),
  ...[tokyoNights, tokyoDays, autumn, summer, winter, filmNoir].map(preset)];
export const presetsOfKind = (kind: PresetKind): PresetPack[] => PRESETS.filter((p) => p.kind === kind);
export const DEFAULT_PRESET = 'standard-1.1';
export const presetById = (id: string | undefined): PresetPack | undefined => PRESETS.find((p) => p.id === id);
export const defaultPreset = (): PresetPack => presetById(DEFAULT_PRESET)!;
/** Standard 1.0 = the built-in library of the app before packs (looks saved then name it by a plain origin). */
export const legacyPreset = (): PresetPack => presetById(LEGACY_PACK)!;
/** The preset pack a look was added from, if any. */
export const presetOf = (l: Look): PresetPack | undefined => presetById(originRef(l)?.pack);
