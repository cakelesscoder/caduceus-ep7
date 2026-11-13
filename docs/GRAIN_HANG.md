# Keys stop working after a grain shot on v0.32 (2026-11-13)

**Report (owner's camera, v0.32, seen twice):** COLOR profile on Gold 200 from Standard 1.1 (tone ends, Glow 1,
highlight split Yellow +1, no shadow split) with Grain Low. The first shot saves. Live view keeps running and the
shutter still takes photos, but INFO, OK and the other keys do nothing until a power cycle.

**Result: no cause found in the firmware.** None of the four suspects explains it from code or the emulator. Three are
ruled out or unlikely. One (pool pressure) is still possible but unproven. v0.32a was built afterwards, once the owner confirmed pool pressure (last section). A ranked list and the
camera test that tells them apart are at the end.
[V] = read in code or the image, or shown in the emulator. [I] = inference.

## What v0.32 changes against v0.31d [V]

Diff of the two `edits.json` (470 vs 431 edits):
- **Capture path:** only the tone hook `0x603b14ff` (`call tone` → `call st`) and st's seven code pieces.
- **Loader:** the SD loader v3 range bytes for +62/+63 (in place).
- **fm_load:** L is 2640 B (was 2560), and fm_check goes through ls_chk.
- **GUI only:** look_editor `k_step` → `xp_step`, the look_extras facade words, the guide words, scp_name, the
  extras_pages, looks_split and i18n_zh code, and the lv_grid OSD bitmaps.
- **Unchanged byte for byte:** grain (r2), grain_kind, halation, recview, bloom/clarity and the work-list hooks.
  So hypothesis 4 (the grain path meeting the glow slot) has no new code to act through. Grain plus glow runs the
  same bytes as on v0.31d.

## 1. Memory-pool pressure from split_tone: possible, unproven

- **Where S comes from [V]:** `st_c` calls `malloc(3120)` once, on the first pass that carries a split (normally the
  first live-view frame on such a look). It publishes S at P+848 and never frees it. Capture and live view share
  the block (set 0 and set 1). A pass only rebuilds a set when its source curve or split word changes.
  - The block is **class 2**: malloc 0x60022782 picks the class by size (≤128, ≤2048, ≤16384) and calls
    `alloc_phys_impl` 0x60022a61.
  - The pool parameter tables at 0x60026df4 / e04 / e34 give class 2 as **43 fixed blocks of 0x4040 B**
    (0xa1dd8d40), shared by every CPU (uncached, behind hardware semaphore 0xa09000a). One allocation takes one
    whole 16-KB block, whatever its size.
