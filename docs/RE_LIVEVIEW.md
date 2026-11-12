# Live-view job lifecycle and stills RGB gamma (E-P7 1.1)

Static analysis only: objdump (`tools/dis.sh`), `tools/ep7_xref.py` and REA/Ghidra. No build, emulator run or camera test.
Answers atlas unknowns #1 and #5. Tags: **[V]** read from bytes or disassembly, **[I]** inference. Raw listings are in
`~/ep7fw-private/decomp/liveview/` (private, not in the repo). New symbols are in `tools/atlas/new_liveview.py`.

## 0. Short answers

1. **Live view runs on CPU2, in the movie-recorder (MVR) task family** [V bytes, I for the core]. A second static
   task table at `0x6003d344` (ids 0x2001..0x201c) pairs with the name table `0x61400b18` (BOOT_CPU2, MVR_MAIN, …).
   The LV job state machine runs in **MVR_MAIN** (id 0x2002, entry `0x603291af`, prio 25).
2. **Setting change → LV**, in order: TAKE-side ops slot `0x6029413f` → post `0x60296ec8` → TAKE_MOV (CPU0 task 120)
   → "TH" through-update `0x60303ad3` → `0x60327b3c` (record build `0x60309805`) → deferred flag set `0x6031da00`
   (MVR_MAIN flag, bit 0x1) → MVR_MAIN `0x6032a07d` → **event 7** → per-state action (`0x6032dd61`, …) → settings
   re-read `0x6032cba8` → apply `0x6032936a` → comparator → **update `0x603118d6` → `0x60321f75`**, or delete and
   rebuild `0x60311440` / `0x603114e0`. [V call graph; I for what each hop means]
3. **Look switch without a mode switch:** event 7 is enough. Its handlers re-read the effective S and WB properties
   themselves (`0x6032cba8` → `0x6030ba2b` → `prop_get`). Effects that live in job flags (bloom 0x80, Pin Hole) also
   need the comparator to return 2 (the LV_ART_PREVIEW §7 hook). **Lag cause [I]:** about five async hops across two
   cores and three tasks for every refresh. The S-nudge refresh also pays the settings-manager path. Flag changes
   never trigger a rebuild in stock.
4. **Stills per-channel gamma:** the **gamma stage `0x603ae80d`**, called from the dev stage list at `0x603b14a6`
   (after `mono_selector`, before `color_selector`/tone). It calls `gamma_select` `0x603ae354`, which returns **three**
   pointers (R, G, B), then `rgb_gamma_set`. The hardware copy `0x60346e37` has a real per-channel mode. **Stock
   already split-tones:** Vintage I lifts blue in the shadows (B[0] = 1283) and cuts it in the highlights
   (B[255] = 3818), and Cross Process I/II use three different curves. So a split tone is three bank-A-format curves. [V]

## 1. Tasks and mailboxes

| Item | Value | Tag |
|---|---|---|
| CPU2 task table | `0x6003d344`, 28 × 28 B, same record as `task_desc_table` (`{id, attr, 0, entry, prio, stack, 0}`), ids 0x2001..0x201c | V bytes |
| CPU2 task names | `0x61400b18`, 26 B `{name[24], u16 n}`, n = 1..0x1c ↔ id 0x2000+n (CPU1 names are at `0x6140033a`, ids 1..0x29) | V bytes, I pairing |
| Relevant CPU2 tasks | 0x2002 MVR_MAIN `0x603291af` p25 · 0x2003 MVR_MOVIE `0x6032fe67` p26 · 0x2005/0x2007/0x200a MVR_IMG1/IMG2/IMG_POST share entry `0x60327cfd` p25 · 0x2006 MVR_CALC `0x60325123` · 0x2008 MVR_ENC `0x60325eae` · 0x200c MVR_RECVIEW `0x603324b6` · 0x2012 REC_MAIN_CPU2 `0x603e28c6` · 0x2014 REC_VIEW_CPU2 `0x603f2b1f` · 0x2017 MVR_EXEC `0x6032629f` p24 | V bytes |
| MVR mailbox ids | u16 words `0x6004109e`.. = 0x2001, 0x2002, 0x2003, 0x2004, … `0x600410be` = 0x2011 (the "Rec View" mailbox) | V bytes |
| Generic MVR service loop | `0x6032560b(d0 = mailbox id, a0 = ctx)`: receive (`0x6031d88c`), then handler slot from table **`0x604e2f64`**: slot 0 (mbx 0x2001/2) `0x60329646` (LV state machine), 1 `0x6032819d`, 2 `0x603301cc`, 3 `0x603252a9`, 4 `0x60325ed9`, 5 `0x60332acc`, 6 `0x603324fc` (Rec View) | V |
| MVR_MAIN loop | Waits on event flag (id word `0x60041076`, pattern 0x7fff) at `0x6032920e`. Bit 0x4 → drain mbx 0x2001, bit 0x8 → mbx 0x2002, other bits → `0x6032a07d` (flag → internal event) | V |
| Flag set | `0x600510e8(d0 id, d1 bits)` (set_flg). Deferred form `0x6031da00(a0 req{u16 flag, u32 bits, u32 delay, u8 mode})` picks a setter by bits (1 → `0x6031daaa`, 2/0x400 → `0x6031dafa`, 0x4000 → `0x6031db4b`) and arms it through the alarm/timer call `0x6005633f`. Stock posts use delay 0, mode 2 | V code, I "alarm" |
| TAKE_MOV | CPU0 task 120 `0x60553eca`, prio 24: waits on its flag (id `0x60040c2e`), dequeues requests from queue object `(0x6223cbbc)` (`0x60554128`); arg == 0 → full step `0x60554173` → … → `0x605542ba` → **`0x60303ad3`** | V |
| Through-update post | `0x60296ec8`: enqueue `{1, 0}` on `(0x6223cbbc)`, set TAKE_MOV flag bit 1. Only caller `0x6029413f`, gated by `(0x62236dbd) != 0`. `0x6029413f` sits in an ops struct built on the stack at `0x6054cb48..` (slot word `0x6054cb98`; sibling `0x60294128` → `0x605540dc`). The caller of that slot is indirect and was not found | V, I role |

