# Drawing primitives and a card-loaded plugin layer (E-P7 1.1)

Atlas unknown #2 (drawing primitives, layers, palette, geometry) plus a feasibility study for running a small code
blob from the SD card. Static analysis of the stock main image only: no build, no patch, no camera.

- Tags as in the atlas: **[V]** read from the bytes (`tools/dis.sh`, byte dumps, REA xrefs), **[I]** inference.
- Addresses are E-P7 1.1 main CPU addresses. RAM addresses are .bss/statics unless marked.
- Disassembly listings and REA dumps behind this note are private:
  `~/ep7fw-private/decomp/draw_plugin/` (`<addr>_<name>.dis`, `rea_json/`). Nothing decompiled is copied here.
- New symbols: `tools/atlas/new_draw.py` (same record format as `atlas_data.py`, not merged).

## 1. Short answers

| Question | Answer |
|---|---|
| Is there a draw API? | **Yes, three layers of it.** GUI "gpi" platform layer (sec 6, 0x60d115d4–0x60d13a6x) → `OSDControl` API (sec 5, 0x60799a99–0x6079c2xx, API ids 0x11101–0x11116) → 2D command renderer (sec 6, 0x60bab…–0x60bb0…). Dot, line, filled rect, bitmap, glyph, block copy, palette, layer order, present. [V] |
| Canvas | Every OSD plane is an **800×600** VRAM surface (clip bounds 800/600 hard-coded in the gpi checks), not 720×480. [V] |
| Layers | Three OSD planes (API plane 0/1/2 = `OSD3/LAYER1`, `OSD1/LAYER2`, `OSD2/LAYER3`) + plane 3 WORK + image planes 4/5. The GUI's layers 0/1/2 map to planes **1/2/0** with **4/8/4 bpp**. Each GUI layer is **double-buffered**. [V] |
| Palette | Index 0 is transparent in every stock block [V, OSD.md]. The 8-bpp GUI layer is a "128Color Layer" (debug string at the palette commit) [V]. **Which of the 58 stock blocks is live in shooting/LV is still not pinned** [open]. |
| Invalidate/redraw | GUI engine (GE) paints dirty widgets into the back buffer, then **present** (0x60d125af: commit palette, `updateDisplay`, flip, clear dirty), then copies the dirty rects front→back. All in task **GUI_TASK**. [V] |
| Widget geometry | **Not decoded.** View part tables in .data are function lists, not rectangles. Leads in §2.6. [open] |
| Plugin layer feasible? | **Yes, with limits.** Load once per power-on from the existing half-press loader into a never-freed malloc class-2 block, run it from that block, call it from one new hook in GUI_TASK. No I-cache maintenance is needed if the block is never re-used for code in the same power-on. Two hardware facts need one camera probe each (§4.4). |

## 2. Drawing stack

### 2.1 Layers of code

```
GE widgets / views (sec 6, GCPanel_*, *_Viewer)
  └ graphics context ("DC", 164 B) per GUI layer: +76 function table (18 words)
      └ gpi wrappers (pick VRAM of the current back buffer) → gpi primitives 0x60d127f8.. (clip, draw offset, debug log)
          └ OSDControl API 0x6079xxxx (trace id 0x111nn, builds the renderer request)
              └ renderer 0x60baf798.. (mallocs a 108-B command, queues it; flushed at drawOsdEnd 0x60bb079a)
```

- OSDControl API ids and names [V]: the .data name table at **0x6023ff38** (`OSDControl::initOsdControl` …
  `drawTrapezoid`) is indexed by the low byte of the trace id each API function passes to its tracer
  (e.g. `mov 0x11106,d0` in drawDot). Id = 0x11100 + table index + 1.
- The renderer is a command queue, not direct pixel writes [V: 0x60baf7fd mallocs 108 B via 0x60022700 and
  submits through 0x60babdda]. Whether a hardware 2D engine executes it is [I].
- A stock **debug shell** ("`sdk api`", 0x607dd584–0x607de2e8, sec 5) drives the OSDControl API directly with
  plane numbers and test patterns: a working stock precedent for calling it outside the GE [V].

### 2.2 OSDControl API (section 5)

