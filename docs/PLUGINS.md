# SD-card plugins (E-P7 1.1, v0.32 early test)

> **Shelved (owner, 2026-11-13).** Camera-proven: the loader works (L7). Not working: the Shortcut cycle (no Fn press reached either hook, K0) and the Extras overlay (text intermittent, garbled, and the rear dial broke). The last diag/trace build (098c048b…, §13) was never run on the camera. Releases build v0.32 with `plugins=False`. Resume from §13 if this is picked up again.

A plugin is a small piece of code on the card, `EP7MOD/PLUGIN.BIN`, that the firmware loads once per power-on and
runs. It lets a feature be tried without a new firmware flash. Background and the design study:
[RE_DRAW_PLUGIN.md](RE_DRAW_PLUGIN.md) §3–§5. Code: `patches/plugin_loader/` (loader, checks in `verify.py`),
`tools/plugins/hello/` (the first plugin). Space claims: [CODE_SPACE_MAP.md](CODE_SPACE_MAP.md) (v0.32 table).

Status: emulator-verified, **not camera-tested**.

## 1. Loading

- **When:** on the first shutter half-press after power-on, as the last step of the card loaders (after
  BUNDLES.BIN, LOOKS.BIN, MOVIE.BIN and AP.BIN). Boot never reads the card, so a bad plugin can't cause a bootloop.
- **Once:** ap_post's `EP7U` guard (heap P+992) lets the step run once per power-on. Later half-presses do nothing.
- **How:** malloc one 16 KB class-2 block B, open the file, check the size (34–16384 B), read it all, close it,
  check the header (§2). Any failure frees B and leaves the camera as it was without a plugin.
- **Run:** `init` is called at file offset 32 through the cached alias of B (B − 0x40000000). If it returns 0, the
  loader stores B at P+856 and then `EP7K` at P+852 (the "ready" mark, written last). From the init call on, B is never
  freed or reused, so no I-cache maintenance is needed.

## 2. File format

Little-endian. The file is one image linked at 0; bytes 0..31 are the header, code starts at 32.

| Offset | Size | Field |
|---|---|---|
| 0 | 4 | magic `EP7P` |
| 4 | 4 | CRC-32 (zlib) of bytes 8 .. end |
| 8 | 2 | ABI version, `1` |
| 10 | 2 | flags, `0` (any other value is rejected) |
| 12 | 4 | firmware id `5d d9 af 16` (first bytes of the stock E-P7 1.1 main SHA-256, as in BUNDLES.BIN) |
| 16 | 4 | file size (must equal the real size) |
| 20 | 8 | reserved, 0 |
| 28 | 4 | hook word, 0 in the file. `init` may set it (§3) |
| 32 | – | `init` |

`tools/plugins/hello/build.py` has `make(code)`, which fills the header for any linked image.

## 3. ABI v1

**init** is entered with `calls`: a0 = API table, d0 = B (the uncached alias; use it for data, since code runs from
the cached one). It returns d0 = 0 to accept or non-zero to decline, with `rets`. A declined plugin stays in memory
but is never called again.

**API table** (read-only, 4-byte aligned):

| Offset | Content |
|---|---|
| +0 | u16 ABI version (1), u16 number of words that follow (3) |
| +4 | pointer to the wide Caduceus version string (L"0.32") |
| +8 | prop_get 0x6005e971: d0 key, d1 index, a0 0, 4 B argument slot; frame `[d2,d3],12` → d0 |
| +12 | text setter 0x60d4c9df: a0 widget, a1 wide string; frame `[d2,d3,a2,a3],24` |

Check the version and the count before using an entry. Later ABIs only add words at the end.

**Hook word B+28 (Firmware screen):** while the plugin is ready and B+28 is non-zero, Setup > Firmware shows the wide
string at B+28 in place of `0.32`. This is the only hook in v1. With no plugin, or B+28 = 0, the screen is unchanged.

The `hello` plugin (120 B) copies the version string into its block, adds `P` and sets B+28, so the Firmware screen
reads **Caduceus: 0.32P** after the first half-press.

Entries +8 and +12 are the raw stock entry points. They end in `ret [regs],imm`, so a caller has to build the same
frame a stock `call target,[regs],imm` would. No plugin uses them yet and that path is not emulator-tested. ABI v2
should add vetted thunks in our code space that a plugin can enter with plain `calls`.

## 4. Rules for plugin authors

- **Never call flash, file-write, settings-write or updater code** (for example 0x600c4f35, fwrite, the firmup
  paths). A plugin is unrestricted code on a CPU with no MMU: these calls can brick the camera. Only the API table is
  supported; any other stock address is at the author's risk and breaks on a rebuild.
- Position-independent code only: reach your own data through d0 = B, never through an absolute address.
- No `fb`-prefixed forms, no mul/div/setlb, no `trap` (the same rules as our firmware code). `hello/build.py`'s
  `check()` rejects them.
- Keep d2, d3, a2, a3 and the stack as found; use ≤ 512 B of stack; return quickly. `init` runs in HLS_EVENT on the
  half-press, so no blocking calls and no loops without a bound.
- Fit in 16384 B including the header, and keep data you need later inside B (it lives until power-off).
- Write the hook word last, after the string it points to is complete.

## 5. Safety

- **No plugin = no change.** Without the file, the loader only mallocs and frees one block after AP.BIN has loaded.
  The emulator shows registers, heap and AP.BIN results identical to v0.32 without the layer.
- **Bad file = no change.** Wrong magic, ABI, flags, firmware id, size field or CRC, a file under 34 B or over
  16384 B, a short read or a failed seek: no plugin code runs and the block is freed.
- **A valid but buggy plugin can crash the camera** after the first half-press. It can't cause a bootloop, because
  every boot is stock until the next half-press. Recovery: take the card out, delete `EP7MOD/PLUGIN.BIN` on a computer.
- Looks and settings are loaded before the plugin, so a plugin failure can't damage them.
- `patches/plugin_loader/verify.py` covers all of the above in the emulator; run it after any change to the layer.

## 6. Next candidates

1. **Text drawing:** a thunk around the text setter and a widget lookup, so a plugin can label things outside the
   Firmware screen (RE_DRAW_PLUGIN §2.3, §4.3).
2. **Film-page takeover:** let a plugin supply the Film page's rows and labels through a hook word, so new pickers can
   be tried without a flash.
3. **Extras v2 pages** ([EXTRAS_MENU_V2.md](EXTRAS_MENU_V2.md)): the v2 table needs about 0.5 KB that the image no
   longer has; a plugin block has 16 KB.
