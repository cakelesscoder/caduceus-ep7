import './style.css';
import { decodeLooksBin, encodeBundlesBin, hasTone, nameProblem, PackError, validatePack, type Problem, FW_LATEST, firmware, setFirmware, type Fw } from './format';
import {
  ARTS, HALO_STAGES, HALO_TINTS, MAX_LOOKS, MONO_FILTERS, NAME_MAX, NOTE_MAX, PACK_SCHEMA, SECTORS, SLOT_NAMES, TONE_KEYS, blankLook, cloneLook, lookHalo, setLookHalo,
  exportable, parseLook, parsePack, toneIsZero, toneLimit, profileOf, type FilmGrain, type Grain, type Halo, type HaloStage, type Look, type Pack, type Sharp, type SlotName, type Tone,
} from './pack';
import { History } from './history';
import { fromLibrary, libraryOrigin, migratePack, originRef, replaceRetiredLooks, resetLook, standardPack } from './reset';
import { PRESETS, defaultPreset, legacyPreset, presetById, presetOf, presetsOfKind, type PresetPack } from './packs';
import { renderLook } from './preview';
import { decodeLookCode, decodePackCode, encodeLookCode, encodePackCode, isPackCode } from './sharecode';
import { makeZip } from './zip';
import { namesBin } from './om3names';
import { COLORS, OM3, PER, SHARP, parseBank, profilesBin, sharpLabel, toOm3, validateBank, type Fw as Om3Fw } from './om3';
import { CAMERAS, type Cam } from './cameras';
import { OM3_FWS, OM3_REPO, bankToPack, decodeOm3Code, isOm3Code, looksBinToPack, om3Fw, packToBank, setOm3Fw } from './targets/om3';
import { rrpreset } from './rapidraw';
import { TARGETS, targetById } from './targets';
import { recipeCard } from './targets/recipe';
import { previewToneLut } from './tone';
import { SPLIT_COLOURS, SPLIT_MAX, hasSplit } from './split';

// ---------------------------------------------------------------- state
// Standard 1.0 = the built-in library before preset packs: saved packs from then are migrated against it (below).
const LIBRARY = legacyPreset().pack;
const STORE = 'caduceus.pack.v2', STORE_V1 = 'caduceus.pack.v1', STORE_LIB = 'caduceus.library';
// '+m2': forces one more migration pass for packs saved before tone fingerprints were handled
const LIB_VERSION: string = (legacyPreset().stamp ?? 'dev') + '+m2';
const SAMPLES = [
  { id: 'neon', label: 'Neon' }, { id: 'harbour', label: 'Harbour' }, { id: 'portrait', label: 'Portrait' },
  { id: 'forest', label: 'Forest' }, { id: 'brasserie', label: 'Night' },
];
const SWATCH = ['#e3c22f', '#e8932e', '#e0602a', '#d03434', '#c43c92', '#8a52c6', '#3d5bd0', '#3d8bd0', '#2fb2c6',
  '#2fb28c', '#45a845', '#9fc63b'];
type Tab = 'hue' | 'light' | 'sat';

let libNotice = '';   // before S: startPack() sets it
const S = {
  pack: startPack(),
  sel: 0,
  tab: 'hue' as Tab,
  image: 'harbour',
  advice: true,
  compare: false,
  grain: 'off' as FilmGrain,   // preview only: the COLOR profile's Grain (E-P7)
  browse: false,               // the editor pane shows the preset pack browser
  peek: null as { look: Look; from: string } | null,   // a preset look shown in the preview without adding it
};
const GRAIN_OPTS: [FilmGrain, string][] = [['off', 'Off'], ['low', 'Low'], ['med', 'Med'], ['high', 'High']];
const NR_OPTS: [Grain, string][] = [['off', 'Camera'], ['standard', 'Std'], ['fine', 'Low'], ['film', 'Off']];
const SHARP_OPTS: [Sharp, string][] = [['camera', 'Camera'], ['off', 'Off']];
const HALO_OPTS: [Halo, string][] = [['look', 'Look'], ['off', 'Off'], ['low', 'Low'], ['med', 'Med'], ['high', 'High']];

/** The saved pack brought up to the current built-in library (or the default preset pack for a first visit). */
function startPack(): Pack {
  const stored = loadStored();
  const swap = stored ? replaceRetiredLooks(stored, LIBRARY) : null;
  const saved = swap ? swap.pack : stored;
  if (swap?.replaced) {
    libNotice = 'Nostalgic has been replaced by Provia 400 in your saved pack.';
    try { localStorage.setItem(STORE, JSON.stringify(swap.pack)); } catch { /* private mode */ }
  }
  let prev: { version?: string; names?: string[] } = {};
  try { prev = JSON.parse(localStorage.getItem(STORE_LIB) ?? '{}'); } catch { /* none */ }
  const stamp = () => { try { localStorage.setItem(STORE_LIB, JSON.stringify({ version: LIB_VERSION, names: LIBRARY.looks.map((l) => l.name) })); } catch { /* private mode */ } };
  if (!saved) { stamp(); return standardPack(defaultPreset().pack); }
  if (prev.version === LIB_VERSION) return saved;
  const m = migratePack(saved, LIBRARY, prev.names);
  stamp();
  if (m.updated || m.added)
    libNotice = (libNotice ? libNotice + ' ' : '') + `Film library updated to v${LIB_VERSION}: ${m.updated} look${m.updated === 1 ? '' : 's'} refreshed` +
      (m.added ? `, ${m.added} added` : '') + '. Your own and edited looks are unchanged.';
  try { localStorage.setItem(STORE, JSON.stringify(m.pack)); } catch { /* private mode */ }
  return m.pack;
}

function loadStored(): Pack | null {
  try {
    const s = localStorage.getItem(STORE);
    if (s) return parsePack(JSON.parse(s));
    // v1 storage predates Look.origin: looks named like a library look are taken to be that look (for Reset look).
    const old = localStorage.getItem(STORE_V1);
    if (!old) return null;
    const p = parsePack(JSON.parse(old));
    for (const l of p.looks) if (LIBRARY.looks.some((o) => o.name === l.name)) l.origin = l.name;
    return p;
  } catch { return null; }
}
let saveTimer = 0;
function flush() { clearTimeout(saveTimer); try { localStorage.setItem(STORE, JSON.stringify(S.pack)); } catch { /* private mode */ } }
function persist() { clearTimeout(saveTimer); saveTimer = window.setTimeout(flush, 250); }
window.addEventListener('pagehide', flush);

// ---------------------------------------------------------------- undo / redo
// Every edit calls save(). Continuous edits (slider drags, typing) run inside draft(): they are saved but only become
// an undo step at the end of the gesture (the input's change event: pointer-up, blur or Enter) via checkpoint().
const hist = new History(JSON.stringify(S.pack), 200);
let drafting = false;
function save() { persist(); if (!drafting) checkpoint(); }
function draft(f: () => void) { drafting = true; try { f(); } finally { drafting = false; } }
function checkpoint() { hist.commit(JSON.stringify(S.pack)); undoUi(); }
function undoUi() {
  const u = document.getElementById('undo') as HTMLButtonElement | null, r = document.getElementById('redo') as HTMLButtonElement | null;
  if (u) u.disabled = !hist.canUndo;
  if (r) r.disabled = !hist.canRedo;
}
function step(dir: 'undo' | 'redo') {
  checkpoint();
  const s = dir === 'undo' ? hist.undo() : hist.redo();
  if (s === null) return;
  const prev = S.pack;
  S.pack = parsePack(JSON.parse(s));
  const n = S.pack.looks.length;
  const k = S.pack.looks.findIndex((l, i) => JSON.stringify(l) !== JSON.stringify(prev.looks[i]));
  S.sel = Math.max(0, Math.min(k >= 0 ? k : S.sel, n - 1));
  persist(); renderAll(); undoUi();
}
const isTextField = (t: EventTarget | null) => t instanceof HTMLTextAreaElement || (t instanceof HTMLElement && t.isContentEditable) ||
  (t instanceof HTMLInputElement && !['range', 'checkbox', 'radio', 'button', 'submit', 'reset', 'color', 'file'].includes(t.type));
document.addEventListener('keydown', (e) => {
  if (!(e.ctrlKey || e.metaKey) || e.altKey || isTextField(e.target) || document.querySelector('dialog[open]')) return;
  const k = e.key.toLowerCase();
  if (k === 'z') step(e.shiftKey ? 'redo' : 'undo');
  else if (k === 'y' && !e.shiftKey) step('redo');
  else return;
  e.preventDefault();
});
const cur = (): Look | undefined => S.pack.looks[S.sel];

// ---------------------------------------------------------------- DOM helpers
type Attrs = Record<string, unknown>;
function h<K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Attrs = {}, ...kids: (Node | string | null | false | undefined)[]): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k.startsWith('on')) el.addEventListener(k.slice(2).toLowerCase(), v as EventListener);
    else if (k === 'class') el.className = String(v);
    else if (k === 'value') (el as HTMLInputElement).value = String(v);
    else if (k === 'checked') (el as HTMLInputElement).checked = Boolean(v);
    else el.setAttribute(k, v === true ? '' : String(v));
  }
  for (const c of kids) if (c !== null && c !== false && c !== undefined) el.append(c);
  return el;
}
const $ = <T extends HTMLElement>(sel: string) => document.querySelector(sel) as T;

/** Line icons (24-unit grid, drawn with currentColor). Static markup only. */
const ICONS: Record<string, string> = {
  undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
  redo: '<path d="m15 14 5-5-5-5"/><path d="M20 9H9.5a5.5 5.5 0 0 0 0 11H13"/>',
  up: '<path d="m18 15-6-6-6 6"/>',
  down: '<path d="m6 9 6 6 6-6"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  grip: '<g fill="currentColor" stroke="none"><circle cx="9" cy="6" r="1.5"/><circle cx="15" cy="6" r="1.5"/><circle cx="9" cy="12" r="1.5"/><circle cx="15" cy="12" r="1.5"/><circle cx="9" cy="18" r="1.5"/><circle cx="15" cy="18" r="1.5"/></g>',
  packs: '<rect x="3" y="4" width="18" height="6" rx="1.5"/><rect x="3" y="14" width="18" height="6" rx="1.5"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  camera: '<path d="M14.5 4h-5L7.5 7H4a1 1 0 0 0-1 1v11a1 1 0 0 0 1 1h16a1 1 0 0 0 1-1V8a1 1 0 0 0-1-1h-3.5z"/><circle cx="12" cy="13" r="3.5"/>',
};
function icon(name: string): HTMLElement {
  const s = h('span', { class: 'ic', 'aria-hidden': 'true' });
  s.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">${ICONS[name]}</svg>`;
  return s;
}
function brandMark(): HTMLElement {
  const s = h('span', { class: 'mark', 'aria-hidden': 'true' });
  s.innerHTML = '<svg viewBox="0 0 32 32" width="26" height="26"><circle cx="16" cy="16" r="15" fill="currentColor"/>' +
    '<path d="M16 5v22M11 10c5 0 10 3 10 6s-10 3-10 6 5 4 10 4M21 10c-5 0-10 3-10 6s10 3 10 6-5 4-10 4" stroke="var(--on-accent)" stroke-width="1.8" fill="none" stroke-linecap="round"/></svg>';
  return s;
}

function download(name: string, data: Uint8Array | string, type = 'application/octet-stream') {
  const url = URL.createObjectURL(new Blob([data as BlobPart], { type }));
  const a = h('a', { href: url, download: name });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

let toastTimer = 0;
function toast(msg: string, kind: 'ok' | 'err' = 'ok') {
  const t = $('#toast');
  t.textContent = msg;
  t.className = `toast show ${kind}`;
  clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => (t.className = 'toast'), 3200);
}

function modal(title: string, body: Node, actions: (HTMLElement | null)[] = []): HTMLDialogElement {
  const dlg = h('dialog', { class: 'modal' },
    h('form', { method: 'dialog', class: 'modal-head' }, h('h2', {}, title), h('button', { class: 'icon', 'aria-label': 'Close' }, '×')),
    h('div', { class: 'modal-body' }, body),
    actions.length ? h('div', { class: 'modal-actions' }, ...actions) : null);
  dlg.addEventListener('close', () => dlg.remove());
  document.body.append(dlg);
  dlg.showModal();
  return dlg;
}

async function copy(text: string, what = 'Copied') {
  try { await navigator.clipboard.writeText(text); toast(what); } catch { toast('Copy failed: select the text and copy it by hand', 'err'); }
}

const shareBase = () => location.origin + location.pathname;

