# AE: cadence, exposure fields, Auto ISO / shift / gradation hooks (E-P7 1.1)

Static analysis only: objdump (`tools/dis.sh`), `tools/ep7_xref.py`, REA/Ghidra. No build, emulator run or camera test.
Answers atlas unknown #3. Tags: **[V]** read from bytes or disassembly, **[I]** inference. Raw listings and decompiler
output are in `~/ep7fw-private/decomp/ae/` (private). New symbols: `tools/atlas/new_ae.py`.
Units everywhere are **APEX × 256** (1 EV = 256, 1/3 EV = 85/86, 1/6 EV = 42/43) [V: validator lists below].

## 0. Short answers

1. **Cadence.** The stills AE calculation is `te_calc_core 0x6042760c`. **Every call rebuilds both settings records
   from scratch** (`ae_record_build 0x6042777c`, plus the 16-B "B" record), on a zeroed stack frame, reading every
   setting live through `prop_get` [V]. There is no record cache. It runs:
   - from the per-frame detection callback `ae_frame_cb 0x60426e30` (and `0x60427118` in mode 198), under semaphore
     (`0x60040a36`) [V]; the caller task of the callback is not identified [I: the photometry/3A service];
   - from ~38 TAKE_EXPOSE (task 111) message handlers via `take_expose_calculate_internal 0x604275b3` [V];
   - synchronously from a settings change, via `take_expose_calculate 0x6042754a` ← `exp_change_notify 0x6028e684`
     ← `0x602e87e1` (18 callers, among them the descriptor callbacks of sid 86 and sid 6) [V].
   - **0x949a / 0x30ea / 0x30fa are property keys, not message keys.** No message is sent per key. A change is picked
     up by the next calculation, whatever triggers it [V].
2. **Pointer caches have no value fast path.** `0x6020d7a6`, `0x6020da40` and `0x6020d393` are three of ~200 call sites
   inside `ae_prop_handles_init 0x6020d024`. It resolves each AE key once to its registry storage pointer
   (`prop_handle 0x6005e947`) and stores it in `0x622a09a4..0x622a0bfc` (on = 1), or zeroes them all (on ≠ 1).
   `prop_get` with a non-zero a0 skips the registry lookup and reads the **current** value from that storage
   (`0x6005efbd`) [V]. So the handles only skip the lookup. Hooks must sit at the `prop_get` call sites, because a
   registry-side hook (`prop_lookup 0x6005d924`) is skipped [V].
   - **One real cache exists, on the other record.** The 124-B detection-parameter record ("DP", `ae_detect_build
     0x6042661b`) is cached at `0x622a084c` by the pre-frame callback `0x60426f83`. In AE mode 7 (`0x622a063e`) it is
     rebuilt at most every 100 000 ticks of the free-running counter (`0x60022319`) [V; I: µs, so 100 ms]. Otherwise it
     is rebuilt only when a state byte (DP+62) matches `0x60555c80()`. On a mismatch the stale cached copy is
     handed out [V code; I meaning]. So DP values (Auto ISO upper at DP+32, shift at DP+56..60) can lag the AE record
     briefly.
3. **Auto ISO upper limit** enters as record A+24 (sid 112). The Sv resolver `ae_sv_resolve 0x603fcaf1` substitutes it
   for the sentinel 0x9f00 in the per-mode program table when ISO is Auto [V].
4. **Hooks** (§5): Auto ISO ceiling = 2 rel32 `prop_get` sites. EI shift = 1 site in the exposure-comp getter, or
   6 exposure-shift sites. Gradation = 1 AE site + the capture site. All are `dd` rel32 calls with the stock
   `[d2,d3],12` frame, and each falls back to stock by calling `prop_get` first [V sites; I behaviour].

## 1. Who runs AE