- **Emulator [V]** (scratch harness on `patches/split_tone/verify.py`'s fixture):
  - Setup: real malloc, `alloc_phys_impl`, cpu_lock/unlock, ssc lock/unlock and the pool tables from the image.
    The counters (0xa2728f28.., bitmap 0xa2729210) were RAM and the semaphore page 0x8fe00000 was RAM. Only
    prop_get was mocked.
  - Sequence: LV → capture → LV → preview (no marker) → capture → LV, on COLOR1 with +62/+63 = 0x00/0x10 (Gold 200).
  - v0.32 takes exactly **one** class-2 block, on the first LV pass (bump 5 → 6, bitmap 0x1f → 0x3f). Every later
    pass allocates nothing.
  - Capture uses set 0 and LV uses set 1, with no rebuild loop.
  - The semaphore bit is clear after every pass. PSW IE/IM come back as 0xf00 (only the dead Z flag differs).
    No MMIO is touched.
  - v0.31d's same passes allocate nothing.
- **Peak class-2 use by Caduceus during a grain shot [V code, I timing]:**
  - v0.31d: L (LOOKS buffer) plus grain r2's two blocks (16-KB ring and 8-KB T, freed at the pass end) = 3.
  - v0.32: the same plus S = 4.
  - A v0.31d halation look adds halation's 4096-B block and grid block. They are freed before or after grain on
    the same task, so the peak is about the same [I].
- **What is missing:** stock's own class-2 use during a capture, Rec View and the return to shooting. If stock runs
  within one block of the limit, S plus grain's two blocks could make a stock allocation fail. That allocation
  logs "no more heap", dumps (0x60022dcd) and returns 0.
  - A failure on the GUI side could plausibly leave a screen state stuck [I].
  - Nothing static shows stock near the limit, and 43 blocks for one extra is a narrow margin to assume.
- **Hypothesis 3 is ruled out [V]:** 2560 and 2640 are both in 2049..16384, so L stays in class 2 and in one block,
  as before.

## 2. Something left locked or flagged on the capture path: ruled out for st

- st takes no lock of its own. Its only lock is inside malloc, on that one pass, and the emulator shows it released
  with PSW restored.
- Stores [V, emulator and st.s.in]: the stack, S, P+848, O+2596..2607 and C+108 bit 0. On the stock stage list
  0x603b1466, d3 is the stage context C at the hook (`mov a0,d3` at entry), C+4 is the request and C+12 is O.
- **C+108 bit 0 [V]:** the register writer 0x60346eb4 reads it with `btst 1` at 0x60346ed0 and then CPU-copies
  the curves at O+2596.. into its register image (a fourth word at +2608 of the same object is read too [I]). The selector's skip path clears it at 0x603ae9cf. It isn't a wait
  flag or an event, and nothing else in the capture chain tests it.
- st calls prop_get 0x6005e971 on non-marker passes (LV, preview and Rec View jobs). It is a RAM registry read, and
  tone already makes the same call. v0.32 calls it on more passes (there is no pre-scan), but takes no new lock by
  doing so.

## 4. Grain path with a glow look

No v0.32 bytes there (above). One gap, not specific to v0.32: **CPU grain has never been camera-tested with
RAW+JPEG**. The OM-3 port freezes after the photo with RAW+JPEG and grain (androidfanman/caduceus-om3 #18; see
OM3_NOTES, GRAIN_PORT "Open: RAW+JPEG"). The same holds for glow plus grain **without** halation (Standard 1.1's
Gold 200): on v0.31d the owner's Gold 200 was most likely the Standard 1.0 look, with Halo Low [I].

## Ranked list

1. **The grain path with a setting not yet tested on camera** (RAW+JPEG, a drive mode, or Glow 1 + Grain without
   halation). This is not a v0.32 change. It matches "first shot saves, the GUI never comes back".
2. **Class-2 pool exhaustion** from S's permanent block plus grain's two transient ones. This is the only v0.32
   mechanism that touches shared state, but it needs stock to be at 42/43.
3. **The v0.32 GUI layers** (extras_pages `xp_step` / facade, scp_name, i18n_zh, lv_grid). They run only in the
   editor and on the label paths, with no link to a shot. Unlikely.
4. ~~L size (hypothesis 3)~~ ruled out. ~~st lock or flag (hypothesis 2)~~ ruled out in the emulator.

## The camera test that tells them apart

On v0.32, same Gold 200 and Grain Low:
1. Set **Highlight tone colour = Off** on the Colour & Light page and leave the menu so it saves.
2. **Power-cycle.** With no split in any COLOR slot, st never allocates S.
3. Take three JPEG-only shots, then press INFO and OK.

How to read it:
- **Still hangs:** split_tone is out (1 or 3). Next, compare JPEG only with RAW+JPEG, and Grain Off.
- **Works:** turn the split back on with **Grain Off**.
  - Hangs then: st itself.
  - Works then: pool pressure (S plus grain together).

Also ask:
- the image quality setting (RAW+JPEG?);
- the drive mode and Rec View setting;
- whether the later shots also save;
- whether the card lamp stays lit;
- whether MENU and Playback are dead too.

**Fix if (2) is confirmed:** put S in L's class-2 block, past L+2640. The block is 16448 B, so about 13.8 KB is
unused. Keep malloc only as the fallback when there is no LOOKS.BIN. That removes the extra block without changing
the format.

## v0.32a: split tone without a pool block of its own (2026-11-13)

The owner confirmed the pool-pressure diagnosis and asked for the fix. This build is the last section's fix, made
in `patches/split_tone` and rebuilt through `patches/v032/build.py --version 0.32a`. Everything else is as in v0.32.

**What changed:** when P+848 holds no S, `st_c` now jumps to `st_h`.
- **LOOKS.BIN loaded:** P+1020 is 'EP7F', and L = P+1016 is 4-aligned in the class-2 pool with room for S,
  L+2112 = 'EP7L' and L+2116 = P. Then **S = L+2688**, in the unused tail of the LOOKS block. fm_load requests
  2640 B, but the block is 16448 B. There is no malloc.
- **P+1020 is 'EP7X'** (no valid LOOKS.BIN, or fm_load is still reading). This case is handled in `st_w`:
  - A capture mallocs at once, as v0.32 did. A shot can't start while fm_load runs on HLS_EVENT [I].
  - Live view first counts 240 split passes in P+848 (tag 0x5354xxxx, which is never a valid S). A frame during the
    LOOKS read therefore never takes a block that the LOOKS block would make unneeded.
- **fm_load not run yet:** no split on that pass.
- **Code:** `.sth` 0x60210e90 (78 B, sec-1 FF) and `.sti` 0x601de740 (59 B, sec-1 dead EVF). `.stc` grows to 104 B.
  CODE_SPACE_MAP has the claims. `patches/v032/build.py` refuses an L request over 2688 B.

**Can a LOOKS.BIN reload overwrite the curves? No [V, source].**
- fm_load runs at most once per P: it writes 'EP7X' to P+1020 before its malloc, and ed_trig skips it on
  'EP7X' / 'EP7F'.
- Nothing else writes P+1020. The Movie and AP code writes it only in P2 / P3. ap_boot's first-half-press clear
  covers +960 / +980 / +984 / +992, not +1016 / +1020.
- L is freed only on fm_load's own failure path, before it is published. The other frees (mvl 310, ap 943 / 1039)
  are P2 / P3 and the write buffers.
- Writes into L stay below +2640:
  - fread ≤ 2112;
  - the n / pos / snap bytes and the own snapshots 2120..2455;
  - staging 2456..2535 and the art byte 2536;
  - the looks_split tag and stash 2560..2631;
  - ls_sc's CRC rewrite inside the file.
- The Movie and AP Film pages only **read** L (a 2560-B copy into L2 / L3).
- The BUNDLES retry (ap_custom, ≤ 4 per boot) only resets a loader that failed. That P never became valid, so no L
  and no S existed for it.

**Caveat, unchanged from v0.32:** on a restart that keeps DRAM, a new P can hold an earlier session's P+848 /
P+1016 / P+1020 words. ap_boot doesn't clear those. If the block addresses match, st would take the old S (or L)
as valid without its block being allocated in this session. It needs the same block addresses and the tags intact,
and it was not seen on camera. Clearing P+848 and P+1020 in ap_boot would close it; that is not in this build.

**Verify** (`patches/split_tone/verify.py`, v0.31d vs v0.32a):
- **N, C, L, G** pass, now in the LOOKS mode (S at L+2688).
- **A** (new) passes:
  - with LOOKS, S = L+2688, nothing is malloc'd and L+0..2687 is untouched, in capture and in live view;
  - without LOOKS, a capture mallocs, and live view stays stock with the counter at 1, then mallocs on pass 240;
  - 'fm_load not run' and 'bad L back-pointer' are byte-identical to v0.31d.
- **P** passes: decode == stock + edits, restore == stock, no stray bytes, the disk packages match.
- `hang_seq` (real malloc), LV → capture → LV → preview → capture → LV:
  - **with LOOKS.BIN, no class-2 block is taken** (bump stays 6 = L only);
  - without LOOKS.BIN, one block is taken on the first capture, as v0.32 did;
  - the semaphore is clear and IE/IM are kept on every pass.

Package: `generated/v032/rel/patched.pkg.bin` sha256 `83e84b7dfe0261dbd96aa547541af408424f577d51cfe763e9c49fcb7764c546`.
Restore `963f4dfe…2327` (= v0.32). Firmware screen: `Caduceus: 0.32a`. Not camera-tested.
