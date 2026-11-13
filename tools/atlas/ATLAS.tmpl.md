# E-P7 1.1 stock firmware atlas

One map of how the stock PEN E-P7 1.1 (build 1100) main program works, so feature work starts from known
addresses. It consolidates `docs/*.md`, `patches/*/`, `tools/*.py`, `generated/*/symbols.json` and `WORKLOG.md` as of
2026-11-12. It does not replace the feature docs: each row links the doc with the detail.

- **Scope.** Stock code and data only. Our own code-space claims, hook sites and FF guards are in
  [CODE_SPACE_MAP.md](CODE_SPACE_MAP.md); never allocate from this file.
- **Addresses** are E-P7 1.1 main CPU addresses (decoded offset + 0x60020020) unless marked RAM/OSD. **None carry to
  another body** ([FIRMWARE_GUIDE.md](FIRMWARE_GUIDE.md) §12).
- **Tags** as in FIRMWARE_GUIDE: **V** code/bytes/emulator, **C** camera-proven (a stronger V), **I** inference.
- **Machine-readable:** [atlas.json](atlas.json) ({{NSYM}} symbols, incl. {{NTASK}} static tasks).
  `tools/atlas_annotate.py START STOP` runs `tools/dis.sh` and names every atlas address in the listing.
- **New in this atlas (checked against the bytes here):** the static task descriptor and name tables (§2.1), the
  mailbox-id table, and the corrected COLOR editor record bases (§4, §15).

