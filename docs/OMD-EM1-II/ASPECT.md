# Still aspect ratios 65:24 and 21:9 on the OM-D E-M1 Mark II (fw 3.70)

How the E-M1 II decides which Image Aspect options to offer, why the E-P7 aspect patch didn't work here at first,
what fixed it, and what's still open. Main image `em1mk2/extracted/00_0100_40560020.decoded.bin`, base `0x60021020`.
Patch: `patches/omdem1mk2/aspect/build.py` → `edits.json`. Releases: `releases/em1mk2/`. History: `WORKLOG.md` 2026-11-11/12.

Evidence labels: **[V]** read in the image or executed in the emulator, **[E]** emulated with the camera's own code,
**[C]** seen on the camera, **[I]** inference.

## 1. Summary

| Item | State |
|---|---|
| 65:24 (id 6) and 21:9 (id 7) selectable | **Yes** [C v0.4c1, v0.4c3] |
| Saved JPEG size | 65:24 → **5184×1920** [C v0.4c1]; an entry chosen on the detail screen saved **5184×2224** (= the 21:9 size) [C v0.4c3] |
| Shooting Menu 1 row shows the value | **Yes**, as "65:24" / "21:9" (kind-5 text) [C v0.4c3] |
| Image Aspect detail screen (OK on the row) | v0.4c3: 6/7 appear as **two empty, selectable** entries; after scrolling past them they vanish [C]. v0.4c5: regular menu path "works great" [C] (§6.1) |
| Live Control strip | v0.4c1: one blank, selectable cell [C]; v0.4c3 not reported separately |
| Super Control Panel (SCP) | v0.4c3: 6/7 **missing** [C]. v0.4c5: 6/7 **present and selectable, but blank** [C] → the display-resource icon tables 0x1ff/0x200 are the SCP's option source (§6.2) |
| SCP tile / option row | **Working [C v0.4c13]:** tile shows the 65:24 / 21:9 labels (since c11); option row (OK on the tile) shows the 65:24 / 21:9 icons. It took five separate lists (§6.6, 6.9, 6.10, 6.13) |
| AF target selector | v0.4c6 and v0.4c7: opens with the **4:3 layout, no green cursor** [C]. **v0.4c8: works** [C] (E-P7 aspect_fix port, 6/7 = 16:9 in six display lookups, §6.7) |
| Live-view framing, Wide in live view, boot with 6/7 saved | **untested** |

## 2. The setting

- Settings id **270**. Values: 1 4:3, 2 3:2, 3 16:9, 4 1:1, 9 3:4 (offered by stock); 5 5:4, 6 7:6, 7 6:5, 8 7:5
  (hidden stock aspects); 10 17:9 (movie). [V, E-P7 ASPECT.md §1 + E-M1 tables]
- The patch **repurposes 6 → 65:24 and 7 → 21:9**. Because 6/7 are real hidden stock aspects, unpatched code that
  switches on the aspect still has a stock case for them (7:6 / 6:5 behaviour), which keeps the crash risk down. [V]

## 3. How the camera decides which options to show (the chain)

Every screen that lists aspect options goes through the same layers. All addresses [V]; the **[E]** rows were executed.

| Layer | Address | Notes |
|---|---|---|
| Option builder (generic) | `0x60e4a59c` | obj+80 = sid. Count = facade **+24** → obj+92. Arrays obj+100 (flags), obj+104 (values). Loop: value = facade **+28**(sid, i); if mode flag (`0x607f7107` vt0(sid)) == 1, ask facade **+36**(sid, value): 1 → row shown (flag 0), else hidden (flag 1). |
| Settings facade vtable | `0x60afb400` | +8 get current (`0x60837434`-family), +24 count `0x60836769`, +28 value-by-index `0x60836991`, **+36 availability `0x60836357`**. Facade object getter `0x608362c5`. 53 GUI sites call +36 (menu, SCP `0x60e59xxx`, others). |
| Count / value | `0x602dc36d` / `0x602dbad4` | Runtime slots (`0x622512fc`, 2 × 76 B, only sids with a registry record) → registry callback (`0x602dc343`) → **validator**. |
| Validator | record `0x604f07cc` | `{270, 0x80, list, alt, bytes, elem, …}`; count = +12 / +14 (`0x602e6588`), value = byte list[i] (`0x602e65f3`). Hash `0x622540f4` (128 buckets) built at boot by `0x602e6ba4` from 1215 × 20 B records at `0x604ee648`. **[E]** stock `1,3,2,4,9`; v0.4b5+ `1,3,2,4,9,6,7`. |
| Availability | `0x60836357` → `0x6086333c`(sid, v) → `0x602da752`(sid, 0, v) → `0x602de6a7` → interlock engine `0x602de667` / `0x602de0a0` | Returns 0 = allowed. |
| **Interlock rules** | ROM `0x604a8408`, 324 × 20 B; RAM hash `0x62252c28` (32 buckets) built at boot by `0x602de9c9` | Sid 270 = **record 179** `{270, 2000, list 0x604a0578, n 13}`: condition entries (sid 24 = 185..189, sid 44 = 1, 15206/15263, 697, 705, 15210) and `{u16 value, u16 result}` tables `0x604a0518` (→3), `0x604a0530` (→1), `0x604a0548` (→10), `0x604a0560` (identity, 10→1), **all listing only 1,3,2,4,9,10**. Continuation entries `0x604a05e0..0x604a0640` use the same tables. |

**[E] result** (`tools/omdem1mk2_emu_rules.py`): stock and v0.4b5 → rule 0 for 1,2,3,4,9 and 256 for 5,6,7,8,10;
facade +36 offers exactly `[1,2,3,4,9]`, which is what the camera showed. v0.4c1 → `[1,2,3,4,6,7,9]`.