| Item | Value | Tag |
|---|---|---|
| TAKE_EXPOSE loop | `0x60421540`: `queue_recv` on queue id `(0x60040d9a)`, msg id ≤ 3331, hash table **`0x6054aa50`** (64 × `{u32 id+1, u32 handler}`, linear probe). Ids 0x000, 0x001, 0x100/0x101, 0x200–0x202, 0x300/0x301, 0x400/0x401, 0x500/0x501/0x503, 0x600/0x601, 0x701, 0x800–0x802, 0x903/0x907, 0xa00–0xa02/0xa05/0xa06, 0xb00/0xb01/0xb04, 0xc00/0xc01, 0xd03 | V |
| Public entry | `take_expose_calculate 0x6042754a`: log "[TEXP]take_expose_calculate" (`0x60549eb0`), sem take `0x60418019(0x60040a36)`, core, optional `0x60425e0c(2)` if `0x622a063e` bit 0x20, sem give `0x60418025`. Callers `0x6028e6a8` (settings side), `0x604259cb`, `0x60425a64` | V |
| Internal entry | `take_expose_calculate_internal 0x604275b3` (string `0x60549ecc`), same sem. 38 callers in the TAKE_EXPOSE handlers `0x60422161..0x60425345` | V |
| Core | `te_calc_core 0x6042760c(d0 flag)`. Frame 760 B: record A 84 B (sp+36), record B 16 B (sp+120), photometry 480 B (sp+136), result 76 B (sp+616). Steps: `ae_record_build(A, B)` → `ae_photometry_in 0x60427dac` → `ae_stability 0x603f3956` → param block (sp+720) → **`ae_program 0x603f38f8 → 0x603fbe7a`** → `ae_result_publish 0x6042805e` (results into properties via `prop_set 0x6005ea22`) → `0x6042857f` → copy 76 B to `0x622a0714` | V |
| Bracket steps | `0x60427394` / `ae_bkt_advance 0x6042742e` step the AE/ISO bracket index (keys 0x8291, 0x97c1) and re-run the core | V code, I role |
| Frame callbacks | Struct slots `0x622a08cc` / `0x622a08d0` / `0x622a08d8` set at `0x604240dc..f4` and `0x604260d8..6179` (per sequence id 1280/1285/1289/1290/1295/1792/2592): result cb `0x60426e30` / `0x604270b7` / `0x60427118` / `0x6042721e`, pre-frame cb `0x60426f83`, end cb `0x60421db9`. Handed on through `0x60426432` | V |
| `ae_frame_cb 0x60426e30` | If status word (a3) == 0 and mode ≠ 7: publish photometry (`0x60425ba3`) + core, **on every callback**. Otherwise, while `0x622a0641` == 0: the same once, then set it and arm timer `0x6006b003(cb 0x60425e05, 250)`, whose callback clears `0x622a0641` (≈ 4 Hz while that state lasts) [V code; I ms]. Always writes key 0xce0a | V |

## 2. Records

**Record A (84 B, `ae_record_build 0x6042777c`, a0 = A, a1 = B)** [V offsets/keys; names I unless noted]

| Off | Source (sid, key) | Meaning |
|---|---|---|
| +0 / +1 | `0x60429733` (0x8121) / `0x60429787` (0x8131) | u8 flags |
| +2 | `0x6020e0e3` (sid 24, 0xc011) | exposure mode (P/A types 3, 4, 36, 37; M 6) [V per MIN_SHUTTER/APERTURE_RING] |
| +3 / +4 | sid 1540 / 1547 / 103, or `0x604292c6` / `0x60429285` (sid 1, 0x80a1) | metering-related; +4 metering mode |
| +5 / +8 / +10 | `0x604293f2` outputs | sub-mode flags (+5 gates the flash/LV rows of the program table) |
| +6 / +7 | sid 16 / sid 1478 | |
| +12 | `0x60173a2f()` | u16 |
| **+14** | **`ae_gradation_get 0x60429629`** (sid 105, 0x8eb9), s8 | **gradation** (0, 1 High, −1 Low, 2 Auto) [V key] |
| +15 | `0x60429666` (0x9961) | |
| +16 / +18 | min(`0x60429b3d`, +18) / sid 114 (0x94ba; list ISO 800..200) | an ISO cap (flash-related [I]) |
| +21 / +22 | sid 25 (0xc021) / sid 65 (0x8c61) | |
| **+24** | **sid 112 (0x949a)**, Sv | **Auto ISO upper limit** (list 1536..3328 = ISO 200..25600) [V list] |
| **+26** | **sid 172 (0x9a9a)**, Sv | **Auto ISO default** (lower). sid 112's descriptor callback `0x602b524a` forces 172 ≤ 112 [V] |
| +28 | sid 174 (0x9aba), Tv | list 1/250 .. 30 s [V]; flash slow limit [I] |
| **+30** | sid 1147 or 0x7eee | **Lowest S/S** (MIN_SHUTTER) [V] |
| +32 / +33 | sid 5 (0x8281) when +57 ∈ {1, 4}, else 0 / d3 | AE bracket |
| +34 / +36 / +37 / +38 | sid 1571 / 0 or 2 (`0x622a063f`) / sid 241 / sid 382 | |
| **+40 / +42 / +44** | **sid 273 / 274 / 275 (0x30ea / 0x30fa / 0x310a)**, s16 | **Exposure Shift ESP / centre-weighted / spot**, ±256 in 1/6 EV [V list; V mapping by the EXIF-style writer `0x604290a4`: metering 5 → 0x30ea, 2 → 0x30fa, 3 → 0x310a] |
| +56..+74 | sids 271, 1494 (+57), 600 (+58), 683, 682, 758, 1493, 1487, 1158, 1159, 1160 | drive/bracket/ND context |
| +62 / +63 / +64 | `0x60429b02` / `(0x622a0762)` / 1..6 from `0x622a063e` | |

