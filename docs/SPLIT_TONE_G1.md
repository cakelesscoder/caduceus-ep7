# Split tone at G1 (alternative, not built), framing grid notes, looks at card mount (research)

**v0.32 outcome:** split tone shipped with the tone-hook design (docs/SPLIT_TONE.md "As built"), the grid with the
stock-table route of §2 (bitmaps rewritten **in place** in the dead 17:9 grid bitmaps, not appended: the append + placeholder
route of docs/ASPECT.md v8 never showed on the camera). §1 here (G1, LOOKS.BIN v4) stays an unbuilt alternative; §3 is an
open research item.

Status: **stopped before building**. Nothing was flashed, packaged or committed. The card was not touched.
Why I stopped: a second agent was writing `patches/split_tone/st.s.in` at the same time (19:34, a different design:
the tone_ends hook 0x603b14ff, slot +62/+63, its own block S) and building `generated/v031e_scp`. Two split-tone
builds and two sets of code-space claims in one tree would collide. This note holds what I verified so that one
agent can finish. My draft source is `patches/split_tone_g1/st.s.in` (not built or emulated).
Tags: [V] read from the bytes or disassembly this session, [I] inference.

## 1. Split tone

### 1.1 Format proposal: LOOKS.BIN v4 (per the coordinator: slot +53..+56 in the OM-3 order)

The shared look field already exists: `split {sh_color 0..11, sh -5..5, hl_color 0..11, hl -5..5}` (`webapp/src/split.ts`,
packs, `pk1_`). Only the E-P7 card files need a place for it. The v3 record is full [V: +0..44 bundle, +45 class, +46 mask,
+47 tint, +48..63 name, all range-checked by `fm_check`].

- **Header:** as v3, but version (+4) = 4. +32 u32 = CRC-32 (zlib) of the extension section, +36 u16 = 16 (extension
  record length), +38 u16 = 0, +40..63 = 0. The CRC at +16 is **the v3 CRC**: the CRC of the same file with version 3,
  +32..39 zero and without the extension.
- **Body:** the n 64-byte v3 records, unchanged, then **n × 16-byte extension records**, one per look in the same order.
  The logical v4 record is therefore 80 bytes. It is stored as two arrays, so every camera consumer of L+64+64j
  (fm_check, the Film page, mvl, ap_custom, lt_mod, sl_pick) stays as it is.
- **Extension record:** +0..+6 = slot bytes +53..+59: +0 sh_color 0..11, +1 sh s8 −5..5, +2 hl_color 0..11, +3 hl s8 −5..5,
  +4 Auto ISO ceiling, +5 EI shift, +6 gradation (reserved, written 0). +7..+15 reserved, 0. The firmware checks +0..+3,
  ignores +4..+15, and copies only +0..+3.
- **Size:** 64 + 80 n, up to 2624 B for 32 looks.
- **Writers:** the panel writes v4 only when the firmware option is ≥ v0.32 **and** some look has a split. Every other
  file stays byte-identical v3.
- **Readers:**
  - Old firmware rejects a v4 file (version byte) and stays stock, the same as the v0.24 sat-nibble precedent.
  - Old panels refuse it with "only version 3".
  - New firmware reads v3 and v4.
- **Slot (BUNDLES.BIN):** +53..+56 in the OM-3 order, matching caduceus-om3. The SD loader v3 range tables need
  lo/span edits: lo 0x605b76e1, span 0x605b7721, bytes 53..56 → 0..11 / −5..5 [V: all four are 0/0 today]. A downgrade
  to older firmware then rejects such a BUNDLES.BIN, the same as Halo +52 did. The MOVIE.BIN/AP.BIN zero checks from +53
  stay as they are, because no path writes split tone into those slots (below).
- **OM-3 export:** no drop is needed. The OM-3 already does split tone and its target writes +53..+56 for fw ≥ 25 [V
  `webapp/src/om3.ts:150`].

### 1.2 Firmware design (G1, as RE_LIVEVIEW §5)

- **G1 0x603ae830** [V bytes `f8 92 3c 5c 24`, frame `add -260,sp`]: (40,sp) = request R, (36,sp) = O, (60,sp) = select
  result, (68/72/76,sp) = R/G/B. The stage returns by `ret`, after inner calls, so MDR is dead there [V]. The draft saves
  it anyway with `movm [..,other]`.
- **Gate:**
  - the bundles `hl` job guard (callback 0x60355fd4, record scan, marker 0xB2 at job+15490, mode 11, profile 1..4);
  - d0 == 1 with R == G == B;
  - `tbl_idx(k)` entry == P+32+64k. This excludes the flashed table and the AP+Vivid sanitised copy, whose +53.. are 0
    anyway [V ap_tx].
- **Movie and AP:** movie and LV jobs carry no marker. The Movie and AP Film pages run on L2/L3, the copies of L that
  `mvl`/`ap.s.in` make; they copy only 2560 B and point their back-pointer at P2/P3 [V mvl.s.in:236–258]. The split
  block is tagged with the real P, so their slots never get +53..+56.
- **Curves:**
  - Two keyed 1.5 KB sets in L (L malloc 2560 → 7168, still class 2).
  - A new key is built only into the set not handed out last.
  - The stage's change cache word (R+1484)+5736 is cleared when our pointers are handed out, so the LUT always
    re-uploads. That covers the RE_LIVEVIEW stale-LUT rule even if several cache objects exist.