// ---------------------------------------------------------------- layout
function shell() {
  const app = $('#app');
  app.replaceChildren(
    h('div', { class: 'ambient', id: 'ambient', 'aria-hidden': 'true' }),
    h('header', { class: 'top' },
      h('div', { class: 'brand' }, brandMark(), h('span', { class: 'word' }, 'Caduceus'),
        h('span', { class: 'sub' }, 'Control Panel')),
      h('nav', { class: 'actions', 'aria-label': 'Pack' },
        h('span', { class: 'tb-group undo-btns' },
          h('button', { id: 'undo', class: 'icon', title: 'Undo (Ctrl+Z)', 'aria-label': 'Undo', disabled: true, onclick: () => step('undo') }, icon('undo')),
          h('button', { id: 'redo', class: 'icon', title: 'Redo (Ctrl+Shift+Z)', 'aria-label': 'Redo', disabled: true, onclick: () => step('redo') }, icon('redo'))),
        h('span', { class: 'tb-group' },
          menu('New', [
            ...PRESETS.map((p): [string, () => void] => [`Start from ${p.label}${p === defaultPreset() ? ' (default)' : ''}`, () => newPack(p)]),
            ['Mix looks from packs…', () => openBrowser()],
            ['Empty pack', () => newPack(null)],
          ], 'ghost'),
          h('button', { class: 'ghost', onclick: openFile }, 'Open…'),
          h('button', { class: 'ghost', onclick: pasteDialog }, 'Paste code'),
          h('button', { class: 'ghost', onclick: sharePack }, 'Share pack')),
        h('span', { class: 'tb-group' },
          h('button', { class: 'ghost', onclick: () => (CAM === 'om3' ? om3InstallDialog() : installDialog()) }, 'Install firmware'),
          h('button', { class: 'ghost', onclick: aboutDialog }, 'About'))),
      h('div', { class: 'top-end' },
        h('button', { id: 'fw-btn', class: 'cam-chip', title: 'Your camera and firmware', onclick: () => setupDialog() }, ...fwChip()),
        h('button', { class: 'primary', onclick: exportDialog }, 'Export'))),
    h('main', { class: 'layout' },
      h('aside', { class: 'pane list-pane', id: 'list' }),
      h('section', { class: 'pane preview-pane', id: 'preview' }),
      h('section', { class: 'pane editor-pane', id: 'editor' })),
    h('footer', { class: 'foot' },
      h('span', {}, 'Caduceus is an unofficial, community firmware mod. Files are made in your browser; nothing is uploaded.'),
      h('a', { href: './samples/CREDITS.md', target: '_blank', rel: 'noopener' }, 'Image credits (CC0)')),
    h('div', { id: 'toast', class: 'toast', role: 'status', 'aria-live': 'polite' }),
    h('input', { type: 'file', id: 'file', accept: '.json,application/json,.bin,.BIN', hidden: true, onchange: onFile }),
    h('input', { type: 'file', id: 'photo', accept: 'image/*', hidden: true, onchange: onPhoto }));
  buildPreview();
}

function menu(label: string, items: [string, () => void][], cls = ''): HTMLElement {
  const d = h('details', { class: `menu ${cls}` }, h('summary', {}, label, icon('down')),
    h('div', { class: 'menu-items' }, ...items.map(([t, f]) => h('button', { onclick: () => { d.open = false; f(); } }, t))));
  document.addEventListener('click', (e) => { if (!d.contains(e.target as Node)) d.open = false; });
  return d;
}

function renderAll() {
  renderList();
  renderEditor();
  schedulePreview();
}

// ---------------------------------------------------------------- look list
const SLOT_SHORT = (s: SlotName) => (s.startsWith('COLOR') ? 'C' : 'M') + s.slice(-1);
/** Can look `l` go in starter slot `s`? COLOR slots take colour looks; MONO slots take any look without a tone. */
const slotOk = (s: SlotName, l: Look) => (s.startsWith('COLOR') ? l.kind !== 'mono' : !hasTone(l));
const slotsVisible = () => CAM !== 'om3';   // BUNDLES.BIN starter slots are an E-P7 file

function renderList() {
  const el = $('#list');
  const p = S.pack;
  const problems = validatePack(p);
  const bad = new Set(problems.map((x) => x.look).filter((x) => x !== undefined));
  const n = p.looks.length;
  const mixed = new Set(p.looks.map((l) => presetOf(l)?.id).filter(Boolean)).size > 1;   // tag each look with its pack
  const inSlots = (i: number) => SLOT_NAMES.filter((s) => p.slots[s] === i);
  const ol = h('ol', { class: 'looks', 'data-drop': 'list', 'aria-label': 'Looks in this pack' }, ...p.looks.map((l, i) => {
    const slots = inSlots(i);
    const li = h('li', {
      class: `look${i === S.sel ? ' sel' : ''}${bad.has(i) ? ' bad' : ''}`, tabindex: 0, 'data-drop': 'row', 'data-i': i,
      'aria-current': i === S.sel ? 'true' : undefined,
      onclick: () => { S.sel = i; S.browse = false; S.peek = null; renderAll(); },
      onkeydown: (e: KeyboardEvent) => {
        if (e.target !== li) return;
        if (e.key === 'ArrowUp' && e.altKey) { move(i, i - 1); e.preventDefault(); }
        else if (e.key === 'ArrowDown' && e.altKey) { move(i, i + 1); e.preventDefault(); }
        else if (e.key === 'ArrowUp' && i > 0) { S.sel = i - 1; renderAll(); focusSel(); e.preventDefault(); }
        else if (e.key === 'ArrowDown' && i < n - 1) { S.sel = i + 1; renderAll(); focusSel(); e.preventDefault(); }
        else if (e.key === 'Enter' && S.browse) { S.browse = false; S.peek = null; renderAll(); e.preventDefault(); }
      },
    },
    h('span', { class: 'grip', title: 'Drag to reorder, or onto a slot' }, icon('grip')),
    h('span', { class: 'idx' }, String(i + 1)),
    h('span', { class: 'nm' }, l.name || '(no name)', mixed && presetOf(l) ? h('span', { class: 'from', title: `From ${presetOf(l)!.label}` }, presetOf(l)!.version) : null),
    h('span', { class: 'tags' },
      l.kind === 'mono' ? h('span', { class: 'kind mono', title: 'Monochrome look' }, 'B&W') : null,
      ...(slotsVisible() ? slots.map((s) => h('span', { class: 'kind slot-tag', title: `In starter slot ${s}` }, SLOT_SHORT(s))) : [])),
    h('span', { class: 'row-btns no-drag' },
      h('button', { class: 'icon', title: 'Move up (Alt+↑)', 'aria-label': `Move ${l.name} up`, disabled: i === 0, onclick: (e: Event) => { e.stopPropagation(); move(i, i - 1); } }, icon('up')),
      h('button', { class: 'icon', title: 'Move down (Alt+↓)', 'aria-label': `Move ${l.name} down`, disabled: i === n - 1, onclick: (e: Event) => { e.stopPropagation(); move(i, i + 1); } }, icon('down')),
      h('button', { class: 'icon danger', title: 'Remove', 'aria-label': `Remove ${l.name}`, onclick: (e: Event) => { e.stopPropagation(); remove(i); } }, icon('x'))));
    dragSource(li, () => ({ kind: 'row', i, look: l }), () => l.name);
    return li;
  }));
  el.replaceChildren(
    h('label', { class: 'field' }, h('span', { class: 'lbl' }, 'Pack name'),
      h('input', { type: 'text', value: p.name, maxlength: 60, oninput: (e: Event) => draft(() => { p.name = (e.target as HTMLInputElement).value; save(); }), onchange: checkpoint, onkeydown: enterCommits })),
    ...(slotsVisible() ? [slotStrip()] : []),
    h('div', { class: 'list-head' }, h('span', { class: 'lbl' }, 'Looks'), h('span', { class: n > MAX_LOOKS ? 'count over' : 'count' }, `${n} / ${MAX_LOOKS}`)),
    ol,
    ...(n === 0 ? [h('p', { class: 'empty', 'data-drop': 'list' }, 'No looks yet. Add one below, or drag one in from a preset pack.')] : []),
    h('div', { class: 'add-row' },
      menu('Add look', [
        ['Blank colour look', () => addLook(blankLook('colour', uniqueName('New Look')))],
        ['Blank mono look', () => addLook(blankLook('mono', uniqueName('New Mono')))],
        ['From a preset pack…', () => openBrowser()],
        ['Duplicate selected', () => { const l = cur(); if (l) addLook({ ...cloneLook(l), name: uniqueName(l.name) }); }],
        ['Paste a look code…', pasteDialog],
      ]),
      h('button', { class: `browse-btn${S.browse ? ' on' : ''}`, 'aria-pressed': String(S.browse), onclick: () => (S.browse ? closeBrowser() : openBrowser()) },
        icon('packs'), 'Preset packs')));
}

/** The 8 starter slots of BUNDLES.BIN: drop targets, and a menu each (the keyboard and touch way to fill them). */
function slotStrip(): HTMLElement {
  const p = S.pack;
  const tile = (s: SlotName) => {
    const k = p.slots[s], l = k === undefined ? undefined : p.looks[k];
    const sel = h('select', {
      'aria-label': `${s} starter look`, title: l ? `${s}: ${l.name}` : `${s}: stock`,
      onchange: (e: Event) => {
        const v = (e.target as HTMLSelectElement).value;
        if (v === '') delete p.slots[s]; else p.slots[s] = Number(v);
        save(); renderList();
      },
    }, h('option', { value: '' }, 'Stock'),
    ...p.looks.map((o, i) => (slotOk(s, o) || p.slots[s] === i ? h('option', { value: i, selected: k === i }, o.name) : null)));
    return h('div', { class: `slot-tile${l ? ' filled' : ''}`, 'data-drop': 'slot', 'data-slot': s },
      h('span', { class: 'slot-k' }, s.slice(-1)), sel, icon('down'));
  };
  return h('section', { class: 'slot-strip', 'aria-label': 'Starter slots' },
    h('div', { class: 'list-head' }, h('span', { class: 'lbl' }, 'Starter slots'),
      h('span', { class: 'count', title: 'Written to EP7MOD/BUNDLES.BIN when you include it on export' }, 'BUNDLES.BIN')),
    h('div', { class: 'slot-cols' },
      h('div', { class: 'slot-col' }, h('span', { class: 'slot-h' }, 'Colour'), ...SLOT_NAMES.filter((s) => s.startsWith('COLOR')).map(tile)),
      h('div', { class: 'slot-col' }, h('span', { class: 'slot-h' }, 'Mono'), ...SLOT_NAMES.filter((s) => s.startsWith('MONO')).map(tile))));
}

// ---------------------------------------------------------------- drag and drop
// One pointer-based system for mouse, pen and touch (HTML5 drag and drop does not work on most touch screens).
// Sources: looks in the pack list (reorder, or onto a slot) and looks in the preset browser (into the list or onto a
// slot). Targets carry data-drop: "row" (insert before/after), "list" (append) or "slot". Every drop has a click or
// keyboard equivalent: Alt+arrows / move buttons, the slot menus, and the browser's Add button and slot menu.
type DragSrc = { kind: 'row'; i: number; look: Look } | { kind: 'preset'; pack: PresetPack; look: Look };
interface Drag { src: DragSrc; label: string; x0: number; y0: number; x: number; y: number; on: boolean; ghost?: HTMLElement; over?: HTMLElement; after?: boolean; timer?: number; touch: boolean }
let drag: Drag | null = null;
let swallowClick = false;
const blockTouch = (e: TouchEvent) => { if (drag?.on) e.preventDefault(); };
document.addEventListener('touchmove', blockTouch, { passive: false });
document.addEventListener('click', (e) => { if (swallowClick) { e.stopPropagation(); e.preventDefault(); swallowClick = false; } }, true);

function dragSource(el: HTMLElement, src: () => DragSrc, label: () => string) {
  el.addEventListener('pointerdown', (e) => {
    if (e.button !== 0 || drag || (e.target as Element).closest('select, input, textarea, .no-drag')) return;
    const touch = e.pointerType !== 'mouse';
    const fromGrip = !!(e.target as Element).closest('.grip');
    drag = { src: src(), label: label(), x0: e.clientX, y0: e.clientY, x: e.clientX, y: e.clientY, on: false, touch };
    // Touch: the grip starts a drag at once (it has touch-action: none); anywhere else needs a long press, so the
    // page still scrolls under a finger.
    if (touch && !fromGrip) drag.timer = window.setTimeout(() => { if (drag && !drag.on) startDrag(); }, 380);
    if (touch && fromGrip) startDrag();
    document.addEventListener('pointermove', onDragMove);
    document.addEventListener('pointerup', onDragEnd);
    document.addEventListener('pointercancel', onDragCancel);
  });
}
function startDrag() {
  if (!drag) return;
  drag.on = true;
  clearTimeout(drag.timer);
  window.getSelection()?.removeAllRanges();
  drag.ghost = h('div', { class: 'drag-ghost', 'aria-hidden': 'true' }, icon('grip'), drag.label,
    drag.src.look.kind === 'mono' ? h('span', { class: 'kind mono' }, 'B&W') : null);
  document.body.append(drag.ghost);
  document.body.classList.add('dragging');
  for (const t of document.querySelectorAll<HTMLElement>('[data-drop="slot"]'))
    t.classList.toggle('cannot', !slotOk(t.dataset.slot as SlotName, drag.src.look));
  if (drag.src.kind === 'row') document.querySelectorAll('#list li.look')[drag.src.i]?.classList.add('lifted');
  try { navigator.vibrate?.(8); } catch { /* not supported */ }
  placeGhost();
  requestAnimationFrame(autoScroll);
}
function placeGhost() {
  if (!drag?.ghost) return;
  // above the finger on touch (so it stays visible), beside the cursor with a mouse
  drag.ghost.style.transform = drag.touch ? `translate(${drag.x - drag.ghost.offsetWidth / 2}px, ${drag.y - 64}px)` : `translate(${drag.x + 14}px, ${drag.y - 16}px)`;
}
const dropTarget = (x: number, y: number) => document.elementFromPoint(x, y)?.closest<HTMLElement>('[data-drop]') ?? undefined;
function onDragMove(e: PointerEvent) {
  if (!drag) return;
  drag.x = e.clientX; drag.y = e.clientY;
  if (!drag.on) {
    const d = Math.hypot(drag.x - drag.x0, drag.y - drag.y0);
    if (drag.touch) { if (d > 10) cancelDrag(); return; }     // finger moved before the long press: a scroll
    if (d < 5) return;
    startDrag();
  }
  placeGhost();
  const t = dropTarget(drag.x, drag.y);
  if (t !== drag.over) { drag.over?.classList.remove('drop-over', 'ins-before', 'ins-after'); drag.over = t; t?.classList.add('drop-over'); }
  if (t?.dataset.drop === 'row') {
    const r = t.getBoundingClientRect();
    drag.after = drag.y > r.top + r.height / 2;
    t.classList.toggle('ins-after', drag.after); t.classList.toggle('ins-before', !drag.after);
  }
}
function autoScroll() {
  if (!drag?.on) return;
  const edge = 56, list = document.querySelector<HTMLElement>('#list .looks');
  if (list && list.scrollHeight > list.clientHeight) {
    const r = list.getBoundingClientRect();
    if (drag.x >= r.left && drag.x <= r.right) {
      if (drag.y < r.top + 28 && drag.y > r.top - 40) list.scrollTop -= 8;
      else if (drag.y > r.bottom - 28 && drag.y < r.bottom + 40) list.scrollTop += 8;
    }
  }
  if (drag.y < edge) window.scrollBy(0, -12); else if (drag.y > innerHeight - edge) window.scrollBy(0, 12);
  requestAnimationFrame(autoScroll);
}
function cancelDrag() {
  if (!drag) return;
  clearTimeout(drag.timer);
  drag.ghost?.remove();
  drag.over?.classList.remove('drop-over', 'ins-before', 'ins-after');
  document.body.classList.remove('dragging');
  document.querySelectorAll('.cannot, .lifted').forEach((x) => x.classList.remove('cannot', 'lifted'));
  document.removeEventListener('pointermove', onDragMove);
  document.removeEventListener('pointerup', onDragEnd);
  document.removeEventListener('pointercancel', onDragCancel);
  drag = null;
}
function onDragCancel() { cancelDrag(); }
function onDragEnd(e: PointerEvent) {
  const d = drag;
  if (!d) return;
  const on = d.on, t = on ? dropTarget(e.clientX, e.clientY) : undefined, after = d.after;
  cancelDrag();
  if (!on) return;
  swallowClick = true;
  setTimeout(() => { swallowClick = false; }, 0);
  if (t) dropOn(d.src, t, !!after);
}
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && drag?.on) { cancelDrag(); e.preventDefault(); } });

