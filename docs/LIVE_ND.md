# Live ND on the E-P7

Research only (2026-11-07): static reads of the E-P7 1.1 main, nothing built or run.
**[V]** = read in the image, **[I]** = inference. Addresses are CPU addresses (file offset + 0x60020020).

**Verdict.** The OM-style Live ND module is not in the E-P7. The part that matters is there, though: stock
**Multiple Exposure** already averages Bayer frames. Its combiner loops over N frames, and with Auto Gain on it
gives each frame a gain of 1/N. A useful "Live ND lite" (ND2 to ND4, maybe ND5) needs only menu and validator data,
not new code. Real ND8 to ND32, taken with one press and shown in live view, would be a new module. It is not worth
starting.

This corrects VIDEO_HIDDEN §4 ("none of it") and FEATURE_GAPS ("Live ND (0 hits)"): the name table is present, but
the code is not.

## 1. Live ND remnants

- **[V] Function-name enum only.** The iseq trace-name table at `0x6070567c` has pairs (id, name) and 823 ids. Its
  lookup is at `0x6060b86c`. The table names the whole Digital ND module: `iseq_StartNd`, `iseq_SetNdHandle`,
  `iseq_ExecNdExposure`, `iseq_TermNdLv`, `iseq_ExecNdLv` (ids 3–7), and `iseq_nd_*` / `iseq_ndlv_*` (ids 719–822).
  The latter include `iseq_nd_if_dsp_multi_exp_stl/_lv`, the light and dark frame managers, `ndlv_judge_shake`, and
  `comp_countup/retention`.
- **[V] The code is absent.** The iseq source-file names compiled in (`0x60707094..`, used by asserts at
  `0x6060bc63..0x6060f993`) are only `iseq_mng_cmd.c`, `iseq_sub.c` and `iseq_swpa_*.c`. The local E-M1 III main also
  has `iseq_nd*.c`, `iseq_ndlv*.c` and the `ISEQ_ND_*` dumps; the E-P7 has none of them. Pixel-shift (`iseq_pixshift_sr_*`)
  is enum-only in the same way.
- **[V] Other leftovers:**
  - Sensor-mode flag name `DIGITAL_ND` = bit 0x400 in the flag dump at `0x6060210f`. HAND_HIGH_RES is 0x800 and
    COMPOSITE is 0x4.
  - The AE debug record "THR TAG MOV & DIGITAL_ND" with fields mov/nd_frm_max/tv/rst (`0x613eeda4`, record type 7,
    bytes +81/+76/+78/+80).
  - The help text of the debug command "iseq extif 4 (Digital ND Filter)".
  - The factory `LIFE_TEST_MODE_DURABLE_ND_FILTER`.
- **[V] No UI.** No ND string exists in `generated/osd/strings_en.json`, and no setting id or job type for it was found.
  **[I]** The headers are shared across bodies, so these names prove nothing about the hardware.

## 2. Multi-frame machinery

| Feature | What it does | Use as a base |
|---|---|---|
| **Multiple Exposure** (sid 267 frames, 268 Auto Gain, 269 Overlay) | Bayer combine of N frames, gain 1/N with Auto Gain | **Best** |
| Image Overlay (playback, job 4101) | Same combiner, per-image gain table | Proves arbitrary gains |
| Live Composite / Live Bulb / Live Time | Composite is lighten (max), per VIDEO_HIDDEN, not re-checked | No |
| HDR1/HDR2, HDR BKT | Tone-mapped merge, not linear | No |
| Focus BKT / stacking | Bracketing plus a lens-gated stack | No |
| ISP combiners 11/12/136 (BLOOM_HALATION) | YCbCr two-input blends: 136 = A + B | Fallback only. They are on the developed-image path, not Bayer |

Multiple Exposure in detail:

- **[V] Settings.**
  - Menu `0x611bf200`: sid 267 "Number of Frames", list `0x611bad34` = {0 Off, 2 "2f"}.
  - Sid 268 "Auto Gain", sid 269 "Overlay". A second copy is at `0x611cc96c` (list `0x611c84a0`).
  - Validator record 438 `0x604cebc4` = sid 267, list `0x604cb73c`, 2 bytes, **{0, 2}**.
  - Labels "3f"/"4f"/"5f"… already exist (strings 1430, 1431, 1899…).
- **[V] Capture fields.** `0x602a8372`/`0x602a8385` copy keys 0x1851 (Auto Gain) and 0x1841 (frames) into capture
  +24141 and +24140. `0x602ebd93..ab` also copies them from the getter.
- **[V] Gain.** `0x603ee3d8`:
  - Job type 4101 (Image Overlay) takes the gain from table job+238.
  - Otherwise the gain is 256, or `256 / frames` when Auto Gain is 1, then `<< 3` (Q11, 2048 = 1.0).
  - So gain = 1/N per frame, an average for any N.