**Record B (16 B)** [V offsets/keys]

| Off | Source | Meaning |
|---|---|---|
| +0 | `0x604294da` (sid 4, 0x80da) | Tv setting; 0x7fff → −0x8000; −0x7fff → key 0xedca |
| +2 | `ae_iso_get 0x60429519` (sid 6, 0x810a) | ISO; **0 = Auto**. If `0x622a076a` == 1 and Auto, returns 1536 (`0x603f3968`) |
| +4 | `ae_aperture_snapshot` → `0x60429548` (sid 3, 0x80ca) | Av setting |
| **+6** | **`ae_expcomp_get 0x604297db` (sid 2, 0x80ba)** | **exposure compensation** (±1280) + bracket offset from `0x60420f5c` (or bracket goes into +0 in M with fixed ISO, `0x60428861`) |
| +8 | bracket offset | |
| +12 / +14 | sid 64 (0x8bea: 85/128/256) / sid 86 (0x8e5a, ±1280) | EV step / **program shift** [I: added to Tv, subtracted from Av in `ae_program_line`, program modes only] |

**DP (124 B, `ae_detect_build 0x6042661b`)**: same getters. +18 gradation, +32/+34 Auto ISO upper/default, +46 ISO,
+48 Av, +50 exposure comp, +52 EV step, **+56/+58/+60 exposure shift** [V].

**Override path [V].** `0x60429666`, `0x604296df`, `0x60429733`, `0x60429787` and `ae_expcomp_get` return a byte or
halfword of a 24-B struct (`0x603b6fb7`: `0xa27396d8 + 24·(0xa2739720)`) instead of the property when sid 382 == 1 and
sid 323[1] == 0. The gradation getter's own branch is dead: `0x603042a9` is a stub that returns 0.

## 3. How the program uses them

- `ae_program 0x603fbe7a(a0 → {A, B, photometry, ., stab, ., result, aux})` [V]:
  - with 2 < mode < 0xdd, tail-jumps to a per-mode program from hash `0x60542558` (64 × 8 B, key mode−2);
  - else limits `0x603fc6ba` → `0x603fc4c5` → `ae_program_line 0x603fce91` → `0x603fc2c9`.
- **Per-mode program table `0x60541326`** (70-B rows, mode u16 at +0x44, lookup `0x603fca0a`). Rows hold Av/Tv/Sv bounds.
  Sv entries may be sentinels [V]:

  | Sentinel | ISO Auto (B+2 == 0) | Manual ISO |
  |---|---|---|
  | 0x9f00 | A+24 (Auto upper), or 0xd00 (25600) if 0 | B+2 |
  | 0xa000 | A+26 (default), or the floor if 0 | B+2 |
  | 0xa100 | as 0xa000, +256 when `0x603fe960` holds | B+2 |
  | 0xa200 | floor | B+2 |
  | other | literal | B+2 |

  Then clamp to [floor, 0xd00] unless key 0xc222 == 2. Floor = 0x600 (ISO 200) when `0x603fe808` holds, else 0x500
  (ISO 100) [V code; I which struct `0x603fe808` reads].
- Slow limit: A+30 through predicate `0x603fe925` and rule `0x603fc5d3` (MIN_SHUTTER) [V]. `0x603fc6ba` picks the
  Tv bound row by `0x603fe925` [V].
- Exposure comp: B+6 and DP+50 [V]. Program shift: B+14, applied only in a listed set of program modes
  (`0x603fce91`) [V].
- Exposure shift: A+40..44 and DP+56..60 [V]. **Consumer not located** (searched the AE library
  `0x603f3000..0x60421600` for metering-indexed reads) [open].
- Gradation: A+14 and DP+18 [V]. **AE consumer not pinned.** Lead: `0x604017cf` maps a field of 1 / −1 to +127 / −129
  (≈ ±½ EV) for some record [I].

## 4. Readers per key (immediate-load scan of the whole image) [V]

