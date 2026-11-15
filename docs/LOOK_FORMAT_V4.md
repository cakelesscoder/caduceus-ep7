# Look format: base curve and colour matrix (proposal, v0.34a)

Two new fields for the shared look format, how each camera carries them, and what older firmware and panels do with them.
They come with `patches/look_hw` (v0.34a dev layer): a per-look **base curve** and a per-look **colour matrix**, both done
by the image hardware, so they cost no time per photo. Per [AGENTS.md](../AGENTS.md) ("Don't invent a parallel format"),
this is proposed here first, with defaults that older firmware and panels ignore safely.

## 1. Shared look fields (pack JSON, `pk1_` pack links)

| Field | Type | Default (absent) | Meaning |
|---|---|---|---|
| `curve` | string: `standard`, `auto`, `pale`, `light`, `pop`, `flat`, `log` | the camera's own | The base tone curve under the look (before the look's own tone, split tone and the colour engine). `standard` = the ordinary picture-mode curve, `auto` = Gradation Auto's (lifted shadows), `pale` = Pale & Light Color's, `light` = Light Tone's, `pop` = Pop Art II's, `flat` / `log` = the movie Flat / log curves |
| `matrix` | 6 integers `[m01, m02, m10, m12, m20, m21]`, each −64..64 | all 0 (identity) | A 3 × 3 colour matrix in units of 1/128, applied in linear RGB after the camera's own colour matrix and before the curve. Rows are the output R, G, B; columns the input R, G, B. Each row's diagonal is 128 minus its two entries, so **greys stay neutral** and only the six off-diagonals are free. `m01 = +32` reads: red picks up a quarter of (green − red) |

- One look means the same on every body. A body that can't do a field drops it in its export target and says so; the look
  keeps the value.
- Look codes (`1…`–`8…`, single looks) have no digits for either field, as for split tone: a shared single look loses
  them. `pk1_` pack links are the JSON and keep them.
- Old panels parse a pack with these fields and drop them (unknown fields are ignored by `parseLook`). New panels read old
  packs unchanged (absent = default).

## 2. E-P7 card files

### BUNDLES.BIN (v0.34a, built)

COLOR slots, slot bytes that were 0 in every earlier file:

| Slot byte | Field | Values | Loader range (lo / span) |
|---|---|---|---|
| +53 | `curve` | 0 camera's own, 1 standard, 2 auto, 3 pale, 4 light, 5 pop, 6 flat, 7 log | 0 / 7 |
| +54..+59 | `matrix` | m01, m02, m10, m12, m20, m21 as s8 | −64 / 128 |
| +60 | (camera only, v0.34b) | the Extras Mix / Strength choice: 8 × (10 − strength) + mix; mix 0 Off, 1 Warm film, 2 Cool separation, 3 Muted, 4 Punchy; strength 0..10 = 0..100 % | 0 / 84 |

- MONO slots keep 0 (the firmware gates on key 11, COLOR).
- The panel writes them only for the firmware option v0.34 or later, and only when a look sets them. Every other file stays
  byte-identical. Older firmware rejects a BUNDLES.BIN with these bytes set (its range table says 0..0) and keeps the
  flashed table, as with Halo +52 and split +62/+63.
- **Extras v2's pencilled +57..+59** (Auto ISO ceiling, EI shift, Gradation; [EXTRAS_MENU_V2.md](EXTRAS_MENU_V2.md), not
  built) **must move**: **+61 is now the only COLOR slot byte left** (v0.34b took +60), so that proposal needs another place.
- **+60 is not a look field.** It is the camera's memory of which named mix and strength the user dialled on the Extras page
  (`patches/look_hw_ui`), so the page can show the name and strength again after power-off. The look itself is still only
  `matrix` (+54..+59): the camera writes the scaled numbers there. The panel writes +60 = 0; the camera then names a matrix
  by matching it (below). v0.34a and older reject a file with +60 set (their range is 0 / 0), as for every new byte.

### Named mixes (v0.34b, camera Extras page and Control Panel)

Named presets for `matrix`, the same on the camera and in the panel (`patches/look_hw_ui/build.py` `MIXES`,
`webapp/src/pack.ts` `NAMED_MIXES`; change both together). In 1/128, slot order m01 m02 m10 m12 m20 m21:

| Mix | Values |
|---|---|
| Warm film | 6, −10, 4, −6, −8, 4 |
| Cool separation | −8, 4, −4, 6, 6, −8 |
| Muted | 14, 10, 10, 8, 10, 12 |
| Punchy | −12, −6, −8, −6, −6, −10 |

- **These are starting values from a mock-up, not tuned looks.** They are kept modest (at most 14/128) on purpose; tune
  them against camera JPEGs before calling them finished.
- Strength s (0..10 = 0..100 %) scales each value: v × s / 10, rounded half away from zero. Strength 0 = all six bytes 0
  (no effect). The build refuses a table in which two (mix, strength) pairs give the same bytes or a non-zero strength
  rounds to all zero, so the camera can always tell them apart.