- **[V] Combine loop.** `0x603edcca`, reached from the job-type switch `0x603e5fce` (table `0x6053dac0`; types 4098
  and 4101 both go there).
  - It walks job+236 images from job+56.
  - Each pass sends a two-input Bayer request through `0x603523db` (callback `0x603e7b83`). The request carries a
    gain, WB and OB for each input: A gain at sp+310, B gain at sp+398.
  - The running result keeps gain 2048 (1.0) and each new frame gets 1/N, so acc = Σ frame/N.
  - **[I strong]** Type 4098 is the Multiple Exposure combine, since it is the only type that uses the Auto Gain path.
- **[V] The sequencer counts to N, not to 2.**
  - `0x60919ec4`: the counter `0x61faccb8` counts up to setting 267 (log "MULTI EXP:get take count over").
  - `0x6091a844`: when count == setting 267 it finishes.
  - `0x6091b064`: each frame handle goes into array `0x61faccac`.
- **[V] Hard limit: 5 frames.** The array is `malloc(20)` at `0x6091b038` (`mov 20,d0`), and the clear loop runs to 5
  at `0x6091b061`. More than 5 frames would overflow it unless both are patched.
- **[I] The other limit is memory.** Every frame is held until the end, at about 40 MB of Bayer each. HDR already holds
  4 full frames on this body, so 4 should fit. 5 is untested.

## 3. Routes

| Route | What | Code space | Feasibility | Brick risk | Garbled-frame / hang risk |
|---|---|---|---|---|---|
| **A. Frames 3f/4f/5f** | Validator list {0,2,3,4,5} plus 5-entry label lists (both menu copies) | ~6 B validator list + 2 × 60 B lists, 6 pointer/count edits. **Data only, no code** | **High** | Low: menu data, same kind as aspect v4, nothing on the boot path | Low–medium: memory at 4–5 frames, or another 2-only assumption in the rec job (untraced) |
| B. Auto-sequence | One press takes all N frames (drive or self-timer driving Multiple Exposure) | 0 B if stock allows it, else a sequencer hook (~50–100 B) | Unknown, so test stock first | Low | Medium |
| C. ND8–ND32 | Change the combine to accumulate as it goes (two buffers, N passes), raise the frame cap, and add N-frame burst sequencing | 1–2 KB new code, new buffer handling | Low | Low–medium | **High**: real-time capture loop, no stock template |
| D. Live-view ND preview | Average live-view frames like `ndlv_*` | Large | Very low | Medium | High |
| Video | Would need 4× sensor rate plus an accumulator in the real-time movie path. MSHDR 120p exists but is not an averager | — | Not feasible | — | — |

- **UI for A.** No new menu. Shooting Menu → Multiple Exposure → Number of Frames: Off / 2f / 3f / 4f (/ 5f), with
  Auto Gain On.
  - ND level = frame count: 2f is ND2 (1 stop), 4f is ND4 (2 stops).
  - The camera meters each frame normally, so the result keeps the brightness of one frame and the motion blur of all
    N frames, plus the gaps between them.
  - A later step could relabel the rows "ND2/ND3/ND4" through the existing strings or the film-menu label hooks.
- **Limit of A.** The gaps between frames show as steps in fast motion. The effect is smooth on water, clouds and
  long-ish exposures, and choppy on short ones. Route B is what closes the gaps.

## 4. Recommendation

Do A, after Probe 0 on stock firmware. It is the stock combiner run at its existing N, on settings data alone. Hold
back on C: OM's 9-bit-headroom accumulate, dark frames and live-view simulation are a different module, and nothing
in the E-P7 runs it.

## 5. First probes

**Probe 0: stock, no build.** It shows that the two-frame average already works.

1. Use a tripod and moving water or clouds. Set Multiple Exposure to 2f, Auto Gain On, Overlay Off. Take two 1 s
   frames.
2. Take a single 2 s frame at one stop less (f-stop +1) for comparison.
3. Expect the same brightness, smoother motion, and no ghost edges on static detail.
4. Also check, for Route B:
   - Does Sequential L, or a custom self-timer set to 2 frames, capture both frames with one press?
   - Is a RAW of the combined result saved?

**Probe 1: one small data patch.** Allow 3f and 4f only. Leave 5f out until 4f has been seen to work.

- Validator record 438 `0x604cebc4`: +4 points to the new list `00 02 03 04`, and +12 changes from 2 to 4. Claim the
  bytes in CODE_SPACE_MAP first.
- Both label lists move to 4-entry copies {0 Off/1454, 2/42, 3/1430, 4/1431}, kind 4, ptr as stock (`0x611b6f68`
  and `0x611c465c`). Then repoint the parent list pointers at `0x611bf20c` and `0x611cc978`, and set the counts at `0x611bf210` and
  `0x611cc97c` from 2 to 4.
- Emulator check, as in ASPECT §1c V1–V6: sid 267 lists 0,2,3,4, and stepping wraps.
- **Camera test** at 4f, Auto Gain On:
  - Four frames are taken and a single file is saved.
  - Brightness equals one frame.
  - Noise is about half of a single frame's in flat areas, since averaging 4 frames gives √4 = 2× lower noise. This is
    the proof that it averages.
  - Watch for "memory full", a hang, or a dark result. A dark result would mean the gain was applied twice.
  - A hang is recoverable by pulling the battery. Never touch the SD card for this.

