# Changelog

Caduceus firmware patches for the Olympus PEN E-P7 (firmware 1.1). Releases from v0.25 are betas; earlier ones
were early-development pre-releases. Use at your own risk (see the README).

## Control Panel — 2026-11-13 (redesign and mood packs)

- **New look:** frosted-glass panels over a blurred copy of the sample photo, one gold accent, Inter type, light mode that follows your system.
- **Mood packs:** small themed collections next to the Standard libraries: Tokyo Nights, Tokyo Days, Autumn, Summer, Winter and Film Noir, each with suggested starter slots. See `docs/PACKS.md`.
- **Preset packs browser and drag and drop:** browse every pack with thumbnails, click a look to preview it, and drag it onto a COLOR/MONO starter slot or into your list (or use + and Slot…, keyboard and touch work too). **Load whole pack** adds a pack and its slots in one undoable step.

## Control Panel (with v0.32)

- **Preset look packs:** pick **Standard 1.1** (new default: split tone where the real stock has a shadow/highlight cast, halation only on rem-jet-free film) or **Standard 1.0** (the previous library, unchanged) from **New**, or mix looks from several packs with **+ Add look › From a preset pack…**. Looks get a **Split tone** editor and the preview shows it. Saved packs and share links work as before. See `docs/PACKS.md`.

## v0.33 — 2026-11-14 (beta)

- **Grain without tiling:** v0.32b's faster grain laid its noise down in 64-pixel blocks, and at High a faint repeating pattern could show, most when a photo is viewed zoomed out. The grain now uses the same noise pattern as v0.32a and earlier again, with no blocks and no repeats, and the same strength at Low, Med and High. It keeps what made v0.32b stable: no shared camera memory during a shot and short interrupt holds. A photo with Grain saves about 1.85 times faster than on v0.32a (v0.32b was 2.4 times).
- **Halation is faster and looks identical:** the tinted glow does 48–74 % less work per photo (most on night scenes with a few lights), with far fewer cache flushes, and the result is the same picture, byte for byte. With a `LOOKS.BIN` on the card it no longer takes any of the camera's shared memory blocks.
- **Clean start after a crash:** the camera's memory survives a crash and restart, and Caduceus could mistake leftovers from before the crash for freshly loaded looks. That could leave the Film page, split tone or halation working on memory they no longer owned until the battery was pulled. The camera now starts clean on the first half-press after any restart.
- **Crash record:** if the camera ever freezes and restarts by itself, the next half-press writes a small file, `EP7MOD/CRASH.BIN`, with what the camera was doing. Nothing else changes and normal shooting is untouched. If you report a crash, please attach that file; `tools/ep7_crash.py` reads it. See `docs/CRASH_LOG.md`.
- Firmware screen shows `Caduceus: 0.33`. Card files unchanged from v0.32.

## v0.32b — 2026-11-14 (beta)

