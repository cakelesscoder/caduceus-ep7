# Work log

Every step, check and decision, newest last. "Verified" = checked by hash or reproducible command.

## 2026-11-01 — Step 1: setup, stock firmware, decode, toolchain

- Supplied archives `reference/om-c-firmware-dbv0.3.0.{zip,tar.gz}` contain only a 15-byte README. Not usable source.
- Basis chosen: fishcu/oly_fw_analysis @ `539fcf1` (submodule `external/`). No licence → referenced, never copied.
- Stock fw: OM catalog (model 1420) offers only v1.1 / build 1100, dated 2022-02-28.
  Downloaded via `tools/fetch_stock.sh`. **Verified** SHA-256 `9d1610…eaeb` = fishcu's reference.
- Project moved from `/mnt/Storage` (NTFS/fuseblk) to `~/projects/ep7-firmware` (btrfs). Toolchains live in `~/ep7fw-toolchains`.
- Decoded with fishcu `oly_container.py` (reviewed first: pure Python, no I/O beyond files).
  **Verified**: exact decode→encode round trip; all 5 component hashes match fishcu's inventory
  (`docs/ep7_1100_components.sha256`). Main CPU base `0x60020020`.
- **Verified** SD updater strings in main: `DCOLYMP/E142????BIN` (body), `S142????BIN` (boot), `G142` (unknown) at decoded `0xf0cb04..`.
- Toolchain: `tools/setup_toolchain.sh` (binutils 2.45 mn10300-elf, GNU sig checked).
- Component roles identified (docs/FINDINGS.md). HSL needs main (0x100) + likely OSD (0x101) for the "Value" graphic, as on PEN-F.
- Toolchain built: binutils 2.45 mn10300-elf in `~/ep7fw-toolchains/mn10300/bin` (GNU signature verified by gpgv).
- **Verified** CPU mapping (base 0x60020020) + fishcu's E-P7 colour addresses: builder 0x603b0068 uses record
  offset 688 and ends `mov d0,(976,a0); retf` at 0x603b024b–0x603b024f, matching their records/control offsets.
- Added `tools/dis.sh` (disassemble by CPU address). **Step 1 complete.**

## 2026-11-01 — Step 2: desktop sims
- Emulator: fishcu MN103 sim built from git commit 87ffb882 (gitiles tarball hash not reproducible; commit + pristine
  file hashes verified; regenerated strict patch byte-identical). fishcu synthetic checks: 50/50 pass.
- `tools/ep7_color_table.py`: E-P7 COLOR table extracted; **verified** SHA `a33d64bd…` = fishcu shared-table hash.
  Records: word0 = sector centre angle, word1 = width, +14 = sat amplitude; per-sector +/- gains.
- `sim/pipeline.py`: ORF→LibRaw linear→tone curve→12-sector engine (firmware angles/gains)→grain→crop.
- `sim/calibrate.py` vs 12 camera JPEGs (testdata, gitignored): colour-only median dE76 ~1–6 (mean 3.1 on CP shots).
- `sim/diff_test.py` Kodachrome(1063) vs warm(1064) same scene: per-hue chroma-ratio error 0.31 without sector
  model → 0.13 with it (corr 0.86). Engine reproduces the camera's Color Profile behaviour approximately.
  Defaults chosen: angle_offset 15°, sat_scale 1.5, base_chroma 1.1 (fitted; not firmware facts).
- `sim/film.py`: recipe renderer limited to camera-feasible controls (stock + planned HSL/grain/vignette).
  Base curve `sim/base_curve.json` = median of 12 fitted camera curves (consistent in shadows/mids).
  Tone-step model cross-checked: 1063 vs 1064 shadow delta ≈ 0.012 luma/step, matches TONE_STEP model.
  Grain scaled for preview size; hue step 5.5°/step is a placeholder pending camera test.
- `tools/build_package.py`: component-selective package + stock restore with stock-byte checks.
  **Verified**: no-op package == restore == exact stock slice; wrong-expect and overlapping edits refused;
  1-byte main+OSD test package re-parses with valid checksums (test output deleted; never SD-named).