Contents: [1 Boot](#1-boot-and-sections) · [2 RTOS](#2-rtos-tasks-queues-memory) · [3 Settings](#3-settings-property-store) ·
[4 UI](#4-ui-menu-framework) · [5 OSD](#5-osd-component) · [6 Live view](#6-live-view-and-display) ·
[7 Capture](#7-capture-settings-to-job) · [8 Pipeline](#8-image-pipeline) · [9 JPEG/EXIF](#9-jpeg-and-exif) ·
[10 File I/O](#10-sd-and-file-io) · [11 Movie](#11-movie) · [12 Lens/AE](#12-lens-ae-and-sequencer) ·
[13 Updater](#13-updater-and-container) · [14 Code space](#14-our-code-space) · [15 Conflicts](#15-address-conflicts-and-resolutions) ·
[16 Unknowns](#16-known-unknowns-ranked)

## 0. Address space

| Range | What | Tag |
|---|---|---|
| 0x60020020–0x600d7800 | Base image, resident (kernel, drivers, flash, boot) | V |
| 0x600d7800–0x6143a800 | Sections 1–9, copied at boot in order 1,7,2,3,4,5,6,8,9 (table: FIRMWARE_GUIDE §2) | V |
| 0x60020020–0x6191ffe0 | Loaded image; **stock never stores here** (32,217 abs stores swept) | V |
| 0x60230800–0x6025eb50 | .data init image → RAM 0x61f98540 (RAM = flash + 0x1d67d40) | V |
| ≥ 0x61b2xxxx | Stock writable statics; heap pools, .data | V |
| 0x621caf00–0x62796888 | .bss, zeroed at boot (0x6002046d) | V |
| 0xa1dd8d40–0xa1e85800 / 0xa1f8d800–0xa1f98540 | Heap class 2 (≤16 KB) / class 1 (≤2 KB), uncached | V |
| 0xa3091000.. | OSD runtime banks, fonts, strings (§5) | V |
| 0x98xxxxxx–0x9cxxxxxx | MMIO: 0x98100058 windows, 0x98e0008c WDT/ctrl, 0x99700000 bus monitor, 0x99901xxx JPEG, 0x9c00xxxx display | V |
| 0x40000000.. | Logical flash. **Never write** | I (brick risk) |
| 0x47000000.. | Boot-ROM helpers outside the package (memcpy 0x47001052, memset 0x4700115e, WDT kick 0x470008ae) | V refs |

Section boundaries by section: base, 1 0x600d7800, 2 0x60280800, 3 0x6057b200, 4 0x605baa00, 5 0x6075a800,
6 0x60ba7000, 7 0x612c7000, 8 empty, 9 0x613c1000. Rough subsystem layout [I from the symbols below]: sec 1 drivers,
lens, display, OSD loader; sec 2 settings, capture, job and ISP stages (0x6028–0x6055); sec 4 file system (0x6061–0x6065);
sec 5 app framework, HLS, sequencer, GUI facade (0x6076–0x60b9); sec 6 GUI screens and editors, updater, playback
(0x60ba–0x6124); sec 9 debug dumps and the task name table.

## 1. Boot and sections

Startup: `BOOT_CPU0` → section load FSM (copies 1,7,2,… and sets 0xa272e420 bits) → USRSTART2 (waits on each
section, runs sec-2 initializers at its start, creates the HIGHLEVEL framework) → USRSTART3/4 → USRSTART5 (starts
FIRMUP_SRV). Boot tail resets volatile settings (0x60192961). The HIGHLEVEL app framework is created only after wait(6) (sections 1–6 loaded).

{{TABLE:boot}}

## 2. RTOS: tasks, queues, memory

Kernel with μITRON-style error codes (E_CTX −25) [I]. Lower priority number = higher priority (REC_IMAGE 54 pre-empts SYS_WDT 55). Static tasks are
described by a 28-B record per id; dynamic tasks (HLS_EVENT) are created at run time. IDs of tasks and mailboxes are
read from constant u16 tables (`movhu (0x60040d20),d0` = FILECLBK's mailbox).

**Rules learnt** ([SD_V2_CRASH.md](SD_V2_CRASH.md), [HALATION_RED.md](HALATION_RED.md) §18–22): file calls from any
CPU0 task are a blocking RPC to FILECLBK; never call them from a task FILECLBK may wait on (FILEFGND). The hardware
watchdog is kicked only by SYS_WDT; a CPU-bound pass in a higher-priority task starves it (Caduceus raised the limit
10 → 30 s). Interrupt-masked locks are per CPU.

{{TABLE:rtos}}

### 2.1 Static task list (descriptor table 0x600389d0, names 0x613ff240) [V bytes]

Record: `{u32 id, u32 attr, u32 0, u32 entry, u32 prio, u32 stack, u32 0}`; descriptor id == index for 1..137; attr is 0 except BOOT_CPU0 (2) [meaning unknown].
Ids 138–143 (DBG_OUT, CPUCONN_CPU0, CPUCALL_CPU0, S_SHELL, U_SHELL, PWR_STANDBY) have names but no matching static
record (other core or created elsewhere [I]). Roles from names are [I] unless a doc covers them.

{{TASKS}}

## 3. Settings (property store)

Model: a **sid** (0..1768, plus virtual sids ≥ 10000 like 15271/15272) maps through 0x604d6c14 to a property
**key** `id<<4 | type` and an index; values live in a RAM registry (no fixed RAM address). Writes go GUI facade →
settings manager → set → store → post-set → the sid's descriptor callback (+24 of a 60-B registry record). Allowed values
come from the static validator records. Per-mode planes and forced pairs (rule DB, mode blocks) override values
while a mode is active.

| Record | Layout | Where |
|---|---|---|
| sid table entry | `{u16 key, u16 index}` | 0x604d6c14 + 4·sid |
| validator | `{u16 sid, u16 attr, u32 list, u32 alt, u16 bytes, u16 elem, u8 sub, u8 type, u16 0}` (20 B) | 0x604cc98c + 20·n |
| descriptor | 60 B, +24 on-change callback | 0x604317ac + 60·n (439) |
| rule DB | 20 B, sid at +0 (201) | 0x6045e5fc |
| grey-out item | `{id, cond bytes, n}` 12 B (611) → predicates 0x60ade144 | 0x60adf518 |
| mode forced block | index entry `{u16 mode, u16 sub, u32 block, u16 count}`, pairs `{sid, value}` | 0x60475e88 / 0x6047a530 |

Key sids: 111 effective picture mode (key 0x9481; GUI enum, Vivid 0), 1645/1646 normal/profile lists (key 0xc9b2),
15272 which list is active, 908/973 effective COLOR/MONO profile (0xF6B1/0xF731), 915–926 effective S (0xF6EA),
44 movie mode, 270 aspect (key 0x3081), 24 drive-ish mode (211 = AP ME), 1147 Lowest S/S (0x536a), 143 Noise Filter,
7 Sharpness (0x8119), 47–56 buttons. Detail: [FIRMWARE_GUIDE.md](FIRMWARE_GUIDE.md) §3, [MOVIE_COLOUR.md](MOVIE_COLOUR.md) §2.

{{TABLE:settings}}

## 4. UI (menu framework)

Layers, top down: **screens** (group + state; SsMenuLv matrix dispatch) → **actuators/editors** (keyed records of
handler words; data-hookable) → **children** (one per setting) → **labels** (value → label source → kind-specific
draw) → GUI **facade** for every value read/write. Key events arrive as 0x90xx codes; only some reach a given screen
on camera (INFO yes, Movie/Delete never in the COLOR editor).

| Record | Layout |
|---|---|
| Editor record (56 B) | +0 key, +4 init 0x60e20a54, +8 child_get 0x60e20bc7, +12 Up 0x60e20e0a, +16 Down 0x60e2107a, +20 Left 0x60e213bb, +24 Right 0x60e21852, +28/+32 dial 0x60e21cae/0x60e21efb, +36 catch-all 0x60e22191, +40 0x60e223ae, +44 INFO 0x60e22579, +48/+52 0 |
| Editor parent object | +48..+88 copies of record +12..+52; +100 key; +120 child count; +122 cursor; +124 child[] |
| Property child (144 B, vtable 0x61155a7c) | +84 sid, +88 count, +90 current index, +96 codes, +100 list |
| Menu page (28 B) | `{u16 tab, u16 n, items, helps, ndesc, desc[], n2, x}`; item 12 B `{u32 sid, label src}`; desc 8 B `{u16 id, u16 count, list}` |
| Option list entry | `{u32 value, label source}`; label source `{u16 kind, u16 id, u32 text}`; kinds 3 bitmap, 4 string id, 1/2 string+text, 5/6/12 char* (≤32), 7/8 bitmap+text |
| Cursor_Move per-mode init | `{u16 mode, fn}` × 314 at 0x61151474 |

Events: 0x9004/0x9006 step, 0x9008/0x900a sector, 0x900c commit, 0x900e MENU, 0x9010 PLAYBACK, 0x9012 Movie, 0x9014 INFO,
0x9016 Delete, 0x903e held OK; half-press 0x02000100 (HLS). Buttons: key → sid (0x60f389a8) → function code → action
(0x60f38af8). Detail: [LOOK_EDITOR.md](LOOK_EDITOR.md), [LOOK_MENUS.md](LOOK_MENUS.md), [BUTTONS.md](BUTTONS.md), [ASPECT.md](ASPECT.md) §1b–1j.

{{TABLE:ui}}

## 5. OSD component

Component 0x101, loaded from flash with no CRC. Bitmap descriptor `u16 fmt, u16 w, u16 h, u16 field6, 0, 0, u32 enc
size, u32 payload`; RLE modes 11 (8-bit index, 4-bit run), 10, 1, 9 (glyphs). Strings UTF-16LE, edit in place at the same
length. Detail: [OSD.md](OSD.md), [FIRMWARE_GUIDE.md](FIRMWARE_GUIDE.md) §5, `tools/osd_extract.py`.

{{TABLE:osd}}

## 6. Live view and display

Live view and movie share the still pipeline (same constructor, stage list, selector and tables); the difference is the
input record R and that LV jobs never pass a converter (their readers use property 0xF6B1). LV job key is fixed at job
build; parameter updates reuse the job.

| Record | Fields |
|---|---|
| LV/movie record R | +292.. from message A+352; **+294 picture mode**, +295 art sub, +296 Art Effect id; +660 Rec View; +902 class input; **+925 hidden gamma (1 Flat, 2 log)**; +2117/2118; **+2119..2130 S ×12** → params+5538 |
| Settings message A | +20 = 0xF6B1 profile (0 zeroes R+2119); +352..; +354 picture mode |

{{TABLE:liveview}}

## 7. Capture: settings to job

Order: capture population (settings → capture record) → capture setup (EXIF fields) → WB resolution → converter
(capture → params = job+36, mode-gated) → **job constructor (builds the work list inside it)** → converter writes the
Caduceus extension → work list runs synchronously in REC_IMAGE.

| Capture record offset | Field |
|---|---|
| +18 | EXIF Orientation (from +24168 when 3/6/8) |
| +312 | remaining shots |
| +1384 / +1448 / +1554 / +1660 | Artist / ImageDescription (32) / Copyright / UserComment (125) |
| +2172 | maker string ("OLYMPUS DIGITAL CAMERA", key 0x8f11) |
| +3028/+3030 | WB bracket step |
| +24002 / +24006 | WB preset / category |
| +24010 / +24016 / +24018 / +24048 | Sharpness / Contrast / Tone (gradation) / Saturation |
| +24053 | picture mode |
| +24054 | read as `movbu` by the Art Effect mapper (Art Effect id [I]) |
| +24058..69 | S ×12 |
| +24083 | profile number (COLOR/MONO index) |
| +24084..86 | mono settings (+24085 grain → params+5551, +24086 shading → params+5552) |
| +24140/+24141 | ME fields (LIVE_ND) |
| +24168 | orientation latch |

{{TABLE:capture}}

## 8. Image pipeline

Stage order for a still (key 11 COLOR shown):

```
job ctor 0x603537eb ─ flags (0x60521a54 hash, Art Effect 0x603eab39, strips 0x60353b15)
  └ work list 0x60357415 ─ key hash 0x6052200c → handler (default 0x6035749f / key-12 0x6035778b / GF 0x603574e3)
       └ per-flag passes: 0x80 Soft Focus (reduce 0x6035cee6 → upscale 0x6035cfe9 → blend 0x6035ca31),
         0x40 Star Light 0x6035d6ef, 0x400 Pin Hole, 0x100/0x200 Diorama, 0x80000 shading 0x6035b03a, grain (key 12)
REC_IMAGE runs entries (0x60354214) → request packer 0x60354ce4 (job+11364) → stage dispatch 0x603aaced
  └ dev stage list 0x603b1466: colour selector 0x603b0252 → builder 0x603b0068 (key 11) | art 0x603afb94 | general 0x603afd26
                               tone LUT 0x603b0a70 (selectors 0x603b039b / 0x603b04fa / gamma 0x603ae354, RGB 0x603ae7d3)
                               chroma 0x603b132a, sharpen gain 0x603ac0c1
  └ combiners (select 0x603b5200, config 0x603a013b): 11/12 mix, 31/32 grain, 33 mask, 136 additive
→ JPEG (0x603b6120 quant) → EXIF (tag table 0x604dadf0) → REC_FILE
```

| Struct | Offsets |
|---|---|
| Job (15488 B) | +16 flags (0x80 SF, 0x40 Star, 0x400 Pin Hole, 0x100/0x200 Diorama, 0x80000 shading); +20 type (0x1000 still, 0x3x LV/movie, 0x40 rec, 0x110/0x120 special); +36 params; +6592 buffer records 48 × 88 B; **+11308 key** (11 COLOR, 12 MONO, 0x0101_00yy art I, 0x0102.. II, 0x0103.. III, 0x01010065 Soft Focus, 2000 Flat, 2001 log); +11320; +11322/+11330 WB gains; +11341 class; +11364 request |
| Params (job+36) | +8..11 key; +16 type; +30 class input; +4466/+4474 WB; +5520/5521 WB idx; +5522 chSharp; +5523 chContrast; +5524 chTone; +5525 chSaturation; +5536/5537; +5538..5549 S ×12; +5551 grain → request+1828; +5552 shading → +1829 |
| Request (1884 B) | +8..11 key; +12 stage; +14 type; +20/+84 inputs; +148 third port (mask); +276 mask desc; +532 mask desc copy; +1512 tone raw; +1524 alt builder; +1795 sharpness; +1796 contrast; +1797 gradation (1 HK, −1 LK, 2 Auto); +1800 mono; +1803 toning index; +1816 S ×12; +1828 grain; +1829 shading; +1832 SF level; +1838 effect code |
| Builder output O | +4 flags; +76 chroma {enable, Cb, Cr}; +688 12 × 24 B (hue +18, sat +20, L +22); +2612 tone LUT |
| Context C | +60 flags (0x10000000 alt builder, 0x80000000 tone); +64 tone input |
| Buffer record (88 B) | +0 bus addr, +8 format, +10 stride px, +12 w, +14 h, +16/18 active, +20/22 x/y, +24/26 half sizes, +72 size. 0x1000 developed (fmt 0x0302, 2 B/px, Y in even bytes), 0x1060 reduce (0x0305, 4 B/px), 0x1061 upscale, 0x1083 star layer; mask fmt 0x080C |

CPU access to buffers only through the window mapper, lock, flush ([FIRMWARE_GUIDE.md](FIRMWARE_GUIDE.md) §7).

{{TABLE:pipeline}}

## 9. JPEG and EXIF

The EXIF **writer** itself is not located; what is known is the tag table (rows point at capture-record offsets) and the
capture-setup code that fills those fields. Quantisation is scaled at run time from Q50 tables.

{{TABLE:jpeg_exif}}

## 10. SD and file I/O

fileif API in section 4. From an ordinary CPU0 task each call is a synchronous RPC to FILECLBK (no timeout). Paths
`C:\…`. Caduceus reads/writes `EP7MOD\*.BIN` from HLS_EVENT on half-press ([FIRMWARE_GUIDE.md](FIRMWARE_GUIDE.md) §8).

{{TABLE:fileio}}

## 11. Movie

Picture mode reaches movies through the settings message and record +294; log/Flat via the hidden byte +925 →
effect ids 2001/2000. The colour route of the recording stream (0x6039a97b) is only partly traced.
Detail: [MOVIE_COLOUR.md](MOVIE_COLOUR.md), [VIDEO_LOG.md](VIDEO_LOG.md), [VIDEO_HIDDEN.md](VIDEO_HIDDEN.md),
[VIDEO_ROTATION.md](VIDEO_ROTATION.md).

{{TABLE:movie}}

## 12. Lens, AE and sequencer

{{TABLE:lens_ae}}

## 13. Updater and container

Container: 32-B header `OE`, model `14 20`, +12 size, +20 kind; payload; 32-B trailer (repeats header 0–27, +28
checksum; word sum over header + decoded payload + trailer = 0). Scramble = invert + 16-byte lane permutation.
FIRMUP_CLI picks `DCOLYMP\E142????BIN` with the largest hex suffix > 0; components written main last; no rollback.
Detail: [FIRMWARE_GUIDE.md](FIRMWARE_GUIDE.md) §1, [SD_UPDATE.md](SD_UPDATE.md), [SD_REJECT.md](SD_REJECT.md).

{{TABLE:updater}}

## 14. Our code space

Not in this atlas. Every Caduceus claim (section FF tails, dead EVF gamma tables 0x601de13c–0x601e3b3c, heap P layout,
.bss pads 0x622cbcc2 / 0x6203c8ba / 0x6203c8bb) and every hook site is registered in
[CODE_SPACE_MAP.md](CODE_SPACE_MAP.md). Symbol names of our builds: `generated/*/symbols.json`.

## 15. Address conflicts and resolutions

| # | Where | Docs said | Bytes / resolution |
|---|---|---|---|
| 1 | COLOR editor records | FIRMWARE_GUIDE §4, LOOK_EDITOR §1: records at 0x61185be8/…c20/…c58/…c90 (0x13a9 at 0x61185bb0), "+0 key" | **Off by 12.** Byte dump: key words at **0x61185bdc** (0x13b3), 0x61185c14, 0x61185c4c, 0x61185c84 (0x140c), 0x61185ba4 (0x13a9); the quoted addresses hold the +12 Up word 0x60e20e0a. Patches use them as +12 words (FILM_MENU_V2 F1–F4), so builds are right; only the base/offset labelling is wrong. Same for 0x61186400/38 (= +12 of keys 0x1413/0x1414 at 0x611863f4/0x6118642c) |
| 2 | Capture task | HALATION_RED §18: "REC_MAIN's entry 0x603e5d57, priority 0x36" | Descriptor table: 0x603e5d57 is **REC_IMAGE** (task 31, prio 54, stack 0x3700); REC_MAIN is task 32, entry 0x603df803. The priority argument (54 < SYS_WDT 55) stands |
| 3 | COLOR builder end | WORKLOG step 1: builder "ends `mov d0,(976,a0); retf` at 0x603b024b–f" | dis: builder returns `ret [d2,d3,a2,a3],96` at 0x603b0244; 0x603b0247–0x603b0251 is a separate leaf. REVIEW_fixed_hl is right; FINDINGS' "0x603b0068–0x603b0247" is end-exclusive |
| 4 | Arrow sids | BUTTONS §1, WORKLOG l.178: right/down = 51/53 | Corrected in BUTTONS §4d (camera, SEND_KEY table 0x60f3928c): **50 up, 51 down, 52 left, 53 right**. WORKLOG line is stale |
| 5 | Recording limit | FEATURE_GAPS 0x60319156/0x6031915b; V02_BUNDLES/WORKLOG 0x60319157/0x6031915c | Same edit: instruction vs immediate byte |
| 6 | HLS_EVENT creation | 0x6076fd56 (SD_BUNDLES_V2), 0x6076fd8e (REVIEW_SD_V2), 0x6076fd95 (SD_V2_CRASH) | dis: function start / `call 0x60051d66` / `movhu d0,(a2)` tid store. Consistent |
| 7 | Shading-mask generator | 0x6036cec0 (FIRMWARE_GUIDE) vs 0x60338d49 (GRAIN_PORT) | Both: 0x6036cec0 fills the descriptor (cache 0x6036b635), 0x603390a4 → 0x60338d49 writes the pixels |
| 8 | Getter 0x6005e96f | tools/port_em10iv_map.py, patches/em10iv_vivid | That is the **E-M10 IV** getter; E-P7 is 0x6005e971 (dis-checked). Several `tools/*.py` constants (OSTR 0x601a47b0, FLASH_WRITE 0x600c1ea1, …) are other bodies: check the body before reusing |
| 10 | LV job state table | LV_ART_PREVIEW §7: table at 0x604e3190, handlers labelled "event 0" | Table starts **0x604e315c** (13 states × 28 events, dispatch 0x6032967e); those handlers are **event 7** (param update). [RE_LIVEVIEW.md](RE_LIVEVIEW.md) |
| 11 | Watchdog handler | HALATION_RED §18: wdt_expiry_handler 0x60059c20 | Mid-instruction. All faults and WDT enter NMI handler **0x60059a9d**; the WDT case is the branch at **0x60059c63**. [RE_CAPTURE.md](RE_CAPTURE.md) |
| 12 | Extras overlay hook / Firmware text | EXTRAS_OVERLAY §2.2: +164 "empty in both window classes" (0x60f94820, 0x60fac3f0); PLUGINS §3: "0.32S" readable | 0x60cfe263 is the +164 word of ~400 vtables; those two are one class pair (ctors 0x60cff51e / 0x60d43e80). The only +164 call is 0x60d005ef in 0x60d00506 (v0.32 diag hooks it). "0.32" already clips, so a suffix isn't readable; diag shows "L/O". [PLUGINS.md §10](PLUGINS.md) |
| 9 | Doc-internal corrections already recorded | SsMenuLv matrix index (AP_CUSTOM b6 → b7, event-major); updater LED meaning (SD_REJECT); .data init delta (MIN_SHUTTER m2); SD loader v1 hook dead (REVIEW_v04) | Use the corrected forms (this atlas does) |

## 16. Known unknowns, ranked

Ranked by how much each would speed up likely next features (from [FEATURE_GAPS.md](FEATURE_GAPS.md),
[FUJI_GAPS.md](FUJI_GAPS.md), the CHANGELOG/WORKLOG backlog: split toning #38, per-slot gradation / Auto ISO /
exposure shift, XPan grid, film counter, LV preview of effects, crash triage).

| Rank | Unknown | Unblocks | What we have | Next step |
|---|---|---|---|---|
| 1 | **[Mostly answered → [RE_LIVEVIEW.md](RE_LIVEVIEW.md)]** **Live-view job lifecycle**: what rebuilds or re-parameterises the LV job (key fixed at build, 0x603118d6), when compact WB / S records refresh, how to push a look change to LV without a mode switch; per-profile transport into LV jobs | LV preview of every effect (bloom, grain, halation, split tone), look-switch lag, WB/movie colour | Constructor path 0x60321d36 → 0x603220e5 → 0x60324071; param update 0x60321f75; Rec View posts 0x6031c883 ([LV_ART_PREVIEW.md](LV_ART_PREVIEW.md), [LV_BUNDLES.md](LV_BUNDLES.md)) | Trace callers of 0x60321d3b/0x60321f75 from a settings-change listener in the emulator |
| 2 | **[Partly answered → [RE_DRAW_PLUGIN.md](RE_DRAW_PLUGIN.md): OSDControl API, gpiDrawOsdRectangle 0x60d129d0, GUI_TASK present 0x60d125af; open: live layer/palette, font call]** **Drawing primitives and widget geometry**: no known API to draw text, lines or bitmaps at x,y into an OSD layer; widget widths; which palette/layer is live; the screen stack is not emulated | Film counter, XPan/21:9 grid lines, new labels without clipping, any new on-screen element | Text setter 0x60d4c9df, label builders, grid lookup 0x60df72e8, AF frame geometry 0x60df798a, palettes 0x61110a74.. ([OSD.md](OSD.md), [ASPECT.md](ASPECT.md) §7) | Trace a stock overlay draw (grid or level gauge) to its blit call; one harmless camera probe for layer/palette |
| 3 | **[Mostly answered → [RE_AE.md](RE_AE.md): rebuilt every calc, APEX×256 fields, prop_get hook sites; open: shift/gradation consumers]** **AE update cadence and exposure-field meaning**: how often AE messages rebuild (keys 0x949a at 0x60426886/0x60427991, 0x30ea/0x30fa at 0x604269c1/0x60427a9c), pointer caches 0x6020d7a6 / 0x6020da40 / 0x6020d393, AE side of gradation 0x6042965b | Per-slot Auto ISO ceiling, exposure shift (film EI), gradation per slot | AE record builder 0x6042777c, slow-limit rule 0x603fc5d3 ([MIN_SHUTTER.md](MIN_SHUTTER.md), [FEATURE_GAPS.md](FEATURE_GAPS.md) §4–5) | Emulate 0x6042777c with a fixture and log which keys feed which fields; confirm caches have no fast path |
| 4 | **[Mostly answered → [RE_CAPTURE.md](RE_CAPTURE.md): task/mailbox chain, nothing persisted on crash, crash-log design pending RAM-retention probe]** **Capture-task timing and crash triage**: v0.31a crash ≈2 s after a bright-scene shot (cause not found), buffer-pool limits in bursts, Rec View interplay with CPU passes; no crash log readout | Every CPU-pass feature (grain, halation, future CPU split tone), burst safety | REC_IMAGE runs the work list synchronously; buffer pool 0x60350560 errors 0x9ec3/0x9ece; watchdog model ([HALATION_RED.md](HALATION_RED.md) §18–22, [GRAIN_PORT.md](GRAIN_PORT.md)) | Find the crash/exception logger and whether it persists anything to flash or card; map REC_VIEW (task 108) waits |
| 5 | **[Answered → [RE_LIVEVIEW.md](RE_LIVEVIEW.md) §3–5: gamma stage 0x603ae80d, hook G1 0x603ae830]** **Per-channel tone stage for stills**: which stage calls the RGB gamma setter 0x603ae7d3 with three curves on key 11, and whether a per-job swap leaves movie log (shared tables 0x604edc78..) untouched | Split toning / crossover (#38), luminance-dependent colour | Setter takes three pointers; stock passes three curves on one path ([FUJI_GAPS.md](FUJI_GAPS.md) §6, [SPLIT_TONE.md](SPLIT_TONE.md)) | Emulate the dev stage list on a key-11 still and record the three pointers |
| 6 | **JPEG/EXIF writer**: the EXIF/maker-note writer function, whether ORF uses the same tag table and cap+1448, where `Sf` is chosen per quality and whether `ulJpegTargetSize` drives rate control | Look settings code in EXIF, ORF tags, Software tag, finer/coarser JPEGs | Tag table 0x604dadf0, capture setup 0x603017f3, quant scaler 0x603b6120 ([JPEG_QUALITY.md](JPEG_QUALITY.md)) | xref the tag table's readers; run the JPEG setup in the emulator to read `Sf` |
| 7 | **Drive / sequencer model**: drive sid 3281 lies past the sid table; interval limit (sid 479) has no validator; Pro Capture / High Res gates | Interval timer limits, drive-based features, Live ND one-press | Sequencer gates 0x609352c9.., ME parts ([LIVE_ND.md](LIVE_ND.md), [UNLOCK_LEADS.md](UNLOCK_LEADS.md)) | Find 3281's storage via the SCP select record `{3281, 21, 0x61175b80}` readers |
| 8 | **HSL second axis**: the 16-knot per-sector curves (chroma or luminance) in the COLOR record not pinned | Hue × luma looks (closer film emulation without a 3D LUT) | [FUJI_GAPS.md](FUJI_GAPS.md) §1 | One A/B camera test of a knot edit |
| 9 | **Where WB fine-tune and NR reach pixels**; MakerNote NF vs menu mismatch | Per-look NR/WB verification | v0.25 notes ([CODE_SPACE_MAP.md](CODE_SPACE_MAP.md) v0.25 row, WORKLOG) | Wall test (planned) |
| 10 | **Pre-main boot / sub-CPU**: the OK-at-power-on updater button read is not in main; sub-CPU (0x10e) is strings only | Recovery confidence, not features | [SD_UPDATE.md](SD_UPDATE.md) | Low priority |
