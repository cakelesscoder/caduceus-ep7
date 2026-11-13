# Code-space survey (E-P7 1.1 main): dead stock regions and plugin migration

Analysis only, 2026-11-12: no build, no patch, no camera. Base: stock main (`5dd9af16…`) and the v0.32 edit list
(`generated/v032/edits.json`). Proposals for [CODE_SPACE_MAP.md](CODE_SPACE_MAP.md); nothing here is claimed until
it is merged there. Tags as in FIRMWARE_GUIDE: **[V]** read from the bytes or code, **[I]** inferred.

**Why.** After v0.32 the image had only the 64 B hole 0x601de740–0x601de780 and the 96 B sec-1 FF hole
0x60210e90–0x60210ef0 left (the auto-load work that was going to take them is shelved, so both are **still free**).
Wanted: about 40 B for the plugin key hook (PLUGINS.md §7), more hook stubs, and about 0.5 KB for the Extras v2
table (EXTRAS_MENU_V2.md).

## Method

Scripts in the session scratchpad (not committed); the checks are the same as the build scripts' (FIRMWARE_GUIDE §2):

1. **Literal references** to a candidate range on four aliases: cached `0x6…`, uncached `0xa…`, flash
   `0x40…` (= CPU − 0x60020020 + 0x406a0020) and uncached flash `0x80…`, at every byte offset.
2. Each hit is classified:
   - **code-imm**: the containing function (decompiled corpus index, `~/ep7fw-private/decomp/full/index.tsv`) is
     disassembled with objdump from its entry, and the hit counts only if an instruction starts 1–3 bytes before it
     and its operand text is that exact value;
   - **data word**: 4-byte-aligned, outside every indexed function; the neighbouring words are printed so pointer
     tables stand out from instruction bytes;
   - **rel**: `jmp`/`call` d16/d32 (`cc`/`cd`/`dc`/`dd`) and `calls` d16/d32 (`fa ff`/`fc ff`) decoded at every
     byte offset, kept only when the source is a true instruction boundary inside a function (otherwise listed as
     "nofunc" and triaged by hand).
3. Function-pointer tables are found by walking the pointer runs around every data-word hit.
4. Overlap with v0.32 edits is checked against `generated/v032/edits.json`.

Static absence of references doesn't exclude computed or DMA access [I]; where the bytes are stock code, the
proposal also removes the last pointer into the region (a stock data edit) so that it is dead by construction.

## 1. Result

