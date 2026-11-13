# Split toning on the E-P7 (scope, 2026-11-12)

Source: Caduceus for OM-3 v0.26 (`st_run` in `firmware/src/editor.s`, `docs/DEVELOPER_NOTES.md` "v0.26 release"),
Apache-2.0. Shared look field: `split {sh_color 0..11, sh -5..5, hl_color 0..11, hl -5..5}` (`webapp/src/split.ts`,
already in packs and `pk1_` links; the E-P7 export ignores it today). Nothing built. [V] = read in code or docs, [I] = inference.

## What the OM-3 does [V]
At the tone hook's exit it bends the job's R/G/B gamma tables in place:
t' = t + ((Ks·ws + Kh·wh) >> 8), ws = ((t·s>>12)·s)>>12, wh = ((t·t>>12)·s)>>12, s = 4095 − t, with a running max so
each curve keeps rising. K = `st_k`[colour] × strength (12 colours). Only for COLOR (key 11); stills and live view.

## E-P7 differences
- **Gamma is ROM, not a job table [V]:** the selector writes one ROM pointer to all three slots, O+2596 / 2600 / 2604
  (`0x603ae7d3`, docs/VIDEO_LOG.md bank A, 256 × u16, 12-bit). So we copy the ROM curve into three 512-B RAM
  buffers, bend each one and point the three slots at them. This takes 1.5 KB of RAM per context (live view and capture), and
  the curve has to be rebuilt when the pointer changes (the same idempotence rule as tone_ends v0.19b).
- **Hook:** the tone_ends hook `0x603b14ff` runs after the gamma pointer is set, with the same gates (key 11, profile
  from job+15488 / getter 0xF6B1) [V for the hook, I for the order]. Code size is about 250 B [I]. It needs new free space (CODE_SPACE_MAP).
- **Look bytes: the LOOKS.BIN record is full [V]:** +0..44 bundle, +45 class, +46 mask, +47 bloom tint, +48..63
  name. Split needs 2 bytes (4 nibbles). Options:
  1. LOOKS.BIN v4 with a larger record, which needs loader and panel changes. Old firmware rejects it (size % 64).
  2. Names cut to 13 characters to free +61..62. This truncates existing names. **Chosen for v0.32** with names
     capped at 12 (no built-in name is longer): `patches/looks_split`, docs/PACKS.md.
  3. Use the free bundle bytes 46..63, which needs a layout.json change.
  The slot entry has space (+45..63 are written on a pick).
- **Camera editor:** the OM-3 adds wheel pages 5 / 6. Leave these out of the first slice: the look is set in the Control Panel only.

## Plan (smallest testable slice)
1. Decide the record format (above). This is a format question, so agree it in this repo first (AGENTS.md).
2. Firmware: RAM curves + bend at the tone hook, COLOR stills and LV. Port `st_k` and the formula unchanged.
3. Control Panel: E-P7 export writes the split bytes; the preview already has `bendSplit`.
4. Camera test: one look with Gold-200-style warm highlights / cool shadows against the panel preview; grey card stays neutral at 0.

Estimate: 1–2 agent sessions after the format decision. Risk: low–medium (it edits a table like tone_ends, but it is a new RAM
buffer in the live view path).

## Port session notes (2026-11-12, handed over unfinished)

State: `patches/split_tone/` has a draft `st.s.in` (our own code, same formula and `st_k` as OM-3 v0.26 / `split.ts`)
and a draft `build.py` (`apply(spec, version)`, layered on v0.31d). **Not built, not emulator-run, no verify.py, nothing
in generated/.** The build.py REGIONS table is stale (written for an older 6-section layout; see "Code space" below), and
`check_free`'s alias scan needs the per-section flash source offsets from the descriptor table.

### Facts checked this session [V = code/disassembly]
- **Order [V]:** stage list 0x603b1466 calls the gamma selector 0x603ae80d at 0x603b14a6, before the hook 0x603b14ff, on
  the same (beq 0x603b14ea) path. The selector's setter 0x603ae7d3 writes R/G/B = a1/d0/d1 to O+2596/2600/2604 (three
  pointers, may differ) and clears O+4 bit 12; 0x603ae7ee sets O+4 bit 12 (gamma off). The setter's other caller
  (0x603af2db, in 0x603af1f1) belongs to the second stage list 0x603b1517 (art keys), not ours. No stage after the hook
  in 0x603b1466 touches the slots (imm-offset grep).
- **Selector skip path [V]:** when key/inputs and the cached ROM pointers are unchanged it jumps to 0x603ae9cf, clears
  **C+108 bit 0** and does **not** rewrite the slots. So in LV the slots can still hold last pass's pointers (ours).
- **Register writer [V code, I meaning]:** 0x60346eb4 reads O+2596; skips if 0; re-copies gamma when its "context
  changed" flag is set or C+108 bit 0 is set. R = G = B uses a shared path; distinct R/G/B has its own path (stock
  supports three different curves). So after changing pointers without a selector rebuild, set C+108 bit 0.