function dropOn(src: DragSrc, t: HTMLElement, after: boolean) {
  const n = S.pack.looks.length;
  if (t.dataset.drop === 'slot') {
    const s = t.dataset.slot as SlotName;
    if (src.kind === 'row') setSlot(s, src.i);
    else presetToSlot(src.pack, src.look, s);
    return;
  }
  const at = t.dataset.drop === 'row' ? Number(t.dataset.i) + (after ? 1 : 0) : n;
  if (src.kind === 'row') { const to = at > src.i ? at - 1 : at; if (to !== src.i) move(src.i, Math.min(to, n - 1)); }
  else addPresetLook(src.pack, src.look, at);
}

/** Put look `i` of the pack in starter slot `s` (one undo step). */
function setSlot(s: SlotName, i: number) {
  const l = S.pack.looks[i];
  if (!l) return;
  if (!slotOk(s, l)) { toast(s.startsWith('COLOR') ? `"${l.name}" is a mono look: it can only go in a MONO slot.` : `"${l.name}" has a tone, so it can only go in a COLOR slot.`, 'err'); return; }
  S.pack.slots[s] = i;
  save(); renderAll();
  toast(`${s}: ${l.name}`);
}
/** Where this preset look already is in the pack (added from that pack, edited or not), or -1. */
const copyIndex = (p: PresetPack, l: Look) => S.pack.looks.findIndex((x) => { const o = originRef(x); return o?.pack === p.id && o.name === l.name; });
const presetCopy = (p: PresetPack, l: Look): Look => ({ ...fromLibrary(l, p.id), name: uniqueName(l.name) });

/** Insert a copy of a preset look at `at` (end of the list by default). */
function addPresetLook(p: PresetPack, l: Look, at = S.pack.looks.length): boolean {
  if (S.pack.looks.length >= MAX_LOOKS) { toast(`A pack holds at most ${MAX_LOOKS} looks. Remove one first.`, 'err'); return false; }
  const c = presetCopy(p, l);
  capNames([c]);
  at = Math.max(0, Math.min(at, S.pack.looks.length));
  S.pack.looks.splice(at, 0, c);
  remapSlots((k) => (k >= at ? k + 1 : k));
  S.sel = at;
  save(); renderAll();
  toast(`Added "${c.name}" from ${p.label}`);
  return true;
}
/** A preset look into a starter slot: uses the copy already in the pack, or adds one at the end. */
function presetToSlot(p: PresetPack, l: Look, s: SlotName) {
  if (!slotOk(s, l)) { toast(s.startsWith('COLOR') ? `"${l.name}" is a mono look: it can only go in a MONO slot.` : `"${l.name}" has a tone, so it can only go in a COLOR slot.`, 'err'); return; }
  let i = copyIndex(p, l);
  if (i < 0) {
    if (S.pack.looks.length >= MAX_LOOKS) { toast(`A pack holds at most ${MAX_LOOKS} looks. Remove one first.`, 'err'); return; }
    S.pack.looks.push(presetCopy(p, l));
    i = S.pack.looks.length - 1;
  }
  S.pack.slots[s] = i;
  S.sel = i;
  save(); renderAll();
  toast(`${s}: ${S.pack.looks[i].name}`);
}
/** Load a whole preset pack: add its looks that are not in the pack yet and apply its suggested slots (one undo step).
 *  When they don't fit in 32, offer to start from that pack instead. */
function loadWholePack(p: PresetPack) {
  const missing = p.pack.looks.filter((l) => copyIndex(p, l) < 0);
  if (S.pack.looks.length + missing.length > MAX_LOOKS) {
    if (!confirm(`${p.label} adds ${missing.length} looks, more than fit (${MAX_LOOKS} at most). Replace your pack with ${p.label} instead? Undo brings yours back.`)) return;
    S.pack = standardPack(p.pack);
    S.sel = 0;
    save(); renderAll();
    toast(`Pack set to ${p.label}`);
    return;
  }
  for (const l of missing) { const c = presetCopy(p, l); capNames([c]); S.pack.looks.push(c); }
  let slots = 0;
  for (const [s, k] of Object.entries(p.pack.slots) as [SlotName, number][]) {
    const l = p.pack.looks[k];
    const i = l ? copyIndex(p, l) : -1;
    if (i >= 0 && slotOk(s, S.pack.looks[i])) { S.pack.slots[s] = i; slots++; }
  }
  if (missing.length) S.sel = S.pack.looks.length - missing.length;
  save(); renderAll();
  toast(`${p.label}: ${missing.length} look${missing.length === 1 ? '' : 's'} added${slots ? `, ${slots} slot${slots === 1 ? '' : 's'} set` : ''}. Undo reverts it.`);
}

function enterCommits(e: KeyboardEvent) { if (e.key === 'Enter') checkpoint(); }
function focusSel() { ($('#list li.sel') as HTMLElement | null)?.focus(); }

/** Look names are at most NAME_MAX (12) characters on every camera (LOOKS.BIN v0.32 keeps split toning in the name
 *  tail). Longer names from files, codes or links are cut; returns how many were cut. */
function capNames(looks: Look[]): number {
  let cut = 0;
  for (const l of looks) if (l.name.length > NAME_MAX) { l.name = l.name.slice(0, NAME_MAX).trimEnd(); cut++; }
  return cut;
}
const capNote = (cut: number) => (cut ? ` ${cut} name${cut > 1 ? 's were' : ' was'} longer than ${NAME_MAX} characters and ${cut > 1 ? 'were' : 'was'} shortened.` : '');

function uniqueName(base: string): string {
  base = base.length > NAME_MAX ? base.slice(0, NAME_MAX).trimEnd() : base;
  const names = new Set(S.pack.looks.map((l) => l.name.toLowerCase()));
  if (!names.has(base.toLowerCase())) return base;
  for (let k = 2; k < 100; k++) {
    const suf = ` ${k}`, nm = base.slice(0, NAME_MAX - suf.length).trimEnd() + suf;
    if (!names.has(nm.toLowerCase())) return nm;
  }
  return base;
}

function addLook(l: Look) {
  if (S.pack.looks.length >= MAX_LOOKS) { toast(`A pack holds at most ${MAX_LOOKS} looks. Remove one first.`, 'err'); return false; }
  const cut = capNames([l]);
  S.pack.looks.push(l);
  S.sel = S.pack.looks.length - 1;
  save(); renderAll();
  if (cut) toast(`Added "${l.name}".${capNote(cut)}`, 'err');
  return true;
}
function remove(i: number) {
  const l = S.pack.looks[i];
  S.pack.looks.splice(i, 1);
  remapSlots((k) => (k === i ? undefined : k > i ? k - 1 : k));
  S.sel = Math.max(0, Math.min(S.sel, S.pack.looks.length - 1));
  save(); renderAll();
  toast(`Removed "${l.name}"`);
}
function move(from: number, to: number) {
  const n = S.pack.looks.length;
  if (to < 0 || to >= n || from === to) return;
  const [l] = S.pack.looks.splice(from, 1);
  S.pack.looks.splice(to, 0, l);
  const old = [...Array(n).keys()];               // new position -> old index
  old.splice(from, 1); old.splice(to, 0, from);
  const map = new Map(old.map((o, k) => [o, k] as [number, number]));
  remapSlots((k) => map.get(k));
  S.sel = to;
  save(); renderAll(); focusSel();
}
function remapSlots(f: (k: number) => number | undefined) {
  for (const s of SLOT_NAMES) {
    const k = S.pack.slots[s];
    if (k === undefined) continue;
    const v = f(k);
    if (v === undefined) delete S.pack.slots[s]; else S.pack.slots[s] = v;
  }
}

function newPack(preset: PresetPack | null) {
  if (!confirm(preset ? `Start from the ${preset.label} preset pack? Your current pack is replaced (Undo brings it back).`
    : 'Start an empty pack? The current pack is replaced (Undo brings it back).')) return;
  S.pack = preset ? standardPack(preset.pack) : { schema: PACK_SCHEMA, name: 'My pack', looks: [blankLook('colour', 'My Look')], slots: {} };
  S.sel = 0;
  save(); renderAll();
  toast(preset ? `Pack set to ${preset.label}` : 'Started an empty pack');
}

function resetSelected() {
  const i = S.sel, l = cur();
  if (!l) return;
  const lib = presetOf(l)?.pack ?? LIBRARY;
  S.pack.looks[i] = resetLook(l, lib, S.pack.looks.filter((_, k) => k !== i).map((o) => o.name));
  save(); renderAll();
  toast(libraryOrigin(l, lib) ? `"${S.pack.looks[i].name}" restored to its ${presetOf(l)!.label} values` : `"${l.name}" reset to neutral`);
}

// ---------------------------------------------------------------- preset pack browser
// Shown in the editor pane. Mix looks from any preset pack: drag them in, or use Add / the slot menu; a click shows a
// look in the preview without adding it.
let pickerPack = '';
function openBrowser() { S.browse = true; renderAll(); document.querySelector<HTMLElement>('#editor')?.scrollIntoView({ block: 'nearest' }); }
function closeBrowser() { S.browse = false; S.peek = null; renderAll(); }

const thumbCache = new Map<string, HTMLCanvasElement>();
let thumbSrc: { key: string; data: ImageData } | null = null;
let userPhotoN = 0;
function lookThumb(p: PresetPack, l: Look): HTMLCanvasElement {
  const key = `${S.image}${S.image === 'user' ? userPhotoN : ''}:${CAM}:${p.id}:${l.name}`;
  let c = thumbCache.get(key);
  if (c) return c;
  c = h('canvas', { class: 'pc-thumb', width: 96, height: 64, 'aria-hidden': 'true' });
  if (srcData) {
    const sk = `${S.image}${userPhotoN}`;
    if (thumbSrc?.key !== sk) {
      const t = document.createElement('canvas'), k = Math.max(96 / srcData.width, 64 / srcData.height);
      t.width = 96; t.height = 64;
      const ctx = t.getContext('2d', { willReadFrequently: true })!, w = srcData.width * k, hh = srcData.height * k;
      const full = document.createElement('canvas'); full.width = srcData.width; full.height = srcData.height;
      full.getContext('2d')!.putImageData(srcData, 0, 0);
      ctx.drawImage(full, (96 - w) / 2, (64 - hh) / 2, w, hh);
      thumbSrc = { key: sk, data: ctx.getImageData(0, 0, 96, 64) };
    }
    const ctx = c.getContext('2d')!, out = ctx.createImageData(96, 64);
    renderLook(thumbSrc.data, out, CAM === 'om3' ? toOm3(l).look ?? l : l, { advice: true, nr: cam().lookNr, grain: 'off' });
    ctx.putImageData(out, 0, 0);
    thumbCache.set(key, c);
  }
  return c;
}