- Naming a matrix (camera and panel, same order): +60's choice if its bytes match; else all zero = Off; else the first
  named mix, strength 100 % down to 10 %, whose bytes match; else the look's own numbers ("From look" on the camera,
  "Own numbers" in the panel).

### LOOKS.BIN v4 (v0.34e, built: `patches/looks_v4`; emulator-checked, not camera-tested)

The v3 record (64 B) has no free byte: the name tail +61/+62 holds split tone, +63 is the name's NUL. So v4 adds an
extension after the records. Without looks_v4 (v0.34a..d), or with a v3 file, a **Film pick of a library look clears
+53..+59** and Own / Stock put back the profile's own bytes from the Film page's snapshot.

- Header as v3 with version (+4) = 4, +32 u32 CRC-32 (zlib) of the extension section, +36 u16 = 16 (extension record
  length). +12 payload stays 64 n, +24 n. The +16 CRC is the v3 rule over the v3 part as the file has it (bytes 0..15,
  then 20..63+64n), so it covers the extension CRC too.
- Body: the n v3 records unchanged, then n × 16-byte extension records in the same order. Extension +0 = curve (slot +53,
  0..7), +1..+6 = matrix (slot +54..+59, −64..64), +7..+15 reserved 0. File size 64 + 80 n.
- Writers (`tools/ep7_looks_bin.py --fw 0.34`, panel firmware option v0.34): v4 only for v0.34 or later and only when a
  colour look sets `curve` or `matrix`; otherwise v3 byte for byte. Mono looks get a zero extension record. Old firmware
  rejects version 4 and keeps the stock Film page.
- Firmware (`patches/looks_v4/lx.s.in`):
  - fm_load reads only the v3 part into L. A size of 64 + 80 n makes it read the header first; version 4 with matching
    n / payload / +36 sets the read size to 64 + 64 n. Any other v3 file loads with the same file calls as before.
  - The extension is read next into its own class-1 block (malloc 520 B, made once), checked (its CRC, ranges, reserved
    zero) and compacted to 8 B per look (curve, mix × 6, 0 for slot +60) behind 'EP7H' and a back pointer to P.
  - Before fm_check, L's header is turned into the v3 header (+4 = 3, +32..37 = 0, CRC rewritten) once the v4 CRC holds,
    so fm_check, looks_split and every other reader of L see a v3 file. L's layout is unchanged.
  - fm_check accepts: P+872 = the block. Rejects: the block is freed. A bad extension: no block, the looks load as v3.
  - Film pick (after look_hw's lh_pk, before looks_split's ls_pick): a library look writes slot +53..+59 from its
    extension and +60 = 0. Own / Stock: lh_pk's snapshot restore, unchanged. No block: as before (clears +53..+59).
  - P+872 is free: no instruction in any edit of the chain uses a displacement 869..875 (build check); the card loader
    writes P+0..815, clean_boot zeroes the whole 1024 B after the malloc, P2 / P3 use +800..959 of their own blocks.

## 3. Other bodies

- **OM-3** (Caduceus for OM-3): no carrier for these fields; its export drops them and the panel says so. Its own slot
  layout already uses +53..+59 for other fields: the E-P7 meaning of these bytes is E-P7 card-file layout only.
- A port that adds them maps the same names and units in its export target.

## 4. Firmware (v0.34a, `patches/look_hw`)

- **Matrix:** at its select site (v0.34c): right after dev_stage_list's call of mono_selector (0x603b149f), which has just
  written the matrix words, N = L·M on them (registers 0x9f001090..), packed by the stock packer, so rows still sum to 0x80
  (1.0). v0.34a/b did this at pipe_hw_write's callers; the camera showed no effect there (the curve, at its select site,
  did).
  - Row order R, G, B, rows = output: settled statically. The firmware's own saturation matrices (table 0x605304e0, written
    to the same registers by 0x603ad106 / the packer) carry the luma weights 0.30 / 0.59 / 0.11 in columns 0 / 1 / 2.
  - Source of the stock matrix: cap+0x5d34 = (colour matrix, properties 0xaa4a / 0xaa6a) × (WB-preset sensor matrix,
    properties 0xa19a..), in 0x60281aa6 / 0x60287f43; RAW Data Edit takes the per-WB set from the MakerNote. The hardware
    multiplies it again by a picture-mode matrix in mono_selector 0x603acfe4.
- **Curve:** at the gamma selector (0x603ae82b in gamma_stage), so the stage's change test, its curve analysis and split
  tone all work on the chosen curve. Rows go through the stock row pick (variant and column as stock).
- Live view: both run in the development stage list that live view shares (split tone, in the same list, works in live
  view on the camera), so the live view should match the photo. Movie and AP: off (the profile getter reads 0 there).