- **Gamma source [V, VIDEO_LOG]:** COLOR uses row 0 `0x604ede78` (variant `0x604ee078` by request type), not the identity
  curve; the bend is a function of t only, so it equals `split.ts` bending the display value.
- **malloc in pipeline context [V]:** stock does it (0x603383d5 lazily allocates 9292 B and keeps it in a global;
  0x6035e52d). malloc masks interrupts and takes a lock; failure returns 0 and logs.
- **Movie / AP [I strong]:** the real getter 0xF6B1 returns 0 when the picture mode isn't COLOR (v0.26 `mv_prof` relies
  on it), so calling 0x6005e971 directly (not tone's redirected call) keeps split out of movie and AP LV. AP stills
  reach the slot via `tbl_idx` → `ap_tx` (sanitised row; AP.BIN requires +53..63 = 0), so split is off in AP too.

### Slot bytes chosen
- **+62 Shadows, +63 Highlights**: low nibble colour 0..11, high nibble strength s4 −5..5; colour ≥ 12, strength 0 or
  outside −5..5 = off. Every build has these at 0: the v0.31d loader range table (sd_lo 0x605b76e1, sd_span
  0x605b7721) has span 0 for +53..63; MOVIE/AP loaders zero-check +53..63; a Film pick leaves +50..63 alone (u_apply copies bytes 0..49 since v0.25;
  v0.32 looks_split then writes +62/+63 from LOOKS.BIN, or the snapshot for Own / Stock). Kept clear of the EXTRAS_MENU_V2 plans (+53..56 split as s8, +57..59 AE).
- **The loader must change for any card test:** with span 0 a BUNDLES.BIN with +62/+63 set is rejected (and so would the
  camera's own save be, lesson #10). Minimum: sd_span[62] = sd_span[63] = 0xFF (2 data bytes, as halation did for +52).
  This contradicts "don't change the loader": needs the user's decision. v0.31d and older reject such a file.

### Design in st.s.in
- Chained: hook rel32 0x603b1500 → `st`; `st` pushes everything with `movm [d2,d3,a2,a3,other]`, pops, `jmp tone`
  (0x601e103c).
- Gates: P valid (state 0x622cbcc2, 'EP7B'; implies all sections loaded, so later-section pieces are allowed after it),
  O+4 bit 12 clear, slots = one of our sets (base = that set's source) or R = G = B (base = it); then tone's job guard
  (callback 0x60355fd4, record scan, parent), key word 0x000b0000, capture marker 0xB2 + mode 11 + profile job+15488, else
  LV getter 0xF6B1; slot via `tbl_idx` 0x6055e7b0.
- RAM: one malloc block S of 3120 B (class 2, uncached), pointer at **heap P+848** (P+688..999 has no user except movie
  960..983 / AP 984.. [I, grep of sources and build scripts]), S+0 'EP7S', S+4 P back-pointer, range-checked in the
  class-2 pool 0xa1dd8d40–0xa1e85800. Two sets (capture, live view) of 16 B header {source, word} + R/G/B 512 B each.
  Allocated only on the first pass with a split; rebuilt only when (source, word) changes; repointed without rebuild
  when the set already holds that curve; any miss with our curve in the slots restores base in all three + C+108 bit 0.
- Bend: t clamped to 4095 (the only difference from OM-3's integer formula), then OM-3's `ws/wh/K>>8`, clamp, running
  max per channel.

### Code space: the blocker [V measured]
The draft assembles to **~820 B** (seven sections incl. 36-B `st_k`), about 3× the earlier 250-B estimate (imm32
constants, gates copied from tone, alloc, restore path). Unclaimed free space left in v0.31d (sec 1/2, no other edit,
step-table refs only) is only ~300 B: dead EVF 0x601de740–0x601de780 (64), 0x601e1bec–0x601e1c3c (80),
0x601e3900–0x601e393c (60), sec-1 FF 0x60210e90–0x60210ef0 (96, retired bloom/aspect-clamp block, FF guards e70–e90 and
ef0–f00). (0x601e1c3c–0x601e1d3c is guarded by fw_version's overlap check; section 7 left to the SCP-label work.)
Fitting needs unused tails of other claims: live_nd 0x601de6d0–0x601de740, mono presets B 0x601e1a90–0x601e1b3c,
look editor sec-6 0x61242c38–0x61242cf0 (the "released 0.31b4" tail), or ed_view sec-5 0x60b9df10–0x60b9dff0. Planned
shrinks (~60 B): drop the LV pre-scan of +62/+63, detect "ours" by the R slot only. **Nothing is claimed in
CODE_SPACE_MAP.**

### Estimates [I]
- LV per pass with P valid: ~60–150 instructions plus one getter call; rebuild only on change: 3 × 256 × ~38 ≈ 29 k
  instructions (≈0.1 ms). Two LV contexts with different sources would rebuild every pass (still sub-ms) and could share
  a set mid-rebuild (one wrong frame).
- Open risks: P+848 not formally free; C+108 bit 0 meaning inferred; a lost malloc race leaks one block; split values
  edited without a selector rebuild show at once only via C+108 (unproven on camera).

### Still to do
Final placement + build (version per the v0.32 owner), `verify.py` (emulator: hook span 0x603b14ff → 0x603b1506 with
P/S regions mapped and a malloc stub; bend == Python integer model of OM-3 `bend()` with the t clamp, bit-exact; split.ts
float model within rounding; gates off == v0.31d registers/memory; repeat pass stores nothing; restore on miss),
anti-brick P/S checks, a test BUNDLES.BIN (tools/ / patches/sd_bundles_v3) once the loader span question is decided.

Camera test (once built): 1) no card split values → identical to v0.31d. 2) BUNDLES.BIN with COLOR1 +62 = 0x58
(Cyan, +5) and +63 = 0x51 (Orange, +5): LV and a JPEG show cool shadows / warm highlights; a grey card at mid stays near
neutral. 3) Switch to COLOR2 (no split) and MONO: tint gone in LV and photos. 4) Movie and AP: no tint. 5) Power-cycle
after an editor save: the card still loads.