function renderBrowser(el: HTMLElement) {
  const p = presetById(pickerPack) ?? defaultPreset();
  const names = new Set(S.pack.looks.map((l) => l.name.toLowerCase()));
  const full = S.pack.looks.length >= MAX_LOOKS;
  const nSlots = Object.keys(p.pack.slots).length;
  const card = (l: Look) => {
    const at = copyIndex(p, l);
    const peeked = S.peek?.look === l;
    const slotSel = slotsVisible() ? h('select', {
      class: 'pc-slot', 'aria-label': `Put ${l.name} in a starter slot`,
      onchange: (e: Event) => { const v = (e.target as HTMLSelectElement).value as SlotName; if (v) presetToSlot(p, l, v); },
    }, h('option', { value: '' }, 'Slot…'), ...SLOT_NAMES.filter((s) => slotOk(s, l)).map((s) => h('option', { value: s }, s))) : null;
    const li = h('li', { class: `pcard${peeked ? ' peek' : ''}` },
      h('button', {
        class: 'pc-main', 'aria-pressed': String(peeked), title: 'Show in the preview (drag to add)',
        onclick: () => { S.peek = peeked ? null : { look: l, from: p.label }; renderEditor(); schedulePreview(); },
      },
      lookThumb(p, l),
      h('span', { class: 'pc-text' },
        h('span', { class: 'pc-name' }, l.name,
          l.kind === 'mono' ? h('span', { class: 'kind mono' }, 'B&W') : null,
          at >= 0 ? h('span', { class: 'tag' }, `in pack · ${at + 1}`) : names.has(l.name.toLowerCase()) ? h('span', { class: 'tag' }, 'name in use') : null),
        h('span', { class: 'pc-notes' }, l.notes))),
      h('span', { class: 'pc-acts no-drag' },
        h('button', { class: 'icon', title: full ? `Your pack is full (${MAX_LOOKS})` : 'Add to your pack', 'aria-label': `Add ${l.name} to your pack`, disabled: full, onclick: () => addPresetLook(p, l) }, icon('plus')),
        slotSel));
    dragSource(li, () => ({ kind: 'preset', pack: p, look: l }), () => l.name);
    return li;
  };
  el.replaceChildren(
    h('div', { class: 'pane-head' },
      h('h2', { class: 'pane-title' }, 'Preset packs'),
      h('button', { class: 'ghost', onclick: closeBrowser }, 'Back to editor')),
    h('div', { class: 'pb-packs', role: 'radiogroup', 'aria-label': 'Preset pack' },
      ...([['library', 'Libraries'], ['mood', 'Moods']] as const).flatMap(([kind, title]) => {
        const list = presetsOfKind(kind);
        return list.length ? [h('span', { class: 'pb-group' }, title), h('div', { class: `pb-row ${kind}` }, ...list.map((q) => h('button', {
          class: `pb-pack${q.id === p.id ? ' on' : ''}`, role: 'radio', 'aria-checked': String(q.id === p.id), title: q.notes,
          onclick: () => { pickerPack = q.id; S.peek = null; renderEditor(); schedulePreview(); },
        }, h('span', { class: 'pb-name' }, kind === 'library' ? q.label : q.name), h('span', { class: 'pb-meta' }, `${q.pack.looks.length}`))))] : [];
      })),
    h('div', { class: 'pb-info' },
      h('div', {},
        h('b', {}, p.label),
        h('p', { class: 'help' }, p.notes || ' ')),
      h('button', { class: 'primary-soft', title: 'Adds the looks you don\'t have yet and fills the starter slots this pack suggests', onclick: () => loadWholePack(p) },
        'Load whole pack'),
      h('span', { class: 'help pb-sum' }, `${p.pack.looks.length} looks${slotsVisible() && nSlots ? ` · ${nSlots} suggested slots` : ''}`)),
    h('p', { class: 'help pb-how' }, slotsVisible()
      ? 'Drag a look onto a starter slot or into your list (on touch: hold, then drag). Or use + and Slot…. Click a look to preview it.'
      : 'Drag a look into your list (on touch: hold, then drag), or use +. Click a look to preview it.'),
    h('ul', { class: 'pb-looks' }, ...p.pack.looks.map(card)));
}

// ---------------------------------------------------------------- editor
function renderEditor() {
  const el = $('#editor');
  el.classList.toggle('browser', S.browse);
  document.querySelector('.layout')?.classList.toggle('browsing', S.browse);
  if (S.browse) { renderBrowser(el); return; }
  const l = cur();
  if (!l) { el.replaceChildren(h('p', { class: 'empty' }, 'Add a look to start editing.')); return; }
  const i = S.sel;
  const changed = () => { save(); schedulePreview(); refreshProblems(); refreshLookCode(); };
  const np = nameProblem(l.name);
  const nameInput = h('input', {
    type: 'text', value: l.name, maxlength: NAME_MAX, spellcheck: 'false', autocomplete: 'off', 'aria-describedby': 'name-help',
    onchange: checkpoint, onkeydown: enterCommits,
    oninput: (e: Event) => draft(() => {
      l.name = (e.target as HTMLInputElement).value;
      const p = nameProblem(l.name) ?? dupName(l, i);
      $('#name-help').textContent = p ?? `${l.name.length} / ${NAME_MAX}`;
      $('#name-help').className = p ? 'help err' : 'help';
      const row = document.querySelectorAll('#list li .nm')[i];
      if (row) row.textContent = l.name || '(no name)';
      changed();
    }),
  });
  const notesBytes = () => new TextEncoder().encode(l.notes).length;
  el.replaceChildren(
    h('div', { class: 'ed-head' },
      h('label', { class: 'field grow' }, h('span', { class: 'lbl' }, 'Name'), nameInput,
        h('span', { id: 'name-help', class: np || dupName(l, i) ? 'help err' : 'help' }, np ?? dupName(l, i) ?? `${l.name.length} / ${NAME_MAX}`)),
      h('div', { class: 'ed-btns' },
        h('button', {
          class: 'share-btn', onclick: resetSelected,
          title: presetOf(l) && libraryOrigin(l, presetOf(l)!.pack) ? `Restore the ${presetOf(l)!.label} "${libraryOrigin(l, presetOf(l)!.pack)!.name}" values` : 'Set every value to neutral',
        }, 'Reset look'),
        h('button', { class: 'share-btn', onclick: () => shareLook(l), title: 'Share this look as a short code' }, 'Share'))),
    ...(!cam().mono && l.kind === 'mono' ? [h('p', { class: 'warn' }, `The ${cam().short} editor is colour only: this look stays in your pack but is left out of the export.`)] : []),
    ...(!cam().mono && l.kind === 'colour' ? [] : [seg('Type', [['colour', 'Colour'], ['mono', 'Monochrome']], l.kind, (v) => {
      l.kind = v as Look['kind'];
      if (l.kind === 'mono') { l.art_effect = 'off'; l.advice.mono_filter ??= { colour: 'none', strength: 1 }; }
      renderList(); renderEditor(); changed();
    })]),
    l.kind === 'colour' ? sectorPanel(l, changed) : monoPanel(l, changed),
    ...(l.kind === 'colour' ? [tonePanel(l, changed)] : []),
    ...(l.kind === 'colour' ? [splitPanel(l, changed)] : []),
    ...(cam().lookNr ? [h('div', { class: 'group' },
      seg('Noise reduction', [['off', 'Camera'], ['standard', 'Standard'], ['fine', 'Low'], ['film', 'Off (most texture)'], ...(CAM === 'om3' ? [['high', 'High']] as [string, string][] : [])], l.grain, (v) => { l.grain = v as Look['grain']; renderEditor(); changed(); }))] : []),
    effectPanel(l, changed),
    wbPanel(l, changed),
    ...(l.kind === 'colour' && cam().settings ? [settingsPanel(l, changed)] : []),
    ...(l.kind === 'colour' && cam().lensCorrection ? [h('div', { class: 'group' },
      seg('Lens vignette correction', [['off', 'Off (default)'], ['on', 'Keep camera\'s']], l.lens_correction ? 'on' : 'off', (v) => {
        if (v === 'on') l.lens_correction = true; else delete l.lens_correction;
        renderEditor(); changed();
      }),
      h('span', { class: 'help' }, CAM === 'om3'
        ? 'Picking this look on the camera turns the lens\'s vignette correction off, unless you keep it here. Needs Caduceus for OM-3 v0.21 or later. Not shown in the preview.'
        : 'Picking this look on the camera turns the lens\'s vignette correction off, so corners stay natural, unless you keep it here. Needs Caduceus v0.25 or later. Change it on the camera in Extras sector 8. Not shown in the preview.'))] : []),
    ...(l.kind === 'colour' ? [h('label', { class: 'field' }, h('span', { class: 'lbl' }, 'Art Effect'),
      h('select', { onchange: (e: Event) => { l.art_effect = (e.target as HTMLSelectElement).value as Look['art_effect']; changed(); } },
        ...ARTS.filter((a) => cam().arts.includes(a) || a === l.art_effect).map((a) =>
          h('option', { value: a, selected: a === l.art_effect }, CAM === 'om3' ? artLabel(a).replace(/ \(.*\)$/, '') : artLabel(a)))),
      h('span', { class: 'help' }, CAM === 'om3' ? 'Saved in LOOKS.BIN. Not shown in the preview.' : 'Kept in the pack file, share codes and the starter BUNDLES.BIN (COLOR slots). LOOKS.BIN has no Art Effect field. Not shown in the preview.'))] : []),
    h('label', { class: 'field' }, h('span', { class: 'lbl' }, 'Notes'),
      h('textarea', {
        rows: 3, maxlength: 400, placeholder: 'What the look is for, settings advice…', onchange: checkpoint,
        oninput: (e: Event) => draft(() => {
          l.notes = (e.target as HTMLTextAreaElement).value;
          const b = notesBytes();
          $('#notes-help').textContent = `${b} / ${NOTE_MAX} bytes · kept in the pack file (not on the card)`;
          $('#notes-help').className = b > NOTE_MAX ? 'help err' : 'help';
          changed();
        }),
      }, l.notes),
      h('span', { id: 'notes-help', class: notesBytes() > NOTE_MAX ? 'help err' : 'help' }, `${notesBytes()} / ${NOTE_MAX} bytes · kept in the pack file (not on the card)`)),
    lookCodePanel(l),
    h('div', { id: 'problems' }));
  refreshProblems();
  refreshLookCode();
}

/** Per-look share code: live code with copy buttons, and a box to paste a code into this look. */
function lookCodePanel(l: Look): HTMLElement {
  const code = h('code', { id: 'look-code' });
  const help = h('span', { id: 'look-code-help', class: 'help' });
  const inp = h('input', { type: 'text', placeholder: 'Paste a look code to load it into this look', spellcheck: 'false', autocomplete: 'off' });
  const msg = h('span', { class: 'help' });
  const apply = () => {
    const t = inp.value.trim();
    if (!t) return;
    if (isPackCode(t)) { msg.className = 'help err'; msg.textContent = 'That is a pack link: use Paste code at the top.'; return; }
    try {
      const n = decodeLookCode(t), i = S.sel;
      n.notes = l.notes;                                    // codes carry no notes: keep this look's
      S.pack.looks[i] = { ...l, name: '' };                 // so the incoming name may reuse this look's
      n.name = uniqueName(n.name);
      S.pack.looks[i] = n;
      save(); renderAll();
      toast(`Loaded "${n.name}" into look ${i + 1} (Undo brings the old one back)`);
    } catch (e) { msg.className = 'help err'; msg.textContent = (e as Error).message; }
  };
  inp.addEventListener('input', () => { msg.textContent = ''; });
  inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') apply(); });
  const raw = () => { try { return encodeLookCode(cur()!); } catch { return null; } };
  return h('div', { class: 'group look-code' },
    h('span', { class: 'lbl' }, 'Look code'),
    h('div', { class: 'code-box' }, code,
      h('button', { onclick: () => { const c = raw(); if (c) copy(c, 'Code copied'); } }, 'Copy code'),
      h('button', { onclick: () => { const c = raw(); if (c) copy(`${shareBase()}#${c}`, 'Link copied'); } }, 'Copy link')),
    help,
    h('div', { class: 'code-box' }, inp, h('button', { onclick: apply }, 'Load code')),
    msg);
}
function refreshLookCode() {
  const code = document.getElementById('look-code'), help = document.getElementById('look-code-help'), l = cur();
  if (!code || !help || !l) return;
  try {
    code.textContent = encodeLookCode(l, true);
    help.className = 'help';
    help.textContent = 'Share just this look: anyone can paste the code (or open the link) in the control panel. Notes are not included.';
  } catch (e) {
    code.textContent = '—';
    help.className = 'help err';
    help.textContent = (e as Error).message;
  }
}

function dupName(l: Look, i: number): string | null {
  const j = S.pack.looks.findIndex((o, k) => k !== i && o.name.toLowerCase() === l.name.toLowerCase());
  return j >= 0 ? `Same name as look ${j + 1}.` : null;
}
const artLabel = (a: string) => ({ off: 'Off', star_light: 'Star Light', pin_hole: 'Pin Hole', blur: 'Blur (legacy: Off on v0.21+, issue #20)', white_edge: 'White Edge (legacy: Off on v0.15+)', frame: 'Frame (legacy: Off on v0.15+)' } as Record<string, string>)[a] ?? a;

function seg(label: string, opts: [string, string][], value: string, on: (v: string) => void): HTMLElement {
  return h('div', { class: 'field' }, h('span', { class: 'lbl' }, label),
    h('div', { class: 'seg', role: 'radiogroup', 'aria-label': label }, ...opts.map(([v, t]) =>
      h('button', { role: 'radio', 'aria-checked': String(v === value), class: v === value ? 'on' : '', onclick: () => on(v) }, t))));
}

function slider(min: number, max: number, value: number, on: (v: number) => void, fmt = (v: number) => (v > 0 ? `+${v}` : String(v)), aria = '') {
  const shown = Math.max(min, Math.min(max, value));   // another camera's wider value shows at this camera's limit
  const out = h('output', {}, fmt(shown));
  const inp = h('input', {
    type: 'range', min, max, step: 1, value: shown, 'aria-label': aria,
    oninput: (e: Event) => { const v = Number((e.target as HTMLInputElement).value); out.textContent = fmt(v); fillRange(inp, out); draft(() => on(v)); },
    onchange: checkpoint,
    ondblclick: () => { inp.value = '0'; out.textContent = fmt(0); fillRange(inp, out); on(0); },
  });
  fillRange(inp, out);
  return { inp, out };
}
/** Paints a range's filled part from its zero point (or its minimum) to the thumb, and marks a non-zero value. */
function fillRange(inp: HTMLInputElement, out?: HTMLElement) {
  const min = Number(inp.min), max = Number(inp.max), v = Number(inp.value), span = max - min || 1;
  const z = (Math.max(min, Math.min(max, 0)) - min) / span, p = (v - min) / span;
  inp.style.setProperty('--lo', `${Math.min(z, p) * 100}%`);
  inp.style.setProperty('--hi', `${Math.max(z, p) * 100}%`);
  out?.classList.toggle('nz', v !== Math.max(min, Math.min(max, 0)));
}

