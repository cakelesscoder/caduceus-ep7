# AP Custom: Vivid on the AP dial position as its own colour slot (E-P7 1.1)

Built 2026-11-09 as `patches/ap_custom` (0.30a1), a layer over v0.29a. Emulator-verified, **not camera-tested**.
Addresses are main CPU addresses. **[V]** = read from bytes or code, or run in the emulator. **[I]** = inference.

Request: on the mode dial's AP position, Vivid works as an "INFO Custom" slot, the way movie Vivid does since v0.26
([MOVIE_COLOUR.md](MOVIE_COLOUR.md)). Then Multiple Exposure, Live Composite and the other AP modes can shoot a custom look.

## Key questions

**1. AP forces the normal picture-mode list.** In the 15272 switch `0x602b6b4f`, sid 24 ∈ {14, 209..216} forces 1645 (after the
sid 44 movie test and the sid 109 / 278 tests) [V]. Those are exactly the AP values in the AP lists (`0x611644e8..`): 209 Live
Composite, 210 Live Time, 211 Multiple Exposure, 212 HDR, 213 Silent, 14 Panorama, 214 Keystone Compensation, 215 AE Bracketing,
216 Focus Bracketing [V]. Sid 24 (key `0xc011`) shares one value list with SCN (3..220; 204 Light Trails, 205 Backlight HDR, ...)
[V]. It must follow the dial, or the lever would break in P after an AP session [I strong]. So in AP the profile lever is
ignored, 15272 = 1645, and Vivid is pipeline mode 1 (GUI 111 = 0), as in movie.
**AP gate here:** sid 44 ≠ 1 and sid 24 ∈ {14, 209..216}, read through the raw getter `0x6005e971`.

**2. Stills sites that decide the slot.**
- The capture population reads pm (`0x9481`) at `0x602a8577`, the COLOR profile (`0xF6B1`) at `0x602a85b7` (only when pm == 11), and
  12 × S (`0xF6EA`) from `0x602a85cd`. Converters copy them into the job (key 11, ext +15488 profile) [V, PROFILE_INDEX_WB].
- Every slot reader ends in the v3 accessor: `tbl_idx` (hl, tone, grain, bloom/clarity, sc/nr/sh via `sc_slot`) or `tbl_off` (wb_get,
  offset slot·64) [V]. Both finish at `tbl_x` `0x6055e7e7`.
- Extra settings readers take pm/profile themselves: `sc_slot` → `sc_prop` (`0x601e3a5c`), `wb_get` → `wb_prop` (`0x6055e79b`) [V].

**3. The movie INFO route extends.** `mv_lc` (`0x60e5951c`) is gated on sid 44 == 1 only; the handler, row 111 and GUI value 0 are
the same in AP [V emulator, real handler]. The rest of the wheel (`mv_sw`, `mv_get/def/set`, polygon, exit, Film, Extras) works
on "whichever block is swapped in", so it serves a third block unchanged [V].

## As built

**Separate slot, not P2.** Code space was not the limit (2031 B; claim in [CODE_SPACE_MAP.md](CODE_SPACE_MAP.md) "ap_custom").

### Design: make an AP capture a COLOR4 capture, and give COLOR4's row to P3

In AP with Vivid, no stock COLOR job can exist (the lever is forced off). So a COLOR4 row read in that state can only be ours.