| Id | Name | Entry | Signature [V unless marked] |
|---|---|---|---|
| 0x11101 | initOsdControl | 0x60799a99 | (); called by GPIInitPlatform |
| 0x11102 / 03 | drawOsdStart / drawOsdEnd | 0x6079bad5 / 0x6079bb4a | (); `[],4`. Open/close a draw batch. Bracket flag **0x61fa90d4** (1 open). A second Start or an End without Start logs "cw_drawOsd…() gets called twice!!" and carries on |
| 0x11104 | setOsdOrder | 0x6079bbbe | d0 top, d1 middle, a0 bottom (sdk usage "top middle bottom") |
| 0x11106 | drawDot | 0x6079a01f | a0 = request (below), `[d2,d3,a2],52` |
| 0x11107 | drawLine | 0x6079a1e0 | a0 = request, `[d2,d3,a2],56` |
| 0x11108 | drawRect | 0x6079a2b3 | a0 = request, `[d2,d3,a2],60` |
| 0x11109 | drawFont | 0x6079a0e6 | a0 = request (+24..27 four colour indices, +28 glyph pointer), `[d2,d3,a2,a3],68` |
| 0x1110a | drawBitmap | 0x60799f3f | a0 = request |
| 0x1110b | copyFrame | 0x60799e64 | a0 src VRAM_INFO*, a1 dst |
| 0x1110c | copyAreaBlock | 0x60799d3c | request |
| 0x1110d | customDisplay | 0x6079b068 | – |
| 0x1110e | updateDisplay | 0x6079a69d | a0 = present descriptor (three plane VRAM pointers, 0 = plane off); `[d2,d3,a2,a3],184` |
| 0x11110 | setColorPalette | 0x6079a565 | – (callers: GPIInitPlatform, palette commit 0x60d132e6, black-screen util 0x60ea28d7) |
| 0x11111? | setTransparent [I] | 0x6079a60d | follows setColorPalette, same callers |
| 0x11114 | freeVramInfo | 0x6079a395 | a0 VRAM_INFO* |
| 0x11113 | getVramInfo | 0x6079a432 | d0 plane (0..5) → a0 VRAM_INFO* or 0; `[d2,d3,a2],16` |

**VRAM_INFO** (from the sdk getVram printout) [V]: `+0 u32 pData, +4 s8 plane, +8 u16 width, +10 u16 height,
+12/+14 u16 start.x/y, +16/+18 u16 width_new/height_new, +20/+22 u16 start_new.x/y`.

**Draw request** (rect shown; dot/line use the same head) [V]: `+0 VRAM_INFO*, +4 u32 plane kind (u8 from
0x60f95f10[layer]), +8 u16 x, +10 u16 y, +12 u16 w, +14 u16 h, +16 u16 (rect: read, purpose unknown, line width [I]),
+18 u16 colour, +20 u8 colour index, +24 u32 fill (gpi always passes 1)`. Dot: colour index at +14. Line: w/h at
+12/+14, colour at +16/+18.

### 2.3 gpi layer (section 6): the call recipe

Globals [V]:

| Address | What |
|---|---|
| 0x6246aaa8 | VRAM_INFO* table `[layer 0..2][buffer 0..1]` (8 B per layer) |
| 0x6246aac0 | VRAM_INFO* of plane 3 (WORK) |
| 0x61fb2938 | u8 current back-buffer index (0/1) |
| 0x61fb2939 | u8 dirty flag (set by the rect-sync helper, cleared by present) |
| 0x61fb2954 | u16 layer-off mask for present (0x02 layer 0, 0x10 layer 1, 0x100 layer 2); setter 0x60d131db |
| 0x61fb2964/66 | s16 draw offset x/y (gpiSet/Clear/GetDrawOffset 0x60d13a0b / 0x60d13a33 / 0x60d13a52) |
| 0x6246a774 | 3 DCs × 164 B (layers 0..2); 0x6246a960 DC −1 (WORK); 0x6246aa04 DC −2. Getter 0x60d1192f(d0 layer) → a0 |
| 0x60f95f10 | u8[3] layer → plane {1, 2, 0} |
| 0x60f95f2c | u8[3] layer → bpp {4, 8, 4}; stride = 800·bpp/8 (DC+148) |