function sectorPanel(l: Look, changed: () => void): HTMLElement {
  const tabs: [Tab, string, number][] = [['hue', 'Hue', cam().hl], ['light', 'Lightness', cam().hl], ['sat', 'Saturation', cam().sat]];
  const lim = tabs.find((t) => t[0] === S.tab)![2];
  const arr = l[S.tab];
  const rows = SECTORS.map((name, k) => {
    const { inp, out } = slider(-lim, lim, arr[k], (v) => { arr[k] = v; changed(); }, undefined, `${name} ${S.tab}`);
    return h('div', { class: 'srow' }, h('span', { class: 'sw', style: `background:${SWATCH[k]}` }), h('span', { class: 'sname' }, name), inp, out);
  });
  return h('div', { class: 'group' },
    h('div', { class: 'tabs', role: 'tablist' }, ...tabs.map(([t, label]) => h('button', {
      role: 'tab', 'aria-selected': String(t === S.tab), class: t === S.tab ? 'on' : '',
      onclick: () => { S.tab = t; renderEditor(); },
    }, label, l[t].some((v) => v !== 0) ? h('span', { class: 'dot' }) : null))),
    h('div', { class: 'sectors' }, ...rows),
    h('div', { class: 'tab-foot' },
      h('span', { class: 'help' }, ...overNote(arr, lim), CAM === 'om3' ? `±${lim} per sector on the OM-3. Double-click a slider to zero it.` : S.tab === 'sat'
        ? 'A Film pick sets the camera\'s saturation from these values on Caduceus v0.24 or later, for looks with a tone. It is also stored for MONO colour slots (looks without a tone).'
        : `±${lim} per sector on the E-P7. Double-click a slider to zero it.`),
      h('button', { class: 'link', onclick: () => { arr.fill(0); renderEditor(); changed(); } }, 'Reset')));
}

/** Small live tone-curve graph: x = the stock rendering, y = with this look's tone (the camera LUT model). */
function toneCurve(tone: Tone): { svg: SVGSVGElement; draw: () => void } {
  const NS = 'http://www.w3.org/2000/svg', S0 = 200, P = 8, W = S0 - 2 * P;
  const el = <K extends keyof SVGElementTagNameMap>(t: K, a: Record<string, string | number>) => {
    const e = document.createElementNS(NS, t);
    for (const [k, v] of Object.entries(a)) e.setAttribute(k, String(v));
    return e;
  };
  const svg = el('svg', { viewBox: `0 0 ${S0} ${S0}`, width: S0, height: S0, class: 'tone-curve', role: 'img', 'aria-label': 'Tone curve: stock input to look output' });
  const X = (v: number) => P + v * W, Y = (v: number) => P + (1 - v) * W;
  svg.append(el('rect', { x: P, y: P, width: W, height: W, class: 'tc-frame' }));
  for (let i = 1; i < 4; i++) {
    svg.append(el('line', { x1: X(i / 4), y1: Y(0), x2: X(i / 4), y2: Y(1), class: 'tc-grid' }));
    svg.append(el('line', { x1: X(0), y1: Y(i / 4), x2: X(1), y2: Y(i / 4), class: 'tc-grid' }));
  }
  svg.append(el('line', { x1: X(0), y1: Y(0), x2: X(1), y2: Y(1), class: 'tc-ident' }));
  const path = el('path', { class: 'tc-curve', d: '' });
  const dB = el('circle', { r: 3.5, class: 'tc-end' }), dW = el('circle', { r: 3.5, class: 'tc-end' });
  svg.append(path, dB, dW);
  const draw = () => {
    const t = previewToneLut(tone, 128);
    let d = '';
    t.forEach((v, i) => { d += `${i ? 'L' : 'M'}${X(i / 128).toFixed(1)},${Y(v).toFixed(1)}`; });
    path.setAttribute('d', d);
    dB.setAttribute('cx', String(X(0))); dB.setAttribute('cy', String(Y(t[0])));
    dW.setAttribute('cx', String(X(1))); dW.setAttribute('cy', String(Y(t[128])));
    dB.classList.toggle('on', tone.blacks !== 0); dW.classList.toggle('on', tone.whites !== 0);
  };
  draw();
  return { svg, draw };
}

const TONE_LABEL: Record<keyof Tone, string> = { highlights: 'Highlights', shadows: 'Shadows', midtones: 'Midtones', blacks: 'Blacks', whites: 'Whites' };
function tonePanel(l: Look, changed: () => void): HTMLElement {
  const rows = TONE_KEYS.map((k) => {
    const lim = toneLimit(k);
    const { inp, out } = slider(-lim, lim, l.tone[k], (v) => { l.tone[k] = v; drawCurve(); changed(); }, undefined, TONE_LABEL[k]);
    return h('div', { class: 'srow plain' }, h('span', { class: 'sname' }, TONE_LABEL[k]), inp, out);
  });
  const { svg, draw: drawCurve } = toneCurve(l.tone);
  return h('div', { class: 'group' },
    h('div', { class: 'tone-head' }, h('span', { class: 'lbl' }, 'Tone'),
      !toneIsZero(l.tone) ? h('button', { class: 'link', onclick: () => { for (const k of TONE_KEYS) l.tone[k] = 0; renderEditor(); changed(); } }, 'Reset') : null),
    svg,
    ...rows.slice(0, 3),
    h('div', { class: 'tone-sep' }),
    ...rows.slice(3),
    h('p', { class: 'help' },
      'Highlights / Shadows / Midtones (±7): picking the look sets the profile\'s own tone settings to these. ',
      'Blacks / Whites (±5) move the ends of the tone curve (+Blacks lifts to a matte black, −Whites rolls the white point off); ',
      'they act in COLOR slots, and a look with a tone is COLOR-only (it cannot go in a MONO slot). Needs Caduceus v0.19 or later. ',
      'The graph shows stock → this look (camera tone LUT model); dots mark the Blacks and Whites ends.'),
  );
}

/** Split toning (the shared `split` field): a shadow and a highlight tint, a wheel colour and a strength each. */
function splitPanel(l: Look, changed: () => void): HTMLElement {
  const sp = () => (l.split ??= { sh_color: 0, sh: 0, hl_color: 0, hl: 0 });
  const tidy = () => { if (l.split && !l.split.sh && !l.split.hl) delete l.split; };
  const row = (label: string, ck: 'sh_color' | 'hl_color', sk: 'sh' | 'hl') => {
    const sel = h('select', { 'aria-label': `${label} colour`, onchange: (e: Event) => { sp()[ck] = Number((e.target as HTMLSelectElement).value); tidy(); changed(); } },
      ...SPLIT_COLOURS.map(([nm], k) => h('option', { value: k, selected: k === (l.split?.[ck] ?? 0) }, nm)));
    const { inp, out } = slider(-SPLIT_MAX, SPLIT_MAX, l.split?.[sk] ?? 0, (v) => { sp()[sk] = v; tidy(); changed(); }, undefined, `${label} strength`);
    return h('div', { class: 'srow split' }, h('span', { class: 'sname' }, label), sel, inp, out);
  };
  return h('div', { class: 'group' },
    h('div', { class: 'tone-head' }, h('span', { class: 'lbl' }, 'Split tone'),
      hasSplit(l) ? h('button', { class: 'link', onclick: () => { delete l.split; renderEditor(); changed(); } }, 'Reset') : null),
    row('Shadows', 'sh_color', 'sh'), row('Highlights', 'hl_color', 'hl'),
    h('p', { class: 'help' }, CAM === 'om3' ? 'Saved in LOOKS.BIN (Caduceus for OM-3 v0.26 or later). A minus strength tints toward the opposite colour.'
      : 'E-P7 v0.32 or later: picking this look on the camera sets the profile\'s split tone (LOOKS.BIN), and COLOR slots of the starter BUNDLES.BIN get it. Older firmware: not written. Look codes leave it out; pack links keep it.'));
}

function monoPanel(l: Look, changed: () => void): HTMLElement {
  const mf = (l.advice.mono_filter ??= { colour: 'none', strength: 1 });
  return h('div', { class: 'group' },
    h('p', { class: 'help' }, 'Mono looks use the camera\'s Monochrome profile; the per-sector colour sliders do not apply. Filter is advice for the camera setting (and the preview).'),
    h('label', { class: 'field' }, h('span', { class: 'lbl' }, 'Colour filter (advice)'),
      h('select', { onchange: (e: Event) => { mf.colour = (e.target as HTMLSelectElement).value as typeof mf.colour; changed(); } },
        ...MONO_FILTERS.map((c) => h('option', { value: c, selected: c === mf.colour }, c[0].toUpperCase() + c.slice(1))))),
    (() => { const { inp, out } = slider(1, 3, mf.strength, (v) => { mf.strength = v; changed(); }, String, 'Filter strength'); return h('div', { class: 'srow plain' }, h('span', { class: 'sname' }, 'Filter strength'), inp, out); })());
}

function effectPanel(l: Look, changed: () => void): HTMLElement {
  const v0 = () => (!l.effect ? 0 : l.effect.type === 'clarity' ? l.effect.strength : -l.effect.strength);
  const fmt = (x: number) => (x === 0 ? 'Off' : x < 0 ? `Glow ${-x}` : `Clarity ${x}`);
  // Halo (E-P7 0.31+ halation): a tinted glow. It shares the Glow strength: Low / Med / High = Glow 2 / 4 / 5.
  const cur = lookHalo(l);
  const stageSel = h('select', { 'aria-label': 'Halo' }, ...HALO_STAGES.map((t) => h('option', { value: t, selected: t === cur.stage }, t[0].toUpperCase() + t.slice(1))));
  const tints = HALO_TINTS.filter((t) => t === 'red' || t === 'amber' || t === cur.tint);
  const tintSel = h('select', { 'aria-label': 'Halo colour' }, ...tints.map((t) => h('option', { value: t, selected: t === cur.tint }, t[0].toUpperCase() + t.slice(1))));
  const tintRow = h('label', { class: 'field inline' }, h('span', { class: 'lbl' }, 'Halo colour'), tintSel);
  const haloRow = h('label', { class: 'field inline' }, h('span', { class: 'lbl', title: 'Red/orange glow around bright lights, like CineStill. Uses the Glow channel: Low, Med and High set Glow 2, 4 and 5.' }, 'Halo'), stageSel);
  const show = () => { haloRow.hidden = !cam().tints; tintRow.hidden = !cam().tints || (stageSel as HTMLSelectElement).value === 'off'; };
  const { inp, out } = slider(-5, 5, v0(), (x) => {
    if (x === 0) l.effect = null;
    else if (x > 0) l.effect = { type: 'clarity', strength: x };
    else {
      const keep = l.effect && l.effect.type !== 'clarity' ? l.effect : null;
      l.effect = { type: keep?.type ?? 'bloom', strength: -x, ...(keep?.tint ? { tint: keep.tint } : {}) };
    }
    (stageSel as HTMLSelectElement).value = lookHalo(l).stage;
    show();
    changed();
  }, fmt, 'Glow to clarity');
  const apply = () => {
    setLookHalo(l, (stageSel as HTMLSelectElement).value as HaloStage, (tintSel as HTMLSelectElement).value as (typeof HALO_TINTS)[number]);
    (inp as HTMLInputElement).value = String(v0());
    out.textContent = fmt(v0());
    fillRange(inp, out);
    show();
    changed();
  };
  stageSel.addEventListener('change', apply);
  tintSel.addEventListener('change', apply);
  show();
  return h('div', { class: 'group' },
    h('div', { class: 'field' }, h('span', { class: 'lbl' }, 'Glow ↔ Clarity'),
      h('div', { class: 'srow plain' }, h('span', { class: 'end' }, 'Glow'), inp, h('span', { class: 'end' }, 'Clarity'), out)),
    haloRow, tintRow);
}

function wbPanel(l: Look, changed: () => void): HTMLElement {
  const on = l.wb !== null;
  const box = h('input', {
    type: 'checkbox', checked: on,
    onchange: (e: Event) => { l.wb = (e.target as HTMLInputElement).checked ? { a_b: 0, g_m: 0 } : null; renderEditor(); changed(); },
  });
  const rows = on ? [['a_b', 'A–B', 'Amber +  /  Blue −'], ['g_m', 'G–M', 'Green +  /  Magenta −']].map(([k, label, tip]) => {
    const { inp, out } = slider(-cam().wb, cam().wb, l.wb![k as 'a_b'], (v) => { l.wb![k as 'a_b'] = v; changed(); }, undefined, label);
    return h('div', { class: 'srow plain', title: tip }, h('span', { class: 'sname' }, label), inp, out);
  }) : [];
  return h('div', { class: 'group' },
    h('label', { class: 'check' }, box, h('span', {}, 'White balance shift'),
      h('span', { class: 'help' }, !on ? (CAM === 'om3' ? 'off: no shift' : 'off: your own WB fine-tune applies') : CAM === 'om3' ? 'added to the camera\'s own WB for this look' : 'overrides the camera\'s WB fine-tune for this look')),
    ...rows,
    ...(on ? overNote([l.wb!.a_b, l.wb!.g_m], cam().wb).map((n) => h('span', { class: 'help' }, n)) : []));
}

/** Tells the user when a look made for a wider camera is being limited here. */
function overNote(vals: number[], lim: number): string[] {
  return vals.some((v) => Math.abs(v) > lim) ? [`Some values go beyond the ${cam().short}'s ±${lim}: it uses ±${lim}. Your value is kept until you move that slider. `] : [];
}