- **Grain no longer freezes the camera, and saves faster:** the grain code is rewritten. It does about 2.4 times less work per photo (6 instructions per pixel instead of 15), so a photo with Grain saves in well under half the time. It no longer takes any of the camera's shared memory blocks during a shot, and each step that briefly holds the camera's interrupts is less than half as long. On v0.32a a shot with Grain could occasionally freeze the camera and restart it, losing that photo; this has not come back in testing on an E-P7. The grain looks the same: Low, Med and High are within 1 % of the old strength, and the pattern is still different on every photo.
- **Chinese labels, reviewed wording ([#46](https://github.com/cakelesscoder/caduceus-ep7/issues/46)):** Extras is 更多设置, Blacks / Whites are 黑色色阶 / 白色色阶, Glow is 柔和, and the split-tone sectors read 阴影色调 / 阴影强度 / 高光色调 / 高光强度. Thanks to Steven-Yao for checking them.
- Firmware screen shows `Caduceus: 0.32b`. Card files unchanged from v0.32.

## v0.32a — 2026-11-13 (beta)

- **Fewer freezes with grain:** split toning no longer holds one of the camera's shared memory blocks; with a `LOOKS.BIN` on the card it keeps its curves in spare room inside the looks buffer. On v0.32, a profile with split tone plus Grain could occasionally leave the keys (INFO, OK) unresponsive after a shot until a restart. Heavy effect stacks (Grain + Halo + strong glow) can still very occasionally stall the camera; see the README's Quick answers.
- Firmware screen shows `Caduceus: 0.32a`. Card files unchanged from v0.32.

## v0.32 — 2026-11-13 (beta)

- **Split toning on COLOR1–4:** each COLOR profile can tint its shadows and its highlights separately, with one of the colour wheel's 12 colours and a strength from −5 to +5 each (for example teal shadows with orange highlights). It uses the same formula and numbers as Caduceus for OM-3, so a look tints the same way on both cameras and in the Control Panel preview. It shows in live view and in photos. Movie, AP colour, MONO and stock profiles are unchanged. Set it in the Control Panel (choose **v0.32 or later** on the Export page): it goes into `BUNDLES.BIN` and into `LOOKS.BIN`, so picking a film on the camera's Film page sets that film's split tone, and a film without one clears it. **Own** and **Stock** bring back the split the profile had before. Look names are now at most 12 characters (the panel shortens longer ones), because `LOOKS.BIN` keeps the split where the end of the name was. Older firmware rejects a `BUNDLES.BIN` or `LOOKS.BIN` that has split toning, so pick your firmware on the Export page.
- **Extras split into two pages:** press INFO past Light for **Effects** (1 Grain, 2 Glow/Clarity, 3 Halo, 4 Art, 5 Sharp, 6 NR, 7 VigFix), then INFO again for **Colour & Light** (1 WB amber/blue, 2 WB green/magenta, 3 Blacks, 4 Whites, 5 Shadow tone colour, 6 Shadow tone strength, 7 Highlight tone colour, 8 Highlight tone strength). Split toning can now be set on the camera: pick a colour (Off or one of 12) and the strength jumps to +3, then adjust −5..+5 (negative gives the opposite tint). Every setting keeps its place in the card files, so bundles, looks and share codes still work. Movie and AP keep their "stills only" locks, and split reads `Split: COLOR 1-4` there.
- **Simplified Chinese labels ([#46](https://github.com/cakelesscoder/caduceus-ep7/issues/46)):** with the camera's language set to 简体中文, Caduceus's own editor labels (page names, Extras sectors, the Colour Profile page label) show in Chinese, using the camera's own Chinese font. In every other language they're unchanged. Mono preset names and a few menu rows stay English. Translations welcome in #46 (`docs/I18N_ZH.md`).
- **Framing lines in live view:** with **Displayed Grid** set to the diagonal grid, the 16:9 view (and movie) shows frame lines for Panorama 65:24 (solid) and Wide 21:9 (dashed). In the Panorama (XPan) aspect, any grid setting now shows a rule-of-thirds grid inside the panorama frame; before, no grid showed. Set Displayed Grid to Off to hide them. The Wide (21:9) still aspect still has no grid.
- **Colour Profile page label ([#41](https://github.com/cakelesscoder/caduceus-ep7/issues/41)):** the full Colour Profile page now shows the same page and look name in its guide line as the wheel opened from the Super Control Panel.
- Firmware screen shows `Caduceus: 0.32`.

## v0.31d — 2026-11-12 (beta)

- **Look name in the photo's EXIF:** JPEGs taken on a COLOR1–4 look carry its name in ImageDescription (`Gold 200`) and UserComment (`Caduceus Gold 200`), the same layout as Caduceus for OM-3, so photos can be sorted by look in any EXIF tool. A `*` after the name (`Gold 200*`) means the look was changed on the camera after it was picked, the same as the `*` on the Film page. MONO and stock shots keep the camera's blank fields.
- Firmware screen shows `Caduceus: 0.31d`.

## v0.31c — 2026-11-10 (beta)

- **Effects off in Movie and AP colour:** on the Movie and AP colour wheels, Grain, Glow/Clarity, Art and Halo are locked and read "…: stills". AP shots never apply them, whatever the slot holds (they could crash the camera in AP modes). Movie already left them out. Stills COLOR1–4 are unchanged.
- **Wheel cursor fixed on the Movie and AP wheels:** the selection line now moves with the cursor, as on COLOR1–4.
- **Movie picture mode Muted now reads `8-BIT LOG`**, since it records Caduceus's log curve. Stills Muted is unchanged.
- Firmware screen shows `Caduceus: 0.31c`.

## v0.31b — 2026-11-10 (beta)

- **Bright scenes with grain and halation no longer crash.** v0.31a's pauses during processing let other camera tasks run halfway through a photo, and on bright daylight frames that crashed the camera about 2 s after the shot. The pauses are gone: grain and halation run uninterrupted as in v0.31, and the camera's watchdog limit is raised from 10 s to 30 s so long saves can't trip it. Very bright, overexposed frames skip halation and save quicker.
- Keeps v0.31a's look-loading retry. The halation look is unchanged from v0.31.
- Firmware screen shows `Caduceus: 0.31b`.

## v0.31a — 2026-11-10 (beta)

- **No more restarts on heavy shots:** a photo with strong grain and halation could take long enough that the camera's watchdog restarted it. Grain and halation now pause briefly while they work, so this can't happen; it adds about 0.2 s per photo. The halation look is unchanged from v0.31.
- **Looks always load:** if the first load of your looks failed (for example right after a crash), the camera stayed stock until you switched it off and on. It now tries again on the next half-presses.
- Firmware screen shows `Caduceus: 0.31a`.

## v0.31 — 2026-11-10 (beta)

- **Tinted halation:** a red/orange glow around bright lights, like CineStill and other films without an anti-halation layer. Set it per profile on Extras sector 11 **Halo**: Off / Low / Med / High. Picking a look sets its own halo (CineStill 800T Med; CineStill 50D, Vision3 500T, Portra 400, Polaroid and Gold 200 Low), and you can change it after. White cores stay white, and grain sits on top. It adds about 1–2 s to saving a night photo with lights, and very bright frames (lots of sky) skip it so they save at normal speed. Stills only.
- **Rec View with bloom and clarity looks fixed ([#19](https://github.com/cakelesscoder/caduceus-ep7/issues/19)):** the review image no longer goes black while the effect processes. It shows the shot (without the glow) for the whole Rec View time, and the saved photo still has the effect.
- **Grain fix:** a safety check in the grain code read the wrong record and never ran. It now keeps grain's extra pass off the small preview images when a look has an Art Effect. Grain on your photos is unchanged.
- **Live ND is safe in every drive mode:** ND3 and ND4 take one frame per press (Single or Sequential), and can no longer stall or crash. One-press capture is parked for now.
- **Control Panel:** looks get **Halo** and **Halo colour** (Red / Amber), and the Export page gets per-profile **Sharp** and **Halo**. Choose the v0.31 firmware option there. Older share codes and packs still load.
- `LOOKS.BIN` updated with the new halos; the builder copies it to the card as usual, and your `BUNDLES.BIN`, `MOVIE.BIN` and `AP.BIN` are kept.
- Firmware screen shows `Caduceus: 0.31`.

## v0.30 — 2026-11-09 (beta)

- **AP Custom colour:** on the AP dial position, picture mode Vivid becomes its own colour profile, as Movie colour does for movies, saved in `EP7MOD/AP.BIN`. Half-press once after switching on; Vivid then reads `INFO Custom`. On the Super Control Panel, highlight the picture-mode cell on Vivid and press **INFO** (or press OK on the Saturation cell) to open the full colour wheel; INFO in Live Control works too. Use it with Multiple Exposure, Live Composite and the other AP modes.
- **Live ND (ND3 / ND4), early alpha:** with the dial on AP and Multiple Exposure selected, Shooting Menu 2 › Multiple Exposure › Number of Frames is no longer greyed out and offers Off / 2f / **ND3** / **ND4**. ND3 and ND4 average 3 or 4 frames (about 1.6 and 2 stops) at normal brightness, with less noise. Set drive to **Sequential H** and hold the shutter to take all frames with one press. In Sequential L it can stop after 2 frames (release and press again); in Single drive it takes one press per frame. 2f and Off work as stock. Capture is still picky (frames can be missed or the burst can stop early); it is being worked on.
- **Lowest S/S Setting:** a new row in Custom Menu D1, under ISO-Auto Set, opens the camera's own hidden Lowest S/S picker: Auto (stock) or 1/1.3 to 1/8000. In P and A, the camera raises ISO before going slower than that speed.
- **Fix:** after some restarts the Movie slot could fail to load until a battery pull. Both slots now load on the first half-press every time.
- Firmware screen shows `Caduceus: 0.30`.

## v0.29a — 2026-11-08 (beta)

- **Fewer presses to change film:** the colour wheel now opens on **Film**, and INFO goes Film → Saturation → Saturation·All → Hue → Light → Extras. If you close it on Saturation·All, it reopens there. Without `LOOKS.BIN` it behaves as before. The Movie wheel uses the same order.
- **See the film on the wheel:** on the Film page, the wheel's shape now follows each film's saturation pattern as you turn through them, in stills as it already did in movie.
- Firmware screen shows `Caduceus: 0.29a`. The builder now treats letter versions (v0.29a) as newer than v0.29.

## v0.29 — 2026-11-08 (beta)

- **Arrow keys you can set:** Custom Menu › Button Function now shows **Right Fn** and the down-arrow row (Drive). Choose Flash, Drive, Exp comp, MF, ISO/WB, WB/ISO, Peaking, Level, Tele-converter, RAW, Electronic Zoom, touch lock, Accessories or Off. The defaults are stock (right = Flash, down = Drive). Up and left stay fixed.
- **More REC (◉) and Fn functions:** AF Home, RAW, ISO/WB, WB/ISO, Level, HDR, BKT, Test picture, Keystone, IS mode and Multi Function.
- **Panorama (XPan) and Wide (21:9) fixes ([#23](https://github.com/cakelesscoder/caduceus-ep7/issues/23)):** the AF target selector no longer crashes and has the right grid; AF points, metering marks and iAuto/tracking work; the aspect stays set after a reboot; and the Super Control Panel value cell shows `XP` / `21:9` instead of 4:3. Thanks to flickering-star, whose 65:24 work pointed the way. The composition grid overlay isn't fixed yet.
- Before going back to older firmware, set the arrow rows back to stock (old firmware can't show the new choices; they still work).
- Firmware screen shows `Caduceus: 0.29`.

## v0.28 — 2026-11-08 (beta)

- **Sharpening off per profile:** Extras sector 10 **Sharp** Camera / Off. Off turns the camera's sharpening fully off for that COLOR profile, for stills and the Movie profile. Sharpness −2 still leaves about 40% of it. Set by you, never by a look, Own, Stock or a reset.
- **Grain is back to the finer, gentler grain** tested before v0.27. v0.27's coarser grain was too strong.
- `BUNDLES.BIN` or `MOVIE.BIN` with Sharp Off is rejected by v0.27 and older: set Sharp back to Camera before going back.
- The Control Panel doesn't set Sharp yet: a `BUNDLES.BIN` exported from it has Sharp at Camera on every profile.
- Firmware screen shows `Caduceus: 0.28`.

Sharpening off was checked on an E-P7 (the setting saves and the photos come out softer), but not yet in a controlled side-by-side with focus locked, so reports are welcome. Whether it reaches movie recordings isn't confirmed yet.

## v0.27 — 2026-11-08 (beta)

- **Film grain on colour photos:** Extras sector 1 **Grain** Off / Low / Med / High, per COLOR profile. It's added to the photo's brightness after development, so colour is untouched. Stills only: not in live view, movies, the Movie slot or Monochrome.
- **Saving with grain takes a few seconds longer** (about 3–5 s per photo in tests), and burst is slow with grain on. Grain Off is as fast as v0.26. Glow, Clarity and Art Effect looks still work, and grain is added after them.
- **NR moves to Extras sector 9**, with the same values and your saved settings kept.
- **Grain and NR are yours:** picking a look, Own, Stock or a reset never changes them. A look's NR in `LOOKS.BIN` is ignored.
- **Control Panel:** Grain and NR are set for each COLOR profile, not in a look. Choose "v0.27 or later" in the firmware selector to export Grain.
- `BUNDLES.BIN` or `MOVIE.BIN` with Grain set is rejected by v0.26 and older: set Grain to Off before going back.
- Firmware screen shows `Caduceus: 0.27`.

The grain method follows androidfanman's [Caduceus for OM-3](https://github.com/androidfanman/caduceus-om3). Grain was camera-tested on an E-P7 at the earlier, finer strength; this release ships coarser, stronger grain that hasn't been shot yet, so reports on how it looks are welcome.

## v0.26 — 2026-11-07 (beta)

Flashed and used on an E-P7. **Reports wanted:** long recordings haven't been tested yet, see below.

- **Movie colour:** movie picture mode Vivid becomes its own colour profile, with the same pages as the stills wheel, separate from COLOR1-4 and stored in the new `EP7MOD/MOVIE.BIN`.
  1. Half-press the shutter once after switching on. This loads the profile, and clips shot before it are stock Vivid.
  2. In movie mode, select Vivid in Live Control (the strip up the side of the screen, not the Super Control Panel).
  3. Press **INFO** to open the wheel. Once loaded, Vivid's name reads `INFO Custom` in movie mode; stills Vivid stays Vivid.
  - OK saves and stays on the Movie profile. With it loaded, a button assigned directly to Color Creator may not switch movie mode to it; the Live Control strip should still work.
  - Glow and Art Effects are off in movies. Muted still gives log. Without `MOVIE.BIN`, movie Vivid is stock Vivid.
- **Vertical video:** clips shot in portrait or upside down record their rotation, so they no longer import sideways. A clip keeps the rotation the camera had when recording started.
- **Card files:** add `EP7MOD/MOVIE.BIN` and keep your `BUNDLES.BIN`. The builder's card copy leaves an existing `MOVIE.BIN` alone.
- Firmware screen shows `Caduceus: 0.26`.

**Not tested yet:** recordings of 20+ minutes in 4K, chapter splits, and players other than ffmpeg's reading of the rotation. The Control Panel can't export `MOVIE.BIN` yet, so edit the Movie profile on the camera.

**Known issues:** the Super Control Panel value cell still shows 4:3 on Panorama and Wide, and a clip started before the first half-press is stock Vivid.

## Control Panel — 2026-11-06

- **OM-3 export:** set your camera in the setup pop-up (the **Camera** button later), and Export translates your looks to `OM3MOD/LOOKS.BIN` and `NAMES.BIN` for [Caduceus for OM-3](https://github.com/androidfanman/caduceus-om3). It shows which looks go where and what changed. The card's OM-3 `LOOKS.BIN` and OM-3 share links open here too.
- **The editor adapts to your camera:** slider ranges, Art Effects, glow colour, monochrome, lens correction and the preview follow the selected camera, and the OM-3 gains Contrast, Sharpness and Shading sliders. A wider value from another camera is kept until you move that slider.
- **About button:** what Caduceus is, who to go to for each camera, and credits.
- Translator and name renderer by androidfanman. Not yet tried on an OM-3.
- The setup pop-up appears once more for existing users, to ask for the camera.

## v0.25 — 2026-11-06 (beta)

First beta release. E-M10 IV firmware is in development and needs a volunteer to test it and report issues ([issue #21](https://github.com/cakelesscoder/caduceus-ep7/issues/21)).

Flashed and used on an E-P7. **Reports wanted:** whether the vignette change alters photos hasn't been confirmed yet ([how to test](README.md#vignette-correction-reports-wanted)).
NR is confirmed in each photo's recorded settings; a side-by-side pixel comparison is still to do.

- **`XP` and `21:9` icons:** the Super Control Panel option strip shows them for Panorama and Wide. They are drawn over four headphone icons the E-P7 appears not to use.
  **Known issue:** the current-value cell in the Super Control Panel still shows the 4:3 icon when either is selected. The setting and the photo are right.
- **Lens vignette correction off by default for looks:** picking a look turns the camera's lens shading correction (Shading Comp.) off for that colour
  profile, without changing the menu setting. A look can keep the correction (Control Panel). Extras sector 8 changes it on the camera: `8 VigFix Off` (natural corners) or
  `8 VigFix Camera` (follow the camera's Shading Comp. setting). It follows a profile switch. Profiles already set up keep following the camera until you pick a look or change sector 8.
  A `BUNDLES.BIN` saved with Shading Off, or a `LOOKS.BIN` with a look that keeps correction, is rejected by v0.24 and older.
- **Look NR now reaches photos:** Extras sector 1 and a look's NR now apply to stills at each shot, and follow a profile switch. v0.22-v0.24
  wrote setting 1334, whose reader is the live-view/movie path, and the camera's stills value is a different setting. Looks no longer change
  a camera setting; if a past look changed your movie Noise Filter, set it again in the menu. Looks with NR Low or Off (for example
  Provia 400) can now look different at high ISO.
- **Control Panel:** a look can keep the lens correction, and a firmware selector (asked on first visit, then the Firmware button) makes card files for your version.
- Firmware screen shows `Caduceus: 0.25`.

## v0.24 — 2026-11-05

- **A Film pick now sets the look's saturation:** picking a look writes its 12 per-colour values to the profile's
  saturation, as it already did for Highlights, Midtones and Shadows. It replaces whatever that profile's saturation was.
  Every colour look now shows its designed saturation for the first time, so strong looks like Velvia will look stronger.
  Own and Stock picks don't change saturation.
- **New `LOOKS.BIN`:** tone records carry saturation as nibbles at +38..43 with marker +44 = 1. **v0.23 and older reject this
  file**, so install it with v0.24. An older `LOOKS.BIN` on v0.24 still works and leaves saturation alone. Control Panel
  exports need v0.24 or later.
- Control Panel preview always shows saturation. Firmware screen shows `Caduceus: 0.24`.

## Looks — 2026-11-05

- **Provia 400 replaces Nostalgic** (same Film-page position), designed from a tripod comparison of real Provia 400X and
  100F slides plus Fujifilm's bulletin and reviews: WB G-3 (magenta-red cast), warm-sector hue toward red, blue hue +1, light
  -1 on red, blue, blue-cyan, green-cyan and yellow-green, -2 on green, tone S-1 M-1 Blacks -1 Whites -3, NR Low, no bloom.
  Saturation +1 warm, +2 blue (applied on a pick from v0.24); set contrast +1 on the camera.
- `releases/v0.23/card/EP7MOD/LOOKS.BIN` rebuilt (SHA256SUMS updated). Card file only, no re-flash.
- Control Panel: a saved, unedited Nostalgic becomes Provia 400 in place; an edited one is kept as your own look.

## Control Panel — 2026-11-04

- **RapidRAW preset export:** a look's *Share* dialog and *Export › RapidRAW presets* save it as a `.rrpreset` for
  RapidRAW, for ORF files or raws from any camera; Export also zips every look as its own preset. The 12-sector colour settings are fitted to
  RapidRAW's 8 HSL bands; tone and contrast go into the luma curve; WB, glow/halation, clarity, vignette and the mono
  filter are mapped as well. An approximation of the camera rendering, not an exact match.
- **Install firmware** button: a step-by-step install guide with links to the latest release and `docs/INSTALL.md`.

## v0.23 — 2026-11-03

- **No more duplicate looks on the Film page:** when a profile was already on a library look, turning the dial
  showed that look twice (its saved copy and the library entry). An unedited copy is now skipped; if you've edited
  the look (`*`), your edited version stays in the cycle so you can get back to it.
- **`Film: ` prefix is back** on the colour Film page, for every name: `Film: Velvia`, `Film: Kodachrome64*`
  (label up to 19 characters).
- Firmware screen shows `Caduceus: 0.23`. Card files (`LOOKS.BIN`) unchanged from v0.22.

## v0.22 — 2026-11-03

- **Noise reduction per look** (replaces colour grain): camera tests showed the camera's grain stages add nothing
  visible to colour photos (the v0.16–v0.21 route and a Monochrome-route probe, both dropped). Extras sector 1 is now
  **NR**: `1 NR Camera` (leave the camera's Noise Filter alone), `1 NR Std`, `1 NR Low`, `1 NR Off` (most texture).
  Set on a look pick and on a sector-1 edit through the stock settings path. The Noise Filter is camera-wide, so it
  stays at the last value when you switch profiles. True film grain is on the roadmap.
- Card values: 0 Global (old cards' "off"), 6 Std (new), 1 Low (old low), 2–5 Off (old medium/high). Library: no
  grain → Global, low → Low, medium/high → Off. Web app: "Noise reduction: Camera / Standard / Low / Off (most texture)"; older packs
  and share codes still load (Standard uses new code prefixes 5/6). Card loaders accept 0..6.
- Firmware screen shows `Caduceus: 0.22`.

## v0.21 — 2026-11-03

- **Five colour grain levels:** a COLOR slot's grain is now Off / 1–5 (Extras sector 1 shows `1 Grain Off`,
  `1 Grain 1` … `1 Grain 5`; the value stops at 0 and 5). Gains 220 / 600 / 1200 / 1500 / 1800: levels 1–3 are the
  old Low / Medium / High, unchanged, so existing cards and looks keep their strength; 4 (heavy) and 5 (extreme) are
  new. MONO grain is stock. The card loaders accept grain 0..5 (a v0.21 look with grain 4/5 is rejected by older
  firmware's loader, which allows 0..3). Web app: grain Off/1–5; share codes for grain 4/5 use new prefixes 3/4,
  every other code is unchanged.
- **Blur Art Effect removed (issue #20):** on a colour profile, Blur could restart the camera without saving the
  photo. Blur is now Off everywhere: the photo path, the live-view preview and Extras sector 5, which now cycles
  Off / Star Light / Pin Hole. A slot that already has Blur saved keeps the byte on the card, but it does nothing and
  shows as Off. Web app: Blur is listed only as a legacy value (Off on v0.21+). docs/ISSUES_19_20.md.
- Firmware screen shows `Caduceus: 0.21`.

**Known issue (all versions):** colour film grain adds no visible grain to full-size colour photos. Camera
measurements (v0.21) show grain 5 and grain off are identical; the grain route used only works on small images.
A fix is on the roadmap.

## v0.20 — 2026-11-02

- **Rear LCD less pink, and adjustable:** the stock LCD has a slight magenta cast. Setup › Monitor Adjust's
  colour slider (−7..+7) is now a **green ↔ magenta** slider for the LCD: 0 (default) adds 8 % green (about two WB
  green fine-tune steps), each step ±2.3 %, so −7 is 8 % more magenta than stock and +7 is 24 % greener than stock.
  The warm/cool setting is gone (one slider, one axis); brightness is unchanged. Data-only change to the LCD
  panel's own registers: photos, movies, HDMI out and the View Assist / log paths are byte-identical to v0.19.
  Build-time sizes: `patches/lcd_tint/build.py --green-pct 8 --span-pct 16`.
- Firmware screen shows `Caduceus: 0.20`.

## v0.20 — 2026-11-02

- **LCD pink cast fixed:** the rear screen's panel colour table sent green lower than red/blue at every Monitor
  Adjust step, giving live view a pink cast. Green is now raised (+8 % at the default).
- **Monitor Adjust colour is now green↔magenta:** Setup › Monitor Adjust's colour slider shifts the LCD from
  magenta to green (about 2.3 % per step; 0 = corrected default). Display only: photos, movies and HDMI are
  unchanged. (The warm/cool screen adjustment is replaced.)
- Firmware screen shows `Caduceus: 0.20`.

## v0.19 — 2026-11-02

- **Blacks and Whites per Colour Profile:** two new tone controls that move the ends of the tone curve, which
  the stock Highlight/Shadow controls never touch. Blacks + lifts the black point (matte, faded), − deepens the
  shadows; Whites − rolls the white point off, + pushes the brightest tones. Set them on the colour editor's
  Extras page, sectors 6 and 7 (−5..+5). Live view shows them.
- Fix (camera): in live view Blacks/Whites kept getting stronger frame by frame. The curve is now bent once per
  stock rebuild and left alone otherwise (JPEGs were already right).
- **Picking a look on the Film page applies its tone:** the look's Blacks/Whites go into the slot and its
  Highlight/Midtone/Shadow become that profile's stock tone settings (shown on the stock tone screen). Own and
  Stock picks leave tone as before. The card LOOKS.BIN carries each colour look's tone (same v3 format; old
  LOOKS.BIN files still load, without tone).
- Needs v0.19 firmware: v0.18 rejects a BUNDLES.BIN that uses Blacks/Whites.
- Look tweaks: Polaroid is punchier (narrow dynamic range), Atrophy's faded blacks toned down (+1), Cuban Neg
  bloom 3.
- Firmware screen shows `Caduceus: 0.19`.
- Caduceus Control Panel: tone sliders (Highlights/Midtones/Shadows/Blacks/Whites), tone in share codes, exports
  the v0.19 `LOOKS.BIN`.

## v0.18 — 2026-11-02

- **Cleaner look names on camera:** the Film page and the mono preset picker show just the look's name
  (`Velvia`, `Velvia*`, `Acros*`) instead of `Film: Velvia`. Long names have more room. `*` still marks a
  look you've modified.
- Firmware screen shows `Caduceus: 0.18`.

## v0.17 — 2026-11-02 (not released separately; included in v0.18)

- **New looks:** **Cuban Neg** (inspired by Osan's "Classic Cuban Neg" Fujifilm recipe; bloom 4) and
  **Atrophy** (inspired by [Gx]Ace's Atrophy pack: decayed, industrial tones).
- **Faux IR:** the "Aerochrome" look is renamed *Faux IR*. The camera's per-colour hue range can't turn green
  foliage red, so it's an infrared-inspired false-colour look rather than true Aerochrome.
- Library changes: Provia and Superia 400 removed (they duplicated the stock profile and Classic Neg).
- An experimental extended hue range (±15) was tried and **reverted**: it blanked the Hue label in the editor.
  v0.17/v0.18 firmware is otherwise identical to v0.16.
- Firmware screen shows the version in its own `Caduceus` row.

## v0.16 — 2026-11-02

- **Stronger colour grain:** Low/Medium/High about 4×/8×/12× stronger (colour profiles only; Monochrome grain
  stays stock).
- **One-press builder:** double-click launchers for Windows, macOS and Linux; can copy straight to the SD card.
- Clearer install and flashing guide.

## v0.15 — 2026-11-02 (first public release)

- Film simulations picked and edited in the camera (Film page in the Colour Profile editor), 29+ looks.
- Look editor pages: Saturation, Hue, Light, Film, Extras (INFO cycles); edits save to the SD card.
- Extras per profile: grain, bloom ↔ clarity, WB shift, Art Effects (Star Light, Pin Hole, Blur).
- Mono film presets (Pan F, Acros, T-Max, SFX, Tri-X, HP5, Delta 3200, Sepia, Selenium, Cyanotype).
- Hidden log video (movie picture mode = Muted), XPan 65:24 and 21:9 stills, longer recording limit,
  live-view preview of looks.

## Tools

- **Caduceus Control Panel** (https://cakelesscoder.github.io/caduceus-ep7/): make, edit and share looks in the
  browser, with short share codes, undo/redo and reset; exports `LOOKS.BIN`.