- **Load:** fm_load needs three immediate edits plus one jmp:
  - `mov 2560,d0` → 7168 at 0x6143a439;
  - the size test `and 63` → `and 15` at 0x6143a49e;
  - `cmp 2113` → 2625 at 0x6143a4af;
  - `call fm_check` 0x6143a4ed (5 B) → `jmp st_trim`, which ends `call fm_check` + `jmp 0x6143a4f2`.
- **Pick:** sl_pick's tail `jmp 0x601e37b4` (rel32 at 0x601e3a17) → st_pick → fm_post. lt_mod compares only bytes 0..48
  [V 0x601e247e `cmp 49`], so split doesn't set `*`.
- **Open, check in the emulator:** 0x603b5e8c now runs per channel on three different curves (d0 = 1 with R ≠ G). Stock
  never does that with d0 = 1 [I].

### 1.3 Code space: the blocker to agree first

The free list in EXTRAS_MENU_V2 is stale:
- 0x601de880–0x601dea3c is halation `.hlb` (422 of 444 B differ from stock in v0.31d) [V];
- 0x601df03c–0x601df0e0 is ap_custom (all 164 B differ) [V];
- 0x601e1d78–0x601e1e3c is mostly taken (180 B differ) [V].

What is really free in v0.31d (FF and stock-equal) [V]:

| Hole | Size | Note |
|---|---|---|
| sec 5 0x60b9df10–0x60b9dff0 | 224 | unused tail of ed_view's claim |
| sec 4 0x60747f30–0x60748000 | 208 | only ref is the sec-4 ctor table label 0x60747f1c with count 0 (0x6018e1b3); 0x80dc7f38 hits are data |
| sec 7 0x61378ec0–0x61378f80 | 192 | needs exif_name's claim shrunk to 0x61378eb0 (its code ends 0x61378ead); aperture-ring guard 0x61378f8c |
| sec 6 0x61242c30–0x61242ce0 | 176 | released in 0.31b4 |
| sec 1 0x60210e80–0x60210ef0 | 112 | old aspect boot clamp, removed |

Total ≈ 910 B. The draft links (unrelaxed) to about **950 B**: st_g1 ≈ 450, build + st_k ≈ 225, st_trim ≈ 220, st_pick
≈ 56. Even after trimming it would take nearly all of the space left, with nothing for the Extras v2 table. The
other agent's tone_ends route needs about 250 B plus its own load path. **Pick one design before claiming space.**

## 2. Framing grid: a data-only route found (no GUI_TASK hook, no P3 probe)

- The LV grid selector 0x60e32406 looks up `{aspect, list, count}` in three 6-row tables 0x6118cc00 / cc48 / cc90
  (`mov 6,a0` at 0x60e326c3), then `{value, bitmap}` [V].
- Its aspect is GetValue(270) for stills, or 1/3 forced in movie [V 0x60e32423..0x60e32473]. 270 is never 10, so **row 5
  (aspect 10 = 17:9) and its lists 0x6118c8e0 / c9d0 / cb10 are dead here** [V: those rows and lists are referenced only
  from these tables, xref].
- Slice A (XPan stills grid, 0 B of main code):
  - row 5 aspect 10 → 6 in all three tables (3 × u32);
  - its 5 list bitmap ids → 3 new OSD bitmaps (one per display class).
  Each bitmap is the class's 16:9 thirds size (708×399, 710×474, 628×354), with index-124, 2-px lines: frame lines at
  the 65:24 band and thirds inside it.
  21:9 has no dead row left. It needs relocated tables (288 B) or the OSD-hosted table idea.
- Slice B (ASPECT §7.3): value 8 (diagonal) in the three aspect-3 lists → 65:24 + 21:9 frame lines (3 bitmaps). This
  covers movie and 16:9 stills.
- **Switch:** the stock Displayed Grid setting. Stock already draws it in shooting LV only, so it shows nothing in menus
  or playback, and stock code clears it, so nothing is left behind.
- **Cost:**
  - OSD append through `patches/aspect/osd_icons.py` `encode()` after the current resource-69 end;
  - 6 unused placeholder ids (check O3);
  - about 27 KB per bitmap of mode-11 RLE.

## 3. Looks at mount: not safe to hook directly

- The mount path `card_mount_dcf_init 0x60618b53` (dcfnum.c, callers 0x606189a5 / 0x60618b4a / 0x6061a759) reads
  PARAMDT through the file layer's internal calls [V]: 0x606137f9 and 0x60628c81, not the fopen RPC 0x60634fbc.
- It runs inside the file system's own task context [I]. Our loaders use the blocking fopen RPC to FILECLBK, so calling
  them from there risks a deadlock. It also runs on the boot mount (SD_BUNDLES_V2 §2 rejected 0x608658f6 for the same
  reason).
- A safe version needs a deferred post into HLS_EVENT. That would be a synthetic event that `sd_hook` 0x602c805f accepts
  besides TRIG 0x100/0x101, with the half-press kept as the fallback. That queue API has not been traced, so it is a
  research round plus a deep boot-path test, not part of this build.

## 4. New verified stock addresses

`tools/atlas/new_build032.py`.
