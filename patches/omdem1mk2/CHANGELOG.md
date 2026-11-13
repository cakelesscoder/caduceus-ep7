# Changelog — Caduceus for Olympus OM-D E-M1 Mark II

Firmware modification package for the Olympus OM-D E-M1 Mark II (firmware v3.70 / build 3700 / model `0x1250`).
Container update package: `E1259999.BIN` (93,050,944 bytes) installed via `DCOLYMP/` with the **OK** button held during power-on.

---

## v0.4c13 — 2026-11-13 (camera-tested: SCP tile and option row show 65:24 / 21:9 — working)

- Super Control Panel option row: the screen already had the two extra cells, but it reads its icons from one more
  list that still had only the five stock aspects. That list now has 65:24 and 21:9 too.
- v0.4c12 is withdrawn (it changed the option screen on a wrong assumption; never flash it).

## v0.4c12 — 2026-11-13 (WITHDRAWN, never flashed)

- Super Control Panel option row: 65:24 / 21:9 open the camera's general option row, which has room for all seven
  aspects. The aspect-only row it used before draws just five cells. The pixel-size line under the row may no longer
  appear.

## v0.4c12d — 2026-11-13 (diagnostic; camera-tested: both slots blank → the row draws only five cells)

- Test build for the Super Control Panel option row only: the 65:24 slot uses the stock 16:9 icon, and 21:9 shows the
  16:9 icon everywhere. What appears in the two slots tells which part of the drawing still fails. Not for regular use.

## v0.4c11 — 2026-11-13 (camera-tested: SCP tile labels render; option row still empty)

