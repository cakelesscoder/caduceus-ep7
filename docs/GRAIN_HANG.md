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

**Stale P words after a restart** (P+848, P+1016, P+1020 and the rest): closed by `patches/clean_boot`, see
"Clean restart" at the end.

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

## The LOOKS.BIN block's tail: who holds what (halation h6, 2026-11-14)

L is one class-2 block: 16448 B (0x4040) from its start, of which a malloc can ask at most 16384. fm_load asks 2640.
`malloc` returns the block's first byte (index × 0x4040 + pool base, 0x60022a61) and writes nothing into the block [V], so
the rest belongs to whoever claims it here.

| L+ | Holder | Life |
|---|---|---|
| 0..2111 | the LOOKS.BIN file as read (fm_load) | session |
| 2112..2119 | 'EP7L', back pointer P | session |
| 2120..2455 | n, pos, snap bytes, own snapshots | session |
| 2456..2536 | staging T, art byte | session |
| 2560..2631 | looks_split: 'EP7W', P, the split stash | session |
| 2632..2687 | free (fm_load's request ends at 2640) | – |
| 2688..5807 | split_tone S (v0.32a) | session |
| 5808..5823 | free | – |
| **5824..16383** | **halation h6: the cell grid** (GW × GH bytes rounded up to 4: 4944 for a 5184 × 3888 photo, 10560 at most). Cleared, filled and read inside one photo's halation passes; nothing is kept, and nothing reads it afterwards | one capture |
| 16384..16447 | free: the 64 B a class-2 block has past the largest request | – |

- **h6 takes the tail only when the block is proven** (as split_tone's `st_h`): P from `ap_P` (the unswapped block), P+1020 =
  'EP7F', L = P+1016 4-aligned with L+16384 inside the class-2 pool, L+2112 = 'EP7L', L+2116 = P, and the grid fits
  (≤ 10560 B). Otherwise the grid is one malloc, freed at the end of the passes; a failed malloc means no halation.
- **With LOOKS.BIN loaded a halation shot now takes no pool block at all** (h2 took three: 512 B class 1, 4 KB and the grid in
  class 2). With grain g2 (no heap) the whole CPU pass of a photo is allocation-free.
- **Build guards:** `patches/v032/build.py` refuses an L request over 2688. `patches/halation_h6/build.py` `check_l` refuses
  when split_tone's S ends past 5824, when the L request reaches the tail, or when another layer's spec entry carries an
  `L_tail` (`{lo, hi}`) that overlaps 5824..16384. **A layer that wants part of the tail** records `L_tail=dict(lo=, hi=)`
  in its spec entry and moves h6's `L_LO` / `L_HI`: a smaller tail only sends larger grids to malloc (the full-size photo
  needs 4944 B).
- Only the capture task (REC_IMAGE, inside the work list) touches 5824.., and only between `h6_run`'s entry and its return.

## Clean restart: P is cleared before anything can read it (patches/clean_boot, 2026-11-14)

Layer on the v0.33 chain, after halation_h6. Built and emulator-verified; released in v0.33; normal shooting camera-tested, the crash / restart path itself not yet seen on a camera.

**The bug.** DRAM keeps its contents through a crash-restart [I: the 0.30b9 stale marks, AP_CUSTOM.md], and the pools hand
out never-used blocks in index order (`alloc_phys_impl` 0x60022a61: the bump index first, the free stack only once it is
spent) [V]. So the P of a new session is usually a block of the old one. The card loader writes P+0..+815 and nothing above
[V]; what the other layers keep there was trusted as found. `ap_boot` cleared four of those words, and only after the
handle was public.

| P+ | Left by the old session | What it did on v0.33 ([V] emulator unless marked) |
|---|---|---|
| 680..687 | `EP7E`, page, dirty, status, sub-page | With dirty = 1 the first half-press went on to save the table it had just loaded (it opens BUNDLES.NEW). The page is reset when an editor opens [V code] |
| 848 | S, or the live-view wait counter | The tone pass took the old S by its tag and back pointer. The curves it sent to the gamma stage, and the ones it rebuilt, were in a block this session had not allocated |
| 960, 964, 980 | `EP7V`, P2, `EP7T` | Cleared by ap_boot on the first half-press, but public before that: for the length of the crash file write after a fault [V code] |
| 984, 988, 992 | `EP7A`, P3, `EP7U` | As above. +988 was never cleared; it is read only behind +984 [V code] |
| 1000 | grain record | Accepted by its `GDIA` word alone: stage and guard bytes written into a class-0 block that may be someone else's |
| 1004..1011 | mono positions, `EP7M` | Positions not rebuilt from the saved names [V code] |
| 1016, 1020 | L, `EP7F` | fm_load never ran, and L was a block not allocated now. mv_load and ap_load copied 2560 B from it unchecked (a read fault in the emulator when it is unmapped), halation h6 put its grid at L+5824, the Film page and the tone pass worked inside it. With the pools in the same order the Movie slot's L2 landed on the old L and took its back pointer: no Film page on COLOR1-4. After a fault the crash file's copy took that block: no Film page and no split tone |
| P2 / P3: 960, 964, 968 | `EP7V`, a pointer to itself, P's handle | P2 and P3 are byte copies of P (1024 B), so they inherit all of the above. When the BUNDLES retry puts P one block on, on the old P2, `ap_P` reads the new P as a swapped-in slot of the old P: only BUNDLES.BIN loads, and every `ap_P` user works on a freed block |

Not read in these builds: +852 / +856 (plugins, shelved), +928..959 (MONO-colour v0.15), +996 (live_nd `--log`). Nothing
else was trusted as found: L, L2, L3, S, the grain record and the save buffers are initialised by the code that allocates
them [V code].

**The fix.** `cb_zero` (33 B, section 3) clears the whole block, 1024 byte stores, between `sd_load`'s malloc and its
fopen. The block is private at that point: nothing is in it, and the state word says 0xFFFF until the loader publishes the
handle as its last step. So the clear runs before every reader and writer of P on that half-press (the loader itself,
`cl_first`, `ap_pre` / `ap_boot`, `mv_trig`, `fm_load`, `mv_load`, `ap_post`, `ap_load`, `ed_trig`) and before any other
task can find P. P+1000 stays 0 until `gc_mark` makes this session's record.
- **Hook:** `sd_load`'s three instructions after the malloc call (`mov a0,a2; cmp 0,a2; bne`, 0x605b74a1) become
  `jmp cb_zero`, which replays them. No call, no stack, no word or halfword access. Every register but a1 (the loader loads
  it two instructions later), the flags and MDR are as before [V emulator].
- **The retry** (ap_boot's other branch) runs sd_load again, so its new block is cleared the same way. Without a block,
  or without a card, nothing changes.
- `ap_boot`'s own clear stays; it now clears zeros.
- **Code space:** the place of halation h2's `hl_pc`, unused since h6 (CODE_SPACE_MAP "clean_boot").
- **Build:** the v0.33 chain command with `--extra clean_boot=patches/clean_boot/build.py` last (the docstring of
  `patches/clean_boot/build.py`). The layer reads nothing of the grain layers: applied by itself to
  `generated/v033/edits.json` it gives the same edits.

**Verify** (`patches/clean_boot/verify.py generated/clean_boot/base.json generated/clean_boot/edits.json
generated/clean_boot/rel`, all pass). The run is one half-press from `sd_hook` to the stock code after it, on the real
code of every layer on the way. malloc, free and the file calls are logged stubs over the release card's four files.
- **T** 4/4: cb_zero by itself, up to `call ep7_fopen`: registers, flags, MDR and stack == BASE; the block is zero and its
  neighbours untouched; the same at an odd block address; no block.
- **C** 2/2: zero DRAM: the 28 calls (6 mallocs, no free), every heap block, the state word, the boot byte, the registers
  and the stack == BASE. DRAM full of 0xEE: the same calls; BASE keeps 184 such bytes in P, NEW none, and NEW's tables
  are the zero-DRAM ones.
- **R** 22/22: the heap of a finished session left in DRAM (every mark set, an unsaved edit, S, a grain record), four
  ways: the pools give the same blocks; other blocks; the retry; after a fault (crash record in RAM, its file written).
  - NEW each time: the calls and tables of the same half-press on zero DRAM. Where the old blocks are not reused
    (other blocks, the retry), nothing faults with them unmapped.
  - On the first two, the real tone pass (capture and live view), `h6_run` and `gc_mark` then run on that state: S and
    the grid are in the new L, S is built again, the record is new, the Film page is valid, no old block is written.
  - BASE on the same DRAM does what the table says in its [V] emulator rows.
- **N** 4/4: no card; no BUNDLES.BIN (retry armed); the retry; no memory: == BASE.
- **A:** cb_zero's 1024 memory accesses are byte stores into the block, each byte once.
- **P:** package == the emulated image, restore == stock, 123 B differ from BASE (the code, the freed rest of `.hlp`, the
  5 B site), no stray byte.

**Not proven:**
- That DRAM survives on the camera, and in which cases (watchdog reset, power switch with the battery in). The fix does
  nothing wrong if it doesn't.
- That the report in #48 ("crashes, reboots, then needs the battery out") was this. The mechanism fits; no crash record
  from that camera exists yet.
- The order in which the camera's pools hand out blocks after a restart. Four layouts were run; the fix does not depend
  on the layout.
- The emulator runs no tasks. That no other task sees P early rests on the loader writing the state word last [V code].

Package: `generated/clean_boot/rel/patched.pkg.bin` sha256
`494242c368e0dfae8a9abc200f88bd78c1707678d783f61af1e1c7e9fffee04c`, restore `963f4dfe…2327`. Firmware screen
`Caduceus: 0.33`.

**Camera checks:**
1. Everyday use is unchanged: after power-on and one half-press the look names, the Film page, the Movie slot and the AP
   slot are there. Change a look, half-press, power-cycle: the change is still there.
2. After the next restart the camera makes by itself, leave the battery in. Half-press, then check that the Film page
   steps through the looks on COLOR1-4 and that a split-tone photo and a halation photo look right.
3. Power on without the card: stock behaviour. Put the card back: everything loads on the next half-press.
