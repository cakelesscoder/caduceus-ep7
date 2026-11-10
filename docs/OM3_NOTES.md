# What we learnt from Caduceus for OM-3

[androidfanman/caduceus-om3](https://github.com/androidfanman/caduceus-om3) (Apache-2.0, read at `daa453b`, its v0.20) is a camera-tested OM-3 port in the Caduceus family. Details are in its `docs/DEVELOPER_NOTES.md` and `docs/FORMATS.md`. OM-3 addresses don't apply to the E-P7.

## Open question: hue direction

The two bodies' camera results point opposite ways for a positive hue value, though both write the same native value (`-1000 × UI`):

| Body | Evidence | + moves |
|---|---|---|
| E-P7 | Test 7b: greens +7 gave teal (`WORKLOG.md`). One test | Toward the lower-numbered neighbour (Green → Green-cyan) |
| OM-3 | Its `USING.md` and developer notes: "camera-tested direction" | Toward the higher-numbered neighbour (Yellow → Orange, Blue → Blue-cyan) |

**Left for later.** The Control Panel copies hue numbers across unchanged, as the OM-3 project's own panel does, so a look's hue shifts may go the other way on an OM-3. A fair test needs both cameras shooting the same scene with the same setting. `sim/pipeline.py` also still calls the E-P7 direction unverified.

## Ideas to assess later

These are the OM-3 project's reports. We haven't tested them and nothing here has been added to the E-P7.

- **Code loaded from the card.** Out of firmware space, it puts a relocatable code block at the end of `GUIDES.BIN`, loads it at first half-press and runs it only if a tag matches the exact firmware. Without the file, the hooks behave as stock. This would ease our own code-space limit.
- **Art Effects in live view.** It hooks the gate that maps an Art Effect to job flags only for picture mode ≥ 100, and reports glow and Art Effects showing in live view as camera-tested. That is the likely route for our "preview updates immediately" roadmap item.
- **White Edge and Frame on COLOR photos** are camera-tested there, though we dropped them in v0.15. It also replaces the Frame pictures with its own white ones, generated on the user's computer.
- **Value labels per sector.** The label next to the dial value names the sector and its meaning (`NR Low`, `Clarity`), drawn from 1-bit letters in `LABELS.BIN`.
- **Look names as pictures.** `NAMES.BIN` holds one rendered name per look in the camera's label style.
- **`om-emu`** ([flatpanda/om-emu](https://github.com/flatpanda/om-emu)) drives real UI sessions in emulation, which our harness doesn't do.

## Lessons

- **Where hook code lives matters.** An early test bootlooped, likely because a stage hooked in section 2 called code in section 8, which wasn't loaded yet. Code in sections 1-5 was safe on that pipeline. Reflashing a working build recovered the camera.
- **Colour grain through the MONO route is a dead end there too:** the route is luma-only end to end, with Cb and Cr exactly 128.
- Its stills NR override is the same design as ours, and its pixel comparison is also still to do.

## Look translation (Control Panel)

The OM-3 holds 5 looks for each of COLOR 1-4, in `OM3MOD/LOOKS.BIN` and `NAMES.BIN`. The panel exports the first 20 colour looks in list order.

| Look value | On the OM-3 |
|---|---|
| Hue, Light | Limited to ±5; hue numbers copied as they are (above) |
| WB shift | Limited to ±5 |
| Saturation, tone, NR, glow, clarity, Star Light, Pin Hole | Carried over |
| Contrast, Sharpness | Real settings there, limited to ±2 |
| Vignette | Becomes the camera's Shading |
| Halation | Becomes plain glow; glow colour is dropped |
| Blur | Left out |
| Lens correction choice | Left out (not built on the OM-3 yet) |
| Monochrome looks | Left out (COLOR only) |

`webapp/src/om3.ts` and `om3names.ts` are vendored unchanged; our glue is `webapp/src/targets/om3.ts`. One-look (`op1_`) and bank (`ob1_`) links from the OM-3 panel open here. In the other direction, its panel rejects our version 7 and 8 look codes (looks that keep the lens correction), which it could fix by updating its `sharecode.ts`.

## Update read 2026-11-10 (their `87b3e6f`, v0.26.1; research only, nothing built here)

Read from a fresh clone, as data only: none of its code was run. Since our last reads (`daa453b` for the panel, `41e7e8b` for grain), there have been 184 commits and releases v0.22, v0.24.1, v0.25, v0.26 and v0.26.1 (v0.24 was withdrawn). `[V]` means read here, in their repo or in our E-P7 image. `[I]` means inference. OM-3 camera results are as that project reports them.

### Fast grain (v0.25): Grainy Film's texture, blended by the image processor

**What it is.** It isn't a faster CPU loop: their CPU grain loops (`xb_p1s`, `xb_p2s`) are unchanged since `41e7e8b` `[V]`. COLOR stills with Grain now borrow the **Grainy Film Art Filter's ready-made grain texture**. The image processor blends it in during the normal development pass, so the CPU does nothing per photo. The owner calls it "quick across the board", and it is as fast as no grain. Trail: their `research/NOTES.md`, sections "Grainy Film's grain path" (ft1..ft9) and "v0.25 candidate" (rc1..rc2c); code `firmware/src/xblock.s` `xb_tex`, `xb_wl`, `xb_dev`, `xb_sel2`, `xb_c1e`.

1. **Texture.** `xb_tex` calls the cached texture builder `0x604cd921` with Grainy Film's 6-byte parameter block and gate, and stores the object at job+8324. The stock clean-up frees it. The cache holds 4 objects, and a texture with the same parameters is reused.
2. **Work list.** `xb_wl` hooks the builder's key read. It makes the texture there, because the list is built before the set-up, and answers Grainy Film II's key `0x01020068` for the list lookup only. The job keeps key 11, so the colours stay COLOR's. That list has the development with texture hook `0x604bc0cf` (descriptor to request +780, +12 = 0x0100), then any Art Effect as its own stage-0x0101 pass.
3. **Combiner 1.** `xb_dev` and `xb_sel2` hook both selector calls, at request configuration and inside the combiner set-up, to answer combiner 1.
4. **Back to colour.** `xb_c1e`, at the end of combiner 1's set-up, puts back COLOR's chroma gains (+96 = 0x04000400, +100 = 1024). Grainy Film's own values (1024 / 0) are what make it black and white. It also sets the texture gain (+148: Low 448, Med 832, High 1280) and a Y offset (+180 low half = −0.102 × gain), because the texture isn't zero-mean.

Result: colour is kept (Cb/Cr high-pass < 1), Y high-pass about 10 / 16 / 24 for Low / Med / High, and it works with Shading, Glow / Clarity, Pin Hole and Star. Failures on the way, all freezes or restarts and none a brick:
- texture plus Frame on COLOR's list restarted the camera (ft5);
- texture on the kind-3 conversion pass hung it until a battery pull (ft7, "do not retry");
- Glow + Frame + Grain wrote no picture, and now falls back to CPU grain (rc2c).

**Open bugs on that route:**
- **#18 / roadmap:** RAW+JPEG with grain freezes the camera after the photo. Thought to affect v0.25–v0.26.1. Not fixed.
- **#12:** Glow + grain still shuts the camera down on v0.26.1, per the reporter. The roadmap says it is fixed, but no code change matches that.
- **#16:** Med grain is much stronger with Glow on.

**The E-P7 has the same machinery `[V]`, read statically from our image:**

| Piece | OM-3 | E-P7 1.1 |
|---|---|---|
| Builder key read; Grainy Film I/II keys | `0x604b8d91`; `0x01010068` / `0x01020068` | `0x60357435` (job+11308); **same keys** (cmp at `0x60357436` / `0x6035743e`) |
| List hash table, (key − 11) & 31 | `0x606c957c` | `0x6052200c`; GF I/II → handler **`0x603574e3`** |
| GF list | pre-pass by job+5385 4..8, dev `0x604bc17e` + hook `0x604bc0cf`, tail `0x604b918c` | pre-pass by job+11341 4..8 (`0x60356a4d` / `0x60356a6f`), dev `0x6035a9d2` + hook **`0x6035a959`**, tail `0x603578b6` (`0x6035aafe` / `0x6035ac5c`) |
| Texture attach (hook) | 19 words to request +780 (kind 0) / +96 (kind 3), +12 = 0x0100 | 16 words from (S+14224)+8 to request **+468** / **+84**, bus address from obj+8 + (S+14216 & obj+92), +12 = 0x0100 |
| Texture builder (cache) | `0x604cd921`, gate in set-up near `0x604b998b` | **`0x6036b36a`**, called at `0x603580cd` with the same flag gate and a 6-byte block built at (48..53,sp); result to S+14224 (`0x603580d8`) |
| Combiner 1 set-up | `0x60504b90`: +4 = 0x00200001, +8 = 3822, +92 / +144 = 0x2a0000, +96 = 1024, +100 = 0, +148 = 1024 | `0x603a0198` (bank = base+7364): +4 = 0x00200001, +8 = 3822, then `0x603a0828`: +88 / +132 = 0x2a0000, +92 = d3, +96 = 0, +136 = d3; exit `jmp 0x603a095f` |
| Selector calls | `0x604955f1`, `0x60504b5d` | `0x60339d3c`, `0x603a0165` (GRAIN_PORT §1) |

So the port is plausible, though the bank layout differs: the E-P7's equivalents of +96, +100, +148 and the Y-offset word +180 are **not mapped**. A guess from the shifts is chroma gains near +88..+96 and texture gain near +136, but this needs an emulator run of `0x603a0198` against the default case before any camera build. Our stock MONO grain (combiners 31 / 32) doesn't use this texture `[V]`, which is why it never came up.

**Expected gain on the E-P7 `[I]`:**
- **Grain:** from about 3–5 s per photo to about 0 extra, and burst with grain returns to normal.
- **Grain with halation:** only halation's CPU pass is left: 0.2–0.3 s plain, about 0.6–0.9 s on a night street, 2.2–3.5 s on a dense night scene (HALATION_RED §18). Grain no longer adds to the time the watchdog sees. The h4 yields can stay.
- **Order changes:** grain moves into the development, before the Soft Focus passes and the halation tint.
  - The glow and halo would sit over the grain, so the grain is softened inside halos. The OM-3 saw Y high-pass 20 → 16 with Glow −3.
  - Today the grain goes over the glow.
- **Panel and formats:** no change. Grain stays per-profile (BUNDLES +50, Extras sector 1).

**Look risks `[I]`:**
- **The texture comes from a 4-object cache keyed by its parameters,** so every photo probably gets the same grain pattern. Check two frames for identical grain.
- **Grain size is fixed by Grainy Film's texture.** It is a half-size image in the OM-3 logs, so likely coarser than our full-resolution s3 grain, which the owner chose over r1's coarser grain. Only strength can be tuned.
- **Their roadmap plans "our own grain texture" for colour speckle and size.** On the E-P7 that would mean writing the texture object's buffer through the bus window once, at boot or first use: a one-off CPU cost instead of one per photo.

**Effort `[I]`:** 2–3 agent sessions plus camera rounds. The OM-3 needed about 12 camera builds in one day.
1. Emulator: map combiner 1's bank against the default case. Trace the GF list on a COLOR job with the `0x01020068` lookup and the texture attach (0.5–1 session).
2. t1: plain looks only, one level, our hooks at the builder key read (next to `gc_wl` at `0x6035749f`, so the two must share or chain that site), set-up texture, both selector calls and the combiner-1 exit (1 session, one camera round).
3. Strengths, Y offset and an effect matrix: Glow / halation, Clarity, Star / Pin Hole, Shading, burst, **RAW+JPEG** (0.5–1 session).

Keep CPU grain as the fallback for anything that fails: OM-3 Frame + Glow is the precedent.

**Risk:** a hang, restart or missing picture (battery pull) on combinations not tested, as on the OM-3. No flash or settings writes, so it carries no brick risk beyond the current grain route. **Test RAW+JPEG with our current CPU grain too:** the OM-3 freeze may not be specific to the texture route, and none of our grain or halation camera tests used RAW+JPEG (GRAIN_PORT, ISSUES_19_20).

### Other changes since our notes

| Change (their version, where) | For the E-P7 | Effort / risk |
|---|---|---|
| **Split toning** (v0.26, `st_run` in `editor.s`; `webapp/src/split.ts`): Shadows and Highlights colour (12 wheel colours) and strength −5..5. It bends the job's R/G/B gamma tables at the tone hook's exit; stills and live view | Portable in principle: their tone hook is a port of our `patches/tone_ends` (their NOTES). Needs a look field and a LOOKS.BIN place on our side | 1–2 sessions; low risk (table edit, like tone_ends) |
| **Films in the Picture Mode list, Picture Mode rows, WB grid row** (v0.24.1–v0.25) | OM-3 UI addresses; a big port | Not now |
| **NR High** (v0.23) | The E-P7 has none (their pack writes it as `standard` for us) | – |
| **WB ±7 in LOOKS.BIN** (v0.26.1) | E-P7 already ±7 in the panel | – |
| **20 own film sims** (`webapp/scripts/films.py`, `data/om3films.json`, Apache-2.0, their designs) | Could go in our library, with credit | 0.5 session |
| Lessons: (1) a `call` with no return-address slot overwrote a saved register (`gd_set`, v0.25 fix); (2) calling the settings getter during capture rebooted on Grain High (v0.24 → v0.24.1); (3) 64 KiB of section 6 proven as code space there (GX2) | (1) and (2) are general AM33 and firmware rules worth keeping; (3) is OM-3 only | – |

### Control Panel and formats

- **Their panel reads `op1_` / `ob1_` codes** (`27ae32b`). Our panel keeps importing those and exporting OM-3 files, through the vendored `om3.ts` and glue in `targets/`.
- **Their look JSON has grown** in `webapp/src/pack.ts`: `film_grain` 1..3, `split` {sh_color, sh, hl_color, hl}, `lens_correction`, Sharp −5..+2 in `advice.sharpness`, and NR `grain: 'high'`.
  - **Conflict:** our `parseLook` throws on `grain: 'high'`, so an `op1_` / `ob1_` link with NR High fails to open here.
  - **Lost silently:** `film_grain` and `split`.
  - **Fix on our side:** accept `high` (map to `standard` for the E-P7) and carry `film_grain` / `split` as OM-3-only fields. That keeps one format. `film_grain` conflicts with nothing: E-P7 grain is a profile setting, not a look field.
- **Our vendored `om3.ts` (`daa453b`) writes the v0.20 record.** v0.26.1 still accepts it, because the new bytes +50..+56 are zero. But it drops lens correction (VigFix +50 now exists), Sharp (+52) and split toning, and writes the old ±2 sharpness into +42. Re-vendoring at `87b3e6f` also needs `split.ts`, `om3films.ts` and `data/om3films.json`, and a firmware choice for `profilesBin(bank, fw)`, which defaults to 22 there.

### Licence and credit

Still Apache-2.0: `LICENSE` and `NOTICE` are unchanged since `daa453b` `[V]`, and GitHub reports Apache-2.0. A texture-grain port written in our own code needs a `NOTICE` line next to the existing CPU-grain credit, for example: "The fast colour-grain method (Grainy Film's texture blended in development, combiner 1 with COLOR's chroma gains) follows Caduceus for OM-3 (androidfanman/caduceus-om3, Apache-2.0), firmware/src/xblock.s and research/NOTES.md." Re-vendored panel files keep their source line and extend the existing vendored-files line to the new files. The film sims would be credited as androidfanman's designs. Copy nothing from OM firmware.