DC (164 B) [V partial]: +0 u16 layer, +2 u16 800, +4 u16 600, +6 u16 bpp, +36 colour word [I], +72 → layer
descriptor, +76.. function table (copied from a stack template in GPIInitPlatform 0x60d115d4), +148 u16 stride,
+150 u8 2.

DC function table (offset from +76) [V targets; roles from the callees]:

| +off | Entry | Role |
|---|---|---|
| 0 | 0x60d11964 | dot → gpiDrawOsdDot |
| 4 | 0x60d119a2 | h/v line → gpiDrawOsdLine |
| 8 | 0x60d125f0 | sync rect: Start, copy rect front→back (0x60d12adf), End, dirty = 1 |
| 16 | 0x60d11b02 | filled rect → gpiDrawOsdRectangle |
| 20 | 0x60d119f0 | general line (helpers 0x600da830, 0x60d14a3b) [I] |
| 28 | 0x60d1216c | **one character** through the font engine 0x60d15xxx → gpiDrawCharactor; `@` (0x40) goes to the symbol path 0x60d154fa [I args] |
| 36 | 0x60d11b9c | bitmap → gpiDrawBitmap / block copy |
| 48 | 0x60d12745 | read pixel (4/8 bpp) |
| 52 | 0x60d12665 | set palette → setColorPalette/0x6079a60d |
| 60, 64 | 0x60d127b5, 0x60d127e2 | 0x6079a60d call; copy 13 words of DC info out |

gpi primitives (enter with exactly these call frames; arguments past a1 are the caller's (4,sp), (8,sp), …) [V]:

| Function | Entry, frame | Arguments |
|---|---|---|
| gpiDrawOsdDot | 0x60d127f8, `[d2,d3,a2,a3],68` | d0 x, d1 y, a0 VRAM_INFO*, a1 colour; (4) layer |
| gpiDrawOsdLine | 0x60d128c5, `[d2,d3,a2,a3],84` | d0 x, d1 y, a0 VRAM_INFO*, a1 w; (4) h, (8) colour, (12) layer |
| **gpiDrawOsdRectangle** | **0x60d129d0, `[d2,d3,a2,a3],92`** | **d0 x, d1 y, a0 VRAM_INFO*, a1 w; (4) h, (8) colour index, (12) layer**. Filled. Stock clears a layer with (0,0,800,600) at 0x60d116e8 |
| gpiDrawOsdBlockCopy | 0x60d12adf, `…,108` | src/dst VRAM, rect [I order] |
| gpiDrawBitmap | 0x60d12c4b, `…,96` | d0 x, d1 y, a0 VRAM, (4) w, (8) h, (12) data, (20) layer [I: pixel format of data not traced] |
| gpiDrawCharactor | 0x60d12d57, `…,152` | builds the drawFont request in the static 0x6246a74c [I args] |
| gpiUpdateDisplay | 0x60d12f60, `[d2,a2],88` | d0 0 = show buffer `cur`, 1 = show `cur^1` |
| GPISetOsdOrder | 0x60d13180 | d0, d1 layer pair → setOsdOrder |

Clip: x+offset must lie in [0, 800] and y+offset in [0, 600]; otherwise the draw offset is ignored (not the draw).
Overflow is only logged. **Stay inside 800×600 yourself.**

**Minimal recipe: a framing grid on GUI layer L, from inside the GE paint** [V calls, I layer/colour]:

```
vram = *(u32*)(0x6246aaa8 + 8*L + 4*(u8)*0x61fb2938)     ; back buffer of layer L
if (vram == 0) skip
for each grid line:  call 0x60d129d0,[d2,d3,a2,a3],92  with
     d0 x, d1 y, a0 vram, a1 w,  (4,sp) h (1–2 px), (8,sp) colour index, (12,sp) L
```

A text label: either issue one `DC+28` call per character with the layer's DC (needs the font engine's argument
contract, [I]), or draw a small built-in 1-bit font as runs of 1-px rects. The second needs only the verified rect
call. The existing kind-5 label path (FIRMWARE_GUIDE §4) remains the way to change text inside stock widgets.

### 2.4 How a screen is redrawn [V]