### Why the E-P7 patch didn't carry over
The E-P7 needed only the option lists plus the validator (its ASPECT.md §1c). The E-M1 II adds the **interlock rule
value tables** as a further per-value filter, which the E-P7 analysis never reached. Every change before v0.4c1
(option lists, icon lists, 511/512 validators, list order) was invisible on camera because of it.

## 4. What the patch changes (v0.4c3)

| § in build.py | What | Where |
|---|---|---|
| 1–6 | Per-aspect size/geometry tables (46), capture W/H tables, ORF AspectFrame jump table, rec-view 640 tables, ratio tables, AF window tables | various (see `edits.json`) |
| 7 | Section-1 cave: validator list `1,3,2,4,9,6,7`, menu list (8), strip list B (7), live-view case blocks, 7-column pixel table | `0x60257580..0x602577f2` |
| 8 | Validator record → new list, count 7 | `0x604f07cc` |
| 9 | Menu descriptor `{270}` → 8-entry list | `0x6124ea1c` |
| 10 | Strip record `{270}`: list A in place, list B → cave, count 7 | `0x61249554`, `0x6124aea4` |
| 11 | Live-view switch tables S7/S8/S9/S10/S_alt ids 6/7 → cave blocks (checked against the stock cases: same registers, stack slots and resume addresses) | `0x60b2f8ec` … |
| 12 | Pixel-size readout → 7-column table (offsets 2/16, stride 30, 10 rows = the loop bound) | `0x60f13985` |
| **13** | **Interlock value tables with 6/7** (→3/→1/→10/identity), 13 references repointed | tables `0x60580700` (section-2 tail), entries `0x604a0580..0x604a0640` |
| **14** | **AF target selector**: headers `{flag, list, u16 n}` at `0x61212d34` (stride 12; code `0x60e3ad47..` skips the mask/style store on a miss — the E-P7 issue #23 crash) → 8-row copies, 6/7 = the **4:3** row since v0.4c7 (16:9 row in c1–c6, §6.5) | lists `0x60bc8560` (section-5 tail) |
| labels | Menu entries 6/7 = **kind 5** (text from a `char*`) → `"65:24"`, `"21:9"`; strip/record entries 6/7 = **kind 3** icons (ids 6668 = 65:24, 7086 = 21:9; v0.4c3/c4: stock placeholder bitmaps (blank); since v0.4c6 the selected/green lists use the white ids too) | text `0x602577f4` / `0x602577fa` |
| **15** | **Detail screen** (screen record `0x612abd20`): label list +28, size lists +32/+36/+52/+56 and the 7 Middle/Small class lists (via +44) copied as 8-row lists with 6/7 (kind-5 size text from the pixel table), list count +2: 6 → 8 | lists + text `0x6078e8c0..0x6078edfb` (section-4 tail; **conflicts with debug_log** if it returns) |
| SCP icons | Display resources 0x1ff/0x200 (`{id, A, B, n}` at `0x612e1f08` / `0x612e1fb8`): value→bitmap lists copied with 6/7, n 5 → 7 (default since v0.4c4) | lists `0x60bc8760` (section-5 tail) |
| Icons | `patches/omdem1mk2/aspect_icons` (v0.4c6): white 65:24 / 21:9 streams + descriptors in main-image free space; OSD bank-0 table entries 6668 / 7086 → those descriptors (2 OSD edits, nothing appended). v0.4c5 appended four icons after resource 69 instead (blank on camera) | streams `0x605d2a6c` (section-3 tail), `0x60256cf0` (section-1 padding); descriptors `0x605d2d9c` / `0x605d2db4` |

Not changed on purpose:
- **Stock strings** 241 "Panorama" and 2661 "Wide" are shared (241 = value 14 in the lists at `0x61236fb0` /
  `0x612b6f24`; 2661 = value 100 at `0x612a8600`), so they are not edited in place. [V]
- **No boot clamp**: a saved 6/7 is used at power-on. Ids 6/7 are stock hidden aspects, so start-up code has cases
  for them [I], but this is untested.

## 5. Labels: what draws text and what draws icons

List entries are `{u32 value, u16 kind, u16 id, u32 text}` (FIRMWARE_GUIDE "Labels"). The E-M1 II resolver
`0x60e59f78` (= E-P7 `0x60df250b`) handles kind 3 (bitmap), 4 (string id) and the text kinds (1, 2, 5, 6, 7, 8, 9, 10, 11:
memset 66 B, `strlen 0x600e17d1`, copy). [V]

| Surface | Draws | 6/7 on camera |
|---|---|---|
| Shooting Menu 1 row (current value) | text | "Panorama" (v0.4c1, kind 4), **"65:24" / "21:9"** (v0.4c3, kind 5) [C] |
| Image Aspect detail screen | icon box (green) + pixel-size table | empty box [C v0.4c3] |
| Live Control strip | icons only | blank cell with text entries [C v0.4c1] |
| SCP | ? | missing [C v0.4c3] |

There are no 65:24 / 21:9 strings or icons in the camera. English string table: OSD component 0x101, resource 8,
pointer table at resource +0x2af30 (3645 strings; solved with a runtime-base search). Ids 70 "Image Aspect",
292/291/293/1786/295/3261 = 4:3/16:9/3:2/1:1/3:4/17:9, 241 "Panorama", 2661 "Wide" — the same ids as the E-P7. [V]

## 6. Open issues

### 6.1 Image Aspect detail screen (camera v0.4c3)
OK on the menu row opens a selector (up/down, a green box, and a RAW / Large / Middle / Small / 50M / 25M pixel-size
table). 6/7 show as two **empty** entries that can be selected (the camera then shoots the new size), and they
**disappear after scrolling past them** [C]. Likely: this is the E-P7's "quality / pixel-count screen" (E-P7 record
`0x611d6754` `{0, 6, row labels, title 70, …, pixel-string lists}`, count 6 shared by all its lists, ASPECT.md §1b),
whose lists have no 6/7 entries. [I]