- Research agent: `docs/FILM_SIMS.md` (Fuji sim anatomy, 75 sources) + `sim/recipes/fuji_like.json` (10 recipes,
  derived from Fuji's published F-Log2 LUTs relative to Provia). Untested starting points.
- film.py: Monochrome Profile filter mixing (Acros). Contact sheets in generated/film/.

## 2026-11-01 — Step 2: OSD resources (component 0x101), offline

- Added `tools/osd_extract.py`, `sim/ui_mock.py` (+ `sim/screens/*.json`), `docs/OSD.md`. Read-only; hash-checked inputs.
- **Verified**: bank 0 base `0xa3091000`, bank 69 base `0xa3611000`, string base `0xa407f540` (all unique by structural search).
  All 5514 bitmaps (modes 11/10), 245 symbols (mode 1) and 34 font resources (mode 9) decode strictly; visually checked.
- E-P7 8-bit bitmaps are mode 11 (12-bit tokens), not PEN-F mode 3 — PEN-F bitmap patches need re-encoding.
- Palettes: 58 ARGB blocks in main `0x61110a74..0x6111f03c`; render candidate `0x61110e7c`/`0x6111570c` — runtime selection unverified.
- Colour wheel not a bitmap; C3D-drawn (strings `BackGroundCtrl::drawC3dAsync`). Mock wheel is procedural.

## 2026-11-01 — Step 2: PEN-F HSL → E-P7 port mapping (offline)

- Mapped all 153 PEN-F `main_ranges` to E-P7 candidates: `patches/hsl/ep7/port_map.json` (stock bytes read by
  `tools/ep7_port_map.py`; `--check` passes). Write-up: `docs/HSL_PORT.md`.
- **Verified (emulator, `tools/ep7_color_probe.py`)**: builder 0x603b0068 record layout; selector 0x603b0252 runs natively;
  5-byte jmp at 0x603b02d9 → stub → rejoin 0x603b02de works with E-P7 job offsets (request job+11364, records +14576 ×56,
  callback 0x60355fd4, trailer job+15488). Stub exists only in emulator RAM.
- Code-space audit `tools/ep7_code_space.py`: descriptor table 0x60027068, loader 0x600457e7; 8 FF suffixes inside loads.
- No firmware image built, nothing flashed, nothing committed.
- **Independent check of HSL-port agent (me):** hook 0x603b02d9 = `cd8ffdf060` call 0x603b0068 (COLOR builder),
  preceded by `mov 0x6051de2c,a0` (COLOR table). Section table 0x60027068 + end getter 0x60045786 decoded:
  section 2 = 0x60280800..0x6055e800 (contains builder); tail 0x6055e5b0..0x6055e800 all FF, no abs32 refs. Agrees.
- UI agent: `tools/osd_extract.py` (5514/5514 bitmaps, 245 symbols, fonts), `sim/ui_mock.py` + screens, docs/OSD.md.
  E-P7 uses RLE modes 9/10/11 (no PEN-F format 3) → "Value" graphic must be re-encoded. Colour wheel is runtime-drawn.

## 2026-11-01 — Step 3: minimal fixed-H/L patch (offline)
- **Verified (me)** section loader: table 0x60027068 + end getter 0x60045786 → section 2 = 0x60280800..0x6055e800.
- `patches/hsl/ep7-fixed/`: recipe → 5-byte hook (0x603b02d9 `cd8ffdf060` → `jmp 0x6055e5c0`) + 116-byte routine
  (re-issues builder call, inline 16-byte frame, writes hue/L of 12 output records from a constant table, jmp 0x603b02de).
  Native values: H = -1000*slider, L = fishcu LUT; physical record order r ↔ UI 2*(r%6)+r//6.
- `tools/ep7_verify_package.py`: builds the package in memory and runs the native selector from the PATCHED payload
  vs STOCK in the emulator. classic_neg: **PASS** at 4 saturation sets (H/L exact, sat + all other output bytes ==
  stock, ctx == stock, stack/callee-saved OK); 109 changed bytes all inside edit spans.
  Mutation tests (offset 706→708, loop 12→11, stack 16→12): all detected (FAIL).
- Scope limits: emulator covers CPU code only, not the ISP's pixel response, live-view path, or the alternate
  builder 0x603afb94. On-camera H/L direction/scale unverified.
- docs/FEATURE_GAPS.md (me): string + code survey. Key find: recording-duration routine 0x60319139 identical in shape
  to PEN-F 60566309 (1740 s @0x60319156, 7200 s @0x6031915b) → 4-byte port candidate with precedent.
  Code strings for HIGH_RES/pixshift, pro_cap, focus_bracket, C4K exist in main; menu has Flat picture mode.
- ui_mock: image background (live-view stand-in from film renders); screens xpan_live, hsl_live. Aspect crop previews in generated/aspect.
- Independent review (agent, docs/REVIEW_fixed_hl.md): **no blockers, no code defects**. Verdict "not yet":
  H1 E-P7 SD update trigger/acceptance untraced (updater in section 6 ~0x60c96xxx; skips 1 MiB blocks equal to
  flash) → recovery path unproven. H2 main-only packages require camera already on 1.1.
  Medium: power loss mid-write in section 2 (runs at boot before updater); ISP H/L interpretation unverified.
  Confirmed: hook boundaries/liveness, routine bytes, code-space load + no integrity scan, package == stock metadata.
- Next: trace E-P7 SD updater entry + acceptance rules; then a restore-only dry run on camera (user go-ahead needed).
- SD updater trace (agent, docs/SD_UPDATE.md; probe 19/19 PASS): client task 88 FIRMUP_CLI 0x60c95bab → server
  task 18 FIRMUP_SRV 0x60c96030. Accepts model 0x1420 + valid checksums; version NOT checked (same-version /
  main-only OK); all components validated before any erase. Main = full erase+program (corrects review: 0x100000
  is a BOOT type flag — spot-checked by me: `cmp 1048576,d0` on stack arg at 0x60c971ea). LED-only feedback.
  Trigger (button combo) NOT found in main — likely pre-main/sub-CPU. FIRMUP_SRV started only in normal startup
  after section 2 init → a boot-breaking section-2 fault likely makes SD recovery unreachable.
  Safe trigger test: checksum-corrupted restore copy (rejected before erase).

## 2026-11-01 — Step 4: unlock push
- Saved `releases/v0.1-fixed-hl-classic_neg/` (sources + hashes committed; .pkg.bin local only).
- `patches/rec_limit/`: recording-duration routine 0x60319139 (entered via `calls`, ret [d2],28) — operands
  @0x60319157 (1740) and @0x6031915c (7200) → 32400 s. Emulator: native routine patched vs stock, modes
  3/6/8/9/4 all return 32400 s with ret 0, stack/regs intact. **PASS.** Chapter/file/thermal limits untouched.
- `tools/merge_specs.py`; v0.1 + rec_limit combined: fixed-H/L verifier still PASS, 113 bytes changed, all in spans.
- Agents running: film-look research (bloom/halation), colour-grain RE, video-log research (verdict before code).
- Aspect tables found: 9 still aspects in code (5:4, 7:6, 6:5, 7:5 hidden) + 17:9 entry; XPan/21:9 via repurposed hidden slots (FEATURE_GAPS.md).
- Aspect menu mask: simple value-list search (ids 1,2,3,4,9 / codes) found nothing specific → needs schema/menu trace (queued).
- Profile bundles design (docs/PROFILE_BUNDLES.md, bundles/example.json): per-COLOR-slot HSL/grain/WB/effect table; blocker = active profile index at hooks.
- Issues #11 rename profiles (OSD strings + badges), #12 more slots (hard; alternatives listed).
- Decisions: no build-time rename (#11); MONO1–4 become universal bundle slots → 8 slots (#12).
- Film-look agent: docs/FILM_LOOK.md, sim/effects.py (halation, bloom, grain_v2, film_curve, subtractive_saturation,
  color_chrome), sim/recipes/film_look.json (cinestill_800t, portra_400_bloom, classic_neg_halation).
  Findings: no Fuji film sim has halation/bloom (only X-Half film filters); GFX glow ≈ diffusion filter or post.
  E-P7: bloom ↔ Soft Focus (FANTASIC_FOCUS) blend; halation plausible (highlight mask + tint + blur) but unproven.
  **Verified (me):** all 10 fuji_like recipes render byte-identical vs pre-agent film.py; synthetic halation/bloom look correct.
- Profile-index agent (docs/PROFILE_INDEX_WB.md): settings 908 = active COLOR profile (key 63153), 973 = active
  MONO profile (key 63281), getter 0x6005e971(key,idx,a0=0). Capture population stores profile byte at
  capture+24083 (mode 11→COLOR idx, 12→MONO idx). **Verified (me)** at 0x602a859c–0x602a85c0.
  Not transported into job/request → hook can't see it yet. Design: job +1 byte (constructor edits 0x603537f0/
  0x6035390c) + converter hooks 0x603e669f/0x603e91e4; getter fallback for live view. MONO splits at 0x603b02c1.
  WB fine-tune: candidates settings 324/325, 329/330 — unresolved.
- Colour grain (agent, docs/GRAIN_PORT.md): 3 gates (converter copies grain only for mode 12; work-list gives COLOR
  no grain pass; combiner selector maps 0x0901/0x0902 only for key 12). Approach B built: hooks 0x6035749f,
  0x603b5249 + 123 B @0x6055e680–0x6055e6fa; COLOR gets MONO's single-pass grain (combiner 32, gain 50/75/100).
  **Re-run by me:** tools/ep7_grain_verify.py all PASS; merged v0.1+grain+rec_limit = 7 edits / 243 B, H/L verifier PASS.
  Main unknown: combiner 32 never used on full-size stills in stock (possible size limit) — on-camera test needed.
- **Video log (agent, docs/VIDEO_LOG.md): hidden log modes found.** Movie picture-mode ids 2000/2001 (settings byte
  +925 = 1/2 via 0x60349297) with own gamma tables 0x604f4278 / 0x604f4478, identity luma curve, picture params
  zeroed (same lock-out OM uses for Flat/OM-Log400). id2001 = true log: ~12.4%/stop, within 0.8% of pure log over
  1–6 stops below clip, linear toe. Precedent: E-M1 II (TruePic VIII) got OM-Log400 via fw 3.0.
  **Verified (me):** probe passes; independent read of tables: default 100/88/67/46/27/15/8/4/2 % vs
  id2001 100/88/75/63/50/38/27/18/10 % at 0..8 stops below clip.
  Open: X1 who writes +925 (menu/setting), X2 movie frames use this builder. No patch code yet (per user).
- WB/MONO agent (docs/WB_AND_MONO.md): WB fine-tune = per-WB-mode s8 arrays (keys 0x84F9 A-B, 0x9679 G-M, 20 modes;
  CWB none). Per-profile override = redirect all 16 getter call sites to 166-B stub @0x6055e700. **Re-run (me):**
  wb probe S/W/G PASS; mono probe PASS. LV coverage inferred, not proven. MONO→colour needs 3 hooks
  (selector 0x603b02c1, chroma 0x603b134e, filter guard 0x60353db9); chroma stage 0x603b132a makes grey.
- docs/CODE_SPACE_MAP.md: allocation registry for all patches.
- SD mod loading design (docs/SD_MODS.md, user idea): data-from-card first; remove card = stock.
- v0.2 bundles (agent, docs/V02_BUNDLES.md): job +24 B, converter stubs copy profile/mode/marker, 8×64 table @0x60210900
  (section-1 tail). **Re-run (me):** tools/ep7_verify_bundles.py overall PASS (A/B/C/D + 19 mutations). Risk: profile
  stored as 1–4 assumed (check COLOR1 isn't stock on camera); live view shows stock H/L.
- Bloom (agent, docs/BLOOM_HALATION.md): Soft Focus = job flag 0x80 (shrink 160×120 → upscale → combiner 11 linear mix).
  Patch: 2 hooks + 51 B @0x6055e7b0. **Re-run (me):** ep7_bloom_verify T1–T5 PASS on merged build (10 edits/304 B).
  Halation: design only (per-channel controls; true red tint not possible). Risk: blend input order → test strength 1.
- Aspect (docs/ASPECT.md, patches/aspect): setting 270 ↔ key 0x3081; menu = option list {270,6,0x6117a834} (4:3,16:9,3:2,1:1,3:4,17:9);
  ratio code (H<<8)|W. Repurposed id6 → XPan 5184×1912 (0x1841), id7 → 21:9 5184×2224 (0x0915) across 44 tables + 6 sec-5 switches;
  list relocated to 0x61242f00 ("Panorama"/"Wide" labels), case blocks 0x60210f00. build.py: 136 checks PASS, 101 edits/950 B.
  Open: 17:9 menu filter, icon-miss path (ids 6/7 have no icon), LV grid selector, art/bracket paths.
- Log video (agent): no hidden menu; option A code patch: hook 0x6030df3d → 42-B stub @0x60210c90; movie + Muted →
  +925=2 (log id 2001). Emulator PASS (stills unaffected). Muted = picture-mode id 3 inferred.
- Aspect (agent, docs/ASPECT.md): setting 270, menu list 0x6117a834 → new 8-entry list; id 6→XPan 5184×1912,
  id 7→21:9 5184×2224 (labels reuse "Panorama"/"Wide"). 101 edits; 136/136 checks PASS. Risks: icon miss, 17:9 filter.
- merge_specs: namespaced per-patch metadata. **v0.3 candidate (me):** all 6 merged = 117 edits / 1,674 B;
  bundles 75/75, grain 5/5, bloom 5/5, video_log, aspect PASS. Saved releases/v0.3-candidate (pkgs local only).
- Saved v0.3 (releases/v0.3, git tags v0.1/v0.3). Status page v2 published. Agents: v0.3 review, WB patch build, MONO-colour build. SD-loader agent stopped (brief truncated); SD loading paused.
- MONO-colour agent (interrupted before implementing): mono filter = 3×3 matrix id via guard 0x60353db9 → request+1802
  (selector 0x603acfe4); toning in chroma stage 0x603b134e; selector redirect needs 6 bytes at 0x603b02bf → 0x603b02d9;
  H/L hook must accept mode 12; candidate code space section 7 tail 0x61378c68–0x61379000; MONO grain/shading still run.
- **v0.3 review (agent, docs/REVIEW_v03.md):** no structural defects; not cleared as combined build. H1 grain hook skips stock job-type check (0x6035778b) → fix. H2 grain+bloom on every COLOR shot, no off switch. H3 aspect persists at boot. H4 restore unproven. M1 aspect heights → round to 16. Test order: rec_limit → log → bundles → grain → bloom → aspect → combined.
- Step-0 camera kit (releases/step0-kit): corrupt trigger-test + exact stock restore; corrupt copy fails additive checksum; native validator rejects bad checksum with 0x3211 / 0 writes (USB + SD modes).
- Per-profile WB (agent, docs/WB_PATCH.md): 164-B stub @0x6055e700 + 14 getter redirects (RAW-dev sites stock). Merged v0.3+WB 132 edits/1890 B: bundles, grain, bloom, WB (20/20 mutations) PASS. LV unproven. Example recipes carry wb_shift → applied when override set.
- **Camera step 0 (user, 2026-11-01):** fw 1.1 confirmed. OK+power starts SD updater. Corrupt file: ~15 s solid → fast blink (rejected, as predicted). Stock main-only restore: identical ~15 s solid → fast blink = REJECTED, nothing written; camera boots fine on 1.1. Battery ~50%. Emulator modelled only the validator → real path has an extra check. Agent tracing (docs/SD_REJECT.md).
- SD looks loader (agent, docs/SD_BUNDLES.md): fopen/fread API found (FILECLBK task 16); hook at media 'MOUNT OK' 0x60863e90; 564-B loader @0x61242a00 reads C:\EP7MOD\BUNDLES.BIN (CRC/range-validated) into table 0x60210900. **Built, NOT emulator-verified yet** (WIP). Desktop writer tools/ep7_bundles_bin.py.
- SD reject trace (agent, partial): validator ACCEPTS exact stock main-only on real bytes (mode 0 → 1 write 0x806a0000 size 0x1900000, chained emulation); server E-path has no date/version/size checks. Rejection likely pre-erase guard in flash writer (battery?) — tracing. Same 15 s solid for both files ≈ file read time → nothing erased.
- SD reject (agent, docs/SD_REJECT.md): no visible check rejects stock main-only; no battery check on E path. Hypotheses: OK+power isn't task 88; file read truncated; misread blink. Zero-write tests: T1 no E-file, T2 tiny corrupt E-file (timing), T3 full battery.
- MONO-colour (agent, docs/MONO_COLOUR.md, patches/mono_colour): bundle slot +32 `colour` (==1) / +33 `sat[12]` (−5..5);
  hooks 0x603b02bf (selector → COLOR builder with slot sat + slot H/L, own copy of v0.2 hl logic so v0.3 merges unchanged),
  0x603b134e (chroma a0=0, MDR restored), 0x60353db9 (params+5528/5529 = 0, merge skipped); 764 B @0x61378c80 (sec-7 tail).
  tools/ep7_mono_colour_verify.py on v0.3+mono_colour (121 edits/2438 B): 213/213 + 20/20 mutations PASS; demo bundle
  bundles/mono_colour_example.json R test PASS. ep7_verify_bundles now maps the sec-7 tail. Grain/bloom/bundles verifiers
  PASS at HEAD versions; working-tree versions are mid-v0.4 rewrite (not v0.3-compatible). Open: MONO grain/shading,
  0x60367ee3 skipped pass, LV stays mono, EXIF Monotone.
- Review fixes (agent): H1 grain job-type check (T6 77 rows), H2 grain/bloom per-slot & off by default (bloom_flag uses capture bytes), M1 heights ×16. v0.4-candidate merged 117 edits/1,969 B, all verifiers PASS.
- MONO→colour (agent, docs/MONO_COLOUR.md): 3 hooks (0x603b02bf, 0x603b134e, 0x60353db9) + 764 B @0x61378c80 (sec 7). Slot +32 colour, +33 sat[12]. 213/213 tests, 20/20 mutations on v0.3+mono. Needs re-verify on v0.4 merge.
- Full merge (agent): v0.4 + WB + MONO-colour + SD loader = releases/v0.4-candidate/edits_full.json, 138 edits / 3,504 B. All 9 verifiers PASS (SD: 173 cases + 7 sequences + 17/17 mutations). Open: section-6/1 RAM writability for loader state + table.
- **REVIEW_v04:** no code defects; B1 blocker = no proven install/recovery path. H1-new SD loader hook dead (confirmed by me at 0x60863e4f/0x60863e62) → excluded. Saved releases/v0.4 (no SD loader), tag v0.4.
- **Buttons (agent, docs/BUTTONS.md, patches/buttons):** buttons = settings whose value is a function code; menu/stepping read the
  static validator lists (0x604cc98c, no availability filter for button sids); dispatcher 0x60cc872f maps key->sid->code->action
  (55-entry table 0x60f38af8) with no per-key check. Arrow right/down = sids 51/53 (8 codes), up/left 50/52 fixed (no list).
  **Built** data-only, 10 edits/100 B in place (sec 2): sids 47/48/49 -> 23 codes (+Multi Function, ISO/WB, HDR, BKT, Level, ...),
  arrows 51/53 -> 16 codes (+ISO/WB, WB/ISO, Peaking, Magnify, Level, tele-con, Multi Function, RAW). tools/ep7_buttons_verify.py
  S/V/N/A/M PASS. Merge releases/v0.5-candidate/edits.json (v0.4 + buttons, 146 edits/3,005 B): bundles, grain, bloom, WB,
  MONO-colour, buttons verifiers all PASS. Queued: profile-slot select (no function code exists), ISO/WB-only, up/left, movie arrows.
- Aperture ring (agent, docs/APERTURE_RING.md): port of fishcu PR #4 with E-P7 fix (81 E3 kind 4/5 → parse rule (kind&2)==0). 6 edits/223 B; dispatcher 1921/1921, parser 600/600, AE 298/298, 8/8 mutations. Merges with v0.4 (142 edits), other verifiers pass. Risks: section-1 RAM write, Panasonic ring word from PEN-F reports only.
- Camera: official full 1.1 file w/ FULL battery → same solid (1–2 min) then ~2 Hz blink. fishcu PEN-F INSTALLATION.md: 'blinks rapidly on completion' = SUCCESS → our fast=fail inference likely wrong; updates may have succeeded (invisible: same firmware). Probe: OSD-only package (7 bytes, Setup 'Firmware'→'FIRMWARE'); emulator: OSD-only accepted, writes only OSD region. build_package now allows OSD-only.
- **CAMERA PROOF (user):** OSD probe flashed via SD (OK+power) → Setup shows 'FIRMWARE'. ⇒ SD updater writes; ~2 Hz blink after solid = SUCCESS (code-derived fast=fail was wrong). Earlier stock main-only restore + official full reinstall therefore also succeeded (camera fine on 1.1). REVIEW_v04 B1 resolved: install + recovery path proven.
- v0.5 = v0.4 + buttons + aperture ring: 152 edits / 3,233 B; all 7 verifiers PASS (background run).
- **TEST 1 PASSED (camera):** rec_limit flashed via SD; movie remaining time now ~1 h (card-limited) vs stock 29-min cap; stock OSD restored.
- **TEST 2 PASSED (camera):** movie + Muted records log-looking footage.
- Test 3 verify (releases/test3-full/VERIFY.log): all functional checks PASS (buttons, aperture, grain, bloom, WB 25, MONO 234, bundles 73). Undetected mutations (WB 3, bundles 1) are config-dependent: they need WB override / COLOR3 enabled, which the personal bundle leaves off; same code catches them on the example bundle. Cleared to flash.
- **TEST 3 FAILED (camera): BOOTLOOP** with releases/test3-full (bundles-lachlan, wb, grain, bloom, mono_colour, rec_limit, video_log, buttons, aperture_ring). **Recovered**: battery out → OK+power with stock main restore → success, camera back to stock. ⇒ SD updater reachable even from a bootloop. Next: bisect one feature per flash; test4 = rec_limit + video_log + buttons.
- Buttons dropped (user). Test 4 = rec_limit + video_log + bundles-lachlan.
- Aperture ring parked (user) — excluded from builds; kept in repo for community later.
- Agents: SD loader v2 (boot-safe, post-boot trigger), film-sim library + menu design, log view-assist feasibility.
- Bootloop analysis (agent, docs/BOOTLOOP_T3.md): #1 aperture ring (runs at power-on every lens request; bit 0x80 unproven; parser consumes 2 bytes unconditionally), #2 WB (4 LV-start sites), #3 MONO chroma; bundles low risk at boot. Test 4 (rec+log+bundles) cleared.
- **TEST 4 PASSED (camera):** rec_limit + log + bundles booted fine; COLOR2/COLOR4 colours visibly changed.
- Fuji gaps (agent, docs/FUJI_GAPS.md): Clarity likely feasible (Soft Focus + weight>1024 unsharp, effect_id 3); split toning feasible via per-channel RGB gamma setter 0x603ae7d3; LV preview partial; red halation partial (combiner 156 colour word + mask); 3D LUT infeasible; grain size infeasible; colour grain chroma gains possible.
- Film library (agent, docs/FILM_LIBRARY.md): menu labels CAN come from runtime text (kind 5/6/12 entries draw a C string pointer). Cheapest Film Sim menu: switch ~40 COLOR/MONO option entries to kind 5 pointing at 8 name cells loaded from card. Library v2 format + tools/ep7_library.py (18-look example, 12 corruption tests rejected). Mocks docs/img/ui_film_sim_*.jpg.
- Log View Assist (agent, docs/LOG_VIEW_ASSIST.md): feasible via dormant display-controller RGB LUT (loader 0x60187439, regs 0x9c002000/0x9c000204, steps 17–19 empty); LUT = default∘inverse(log). Trigger site undecided (needs frequency/blocking trace). HDMI stays log. Not built.
- Test 5 verified (grain 7/7, bloom 6/6, bundles 73 functional; config-dependent mutation miss only). Loaded on card. Test-4 camera shots copied to testdata/camera_t4 (36 JPG/ORF, 4 MOV).
- SD loader v2 (agent, docs/SD_BUNDLES_V2.md): trigger = first shutter half-press (hook 0x602c805f in HLS_EVENT task), 659 B in section-3 tail; nothing at boot. Verifier from upstream event: 173 runs + 10 sequences + 15/15 mutations PASS. Risk: possible event-queue deadlock at that press (UI hang; battery pull recovers). Needs independent review before camera.
- **TEST 5 PASSED (camera):** rec_limit + log + bundles + grain + bloom boots; looks good; slight write lag esp. COLOR4 (bloom = 3 extra full-image passes, expected). Shots → testdata/camera_t5. Log clip analysis (PB010013): p1 26 / p50 126 / p99 196, no clipping = log confirmed.
- SD loader v2 review (agent, docs/REVIEW_SD_V2.md): no blockers; OK for camera test as its own step on test-5 base. H1 section-RAM writability unproven (crash on 1st half-press if faulting; SD updater still recovers). M1 UI freeze during read / narrow deadlock window. Test plan: step1 card without BUNDLES.BIN; step2 file = flashed table + 1 visible change.
- Test 6 verified (WB 26 functional, grain 7, bloom 6, bundles 73; config-dependent mutation misses only). Loaded on card.
- **TEST 6 PASSED (camera):** per-profile WB — COLOR4 shot EXIF WB fine-tune A+2 G0 (override) vs COLOR3 0/0 (global); R/B 1.31 vs 1.19.
- Test 7a verified (SD v2 suite 21 PASS incl. mutations); loaded on card with NO EP7MOD folder.
- **TEST 7a FAILED (camera):** boots fine; crash + restart on first shutter half-press (card mounted, no EP7MOD). Matches REVIEW_SD_V2 H1 (section-RAM write). Plan: reflash test6; agent root-causing (docs/SD_V2_CRASH.md).
- SD v2 crash analysis (agent, docs/SD_V2_CRASH.md): no proven cause; lead = sd_state store into section-3 RAM (stock never writes loaded image; writes only ≥0x61b2xxxx). Fix: state at 0x622cbcc2 (HLS object padding), table via malloc'd uncached buffer + accessor in 6 readers. Probe plan P1 (section-3 store only) / P2 (store at 0x622cbcc2) / P3 malloc / P4 fopen / P5 full.
- Probe P2 (store to 0x622cbcc2 only, no section-RAM write, no file calls) built + emulator-verified; differs from test6 only at hook + 146-B probe (checked by me). Loaded on card.
- Film Sim menu v2 design (agent, FILM_LIBRARY.md §8): hook in label builders (0x60df255f/0x60df25dc), 40 profile entries point at 8 flashed empty-string markers; names read from v3 loader heap block when valid; no runtime writes to image; no card → stock labels. Depends on SD loader v3.
- **PROBE P2 PASSED (camera):** first half-press + shots fine with hook + gates + store to 0x622cbcc2. ⇒ hook/gates/replay OK; 0x622cbcc2 writable at runtime; 7a crash attributed to section-3 RAM store (P1 not run, by user choice). Proceed with v3 (no image-region writes).
- SD loader v3 (agent, docs/SD_BUNDLES_V3.md): state 0x622cbcc2, heap buffer + accessor in 6 readers, zero image-region stores (audited + emulator read-only). test7b = test6 + v3 (34 edits); readers pass with flashed and heap tables; loader 179 runs + 10 seq + 10/10 mutations. Test file: COLOR1 greens hue +7. New camera risk: first real fopen from HLS_EVENT → test without EP7MOD first.
- **TEST 7b step A PASSED (camera):** loader v3 + half-press with no EP7MOD → no issues (fopen of missing file OK).
- **TEST 7b step B PASSED (camera):** EP7MOD/BUNDLES.BIN (COLOR1 greens hue +7) loaded on first half-press → teal greens. SD look loading proven on camera.
- View Assist: safe trigger found (display reply tail 0x601751f4); blocker = no playback flag → LUT can't auto-off in playback. Awaiting user choice.
- Look library v1 (agent, docs/LIBRARY_V1.md): 19 looks (16 colour, 3 mono), camera-feasible, tuned over 4 rounds on test shots; names ≤12 chars.
- Clarity (agent, docs/CLARITY.md): effect_id 3 unsharp via bloom path with weights 1100–1420 (negative blend weight in combiner 11 mode unproven on HW). 270 B @0x6055e5c0; loader effect range 0..3. test9 = test7b + 5 edits; all verifiers pass.
- View Assist (agent): probe-VA0 + test10 built on test7b; LUT/stub in unused EVF gamma tables (section 1); no RAM stores; 58-case matrix + mutations pass. Probe first: LV contrasty, playback normal.
- Test 8 film-sim menu (agent): BUNDLES.BIN 680 B w/ names; loader --names; 2 label hooks + 40 entries; 44,703 label sources × builders × 11 states pass; readers pass. Card: Kodachrome / Classic Neg / Warm / Portra.
- **TEST 8 step A PASSED (camera):** stock labels without file.
- **TEST 8 PASSED (camera):** Picture Mode shows Kodachrome / Classic Neg / Warm / Portra from card. Tagged v0.6 (= test8 + card).
- Test 11 = v0.6 + clarity + view assist (83 edits): clarity 21/21, menu S/X/M, bloom, view assist S/P/M pass; loader byte-identical to test8. Card: lachlan names + COLOR2 clarity 3.
- Test 11 camera: worked, but card FAT corruption on last shot PB010089 (invalid cluster chain) → camera shows Write Protect. 171 files backed up. Cause TBD (power-off mid-write vs firmware). Test 12 (editor H/L + card save) built + verified (emulator found/fixed 3 bugs) — HOLD until card corruption cause understood (it writes to card). Picker v2: Delete in COLOR editor cycles library looks (design).
- Test 12 camera: Delete never reaches colour editor (any route). Test 12b: Movie (0x9012) via COLOR record +52 → axis cycle; suite all pass, 22/22 mutations.
- Test 12c (look editor): axis indicator `[S]/[L]/[H]` in the editor guide label. View part 3 is the .data word
  0x6025aa98 → ed_guide (sec 5 0x60b9dd10, 287 B), which rewrites id 2755/2756 as kind 5.
  - Movie cycle → ed_poke re-writes the cursor setting (listener refresh). H/L edit → ed_set re-enters
    0x60827440 with the unchanged S value.
  - Finding: the picture-mode refresh in 0x60827440 is only for ids 111/1645/1646/15271. LV can't show H/L
    (capture-only reader); a refresh doesn't change that. Bundles don't override COLOR saturation.
  - 102 edits; S/G/W/E/V/I/T pass, M 41/41 (verifier `--jobs` pool); package == emulated image; restore == stock.
- Film menu v2 (agent, docs/FILM_MENU_V2.md): design only, nothing built. Route: a 4th "F" stop in the editor Movie cycle; Up/Down record words +12/+16 (0x61185be8/bec …c90/c94; every dial/arrow/touch step goes via parent+48/+52 [V]) step the 16 colour looks from LOOKS.BIN into the slot (heap P), saved by the 12c BUNDLES.BIN save. Needs E1–E3 in the 12c files, so it waits for the 12c camera result (= 12d). Dedicated list rejected: the lists are value→label tables, so it would need a host setting.
- Look extras (agent, docs/LOOK_EXTRAS.md, patches/look_extras): X stop after H in the colour editor; sectors 1–4 = grain / glow−·clarity+ / WB A–B / G–M of the slot; layer re-points 8 editor-owned words (falls through), 1112 B in dead EVF step-2/1 tables 0x601e323c; on 12c: G 744, W 4048, E 246, V 648, M 16/16 PASS; key route param (Movie dead on camera → rebuild on 12d with --key-word 44 --events 0x9014; --x-prev 3 --x-axis 4 after film-menu F). Not cleared.
- Aspect v2 (agent, docs/ASPECT.md §3(c), §6): XPan/21:9 ported onto the current line as the standalone spec patches/aspect/edits.json
  (103 edits, 1012 B; M1 ×16 heights already in it). H3 fix is a **boot clamp**: at the boot tail 0x601929a4 (after the stock per-boot resets), stored aspect 6/7
  → stock default 4:3 via the stock reset primitive 0x602b972b (gate 0x62257b04 as stock). Stub 56 B @0x60210e90 (sec-1 tail, retired v0.4 bloom block).
  The spec merges with test12c with 0 overlaps (also clear of 0x60b9dd10–e000, 0x6143a400–a800 and look_extras EVF tables). 174/174 aspect checks pass on test12c+aspect, and 12c's verifiers are
  unchanged vs the 12c baseline. No test13 package (combined build: 12d folds it in). tools/merge_specs.py now keeps the `look_editor` metadata.
- LV bundles (agent, docs/LV_BUNDLES.md, patches/lv_bundles): LV and stills share the colour builder 0x603b0068 (via selector 0x603b0252); LV jobs (0x60321d36 → 0x60324071, R+2119 → params+5538) have no transport, so hl is skipped. Listener = descriptor+24 callback (0x602b5e91/eaa/ec3/edc) → 0x602b8916 → 0x602b7b71. New hook 0x603b02de → lv (284 B @0x601e0e3c, dead EVF LUT); for no-marker COLOR jobs, profile from getter 0x6005e971(0xF6B1) → same H/L as hl. Verified on the test12c base: 91/91 + 18/18 mutations. Not integrated or camera-tested.
- Test 12d (combined: editor 12d + look_extras X + aspect XPan/21:9; 204 edits). 12c camera: `[S]` shown, never
  changed; Movie never reaches the editor. 12d: INFO (record +44) cycles S·Single → S·All → L → H → X → S·Single via
  `ed_info` (ALL only toggled by stock code); guide label = current state (12c wording was inverted: 2755 = ALL off);
  key probe in the label (router + object-entry vtable words, P+1000/1002, `--no-probe`). Movie/Delete words stock.
  Editor S/G/W/E/V/K/I/T pass, M 56/56; extras G/W/E/V pass, M 16/16 (integration edits: 2755/2756 swap, texts,
  ed_probe, E harness); aspect 174/174; package == emulated image, restore == stock. Not camera-tested.
- LV art preview (agent, docs/LV_ART_PREVIEW.md, patches/lv_art): Art-Filter LV = same constructor 0x603537eb via record path 0x603114e0 → IPCR 0x60321d3b (call 0x60321ea8); Art Effect bits (0x60312f42) only for picture mode ≥100, type 0x3x → classes 5–8 → single-pass Soft Focus 0x6035cc1b (reduce 144×108/80 + one combiner-12 blend), grain 0x0902. Our looks miss LV because only converters write the job transport. **Phase 1 built:** hook 0x60353c6f (pre-dispatch; gate return word 0x60321eaf, key 11, type 0x3x, profile via 0xF6B1) writes the transport + flag 0x80 for bloom slots → LV bloom + H/L (grain opt-in), 177 B @0x601e113c (EVF step-13 R). On test12c: S/F/H/C/D/R pass, 15/15 mutations (default build). Not cleared; first camera test decides whether this route is the LCD LV. Note: also reaches FHD movie jobs (type 0x3x).
- Aspect v3 (agent, docs/ASPECT.md §1b): 12d camera result = Panorama/Wide missing from the SCP. Cause: the SCP/Live Control strip (Lv_Control select array 0x61177140 → 30 × 24 B) has its own setting-270 record 0x61176fc0 {270, 5, white/green icon lists} with values 1,3,2,4,9 only; the menu descriptor is not used there. All other aspect enumerations found (icon resources 0x6123dc94.., quality/pixel-count screen 0x611d6754, LV layout lookups 0x61162468.., 0x611d3198.., 0x61140d98.., 0x6116daf4, map 0x61173d88) are value lookups, left unchanged. Fix: record count 5→7, list A rewritten in place (0x61175d78), list B → 0x61242f60; ids 6/7 are type-4 text entries 241 "Panorama" / 2661 "Wide" (no aspect bitmap exists; resolver 0x60df250b fills the string slot for type 4 [V], drawing in the icon cell [I]). 106 edits / 1192 B; 198/198 checks standalone and on 12d-minus-aspect (= look_extras_12d merged; R runs through the film-menu resolver hooks); merge 207 edits clean; package test-built to scratch, restore sha unchanged. Not camera-tested.
- Test 12e (combined; 224 edits: editor 12e + extras + film page + lv_bundles + lv_art + aspect v3 on test 11). 12d camera: INFO + save OK; Movie/Delete never reach the editor. 12e: MENU (0x900e) / PLAYBACK (0x9010) via record +36 cycle Saturation → Hue → Light → Film → Extras; INFO back to the stock ALL toggle; plain ≤16-char labels (no probe); Film page picks the 16 LIBRARY_V1 colour looks from EP7MOD/LOOKS.BIN, saved via the half-press save. Emulator: editor E 474/V 230/S/I/T, extras G/W/V, film V/U/P/L/H/T, lv 91/91, lv_art 8/8 + lv×lv_art case, aspect 198/198; package == emulated image, restore == stock. No mutations (user request). Card = the user's 12d BUNDLES.BIN + LOOKS.BIN. Not camera-tested.
- 12e revised in place: camera showed MENU/PLAYBACK open their own screens (outer screen consumes them), so +36 hook dropped (stock again); INFO now cycles Saturation → Sat-All → Hue → Light → Film → Extras → Saturation. 220 edits. Editor S/E 269/V 230/T, film P/H/T pass; package == emulated image, restore == stock.
- test13 + wheel polygon (ed_poly at 0x609330f9; producer 0x60932fa6 vtable+4972 mapped). 223 edits. verify_poly 595/595 ×4 specs, editor E/T, film H/T; package == emulated, restore == stock. docs/LOOK_MENUS.md: list menus need a host item, not built.
- test13 in place (243 edits): Film label `*` when the slot differs from its picked look (fm_mod via ed_cfg_fm); red bloom effect_id 2 (bloom --halation + halo stub 0x60210e10, hook 0x603a04e8; CineStill800 uses it, LOOKS.BIN regenerated); mono presets on stock MONO filter/shading editors' INFO (6 presets via stock SetValue + slot name; mono_colour dropped per user). Aspect v5 kept. Emulator: film M 50, halation F/W/D 400, mono S/H 146, editor/extras/film/poly/lv/lv_art regressions pass; package == emulated, restore == stock. No mutations. Not camera-tested.
- Camera test 13b (PB021368–1379, makernotes parsed without exiftool), fixed in place in test13 (243 edits; the aspect agent then added 11 and packaged 254, which contain every 13b edit unchanged; decode == emulated image re-checked):
  - **Red bloom:** COLOR1 = CineStill800, effect 2. It renders a luma glow, but the chroma term only scales the
    light's own chroma: the LED fringe is Cb −5 / Cr +5 and the clipped core has Cr 0. No cross-channel term exists
    in combiner 11.
  - **Bloom colour built:** slot byte +45 `bloom_tint` (0 neutral, 1 red, 2 amber, 3 warm, 4 cool; loader span
    0→4; LOOKS.BIN +47). bw_tint + halo in the dead EVF step-6 R table (w = W[s] + tint), Extras sector 5
    `5 Bloom …`, and lv_art previews effect 2. CineStill800 v2 = bloom 4 red.
  - **Mono presets:** the settings landed (filter red s2, grain low, shading −1, HL +1) but 999/1000 =
    midtones/shadows (swapped), and the open screen did not redraw. Fix: IDs swapped, plus a post-refresh poke of
    the editor's own child (mp_set; mp moved to 0x601e283c).
  - **LV report:** CineStill lost its LV glow in test13 (effect 2 was not previewed by lv_art). This is fixed. The
    weaker colour is library v2's 3× smaller WB shifts. The halo hook and the aspect LV ratio do not touch LV colour.
  - **Emulator:** halation F 24 / W 84 / D 112; mono S 98 / H 48; extras S / G 120 / W 224 / V 72 (quick); film
    L 50 / P 5 / M 50 (quick); lv_art 8/8; loader v3 E 179 + N 29 on the base. Package == emulated image; restore
    == stock (identical to the previous test13); 3160 bytes differ from the previous test13, all inside edit spans.
    No mutations.
- Camera test 13c bloom colour ("still a no go"), analysis only; releases/test13 unchanged (docs/HALATION_RED.md §9):
  - Shots: 1380–1383 = COLOR2 (makernote mode 10; bloom 4 cool), 1384–1390 = COLOR4 (mode 17; bloom 5 red). The card's +45
    bytes are right.
  - The tint *is* applied for effect 1. halation verify on the release: F 24 / W 84 / D 112 PASS, and W covers effect 1 × tint 1..4.
  - Fringe chroma: cool and red both show the LED's own warm fringe, about Cb −9 / Cr +10..14 at ≤30 px, with a neutral core.
    This is as the model predicts: the halo stub only re-spreads the light's own chroma.
  - The real luma-keyed tint was not built. New RE: bank groups A/B at +76/+120, each with a constant colour word; kind-3 mask
    port at request+148; the blend setup copies +20/+84 only. Each route depends on unknown mask-mode/format semantics or on
    buffer lifetime (§9). A tint-1-only probe build is proposed.
- test13 in place, camera 13c fixes (273 edits): aspect v7: `%dx%d` table 0x611f09e0 extended to 7 ids (0x601e14b0), so Panorama/Wide read 5184x1920/2224; info icon lists +6/7 → 16:9 bitmap (0x601e15f0/1628), §1f. Mono preset label `Preset: <name>` in the Profile view (0x60e26ab0) guide slot on the MONO filter/shading pages (call sites 0x60e27209/0x60e275c1 → mp_lbl1/2; mp 1020 B). INFO already consumes the event with a table; the filter jump is the preset filter. mono S 98/H 48, label L 10/10, aspect lean 157/157; decode == emulated, restore == stock; 980 B differ, all in spans. No mutations. Not camera-tested.
- test13 in place, red-tint mask-route probe (274 edits; on top of the log probe, 04:18:49 spec):
  - What it does: on red-tint slots only, the blend setup hook 0x6035caad copies job buffer 0x1060's descriptor to
    request+148. The halo stub then sets a combiner-33-shape bank (mode 0x1002, colour 0xC060D0, β = 2b), but only if
    the port matches. Otherwise it falls back to bloom colour.
  - Code: 510 B in the EVF step-6 R+G tables.
  - Card: COLOR1 = bloom 4 Red, other slots kept from the 13c card.
  - Checks: probe S 110 / B 66, halation F 24 / D 112 (W: (sp) scratch word only). Decode == emulated image, restore == stock.
    No mutations. Not camera-tested. docs/HALATION_RED.md §10.
- v0.14 (was test13): the red mask probe garbled frames (salmon ~65 px tile grid; mask port does not read the 0x0305 reduce
  buffer as a per-pixel mask). Reverted in place: 273 edits, bloom edits == pre-probe build, log probe kept. Halation
  F/W/D pass; decode == stock+edits, restore == stock; SHA256SUMS regenerated. HALATION_RED §10b.
- **v0.14 LOG FIXED (camera):** log hook now keys on the movie picture mode (stills pm ≠ movie pm broke it since 12e) and View Assist removed (its display LUT was baked into recordings, cancelling log). PB021401: p1 13 / p50 88 vs p1 1 before, visibly flat. View Assist must not come back in that form.
- v0.14 Art Effect + Extras re-layout (271 edits, on the 04:54:39 spec):
  - Bloom colour as per-channel weights is not possible: combiner 11 is diagonal YCbCr, and an RGB weight needs a cross
    term (HALATION_RED §11).
  - COLOR Art Effect, slot +46 (loader span 0..5, layout_crc unchanged): `art` stub 0x601e1d3c from bloom_flag.
  - Extras: sector 5 Art, sector 6 Bloom colour, log label on 7–12.
  - Checks: art F 768 / L 20 / S 4096, extras G 936 / W 5392 / V 864, halation F/W/D, build_probe PASS; decode ==
    stock + edits, restore == stock.
  - The blur probe crash is noted in HALATION_RED §10e.
- v0.14 in place (268 edits, on the 04:57:52 spec), after camera feedback that the Art Effects and log work:
  - Bloom colour off: --eff2-bloom, no halo hook; tint ignored and effect 2 = plain bloom. B 240.
  - Extras: sector 6 hidden; Art wraps modulo 6. G 936 / W 5392 / V 864.
  - LV Art Effect: Pin Hole, Blur, White Edge and Frame via lv_art; Star Light not. V 20; lv_art S / H 49 / gates / C / D / R.
  - Log probe and LOGDBG dump removed; the decision fix (A+354) is kept at 0x60210c90. H/M/G/L PASS.
  - Art F 768 / L 20 / S 4096. Decode == stock + edits, restore == stock; 11365 B in spans. AE-grid mask idea parked (§12).
- v0.15 MONO colour (agent, docs/MONO_COLOUR.md "v0.15"): MONO1-4 hold colour or B&W per slot (+32 colour byte). Capture =
  mono_colour --sd-v3 (sec-7 tail). New `mc` (2275 B 0x601e1e3c + data 0x601e383c): colour MONO slot opens the COLOR m wheel
  editor (lookups 0x60e4cea8/cf21 + type-7 word), 111 spoof at 13 editor/view return addresses, virtual S/H/L on the MONO
  slot, polygon, Film page lists colour looks + mono presets + B&W, label, `mc_pick` API for the mono picker. COLOR slots
  stay colour (mono-in-COLOR not cheap). Card: MONO1 Portra 400 / MONO2 Kodachrome64 colour, MONO3/4 B&W. Capture
  A213/L210/B30/V12/N32, UI R634/G1237/S204/P48/U190/L12/T9/K48, mp verify PASS; decode == stock+edits, restore == stock.
  LV/movie of a colour MONO slot stay B&W. Not camera-tested.
- Project renamed **Caduceus** (was EP7 Unlocked; briefly Zeus). Firmware version screen to show "Caduceus vX.YY" from v0.15.
- v0.15 Firmware screen fix (camera: `Body Caduceus` clipped, `: 1.1`): label back to stock "Body"; the view 0x60d7f0a4's
  two Body value setter calls (0x60d7f271 +940, 0x60d7f2cd +300) go to `fw_val` (0x601e1c40, dead EVF step-10 B), which
  appends " Caduceus v0.15" to the stock field ("1.1 Caduceus v0.15"); the setter 0x60d4c9df heap-copies any length.
  Builder/sprintf/updater/EXIF byte-identical. E 8/8 builder + 16/16 view, S, P PASS; 280 edits, rebuilt in place.
  Value widget width not known: the text may clip on camera.
- **v0.17 extended hue/light** (docs/V02_BUNDLES.md "Extended H/L"): the ±7 limit was our reader check + 15-entry LUTs (and the
  loader / film-menu / tool range tables), not hardware: the stock art-filter COLOR table writes hue −15000. UI −15..15, old
  −7..7 entries unchanged; hue −1000/step to 15000, light to ±1000. LUTs at 0x601e123c (dead EVF step-13 G); hl/lv/loader/
  fm_core changed in place (same sizes and labels, sd_back → 0x605b7340). Table geometry suggests 11°/1000 (sim default stays
  5.5). Aerochrome retuned as lib3_aerochrome (green −10 → crimson foliage, red +6 → orange, blue light −15). v0.17 = v0.16 +
  hl_ext + fw "0.17" (286 edits); card LOOKS.BIN from library_v3 (Atrophy + Aerochrome). tools/ep7_verify_hl_ext.py 53/53;
  caduceus build --release v0.17 matches SHA256SUMS. Not camera-tested.
- v0.17 fix (camera: Hue page guide label blank): stock guide 0x60decbfc blanks the ALL-off label when the page's (±5-clamped)
  values hit both −5 and +5 (Aerochrome hue); ed_guide now labels id 0 too (ed_view 516 B). Guide S/S·All/Hue/Light/Film/Extras
  == v0.16 byte for byte in the emulator; hl_ext verify 73/73; v0.17 rebuilt in place, caduceus reproduces it.
- v0.17 Extras guide label: same stock blank (values touching −5 and +5); ed_guide puts the blanked ALL-off id back to 2755 on
  the Extras page so ex_guide labels it (ed_view 556 B). hl_ext verify 84/84 (labels == v0.16, blanked S/H/L/Extras labelled,
  no card table == stock). Vignette (Extras 6) not built: needs the shading work-list + mask on key 11; plan in docs/VIGNETTE.md.
- **v0.25** (patches/v025 + patches/aspect_icons, flashed 2026-11-06; strip icons OK, SCP value cell still 4:3, vignette pixels unconfirmed): shading off per COLOR slot (+49, Extras sector 8, 5 reads of 0x8c21 incl. 0x605554bc which the first scan missed). A pick sets +49 = 1 unless the
  record's mask has bit 2 (fm_check accepts it from v0.25; sl_pick replaces ng_pick at lt_post); own restores its snapshot, Stock 0; lt_mod ignores +49. NR via read-site override of sid 143 (0x602a8095 capture,
  0x6028d08a MakerNote), 1334 writes gone. Flat tried and removed (user: log already covers it, costs Portrait). verify.py: U shading 26880 + NR 13440, W 56, P 175 steps + masks, R, D, K. tools/ep7_verify_v025_extras.py G 936, V 1656, W 6160.
  Open: the stills NR claim is static; camera_v022 PB031626/27 have MakerNote NF 0 among -2s (menu change, or 1334 reaching stills). The override is right either way. Where correction reaches pixels is not found: wall test decides.
- **v0.26** (patches/v026 = v026_rot + v026_movie, flashed 2026-11-07; pkg 0d2e45aa; replaced twice the same day: loader rejected a saved Film pick, label added (69eb70ca); OK switched movie mode to Color Creator): rotation via tkhd matrix; Movie slot P2 + own L2 (docs/MOVIE_COLOUR.md, docs/VIDEO_ROTATION.md). Camera: rotation flags in ffmpeg, colour in file, wheel via INFO. Open: 20+ min 4K, chapter splits, other players, Control Panel MOVIE.BIN export.
- **v0.27** (patches/v027 + patches/grain_cpu r1, pkg d774f62a, 2026-11-08): CPU film grain on COLOR stills (Extras 1, slot +50), NR to Extras 9, looks never set Grain/NR. Route camera-proven on s3 (finer grain, 23/55/91); r1 coarser (half-res noise ×2) and 40/102/180, not yet shot. Diagnostics: GRAIND (removed for release). Open: save time 3–5 s, speed (window mode hold unproven).
- **v0.28** (patches/v028 = v027 grain r2 + patches/sharp_off, 2026-11-08): grain back to s3's (r1 too strong), Extras 10 Sharp Camera/Off (slot +51, Sharpness read → −5, gain 0; Movie via the settings message +18). Camera: saves and photos softer, no hang; controlled test not done (no tripod). Live ND shelved (docs/LIVE_ND.md).
- **v0.29** (patches/v029 = omc_buttons + aspect_fix + aspect_scp + btn_arrows on v0.28, 2026-11-08, pkg 0e37787b): all camera-tested in builds b1-b5. Arrow ids: up 50, down 51, left 52, right 53 (docs/BUTTONS.md 4d). Grid overlay for XP/21:9 still open. om-c-firmware has no public code (docs/OMC_FEATURES.md).
- **v0.29a** (patches/v029a = v029 + page_order + film_poly, 2026-11-08): Film-first INFO order, open on Film, Film page polygon = slot S (1 byte in ed_poly). Camera-tested as 0.29p1/p2.
- **v0.30** (patches/v030 = v029a + min_ss m4 + ap_custom + live_nd n8, 2026-11-09): camera-tested as 0.30b1-b10. AP Vivid slot (AP.BIN; SCP INFO = state 3 handler word 24, event-first table), P marker reset on first half-press (stale heap markers skipped the loaders). Live ND: grey-out table 0x60adf518 entry 24→23, preset pair removed, lnd_cont re-requests the continue (Seq H reliable, Seq L can stop at 2). Lowest S/S: stock sids 1146/1147 + picker 0x1aa, row in E1 (init list 0x6025aa90 offset).
- **v0.31** (patches/v031 = v030 chain (live_nd floor, selftimer off) + recview (grain_kind) + halation h2, 2026-11-10): camera-tested as 0.31r2/h1/t3. Rec View: rv_gate strips 0x40/0x80 on small dev types. Halation: CPU tint on grain route, Extras 11 Halo (+52). Live ND self-timer one-press hung after the last frame (not battery; cause unresolved, docs/LIVE_ND.md), parked.
- **v0.31a** (patches/v031: ap_custom a1 loader retry + halation h4 = h2 output + watchdog yields, 2026-11-10): camera-tested as 0.31b2. h3 speed-ups looked wrong (too strong, blocky, missed LED) and were dropped (docs/HALATION_RED.md §18-19).
- **v0.31b** (patches/v031: halation h2 code unchanged + hardware WDT 10 s -> 30 s at 0x6005b23a/0x6005bcff, no yields, 2026-11-10): camera-tested as 0.31b4. v0.31a yields caused a crash ~2 s after the shot on bright frames.
- **v0.31c** (patches/v031 + ap_custom c2, 2026-11-10): Movie/AP Extras sectors 1/2/5/11 locked with "stills" labels, AP slot read returns a cleaned copy (no FX), sid 1686 is the wheel cursor (v0.26 movie code treated it as S·All; fixed), movie Muted label "8-BIT LOG". Camera-tested as 0.31c1/c2.

## 2026-11-10 — E-M1 Mark II: why Color Creator looks did nothing (v0.1 → v0.2b1)
- Camera report on em1mk2 v0.1: Page 0 changes the look name only; Chroma/Luminance/Midtones change only the banner;
  the SCP rear dial seems dead on the Color Creator tile.
- Traced the stock route (em1mk2/docs/ARCHITECTURE_AND_MEMORY_MAP.md §7.5): Up = child 1 `0x9004` + `0x900c`; children
  from descriptor `0x6125a038`, vtable `0x6122ba84`, fn table `.data 0x61fbd444` (flash `0x60297f04`); commit
  `0x60e4c0a7` writes with facade `SetValue(sid, 0, list[idx])`, the same call v0.1 makes. **SetValue does not filter by
  mode**: `0xF0000058` comes from global camera-state bits (`0x607abb14`), so the TODO's "mode filter" diagnosis was wrong.
- Found the sid table (`0x604f808c`, E-P7 format) and the validator (`0x604ee648`, 1,215 × 20 B, unsorted). This body's
  tone/sat sids are the E-P7's minus 2: effective sat `0xF6EA` = 913..924, per-profile sat `0xF6FA` = 925..960, COLOR tone
  961..969, ordinary tone 889/890/891. v0.1 wrote E-P7 numbers (915..926, 963..965) plus the untraced 449/450.
- Request builder `0x602d1de5..` (getter `0x6005e6cf`) reads 617/618, tone mirrors 383/384/692, picture mode, COLOR/MONO
  profile numbers and `0xF6EA[0..11]`: the TruePic VIII pipeline has COLOR-profile plumbing; the E-M1 II lacks the UI.
- Patch bugs: arrow handlers clobbered `d2`/`d3` before saving (the stock dial loop's counter/count), dial wrappers left
  `d2` changed; mono looks wrote vividness −5 (valid −4..+3); untraced `0x602da6b9` / `(0x61fbfc94)`+76 calls;
  init read tone via `0x602da5f9` (not the sid getter). Card generator wrote raw sat over the tone bytes.
- v0.2b1 (`releases/em1mk2/v0.2b1`, patched SHA-256 `473e4414…`): fixes above, tone → 889/890/891, sector writes
  removed (Chroma page kept but inert), ` Exx` diagnostic for failed 617/618 writes, tone banners read back. Cave 1,944 B.
  `make_release_edits.py` / `make_looks_bin.py` take a version so v0.1 is not overwritten (v0.1 SHA256SUMS still OK).
  `caduceus.py build` + `verify`: All good. **Not camera-tested.** Test list in docs/PORT_EM1MK2.md §4.
- Own mistake caught mid-way: first lookup said 449/450 had no validator record (assumed a sorted table); the full table
  has them (byte −7..+7). Docs and comments corrected.

## 2026-11-10 — E-M1 Mark II v0.2b1 camera test → v0.2b2 (state moved out of a stock ring)
- Camera (v0.2b1): saturation always 0; looks all the same; garbage look names; hue/sat/chroma do nothing.
- Root cause: the patch state block 0x621e2f76..0x621e2f87 ("verified unreferenced .bss") is inside a stock
  32-entry `{callback, arg}` ring at 0x621e2f74 (writer 0x6023d231, drain 0x6023d1cb `calls` each entry; head
  0x621e2f70, tail 0x621e2f72). Only base+index*8 accesses, so the absolute-address search missed it. Present since v0.1.
- New design = E-P7 heap P: `em1mk2/patches/p_layout.inc`; sd_loader owns `p_get` 0x605803a2 / `p_ensure` 0x605803d1
  (exported via sd_loader/exports.json to color_creator_wheel); handle u16 at 0x621e24ae (padding between byte
  0x621e24ac and word 0x621e24b0; nearest base 0x621e2488 is a 2-word array). Magic 'EM1P' + handle copy; any
  handle maps into RAM 0x61b00000..0x622fff80. Without P all CC handlers fall through to stock.
  Rejected: 0x6227d254 / 0x6223678c (tails of runtime-sized buffers after −1 markers).
- Also: sd_check frame had no call slot (sd_crc's return address could land on the caller's saved a2 = buffer);
  em1_free was 0x600232d9 (uncached pool) → 0x6002323d; names filtered to printable ASCII; page-banner numbers
  print '?' when out of range. Loader/fseek/fopen conventions checked against stock callers.
- Store audit of both caves: only absolute stores are the stock replay 0x621e2f6e and the handle 0x621e24ae; no fb
  opcodes, no mul/div/setlb.
- v0.2b2: releases/em1mk2/v0.2b2, patched SHA-256 43224d02…; caduceus build + verify All good; v0.1 and v0.2b1
  SHA256SUMS still OK. Caves: sd_loader 648 B, color_creator_wheel 1,904 B. **Not camera-tested.**

## 2026-11-10 — E-M1 Mark II v0.3b1: looks through the E-P7 COLOR engine, E-P7 LOOKS.BIN
- Camera (v0.2b2): some looks load but look wrong (Eterna B&W-looking at vividness −3). Color Creator's single
  hue/vividness can't express a look; user asked to follow the E-P7 implementation.
- Downloaded E-P7 1.1 stock (tools/fetch_stock.sh, SHA OK); main extracted with caduceus.parse to
  analysis/ep7_1100/00_0100_406a0020.decoded.bin (5dd9af16…, matches docs/ep7_1100_components.sha256; the fishcu
  submodule is not checked out). New em1mk2/scripts/ep7_match.py (masked signature match).
- Colour stage identical: E-P7 selector 0x603b0252 / builder 0x603b0068 ↔ E-M1 II 0x603ec82c / 0x603ec642 (builder
  differs in 3 bytes = one table pointer; selector in addresses only). E-P7 movie-layer sites (record/message/
  constructor) have no match, so v0.3 hooks only the colour stage: cc_sel 0x603ec89b, cc_hl 0x603ec8b8 (E-P7 lv).
- EM1MOD/LOOKS.BIN is now the E-P7 v3 file; loader ignores E-P7-only header fields. make_looks_bin writes it; panel
  check (webapp checkLooksBin/decodeLooksBin via node --experimental-transform-types) passes; the em1mk2 target now
  uses encodeLooksBin and its export is byte-identical. Generator fix: mono looks carry no tone (format.ts hasTone).
  cameras.ts em1mk2 settings:false (firmware has no per-look Contrast/Sharpness/Shading).
- P moved to the uncached pools (0x6002329a/0x600232d9, P_BASE 0xa1b00000). Audit: absolute stores only 0x621e2f6e
  (stock replay) and 0x621e24ae; no fb/mul/div/setlb. Built-in looks table == card records.
- v0.3b1: releases/em1mk2/v0.3b1, patched SHA-256 ae765736…; caduceus build + verify All good; earlier releases
  untouched. Caves: sd_loader 1,060 B, color_creator_wheel 2,764 B. **Not camera-tested.**

## 2026-11-11 — E-M1 Mark II v0.3b1 camera test → v0.3b2 (section bounds)
- Camera (v0.3b1): colours change with looks (COLOR engine route works). Only 2 looks labelled, 2–3 distinct, the
  rest repeat; chroma/hue do nothing on those.
- Root cause: Section 6 really ends at 0x612e7000 (descriptor table 0x60027450, end getter 0x60042b35 / jump table
  0x6004354c; matched from E-P7 0x60045786 / 0x600457e7 with ep7_match.py). The doc's 0x61300000 is Section 7's start.
  The CC cave's data (v0.1–v0.2 preset names/values, v0.3b1 built-in looks at 0x612e6fcc) was never loaded — also
  explains the earlier garbage names and Eterna-as-B&W. Card file not loading either (names would come from it).
- Fix: built-in looks to the Section 5 FF tail 0x60bc8150 (S5 = 0x60796000..0x60bc8800; tail unreferenced except two
  call-displacement false positives at 0x60cd07c5 / 0x613ac57f); CC cave now 0x612e6900..0x612e6fe8 (8 B left).
  New em1mk2/scripts/check_loaded.py (all sections from the firmware's table; .data init word 0x60297fb4 a known,
  camera-proven exception); make_release_edits.py runs it. v0.1/v0.2b2/v0.3b1 fail it, v0.3b2 passes.
- Banner: card state " C1/C0/CF" before " K…". Paths C:/D: confirmed as SD slots (stock "C:\DCIM\100OLYMP\").
- v0.3b2: releases/em1mk2/v0.3b2, patched SHA-256 cf4ecc5b…; build + verify All good; store audit clean.
  **Not camera-tested.**

## 2026-11-11 — Upstream v0.31c merged into the E-M1 II working branch
- Fast-forward to origin/main (14 commits: v0.30–v0.31c, panel OM-3 resync, AGENTS "ports keep to the shared formats").
  Local work stashed and restored; conflicts resolved in cameras.ts (upstream OM-3 lensCorrection + our em1mk2 entry),
  caduceus.py (our camera-generic copy_to_card + upstream AP.BIN handling) and WORKLOG.md (both appendices kept).
- Checks after merge: v0.3b2 rebuilds to the same package hash (cf4ecc5b…); check_loaded OK; panel checkLooksBin on
  the E-M1 card = no problems and the em1mk2 export is byte-identical with the updated format.ts; caduceus.py parses
  and lists all em1mk2 releases. LOOKS.BIN format unchanged upstream (new bytes are BUNDLES.BIN +51/+52 only).
- Relevant upstream notes recorded in current.todo §2d (own-repo/merge-export guidance, watchdog, RAW+JPEG, E-M5 III
  section table agreeing with ours).

## 2026-11-11 — v0.3b2 pre-flash review
- Package: caduceus verify All good; restore/E1259999.BIN == stock (f0c25dd8…); check_loaded OK.
- vs v0.3b1 (flashed): Section 2 cave (loader, P, cc_sel, cc_hl) byte-identical, so it is camera-run (colours changed, no
  crash). Changes: built-in looks at 0x60bc8150 (new), CC cave 2764 → 1768 B, SCP call displacement. All 10 hook
  words and the SCP call land on their function starts (relinked symbol table); SCP keeps `f0 88`.
- CC code diff vs v0.3b1: only shifted string addresses, the two built-in-table references (0x60bc8150 / +48), the card
  status block and one bra→jmp. Banner worst case 29 of 33 units.
- Loader file path checked against stock: fseek(fh,0,1)/ftell/fseek(fh,0,2) is the sequence at 0x60c0b8b5; fread
  (a0 buf, d0 1, d1 count, a1 fh) as stock 0x60199dc7; "fread == size" as the camera-proven E-P7 loader.
- Card file passes the firmware's checks (re-implemented in Python): magic, version, lengths, n, CRC; 16 names.
- Handle slot 0x621e24ae and P ran in v0.3b1 without a crash (still only static evidence that nothing else uses it).

## 2026-11-11 — E-M1 Mark II v0.3b2 camera test → v0.3b3 (tone settings, vividness reset)
- Camera (v0.3b2): colours change better; after a B&W look (vividness −4) all looks stay B&W; only hue affects the image.
- Colour looks never reset 618, and Color Creator's own processing still runs (its hue acts), so −4 stuck.
- Tone: 889/890/891 have no descriptor in the 60-byte registry (0x6046eb7c, 344 records; copy at 0x60474db0) and no code
  reads 0xF609/F619/F629 → dead. 449/450 (0xD7EA/D7F9) have records 0x60472308/0x604722cc with apply callbacks
  0x602db1b2 → 0x602f0d3a(v,8) and 0x602db195 → 0x602efaca(v,8), plus readers at 0x60192d71..0x601a0156. The
  E-M1 II has Highlight/Shadow only, no Midtone.
- v0.3b3: tone → 449/450, Midtones page removed (N_PAGES 3), colour looks set 618 = 0. CC cave 1,716 B. Section 2 cave
  unchanged. Audit: stores only 0x621e2f6e/0x621e24ae, no fb ops, hooks on instruction starts, check_loaded OK.
  releases/em1mk2/v0.3b3 patched SHA-256 6fffb0fe…; build + verify All good. **Not camera-tested.**

## 2026-11-11 — E-M1 Mark II v0.3b3 camera test → v0.3b4 (refresh + Strength)
- Camera (v0.3b3): B&W bug gone; looks change colour (tone too on look change) but subtly; Chroma and Luminance steps
  have no visible effect.
- Look changes write 618 and show; manual steps didn't write it. 0x60863a8a always stores, calls 0x608647c0(sid) and
  notifies (no unchanged-value skip), so v0.3b4 re-writes 618 with its current value after Chroma/Luminance/Strength.
- New Strength page (P_STR, x1/x1.5/x2/x3 via repeated add; S clamp ±10, H/L ±15; builder scales S linearly). look_fill
  now in the Section 2 cave at 0x60580622 (cave 1,248 B; earlier bytes unchanged except 2 padding bytes). CC cave 1,716 B.
- Audit: stores only 0x621e2f6e/0x621e24ae; no fb/mul/div; hooks on instruction starts; check_loaded OK.
  releases/em1mk2/v0.3b4 patched SHA-256 f02172d0…; build + verify All good. **Not camera-tested.**

## 2026-11-11 — v0.3b4 on camera: Velvia matches the Panel preview
- Camera JPEG of the Panel sample photo with Velvia ≈ the Panel's Velvia preview: red ground, saturated blue boats,
  red/yellow clothing, deepened shadows, neutral sky. Blues lean slightly more cyan. First end-to-end confirmation that a
  look renders as designed on the E-M1 II, and that the capture path goes through the colour-stage hooks.
- The violet cast in the earlier live-view photo came from shooting a monitor (AWB + phone), not from the look.
- Open: Provia on the same scene (cyan lean: look vs Color Creator hue), Chroma/Luminance/Strength on v0.3b4.

## 2026-11-11 — v0.3b4 desk test: neutral vs i-Enhance vs Velvia (camera JPEGs)
- Patch measurements (HSV, 24 px squares; wall/strap patches unreliable across framings):
  orange S 56→74 (+18, H 26→24), purple S 46→55 (V 82→78), blue mouse S 84→88 (H 201→204), light desk pad V 91→80,
  black speaker V 9→7. i-Enhance: orange S 74, purple S 61, mouse clipped (S 99, H 186).
- Saturation at Strength ×1 is in Velvia's range (≈ i-Enhance punch, different hues): keep ×1 as the default for now.
- Tone suspicious: Velvia HL +1 / SH −4 should not darken light areas by ~11 points; consistent with 449/450 swapped
  (HL −4, SH +1), or with a metering difference between shots. Camera check pending (Luminance page dials).

## 2026-11-11 — v0.3b4 desk test: Provia baseline (corrects the previous entry)
- Provia (Color Creator + neutral look) vs stock neutral: orange S 56→60, purple 46→45, mouse S 84=84 (H 201→204), blacks
  V 9=9. Color Creator at vividness 0 adds almost nothing: no compensation needed.
- Provia → Velvia: orange S 60→74, purple 45→55, mouse 84→88, blacks V 9→7. Moderate, as designed at E-P7 strength;
  Strength ×1 stays the default, ×1.5 for punchier.
- Correction: the earlier "light areas −11, 449/450 swapped?" came from the desk-pad patch, which is not comparable across
  these framings (Provia's reads V 71, neutral 91, Velvia 80). The swap question stays open, for the Luminance page check.

## 2026-11-11 — v0.3b4 page checks
- Camera: Luminance page: H/S numbers change (read back from 449/450, so the writes succeed), image doesn't. Chroma
  page: number changes; single steps not visible, but Chroma +5 on Provia makes the image punchier → the per-sector S
  path (P_SAT → request+1816) works. Strength ×2: visible. look_fill disassembly checked: P_CHR (P+25) is added to S.
- Open: was Chroma +5 visible in live view or only in the JPEG (refresh); Test B (JPEG at H 0/S 0 vs H −7/S +7) decides
  whether 449/450 reach stills, or whether tone must go to the request's mirrors 383/384/692.

## 2026-11-11 — Test B → v0.3b5 (tone = the request's own values)
- Camera: Luminance at 0/0, +5/+5, −5/−5 (449/450) → no change in live view or JPEG.
- E-P7 vs E-M1 II sid tables: 383 = 0x3719, 384 = 0x3739, E-P7 694 / E-M1 II 692 = 0xEFC9 on both; the E-M1 II request
  builder reads exactly these (0x602d243d/2453/2466 → +24937..9). E-P7 mapping 384 HL / 694 MID / 383 SH.
- v0.3b5: SID_TONE_HL 384, SID_TONE_MID 692 (written again from looks), SID_TONE_SH 383. CC cave 1,724 B; loader/hooks
  unchanged from v0.3b4. Audit clean. releases/em1mk2/v0.3b5 patched SHA-256 72552d29…; verify All good. Not camera-tested.

## 2026-11-11 — v0.3b5 on camera: tone works (request-side 384/692/383)
- Camera: Luminance +7/+7 vs −7/−7 changes live view and the JPEG. Measured (V, 20 px patches): wall 93→80 (+14), white
  tag 99→91, orange (mid) 100→96 (+3), speaker face 31→6 (+24), monitor arm 40→20 (+20). Highlights and shadows move
  strongly, mids barely: a real highlight/shadow curve. So until v0.3b5 no look's tone reached the image.
- Still open: which dial is which (single-dial test: H −7 / S 0), and Velvia vs Panel preview with tone now active.
- Camera (v0.3b5): Highlights dial affects only bright areas → 384 = Highlights, 383 = Shadows (not swapped). Tone done.
- 4000 (Velvia) vs 4001 ("neutral"): 4001 matches the earlier i-Enhance signature (mouse H184/S99, orange S82), so it
  was not a neutral mode. This Velvia measured less saturated than the earlier session (orange 65 vs 74, purple 40 vs 55)
  under warmer/dimmer light; cross-session comparison inconclusive. Next: Provia and Velvia (×1, Chroma 0) back to back.