1. GE screen manager paint routine (around 0x60d00560–0x60d00670): widget callbacks through the screen object's
   vtable (+164, +160, +680 multi-layer test) draw into the **back buffer** `cur` of each layer.
2. Paint end: **0x60d0658a** (multi-layer: for each flagged layer, 0x60d0fd95 then 0x60d0ed79; then drawOsdEnd) or
   **0x60d06468** (single: 0x60d0ed79, then the dirty-rect copy loop through 0x60d0ed81).
3. **0x60d0ed79** = `call 0x60d125af,[],4; ret [],4` (two callers only: 0x60d06475, 0x60d065d4).
4. **0x60d125af present-if-dirty**: if `0x61fb2939 == 1`: palette commit 0x60d132e6, gpiUpdateDisplay(0),
   `cur ^= 1`, dirty = 0.
5. Dirty rects are then copied from the new front into the new back (DC+8 → 0x60d12adf), so the back starts equal
   to the screen.
6. After updateDisplay, 0x60d139e4 posts GE event 0xa401 (update-display callback) through 0x60d1050a.

The GE runs in a **dynamic task "GUI_TASK"** [V]: created at 0x60cfcee5 (via 0x607a791e, entry 0x60dd5067, stack
16384) → WinMain 0x60cfd311 (message loop). Its priority is changed later ("changeTaskPriorityNormal"); the value
is not traced.

### 2.5 Layers and palette in shooting and live view

- All three OSD planes are composited over the image plane by updateDisplay; a plane is shown unless its bit in the
  0x61fb2954 mask is set [V].
- **Not pinned:** which GUI layer the LV info screen, the stock framing grid (bitmaps 5996–6143, `grid_draw_lookup`
  0x60df72e8) and menus use, and which palette block each layer has in shooting. The palette goes in through
  setColorPalette (0x6079a565) from three places (GPIInitPlatform, the commit 0x60d132e6 at every present, and
  guiUtility::SetBlackScreen 0x60ea28d7); its source pointer was not traced back to a 0x61110a74 block.
- One harmless camera probe settles it (§4.4 P3): from the overlay hook, draw a 40×40 rect of index 1 on each
  layer L = 0, 1, 2 at three positions, then photograph the screen in LV and in a menu.

### 2.6 Widget geometry

Not found. The view "part" tables (e.g. 0x61fc27d0) list draw functions; positions are inside those functions or in
GE layout data. Leads: `GCPanel_*::OnCreate` / `OnUpdateDB` (strings 0x60ff0300..), the "GUIDB" redraw strings in
WinMain, `Shooting::setGridSettingScreenSize` (API name at 0x6024039c, string 0x60a745ad). Tracing one `GCPanel`
OnCreate to its first rect call would give the record layout.

## 3. Card-loaded code: findings

### 3.1 RAM to own

| Candidate | Size | Verdict |
|---|---|---|
| **malloc class 2** (0x60022782, ≤16384 B; pool 0xa1dd8d40–0xa1e85800 = 43 blocks of 0x4040) | 16 KB | **Use.** Returns an uncached address [V]. Taking one block for the whole power-on is 2.3 % of the pool; peak stock use is unknown [I]. malloc failure → no plugin |
| malloc class 1 (≤2048) | 2 KB | Too small, and already carries P (1 KB) and L (2 KB) |
| Loaded image / FF tails / dead EVF tables | – | **No.** Stock never stores into the loaded image, and the one build that did crashed (FIRMWARE_GUIDE §2, §10). Fine for the fixed loader and hook, never for card code |
| Heap P | 1 KB | **Full to +1023** (fields at +1000..+1020). The plugin pointer needs a new home: a tagged word in L (LOOKS block, layout ends near +1425 of 2048, FILM_MENU_V2 §4) or a new proven .bss pad. Claim it in CODE_SPACE_MAP first |

**Executable?** The cached alias `block & ~0x40000000` (0x61dd…) is ordinary RAM. No MMU or execute-protection set-up was
found in main; the only region checker is the bus monitor 0x99700000, disabled after wait(9) [V for the monitor, I
for the absence]. Instruction fetch from
the uncached alias 0xa1dd… is untested [I]. Neither alias has ever been an instruction target in stock.

### 3.2 Cache maintenance