**Found [V]:** screen record `0x612abd20` (first of a 64-B screen table; selected at `0x60efa4f4`). Its draw function
`0x60efa603` resolves the selected value through `0x60e59f78` with **count = u16 record+2 (6)** in: +28 the box label
list (`{v, kind 4, string}` 1,2,3,4,9,10), +32 RAW / +36 Large / +52 50M / +56 25M size text (`{v, kind 5, char*}`,
5 rows + a non-matching sixth), and, through the class table +44 (7 × `{class, list}`: 13, 11, 3, 8, 7, 6, 5), the
Middle/Small size text. The five rows are fixed calls; +2 is the list length, not a row count. Fix (§15): all 12 lists
copied as 8 rows with 6/7 ("65:24"/"21:9" for the box; sizes such as `5184x1920`, `3200x1184`, `640x272` from the
pixel table), a never-matching 8th row in the size lists, count → 8. Static only; the "entries vanish after scrolling
past" symptom is not explained yet.

### 6.2 Super Control Panel
**Option source found [C v0.4c5]:** 6/7 were missing on v0.4c3 and appear (selectable, blank) on v0.4c5, whose only
SCP-relevant addition over c3 is the display-resource icon tables 0x1ff/0x200 (c4 = c5 minus the icons, not flashed).
So the SCP offers a value only if it has an entry in those value → bitmap lists. Blank = the bitmap didn't draw (§6.3).

Earlier notes: 6/7 missing entirely [C v0.4c3]. The SCP has its own actuator (`[GUI FUNC-SCP]` strings around `0x60e57636..0x60e59b02`;
value changes go through C++ member-function pointers; only ISO and AF frame have dedicated handlers). Its option source
is not found yet. Candidate [I]: the display-resource icon tables 0x1ff/0x200 (value → bitmap, the E-P7's SCP/info
icons). The b9/b10 probes extended them while the interlock rules still hid 6/7, so they were never tested properly;
default since v0.4c4.

### 6.3 Real icons (v0.4c5 → v0.4c6)
`patches/omdem1mk2/aspect_icons/build.py` reuses the E-P7 library (`patches/aspect/osd_icons.py`, `tools/osd_extract.py`
with `check_hash=False`, `COMPONENT_ADDR 0x42060020`, `MAIN_BASE 0x60021020`). The E-M1 II OSD parses unchanged: same
aspect icon ids and formats (white 50×38, green 64×48, fmt 14), bank-0 base `0xa2c91000`, bank-69 base `0xa3691000` [V].
- **21:9** = the E-P7 `make_219` (stock '2' + '1' ':' '9' glyphs). **65:24** = stock '6' ':' '2' '4' + a '5' from DejaVu
  Sans Condensed Bold, composed as a coverage map and squeezed 44 → 38 px to fit the stock label span, quantised to the
  icon's own indices (palette: first of `OSD.palettes()`, 4 white / 5, 6 greys / 16 black). Streams 815 / 1359 / 678 / 1238 B.
- **Placement** = the E-P7 "v8" route: payload+descriptor pairs appended after resource 69 (zero in stock), its directory
  size `0x47d400` → `0x47e600`, bitmap table entries of four placeholders (fmt 1) repointed. Loader `0x6017841a` = the E-P7
  one (size bound `0xf26140`, copies `size` bytes); pool layout checked: the predicted string base `0xa3c7f540` equals the
  solved one, bank 69 ends `0xa3b0e400`, the bitmap pool ends `0xa3bb7140` (675 KB free) [V/I].
- **Ids** 6668/6669 (65:24 white/green), 7086/7087 (21:9): placeholders with no type-3 entry, no u32 in the section-6 UI
  data and no 16-bit immediate load in the GUI code (214 such ids). Not provably unused [I].
- Checked from the built package: the four ids decode to the intended pixels; no other bitmap changed; restore OSD = stock.
- Risk: the E-P7's v8 append route was never cleanly confirmed on its camera (its later in-place route was). The E-M1 II
  has a headphone jack, so the E-P7's in-place donors (headphone icons) aren't available here. If the icons don't draw,
  `EM1_ASPECT_PLACEHOLDER_ICONS=1` builds the placeholder variant.
- **Camera, v0.4c5: the SCP shows 6/7 blank** [C]. The append route failed here as on the E-P7.

**Why the append failed (open) [V/I].** Loader `0x6017841a` (message-driven; bank index in `0xa26cda6c`) puts bank 0 at
`0xa2c91000` and any other bank it is asked for at `0xa3691000`, copying `size` bytes (bound `0xf26140`). Bank 69 *is*
a resident bitmap bank: 3095 of the 7408 stock table entries point into `0xa3691000..0xa3b0e400` (4313 into bank 0).
Language banks 1–67 hold self-pointers near `0xa3ca..` (string area, other loader) and bank 68 near `0xa3bb..`. So the
appended icons at `0xa3b0e400..0xa3b0f600` were in the "675 KB free" gap between bank 69 and bank 68, which is most
likely used at runtime [I, not traced]. (A first reading in this session that bank 69 shares a slot with the language
banks was wrong.)

**v0.4c6: icons in main-image free space [V static].** Nothing appended to the OSD, no directory change:
- White streams in free `0xFF` space of always-loaded, never-written sections: 65:24 (815 B) at `0x605d2a6c` (section-3
  tail, 1428 B free), 21:9 (678 B) at `0x60256cf0` (section-1 linker padding `0x60256ce8..0x60256ff0` before the
  aligned function `0x60256ff0`). Descriptors `{14, 50, 38, 8, 0, 0, len, payload, 0}` at `0x605d2d9c` / `0x605d2db4`.