## 2. LV state machine (MVR_MAIN, mailbox 0x2001/0x2002)

- **Table `0x604e315c`** [V]: 13 states × 28 events × 8 B `{u32 action, u32 post}`. Row stride 0xE0, entry =
  base + 0xE0·state + 8·event. The dispatcher **`0x6032967e(d0 event, a0 state*, a1 ctx)`** calls `action(state,
  entry, ctx, &out)` and then `post(state)`. A non-zero post result logs; a zero result reports state change via
  `0x60305a7a(0xe, …)`.
  - **Correction to LV_ART_PREVIEW §7:** it reads the table at `0x604e3190`, which is 4 B into an entry. Its
    "event 0" handlers (`0x6032dd61`, `0x6032ddb2`, `0x6032de23`, `0x6032de8e`, `0x6032dee6`, `0x6032f09e`) are
    **event 7**, with post `0x6032e074` (`0x6032e0aa` in state 1). Event 7 exists in all 13 states.
- **Event sources** [V]:
  - Mailbox 0x2001 code (msg+4) through `0x60329479`: 1→0, 2→1, 16→2, 26→3, 17→4, 23→5, 18→6.
  - Mailbox 0x2002: 1→11, 5→12, 2→13, 3→14, 4→15, 6→16, 7→17, 8→18, 10→19, 33→24, 34→25, 35→26, 36→27
    (jump table `0x604e3f00`).
  - Flag bits, through `0x6032a07d`: **0x1 → 7**; 0x2/0x400 → 8 (`>dmy_cap`); 0x10 → 9 (`>rec_err`); 0x20..0x100 → 10
    (`>allow_rec_end`); 0x200 → `>post_through_end_timeout`. Before posting event 7, bit 0x1 runs `0x6032c82d`, and
    0x1/0x2/0x400 run `0x60305edd` / `0x60305e3b` / `0x6031a8a0` / `0x6032c703`.
  - Job-end word bits, through `0x6032caec`: 0x4000 → 23, 0x800 → 20, 0x1000 → 21, 0x2000 → 22.
