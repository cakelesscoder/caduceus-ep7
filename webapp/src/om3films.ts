// Vendored from androidfanman/caduceus-om3 @ 87b3e6f (Apache-2.0, see NOTICE), unchanged. Update by copying; our glue is in ./targets/om3.ts.
// The film sims for the OM-3: our own looks, designed by hand from public descriptions of each film and tuned by eye
// (scripts/films.py makes src/data/om3films.json from short recipes). Each becomes an ordinary OM-3 look: Hue / Light
// / Saturation per sector, Highlights / Shadows / Midtones, Blacks / Whites, Contrast, Sharp and the WB shift. No grain,
// Glow / Clarity or Art Effects: those stay the user's choice.
import filmsJson from './data/om3films.json';
import { blankLook, type Look } from './pack';

export interface Film {
  name: string; group: FilmGroup; film: string; desc: string;
  hue: number[]; light: number[]; sat: number[];
  tone: Look['tone']; contrast: number; wb: { a_b: number; g_m: number } | null;
  sharp: number;   // firmware v0.22 Sharp, the camera's numbers (0 = its normal)
  split?: { sh_color: number; sh: number; hl_color: number; hl: number };   // v0.26 split toning
}
export type FilmGroup = 'fuji' | 'slide' | 'neg' | 'instant' | 'print';
export const FILM_GROUPS: [FilmGroup, string][] = [
  ['fuji', 'Fujifilm simulations'], ['slide', 'Slide film'], ['neg', 'Colour negative'], ['instant', 'Instant film'], ['print', 'Cinema print'],
];
const DATA = filmsJson as { films: Film[]; aliases: Record<string, string>; camera: string[] };
export const FILMS = DATA.films;
/** The 20 films for the camera, FILM 1-20 in the owner's order (scripts/films.py CAMERA). */
export const CAMERA_FILMS: Film[] = DATA.camera.map((n) => FILMS.find((f) => f.name === n)!);

/** A look's film sim, from its origin (`film:<name>`, set when it was added) or, for looks added before origins, its
 *  unchanged name. Renamed or edited looks keep their origin. Names from earlier versions of the list map to the film
 *  that replaced them. */
export const FILM_ORIGIN = 'film:';
export const filmByName = (name: string) => FILMS.find((f) => f.name === (DATA.aliases[name] ?? name));
export function filmOf(l: Look): Film | undefined {
  if (l.origin?.startsWith(FILM_ORIGIN)) return filmByName(l.origin.slice(FILM_ORIGIN.length));
  return l.origin === undefined ? filmByName(l.name) : undefined;
}

/** The film as an OM-3 look (no grain or Extras: those stay the user's choice). */
export function filmLook(f: Film): Look {
  const l = blankLook('colour', f.name);
  l.origin = FILM_ORIGIN + f.name;
  l.hue = [...f.hue]; l.light = [...f.light]; l.sat = [...f.sat];
  l.tone = { ...f.tone };
  l.advice = { contrast: f.contrast, sharpness: f.sharp ?? 0 };
  l.wb = f.wb ? { ...f.wb } : null;
  if (f.split) l.split = { ...f.split };
  l.notes = f.desc;
  return l;
}