- OSD bank-0 table entries 6668 / 7086 → those descriptors (cached addresses `0x60..`; the CPU always reads them, and
  a reader masking to physical sees the same; stock OSD pointers are uncached because that RAM is rewritten).
- No room for the 64×48 green icons (1359 + 1238 B), so the selected-state lists (B of 0x1ff/0x200, SCP list B) use the
  white ids too: the selected cell shows the white icon.
- Checked from the spec: both ids decode through the patched table → descriptor → stream to the intended pixels; lists
  0x1ff/0x200 A and B map 6 → 6668, 7 → 7086; check_loaded and the opcode audit pass.
- Not checked: that the draw path accepts a descriptor outside the OSD banks (on the E-P7 the getter is plain
  `&table[id]` with no bound, E-P7 ASPECT.md §1h; not re-read on this body).
- **v0.4c6p** = c6 with `EM1_ASPECT_PLACEHOLDER_ICONS=1`: 6/7 point at the stock 16:9 / 3:2 icons (differs from c6 only
  in the SCP list A/B and the 0x1ff/0x200 lists). Flash it only if c6 is blank: if c6p shows 16:9 / 3:2 in the 6/7
  cells, the lists work and the descriptor/stream placement is at fault; if c6p is blank too, the SCP reads another list.

### 6.3b v0.4c6 on camera and v0.4c7
- **v0.4c6: SCP 65:24 / 21:9 still blank** [C]. So moving the data into always-loaded main-image space was not enough.
- Draw path read [V]: bitmap getter `0x60d76dc9` = `&table[id]` from `(0x61fbc3e0)`, no bound (= E-P7 `0x60d10ba1`);
  draw `0x60d7aaea` (= E-P7 `0x60d145bf`) reads the descriptor (fmt 14/15/16 flag, colour key +20) and hands off to
  `0x60d7909a`; no address-range check seen, but the payload's path into the blitter was not traced.