function settingsPanel(l: Look, changed: () => void): HTMLElement {
  const row = (label: string, lim: number, value: number, on: (v: number) => void, lo = -lim, fmt?: (v: number) => string) => {
    const { inp, out } = slider(lo, lim, value, on, fmt, label);
    return h('div', { class: 'srow plain' }, h('span', { class: 'sname' }, label), inp, out);
  };
  return h('div', { class: 'group' },
    h('div', { class: 'field' }, h('span', { class: 'lbl' }, 'Camera settings')),
    row('Contrast', OM3.contrast, l.advice.contrast ?? 0, (v) => { l.advice.contrast = v; changed(); }),
    row('Sharp', SHARP.hi, l.advice.sharpness ?? 0, (v) => { l.advice.sharpness = v; changed(); }, SHARP.lo, sharpLabel),
    row('Shading', OM3.shading, l.vignette, (v) => { l.vignette = v; changed(); }),
    h('span', { class: 'help' }, `Saved in the look on the ${cam().short}. Sharpness and Shading aren't shown in the preview.`));
}

function refreshProblems() {
  const el = document.getElementById('problems');
  const probs = validatePack(S.pack);
  if (el) {
    const mine = probs.filter((p) => p.look === S.sel);
    el.replaceChildren(...(mine.length ? [h('ul', { class: 'problems' }, ...mine.map((p) => h('li', {}, p.message)))] : []));
  }
  const bad = new Set(probs.map((p) => p.look));
  document.querySelectorAll('#list li.look').forEach((li, k) => li.classList.toggle('bad', bad.has(k)));
}

// ---------------------------------------------------------------- preview
let srcData: ImageData | null = null;
let userPhoto: ImageData | null = null;
let canvas: HTMLCanvasElement;
let previewQueued = false;

function buildPreview() {
  canvas = h('canvas', { class: 'pv', 'aria-label': 'Approximate preview of the selected look' });
  const thumbs = h('div', { class: 'thumbs' },
    ...SAMPLES.map((s) => h('button', { class: `thumb${S.image === s.id ? ' on' : ''}`, 'data-id': s.id, onclick: () => pickImage(s.id), title: s.label },
      h('img', { src: `./samples/${s.id}.jpg`, alt: s.label, loading: 'lazy' }))),
    h('button', { class: `thumb own${S.image === 'user' ? ' on' : ''}`, 'data-id': 'user', onclick: () => (userPhoto ? pickImage('user') : $<HTMLInputElement>('#photo').click()), title: 'Your photo (stays on this device)' },
      h('span', {}, '+ Your photo')));
  const cmp = h('button', {
    class: 'compare', title: 'Hold to see the original',
    onpointerdown: () => { S.compare = true; schedulePreview(); },
    onpointerup: () => { S.compare = false; schedulePreview(); },
    onpointerleave: () => { if (S.compare) { S.compare = false; schedulePreview(); } },
  }, 'Hold: original');
  $('#preview').replaceChildren(
    h('div', { class: 'pv-wrap' }, canvas, h('span', { class: 'badge', id: 'pv-badge' }, 'Approximate preview'), cmp),
    thumbs,
    h('div', { class: 'pv-opts' },
      h('label', { class: 'check' }, h('input', { type: 'checkbox', checked: S.advice, onchange: (e: Event) => { S.advice = (e.target as HTMLInputElement).checked; schedulePreview(); } }),
        h('span', {}, 'Include advice (contrast)')),
      h('label', { class: 'check', id: 'pv-grain', title: 'Preview only. Grain is set for each COLOR profile, not by the look.' }, h('span', {}, 'Grain'),
        h('select', { onchange: (e: Event) => { S.grain = (e.target as HTMLSelectElement).value as FilmGrain; schedulePreview(); } },
          ...GRAIN_OPTS.map(([v, t]) => h('option', { value: v, selected: v === S.grain }, t)))),
      h('button', { class: 'link', onclick: () => $<HTMLInputElement>('#photo').click() }, 'Use your own photo…')),
    h('p', { class: 'help' }, 'A rough desktop-sim port running on JPEGs, not the camera\'s pipeline: use it for direction and strength, then check on the camera. Your own photo never leaves this browser.'));
  pickImage(S.image);
}

async function pickImage(id: string) {
  S.image = id;
  document.querySelectorAll('.thumb').forEach((t) => t.classList.toggle('on', (t as HTMLElement).dataset.id === id));
  const amb = document.getElementById('ambient');
  if (amb && id !== 'user') amb.style.backgroundImage = `url("./samples/${id}.jpg")`;
  if (id === 'user') { srcData = userPhoto; schedulePreview(); if (S.browse) renderEditor(); return; }
  try {
    const img = new Image();
    img.src = `./samples/${id}.jpg`;
    await img.decode();
    srcData = toImageData(img, img.naturalWidth, img.naturalHeight);
    if (S.image === id) { schedulePreview(); if (S.browse) renderEditor(); }
  } catch { toast('Could not load the sample image', 'err'); }
}

function toImageData(img: CanvasImageSource, w: number, h0: number, max = 1024): ImageData {
  const k = Math.min(1, max / Math.max(w, h0));
  const W = Math.round(w * k), H = Math.round(h0 * k);
  const c = document.createElement('canvas');
  c.width = W; c.height = H;
  const ctx = c.getContext('2d', { willReadFrequently: true })!;
  ctx.drawImage(img, 0, 0, W, H);
  return ctx.getImageData(0, 0, W, H);
}

async function onPhoto(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0];
  (e.target as HTMLInputElement).value = '';
  if (!f) return;
  try {
    const bmp = await createImageBitmap(f, { imageOrientation: 'from-image' } as ImageBitmapOptions);
    userPhoto = toImageData(bmp, bmp.width, bmp.height);
    userPhotoN++;
    bmp.close();
    pickImage('user');
  } catch { toast('That file could not be read as an image', 'err'); }
}

function schedulePreview() {
  if (previewQueued) return;
  previewQueued = true;
  requestAnimationFrame(() => {
    previewQueued = false;
    const pg = document.getElementById('pv-grain');
    if (pg) pg.hidden = cam().lookNr;
    const badge = document.getElementById('pv-badge');
    if (badge) { badge.textContent = S.peek ? `Preview · ${S.peek.look.name} (${S.peek.from})` : 'Approximate preview'; badge.classList.toggle('peek', !!S.peek); }
    if (!srcData || !canvas) return;
    if (canvas.width !== srcData.width || canvas.height !== srcData.height) { canvas.width = srcData.width; canvas.height = srcData.height; }
    const ctx = canvas.getContext('2d')!;
    const l = S.peek?.look ?? cur();
    if (S.compare || !l) { ctx.putImageData(srcData, 0, 0); return; }
    const out = ctx.createImageData(srcData.width, srcData.height);
    renderLook(srcData, out, CAM === 'om3' ? toOm3(l).look ?? l : l, { advice: S.advice, nr: cam().lookNr, grain: cam().lookNr ? 'off' : S.grain });
    ctx.putImageData(out, 0, 0);
  });
}

// ---------------------------------------------------------------- import / export / share
function openFile() { $<HTMLInputElement>('#file').click(); }
async function onFile(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0];
  (e.target as HTMLInputElement).value = '';
  if (!f) return;
  const bytes = new Uint8Array(await f.arrayBuffer());
  const magic = bytes.length >= 4 ? String.fromCharCode(...bytes.subarray(0, 4)) : '';
  if (magic === 'OM3N') { toast('That is NAMES.BIN (name pictures). Open LOOKS.BIN instead: it holds the names too.', 'err'); return; }
  if (magic === 'OM3P') {
    try {
      const p = looksBinToPack(bytes, f.name.replace(/\.bin$/i, '') || 'LOOKS.BIN');
      replacePack(p, `Opened ${f.name} (${p.looks.length} OM-3 looks)`);
    } catch (err) { toast((err as Error).message, 'err'); }
    return;
  }
  if (magic === 'EP7B') {   // a card LOOKS.BIN
    try {
      const p = decodeLooksBin(bytes, f.name.replace(/\.bin$/i, '') || 'LOOKS.BIN');
      replacePack(p, `Opened ${f.name} (${p.looks.length} looks; LOOKS.BIN has no notes or Art Effects)`);
    } catch (err) { toast((err as Error).message, 'err'); }
    return;
  }
  try {
    const p = parsePack(JSON.parse(new TextDecoder().decode(bytes)));
    replacePack(p, `Opened "${p.name}" (${p.looks.length} looks)`);
  } catch (err) { toast(`Not a pack file or LOOKS.BIN: ${(err as Error).message}`, 'err'); }
}

function replacePack(p: Pack, msg: string) {
  const cut = capNames(p.looks);
  S.pack = p;
  S.sel = 0;
  save(); renderAll();
  const probs = validatePack(p);
  toast((probs.length ? `${msg}. ${probs.length} problem(s) to fix before export.` : `${msg}.`) + capNote(cut), probs.length || cut ? 'err' : 'ok');
}

function shareLook(l: Look) {
  let code: string;
  try { code = encodeLookCode(l); } catch (e) { toast((e as Error).message, 'err'); return; }
  const link = `${shareBase()}#${code}`;
  const grouped = encodeLookCode(l, true);
  modal(`Share "${l.name}"`, h('div', { class: 'share' },
    h('p', {}, 'Anyone can paste this code into the Caduceus Control Panel (Paste code) to get this look.'),
    h('div', { class: 'code-box' }, h('code', {}, grouped), h('button', { onclick: () => copy(code, 'Code copied') }, 'Copy code')),
    h('div', { class: 'code-box link' }, h('input', { type: 'text', readonly: true, value: link, onfocus: (e: Event) => (e.target as HTMLInputElement).select() }),
      h('button', { onclick: () => copy(link, 'Link copied') }, 'Copy link')),
    h('p', { class: 'help' }, `${code.length} characters. Carries the card values (incl. tone), name, Art Effect and mono filter; notes stay out (use a pack link for those). Dashes and case don't matter when pasting.`),
    h('div', { class: 'ex-row' },
      h('div', {}, h('b', {}, 'RapidRAW preset'), h('p', { class: 'help' }, 'This look as a .rrpreset for RapidRAW (Presets › Import), for ORF files or raws from any camera. An approximation of the camera look.')),
      h('button', { onclick: () => { const i = S.pack.looks.indexOf(l); if (i >= 0) downloadRr(i); } }, 'Download'))));
}

async function sharePack() {
  const code = await encodePackCode(S.pack);
  const link = `${shareBase()}#${code}`;
  modal('Share this pack', h('div', { class: 'share' },
    h('p', {}, `A link to the whole pack (${S.pack.looks.length} looks, notes and starter slots). Opening it loads the pack in the editor. The pack is inside the link itself: nothing is stored on the server.`),
    h('div', { class: 'code-box link' }, h('input', { type: 'text', readonly: true, value: link, onfocus: (e: Event) => (e.target as HTMLInputElement).select() }),
      h('button', { onclick: () => copy(link, 'Link copied') }, 'Copy link')),
    h('p', { class: 'help' }, `${link.length} characters. For a single look, use the Share button next to its name: much shorter.`)));
}

function pasteDialog() {
  const ta = h('textarea', { rows: 3, placeholder: 'Paste a look code (e.g. 1K7G-…) or a pack link', spellcheck: 'false' });
  const msg = h('p', { class: 'help' });
  const go = h('button', { class: 'primary' }, 'Import');
  const dlg = modal('Paste a code', h('div', {}, ta, msg), [go]);
  go.addEventListener('click', async () => {
    const r = await importCode(ta.value);
    if (r) dlg.close(); else msg.className = 'help err';
  });
  ta.addEventListener('input', () => { msg.textContent = ''; });
  importCodeMsg = (m) => (msg.textContent = m);
  ta.focus();
}
let importCodeMsg: (m: string) => void = (m) => toast(m, 'err');

