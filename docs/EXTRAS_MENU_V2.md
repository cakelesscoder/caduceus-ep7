# Extras menu v2: design (E-P7 1.1)

Design only (2026-11-12): nothing built, no camera, no REA run. Base: v0.31d.
Sources: LOOK_EXTRAS, LOOK_EDITOR §6, LOOK_MENUS, FILM_MENU_V2, HALATION_RED §16–17, GRAIN_PORT, SHARPENING_OFF,
TONE_ENDS, SPLIT_TONE, RE_UI, RE_AE, ATLAS, CODE_SPACE_MAP, CHANGELOG.
[V] = stated as verified in those docs. [I] = inference. [?] = open.

**Recommendation (hybrid, option C):**
- **Anything stored per slot stays on the colour wheel.** The one Extras page becomes four themed pages: Effects,
  Colour, Tone and Profile.
- **Anything global goes to a new Setup Menu › Caduceus page**, built from stock item kinds (RE_UI §7).
- The rule the user sees: the wheel holds this profile's look and its own settings, and the menu holds camera-wide
  settings. The Profile page also makes the look/profile split visible: a pick never changes anything on it.

## 1. Inventory (v0.31d)

Slot = 64-B BUNDLES.BIN slot (COLOR1–4); MOVIE.BIN / AP.BIN use the same layout. **Look** = a Film pick sets it and
it counts for the `*` marker. **Profile** = your own choice, which a pick, Own, Stock or a reset never changes.

| # | Setting | Owner | Storage | Range (camera UI) | Edited today | LV |
|---|---|---|---|---|---|---|
| – | Film pick | look | whole slot entry, from LOOKS.BIN | library + Own + Stock | wheel page **Film** (INFO 0) | Film page polygon |
| – | Saturation ×12 | look (since v0.24) | stock sids 927–962 / 1655–1666 | −5..+5 | wheel **Saturation** / **Sat·All** (stock) | yes (stock) |
| – | Hue ×12, Light ×12 | look | +0..11, +12..23 | −5..+5 (file −7..7) | wheel **Hue**, **Light** | no |
| – | Highlight / Shadow / Midtone | look | stock tone settings | stock | stock tone screen | yes |
| X1 | **Grain** | **profile** | +50 | Off / Low / Med / High | Extras sector 1 | no (stills) |
| X2 | Glow− / Clarity+ | look | +28 id, +29 strength | −5..+5 (−: bloom 5..1, +: clarity 1..5) | Extras 2 | no |
| X3 | WB A–B | look | +26, override bit +25.0 | −5..+5 (file ±7) | Extras 3 | untraced |
| X4 | WB G–M | look | +27, +25.0 | −5..+5 (file ±7) | Extras 4 | untraced |
| X5 | Art | look | +46 | Off / Star Light / Pin Hole (Blur retired) | Extras 5 | yes (lv_art) |
| X6 | Blacks | look | +47 | −5..+5 | Extras 6 | yes |
| X7 | Whites | look | +48 | −5..+5 | Extras 7 | yes |
| X8 | VigFix (lens shading) | look | +49 | Off / Camera | Extras 8 | [?] |
| X9 | **NR** | **profile** | +24 | Camera / Std / Low / Off | Extras 9 | no |
| X10 | **Sharp** | **profile** | +51 | Camera / Off | Extras 10 | [?] |
| X11 | Halo | the look's value, with a per-profile override | +52 (0 = the look's) | Look / Off / Low / Med / High | Extras 11 | no |
| X12 | – | – | – | `Extras: 1-11 only` | – | – |
| – | Bloom/halo tint | look | +45 | 0..4 | Panel only | – |
| – | Movie slot, AP slot | as COLOR | MOVIE.BIN, AP.BIN | same pages | Movie: LC INFO; AP: SCP INFO | Grain, Glow, Art and Halo locked (`…: stills`) |
| – | LCD tint, Lowest S/S, arrow-key functions | global | stock sids (Monitor Adjust, 1147, 51/53) | stock lists | stock menus | – |

**Coming** (no UI yet):

| Field | Owner | Shared format | Proposed home |
|---|---|---|---|
| Split tone: shadow colour, shadow amount, highlight colour, highlight amount | look | `split {sh_color 0..11, sh −5..5, hl_color 0..11, hl −5..5}`, already in packs and `pk1_`. OM-3 stores it at record +53..+56 | Colour page |
| Framing grid on/off + style | **global** | none (not a look field) | Caduceus menu, Display group |
| Auto ISO ceiling | look | **new field**, to propose here | Tone page |
| EI exposure shift | look | **new field** | Tone page |
| Gradation | look | **new field** | Tone page |

