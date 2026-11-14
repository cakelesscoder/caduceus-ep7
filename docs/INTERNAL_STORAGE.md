# Looks in the camera's own memory (research and design, E-P7 1.1)

Research and design only: **nothing is built, no patch, no camera test.** Issue: every look lives on the card today
(`EP7MOD/LOOKS.BIN` 2112 B, `BUNDLES.BIN` 680 B, `MOVIE.BIN` 96 B, `AP.BIN` 96 B, loaded at the first half-press). The goal is
looks kept in the camera, so any card works and no `EP7MOD` folder is needed.

- **[V]** = read in code or bytes, or emulated here. For the OM-3: read in that project's repository (notes, source, issues);
  its camera results are as that project reports them. **[I]** = inference.
- The method follows the OM-3 port (§1, credit in §6). OM-3 addresses don't apply to the E-P7.
- Scripts behind §2 (ours, no firmware bytes): `~/ep7fw-private/decomp/internal_storage/` (`walk_banks.py`, `scan_tail_refs.py`,
  `emu_mode_tail.py`). New symbols: `tools/atlas/new_internal_storage.py`.

## 0. Short answers

| Question | Answer |
|---|---|
| Feasible? | **Yes.** The E-P7 has the same settings store as the OM-3, one generation older [V §2.1], and the same kind of unused room |
| Where | The unused tail of the **MODE bank** (the camera's user-settings image, RAM `0x624ea400`, 0x40000 B). Its records end at image offset 0x255b0; **109,132 B are free** [V §2.2]. Proposed block: image offset **0x3A000** (RAM `0x62524400`, uncached alias `0xa2524400`), 3,080 B used of a 4 KB reserve (§3.1) |
| How big | All four files as they are: 3,080 B with header. Smallest useful form: `BUNDLES.BIN` alone, 776 B (§3.2) |
| Who saves it | **The camera's own settings save**, `settings_save 0x602cc6dd`, at power-off and at sleep (also after a firmware update). It compares the whole image with the last saved copy, so a change in the tail is saved like any setting. We never call it and never write flash [V §2.5, emulated §2.9] |
| Reset | A menu Reset (Basic or Full) **does not clear the tail** on the E-P7: every reset path writes settings one by one [V §2.6]. The OM-3 project expects a Reset to clear its block (untested there) |
| Restore to stock, re-install | The updater doesn't touch the bank's flash and saves the image as it is in RAM. The block **survives** the restore file and any later install [V §2.7]. Stock never reads it. A "forget" action is needed to remove it (§3.6) |
| Biggest risks | (1) a wrong store into the settings image outside the block is saved and is **not undone by the restore file**; (2) our write landing between the camera's checksum and its flash write (the camera then falls back to its previous copy); (3) nothing here is camera-proven yet, including that nothing else uses the tail (§5) |
| First risky camera step | A **16-byte marker** written at the block address (step S1), after a read-only probe (S0) that carries no risk to the settings (§4) |
| Estimate | 4 to 5 agent sessions and 4 short camera rounds (§4) |

**Correction to [RE_SETTINGS.md](RE_SETTINGS.md) §4:** the MODE and EEROM banks do have two flash copies. The settings layer
names one shadow per bank, but the flash layer under it alternates two slots and picks the newer valid one at boot [V §2.4].

## 1. How the OM-3 port does it

Read from a shallow clone of `androidfanman/caduceus-om3` at `0b1d5cb` (2026-11-13, v0.29.1), as data only; none of its code
was run. Research and design: iancw (their issue #35 and PR #36, which holds six traces and the design spec; not merged). Built
and camera-tested by androidfanman in v0.29-beta, v0.29 and v0.29.1.

| Topic | OM-3 [V their repo] |
|---|---|
| Region | "Store M", the camera's settings image: RAM `0x62920700`, 0x40000 B, two alternating flash copies, 8-byte header `{u16 id, u16 checksum, u32 counter}` |
| Room | 1,215 items end at image offset 0x39465. 27,535 B up to size − 12 belong to no item. The block sits at **0x3A000** (0x39465..0x3A000 left as a margin) |
| How "unused" was shown | They walked M's layout list (`{u16 code, u16 count, defaults}`, at `0x600e4bec`) and got the same 1,215 objects and end offset as the emulator's live object table. The list's three users stop at its terminator. The tail is zero in a blank-camera image. Then a camera probe (below) |
| Who writes flash | Only the camera: `0x60063d73` (the GUI's `saveUserSetup`) writes M when the "changed" byte `0xa32bfb32` is 1, on the **return to shooting after a menu or Picture Mode**, and M is saved at **power-off** too (emulator). Counter + 1, 16-bit sum of the whole image made 0, next slot programmed. Load copies the whole image; a slot is valid when its id matches and the whole image sums to 0 |
| What their code does | Builds the block in a staging buffer, then, with dispatch held and only while the camera's own save isn't running (busy byte `0xa32a9904`), copies it to the cached and the uncached address and sets the changed byte. If the save is running: a pending flag, and another try at the next shutter event. It never calls the save |
| Format | `OM3U`, version 1, length 3,912, CRC-32 of bytes 16.., generation, a ring of 16 film-set identities, then the `LOOKS.BIN`, `EDITS.BIN` and `BUNDLES.BIN` images **byte for byte** (their parsers are reused; only the container is new) |
| Card rule | A valid block wins. A card's `LOOKS.BIN` is taken only when its identity (CRC-32 of records and names) is **not in the ring**: "films the camera never had". The camera keeps its selection and the edits of films that didn't change. `EDITS.BIN` and `BUNDLES.BIN` are read only when there is no valid block (first start). Nothing is written to the card any more (owner's choice) |
| Reset, update | "Probably clears" for a menu Reset and an OM update: **not tested**. Their own update kept the block (camera: written under one build, read by the next) |
| Proof on the camera | Probe `mp1`: a 16-byte marker (`OMPB`, counter, version, CRC-32) at 0x3A000, written at the first shutter event, never calling the save. It survived two battery pulls; the store's own counter went 4672 → 4674; the camera's settings were unchanged |

**Problems they hit [V their notes and issues]:**
1. Their emulator stubbed the settings save, so the first trace saw no save at all. Persistence needed a mode that runs the
   stores' saves natively and keeps the image between runs.
2. Frames: three new routines saved four registers in a 16-byte frame, so their own calls overwrote a saved register. It was
   harmless in the first build and broke the next one.
3. **v0.29, no looks without a card** (their #38): the first-half-press gate still waited for a mounted card. v0.29.1 goes on
   when no card is mounted and the block is valid. Side effect: a card that isn't mounted yet at that half-press has its new
   looks taken at the next power-on.
4. **Loading at start-up was given up.** v0.26.2's automatic load caused rare freezes (v0.27.1 removed it). A v0.29 test build
   that loaded from the block at start-up made switch-on lag. Their conclusion after three start-up failures: leave the
   camera's start-up alone. This matches our [BOOTLOOP_T3.md](BOOTLOOP_T3.md) and [AUTOLOAD.md](AUTOLOAD.md).
5. Their Control Panel can no longer read on-camera changes from the card.
6. A battery pull before the next save loses the last change. Worst case named: the camera refuses its image and resets all
   its own settings. That never happened in their tests.

**What doesn't carry over:** their changed byte and the save on leaving a menu. The E-P7 has neither (§2.5, §2.11).

## 2. The E-P7's settings store, as far as this design needs it

Base: [RE_SETTINGS.md](RE_SETTINGS.md) and ATLAS §3. Everything below was re-read in the bytes or emulated.

### 2.1 Same store, one generation older [V]

- The debug tags are the ones the OM-3 notes quote (`FlD`, `BlD`, `ElD`, `MlD`; here also `…lR` for "rebuilt from ROM"), at
  `0x60078ace`. The default builder returns the same error 7427 and subtracts the same 12 bytes (`0x6005e309`).
- `settings_save` carries id 0xf001e (983070), the id the OM-3 trace gives for its "save E + M" wrapper.
- MODE is device 7, as the OM-3's M is kind 7.

### 2.2 RAM images, layout, free room [V walk of the ROM lists; MODE also emulated]

Image: `{u16 id, u16 checksum, u32 generation}`, then the values packed in ROM-list order (each aligned to its width), then
unused bytes up to the size. The default builder counts against size − 12.

| Bank (device) | RAM | Size | Records | Packed end (image offset) | Free |
|---|---|---|---:|---|---:|
| **MODE (7)** | `0x624ea400` | 0x40000 | 1,084 | `0x6250f9b0` (0x255b0) | **109,132 B** (0x255b0..0x3fffc) |
| EEROM (6) | `0x624da400` | 0x10000 | 125 | `0x624deec9` (0x4ac9) | 46,387 B |
| BKRAM (3) | `0x6252a400` | 56 | 14 | 0x24 | 16 B |

- MODE's last record is key `0xfa64` (27 words at 0x25544). 84 % of the used part is the snapshot array `0x85d4` (128,160 B).
- The banks lie in .bss (0x621caf00–0x62796888), which the start code clears on every start (call at `0x60020074` [V]; that
  the fill routine `0x6002046d` zeroes is [I], it isn't emulated). So the tail is zero in RAM until the load copies an image
  over it, **also after a crash-restart that kept DRAM** (§3.5). If that clear ever failed, the worst a stale tail could
  hold is an old block of ours or bytes that fail its CRC.
- The last 4 bytes of an image are in the checksum but outside the save's compare (§2.5). The design doesn't use them.

### 2.3 Checksum and validity [V bytes; emulated]

- `prm_bank_cksum 0x6005c7f3`: the negated 16-bit sum of **every** halfword of the image except the checksum word itself.
- `prm_bank_check 0x6005c78a`: valid when the first halfword equals the bank id and all size / 2 halfwords sum to 0.
- So the tail is sealed and checked like the settings: one changed tail byte after the checksum makes the image invalid.

### 2.4 Two flash slots under one shadow [V bytes]

- The settings layer sees one "shadow" per bank: a RAM mirror of the saved image (MODE `0xa2a78000`). Its second-copy field is
  empty (`0x6005dc4b`), which is why RE_SETTINGS read "no A/B".
- The flash layer keeps a slot table (RAM `0x61b21368`, 2 × 28 B `{size, shadow, flash}`; filled at boot from ROM
  `0x6002e3a8` by the data copy at `0x60020117`): **slot 0 = `0x40240000`, slot 1 = `0x40280000`**, both for the same shadow.
  EEROM has `0x402c0000` and `0x402e0000`.
- **Save** (`0x600216fd`, reached from `flash_write` for MODE addresses, class 2 of `0x6005b634`): the slot byte `0x61b213a1`
  flips, that slot is erased and programmed from RAM, and the slot is read back into the shadow.
- **Boot** (`0x6005b6cc`): reads both slots' headers and compares the generations. The slot that is one ahead is read in full
  and its sum is checked. **If the sum is wrong, the other slot is loaded instead.** If neither generation follows the other
  (two blank slots), both are erased.
- So an interrupted or torn save costs the changes since the save before it, not every setting [V code; I on real NAND
  behaviour].

### 2.5 Save routine and its triggers [V]

`prm_bank_save 0x6005c5be`: compares RAM + 8 with shadow + 8 over size − 12 bytes. If equal, nothing is written. Otherwise:
generation + 1, checksum, D-cache flush, then `prm_flash_op(size, 0, uncached RAM, shadow)`. There is no "changed" flag and no
busy flag: the compare is the trigger.

| Trigger | Entry | Banks |
|---|---|---|
| Power-off | `OlyHfwPower::startShutDown 0x607a957a` (`0x607a9978`, and `0x607a943e` with the power-off reason) | EEROM + MODE (`settings_save`), BKRAM |
| Sleep | `0x607aa1d6` (`0x607aa4e0`), early in the routine [I: before the camera sleeps] | EEROM + MODE, BKRAM |
| After a firmware update, success or failure | `0x601e729e` ("Power OFF" / "Power Reboot"), from `fw_report_ok 0x601e7094` and the fail report `0x601e71b6` | MODE |
| Update check, PTP update | `0x609a6c4b`, `0x60c4970b` | EEROM + MODE |
| Boot, only when the MODE image was refused | `0x602b039a` (from `boot_tail_resets`): all settings to defaults (`0x602b962f`), then `settings_save` | EEROM + MODE |
| Fatal stops | `0x604057e3` (error code, save, lock, spin); `0x6011f48b` and the lens-update path `0x60559357` [I: their roles] | MODE |
| Factory, service and debug paths | factory-setting reset `0x607ac5eb`, self-adjust, life tests, the ADJ task, the settings command table `0x602cb832`, the debug shell | various |

- **Never on a setting change and never on leaving a menu.** All 21 `prm_ctl` call sites were decoded; none is a GUI path.
  A change made in a session reaches flash at the next power-off or sleep. A battery pull before that loses it, as it loses
  the camera's own setting changes.
- Stock writes a value to the cached address and to its uncached alias (`0x6005eadf`), on CPU0 only; other CPUs send the
  write to CPU0 (`prop_set 0x6005ea22`). The checksum reads the cached image; the flash write reads the uncached one after
  the flush.

### 2.6 Load at boot, and what resets do [V]

- `prm_banks_init 0x6005daeb` clears each image's first 16 bytes and runs the load. `prm_bank_load 0x6005c524` copies the
  **whole** shadow to RAM (size / 4 words) when the check passes.
- When it fails: flag `0xa2715cb8`, then `prm_clear(7)`. That rebuilds the records from ROM (`0x6005e309`) and **doesn't touch
  the tail**, which is still zero because nothing was copied. Then `0x602b039a` sets every setting to its default and saves at
  once. A refused image therefore ends with a clean bank and an empty tail.
- **Menu resets write settings one by one:** the two list resets `0x602b3a60` (626 ids) and `0x602b3a8c` (1,785 ids), the
  boot-time `reset_pick`, the factory-setting reset and the full default pass `0x602b962f` all go through the settings
  functions. Which list is "Basic" and which "Full" is [I].
- `prm_clear(7)` has two callers: the failed load and the debug shell's `clear`. Bank erase (`prm_ctl` op 3) is reachable only
  from the debug shell (`0x6005d5a0`); the factory-adjust handlers save and reload.
- **So nothing a user can do clears the tail except a refused image.** A Reset leaves it alone.

### 2.7 What the updater does [V]

- The container's components sit at `0x406a0020` (main), `0x421a0020`, `0x43aa0020` and `0x467e0020`, plus the sub-CPU
  firmware. None covers `0x40240000`–`0x402fffff`, and the updater writes components only (FIRMWARE_GUIDE §1).
- After the update it saves MODE from RAM (§2.5). RAM holds what the boot loaded, tail included.
- So **the tail survives every update, the restore file included.** This is the fact that kept us away from settings memory.
  The OM-3 saw the same on the camera for its own update. Our own experience agrees: E-P7 settings survive a flash [I for
  the tail].

### 2.8 Is the tail really unused? [V for static use; I for run-time use]

1. **No record reaches it.** All 1,084 records end at 0x255b0, and the registry stores a pointer and a count per record.
2. **The bank's addresses are named only by the store itself.** Every absolute reference to `0x624ea400`, `0x6252a400` and the
   bank object pointer `0xa2711a9c` is inside `0x6005d6c6`–`0x6005f402`. Those routines copy, sum, compare or program the
   whole image, or stop at the records.
3. **No reference into the tail.** A scan of all 26 MB at every byte offset for a 32-bit value in `0x6250f9b0`–`0x6252a400`
   or `0xa250f9b0`–`0xa252a400` gives 191 raw hits. None is the operand of an instruction with a 32-bit operand (`fc` and
   `fe` forms), none is an entry of a pointer table (the aligned hits outside known functions were read one by one), and the
   hits near the proposed block are the loop idiom `inc d2; inc4 a2; cmp d0,d2` (bytes `48 52 a2`). The decompiled corpus
   (56,440 functions) names one address in the range: the bank's upper bound in `prm_device_of`.
4. **The end cursor is debug-only.** The default builder stores the first free address at `0xa2715ab8`. Its only reader is the
   debug shell's `size` command (`0x6005e57b`), which rebuilds the defaults as a side effect and is never run by the camera.
5. **Not shown:** a write through a computed pointer, and that the tail is zero in a real camera. Step S0 reads both (§4).

### 2.9 Emulated with the stock routines [V emulated]

`emu_mode_tail.py` runs the stock code on a MODE image with bytes in the tail. `prm_flash_op` is a breakpoint, never run.

| Check | Result |
|---|---|
| Default build over an image filled with 0xA5 | Records written, end cursor `0x6250f9b0`, all 109,136 tail bytes untouched |
| Stock checksum, then stock check, with a marker at 0x3A000 | Sum 0, accepted. One tail byte changed afterwards: refused |
| The save's compare, tail-only difference | Seen |
| `prm_bank_save`, RAM differs from the shadow only in the tail | Reaches the flash call with size 0x40000, mode 0, source `0xa24ea400`, destination `0xa2a78000`; generation + 1; sum 0; tail kept |
| `prm_bank_save`, RAM equal to the shadow | No flash call |
| `prm_bank_load`: valid shadow, then a shadow with a wrong sum | Copied whole, tail included; not copied (returns 1) |

### 2.10 Other homes considered

| Home | Verdict |
|---|---|
| **MODE tail** | **Chosen.** User-settings bank; a lost image means a settings reset, which the camera handles itself |
| EEROM tail (46 KB free, saved by the same call) | No: the bank holds non-user data, and a refused EEROM image is rebuilt from ROM [I: what that loses] |
| Spare snapshot slots in key `0x85d4` (9 × 14,152 B) | No: registered storage that stock rewrites; which slots are spare is unproven |
| ICTLOG (mirror `0x62de0000`, flash `0x47b00000`, RE_CAPTURE §4) | No: the service log, saved only at power-off, free room not mapped |
| Unused persisted sids (RE_SETTINGS §7) | No: a few bytes each, and stock validates and resets them |
| Our own flash write | Ruled out |

### 2.11 Differences from the OM-3 that shape the design

| | OM-3 | E-P7 |
|---|---|---|
| What makes the camera save | A "changed" byte, which their code sets | The compare with the shadow: nothing to set [V] |
| When | Leaving a menu or Picture Mode; power-off | Power-off and sleep only [V] |
| Save-in-progress signal | A busy byte | None. RAM generation ≠ shadow generation from the save's first step until its read-back (§3.4) [V] |
| Menu Reset | Expected to clear the block (untested) | Doesn't clear it [V] |
| Free tail | 27,535 B | 109,132 B [V] |
| Files to keep | Films, edits, Extras; code and pictures moved into the firmware | The four card files. Our code is already all in the firmware |

## 3. Design

### 3.1 The block

- **Address:** MODE image offset 0x3A000: cached `C = 0x62524400`, uncached `U = 0xa2524400`. Reserve 0x3A000..0x3B000 (4 KB);
  version 1 uses 3,080 B. It starts 84,560 B above the last record, and the reserve ends 20,476 B before the end of the
  compared area. The offset equals the OM-3's by choice; nothing depends on that.
- **Format, version 1:**

| Offset | Size | Field |
|---:|---:|---|
| 0 | 4 | magic `EP7I` |
| 4 | 2 | version 1 |
| 6 | 2 | length 3080 |
| 8 | 4 | CRC-32 (zlib) of bytes 12..3079 |
| 12 | 4 | generation, + 1 at every write |
| 16 | 1 | present bits: 0 BUNDLES, 1 LOOKS, 2 MOVIE, 3 AP |
| 17 | 1 | next ring place |
| 18 | 2 | `LOOKS.BIN` length (64 + 64 n; 0 = none) |
| 20 | 2 | `BUNDLES.BIN` length (544 or 680) |
| 22 | 10 | zero |
| 32 | 64 | ring of 16 identities the camera has taken from a card |
| 96 | 680 | `BUNDLES.BIN` image |
| 776 | 2112 | `LOOKS.BIN` image, zero padded |
| 2888 | 96 | `MOVIE.BIN` image |
| 2984 | 96 | `AP.BIN` image |

- **The files are stored byte for byte**, so the loaders' own checks (`sd_check`, `fm_check`, the MOVIE and AP checks) run on
  the block's copies unchanged, and the shared formats, share codes and the Control Panel's export don't change.
- **Identity** of a file = its own CRC word (`BUNDLES` +16 xor the name CRC at +676, `LOOKS` +16, `MOVIE` / `AP` +12), xor a
  constant per file kind. The loader has already verified that CRC, so the identity costs nothing.

### 3.2 What is stored, and the minimum

| Form | Bytes | Gives |
|---|---:|---|
| Header + ring + `BUNDLES.BIN` | 776 | The eight slots as they render, with names: the looks in use work on any card |
| + `LOOKS.BIN` | 2,888 | The Film page's library too |
| + `MOVIE.BIN`, `AP.BIN` | 3,080 | Everything the card holds today |

Room is not the limit (109 KB). Version 1 stores all four.

### 3.3 Reading: first half-press only, nothing at boot

The block is already in RAM (the camera's own boot loaded it), so reading it needs no file and no flash call. It is still read
only at the first gated half-press, in HLS_EVENT, where the card files load today, through the cached address `C`. Boot stays
untouched (§1 problem 4).

**Where the camera copy goes in:** in place of the file read, not around it. `sd_load` keeps its order: malloc P, `cb_zero`
(patches/clean_boot clears all 1024 B of P), then the 680 bytes from the card **or from the block**, then `sd_check`, and the
handle published last. `fm_load`, the MOVIE load and the AP load do the same for L, P2 and P3. So a look from the camera
passes the same checks as one from the card and lands in a block made in this session (P cleared by `cb_zero`; L, P2 and
P3 initialised by the code that allocates them), and P is still private while it is filled [V the loader's order,
GRAIN_HANG "Clean restart"].

Per file F of the four, decided once per power-on:

| Card at the first gated half-press | Block valid | F comes from | Block written |
|---|---|---|---|
| Nothing mounted | yes | the block; **no file call at all** | no |
| Nothing mounted | no | nothing loads; the loader stays armed, as today | no |
| F valid, identity **not** in the ring | either | **the card** (a set the camera never had) | yes: F and its identity |
| F valid, identity in the ring | yes | **the camera** (its copy may hold newer on-camera changes) | no |
| F missing or invalid | yes | the camera | no |
| F missing or invalid | no | stock for F, as today | no |
| `EP7MOD/FORGET.BIN` present | either | the card, as v0.32 does | zeroed (§3.6) |

- A valid block means: magic, version, length, CRC, and then each file image passes its own loader check. A block that fails
  is treated as empty and is never trusted in part.
- "Nothing mounted" needs the gate change the OM-3 made in v0.29.1. A card that mounts after that half-press has its new files
  taken at the next power-on.
- An old card can't put old looks back: its identities are in the ring. The ring holds 16; the 17th import forgets the first.
- An identical export isn't taken twice. To force it: `FORGET.BIN`, or any change in the Control Panel.

### 3.4 Writing: the only stores into the settings image

When: after an import (§3.3), and where today's code saves to the card (`ed_save` for BUNDLES, `mv_save`, the AP save), on a
half-press in HLS_EVENT. Never during capture, never at boot.

1. Build the 3,080-byte image in a transient heap block; compute its CRC there. No heap block: skip, try at the next half-press.
2. `cpu_lock`.
3. **Bank check:** the bank object at `(0xa2711a9c)` has RAM `0x624ea400` and size 0x40000, and the image's id word is 7.
4. **No save in flight:** RAM generation `(0x624ea404)` equals shadow generation `(0xa2a78004)`. `prm_bank_save` raises the
   RAM generation before the checksum, and the shadow follows only when the slot is read back, so the two differ for the whole
   window in which a store would break the checksum [V §2.5, §2.4].
5. **Reserve check:** the 4 KB at `C` is all zero or starts with our magic. Anything else: never write (something else uses it).
6. Copy the image to `C`, then to `U`, as stock writes its values (§2.5).
7. `cpu_unlock`, free. If check 4 failed: a pending flag, and another try at the next gated half-press. No waiting, no loop.

**State lives in P, nowhere else.** The layer needs three marks per power-on: a write is pending, `FORGET.BIN` was seen, and
(S1 only) the marker was written. They go in one free word of the real P (the one `ap_P` returns; P+860 is free in the
clean_boot table and in CODE_SPACE_MAP's heap rows [I: to be claimed and re-checked at build]).
- `cb_zero` clears that word on every load attempt, so a mark from an earlier session can't be found after a restart that
  kept DRAM. Zero must mean "nothing pending, nothing seen", and the layer writes the word only after `cb_zero` has run.
- No .bss pad and no byte outside the heap is used, so there is nothing of ours for stale DRAM to hold.
- "Is the block valid" is not kept at all: it is worked out again whenever it is needed (a 4-byte magic test first, then the
  CRC of 3 KB).
- P2 and P3 are byte copies of P and inherit the word. Only the real P's copy is read or written.
- A loader retry (`ap_boot`) makes a new P and drops the marks. That is safe: a retry happens only when no table was loaded,
  so nothing was pending.

- The lock covers about 1,540 word stores. All settings writes and the save run on CPU0 (§2.5), where the lock keeps the save
  from starting between check 4 and the last store [I: that HLS_EVENT is a CPU0 task; S0 logs the CPU id].
- A save that starts after step 7 sees a finished block. A save whose compare has already passed the tail misses this change
  and the next one takes it.
- **We call no settings function, no save and no flash routine.** The addresses are constants and the length is a constant.
  The build must prove that every store of the layer lands in the heap block, on the stack, in its own state bytes, or in
  `[C, C + 0x1000)` and `[U, U + 0x1000)` (§4).

### 3.5 When it reaches flash

At the next power-off or sleep, by the camera (§2.5). Until then the change is in RAM only.
- Battery pull or freeze before that: the change is lost, with the session's own setting changes. If it was an import, the
  card is imported again at the next power-on.
- **Crash-restart with DRAM kept** (GRAIN_HANG "Clean restart" [I: that DRAM survives]): the unsaved block in RAM is not
  what the next session reads. The start code clears .bss and the boot then copies the whole saved image over the bank
  (§2.2, §2.6), so the block is the last **saved** one, exactly as after a battery pull. A block half-written at the moment
  of a fault is discarded the same way; the NMI handler doesn't save (RE_CAPTURE §4), and a fatal-stop save runs as a task
  on CPU0, which the lock of §3.4 keeps out of the copy.
- Flash wear: no extra writes. The camera rewrites the bank at power-off whenever any setting changed.

### 3.6 Reset, restore, re-install, and getting back to stock

| Event | Block |
|---|---|
| Menu Reset (Basic / Full) | **Kept** (§2.6). The looks stay, as they stay on a card today |
| Camera refuses its newest saved copy at boot | The previous copy loads: settings and block as of the save before (§2.4). Both refused: defaults, block gone (§2.6); the next card import fills it again |
| Flashing another Caduceus version | Kept. Versions before this feature ignore it and read the card |
| **Restore file (stock 1.1)** | **Kept, inert.** Stock saves it along with its own settings and never reads it |
| Re-install later | Found again and used; a card with a set the camera never had still wins |
| `FORGET.BIN` on the card | The 4 KB reserve is zeroed in RAM (same guarded write), nothing is imported while the file is there, and the camera saves the zeros at power-off |

**Back to a fully stock camera:** put `EP7MOD/FORGET.BIN` on the card, half-press, switch off, then flash the restore file. The
tail is then zero, as before the first install [I: that it was zero before; S0 shows it]. Restored without that step: flash
Caduceus again, forget, restore. A menu item can replace the file later.

### 3.7 Failure modes

| Failure | Result |
|---|---|
| Block CRC wrong, torn, unknown version | Treated as empty: card files if present, else stock looks. Not overwritten until an import |
| A file image fails its loader check (for example written by a newer build) | The whole block is treated as empty |
| A save is in flight at our write | Write put off to the next half-press |
| Our write still lands inside a save (the guard fails) | That slot's sum is wrong; at the next boot the camera loads its previous slot: the last session's setting changes are lost, nothing else [V code]. If both slots were bad: every setting back to default, camera boots |
| Power lost during the camera's save | The same fallback. Stock behaviour, with or without this feature |
| Battery pull before power-off or sleep | Last change lost (§3.5) |
| Card with an older set | Ignored (identity in the ring) |
| No card, no block | Stock behaviour, loader stays armed |
| **A store outside the block** (a bug in our write) | The camera saves it with a valid checksum. The restore file doesn't undo it. A menu Reset repairs settings, if the camera still boots. This is the failure the staged plan exists to exclude |

### 3.8 Code and hooks

- A layer `patches/internal_storage` after the loaders and after clean_boot, about 1.0–1.3 KB [I], in the sec-5 dead
  `sdk api` space (CODE_SPACE_SURVEY §2). It claims its range in CODE_SPACE_MAP when it is built. RAM: one word of P (§3.4).
- Touch points, all in our own code [V source names]: the gate's "medium mounted" test and `sd_go` (crash_log's `cl_first`
  chains there, so this layer must chain too); `sd_load` / `fm_load` / the MOVIE and AP loads (source = card or block);
  `ed_save`, `mv_save` and the AP save (block write); the firmware-screen text.
- In `sd_load` the switch sits at the `call ep7_fopen` that follows `cb_zero`'s return (`0x605b74a9`), not in the first
  37 bytes, which clean_boot owns (`0x605b74a1`). With no card mounted the file calls are skipped, not left to fail.
- Frames: a routine that calls another keeps (0,sp) free (§1 problem 2; our rule already).

### 3.9 Decisions for the owner

1. **Card copies.** Recommended, as the OM-3 chose: once the block is valid the camera no longer writes `BUNDLES.BIN`,
   `MOVIE.BIN` or `AP.BIN` to the card. Fewer card writes and one clear rule, but the Control Panel can't read on-camera changes
   from the card. Keeping the copies needs a "written by the camera" mark in the file, which is a shared-format change.
2. **Forget:** a card file first (no UI), a menu item later.
3. **S0 and S1** as a development layer in the current build, or as a separate test build.

## 4. Staged plan

Risk level is for the camera's settings. Each step is one layer on the current build and one camera round.

| Step | What | Risk | Sessions |
|---|---|---|---:|
| **S0 read-only probe** | At the first half-press, write a 96-byte `EP7MOD/NVPROBE.BIN` through the camera-proven file helper (`ed_wfile`, as GRAIND.BIN): CPU id, MODE id, RAM and shadow generation, slot byte `0x61b213a1`, load-failed flag, count of non-zero bytes in 0x255b0..0x3fffc, 32 bytes at `C`, at `U` and **at the same offset in the shadow** (`0xa2ab2000`, what the boot read from flash). **Reads only** | None to the settings | 1, with S1 |
| **S1 marker** | The guarded write of §3.4 with a **16-byte marker** (`EP7R`, counter, version, CRC-32) instead of the block, and the `FORGET.BIN` rule to clear it. Written once per power-on, only when `BUNDLES.BIN` loaded, so taking `EP7MOD` off the card stops it. S0's file reports what the next power-on finds | **First real risk** | (same build) |
| **S2 read and import** | The block of §3.1: import from the card, sources per §3.3, the no-card gate | Medium | 1–2 |
| **S3 on-camera changes** | Block write at the save points, the ring rule, `FORGET.BIN`, card copies per decision 1 | Medium | 1 |
| **S4 release** | Control Panel wording (Install, Export), guides, CHANGELOG, a beta | Low | 0.5 |

**Total: 4 to 5 agent sessions, 4 short camera rounds.**

**Making S1 as safe as it can be:**
- Before it, S0 must show: MODE id 7, the two generations equal, HLS_EVENT on CPU 0, the tail all zero, `C` and `U` reading the
  same. Any surprise stops the work.
- The verifier runs the layer in the emulator together with the **stock** routines (`emu_mode_tail.py` shows the method):
  marker write, stock save up to the flash call (sum 0), stock load, marker read back. It traces every store of the layer and
  fails on any address outside the allowed set. Cases: save in flight (generations differ), non-zero reserve, wrong bank
  object, no heap.
- The package passes the usual anti-brick check. The layer changes no stock byte outside its hook in our own loader.
- **A marker kept only by DRAM must not pass.** The proof is the copy in the shadow, which the boot fills from flash, and the
  battery-out round. The "written" mark is in P (§3.4), so it is gone at every start; after a loader retry the marker may
  be written twice in one power-on (counter + 2), which is harmless.
- The owner notes the important settings first, and keeps the previous build's package and the restore file at hand.
- **S1 camera round (about 30 min):** (1) half-press, switch off, on, half-press: marker found, counter 1; (2) battery out for
  30 s after a clean power-off: still there; (3) let the camera sleep and wake: counter rises, settings unchanged; (4) Reset
  Basic, then Full: marker **expected to stay**, the camera's own settings reset as usual; (5) restore file, then this build
  again: marker expected to stay; (6) `FORGET.BIN` on the card, half-press, power cycle: tail zero again. If the camera
  restarts by itself during the round, leave the battery in and half-press: the file must show the last **saved** counter.
- **Stop rules:** the camera's settings reset by themselves once: stop and read the probe file. Marker gone after a clean
  power-off: the save doesn't cover the tail on the camera; the design is dead. Marker gone after a Reset: fine, and §3.6
  gets simpler.

**What S2 and S3 test on the camera:** first import from today's card; a card without `EP7MOD`; no card; a blank card; a new
export (taken once); the old card (ignored); an on-camera Film pick kept over power-off and battery pull; `FORGET.BIN`; back
to v0.32b and forward again.

## 5. Risks, ranked

| # | Risk | Level | Why | Mitigation |
|---:|---|---|---|---|
| 1 | A store of ours lands in the settings records | **High impact**, low likelihood | Saved with a valid checksum, in both slots after two saves. The restore file doesn't undo it. A bad value could, at worst, stop stock from booting, and then there is no way in [I] | Constant addresses and length, bank check, every store traced in the verifier, marker step first, one layer per step |
| 2 | Our write overlaps the camera's save | Medium | Wrong sum in the new slot → the camera falls back to the previous slot [V]; a full settings reset only if both are bad | Generation check under `cpu_lock`, both aliases written, no waiting |
| 3 | Not camera-proven | Medium | Tail unused at run time, tail zero, power-off and sleep saves covering it, the CPU of HLS_EVENT: all from code | S0, then S1, before any real data |
| 4 | Residue after a restore to stock | Low (expectation, not safety) | The block survives Reset and restore | `FORGET.BIN`, and say so in the guide |
| 5 | Last change lost on a battery pull | Low | Saves happen only at power-off and sleep | Same as the camera's own settings; documented |
| 6 | Heap pressure at the half-press | Low | One transient class-2 block for the staging image | Skip and retry; no block is kept |
| 7 | Stale state after a restart that kept DRAM | Low | The reason for clean_boot: marks in P were trusted as found | All of the layer's state is one word of P, written after `cb_zero`; the bank is reloaded from flash by the boot (§3.4, §3.5) |
| 8 | Debug shell `size` / `clear` | None in use | They rebuild defaults; no user path | – |

## 6. Credit and NOTICE

- The idea, the research behind it and the design it follows are **iancw's** (caduceus-om3 issue #35, PR #36); **androidfanman**
  built and camera-tested it in Caduceus for OM-3 v0.29 (Apache-2.0). This document's E-P7 findings are our own.
- **If only the method is used** (our own code), add to `NOTICE`, in the style of the grain line:
  "Keeping looks in the camera's settings memory (a block in the unused tail of the settings image, saved by the camera's own
  save) follows Caduceus for OM-3 (androidfanman/caduceus-om3, Apache-2.0, v0.29; research and design by iancw, its issue #35
  and PR #36). The E-P7 code in patches/internal_storage is our own."
- **If code is adapted** (for example their `ub_*` routines in `firmware/src/editor.s`): Apache-2.0 §4 applies. The `NOTICE`
  line must name the file and its source ("patches/internal_storage/`<file>` is adapted from firmware/src/editor.s (`ub_chk`,
  `ub_put`, `ub_try`) of Caduceus for OM-3 @ `<commit>`, Copyright 2026 androidfanman, Apache-2.0; design by iancw"). The
  adapted file carries a header saying where it came from and that it was changed, and their copyright line is kept.
- The sister project should hear two things from this round: a menu Reset probably doesn't clear its block either (same store
  family) [I], and the generation compare works as a save-in-flight test without a busy byte.

## 7. Open

- Everything §2.8 item 5 and §5 risk 3 name: answered by S0 and S1.
- Which task runs the power-off save, and whether a half-press can still be delivered while it runs. The guard doesn't depend
  on the answer.
- Whether a card that is present but not yet mounted can be told from "no card" at the first half-press. Until then: the
  OM-3's rule (§3.3).
- Loading at switch-on is **not** part of this. With the block in RAM it needs no card, but boot-time work has failed on both
  bodies ([AUTOLOAD.md](AUTOLOAD.md) stays shelved).
