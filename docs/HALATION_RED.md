# Red halation per slot ("red bloom", effect_id 2)

Status: **built into test13 (§6); camera test 13b: no red glow (§8); replaced in place by bloom colour (§8).** This design extends the bloom +
clarity routine (docs/BLOOM_HALATION.md, docs/CLARITY.md). Labels: **[V]** read from the decoded main.
**[I]** inference.

## 1. Verdict

- **True red halation is not small.** A red glow around *white* lights needs a chroma term that follows the
  highlight luma. That needs the combiner-156 colour word plus a brightness-key mask pass (FUJI_GAPS §4). It
  is high effort and high risk, and it is not proposed here.
- **A small change can make the existing bloom halo redder than its source.** Spread the blurred image's
  chroma more than its luma, and spread Cr more than Cb. Warm practicals (tungsten, sodium, neon, tail
  lights) then get a red-orange fringe that reaches past the luma glow. White lights still get a neutral glow.
  This is the realistic per-slot "red bloom".

## 2. Facts it relies on [V]

- Combiner 11 handler `0x603a049e`:
  - w comes from getter `0x6039fee8`, which the bloom hook already controls.
  - Per input it writes a config word: A at +88, B at +132, both 0x002A0000.
  - It then writes three gains per input:
    - A: +92 = w | w<<16, and +96 = w.
    - B: +136 = (1024−w) | (1024−w)<<16, and +140 = 1024−w.
  - The tail is `0x603a04e8 mov d1,(136,a3)` / `0x603a04ec mov d3,(140,a3)` / `0x603a04f0 ret [d2,d3,a2,a3],20`.
    At the tail, d2 = w, d3 = 1024−w and a3 = bank.
- Combiner 135 loads **three separate B gains** from request+672/674/676 into the same +136 lo/hi and +140
  fields. So the three gain fields are per channel.
- Defaults `0x6039fdf0` set up signed chroma (offset −128). A gain on a chroma channel therefore scales
  around neutral.
- `effect_id` 2 (halation) already passes the SD loader v3 range (0..3), the LOOKS.BIN check and
  `patches/bundles` (`"type": "halation"`). Today it is stored but not consumed.

## 3. Design

Each chroma channel c gets k_c times the blur share. The weights still sum to 1024 per channel. This is
the same lerp mode that bloom uses on camera, and there are no negative gains:

    B_c = (1024 − w) · k_c        A_c = 1024 − B_c         (luma channel unchanged: A = w, B = 1024 − w)

In flat areas the output equals the input, so there is no global tint or saturation change. Near a light,
chroma bleeds k_c times further than luma. With k_Cr ≈ 2.5 and k_Cb ≈ 0.6, the fringe leans red.

| Piece | Change | Size |
|---|---|---|
| bloom_flag | accept effect_id 2 as well as 1 and 3 (one extra compare) | +4 B |
| bloom_w | effect 2 → halation LUT, 5 weights that no stock or bloom path produces (e.g. 943/883/821/749/667) | +8 B code, 10 B LUT |
| new hook 0x603a04e8 (6 B: `mov d1,(136,a3)` + 2 B → `jmp halo; nop`) | `halo` replays both stores. If d2 is in the halation LUT (5 compares), it computes B_Cr, B_Cb and A_Cr, A_Cb with `mul` + `asr 8` (k in 1/256 units; MDR is not needed because exit is via `ret`, not `retf`). It rewrites the matching halves of +92/+96/+136/+140, then `ret [d2,d3,a2,a3],20` | ~80 B |
| k table | k_Cb, k_Cr per strength 1..5 | 10 B |

- **Total:** about 110 B of new code and data, plus one new 6-B hook. The two existing bloom hooks are unchanged;
  only the routine behind them grows.
- **Space:** it does not fit in the 34 B left in the sec-2 bloom claim (0x6055e6ce–0x6055e6f0). Candidates:
  - the dead EVF step-13 G table after lv_art (0x601e123c…), using the same dead-EVF argument and build check
    as lv_art;
  - the retired sec-1 bloom block 0x60210e10–0x60210e80. The aspect stub starts at 0x60210e90.
- **No loader, ABI, LOOKS.BIN or BUNDLES.BIN format change.** CineStill800 would use
  `"effect": {"type": "halation", "strength": 4}`.
- **Gating:** the halo stub acts only on its own LUT weights. Combiner 11 under the stock Soft Focus filter
  (600..200), bloom (942..666) and clarity (≥1100) is never touched.

## 4. Unknowns and confidence

- **Channel order of the three gains [I].** It is not known which of +92/+136 lo/hi and +96/+140 hold Y, Cb
  and Cr.
  - Plan for the first camera A/B: three build variants that each boost one field. One field's variant
    blurs the luma (that field is Y), one tints the fringe red (Cr), and one tints it blue (Cb).
  - A wrong guess is harmless: the image is softer or tinted, and it does not crash.
- **Look [I].** The fringe colour follows the light's own chroma, so white LEDs stay white. The halo radius
  is fixed by the 160×120 reduce, as for bloom.
- **Side effects:**
  - Extras sector 2 shows effect 2 as neither Glow nor Clarity, and editing it there rewrites it to 1 or 3.
    A label tweak in look_extras would be about 20 B.
  - lv_art previews only effect 1, so a halation slot would have no LV glow.
- **Confidence:**
  - CPU side: **high**. It is the same pattern as clarity: weights in the proven combiner, positive gains
    that sum to 1024, and a store set limited to the bank.
  - Pixel result: **medium–low** until the channel-order A/B test is done.

## 5. Library v2

CineStill800 now uses `"effect": {"type": "halation", "strength": 4}` (bundles/library_v2.json), so a Film pick
of CineStill800 gets red bloom. Its light OR/R +2 and hue OR −1 stay. On firmware older than test13, effect 2 turns
the glow **off**: only use this LOOKS.BIN with test13 or later.

## 6. As built (test13)

- `patches/bloom/build.py --sd-v3 --clarity --halation`:
  - bloom_clarity.s.in (`.if HALO`): bloom_flag also accepts effect_id 2; bloom_w returns `h_lut` =
    943/883/821/749/667 for it (both combiners; no other path returns these). 298 B (was 270) in the same claim.
  - `halo.s.in` at 0x60210e10 (104 B): hook 0x603a04e8 (8 B) `jmp halo; nop×3`. It replays both stores, scans
    the 5 weights, and only on a hit rewrites the gains: Y B = b (stock), Cb B = b/2 + b/8, Cr B = 2b + b/2
    (b = 1024 − w, at most 892), A = 1024 − B. No mul, no clamp needed (build check). It exits with the stock
    `ret [d2,d3,a2,a3],20`, keeping d0/a0 as the stock tail.
- Channel order Y, Cb, Cr (+136 lo, hi, +140) is still [I]. If the camera shows a blurred image instead of a red
  fringe, or a blue fringe, swap the fields in halo.s.in (§4).
- Verified (`tools/ep7_halation_verify.py`): F converter flag for effect 2 / strength / MONO / mode 12; W banks on
  both combiners for strength 1..5 (combiner 11 == the formula; combiner 12 == plain pack; rest of the bank and
  the live stack == stock); D bloom 1..5, clarity 1..5, off, erased, bad effect and stock Soft Focus banks
  byte-identical to the previous test13.
- Known gaps: Extras sector 2 shows effect 2 as `Clarity/Glow 0`, and editing it there rewrites it to bloom or
  clarity. lv_art previews only effect 1, so a red-bloom slot has no LV glow.

## 7. Bloom colour presets (plan, not built)

The tint is the pair (k_Cb, k_Cr) in the halo stub, so presets are cheap in code: neutral (1, 1) = stock bloom,
red (0.625, 2.5), amber (0.4, 2.0), warm/orange (0.8, 1.6), cool (2.0, 0.6). A 5-row k table and one extra index
add about 30 B to the stub.

The cost is the **per-slot byte**:
- The loader's range table only allows 0 in bytes +45..63.
- +32..44 are the colour byte and sat advice, which the placement rule and the LOOKS.BIN records already use.
- So a tint byte means a BUNDLES.BIN / LOOKS.BIN rule change (loader v3 range table, `fm_check`,
  `ep7_looks_bin`, `ep7_library.place`) plus a sixth Extras field (`5 Bloom Red`, about 60 B in look_extras).

That is well beyond the 110-B red-only design, so test13 ships red only. Suggested route: allow 0..4 in byte +45
(`bloom_tint`) in the next loader revision. The stub never needs the slot: bloom_w can return a distinct weight per
(strength, tint) pair (25 values near the red-bloom ones), and the stub maps the weight back to its k pair.

## 8. Camera test 13b and bloom colour (test13 in place)