- SCP cell builder `0x60f359d6`: picks item table `0x612e1e98` (mode 215) or `0x612e1f48` (216), 11 records
  `{u16 item, ?, A, B, u16 n}`; for each panel item copies A/B/n (0x1ff / 0x200 are the aspect item's records) [V].
- Remaining causes: (a) the cached `0x60..` pointers (every stock pointer is uncached `0xa2..`/`0xa3..`; a
  base-subtracting conversion would break cached ones), (b) descriptors outside the OSD are rejected somewhere, or
  (c) OSD component edits don't take effect on this body at all (never confirmed on the E-M1 II).
- No in-place donors: of 801 white 50×38 bitmaps only 35 have no reference (kind-3, u32, immediate), and all 35 are
  members of computed sequences this body uses (ISO 200…25600, CWB, 4K 30p/25p/24p, ART 13 III, ISO L64).
- **v0.4c7** (`EM1_ICON_DIAG=1`): 65:24 = the c6 icon with **uncached** pointers (`0xa05d2d9c` / `0xa05d2a6c`; the
  `0xa0..` alias is mapped: stock code passes `0xa0b5ed8d`). 21:9 = table entry 7086 → the **stock 16:9 descriptor**
  `0xa2d9ce8c`. Reading the camera:

  | 65:24 cell | 21:9 cell | Meaning |
  |---|---|---|
  | 65:24 icon | 16:9 icon | Fixed by uncached pointers; next build restores the 21:9 icon |
  | blank | 16:9 icon | OSD table edits work; main-image descriptors/payloads don't. Next: descriptor in place over a placeholder's own descriptor, then payload location |
  | blank | blank | OSD edits don't take effect on this body. Next: patch the RAM table at runtime (hook) or a non-OSD route |

### 6.5 AF target selector (v0.4c6 → v0.4c7)
Camera v0.4c6 [C]: in 65:24 / 21:9 the selector opens with the 4:3 layout and no green cursor; AF works without a
visual indicator; grid modes switch. Read [V]: AF_Target_Actuator reads sid 270 at seven sites. Four
(`0x60e3b2f0/b54a/b637/b724`) only special-case 3 or 9 with setting 34 = 1. Two (`0x60e3be0f`, `0x60e3c9d2`) are
if-chains over 9, 4, 3, 2, 1, 10 picking a cursor-layout table `{key, list, u16 n}` per aspect (and per a second flag,
`(52,sp)` = 1 → reduced tables); any other value falls to the 4:3 default `0x612141a0` (12 keys). So 6/7 always get
the 4:3 layout, while §14 gave them the 16:9 mask/style (style 2): the two disagree. v0.4c7 gives 6/7 the 4:3 rows
(style 0 / 4, as stock 3:2 uses style 0 in headers 0/1). The AF window sizes (§6, 43×27 / 84×52 as 3:2 and 16:9)
stay. Side effect: AF points outside the 65:24 / 21:9 frame are selectable, as on 4:3.

### 6.6 SCP value cell (v0.4c8) — found with the E-P7 §1j map, checked in the emulator
c7's 21:9 cell stayed blank with its table entry on the stock 16:9 bitmap, so the cell never reached a bitmap at all.
The c5–c7 icon work (§6.3/6.3b) was aimed at the wrong layer.
- Cell builders `0x60e6a0b9` (cell self+2096) and `0x60e70bf0` (self+2100) clear `{u16 index, u8 kind, u8 state}`,
  read GetValue(270) and look it up with `0x60e59f44` in `{value, index}` lists `0x612413f4` / `0x612449d0`:
  1,3,2,4,9,10 → 2,6,3,5,4,7. 6/7 miss → index 0 [V emulated].
- Widget record `0x611329f8`: `+0x34 u8 2, u8 count 5`, parts `0x61131744` `{0xffff,7,7,bitmap}` = 477 4:3, 478 3:2,
  479 3:4, 2422 1:1, 476 16:9 (index 2..6 order), `+0x3c u16[count]`. setPart `0x60daecb8` ignores part ≥ count.
  Three more records (`0x61130628`, `0x611613c4`, `0x611c0ae8`) have the order …16:9, 1:1 and are not driven by these
  cells (left alone). Two other cells use `→ 8..13` lists (`0x61240cec`, `0x612442c8`; not changed, conversion unknown).
- Fix (aspect/build.py §16, as E-P7 aspect_scp t1): one 8-entry list (stock + 6→7, 7→8) at `0x605d2e80`; both sites
  `mov imm32,a1 / mov 6,d1` → new list, 8; record → count 7, parts `0x605d2e00` (stock 5 + 6668, 7086), u16 `0x605d2e70`.
- **Emulated** (`tools/omdem1mk2_emu_scp.py`): C both builders × values 0–12 — stock values unchanged, 6 → 7, 7 → 8
  (the same run on c7 reproduces the camera: 6/7 → 0, no part); W index → part → bitmap; G the firmware's getter
  `0x60d76dc9` with the patched OSD bank 0 at `0xa2c91000` → entry → descriptor → payload decodes to the built icons.
- **Not emulated:** the widget draw / blitter, and whether the OSD component edits reach the camera (still never
  confirmed on this body). If the cell shows nothing on c8, the index/part path is proven by emulation and the
  remaining suspect is the bitmap itself; next diagnostic: point part 5 at stock 476 (no OSD dependency).

### 6.7 AF / AE display lookups (v0.4c8) — E-P7 aspect_fix port, checked in the emulator
c7's 4:3 rows changed nothing on camera. The E-P7 fix that worked on its camera treats 6/7 as 16:9 in **every**
AF/AE display lookup that lacks them (centred full-width crops, 16:9 geometry is the superset). Sites found on the
E-M1 II (E-P7 equivalents by code shape) and hooked with register-only stubs (`patches/omdem1mk2/aspect/af.s`,
`0x605d2ec0..0x605d2f47`, no stores):

| Hook | Site | Key | Stock behaviour for 6/7 [V emulated] | E-P7 |
|---|---|---|---|---|
| sv | `0x60ea25e2` | `(4,a1)` | selected-point validity maps (10 lists): result `(12,sp)` **unwritten** (stack garbage used) | `0x60e3bde8` |
| ag1 | `0x60e5f5d7` | obj+248 | AF frame display geometry (6 lists): byte obj+18 **unwritten** | `0x60df798a` |
| ag2 | `0x60e5f823` | obj+248 | same, second function | `0x60df7b55` |
| mt | `0x60e99d28` | `(40,sp)` | metering display geometry: outputs **unwritten** | `0x60e32899` |
| ch1 | `0x60e3be27` | `(56,sp)` | AF_Target_Actuator cursor layout: falls to the 4:3 default `0x612141a0` | — (E-M1 II only) |
| ch2 | `0x60e3c9d7` | `(52,sp)` | same, second chain | — |

§14 back to the 16:9 rows. **Emulated** (`tools/omdem1mk2_emu_af.py`, 768 runs): for every list/key, stock values give
identical results on stock and patched; on patched, 6/7 give exactly the stock 16:9 result; on stock, 6/7 are
unwritten (sv/ag/mt) or 4:3 (ch). **Not emulated:** drawing and the consumers of these results; the E-P7's
rows/cols switches, ratio-pair globals, tracking and AUTO sites were not found on this body by byte pattern (AF itself
works, so not pursued yet); the grid overlay (E-P7: not fixed either).

### 6.8 Icons without the OSD: bitmap-getter hook (v0.4c9)
Camera v0.4c8 [C]: AF selector works; SCP 65:24 / 21:9 still **two empty, selectable slots**. The c8 index/part path is
emulated correct, so the cell now asks for bitmaps 6668 / 7086. Every icon attempt (c5 append, c6 main-image descriptors,
c7 uncached pointers and 21:9 → stock 16:9 descriptor, c8) went through **OSD bank-0 table edits**, and none ever drew,
although the c7 package holds them. Conclusion at the time [I]: OSD (0x101) table edits don't take effect on this body. **Withdrawn after c9d (§6.9):**
the slots never asked for a bitmap, so c5–c9 say nothing about OSD edits either way.
- Read [V]: the getter `0x60d76dc9` (`&table[id]`, table pointer `(0x61fbc3e0)` = `obj+16` of a resource object,
  set at `0x60f13d22`) is the **only** reader of that pointer; all 17 bitmap draws call it. The widget part draw
  `0x60daef77` uses a per-object 32-slot entry cache at +172 (zeroed in the constructor `0x60dae2fb`) first, else the getter;
  setPart `0x60daecb8` bounds the part by +131 (count, from the record). The kind-3 label resolver `0x60e59f78` passes
  the id through unchanged (no remap).
- Fix (af.s `gt`, hook `0x60d76dc9` `811da500c906` → `jmp`): id 6668 → `0x605d2dcc`, 7086 → `0x605d2dd0`, else the
  stock code (`0x60d76dcf` / `0x60d76dd3`). The entry words (aspect_icons/build.py `ENTRY_AT`) hold the main-image
  descriptors `0xa05d2d9c` / `0xa05d2db4`. **No 0x101 edits**: the release's OSD component is stock again.
  `EM1_ICON_ROUTE=osd` rebuilds the c6–c8 table-edit route.
- **Emulated** (`tools/omdem1mk2_emu_scp.py`, stock OSD): C/W as c8; G: the patched getter returns the entries for
  6668 / 7086 and both decode to the built icons; 395 other ids (every 19th, neighbours, 0, 65535) return the same entry
  as stock. AF harness (768 runs), rules (offered 1,2,3,4,6,7,9) and validator pass.
- **Not emulated:** the part draw `0x60daef77` → blitter `0x60d7909a` with a main-image descriptor/payload (uncached
  `0xa0..` alias). If c9 is blank, that is the remaining suspect.
- **v0.4c9d** (`EM1_ICON_DIAG=1`): identical except the 7086 entry → the stock 16:9 descriptor `0xa2d9ce8c`. Flash only
  if c9 is blank: 16:9 in the 21:9 slot = hook works, main-image bitmap data is the problem; still blank = the slots
  don't draw through this getter.

### 6.9 SCP option row: the second item table (v0.4c10) — found by reading, checked in the emulator
Camera v0.4c9 and v0.4c9d [C]: both blank. Owner: the blank spot is the **option row** opened with OK on the aspect
tile, where stock values show icons. c9d served the stock 16:9 bitmap for id 7086 at the only bitmap-table reader and
the 21:9 slot still drew nothing, so the slot never requested a bitmap.
- Every aspect icon list in the image (label entries `{value, 3, id}` and `{value, bitmap}` pairs) was enumerated. Two
  were never extended: label list `0x6123a174` (ref `0x6123e198`, owner not traced) and value→bitmap copies
  `0x612e2eb0` / `0x612e2ed8` = the 0x1ff/0x200 lists, used by a **second item table `0x612e3040`** (22 × 20-B
  records `{u32 item, u32 type, A, B, u32 n}`, 11 per SCP mode 215/216, picked at `0x60f3699b`; items 0x1ff/0x200 at
  `0x612e307c` / `0x612e3158`, type 0x39, n 5) [V].
- Option-row builder `0x60f36b24(obj, n, A, B)`: for each offered option k, value = `0x60f35214(k)`; search A
  (n entries) for it; on a match write the white id to `obj+232[k]` and the green id (B) to `obj+228[k]`. No match →
  nothing written → empty slot. Which values are offered comes from elsewhere (the first table, extended in c5), so
  6/7 were selectable with no bitmap [V emulated].
- Fix (aspect/build.py, after the 0x1ff/0x200 block): both 20-B records → the existing 7-entry lists `0x60bc8760` /
  `0x60bc8798`, n 7. The getter hook (§6.8) stays, so the icons don't depend on OSD edits.
- **Emulated** (`tools/omdem1mk2_emu_scp.py` R): native record search `0x60f36a43 → 0x60f36a6a` (stock n 5, patched
  n 7 + new lists) and per-option search `0x60f36cd3 → 0x60f36d0b`: stock 6/7 → no id (reproduces the camera), patched
  6 → 6668/6668, 7 → 7086/7086, stock values identical. C/W/G as c9.
- **Not emulated:** the cell drawing from obj+232/228 (stock values use the same path); label list `0x6123a174`.

### 6.10 SCP tile record and the option row's values (v0.4c11)
Camera v0.4c10 [C, owner photos]: (1) SCP tile reads **"17:9"** with 65:24 set; (2) OK on the tile → Image Aspect
screen (5184×1920 size text = §15 lists, working) with a strip of 5 stock icons and an empty area for 2 more;
(3) owner: the **regular-menu** Image Aspect strip shows both new icons → main-image bitmaps via the getter hook draw.
- **Tile [V].** The tile on this body is widget record **`0x611771d8`** (type 0xe2 like `0x611329f8`; 6 parts =
  boxed text labels 5871..5866 = 4:3, 3:2, 3:4, 1:1, 16:9, 17:9, 106×31, colour key 7; layout ref `0x60293de0`), found
  by rendering every 6–8-part record. Index − 2 = part, so c8's 6 → 7 hit the **17:9** label (value 10's slot) and
  7 → 8 was past the count. **§6.6's "record 0x611329f8 is the cell" was wrong for this layout.**