Wheel budget: 11 fields in use + 4 split + 3 AE = **18 for 12 sectors**. Adding a grid, which is global, would be
wrong on a per-slot wheel anyway.

## 2. Options

Notation: **W** = presses to open the wheel from shooting (SCP OK → picture-mode cell → INFO, about 3 [I]).
**INFO** reaches the editor; MENU, PLAYBACK, Movie and Delete do not (FIRMWARE_GUIDE §4 [V camera]). So each wheel
page adds one INFO press to every page after it. Dial = sector steps: 0 to n−1, or about n/2 if the ring wraps [?].

| | A. Caduceus menu page for everything | B. Paged wheel editor | **C. Hybrid (B + Caduceus page for globals)** |
|---|---|---|---|
| Flow | MENU › Setup › Caduceus › group › item › value | Film → Sat → Sat·All → Hue → Light → **Effects → Colour → Tone → Profile** → Film | Per-slot items as B. Globals: MENU › Setup › Caduceus › item |
| Presses | ≈ 12–18 first time; ≈ 4 when the menu reopens on the last row [I: gui_db id 0x10] | Effects W+5, Colour W+6, Tone W+7, Profile W+8, plus ≤ 6 dial steps. W+1 with "reopen on the last Extras page" | as B; globals ≈ 8 |
| Live feedback | none: the menu covers LV [I] | Color Profile view over LV (Blacks/Whites, Art and split tone show; stills-only fields don't) | as B |
| Which slot | **the active COLOR profile only**; Movie/AP awkward | the slot being edited (COLOR1–4, Movie, AP), as today | as B |
| Code | ≈ 1.0–1.5 KB: facade answers for ~20 virtual ids + active-slot resolve + labels; data ≈ 1.5 KB (rows, item-info 36 B × 20, listA, value lists) | ≈ 0.4–0.6 KB: sub-page byte, INFO step, id remap, field-table engine; +≈ 12 B per new field | B + stage 4: ≈ 0.5 KB data for the page (stock sids), and code only for Caduceus-only globals |
| Hooks | facade +0 (0x607fa355), +8, +24, +28, +20/+36, +152, possibly CANEXEC 0x6082686f and value column 0x60e8af1c | **none new**: front of the existing X1–X4 chain words and the k_step branch in ed_keys | B + RE_UI R1–R10 data, one action fn word |
| RE_UI open checks | 1 (unknown id in the viewer, CANEXEC), 2 (repurposed slots), 4 (item-info tree) | none | 1, 2, 4, for stage 4 only |
| Risk | **M–H**: an unhandled path hands a virtual id to stock getters (LOOK_MENUS §6); the screen stack can't be emulated | **L**: same mechanism as camera-proven pages since test12e; risk is wrong labels or numbers only | L for per-slot items; M for the menu page, which is isolated and data-first |
| Verdict | Rejected as the main home | Necessary, but has nowhere to put globals | **Recommended** |

Sub-option rejected for now: **per-profile rows under Shooting Menu 1 › Picture Mode › Color Profile n** (2CNL 130–133,
next to stock Sharpness/Contrast). That is a natural place for Grain/NR/Sharp, but it needs 12 virtual ids through
every facade method, has no Movie/AP equivalent and duplicates the Profile page. Revisit only after stage 4 proves
virtual ids.

### Option B/C mechanism (wheel)

| Part | Design | Size |
|---|---|---|
| Pages | Keep axis byte = X (4) on every Extras page, so the inner layers (tone_x, gc, sh, hl, v025 sg/ss/su) still see X. A new **sub-page byte P+687** (0 Effects, 1 Colour, 2 Tone, 3 Profile) is zeroed by the loader with P+680..703 | 0 |
| INFO | k_step (in place, full: 48 of 49 B) gets one `jmp` to a relocated step: on X, sub-page < last → sub-page+1 and stay on X; else → Film / Saturation as today | ≈ 40 B |
| Open | po_init: if closed on an Extras page, reopen there (as Sat·All does today) | ≈ 20 B |
| Remap front | Ahead of ex_get / ex_default / ex_set / ex_guide (words X1–X4) and ed_poly's facade read: on X, look up `map[sub][sector]`. Old field → translate to its v0.31 sector id, so the old handler runs unchanged. New field → field-table engine. Empty → `Effects: 1-4 only`-style label, writes ignored | ≈ 120 B + 48 B map |
| Field table | `{u8 slot_off, s8 min, s8 max, u8 flags (signed, look/profile, stills-lock, override-bit), u8 labelset, name[≤9]}`. Engine get/set/label copies ex_set's order: value, dirty, stock manager with the unchanged S value for the redraw | ≈ 250 B + 12–16 B per field |
| Labels | `<page letter><n> <name> <value>`, ≤ 16 characters: `E2 Halo Med`, `C3 Shadow Teal`, `T4 EI +2/3`, `P1 Grain Low` | strings ≈ 10 B per field |

Code space: there is no single 0.5 KB hole. Listed free ranges: 0x601de880–0x601dea3c (444 B),
0x601df03c–0x601df0e0 (164 B), 0x61242c30–0x61242ce0 (176 B), 0x601e1d78–0x601e1e3c (196 B, only a byte-table false
positive), all [V, CODE_SPACE_MAP]. Split tone (≈ 250 B) is competing for the same space, so agree on claims with
that agent. A code-space round (more dead tables) may come before stage 4.

## 3. Recommended layout

### 3.1 Wheel (per slot; COLOR1–4, Movie, AP)

INFO order: **Film → Saturation → Saturation·All → Hue → Light → Effects → Colour → Tone → Profile → Film.**

| Page | Sector | Item | Byte | Range | Owner | Status |
|---|---|---|---|---|---|---|
| **E Effects** | 1 | Glow− / Clarity+ | +28/+29 | −5..+5 | look | old X2 |
| | 2 | Halo | +52 | Look/Off/Low/Med/High | look + override | old X11 |
| | 3 | Art | +46 | Off/Star/Pin Hole | look | old X5 |
| | 4 | Lens shading (VigFix) | +49 | Off/Camera | look | old X8 |
| | 5–12 | free (e.g. halo tint +45, vignette +30) | | | | reserve |
| **C Colour** | 1 | WB A–B | +26 (+25.0) | −5..+5 | look | old X3 |
| | 2 | WB G–M | +27 (+25.0) | −5..+5 | look | old X4 |
| | 3 | Shadow tint colour | +53 | 12 wheel colours | look | split, new |
| | 4 | Shadow tint amount | +54 | −5..+5 | look | split, new |
| | 5 | Highlight tint colour | +55 | 12 wheel colours | look | split, new |
| | 6 | Highlight tint amount | +56 | −5..+5 | look | split, new |
| | 7–12 | free | | | | reserve |
| **T Tone** | 1 | Blacks | +47 | −5..+5 | look | old X6 |
| | 2 | Whites | +48 | −5..+5 | look | old X7 |
| | 3 | Gradation | +59 | Camera/Normal/High/Low | look | new |
| | 4 | EI shift | +58 | −2..+2 EV in 1/3 | look | new |
| | 5 | Auto ISO ceiling | +57 | Camera/200..25600 | look | new |
| | 6–12 | free (an Exposure page splits off when it reaches 4 or more items) | | | | reserve |
| **P Profile** | 1 | Grain | +50 | Off/Low/Med/High | **profile** | old X1 |
| | 2 | NR | +24 | Camera/Std/Low/Off | **profile** | old X9 |
| | 3 | Sharp | +51 | Camera/Off | **profile** | old X10 |
| | 4–12 | free | | | | reserve |

- Movie/AP: same pages. Fields that are stills-only keep the `…: stills` lock (flag in the field table). AE fields lock
  on Movie, and on AP until tested there.
- With no LOOKS.BIN, Film is skipped as today. With no BUNDLES.BIN, the editor is stock.
- Grain, NR and Sharp stay outside u_apply and lt_mod, as now. New look fields join both.

### 3.2 Setup Menu › Caduceus (global)

| Group | Row | Kind (RE_UI §4.5) | Storage |
|---|---|---|---|
| Display | Framing grid (Off / styles) | inline picker | the grid agent's choice. Preferred: extend a stock sid (Displayed Grid 155/447) with new values, following the aspect/Lowest S/S precedent (boot clamp needed). Otherwise a Caduceus global byte |
| Display | Grid style | inline picker | as above |
| Looks | Reload looks (re-run fm_load / sd_load) | action fn (R10), returns 1 | – |
| About | Caduceus version, looks file state | read-only rows, kind-5 text | – |
| (later) | other camera-wide Caduceus toggles | inline picker on a virtual id (LOOK_MENUS V1 facade answers) | one body-local global block, format decided in stage 4 |

Per-slot items never go here. That keeps the menu free of the "which profile?" problem.

## 4. Staged build plan

| Stage | Content | Code | Look format (shared with OM-3, AGENTS.md) | Gate |
|---|---|---|---|---|
| **1** | **Data-only menu probe.** RE_UI R1–R3: Setup row list → 8 ids with virtual id **X = 5200**; Menu_Viewer items/helps relocated (+1, label kind 5 `Caduceus`); 2CNL 68 listB/listC relocated (+1 `{1, X, 0, 0, 14, 68}`) so Right/OK open the **stock (14, 68) Wi-Fi/Bluetooth page**. **Skip R4**: no new group-14 descriptor, no 3.2 KB relocation. ≈ 550 B data | none | none | emulator: `app_check_mode` 0x608290c8 for id 5200 (RE_UI §9.1); package/restore check; table diff only. Can go into the current build |
| 2 | **Wheel pages**: sub-page byte, INFO step, reopen-on-page, remap front, field-table engine (empty), 11 old fields moved as in §3.1. No new fields | ≈ 0.4–0.5 KB | none: same bytes, only the page/sector move | existing verifiers G/W/V/E/M (look_extras, tone_ends, sharp_off, halation) per page and sector; polygon verify_poly |
| 3 | **Split tone on the Colour page**: 4 field-table entries | ≈ 50 B + labels | slot **+53..+56** in the OM-3 order (sh_color, sh s8, hl_color, hl s8). The LOOKS.BIN record is full, so **LOOKS.BIN v4** (larger record) is one decision with the split agent and should also carry the stage-5 fields. Loader spans and the MOVIE/AP zero checks move from +53 | split agent's image test; loader accepts every byte the UI saves (FIRMWARE_GUIDE §8, §10 #10) |
| 4 | **Caduceus page with stock kinds**: repurpose 2CNL slot 43 or 96 + its column mode (31/38) + item-info key (30/45/70–72) + one unopened group-14 descriptor; repoint the stage-1 transition. Rows: grid rows (stock sid) + Reload action. Virtual-id rows only if a global truly needs one | ≈ 50 B (action) + ≈ 0.5 KB data | none for looks. Globals are body-local; document any global block here | RE_UI open checks 2 and 4 audited statically first |
| 5 | **AE fields on the Tone page**: RE_AE A1 (0x60426886, 0x60427991), E1 (0x60429824), G1 (0x6042965b + capture 0x602a803b), each falling back to `prop_get` stock; active slot through `sc_slot` | ≈ 150 B stubs + 3 table entries | **propose first** (issue/PR): `iso_max` (0 = camera, else ISO 200..25600), `ei` (EV in thirds, −6..+6, 0 = none), `gradation` (camera/normal/high/low). Slot **+57 / +58 / +59**. Defaults 0, so old firmware and panels ignore them. OM-3 export: translate or drop | RE_AE emulator fixture for `ae_record_build`; clamp so the ceiling is ≥ the Auto ISO default (sid 172) |

Order 3/4/5 follows feature arrival. Stage 2 must land before split tone gets a camera UI. Stages fold into the
current build when ready (no version churn).

## 5. Camera checks (minimal)

| # | When | Check | Pass |
|---|---|---|---|
| C0 | now, stock, no flash | (a) Setup tab: 7 rows, does it scroll? (b) Does the wheel sector dial wrap 12 → 1? (c) Shooting Menu 1 shows 5 rows (RE_UI §8.1) | notes only |
| C1 | stage 1 | Setup shows `Caduceus` (8th row) with no garbage value text. Right and OK open Wi-Fi/Bluetooth; MENU returns; the menu reopens on the row; power cycle; no card → same rows | all yes. **Greyed row = record it, not a fail.** Crash or garbage → restore and do RE_UI §9.1 before stage 4 |
| C2 | stage 2 | INFO walks E → C → T → P → Film with the right labels. One edit per old field → the same slot byte as v0.31d (`tools/ep7_bundles_bin.py`); half-press save; power cycle. Close on Tone → reopens on Tone. Movie wheel shows the locks. The polygon follows the page | all yes |
| C3 | stage 3 | split values save and reload; an old LOOKS.BIN still loads | yes |
| C4 | stage 4 | Caduceus page opens, rows edit, MENU back, Reset (10003) and custom-mode recall don't crash | yes |
| C5 | stage 5 | dim scene: look ceiling 800 vs user 6400 → ISO ≤ 800; EI +1 → brighter, EXIF bias unchanged; gradation: metering and curve agree | yes |

Anti-brick:
- Stages 1–3 and 5 write no internal settings and fall back to stock without the card files.
- Stage 4's stock-sid extension stores new values in internal settings, so it needs the aspect-style boot clamp
  before flashing.