Not traced yet: whether the rec job builder for type 4098 sizes buffers or the job+56 array for exactly 2. Probe 1
answers this directly.

## As built: 0.30n3 (patches/live_nd, 2026-11-09)

**History.** n1 added two AP tiles (sid 1429 values 217/218). On camera, the composed 0.30b1 left the AP select screen
glitchy: its per-mode record has more lists and value-keyed view tables than n1 extended. n1 is withdrawn. n2 put ND into
Multiple Exposure > Number of Frames. On camera (0.30b2, dial on AP), that item was greyed and showed 2f.

**Why it was greyed [V code].** The settings system keeps a table of forced values per mode: index 0x6047a530, 69
entries `{u16 sid-26 scene, u16 sid-109 sub, u32 block, u16 count}`, with blocks of `{u32 sid, u32 value}` pairs.
- The AP Multiple Exposure entry (0x6047a800, scene 211) points to block 0x60475e88, which has 227 pairs. It includes
  **267 = 2, 268 (Auto Gain) = 0 and 269 = 0**.
- Entering the mode applies the pairs (0x602b9a7d). They become the values every getter reads, and the exit path
  (0x602b9ae8) undoes them.
- The sid lookup 0x602ba40b (returns 128 for "not forced") tells the settings layer that 267 is mode-fixed, so the menu
  shows the forced 2f, greyed [I for the exact grey-out caller].
- Other AP and SCN modes force 267 = 0. P/A/S/M have no entry, so the menu item should be usable there.

**So AP Multiple Exposure's frame count is sid 267, held at 2 by its preset**, and its Auto Gain is forced Off (a
2-frame sum).

**n3:**
- **[V] Number of Frames** offers Off / 2f / ND3 / ND4. These are real frame counts 0/2/3/4 (validator record 438 and
  both label lists); the ME machinery reads 3/4 natively, and the frame array has 5 slots.
- **[V] Auto Gain.** One hook (0x602a8378) makes capture Auto Gain = 1 while frames ≥ 3, so ND3/ND4 always average.
- **[V] Unlock in AP.** The 267 = 2 pair is removed from the AP Multiple Exposure block (tail shifted, count 226), so
  the user's Number of Frames is used and selectable there [I: the grey-out follows this lookup].
- **[V] Guards.** The 267 reads in the ME machinery, capture +24140 and the app layer return 2 when the value is 0/1 and
  sid 24 == 211. So Off or 2f in AP Multiple Exposure behaves exactly as stock (2 frames, Auto Gain as forced, Off).
- **[V code, not emulated] One press.** In Sequential drive the ME sequence parts takes frames back to back while the
  shutter is held, until N (TAKE_PICTURE_CONT, 0x6096af89 / 0x6096b73c).

**Emulated** (`verify.py`): all 12 sites × frames 0–4 × Auto Gain × sid 24 = 240/240, data 8/8 (including the preset
block = stock minus the pair), and anti-brick (516 B differ from v0.29a, no stray bytes).

**Camera test:**
1. In AP > Multiple Exposure, Shooting Menu 2 > Multiple Exposure > Number of Frames should now be selectable:
   Off/2f/ND3/ND4.
2. Choose ND4 and shoot in Single drive: 4 presses should give 1 file at single-frame brightness.
3. Sequential L: hold the shutter for 4 frames.
4. 2f in AP should behave as before (2 frames, summed).
5. The same menu in P mode: ND4 should behave the same.
6. Noise proof: brace against a wall at ISO 6400+ on a flat dim surface, single frame vs ND4.

**Open risks.**
- **Number of Frames is now shared between AP and P/A/S/M.** ND4 chosen in AP stays set in P (P then shoots Multiple
  Exposure). Stock may cancel it on a mode change (one-shot reset list 0x60920acc) [I].
- **Before restoring stock, set Number of Frames to Off or 2f.**
- Other menus may still stay greyed if their grey-out uses another rule [I].
- UI readouts keyed on frames {0, 2} may show blank for 3/4.
- Holding 4 Bayer frames is untested on camera.
- The kind-5 labels are untested here; the fallbacks would show "3f"/"4f".

**n3 camera result (0.30b3) and the grey-out rule.** With the dial on AP and AP Multiple Exposure selected, the row is
still greyed but now shows "Off". So the forced pair supplied the value, and the grey-out comes from somewhere else.
- **[V code] The row's enable state is a rule engine, not a menu mask.**
  - Facade +20 `isEnabled(sid)` calls 0x60826dde, then 0x602af9d1(sid, 2, 3200), then 0x602b2fad. Sid 1716 has
    special handlers; everything else goes to the generic 0x602b2961.
  - The generic path takes per-sid rule records: 201 static records of 20 B at 0x6045e5fc, hashed into 0x62246e10 at
    boot. Each rule is a list of conditions (`{u16 sid, i16 value}`; all must match) plus a value map.
  - For an item query, a matched rule whose map sends every value to one value returns 256 (shown greyed) [I for
    256 = greyed]. No match returns 0 (enabled).