## As built (v0.32, 2026-11-12; emulator-verified, not camera-tested)

Built from the port session's draft (`patches/split_tone/`), layered by `patches/v032/build.py` after scp_name.
- **Fixes to the draft:**
  - st kept P at (0,sp), where every `call` stores its return address, so P was overwritten on the first inner call.
    The locals now start at (4,sp), with a 52-B frame.
  - `call st_kv,[],0` → `[],4`.
  - P comes from ap_custom's **ap_P** (0x601df03c, sec 1). With the Movie or AP wheel swapped in, S is still found in
    the real P. P2 keeps its MOVIE.BIN file buffer at +800..895, so P2+848 is not free.
  - The live-view pre-scan was dropped: the getter is called on LV passes that carry a split.
  - The exit `st_x` sits in the sec-1 gate piece, so nothing before the P check leaves sec 1.
- **Loader:** the SD loader v3 range bytes for +62/+63 are now lo −128 and span 255 (4 data bytes). The check is
  `(s8 byte − s8 lo) ≤ span` unsigned. Span 255 alone would still reject a negative strength (high nibble ≥ 8). st
  checks the nibbles itself.
- **P+848 [V]:** grep of every `.s.in` and build-script constant. Loader staging ends at +815, mono_colour uses
  +928..955, movie +960..983, AP +984..995, live_nd +996, the editor probes +1000/1002, film +1016..1023. In P2, +848 is
  file-buffer space, which is why st uses ap_P.
- **0x603b5e8c:** it never sees our curves in this design [V]. The gamma stage calls it on its own frame pointers
  (68/72/76,sp), which are the selector's ROM pointers. Ours go only into O+2596..2604, after the stage, at the tone
  hook. The stage's only O-slot read (O+2600 at 0x603aeacd) is in the art-key branch (keys 0x01010064..0x01030069),
  after its own setter. Only the register writer 0x60346eb4 consumes our curves, and it supports three different
  curves [V].
- **Placement** (CODE_SPACE_MAP "v0.32"): 783 B across sec 1 (48 + 76), sec 5 (196), sec 4 (178) and sec 7 (285).
- **Verify** (`patches/split_tone/verify.py`): N, C, L, G and P pass.
  - N (boot-path no-op): byte-exact registers, MDR, LIR, LAR, stack and fixture against v0.31d. PSW differs, but it is
    dead at tone's entry.
  - C: the bend equals the integer model bit for bit on stock row 0, three distinct curves. A repeat pass stores
    nothing, a new word rebuilds, and split 0 restores.
  - L: live view uses set 1; getter 0 → stock.
  - G: 7 gates.
  - P: decode == stock + edits, restore == stock, no stray bytes.

### Format note (proposal: the E-P7 slot bytes; the shared look format is unchanged)
- The shared field is the existing `split {sh_color 0..11, sh −5..5, hl_color 0..11, hl −5..5}` (packs, `pk1_`). Its
  meaning is the same on both bodies; OM-3 stores it at record +53..+56.
- On the E-P7 it lives in the **BUNDLES.BIN COLOR slot**: +62 = sh_color | (sh & 15) << 4, +63 = hl_color | (hl & 15) << 4.
  0 means off. MONO slots and MOVIE.BIN / AP.BIN keep 0.
- The Control Panel writes it only for firmware ≥ v0.32 (`webapp/src/format.ts` `placeLook`), so files for older
  firmware are unchanged. v0.31d and older reject a BUNDLES.BIN carrying it.
- LOOKS.BIN stays v3. Its split goes in the record's name tail (+61/+62, names at most 12 characters) and a Film pick
  copies it to slot +62/+63: `patches/looks_split`, docs/PACKS.md "Split tone on the E-P7". (Without that layer a pick
  left +62/+63 alone: u_apply copies slot bytes 0..49 only.)
- The OM-3 export already writes +53..+56, so nothing is dropped.