### What the camera showed
- Shots: PB021368–1373 are COLOR1 (makernote PictureMode 9; the card's COLOR1 = CineStill800, effect 2 strength 4).
  PB021376–1379 are COLOR2 (mode 10; Pro 400H, plain bloom 5). PB021374–1375 are MONO1 (mode 12).
- PB021373 is a white-warm LED strip. There is a wide luma glow. Across the strip, the fringe chroma is Cb −5 / Cr +4..+7,
  which is the lamp's own warm cast. The clipped core is Cb −1..−2 / Cr 0. There is no red excess anywhere.
- **Root cause (design, not a crash or a wrong hook).** Effect 2 ran as bloom: the luma glow is there. Its chroma term
  only scales the blurred image's *own* chroma (B_Cr = 2.5 b). A clipped or white light has Cr ≈ 0 after
  development, so 2.5 × 0 stays 0. On a warm light, the extra is a few Cr units: too small to see.
  - The field order (§4) cannot be the cause. With Cb and Cr swapped, the fringe would still be only the source chroma.
  - Every combiner-11 bank field is per channel (+80 offsets, +92/+96 and +136/+140 gains, clamps, output offset).
    A constant chroma term would therefore tint the whole frame, and linear compensation cancels it.
  - A red glow around **white** lights still needs the mask route (FUJI_GAPS §4). That was not built.
  - Side finding [V bytes, I meaning]: the input config words (+88/+132) are three 2-bit per-channel source selectors
    (0x2A = image on all channels, 0x15 = the constant / mono term, 0x14 or 0x28 = chroma only). Stock combiners 33, 135
    and 156 use the 0x15 term with a colour word at +120. If that term is "Y of the input × colour word", it would give
    a true luma-keyed red glow in combiner 11. This needs a camera A/B; it is not built.

### What was built (bloom colour)
- **Card format:** slot byte **+45 `bloom_tint`**: 0 neutral, 1 red, 2 amber, 3 warm, 4 cool (layout.json).
  - Loader v3 range: 0..4. Only the span byte at 0x605b774e changes, 0 → 4.
  - LOOKS.BIN record +47 (was "must be 0") carries the tint, and the Film page places it at slot +45.
  - Old files have 0 there, which means neutral, so they still load. `bloom_tint` is kept out of `layout_crc`,
    so old LOOKS.BIN files still pass the header check.
  - Effect 2 with tint 0 renders red (legacy CineStill800 v2 slots).
- **Weights:** `bloom_w` sends effect 1 and 2 to `bw_tint` (sec 1, dead EVF step-6 R table 0x601e263c).
  - It returns w = W[s] + tint (row 0 = the plain bloom table, so tint 0 banks are byte-identical to before).
  - Rows 1..4 are weights no other path returns.
- **Halo stub** (same hook 0x603a04e8, same table): it maps the weight back to (tint, strength).
  - Y spreads as bloom.
  - Cb and Cr: B_c = min(k_c · b / 8, 1024), A_c = 1024 − B_c, so gains stay positive and sum to 1024.
  - k_Cb / k_Cr: red 0.5 / 3.5, amber 2 / 3, warm 1.25 / 2, cool 3 / 0.75.
  - Red spreads Cr further than before (3.5 vs 2.5) and Cb less.
- **Honest limit:** the colour still follows the light's own chroma. Tungsten, sodium and neon get a clearly tinted
  fringe; white LEDs and clipped cores stay neutral.
- **Extras page:** sector 5 shows `5 Bloom Neutral|Red|Amber|Warm|Cool`; the dial steps 0..4.
  - Sector 2 now shows effect 2 as Glow.
  - Editing sector 2 on an effect-2 slot first sets tint red, so the slot stays red when it becomes effect 1.
- **Live view:** lv_art now previews effect 2 as well, as a luma glow. CineStill800 v2 lost its LV glow in test13
  because lv_art previewed effect 1 only.
- **Library v2:** CineStill800 = `{"type": "bloom", "strength": 4, "tint": "red"}`.
- **Verified** (`tools/ep7_halation_verify.py` vs the previous test13): F 24, W 84, D 112.
  - W covers tints 1..4 and effect 2 + tint 0 on both combiners, plus tint 5/255 and strength-6 guards.
  - D: bloom tint 0, clarity, off and erased banks are byte-identical.

## 9. Camera test 13c: bloom colour "still a no go" (analysis; nothing new built)

### Which slots were shot (makernote 0x0520 PictureMode; 9/10/11 = COLOR1–3, 17 = COLOR4 by elimination, 12 = MONO1)
- PB021380–1383: mode 10 = **COLOR2** (bloom 4, tint 4 cool). PB021384–1390: mode 17 = **COLOR4** (bloom 5, tint 1 red).
  - 1384–1388 are XPan desk scenes without a light source. The LED-strip shots are 1381–1383 (cool) and 1390 (red).
- The card's BUNDLES.BIN passes `ep7_bundles_bin.py --check`. Byte +45 is 4 in COLOR2 and 1 in COLOR4, as intended.

### 1. Is the tint applied for effect 1? Yes. Not a bug.
- `bw_tint` takes effect 1 and 2. Effect 1 uses its own +45 tint, and effect 2 with tint 0 becomes red.
- `tools/ep7_halation_verify.py` on releases/test13 gives F 24 / W 84 / D 112, all PASS. W covers effect 1 × tint 1..4 × strength 1/3/5
  on combiner 11 (halo gains) and combiner 12 (plain pack).
- Stills use combiner 11: clarity, which acts only there, was visible on camera in test 11.

### 3. Fringe chroma, measured (1/8-size JPEG decode, rings around the largest Y > 248 region; Cb/Cr offset from 128)

| Shot | slot / tint | core | ≤4 px | ≤12 | ≤30 | ≤60 | ≤120 |
|---|---|---|---|---|---|---|---|
| 1381 | COLOR2 cool | −1.6/+1.0 | −6.4/+4.1 | −9.8/+7.3 | −8.6/+10.0 | −5.0/+9.1 | −2.2/+4.2 |
| 1382 | COLOR2 cool | −1.4/+1.1 | −5.4/+4.6 | −8.9/+8.9 | −9.0/+13.8 | −5.5/+13.7 | −2.4/+7.3 |
| 1383 | COLOR2 cool | −2.7/+0.4 | −5.8/+5.4 | −8.5/+10.2 | −7.9/+13.2 | −4.7/+11.2 | −1.7/+5.3 |
| 1390 | COLOR4 red | −1.2/+2.0 | −5.1/+4.4 | −10.8/+8.8 | −13.5/+14.5 | −9.6/+13.8 | −4.3/+8.1 |
| 13b 1373 | COLOR1 red (eff 2) | −0.9/+0.5 | −3.4/+2.8 | −5.9/+5.4 | −2.5/+5.2 | −0.2/+3.3 | −0.7/+2.0 |

(Cb/Cr pairs; units of 8-bit chroma.)
- "Cool" and "red" give the **same warm fringe** (Cb −9, Cr +10..14). That fringe is the warm-white LED's own chroma, carried by the
  luma glow. The core is neutral (|Cb|, |Cr| ≤ 3) in every shot.
- The model predicts exactly this. The halo stub scales each chroma channel's own blur share, so it can only re-spread chroma the
  light already has. A cool k_Cb = 3 on a source with Cb ≈ −9 makes the fringe *more* yellow, not blue. A clipped white core has
  nothing to spread. A tint you can see needs a term that depends on luma.
- A pixel "after" for the real route cannot be simulated. That route rests on ISP semantics that are not known (below), and there
  is no ISP model to run it on.

### 2. The real tinted-glow route: not built (blockers found this round)
New facts [V bytes]:
- Each combiner-bank input group is 44 B: A = +76..+119, B = +120..+163.
  - +76 / +120 are the group's **constant colour word**: cleared by the config 0x603a013b; set by combiners 33/156/135.
  - +80/+84 and +124/+128 are offsets, +88/+132 config, +92/+96 and +136/+140 gains, +104..+112 and +148..+156 clamps.
  - +164/+168 is the output offset.
- Config word byte 2 = 0x2A selects the image on all three channels, and byte 1 = 0x15 selects the constant (Vintage B =
  0x1500 + colour 0x001900E1, weight 115). Combiner 135 is the same, with colour 0xFFFFFF and per-channel gains from request+672..676.
  No stock config mixes per-channel sources, and none routes Y into a chroma channel.
- Masks: kind-0 requests get the mask descriptor at request+532 (MONO 0x60359e15, shading 0x6035b0ab). **Kind-3 requests get it at
  request+148** (shading modifier 0x6035b0d8, copied from job+14240 → +12, 64 B). The Soft Focus blend setup 0x6035ca31 copies
  buffer 0x1000 → request+20 and 0x1061 → request+84 (job+6592 + 88·idx, idx from 0x60350975). Its +148 is not set.

Why it is not built (each item is [I] and needs a camera probe; a wrong guess means garbage frames or an ISP stall on tinted slots):
1. **Per-channel ops cannot do it.** Every gain, offset and clamp acts on one channel. In flat areas, a constant chroma term on
   B tints the whole frame by β·K. A luma-keyed term needs a mask or a Y→chroma selector, and neither has been exercised.
2. **Mask route inside the blend** (copy 0x1060's descriptor to blend request+148; bank in the combiner-33 style: mode 0x1002,
   B = colour word, +180 = 3):
   - The meaning of mode 0x1002 and of A config 0 in combiner 33 is unknown.
   - The format of a 0x0305 (4 B/px, 160×120) buffer on the mask port is unknown. The shading mask is created by 0x6036b635,
     format not traced.
   - Whether B (+84) is still read in that mode is unknown.
   - Either way, B = the colour word means the luma blur is replaced, not tinted.
3. **Route via the stock late shading pass** (it already runs after every COLOR blend, combiner 33 = lerp(image, colour, mask)):
   - It would need the mask from the blur buffer.
   - 0x1060/0x1061 are released before that pass runs (blend callback), so a lifetime change across two entries is needed.
     That risks a buffer-pool leak (48 slots) or reuse.
   - It also takes over the slot's vignette.
4. The full FUJI_GAPS §4 route (new mask pass) adds a full-size pass, so it is not at stock Soft Focus speed.

Suggested next step (not done; needs the user's go-ahead): a **probe build** that changes only tint 1 (red) to route 2,
with the other tints unchanged, shot on one warm and one white light. If the frame is valid, the mask/colour semantics are
settled and the tints become colour words. If not, revert the tint-1 rows.

## 10. Red-tint mask-route probe (built into test13 in place; not camera-tested)

User go-ahead after §9: route 2, red tint only.
- **probe_set** (hook 0x6035caad in blend setup 0x6035ca31; replays `movhu (12,a3),d1; movhu (14,a3),d2` → 0x6035cab3).
  - Guards: job marker 0xB2, mode 11, profile 1..4. The slot comes via the v3 accessor and must be effect 1 tint 1, or
    effect 2 tint 0/1.
  - It then finds job buffer 0x1060 (job+6592, 48 × 88 B, id at +76; the 160×120 reduce, alive until the blend
    callback) and copies its 64-B descriptor to request+148, the kind-3 third port (the shading mask port; the generic
    programmer 0x60352729 always loads +148).
  - It also sets request+680 = 1024 (the shading modifier's neutral mask gain [I]).
  - Fail safe: any failed check, or no 0x1060, means no store.
- **probe_bank** (halo stub, red row only). If request+148 equals the 0x1060 descriptor word for word, the bank becomes
  combiner 33's (vignette) shape:
  - mode 0x1002, A cfg 0, A gains 1024, B colour word +120 = 0x00C060D0 (Y 0xD0, Cb 0x60, Cr 0xC0), B cfg 0x151500,
    B gains β = 2b (≤ 714, build-checked), +180 = 3.
  - Otherwise it is the §8 chroma-spread bank.
  - Expected look [I]: lerp(image, orange-red, β × blurred-image mask). The colour's Y gives the glow, so this replaces
    the luma blur blend for red slots.
- Space and checks: bw_tint + halo + probe = 510 B in 0x601e263c–0x601e283c (dead EVF step-6 R and G). The only abs32
  refs are the step-table words 0x601e3ce0/e4. `--red-probe` adds the hook edit. Builds without the flag are
  byte-identical to before.
- Unknowns the camera decides:
  - whether mode 0x1002 reads the mask from port +148 at 160×120 / format 0x0305;
  - which byte of the colour word is Cr. A blue halo means swap 0x60/0xC0;
  - the mask scale.
  - A stall is possible on the hardware side only. The CPU side always falls back.
- Verified: `tools/ep7_red_probe_verify.py` S 110 / B 66; halation F/D pass, and W differs only in the (sp) call scratch
  word. Anti-brick: decode == stock + edits, restore == stock.

### 10b. Camera result (PB021392–1394, testdata/camera_v014): garbled frames, probe reverted in releases/v0.14
The red slots came out as a salmon/brown frame with a regular grid of about 65 px tiles (about 80 × 60 across 5184 × 3888).
Each tile is either the flat colour or the image showing through a dark, rounded blob. Mono and plain shots (1391, 1395) were fine.

What this tells us:
- **Proven:**
  - The capture did not stall.
  - Mode 0x1002 does lerp(image, colour word, mask): where the "mask" is low, the image survives, including sharp text.
  - The colour word's byte 2 drives Cr: the hue is red/salmon, not blue.
  - So the bank shape, port +148 and the colour path work.
- **Inferred [I]:**
  - The mask port does not read the 0x0305 (4 B/px, 160 × 120) reduce buffer as one value per pixel. The grid is half of
    160 × 120 per axis. Each tile is interpolated on its own, so blobs are not continuous across tiles.
  - That points to the port expecting the shading mask's own format: probably 1 B/px or a block-grid / tile layout
    with its own stride.
  - It read our YCbCr bytes as that layout. The wrong stride and format give quasi-random, mostly saturated values, so
    most tiles hit full colour.
- **For a retry:**
  - Trace the shading mask's format, size and stride where it is built (0x6036b635 → 0x6036cec0) and copy that descriptor
    shape.
  - Feed the port a buffer in that format, e.g. a reduce pass that writes Y only. Do not feed it the 0x1060 image buffer.
  - A threshold or scale on the mask is still needed: bright flat areas would otherwise tint.

The release is back to the §8 chroma-spread bank for red slots: 273 edits, bloom edits identical to the pre-probe build,
the log probe kept, and the card unchanged (COLOR1 = bloom 4 red). `--red-probe` stays in patches/bloom/build.py for a
future retry, off by default.

### 10c. Retry with the vignette mask's own format: mask side mapped, source side not (nothing built)
**Vignette mask, mapped [V code]:**
- Built by the cache 0x6036b635: 4 objects of 100 B at 0xa27364e8, key 12 B, refcount at +96.
- Generator 0x6036cec0 fills the 64-B descriptor at object+12:
  - +8 format = **0x080C**, +10 stride = 128 px, +12/+14 = 128 × 128, +16/+18 = 128, +20/+22 = 0, +24/+26 = 64/64 (centre);
  - beyond the copied 64 B: +72 = 0x8000, +76 = 0x00011106.
- Memory comes from the memory manager (0x603509e3, message 19). +0 = the address.
- 0x603390a4 → 0x60338d49 then writes the mask **on the CPU**: **u16 per pixel**, row stride 2 × 128 B, a radial profile
  from table 0x604ebf1c (1024 at the centre, falling to 0) plus 7.
  - So the mask is Q10, and 1024 = image unchanged [I strong: the vignette leaves the centre untouched].
  - No cache flush follows the writes, so this memory is coherent for CPU writes [I].
- The shading request copies that descriptor to kind-3 request+148, with +680 = the level gain (1024 neutral).
- This explains 10b: we handed the port a 0x0305 buffer (4 B/px, 160 × 120). Read as a u16 0x080C-style mask, those bytes
  are mostly saturated or out of range, so most tiles go to full colour.

**What a correct mask would need:** a 64 × 64 or 128 × 128 u16 buffer, m = 1024 − k·max(0, Y − T), built on the CPU from
the blurred highlights at blend-setup time. 64 × 64 could be written in place over 0x1060's memory without overwriting
rows not yet read.

**Why it is not built:** the source side is not mapped with reasonable confidence.
1. The component layout of 0x0305 is unknown: which byte or half-word is Y, and whether it is 8 or 16 bit with a pad.
   - Size = stride × h × 4 is confirmed, nothing else.
   - A layout-agnostic proxy (max byte) fails if the pad byte is 0xFF, and is noise if the components are 16-bit.
2. It is not shown that the reduce pass has *finished* when the blend setup 0x6035ca31 runs. Work-list execution order
   is [I].
3. CPU reads of a DMA-written buffer may be cached. A stale mask is harmless, but it makes the probe ambiguous.

**Safe next step (proposed, not built):** a read-only probe. At blend setup, copy 16 bytes from a bright and a dark
pixel of 0x1060, plus its descriptor words, into the log probe's heap record, and show them on the Extras page as the
video-log probe does. One shot of a lamp then maps the 0x0305 layout and timing with no change to the image pipeline.
After that, the mask route above is a small, well-defined build.

### 10d. Read-only blur-buffer probe (v0.14, in place; not camera-tested)
- `patches/bloom/build.py --blur-probe` (with --sd-v3 --clarity --halation). The code is `blurprobe.s.in`, 632 B in the dead
  EVF step-9 R/G/B tables 0x601e1d3c.
- Hooks:
  - **0x6035caad (blend setup) → bp_set.** Red-tint jobs only. It records 0x1060's descriptor words (+0 addr, +8 fmt/stride,
    +12 w/h, +16) and 5 samples × 8 B (2 px), at the quarter points (2,2) (1,1) (3,1) (1,3) (3,3).
  - **0x6035cbaa (blend callback) → bp_cb.** For the same job, it takes the same samples again *after* the blend.
    Equal = the reduce had finished at setup.
- Record **R = L+1920**: +0 'EP7Q', +4 setup n, +5 callback n, +6 LOGDBG pending, +8 job, +12 flags (bit0 0x1060 found),
  +16..31 descriptor words, +32..71 setup samples, +72..111 callback samples.
  - L = the film-page block, P+1016, which needs LOOKS.BIN on the card.
- Output: `vlog_dump` (patches/video_log) now runs when the video-log batch *or* the bloom record is pending, through
  `bq_gate`. It appends 10 lines `Qk: b0 .. b11` (R+0..119) via `bq_dump`. malloc is now 1024.
- Both hooks replay their stock instructions. Only the heap record and the stack are written. The image pipeline and
  the combiner banks are unchanged.
- Checks:
  - `tools/ep7_blur_probe_verify.py`: S 270 / C 5.
  - halation F 24 / W 84 / D 112 against the 04:36 spec.
  - video_log build_probe: all PASS. Q-dump: 4/4.
  - Anti-brick: decode == stock + edits, restore == stock.

### 10e. Blur-buffer probe: camera crash (removed by the log agent)
A COLOR1 Red capture crashed about 1 s after the shot. The only CPU access new in that build was bp_set/bp_cb **reading
the reduce buffer 0x1060 through its descriptor address**. Inference [I]: that address is not CPU-readable (an ISP/DMA
address, or unmapped for the CPU), and the read faulted.

Rules for later:
- Never CPU-read image buffers through a job-buffer descriptor.
- Every route that needs the blur buffer on the CPU is closed until the address space is mapped.

## 11. v0.14: per-channel bloom colour (not possible) and COLOR Art Effect (built)
**Per-channel bloom weights are not possible in this blend.**
- Combiner 11 works on **YCbCr**: signed chroma, offsets of −128 on channels 1 and 2. Its per-channel gains are
  diagonal in Y, Cb and Cr.
- An RGB weight diag(w_R, w_G, w_B) is a full 3 × 3 matrix in YCbCr, so it needs cross-channel terms the combiner
  does not have (§9).
- For a white light the blur difference B − I is pure luma, so any diagonal YCbCr weighting adds luma only.
  This is exactly the existing chroma spread, which the 13c camera shots confirmed.
- Normalising the per-channel gains to sum to 1 cannot change that. The current bloom colour therefore stays as it is.

**Art Effect (slot +46, `art_effect`):**
- Values: 0 off, 1 Star Light, 2 Pin Hole, 3 Blur (Diorama V), 4 White Edge, 5 Frame.
- Loader v3 range 0..5 (span byte 0x605b774f). `bundles` "art_effect": "star_light|pin_hole|blur|white_edge|frame".
- The byte is kept out of layout_crc, so old LOOKS.BIN files load, and old files (0) mean off.
- `patches/bloom --art`: bloom_flag jumps to `art` (76 B, dead EVF step-9 R 0x601e1d3c) right after the slot lookup,
  so only key-11 COLOR stills with profile 1..4 get it. The stub applies the stock converter's own flag update for
  that Art Effect id: 0x40 / 0x400 / (&~0x300) | 0x100 / 0x2000 / 0x8000.
- LV is untouched: the LV route is 0x60312f42 / lv_art, and neither reads +46.
- **Extras:** sector 5 = `5 Art <name>`, sector 6 = `6 Bloom <colour>`, sectors 7–12 = the log probe label / "Extras: 1-6 only"
  (build_probe constants updated).
- Film page: placing a look writes 0 to +46, and fm_mod counts +46, so a slot with an art effect shows `*`.

**Verified** (`tools/ep7_art_verify.py`, native):
- F 768: the converter for art 0..6/255 × effects × profiles × modes × keys × erased table. Flags == the stock
  converter's own result for that id. Everything else == before.
- L 20: the full work-list builder run to its `ret`, for each flag, classes 0/5, with and without bloom. A COLOR job's
  entries == before with the same flags, and the entries each flag adds on key 11 == the entries it adds on the Pop Art
  key in stock (ART mode).
- S 4096: the kind-3 selector gives the same combiner for key 11 and Pop Art for every effect 0x000–0xfff.
- Extras S / G 936 / W 5392 / V 864. Bloom-colour check F/W/D unchanged. build_probe all PASS.
- Anti-brick: decode == stock + edits, restore == stock.

**Not verified:** the effects' own pass setups (buffer allocation, frame and overlay data) do not run in the emulator.
They are the stock ART-mode setups for the same job flags.

### 11b. v0.14 after the camera feedback (Art Effects and log work)
- **Bloom colour off.** `patches/bloom --eff2-bloom --art`, with no --halation:
  - the halo hook 0x603a04e8 and its stub are gone;
  - effect 2 renders as plain bloom (flag and weight);
  - +45 is kept and the loader still accepts 0..4, but it is ignored.
  - `tools/ep7_bloom_tint_off_verify.py`: B 240. Every tint and effect 2 == plain bloom; clarity, off and erased == before.
- **Extras:** sector 6 (bloom colour) is hidden; sectors 6–12 show "Extras: 1-5 only". The Art field wraps modulo 6:
  writes are pre-clamped to −6..11 and stored as v mod 6. So the stock dial counter can never park outside 0..5: from
  Off, one step down = Frame.
  - The ±5 fields keep their clamp. Before, the Art field went through that −5..5 clamp and then 0..5, so the dial's own
    counter could sit below 0 while the stored value stayed 0.
  - extras G 936 / W 5392 (−6..6, ±127, ±2^31 on the art ids) / V 864.
- **LV Art Effect** (`patches/lv_art --features hl,bloom,art`):
  - COLOR LV jobs (the same lv_art gate) get the stock job flag for Pin Hole 0x400, Blur 0x100, White Edge 0x2000 and
    Frame 0x8000, whether or not the slot has a transport.
  - Star Light is not previewed. In stock it adds no LV stage in classes 5–7, and the stock LV converter gates it.
  - `tools/ep7_art_verify.py` V 20: for each effect and LV class 5..8, the entries the builder adds on key 11 == those on
    the Pop Art key. lv_art verify: S, H 49 (tables A1–A3 with every art value), gates 22, C, D, R.
- **Log:** the probe ring, label and LOGDBG.TXT dump are removed (the step-8/7 tables are stock again, and the loader's
  sd_back goes to ed_trig again). The log decision keeps the v0.14 fix: the trigger is the movie picture mode A+354.
  It is in `video_log.s.in`, built by `build_and_verify.py`, at 0x60210c90. H/M/G/L PASS, including the case "stills
  pm = trigger, movie pm COLOR -> not log".

### 12. Parked idea: tinted halation from the AE metering grid
A future tinted halation could build the vignette-format mask (0x080C, 128 × 128 u16 Q10, written by the CPU as the
stock vignette generator 0x60338d49 does, §10c) from the **AE metering grid**. The CPU already reads that grid, so it is
CPU-readable, unlike the reduce buffer, whose read crashed (§10e).
- Upsample the grid's highlight cells into m = 1024 − k·max(0, Y − T).
- Feed the mask to the existing mode-0x1002 lerp toward a colour word (proven to blend and to give a red hue in 10b).
- Open: the grid's location and resolution per capture, and whether a grid-resolution key looks like a halo.

### 13. Issue #8 verdict: tinted halation (research, nothing built)
**Hard. Feasible only through a mask, not through the blend gains.**
- Closed [V bytes, §11]: per-channel weights in combiner 11, because they are diagonal in YCbCr, so white highlights add luma only.
- Closed [V camera, §10e]: reading the reduce buffer on the CPU.
- Open route: §12, a vignette-format mask (0x080C, 128×128 u16) built by the CPU from the AE metering grid, fed to the proven mode 0x1002
  lerp toward a colour word (§10b). It reuses the stock late shading pass, so time per shot is about stock [I]; the CPU work is a few
  thousand operations.
- Limits [I]: 128×128 is coarse, so the result is a broad warm wash around large highlights, not a thin halo. It also takes over the
  slot's vignette. Grid location and resolution per capture are untraced, and that is the next step.
- Camera test: one warm and one white light; failure mode is a garbled frame (§10b), not a brick.

## 14. Re-evaluation with the CPU grain engine (2026-11-09, research only, nothing built)

**Verdict: feasible.** The CPU grain route (GRAIN_PORT s3/r2) removes both old blockers: the CPU can now read and write the
finished photo safely (mapper `0x60067146`, camera-proven), and it can do the cross-channel step (luma mask → chroma tint) that no
combiner can (§11). Recommended design: **H1, all on the CPU**, mask at 1/16 resolution. About **0.6–1.5 s per photo typically,
up to about 4.5 s worst case**. Effort 2–3 agent sessions, including one chroma probe. Brick risk: none beyond the grain route's.

### 14.1 What the buffer gives us

- **[V]** Buffer 0x1000 is format 0x0302, 2 B/px, 5184 × 3888, with **Y in the even bytes** (d3: the band moved Y only, Cb noise
  stayed flat). The combiners treat the developed image as YCbCr with signed chroma and offset −128 (§11).
- **[I strong]** So the odd bytes are chroma, 4:2:2: one Cb and one Cr per pixel pair, offset-binary (128 = neutral).
  **Not proven:** which odd byte is Cb and which is Cr, and whether chroma is offset-binary or two's complement. Grain never wrote
  chroma, so no camera result settles it. A probe settles both (§14.5). A wrong guess is a blue or green halo, not a crash.
- **[V]** Chroma is reachable: the same row writes as grain, on the odd bytes. Grain's survival to the JPEG shows edits before the
  output pass `0x6035b529` (creative shading, combiner 33) are kept.

### 14.2 Measured throughput

- **[V]** s3/r2's pass is 15.1 instructions per pixel (emulated), about 304 M per photo, with 972 locks and 1944 flushes.
- **[V camera]** The owner measured about 3–5 s extra per photo (CHANGELOG v0.27; d3 about 5 s including the forced Soft Focus passes).
- **[I]** So a full-frame pass costs about **0.2–0.33 s per instruction per pixel**, including window and flush overhead. All the
  estimates below use this.

### 14.3 Design H1 (CPU only)

Hook: grain's plain-look position (`gc_ob`, after the dev request wait `0x60354930`, before `0x6035b529`), on `dev + 0x6035b529`
lists, so no Soft Focus passes are forced. Halation is a look effect (effect_id 2), so it never coexists with Glow (1) or Clarity
(3). Art-effect looks would use the blend-hook position, as grain does. Run halation before grain, because film grain sits over
the glow.

| Pass | Work | Instructions | Time [I] |
|---|---|---|---|
| A. Read | Y of every 2nd pixel on every 2nd row (5 M samples); e = max(0, Y − T); sum e into a 324 × 243 cell grid (1/16) | about 4 per sample, about 1 per pixel | 0.2–0.35 s |
| B. Mask | Separable blur on the grid: 3 running-sum box passes per axis ≈ Gaussian. The cost doesn't depend on radius. Radius 2–6 cells ≈ 30–100 px σ. An optional second, wider scale for a long tail | about 30 per cell × 79 k cells, about 2.4 M | < 0.05 s |
| C. Write | Per row: lerp two mask rows into a 324-entry line. Skip 16-px spans whose ends are both 0. Elsewhere, g by incremental horizontal lerp, then Y += g·kY (clamped), and per pixel pair Cr += g·kCr, Cb −= g·kCb (clamped). Skip chroma where Y ≥ 250, so cores stay white | about 12 per pixel touched | 2.4–4 s × coverage |

- **Coverage** = the share of the frame inside the glow. For night, stage and window scenes it is about 10–30 %, so C costs about
  0.25–1.2 s and the total is **0.6–1.5 s**. For a clipped sky over half the frame, the total is about 4.5 s. A coverage cap is
  advisable: if the grid shows more than about 50 %, scale the gain down or skip, so daylight shots stay fast.
- Summing the threshold excess (not max-pooling) keeps the glow proportional to the light's area. A 20-px lamp gives a small,
  real halo instead of nothing (the 160 × 120 average in §10 diluted it).
- The tint vector (kY, kCb, kCr) per bloom_tint (+45: red, amber, warm, cool), with gain from strength 1..5. That reuses the
  existing **effect_id 2 + tint + strength** fields: **no LOOKS.BIN, BUNDLES.BIN or share-code change**, and the Control Panel's
  halation type stays. Today effect 2 renders as plain bloom (§11b), so CineStill-style looks would gain the tint.
- **Memory** [V limit, I fit]: class-2 malloc caps at 16 KB per block, and the job pool is reachable only through a window
  (GRAIN_PORT s1). A u8 grid of 79 KB takes 5 blocks (up to 50 rows each), plus one 16-KB scratch for the blur. Any failed malloc means
  no halation and stock output (a guard, as grain has). Total heap capacity is unmeasured.
- **Live view:** no tint. lv_art keeps the existing luma-glow preview for effect 2.
- **Combined with grain:** run them in sequence first. Merging into one row loop later saves one set of locks and flushes (about
  0.3 s).

### 14.4 Can an ISP stage do the blur?

- **The Soft Focus reduce and upscale (0x1060 → 0x1061)** would give a full-res blurred image for free. Rejected:
  - it blurs *before* the threshold, so small lights are averaged away;
  - it costs about 1 s of passes and two 40-MB buffers;
  - the CPU would still need a full-res pass reading 0x1061 as well as rewriting 0x1000, about 14+ instructions per pixel over
    the whole frame, with two windows that may need different modes.
  The blur is the cheap part anyway (pass B, < 0.05 s).
- **The ISP doing the full-res write (H2):** the only stock cross-channel route is combiner 33, mode 0x1002: a lerp toward a
  colour word through a 128 × 128 u16 Q10 mask (proven red in §10b, mask format §10c). The CPU would run passes A and B, write
  the grid as a 0x080C mask, and let `0x6035b529` do the rest. That is about 0.4 s total. Reasons it is a later option, not the
  plan:
  - it is a lerp, not an add, so bright areas inside the mask are pulled toward the colour, and core exclusion only works at
    about 40-px resolution;
  - the stock mask object comes from a shared 4-entry cache (`0x6036b635`), so writing into it would poison later jobs'
    shading, unless we allocate a separate object (an untraced message-19 allocation);
  - it takes over the slot's vignette on that job;
  - the colour word is fixed per job.
  Try H2 only if H1's time turns out unacceptable.

### 14.5 Risks and first probe

| Risk | Effect | Handling |
|---|---|---|
| Chroma byte order or sign wrong | Blue, green or inverted tint | **Probe first**: a d1-style band on rows 0–63 that sets the odd byte of even pixels to 168 in one half of the width, and the odd byte of odd pixels to 168 in the other half. The JPEG hue shows which byte is Cr and the sign convention |
| Save time | +0.6–1.5 s typically, about 4.5 s worst; with grain on, both add up | Coverage cap; one shared loop later |
| Heap | Malloc fails on a busy heap | Guard → stock output |
| Window crossing, interrupts | As grain | Same row-split and K = 4 code as gr2 |
| Look in gamma space | The add happens on 8-bit gamma Y, not linear light | Tune kY and the falloff by table. A mild screen curve on Y avoids hard clipping |
| Loop bug | Hang | Battery pull. No flash or settings writes are involved |

**Next step (needs the owner's go-ahead):** the chroma probe as a one-shot diagnostic on the grain route (0.5 session, one camera
shot). Then H1 with effect 2 (1–1.5 sessions), then tuning against the §9 LED-strip scene (0.5–1 session).

## 15. As built: h1 (patches/halation, 0.31h1, 2026-11-09; emulator-verified, not camera-tested)

Layer on v0.30: `patches/halation/build.py releases/v0.30/edits.json --out generated/halation/h1/edits.json`, package
`generated/halation/h1/pkg` (patched `b053f42e…`, restore `963f4dfe…2327`). Verifier `patches/halation/verify.py`: all pass.

**Changes from the §14 design** (code space forced the first two):
- **Route:** the Soft Focus blend hook (`gc_gs`), not the plain route. The pass is triggered only by looks that already run the
  bloom passes (effect 1 or 2), so the ISP's luma glow stays and the CPU adds the tint. Order: blend → **halation → grain**.
  Film grain sits over the glow.
- **Grid:** 64 × 64 px cells, u8, one malloc (≤ 16 KB). Blur: two [1 2 1] passes per axis. With bilinear interpolation the
  glow has σ ≈ 70 px, so the smallest halo is about 100–150 px. The §14 plan was 1/16.
- **Map:** u = min(255, 21v/8), g = u(511 − u)/256 × gmax/256, a soft knee with no LUT. Coverage cap: no halation when ≥ 1/3
  of the cells have g ≥ 16.
- **Add:** with w = 255 − Y, Y += w·g·dY/2^16, C += w0·g·dC/2^16, clamped. The add fades on bright pixels, so white cores
  stay white with no hard threshold.

**Look fields, no format change [V]:** effect_id +28 = 2 (tint +45; 0 = red), or effect 1 with tint 1..4 (red, amber, warm,
cool); strength +29 = 1..5 → gmax 64/96/128/176/224. The library's CineStill800 (bloom 4 red), CineStill50D and Vision3 500T
get it. Bloom without a tint, Clarity, MONO and no card record stay as v0.30 [V emulator G].

Tint rows at full glow on black (dY, dC0, dC1): red 48/−24/+72, amber 56/−48/+48, warm 56/−36/+30, cool 48/+48/−20.
**C0 = byte 1 = Cb, C1 = byte 3 = Cr is the unproven guess** (§14.1). `--swap` builds the other order, a one-constant change.

**Verified (emulator, real gc_gs/gc_lvl/gc_grain/lock/mapper/lookup; malloc, free, blend, flush stubbed):**
- M 6/6: bit-exact with the Python model, red/amber/cool, direct and windowed;
- E 1/1: a 5184 × 70 buffer across 0xd0000000, two pieces per row, mode restored;
- G 22/22: off cases == v0.30; halation + Grain == v0.30's grain over the model;
- C 2/2 (cap, no highlights); F 8/8 (malloc failures, bad records: untouched, frees balanced);
- P: package, restore == stock, no stray bytes.

**Cost [I]:**
- Pass A: about 18 M instructions.
- Pass B: under 1 M.
- Pass C: about 6 instructions per pixel pair with no glow, about 45 with glow, on rows near highlights only. The Gp build
  runs outside the lock.
- At grain's measured rate (§14.2): about 1–2 s per photo for a night scene with lights, up to about 3 s near the cap,
  on top of the bloom passes. One lock (and one full flush) per row piece.

**Camera test (one round):**
- Setup: COLOR slot with CineStill800 (bloom 4, red) or any halation look; night scene with white LEDs, tungsten lamps and
  a dark background.
- Red/orange halo around the lights: byte order is right.
- **Blue/purple halo:** order swapped. Rebuild with `--swap`.
- Green/cyan halo: the sign is inverted (unexpected).
- Blotchy halo with neutral speckles: chroma is two's complement, not offset-binary. The clamp needs the XOR-0x80 form.
- Also check:
  - a daylight frame saves at normal bloom speed (cap);
  - Grain on + halation works;
  - no hang across ~10 shots.

**Camera result, h1 (generated/v031h = v0.30 + recview r2 + halation h1):** success. CineStill 800T shows a clear red/orange halo
around an LED strip, so the byte order C0 = Cb, C1 = Cr is right and `--swap` is not needed [V camera].

## 16. h2: Halo on the Extras wheel (0.31h2, 2026-11-09; emulator-verified, not camera-tested)

Chain: `releases/v0.30` → `patches/recview` (r2) → `patches/halation` (h2), built by `patches/halation/build.py
generated/halation/h2/base_r2.json --out generated/halation/h2/edits.json`. The base is identical to generated/v031h/r2.json.
Package `generated/halation/h2/pkg`. Verifier: all pass (M 6, G 29, C 2, F 8, A 80, X 47, K 2, L 1, E 1, P).

**Control:** Extras **sector 11** (index 10), `11 Halo Off/Low/Med/High`. Sector 12 now shows `Extras: 1-11 only`. Slot byte
**+52**:

| +52 | Meaning |
|---|---|
| 0 | the look's (as h1): effect 2 (tint 0 = red), or 1 with tint 1..4; strength 1–2 Low, 3–4 Med, 5 High |
| 1 / 2 / 3 / 4 | Off / Low / Med / High, set on the wheel |
| other | off (the reader's check) |

- Stages: gmax 112 / 176 / 240. **Med = h1's CineStill 800T** (strength 4, gmax 176). CineStill 50D and Vision3 500T are Low.
- Tint stays the look's (+45: red, amber, warm, cool; 0 = red). There is no tint control, to keep the UI simple.

**Behaviour:**
- **The pass needs the Soft Focus blend.** `hl_flag` adds the 0x80 flag when a COLOR still with an ordinary capture kind has a
  stage. So Halo works on any look, including one without bloom: the blend is neutral (bw_default 1024), as with Art + Grain.
  Exceptions are kinds 0x2001, 0x2006, 0x1008 and 0x1006, the same as grain.
- **A pick sets the look's halation:** a Film pick, Own or Stock sets +52 = 0. Grain +50, Sharp +51 and NR +24 are untouched
  [V K].
- **Defaults:** a reset gives the look's stage (`hl_def`), which is then written as an explicit value.
- **The `*` marker** ignores +52, as it ignores Grain and Sharp.

**Files:**
- BUNDLES.BIN accepts +52 0..4 (SD loader span).
- MOVIE.BIN and AP.BIN zero checks now start at +53.
- `tools/ep7_bundles_bin.py` and `tools/ep7_movie_bin.py` accept +52 0..4.
- The Control Panel does not know +52 yet.
- **v0.31h1 and older reject a file with +52 ≠ 0.** Before going back, pick the look again in each slot changed on the
  wheel; this resets +52 to 0.

**Not emulated:** the guide text path (`hl_su`; same shape as sh_su, labels checked as bytes) and the Movie slot. The Movie
slot saves the byte, but movies have no halation.


## 17. Presets and Control Panel (2026-11-09; webapp tests and build pass; card files load-checked in the emulator)

**Preset halation** (`bundles/library_v3.json` and `library_v3_20.json`): a bloom with a tint is a halo, staged by strength
(1–2 Low, 3–4 Med, 5 High). Only Gold 200 gains a Glow pass: it costs about 1 s more per photo.

| Look | Halo | Why |
|---|---|---|
| CineStill800 | Med red (unchanged) | No remjet: the defining red halo around lights |
| CineStill50D | Low red (unchanged) | Same base without remjet; a daylight stock, so it shows less |
| Vision3 500T | Low red (unchanged) | The real stock has remjet and almost no halation, but people expect a cine glow; Glow 1 keeps it faint |
| Portra 400 | Low warm (new tint on its Glow 1) | Bright highlights in overexposed Portra scans show a soft warm bleed; it suits the "glowing skin" look |
| Polaroid | Low warm (new tint on its Glow 2) | Integral film blooms warm around light sources |
| Gold 200 | Low amber (new, Glow 1) | Consumer negative with a golden cast; a faint amber bleed around lights fits |
| Vision3 250D, UltraMax 400, Pro 400H, Cuban Neg | none | Remjet daylight stock; a grain-led, punchy look; a cool pastel look; a look whose Glow is a soft bloom, not a halo |
| Slide films, B&W, Faux IR, Cross Proc., Atrophy | none | Slide and mono stocks have anti-halation layers. The halo can't be neutral for mono (tint 0 = no halo on bloom) |

`LOOKS.BIN` changes only in those three records: Portra 400 and Polaroid +47 = 3, and Gold 200 +28/+29/+47 = 1/1/2.

**Control Panel** (`webapp/`):
- **Per look:** **Halo** Off/Low/Med/High and **Halo colour** Red/Amber under the Glow ↔ Clarity slider. Warm/Cool are
  shown only when a look already has them.
  - The halo is the tinted Glow: Low/Med/High set Glow 2/4/5, and Off keeps the Glow without a tint.
  - The share format is unchanged: look codes already carry effect, strength and tint.
- **Per COLOR profile (Export → slots):** **Sharp** Camera/Off (+51, v0.28+) and **Halo** Look/Off/Low/Med/High (+52, v0.31+).
  - Both are optional fields in `profiles`, so older packs and links load unchanged.
  - Older apps ignore the new keys.
- **Firmware selector:** v0.31+ (new default), v0.28–v0.30, then the older options. Older choices write 0 in the bytes
  their firmware would reject.
- **Other targets:** the OM-3 target already turns halation into a plain glow (no tint), and the recipe card says
  "Glow N of 5, halo Low (amber)".
- **Tests:**
  - Tests that compared the built-in library byte for byte with the v0.24 release file now compare it with that file plus
    the three record edits (`webapp/tests/halation-fixture.ts`).
  - The old Gold 200 v1 share code still decodes, to the look as it was before the halo.
  - New tests cover the Halo helpers, the +51/+52 bytes per firmware, and pack/link round trips.
  - `npm test`: 103 passed, 1 skipped (OM-3 cross-check: its repo isn't present). `npm run build`: OK.

**User card** (`generated/halation/h2/card/EP7MOD/`):
- `LOOKS.BIN` is regenerated with `tools/ep7_looks_bin.py`.
- `BUNDLES.BIN` is the user's own file, unchanged. Its COLOR slots hold Portra 160, CineStill800, Provia 400 and Cuban Neg.
  - Bytes 0..31 and the tint match the new look records, so nothing needed rewriting.
  - The user bytes stay: NR +24, Grain +50 (COLOR4 High), Sharp +51 and WB.
  - +52 = 0 everywhere, so COLOR2 (CineStill800) gets its Med halo from the look.
- `patches/halation/check_card.py` runs the h2 image's own `sd_check` and `fm_check` in the emulator:
  - both files accepted;
  - +52 = 4 accepted and +52 = 5 rejected;
  - bad CRCs rejected, and a tint of 5 rejected.

## 18. h3: the camera restart, and a faster pass (0.31h3, 2026-11-10; emulator-verified, not camera-tested)

**Report (v0.31):** a shot with heavy grain and High halation on a bright night scene made the camera restart by itself "after a
while".

**Cause: the system watchdog [V code, I that it fired].**
- `SYS_WDT` (task id 0x19, priority 0x37, entry 0x6005b287) waits up to 3 s on its queue and then kicks the hardware watchdog
  (0x6005b253 → 0x470008ae).
- The timeout is set to 10 (seconds, via 0x6005b1f8 → 0x98e0008c). On expiry the camera logs
  `[SYS WANA]WATCHDOG_TIMEROVER` (handler 0x60059c20) and spins until reset.
- The work list runs in the capture task (around 0x603e624d, next to REC_MAIN's entry 0x603e5d57, priority 0x36). That
  is a higher priority than SYS_WDT.
- Our CPU passes never block, so while they run SYS_WDT cannot run on that CPU. Brief interrupt-masked locks don't help.
- Grain alone is about 3–5 s, and halation on a dense night scene about 3–5 s (below). Together they come close to 10 s,
  plus up to 3 s since the last kick. That is a reset.
- Not the cause:
  - heap: three small blocks (512 B, 4 KB, up to 16 KB), and a failed malloc means no effect;
  - the coverage cap: that scene was below it, and the cap is not what bounds the run time.

**Fix (h3):**
- **Yield.** `hl_unl` replaces the unlock in every halation row and in gc_grain's three unlock calls.
  - After every 32nd unlock it sleeps one tick: `dly_tsk(1)`, 0x600313ef. Stock code uses dly 1–3 as millisecond waits.
  - Lower-priority tasks, SYS_WDT included, then run at least every ≈ 0.02 s in halation and ≈ 0.15 s in grain.
  - Total length no longer matters to the watchdog. The cost is at most about 0.2 s of sleeps per photo.
- **Faster halation:**
  - `hl_gpb` makes one cell interpolation per segment instead of two, and fills all-zero segments with word stores.
  - Pairs with g < 8 are dropped, a change of 2 or less.
  - The pass-C loop skips 4 zero pairs per aligned word read.
  - Y1 uses Y0's delta (one multiply fewer).
  - The chroma clamps take one compare in the common case.
- **Code:** `.text` 732 B. The tables move to a new `.hl6` in section 6 with `hl_unl` (CODE_SPACE_MAP).
- **Verifier:** all pass, including **Y yields** (dly_tsk stubbed and counted); the model is updated for the g threshold
  and Y1. Grain output is unchanged: G compares halation + Grain with the base chain's grain over the model.

**Halation cost per photo (5184 × 3888, High), instructions, scaled from emulated full-width strips:**

| Scene | h2 | h3 | Time at grain's rate [I] |
|---|---|---|---|
| No highlights, or daylight (capped) | 18–20 M | 18–20 M | 0.2–0.3 s |
| Night street, a few lights (≈ 1/4 of the rows glow) [I: from the per-row costs] | ≈ 80 M | ≈ 55 M | ≈ 0.6–0.9 s |
| Dense city night just under the cap (every row glows, 19 % of cells) | 321 M | 220 M (−32 %) | 3.2–5 s → 2.2–3.5 s |

Rate: grain's 304 M instructions take 3–5 s on camera, so about 1.0–1.6 s per 100 M, flushes included. Grain itself is
unchanged (3–5 s) and now yields too.

**Build:** `patches/v031/build.py releases/v0.28/edits.json --version 0.31h3`. It was run from a scratch tree with HEAD's
`patches/ap_custom`, because that layer has uncommitted work by another agent (0.31a1). Against v0.31, only the halation
regions, the three gc_grain sites and the version label differ. Output `generated/halation/h3/` (edits.json, base.json =
the chain without halation, pkg).

**Camera result, h3 (0.31b1 = v031 chain with ap_custom a1 + h3):** no restart, so the yields work. But the user found the
halation "baaaad": **too strong, blocky, lighting up highlights, and missing the LED light completely.** Best guess per symptom
(none was isolated on the camera):

| Symptom | Most likely h3 change | Why |
|---|---|---|
| Missing the LED light | **g < 8 dropped** | A thin LED strip fills little of a 64-px cell, so its blurred, mapped g stays small. Under 8 everywhere, its halo vanished completely; bigger and brighter areas kept theirs |
| Lighting up highlights, too strong | **Y1 takes Y0's delta** | h2 weights each pixel by its own darkness (255 − Y). h3 used Y0's for both pixels of a pair, so a bright pixel next to a dark one got the dark pixel's large lift and clipped. At edges and in textured highlights it reads as brighter and stronger |
| Blocky | **g < 8 dropped**, with the 64-px bilinear grid | The cut-off contour follows the cell interpolation, so halo edges end in a squarish line instead of fading out |
| – | 4-pair zero skip, single-pass strips | No pixel change: the skip only passes words whose four g are 0, and a_k = b_(k-1) = li(k-1) gives the same strip values (verified bit-exact in h3's model). They are dropped in h4 anyway, as asked |

For any later speed-up: keep the per-pixel darkness weight and every non-zero g. Only exactly neutral work can be skipped.

## 19. h4 (0.31b2): h2's halation, bit for bit, plus the yields (2026-11-10; emulator-verified, not camera-tested)

- `hl.s.in` is the committed h2 source (v0.31) with one change: its two unlock calls go through `hl_unl`. The tables are back
  in `.text`, as in h2.
- `.hl6` holds only `hl_unl`. gc_grain's three unlock calls also go to `hl_unl`, as in h3.
- No pixel arithmetic differs from h2: no g threshold, no Y delta reuse, no word skip, and h2's own strip builder.
- Built in the current tree (ap_custom a1 included) with `patches/v031/build.py releases/v0.28/edits.json --version 0.31b2`
  into `generated/v031b2/`.
- **Verified:**
  - `patches/halation/verify.py generated/v031b2/base.json generated/v031b2/edits.json generated/v031b2/pkg`: all pass. M is
    bit-exact against h2's model, Y checks the yields, P is anti-brick against the chain without halation.
  - Same inputs on the v0.31 release image (h2) and on 0.31b2 give identical photos: thin LED-like lights at High, CineStill
    Med, and Low amber with Grain. The yields fire 18–19 times.
  - The edge row costs 4.19 M instructions, the same as h2.
- **Package:** patched `ba0eaf69458bcde0b87713465c01736da80b33bd1e0f714dcf541b14d948b5a8`, restore `963f4dfe…2327`.


## 20. v0.31a crash on bright daylight frames (0.31b3, 2026-11-10; mitigation, cause not reproduced)

**Report:** CineStill 800 + Grain on a bright daylight scene (close house, palm tree, blue sky, white walls; PB102079 is a frame
saved just before) crashes about 2 s after the shutter, every time. Darker scenes take about 8 s and are fine.

**Emulated, not reproduced:**
- Setup: real gc_gs, halation, grain, lock, mapper and lookup. Malloc, free, blend and dly_tsk stubbed. Full 5184 × 3888 buffer
  from PB102079's luma at the real bus 0xce9d4b80, so it crosses 0xd0000000 and every row splits as on the camera.
  `tools`-free script `crashfull.py` (scratch) resumes across the emulator's 100 M limit.

| Frame | Halation | Grain | Instructions | Result |
|---|---|---|---|---|
| ×1.0 (g > 0 in 17 % of cells) | b2 | off | 201 M | clean, 3 frees, 113 yields |
| ×1.0 | b2 | Med | 504 M | clean, 5 frees |
| ×1.12, ×1.3 (27 %, 36 %, under the h2 cap) | b2 | off | 267 M, 309 M | clean |
| ×1.6, ×2.2 (over the cap: early exit) | b2 | Med | 325 M, 328 M | clean |

- On the same inputs, h2 (v0.31) and b2 give identical photos, so the halation output is unchanged by the yields.
- Every candidate checked comes out clean:
  - the cap path: early exit, unlock pairing and frees;
  - grid sums: u8, saturating at 248;
  - blur and soft curve: in range;
  - tint index and stack: as above.
- **Misaligned-access audit** (the camera faults, the emulator doesn't): every word and halfword access in the halation code
  is stack-, record- or job-relative, the 4-aligned tint table, the u16 box temp in a malloc block, or record +96.
  - None depends on image data. No byte-indexed word access exists.
- No stock or patch code refers to any halation placement, other than the known step-table words and pinned false positives.

**What the emulator does not model:**
- the real dly_tsk and the tasks it lets run;
- the stack depth of the job's task during a yield;
- interrupt latency in the long locked rows of a dense frame;
- malloc and cache behaviour;
- the other layers that act around a capture: Rec View (recview rv_gate), and the ap_custom a1 loader retry on half-press, which
  can now run mid-processing because of the yields.

**Mitigation in 0.31b3 (h5 = h4 + one check):**
- `hl_cap` in `.hl6`, reached from hl_pb before pass C, skips the halation when more than 30 % of the 64-px cells have any
  glow (g > 0).
  - Such frames (big bright skies and walls) spend 200–300 M instructions in pass C on a faint wash.
  - That is the class of frame that crashed, so they now skip the long row passes.
  - Every frame under the check is h2's output, bit for bit.
- Known-good camera frames sit at 2–27 %: PB021373 11 %, PB021380–82 13–27 %, PB102076–78 2–18 %. PB102079 as saved is 17 %.
- **It does not prove a cause.** If the crash is in the capped / early-exit path, or outside halation, it remains.

**Camera test to isolate the cause (one scene, 4 shots):**
1. b3 as is. A crash means the cause is not pass C's volume.
2. b3, Extras 11 Halo Off. Grain only.
3. b3, Extras 1 Grain Off. Halation only.
4. v0.31 (h2, no yields) on the same scene, if the user can flash back.
- **Verified (0.31b3):**
  - `patches/halation/verify.py generated/v031b3/base.json generated/v031b3/edits.json generated/v031b3/pkg`: all pass. M uses
    2048 × 1536 frames, so three lights stay under the cap.
  - Same inputs as on v0.31 (h2): identical photos for thin lights at High, CineStill Med, and Low amber with Grain.
  - Full-frame PB102079 ×1.0 (17 %): identical to b2.
  - ×1.3 (36 %): no halation, 19 M instructions, and the buffers are freed.
- **Package:** `generated/v031b3/pkg/patched.pkg.bin`, SHA-256 `f85e710d30f8c1a4c7d08dd8c61b2338668f0387bbbc4d557581104ef1b0f9e7`.

## 21. Draft (superseded by §22, not built as 0.31b4): watchdog off/on around the passes (2026-11-10)

The user dropped the pauses: they let other tasks (Rec View, the loader retry, card I/O) run while our buffer work is half done.

**1. Feeding the watchdog [V code]:**
- **No task heartbeat.** SYS_WDT (0x6005b287) waits up to 3 s on its mailbox, then kicks the hardware: 0x6005b253 →
  0x470008ae, boot code outside the update package, so its body can't be read.
- **No other caller of the kick.** Nothing else calls 0x6005b253 or 0x470008ae: the kick is only ever made by SYS_WDT itself.
  The only control is a request to SYS_WDT through **0x60054b33** (mailbox `(0x60040d60)`, d1 = 0 off, 1 on (also kicks:
  0x6005b232 then 0x6005b253), 2 = new timeout). It sends and waits for the reply.
- **What stock long jobs do:** switch it off around the long work. 0x60057440 sends off, makes a long call (0x60022e96),
  then on. Other off/on senders: 0x600f3141/3161, 0x600f35eb, 0x60105728, 0x60c4972b.
- **Our use:** `hl_grain` jumps to `hl_g6` (sec 6), which does that.
  1. If SYS_WDT is enabled (`0x6203ba08` ≠ 0): request off.
  2. Halation (if any), then grain (a nested `call gc_grain` with its own 144-B frame).
  3. If it was enabled: request on, which also kicks.
- **Where it can block:** the two requests wait for SYS_WDT's reply, so the task blocks there, but only before the first pixel
  and after the last. These are the same points where the blend wait (`ep7_sf`) already blocks. The CPU passes themselves never
  pause again: halation and gc_grain's unlock calls are stock / v0.31.
- **Scope:** Glow or Clarity + Grain jobs on the blend route get the same off/on. Plain-look grain (the `gc_ob` route) is
  unchanged: alone it is 3–5 s, well inside 10 s, as in v0.27–v0.30.
- **Why it's safe:** stock code does exactly this around its own long calls. The watchdog is off for at most the length of the
  passes, about 8 s on the heaviest frame, and is always switched back on: hl_g6 has one exit, after both passes. A hang inside
  the passes would then hang, not restart, the camera; none is known.

**2. Deterministic budget:**
- b3's `hl_cap` stays: halation is skipped when more than 30 % of the cells have any glow. It depends only on the image, so the
  same scene always gives the same photo.
- It bounds pass C to the frames that ran fine on camera (≤ 27 % in every known-good frame), about 300 M instructions at most.
- A time budget against the watchdog isn't needed once it is off, so none was added.

**3. Pauses removed:** `hl_unl` and its counter are gone, and gc_grain is byte-identical to v0.31's grain block.

**Verified (0.31b4)** — see the report.

**Diagnostic plan (0.31b4, same bright scene, 4 shots):**
1. As built, CineStill800 + Grain. A crash now cannot come from pauses. The watchdog is off, so a restart can't be the watchdog
   either.
2. Extras 11 Halo Off: grain only, on the blend route with the watchdog off/on, because the look has a glow.
3. Extras 1 Grain Off: halation only.
4. Grain Off and Halo Off, CineStill800 kept: the stock bloom passes only (no CPU pass, no watchdog requests). A crash here is
   outside our CPU code (bloom, Rec View or the loader).

## 22. 0.31b4 as built: v0.31's halation and grain, watchdog timeout 30 s (2026-11-10; emulator-verified, not camera-tested)

User direction: no time budget, no pauses. Raise the watchdog's limit instead.

**The watchdog [V code]:**
- **No software heartbeat or per-task alive flags.** SYS_WDT (task 0x19, priority 0x37, 0x6005b287) waits up to 3 s on its
  mailbox and kicks the hardware: 0x6005b253 → 0x470008ae. Nothing else kicks it.
- **The limit is the hardware timer itself:** 0x600219ab writes d0 into the 6-bit field (bits 0..5) of **0x98e0008c** and
  waits on 0x98e000a4. The unit is seconds (debug command `time XXX: timer change XXXsec`), so the maximum is 63.
- **Run-time settings of 10 s:**
  - `mov 10,d0` at **0x6005b23a**, in 0x6005b232: SYS_WDT on, at boot (via 0x60044be4) and on each "on" request;
  - `mov 10,d0` at **0x6005bcff**, the restore after a flash operation: 0x6005bcb5.. sets 0 (off), runs the op, sets 10.
- **Other settings, left as they are:** 1 (0x6018cb22/68, 0x601e7393, 0x60630256, 0x60767d0e, 0x60020880/097e,
  0x60058b84, 0x60059aa4, 0x6005a2b2) and 0 (0x6005bcba/e4, 0x6055939a, 0x60c974c1) are the deliberate short or off cases
  (resets, power paths, flash ops).
- **Feeding it is not a stock pattern for long jobs.** Stock long jobs switch it off and on via SYS_WDT's request
  (0x60054b33, §21), which blocks.

**Change:** both `mov 10,d0` → `mov 30,d0` (2 bytes each). Halation, grain and every other byte are v0.31's (h2): no pauses,
no watchdog requests, no cap. Every halation placement and the grain block are byte-identical to `releases/v0.31`.

**Why 30 s is safe:**
- **It is the hardware watchdog itself, not a software layer in front of one.** There is no second limit behind it.
  - The ARM-side watchdog (`ARM WDT!!!`, 0x60059cf1) watches the ARM core, not this CPU's tasks.
  - The setting is 30 of a possible 63, so it is a plain value inside the documented range.
- **Kicks continue as before**, every ≤ 3 s whenever SYS_WDT gets the CPU.
- **Cost:** a real hang anywhere now restarts the camera after up to 30 s instead of 10 s.
- **Margin:** our heaviest frame is about 504 M instructions (≈ 5–8 s) of CPU-bound work, + ≤ 3 s since the last kick, well
  under 30 s. 20 s would also do; 30 leaves room for slower-than-estimated cases.

**Verified:** `patches/halation/verify.py generated/v031b4/base.json generated/v031b4/edits.json generated/v031b4/pkg`, all pass.
- W: no dly_tsk and no watchdog request from the passes; both timeout bytes are 30.
- M: h2's model, bit-exact.
- P: anti-brick, 443 edits, no stray bytes.
- `patched.pkg.bin` SHA-256 `237e0c2658292f78967710edf0260899a0c5befd57cf7358c3d107d39488b73b`.

**4-shot diagnostic (0.31b4, the same bright daylight scene, CineStill800 on COLOR2):**
1. As built (Halo from the look, Grain Med). **No crash** means the v0.31a pauses were the cause, since b4 is v0.31 + 30 s.
   **A crash at ≈ 2 s** means it isn't the pauses, and isn't the watchdog either: a 10 s limit can't fire at 2 s.
2. Extras 11 Halo Off: grain only, on the bloom route.
3. Extras 1 Grain Off: halation only.
4. Halo Off and Grain Off: CineStill's stock bloom passes only, no CPU pass. A crash here is outside grain and halation:
   bloom, Rec View (recview), or the ap_custom a1 loader retry.