- **[V] Sid 267's rules** (record 0x6045e5fc, rules at 0x6043bf3c, map 0x6043bf34 = {0→0, 2→0}):
  - sid 24 ∈ {3, 4, 5, 6} (P/A/S/M) and virtual 3446 == 1;
  - virtual 15206 == 1;
  - sid 24 == 6 and 1697 == 1 and 1696 == -32767.
  None names AP (sid 24 = 211). So in AP Multiple Exposure **the only rule that can grey the row is `15206 == 1`**.
  15206 is a virtual sid recomputed on every mode change (0x602b3692/0x602b37a3). judgeSeqATT turns it into seqAtt
  bit 256. Its meaning was not decoded [I]. If it is the cause, its map {0→0, 2→0} would also make the setter reject
  3 and 4. Un-greying the row alone would not let ND be chosen there.
- **[V] Frame count in AP Multiple Exposure with n3.** The preset no longer writes 267, so the user's stored value is
  used.
  - Off or 2f gives 2 frames (the lnd guards return 2; reads of 3 and 4 pass through).
  - Auto Gain stays forced Off by the preset, as stock (2-frame sum), unless frames ≥ 3, where lnd_kg forces On.
  - So **ND3/ND4 set in P/A/S/M (where the row's rules allow it) carry into AP Multiple Exposure**, and the greyed row
    there shows the value.

## As built: 0.30n4 (patches/live_nd, 2026-11-09)

The n3 finding "the only rule that can grey the row is 15206" is **wrong**: that was the settings rule engine, which is
only one input. The real gate is the menu grey-out table.

**[V code] What greys Shooting Menu 2 > Multiple Exposure / Number of Frames (id 267).**
- **The gate is the menu grey-out table 0x60adf518**: 611 × 12 B `{u16 id, u16 0, u32 cond bytes, u8 n}`, evaluated by
  0x608290c8.
  - Each condition byte indexes the predicate table 0x60ade144. The predicates are OR'd, and the first one that returns
    non-zero greys the row (only Interval, 478, has a special case).
  - Id 267 has 39 conditions (bytes at 0x60ade957, shared with no other id). One of them, **index 24 = 0x608296e8 =
    `sid 24 == 211`**, greys the row in AP Multiple Exposure.
  - The other conditions are mode checks that don't match AP Multiple Exposure:
    - the scenes 14, 8, 143, 67, 198, 204–207, 209, 210, 212–216 and 115;
    - predicate 54's table: 77–83, 87, 88, 93, 97, 146, 164, 183 and 220;
    - keystone (685), movie (44), SCN 1438, sub-mode 109, Wi-Fi and similar.
  - Condition 0 is the settings rule engine (0x602af9d1(id, 2)).
- **In P/A/S/M the row is greyed by condition 7**: shooting mode ∈ {P, A, S, M} and `15272 == 1646`, i.e. while the
  COLOR/MONO profile control is active. That is a stock product rule (no Multiple Exposure with Color/Mono Profiles in
  P/A/S/M). n4 leaves it alone, so it explains "greyed in P" for a profile user.
- **What the settings rule engine's conditions mean:**
  - 3446 = `sid 4513 & 0x10`. Sid 4513 is the current display device (log strings "Crrnt dsp EVF/TFT"), so 3446 is an
    external-output bit.
  - 15206 = Wi-Fi remote shooting active (set in `rcvWifiReqStartRemoteTake` 0x6092410b, cleared in
    `clearWifiRemoteTakeFunction` 0x60959c22).
  - Neither is set in normal use.

**[V code] Values and storage.**
- Value checks go through 0x602af9d1 kind 0. The rule engine has no matching rule, and the second stage has no 267
  handler, so Off/2f/ND3/ND4 are all accepted (validator {0, 2, 3, 4} from n2).
- Mode change saves and restores settings through per-mode planes. Table 0x604a8420 gives each mode a byte per sid;
  backup property 0x8b64 is indexed plane × 1769 + sid, current is 0x8b54. Leaving a mode saves (0x602b982a), entering
  restores (0x602b97c5), then forced pairs are applied (0x602b9b53).
- For 267/268/269, **P/A/S/M use plane 0 and every AP/SCN mode uses plane 1**. So **ND chosen in AP Multiple Exposure
  never reaches P** (P restores its own plane-0 value).
- With n3's pair removal, AP Multiple Exposure shows the plane-1 value. Other AP/SCN modes still force 267 = 0, so
  visiting one resets the AP choice to Off, which shoots 2f through the guards.
- 0x60920acc is not a mode-change reset. It is the Wi-Fi remote-take setup (0x60920a03, from 0x60921c59).

**n4 = n3 plus:**
- **[V] Grey-out fix:** condition byte 0x60ade969 changes from 24 to 23 (`sid 24 == 210`, Live Time, already in the
  list). Only AP Multiple Exposure stops greying id 267; every other mode and item is unchanged.
- **[V] Row summary:** list 0x6117b154 now has 4 entries, so the row shows ND3/ND4.

**Emulated:**
- G: the real 0x608290c8 for id 267 and 472, with every predicate stubbed to "true only for index k". v0.29a greys 267
  for k = 24; n4 doesn't; k = 0, 7 and 23 still grey; 472 is unchanged.
- H: the hooks (240/240).
- D: data (10/10).
- P: anti-brick.
- Not emulated: the menu screen itself, and the capture sequence at 3/4 frames.

**Camera test (0.30b5):**
1. Dial on AP, AP Multiple Exposure selected: Shooting Menu 2 > Multiple Exposure is enabled, and Number of Frames
   offers Off/2f/ND3/ND4.
2. Choose ND4 and shoot in Single drive: 4 presses give 1 file at single-frame brightness. Then Sequential L, holding
   the shutter.
3. Turn the dial to P and back to AP Multiple Exposure. P doesn't shoot Multiple Exposure, and AP Multiple Exposure is
   still ND4.
4. With the profile control on COLOR in P, the row stays greyed (stock). On a normal picture mode it is enabled.
5. Choose 2f in AP: it shoots stock 2 frames. Choose Off in AP: it also shoots 2 frames.

**Open risks.**
- Changing Number of Frames while AP Multiple Exposure is active hasn't been seen on a camera. The app may restart or
  end the ME sequence on a change; its reads see ≥ 2 through the guards.
- Off in AP shows "Off" but shoots 2 frames.
- The Auto Gain row still shows the forced Off in AP; ND3/ND4 force gain On at capture regardless.
- Holding 4 Bayer frames is untested on camera.
- Before restoring stock, set Number of Frames to Off or 2f in both P and AP Multiple Exposure.

## As built: 0.30n5 (patches/live_nd, 2026-11-09)

Camera on 0.30b5: ND4 shot and combined in AP Multiple Exposure, but it took 4 presses even in Sequential L, and ND3/ND4
showed blank in the Number of Frames popup.

**Why holding didn't advance [V code].** The AP Multiple Exposure preset block forces **1487 = 0** (the continuous-drive
flag), and also 1493, 605, 764, 1158, 1489 and 405 = 0. So the drive setting never reaches AP Multiple Exposure. The ME
sequence parts' complete continuous path (TAKE_PICTURE_CONT) never runs. That path is:
- judgeSeqATT sets the CONTI bit from 1487;
- each frame done (0x6096af89) adds the count;
- while count + overlay < (224) it posts the continue event, and `sendTakePictureContinue` (0x6096b73c) takes the next
  frame into a new buffer, driven by the parts itself;