async function importCode(text: string, fromLink = false): Promise<boolean> {
  const t = text.trim();
  if (!t) return false;
  try {
    if (isOm3Code(t)) {
      const v = await decodeOm3Code(t);
      if (/(^|#)\s*ob1_/.test(t)) {
        const b = parseBank(v, parseLook), p = bankToPack(b.bank, b.name);
        if (!confirm(`Open the shared OM-3 looks "${p.name}" (${p.looks.length} looks)? They replace your current pack.`)) return false;
        replacePack(p, `Opened "${p.name}"`);
        return true;
      }
      const l = parseLook(v, 'look');
      if (S.pack.looks.length >= MAX_LOOKS) { fullDialog(l); return true; }
      l.name = uniqueName(l.name);
      addLook(l);
      toast(`Added "${l.name}"`);
      return true;
    }
    if (isPackCode(t)) {
      const p = await decodePackCode(t);
      if (fromLink) return confirmPack(p);
      if (!confirm(`Open the shared pack "${p.name}" (${p.looks.length} looks)? It replaces your current pack.`)) return false;
      replacePack(p, `Opened "${p.name}"`);
      return true;
    }
    const l = decodeLookCode(t);
    if (S.pack.looks.length >= MAX_LOOKS) { fullDialog(l); return true; }
    l.name = uniqueName(l.name);
    addLook(l);
    toast(`Added "${l.name}"`);
    return true;
  } catch (e) {
    importCodeMsg((e as Error).message);
    return false;
  }
}

/** A shared look arrives while the pack already holds 32: replace one, or start a new pack with it. */
function fullDialog(l: Look) {
  const sel = h('select', { 'aria-label': 'Look to replace' }, ...S.pack.looks.map((o, i) => h('option', { value: i, selected: i === S.sel }, `${i + 1}. ${o.name}`)));
  const rep = h('button', { class: 'primary' }, 'Replace');
  const fresh = h('button', {}, 'New pack with just this look');
  const dlg = modal(`Add "${l.name}"`, h('div', {},
    h('p', {}, `Your pack is full (${MAX_LOOKS} looks, the camera's limit). Replace one of them with "${l.name}", or start a new pack.`),
    h('label', { class: 'field' }, h('span', { class: 'lbl' }, 'Replace'), sel)), [fresh, rep]);
  rep.addEventListener('click', () => {
    const i = Number(sel.value);
    const old = S.pack.looks[i].name;
    S.pack.looks[i] = { ...S.pack.looks[i], name: '' };   // so the incoming name may reuse the replaced one
    l.name = uniqueName(l.name);
    S.pack.looks[i] = l;
    S.sel = i;
    save(); renderAll(); dlg.close();
    toast(`Replaced "${old}" with "${l.name}"`);
  });
  fresh.addEventListener('click', () => {
    capNames([l]);
    S.pack = { schema: PACK_SCHEMA, name: 'My pack', looks: [l], slots: {} };
    S.sel = 0;
    save(); renderAll(); dlg.close();
    toast(`New pack with "${l.name}"`);
  });
}

function confirmPack(p: Pack): boolean {
  const yes = h('button', { class: 'primary' }, 'Open pack');
  const keep = h('button', {}, 'Keep my pack');
  const dlg = modal('Open shared pack?', h('div', {},
    h('p', {}, `"${p.name}": ${p.looks.length} looks (${p.looks.slice(0, 6).map((l) => l.name).join(', ')}${p.looks.length > 6 ? ', …' : ''}).`),
    h('p', { class: 'help' }, 'Opening it replaces the pack you are editing. Export yours first if you want to keep it.')), [keep, yes]);
  yes.addEventListener('click', () => { replacePack(p, `Opened "${p.name}"`); dlg.close(); });
  keep.addEventListener('click', () => dlg.close());
  return true;
}

const GH = 'https://github.com/cakelesscoder/caduceus-ep7';
function installDialog() {
  const link = (href: string, text: string) => h('a', { href, target: '_blank', rel: 'noopener' }, text);
  const code = (t: string) => h('code', {}, t);
  const step = (title: string, ...body: (Node | string | null)[]) => h('li', { class: 'step' }, h('b', {}, title), h('div', { class: 'step-body' }, ...body));
  const exportBtn = h('button', { onclick: () => { dlg.close(); exportDialog(); } }, 'Open Export');
  const body = h('div', { class: 'install' },
    h('p', { class: 'warn' }, h('b', {}, 'Unofficial, experimental firmware. '), 'Flashing can brick your camera; you do this at your own risk. Without the EP7MOD folder the camera is almost stock, and the restore file returns it fully to stock.'),
    h('ol', { class: 'steps' },
      step('Check your camera',
        h('p', {}, 'Olympus PEN ', h('b', {}, 'E-P7'), ' on firmware ', h('b', {}, '1.1'), ' (Setup › Firmware), a charged battery and an SD card formatted in the camera.')),
      step('Get Python 3.10+ (once)',
        h('p', {}, 'Windows / macOS: ', link('https://www.python.org/downloads/', 'python.org/downloads'), '. Windows: tick ', h('b', {}, 'Add python.exe to PATH'), '. macOS: afterwards run ', code('Install Certificates.command'), ' in the Python folder. Linux: usually already installed.')),
      step('Download Caduceus',
        h('p', {}, 'Open the ', link(`${GH}/releases/latest`, 'latest release'), ', download ', h('b', {}, 'Source code (zip)'), ' and unzip it. There is no firmware file to download: OM\'s licence means you build it yourself in the next step.')),
      step('Build (one double-click)',
        h('p', {}, 'In the unzipped folder, double-click the launcher for your system:'),
        h('ul', {},
          h('li', {}, 'Windows: ', code('Build Caduceus (Windows).bat')),
          h('li', {}, 'macOS: ', code('Build Caduceus (Mac).command'), ' (first time: right-click › Open, then Open)'),
          h('li', {}, 'Linux: ', code('build-caduceus-linux.sh'))),
        h('p', {}, 'It downloads OM\'s official 1.1 firmware, builds Caduceus, checks every file and offers to copy it to your camera card. Otherwise copy ', code('DCOLYMP'), ' and ', code('EP7MOD'), ' to the root of the card. Keep ', code('restore/'), ' on your computer.')),
      step('Your looks: LOOKS.BIN (optional)',
        h('p', {}, h('b', {}, 'Nothing to do if you\'re happy with the built-in looks.'), ' The ', code('EP7MOD/LOOKS.BIN'), ' that step 4 puts on the card already holds all 32 built-in looks (Velvia, Portra 400, CineStill 800T, Acros…).'),
        h('p', {}, 'To use your own versions instead:'),
        h('ol', { class: 'substeps' },
          h('li', {}, 'Tweak looks here in the Control Panel, or add new ones (the preview shows the effect).'),
          h('li', {}, 'Press ', h('b', {}, 'Export'), ' › ', code('LOOKS.BIN'), ' › Download.'),
          h('li', {}, 'Copy it to ', code('EP7MOD/'), ' on the card, replacing the old ', code('LOOKS.BIN'), '. Keep the name exactly ', code('LOOKS.BIN'), '.'),
          h('li', {}, 'Put the card back and half-press once: your looks are on the Film page.')),
        h('p', {}, 'No re-flash needed: swap ', code('LOOKS.BIN'), ' any time. Your saved slot choices (', code('BUNDLES.BIN'), ') stay as they are.'),
        exportBtn),
      step('Flash',
        h('p', {}, 'Put the card in the camera, hold ', h('b', {}, 'OK'), ' and switch on. Wait for the update to finish (blinking LED) and don\'t switch off meanwhile. Setup › Firmware then shows Caduceus.')),
      step('Shoot',
        h('p', {}, 'Half-press once so the looks load. Picture Mode › a Colour Profile › colour wheel, press ', h('b', {}, 'INFO'), ' until ', code('Film: <name>'), ', and turn the dial to pick a look.')))
  );
  const dlg = modal('Install the firmware', body, [
    h('a', { class: 'btn', href: `${GH}/blob/main/docs/INSTALL.md`, target: '_blank', rel: 'noopener' }, 'Full guide on GitHub'),
    h('a', { class: 'btn primary', href: `${GH}/releases/latest`, target: '_blank', rel: 'noopener' }, 'Latest release'),
  ]);
}

const STORE_FW = 'caduceus.firmware';
const FW_OPTIONS: [Fw, string, string][] = [
  [32, 'v0.32 or later', 'Everything works, including split toning on COLOR profiles (a Film pick sets it from LOOKS.BIN) and Grain, Sharp and Halo for each profile.'],
  [31, 'v0.31', 'Files work. Split toning is left out of LOOKS.BIN and BUNDLES.BIN.'],
  [28, 'v0.28 to v0.30', 'Files work. Halo for each profile is left out of BUNDLES.BIN (looks keep their halation).'],
  [27, 'v0.27', 'Files work. Sharp and Halo for each profile are left out of BUNDLES.BIN.'],
  [25, 'v0.25 or v0.26', 'Files work. Grain is left out of BUNDLES.BIN.'],
  [24, 'v0.24', 'Files work. Grain and lens vignette correction choices are left out of them.'],
  [23, 'v0.23 or v0.22', 'Files work. Grain, saturation and lens vignette correction choices are left out of them.'],
];
const STORE_CAM = 'caduceus.camera';
let CAM: Cam = 'ep7';
const cam = () => CAMERAS[CAM];
/** The camera chip: "Camera: " is dropped on narrow screens. */
const fwChip = () => { const [a, b] = fwLabel().split(': '); return [h('span', { class: 'cam-pre' }, `${a}: `), b]; };
function fwLabel() { return CAM === 'om3' ? 'Camera: OM-3' : `Camera: E-P7, v0.${firmware()}${firmware() === FW_LATEST ? '+' : ''}`; }
function saveSetup(cam: Cam, fw?: Fw) {
  CAM = cam;
  if (fw) setFirmware(fw);
  try {
    localStorage.setItem(STORE_CAM, cam);
    if (fw) localStorage.setItem(STORE_FW, String(fw));
  } catch { /* private mode */ }
  const b = document.querySelector('#fw-btn');
  if (b) b.replaceChildren(...fwChip());
  renderAll();
}
function setupDialog(first = false) {
  const on = (cam: Cam, fw?: Fw) => (cam === CAM && (cam === 'om3' || fw === firmware()) ? 'primary' : '');
  const row = (label: string, help: string, cam: Cam, fw?: Fw) => h('div', { class: 'ex-row' },
    h('div', {}, h('b', {}, label), h('p', { class: 'help' }, help)),
    h('button', { class: on(cam, fw), onclick: () => { saveSetup(cam, fw); dlg.close(); } }, 'Use this'));
  const body = h('div', { class: 'export' },
    h('p', {}, 'Which camera and Caduceus version do you have? Looks stay the same everywhere; card files are translated to match your choice. The firmware screen in the camera\'s setup menu shows the version.'),
    h('h3', {}, 'Olympus PEN E-P7'),
    h('p', { class: 'help' }, 'On anything older than v0.22, install the latest release first.'),
    ...FW_OPTIONS.map(([f, label, help]) => row(label, help, 'ep7', f)),
    h('h3', {}, 'OM SYSTEM OM-3'),
    row('Caduceus for OM-3 v0.19 or later', 'Exports OM3MOD/LOOKS.BIN and NAMES.BIN (choose your firmware version on export). The firmware is a separate project: never use E-P7 firmware on an OM-3.', 'om3'),
    h('p', { class: 'help' }, 'Other bodies aren\'t supported yet: ', h('a', { href: `${GH}/blob/main/docs/BODIES.md`, target: '_blank', rel: 'noopener' }, 'see where each one stands'), '.'));
  const dlg = modal(first ? 'Welcome to the Caduceus Control Panel' : 'Your camera', body);
}
function loadSetup() {
  let cam: string | null = null, v: string | null = null;
  try { cam = localStorage.getItem(STORE_CAM); v = localStorage.getItem(STORE_FW); } catch { return; }   // storage blocked: E-P7 latest, no pop-up
  const q = new URLSearchParams(location.search).get('camera');
  const f = Number(v) as Fw;
  if (v !== null && FW_OPTIONS.some(([x]) => x === f)) setFirmware(f);
  if (q === 'om3' || q === 'ep7') saveSetup(q);
  else if (cam === 'om3' || cam === 'ep7') { CAM = cam; $('#fw-btn').replaceChildren(...fwChip()); }
  else setupDialog(true);                              // first visit, or set up before the camera choice existed
}
function aboutDialog() {
  const link = (href: string, text: string) => h('a', { href, target: '_blank', rel: 'noopener' }, text);
  const row = (name: string, who: string, repo: string) => h('div', { class: 'ex-row' },
    h('div', {}, h('b', {}, name), h('p', { class: 'help' }, `By ${who}. Install guides and bug reports are here.`)),
    link(repo, 'Open repo'));
  modal('About Caduceus', h('div', { class: 'export' },
    h('p', {}, 'Caduceus is firmware built to extend the community\'s camera capabilities and allow full creative direction over their gear. It is unofficial and not affiliated with OM Digital Solutions.'),
    h('h3', {}, 'Your camera'),
    row('Olympus PEN E-P7', 'cakelesscoder', GH),
    row('OM SYSTEM OM-3', 'androidfanman', OM3_REPO),
    h('p', { class: 'help' }, 'Other bodies: ', link(`${GH}/blob/main/docs/BODIES.md`, 'see where each one stands'), '.'),
    h('h3', {}, 'Credits'),
    h('p', {}, 'Inspired by ', link('https://www.reddit.com/user/fischgurke/', 'u/fischgurke'), '\'s PEN-F HSL firmware mod, and built on the PEN-F research in ', link('https://github.com/fishcu/oly_fw_analysis', 'fishcu/oly_fw_analysis'), '. ', link(`${GH}#credits`, 'Full credits'), '.')));
}
function om3InstallDialog() {
  modal('Install Caduceus for OM-3', h('div', { class: 'export' },
    h('p', { class: 'warn' }, h('b', {}, 'Unofficial, experimental firmware. '), 'Flashing can brick your camera; you do this at your own risk. Never use E-P7 firmware on an OM-3.'),
    h('p', {}, 'The OM-3 firmware is its own community project by androidfanman, in the Caduceus family. Follow its guide to install it, then export your looks here with the camera set to OM-3.')),
  [h('a', { class: 'btn', href: `${OM3_REPO}/blob/main/docs/INSTALL.md`, target: '_blank', rel: 'noopener' }, 'Install guide'),
    h('a', { class: 'btn primary', href: `${OM3_REPO}/releases/latest`, target: '_blank', rel: 'noopener' }, 'Latest release')]);
}
function om3Body(): HTMLElement {
  const r = packToBank(S.pack), probs = validateBank(r.bank);
  const fname = (S.pack.name || 'pack').replace(/[^\w.-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40) || 'pack';
  const adjusted = r.placed.filter((p) => p.changed.length || p.dropped.length);
  const notes = [
    r.extra.length ? `Left out (only 20 fit; drag looks in the list to choose): ${r.extra.join(', ')}.` : '',
    r.mono ? `${r.mono} monochrome look(s) left out: the OM-3 editor is COLOR only.` : '',
    r.lens && om3Fw() < 21 ? `${r.lens} look(s) keep the lens correction: that choice needs v0.21 or later.` : '',
  ].filter(Boolean);
  const files = async () => [
    { name: 'OM3MOD/LOOKS.BIN', data: profilesBin(r.bank, om3Fw()) },
    { name: 'OM3MOD/NAMES.BIN', data: await namesBin(r.bank) as Uint8Array },
  ];
  const busy = (b: HTMLButtonElement, f: () => Promise<void>) => { b.disabled = true; f().catch((e) => toast((e as Error).message, 'err')).finally(() => { b.disabled = probs.length > 0; }); };
  const zip: HTMLButtonElement = h('button', { class: 'primary', disabled: probs.length > 0, onclick: () => busy(zip, async () => {
    const pack = { name: `${fname}.caduceus.json`, data: new TextEncoder().encode(JSON.stringify({ ...exportable(S.pack), schema: PACK_SCHEMA }, null, 1) + '\n') };
    download(`${fname}-om3-card.zip`, makeZip([...await files(), pack]), 'application/zip');
  }) }, 'Download');
  const names: HTMLButtonElement = h('button', { disabled: probs.length > 0, onclick: () => busy(names, async () => download('NAMES.BIN', (await files())[1].data)) }, 'NAMES.BIN');
  return h('div', { class: 'export' },
    probs.length
      ? h('div', { class: 'problems-box' }, h('b', {}, `${probs.length} problem(s) to fix first:`), h('ul', { class: 'problems' }, ...probs.slice(0, 12).map((p) => h('li', {}, p.message))))
      : h('p', { class: 'ok' }, `✓ ${r.placed.length} looks pass the OM-3's checks.`),
    h('label', { class: 'field' }, h('span', { class: 'lbl' }, 'Caduceus for OM-3 on the camera'),
      h('select', { onchange: (e: Event) => { const sel = e.target as HTMLSelectElement; setOm3Fw(Number(sel.value) as Om3Fw); sel.closest('dialog')?.close(); exportDialog(); } },
        ...OM3_FWS.map(([f, label]) => h('option', { value: String(f), selected: f === om3Fw() }, label))),
      h('span', { class: 'help' }, 'Older firmware refuses newer settings, so they are left out for it.')),
    h('p', { class: 'warn' }, 'This replaces the looks on the card, including ones made on the camera. To keep those, Open… the card\'s LOOKS.BIN first.'),
    ...Array.from({ length: COLORS }, (_, k) => h('p', { class: 'help' }, h('b', {}, `COLOR ${k + 1}: `),
      Array.from({ length: PER }, (_, v) => r.bank[k][v]?.name ?? 'Empty').join(' · '))),
    ...notes.map((n) => h('p', { class: 'help' }, n)),
    adjusted.length ? h('details', {}, h('summary', {}, `${adjusted.length} look(s) adjusted to fit the OM-3`),
      h('ul', { class: 'problems' }, ...adjusted.map((p) => h('li', {}, `${p.name}: ${[...p.changed.map((c) => `${c} limited or changed`), ...p.dropped.map((d) => `${d} left out`)].join(', ')}`)))) : null,
    h('div', { class: 'ex-row' },
      h('div', {}, h('b', {}, 'Card folder (.zip)'), h('p', { class: 'help' }, 'OM3MOD/LOOKS.BIN, OM3MOD/NAMES.BIN and the pack file. Unzip at the card root (never into DCOLYMP/). Keep the GUIDES.BIN and LABELS.BIN from your OM-3 release.')),
      zip),
    h('div', { class: 'ex-row' },
      h('div', {}, h('b', {}, 'Single files'), h('p', { class: 'help' }, 'Both go in OM3MOD/. NAMES.BIN holds the names the camera shows on the Film page.')),
      h('div', { class: 'ex-btns' },
        h('button', { disabled: probs.length > 0, onclick: () => download('LOOKS.BIN', profilesBin(r.bank, om3Fw())) }, 'LOOKS.BIN'),
        names)));
}

const STORE_TARGET = 'caduceus.target';
// The camera is chosen in setupDialog; this older per-export selector stays off.
const SHOW_CAMERA_SELECTOR = false;
function exportDialog() {
  if (!SHOW_CAMERA_SELECTOR) { modal(CAM === 'om3' ? 'Export for the OM-3' : 'Export', CAM === 'om3' ? om3Body() : h('div', { class: 'export' }, ep7Body())); return; }
  let target = targetById((() => { try { return localStorage.getItem(STORE_TARGET); } catch { return null; } })());
  const sel = h('select', {
    'aria-label': 'Camera',
    onchange: () => {
      target = targetById(sel.value);
      try { localStorage.setItem(STORE_TARGET, target.id); } catch { /* private mode */ }
      paint();
    },
  }, ...TARGETS.map((t) => h('option', { value: t.id, disabled: t.status !== 'ready', selected: t.id === target.id },
    t.status === 'ready' ? t.label : `${t.label} (coming soon)`)));
  const soonLinks = h('p', { class: 'help' }, 'Coming soon: ', ...TARGETS.filter((t) => t.status === 'soon').flatMap((t, i) =>
    [i ? ' · ' : '', h('a', { href: t.doc, target: '_blank', rel: 'noopener' }, t.label)]));
  const note = h('p', { class: 'help' });
  const content = h('div', {});
  const paint = () => {
    note.textContent = target.note;
    content.replaceChildren(target.id === 'recipe-card' ? recipeBody() : ep7Body());
  };
  const body = h('div', { class: 'export' },
    h('label', { class: 'field' }, h('span', { class: 'lbl' }, 'Camera'), sel, note), soonLinks, content);
  paint();
  modal('Export', body);
}

function recipeBody(): HTMLElement {
  const fname = (S.pack.name || 'pack').replace(/[^\w.-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40) || 'pack';
  const l = cur();
  const files = () => targetById('recipe-card').export(S.pack);
  return h('div', {},
    l ? h('pre', { class: 'recipe-card' }, recipeCard(l)) : null,
    h('div', { class: 'ex-row' },
      h('div', {}, h('b', {}, 'This look (.md)'), h('p', { class: 'help' }, `The card above: "${l?.name ?? ''}".`)),
      h('button', { class: 'primary', disabled: !l, onclick: () => { if (l) { const f = files()[S.sel]; download(f.name, f.data, 'text/markdown'); } } }, 'Download')),
    h('div', { class: 'ex-row' },
      h('div', {}, h('b', {}, 'All looks (.zip)'), h('p', { class: 'help' }, `${S.pack.looks.length} cards, one Markdown file per look.`)),
      h('button', {
        disabled: !S.pack.looks.length,
        onclick: () => download(`${fname}-recipes.zip`, makeZip(files().map((f) => ({ name: f.name, data: typeof f.data === 'string' ? new TextEncoder().encode(f.data) : f.data }))), 'application/zip'),
      }, 'Download')));
}

const rrName = (n: string) => n.replace(/[^\w.-]+/g, '-').replace(/^-+|-+$/g, '') || 'look';
const downloadRr = (i: number) => download(`${rrName(S.pack.looks[i].name)}.rrpreset`, rrpreset(S.pack, i), 'application/json');
const rrFiles = () => S.pack.looks.map((l, i) => ({ name: `${String(i + 1).padStart(2, '0')}-${rrName(l.name)}.rrpreset`, data: new TextEncoder().encode(rrpreset(S.pack, i)) }));
function ep7Body(): HTMLElement {
  const probs = validatePack({ ...S.pack, slots: {} });
  const slotSel = (s: SlotName) => {
    const sel = h('select', {
      onchange: (e: Event) => {
        const v = (e.target as HTMLSelectElement).value;
        if (v === '') delete S.pack.slots[s]; else S.pack.slots[s] = Number(v);
        save();
      },
    }, h('option', { value: '' }, '— stock —'),
    ...S.pack.looks.map((l, i) => (s.startsWith('COLOR') ? l.kind === 'mono' : hasTone(l)) ? null : h('option', { value: i, selected: S.pack.slots[s] === i }, `${i + 1}. ${l.name}`)).filter(Boolean) as HTMLElement[]);
    if (!s.startsWith('COLOR')) return h('label', { class: 'slot' }, h('span', {}, s), sel);
    const pick = (label: string, opts: [string, string][], key: 'grain' | 'nr' | 'sharp' | 'halo', dflt = '') => h('label', {}, h('span', {}, label),
      h('select', {
        onchange: (e: Event) => {
          const v = (e.target as HTMLSelectElement).value;
          S.pack.profiles = { ...S.pack.profiles, [s]: { ...profileOf(S.pack, s), [key]: v } };
          save();
        },
      }, ...opts.map(([v, t]) => h('option', { value: v, selected: (profileOf(S.pack, s)[key] ?? dflt) === v }, t))));
    return h('div', { class: 'slot-color' }, h('label', { class: 'slot' }, h('span', {}, s), sel),
      h('div', { class: 'slot-prof' }, pick('Grain', GRAIN_OPTS, 'grain'), pick('NR', NR_OPTS, 'nr'),
        firmware() >= 28 ? pick('Sharp', SHARP_OPTS, 'sharp', 'camera') : null,
        firmware() >= 31 ? pick('Halo', HALO_OPTS, 'halo', 'look') : null));
  };
  const withBundles = h('input', { type: 'checkbox' });
  const fname = (S.pack.name || 'pack').replace(/[^\w.-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40) || 'pack';
  const looksBin = () => {
    try { return targetById('ep7-caduceus').export(S.pack)[0].data as Uint8Array; } catch (e) { toast(e instanceof PackError ? 'Fix the problems listed first' : (e as Error).message, 'err'); return null; }
  };
  const packJson = () => JSON.stringify({ ...exportable(S.pack), schema: PACK_SCHEMA }, null, 1) + '\n';
  const body = h('div', { class: 'export' },
    probs.length
      ? h('div', { class: 'problems-box' }, h('b', {}, `${probs.length} problem(s) block LOOKS.BIN:`),
        h('ul', { class: 'problems' }, ...probs.slice(0, 12).map((p) => h('li', {}, fmtProblem(p)))))
      : h('p', { class: 'ok' }, `✓ ${S.pack.looks.length} looks pass the camera's LOOKS.BIN checks (v0.19 firmware).`),
    h('div', { class: 'ex-row' },
      h('div', {}, h('b', {}, 'LOOKS.BIN'), h('p', { class: 'help' }, 'The looks the camera\'s Film page offers (made for the firmware you chose: see the Firmware button). The firmware install already puts the 32 built-in looks on the card; download this only to use your own edits. Copy it to EP7MOD/ on the card (replacing LOOKS.BIN there) and half-press. No re-flash needed.')),
      h('button', { class: 'primary', disabled: probs.length > 0, onclick: () => { const b = looksBin(); if (b) download('LOOKS.BIN', b); } }, 'Download')),
    h('div', { class: 'ex-row' },
      h('div', {}, h('b', {}, 'Pack file (.json)'), h('p', { class: 'help' }, 'Everything, including notes and advice. Open it here later or send it to someone.')),
      h('button', { onclick: () => download(`${fname}.caduceus.json`, packJson(), 'application/json') }, 'Download')),
    h('div', { class: 'ex-row' },
      h('div', {}, h('b', {}, 'RapidRAW presets (.rrpreset)'), h('p', { class: 'help' }, 'One look, or every look as its own preset in a zip, for ORF files or raws from any camera. Unzip, then in RapidRAW: Presets › Import and select the files. Approximate: RapidRAW starts from its own raw rendering, so expect the look\'s character, not an exact match to the camera JPEG.')),
      h('div', { class: 'ex-btns' },
        h('button', { disabled: !cur(), onclick: () => { if (cur()) downloadRr(S.sel); } }, 'This look'),
        h('button', { disabled: !S.pack.looks.length, onclick: () => download(`${fname}-rapidraw.zip`, makeZip(rrFiles()), 'application/zip') }, `All ${S.pack.looks.length} (.zip)`))),
    h('details', { class: 'ex-bundles' },
      h('summary', {}, 'Starter slots (BUNDLES.BIN, optional)'),
      h('p', { class: 'help' }, 'BUNDLES.BIN holds the looks currently in the 8 picture-mode slots. Your card\'s BUNDLES.BIN has your saved slot choices: only replace it if you want to reset them. Empty = the camera\'s stock rendering.'),
      h('p', { class: 'help' }, 'Grain and NR belong to each COLOR profile, not to a look: picking a look keeps them. On the camera: Extras sector 1 (Grain) and 9 (NR). Grain needs v0.27 or later.'),
      h('div', { class: 'slots' }, ...SLOT_NAMES.map(slotSel))),
    h('div', { class: 'ex-row' },
      h('div', {}, h('b', {}, 'Card folder (.zip)'), h('p', { class: 'help' }, 'EP7MOD/LOOKS.BIN (+ BUNDLES.BIN if ticked) and the pack file. Unzip at the card root.'),
        h('label', { class: 'check' }, withBundles, h('span', {}, 'Include starter BUNDLES.BIN'))),
      h('button', {
        disabled: probs.length > 0, onclick: () => {
          const lb = looksBin();
          if (!lb) return;
          const files = [{ name: 'EP7MOD/LOOKS.BIN', data: lb }];
          if (withBundles.checked) {
            try { files.push({ name: 'EP7MOD/BUNDLES.BIN', data: encodeBundlesBin(S.pack) }); } catch (e) { toast((e as Error).message, 'err'); return; }
          }
          files.push({ name: `${fname}.caduceus.json`, data: new TextEncoder().encode(packJson()) });
          download(`${fname}-card.zip`, makeZip(files), 'application/zip');
        },
      }, 'Download')),
    h('p', { class: 'help' }, 'Copy EP7MOD/ to the root of the card (never into DCOLYMP/). The camera checks every file and ignores one that fails.'));
  return body;
}
const fmtProblem = (p: Problem) => (p.look !== undefined ? `Look ${p.look + 1} (${S.pack.looks[p.look]?.name || 'no name'}): ` : '') + p.message;

// ---------------------------------------------------------------- start
async function handleHash() {
  const code = decodeURIComponent(location.hash.slice(1));
  if (!code) return;
  history.replaceState(null, '', location.pathname + location.search);
  importCodeMsg = (m) => toast(`Link: ${m}`, 'err');
  await importCode(code, true);
  importCodeMsg = (m) => toast(m, 'err');
}

shell();
renderAll();
loadSetup();
if (libNotice) toast(libNotice);
undoUi();
handleHash();
window.addEventListener('hashchange', handleHash);