- Fix: index list 6 → **8**, 7 → **9**; both type-0xe2 records → 8 parts (`0x611329f8`: + 476 filler for the 17:9
  slot, 6668, 7086; `0x611771d8`: + 6669, 7087), shared zero u16[8] at `0x6146cfd4`. New tile labels
  (`patches/omdem1mk2/aspect_icons/tile.py`): composed from the stock label glyphs (65:24 with a rendered '5'), box
  rebuilt to width, cropped to the box (89×27 / 65×27; the widget aligns its bitmap — record flags `01 01`, not proven),
  65:24 without the lightest AA level to fit. Served by the getter hook as ids 6669 / 7087 (entries `0x605d2dd4/dd8`).
  Placement: streams in the section-7 tail `0x613ecd9c` (596 B) and section-4 tail `0x6078edfc` (506 B), descriptors
  `0x60256f98` / `0x60bc87d0`, record-B parts `0x6146cf54` (section-9 tail).
- **Option row [V read, emulated in part].** The row's slot values come from a list object (+56 count, +64 values)
  filled at `0x60f34f2a` through the settings facade (vtable +28) for the item's sid (`obj+50`); the aspect items are
  0x1ff / 0x200 = **sids 511 / 512**, whose validator lists still had the 5 stock values. Past the count `0x60f35214`
  returns 2000 → no match in the A list → empty slot. So c10's table fix (§6.9) was necessary but not sufficient.
  Fix: sids 511/512 validator records → the 7-value list (the old `EM1_ASPECT_511` probe, now default).
- **Emulated:** SCP harness C (6 → 8, 7 → 9; stock unchanged), W (both records: stock values unchanged, 6/7 → 6668/7086
  and 6669/7087), R (option row), G (6669 / 7087 decode to the built labels; 393 other ids = stock); rules: sid 511/512
  count 7 [1,3,2,4,9,6,7], offered [1,2,3,4,6,7,9]; AF 768 runs.
- **Not emulated:** the facade +28 enumeration for sid 511 into the list object (read only); the tile alignment of the
  cropped labels (if left/top-aligned, the label sits a few pixels off-centre).