- at N it stops (0x6094f064) and combines;
- releasing the shutter stops it early (0x6096b28c → 0x60945a75 → 0x6094f064).

**One press, n5:**
- **lnd_c:** only the shooting sequence's four reads of 1487 return 1 while ND is active (sid 24 == 211 and 267 is 3 or
  4): judgeSeqATT 0x609351ba, the log snapshot 0x60935633, the shoot-info snapshot 0x6094b009 and the parts'
  continuous setup 0x60965c34. Everything else (AE, AF, UI, capture population, the stored setting) keeps the preset's
  0. No settings write is needed, and nothing outside AP Multiple Exposure with ND changes.
- **lnd_off:** the vtable slot 0x60b4ffac for `rcvTrig2KeyOffIn_TAKE_PICTURE_CONT` returns without stopping while ND is
  active. Otherwise it runs the stock handler with all registers intact. The base handler only calls the stop
  0x6094f064, which the frame-done handler also calls at N, so the release is just deferred to the N cap.
- **Hard stops** are all stock: the N cap in the frame-done handler, take-fail and operation-error handlers, and
  mode/menu/playback aborts of the sequence [I: not emulated].
- Why not write 1487 = 1 into the setting: that needs three settings-manager hooks (preset apply, the 267 change, and
  plane-1 containment for scene (207, 1), the one AP/SCN mode that doesn't force 1487).

**Popup labels [V].** The Number of Frames descriptors (36 B) have two lists: +12/+16 (row) and +28/+32 (popup:
0x611b7ac8 and 0x611c51bc). n2 extended only the first. n5 extends both, with kind-5 ND3/ND4 entries that keep the
"3f"/"4f" ids.

**Emulated** (`verify.py`):
- H: 320/320, including lnd_c at all four sites with 1487 0/1 × sid 24 × frames.
- R: 8/8, a `calls` through the real vtable word; the stock handler is reached with d0/d1/a0 intact unless ND is
  active.
- G: 7/7.
- D: 16/16.
- P: anti-brick, 794 B differ from v0.29a.
- Not emulated: the burst itself, the capture side at 3/4 continuous takes, and the popup.

**Camera test (0.30b6):**
1. AP Multiple Exposure, Number of Frames popup: Off/2f/ND3/ND4 all labelled.
2. ND4 in Single drive, one short press: 4 frames back to back, one combined file.
3. ND3: 3 frames.
4. 2f: stock behaviour (a press per frame).
5. During an ND4 burst, press MENU or Playback, or turn the dial: it stops cleanly. Battery-pull if it doesn't.
6. Check P still shoots normally.

**Open risks.**
- AF and AE run in single-shot mode for each frame of the burst, because only the sequence sees "continuous". Frame
  spacing is whatever the parts' continue loop gives.
- A long exposure × 4 cannot be cancelled by releasing the shutter, only by the mode/menu/playback aborts [I].
- Kind 5 in the popup is unproven. If the labels are blank again, use the "3f"/"4f" fallback (switch the entries to
  kind 4).

**n5 camera result (0.30b6) and what is known [V code, not yet resolved].** The popup labels work. One press does not
auto-advance: holding shows rec view, then grey until release, then live view, with no hang.
- The ME parts' full-press routine 0x6096a052 picks the path:
  - no CONTI → single (state 16);
  - CONTI with bit 0x40 or 0x10000 → "TakePicAutoStart" (state 15);
  - otherwise → the CONT take (0x6096b8bd, state 14).
  With lnd_c the CONT path is entered.
- entryTAKE_PICTURE_CONT (0x6096a1c7) has these gates before the next frame:
  1. (212,a3) must be 0;
  2. the base release check 0x6094ca4e must return 1 (0 on any of about 20 error codes, logged through 0x60930716) or
     it stops;
  3. the key state 0x61facd8c must be 4 (shutter fully pressed; set by 0x6095abda);
  4. count + overlay < (224);
  5. in `sendTakePictureContinue`, a new Bayer buffer from 0x6082f6b2 is required, else it silently skips the frame.
  The take limit 0x61facce8 (0x60950560: 1 unless brackets) applies only with attribute bit 2, so it isn't the cause.
- Grey-while-held fits gate 2 or gate 5 failing in AP ME, where the rest of the camera still has the preset's
  single-drive state. Which one isn't known; the emulator cannot run the sequencer.

## As built: 0.30n6 (patches/live_nd, 2026-11-09)

**Continuous drive for real while ND3/ND4 is chosen in AP Multiple Exposure.** n5's sequence-only lnd_c is removed (its
four sites are stock again). Sid 1487 itself is now 1, so AE, AF, the display, capture population and the sequencer
all agree, as with stock P + Multiple Exposure + Sequential.
- **Entry (lnd_pw):** the preset apply loop 0x602b9b53 writes each forced pair with `0x602cc122(sid, value)` at
  0x602b9b8a, with a0 = pair address. For the AP Multiple Exposure block's (1487, 0) pair it writes 1 when 267 is 3
  or 4, else the stock 0. 267 has already been restored from plane 1 on the dial path (0x602b3502 restore, then
  0x602b3509 apply).
