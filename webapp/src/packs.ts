// Preset look packs: one data file each in ./data/packs (docs/PACKS.md). A preset pack is camera-neutral, in the
// shared pack format (caduceus-pack/1) plus id / name / version; each export target translates it like any other pack.
// A new pack = one more JSON file, imported and listed here. Packs are frozen once released: a revision is a new file
// (a new version), so looks people saved from an older pack keep their values and their Reset look.
import std10 from './data/packs/standard-1.0.json';
import std11 from './data/packs/standard-1.1.json';
import { parsePack } from './pack';
import { LEGACY_PACK, originRef, type Library } from './reset';
import type { Look } from './pack';

export interface PresetPack {
  id: string;          // stable: written into the origin of looks added from it ("pack:<id>:<name>")
  name: string;        // "Standard"
  version: string;     // "1.1"
  label: string;       // "Standard 1.1"
  notes: string;
  stamp?: string;      // Standard 1.0 only: the old library build stamp (src/main.ts migration of pre-pack saves)
  pack: Library;
}

function preset(j: unknown): PresetPack {
  const m = j as { id: string; name: string; version: string; notes?: string; stamp?: string };
  const p = parsePack(j);
  return { id: m.id, name: m.name, version: m.version, label: `${m.name} ${m.version}`, notes: m.notes ?? '', stamp: m.stamp,
    pack: { ...p, name: `${m.name} ${m.version}`, id: m.id } };
}

/** Newest first (the order of the pickers). */
export const PRESETS: PresetPack[] = [preset(std11), preset(std10)];
export const DEFAULT_PRESET = 'standard-1.1';
export const presetById = (id: string | undefined): PresetPack | undefined => PRESETS.find((p) => p.id === id);
export const defaultPreset = (): PresetPack => presetById(DEFAULT_PRESET)!;
/** Standard 1.0 = the built-in library of the app before packs (looks saved then name it by a plain origin). */
export const legacyPreset = (): PresetPack => presetById(LEGACY_PACK)!;
/** The preset pack a look was added from, if any. */
export const presetOf = (l: Look): PresetPack | undefined => presetById(originRef(l)?.pack);