### 6.11 Option row after c11: data path emulated end to end, cells still empty (v0.4c12d diagnostic)
Camera v0.4c11 [C]: the SCP tile shows both new labels; the option row still has two empty, selectable slots.
Emulated on c11 (scratch script, same fixtures as `omdem1mk2_emu_rules.py`):
- The list object's values come from facade +24 (count) / +28 (value k; worker `0x608632e8` → `0x602dc36d` count,
  `0x602da61e` / `0x602da63c` value) for the item sid: stock sids 270/511/512 → 5 values `1,3,2,4,9`; c11 → 7 values
  `1,3,2,4,9,6,7`. The per-slot availability (facade +36, `0x6086333c`) for sids 511/512 is 1 for every value.
- So slots 6/7 hold 65:24 / 21:9, and (check R) the row builder writes 6668 / 7086 into obj+232 / obj+228.
- Draw: `0x60f36fd4` switches on the visible-cell count (obj+214, 1..7) and copies the ids into the cell structs
  (+10 white, +12 green, +2 / +3 flags from obj+236). The cells' own drawing was **not** traced: it needs the
  panel's live widget objects, which the fixtures don't build.
**v0.4c12d** (`EM1_ICON_DIAG=1 EM1_SCP_ROW_DIAG=1`; = c11 except): row/0x1ff lists 6 → stock id **476** (no hook,
OSD data); id 7086's hook entry → the stock 16:9 descriptor (so 21:9 shows 16:9 everywhere, incl. the regular menu).
| 65:24 slot | 21:9 slot | Meaning |
|---|---|---|
| 16:9 | 16:9 | Cells draw ids and new ids; main-image **bitmap data** isn't drawn by this widget → move the data |
| 16:9 | blank | The row rejects **new ids** (cache / bound) → use or remap to stock-range ids |
| blank | blank | Cells 6/7 are **not drawn** at all → trace the cell layout / page code |

### 6.12 Option screen 57 has five cells (v0.4c12) — **wrong, withdrawn**
**Correction (owner, after c12 was built):** screen 57 already showed two extra cells since c10/c11, and before that
the row was tight around the five stock options, so the screen does adapt to 7 values. The problem is the icon drawn
in cells 6/7, not the layout. v0.4c12 (screen type → 0x3e) rests on the wrong inference: **not flashed, superseded by
c13**; `EM1_SCP_ROW_TYPE` defaults back to 0x39. The original notes follow for the record.
Camera v0.4c12d [C]: both diagnostic slots blank (65:24 slot with the stock 16:9 id, 21:9 slot with the stock 16:9
data) → the row never draws cells 6/7. It isn't the bitmaps, the ids or the values.
- Row record (obj+104, 38 B, published as data block 35 by `0x60d66569`): byte 0 = visible cells (obj+214, 7 when
  n ≤ 7), byte 1 = the item record's **type**, 2..8 flags, 9 selection, 10..22 seven bitmap ids, 24/25 arrows. With
  n = 7 the switch at `0x60f36fd4` takes case 7 and fills all seven ids and flags [V].
- The type is the **option screen** opened by OK: `0x60f0f08a` returns the current screen id and `0x60f37808` /
  `0x60f37ac8` test it against **57 = 0x39**. In the option-row item table only aspect (0x1ff/0x200) uses 0x39; the
  generic types 0x3a / 0x3b / 0x3e serve items with 14, 69 and 41 / 4 / 2 values [V]. Screen 57's layout evidently
  draws 5 cells (aspect never had more) [I; its widget list was not found: the SCP main layout (229 widgets,
  `.data` `0x60293d30`) has no 50×38 cell run at the strip position].
- Fix: type 0x39 → **0x3e** in both item records (`EM1_SCP_ROW_TYPE`, default 0x3e; 0x39 = stock). Loses whatever
  screen 57 adds (likely the pixel-size line) [I].
- Emulated: the row builder only copies the type into byte 1 (no other use in the builder); SCP C/W/R/G, AF, rules
  and the facade enumeration pass as on c11. **Not emulated:** screen 0x3e's drawing (needs the live GUI objects).

### 6.13 Screen 57's own label source (v0.4c13) — the list flagged in §6.9
c12d put the stock 16:9 id (and, via the hook, the stock 16:9 data) into the row data of §6.9–6.11 and cells 6/7 still
drew nothing → screen 57's cells take their icons from somewhere else. The one aspect list never extended was the
label list `0x6123a174` (§6.9).
- It belongs to the **option-label provider** `0x60e65473`: directory `0x6123ee2c` {u16 key, u16 n, table}; key 0 →
  78 × 52-B records at `0x6123de54` {u32 key, A, B, u32 n, …}. **Key 16 = aspect** (`0x6123e194`): A white
  `0x6123a174`, B green `0x6123a1b0`, n 5, entries {u32 value, u16 kind 3, u16 bitmap, u32 cond} for 1,3,2,9,4 [V].
- User: `0x60e651e9..0x60e65229` (SCP area) picks the provider, searches the records for the current item's key
  (stride 52) and keeps the record at obj+8724 [V read].
- Fix (aspect/build.py §18): new 7-entry A / B lists (stock + 6 → 6668, 7 → 7086, kind 3, stock cond) at
  `0x60580780` / `0x6058018c` (section-2 FF tail), record n 5 → 7.
- **Emulated** (`tools/omdem1mk2_emu_scp.py` L): record key 16 → the firmware's resolver `0x60e59f78` natively for
  values 1,2,3,4,9,6,7: stock → 6/7 **none** (= the camera), c13 → 6668 / 7086 (white and green), stock values
  unchanged. C/W/R/G, AF (768) and rules pass; R now expects screen 0x39.
- **Not emulated:** that screen 57's cells draw from the key-16 record (read at `0x60e65214`, consistent with c12d),
  and the cell drawing itself.