- **CHCTR is at 0x00008070** (16-bit). Stock touches it only for the D-cache [V]:
  - 0x60066fc0: full D-cache write-back + invalidate (clear DCEN 0x0002, wait DCBUSY 0x0008, tag sweeps at
    0x28a00000/0x28a80000 and 0x28900000/0x28980000, memory-controller flush bit 0x10 at 0x98100000 + 0x400·cpu,
    set DCINV 0x0020, set DCEN). Brackets itself with cpu_lock/cpu_unlock.
  - Section 9: 0x6136a7fd (whole D-cache), 0x6136a854 / 0x6136a8fd (ranged, d0 addr, d1 len; >8 KB falls back to
    whole).
- **No stock code invalidates the I-cache** (the 0x8070 sites are 0x60066fc0, section 9 0x6136a7fd–0x6136a923 and
  a register-peek helper at 0x6075eecc; none sets ICINV 0x0010 or clears ICEN 0x0001) [V]. Bit names follow the AM33 CHCTR layout, which the D-cache code matches bit for bit [I
    for the I-cache bits].
- **Why none is needed here [I]:** the loader writes the blob through the uncached alias, so RAM is current; the
  I-cache can hold lines for the block only if that address was fetched as code earlier in the same power-on. Load
  once per power-on, never free the block, never reload into it. The section loader relies on the same property at
  boot (copies through the uncached alias, no I-cache maintenance) [V].
- If a reload is ever wanted: allocate a new block (never execute a freed one) or add an I-cache invalidate built on
  the CHCTR sequence above. The latter has no stock precedent and needs its own camera test.

### 3.3 Earliest safe point after the card is mounted

The **first shutter half-press** chain the looks already use [V, SD_BUNDLES_V2 §3, FILM_MENU_V2]: hook 0x602c805f in
HLS_EVENT; gate = all nine sections loaded, caller is HLS_EVENT, a medium reports MOUNT OK. The plugin load should be
the **last** step of that chain, after BUNDLES.BIN and LOOKS.BIN, so a plugin failure can't affect looks. The
mount-complete path 0x608658f6 runs during boot and stays rejected (SD_BUNDLES_V2 §2).

### 3.4 How our loaders read files [V, FILM_MENU_V2 §4, SD_BUNDLES_V3]

malloc → fopen `C:\EP7MOD\…` "r" → fseek END / ftell (size check) → fseek SET → fread (count check) → fclose →
range checks + CRC-32 → publish (set the magic last) → else free and stay stock. File calls are a blocking RPC to
FILECLBK, fine from HLS_EVENT, never from FILEFGND. Services: fopen 0x60634fbc, fread 0x6063514b, fseek 0x60635243,
ftell 0x606351d9, fclose 0x60634fc5, malloc 0x60022782, free 0x600227b4.

## 4. Recommended design (not built)

### 4.1 Pieces

1. **Overlay hook (firmware, fixed):** 5 bytes at **0x60d0ed79** (`call 0x60d125af,[],4`) → `jmp ov_hook`. ov_hook:
   if the plugin pointer is valid and `0x61fb2939 == 1` (a present is about to happen): if `0x61fa90d4 == 0`, wrap
   the plugin call in drawOsdStart/End; call `overlay(api)`; then replay `call 0x60d125af,[],4` and `jmp 0x60d0ed7e`.
   Miss path = the one stock call. Runs in GUI_TASK from boot, so the miss path must be byte-for-byte stock behaviour
   while no plugin is published (pointer 0 at power-on). Build checks as usual: nothing branches into
   0x60d0ed7a..7d (`tools/ep7_xref.py --short`), emulator compare of the miss path.
2. **Plugin loader (firmware, fixed):** last step of the half-press chain. `PLUGIN.BIN` under `EP7MOD/`:
   - header 32 B: magic `EP7P`, u16 ABI version, u16 flags, u32 build 1100, u32 main SHA-256 prefix, u32 code size
     (≤ 8192), u32 init offset, u32 overlay offset, u32 CRC-32 of the code;
   - checks: size, magic, ABI, build + SHA prefix, offsets inside the code, CRC; any failure → free, stock;
   - copy into a class-2 block, call `init(api, base)` once in HLS_EVENT; init returns 0 to accept;
   - publish the overlay pointer with one aligned 32-bit store, tagged with a magic word written last.