| Site | Change | Effect |
|---|---|---|
| `0x602a8577`, `0x602a85b7`, 12 S calls (rel32) | `ap_get` | AP + real pm 1: pm → 11, profile → 4, S → P3 +257+i. The real read still runs, so only d0 differs |
| `0x601e3a5c` sc_prop, `0x6055e79b` wb_prop (rel32) | `ap_get` | Shading, NR, Sharp and WB follow the AP slot |
| `0x6055e7e7` tbl_x (5 B) | `ap_tx` | Offset 192..255 (COLOR4's row) in AP + Vivid → P3 + 32 + offset |

Grain, H/L, tone, glow, clarity: all reach the AP slot through ext profile 4 → `tbl_idx(3)` → `ap_tx` [V tbl, I end to end].
Grain still needs job type 0x1000 (`gc_lvl`), so it applies to ordinary AP stills only; nothing extra was built for it.

### Live view (record path, chained in front of the movie hooks)

| Site | Was | Now | AP + record pm 1 |
|---|---|---|---|
| `0x60316bfb` | mv_key | `ap_key` | job key 11 |
| `0x60315900` | sh_msg | `ap_msg` | message +20 = 4 (S valid), skips sh_msg (live view sharpness stays stock) |
| `0x6030bd5d` | mv_s | `ap_s` | S from P3 |
| `0x601e0ee2`, `0x601e110a` | mv_tbl | `ap_tb` | mv_prof's mark → P3 row |

WB needs no hook: `mv_wb` misses outside movie and `wb_get` → `wb_prop` → `ap_get` → `tbl_off` → `ap_tx` [V emulator].
`mv_cons` is not movie-gated, so AP live view jobs also lose flag 0x80000 and lv_art, as in movie.

### Wheel, label, Color Creator trap

- `ap_lc` in front of `mv_lc`: row 111, value 0, sid 1337 ≠ 1, AP slot loaded, AP → state word = P3's handle, key `0x140c`, stock
  art-variation route. `mv_exit` restores P (P3 +968).
- **1645 := 21 trap:** in AP 15272 is 1645, so the three Color Creator sites would fire as in movie. `ap_ccg` replaces mv_get's
  call to `mv_ccg` (`0x601e202d`): AP + AP slot → 1646, else `mv_ccg`.
- Label: `ap_la` / `ap_lb2` in front of `mv_la` / `mv_lc2`; on AP they jump into `mv_lb`'s own text writer (`0x601e0fe1`), so the
  text is the same "INFO Custom". The Live Control strip's Vivid entry is a bitmap, so the label shows only in text lists (as movie).

### AP slot (P3) and AP.BIN

- **Card:** `EP7MOD/AP.BIN`, 96 B, **the MOVIE.BIN format** (`EP7V`, `tools/ep7_movie_bin.py`). A MOVIE.BIN copied as AP.BIN works.
- **Default file:** `generated/ap_custom/card/EP7MOD/AP.BIN` (`ep7_movie_bin.py --name AP`, a zero slot). **With no AP.BIN, AP is
  stock Vivid and INFO does nothing:** the camera does not create the file. Copy the default to start.
- **P3** = copy of P (after mv_load) with the slot at +224, name at +592, its own L3 (L3+2116 == P3) for the Film page,
  +960 `EP7V`, +964 P3, +968 P's handle, +972/976 ALL. P: +984 `EP7A`, +988 P3, +992 `EP7U` (tried). Every reader validates P3
  (pool range, alignment, `EP7B`, `EP7V`, +964 == itself), and `ap_P` finds P from P2 or P3 when one is swapped in.
- **Loader** `ap_load` = mv_load's checks: H/L +0..23 and WB +26/27 ±7, S +33..44 and B/W +47/48 ±5, +52..63 zero, name NUL.
  **+24 NR, +49 lens, +50 Grain, +51 Sharp are not range-checked here** (as current mv_load; their readers check), so every byte the
  UI saves loads [V emulator, a file with +24 6, +49 1, +50 3, +51 1].
- **Load point:** `ap_post` on mv_trig's tail jmp, first half-press only, after mv_trig's film and Movie slot loads. No new load point.
- **Save:** `ap_pre` on sd_back, before mv_trig: P3 dirty → AP.NEW verified, old → AP.BAK, AP.BIN verified. It clears the dirty
  byte first, so a half-press while the AP wheel is open can't make mv_trig write P3 as MOVIE.BIN. `mv_gsave` already refuses
  P3 as BUNDLES.BIN (P3 +964 == P3).
- Grain / NR / Sharp in the AP slot are the slot's own bytes, set on the Extras page. A look never sets them (Film picks copy as in movie).

### Checks (`patches/ap_custom/verify.py`, against v0.29a)

G capture reads 420, X tbl_idx/tbl_off 140, B WB end to end 42, K job key (real mapper) 84, V message/S/slot 420, L real Live
Control handler 48, C Color Creator guard 4, F AP.BIN load/save/triggers 12, N label builders 12: each is v0.29a byte for byte
without the card file, without AP or with another picture mode. D: image differs only at our sites. A: package parses, restore ==
stock, decoded == emulated. Package: `generated/ap_custom/pkg` (`caduceus.py verify` OK); restore == v0.29a's.

## Camera: 0.30b1 (composed with live_nd)

**INFO on Vivid in AP Live Control left the menu.** The user half-pressed first, and the strip showed "INFO Custom", so P3 is loaded
and `ap_mode` passes. Live ND edits nothing on the INFO path (handler `0x60e593be..`, the sid 111 record `0x61176ea0`, the
111 lists, the state functions, our code); its strip record `0x61176ee8` is sid 1429's [V spec diff].
"Leaves the menu" is the stock fallthrough: `0x60e59713` → `0x60e59742` → the sid 281 control-mode cycle. In stills and AP, 281
has several control modes, so INFO switches Live Control away. In movie it has one, which is why the first movie build "did
nothing" [V code, I for the 281 values per mode]. So the press either reached `ap_lc` and missed its gate, or never reached it.
Read from code, the only AP-specific gate left was sid 1337 == 1 (stock blocks art variations with it in movie only). State 7
failing to open is the other candidate [I]; the emulator can't tell these apart.

**0.30b2:** `ap_lc` no longer tests sid 1337. A probe records each INFO release that reaches `0x60e5951c` at P+996..999, and the
Vivid label in AP then reads `r<row> v<GUI value> f<flags> n<count> Custom`. Flags: 1 = sid 1337 was 1, 2 = swapped to P3.
- No `r…` text after pressing INFO: the press never reaches this handler.
- `r111 v0 f2`: the swap ran, so state 7 / group 18 didn't open from AP.
- Another row or value: that's the mismatch.
Remove the probe before release.

## Camera: 0.30b2 → 0.30b3 (the SCP)

**0.30b2:** in AP the user sets picture mode on the SCP, not Live Control. After INFO the label stayed "INFO Custom", so the press
never reached `0x60e5951c`. The SCP is another screen, which `ap_lc` doesn't see.

**0.30b3, the SCP route:** SCP and menu cells open editors through the screen lookups `0x60e4cea8` / `0x60e4cf21` (group 0x12,
key). This is the route v0.15 `mc` used on camera to turn MONO filter keys into COLOR wheels.
- `ap_scr` / `ap_scr2` sit on the lookup entries. In group 0x12, in AP with the slot loaded, they record the key.
- Key `0x6f` (group 18 keys are sids: 111 = the picture-mode list that the SCP cell opens; camera probe on 0.30b3 read `S18/0/111`) in AP, with pipeline mode 1 and GUI 111 == 0 (Vivid): swap to P3 with a pending mark, and the key becomes `0x140c`. 0.30b3 used `0x77` (sid 119, a slider), which never fired. Side effect: in AP on Vivid, the SCP cell opens the wheel instead of the list; change the mode with the dial on the cell, or in Live Control.
- The Live Control route stays and now also marks pending.

**Undoing the swap.** An SCP-opened wheel doesn't leave through state 7, so `mv_exit` doesn't run.
- `ap_init` runs in front of `po_init` on COLOR1–4's record +4. A swap without pending is undone there, so a stills editor never
  works on P3; pending is consumed by our own open.
- `ap_pre` undoes a P3 swap on a half-press off AP.
- `ap_tx` now always reads P's table, except COLOR4's row in AP + Vivid, so a swap left in place can't change stills or other slots.
- Left open: a lookup that never ends in an init keeps pending until the next COLOR editor open.

**Probe** (P3 +800..808, cleared at load). The Vivid label reads `L<row>/<value>/<flags>/<n> S<group>/<key hi>/<key lo>/<flags>/<n>`.
L is Live Control INFO, as in b2. S is the last group-0x12 lookup in AP, flags 1 = swapped.
- (b3/b4 history) `S18/0/119/1/n` with no wheel: the swap ran and the wheel screen didn't open from that context.
- `S18/x/y/0/n` with another key: that key is the Vivid cell. Rebuild with `VKEY` = x·256 + y.
- No S part: the SCP press doesn't open an editor through these lookups.

## Camera: 0.30b4 → 0.30b5 (INFO on the SCP, as movie)

**0.30b4:** OK on the SCP picture-mode cell opened the AP wheel, which the user could use; INFO still did nothing.

**How the SCP routes keys [V code].** The SCP is a state of the SsMenuLv machine: its handler `0x60e56a7f` (table word `0x611a2c3c`;
it logs `doCmd_SsMenuLv_DtlScp_EvtKeyOkOn`) is the same family as Live Control's `0x60e593be`.
- It forwards every event to the SCP screen (`0x60e4d032`) and acts only on rc 1 (OK).
- On OK it puts the cell's sid (`0x60e4d144`) in `0x61fc4370` and returns (4,7). State 7 then opens group 18 with that key; for the
  picture-mode cell the key is 111, the list.
- INFO gets no rc 1, so stock does nothing with it. The group-18 setting screens' own INFO press only toggles a flag
  (`0x60e03ffe`).

**0.30b5:**
- `ap_dtl` replaces the DtlScp handler word. INFO release, the current cell is 111, AP, pipeline mode 1, GUI 111 == 0, slot loaded →
  arm (P3 +809), key word 111, then the handler's own (4,7) exit (`0x60e56d45`), the same thing OK does on that cell.
- `ap_sc` swaps lookup (18, 111) → `0x140c` on P3 **only when armed**, so OK opens the stock list again. Any other SCP event, and
  every editor init, drops an arm.
- **Exit:** state 7's exit is `mv_exit`, which restores P from P3 +968 (the b4 OK route already left through it). A half-press saves
  AP.BIN (`ap_pre`); `ap_init` and `ap_tx` keep later stills COLOR edits on P.
- **Probe removed.** The Vivid label is "INFO Custom" again; the b3/b4 readouts showed the label builders draw the SCP cell too.

## Camera: 0.30b5 → 0.30b6 (where the SCP consumes INFO)

**0.30b5:** the label was right, but INFO still left the SCP, so `ap_dtl` never saw INFO.

**The SsMenuLv machine, decoded [V tables].** Descriptor `0x611a3bc8` = {29 states, 112 events, 138 handlers}.
- Events `0x611a2888` are {u32 code, u32 index}: 0x900c → 6, 0x9014 → 10, 0x9015 → 11.
- Handler words are at `0x611a2c08`. The matrix at `0x611a2e30` is u8 [state][event] → handler.
- DtlScp `0x60e56a7f` appears only in state 1, and only for event 0x9ac4 (the SCP screen's cell activation after OK), so state 1 is
  the SCP. That is why b5's `cmp 0x9015` there could never match.
- State 1's INFO press goes to handler 78 `0x60e5859e`: it forwards to an open sub-screen and returns 0, and only state 1 uses it.
- State 1's INFO release goes to handler 102 `0x60e59987`, a close handler shared with e.g. state 0's MENU: **this is what left the SCP**.

**0.30b6 (data-only routing, so other states stay untouched):**
- Handler word 78 → `ap_sinfo`, and state 1's release byte (`0x611a2eab`, 102 → 78).
- `ap_sinfo` passes a press to `0x60e5859e`. On a release, with cell sid 111 (`0x60e4d144` on `0x61fc4328`), AP, pipeline 1, GUI 0
  and the slot loaded, it arms, puts 111 in `0x61fc4370` and returns rc (4,7), as DtlScp does for OK; `ap_sc` turns that open into
  the wheel. Any other release jumps to `0x60e59987` with every register as on entry, so INFO closes the SCP as before.
- `ap_dtl` is removed.
- **Probe:** a release in AP with the slot loaded that misses counts at P3 +810 (+811 reason: 2 not GUI Vivid, 3 other cell; +812
  that value). Only then does the Vivid label read "INFO Custom n/reason/value". With no miss, the label is plain.

## 0.30b6 → 0.30b7: the Saturation cell, no probes

**b6 read the SsMenuLv matrix wrongly.** The dispatcher `0x60d11448` indexes it **event-major**: handler =
words[matrix[event_index · 29 + state − 1]] [V code]. Read that way:
- state 2 is Live Control (every key → `0x60e593be`);
- state 3 is the SCP: OK → DtlScp `0x60e56a7f`, INFO press → `0x60e56eff`, INFO release → `0x60e56f3f`, which cycles sid 281 and
  leaves the SCP.
So b5 hooked the SCP's OK handler and waited for INFO there. b6 changed byte `0x611a2eab`, which is **(state 8, event 0x9008)**, from
the default handler 102 to 78 (state 7's 0x9008 handler).

**Vivid → Natural on dial re-entry, cause [I strong]:** handler 78 forwards the event to the last group-18 screen
(`0x61fc4330`), which is the picture-mode list. With b6's byte, a 0x9008 ("next") arriving in state 8 stepped that list one entry on.
None of the other hooks writes a picture mode: `ap_ccg` only answers 15272 at the three Color Creator sites, and `ap_unswap`,
`mv_exit` and `ap_init` only touch the state word. b7 returns the byte and word 78 to stock (diff check D).

**b7, built:**
- **INFO on the SCP Vivid cell:** handler word 24 (`0x611a2c68`) → `ap_sinfo`. Under the event-major reading, word 24 serves only
  (state 3, INFO release) [V, build-checked].
  - Cell 111 (`0x60e4d144` on `0x61fc4328`), AP, pipeline 1, GUI 0 and the slot loaded → arm (P3 +809), key word 111, rc (4,7), the rc
    DtlScp returns for OK.
  - State 7 then opens lookup (18, 111), and `ap_sc` swaps it to `0x140c` on P3 only while armed. So OK on that cell still opens the
    stock list. An editor init drops any leftover arm.
  - Anything else goes to the stock `0x60e56f3f` (the sid 281 cycle that leaves the SCP).
  - INFO is 0x9014 / 0x9015, the only INFO codes in the event map; the press handler stays stock.
- **Fallback:** OK on the SCP Saturation cell (group 18 key `0x77`, sid 119) in AP + Vivid + slot opens the AP wheel instead of the
  −2..2 slider. Sid 119 shares its value list with sid 186, the saturation of Custom on Vivid [I: the cell's label wasn't read].
- The Live Control INFO route stays. `ap_dtl`, b6's byte and word edits, and every probe are gone.
- **Label:** "INFO Custom" (mv_lb's own writer), in AP and in movie.
- **Checks:** T runs the real dispatcher with the real tables: state 3 INFO release on Vivid → (4,7) → state 3's exit `0x60e57a89`;
  every other state, event and miss reaches the v0.29a handler.

## 0.30b9 → 0.30b10: stale heap marks

**Symptom (b9):** no "INFO Custom" label and no wheel, even after a half-press and shots. The camera's AP.BIN (a Film pick,
"Cibachrome") loads correctly on the composed b9 image in emulation, including the name resume into L3, so the file, the loader and
the heap layout are fine. min_ss and live_nd n7 touch none of our sites or gates; with `ap_custom` alone the image is byte-identical
in our ranges.

**Cause [V code, I for the camera state]:** P is a fresh class-1 malloc on each power-on, and the BUNDLES loader zeroes only +544..+703.
Our marks (+960 `EP7V`, +980 `EP7T`, +984 `EP7A`, +988 P3, +992 `EP7U`) are trusted on sight. DRAM keeps a previous session's bytes,
and the pools hand out blocks in the same order, so a new P can carry the old marks:
- `ap_post` sees `EP7U` (tried) and never loads AP.BIN;
- `ap_mode` follows the old P3 pointer into a block that's been reused, whose magics fail, so there's no label and no wheel;
- mv_trig likewise skips its first-press loads on a stale `EP7T`.
b7 worked when its session started from clean memory.

**Fix:** one .bss byte, `0x6203c8bb`, which boot clears (the padding after rotation's latch `0x6203c8ba`; same evidence as that latch).
On the first half-press with a valid P this power-on, `ap_pre` clears P +980, +960, +984 and +992, then sets the byte. mv_trig then does
its film and Movie loads, and `ap_post` loads AP.BIN. This also protects the Movie slot. New F case "stale": a fresh P with an earlier
session's marks loads AP.BIN on the first press (on b9 it doesn't).

**ISO / WB cells on the SCP in AP:** not ours. The screen lookups give the same registers, heap and caller stack as v0.29a for keys
6, 7, 8, 9, 10, 85, 866, 1106 and 1139 in AP + Vivid with the slot loaded, and the SCP's OK handler (DtlScp) is stock. A per-mode
CANEXEC rule wasn't decoded [I: stock restriction].

**Vivid → Natural:** every AP sub-mode's preset table (records `{mode, table, count}` at `0x6047a7d0..`, e.g. 211 → `0x60475e88`, 227
pairs) holds (1645, 2) and (111, 2), Natural. Picking a sub-mode in the AP menu applies its preset, so this is very likely stock.
b6's misrouted byte was a second, separate route and is gone.

## 0.31a1: BUNDLES not in use after a crash-restart

**Symptom (v0.31):** after a crash-restart during a heavy grain + halation shot, and again after a power cycle, the camera behaved stock
(no look names, no HSL / FX pages): P never loaded. The card files pass the v0.31 loaders in emulation.

**What the BUNDLES loader trusts across a restart [V code]:** only its state word `0x622cbcc2`, which is in .bss and so is zeroed by
the boot code on every start, warm or cold. So it isn't stale. But it gets **one attempt per power-on**, spent as soon as the gate
passes, and the gate accepts any of four media status words == 0xF000 (SD_BUNDLES_V2 §6.5). If fopen or fread fails on that press,
for example a card still mounting or being checked after an unclean stop, the state stays 0xFFFF for the whole session. That's stock
behaviour until the next power-on [I: which step failed on camera isn't known]. Our own marks (P +960/+980/+984/+992) were already
reset once per boot (0.30b10); the film loader's `EP7F` at P+1020 only matters once P exists.

**Fix:** `ap_boot`, called from `ap_pre` on every half-press, sets state 0xFFFF back to 0 up to 4 times per boot (count in the high
nibble of the boot-cleared byte `0x6203c8bb`). The loader's own gate and checks then run again on the next half-press, in the same
proven context. A handle, a P2 / P3 swap or 0 are never touched. Without card files that's at most 4 extra fopen calls.
- `ap_boot` sits after the loaders: patches/halation rewrites ap_load's zero check at the fixed address `0x601df8e2`, so ap_pre's call
  is padded with nops to keep it there (build-checked).
- **E** runs the real loader (sd_hook, gate, sd_load, sd_check) on the crash card's BUNDLES.BIN: press 1 has no file → 0xFFFF; ap_pre
  re-arms; press 2 loads (`EP7B`, handle published). **R:** 0xFFFF is reset only on a press and only up to the cap.
- **Workaround on the camera:** if it happens, half-press a few times; the reset never needs a battery pull.

## Open risks

- **Key 11 in AP job kinds** is a combination stock never makes in AP. COLOR + Multiple Exposure (menu) and COLOR + Live Composite
  (M / B) may be stock combinations in P/M [I]. HDR, Keystone, Panorama, Focus/AE bracketing are least known. A bad mode drops
  out with one byte (the AP list in `ap_mode`).
- **Whether Multiple Exposure / Live Composite combine jobs pass a converter** is not traced. If not, the combined frame gets key 11
  and P3 S from the capture record but no ext marker, so H/L, tone and grain miss [I]. Harm is not expected: misses are stock paths.
- Vivid's own contrast, sharpness and gradation stay (read per mode), as in movie [I]. The JPEG may report COLOR profile 4 [I].
- **The live view job key is fixed when the job is built** (MOVIE_COLOUR). After the first half-press, cycle the dial or picture
  mode for the preview. Captures read at shutter time, so stills follow at once [I].
- `ap_tx` runs `ap_on` (up to 4 getter calls) on every COLOR4-row read, including in pipeline tasks. That is about 100 B more stack
  than mv_prof's getter read in the same places [I].
- SCN Panorama, if it also uses value 14, counts as AP [I].
- No Control Panel export for AP.BIN yet. The MOVIE.BIN export, renamed, is the format.

## Camera test

1. Copy `generated/ap_custom/pkg/DCOLYMP/` and `EP7MOD/` (with AP.BIN) to the card; flash. Firmware screen: v0.30a1.
2. P mode COLOR1–4 shots and movie Vivid INFO Custom: as v0.29a.
3. Dial AP → Multiple Exposure (then Live Composite). Half-press once. Live Control → Picture Mode → Vivid → INFO: the wheel opens.
   Make an obvious edit (greens hue +7, reds S +5). OK.
4. Shoot: the JPEG has the look. Cycle the dial: live view shows it. Half-press: AP.BIN rewritten (AP.BAK after the second save).
5. Power cycle, half-press, AP Vivid: the look is back; movie Vivid still has its own.
6. The other AP modes one at a time. If one fails or restarts: battery out, note the mode.
7. Remove AP.BIN: AP Vivid is stock and INFO does nothing.