4. **Shortcut-button cycle:** a plugin-defined list of settings that one button steps through. Blocked without
   one resident hook (§7).

Each needs one new hook in the firmware and one camera probe first, one feature per flash (FIRMWARE_GUIDE §10).

## 7. Shortcut-button cycle (Fn): not buildable as a pure plugin

Static study, no build. Addresses: `tools/atlas/new_shortcut.py`. **[V]** read from the bytes, **[I]** inferred.

**Where the Fn press goes [V].** The Shortcut button is keycode 15 (sid 47). It reaches CA_MAIN as event 0x0100002e
(press) / 0x0100002f (release) (table 0x60f3928c). `ca_dispatch` 0x60cf5b2c finds the handler in per-state
`{event, 1, 1, fn}` tables. It looks them up through immediates and image-resident lists (0x60cf6824), so **no RAM word
on this path can be redirected**. In shooting, the record points to the generic key handler 0x60ce0108: `btn_dispatch`,
then action class (0x60cc87ac). Class 1 is a select mode (dials, stock popup), 2 is a one-shot action, and 0 does
nothing. The function table, action table and HSM descriptors all sit in the loaded image, and a store there crashed
the camera (FIRMWARE_GUIDE §10 #2).

**Action 76 LV_CTRL_PROFILE [V].** It is class 0, so firing it from a key does nothing. Its only use is as the CANEXEC
id inside `startProfileSelect` 0x60cd4830 (it sets CA state 0x5704 and request 183). That function is reached only from
`startMoveToShootingReady` (0x60cd2fff, "START_PROFILE_NEXT_PROC"). No function code or class-1/2 action selects a
profile. So even swapping Fn's function code (for example by wrapping the getSetting interface, 0x60ccf9f3 → vtbl +8)
could give aspect (Multi Function 437 with sub-function 3 → action 50) but never profile.

**What a plugin can redirect [V].**
- The GUI HSM reads its ss table only through `hsm_ctx+4` (0x6246684c+4, read by 0x60d115c2; the stock table 0x611317c4
  is referenced once, at init). A plugin can copy the table, one descriptor and its handler words into B, change words,
  and store one pointer. The GUI does see Fn: in shooting (SsCommon state 8), 0x9057 goes to handler word 57, a no-op
  (0x60e4ba62) that nothing else uses.
- This doesn't solve the problem. CA still runs Fn's assigned function at the same time, and the dials are CA's, so the
  GUI can't change what they control.

**What's needed: one resident hook in CA (about 40 B, a future build) [I design].**
1. 5 to 7 B at the generic key handler 0x60ce011a (`call 0x60cc9a05,[d2],4`, the first call after the event copy), or
   at `btn_dispatch` 0x60cc872f (5 B of whole instructions up to 0x60cc8734; nothing branches into 0x60cc8730..33).
   It jumps to a stub. The stub replays the instructions. If P+852 = `EP7K` and a new hook word in the block (for
   example B+24) is non-zero, it calls that word with `calls`, passing d0 = event, a0 = CA module, a1 = event record. A
   return of 1 means consumed (`ret [d2,a2,a3],40`). Anything else continues stock.
2. Plugin side:
   - On 0x0100002e in a still P/A/S/M state, step the mode.
   - Aspect: enter the class-1 handler 0x60ceb5b6 with d0 = 50 (stock aspect popup, dials).
   - Profile: call `startProfileSelect`. Its a0/a1 context and its CA state 0x5704 have to be traced first.
   - Any other event, AP or movie: return 0 (stock).
3. Without PLUGIN.BIN the hook word stays 0, so the stub only adds one load and compare per key event.

## 8. ABI v2 helpers (plugin-side)

A stock function that is entered by `call f,[regs],n` ends in `ret [regs],n` (or `retf`). To call it with `calls`,
build the same frame in a small plugin thunk:

```
thunk:  movm [regs],(sp)       ; same register list as the stock call
        add -(n - 4*k),sp      ; k = number of registers in the list
        jmp (a2)               ; a2 = f, loaded by the caller; d0, d1, a0, a1 carry the arguments
```

The caller does `calls thunk`, which stores the return address at (sp) and in mdr, so both `ret` and `retf` come back
to it. a2 comes back holding f (the callee restores the a2 it was entered with), so save your own a2 first. Stock dual-entry functions use exactly this prologue (0x60d11448: `movm [d2,d3,a2,a3],(sp); add -32,sp` in front
of the `call` entry 0x60d1144d, frame 48) [V]. Stack arguments go at the caller's (4,sp), (8,sp) … before the call.
One thunk per frame shape: prop_get `[d2,d3],12` → `add -4`; text setter `[d2,d3,a2,a3],24` → `add -8`.
**Not emulator-tested**, and no plugin uses it yet.

## 9. Key hook build log

Progress notes for the resident key hook and the Shortcut-cycle plugin (v0.32), newest last.

- **Site.** Hooked the generic key handler at 0x60ce011a (`call 0x60cc9a05,[d2],4`, 7 B), not `btn_dispatch`. There
  the handler's own frame is live (a3 = CA module, a2 = event record, sp+4..27 = the copied record), so "handled" can
  leave through the handler's own epilogue `ret [d2,a2,a3],40`. `btn_dispatch` only sees the mapped key in d0.
  Nothing branches into 0x60ce011b..0x60ce0121 (`ep7_xref.py --short`). The registers at the site are fixed by the
  copy loop (a0 = sp+28, a1 = a2+24, d0 = (24,sp), d1 = 0), so the miss path rebuilds them and replays the call.
- **Handler return value is ignored** by the matcher 0x60cf304c (`calls (a2)`, then `mov a3,d0`), so the handled path's
  d0 does not matter.
- **Fn release (0x0100002f) never reaches 0x60ce0108**: it goes to per-state release handlers (0x60ce05ab and others).
  A plugin can only take the press. The release still runs stock for whatever function Fn is assigned.
- **Profile: not added.** `startProfileSelect` 0x60cd4830 is a step of the move-to-shooting-ready flow, not a
  select mode: it calls the LV_CTRL action setter 0x60ccac3e(75), rewrites CA state (+192 = 0x5704 or 0x5109) and the
  request word (+32 = 183 or 174), and calls three GUI vtable entries, behind six precondition checks that belong to
  that flow. Firing it from a key press is the COLOR Blur pattern (FIRMWARE_GUIDE §10 #8). The plugin ships aspect only.
- **Status (stopped before tests).** Built: `patches/keyhook/` (kh.s.in, build.py: 172 B at 0x607b6430, API v1.1 at
  0x607b64c0, claim reference scan with 14 dis-checked pins plus the 0x40e4ab40 pin, three `sdk` words -> kh_ret0),
  wired into `patches/v032/build.py` (`keyhook=True`), and `tools/plugins/shortcut_cycle/` (304 B, aspect only, "0.32S").
  Not done: `patches/keyhook/verify.py` (emulator N/H/C/D tests), the package and its anti-brick check, the docs
  (CODE_SPACE_MAP rows, CHANGELOG, atlas). **Do not flash** until the verifier passes (it now does, see below).
- **Step 2.** `apply(v0.31d, keyhook=False)` == current `generated/v032/edits.json` (edits identical; only split_tone's st_k tuple/list metadata differs before JSON).
- **Step 3-5.** v0.32 rebuilt with keyhook (overlay layer not yet in `patches/v032/build.py`): 501 edits,
  `generated/v032/rel/patched.pkg.bin` sha256 1b332fe1…bd62d0. Anti-brick PASS (decode == stock + edits == emulated
  image, restore == stock, files on disk match). Previous package kept in the scratchpad. PLUGIN.BIN (304 B) in
  `generated/plugins/shortcut_cycle/EP7MOD/`. **Emulator verifier still not written: not camera-ready.**
- **Step 6.** Docs: CODE_SPACE_MAP v0.32 rows (claim, sub-command words, key site, API mov, B+24), CHANGELOG v0.32 line, `tools/atlas/new_keyhook.py`.
- **Verifier, chunk 1.** `patches/keyhook/verify.py` harness: whole `ca_key_generic` run from its `calls` entry to the
  caller's return address, real hook / ap_P / plugin code, the handler's stock callees (kmap, btn_dispatch, 0x60cd423b,
  action_class, class-1/2 handlers, prop_get) stubbed and logged from the trace. First Fn / arrow runs == keyhook=False.
- **Verifier, chunks 2-4.** Added S (static), N (142 CA key events x 10 states: no plugin, hello, six bad hook words),
  H (test hooks returning 1 / 0 / 2, with and without clobbers), C (shortcut_cycle through the real loader), D (sdk words),
  R (plugin_loader N/R/V/F on the keyhook build). Harness fixes, not hook bugs: the btn-20 early exit reads the state
  word at record+196 (a2 is the record), and the pl_chk mov imm32 merges into plugin_loader's edit, so S allows it by address.
- **Verifier, chunk 5.** P (package anti-brick + PLUGIN.BIN rebuild) added. Two more harness fixes: the stock-run
  comparison now leaves out the plugin's own calls (hook, prop_get via ka_get) from the call log, and the Firmware check
  expects "0.32S" in BASE too (keyhook=False keeps plugin_loader's B+28 hook). No hook or plugin change so far.
- **Verifier: ALL PASS** (`.venv/bin/python -I patches/keyhook/verify.py releases/v0.31d/edits.json generated/v032/edits.json
  generated/v032/rel generated/plugins/shortcut_cycle/EP7MOD/PLUGIN.BIN`, about 5 min, about 2 min of it the BASE build).
  S: 188 B differ, all in the 6 keyhook sites, keyhook.apply(BASE) == NEW. N: 1420 runs (142 CA key events x no plugin /
  hello / 6 bad hook words, 8 handler paths) == keyhook=False. H: return 1 leaves through `ret [d2,a2,a3],40` with pc, sp,
  d2, d3, a2, a3 as entered and no stock callee; 0 / 2 / 0 with clobbers == BASE. C: shortcut_cycle through the real
  loader, Fn in still modes -> ka_sel(50) twice; movie, AP 14 / 209..216, record+4 == 152, Fn release and the 141
  other events == BASE; Firmware "0.32S" at both sites. D: the three sdk words return d0 = 0 in 2 instructions.
  R: plugin_loader verify.py ALL PASS on the keyhook=False spec; its N / R / V (v1.1 table) / F pass on the keyhook build.
  P: package anti-brick PASS (decode == stock + 501 edits == emulated image, restore == stock, files on disk match).
  No hook or plugin change was needed, so generated/v032 was not rebuilt: `patched.pkg.bin` sha256 1b332fe1…bd62d0,
  PLUGIN.BIN 304 B sha256 94ce3a39…cc25cf9. Emulator-verified; **not camera-tested**.
- **Fn cycle v2 (press 1 stock, press 2 aspect, press 3 close): blocked, nothing built.** Static trace of the stock image [V]:
  the `{0x0100002e, 1, 1, fn}` records, mapped to CA states through the state lists, send Fn to `ca_key_generic`
  0x60ce0108 (our hook) only in states 0x5100, 0x5201, 0x5204, 0x5300, 0x5400 and 0x5b00. The select-mode handler
  0x60ceb5b6 requests 0x5805 / 0x5808 / 0x5c09 (record+200, request 157 at record+32) or enters 0x5800 (0x60ce3f67).
  In 0x5800-0x5805, 0x5808, 0x5809 and 0x5c09, Fn goes to **0x60cebc89** (its own copy loop and
  `call 0x60cc9a05,[d2],4` at 0x60cebc9a, then btn_dispatch and a jump table on functions 12..62 at 0x60f4d728; 49 and
  50 land on 0x60cebd76, which is a no-op unless d3 == 1). In 0x5704 (startProfileSelect) Fn goes to 0x60ce017e, the
  unhooked twin. A colour-profile assignment fires action 49 SELECT_MODE_COLOR_CREATOR (class 1, so a 0x58xx state)
  or 76 LV_CTRL_PROFILE (class 0, does nothing). **So press 2 or 3, made while a popup is open, never reaches the hook.**
  Options: (a) plugin only, no flash: Fn alternates between stock and aspect on presses made with no popup open (the
  hook sees only those). The user closes each popup the stock way. Any other key event the hook sees resets it to
  stock. This loses "press 2 while open" and "press 3 closes". (b) Resident, the real fix: a second jmp at 0x60cebc9a
  (same 7 B call shape) into the same kh stub with the 0x60cebc89 epilogue `ret [d2,d3,a2],48`, about 30 B in the
  claim, plus a re-verify and a new flash. A RAM redirect of the getSetting interface (0x60cfd27b lookup, vtbl +8) is
  unverified, and changing Fn to 50 while in 0x58xx would only reach the 0x60cebd76 no-op.
- **Fn cycle v3, chunk 1 (built, not yet verified).** The film picker can't be opened from a key: it exists only as the
  Film stop inside the Colour Profile editor's GUI cycle (FILM_MENU_V2 §1, LOOK_PICKER §10), and none of it is
  built. So this build ships profile -> aspect, and the film step is left for when 12d exists (it would need a GUI-side
  entry, not a CA select mode). Resident: second site 0x60cebc9a (`call 0x60cc9a05,[d2],4` in the select-state key
  handler 0x60cebc89, also entered as `call 0x60cebc8e,[d2,d3,a2],48` from 0x60cec20a, the keycode-28 handler;
  `ep7_xref --short` finds nothing branching into 0x60cebc9b..0x60cebca1) -> kh2, handled exit `ret [d2,d3,a2],48`
  (= 0x60cebd88). kh_chk now passes d2 = site (0 shooting, 1 select state) and a0 = CA or 0 (there is no CA module at
  site 1). API v1.1 grows to 7 words: +24 features = 3, +28 = &0x6233b9a4 (the open select mode's action). `.kh` is
  216 B. Plugin (364 B): press 1 stock; press 2 in the popup = stock exit (request 158 at record+32, like the select
  states' `{ev, 158, 1, 0}` records) and arm aspect; press 3 = aspect (ka_sel 50); press 4 in aspect = stock exit
  (close, no wrap). Not using 0x60cebc43 (exit and replay): 0x5800's exit replays the stored key through 0x60cebdeb,
  which bypasses the hook and would reopen the profile popup. A same-press switch (exit and enter aspect in one
  event) would be two CA transitions in one event, the FIRMWARE_GUIDE §10 #8 pattern, so press 2 only closes.
- **Fn cycle v3, chunk 2.** verify.py: site-1 harness (stubs for 0x60cebc89's callees, the 0x6233b9a0 / 0x61fb0dd0
  globals, three entries: 0x60ce0108, 0x60cebc89, 0x60cec1f3 -> `call 0x60cebc8e`), N over all three, C rewritten for
  the cycle. Scope set by the owner: N sweep, one cycle pass, one reset, movie/AP, anti-brick (H/D/R still available
  with `--only`). S + C PASS on the keyhook-only spec. generated/v032 rebuilt **with** the verified overlay probe layer
  (one flash): 506 edits.
- **Fn cycle v3: ALL PASS (emulator; not camera-tested).** keyhook verify.py on the final generated/v032 (keyhook +
  overlay probe, 506 edits): S 848 B, all in keyhook + overlay sites, rebuilt from BASE == NEW. N 4260 runs (142 events x
  10 states at site 0, site 1 and the 0x60cec1f3 entry) == keyhook=False. C cycle 1 -> 2 -> 3 -> 4, a reset after a
  close by OK, movie / AP at both sites == BASE, Firmware "0.32S". P anti-brick PASS. overlay_probe verify.py on the same
  image: ALL PASS (OFF, UPD, DRAW, MISS, P). Package `generated/v032/rel/patched.pkg.bin` sha256 4976b8c2…20e7ef
  (previous 1b332fe1… kept in the scratchpad). PLUGIN.BIN 364 B sha256 e2556151…. **Open on the camera:** after
  press 2's exit the plugin waits for press 3; it doesn't open aspect in the same press. Also check that the open
  select mode (0x6233b9a4) reads 49 for the colour-profile popup.

## 10. Camera diagnosis (v0.32 on the camera: no "0.32S", Fn stock, no overlay)

Static re-check of the camera build (package 4976b8c2…, 506 edits) against what the emulator assumed, then a resident
status readout on the Firmware screen. Newest last. **[V]** bytes, **[I]** inferred.

- **Sec-5 claim is loaded [V].** Descriptor 0x60027068 entry 5 = {0x6075a800, src 0x40dda800, dst 0x6075a800}; end
  getter 0x60045786 (d0 5 → jump table 0x60046780 → stub 0x600457b4 `mov 0x60b9e000,d0`) → section 5 is
  0x6075a800–0x60b9e000, so keyhook's 0x607b6420–0x607b8420 and the overlay's 0x607b8420–0x607c8420 are inside the
  copied range (flash source = image address − 0x60020020 + 0x406a0020, identity layout). Not a cause.
- **Loader gate [V].** ap_post 0x601df6e5: event 0x02000100, ap_P valid, P+980 `EP7T`, P+992 ≠ `EP7U` → sets `EP7U`,
  then 0x601df730 `call pl_ap` (pl_ap runs ap_load first). ap_load has no other caller, so **if AP.BIN still loads on
  v0.32, pl_ap ran**. The fixture's P (EP7B + EP7T) matches what ap_pre/mv_trig leave on the camera.
- **Loader services [V].** Frames and arguments match the camera-proven BUNDLES.BIN loader (sd_bundles_v3) call for
  call: fopen(a0 path, a1 "r") `[],4`, fseek(d0 0, d1 1 END / 2 SET) `[d2,d3,a2,a3],20`, ftell `[d2,a2,a3],16`,
  fread(a0, d0 1, d1 n, a1 h) `[d2,d3,a2,a3],24`, fclose `[d2,a2,a3],16`. The verifier stubs all of them and malloc,
  so **class-2 availability is untested**: malloc(16384) picks class 2 (0x60022782: ≤128 → 0, ≤2048 → 1, ≤16384 → 2),
  a fixed pool of 43 blocks of 0x4040 B (0xa1dd8d40–0xa1e85800) that the image-job ctor also draws from. If it is
  exhausted at the first half-press the loader silently does nothing. The readout (below) shows this as L1.
- **Firmware-screen text [V, I for the camera].** Both Body value sites go through pl_fw, which falls back to fw_val
  ("0.32"). The camera shows "0.32" slightly clipped; "0.32S" (one glyph wider) would clip to about the same, so
  **the camera reading does not tell "loaded" from "not loaded"**. Hence the short readout.
- **Stale P+852 (bug, fixed in the diag layer) [V].** P is a fresh class-1 malloc each power-on and DRAM keeps an earlier
  session's bytes (AP_CUSTOM.md 0.30b10). ap_boot clears +960/+980/+984/+992 but not +852/+856, so a new P can carry an
  earlier session's `EP7K` and a stale B: kh_chk would then call into a reused block. The new loader clears P+852 first.
- **Overlay hook: wrong place and wrong flag logic [V code, I camera].** 0x60cfe263 (`retf [],0`) is the +164 word
  of about 400 vtables. The probe re-pointed two (0x60f9477c: base class, ctor 0x60cff51e; 0x60fac34c: its one subclass,
  ctor 0x60d43e80, made only at 0x60d39f41), so any window of another class never reached ov_post. And ov_post
  cleared the flag on the first post-paint after each view update, so at best one frame was drawn and then painted
  over. The emulator drove ov_post directly, so it saw neither. Also, the flag and counter used the uncached alias
  0xa22ab792/3 while stock keeps 0x622ab790/794 in the same cache line: an uncached store can be lost when that line
  is written back (VIDEO_ROTATION.md). The view itself is right: vtable 0x61155e14 (+0 update 0x60dec790, +4
  dtor 0x60dec697) is the Colour Profile editor's view, whose guide label (update part 3) already works on the camera.
- **Fix (patches/diag, last layer of v0.32).** The hook moves to the one +164 call site in the GE paint routine
  0x60d00506 (0x60d005ef `mov (164,a2),a2; calls (a2)` → `jmp dg_paint` + nop; one caller 0x60d3907e; nothing
  branches into 0x60d005f0–f4), which sees every window. The two vtable words go back to stock. The flag is now
  "view alive": set by the view's update (+0), cleared by its dtor (+4), read on every paint, cached alias.
- **Readout (patches/diag).** Firmware screen Body value shows **`L/O`** (3 glyphs, narrower than "0.32"), always,
  in place of "0.32" or a plugin's B+28 text (an empty field still passes through):
  - L = loader stage, bits 1–3 of the ap_custom boot byte 0x6203c8bb (ap_boot keeps them: it only ORs bit 0 and adds
    to bits 4–7; same HLS task): 0 not run, 1 no file or no 16 KB block, 2 opened but seek/size/read failed,
    3 magic/ABI/flags, 4 firmware id, 5 size field/CRC, 6 init declined, 7 accepted;
  - O = overlay stage, bits 4–6 of 0x622ab792 (bit 0 = view alive): 0 none, 1 the view's update ran, 2 a post-paint
    ran while the view was alive, 3 the first text call was made.
  The loader is pl_ap + pl_chk re-laid in sec 5 (`jmp dg_ap` at pl_ap) with the stage marks and P+852 cleared first.
- **Verified (emulator; not camera-tested).** `patches/diag/verify.py BASE NEW [rel] [PLUGIN.BIN]`: S (1178 B differ,
  all in diag edits, rebuild == NEW), L (18 cases give L0…L7 as above; stale `EP7K` cleared; boot 0x31 → 0x33; no
  file == BASE), O (paint with the view not alive == BASE; alive + Extras → 4 draws, O3; elsewhere O2 and no draw;
  update O1; dtor clears alive with every register as found), F (both sites, 6 states, empty field == BASE), P
  (package anti-brick). Superseded on this build, by design: plugin_loader F / V "0.32P", keyhook C "0.32S", and
  overlay_probe OFF/DRAW (they drive the vtable words).
- **Build.** generated/v032: 507 edits, `rel/patched.pkg.bin` sha256 9a1a5be1…20e0fd1c (restore 963f4dfe…; the
  4976c8b2 package is kept in the scratchpad). PLUGIN.BIN unchanged (364 B, e2556151…).
- **What to read on the camera.** Setup › Firmware, Body value, after one half-press:
  `7/x` plugin loaded (then Fn press 2 inside the popup is the open question: if the owner's "Colour/Mono profile
  scroll menu" is not a 0x58xx select state, press 2 never reaches the hook, §9); `1/x` with PLUGIN.BIN on the card =
  no 16 KB block free or fopen failed; `0/x` = pl_ap never ran (then AP.BIN cannot load either). Then open a COLOR
  profile editor, go to the Extras page, back out, reopen Setup › Firmware: `x/0` the view never updated (wrong view),
  `x/1` no post-paint while it was alive (wrong paint path), `x/2` drawn condition failed (P / EP7E / axis 4), `x/3`
  text calls made (if nothing is visible, it is the draw recipe: gc, colour or layer).
- **Camera vs emulator lessons.** (1) A hook re-pointed in a vtable covers only that class; for "every window" hook
  the one call site. (2) A verifier that calls a hook directly can't tell whether stock ever calls it: also trace one
  real caller, or report a stage on the camera. (3) A "set by A, consumed by B" flag only works if A runs at least as
  often as B. (4) Shared cache lines: use the cached alias for .bss pad bytes, as stock does. (5) Stubbed services
  (malloc) hide pool exhaustion: leave a stage mark.

## 11. Overlay text invisible on the camera (diag `7/3`): text colour 0

Camera, diag build 9a1a5be1…: `7/0` after a half-press (plugin loaded), `7/3` after the Extras page (text call made),
but no text on screen. Static trace of how stock draws the Colour Profile editor's guide label, then one fix. **[V]**
bytes, **[I]** inferred. Addresses: `tools/atlas/new_diag.py` (§11 block); corrections in `new_overlay.py`.

- **How stock draws the guide label [V].** The view's update 0x60dec790 runs its part list (view+4…; part 3 is the
  guide), then publishes GUI data 175 (96 B at view+40, which holds the 74-B label at view+44) with 0x60cfeca9. A
  label widget renders it in its draw method 0x60d4c434 (vtable word 0x60faeeb4), inside the window paint, with the
  paint gc: `0x60d0fce0(gc, widget+128)` (text-style id, not a font index), `0x60d0fd83(gc, 2)` (gc+0x34), then
  for inline text (widget+174 == 1) `0x60d075a7(d0 = widget+132 style, d1 text, a0 gc, a1 rect)`. **No colour call on
  the gc**: the colour is in the style record.
- **The string drawer takes its colours from the style [V].** 0x60d075a7 saves gc+0x24/+0x28c/+0x290, then calls
  `0x60d0fc05(gc, style+0)`, `0x60d0fb5d(gc, style+4)` (gc+0x28c) and `0x60d0fb40(gc, style+8)` (gc+0x290), draws,
  and restores them. Style layout (24 B, corrects EXTRAS_OVERLAY §2.1): +0 text colour, +4 / +8 two more colour words,
  +12 h-align (0 left, 1 centre, 2 right), +13 v-align, +14 x offset, +16 right inset, +18 y offset, +20 bottom inset.
- **Cause [V code, C symptom].** The probe set the colour with 0x60d0fc05 before the call and passed a zeroed
  style, so the drawer overwrote it with colour 0. The OSD layers are 8-bit palette (OSD.md): entry 0 is `00ffffff`,
  transparent, so all four rows were drawn invisibly. The emulator logged the gc colour calls and so passed.
- **Paint path checked, not a cause [V].** GE paint 0x60d00506 (single-layer path): begin 0x60d0642a copies the
  window's update region (window+1392, 36 B: two rects, count at +24) into gc+168, sets gc+12 / the DC clip from
  window+1200; children draw; +164 (our site); paint end 0x60d06468 = `ge_present` 0x60d0ed79 → 0x60d125af (flips the
  **whole** back buffer with gpiUpdateDisplay when 0x61fb2939 is set) and then copies only the update-region rects
  front → back (0x60d0ed81 → DC +8). So text drawn at +164 is in the same back buffer as the stock widgets and is shown
  by the same flip; outside the update rects it is not carried into the other buffer, but dg_paint redraws on every
  paint. The text under our rows is not cleared (row D will ghost: expected, it is the probe's ghosting test).
- **Fix (patches/diag).** Each row writes its colour (1, 2, 4, 6) into style +0; the gc colour call is gone (stock
  label recipe: style colour, gc+0x34 = 2, no font change, so the window gc keeps the font the stock labels set).
  New guard: gc+0x4c (font) == 0 → no call (the drawer would return without drawing) and O4.
- **Readout (Firmware Body value, still `L/O`, 3 glyphs).** O: 0 none, 1 view update ran, 2 post-paint while the view
  was alive, **3 text drawn with a font on the gc**, **4 Extras page reached but the gc had no font (no draw)**; 3 wins
  over 4. Flag byte 0x622ab792: bit 0 alive, bit 3 the O4 mark, bits 4–6 O1–O3. Room for a keyhook digit K: the
  readout buffer is built at dg_fw's (4,sp) in an 88-B frame, so `L/OK` (4 glyphs, narrower than "0.32") fits.
- **Verified (emulator; not camera-tested).** `patches/diag/verify.py`: S, L, O (paint not alive == BASE; Extras →
  4 draws with style +0 = 1/2/4/6, no gc colour call, gc+0x34 = 2, O3; elsewhere O2; gc without font → O4, no
  draw; upd; dtor), F (adds `7/4`, `7/3` over 4), P (package anti-brick).
- **What to see on the camera.** COLOR profile editor, Extras page: `c1 Clarity +2` (yellow ramp, top-left),
  `c2 Halo Red 3` below, `c4 Shadow Teal` low left (white if index 4 is the white ramp), `c6 #NN` top-right (grey,
  counter steps each repaint; ghost digits expected). Then Setup › Firmware: `7/3` drawn, `7/4` the gc had no font
  (next step: select the label's text style with 0x60d0fce0). If `7/3` and still nothing, the remaining suspects are
  the window whose paint we draw into (another layer) and the palette indices.
- **Build.** generated/v032: 507 edits, `.dg` 1168 B (0x607b8700–0x607b8b90), `rel/patched.pkg.bin` sha256
  827c713a…3176c7145 (restore 963f4dfe…; the 9a1a5be1 package is kept in the scratchpad). diag verify.py ALL PASS
  (S 1181 B, all in diag edits). PLUGIN.BIN unchanged.
- **Camera, 827c713a: `7/4` [C].** The gc had no font, so nothing was drawn. Re-trace [V]: the +164 argument is the
  **painter**, not the gc. GE paint gets its gc with `0x60d060e3` (= `*(painter+8)`, 0x60d00527), present uses
  `*(painter+8)`, and the label draw 0x60d4c434 does the same (`a1` painter → 0x60d060e3 → (24,sp) gc). The probe
  (and ov_post before it, `*(window+72)` = the painter) passed the painter to the drawer, read the painter's +0x4c
  (0: lucky, else the drawer would have run on a non-gc) and stored the mode word to painter+0x34. So the no-font
  reading was the wrong object, and the earlier `7/3` builds never had a real gc either.
- **How stock puts a font on the gc [V].** Every text draw selects it right before drawing: `0x60d0fce0(a0 gc, d0
  text-style id)` → 0x60d10b88 (74-B style record = `*(0x61fc15bc + 4·bank) + 74·id`, bank 0x60d10c09) →
  0x60d0fcf1 → 0x60d106f6 / 0x60d1071b (font instance) → 0x60d0fd74 (`gc+0x4c` = font); returns a0 = font or 0 (stock
  skips the draw on 0). Label widgets pass their own id (widget+128). The generic GE draw 0x60d0695c (0x60d06bb7)
  uses the screen default: current window `*(0x61fb3138)` (getter 0x60d3379b; set by the window ctor 0x60cff51e and
  0x60cfd455), its vtable +488 = 0x60d00f90 → `u16 window+108` (the ctor sets 0).
- **Fix 2 (patches/diag).** gc = `*(painter+8)` (0 → no draw). If gc+0x4c is still 0, select the current window's
  default text style exactly as 0x60d06bb7 (window +488 → 0x60d0fce0); a0 = 0 → no draw, O4. The build checks the
  getter, both window vtables' +488 and the two function heads against the stock bytes.
- **Readout.** O: 3 drawn with the gc's own font, **5 drawn after we selected the default style**, 4 no font and none
  could be selected. Flag bit 1 = "font selected by us". Verified (emulator): painter untouched; gc with font → 4
  draws, no font call; no font → style id from window+108 passed to 0x60d0fce0, gc+0x4c set, 4 draws, O5; select
  returns 0 or no current window → O4, no draw; F adds `7/5`.
- **Build 2.** generated/v032: 507 edits, `.dg` 1230 B (0x607b8700–0x607b8bce), `rel/patched.pkg.bin` sha256
  58b45b8c…daafa77e (restore 963f4dfe…; 827c713a kept in the scratchpad). Built as `diag.apply()` on the v0.32 spec
  with the **camera-tested keyhook** (216-B `.kh`), because patches/keyhook/build.py had in-progress changes from
  the keyhook work (304-B `.kh`) that a plain `patches/v032/build.py` run would have picked up. diag verify.py ALL
  PASS (S 1239 B, all in diag edits). PLUGIN.BIN unchanged. **On the camera:** Extras page → rows as above; Firmware
  `7/3` or `7/5` = drawn (5: with the default style we selected), `7/4` = no font could be selected.
- **Build 3 (combined, K digit).** Readout is now **`L/OK`** (4 glyphs): K from the keyhook Fn stage byte
  0x6203bcb2 (§12): 0 if the site bits are 0, else 3 × (bits 0–1) − 2 + (bits 2–3) = 1..6; the count bits are not
  shown. diag build.py refuses a keyhook spec without `stage` = 0x6203bcb2. generated/v032 = v0.31d + all v0.32
  layers with the final keyhook (304-B `.kh`, API 8 words) + overlay + diag: 507 edits, `.dg` 1264 B
  (0x607b8700–0x607b8bf0), `rel/patched.pkg.bin` sha256 8ab2261d…8f49c330 (restore 963f4dfe…; 58b45b8c kept in the
  scratchpad). PLUGIN.BIN 440 B, 3183741e…a779d29a. diag verify.py ALL PASS (S 1272 B, L incl. shortcut_cycle → L7
  through dg_ap, O, F `0/00` … `7/56`, P anti-brick). keyhook verify.py `--only=SNC` runs on the same spec without
  diag (identical keyhook bytes): its loader fixture patches pl_ap's path, which diag bypasses (dg_ap has its own
  path), so C cannot load the plugin on the diag image — a harness limit, the diag L test covers that load.

## 12. Fn cycle on the camera: which popup, the press-2 switch, and the K stage digit

Camera, diag build 9a1a5be1…: `L = 7` (shortcut_cycle loaded), Fn "behaves exactly stock": press 1 opens the
Colour/Mono profile scroll menu, press 2 "does nothing new". Static trace, then a fix and a stage mark. Newest last.
**[V]** bytes, **[I]** inferred. Addresses: `tools/atlas/new_keyhook.py` (§12 block).

- **Which popup [V].** No function code maps to a profile action (BUTTONS §1), so the menu comes from Fn = Multi
  Function (code 437 → action 18 `EVF_FN`, class 2) with the colour/mono sub-function (sid 437 → table 0x60f38d8c:
  6 → 49 `SELECT_MODE_COLOR_CREATOR`). Press: site 0 (0x60ce0108, hooked) → 0x60ce026a case 18 → 0x60ce2d84: request
  174, CA state 0x590d (Fn held, no popup yet). Release (0x0100002f in 0x590d → 0x60ce2da0, unhooked): sub-function 49
  → 0x60ceb5b6 → table 0x60f4d230 → **state 0x5800**, open mode 0x6233b9a4 = 49. In 0x5800 Fn goes to 0x60cebc89 =
  **site 1, hooked**. Not 0x5704: that is the profile-lever flip (`startProfileSelect` is gated on
  `isChangeProfileLeverSw(2)`), not a Fn path.
- **So the camera result is the v3 design working, not a miss [V code, I camera].** Stock press 2 in that popup
  (0x60cebc89 case 18, 0x60cebd3d) closes it (request 158, no replay); the v3 plugin's press 2 did the same (close +
  arm) and waited for press 3 to open aspect. Both look identical on the camera.
- **Press 2 → aspect in the same press: the stock exit-and-replay [V stock path, I that the re-post lands at site 0].**
  When another key is pressed in a select state, 0x60cebc89 (case 26, 0x60cebce9..0x60cebd1d) does
  `0x60cd2330(key); request 158; 0x61fb0ddc = key; 0x61fb0dd8 = key` (dd8 only when the key's function is not the
  open mode). The exit 0x60ceb952 reads and clears dd8; a Fn press (in list 0x60f39e08, sub 0 in 0x60f3928c) goes
  0x60cebd8b → btn_dispatch → 18 → 0x60cebdeb: record+176 = key, +184 = 1, the CA's pending event, dispatched after the
  transition in the shooting state, i.e. at site 0. One transition per event (FIRMWARE_GUIDE §10 #8 is not hit). kmap
  0x60cc9a05 returns record+4 for a Fn press (table 0x60f3a088 key 1), so that is the value stock stores.
- **Change, resident (patches/keyhook).** API v1.1 grows to 8 words: +32 `ka_rep` (calls, a1 = record): mirrors the
  stock block above with v = record+4. Features = 7 (bit 2 = +32). `.kh` 304 B (0x607b6430–0x607b6560), API at
  0x607b653c. build.py checks the stock replay bytes it mirrors and allows exactly the stores listed below.
- **Change, plugin (shortcut_cycle, 440 B).** Press 1 stock (ST 1). Press 2 at site 1 with ST 1, open mode ≠ 50 and
  the key-held flag (0x6233b9ac = selw + 8) clear: `ka_rep`, ST 2, handled. The replay arrives at site 0 with ST 2 →
  `ka_sel(50)`, ST 3 (aspect). Next Fn in aspect (mode 50, ST 3): close (158), ST 0. On an API without +32 the plugin
  keeps the v3 behaviour (press 2 closes, press 3 aspect). Film sim: still no key entry point (§9).
- **Stage mark K (new).** kh_chk writes the boot-cleared .bss pad **0x6203bcb2** (cached alias; CA task only) on every
  Fn press (0x0100002e) at either site, plugin or not: bits 0–1 = site + 1 (1 = 0x60ce0108 shooting, 2 = 0x60cebc89
  select state), bits 2–3 = plugin decision (0 not called, 1 returned stock, 2 handled), bits 4–7 = Fn presses seen,
  mod 16. Pad proof (build.py `check_stage`): no abs32 word equals 0x6203bcb1..b3 in either alias, the u16 0x6203bcb0
  is reached only by movhu abs forms, the u32 0x6203bcb4 follows (rotation-pad pattern), inside the boot clear
  0x62038100–0x6203c934. 0x6203bcb3 stays free.
- **Readout K (for the diag layer's `L/OK`, added there at the next rebuild).** K = 0 no Fn press seen; else
  3 × (site + 1) − 2 + decision, i.e. 1 / 2 / 3 = last Fn at 0x60ce0108 (shooting) with the plugin not called /
  stock / handled; 4 / 5 / 6 = the same at 0x60cebc89 (popup open). Count bits 4–7 are not shown.
- **Verified (emulator; not camera-tested).** `patches/keyhook/verify.py --only=SNC` on a keyhook-only spec
  (v0.31d + v032 layers up to keyhook, scratchpad): S 324 B, all in the 7 keyhook sites, rebuilt == NEW; N 4260 runs
  (142 events × 10 states × 3 entries) == keyhook=False (stage byte excluded from the compare); C: 1 stock (stage 0x15)
  → 2 `ka_rep` (158, dd8 = ddc = record+4, 0x60cd2330 called) → replay at site 0 → `ka_sel(50)` → close; key-held
  flag → stock; no plugin at site 1 → stage 0x12, else == BASE; movie / AP at both sites == BASE. Not emulated: the
  CA's re-post of record+176 (the K digit answers it on the camera). Package / anti-brick: at the next v032 rebuild
  (overlay agent's, with the K digit). PLUGIN.BIN 440 B, sha256 3183741e…a779d29a.
- **What the user should see.** Fn: profile popup. Fn again: the popup closes and the aspect popup opens. Fn again:
  aspect closes. Then Setup › Firmware: `7/x3` = the replay reached site 0 and the plugin opened aspect (expected
  after press 2 or 3); `7/x6` = press 2 handled at the popup but the replay never reached site 0 (aspect missing:
  the re-post went elsewhere); `7/x2` = last Fn ran stock at site 0; `7/x5` = a press in a popup ran stock (wrong
  mode or the key-held flag); `7/x0` = no Fn press reached either hook.

## 13. TRACE ring log, and the overlay side effects (diag build 8ab2261d on the camera)

Camera, 8ab2261d: `7/30` (plugin loaded, text call made with the gc's own font, **no Fn press reached either hook**).
The overlay text showed only every 2–3 front-dial scrolls, only the "Halo" row, badly drawn, and while it was active
the rear dial stopped changing the selected effect's value. The physical button is labelled "Shortcut"; its event code
may not be 0x0100002e. **[V]** bytes, **[I]** inferred. Addresses: `tools/atlas/new_diag.py` (§13 block).

- **Overlay cause, found statically [V code, I camera].** Every stock text draw selects a font right before drawing
  and releases it after: `0x60d0fce0(gc, style)` → draw → `0x60d10708(font)` (calls `(0x61fb2614)`; label draw
  0x60d4c638, 0x60d457a5, the generic draw 0x60d0695c). So the gc+0x4c a stock draw leaves behind is a **released**
  font. The camera build drew with that leftover font whenever gc+0x4c was non-zero (O3), i.e. always on the camera:
  bad glyphs and font-engine state we don't own. It also left gc+0x34 = 2 and drew into **every** window that
  painted while the view was alive (popups and the value window included), not only the editor's. The rear-dial stall
  is not proven to come from this [I], but it is the only state the layer left changed.
- **Fix (dg_draw / dg_pnt).** Draw only when the painted window (paint's d3) is the current window `*(0x61fb3138)`.
  Always select the window's default style (window +488 → 0x60d0fce0, as 0x60d06bb7), draw the four rows, release the
  font with 0x60d10708, then put gc+0x4c and gc+0x34 back as found. Registers and sp were already clean (checked: the
  code after the site reloads a0/a1/a2; d2/d3/a3 come back through our frames). O now reads 5 when drawn (3 no longer
  occurs), 4 if no font could be selected.
- **Ring log.** One 16 KB class-2 block, taken in dg_ap **after** the plugin's block (so the plugin never loses a block
  to it; none free → no log). Pointer: real P (ap_P) +860 base, +864 bytes ever logged, +868 paint entries since the
  last dump. +860..927 has no user (SPLIT_TONE P+848 slot list; loader +852/856, mono_colour from +928). P is a fresh
  malloc with stale DRAM each power-on, so logging is gated on **0x6203bcb3**, the boot-cleared .bss pad byte that
  keyhook's `check_stage` left free (build.py re-checks: no reference in either alias), set to 1 only by dg_ap after
  this power-on's block is in P; the base is also range-checked against the class-2 pool. 16-B entries
  (tag, w1, w2, w3), a true ring (oldest overwritten):
  - **K0 / K1 / KT**: every key event at 0x60ce011a / 0x60cebc9a / the unhooked twin's kmap call 0x60ce0190
    (twin 0x60ce017e, same copy loop; nothing branches into 0x60ce0191..96): event code, CA state (record+196),
    record+4. All codes, before the plugin. **D0 / D1**: the plugin handled it (same words, after). dg_key0/1 run
    kh_chk / kh_chk2 themselves and leave through kh_miss / kh2_miss or the handler epilogue, as kh / kh2.
  - **PT** (capped at 64 per dump): each paint while the view is alive: window, its vtable, painter; tag bits 8–15 =
    flag byte. **PD**: gc, gc+0x4c before, after; tag bits: selected, rows, gc+0x34 before/after. **PS**: sp on entry,
    sp on exit, the draw's d0.
- **Dump.** dg_half at ap_post's half-press block 0x601df6fa (5 B `movm; add -4,sp`, relocated; d0–a1 are dead there,
  ap_post reloads them from (0..12,sp), so our call slot is below that). If the log is live and something was logged
  since the last dump: fopen(`C:\EP7MOD\TRACE.TXT`, "w" 0x60a65d37), a title line `CADUCEUS TRACE 1`, a header
  `FFFFFFFF <build id> <L<<16 | flag<<8 | kstage> <entries ever logged>`, then the ring oldest first, one
  `W W W W` hex line per entry (fwrite 0x60635041 per line), fclose. At most one write per half-press; fopen fails →
  nothing written and the log is kept. Up to 1024 lines (about 37 KB) on the HLS task: a half-press right after a
  long session may be slow once. Logs from two tasks (CA, GUI) are not locked: a rare torn or lost entry is possible.
  Decode with `tools/trace_decode.py TRACE.TXT`.
- **Verified (emulator; not camera-tested).** `patches/diag/verify.py`, scope set by the owner: S (2302 B, all in diag
  edits, rebuild == NEW), L (18 cases incl. shortcut_cycle → L7; the log block is taken after the plugin), O (one
  overlay paint: four rows, style selected and released, gc+0x4c / +0x34 as found, PT/PD/PS logged, registers and sp;
  view not alive, log off and on == BASE), K (216 runs: 3 sites × 12 sample event codes × 3 CA states × log off / on
  == BASE in registers, stack, record, CA and P; log on adds one entry), H (write path; two in a row; wrapped ring;
  fopen fail; log off / other event == BASE), F, P (package anti-brick).
- **Build.** generated/v032: 508 edits, `.dg` 2286 B (0x607b8700–0x607b8fee), build id 0xa0e02b1f, `rel/patched.pkg.bin` sha256
  098c048b…f734223d5 (restore 963f4dfe…; 8ab2261d kept in the scratchpad). PLUGIN.BIN unchanged (440 B, 3183741e…).
- **Camera steps.** Card with EP7MOD/PLUGIN.BIN (EP7MOD folder must exist). Power on, half-press once (loads the
  plugin, starts the log). Press the Shortcut button a few times (with and without its popup open), turn both dials,
  open a COLOR profile editor, go to the Extras page, turn the front and the rear dial, back out. Half-press once
  (writes TRACE.TXT). Copy EP7MOD/TRACE.TXT off the card. Also note: rows visible / clean, rear dial working, and
  Setup › Firmware `L/OK`.