- **Change (lnd_cb):** both sid-267 registry records (0x6043459c, 0x6043acf8) have their +24 change callback
  re-pointed. lnd_cb runs the stock callback 0x602b5407, then, if sid 24 == 211, writes 1487 = 1 for ND3/ND4 and 0
  otherwise, with the same primitive. Switching ND off restores the stock 0.
- **Containment (lnd_sv):** the mode-leave save 0x602b982a reads each value with 0x602cc0fc at 0x602b985f. For 1487
  while saving mode (211, 0), it returns the preset's 0, so plane 1 never holds an ND 1.
  - Every other plane-1 mode forces 1487 on entry except (207, 1), and that one now gets 0.
  - P/A/S/M restore plane 0.
  - So ND's continuous drive cannot leak.
- **Release (lnd_off, kept):** the release during an ND burst is deferred to the N cap.

**Gates re-read with real continuous:**
- **Buffer (gate 5):** `sendTakePictureContinue` allocates with 0x6082f6b2 (pool +292, else 0x6082f793), the same call
  as the single-shot `sendTakePicMultiExposure` (0x6096b8fc). Single-press ND4 already got 4 buffers on the camera.
  Nothing is continuous-specific.
- **Release check 0x6094ca4e (gate 2):** its AP-relevant input is attribute bit 8 (1493 == 3), and AP ME forces 1493
  = 0. The rest are generic busy, card and event checks.
- The n5 symptom (rec view, then grey) fits the half-spoof: the display and capture side ran single-shot rec view, so
  the release check refused the next frame [I].

**Emulated:**
- W/S/C 33/33: the real apply-loop instructions with a0 on the AP ME 1487 pair, another block's 1487 pair and a
  non-1487 pair; the real save-loop instructions with AP ME vs other keys and sids; a `calls` through both descriptor
  words (stock callback runs, then the 1487 write only when sid 24 == 211).
- H 240/240, G 7/7, R 8/8, D 16/16, and anti-brick (893 B differ from v0.29a).
- Not emulated: the burst, gate 2 at run time, and the screens.

**Camera test (0.30b7):**
1. In AP Multiple Exposure, set ND4 and give one short press: 4 frames back to back, one combined file.
2. ND3: 3 frames.
3. Set Number of Frames back to 2f: stock behaviour, a press per frame.
4. ND4 in AP, then dial to P: P shoots single frames (no continuous, no Multiple Exposure); back to AP, still ND4 and
   one press.
5. During a burst, press Menu or Playback, or turn the dial: it stops cleanly. Battery-pull if not.

