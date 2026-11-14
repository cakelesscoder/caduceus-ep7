# Halation on the OM-D E-M1 Mark II (fw 3.70): port plan

Status: **design, nothing built** (2026-11-13). Source: the E-P7 halation in this repo (`patches/halation`,
`docs/HALATION_RED.md` §14–17, on `patches/bloom` + `patches/grain_cpu` r2). The OM-3 version
(androidfanman/caduceus-om3 v0.28, Apache-2.0, its own code after the E-P7 method) runs on different base firmware; only its
tuning is a candidate for later (h2: u = 255v/(v+K) tables, 3 + 10 two-layer blur, chroma weight from the cell's mean
brightness, gradual daylight fade; credit in NOTICE).

## Owner decisions (2026-11-13)

| Question | Decision |
|---|---|
| Scope | Halation applies **over any film / colour profile** once enabled, not per look |
| Where the setting lives | **A camera control, remembered over power-off** in the camera's own settings memory (one spare stock setting, found and emulator-proven first) |
| Picture modes | **All colour modes**: our looks (Color Creator) and the stock colour modes (Natural, Vivid, Muted, Portrait, i-Enhance, …). Not Monotone, not Art Filters |
| Precedence | **The global setting sets the strength; the glow colour comes from the look** (red / amber / warm / cool, `tint` +45), red when the look has none |

## How "always applied" is guaranteed

1. **One global stage** (Off / Low / Med / High = gmax 0 / 112 / 176 / 240), read at each shot from its own setting. It is
   not in any look slot, so picking a film, a look or a picture mode cannot change or drop it.
2. **The gate is the shot, not the look:** the capture-flag hook adds the Soft Focus flag 0x80 (neutral blend, as on the
   E-P7) when stage ≠ Off **and** the job is an ordinary still of a colour mode. Excluded: the capture kinds the E-P7
   skips for grain (0x2001, 0x2006, 0x1008, 0x1006), Monotone, Art Filters (they keep their own flags), movies, live view.
   If the job already has 0x80 (e.g. a look with bloom), the halation pass runs after that blend as on the E-P7.
3. **Look values are only a fallback for the tint.** The E-P7's "0 = follow the look" stage is not used on this body.
4. **Emulator proof before any camera build** (AGENTS.md): run the flag hook and the pass entry with stage on/off for every
   picture-mode value, every look slot (built-in, card, none), card present / absent, each excluded capture kind, and
   bloom on/off; pass = the 0x80 flag and the pass call happen exactly when the rule above says, stock otherwise. The
   pass itself bit-exact against a Python model (as the OM-3 did).

## What has to exist first (E-P7 layers → E-M1 II)

| Layer | E-M1 II status (2026-11-13, byte search of the E-P7 sites) |
|---|---|
| Soft Focus route (bloom: flag hook, blend setup, combiner 11, callback) | callback `0x60391959`, blend setup `0x60398f5f`, effect selector `0x603f1653` exact; flag hook ≈ `0x604228fc`, Soft Focus entry ≈ `0x6039517c` / `0x60398ee1` (prefix match); combiner 11/12 calls not found by bytes |
| CPU pass route (grain_cpu r2: work-list hook, window / mapper, lock / unlock) | not found by bytes; needs code-shape search |
| Watchdog 10 s → 30 s (E-P7 v0.31b) | sites not found by bytes |
| Spare remembered setting for the stage | to find |
| Code space ~1.8 KB + tables; one malloc ≤ 16 KB per shot | **blocker**: the known free space is used up by the aspect work |
| Camera control | a Halo row/page in the look editor (`color_creator_wheel`) |

## Step 1: code-space probe sp1 (2026-11-13; **camera: S+**)

- Gaps between loaded sections (loader `0x60042b96`, end getter `0x60042b35`, descriptor table `0x60027450`), scanned for
  code that uses an address inside them (`mov imm32` / absolute operands, cached and uncached): `0x605d3000` (8 KB),
  `0x6078f000` (28 KB), **`0x60bc8800..0x60bf1000` (162 KB)** and **`0x612e7000..0x61300000` (100 KB)** are referenced only
  by their section's end word; `0x60580800..` is written at runtime (`0xa05842f8`): not usable. The getter is called only by
  the loader. Base-region 0xFF runs are startup copy/clear ranges (`0x60021111`): not usable.
- sp1 raises **section 5's end word** (`0x60042b6d`) `0x612e7000 → 0x61300000`: the flash span then ends at section 6's own
  source (`0x4183f000`), so the loader copies the gap straight from the package. The gap holds a magic word + an LCG
  pattern; a 65-B check (`0x605d2f98`, section-3 tail, outside the probed region) sums it on each look-editor banner draw and
  appends **`S+`** (loaded, intact), **`S!`** (loaded, changed since boot) or **`S0`** (not loaded). Patch
  `patches/omdem1mk2/space_probe`; editor call only with `EM1_SPACE_PROBE=1`; `check_loaded` now reads the release's own
  end words.
- **Emulated** (`tools/omdem1mk2_emu_space.py`): end getter stock `0x612e7000` / patched `0x61300000`, flash span =
  section 6's source; the check on the built / 0xFF / one-word-changed region → `S+` / `S0` / `S!`, registers kept; the
  editor's own `call` site through the check and back. **Not emulated:** the loader's flash copy, and whether anything
  uses that RAM later -- that is the camera test.
- **Camera (owner, v0.4c13-sp1):** banner `Provia C0 S+ K0009+` after several bursts and picture-mode changes: the region is
  loaded and untouched by normal use → **0x612e7000..0x61300000 (100 KB) usable** for code and tables [C]. Still to see:
  `S+` after a power cycle and a movie. (`C0` = the card loader has not run yet; to compare with v0.4c13's reading.)
- The 162 KB gap after section 4 can be probed the same way when needed.

## Order

1. Code space: prove more loaded space (camera probe of a section's loaded-end word, as the OM-3 did) or a card-loaded code block.
2. Find the spare remembered setting and the Soft Focus / CPU-pass sites; emulator fixtures for the capture job.
3. Bloom route (useful alone, and it provides the finished YCbCr buffer), one camera test.
4. Halation pass with the global stage and gate above, then the camera control; emulator proof as in §"How", then camera.
