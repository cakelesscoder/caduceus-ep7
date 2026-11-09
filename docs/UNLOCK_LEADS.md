# Issue #10 unlock leads: Flat, focus bracketing, High Res, Pro Capture

Research only (2026-11-09): static reads of the E-P7 1.1 main plus string-set comparisons with the local E-M10 IV, E-M5 III
and E-M1 III mains. Nothing built or run. **[V]** = bytes, disassembly or string sets; **[I]** = inference. CPU addresses.
This extends FEATURE_GAPS "Issue #10 unlock leads" (2026-11-05); facts there are not repeated.

## Verdicts

| Lead | Code in E-P7? | Gate | To enable | Verdict | Effort | Risk |
|---|---|---|---|---|---|---|
| **Focus bracketing** | Yes, whole feature | None: stock AP mode 216 and Bracketing row 860 | Nothing | **Already stock** | 0 (5-min camera check) | – |
| Focus *stacking* | Lens check only; no sequence, record or merge | Absent backend (plus lens list) | New module | **Impossible** | – | – |
| **Flat, movies** | Yes (id 2000, gamma `0x604f4278`) | Hidden byte +925 | One more trigger on the shipped log hook (11 B) | **Feasible, easy** | 0.5 | Low |
| Flat, stills | Gamma table only | Still mappers hard-wire b6 = 0 | Small hook on the RGB gamma selector + a look byte | **Feasible** | 1 | Low–medium |
| **High Res Shot** | UI and sequencer flag only; iseq pixel-shift engine absent | Engine missing (no model flag) | New module, IS commands unknown | **Impossible** | – | High (IBIS hardware) |
| **Pro Capture** | Sequence part present; buffering receivers and UI absent | Engine missing | New module | **Impossible** (practically) | – | Medium–high |

No lead is held back by a model flag, a validator list or the rule engine. Where the UI exists it is gated only by ordinary
mode predicates. The missing pieces are the back ends.

## 1. Gates checked for every lead [V]

- **Settings rule engine** (`0x6045e5fc`, 201 × 20 B, sid at +0): no record for 24, 605, 758, 764, 775, 860, 1158 or 1493.
  So `isEnabled` passes all of them through condition 0.
- **Menu grey-out table** (`0x60adf518`, 611 × 12 B; predicates `0x60ade144`):

| Id | Conditions (bytes) | Meaning of the predicates read |
|---|---|---|
| 860 Focus BKT | `0x60adf459`: 0, 4, 5, 6, 57, 80 | 0 rule engine; 4/5/6 sid 4 ∈ {−32768, 32767, 0x8001} [I: lens state sentinels]; 57 sid 381 / sid 24 == 8; 80 sid 280 == 3 and `0x602aff1f` == 51 |
| 605 Bracketing | `0x60ade79c`: 0, 11–14, 16, 21, 31, 36, 45, 54, 57, 59, 62 | scene/mode exclusions (sid 24 == 14, 8, 143, 198 …; 109/323; 685 keystone; 44 movie) |
| 775 High Res | `0x60adea2f`: 605's list + 9, 10, 65, 80 | the same kind of mode exclusions; 9 = sid 26 ∈ {36, 37} with sid 109 == 0 |
| 24 shooting mode | 0, 36 | – |
| 758, 764, 1158, 1493 | no entry | internal sids, no row |

  None of these predicates reads a model or capability flag.

## 2. Focus bracketing: stock [V]

- AP list `0x611644e8..` holds value **216 Focus Bracketing** with 209–215 (Live Composite … AE Bracketing), and the sid 24
  validator `0x604cc68a` accepts 216 and 207 "Multi Focus Shot" (AP_CUSTOM.md §1, FEATURE_GAPS).
- PASM route: Shooting Menu 2 → Bracketing → **Focus BKT** (sid 860, `0x6116a870`). Its grey-out is lens and state only (§1).
- Sequencer `0x609352c9` sets FOCUS_BKT for sid 605 == 1 and (860 == 1 or sid 24 ∈ {207, 216}).
- **Nothing to unlock.** Answer #10 after the camera check: AP → Focus Bracketing, and Bracketing → Focus BKT in P with an AF lens.

### Focus stacking: absent [V string sets]

| String | E-M5 III (ships stacking) | E-P7 | E-M10 IV |
|---|---|---|---|
| `changeSequence() changed ATT_FOCUS_STACKING`, `Set CMP_SEQ_ATT_FOCUS_STACKING` | yes | no | no |
| `RecordController::EvRecRecordMediaStacking`, `…ErrorForStacking`, `EvRecTakeFree Stacking` | yes | no | no |
| `RecRecordMediaErrorStacking::Wait For Combining Finish`, `recordMediaFocusStacking() combine ERROR` | yes | no | no |
| `fcs_check_focus_stacking_enable` + lens list `0x60716991`, `getFocusStackingStatus`, warning strings | yes | yes | yes |

- The E-P7 string set matches the E-M10 IV here, line for line. The shared focus library carries the lens check, but the
  sequencer attribute, the record handlers and the merge are absent [I strong: no code behind them].
- Enabling would mean writing the stack merge: alignment and per-pixel sharpness selection over 8–15 frames of 20 MP. On the
  CPU, at grain-engine speed (about 0.25 s per instruction per pixel, HALATION_RED §14), that is minutes per stack. **Impossible.**

## 3. Flat

- **No Flat picture mode or tone-curve row in the stills tables** [V]: `COLORTONE_FLAT` / `COLORTONE_SUPERFLAT` are debug-enum
  names only (`0x607c1664`); OSD strings 2886/3258 belong to the shared resource.