**Open risks.**
- Gate 2 can't be evaluated statically for this state, and the burst is camera-only.
- The burst rate and AF/AE behaviour follow the drive settings the camera keeps for AP (now continuous).
- The (207, 1) containment depends on save running before that mode's restore (read from code).

## As built: 0.30n7, the safe floor (patches/live_nd, 2026-11-09)

**Camera on 0.30b7 (n6):** Single drive still needed a press per frame. **Sequential L took 2 frames, then left an
empty live view with AF indicators until reboot: a hang.**

**Cause, as far as the code shows.** With continuous on, the ME continuous route stopped after 2 frames. Stock AP ME
only ever runs 2 frames, and the limit wasn't found statically; a capture-side continuous limit is the likely place.
Stock ends a stalled continuous burst on shutter release: rcvTrig2KeyOffIn_TAKE_PICTURE_CONT → 0x60945a75 → stop
0x6094f064. n5/n6's release latch (lnd_off) ignored that release while ND was active, so the stall became permanent.
n5's grey-until-release had the same shape, and recovered only because the attributes there differed.

**n7 removes all of it:**
- the continuous writes (lnd_pw, lnd_cb, lnd_sv);
- the sequence spoof (lnd_c);
- the release latch (lnd_off).
Those 9 sites and words are byte-identical to stock again, and verify.py F checks that. Continuous drive stays what AP
Multiple Exposure's preset forces: 1487 = 0, whatever the drive menu says.

So **ND3/ND4 always take one frame per press, in Single and Sequential**. This is the behaviour seen on 0.30b5: ND4 in
Sequential L took 4 presses, combined, no hang.

**ND is now AP-only at capture.** The guards lnd_n, lnd_kn and lnd_a read:
- in AP Multiple Exposure: Off → 2 (as stock AP ME), ND3/ND4 as is;
- elsewhere: ND3/ND4 → 2, so P/A/S/M with a stored ND value shoots stock 2f, and P + Sequential stays the stock
  2-frame combination;
- 2f unchanged everywhere.
lnd_kg forces Auto Gain only in AP Multiple Exposure.

**One press is not shipped.** The continuous ME path's 2-frame stop isn't identified, and any one-press scheme needs to
defer or ignore the release, which is what locked the camera. Doing it safely needs that limit found first.

**Emulated:** H 240/240 (guards per mode), G 7/7, F 10/10 (floor), D 16/16, and anti-brick (739 B differ from v0.29a).

**Camera test (0.30b8):**
1. AP Multiple Exposure, ND4, Single drive: 4 presses, one file.
2. The same with Sequential L: still 4 presses, no hang.
3. ND3: 3 presses.
4. 2f: stock.
5. P (normal picture mode) with Number of Frames on ND4: shoots like 2f, including with Sequential L.

## One-press investigation after n7 (2026-11-09): not shipped

n7 stays the shipping default: one frame per press, no hang. Findings, so the next attempt starts from facts:

**1. The continuous ME route [V code, limit not located].**
- Path: the full-press routine 0x6096a052 → state 14 → entryTAKE_PICTURE_CONT 0x6096a1c7.
- Entry gates: (212,a3) == 0, the release check 0x6094ca4e == 1, key state 0x61facd8c == 4 (full press, set by
  0x6095abda), and count + overlay < (224).
- `sendTakePictureContinue` 0x6096b73c: frames = N, or min(N, take limit 0x61facce8) only with attribute bit 2. The
  new buffer comes from 0x6082f6b2, the same pool the single path uses.
- Frame done 0x6096af89 counts frames, posts 0x48000000 below N, and stops (0x6094f064) at N.
- The sequencer's continuous cap 0x61facce8 is 1 unless brackets (0x60950560). The base continuous limit (156,obj) is
  min(…, capture object +312) (0x60932177 ← 0x60888d43).
- Stock never runs this route with more than 2 frames (the Number of Frames validator was {0, 2}).
- The 0.30b7 stop after 2 frames is consistent with a capture-side continuous limit of 2, but its writer wasn't found.
- No stock path ends a stalled continuous burst except the shutter release, so **any one-press scheme on this route
  that defers the release can lock the camera** (0.30b7).

**2. The stock auto-next-frame mechanism [V code].**
- The base take-end routine (0x6094a560…) is the custom self-timer: when frames done (+196) < sid 469 (custom
  self-timer frames) it logs "CUSTOMSELF NEXT" and re-arms the self-timer (0x60945efa); at the limit it logs
  "CUSTOMSELF LAST".
- The ME parts overrides `transitSelfTimerEndOn_SELFTIMER_WAIT_To_TAKE_PICTURE` (0x6096af38) with the same single-take
  send a press uses (0x6096b80b).
- Self-timer waits are cancelled by the stock abort paths (`abortSelfTimer`: keys, menu, mode).
- So "auto re-press" exists in stock as custom self-timer. It is bounded by sid 469, takes no held key, and runs on the
  proven single route.
- **Not proven:** whether ME's own single-take-done handler (0x6096b023) reaches the base take-end routine, and
  whether AP ME allows custom self-timer drive (its preset forces several drive sids: 1493, 1489, 605, 405).