| Rank | Range (end exclusive) | Size | Sec | Bytes | What | Proof (summary) | Confidence |
|---:|---|---:|---|---|---|---|---|
| 1 | **0x607b6420–0x607e87c5** | **205,733 B** | 5 | stock code | `sdk api` debug-shell handlers (1,138 commands A01…!03) | §2.1: only entries are the api table and two `sdk` sub-command words; no code, rel or literal reference from outside; dead by construction after 3 data-word edits | **high** |
| 2 | 0x60aa2b30–0x60aa6088 | 13,656 B | 5 | stock data | the 1,138 × 12 B api table `{code*, name*, fn}` | §2.2: read only by the api dispatcher 0x607b4b25, itself reached only from sub-command word 0x60a9a918 | **high** (with rank 1's edits) |
| 3 | 0x607b4b25–0x607b4cba | 405 B | 5 | stock code | `sdk api` dispatcher | as rank 2 | **high** (with rank 1's edits) |
| 4 | 0x601de740–0x601de780, 0x60210e90–0x60210ef0 | 64 + 96 B | 1 | dead EVF / FF | the two holes left after v0.32 (auto-load shelved, so still free) | CODE_SPACE_MAP v0.32 table | **high** (already build-checked) |
| 5 | 0x60747fe2–0x60748000 | 30 B | 4 | FF | sec-4 tail after split tone `.ste` | CODE_SPACE_MAP | high |
| 6 | 0x60ac7c98–0x60ac9f10 | ≈ 8.8 KB | 5 | stock data | switch jump tables of the rank-1 handlers | every word points into rank 1; readers not yet enumerated | medium |
| 7 | 0x60a9db19–0x60aa2b30 | ≈ 20.5 KB | 5 | stock strings | api command codes and names | pointed to by rank 2; string sharing (tail merging) with live code not ruled out | medium |
| 8 | **0x60211000–0x60230800** (load extension) | up to 128 KB | 1 (new) | FF in flash, not loaded today | grow section 1's load past its end | §3: only reference is the sec-1 end stub; needs one boot-path edit and a camera probe | medium (risk HIGH: boot path) |
| 9 | 0x61379000–0x613bd000 (load extension) | up to 272 KB | 7 (new) | FF, not loaded | grow section 7's load | §3, as rank 8 | medium (risk HIGH) |
| 10 | 0x60177180–0x601777ab, 0x601777e9–0x60177d2c | ≈ 2.9 KB | 1 | stock code | built-in EVF (BI_EVF) panel driver: open / close / serial / brightness | §4: reached only through display-device bit 2 (EVF); the gate is a runtime request, not a model constant | medium-low |
| 11 | 0x6080f000–0x60813e60 (approx.) | ≈ 20 KB | 5 | stock code | ANTISHAKE / APERTURE / CCD `LIFETEST` state machines | §5: entry 0x607f165b from 0x60e4f6e0; gate not traced | low (not needed) |

**High-confidence total: 219,984 B ≈ 215 KiB** (ranks 1–5: 205,733 + 13,656 + 405 + 160 + 30 B), of which
219,794 B is in section 5. That is about 25 times the whole FF-tail budget of the image (8.8 KB) and far more than the asks
(≈ 40 B key hook, ≈ 0.5 KB Extras v2 table, hook stubs).

Not found / not useful:
- **Other bodies' code or table rows.** The image names only the E-P7 (`E-P7` ×3; no E-M10, E-PL, PEN-F, OM-
  strings), and the updater accepts only model 0x1420. Shared-platform code exists (EVF, external VF, accessory
  port) but it is gated at run time by device state, not by a model id (rank 10).
- **Language or help text in main.** Menu strings, help text and fonts are in the OSD component (kind 0x101,
  FIRMWARE_GUIDE §5); main holds only debug/trace strings.
- **Section 9** ("debug dumps", 0x613c1000–0x6143a800, 486 KB): 518 indexed functions, 149 of them called from
  outside section 9, so it is not a closed debug island. It loads last, which makes it the worst place for hooks
  anyway. Not pursued.

## 2. The `sdk api` debug shell (ranks 1–3, 6, 7)

### 2.1 How it is reached [V]

The firmware has a serial debug shell (tasks S_SHELL / U_SHELL; its own help text names the `siodbg` port and
SD-pin ports, "`<arm shell siodbg>`", "`<am shell sd3>`", 0x6005aa25 / 0x600571d4). The chain down to the handlers:

1. Top-level shell command table (sec 1, two copies, `{name*, fn}`): 0x601e5450 `"sdk"` → 0x607687f7, and the same
   at 0x601e6874. 0x607687f7 is `add -4,sp` + 0x607687fa `call 0x607add83`.
2. `sdk` dispatcher 0x607add83 (OlyHfwShellCommand.cpp) walks the 37-entry sub-command table
   **0x60a9a880–0x60a9a9a8** `{name*, fn}` (read at 0x607add88, 0x607af6e4) and enters the match with `calls (a1)`.
   Three entries lead into rank 1/3:
   - 0x60a9a914/918 `"api"` → **0x607b4b25** (the api dispatcher, rank 3);
   - 0x60a9a91c/920 `"starttimer"` → 0x607dab9f, 0x60a9a924/928 `"stoptimer"` → 0x607dac2e (both inside rank 1).
3. The api dispatcher prints `usage: sdk api XXX` / `sdk api [A-z][0-9]`, then loops `cmp 1138,d2` over the table
   **0x60aa2b30** (`mov 0x60aa2b30,a2` at 0x607b4bb7 and 0x607b4bfe, third use at 0x607b4c8a) and calls the
   handler whose 3-character code matches.
4. The 1,138 handlers start at 0x607b6420 (A01 `initializeApi`) and end with !03 `notifyIctlogMoveCursorMenu`
   0x607e8778, whose `ret [d2,a2],20` ends at 0x607e87c4. The next byte, 0x607e87c5, is a live function (callers
   0x60cfd0d7, 0x60dd9c87). The function before (0x607b639c, 132 B) ends at 0x607b6420.

Other entry into the `sdk` dispatcher: only `dbgall` (0x6018e3b2, itself a shell command, table word 0x601e540c),
which runs the canned lines `sdk log off` / `sdk sleep_off` from .data; neither reaches `api`, `starttimer` or
`stoptimer`. The `sdk macro` event recorder ("MACRO000DAT", 0x607b479a…) is also entered only from the sub-command
table.

### 2.2 No other reference into rank 1 [V]

Full scan of 0x607b6420–0x607e87c5 on all four aliases (method above):

| Class | Hits | Verdict |
|---|---:|---|
| code-imm (true `mov imm32` with that value) | 21 | all `mov 0x40e4ab40,a1/d1` in 0x60bed…–0x60c3a… (the flash alias of 0x607cab40). They are the high word of a double constant passed in a0:a1 / d0:d1 with low word 0 (`mov 0,a0` just before, 0x60bed99d); not an address |
| rel / calls at a true instruction boundary, source outside the range | 0 | – (51 `rel` hits are all inside 0x607d7b14, a switch inside rank 1) |
| rel / calls outside any indexed function, source outside | 5 | mid-instruction or data: 0x601c9014 and 0x601e583c are pointer tables (`… 60 dc 6d 1c 60 …`); 0x607e8a90 / 0x607e8af5 / 0x607e93bc are inside `call d32` instructions after rank 1 |
| aligned data words outside functions | 2,899 | 1,124 = the api table; 1,630 = switch tables 0x60ac7c98–0x60ac9f10 (rank 6, used by rank-1 code); 2 = the starttimer / stoptimer words; the rest are instruction-byte patterns (`a0 xx c8 yy` compare/branch runs, `…dd/fc…` opcodes) with no pointer neighbours |

The Ghidra project defines only 5 functions inside rank 1 (0x607b6420, 0x607c4cf4, 0x607d7b14, 0x607d943c,
0x607dd584), all with 0 callers: the handlers were never reached by any analysed call. v0.32 edits nothing in
0x607b4b25–0x607e87c5, 0x60aa2b30–0x60aa6088 or 0x60ac7c98–0x60ac9f10 (its sec-5 data edits are 0x60acb0e4 and
0x60acb174).

The api table (rank 2): the only code that names it is the dispatcher (three `mov 0x60aa2b30`). The only other
aligned word that lands in it (0x6060a788 = 0x60aa4bcc) sits in code bytes (`… 72 cc fc 12 f8 …`). The dispatcher
(rank 3) is referenced only by sub-command word 0x60a9a918.

### 2.3 Making it dead by construction

Today the handlers are reachable, but **only by typing `sdk api …` on the serial debug console**, which a retail
camera never does. Before reusing the bytes, cut that path too, so no input on any port can enter overwritten
code:

| Site | Stock | New | Why |
|---|---|---|---|
| 0x60a9a918 (4, data) | 0x607b4b25 | `ret0` | `sdk api` |
| 0x60a9a920 (4, data) | 0x607dab9f | `ret0` | `sdk starttimer` |
| 0x60a9a928 (4, data) | 0x607dac2e | `ret0` | `sdk stoptimer` |

`ret0` = a 3-byte `clr d0; rets` at the start of the new claim (the sub-command handlers are entered with
`calls (a1)` at 0x607adda1 / 0x607addfa, so `rets` returns correctly; emulator-check it once). After these edits
nothing in the image points into 0x607b4b25–0x607b4cba, 0x607b6420–0x607e87c5 or 0x60aa2b30–0x60aa6088 except
the regions' own internal references, which never execute.

Rules for reusing it:
- **Section 5 loads sixth** (1, 7, 2, 3, 4, 5, 6, 8, 9). Code here may be called from hooks in sections 5, 6, 8 and
  9, and from any hook that only runs after boot (UI, keys, capture, card loaders: everything Caduceus has
  today). It must not be called from code that can run during the section-load phase before wait(5).
- The bytes are stock code, not FF: claim aligned sub-ranges, keep the 16-byte guard habit, and leave the rest
  stock. Every build re-runs the reference scan over its claim (the existing build-check pattern) and checks the
  three table words above.
- The CA key handler for the plugin key hook (0x60ce011a, sec 6) and the GUI screens that read the Extras table
  (sec 6) are both later-loaded than sec 5, so those asks fit here directly.

## 3. Growing a section's load (ranks 8, 9)

Between the sections, the decoded image holds about 1.3 MB of FF that is **in flash but never copied to RAM**
[V: section table vs. image]:

| Gap (end exclusive) | Size | Content |
|---|---:|---|
| 0x60211000–0x60230800 | 128 KB | FF (then the .data init image 0x60230800–0x6025eb50 and boot copy sources at 0x60270800 / 0x60278800 / 0x6027c800, all read from flash, keep clear) |
| 0x6055e800–0x6057b200 | 114.5 KB | FF |
| 0x605b7800–0x605baa00 | 12.5 KB | FF |
| 0x60748000–0x6075a800 | 74 KB | FF |
| 0x60b9e000–0x60ba7000 | 36 KB | FF |
| 0x61243000–0x612c7000 | 528 KB | FF |
| 0x61379000–0x613c1000 | 272 KB | FF (sec 8 is empty at 0x613bd000) |
| 0x6143a800– | 5 MB | FF except **a boot staging buffer** at 0x6143ca00–0x6143e200: `data_copy` 0x60020272 reads 6 KB from flash 0x41abca00 into RAM 0xa143ca00, then copies it to 0x47000800. Avoid this tail |

**Idea.** The loader 0x600457e7 copies `end − start` bytes from flash to RAM, where `end` comes from a
`mov imm32,d0` stub (table 0x60046780). Raising one immediate makes the section's load longer; the new bytes come
from the same component at the same offsets, which the updater already writes in full.

**What was checked [V]:**
- References into each gap, four aliases, filtered as in the method: the **only true code reference** in every gap
  is the section's own end stub (sec 1: `mov 0x60211000,d0` at 0x6004579c; sec 7: `mov 0x61379000,d0` at
  0x600457c4). The other code-imm hits are flash-alias values used as float/double constants (0x41a00000 = 20.0f,
  0x40be2a00, 0x40c38800, 0x4190c083); data-word hits are instruction-byte patterns; the two rel hits into
  0x60b9e000.. come from data at 0x60b99a22 already pinned as false positives (CODE_SPACE_MAP split tone `.stb`).