3. **API table (firmware, fixed):** a small table of vetted thunks in our code space (rect, line, back-buffer VRAM
   of layer L, draw-offset get, current screen/mode getters as they get found). Each thunk carries the exact stock
   call frame, so plugins never encode frames or stock addresses, and an address-map change only touches the table.
   Export no file, flash, settings-write or updater calls.
4. **Plugin code:** position-independent (base in a register; `calls` through the API table), no mul/div/setlb in
   paths that return by `retf`, no `fb` opcodes, ≤ 512 B of stack, no blocking calls, bounded work per present.

### 4.2 Ghosting rule

Overlay pixels are drawn at every present into the back buffer, so they survive the dirty-rect copies. They are
erased only where the GE repaints. A plugin that stops drawing (screen change) leaves ghosts in areas the GE doesn't
repaint. Mitigations, in order: draw on a layer the shooting screens don't use (probe P3); draw only while a
proven "LV shooting screen" predicate holds (not found yet); on exit, fill the overlay's own rectangles with index 0
in both buffers.

### 4.3 First slice

Grid-only plugin: four 1-px lines (rule of thirds) on one layer, colour index from the probe. Uses only the
verified rect call. Text comes after the DC+28 contract is traced or with a built-in bitmap font.

### 4.4 Camera probes needed (each harmless, card-gated)

| # | Probe | Answers |
|---|---|---|
| P1 | Plugin = `mov 0x5a,d0; rets` run from the cached alias of a class-2 block; result shown through an existing probe label | Executing from heap works |
| P2 | Same from the uncached alias | Whether the no-cache option exists |
| P3 | ov_hook with a built-in test: 40×40 index-1 rects on layers 0/1/2 | Live layer per screen, palette colour, ghosting behaviour |
| P4 | Time 100 rect calls inside the hook (frame counter on screen) | Cost per present |

## 5. Risks

| Risk | Where | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| Bootloop from the overlay hook | ov_hook runs in GUI_TASK from the first boot paint, before any card access | Low | High (needs the updater to recover) | Pointer is 0 at power-on, so the hook is one load and compare plus the replayed stock call; emulator miss-path compare; same discipline as the current hooks |
| Bootloop from the loader | Half-press chain only | Very low | – | Not on the boot path by construction (§3.3) |
| Bad card file | PLUGIN.BIN torn, old, wrong build | Medium | None if checked | Size/magic/ABI/build/SHA/CRC gate → stock. Only this class of failure is guaranteed to fall back |
| **Valid but buggy plugin** | GUI_TASK or HLS_EVENT | Medium | Crash or hang after the first half-press. Not a bootloop: every boot is stock until the next half-press | No containment exists on this CPU (no MMU). Recovery: delete PLUGIN.BIN on a PC. Ship only reviewed plugins through the Control Panel; keep the ABI small |
| Plugin writes flash | Any arbitrary code can call 0x600c4f35 | Low (malicious or gross bug) | **Brick** | Don't export flash/updater in the API; review plugins; state plainly that a plugin is unrestricted code |
| Stale I-cache | Block re-used for code in one power-on | None by design | Random crash | Load once, never free, never reload (§3.2) |
| Heap starvation | One class-2 block held forever | Low [I] | Stock malloc failure later | Measure free blocks in P1; fall back to no plugin if fewer than N remain |
| Draw batch misuse | Start/End nesting | Low | Log spam, possibly a corrupted batch | Check 0x61fa90d4 before bracketing (§4.1) |
| Watchdog | Long overlay in GUI_TASK | Low | Reset after 30 s (Caduceus limit) | Bounded work per present; P4 timing |
| Ghost overlay | Screen changes | Medium | Cosmetic | §4.2 |
| Wrong layer/palette | Unprobed | High until P3 | Invisible or wrong-colour overlay | P3 before any feature |

**Verdict.** A card-loaded overlay plugin is feasible with one fixed hook (0x60d0ed79), one fixed loader step and a
small API table. The card file can only fall back to stock if it is malformed; a well-formed but buggy plugin can
crash the camera after a half-press, and can brick it only if it calls flash code. Boot never touches the card.
Do P1–P3 before building anything on it.