| Key | AE readers | Other readers |
|---|---|---|
| 0x949a | `0x60426886` (DP), `0x60427991` (A) | `0x603ecd57` (a0 = 0; ISO/picture-mode processing setup `0x603ecd3b`, from sid 112's refresh `0x602ed2ec → 0x603ec9f3`) |
| 0x30ea / 0x30fa / 0x310a | `0x604269c1` / `d8` / `ec` (DP), `0x60427a9c` / `ab3` / `ac7` (A) | `0x604290c4` (writes shift × 100 / 256 as a /100 rational to a2+2564 [I: metadata]) |
| 0x80ba (exp comp) | `0x60429824` (inside `ae_expcomp_get`, both records) | `0x60303028` (capture [I: EXIF bias]), `0x605519c4` |
| 0x8eb9 (gradation) | `0x6042965b` (inside `ae_gradation_get`, both records) | capture `0x602a803b`, movie `0x6030ec3d`, RAW edit `0x60c668ae` / `0x60c67295` / `0x60c672d5` |

Handle-init lines (`0x6020d7a0`, `0x6020d390`, `0x6020da3a` …) are lookups only (§0.2).
Descriptor callbacks [V]: sid 112 `0x602b524a`, sid 172 `0x602b5290`, sid 174 `0x602b52ce`, sid 86 `0x602b47b2`, sid 6
`0x602b4798`. Sids 273–275, 105 and 1147 have none: they are picked up at the next calculation.

## 5. Hook points

All sites are `dd <rel32> c3 ff c0 0c` (`call prop_get,[d2,d3],12`), 7 B. Retarget the rel32 only. The stub inherits
that frame, calls `prop_get` itself with the same d0/d1/a0, edits d0 and ends `ret [d2,d3],12`. This is the sc_get /
nr_get pattern. **Fallback:** if there is no active look, the field is "camera" (0) or the heap-P magic is bad, return the
stock d0 untouched. Look data: per FEATURE_GAPS, the LOOKS.BIN format has no such fields yet, so new shared look fields
must be proposed first (AGENTS.md).

| # | Feature | Sites | Stub | Risk |
|---|---|---|---|---|
| A1 | **Per-look Auto ISO ceiling** | `0x60426886` (DP+32), `0x60427991` (A+24). Same stub for both | d0 = clamp(look Sv, max(1536, sid 172 via a second `prop_get(0x9a9a)`), 3328). Never below the default: an upper below the lower feeds `0x60420bee` an inverted range [I] | **Low.** Only active with ISO Auto. The UI still shows the user's limit. Lag ≤ one DP rebuild (≤ 100 ms in mode 7) [I]. `0x603ecd57` stays stock (processing-mode choice). Camera: dim scene, look ceiling 800 vs user 6400 |
| E1 | **EI shift (hidden comp)**, smallest | **`0x60429824`** (1 site, covers B+6 and DP+50) | d0 = clamp(d0 + look offset, −1280, 1280) | **Low.** Bracketing adds on top as stock. EXIF bias and the UI keep the user's value. Bypassed in the sid 382/323 override path [V]. Like stock comp, it does nothing in M with fixed ISO [I]. LV brightness should follow [I] |
| E2 | EI as stock Exposure Shift | `0x604269c1/d8/ec`, `0x60427a9c/ab3/ac7` (+ `0x604290c4` for metadata) | d0 += offset, clamp ±256 | **Medium.** 6–7 sites, consumer unknown, stock range only ±1 EV. Use if E1's mode coverage is wrong on camera |
| G1 | **Per-look gradation** | AE `0x6042965b` (1 site, covers A+14 and DP+18) **plus** capture `0x602a803b` (request+1797). Movie `0x6030ec3d` optional | d0 = look value if in {−1, 0, 1, 2}, else stock | **Low–medium.** Patch both or neither, so metering and curve agree. The tone LUT row changes (VIDEO_LOG; test with the TONE_ENDS `lt_post` blacks/whites). LV may keep the user gradation (movie path) [I]. RAW edit stays stock |
| X | `prop_lookup` / registry, `ae_prop_handles_init`, record buffers | – | – | Avoid: the handles skip the lookup, and the records are rebuilt each call, so a write into them is lost |

## 6. Open

- Which task invokes `ae_frame_cb` and at what rate (one per sensor frame?). Emulator or camera log: count
  `0x6042760c` calls per second in LV.
- Meaning of AE mode `0x622a063e` (low nibble 0..7; 7 = the throttled path) and of the DP+62 state byte.
- The exposure-shift and gradation consumers inside the AE library and the photometry side.
- Whether sid 86 is program shift (code shape) or a flash value: one camera check (P, turn the dial, read sid 86).