- Users of the end value: `section_end_get` 0x60045786 has three callers. `section_load` uses it for the size. The
  bus monitor setup 0x6004595c and `section_init_run` 0x6004586c use only `end(9)` and `start(n+1)`, so growing
  sections 1–8 doesn't change the monitored window. No checksum of the loaded RAM was found.
- v0.32 has no edit in any gap or in the end stubs.

**What isn't known [I]:**
- Whether pre-main boot code, another core or a DMA engine uses this RAM by computed address. The boot staging
  buffer after section 9 shows that stock does use image-span RAM outside the sections (by pointer, so the earlier
  "0 absolute stores" sweep can't see it). Nothing points at the sec-1 or sec-7 gaps, but that is not proof.
- Whether the flash read 0x6005bc79 has a size or alignment limit. All stock section sizes are multiples of 0x200
  and every end is 0x800-aligned: keep any new end 0x800-aligned.

**Probe before use (one feature per flash, boot path, risk HIGH):** raise sec 7's end by 0x800 to 0x61379800 and fill
it with a known pattern; a Firmware-screen readout (the fw_version / plugin text hook) shows a CRC of it. Check after
boot, after shooting, movie, playback, Wi-Fi and a long session. Only after that, place code there. Sec 1's gap is
the more valuable one (it loads first, so any hook may call into it), but sec 7's tail already ends at the section
end in v0.32, so its extension is contiguous with split tone's claim.

This is the only route to more space in **section 1** without overwriting stock code. It is not needed for the
current asks (§2 covers them), so treat it as a reserve.

## 4. EVF-only code (rank 10)

The E-P7 has no EVF and no accessory port, and the dead EVF gamma tables already rest on that [I strong, camera
since test 11]. The built-in-EVF panel driver in section 1 is the largest further piece found:

| Function | Size | Strings | Callers |
|---|---:|---|---|
| 0x60177180 | 397 | `display_open_bievf_1st` | 0x6017715a, 0x60177c34 |
| 0x6017730d | 277 | `display_open_bievf_2nd` | 0x6017715a, 0x60177c34 |
| 0x60177422 | 58 | `display_bievf_wrap_tx_data` | 0x60176621 (DisplaySerialControl) |
| 0x60177490, 0x601774d4 | 68, 59 | `bievf_vsc_sio_close` | driver-internal |
| 0x6017750f, 0x6017757b | 108, 90 | `display_close_bievf` | 0x601761c7, 0x60177d18 |
| 0x601775d5, 0x6017773e | 361, 109 | `send_backlight_ctrl` | 0x601744df (DISPLAY task), 0x60176859, 0x60187898 |
| 0x601777e9, 0x6017787b | 146, 314 | `vsc_sio_open`, `send_data` | driver-internal |
| 0x601779b5, 0x60177af2 | 317, 245 | brightness auto / manual | 0x60176a9b, 0x601775d5 |
| 0x60177c34, 0x60177d18 | 228, 276 | EVF switch-in / switch-out | 0x60175684 (`display_open`) |

Keep 0x601777ab–0x601777e9 (small shared helpers with outside callers, e.g. 0x60042b47, 0x60c79a4b).

**Gate [V code, meaning I]:** `display_open` 0x60175684 works on device-group bits, 1 = TFT, 2 = EVF. It calls the
EVF switch-in 0x60177c34 only when the running group has TFT and the request has EVF, and the switch-out 0x60177d18
only in the reverse case. The request comes from the app layer (and from prop 0xc321 via 0x6017592d, where value 6
maps to EVF). That is a **runtime** gate, not a model id: proving it never fires needs the request sources traced
(CA `CHG_OUT_LINE : EVF`, eye-sensor task PER_EYE_SENSOR). Overwriting code is less forgiving than overwriting the
gamma tables (a wrong table gives wrong colours on a panel that doesn't exist; a wrong function crashes), so this
needs either that trace or a probe (a counter at each entry shown on the Firmware screen) first. ≈ 2.9 KB in
section 1; worth it only if section-1 space is needed again and §3 fails its probe.

The EVF GUI windows (`GCWnd_EVF_OM::UpdateBattery` 0x60dd1734, `UpdatePBH` 0x60dd1885, 793 B, sec 6) and the
EVF touch-pad paths in CA (0x60cd2906 and friends) are also EVF-only by name, but they sit inside large live
classes; not pursued.

## 5. Life tests (rank 11)

32 functions with `ANTISHAKE_LIFETEST`, `APERTURE_LIFETEST`, `CCD_LIFETEST` strings, 6,371 B of them indexed,
in a state-machine cluster around 0x6080f000–0x60813e60 (sec 5), plus 0x607f165b (entered from 0x60e4f6e0, sec 6).
The entry gate (a service menu or key combination [I]) was not traced, and `settings_save` 0x602cc6dd lists life
tests among its callers, so this code touches flash-saving paths. Not needed given §2; left at low confidence.

## 6. Moving resident features into PLUGIN.BIN

### 6.1 What would move

v0.32 writes about 37 KB of resident bytes in edits of 32 B or more (sum over `generated/v032/edits.json`, main
component), plus 374 small hook edits. lcd_tint's 5.8 KB is stock table data, not code space. Features that only
do something once BUNDLES/LOOKS/MOVIE/AP have loaded, i.e. on or after the first half-press:

| Feature (patch) | Resident B | Hook edits | Runs before the first half-press today? |
|---|---:|---:|---|
| AP Custom (ap_custom) | 3,203 | 17 | no: AP.BIN loads on half-press; ap_init / screen hooks fall through to stock without P3 |
| Movie slot + colour (v026_movie) | 3,158 | 8 | no: MOVIE.BIN on half-press |
| Grain (grain_cpu r2) + grain_kind + recview | 3,295 | 2 | no: needs a slot +50 |
| Look editor (ed_core / ed_view / ed_ui / ed_keys) | 2,226 | 5 | the wheel pages show stock until P exists |
| Halation (`.text`, `.hlb`, `.hlc`, `.hlp`, h2) | 1,740 | 0 (chained in grain) | no |
| Film menu v2 (fm_core / fm_ui) | 1,650 | 8 | no: needs LOOKS.BIN |
| Mono presets | 1,448 | 11 | no |
| Look extras | 1,308 | 4 | no |
| Split tone | 783 | 0 (chained) + 1 | gate runs every LV frame, exits to stock without slot data |
| Tone ends / look tone / tone_x (v019, tone_ends) | 1,072 | 1 | no |
| v025 (Shading / NR getters, Extras 8), sharp_off | 746 | 8 | getters fall through to stock without a slot |
| exif_name | 301 | 1 | writes "Caduceus" only with a loaded slot |
| **Total** | **≈ 20.9 KB** | **≈ 66** | |

Must stay resident: the four card loaders and the plugin loader (they run before the plugin exists), the bundle
table and HSL/WB converter hooks (cheap, and the base look must not depend on the plugin), and the global features
that work without a card: Lowest S/S, Live ND, aspect / aspect_fix / lv_grid, LCD tint, arrow keys, fw_version.

### 6.2 What it would free

- Each moved hook needs a resident stub: test `P+852 == 'EP7K'`, load a hook word from B, `calls` it, else replay
  the overwritten instructions and continue stock. About 12–20 B per site plus one shared 30–40 B gate, so
  ≈ 66 × 16 + 40 ≈ **1.1 KB of stubs**.
- The plugin block is one class-2 malloc, **at most 16,384 B including the 32-B header** (PLUGINS.md §1). 20.9 KB
  doesn't fit; the largest set that does (everything but AP Custom and one of Movie / grain) is about 14–15 KB.
- **Net: about 13–14 KB of resident space**, spread over the dead-EVF tables, sec 3, sec 7 and sec 9 claims (it
  doesn't come back as one block, and most of it is in sec 1, the only place that matters for early hooks).

§2 alone gives about 15 times that, contiguous, with no change to camera-proven code.

### 6.3 Risks

1. **Rewrite of camera-proven code.** Plugins must be position-independent (PLUGINS.md §4); our `.s.in` sources use
   absolute addresses for their own tables, strings and cross-feature jumps throughout. Every moved feature is a
   port plus a full re-verification, and a regression in features users already rely on.
2. **Hook chains.** Many hooks are chained across features (ap_* in front of mv_* / sh_* / hl_*; halation inside
   grain; split tone in front of tone). A chain has to move whole or keep resident trampolines in both directions.
3. **Silent degradation.** Missing file, CRC mismatch, card swapped, or a declined init: the base look (HSL, WB,
   saturation, resident) still applies but grain, halation, split tone, tone ends and the Extras are gone, and the
   user may not notice. Needs a visible "plugin missing" mark (for example in the film label), not just the
   Firmware screen.
4. **Version coupling.** The plugin header carries the *stock* firmware id, so a plugin built for one Caduceus build
   would load on another and jump to wrong addresses. Moving core features needs a Caduceus build id in the header
   (for example in the reserved bytes 20..27) and a loader that rejects a mismatch.
5. **Crash domain.** A plugin bug crashes after the first half-press and never bootloops (the plugin loads only
   on half-press). This is the one safety gain, and it applies only to new code.
6. **CPU passes.** Grain and halation run in REC_IMAGE on the job's buffers. They'd run unchanged from B (cached
   alias, never freed), but a capture-time crash would then come from a file on the card rather than the flashed
   image, which makes bug reports harder to reproduce.

### 6.4 Half-press-only loading, per feature

The plugin loads in the same half-press handler, right after AP.BIN. For every feature in 6.1 that is **no change**
today, since none of them does anything before the card files have loaded either. Two cases change:
- **If auto-load comes back** (AUTOLOAD.md: looks at power-on, plugin still on half-press), moved features would be
  missing between boot and the first half-press while the looks are already active: a shot taken in that window would
  get the look's HSL/WB but not its grain, halation, split tone or tone ends. Either load the plugin in the
  auto-load too or keep look-rendering features resident.
- The **COLOR / Movie / AP editors** opened before the first half-press show stock pages today; unchanged.

### 6.5 Verdict

**Don't migrate resident features for space.** The sdk-shell region gives about 200 KB of contiguous space with a
3-word edit and no change to working code; migration gives about 13–14 KB, fragmented, at the cost of rewriting and
re-testing most of the look pipeline and making output depend on a card file.

Use plugins for what they are good at: **new and experimental features** (Extras v2 pages, the shortcut-button
cycle, film-page takeovers), tried without a flash, then made resident in sdk-shell space once camera-proven.

## 7. Recommended plan

1. **Register one claim in CODE_SPACE_MAP** (coordinator): sec 5 **0x607b6420–0x607b8420 (8 KB)** for resident
   stubs, the plugin key hook and the Extras v2 table, with 16-B guards kept stock at both ends, plus the three
   data-word edits of §2.3 (`ret0` at 0x607b6430). Leave the rest of 0x607b6420–0x607e87c5 and the api table
   0x60aa2b30–0x60aa6088 listed as *reserve*, so later claims take aligned slices.
2. **Build-check**: add the claim to the reference scan used by the build scripts (all four aliases + PC-relative),
   pin the double-constant false positive 0x40e4ab40 (21 sites, 0x60bed99f…0x60c3a9c2), and assert the three
   sub-command words point at `ret0`.
3. **First consumer: the plugin key hook** (PLUGINS.md §7, ≈ 40 B): site in CA (sec 6), stub in the claim. Then
   the Extras v2 table (≈ 0.5 KB, read by sec-6 screens). Both run only after boot, so section 5 is legal. Minimal
   tests + anti-brick (testing scope): emulator run of the stub with and without `EP7K`, `sdk` dispatcher entry with
   `api` → `ret0`, package P-check.
4. **Keep the sec-1 holes** (64 B 0x601de740, 96 B 0x60210e90) for anything that must run before section 5 loads.
5. **Reserve §3 (load extension)** for when section-1 space runs out again; its first step is the sec-7 pattern
   probe (risk HIGH, one feature per flash).
6. **No bulk plugin migration** (§6.5). New features go plugin-first, then resident in the sdk-shell space.

Open items: enumerate the readers of the rank-6 switch tables and the sharing of the rank-7 strings before claiming
them; trace the EVF request sources (rank 10) only if section-1 space is needed and §3 fails.