**Camera v0.4c13 [C]: works.** Lesson for the next value added to an existing setting: one setting's labels live in
several independent lists (menu, detail screen, SCP tile index + widget record, SCP item tables, the per-sid
validator lists, the option-label provider). Before building, enumerate **every** list that holds the stock values
(search for the stock id/value pairs, as in §6.9) and extend them all, then check each one in the emulator; c5–c12
fixed them one camera test at a time.

### 6.4 Untested
AF target selector with 6/7 (fix §14 is static only), live-view framing and the 640×240 / 640×272 rec-view,
21:9 from the strip, power-off/on with 6/7 saved, RAW+JPEG.

## 7. Tools and method

- **Emulator**: `external/oly_fw_analysis` (submodule, fishcu, pinned 539fcf1), engine built by hand from the verified
  GNU sim source (WORKLOG 2026-11-11 "Emulator set up").
- `tools/omdem1mk2_emu_validator.py <edits.json>`: firmware validator init + count/value for sids 270/511/512.
- `tools/omdem1mk2_emu_rules.py <edits.json|->`: validator init + interlock rule init, then the rule check and facade
  +36 for values 1–10. Fixtures: zeroed `.bss` (+ uncached alias), `.data` from its init image (flash `0x60258000` →
  RAM `0x61f7d540`), CPU id `0x8050` = 0, the E-P7 verifiers' task-table fixture, boot-ROM memcpy/memset stand-ins at
  `0x4700106b` / `0x47001177`, semaphore signal `0x6005e6cf` stubbed. Every other setting reads 0.
- `patches/omdem1mk2/aspect_icons/build.py [--previews DIR]`: builds the icons, previews (`sheet.png`) and the OSD edits.
- Build checks: `tools/omdem1mk2_audit_opcodes.py` (also absolute stores into the image and call/ret frame pairing),
  `tools/omdem1mk2_check_loaded.py` (also every installed `jmp` lands on patch code).
- **Method that worked**: run the camera's own code on the patched image before flashing. Five camera probes
  (v0.4b6–b11) based on static reading moved nothing; the emulator found the rule tables in one session.

## 8. Camera log (aspect)

| Build | Result |
|---|---|
| v0.4 / v0.4b5 | No new options anywhere (strip and menu = stock five) |
| v0.4b6-probe (validator `1,3,2,9,6,7`) | 1:1 disappeared → the screens read the validator |
| v0.4b7-probe (6/7 first in all lists) | No change → not a row cap |
| v0.4b8-probe (17:9 allowed) | 17:9 still hidden → not a per-table row miss |
| v0.4b9–b11 (511/512, icon resources, icon entries) | No change (the "empty slots" were the strip's stock width) |
| **v0.4c1** (interlock tables) | Panorama selectable via a blank strip cell; menu row "Panorama"; **JPEG 5184×1920** |
| **v0.4c3** (short labels, icon entries) | Menu row "65:24" / "21:9"; detail screen: 2 empty selectable entries (vanish after scrolling past); saved 5184×2224; SCP: missing |
| v0.4c4 (detail-screen lists, SCP icon tables) | not flashed |
| **v0.4c5** (= c4 + real icons appended to the OSD) | Regular menu "works great"; **SCP: 65:24 / 21:9 present and selectable, but blank** |
| **v0.4c6** (icons in main-image free space, cached pointers) | SCP 65:24 / 21:9 **still blank**; AF selector: 4:3 layout, no cursor, AF works |
| v0.4c6p (stock placeholder icons) | not flashed (superseded by c7's diagnostic) |
| **v0.4c7** (4:3 AF rows; uncached icon pointers; 21:9 → stock 16:9 descriptor) | SCP 65:24 **and 21:9 both blank**; AF selector same as c6 |
| **v0.4c8** (SCP value cell + AF/AE display lookups, both E-P7 ports; emulator-checked) | **AF target selector works**; SCP 65:24 / 21:9 still two empty, selectable slots |
| **v0.4c9** (getter hook, icons with no OSD edits; emulator-checked) | SCP option row: 65:24 / 21:9 still empty slots |
| **v0.4c9d** (= c9, 21:9 → stock 16:9 via the hook) | Still empty → the slot never requests a bitmap (§6.9) |
| **v0.4c10** (option-row item table 0x612e3040 → 7-entry lists; emulator-checked) | SCP tile shows **"17:9"** for 65:24; option row 5 icons + 2 empty slots; regular-menu strip shows both new icons |
| **v0.4c11** (tile indices 8/9 + tile labels; sids 511/512 → 7 values; emulator-checked) | **SCP tile: 65:24 / 21:9 labels render**; option row still two empty, selectable slots |
| **v0.4c12d** (row diagnostic: 65:24 slot → stock 476, 21:9 → stock 16:9 data via hook) | **Both slots blank** → cells 6/7 never drawn (§6.12) |
| v0.4c12 (= c11 + option screen 0x39 → 0x3e) | **not flashed — withdrawn** (owner: screen 57 already has the 7 cells, §6.12) |
| **v0.4c13** (= c11 + option-label record key 16 → 7-entry lists) | **SCP option row shows the 65:24 / 21:9 icons — working** |

## 9. Corrections to earlier notes

- `patches/omdem1mk2/CHANGELOG.md` v0.4 described menu and SCP integration as done; it didn't work until v0.4c1.
- E-P7 `docs/ASPECT.md` §1c calls `0x60886900` "the generic menu builder"; that code is `CapWif_WifiRemoteTake.cpp`
  (the Wi-Fi remote's settings enumerator), not the on-camera menu.
- The WORKLOG b9/b10 entries read two "empty slots" in the strip as new; they are the strip's stock unused width.
- §6.3 (v0.4c5) called the RAM after bank 69 "675 KB free"; camera v0.4c5 suggests it isn't (icons blank).
- `ARCHITECTURE_AND_MEMORY_MAP.md` described the uncached alias as an OR with `0x40000000`; it is an addition (`0x60..` → `0xa0..`).