- **Event 7 action** (e.g. `0x6032ddb2`) [V]: `0x6032cba8` (S/WB re-read: `0x6030ba2b` → `0x6030bb2d` (WB
  `prop_get` at `0x6030bb5b`/`6e`) and `0x6030bccc` (S, 0xF6EA)), then `0x60309d90`, `0x6030a801` and **`0x6032936a`**.
  `0x6032936a` → `0x6032a1d6` → … → `0x6032a706` follows LV_ART_PREVIEW §7, including comparator `0x60311278`.
  **So compact WB and S are refreshed on every event 7** (answers atlas #1 "when compact WB/S refresh").
- **Paths from a settings message into event 7:**
  - `0x60303ad3` ("TH") → `0x60327b3c`: `0x60308de5`, `0x6030b3b9`, `0x60309805(rec, 0)`, then `0x6031da00` with
    {flag `0x60041076`, bits 1, delay 0, mode 2}.
  - `0x6030ddc7() == 2` takes `0x60327b93` instead (not traced; movie [I]).
  - The other `0x6031da00` users are `0x60303b28` ("THrv", a callback, refs `0x60303bb2`/`0x60303bec`), `0x60303ce7`,
    `0x60303ed0` and `0x60327c36`. [V]
- **Job delete** `0x60311440` (`0x603150f9` / `0x603151a5` / `0x6031524d` / `0x60321f18` / `0x6031fc19`) and **build**
  `0x603114e0` run in MVR_MAIN. Rebuild completion comes back as job-end events 20–23 [I]. Update `0x603118d6` →
  `0x60321f75` → `0x603220e5` reuses the job (LV_ART_PREVIEW §7) [V].

## 3. Look change into live view, and the lag

What each part of a look needs [I unless marked]:

| Look part | Where LV reads it | What makes it appear |
|---|---|---|
| H/L (bundle, LOOKS.BIN slot), gamma pointers | Dev stage list, per development (`hl`/`lv`, gamma stage) | Nothing, if the stage list runs per development. Evidence: the gamma stage keeps a last-pointers cache (`O+5736`) and the LUT upload has an owner/dirty tracker. Both only make sense for repeated calls on one job |
| S ×12, WB | Params from the record, read on event 7 (`0x6032cba8`) [V] | Event 7 → update path |
| Job flags (bloom 0x80, Pin Hole 0x400, …) | Job constructor only [V] | Event 7 **and** comparator result 2 (LV_ART_PREVIEW hook `0x60329ba2`) |
| Art Effect id (rec+296) | Comparator `0x603113cc` [V] | Stock rebuild |

**Lag [I]:**
- An S-nudge refresh runs settings manager → descriptor callback → effective builder (LV_BUNDLES §2.3) → TAKE-side
  ops → TAKE_MOV queue (CPU0, prio 24, a long multi-step `0x60554173`) → `0x60309805` → alarm (delay 0, so at least the
  next tick) → MVR_MAIN on CPU2 (prio 25) → event 7 → re-read of every LV property → update. The new params land on
  the next development after that.
- A comparator rebuild adds a job teardown and rebuild, which waits for frames in flight (events 20–23).
- No single wait (dly_tsk) was found on the path. The lag is the chain itself, plus any frame already queued on the
  old parameters.
- Not measurable statically. A camera timing test would decide it.

## 4. Stills per-channel RGB gamma (atlas #5)

| Item | Detail | Tag |
|---|---|---|
| Stage | `0x603ae80d(a0 = stage ctx)`. ctx+4 = request R (key at R+8..11, type R+14), ctx+12 = colour output O. Called once, from `dev_stage_list` at `0x603b14a6` | V |
| Order in `0x603b1466` | `mono_selector 0x603acfe4` → **gamma `0x603ae80d`** → `0x603ade14` → (`0x603aade3` ? mono branch `0x603adcdd`.. : `0x603af7c6` → `color_selector` → `tone_lut_build` → `0x603b0c66` → `chroma_stage` → `0x603adcf0`) | V (call order; hardware order I) |
| Selector | `gamma_select 0x603ae354(a0 R, a1 &R_ptr, d0 &G_ptr, d1 &B_ptr) → d0`. Returns 1 for one-curve cases and 0 for the three-curve art cases and R+1838 == 257 | V |
| Curve choice | Effect id (R+8 as u32) through the hash `0x60532110` (16 × `{id−1999, handler}`). Pointer table `0x60530b6c`: 25 rows × 8 words (4 columns × {normal, variant}). Column from R+14 by `0x603ae2fd`; variant from `0x603b5606`. Ordinary modes use row 0 (`0x604ede78` / variant `0x604ee078`); R+1879 → row 1 (identity); `0x603b564d` → row 2 | V |
| Three-curve rows (R, G, B) | `0x0101006b` Cross Process I → rows 5/6/7; `0x0102006b` II → 9/10/11; `0x01010079` Vintage I → 12/13/14; `0x01020079` II → 15/16/17; `0x01030079` III → 18/19/20; `0x0102007b` Bleach Bypass II → 21/22/23 | V |
| Setter | `rgb_gamma_set 0x603ae7d3(a0 O, a1 R, d0 G, d1 B)`: O+2596/+2600/+2604 = R/G/B, clears O+4 bit 0x1000. Only callers: `0x603ae995` (this stage) and `0x603af2db` (Ligne Clair kind 3) | V |
| Change cache | `d3 = (R+1484) + 5736` (O-side object, zeroed by `0x60343f9d..`): `{R*, G*, B*, 12 B copied from the stage frame, u8 at +20}`. If all three pointers match and `0x603b5ddc` returns 4, the stage **skips the setter** and clears ctx+108 bit 0 (no LUT re-upload) | V code, I meaning |
| Hardware copy | `0x60346e37` (from `0x60345ebe` at `0x60345f9b`/`0x60345fbd`). Skipped unless the owner changed (statics `0xa27360ec[2]`) or ctx+108 bit 0 is set. R == G == B: one 256-word block at window+0x000. Otherwise R → +0x400, G → +0x800, B → +0xC00 (bytes; u32 words, value = u16 entry). The O+2608 curve → +0x1000. Higher blocks come from O+0xC34.. and O+0xC5C | V |
| Table format | 256 × u16, entry k is the output for 12-bit input 16k (VIDEO_LOG bank A). Output 0..4095. Endpoints are free (Vintage I B[0] = 1283, B[255] = 3818; Bleach II all channels 385..3806). All stock curves are monotone | V |
| LV share | `0x6039a97b` (stream path) also calls `gamma_select` but keeps only the G pointer, for a single curve. A swap at the stage call site does not reach it | V |

**Split tone fits [V for the mechanism, I for the look].** Give R/G/B different shadow offsets and highlight
shoulders, for example the OM-3 `st_run` formula applied per channel to row 0 `0x604ede78`. The CPU copy reads the
curves with `movhu`, so any CPU-readable RAM works. Use an uncached `0xa…` buffer, because CPU2 may run the upload
for LV [I].

## 5. Hook points

| # | Site | Purpose | Notes / risk |
|---|---|---|---|
| G1 | **`0x603ae830`**, 5 B `f8 92 3c 5c 24` (`movbu d0,(60,sp); mov (36,sp),a0`). No branch target in the span (brute scan) | Split tone: after `gamma_select` returns, for key 11 + transport/slot split ≠ 0, overwrite (68/72/76,sp) with RAM R/G/B curves. Replay, resume `0x603ae835` | **Low–medium.** It runs **before** the cache compare, so new pointers invalidate the cache and force the upload. **Rule: a changed look must use different buffer addresses** (per-slot buffers or a 2-set ping-pong). Rewriting one buffer in place leaves the old LUT in hardware. Keep d0 as stock: d0 = 1 runs `0x603b5e8c` on the curves, and what it derives is unknown, so check it in the emulator. Gate key 11 only; log 2001 and Flat 2000 stay stock. 1.5 KB of RAM per buffer set |
| G2 | `0x603ae995` (5 B call to the setter) | Simpler pointer swap | **Not recommended.** A cache hit skips the call, so a look change with the same stock pointers never uploads |
| L1 | Call `0x6029413f` (`calls`; frame `add -4,sp` / `ret [],4`) from our CPU0 look-change code | LV refresh through stock's own through-update path, with no property write | Medium. It is self-gated on `0x62236dbd`, but it is unproven that stock uses this ops slot for settings changes (indirect caller not found) and it runs the long TAKE_MOV step. Replaces the S nudge if a camera test shows the same refresh |
| L2 | Post `0x6031da00` with `{(0x60041076), 1, 0, 2}` (stack request, as at `0x60327b64..7b`) | Fastest event 7: skips the settings manager and TAKE_MOV, and the S/WB re-read still happens | Medium. Skips `0x60309805`, so the record stays as built. That is fine for the update path but may miss fields read only from the record. Stock already calls it from CPU0 code (TAKE_MOV). Never call it from an ISR |
| L3 | LV_ART_PREVIEW §7 comparator hook `0x60329ba2` | Rebuild when job flags must change | As documented there. It is reached from event 7, so L1 or L2 feeds it |
| X | Anything inside MVR_MAIN, or the state table | – | Avoid: CPU2, prio 25, shared with movie recording (states 7–12 look like recording [I]) |

## 6. Open

- Who calls ops slot `0x6029413f` (an indirect call from the settings or TAKE side), and whether
  `0x602b8916` (effective builder) reaches it.
- Whether the dev stage list runs every frame for LV, or once per job plus each update. Emulator: count gamma-stage calls
  per `0x60321f75`.
- What `0x603b5e8c` derives from the curves (into stage frame +44..+64), and what reads it.
- How long the lag actually is on the camera: S nudge vs L1 vs L2.