- **Movie Flat** [V, VIDEO_LOG]: effect id 2000 = gamma `0x604f4278` with identity luma `0x604fa082`, selected by +925 = 1.
  `patches/video_log --trig-flat N` adds it (11 B, fits the 64-B claim `0x60210c90–0x60210cd0`). **v0.30 still ships only the
  43-B log hook** (`releases/v0.30/edits.json`). Trigger proposed: movie Portrait. Effort 0.5 session, risk low.
- **Stills Flat** [V gate, I route]: the still mappers pass b6 = 0 (`0x603eaa71`, `0x603ececd`), so ids 2000/2001 never reach
  stills. Do not change b6: the effect id feeds other selectors. Instead hook the RGB gamma selector `0x603ae354` on key-11
  stills from a slot byte and return `0x604f4278` (plus the identity luma, as id 2000 does). Never patch row 0 (VIDEO_LOG).
  About 40 B, one look byte, so a LOOKS.BIN/Control Panel field. Live view would not match unless the LV selector is hooked too.
  Effort 1 session. Value is moderate: the look tone controls already give a low-contrast base; Flat adds the gentler toe.

## 4. High Res Shot: engine absent [V]

- **Present:** the row (sid 775, `0x6117a1b0`, validator [0, 1]) with a full grey-out entry (§1), drive value 18, sequencer
  test of sid 758 at `0x6093531d` → "PIXSHIFT" (`0x60b41049`), `changeSequence() changed ATT_PIXSHIFT` (`0x60b32b35`), the record
  side `DevRec_Rec::recordMeidaPixShift` (real code at `0x60a3dbd9`), playback pixshift readers, and sensor-mode names
  `HIGH_RES` / `HAND_HIGH_RES`. The `rec_raw_pixshiftsr_*` strings are an (address, id) name table (`0x6053cbf8`), not code.
- **Absent:** the pixel-shift sequencer. `iseq_pixshift_sr_*` (`0x607024c6..`) and `iseqPixshiftSrCb*` are names in the iseq
  trace enum only, as LIVE_ND §1 found.

| iseq source files compiled in | E-P7 | E-M10 IV | E-M1 III |
|---|---|---|---|
| `iseq_pixshift_sr*.c` | 0 | 0 | 17 |
| `iseq_nd*.c` | 0 | 0 | 17 |
| `iseq_swpa*.c` (panorama) | 16 | 16 | 0 |

  The E-P7 iseq file list is identical to the E-M10 IV's, which never shipped High Res [I product fact]. (The E-M5 III image has no iseq file
  names, so it can't be compared this way.)
- **What the absent module did** (from its names): IS ASIC commands for the sub-pixel moves (`if_sys_sasic_cmd_snd`), 8 Bayer
  dumps, 80 M Bayer and RGB buffers, and the ISP `hr_ems` / `hr_compose` jobs. None of these jobs is built anywhere in the E-P7.
- **Hardware:** the E-P7 has 5-axis sensor-shift IBIS, but whether its IS controller accepts half-pixel step commands is unknown
  and can't be tested offline; a wrong IS command is a hardware-side risk. Memory: Multiple Exposure holds at most 5 Bayer frames
  (LIVE_ND §2); High Res needs 8 plus an 80 MP output. A CPU compose would take minutes.
- **Verdict: impossible.** The nearest thing that works is Live ND (multi-frame average, shipped in v0.30) for noise.

## 5. Pro Capture: buffering back end absent [V]

- **Present:** `CmpSqp_SequencePartsZeroLag.cpp` with `startZeroLagBuffering`, `execZeroLagBuffering`, `getZeroLagBuffrLimit`
  (real code; callers `0x607c900b`, `0x6097482e`); drive values 20/21 "Pro Capture High/Low" (`0x611673f4`, `0x61167400`); the
  sequencer gate `0x609353c2` on internal sids 1158 / 764 / 1493 (no validator, grey-out or rule records).
- **Absent:** the receivers and state of the pre-shutter buffer.

| String | E-M5 III (ships Pro Capture) | E-P7 | E-M10 IV |
|---|---|---|---|
| `rcvExecZeroLagBuffering`, `rcvExecZeroLagTimer` | yes | no | no |
| `getZeroLagBufferingStatus`, `setZeroLagBufferingState` | yes | no | no |
| `Osd_Black_Viewer::update_pro_cap_buffer_shooting`, `Rec_Info_Viewer::ProcapBuffer`, `GCWnd…UpdateProcapBufferIcon` | yes | no | no |
| `CmpSqp_SequencePartsZeroLag.cpp`, `execZeroLagBuffering`, `getZeroLagBuffrLimit` | yes | yes | yes |

  The sequence part is a shared library compiled into every body. The part that answers its messages and keeps a ring of frames
  during the half-press is not in the E-P7 [I strong].
- **Hardware:** the E-P7 shoots 15 fps electronic, so read-out is plausible [I]. RAM for a ring of full frames is unknown.
- **Verdict: impossible in practice.** It needs a new real-time module (continuous read-out into a ring, then saving N frames).
  There is no stock template on this body to follow.

## 6. Next steps

1. Camera: confirm Focus Bracketing in AP and Focus BKT under Bracketing in P, then answer #10.
2. Build movie Flat (`--trig-flat 4`) into the current build if wanted.
3. Stills Flat only if users ask: one session, a look byte, gamma-selector hook.
4. Close High Res, Pro Capture and focus stacking on #10 with the tables above.