- Super Control Panel tile: 65:24 showed "17:9" (it borrowed the 17:9 label's slot). 65:24 and 21:9 now have their own
  slots and their own labels in the panel's style.
- Super Control Panel option row: the two extra slots now get their values (the row reads a second copy of the aspect
  setting that still listed only the five stock aspects), so they can show the 65:24 / 21:9 icons.

## v0.4c10 — 2026-11-13 (camera-tested: tile shows "17:9", option row still empty; regular menu icons OK)

- Super Control Panel option row (OK on the aspect tile): 65:24 / 21:9 now have icons. The row reads its icons from
  a second table that still listed only the five stock aspects, so the new slots never had an icon to draw. That
  explains every blank from v0.4c5 to v0.4c9d.
- Keeps the v0.4c9 icon lookup and the v0.4c8 AF fix.

## v0.4c9 / v0.4c9d — 2026-11-13 (camera-tested: both still blank)

- Super Control Panel icons for 65:24 / 21:9 no longer depend on changes to the camera's graphics component, which
  never showed any effect on this camera. The firmware's icon lookup now serves the two icons from the main firmware.
  The graphics component is back to stock.
- v0.4c9d: the same, but 21:9 shows the stock 16:9 icon. Flash it only if v0.4c9 is still blank.

## v0.4c8 — 2026-11-13 (camera-tested: AF target selector works; SCP icons still blank)

- Super Control Panel: the 65:24 / 21:9 value cell. The cell looked the value up in a list that had no 65:24 / 21:9
  entry, so it never picked an icon (that is why v0.4c5–c7 stayed blank whatever icon they offered).
- AF target selector and shooting screen: 65:24 / 21:9 use the 16:9 AF layout, point mask, AF frame geometry,
  selected-point check and metering geometry (as the working E-P7 fix does).
- Both checked in the emulator against stock: stock settings behave exactly as before.

## v0.4c7 — 2026-11-13 (camera-tested: SCP still blank, AF cursor still missing)

- AF target selector in 65:24 / 21:9: uses the 4:3 point layout throughout (the camera's own selector code already
  falls back to 4:3 for these values; v0.4c6 mixed in the 16:9 point mask, so no cursor was drawn).
- Super Control Panel: 65:24 tries the new icon with the address form every stock icon uses. 21:9 deliberately shows
  the stock **16:9** icon this time: it tells whether graphics-table edits work on this camera at all.

## v0.4c6 / v0.4c6p — 2026-11-12 (v0.4c6 camera-tested: SCP still blank; AF selector without cursor)

- Super Control Panel: 65:24 and 21:9 were selectable but blank on v0.4c5. The icons now live in free space in the
  main firmware, and the graphics component only gets two pointer changes (nothing is added to it).
- Selected cells show the same white icon (there is no room for the larger green versions).
- v0.4c6p: the same build with stock placeholder icons (16:9 for 65:24, 3:2 for 21:9). Flash it only if v0.4c6 is blank.

## v0.4c5 — 2026-11-12 (camera-tested: regular menu works; Super Control Panel shows 65:24 / 21:9 blank)

- **Real 65:24 and 21:9 icons** in the stock aspect-icon style (white and green/selected), for the Live Control strip,
  the Super Control Panel tables and the info displays. This build also changes the OSD (graphics) component.
- Includes everything in v0.4c4.

## v0.4c4 — 2026-11-12 (not camera-tested)

- Image Aspect detail screen (OK on the menu row): the box shows "65:24" / "21:9" and the size table shows their pixel
  sizes (e.g. Large 5184x1920 / 5184x2224) instead of blank entries.
- Super Control Panel: its icon tables now know 65:24 and 21:9 (they were missing there on v0.4c3).
- Placeholder icons (16:9 / 3:2) as in v0.4c3.

## v0.4c3 — 2026-11-12 (camera-tested: short labels in the menu row; detail screen and SCP incomplete)

- Labels use the ratio: **65:24** and **21:9** (menu value text; no camera strings changed).
- Strip and option list: 65:24 / 21:9 use placeholder icons (the 16:9 icon and the 3:2 icon) because these screens draw
  icons only; on v0.4c1 they were blank. Real 65:24 / 21:9 icons are next.
- Otherwise as v0.4c1 (Panorama/Wide available; v0.4c1 shot a 5184x1920 JPEG on camera).

## v0.4c1 / v0.4c2 — 2026-11-11 (v0.4c1 camera-tested 2026-11-12: Panorama shows in the menu and shoots at 5184x1920)

- **Panorama (65:24) and Wide (21:9) should now appear** in the Shooting Menu and the Super Control Panel / Live Control.
  The real filter was the camera's interlock rules: the aspect rule only knew the values 4:3, 16:9, 3:2, 1:1, 3:4 and 17:9,
  and the menus hide any value the rule rejects. Its value tables now include Panorama and Wide. Shown in the emulator,
  running the camera's own code (stock: 5 options; v0.4c1: 7).
- AF target selector: Panorama and Wide use the 16:9 AF area table (the E-P7 crashed here before the same fix).
- v0.4c1: the strip entries are text ("Panorama", "Wide"); v0.4c2: placeholder icons (16:9 icon for Panorama, 3:2 icon
  for Wide) in case the strip draws icons only. Real XP / 21:9 icons later.
- No debug log. Switch back to 4:3 before powering off while testing.

## v0.4b5 — 2026-11-11 (not camera-tested)

- The camera-tested v0.3b5 + aspect ratios (Panorama 65:24 / Wide 21:9). **No debug log.**

## v0.3b5r — 2026-11-11

- Rebuild of the camera-tested v0.3b5 without the debug log, byte-identical to it (patched SHA-256 72552d29…). Use it
  to get a working camera back.

## Debug log — pulled (2026-11-11)

- v0.4b3 no longer restarted, but broke the shutter: a CARD error at every half-press with DEBUG.TXT, and a live-view
  reset with nothing captured without it. Its hook point runs for more than the half-press and it lacks the task check
  the E-P7 and OM-3 loggers use. **v0.4b1–v0.4b4 are withdrawn.** It comes back after it is moved and gated.

---

## v0.4b4 — 2026-11-11 (WITHDRAWN: contains the debug log)

- v0.4b3 + the v0.4 aspect patch (Panorama 65:24 / Wide 21:9). Flash only after v0.4b3 works.

## v0.4b3 — 2026-11-11 (WITHDRAWN: CARD error / no capture)

- **Fixes the restart when taking a picture (third fault).** The debug log's hook jumped one byte before its code, onto a
  `break` instruction, in v0.4, v0.4b1 and v0.4b2. The jump now lands on the code; the release check now verifies
  every hook's target.
- Otherwise identical to v0.4b1.

---

## v0.4b2 — 2026-11-11 (WITHDRAWN: hook still lands on a break; use v0.4b4)

- v0.4b1 + the v0.4 aspect patch (Panorama 65:24 / Wide 21:9), unchanged. Flash only after v0.4b1 works.
- Aspect is untested on camera: v0.4 restarted at the shutter before anyone could check it. No static reason found for the
  missing menu entries (validator, menu and SCP records are patched as on the E-P7, all in loaded memory).

## v0.4b1 — 2026-11-11 (WITHDRAWN: still restarts at the shutter; use v0.4b3)

- Fixed two of the three faults behind the restart (it still restarted: see v0.4b3). The debug logger returned to a wrong address on
  every shutter event (its call and ret frames did not match), and it wrote its flags into the firmware image in memory,
  which has crashed a camera before. Rewritten: flags in the shared heap block P, matched frames, waits for a mounted card.
- Debug log: put `DEBUG.TXT` in `EM1MOD`, half-press; `EM1MOD/CADLOG.TXT` (1,024 bytes) shows the build, report number,
  card, P state, look index/page/strength, and the first 8 bytes of `LOOKS.BIN`.
- Aspect left out on purpose (one feature group per flash).
- Build audit now rejects stores into the firmware image and mismatched call/ret frames.

---

## v0.4 — 2026-11-11 (WITHDRAWN: restarts the camera at the shutter; use v0.4b1)

- **Expanded Aspect Ratios: X-Pan (65:24) & Ultra-Wide (21:9)**:
  - Repurposed hidden internal aspect ratios (`id 6` and `id 7`) to provide Hasselblad X-Pan equivalent **65:24** and cinematic **21:9**.
  - **Setting 270 Validator**: Record at `0x604f07cc` expanded from 5 entries `[1, 3, 2, 4, 9]` to 7 entries `[1, 3, 2, 4, 9, 6, 7]`.
  - **Shooting Menu Integration**: Main menu Image Aspect descriptor (`0x6124ea1c`) expanded to 8 options with localized text labels: **Panorama** (String ID 241) and **Wide** (String ID 2661).
  - **Super Control Panel (SCP) & Live Control**: Option strip descriptor (`0x6124aea4`) expanded to 7 selectable options in both white and green strips.
  - **Capture & Sensor Pipeline**: All 46 per-aspect size and geometry tables updated across the firmware image. Split capture tables (Width `0x60556cc4`, Height `0x60556e62`) updated across all 23 size classes.
  - **ORF AspectFrame**: Jump table at `0x60556c24` redirects IDs 6 and 7 to the width-limited framing handler (`0x604240b1`).
  - **Live View Framing & Rec-View**: CapThr switches S7 (`0x60b2f8ec`), S8 (`0x60b2f918`), S9 (`0x60b2f944`), S10 (`0x60b4cedc`), and S_alt (`0x60b3bd68`) redirected to custom Section 1 case blocks rendering $640 \times 240$ (65:24) and $640 \times 272$ (21:9).
  - **Pixel Readout**: Pixel-dimension readout routine (`0x60f13985`) repointed to an expanded 7-column dimensions table.
  - **Cave Residency**: All aspect code and tables live safely in Section 1 free space (`0x60257580..0x602577f2`, 626 of 640 bytes).
  - Opcode audit verified: 0 `0xFB` opcodes, 0 mul/div, 0 hardware loops.

---

## v0.3b5 — 2026-11-11

- **Hardware Image-Request Tone Pipeline**:
  - Highlights, Midtones, and Shadows write directly to the image request records read by the hardware pipeline: Highlights (384), Midtones (692), Shadows (383), matching the E-P7 engine architecture.
  - Tone adjustments confirmed functional on-camera in both live view and saved JPEG stills ($\pm 7 / \pm 7$: highlights $\pm 14$, shadows $\pm 24$).
- **Diagnostic Debug Logger (`debug_log`)**, added later to the rebuilt v0.3b5 folder. **Correction:** this entry called it
  non-invasive and inert without `DEBUG.TXT`. It was not: it crashed the camera at every shutter event, with or
  without the file (mismatched call/ret frames, stores into the firmware image). The v0.3b5 tone work is not affected;
  the fix is v0.4b1.

---

## v0.3b4 — 2026-11-11

- **Velvia & Film Profiles Confirmed on Camera**:
  - Captured JPEGs confirmed matching panel preview (saturated blues, punchy red ground, deepened shadows, neutral sky).
  - Look colour and tone processing verified reaching stills, not just the live view display.
- **Strength Adjustment Page**:
  - Added new Page 3 to Color Creator: allows scaling look intensity ($\times 1$, $\times 1.5$, $\times 2$, $\times 3$) across saturation, hue, and luminance.
- **Live View Refresh Trigger**:
  - Re-triggers colour stage recalculation after manual wheel adjustments by re-issuing vividness (setting 618), eliminating previous need to switch looks back and forth.

---

## v0.3b3 — 2026-11-11

- **Subtle Rendering & Tone Sync**:
  - Corrected tone write settings for live view vs image request.
  - Resolved issue where Chroma and Luminance slider modifications did not visibly affect live view without re-triggering mode refreshes.

---

## v0.3b2 — 2026-11-11

- **Section 5 Relocation (Memory Boundary Fix)**:
  - Relocated built-in looks table into Section 5 tail (`0x60bc8150`) after discovering Section 6 is loaded only up to `0x612e7000` (not `0x61300000`).
  - Added automated section residency verification tool (`omdem1mk2_check_loaded.py`) to prevent any unmapped flash memory edits.
- **Sticky Monochrome Fix**:
  - Fixed bug where picking a B&W look (vividness $-4$) left all subsequent colour looks stuck in monochrome. Colour looks now explicitly restore proper vividness baselines.

---

## v0.3b1 — 2026-11-11

- **TruePic VIII COLOR Hardware Pipeline Hook**:
  - Directly hooked the TruePic VIII 12-sector hardware colour engine (`0x603ec642` / `0x603ec82c`) inside Color Creator mode.
  - Bypassed camera's stock limitation of a single uniform hue and vividness, feeding 12 independent sector saturations, per-sector hue shifts, and lightness offsets.
- **Unified Look File Format**:
  - Switched `EM1MOD/LOOKS.BIN` to standard E-P7 v3 look format (`EP7B`, 64 + 64 bytes per look, up to 32 looks).
  - Cross-compatible with E-P7 Control Panel web exports and custom recipe packs.

---

## v0.2b2 — 2026-11-10

- **Heap & Allocator Safety**:
  - Corrected heap `free()` call to the camera's primary OS allocator pool (`0x6002323d` instead of `0x600232d9`).
  - Fixed caller-saved register clobbering in SD card loader CRC calculation routine.
- **String Sanitization**:
  - Added strict printable ASCII validation to look names to prevent garbage character rendering on OSD banners.

---

## v0.2b1 — 2026-11-10

- **Isolated Shared Heap Block P**:
  - Fixed critical state memory corruption: moved patch state (SD card loaded flag, look index, active page) out of stock callback ring (`0x621e2f74`) into an isolated heap block P referenced via compiler padding pointer (`0x621e24ae`).
- **Register Preservation in Dial Loops**:
  - Arrow key event handlers updated to preserve `d2` and `d3`, preventing disruption of the stock dial loop detent counters.
- **Vividness Range Clamping**:
  - Clamped monochrome look vividness writes to $-4$ to adhere to camera's $-4..+3$ validator limits.

---

## v0.1 — 2026-11-06

- **Initial Port of Caduceus to OM-D E-M1 Mark II**:
  - **Video Recording Limits (`rec_limit`)**: Patched duration check at `0x603549d7` and `0x603549dc` from 29 min (1740s) / 2 hours (7200s) to 9 hours (32400s).
  - **Focus Stacking Unlock (`focus_stacking`)**: Patched `0x60656a4a` (`bne` $\to$ `nop nop`), removing the PRO lens whitelist and allowing automated focus stacking with any autofocus lens (Olympus non-PRO, Panasonic, Sigma).
  - **SD Card Look Loader (`sd_loader`)**: Added initial Section 2 cave routine (`0x60580200`) hooked into shutter half-press event to load custom looks from SD card (`C:\EM1MOD\LOOKS.BIN` or `D:\EM1MOD\LOOKS.BIN`).
  - **Color Creator Look Browser (`color_creator_wheel`)**: Initial implementation of look browser interface overlaid on the camera's native Live View Color Creator screen.

