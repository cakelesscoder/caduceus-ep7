# Lens shading correction on COLOR profiles (sector 8 VigFix): investigation, stalled (2026-11-13)

**Status: no fix built.** The code does not show why COLOR stills would skip lens shading correction, so there is
nothing safe to switch on. This note records what was traced, what was ruled out, and the camera tests that decide the
next step. [V] = disassembly, bytes or emulator. [I] = inference. Static work on the stock 1.1 main plus one emulator
probe of the real stills runner.

User report (v0.31d, 25/1.8, 15/1.7, 42.5/1.2 wide open): i-Enhance corrects vignetting; COLOR1-4 never do, with
Extras sector 8 on either Camera or Off.

## 1. Where the correction comes from

**Capture side (front end).** This is the only place the menu setting reaches.
- [V] Key 0x8c21 (Shading Comp., sid 61) has **five** reads, not the four in VIDEO_HIDDEN.md §5. The fifth is
  `0x605554bc` in `0x6055545e`, a twin of R2 (`0x602ab42d`). v0.25 already redirects all five to `sc_get`
  (`patches/v025/build.py` SITES), so the earlier miss had no effect on the build.
- [V] R2 and R5 build the still-capture command. If the capture-mode record allows it (`0x60555739`, table
  `0x6055ca20`: +4 bit 3, set on the still ids 0x1xxxx, clear on live view 0x2xxxx and on the 0x90000 sensor check)
  and the key reads 1, they OR **0x2000** into cmd+4.
- [V] R3 and R4 (key == 1) run `0x602a79ef`, a front-end command. It has the same 0x2000 bit and outputs into the
  capture object: cap+0x1326 (64 u16), cap+0x13b0, +0x15f0, +0x1650, +0x384a, +0x5da0. The still-capture builder
  `0x602a529f` passes the same pointers (cmd+0x1bc..+0x1d8).
- [V] The RAP block list (`0x602325b4`) has `RAP_SHADING_SETTING` and `RAP_CIRCLE_SHD_SETTING` (and `_2` copies).
  [I] Circle shading is the lens vignetting block, programmed at capture time from the flag and tables above.
- [V] Nothing on this side reads the picture mode. The capture-mode id comes from `0x602a65bd` and the shooting-mode
  byte cap+0x60c8, not from COLOR/i-Enhance (cap+0x5df5).

**Development side.** One stage uses the lens table, and it rarely runs.
- [V] `0x6039e54e` (from the stage list `0x603397e0`, gate `0x60339b8e`): on a kind-0 request with request+0x6fc
  set, it builds a 64-entry radial gain from request+0x67c into bank+0x404/+0x484 and sets bit 4 of bank+0xc.
  Otherwise the gain is flat (0x2000). Path: cap+0x1326 → params+0x18b4 → request+0x67c, and cap+0x13b0 →
  params+0x1934 → request+0x6fc (`conv_still`, `request_pack`). Plain copies, the same for every key.
- [V] The gate needs request+0x668 ≠ 0. Only the multi-pass branch of the default dev entry (`0x60366f21`,
  job+0x2c4a ≠ 0) writes it. job+0x2c4a comes from the job+0x2c20 callback `0x60355ebe` → `0x603a2ec6`. That decision
  uses ISO buckets (tables `0x60505280` / `0x6050528c`). The key only matters for two art keys and 0x0200008f/0x020003e8,
  so **key 7 (i-Enhance) and key 11 (COLOR) decide the same way**. Key 12 (MONO) never gets the callback.
- [V] Emulator: with the synthetic request used by the grain verifiers, the stage does not run for either key
  (request+0x668 = 0), as the code predicts.

## 2. COLOR-specific paths checked, none of which drops the correction

| Candidate | Finding |
|---|---|
| Creative shading, job flag 0x80000 (keys 9/11/12, `job_ctor` 0x60353bcf) | [V] Modifier `0x6035b03f`: level 0 gives effect 0 and gain 0x400. **Emulated runner, key 11: a 128 × 128 mask descriptor at request+0x214 with effect 0 gives a bank byte-identical to no mask.** Level ±1..5 changes 39–43 words. At level 0 it neither adds nor cancels a radial gain |
| `request_pack` gates request+0x742 on 0x80000 | [V] Its source params+5556 is never written on the stills path (only by the RAW-edit builders `0x6030e9d1`/`0x60324071`), so it is 0 for every key |
| Job flag 0x10000 modifier `0x6035b105` (mask, effect 0xfe00) | [V] Cleared for stills in `art_effect_to_flags` (0x603eabd0). No stills path sets it |
| Second mask cache `0x6036b564` | [V] Key 0x01010076 only, fixed ROM tables |
| Work list (`worklist_build`) | [V] 0x80000 fills the dev entry's modifier slot; later modifiers fall back to their own entries. No entry is dropped |
| Our layers | [V] No v0.32 edit touches the capture command, the RAP tables, request+0x67c/+0x6fc/+0x668 or the stage above. Edits in the capture/dev ranges are WB, aperture, NR, sharpness, Live ND, grain, bloom/clarity, tone and HSL hooks. `sc_get` passes the real getter value through when slot +49 is 0 |

So with sector 8 on Camera, a COLOR shot gets the same capture command as i-Enhance [V]. If the correction is
front-end [I], it cannot depend on the picture mode. That conflicts with the report, and the camera tests below are
meant to settle it.

## 3. Why no patch

The task was "make sector 8 follow the camera on COLOR". `sc_get` already does that at every reader of the setting.
No other switch was found that COLOR misses and i-Enhance gets. Forcing the dev stage on (request+0x668 / +0x6fc)
would mean starting the multi-pass branch, its buffers and its NR on every COLOR shot. That is a pipeline change, it
is not what i-Enhance does at low ISO, and it is unsafe without evidence. Under the task's rules, this stops here.

## 4. Camera tests that decide the next step

Same lens wide open, blank evenly lit wall, fixed exposure (M), base ISO, **RAW+JPEG**:
1. **Menu baseline:** i-Enhance with Shading Comp. On, then Off. Do the JPEG corners change? Do the ORF corners
   change? (Open the ORF in a converter with lens correction off.)
   - ORF changes → the correction is in the front end, so in every picture mode. Go to test 2.
   - Only the JPEG changes → the correction is in development. That stage was not found. Send the pair; the next
     target is the dev path, not the capture side.
2. **COLOR baseline:** a COLOR profile with the Stock look (slot +49 = 0, no other edits), Shading Comp. On, then Off.
   Compare with test 1.
   - Corners change like i-Enhance → the profile path is fine. The report comes from look content (tone curve,
     contrast, split tone or highlight roll-off making the fall-off look stronger), not from correction. Check
     sector 8 Off against Camera on the same look.
   - Corners don't change → a stock or Caduceus difference this trace missed. Repeat test 2 on stock firmware
     (restore package) to see which.
3. **Sector 8:** the same COLOR look with sector 8 Camera, then Off. With test 1's lens showing a change, Off must
   match Shading Comp. Off.

## 5. Small findings for the record

- VIDEO_HIDDEN.md §5.1 says "exactly four reads"; there are five (`0x605554bc`). The v0.25 build lists five.
- The radial-mask builder `0x60338d49` serves four generators: creative 128 × 128 (`0x603390a4`, table
  `0x604ebf1c`/`0x604ebf9c`), a fixed 96 × 96 × 4-plane art mask (`0x6033901b`), and two art paths (`0x60339146`,
  `0x603391c5`). None take lens data.
- Atlas entries: `tools/atlas/new_vigfix.py`.