**Next step (a stock feature test, not a diagnostic build).** In AP Multiple Exposure with ND4, set drive to Custom
Self-timer with 4 frames and the shortest interval, if it is selectable.
- If the camera takes 4 frames and combines them, one-press needs no new capture code: Live ND could select that
  timer behaviour when ND is chosen.
- If it is greyed, or stops after 1 frame, the auto route needs sequencer state injection that can't be proven safe
  statically, and one-press should stay off.

## As built: 0.30n8, hold for N frames (patches/live_nd, 2026-11-09)

**Camera on 0.30b9 (n7):** with Sequential L in AP ME + ND4, holding took 2 frames back to back, then grey until
release. Releasing recovered normally. So the stock continuous ME route does run in AP ME, despite the preset's
1487 = 0.

**The 2-frame limit [V code]: the stock route requests one continue only.**
- The full press sends frame 1 (0x6096a052 → 0x6096b8bd).
- entryTAKE_PICTURE_CONT sends one `sendTakePictureContinue` (0x6096a328), which is frame 2.
- Each continuous frame done (0x6096af89) counts the frame. Below N it only sets the status flag 0x48000000 through
  0x60947b55, which is a flag helper (0x40000000 = set), not a state transition, so nothing requests frame 3.
- With stock's maximum N = 2, that is complete, so stock P + ME + Sequential is 2-frame by design.
- What it is not:
  - capture +312: that is remaining shots (0x602d3a7e → 0x60bd1f44, or 100);
  - the take limit 0x61facce8: only with attribute bit 2;
  - the buffer pool.

**n8 = n7 plus one hook, lnd_cont.** It replaces the frame-done flag call at 0x6096b019 (`call 0x60947b55,[d2],4`).
It makes the stock call first. Then it issues the stock `sendTakePictureContinue` (0x6096b73c) only when all of these
hold:
- AP Multiple Exposure (sid 24 == 211), and 267 is 3 or 4;
- the shutter is still fully pressed (the stock key state 0x60955fa2 == 4, the same test the CONT entry uses);
- (212,parts) == 0, as the entry checks;
- the stock release check 0x6094ca4e returns 1, as the entry checks.
`sendTakePictureContinue` requests nothing once the ME controller holds N handles (0x61facca4 via 0x6091a480; 5-slot
array, N ≤ 4). At frame N the stock frame-done handler stops (0x6094f064) and combines.

**Release handling is completely stock:** no latch, and the vtable, 267 callbacks and 1487 are untouched (F checks
this). Releasing mid-burst stops it as today. If any condition fails, nothing is sent, and the state is the verified
0.30b9 one, recoverable by releasing.

**After a release at 2 of N (today) [I, read from code, not camera-checked]:** the burst stops and the ME parts goes
back to standby with 2 frames registered. The remaining frames come from further presses (single route), and it
combines at N, as in the press-per-frame case.

**Emulated:**
- B 18/18: the real tail 0x6096b012..0x6096b020 with stand-ins. The flag call always runs; the continue only for AP ME
  + ND3/ND4 + key 4 + (212) == 0 + release-check 1; d2/a2/sp equal v0.29a.
- H 240/240, G 7/7, F 10/10, D 16/16, and anti-brick (836 B differ from v0.29a).
- Not emulated: the burst itself and the combine of 3/4 continuous frames.

**Camera test (0.30b10):**
1. AP ME, ND4, Sequential L, hold: 4 frames back to back, one combined file.
2. ND3: 3 frames.
3. Release after 2: it stops cleanly, as on 0.30b9.
4. Single drive: a press per frame (n7 floor).
5. 2f with Sequential L: stock 2 frames.

**0.30b10 (n8) camera result and Seq L [V code, gate not identified].** One press works and is reliable in Sequential
H. In Sequential L it usually stalls at 2 and recovers on release. In Seq L, one of lnd_cont's gates is false when the
frame finishes:
- the key state 0x61facd8c: rewritten by the key-kind handlers 0x6095ab89/abac/abda/ac08 with kinds 1/2/4/8; Seq L
  does AE/AF between frames;
- the pending-operation code (212,parts): written by 0x6095180d, 0x6095ddd0 and 0x60963a7d;
- the release check 0x6094ca4e.

Why there is no fix yet:
- **Retry points:** `rcvRecordingDoneIn_active` (0x6096ac96) does nothing in the continuous state ("not case"), and ME
  frames are not recorded individually. No confirmed later per-frame event was found.
- **Replacing the key gate with "stop not requested" (bit 0x8000 at parts+464) is not safe.** The stop 0x6094f064
  sets it only on its 0x6094f9bb branch; the 0x6094df27 branch tests a different object. A continue could follow a
  release, which is the 0.30b7 hang shape.
- **A Seq H redirect** means spoofing the drive-mode setting, which AE, AF, buffers, display and UI read: the n5
  inconsistency class.

**Single drive + hold:** Single never enters the continuous state, so this mechanism doesn't apply.

**Recommendation for now:** use Sequential H with Live ND. n8 is unchanged.
