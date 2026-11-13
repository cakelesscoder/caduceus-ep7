# E-P7 1.1 stock firmware atlas

One map of how the stock PEN E-P7 1.1 (build 1100) main program works, so feature work starts from known
addresses. It consolidates `docs/*.md`, `patches/*/`, `tools/*.py`, `generated/*/symbols.json` and `WORKLOG.md` as of
2026-11-12. It does not replace the feature docs: each row links the doc with the detail.

- **Scope.** Stock code and data only. Our own code-space claims, hook sites and FF guards are in
  [CODE_SPACE_MAP.md](CODE_SPACE_MAP.md); never allocate from this file.
- **Addresses** are E-P7 1.1 main CPU addresses (decoded offset + 0x60020020) unless marked RAM/OSD. **None carry to
  another body** ([FIRMWARE_GUIDE.md](FIRMWARE_GUIDE.md) §12).
- **Tags** as in FIRMWARE_GUIDE: **V** code/bytes/emulator, **C** camera-proven (a stronger V), **I** inference.
- **Machine-readable:** [atlas.json](atlas.json) (927 symbols, incl. 137 static tasks).
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

| Address | Name | Kind | Tag | Signature / layout | Notes | Source |
|---|---|---|---|---|---|---|
| `0x60020020` | main_base | data | V |  | Decoded main offset 0 = CPU 0x60020020 = container 0x406a0020. 0x6.. cached, 0xa.. (+0x40000000) uncached alias | docs/FIRMWARE_GUIDE.md §2 |
| `0x60020074` | bss_clear_call | func | V |  | Calls 0x6002046d(0x621caf00, 0xa2796888): zero .bss at boot | docs/SD_V2_CRASH.md |
| `0x600201fe` | data_copy | func | V |  | .data init: flash 0x60230800-0x6025eb50 -> RAM 0x61f98540 (RAM = flash + 0x1d67d40) | docs/ASPECT.md |
| `0x6002046d` | hw_fill_zero | func | I | (start, end) | Boot fill-to-zero (hardware-assisted [I]); also clears 0x62038100-0x6203c934 | docs/SD_V2_CRASH.md, docs/VIDEO_ROTATION.md |
| `0x60027068` | section_desc_table | table | V | 9 x {u32 start, u32 logical src, u32 dst} | Section descriptors ids 1..9 | docs/FIRMWARE_GUIDE.md §2, docs/HSL_PORT.md |
| `0x60027068` | section_table | table | V | 9 x {start, flash source, destination} | Entry 5 = {0x6075a800, 0x40dda800, 0x6075a800}: sec 5 is copied 1:1 (flash = image addr - 0x60020020 + 0x406a0020) | docs/PLUGINS.md §10 |
| `0x60044afb` | section_load_fsm | func | V |  | Boot load state machine; order 1,7,2,3,4,5,6,8,9 | docs/SD_UPDATE.md, docs/HSL_PORT.md |
| `0x60045786` | section_end_get | func | V | d0 = id (1..9) -> d0 end; else 0 | Jump table 0x60046780 of `mov imm32,d0` stubs | docs/FIRMWARE_GUIDE.md §2 |
| `0x60045786` | section_end | func | V | d0 id 1..9 -> d0 end (jump table 0x60046780 of mov imm32 stubs) | Sec 5 end 0x60b9e000 (stub 0x600457b4); sec 8 empty (0x613bd000) | docs/PLUGINS.md §10 |
| `0x600457e7` | section_load | func | V | id | Copies end-start bytes via 0x6005bc79 -> 0x600c4e80; sets bit (id-1) in 0xa272e420. 9 callers, all in 0x60044f2d-0x600451d0 | docs/FIRMWARE_GUIDE.md §2, docs/REVIEW_v04.md |
| `0x6004586c` | section_init_run | func | V | n | Runs section n initializer list via 0x6004591f -> 0x6018e19e | docs/SD_UPDATE.md |
| `0x600458af` | section_wait | func | V | n | wait(n): narrows bus monitor to [start(sec n+1), end(sec9)]; wait(9) disables it (0x6005915f) | docs/BOOTLOOP_T3.md |
| `0x6004595c` | busmon_setup | func | V |  | Arms bus monitor 0x99700000 channel 8 over [start sec1, end sec9] (from 0x60044b30). Not write-protect | docs/BOOTLOOP_T3.md |
| `0x60046780` | section_end_jtab | table | V | 9 x u32 stub ptr | Targets 0x6004579c.. (stubs `mov END,d0`) | docs/HSL_PORT.md |
| `0x60052158` | BOOT_CPU0 | func | V | task 1 entry | Linear startup: -> 0x60044afb -> 0x60045223. No updater button check found | docs/SD_UPDATE.md |
| `0x60058c66` | busmon_cfg | func | V |  | Only region-check hardware programmed (0x99700000) | docs/REVIEW_fixed_hl.md |
| `0x60059a9d` | nmi_handler | func | V |  | Prints `[SYS WANA] NMI_INT Hassei!` and spins (`bra .` at 0x60059cec). Vectors 0x60055250/c0/330 | docs/BOOTLOOP_T3.md |
| `0x600670bc` | to_cached | func | V | a0/d0 addr | Address alias conversion (pair with 0x60067102) | docs/SD_V2_CRASH.md |
| `0x60067102` | to_uncached | func | V | addr -> addr\|0x40000000 | e.g. 0x6057b200 -> 0xa057b200; sections copied via uncached alias | docs/SD_UPDATE.md |
| `0x6018e19e` | init_list_dispatch | func | V |  | Initializer lists: `mov count,d2; mov ptr,a2` pairs. Sec-2 list 0x6055e580 (48 B), sec-7 0x61378c54 (20 B) | docs/HSL_PORT.md, docs/SD_UPDATE.md |
| `0x6018e1b3` | sec4_ctor_list_runner | code | V | d2 = byte count, a2 = list (0x60747f1c), calls each word | Section-4 ctor list has count 0, so 0x60747f1c is only a label; the sec-4 FF tail 0x60747f20..0x60748000 has no other live ref | docs/SPLIT_TONE_G1.md §1.3 |
| `0x60190df7` | USRSTART2 | func | V | task 43 entry | Boot task: wait(2) 0x60190e18 (runs sec-2 initializers), wait(3)/(4) 0x60191347/5d, wait(5) 0x60191aab, wait(6) 0x60191afb; 0x60191b02 -> 0x60767d20 (HIGHLEVEL framework) | docs/BOOTLOOP_T3.md, docs/SD_BUNDLES_V2.md |
| `0x60191b74` | USRSTART5 | func | V | task 42 entry | Straight-line startup; starts FIRMUP_SRV at 0x601922f0 | docs/SD_UPDATE.md |
| `0x60192961` | boot_tail_resets | func | V |  | Per-boot resets of volatile settings (uses 0x602b972b, gate 0x62257b04). Site 0x601929a4 (trace call) used by the old aspect clamp | docs/ASPECT.md, docs/FIRMWARE_GUIDE.md §3 |
| `0x621caf00` | bss_range | data | V | 0x621caf00-0x62796888 | Stock .bss, zeroed at boot. Stock writable statics are all >= 0x61b2xxxx | docs/FIRMWARE_GUIDE.md §2 |
| `0xa272e420` | sections_loaded_mask | data | V | u32 bits 0..8 | Bit n-1 set after section n copied; loader gates check &0x1ff | docs/FIRMWARE_GUIDE.md §2, §8 |

## 2. RTOS: tasks, queues, memory

Kernel with μITRON-style error codes (E_CTX −25) [I]. Lower priority number = higher priority (REC_IMAGE 54 pre-empts SYS_WDT 55). Static tasks are
described by a 28-B record per id; dynamic tasks (HLS_EVENT) are created at run time. IDs of tasks and mailboxes are
read from constant u16 tables (`movhu (0x60040d20),d0` = FILECLBK's mailbox).

**Rules learnt** ([SD_V2_CRASH.md](SD_V2_CRASH.md), [HALATION_RED.md](HALATION_RED.md) §18–22): file calls from any
CPU0 task are a blocking RPC to FILECLBK; never call them from a task FILECLBK may wait on (FILEFGND). The hardware
watchdog is kicked only by SYS_WDT; a CPU-bound pass in a higher-priority task starves it (Caduceus raised the limit
10 → 30 s). Interrupt-masked locks are per CPU.

| Address | Name | Kind | Tag | Signature / layout | Notes | Source |
|---|---|---|---|---|---|---|
| `0x00008050` | cpu_id | data | V | u? | (0x8050) holds current CPU id; non-zero = other core | docs/FIRMWARE_GUIDE.md §2, docs/SD_BUNDLES.md |
| `0x00008070` | CHCTR | data | V | u16: ICEN 0x1, DCEN 0x2, ICBUSY 0x4, DCBUSY 0x8, ICINV 0x10, DCINV 0x20 | Cache control. Stock only drives the D-cache bits (0x60066fc0, sec 9 0x6136a7fd..); no I-cache invalidate anywhere. I-cache bit names [I] | docs/RE_DRAW_PLUGIN.md §3.2 |
| `0x600219ab` | wdt_hw_set | func | V | d0 seconds (0..63) | Writes 6-bit field of 0x98e0008c, waits 0x98e000a4 | docs/HALATION_RED.md §22 |
| `0x600219e3` | sysreg_bit10_get | func | V | -> d0 = (0x98e00000) bit 10 | Read by dbg init 0x600617c1; set only via debug shell 0x613c4d91 [meaning I] | docs/RE_CAPTURE.md §4 |
| `0x6002245c` | dbgring_mode_set | func | V | d0 0/1/2 | Sets 0xa2728c98; boot passes prop 0xf981 (0x6005d661) | docs/RE_CAPTURE.md §4 |
| `0x600224ff` | dbg_printf | func | V | a0 fmt | Console print -> 0x6002247c -> DBG_OUT queue (0x60040fdc) + tee into the console ring | docs/RE_CAPTURE.md §4 |
| `0x60022700` | alloc_class | func | V | d0 size | Allocator used by job ctor (class 2 <= 16384) | docs/V02_BUNDLES.md |
| `0x60022782` | malloc | func | V | d0 size -> a0 (uncached) or 0; `[],4` | Pools <=128, <=2048, <=16384; >16 KB logs error | docs/FIRMWARE_GUIDE.md §2 |
| `0x600227b4` | free | func | V | a0; `[],4` | Range checks at 0x600227c9/d1 give pool bounds | docs/SD_V2_CRASH.md |
| `0x60023863` | ictlog_add | func | V | d0 item, d1 len, a0 data | Needs state 8 (0x6233b790). dbg_put uses item 119, 60 B (0x60061c4f) | docs/RE_CAPTURE.md §4 |
| `0x600239b4` | ictlog_flash_save | func | V |  | Checksum + 0x6005bc79 write to 0x47b00000. Only via 0x602f8a63 from OlyHfwPower::startShutDown 0x607a9c2e | docs/RE_CAPTURE.md §4 |
| `0x60030000` | vec_base_cpu0 | table | V | +0x08 NMI -> 0x60055250, +0x20 IRQ entry -> 0x600386f8 | CPU1 base 0x60050000 (NMI 0x600552c0), CPU2 0x600d0000 (NMI 0x60055330) | docs/RE_CAPTURE.md §4 |
| `0x6003071f` | task_start | func | V | d0 tid | Kernel start (sta_tsk-like); ~190 callers incl. wrapper 0x60051873, cross-core 0x60053f11, shell `tsk sta` 0x60057d08 | docs/SD_UPDATE.md |
| `0x600313ef` | dly_tsk | func | V | d0 ticks; `call ..,[d2,a2,a3],16` | Ticks ~ms in stock use (1-3); E_CTX -25 outside a task | docs/HALATION_RED.md §18 |
| `0x600317ac` | get_tid | func | V | a0 = &u16 out -> d0 0 ok / -25 not a task | Per-CPU tid | docs/SD_BUNDLES_V2.md, docs/REVIEW_SD_V2.md |
| `0x6003483e` | ref_mbx_count | func | I | d0 mbx, a0 &info -> count at info+4 | Used by REC_MAIN drain 0x603dfb10 | docs/RE_CAPTURE.md §1 |
| `0x600386f8` | irq_entry | func | V | movm [a2,a3,other] | Kernel interrupt entry; saves MDR/LIR/LAR. Vector stubs also write PSW/PC/SP to the NMI frame on every IRQ | docs/RE_CAPTURE.md §4 |
| `0x600389d0` | task_desc_table | table | V | 28 B {u32 id, u32 attr, u32 0, u32 entry, u32 prio, u32 stack, u32 0} x id | Static tasks 1..137 (id at +0 == index). Lower prio number = higher priority. Full list: ATLAS §2.1 | this atlas (bytes), docs/SD_UPDATE.md |
| `0x6003d344` | cpu2_task_desc_table | table | V | 28 x 28 B {u32 id, u32 attr, u32 0, u32 entry, u32 prio, u32 stack, u32 0} | Ids 0x2001..0x201c; names in 0x61400b18 (n = id & 0xff) [I pairing] | docs/RE_LIVEVIEW.md §1 |
| `0x600408d8` | task_id_table | table | V | u16[n] = n | Constant task-id words; FILECLBK id at 0x600408f8, FIRMUP_CLI at 0x60040988 | docs/SD_UPDATE.md, docs/SD_V2_CRASH.md |
| `0x60040cdc` | mailbox_id_table | table | V | u16[n] = n | Constant mailbox-id words: appevent 0x60040ce8 (6), FILECLBK 0x60040d20 (0x22), FIRMUP reply 0x60040d22, SYS_WDT 0x60040d60 (0x42), FIRMUP_SRV 0x60040dca (0x77), display 0x60040df4 (0x8c) | this atlas (bytes), docs/SD_BUNDLES.md, docs/HALATION_RED.md §21 |
| `0x60041076` | mvr_main_flag_id | data | V | u16 flag id | MVR_MAIN event flag; bit 0x1 = LV param event 7 | docs/RE_LIVEVIEW.md §1-2 |
| `0x6004109e` | mvr_mbx_id_words | data | V | u16[] = 0x2001, 0x2002, 0x2003, 0x2004 ..; 0x600410be = 0x2011 | MVR mailbox ids (CPU2 id space) | docs/RE_LIVEVIEW.md §1 |
| `0x600410be` | recview_mbx_id | data | V | u16 (=0x2011) | Rec View mailbox id word (different table); read by 0x6031d189 gate | docs/ISSUES_19_20.md |
| `0x600510e8` | set_flg | func | V | d0 flag id, d1 bits | Event flag set; used by 0x6031daaa/0x6031dafa/0x6031db4b, TAKE_MOV post 0x6020c15c path | docs/RE_LIVEVIEW.md §1 |
| `0x60051143` | wai_flg | func | V | "OlyEvWt" | 72 callers | docs/RE_CAPTURE.md §1 |
| `0x600513e6` | queue_recv | func | V | d1 timeout (-1 = forever) | Blocking receive | docs/SD_V2_CRASH.md |
| `0x600514b6` | queue_send | func | V | d1 timeout (-1 = forever) | Blocks when the queue is full | docs/REVIEW_SD_V2.md |
| `0x6005168d` | wai_sem | func | V | "OlySmWt" |  | docs/RE_CAPTURE.md §1 |
| `0x60051762` | sig_sem | func | V | "OlySmSi" |  | docs/RE_CAPTURE.md §1 |
| `0x60051873` | task_start_wrap | func | V | d0 tid | Start wrapper | docs/SD_UPDATE.md |
| `0x60051d66` | task_create | func | V | a0 name, a1 entry, d0/d1, (4,sp) prio, (8,sp) stack -> d0 tid | Dynamic task create (HLS_EVENT) | docs/SD_BUNDLES_V2.md |
| `0x60054b33` | sync_rpc | func | V | d0 mailbox id, d1 arg, a0 msg; `call ..,[d2,d3,a2,a3],72` | Temp reply mailbox, post, wait forever, delete. Used by fileif, SYS_WDT requests (d1 0 off / 1 on+kick / 2 timeout) | docs/SD_BUNDLES.md, docs/HALATION_RED.md §21 |
| `0x60054d9f` | psw_mask | func | V |  | Interrupt mask via PSW (level 0), used by lock | docs/GRAIN_PORT.md |
| `0x60055250` | nmi_stub_cpu0 | func | V | saves regs to frame, calls 0x60059a9d, rti | CPU1 0x600552c0, CPU2 0x60055330 | docs/RE_CAPTURE.md §4 |
| `0x60056138` | addec_irq_handler | func | V |  | ADDEC (bus/address decode) error: prints ADDR/RDATA/WDATA/STATUS from 0x9a000000+0x100*cpu, clears, returns. Registered by 0x600560a9 via 0x6006aa25 | docs/RE_CAPTURE.md §4 |
| `0x6005633f` | alarm_start | func | I | a0 callback, a1 delay, d0 mode | Deferred callback (cyclic/alarm handler [I]); ~30 callers | docs/RE_LIVEVIEW.md §1 |
| `0x60057440` | wdt_off_on_example | func | V |  | Stock pattern: WDT off, long call 0x60022e96, on. Others 0x600f3141/3161, 0x600f35eb, 0x60105728, 0x60c4972b | docs/HALATION_RED.md §21 |
| `0x60059aab` | nmi_hook_site | code | V | 6 B fc dc ec 74 07 60 (mov 0x600774ec,a0) | After wdt_hw_set(1) at 0x60059aa4 (reset ~1 s later). No branch target in span. Crash-log hook C1 candidate | docs/RE_CAPTURE.md §4.1 |
| `0x60059c63` | nmi_wdt_branch | code | V | btst 2,(0x8900) | WATCHDOG_TIMEROVER case inside nmi_handler 0x60059a9d (replaces mis-addressed wdt_expiry_handler 0x60059c20) | docs/RE_CAPTURE.md §4 |
| `0x60059fcd` | ssc_try | func | V | d0 bit mask, d1 register -> d0 1 got | bset d0,(a0): Z set = was free | docs/GRAIN_HANG.md |
| `0x60059fdd` | ssc_lock | func | V | d0 id (group = bits 3..5, bit = bits 0..2), d1 0 try / 0xff spin / ms -> d0 | Hardware semaphore bset on 0x8fe00000 + 8*group; spin logs every 0x800000 tries. Used by the phys heap with id 0xa09000a | docs/GRAIN_HANG.md |
| `0x6005a126` | ssc_unlock | func | V | d0 id | bclr on the group register | docs/GRAIN_HANG.md |
| `0x6005b232` | wdt_on | func | V |  | `mov 10,d0` at 0x6005b23a (Caduceus: 30). Boot via 0x60044be4 | docs/HALATION_RED.md §22 |
| `0x6005b287` | SYS_WDT | func | V | task 25 entry, prio 55 | Waits <=3 s on mailbox 0x60040d60 then kicks HW (0x6005b253 -> 0x470008ae). Only kicker | docs/HALATION_RED.md §18, §22 |
| `0x6005bcb5` | wdt_flashop | func | V |  | Off, run flash op, `mov 10,d0` at 0x6005bcff (Caduceus: 30) | docs/HALATION_RED.md §22 |
| `0x6006109f` | power_off_seq | func | V | d0 kind, d1 ms | Shutdown tail: dbgring save, ... ends in boot-ROM 0x47000b0a. Callers 0x601e729e, 0x602f7729, 0x613cae2a | docs/RE_CAPTURE.md §4 |
| `0x60061808` | dbg_put | func | V | d0 code, d1 kind, ...; 1900 callers | Central error logger. Kind 1: first-error record 0xa2715d28 + ICTLOG item 119; reboot hooks 0x60054a1d/20/23 are empty retf | docs/RE_CAPTURE.md §4 |
| `0x60066d2d` | bootmode_byte_take | func | V | -> d0 top byte of 0x98e00000, then cleared | Persistent system register (RTC domain I); setter 0x60066d14 (from 0x60192936). Not for our use | docs/RE_CAPTURE.md §4 |
| `0x60066fc0` | cache_flush | func | V |  | Busy bit needs hardware (emulator counts calls) | docs/FIRMWARE_GUIDE.md §7 |
| `0x60067146` | window_map | func | V | bus addr -> CPU addr | <0xb0000000 direct; 0xb..0xdfffffff via per-CPU window (regs 0x98100058 + CPU stride 0x400); refuses 0xc0000000-0xc3ffffff, >=0xe0000000 | docs/FIRMWARE_GUIDE.md §7, docs/GRAIN_PORT.md |
| `0x600672ee` | window_mode_get | func | V |  | Mode array 0xa2716034 | docs/GRAIN_PORT.md |
| `0x600672fe` | window_mode_set | func | V |  |  | docs/GRAIN_PORT.md |
| `0x6006a922` | cpu_lock | func | V |  | Mask this CPU interrupts (other CPUs run) | docs/FIRMWARE_GUIDE.md §7 |
| `0x6006a96b` | cpu_unlock | func | V |  | Restore window mode first | docs/FIRMWARE_GUIDE.md §7 |
| `0x600fa223` | dbgring_save_card | func | V |  | Writes ring to C:\dbgterm\<time>.txt; only caller power-off 0x6006109f | docs/RE_CAPTURE.md §4 |
| `0x602c7f5a` | appevent_get | func | V | frame [d2,d3,a2,a3],88 | Blocking receive from appevent queue (0x60040ce8) via 0x602c9b6a/0x600513e6 (-1); sole caller 0x60770224 (vtable slot 0x60a69820) | docs/SD_BUNDLES_V2.md |
| `0x602c818c` | trig_tracker | func | C | a0 event ptr; `call ..,[d2,d3,a2,a3],36` | api_event_check_release_notice; called at 0x602c805f (Caduceus loader hook) for every 0x02000100 half-press | docs/SD_BUNDLES_V2.md, docs/FIRMWARE_GUIDE.md §8 |
| `0x602fcb69` | key_filter | func | V |  | Stock key filter after tracker (0x602c8066-0x602c807f) | docs/SD_BUNDLES_V2.md |
| `0x60618828` | fs_registered_tid | func | V | d0 tid -> 0/1 | FS library registered-task check | docs/SD_V2_CRASH.md |
| `0x6061a71e` | fs_appevent_qid | data | V |  | FS library holds appevent queue id (+28); posts via 0x6061aace/0x6061aaeb -> 0x6061aa93 -> 0x600514b6(-1) | docs/REVIEW_SD_V2.md |
| `0x6076fbed` | event_mgr_get | func | V | -> a0 0x622cbc14 | `OlyHfwEventManager` singleton | docs/SD_V2_CRASH.md |
| `0x6076fd56` | hls_event_create | func | V | a0 = mgr | If mgr+172 < 0: create HLS_EVENT (0x60051d66 at 0x6076fd8e, prio 54, stack 16360, entry 0x6076fdb6), store tid at 0x6076fd95, start | docs/SD_BUNDLES_V2.md (dis-checked here) |
| `0x6076fdb6` | HLS_EVENT | func | V | dynamic task entry | High-level event loop; calls 0x60770224 -> appevent get | docs/SD_BUNDLES_V2.md |
| `0x60cc0e4a` | ictlog_boot_load | func | V |  | From USRSTART5 0x60191bd5: flash 0x47b00000 (1 MB) -> RAM 0x62de0000; header "log" + checksum, else reinit 0x60023c61 | docs/RE_CAPTURE.md §4 |
| `0x60dd5067` | GUI_TASK | func | V | dynamic task entry | Created at 0x60cfcee5 via 0x607a791e (name "GUI_TASK", stack 16384) -> WinMain 0x60cfd311 message loop. Runs the GE paint and present | docs/RE_DRAW_PLUGIN.md §2.4 |
| `0x6136a854` | dcache_range_op | func | V | d0 addr, d1 len, a0 mode | Section 9 ranged D-cache op; >8 KB -> whole-cache 0x6136a7fd. Wrappers 0x6136a8e9 (mode 0), 0x6136a8f3 (mode 1) | docs/RE_DRAW_PLUGIN.md §3.2 |
| `0x613e63e3` | mod_err_log | func | V | (level, code, line, ...) | REC/module error wrapper -> dbg_put; codes 0x1e0xxxxx in REC code | docs/RE_CAPTURE.md §1 |
| `0x613ff240` | task_name_table | table | V | 26 B {char name[24], u16 id} | 143 names (0x613ff240-0x614000c6); FIRMUP_CLI record 0x613ffb30. ids 138-143 have no static descriptor | this atlas (bytes), docs/SD_UPDATE.md |
| `0x6140033a` | cpu1_task_name_table | table | V | 26 B {char name[24], u16 n} | BOOT_CPU1 1 .. S_SHELL_CPU1 0x29 (wifi, AVM, C3D, FCS_IMG_2NDCPU_MAIN) | docs/RE_LIVEVIEW.md §1 |
| `0x61400b18` | cpu2_task_name_table | table | V | 26 B {char name[24], u16 n} | BOOT_CPU2 1, MVR_MAIN 2, MVR_MOVIE 3, MVR_IMG1 5, MVR_CALC 6, MVR_IMG2 7, MVR_ENC 8, MVR_RECVIEW 0xc, REC_MAIN_CPU2 0x12, REC_VIEW_CPU2 0x14, MVR_EXEC 0x17 ... 0x1c | docs/RE_LIVEVIEW.md §1 |
| `0x61f9f1c8` | trig_state | data | V | u8 (lo nibble cur, hi prev) | TRIG1 = bit 1 | docs/SD_V2_CRASH.md |
| `0x6203ba08` | wdt_enabled | data | V | u? | SYS_WDT enabled flag | docs/HALATION_RED.md §21 |
| `0x622cbc14` | OlyHfwEventManager | struct | V | +172 u16 HLS tid, +174 u16 pad (Caduceus P handle), +176 u32 | Ctor 0x6076fa6a sets +172 = -1 | docs/SD_V2_CRASH.md |
| `0x622cbcc0` | hls_tid | data | V | u16 | HLS_EVENT tid (mgr+172) | docs/SD_BUNDLES_V2.md |
| `0x62ae8000` | nmi_frame | data | V | 3 x 0x40 B per CPU: +0 tid, +4 SP, +8 PSW, +0xc PC, +0x10 busmon, +0x20..+0x3c d0..a3 | Outside .bss; not cleared at boot [V scan]; survival through WDT reset unknown | docs/RE_CAPTURE.md §4 |
| `0x62ae8100` | crashlog_area_cand | data | I | ~2.5 KB in 0x62ae80c0..0x62de0000 | Only static users: ICTLOG debug init/t_init fill (0x613ff19e/0x613ff1c9). Proposed crash record R | docs/RE_CAPTURE.md §4.1 |
| `0x62de0000` | ictlog_mirror | data | V | 1 MB: +0 checksum, +4 u16 1, +0x400 "log", items from +0x440 | 120 item descriptors at 0x61fb035c (12 B) | docs/RE_CAPTURE.md §4 |
| `0x8fe00000` | ssc_regs | mmio | V | 8 groups x 8 B | Cross-CPU hardware semaphores (ssc_lock / ssc_unlock) | docs/GRAIN_HANG.md |
| `0xa1dd8d40` | heap_class2 | data | V | 0xa1dd8d40-0xa1e85800 | <=16384 B pool, blocks 0x4040 apart | docs/FIRMWARE_GUIDE.md §2, docs/LOOK_PICKER.md |
| `0xa1f8d800` | heap_class1 | data | V | 0xa1f8d800-0xa1f98540 | <=2048 B pool, 44 KB, uncached. Caduceus P = 0xa1f8d7ff + h | docs/FIRMWARE_GUIDE.md §2 |
| `0xa2682c34` | dbg_put_state | data | V | u32: off/put/sd/serial/sd-serial/reboot | Boot sets 1 (put) at 0x60061797 | docs/RE_CAPTURE.md §4 |
| `0xa2715d28` | dbg_first_error | data | V | 64 B record | Ver (prop 0xc082 or 0x1100), RTC time, code, args. .bss, lost on reset | docs/RE_CAPTURE.md §4 |
| `0xa2716034` | window_mode_array | data | V | per CPU | Selector bits 8-15 | docs/GRAIN_PORT.md |
| `0xa2726c90` | dbgring_buf | data | V | 8 KB; head 0xa2728c90, tail 0xa2728c94, mode 0xa2728c98 | Console tail ring (.bss) | docs/RE_CAPTURE.md §4 |

### 2.1 Static task list (descriptor table 0x600389d0, names 0x613ff240) [V bytes]

Record: `{u32 id, u32 attr, u32 0, u32 entry, u32 prio, u32 stack, u32 0}`; descriptor id == index for 1..137; attr is 0 except BOOT_CPU0 (2) [meaning unknown].
Ids 138–143 (DBG_OUT, CPUCONN_CPU0, CPUCALL_CPU0, S_SHELL, U_SHELL, PWR_STANDBY) have names but no matching static
record (other core or created elsewhere [I]). Roles from names are [I] unless a doc covers them.

| Id | Task | Entry | Prio | Stack | Id | Task | Entry | Prio | Stack |
|---:|---|---|---:|---:|---:|---|---|---:|---:|
| 1 | BOOT_CPU0 | `0x60052158` | 1 | 0x800 | 73 | MDET_CALC_FLAME_VECTOR | `0x605be54b` | 55 | 0x800 |
| 2 | DCFPROC_SUB | `0x6061d46c` | 66 | 0x600 | 74 | AVM_FILE_IF | `0x603d55b7` | 55 | 0x800 |
| 3 | WIFI_REMOCON_THROUGH | `0x60bd7f21` | 66 | 0x400 | 75 | HDMITOP_CEC | `0x6017eff5` | 55 | 0x400 |
| 4 | TPC_CAMC | `0x60c405af` | 55 | 0x800 | 76 | AUTOMATIC_DIMMER | `0x60041a63` | 55 | 0x800 |
| 5 | ADJ | `0x60bde94e` | 55 | 0x1000 | 77 | REC_PRE_I1 | `0x603ef9bb` | 55 | 0x1000 |
| 6 | ADJSLF | `0x60c39b7b` | 55 | 0xd00 | 78 | MOVP_MAIN | `0x60c8a30f` | 55 | 0x1000 |
| 7 | AUD_WATCH_DOG | `0x60767a54` | 55 | 0x400 | 79 | MOVP_VIDEO | `0x60c92c69` | 45 | 0x1000 |
| 8 | BAS_MAIN | `0x60ba7017` | 55 | 0x800 | 80 | MOVP_AUDIO | `0x60c896f1` | 55 | 0x1000 |
| 9 | BAS_RCU_SRV | `0x60ba9a04` | 55 | 0x800 | 81 | MOVE_MAIN | `0x60cb4eac` | 55 | 0x1000 |
| 10 | BCHK_BATT | `0x60061387` | 55 | 0x400 | 82 | MOVE_VIDEO | `0x60cbc0b1` | 55 | 0x1000 |
| 11 | BCHK_MAIN | `0x6006123b` | 55 | 0x500 | 83 | MOVE_AUDIO | `0x60cb3498` | 55 | 0x1000 |
| 12 | CAM_MAIN | `0x6011f7de` | 55 | 0x40 | 84 | ALBM_MAIN | `0x606551c9` | 55 | 0x400 |
| 13 | DPS_MAIN | `0x60c3f2e7` | 55 | 0x400 | 85 | PER_SLOPE | `0x60070002` | 53 | 0x600 |
| 14 | FACE_FD | `0x603c2184` | 55 | 0xc00 | 86 | SPC_MAIN | `0x60c56fb4` | 53 | 0x400 |
| 15 | FACE_MAIN | `0x603ba18a` | 55 | 0xb00 | 87 | REC_PRE_V1 | `0x603ef94a` | 46 | 0x1000 |
| 16 | FILECLBK | `0x6062fc44` | 55 | 0x1000 | 88 | FIRMUP_CLI | `0x60c95bab` | 45 | 0x800 |
| 17 | FILEFGND | `0x60634a81` | 55 | 0x800 | 89 | AUD_COPY_DATA | `0x6075b405` | 45 | 0x800 |
| 18 | FIRMUP_SRV | `0x60c96030` | 55 | 0x800 | 90 | AUD_MAIN | `0x6075e674` | 45 | 0x1000 |
| 19 | HPROC_PROC | `0x60069b71` | 55 | 0x800 | 91 | TOUCHPANEL | `0x6018bcd9` | 44 | 0x800 |
| 20 | IMG_PRECON | `0x603de62a` | 55 | 0xc40 | 92 | UI_IN | `0x601160a4` | 44 | 0x800 |
| 21 | LENS_FIRM_UP | `0x60557840` | 55 | 0x400 | 93 | PER_PCONT | `0x6006be6b` | 36 | 0x800 |
| 22 | LENS_FLASH | `0x600f29c6` | 55 | 0x400 | 94 | USR_FAST_APP | `0x6018e93b` | 36 | 0x1000 |
| 23 | PER_CCD_TEMP_MAIN | `0x60067553` | 55 | 0x400 | 95 | BC_MAIN | `0x6010b132` | 25 | 0x600 |
| 24 | PER_IN | `0x6006a8bd` | 55 | 0x400 | 96 | EXP_MOVIE | `0x603f332a` | 25 | 0x1000 |
| 25 | SYS_WDT | `0x6005b287` | 55 | 0x400 | 97 | FCS_MOVIE | `0x60692446` | 25 | 0x1200 |
| 26 | PLAY_IMAGE | `0x60c6acde` | 53 | 0x1000 | 98 | LENS_ASKDATA | `0x601eecd1` | 25 | 0x700 |
| 27 | PLAY_LOAD | `0x60c70454` | 53 | 0x1000 | 99 | LENS_COMMAND | `0x600e825f` | 25 | 0x400 |
| 28 | PLAY_MAIN | `0x60c60a11` | 53 | 0x1000 | 100 | LENS_MAIN | `0x601ecea3` | 25 | 0x700 |
| 29 | PLAY_SOUND | `0x60c776ac` | 53 | 0x1000 | 101 | PC_EVENT | `0x60c57117` | 25 | 0x318 |
| 30 | REC_FILE | `0x603e4236` | 54 | 0x1240 | 102 | PC_HOSTCOM | `0x60c57293` | 25 | 0x718 |
| 31 | REC_IMAGE | `0x603e5d57` | 54 | 0x3700 | 103 | PC_PCMRECLINK | `0x60c591ba` | 25 | 0x518 |
| 32 | REC_MAIN | `0x603df803` | 54 | 0x1000 | 104 | PC_PTP | `0x60c58592` | 25 | 0x318 |
| 33 | REC_PREPRO | `0x603ef892` | 55 | 0x1290 | 105 | PC_UAM | `0x60c59771` | 25 | 0x718 |
| 34 | REC_SOUND | `0x603f2cb7` | 55 | 0x1000 | 106 | PC_USB | `0x60c59936` | 25 | 0x518 |
| 35 | SAICAS | `0x60c3ebb7` | 55 | 0x400 | 107 | PC_USBSRV | `0x60c583df` | 25 | 0x318 |
| 36 | SC_TTIMER | `0x600fa9ad` | 55 | 0x600 | 108 | REC_VIEW | `0x603f26a1` | 26 | 0x2000 |
| 37 | SERV_MAIN | `0x606d76dd` | 55 | 0x800 | 109 | STB_EXTERNAL | `0x60168fe3` | 25 | 0x600 |
| 38 | STB_CHARGE | `0x60161481` | 55 | 0x600 | 110 | STB_SEQ | `0x60172c3f` | 25 | 0x800 |
| 39 | TPC | `0x60c4023f` | 55 | 0x800 | 111 | TAKE_EXPOSE | `0x60421540` | 25 | 0x1000 |
| 40 | TPC_DATA | `0x60c412ce` | 55 | 0x300 | 112 | TAKE_FOCUS | `0x606bc087` | 25 | 0x800 |
| 41 | UI_OUT | `0x601194c3` | 55 | 0xc00 | 113 | TAKE_FUNC | `0x6020b00c` | 25 | 0x2000 |
| 42 | USRSTART5 | `0x60191b74` | 55 | 0x800 | 114 | TAKE_FUNC_CP | `0x6020b3b3` | 25 | 0x1000 |
| 43 | USRSTART2 | `0x60190df7` | 55 | 0x800 | 115 | TAKE_MAIN | `0x60289852` | 25 | 0x1000 |
| 44 | USRSTART4 | `0x60191a7f` | 55 | 0x800 | 116 | FIRMUP_LED | `0x601e748a` | 25 | 0x400 |
| 45 | USRSTART3 | `0x601912fb` | 55 | 0x800 | 117 | REC_EXT | `0x603e37c0` | 26 | 0x1800 |
| 46 | USRSTART_LOAD | `0x60044d1a` | 55 | 0x200 | 118 | ZOOM | `0x60280862` | 25 | 0x800 |
| 47 | PROCLOG | `0x600fa451` | 55 | 0x400 | 119 | ISEQ_CPU | `0x6060b7e8` | 25 | 0x1000 |
| 48 | DISP_FRAME | `0x60baa081` | 55 | 0x600 | 120 | TAKE_MOV | `0x60553eca` | 24 | 0x800 |
| 49 | AUD_LATE_RISER | `0x6075d6b5` | 55 | 0x600 | 121 | TPC_CAMC_FILEADD | `0x60c405d1` | 55 | 0x400 |
| 50 | BTSTK_TSKID | `0x60bb37d9` | 55 | 0x1c00 | 122 | TAKE_MAIN_CP | `0x6028a23b` | 26 | 0x1000 |
| 51 | BTTIM_TSKID | `0x60bb37d6` | 55 | 0x800 | 123 | MOVE_TRIM | `0x60cbaa25` | 55 | 0x1000 |
| 52 | BTEVU_TSKID | `0x60bb37d3` | 55 | 0x2000 | 124 | MOVE_FILEREAD | `0x60cb3cbd` | 55 | 0x1000 |
| 53 | BTAPL_TSKID | `0x60bb37dc` | 55 | 0x800 | 125 | MOVE_FILEWRITE | `0x60cb4695` | 55 | 0x1000 |
| 54 | BT_CTRL | `0x60bb37d0` | 55 | 0x1800 | 126 | PLAY_DECODE | `0x60c64443` | 53 | 0x1000 |
| 55 | BTIAP_TSKID | `0x60bb37df` | 55 | 0x800 | 127 | PLAY_LOAD_DRAW | `0x60c70347` | 53 | 0x1000 |
| 56 | OBEX | `0x60bb37cd` | 55 | 0x600 | 128 | TAKE_PROXY | `0x60298596` | 26 | 0x700 |
| 57 | OBEX_ACP | `0x60bb37ca` | 55 | 0x400 | 129 | REC_PROGRESS | `0x603f0c1f` | 55 | 0x600 |
| 58 | DISPLAY | `0x601744df` | 26 | 0x800 | 130 | MOVE_TIMELAPSE | `0x60cb9b7a` | 55 | 0x1000 |
| 59 | EFFECT | `0x60c7a697` | 55 | 0x1000 | 131 | ACC_MAIN | `0x60062f8f` | 55 | 0x600 |
| 60 | EFFECT_EXE | `0x60c7b700` | 55 | 0x1400 | 132 | PLAY_SOUND_BGM | `0x60c77619` | 53 | 0x1000 |
| 61 | HIGHLEVEL_MAIN | `0x60767d89` | 55 | 0x9000 | 133 | ISEQ_SUB | `0x6060bd18` | 55 | 0x1000 |
| 62 | CA_MAIN | `0x60cc6c83` | 55 | 0x2000 | 134 | ISEQ_SWPA_PROC | `0x60611469` | 55 | 0x1000 |
| 63 | PER_ROTATE | `0x6006d180` | 55 | 0x800 | 135 | ISEQ_SWPA_POS | `0x606110cf` | 55 | 0x1000 |
| 64 | PTPCOM | `0x60c45828` | 55 | 0x800 | 136 | ACC_SENS_MAIN | `0x60063014` | 55 | 0x600 |
| 65 | PTPASYNC | `0x60c4569a` | 55 | 0x400 | 137 | ICTLOG | `0x60cc0c7a` | 56 | 0x400 |
| 66 | TPC_LANG | `0x60c4232d` | 55 | 0x400 | 138 | DBG_OUT | – | – | – |
| 67 | C3D | `0x60c530e7` | 55 | 0x1000 | 139 | CPUCONN_CPU0 | – | – | – |
| 68 | EYEFI | `0x6062fbc6` | 55 | 0x1000 | 140 | CPUCALL_CPU0 | – | – | – |
| 69 | PER_EYE_SENSOR | `0x600687db` | 55 | 0x400 | 141 | S_SHELL | – | – | – |
| 70 | C3D_EXE_BRIDGE | `0x60c50156` | 55 | 0x400 | 142 | U_SHELL | – | – | – |
| 71 | SPC_TIMER | `0x60c570d2` | 55 | 0x400 | 143 | PWR_STANDBY | – | – | – |
| 72 | ISEQ_MAIN | `0x6060b41d` | 55 | 0x1cc0 |  | | | |  |

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

| Address | Name | Kind | Tag | Signature / layout | Notes | Source |
|---|---|---|---|---|---|---|
| `0x6005bc79` | prm_flash_op | func | V | d0 size, d1 mode (0 write, 0x10, 0x100 read, 0x200 erase), a0 src, a1 dst | DANGER: the only flash entry of the settings store. Sem 0x60040af0, WDT off around write/erase (wdt_flashop 0x6005bcb5 is inside), -> flash_write / 0x600c4e80 / fmem_erase | docs/RE_SETTINGS.md §4 |
| `0x6005c2f1` | prm_bank_new | func | V | -> a0 bank | 7 bank objects at 0xa26ff940, 28 B: +0 id, +2 current copy, +4/+8 shadow copies, +12 ROM default, +16 RAM, +20 size, +24 in use | docs/RE_SETTINGS.md §3 |
| `0x6005c3bb` | prm_bank_pick_copy | func | V | a0 bank -> d0 copy (0/1, 0xfe none valid) | Checks each shadow copy (prm_bank_check); with two valid copies picks the newer generation (+4, wraps) | docs/RE_SETTINGS.md §4 |
| `0x6005c524` | prm_bank_load | func | V | a0 bank -> d0 1 = failed | Valid shadow copy -> RAM (size/4 words) | docs/RE_SETTINGS.md §4 |
| `0x6005c559` | prm_bkram_load | func | V | a0 bank -> d0 1 = failed | Backup registers -> 0xa26ffa04, check, -> RAM | docs/RE_SETTINGS.md §4 |
| `0x6005c583` | prm_bkram_save | func | V | a0 bank | Gen++, checksum, RAM -> backup registers 0x98e00008 (14 words, 0x60066e14). Not flash | docs/RE_SETTINGS.md §4 |
| `0x6005c5be` | prm_bank_save | func | V | a0 bank -> d0 status | DANGER: flash write. memcmp RAM vs shadow; if different: next copy, gen++, checksum, cache flush, prm_flash_op(size, 0, RAM, shadow). Used for FLASH, EEROM, MODE | docs/RE_SETTINGS.md §4 |
| `0x6005c64c` | prm_fd1_save | func | V | a0 bank | DANGER: writes FLASHD1 (0x60000 B) to flash 0x40080000. Factory data. Runs whenever prm_ctl save has the flash flag | docs/RE_SETTINGS.md §4 |
| `0x6005c69b` | prm_fd2_save | func | V | a0 bank | DANGER: writes FLASHD2 (0x160000 B) to flash 0x400e0000. Factory data | docs/RE_SETTINGS.md §4 |
| `0x6005c6ea` | prm_bank_erase | func | V | a0 bank | DANGER: flash erase (prm_flash_op mode 0x200) of both shadow copies | docs/RE_SETTINGS.md §4 |
| `0x6005c78a` | prm_bank_check | func | V | d0 size, d1 id, a0 image -> d0 0 = ok | Valid when image+0 == bank id and the u16 sum of size/2 halfwords is 0 | docs/RE_SETTINGS.md §4 |
| `0x6005c7f3` | prm_bank_cksum | func | V | d0 size, a0 image -> d0 | Negated u16 sum of the image after the checksum word; stored at +2 by 0x6005c7e7 | docs/RE_SETTINGS.md §4 |
| `0x6005c811` | prm_bank_gen_inc | func | V | a0 image | Generation counter at image+4 += 1 | docs/RE_SETTINGS.md §4 |
| `0x6005c8e2` | prm_csv_load | func | V | a0 cmd {.., +20 drive, +24 dir, +28 name} | Reads a card file into 0x62496400 (max 0x1fffc B), then prm_csv_overlay_build | docs/RE_SETTINGS.md §6 |
| `0x6005d6aa` | prm_registry_build | func | V |  | Clears 4096-slot registry 0xa26ffa88 ({u16 key, u16 count, u32 data}), registers CONST, FLASH, BKRAM, EEROM, MODE, CPRAM records, the DEVICE key list, then FLASHD1/D2 if present | docs/RE_SETTINGS.md §3 |
| `0x6005d8e3` | prm_csv_overlay_build | func | V |  | Builds overlay registry 0xa2707a88 from 0x62496400 and sets 0xa26ffa84 = 1; prop_lookup then prefers the overlay | docs/RE_SETTINGS.md §6 |
| `0x6005d924` | prop_lookup | func | V | key | Registry 0xa26ffa88 + 8*(key>>4); width 0x6005efbd; per-core translator 0x6005c8cf | docs/PROFILE_INDEX_WB.md |
| `0x6005d987` | prm_reg_add_records | func | V | d0 registry, a0 records, a1 storage (0 = inline) | Records {u16 key, u16 count, data, pad 4}. Storage inline, or packed into a1 (aligned to width = key & 3, 0 -> 4). Duplicate key -> error 0x1c005001 | docs/RE_SETTINGS.md §3 |
| `0x6005da25` | prm_reg_add_keylist | func | V | d0 registry, a0 {u16 key, u16 count} list, a1 storage | Used for FLASHD1/D2 | docs/RE_SETTINGS.md §3 |
| `0x6005daeb` | prm_banks_init | func | V |  | Not a Ghidra function. Sets the bank objects (id, shadow, ROM default, RAM, size), clears headers, refills CPRAM, then prm_ctl load {0,1,1,1,1}. FLASHD1/D2 init at 0x6005dd7d / 0x6005de81 | docs/RE_SETTINGS.md §3 |
| `0x6005dfc3` | prm_clear | func | V | d0 device (1 CSV, 2 CPRAM, 3 BKRAM, 4 FLASH, 6 EEROM, 7 MODE, 10/11 FLASHD1/D2) | RAM only: device back to ROM defaults, then prm_registry_build. Not persisted until a save | docs/RE_SETTINGS.md §5 |
| `0x6005e129` | prm_flash_bank_merge | func | V | a0 stored image (0 = none) | Rebuilds FLASH bank RAM: stored records whose key and count match the ROM list first, then ROM defaults for the rest | docs/RE_SETTINGS.md §4 |
| `0x6005e309` | prm_bank_fill_defaults | func | V | d0 size, a0 RAM, a1 ROM records | Packed defaults for BKRAM/EEROM/MODE | docs/RE_SETTINGS.md §5 |
| `0x6005e852` | prm_device_of | func | V | d0 key -> d0 device id | By storage address: 1 CSV, 2 CPRAM, 3 BKRAM, 4 FLASH, 6 EEROM, 7 MODE, 10/11 FLASHD1/D2, 9 DEVICE, 5 ROM | docs/RE_SETTINGS.md §3 |
| `0x6005e947` | prop_handle | func | V | d0 key -> a0 storage ptr (0 if unknown) | prop_lookup + per-core translate 0x6005c8cf. Result is the a0 handle prop_get/prop_set accept: skips the lookup, value still read live | docs/RE_AE.md §0 |
| `0x6005e971` | prop_get | func | V | d0 key, d1 index, a0 0 (global) -> d0; `call ..,[d2,d3],12` | Reads RAM registry via 0x6005d924; no fixed RAM address per setting | docs/FIRMWARE_GUIDE.md §3 |
| `0x6005ea22` | prop_set | func | V | d0 key, d1 index, a0 handle (0 = lookup), a1 value; `call ..,[d2,d3,a2,a3],40` | Used by the AE publish 0x6042805e and the bracket step | docs/RE_AE.md §1 |
| `0x6005eeab` | prop_get_default | func | V | d0 key, d1 index -> d0 | ROM default via 0x6005f005 (record lookup in the owning bank ROM image) | docs/RE_SETTINGS.md §5 |
| `0x6005ef24` | prop_set_default | func | V | d0 key | Copies the ROM default over the property (core 0; wrapper 0x6005eefb forwards from core 1) | docs/RE_SETTINGS.md §5 |
| `0x6005efbd` | prop_read_width | func | V | d0 key, d1 index, a0 storage | Reads u8/s8/u16/s16/u32 by key type nibble (bit 3 = signed, low 3 bits = width) | docs/RE_AE.md §0 |
| `0x6005f099` | prm_ctl | func | V | a0 -> {u16 op, u16 bkram, u16 flash, u16 eerom, u16 mode} | DANGER for op 1/3. op 0 load (prm_load_all), 1 save (flash flag also writes FLASHD1/D2), 2 card CSV overlay, 3 erase. 21 call sites | docs/RE_SETTINGS.md §4 |
| `0x6005f341` | prm_load_all | func | V | a0 cmd | FLASH (merge), BKRAM, EEROM, MODE; a failed check logs, sets 0xa2715cb4/6/8 and restores that bank from ROM (prm_clear), then prm_registry_build | docs/RE_SETTINGS.md §4 |
| `0x60078620` | fmem_xchg_table | table | V | 3 x {u32 uncached shadow, u32 cached shadow, u32 flash} | Read by fmem_shadow_to_flash | docs/RE_SETTINGS.md §4 |
| `0x60078db0` | bkram_rom | table | V | {id 10, cksum, gen}, records | BKRAM defaults, 14 keys; RAM 0x6252a400 (packed, 56 B), backup registers 0x98e00008 | docs/RE_SETTINGS.md §3 |
| `0x60078e2c` | prop_const_records | table | V | records {u16 key, u16 count, data} | CONST: 449 read-only keys, storage inline in ROM | docs/RE_SETTINGS.md §3 |
| `0x6008e9d0` | cpram_rom | table | V | records, 0x932 words | CPRAM image, 522 keys, copied to RAM 0x624b6400 every boot (0x6005e111) | docs/RE_SETTINGS.md §3 |
| `0x60090e98` | flash_bank_rom | table | V | {u16 id 18, u16 cksum, u32 gen}, records | FLASH bank defaults, 113 keys; RAM 0x624ba400 (inline), shadow 0xa2898000, flash 0x40060000, 0x20000 B | docs/RE_SETTINGS.md §3 |
| `0x600921d4` | eerom_rom | table | V | {id 67, cksum, gen}, records | EEROM defaults, 125 keys; RAM 0x624da400 (packed), shadow 0xa2ab8000, flash 0x402c0000, 0x10000 B | docs/RE_SETTINGS.md §3 |
| `0x60096f04` | device_keylist | table | V | {id 0, cksum, gen}, {u16 key, u16 count} | 32 DEVICE keys, registered with count 0 (no storage) | docs/RE_SETTINGS.md §3 |
| `0x60096f90` | mode_bank_rom | table | V | {id 7, cksum, gen}, records (to 0x600be008) | MODE defaults, 1084 keys incl. snapshots 0x85d4/0x8b64/0x8b54; RAM 0x624ea400 (packed), shadow 0xa2a78000, flash 0x40240000, 0x40000 B. prop_init_table 0x600973dc lies inside | docs/RE_SETTINGS.md §3 |
| `0x600973dc` | prop_init_table | table | V |  | Property initial values | docs/MIN_SHUTTER.md |
| `0x600be00c` | fd1_keylist | table | V | {id 2, ..}, {u16 key, u16 count} | FLASHD1: 5 keys (0x7044 9200 words ...); RAM 0x628b8000, flash 0x40080000 | docs/RE_SETTINGS.md §3 |
| `0x600be02c` | fd2_keylist | table | V | {id 1, ..}, {u16 key, u16 count} | FLASHD2: 12 keys (0x7144 52000 words ...); RAM 0x62918000, flash 0x400e0000 | docs/RE_SETTINGS.md §3 |
| `0x600c4e80` | fmem_read | func | V | d0 size, d1 mode 0x100-0x102, a0 dst, a1 flash src | Read only | docs/RE_SETTINGS.md §4 |
| `0x600c4edc` | fmem_erase | func | V | d0 size, a0 addr | DANGER: flash erase via 0x600218a9 | docs/RE_SETTINGS.md §4 |
| `0x600c508d` | fmem_shadow_to_flash | func | V | a0 addr -> a0 flash addr | Maps a bank shadow to its flash address via table 0x60078620: 0xa2ab8000 -> 0x802c0000 (EEROM), 0xa2a78000 -> 0x80240000 (MODE), 0xa2898000 -> 0x80060000 (FLASH) | docs/RE_SETTINGS.md §4 |
| `0x602af887` | set_get | func | V | d0 id, a1 &out | Stock getter behind facade +8 (via 0x60826c82) | docs/LOOK_EDITOR.md |
| `0x602af890` | set_value | func | V |  | Set; -> store 0x602b9deb -> post-set 0x602b143e -> descriptor+24 callback. Unchanged value still runs callback | docs/FIRMWARE_GUIDE.md §3 |
| `0x602af8a3` | set_index_map_thunk | func | V |  | Value-by-index: index map; value 0x602af8c1 | docs/LOOK_MENUS.md |
| `0x602af8dc` | set_count_thunk | func | V |  | -> 0x602b1776. 3 callers: facade, 0x60886900, 0x60bda9b6.. | docs/LOOK_MENUS.md |
| `0x602af9d1` | set_available | func | V | (id, value) | -> 0x602b2961 availability | docs/LOOK_MENUS.md, docs/BUTTONS.md |
| `0x602afa81` | set_get_rules | func | V | d0 sid; `[],4` | Getter with rules; bypasses facade (wheel polygon, AE sids 469-471, 3281) | docs/LOOK_MENUS.md, docs/LIVE_ND.md |
| `0x602afad0` | set_default | func | V | id -> default | Behind facade +152 | docs/LOOK_EDITOR.md |
| `0x602b0560` | reset_pick | func | V |  | sid 10049 == 0 -> reset list 0x6049b31c (27); else list 0x6049c144 (626) and snapshot_store(0) | docs/RE_SETTINGS.md §5 |
| `0x602b174c` | desc_lookup | func | V | d0 sid -> a0 descriptor | Hash sid & 63 at 0x62247d48 (built by 0x602b16f7 over the 439 records) | docs/RE_SETTINGS.md §1 |
| `0x602b2fad` | facade_avail_handler | func | V |  | Only handles sid 1716 | docs/BUTTONS.md |
| `0x602b6b4f` | sid15271_cb | func | V |  | Only wired to sid 15271 descriptor (0x60431d64). Dial->movie 15272 trigger untraced | docs/MOVIE_COLOUR.md |
| `0x602b8916` | eff_sat_recompute | func | V |  | Sector callbacks 0x602b5e91/eaa/ec3/edc -> here -> 0x602b7b71 | docs/LV_BUNDLES.md |
| `0x602b972b` | reset_to_default | func | V | d0 count, a0 u16 id list | Each id := default. Gate byte 0x62257b04 (==1 skips boot resets) | docs/ASPECT.md |
| `0x602b9778` | reset_to_default_cache | func | V | d0 count, a0 u16 id list | Like reset_to_default but writes the RAM sid caches (0x602cc1f2/0x602cc345) instead of the properties | docs/RE_SETTINGS.md §5 |
| `0x602b9bad` | val_default | func | V | id |  | docs/ASPECT.md |
| `0x602b9cda` | val_dial_step | func | V | sid, dir | Also 0x602b9d15 -> 0x602ba146 | docs/BUTTONS.md |
| `0x602b9f70` | val_count | func | V | sid | Reads validator list | docs/FIRMWARE_GUIDE.md §3 |
| `0x602b9fdb` | val_by_index | func | V | sid, index |  | docs/FIRMWARE_GUIDE.md §3 |
| `0x602ba146` | val_step_core | func | V | d0 type, ... | Next/previous value by validator type: 1 u8, 2 s8, 3 s16 nearest, 4 s16, 5 u16, 6 blob (elem bytes) | docs/RE_SETTINGS.md §1 |
| `0x602ba40b` | forced_lookup | func | V | sid -> 128 = not forced |  | docs/LIVE_ND.md |
| `0x602ba4cc` | validator_hash_init | func | V |  | Hashes sid & 127 into RAM 0x62248528 at boot; lookup 0x602ba523 | docs/BUTTONS.md |
| `0x602ba523` | validator_lookup | func | V | d0 sid -> a0 record (0 = none) | Hash bucket sid & 127 (0x62248528); first record for the sid. 0x602ba54d also matches attr | docs/RE_SETTINGS.md §1 |
| `0x602cbc0a` | sid_get | func | V | d0 sid -> d0 | Getter by sid | docs/FIRMWARE_GUIDE.md §3 |
| `0x602cbc13` | sid_get_core | func | V | d0 sid -> d0 | sid_to_key + sid_to_index + prop_get. Body of sid_get | docs/RE_SETTINGS.md §1 |
| `0x602cbc5d` | sid_set | func | V | d0 sid, d1 value | Skipped while reset_gate == 1; else sid_set_core 0x602cbc74 (prop_set). 86 callers | docs/RE_SETTINGS.md §1 |
| `0x602cbcbf` | sid_prop_reset | func | V | d0 sid | Property back to its ROM default (prop_set_default) | docs/RE_SETTINGS.md §3 |
| `0x602cbcfd` | sid_prop_default | func | V | d0 sid -> d0 | ROM default of the sid property (prop_get_default) | docs/RE_SETTINGS.md §3 |
| `0x602cbd3b` | sid_to_key | func | V | d0 sid, a0 &handle -> d0 key (0 = none) | Ranges 0-1768 (0x604d6c14), 3000-3021, 4000-4022, 4500-4521, 10000-10110, 15000-15273; caches prop_handle per sid in RAM (0xa2699cb4.. for 0-1768). Sid 6000 is a RAM word, not a property | docs/RE_SETTINGS.md §1 |
| `0x602cbf8b` | sid_to_index | func | V | d0 sid -> d0 index | 4000/4500 ranges have no index (0) | docs/RE_SETTINGS.md §1 |
| `0x602cbffe` | snapshot_load | func | I | d0 slot | Copies key 0x85d4[slot*3538 + i] -> active key 0x8b64[i], i < 3538 (2 parts x 1769 sids). Slot meaning (Myset n) [I] | docs/RE_SETTINGS.md §5 |
| `0x602cc03a` | snapshot_store | func | I | d0 slot | Active 0x8b64 -> 0x85d4 slot. 0x85d4 has 32040 words = 9 slots, all in the MODE bank | docs/RE_SETTINGS.md §5 |
| `0x602cc076` | snapshot_get | func | V | d0 sid, d1 slot, a0 part -> d0 | 0x85d4[sid + part*1769 + slot*3538] | docs/RE_SETTINGS.md §5 |
| `0x602cc0a7` | sid_active_get | func | V |  | `cmp 1768`, x1769: 1769 words/part, bank stride 3538 | docs/HSL_PORT.md |
| `0x602cc0d0` | sid_active_set | func | V | d0 sid, d1 part, a0 value | Writes 0x8b64[sid + part*1769]; pair of sid_active_get | docs/RE_SETTINGS.md §5 |
| `0x602cc0fc` | sid_read_raw | func | V | sid | Used by mode-leave save 0x602b982a | docs/LIVE_ND.md |
| `0x602cc122` | sid_set_raw | func | V | (sid, value) | Used by preset apply loop 0x602b9b53 | docs/LIVE_ND.md |
| `0x602cc631` | sid_cache_all | func | V |  | Reads every sid of the 0, 3000, 4000, 4500, 15000 ranges into RAM 0x6225359c.. | docs/RE_SETTINGS.md §5 |
| `0x602cc6dd` | settings_save | func | V |  | DANGER: prm_ctl save {bkram 0, flash 0, eerom 1, mode 1}. Callers: OlyHfwPower::startShutDown, sleep, firmware-update check, life tests | docs/RE_SETTINGS.md §4 |
| `0x602cc767` | settings_save_bkram | func | V |  | prm_ctl save {bkram 1}. Backup registers only | docs/RE_SETTINGS.md §4 |
| `0x602ccc3c` | flash_prop_save | func | V | d0 key, d1 value -> d0 1 = failed | DANGER: sets one FLASH-bank key (0x0db1, 0xbac1, 0xbbc1) and saves with the flash flag, which also rewrites FLASHD1/D2. Caller 0x60827377 | docs/RE_SETTINGS.md §4 |
| `0x602ccfcb` | pm_refresh | func | V |  | Picture-mode refresh (also 0x602cd045); only for ids 111/1645/1646/15271 | docs/LOOK_EDITOR.md |
| `0x604317ac` | set_desc_registry | table | V | 439 x 60 B; +24 on-change callback | e.g. sid 47 record 0x60433408 cb 0x602b536b; sid 267 records 0x6043459c/0x6043acf8 | docs/FIRMWARE_GUIDE.md §3, docs/BUTTONS.md |
| `0x6043dfec` | pm_derive_table | table | V | rows {15272 == 1645, 1645 == v} | Derives sid 111 (key 0x9481); outputs 0x6043f2fc. GUI 111: Vivid 0 | docs/MOVIE_COLOUR.md |
| `0x6045e5fc` | rule_db | table | V | 201 x 20 B, sid at +0 | Availability/forced-value rules; hashed by 0x602b32d8. Drive = record 72 (sid 3281, 0x6045eb9c) | docs/BUTTONS.md, docs/LIVE_ND.md |
| `0x60460458` | eff_sat_jtab | table | V | by mode | Per-profile S (927-938..) -> effective 915-926 | docs/PROFILE_INDEX_WB.md |
| `0x60475e88` | mode_forced_blocks | table | V | index 0x6047a530, entry {u16 mode, u16 sub, u32 block, u16 count} | Forced-value pairs per mode (AP ME at 0x6047a800) | docs/LIVE_ND.md, docs/CODE_SPACE_MAP.md |
| `0x604a8420` | mode_planes | table | V | byte per sid per mode | Per-mode save/restore planes. Enter applies forced pairs 0x602b9a7d, leave saves 0x602b982a, undo 0x602b9ae8 | docs/LIVE_ND.md |
| `0x604a8774` | sid_default_table | table | V | s32 x 1769 (sid 0-1768) | Read by val_default; then 0x604aa318 (10000-10110), 0x604aa4d4 (15000-15273). Other ranges default 0 | docs/RE_SETTINGS.md §1 |
| `0x604ad20c` | sid_default_region | table | V | 12 B {u16 region, u16 n, u32 sids, u32 values}, 0-terminated | val_default override keyed by sid 4508. One row: region 1 -> sid 3010 = 0, 3009 = 1 | docs/RE_SETTINGS.md §1 |
| `0x604cc98c` | validator_table | table | V | 1333 x 20 B {u16 sid, u16 attr, u32 list, u32 alt, u16 bytes, u16 elem, u8 sub, u8 type, u16 0} | Record n = 0x604cc98c + 20n (442 = sid 270 at 0x604cec14; 1061 = sid 1147 at 0x604d1c70). Allowed values for menus and dial | docs/FIRMWARE_GUIDE.md §3 |
| `0x604d6c14` | sid_key_table | table | V | 1769 x {u16 key, u16 index} | sid 0..1768. key = id<<4 \| type (width/sign). 4-B stride | docs/FIRMWARE_GUIDE.md §3, docs/FEATURE_GAPS.md |
| `0x604d87b8` | sid_key_3000 | table | V | 22 x {u16 key, u16 index} | Sids 3000-3021. Followed by 0x604d8810 (4500-4521, u16 key), 0x604d883c (4000-4022, u16 key), 0x604d886a (10000-10110, {key, index}), 0x604d8a26 (15000-15273, {key, index}) | docs/RE_SETTINGS.md §1 |
| `0x6061907a` | card_param_csv_load | func | V |  | On card mount (dcfnum.c, 0x60618b53): finds PARAMDT/CP??????.CSV, then prm_clear(1) + prm_ctl op 2 | docs/RE_SETTINGS.md §6 |
| `0x607b3c32` | canexec_get | func | V | -> obj; vtbl[0](id) | CANEXEC row check (0x6082686f -> 0x608290c8) | docs/BUTTONS.md |
| `0x60adf518` | item_cond_table | table | V | 611 x 12 B {id, cond bytes, n} | Menu grey-out; read by 0x608290c8; cond byte -> predicate table 0x60ade144 (OR) | docs/BUTTONS.md, docs/LIVE_ND.md |
| `0x60ef98a4` | opc_prop_table | table | V | 24 B {char* name, u32 sid, get, set, list, 0} | Wi-Fi remote property names: takemode, drivemode 3281, focalvalue 3, expcomp 2, shutspeedvalue 4, isospeedvalue 6, wbvalue 9, artfilter 280, colorphase 665 ... | docs/RE_SETTINGS.md §2 |
| `0x62245800` | set_runtime_slots | data | V |  | Two runtime list slots | docs/ASPECT.md |
| `0x62248528` | validator_hash | table | V | 128 buckets | RAM | docs/BUTTONS.md |
| `0x62257b04` | reset_gate | data | V | u8 | Stock skips boot resets when == 1 (0x602cc6cf, 0x602af9e1) | docs/ASPECT.md |
| `0x624ea400` | mode_bank_ram | data | V | 0x40000 B: {u16 id, u16 cksum, u32 gen}, packed values | User settings working copy. Storage of each key: docs/settings_catalogue.json | docs/RE_SETTINGS.md §3 |
| `0x62509d7c` | sid3009_language | data | V | u8, MODE bank (key 0x85e1) | Menu language value; 5 = Simplified Chinese, 6 = Traditional Chinese, 1 = English | docs/I18N_ZH.md |
| `0x98e00008` | bk_regs | data | V | u32 x 14 | Battery-backed registers for the BKRAM bank (0x60066e14 write, 0x60066e29 read) | docs/RE_SETTINGS.md §4 |
| `0xa26ff940` | prm_banks | data | V | 7 x 28 B bank objects | Pointers: 0xa2711a88 CONST records, 0xa2711a8c CPRAM ROM, 0xa2711a90 FLASH, 0xa2711a94 BKRAM, 0xa2711a98 EEROM, 0xa2711a9c MODE, 0xa2711aa0 DEVICE, 0xa2711aa4 FLASHD1, 0xa2711aa8 FLASHD2 | docs/RE_SETTINGS.md §3 |
| `0xa26ffa88` | prop_registry | table | V | 8 B per key>>4 | RAM property registry | docs/PROFILE_INDEX_WB.md |
| `0xa2707a88` | prop_overlay_registry | table | V | 4096 x 8 B | CSV overlay; active when 0xa26ffa84 != 0 (prop_lookup checks it first) | docs/RE_SETTINGS.md §6 |

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

| Address | Name | Kind | Tag | Signature / layout | Notes | Source |
|---|---|---|---|---|---|---|
| `0x600daed9` | strlen | func | V | a0 |  | docs/FILM_LIBRARY.md |
| `0x601df03c` | ap_P | func | V | `call ..,[d2],8` -> d0 1, a0 = the unswapped P (also while P2/P3 is in the state word) | Ours (ap_custom). Reads the state word 0x622cbcc2; with movie +960 VM and +964 back-pointer it follows +968 to P | docs/SPLIT_TONE_G1.md / docs/SPLIT_TONE.md |
| `0x601e2e28` | u_apply | func | V | a0 = L, a2 = P, d3 = k; T = L+2456 (entry 64 + name 16) | Ours (film_menu_v2 fm_ui): staging T -> slot k bytes 0..49 only (v0.25 bound 0x601e2e46; +50..63 untouched, so split +62/+63 survives the copy), flags byte last, name P+544+16k, dirty; then jmp lt_post 0x601e233c -> sl_pick | patches/looks_split |
| `0x601e37b4` | fm_post | func | V | a2 = P, d3 = k, a3 = parent | Ours (lv_art_refresh): after a Film pick, LV art refresh then ed_poke | patches/looks_split |
| `0x601e39aa` | sl_pick | func | V | a2 = P, d3 = k, a3 = parent | Ours (v0.25 shade): Film-pick tail, library look sets slot +49 (Shading). Its tail jmp 0x601e3a16 -> ls_pick from v0.32 (was fm_post 0x601e37b4) | patches/looks_split |
| `0x601e3a16` | sl_pick_tail_jmp | site | V | 5 B jmp rel32 (dc ..) | Ours: v0.32 -> ls_pick (slot +62/+63 from the LOOKS.BIN stash or the Own snapshot), which ends jmp fm_post 0x601e37b4 | patches/looks_split |
| `0x604cda94` | lens_btn_lists | table | V |  | L-Fn validator lists 0x604cda94/a8/bc (28/28/29 codes) | docs/LENS_BUTTONS.md |
| `0x607b6430` | kh_ret0 | func | V | clr d0; rets | sdk sub-command stub (entered by calls (a1) at 0x607adda1) | docs/PLUGINS.md §9 |
| `0x607b6433` | kh | func | V | jmp target from 0x60ce011a, on ca_key_generic's frame | kh_chk -> 1: ret [d2,a2,a3],40; else rebuild registers, call 0x60cc9a05, jmp 0x60ce0121 | docs/PLUGINS.md §9 |
| `0x607b6454` | kh_chk | func | V | call entry [d2,d3,a2,a3],24 -> d0 1 handled | ap_P, P+852 EP7K, hook word B+24 inside B's cached code bytes -> calls hook(d0 event, d1 B, a0 CA, a1 record) | docs/PLUGINS.md §9 |
| `0x607b6497` | ka_sel | func | V | calls entry: d0 action 41..67, a0 CA, a1 record | movm [d2,d3,a2,a3] + add -52 -> jmp 0x60ceb5b6; other d0 -> -1 | docs/PLUGINS.md §9 |
| `0x607b64ad` | ka_get | func | V | calls entry: d0 key, d1 index -> d0 | prop_get 0x6005e971 with a0 = 0 and its 4 B slot | docs/PLUGINS.md §9 |
| `0x607b64c0` | kh_api | table | V | u16 1, u16 6, fw_text, prop_get, text_set, ka_sel, ka_get, features (bit 0 key hook) | Plugin API v1.1; pl_chk passes it to init (mov at 0x601e1ace) | docs/PLUGINS.md §9 |
| `0x607b8430` | ov_upd | func | I | overlay_probe: view +0 wrapper | Runs 0x60dec790, then sets the .bss overlay flag (0x622ab792 = 1). Same frame/return as the body | docs/EXTRAS_OVERLAY.md |
| `0x607b8450` | ov_post | func | I | overlay_probe: window +164 | Post-paint. Flag 0 -> stock retf. Flag 1 and editor on the Extras page (P valid, EP7E, axis 4) -> draws four text rows via ge_draw_text into the window gc, clears the flag | docs/EXTRAS_OVERLAY.md |
| `0x607b88bc` | dg_fw | func | V | call entry [d2,d3,a2,a3],88: a0 widget, a1 value | Firmware Body value "L/OK" (K from the keyhook Fn stage byte 0x6203bcb2, PLUGINS §11/§12); empty value -> fw_val | docs/PLUGINS.md §10 |
| `0x607b898b` | dg_paint | func | V | jmp from 0x60d005ef | Stock +164 call, then O2, PT log and dg_draw (current window only) while the profile view is alive (0x622ab792 bit 0) | docs/PLUGINS.md §10 |
| `0x607b8a58` | dg_draw | func | V | call from dg_pnt [d2,d3,a2,a3],108; a1 = gc = *(painter+8), d3 window | Four probe rows on the Extras page: style colour 1/2/4/6; always selects the window default text style (+488 -> 0x60d0fce0), gc+0x34 = 2, draws, releases the font (0x60d10708), restores gc+0x4c / +0x34 (PLUGINS §13); none -> O4 | docs/PLUGINS.md §11 |
| `0x607b8d09` | dg_key0 | func | V | jmp from 0x60ce011a | Log K0 (event, record+196 state, record+4), kh_chk; handled -> log D0, ret [d2,a2,a3],40; else kh_miss | docs/PLUGINS.md §13 |
| `0x607b8d3a` | dg_key1 | func | V | jmp from 0x60cebc9a | As dg_key0 with kh_chk2 / kh2_miss, ret [d2,d3,a2],48 | docs/PLUGINS.md §13 |
| `0x607b8d6b` | dg_twin | func | V | jmp from 0x60ce0190 | Log KT, rebuild the copy-loop registers, replay call 0x60cc9a05,[d2],4, jmp 0x60ce0197 | docs/PLUGINS.md §13 |
| `0x607d55ef` | ls_pick | func | V | jmp from 0x601e3a16; a2 = P, d3 = k | Ours: call ls_pk, jmp fm_post | patches/looks_split |
| `0x607d55f9` | ls_pk | func | V | [d2,d3,a2,a3],20 | Ours: real P (ap_P) + L + EP7W tag: library pos -> stash to slot +62/+63 (0 clears); Own / Stock -> snapshot L+2132+80k +62/+63; else nothing | patches/looks_split |
| `0x607f9062` | facade_get | func | V | -> OlyApiSettingControllerController | GUI settings facade singleton | docs/FIRMWARE_GUIDE.md §3 |
| `0x607f9549` | facade_GetValue | func | C | (id, &out) | -> 0x60826c82 -> 0x602af887 | docs/LOOK_EDITOR.md |
| `0x607f95dc` | facade_Count | func | V | id | -> 0x60826d53 -> 0x602af8dc | docs/LOOK_MENUS.md |
| `0x607f964a` | facade_GetDefault | func | V | (id, &out) | -> 0x602afad0 | docs/LOOK_EDITOR.md |
| `0x607f9912` | facade_ValByIdx | func | V | id, idx | -> 0x60826d5f -> 0x602af8a3/0x602af8c1 | docs/LOOK_MENUS.md |
| `0x607f9a06` | facade_Available | func | V | id, value | +20 (also +36 0x607f90f9) -> 0x60826dde -> 0x602af9d1 | docs/LOOK_MENUS.md |
| `0x607fa129` | facade_SetValue | func | C | (id, flags, value) | GUI set call to settings manager at 0x607fa355 | docs/FIRMWARE_GUIDE.md §3 |
| `0x60827440` | settings_mgr_set | func | V |  | Settings manager entry; listeners 0x608280ac.. | docs/FIRMWARE_GUIDE.md §3 |
| `0x60886900` | oishare_prop_list | func | V |  | OI.Share remote property list (entry 0x608868e5 <- 0x6097c7d4) | docs/LOOK_MENUS.md |
| `0x60932fa6` | c3d_wheel_polygon | func | C | view vtable +4972 (case 1) | Cursor from sid 1648, ID table 0x60b40c4c, values via 0x602afa81. Hook 0x609330f9 | docs/LOOK_MENUS.md |
| `0x60a9a918` | sdk_subcmd_api_word | data | V | {name*, fn} word: "api" -> 0x607b4b25 | v0.32 keyhook: -> kh_ret0. Also 0x60a9a920 starttimer (0x607dab9f), 0x60a9a928 stoptimer (0x607dac2e) | docs/PLUGINS.md §9 |
| `0x60acb0dc` | facade_vtable | table | V | +0 Set, +8 Get, +20/+36 avail, +24 count, +28 val by idx, +152 default | Data-hookable words (0x60acb0e4, 0x60acb0f4/f8, 0x60acb174) | docs/FIRMWARE_GUIDE.md §3, docs/LOOK_MENUS.md |
| `0x60cc872f` | btn_dispatch | func | C |  | key -> sid -> value -> action, no per-key check | docs/BUTTONS.md |
| `0x60cc87ac` | action_class | func | V | d0 action -> class | Table 0x60f384f8 (92 x {action, class, name}). Class 0 includes 75 LV_CTRL and 76 LV_CTRL_PROFILE | docs/PLUGINS.md §7 |
| `0x60cc9a05` | ca_event_map | func | V | call entry [d2],4; reads the caller's (4,sp) = event -> d0 | Pure: reads only the stack and image tables; ends retf (MDR). Result goes to btn_dispatch | docs/PLUGINS.md §9 |
| `0x60ccf9f3` | ca_get_setting | func | V | d0 sid -> value (3200 on failure) | getSetting through interface 0x607f9062 (vtbl +8, a1 = &out). btn_dispatch reads sid 47 here | docs/PLUGINS.md §7 |
| `0x60cd4830` | start_profile_select | func | V | call entry, frame [d2,d3,a2,a3],92; d0 out, a0/a1 handler context | SubAppMdlShootingCmn::startProfileSelect: CANEXEC(76) 0x60cce3dc, then CA state 0x5704 / request 183. Only caller 0x60cd2fff (startMoveToShootingReady, START_PROFILE_NEXT_PROC). The only 76 immediate in CA code 0x60cc0000-0x60d00000 | docs/PLUGINS.md §7 |
| `0x60ce0108` | ca_key_generic | func | V | calls entry; call entry 0x60ce010d | Generic key handler (Fn press/release in most shooting states): btn_dispatch, then action class 0x60cc87ac: 2 -> 0x60ce026a, 1 -> 0x60ceb5b6, 0 -> nothing | docs/PLUGINS.md §7 |
| `0x60ce011a` | ca_key_generic_kmap_call | site | V | call 0x60cc9a05,[d2],4 (7 B) | First call after the 6-word record copy. Fixed registers there: a0 = sp+28, a1 = a2+24, d0 = (24,sp), d1 = 0; a3 = CA module, a2 = event record. No branch into +1..+7. v0.32 keyhook: jmp kh + 2 nop | docs/PLUGINS.md §9 |
| `0x60ce017e` | ca_key_generic_twin | func | V | frame [d2,d3,a2,a3],44; a0 CA, a1 record; same 24-B copy loop | Unhooked twin of 0x60ce0108 (CA state 0x5704). kmap call 0x60ce0190 (7 B), resume 0x60ce0197; nothing branches into +1..+6. v0.32 diag: jmp dg_twin | docs/PLUGINS.md §13 |
| `0x60ce05ab` | ca_key_release | func | V | calls entry, frame 48 | One of the Fn release (0x0100002f) handlers; release never reaches ca_key_generic 0x60ce0108 | docs/PLUGINS.md §9 |
| `0x60ce2d84` | ca_multi_function_press | func | V | class-2 action 18 EVF_FN (Multi Function) handler | Request 174, CA state 0x590d (Fn held). The popup opens on the release | docs/PLUGINS.md §12 |
| `0x60ce2da0` | ca_multi_function_release | func | V | state 0x590d handler for Fn release 0x0100002f | Sub-function action = 0x60cc8929 (sid 437 -> table 0x60f38d8c: 6 -> 49 colour/mono profile, 3 -> 50 aspect); 49 -> call 0x60ceb5b6 -> state 0x5800 | docs/PLUGINS.md §12 |
| `0x60ceb5b6` | ca_select_mode | func | V | call entry [d2,d3,a2,a3],68; d0 action, a0 CA module, a1 event record | Class-1 action handler (stock popup + dials), CANEXEC 0x60cce3dc inside; entered from ca_key_generic for class 1. Action 50 = SELECT_MODE_MULTI_ASPECT | docs/PLUGINS.md §9 |
| `0x60ceb952` | sel_exit | func | V | select state exit | Reads and clears 0x61fb0dd8; Fn (in list 0x60f39e08, a press) -> 0x60cebd8b -> 0x60cebdeb: record+176 = key, +184 = 1 (re-posted key event) | docs/PLUGINS.md §12 |
| `0x60cebce9` | sel_other_key_exit | site | V | 0x60cebc89 jump-table case 26 | 0x60cd2330(key), request 158, ddc = key, dd8 = key when its function != the open mode: exit and replay | docs/PLUGINS.md §12 |
| `0x60cebd3d` | sel_fn_same_mode_close | site | V | 0x60cebc89 jump-table case 18 | Multi Function key in its own popup: request 158, ddc = key, no dd8 (close, no replay) | docs/PLUGINS.md §12 |
| `0x60cf30b5` | ca_handler_calls | site | V | calls (a2): a0 = (CA+164), a1 = event record | The handler return value is ignored (the matcher returns a3 = matched) | docs/PLUGINS.md §9 |
| `0x60cf5b2c` | ca_dispatch | func | V | a0 CA module, a1 event record, d0 event code | Prefilter 0x60cf6473, then sub-state table, state table (0x60cf6824: state id -> image list), default table 0x60f6ad58 (124). Records {u32 event, 1, 1, fn}, matched by 0x60cf304c, fn by `calls`. All tables are in the loaded image | docs/PLUGINS.md §7 |
| `0x60cf6824` | ca_state_table | func | V | d0 state id (0x50xx..0x5exx) -> table, count | Jump table 0x60f6b9fc by id>>8; per-group lists {u32 id, u32 table, u32 n} in the image (group 0x51 at 0x60f59668) | docs/PLUGINS.md §7 |
| `0x60cfd311` | gui_WinMain | func | V |  | "[GUI App]:WinMain called" / messageloop | docs/RE_DRAW_PLUGIN.md §2.4 |
| `0x60cfe263` | win_empty_method | func | V | retf [],0 | +164 word of about 400 window vtables (0x60f94628 .. 0x611104b8); re-pointing one vtable covers one class only | docs/PLUGINS.md §10 |
| `0x60cfe263` | ge_window_postpaint | func | V | retf [],0 | The empty vtable +164 method, shared by both window classes (words 0x60f94820, 0x60fac3f0). overlay_probe re-points these to ov_post | docs/EXTRAS_OVERLAY.md |
| `0x60cfec91` | gui_db_get | func | V | (id, size, buf) | 244 callers; set 0x60cfeca9(id, size, buf, flag) | docs/RE_UI.md §5.1 |
| `0x60d00506` | ge_paint_window | func | V | a0 window, a1 gc or 0 (then window+72); frame [d2,d3,a2,a3],32 | One caller 0x60d3907e. Early out if u16 window+1372 == 0. Calls vtable +708, +680, then +164 (0x60d005ef) and +160, then paint end 0x60d0658a / 0x60d06468 | docs/PLUGINS.md §10 |
| `0x60d00506` | ge_window_paint | func | V | a0 window, a1 painter; ret [d2,d3,a2,a3],32 | Window paint: draws the child widgets (0x60d0f3aa / 0x60d06530 / 0x60d0642a), then vtbl +164 (0xa4) then +160 (0xa0), then ge_paint_end (present). *(window+72) and a1 are the painter; gc = *(painter+8) (0x60d060e3, PLUGINS §11) | docs/EXTRAS_OVERLAY.md |
| `0x60d005ef` | ge_paint_post164_site | site | V | mov (164,a2),a2; calls (a2) (6 B); a0 window, a1 = (4,sp) gc | The only +164 call. a0/a1/a2 reloaded at 0x60d005f5; nothing branches into +1..+5. v0.32 diag: jmp dg_paint + nop | docs/PLUGINS.md §10 |
| `0x60d00f90` | win_default_text_style | func | V | window vtable +488; a0 window -> d0 u16 window+108 | Both window classes. Ctor sets 0. Used by the generic GE text draw 0x60d06bb7 before 0x60d0fce0 | docs/PLUGINS.md §11 |
| `0x60d060e3` | painter_gc | func | V | a0 painter -> a0 gc = *(painter+8); [],0 | The +164 argument and *(window+72) are the painter; the drawer needs this gc (PLUGINS §11) | docs/PLUGINS.md §11 |
| `0x60d0642a` | ge_paint_begin | func | V | a0 gc, a1 window+1200, d0 window+1392; [d2,d3,a2,a3],20 | DC clip from window+1200 (0x60d0f8e3), gc+12 = window+1200, update region (36 B) -> gc+168 | docs/PLUGINS.md §11 |
| `0x60d06468` | ge_paint_end_single | func | V | a0 gc; [d2,d3,a2,a3],48 | ge_present(gc+8), then each gc+168 rect -> 0x60d0ed81 (sync front -> back through DC +8) | docs/PLUGINS.md §11 |
| `0x60d06468` | ge_paint_end_single | func | V |  | ge_present, then dirty-rect copy loop (0x60d0ed81). Called at 0x60d0061b | docs/RE_DRAW_PLUGIN.md §2.4 |
| `0x60d0658a` | ge_paint_end_multi | func | V |  | Per flagged layer: 0x60d0fd95 + ge_present; then drawOsdEnd. Called at 0x60d00612 | docs/RE_DRAW_PLUGIN.md §2.4 |
| `0x60d0695c` | ge_draw_label_generic | func | V | GE text draw (caller 0x60d0691b) | Colour = window +504, text style = window +488 -> 0x60d0fce0 (skips if a0 0), 0x60d0fd83(2), 0x60d0758f | docs/PLUGINS.md §11 |
| `0x60d0758f` | ge_draw_text_res | func | V | d0 resource string id, d1 style*, a0 gc, a1 rect; [d2,a2,a3],16 | String id -> 0x60d10bf2, then ge_draw_text | docs/PLUGINS.md §11 |
| `0x60d075a7` | ge_draw_text | func | V | d0 style*, d1 wchar*, a0 gc, a1 rect{x0,y0,x1,y1 s16}; frame [d2,d3,a2,a3],252 | High-level string drawer: per-glyph through DC +28 / drawFont. Returns early if string 0 or gc+0x4c 0. Style 24 B (PLUGINS §11): +0 text colour (applied with 0x60d0fc05, overrides any gc colour; saved/restored), +4 / +8 colours (gc+0x28c/+0x290), +12 h-align, +13 v-align, +14 x off, +16 right inset, +18 y off, +20 bottom inset. Callers 0x60d0758f/0x60d455bf/0x60d4728a/0x60d473db | docs/EXTRAS_OVERLAY.md |
| `0x60d0ed79` | ge_present | func | V | [],4 | -> 0x60d125af: if 0x61fb2939 set, gpiUpdateDisplay(0) (whole-buffer flip), 0x61fb2938 ^= 1, clear 0x61fb2939 | docs/PLUGINS.md §11 |
| `0x60d0ed79` | ge_present | func | V | `call 0x60d125af,[],4; ret [],4` | Callers 0x60d06475 (single-layer paint end 0x60d06468), 0x60d065d4 (multi-layer 0x60d0658a). Proposed overlay hook site | docs/RE_DRAW_PLUGIN.md §2.4, §4.1 |
| `0x60d0f530` | region_count | func | V | a0 region -> d0 (24,a0) | Update region: 36 B, rects at +0 (8 B each), count +24; 0x60d0f529 clears the count, 0x60d0f539 copies 36 B | docs/PLUGINS.md §11 |
| `0x60d0fb40` | gc_set_colour3 | func | V | d0 colour, a0 gc; ret [a2],8 | gc+0x290. ge_draw_text calls it with style +8 | docs/PLUGINS.md §11 |
| `0x60d0fb5d` | gc_set_colour2 | func | V | d0 colour, a0 gc; ret [a2],8 | gc+0x28c (converted if gc+0x294/295 == 1). ge_draw_text calls it with style +4 | docs/PLUGINS.md §11 |
| `0x60d0fc05` | gc_set_colour | func | V | d0 colour, a0 gc; retf [d2,d3,a2,a3],16 | Writes gc+0x24 and gc+0x280; if gc+0x294/295 set, remaps the colour through gc+0x296..298 shifts and gc+0x274/278/27c masks. ge_draw_text overwrites it from style +0, so set the colour in the style (PLUGINS §11). 8-bit palette index; 0 = transparent | docs/EXTRAS_OVERLAY.md |
| `0x60d0fce0` | gc_set_font | func | V | d0 text-style id, a0 gc; ret [a2],8 -> a0 font or 0 | Text-style id (74-B record at *(0x61fc15bc+4*bank)+74*id), not a font index; sets gc+0x4c via 0x60d0fd74. Stock calls it before every text draw (PLUGINS §11) | docs/EXTRAS_OVERLAY.md |
| `0x60d0fd83` | gc_set_mode34 | func | V | a0 gc, d0 -> u16 gc+0x34; retf | All three stock callers pass 2 right before a text draw | docs/PLUGINS.md §13 |
| `0x60d0fd83` | gc_set_mode | func | V | d0 value, a0 gc; retf [],0 | Writes gc+0x34. Stock sets it to 2 before a list text draw | docs/EXTRAS_OVERLAY.md |
| `0x60d0ffb4` | gui_post | func | I | (code, lparam, ., ., msg*) | Builds a 28-B message (sender 0xfffe) and enqueues; 61 callers, most in the input layer 0x60d1d9ec..0x60d25a02 | docs/RE_UI.md §2.3 |
| `0x60d10133` | gui_msg_get | func | V | (timeout) -> nonzero when a message was copied | Serves 0x1002 and 0x1100 first | docs/RE_UI.md §2.3 |
| `0x60d1050a` | gui_msg_purge | func | V | code -> n removed |  | docs/RE_UI.md §2.3 |
| `0x60d10708` | gc_font_release | func | V | a0 font (from 0x60d0fce0); [],4 | calls (0x61fb2614)(font) if both non-zero. Every stock 0x60d0fce0 user calls it after its draw (0x60d4c638, 0x60d457a5, 0x60d0695c); the gc+0x4c it leaves behind is a released font | docs/PLUGINS.md §13 |
| `0x60d10b88` | osd_text_style | func | V | d0 style id -> d0 74-B record | (0x61fc15bc)[bank] + 74*id: the text-style records gc_set_font 0x60d0fce0 reads | docs/I18N_ZH.md |
| `0x60d10bf2` | osd_string_get | func | V | d0 string id -> a0 wchar*; [d2],8 | a0 = (*(0x61fc1530 + 4*bank))[id]; bank = 0x60d10c09. Behind ge_draw_text_res 0x60d0758f and 9 other callers | docs/I18N_ZH.md |
| `0x60d10c09` | osd_lang_bank | func | V | -> d0 = (u8)(0x61fb2818); retf | Index into the per-bank string-table and text-style pointer arrays 0x61fc1530 / 0x61fc15bc | docs/I18N_ZH.md |
| `0x60d113d1` | hsm_init | func | V | (n_ss, ss, ctx, table, state) | Clears ctx, runs first entry. Called from 0x60dd4b19 (19, 1, ctx, 0x611317c4, 2) | docs/RE_UI.md §2.1 |
| `0x60d11448` | ssmenulv_dispatch | func | C | handler = words[matrix[event_index*29 + state-1]] | SsMenuLv: event-major matrix (state 2 LC, 3 SCP). Handler words e.g. 0x611a2c68 (word 24) | docs/AP_CUSTOM.md |
| `0x60d1144d` | hsm_dispatch | func | V | (event, lparam, ctx, uparam) -> 0 ok, 1-4 errors | Call-site entry of ssmenulv_dispatch (prologue 0x60d11448). handler rc = new_ss<<8 \| new_state; exit/entry on change. Sole caller gui_WinMain 0x60cfd558 | docs/RE_UI.md §2.1 |
| `0x60d1145e` | editor_fsm_dispatch | func | V |  | Common FSM dispatcher body | docs/HSL_PORT.md |
| `0x60d1158b` | hsm_event_index | func | V | (event, ., ctx) -> index or 0xffff | Linear scan of the descriptor event map | docs/RE_UI.md §2.1 |
| `0x60d115c2` | hsm_desc | func | V | a0 ctx -> a0 descriptor | descriptor = (*(u32 **)(ctx + 4))[ss - 1]. The ss table pointer is read only through ctx+4 (0x611317c4 has one reference, the init at 0x60dd4b21) | docs/PLUGINS.md §7 |
| `0x60d115c2` | hsm_desc_get | func | V | a0 ctx -> descriptor of ctx.ss |  | docs/RE_UI.md §2.1 |
| `0x60d115d4` | GPIInitPlatform | func | V |  | getVramInfo for layers 0..2 x 2 buffers + WORK; clears each layer (rect 0,0,800,600); builds DC function tables; 800x600 canvas | docs/RE_DRAW_PLUGIN.md §2.3 |
| `0x60d1192f` | gpi_dc_get | func | V | d0 layer -> a0 DC | 0..2 -> 0x6246a774 + 164n; -1 -> 0x6246a960; -2 -> 0x6246aa04 | docs/RE_DRAW_PLUGIN.md §2.3 |
| `0x60d11964` | gpi_dc_dot | func | V | DC fn +0 | Picks back-buffer VRAM of DC layer -> gpiDrawOsdDot | docs/RE_DRAW_PLUGIN.md §2.3 |
| `0x60d119a2` | gpi_dc_line | func | V | DC fn +4 | -> gpiDrawOsdLine | docs/RE_DRAW_PLUGIN.md §2.3 |
| `0x60d11b02` | gpi_dc_rect | func | V | DC fn +16 | -> gpiDrawOsdRectangle | docs/RE_DRAW_PLUGIN.md §2.3 |
| `0x60d1216c` | gpi_dc_char | func | I | DC fn +28; d0 x, d1 y, a0 DC, a1 -> char code | One character via font engine 0x60d15xxx -> gpiDrawCharactor; 0x40 (@) -> symbol path 0x60d154fa. Stack args not decoded | docs/RE_DRAW_PLUGIN.md §2.3 |
| `0x60d125af` | gpi_present_if_dirty | func | V | () | If dirty 0x61fb2939: palette commit 0x60d132e6, gpiUpdateDisplay(0), cur ^= 1, dirty = 0. Sole caller 0x60d0ed79 | docs/RE_DRAW_PLUGIN.md §2.4 |
| `0x60d125f0` | gpi_dc_sync_rect | func | V | DC fn +8 | drawOsdStart; copy rect front -> back (0x60d12adf); drawOsdEnd; dirty = 1 | docs/RE_DRAW_PLUGIN.md §2.3 |
| `0x60d127f8` | gpiDrawOsdDot | func | V | d0 x, d1 y, a0 VRAM_INFO*, a1 colour, (4,sp) layer; `[d2,d3,a2,a3],68` | -> osd_drawDot | docs/RE_DRAW_PLUGIN.md §2.3 |
| `0x60d128c5` | gpiDrawOsdLine | func | V | d0 x, d1 y, a0 VRAM, a1 w, (4) h, (8) colour, (12) layer; `[d2,d3,a2,a3],84` | -> osd_drawLine | docs/RE_DRAW_PLUGIN.md §2.3 |
| `0x60d129d0` | gpiDrawOsdRectangle | func | V | d0 x, d1 y, a0 VRAM, a1 w, (4) h, (8) colour index, (12) layer; `[d2,d3,a2,a3],92` | Filled; adds draw offset, clip 800x600 (overflow only logged) -> osd_drawRect | docs/RE_DRAW_PLUGIN.md §2.3 |
| `0x60d12adf` | gpiDrawOsdBlockCopy | func | V | `[d2,d3,a2,a3],108` | -> osd_copyAreaBlock | docs/RE_DRAW_PLUGIN.md §2.3 |
| `0x60d12c4b` | gpiDrawBitmap | func | V | d0 x, d1 y, a0 VRAM, (4) w, (8) h, ..; `[d2,d3,a2,a3],96` | -> osd_drawBitmap; data format not traced | docs/RE_DRAW_PLUGIN.md §2.3 |
| `0x60d12d57` | gpiDrawCharactor | func | V | `[d2,d3,a2,a3],152` | Fills static drawFont request 0x6246a74c -> osd_drawFont | docs/RE_DRAW_PLUGIN.md §2.3 |
| `0x60d12f60` | gpiUpdateDisplay | func | V | d0 0 = show cur, 1 = show cur^1; `[d2,a2],88` | Builds the present descriptor from 0x6246aaa8 and mask 0x61fb2954 -> osd_updateDisplay; then 0x60d139e4 posts GE event 0xa401 | docs/RE_DRAW_PLUGIN.md §2.4 |
| `0x60d13180` | GPISetOsdOrder | func | V | d0, d1 layer pair | -> osd_setOsdOrder | docs/RE_DRAW_PLUGIN.md §2.3 |
| `0x60d131db` | gpi_layer_mask_set | func | V | d0 mask, d1 present now | Stores 0x61fb2954; d1 != 0 -> gpiUpdateDisplay(1) | docs/RE_DRAW_PLUGIN.md §2.3 |
| `0x60d132e6` | gpi_palette_commit | func | V |  | "cw_setColorPalette (128Color Layer)"; run before every present | docs/RE_DRAW_PLUGIN.md §2.4 |
| `0x60d13a0b` | gpiSetDrawOffset | func | V | d0 x, d1 y | Stores 0x61fb2964/66; clear 0x60d13a33; get 0x60d13a52 (a0 &x, a1 &y) | docs/RE_DRAW_PLUGIN.md §2.3 |
| `0x60d15503` | gpi_platform_fn | func | V | d0 id (0xc..0x89) -> a0 fn | Platform function lookup (open hash 0x60f96578, 32 slots). Registered by 0x60d0eec0 into DAT_61fb2588.. (font metric 0x34, draw 0x8a, etc.) | docs/EXTRAS_OVERLAY.md |
| `0x60d1a6a0` | key_logical_map | func | V |  | Also 0x60d1a73e; logical key 10 -> 0x9016 | docs/LOOK_EDITOR.md |
| `0x60d3379b` | ge_current_window | func | V | -> a0 = *(0x61fb3138); retf | Set by 0x60d337a4 from the window ctor 0x60cff51e and 0x60cfd455. 893 callers | docs/PLUGINS.md §11 |
| `0x60d4c434` | label_widget_draw | func | V | widget draw method, frame [d2,d3,a2,a3]; gc (24,sp), rect (28,sp); ref 0x60faeeb4 | Stock text-label draw: 0x60d0fce0(gc, widget+128 text style), 0x60d0fd83(gc, 2), then inline text (widget+174 == 1) -> 0x60d075a7(style = widget+132); no gc colour call | docs/PLUGINS.md §11 |
| `0x60d4c9df` | text_setter | func | V | a0 widget, a1 wchar*; `[d2,d3,a2,a3],24` | Heap-copies any length | docs/CODE_SPACE_MAP.md, WORKLOG.md |
| `0x60d7f0a4` | firmware_view | func | C |  | Body value setter calls 0x60d7f271 (+940), 0x60d7f2cd (+300) | WORKLOG.md, docs/CODE_SPACE_MAP.md |
| `0x60dd4b47` | hsm_default_handler | func | V | -> 0 | Matrix default in every Ss: unmapped events are dropped | docs/RE_UI.md §2.1, §5 |
| `0x60dd4ba9` | gui_key_sink | func | V | vtbl[0] of the object at (0x61fc18c0); vtable 0x611401c4 | CA -> GUI key forwarder: send-key id -> GUI event, post. Registered in CA at 0x60cc7352 (0x60cfccc8: sub-object +32) | docs/PLUGINS.md §7 |
| `0x60dd5125` | open_request_set | func | V | d0 group, d1 key | Stores u16 0x61fc1bb0 / 0x61fc1bb2; getter 0x60dd5110 | docs/RE_UI.md §4.2 |
| `0x60dd5146` | act_create | func | V | kind -> actuator | Table 0x611401f4 (45 x {kind, create}); sends 0xf805 init | docs/RE_UI.md §3.2 |
| `0x60dd518e` | column_create | func | V | (column kind, ., &param) | Table 0x6114035c (12): 0 Cursor_Move_Set_Mode, 1 kind-4 class, 3/4 Cursor_Move, 5/6 Cursor_2CNL, 7 Plural_Direct, 8 AF_Target, 14 Direct | docs/RE_UI.md §3.2 |
| `0x60dd520c` | column_create_b | func | V | (kind, ., &param) | Table 0x611403dc (5); used by the main-menu actuator | docs/RE_UI.md §3.2 |
| `0x60dd5250` | act_event_base | func | V | vtbl[0] of every actuator: (event, lparam, act) | Hash 0x6114040c -> vtbl +44 Up, +48 Down, +52 Left, +56 Right, +60 0x9032, +64 0x9031, else +68; key grab 0x61fc1bac | docs/RE_UI.md §3.2 |
| `0x60dd5cd6` | af_target_setup | func | C |  | AF_Target_Actuator: four 6-entry lists 0x61140d98..; actuator 0x60dd5dfe (vtable 0x61140490) | docs/ASPECT.md |
| `0x60dda5cf` | cursor_2cnl_init | func | V | Cursor_2CNL_Actuator::Initialize | Copies 7 handler words from RAM 0x61fc1c00 (image 0x60259ec0), then per-kind init 0x6114569c (35) or default 0x60dda6a0 | docs/RE_UI.md §4.2 |
| `0x60ddad77` | cursor_2cnl_left | func | V | handler word +0x38 | Depth 2: close column 2 (rc 1); depth 1: rc 3 | docs/RE_UI.md §4.2 |
| `0x60ddaee9` | cursor_2cnl_right | func | V | handler word +0x3c | listB transition, else listA opens column 2 (depth 2) | docs/RE_UI.md §4.2 |
| `0x60ddb1c2` | cursor_2cnl_ok | func | V | via invidual_act_base 0x60ddb150 / table 0x6114d028 | listC transition, else OK to the column and rc 2 | docs/RE_UI.md §4.2 |
| `0x60ddc1f1` | cursor_2cnl_transition | func | V | (n, ., act, list) -> rc | Entry {u32 depth, u16 row, u16 sub, fn pre(a0 act), u16 group, u16 key, fn post(a0 act, a1 &group, d0 &key)}; open -> rc 4 | docs/RE_UI.md §4.2 |
| `0x60de3540` | CursorMove_Init | func | V | modeId | Cursor_Move_Set_Mode_Actuator: per-mode init table 0x61151474 (314 x 8 B {u16 mode, fn}); default 0x60de3670 (facade +24/+8/+28) | docs/LOOK_MENUS.md |
| `0x60de477b` | pm_list_builder | func | V |  | Picture-mode rows: 15272==1646 -> 8 rows 0x61152c80; else by sid 26 25 rows 0x61151f90 (string ref 0x60de47c0) | docs/LOOK_MENUS.md |
| `0x60dec4d4` | profile_view_new | func | V | a0 parent -> new 148 B view (0x60a4ec03), ctor 0x60dec4f4 [d2,d3,a2,a3],88 | Ctor stores vtable 0x61155e14 and registers listener 111 through 0x607f9062 -> +8 | docs/PLUGINS.md §10 |
| `0x60dec697` | profile_view_dtor | func | V | vtable +4; movm [a2,a3] prologue; a0 view | Restores vtable 0x61155e14, unregisters listener 111. v0.32 diag: word 0x61155e18 -> dg_dtor | docs/PLUGINS.md §10 |
| `0x60dec790` | colprof_view_update | func | V | a0 view; movm [d2,d3,a2,a3]; add -12; ... ret [d2,d3,a2,a3],28 | Rebuilds the view state (GUI data 175) via the facade; reads ALL state 0x61fc3804, picture mode 111, cursor settings 1091/1096/1097/1686 | docs/EXTRAS_OVERLAY.md |
| `0x60decabd` | sector_value_label | func | V |  | ID tables .data 0x61fc27e8/2818/2848/2878 | docs/LOOK_EDITOR.md |
| `0x60decbfc` | guide_label | func | C |  | Blanks ALL-off label when values hit both -5 and +5 | docs/LOOK_EDITOR.md, WORKLOG.md |
| `0x60df249e` | view_create | func | V | kind -> viewer | Table 0x6115c724 (126 x {kind, create}); vtbl[0] draw, [1] dtor | docs/RE_UI.md §3.3 |
| `0x60df250b` | label_by_value | func | C | d0 value, d1 count, a1 list, (4,sp) out | Builder A, 277 callers; miss leaves label untouched. Kind-4 point 0x60df255f (hook site) | docs/FIRMWARE_GUIDE.md §4 |
| `0x60df25b5` | label_from_src | func | C | label source | Builder B, 239 callers; kind-4 point 0x60df25dc (hook site) | docs/FIRMWARE_GUIDE.md §4 |
| `0x60df2618` | label_widen | func | V |  | byte -> UTF-16 into label+8 (kinds 5/6/12, <=32 chars) | docs/FILM_LIBRARY.md |
| `0x60df72e8` | grid_draw_lookup | func | V |  | Grid lists 0x611616ac/e8, 0x61161724/60, 0x61161b5c; miss = no draw | docs/ASPECT.md |
| `0x60df798a` | af_frame_geom | func | C |  | Also 0x60df7b55; six 6-entry lists 0x61162468..; miss draws nothing | docs/ASPECT.md |
| `0x60e0aad4` | menu_label_lookup | func | V |  | Also 0x60e0ab24; uses builder A | docs/LOOK_MENUS.md |
| `0x60e0f9e3` | Menu_Viewer_ctor | func | V | viewer kind 57 | Vtable 0x6117efc8; stores main_menu_root 0x6117b410 | docs/RE_UI.md §3.3, §4.1 |
| `0x60e20a54` | editor_init | func | V |  | Record +4; copies record +12..+52 to parent +48..+88 | docs/LOOK_EDITOR.md |
| `0x60e20cdc` | editor_router | func | C | event | Dispatches 0x9000-0x9fff/0xf8xx to parent words | docs/FIRMWARE_GUIDE.md §4 |
| `0x60e20e0a` | editor_up | func | V |  | Record +12 (step helpers 0x60e20bd5/0x60e20bfd) | docs/LOOK_EDITOR.md |
| `0x60e2107a` | editor_down | func | V |  | Record +16 | docs/LOOK_EDITOR.md |
| `0x60e21cae` | editor_dial | func | V |  | Once per notch, delta from 0x60ea3b35; sector/value 0x60e21efb | docs/LOOK_EDITOR.md |
| `0x60e22191` | editor_catchall | func | V |  | Record +36 | docs/LOOK_PICKER.md |
| `0x60e22579` | editor_info | func | C |  | Record +44, event 0x9014 | docs/LOOK_EDITOR.md |
| `0x60e230e0` | child_min_check | func | V |  | Bound helpers (min -5 / max +5 0x60e231e0), read via GetValue | docs/LOOK_EDITOR.md |
| `0x60e23b98` | lc_actuator | func | C |  | Live Control = screen group 20; INFO release via 0x60e2418b -> 0x60e22413; handler 0x60e593be | docs/MOVIE_COLOUR.md |
| `0x60e26ab0` | mono_profile_view | func | V |  | Preset label slot; view+400 = GetValue(111) at 0x60e26b33 | docs/MONO_PRESETS.md |
| `0x60e27639` | mono_view_page | func | V |  | Page from sid 1088; guide label view+186 | docs/MONO_PRESETS.md |
| `0x60e4ba62` | sscommon_fn_noop | func | V | clr d0; retf | SsCommon state 8 (StCaReqDisp, shooting) handler for 0x9057, handler word 57 of the ss-1 descriptor 0x611992c4, used by no other (event, state) | docs/PLUGINS.md §7 |
| `0x60e4c9a0` | IGui_Controler_ctor | func | V | (controller kind, args, obj 228 B) | Kind -> layout (0x6119a0b0 or RAM resolver 0x61fc4198+8k) -> 0x6119a100 {layout, act kind, view kind}; wrapper with alloc 0x60e4ce8b | docs/RE_UI.md §3.1 |
| `0x60e4cb5a` | screen_build | func | V | (key, 0, obj, desc words) | Fills the 228-B object from a 24-B descriptor; act_create + view_create | docs/RE_UI.md §3.1 |
| `0x60e4ce26` | screen_close | func | V | a0 screen | Frees binding; actuator vtbl +0x28, viewer vtbl +4. 61 callers | docs/RE_UI.md §3.1 |
| `0x60e4cea8` | screen_lookup_a | func | C |  | SCP/menu cells open editors (group 0x12); also 0x60e4cf21 | docs/AP_CUSTOM.md, docs/MONO_COLOUR.md |
| `0x60e4cf21` | screen_open_ex | func | V | (group, key, arg, arg) | As screen_lookup_a with args (build 0x60e4cc53, alt factory 0x60dd51cb) | docs/RE_UI.md §3.1 |
| `0x60e4d032` | screen_event | func | V | (event, lparam, screen) -> 0, 1 decide, 2 back, 3 open request | Pre-callback +28/+32, actuator vtbl[0]; rc 1 -> viewer vtbl[0] redraw (not touch 0xaf00-03); maps actuator rc 2/3/4 -> 1/2/3. 179 callers | docs/RE_UI.md §3.1, §5 |
| `0x60e4d16c` | screen_next | func | V | (&key, &type, screen) | Pending open request; type 0x20 when the screen has no actuator | docs/RE_UI.md §3.1 |
| `0x60e56973` | SsMenuLv_LC_entry | func | V | state 2 entry | screen_open(20, 0) -> 0x61fc432c | docs/RE_UI.md §6 |
| `0x60e56a7f` | SsMenuLv_DtlScp_ok | func | V | state 3 OK handler | Cell sid -> 0x61fc4370, CANEXEC, rc (4, 7) default | docs/RE_UI.md §6 |
| `0x60e56ea0` | SsMenuLv_SCP_entry | func | V | state 3 entry | IGui_Controler(10, 0x62472e44) -> 0x61fc4328 | docs/RE_UI.md §6 |
| `0x60e59198` | SsMenuLv_open_editor | func | V | () | screen_open(18, 0x61fc4370) -> 0x61fc4330, then event 0x9749 | docs/RE_UI.md §6 |
| `0x60e593be` | lc_pm_handler | func | V |  | Tests row 111 for 27/51/52/53,21,8,9,13,15,63; else 0x60e59713 (sid 281 cycle) | docs/MOVIE_COLOUR.md |
| `0x60e5db2e` | SsMenuMain_StWizardMenu_Entry | func | V | state 2 entry of ss 3 | Restores cursor from menu_history; wizard screen object 0x61fc5060 | docs/RE_UI.md §5.1 |
| `0x60e8af1c` | menu_value_column | func | V |  | Runtime-text cases by item id (Artist/Copyright, Lens Info) | docs/LOOK_MENUS.md |
| `0x60e9e771` | gui_transition_log | func | V | (event, old ss/state, new ss/state) | "Event 0x%04x: [%s][%s]-->[%s][%s]" | docs/RE_UI.md §2.1 |
| `0x60e9eb89` | gui_event_trace | func | V | (kind, code, arg) | Event trace ring entry, not a filter | docs/RE_UI.md §2.3 |
| `0x60ea15a3` | gui_timer_start | func | I | (id, ticks) | 76 callers; cancel 0x60ea15ca | docs/RE_UI.md §2.3 |
| `0x60eac6f2` | gui_load_language | func | V | d0 mode (0/1 load strings, 0 also res type 1) | Reads sid 3009 (facade +8 0xbc1), maps it through 0x60eac8a3 / 0x60eac851, loads font (type 0), strings (type 2) and type 1 via facade +0x34; strings "MODE_LANGUAGE", "loadLanguageData", "pFontsList" | docs/I18N_ZH.md |
| `0x60eac851` | lang_to_string_res | func | V | d0 language value -> (a3) u16 resource | Table 0x611f0c5c {u32 lang, u16 res}, -0x10000 end: 5 -> 2 (Simplified Chinese), 6 -> 3 (Traditional), 1 -> 8 (English) | docs/I18N_ZH.md |
| `0x60eac8a3` | lang_to_font_res | func | V | d0 language value, d1 1 -> u16 resource | Table 0x611f0d7c {u32 lang, u16 1, u16 res}: font = string res + 34 (5 -> 36, 6 -> 37) | docs/I18N_ZH.md |
| `0x60f389a8` | btn_key_table | table | C | keycode -> sid | Keycodes 0x1c/0x1d/0x1e -> button sids; arrows sids 50 up, 51 down, 52 left, 53 right | docs/BUTTONS.md |
| `0x60f38af8` | btn_func_table | table | C | 55 entries | Function code -> action | docs/BUTTONS.md |
| `0x60f38d8c` | multi_function_actions | table | V | 9 x {u32 sub-function, u32 action} | 1->48, 3->50, 5->42, 6->49, 2->23, 8->43, 7->44, 9->88, 10->30 | docs/PLUGINS.md §12 |
| `0x60f3928c` | sendkey_event_table | table | V | +16: 8 UP, 0xb DOWN, 0xe LEFT, 0x11 RIGHT | Names 0x60f77cb4.. | docs/BUTTONS.md §4d |
| `0x60f3928c` | ca_key_events | table | V | 142 x 20 B {u32 ca event, u32 keycode, u32 sub (0 press, 1 release, 2/3), u32 mask, u32 send-key id} | Read by 0x60cc9790 (event -> keycode). Fn (keycode 15): 0x0100002e press / 0x0100002f release, send-key 0x57 / 0x58 | docs/PLUGINS.md §7 |
| `0x60f4d230` | select_action_state | table | V | 25 x {u32 action, u32 CA state} | Read by 0x60ceb5b6; 49 and 50 -> 0x5800 | docs/PLUGINS.md §12 |
| `0x60f9477c` | ge_window_vtable | table | V | >= 712 B vtable | Base window class, stored by ctor 0x60cff51e (one caller, 0x60d43e80). +164 at 0x60f94820 | docs/PLUGINS.md §10 |
| `0x60f94820` | win_vtbl_a_164 | data | V | u32 = 0x60cfe263 | Window class A vtable +164 (base 0x60f9477c). overlay_probe -> ov_post | docs/EXTRAS_OVERLAY.md |
| `0x60f95f10` | gpi_layer_plane | table | V | u8[3] = {1, 2, 0} | GUI layer -> OSD API plane | docs/RE_DRAW_PLUGIN.md §2.3 |
| `0x60f95f2c` | gpi_layer_bpp | table | V | u8[3] = {4, 8, 4} | Stride = 800*bpp/8 (DC+148) | docs/RE_DRAW_PLUGIN.md §2.3 |
| `0x60fac34c` | ge_window_sub_vtable | table | V | >= 712 B vtable | Subclass, ctor 0x60d43e80, made only at 0x60d39f41. +164 at 0x60fac3f0 | docs/PLUGINS.md §10 |
| `0x60fac3f0` | win_vtbl_b_164 | data | V | u32 = 0x60cfe263 | Window class B vtable +164 (base 0x60fac34c). overlay_probe -> ov_post | docs/EXTRAS_OVERLAY.md |
| `0x610a3c38` | scp_aspect_cell | struct | C | +0x34 u8 2, u8 count; +0x38 parts; +0x3c u16[count] | SCP current-value widget; parts 0x610a0798 {0xffff,7,7,bitmap} | docs/ASPECT.md |
| `0x611317c4` | hsm_ss_table | table | V | 19 x u32 descriptor*, index ss-1 | Descriptor 32 B: +0 u8 n_states, +2 u16 n_events, +4 u16 n_handlers, +6 s16 n_map, +8 matrix, +0xc handlers, +0x10 event map {code, index}, +0x14 entry[], +0x18 exit[], +0x1c u8 wide | docs/RE_UI.md §2.1 |
| `0x6113e938` | gui_key_table | table | V |  | GUI key codes (HFW order). Events: 0x9004/6 step, 0x9008/a sector, 0x900c commit, 0x900e MENU, 0x9010 PLAY, 0x9012 Movie, 0x9014 INFO, 0x9016 Del, 0x903e held OK | docs/LOOK_EDITOR.md, docs/FIRMWARE_GUIDE.md §4 |
| `0x6113e938` | gui_sendkey_map | table | V | {u32 send-key id, u32 GUI event} | Send-key id n -> GUI event 0x90nn for the Fn range (0x57 -> 0x9057, 0x58 -> 0x9058); 0x7fff = none. Read by 0x60dd4ba9 | docs/PLUGINS.md §7 |
| `0x611401f4` | act_factory_table | table | V | 45 x {u32 kind, fn create} | e.g. 5 Cursor_Move_Set_Mode, 21 Cursor_2CNL, 24 main menu, 26 Plural_Direct, 27 Plural_Lv_Control, 8/9 Func_Scp | docs/RE_UI.md §3.2 |
| `0x6114040c` | act_key_slot_table | table | V | 16 x {u32 event-0x9003, stub} |  | docs/RE_UI.md §3.2 |
| `0x6114b2e0` | cursor_2cnl_kind_table | table | V | 156 x 36 B {kind, column kind, column mode, listA, nA, listB, nB, listC, nC} | Bound 0x9c hard-coded (0x60dda6a0, 0x60dda760). listA 12 B inline column; listB (Right) / listC (OK) 24 B transitions | docs/RE_UI.md §4.2 |
| `0x6114d1a8` | cursor_2cnl_vtable | table | V | Cursor_2CNL_Actuator (0x88 B) | +0x30..+0x48 handler words, +0x4c kind, +0x50 depth, +0x58/+0x5c columns, +0x60.. lists A/B/C. Create 0x60dda3fd, ctor 0x60dda522/0x60dda561 | docs/RE_UI.md §4.2 |
| `0x61150328` | cursor_move_mode_lists | table | V | 150 x 12 B {u32 mode, u32 u16-list, u16 n} | Default rows (0x60de21b0); bound 0x96 | docs/RE_UI.md §4.3 |
| `0x61150568` | btnfn_rows | struct | C | {42, 0x611500f2, 2} = [47, 48] | Button Function rows (Cursor_Move mode 42) | docs/BUTTONS.md |
| `0x61150af4` | menu_tab_row_lists | table | V | 7 x {u16 mode 80..86, u16 n, ptr -> {u16 key, u16 n, u32 list}} | Key-0 record used (0x60de2628). Setup tab record 0x61150aec -> 0x61150aa6 (7) | docs/RE_UI.md §4.3, §8.1 |
| `0x61150bb4` | custom_menu_row_lists | table | V | 15 x {u16 mode 87..116, u16 n, ptr} | Lists in RAM .data (0x61fc1dcc..); init 0x60de276f | docs/RE_UI.md §4.3 |
| `0x61150c2c` | column_init_table | table | V | {u16 mode, fn} | Custom Menu columns: modes 87..116 -> 0x60de276f -> lists 0x61150bb4 | docs/MIN_SHUTTER.md |
| `0x61150d74` | menu_row_remap | table | V | {u16 id, fn} until 3200 | 10 -> 0x60de2e70, 111 -> 0x60de2e9b | docs/RE_UI.md §4.3 |
| `0x61150e0c` | cursor_move_col_vtable | table | V | Cursor_Move column (0x5c B) | +0x40 mode, +0x48 n, +0x4a first enabled, +0x4c grey flags, +0x50 ids, +0x54/+0x56 first/last enabled; init 0x60de2134 | docs/RE_UI.md §4.3 |
| `0x61155a7c` | prop_child_vtable | table | V | 144 B child: +84 sid, +88 count, +90 cur idx, +96 codes, +100 list |  | docs/FIRMWARE_GUIDE.md §4 |
| `0x61155e14` | profile_view_vtable | table | V |  | Color Profile view; update 0x60dec790 rebuilds 96-B state | docs/LOOK_EDITOR.md |
| `0x61155e14` | colprof_view_vtbl | data | V | Colour Profile editor view vtable; +0 update 0x60dec790, +4 0x60dec697 | overlay_probe re-points +0 (update) to ov_upd, which sets the overlay flag each time the editor paints | docs/EXTRAS_OVERLAY.md |
| `0x61159f08` | scp_cell_table | table | V | 39 x 14 B {u16 sid, 6 x u16} | Copied by Func_Scp_Actuator::initActModeDetail 0x60df1429 to actuator +0x5c; per-mode swaps in 0x60df149c | docs/RE_UI.md §6 |
| `0x6115ba70` | func_scp_vtable | table | V | Func_Scp_Actuator (actuator kinds 8/9) |  | docs/RE_UI.md §3.2, §6 |
| `0x6116ae1c` | item_table | table | C | 74 rows x 52 B | Row 16 = aspect at 0x6116b190 | docs/ASPECT.md |
| `0x61177140` | lv_control_select | table | C | {0, 30, 0x61176e70}: 30 x 24 B | SCP/LC option strips; aspect record 0x61176fc0 {270,5,A,B} | docs/ASPECT.md |
| `0x611794a8` | menu_tab_2cnl_table | table | V | 7 x {u16 tab, u32 2CNL kind} | Tabs 0..6 -> 2CNL 62..68; loop bound 7 in 0x60e0f2cb | docs/RE_UI.md §4.1 |
| `0x61179560` | menu_main_act_vtable | table | V | actuator kind 24 (68 B): +0x34 tab column, +0x38 2CNL of the tab, +0x3e focus | Create 0x60e0e7b4; tab -> 2CNL kind table 0x611794a8; per-tab 2CNL built at 0x60e0f2cb | docs/RE_UI.md §4.1 |
| `0x6117af14` | menu_desc_aspect | struct | C | {270, 6, 0x6117a834} | Image Aspect option list (12-B {u32 value, u16 type, u16 string, u32 cond}) | docs/ASPECT.md |
| `0x6117b1ec` | menu_page_video | struct | V |  | Video page: 13 items, desc 652 -> 0x6117aa98 | docs/LOOK_MENUS.md |
| `0x6117b410` | main_menu_root | table | V | 7 tabs | Read by 0x60e0fa45; page array 0x6117b1b4 of 28-B pages {u16 tab, u16 n, items, helps, ndesc, desc[], n2, x}; item 12 B {u32 sid, label src}; desc 8 B {u16 id, u16 count, list} | docs/LOOK_MENUS.md |
| `0x61185bdc` | editor_rec_color1 | struct | C | 56 B: +0 key, +4 init, +8 child_get, +12 Up, +16 Down, +20 Left, +24 Right, +28/+32 dial, +36 catch-all, +40, +44 INFO, +48/+52 0 | COLOR1 (0x13b3). COLOR2 0x61185c14, COLOR3 0x61185c4c, COLOR4 0x61185c84, CC 0x13a9 at 0x61185ba4. Docs quoting 0x61185be8.. give the +12 word | docs/LOOK_EDITOR.md §1 (base corrected here) |
| `0x61186ba4` | editor_desc_table | table | V | 47 x {u16 key, u16 n, u32 child list} | COLOR1-4 keys 0x13b3/0x13b4/0x13b5/0x140c | docs/FIRMWARE_GUIDE.md §4 |
| `0x61187534` | editor_parent_vtable | table | V |  | Ctor 0x60e20691/0x60e206a9. Parent: +100 key, +120 child count, +122 cursor, +124 child[] | docs/LOOK_EDITOR.md |
| `0x6118c818` | lv_grid_value_lists | table | V | 18 x 5 x {u32 value, u32 bitmap}, 40 B each | Values 8 diagonal, 6 golden, 5 grid, 7 cross, 1 thirds; bitmaps 5996-6126, index 124, 2-px lines (6018: 708x399 thirds) | docs/SPLIT_TONE_G1.md §2 |
| `0x6118c8e0` | lv_grid_list_179 | table | V | 5 x {value, bitmap}: 6001 6007 6766 6015 6021 | Aspect-10 (17:9) lists of the three classes: 0x6118c8e0 / c9d0 / cb10. 6001/6007/6087/6099/6105/6031 are referenced in main only by these lists | docs/SPLIT_TONE_G1.md §2 |
| `0x6118cc00` | lv_grid_aspect_table_a | table | V | 6 x {u32 aspect, u32 list, u32 count}; aspects 1,2,3,4,9,10 | LV grid selector 0x60e32406 (count `mov 6,a0` at 0x60e326c3). Siblings 0x6118cc48 (state (1020,this) == 1), 0x6118cc90. Row 5 (aspect 10, 17:9) is dead in this function: aspect is 1/3 in movie or GetValue(270), never 10 | docs/SPLIT_TONE_G1.md §2 |
| `0x611992c4` | ss_SsCommon | struct | V | HSM descriptor, 14 states, 89 events | ss 1 | docs/RE_UI.md §2.2 |
| `0x6119a0b0` | screen_ctrl_kind_table | table | V | {u32 controller kind, u32 layout} until kind 0x20 | 10 -> 13 (SCP), 11 -> 14 | docs/RE_UI.md §3.1 |
| `0x6119a100` | screen_layout_table | table | V | 45 x 12 B {layout, actuator kind, viewer kind} | Layout 13 = SCP (act 8, view 15), 14 = RC SCP (act 9, view 16) | docs/RE_UI.md §3.1 |
| `0x6119a31c` | screen_list_g8 | table | V | 429 x 24 B | Popups (value pickers act 5 + view 25/30/56/122, ...) | docs/RE_UI.md §3.1 |
| `0x6119cb54` | screen_list_g14 | table | V | 132 x 24 B | Menu sub-pages: act 21 (Cursor_2CNL) param = 2CNL kind, view param = item-info key | docs/RE_UI.md §3.1 |
| `0x6119d7b4` | screen_list_g15 | table | V | 3 x 24 B | Key 0 main menu (act 24 / view 57), keys 1-2 Custom Menu (act 25 / view 58) | docs/RE_UI.md §3.1 |
| `0x6119dafc` | screen_list_g18 | table | V | 257 x 24 B, key = sid | Setting editors (act 26 Plural_Direct), opened by SsMenuLv state 7 | docs/RE_UI.md §3.1, §6 |
| `0x6119fadc` | screen_group_table | table | V | 13 x 12 B {u32 group, u32 list, u16 n} | Groups 8 (429 popups), 14 (132 2CNL pages, n at 0x6119faf0), 15 (menus), 18 (257 editors by sid), 20 LC, 21, 3, 16, 17, 26-29. Descriptor 24 B {key, act kind, act param, view kind, view param, hook} | docs/RE_UI.md §3.1 |
| `0x611a1f48` | ss_SsEdit | struct | V | HSM descriptor, 9 states | ss 18 | docs/RE_UI.md §2.2 |
| `0x611a22ac` | ss_SsMenu | struct | V | HSM descriptor, 3 states, 66 events | ss 17 (MENU key entry) | docs/RE_UI.md §2.2 |
| `0x611a3bc8` | ss_SsMenuLv | struct | V | HSM descriptor, 29 states, 112 events, 138 handlers | ss 4; state 2 Live Control, 3 SCP, 7 setting screen. Matrix 0x611a2e30, handlers 0x611a2c08, map 0x611a2888, entry 0x611a3ae0, exit 0x611a3b54 | docs/RE_UI.md §2.2, §6 |
| `0x611a6410` | ss_SsMenuMain | struct | V | HSM descriptor, 13 states, 77 events | ss 3; state 2 StWizardMenu (entry 0x60e5db2e) | docs/RE_UI.md §2.2 |
| `0x611a82f4` | ss_SsPlayIndex | struct | V | HSM descriptor, 18 states | ss 8 | docs/RE_UI.md §2.2 |
| `0x611a9d44` | ss_SsPlayMovieSlide | struct | V | HSM descriptor, 30 states | ss 7 | docs/RE_UI.md §2.2 |
| `0x611abc5c` | ss_SsPlaySingle | struct | V | HSM descriptor, 43 states | ss 6 | docs/RE_UI.md §2.2 |
| `0x611ada58` | ss_SsRec | struct | V | HSM descriptor, 5 states, 47 events | ss 2 | docs/RE_UI.md §2.2 |
| `0x611c2c78` | item_info_index | table | V | 129 x 24 B {key = viewer param, records, n, 0, ., .} | Read by the 2CNL viewer at 0x60e89a28 (bound 129). Record 36 B {id, title label, value list, n, 0, text, popup list, n}. Second tree 0x611cce58.. | docs/RE_UI.md §4.4 |
| `0x611f0c5c` | lang_string_res_tab | table | V | 34 x {u32 lang, u16 res, u16 pad} | Language value (sid 3009) -> OSD string resource 1..34 | docs/I18N_ZH.md |
| `0x611f0d7c` | lang_font_res_tab | table | V | 34 x {u32 lang, u16 1, u16 res} | Language value -> OSD font resource 35..68 | docs/I18N_ZH.md |
| `0x61fb0dd8` | sel_replay_key | data | V | u32 key to replay after the select state exits (+4 0x61fb0ddc last key) | Written by the select-state key handlers and keyhook ka_rep | docs/PLUGINS.md §12 |
| `0x61fb2938` | gpi_cur_buf | data | V | u8 0/1 | Current back-buffer index; toggled by present | docs/RE_DRAW_PLUGIN.md §2.3 |
| `0x61fb2939` | gpi_dirty | data | V | u8 | Set by sync rect, cleared by present | docs/RE_DRAW_PLUGIN.md §2.3 |
| `0x61fb2954` | gpi_layer_off_mask | data | V | u16: 0x02 layer 0, 0x10 layer 1, 0x100 layer 2 | Planes hidden at present | docs/RE_DRAW_PLUGIN.md §2.3 |
| `0x61fb3138` | ge_current_window_ptr | data | V | u32 window* | Current (last constructed) window | docs/PLUGINS.md §11 |
| `0x61fc1530` | osd_string_tables | data | V | u32[bank] -> u32 string pointer table | Bank 0 = *res (p0 of the loaded string resource), written by 0x60eac6f2 | docs/I18N_ZH.md |
| `0x61fc15bc` | osd_style_tables | data | V | u32[bank] | Bank 0 = res[1] of the loaded string resource (text styles / pFontsList) | docs/I18N_ZH.md |
| `0x61fc1c00` | cursor_2cnl_handlers | data | V | 7 words: Up, Down, Left, Right, dial, dial, other | RAM .data, image 0x60259ec0: 0x60ddab47, 0x60ddac5f, 0x60ddad77, 0x60ddaee9, 0x60ddb06d, 0x60ddb0de, 0x60ddb14e. Data-hookable | docs/RE_UI.md §4.2 |
| `0x61fc27d0` | profile_view_parts | table | C | .data, init image 0x6025aa90 | Part 3 guide label: init word 0x6025aa98 (stock 0x60decbfc) | docs/LOOK_EDITOR.md, docs/MIN_SHUTTER.md |
| `0x61fc4328` | scp_screen | data | V | IGui_Controler* | SCP screen; LC 0x61fc432c; group-18 editor 0x61fc4330; open key 0x61fc4370 | docs/RE_UI.md §5, §6 |
| `0x61fc4ffc` | menu_history | data | V | 10 x 6 B {u16 item, u8 cursor, ., u16 x}; depth u8 0x61fc5038 | Push 0x60ea7dcc, pop 0x60ea7d42, drop 0x60ea7da4, peek 0x60ea7c89 | docs/RE_UI.md §5.1 |
| `0x6203bcb2` | kh_fn_stage | data | V | u8 Fn stage byte (.bss pad) | bits 0-1 site + 1, bits 2-3 plugin decision (0 not called, 1 stock, 2 handled), bits 4-7 Fn presses mod 16; diag readout K | docs/PLUGINS.md §12 |
| `0x622ab792` | ov_flag | data | V | .bss u8 (uncached 0xa22ab792) | overlay_probe: set by ov_upd, cleared by ov_post each frame (self-clear on editor close) | docs/EXTRAS_OVERLAY.md |
| `0x622ab793` | ov_counter | data | V | .bss u8 (uncached 0xa22ab793) | overlay_probe: ghosting counter, incremented each draw, shown as 2 hex digits in row D | docs/EXTRAS_OVERLAY.md |
| `0x6246684c` | hsm_ctx | data | V | 32 B: +0 u8 ss, +1 u8 state, +2 u8 n_ss, +4 ss table, +8 u16 cur handler | Pointer stored in 0x61fb2564 by gui_WinMain | docs/RE_UI.md §2.1 |
| `0x62466870` | gui_msg_queue | data | V | 500 x 32 B {u8 used, msg 7 words}; head/tail u16 0x6246a6f0/0x6246a6f2 | Get 0x60d10133 (0x1002/0x1100 first), purge-by-code 0x60d1050a | docs/RE_UI.md §2.3 |
| `0x6246a774` | gpi_dc_layers | struct | V | 3 x 164 B: +0 layer, +2 800, +4 600, +6 bpp, +72 layer desc, +76 fn table (18 words), +148 stride | Also DC -1 0x6246a960, DC -2 0x6246aa04 | docs/RE_DRAW_PLUGIN.md §2.3 |
| `0x6246aaa8` | gpi_vram_tab | table | V | VRAM_INFO* [3 layers][2 buffers] | Back buffer of layer L = [L][(u8)0x61fb2938] | docs/RE_DRAW_PLUGIN.md §2.3 |
| `0x6246aac0` | gpi_vram_work | data | V | VRAM_INFO* | Plane 3 (WORK) | docs/RE_DRAW_PLUGIN.md §2.3 |
| `0xa400bac0` | zh_font_cmap | data | I | u32[256] page dir -> {u16 w, u16 h, u32 glyph}[256] | Font res 36 +0x54580: 636 CJK glyphs (37 px). Second dir +0x54980: 133 Latin / full-width (40 px). tools/zh_glyphs.py. Runtime address via the inferred font base 0xa3fb7540; the structure is verified in flash | docs/I18N_ZH.md |

## 5. OSD component

Component 0x101, loaded from flash with no CRC. Bitmap descriptor `u16 fmt, u16 w, u16 h, u16 field6, 0, 0, u32 enc
size, u32 payload`; RLE modes 11 (8-bit index, 4-bit run), 10, 1, 9 (glyphs). Strings UTF-16LE, edit in place at the same
length. Detail: [OSD.md](OSD.md), [FIRMWARE_GUIDE.md](FIRMWARE_GUIDE.md) §5, `tools/osd_extract.py`.

| Address | Name | Kind | Tag | Signature / layout | Notes | Source |
|---|---|---|---|---|---|---|
| `0x6015ad92` | osd_bank_loader | func | V |  | Resource 0 -> 0xa3091000 else 0xa3611000; copy 0x6015b7bb, no CRC | docs/OSD.md |
| `0x6023ff38` | osdcontrol_api_names | table | V | u32 char* [n]; id = 0x11100 + index + 1 | .data image: OSDControl::initOsdControl .. drawTrapezoid; trace ids passed by every API function (drawDot 0x11106) | docs/RE_DRAW_PLUGIN.md §2.1 |
| `0x60799a99` | osd_init | func | V | () | OSDControl::initOsdControl (0x11101); caller GPIInitPlatform 0x60d115d4 | docs/RE_DRAW_PLUGIN.md §2.2 |
| `0x60799d3c` | osd_copyAreaBlock | func | V | a0 request | 0x1110c; callers gpiDrawOsdBlockCopy 0x60d12adf, 0x60ea9bba | docs/RE_DRAW_PLUGIN.md §2.2 |
| `0x60799e64` | osd_copyFrame | func | V | a0 src VRAM_INFO*, a1 dst | 0x1110b; caller 0x60d135cf | docs/RE_DRAW_PLUGIN.md §2.2 |
| `0x60799f3f` | osd_drawBitmap | func | V | a0 request | 0x1110a; callers gpiDrawBitmap 0x60d12c4b, 0x60ea9b4d | docs/RE_DRAW_PLUGIN.md §2.2 |
| `0x6079a01f` | osd_drawDot | func | V | a0 request; `[d2,d3,a2],52` | 0x11106. Request +0 VRAM_INFO*, +4 plane kind, +8/+10 x/y, +14 colour index -> renderer 0x60baf798 | docs/RE_DRAW_PLUGIN.md §2.2 |
| `0x6079a0e6` | osd_drawFont | func | V | a0 request; `[d2,d3,a2,a3],68` | 0x11109. +8/+10 x/y, +12/+14 w/h, +24..27 four colour indices (2-bit glyph levels), +28 glyph ptr -> 0x60bb0256 | docs/RE_DRAW_PLUGIN.md §2.2 |
| `0x6079a1e0` | osd_drawLine | func | V | a0 request; `[d2,d3,a2],56` | 0x11107 -> renderer 0x60baf88a | docs/RE_DRAW_PLUGIN.md §2.2 |
| `0x6079a2b3` | osd_drawRect | func | V | a0 request; `[d2,d3,a2],60` | 0x11108. Request +0 VRAM_INFO*, +4 plane kind, +8/+10 x/y, +12/+14 w/h, +16 u16 (unknown), +20 colour index, +24 fill -> 0x60baf99e | docs/RE_DRAW_PLUGIN.md §2.2 |
| `0x6079a395` | osd_freeVramInfo | func | V | a0 VRAM_INFO* | 0x11114; caller gpi deinit 0x60d118fd | docs/RE_DRAW_PLUGIN.md §2.2 |
| `0x6079a432` | osd_getVramInfo | func | V | d0 plane 0..5 -> a0 VRAM_INFO* or 0; `[d2,d3,a2],16` | 0x11113. Planes: 0 LAYER1, 1 LAYER2, 2 LAYER3, 3 WORK, 4 image normal, 5 image wide. VRAM_INFO {+0 pData, +4 s8 plane, +8/+10 w/h, +12/+14 start, +16/+18 new w/h, +20/+22 new start} | docs/RE_DRAW_PLUGIN.md §2.2 |
| `0x6079a565` | osd_setColorPalette | func | V |  | 0x11110; callers GPIInitPlatform, palette commit 0x60d132e6, SetBlackScreen 0x60ea28d7. Source block not traced | docs/RE_DRAW_PLUGIN.md §2.2 |
| `0x6079a60d` | osd_setTransparent | func | I |  | Role from position/callers (same callers as setColorPalette) | docs/RE_DRAW_PLUGIN.md §2.2 |
| `0x6079a69d` | osd_updateDisplay | func | V | a0 present descriptor; `[d2,d3,a2,a3],184` | 0x1110e; three plane VRAM pointers (0 = plane off). Callers gpiUpdateDisplay 0x60d12f60, 0x60d130e1 | docs/RE_DRAW_PLUGIN.md §2.2 |
| `0x6079b068` | osd_customDisplay | func | V |  | 0x1110d; callers 0x60d13679, 0x60d1bb8f | docs/RE_DRAW_PLUGIN.md §2.2 |
| `0x6079bad5` | osd_drawOsdStart | func | V | (); `[],4` | 0x11102. Sets bracket flag 0x61fa90d4; nested call only logs "called twice"; renderer begin 0x60bb077e | docs/RE_DRAW_PLUGIN.md §2.2 |
| `0x6079bb4a` | osd_drawOsdEnd | func | V | (); `[],4` | 0x11103. Renderer flush 0x60bb079a; clears 0x61fa90d4 | docs/RE_DRAW_PLUGIN.md §2.2 |
| `0x6079bbbe` | osd_setOsdOrder | func | V | d0 top, d1 middle, a0 bottom | 0x11104; caller GPISetOsdOrder 0x60d13180 | docs/RE_DRAW_PLUGIN.md §2.2 |
| `0x607dd584` | sdk_api_osd_cmds | func | V | shell handlers | Debug shell "sdk api" commands calling init/drawOsdStart/End/drawDot/Rect/getVramInfo with plane numbers (0x607dd584-0x607de2e8) | docs/RE_DRAW_PLUGIN.md §2.1 |
| `0x60baf798` | osd_render_dot | func | V |  | Renderer: mallocs a 108-B command (0x60022700) and queues it via 0x60babdda; others 0x60baf88a line, 0x60baf99e rect, 0x60bb0256 font | docs/RE_DRAW_PLUGIN.md §2.1 |
| `0x60bb079a` | osd_render_flush | func | V |  | Renderer batch flush at drawOsdEnd; begin 0x60bb077e | docs/RE_DRAW_PLUGIN.md §2.2 |
| `0x60d10ba1` | osd_bitmap_get | func | V | id -> &table[id] (0 -> NULL) | No bounds check | docs/FIRMWARE_GUIDE.md §5 |
| `0x60eac846` | osd_bitmap_table_init | func | V |  | Stores bank-0 header +16 in 0x61fc1734 | docs/ASPECT.md |
| `0x61110a74` | palettes | table | I | 58 ARGB blocks to 0x6111f03c | Candidates 0x61110e7c (8-bit), 0x6111570c (4-bit); runtime choice unknown | docs/OSD.md |
| `0x61fa90c8` | osd_trace_level | data | V | u32 | API trace gate tested at every OSDControl entry | docs/RE_DRAW_PLUGIN.md §2.2 |
| `0x61fa90d4` | osd_bracket_open | data | V | u32 (1 open) | drawOsdStart/End batch flag | docs/RE_DRAW_PLUGIN.md §2.2 |
| `0xa3091000` | osd_bank0 | data | V | header +0 symbols, +16 bitmap table | Resource 0 runtime base (7576 descriptors, 245 @A0xx@ symbols) | docs/OSD.md, docs/FIRMWARE_GUIDE.md §5 |
| `0xa3611000` | osd_bank69 | data | V |  | Second bitmap bank (resource 69), copy bounded 0xf26140 | docs/OSD.md |
| `0xa3fb7540` | osd_fonts | data | I |  | Resources 35-68 | docs/OSD.md |
| `0xa407f540` | osd_strings | data | V |  | Language string tables (1-34), 3645 UTF-16LE each; English = resource 8 | docs/FIRMWARE_GUIDE.md §5 |

## 6. Live view and display

Live view and movie share the still pipeline (same constructor, stage list, selector and tables); the difference is the
input record R and that LV jobs never pass a converter (their readers use property 0xF6B1). LV job key is fixed at job
build; parameter updates reuse the job.

| Record | Fields |
|---|---|
| LV/movie record R | +292.. from message A+352; **+294 picture mode**, +295 art sub, +296 Art Effect id; +660 Rec View; +902 class input; **+925 hidden gamma (1 Flat, 2 log)**; +2117/2118; **+2119..2130 S ×12** → params+5538 |
| Settings message A | +20 = 0xF6B1 profile (0 zeroes R+2119); +352..; +354 picture mode |

| Address | Name | Kind | Tag | Signature / layout | Notes | Source |
|---|---|---|---|---|---|---|
| `0x601744df` | DISPLAY | func | V | task 58, prio 26 | Command dispatch 0x60174667 -> 0x601d3a20; reply tail 0x601751f4; QUALITY 0x60174bdb | docs/LOG_VIEW_ASSIST.md |
| `0x60174d19` | colortemp_evf | func | I |  | EVF gamma programmer only for EVF device (dead on E-P7); step table 0x601e3b3c | docs/FIRMWARE_GUIDE.md §2 |
| `0x60187439` | disp_rgb_lut_load | func | V |  | Display-controller RGB LUT (regs 0x9c002000/0x9c000204) | docs/LOG_VIEW_ASSIST.md |
| `0x601d3a20` | display_cmd_jtab | table | V | jump table (id-2) | Display task command dispatch from 0x60174667; names table 0x601798d1 (1 FASTBOOT..8 QUALITY..22 COLORTEMP) | docs/LOG_VIEW_ASSIST.md |
| `0x601e3b3c` | evf_gamma_steptab | table | V | 2 dev x 20 x {u8 step, R*, G*, B*} | Tables 0x601de13c-0x601e3b3c reused by Caduceus (CODE_SPACE_MAP) | docs/CODE_SPACE_MAP.md |
| `0x6029413f` | through_update_req | func | V | calls; add -4,sp / ret [],4 | Gate (0x62236dbd) != 0 -> 0x60296ec8. Ops-struct slot (word 0x6054cb98, built at 0x6054cb48..); indirect caller unknown. Candidate LV refresh trigger L1 | docs/RE_LIVEVIEW.md §1, §5 |
| `0x60296ec8` | through_update_post | func | V | `call ..,[],12` | Enqueue {1,0} on (0x6223cbbc) and set TAKE_MOV flag (0x60040c2e) bit 1. Only caller 0x6029413f | docs/RE_LIVEVIEW.md §1 |
| `0x602e82a8` | aspect_eff | func | V |  | Movie: 1/10/3 from resolution if sid 44==1; else sid 270 clamped | docs/ASPECT.md |
| `0x60303ad3` | through_update | func | V | a0 msg | "TH" tag. 0x6030ddc7()==2 -> 0x60327b93, else 0x60327b3c. Callers 0x6055439b (TAKE_MOV), 0x60303e2e | docs/RE_LIVEVIEW.md §2 |
| `0x6030bb2d` | lv_wb_fill | func | V |  | Compact WB fill (prop_get at 0x6030bb5b/6e, key 0x84f9..); from 0x6030ba2b on every event 7 | docs/RE_LIVEVIEW.md §2 |
| `0x6030bb5b` | lv_wb_read | func | C |  | Compact-record WB reads (also 0x6030bb6e) | docs/WB_PATCH.md |
| `0x60311440` | lv_job_delete | func | V |  | Called by act 0x6032a706 at 0x6032a7df before rebuild 0x603114e0 | docs/RE_LIVEVIEW.md §2 |
| `0x603118d6` | lv_key_fixed | func | V |  | Job key fixed at build; param update does not change it | docs/LV_ART_PREVIEW.md |
| `0x60312f42` | lv_art_bits | func | V |  | Art Effect bits only for pm >= 100; record +292..+296 (+294 pm, +295 sub, +296 effect) | docs/LV_ART_PREVIEW.md |
| `0x6031c883` | recview_post | func | V | kind | Posts to Rec View mailbox (send 0x6031ca88/0x6031d8d0); gate 0x6031d189 | docs/ISSUES_19_20.md |
| `0x6031da00` | mvr_flag_post_deferred | func | V | a0 req {u16 flag, u32 bits, u32 delay, u8 mode} | Bits 1 -> setter 0x6031daaa, 2/0x400 -> 0x6031dafa, 0x4000 -> 0x6031db4b; armed via 0x6005633f (alarm/timer [I]). Stock: delay 0, mode 2 | docs/RE_LIVEVIEW.md §1 |
| `0x60321d36` | ipcr_dev_handler | func | C |  | LV/movie job: calls ctor at 0x60321ea8 (only one; ret 0x60321eaf); params 0x60321d97-0x60321e52 (key params+8, type params+16) | docs/LV_BUNDLES.md, docs/MOVIE_COLOUR.md |
| `0x60321f75` | lv_new_params | func | V |  | New params on existing job (reads job+4 incl. flags); no ctor/work list | docs/LV_ART_PREVIEW.md |
| `0x603220e5` | lv_params_from_R | func | V |  | -> 0x60324071 (at 0x60322155): R+2119..2130 -> params+5538.. (12 S) | docs/LV_BUNDLES.md |
| `0x6032560b` | mvr_service_loop | func | V | d0 mailbox id, a0 ctx | Receive 0x6031d88c, then handler slot from 0x604e2f64 by mailbox (0x2001/2 -> 0, 0x200a/c/f -> 1, 0x2003/4 -> 2, 0x200b -> 3, 0x200e -> 4, 0x2010 -> 5, 0x2011 -> 6) | docs/RE_LIVEVIEW.md §1 |
| `0x60327b3c` | through_record_post | func | V | a0 msg, a1 0x62039f24 | 0x60308de5, 0x6030b3b9, 0x60309805(rec,0) record build, then 0x6031da00 {flag 0x60041076, bits 1, delay 0, mode 2} -> event 7 | docs/RE_LIVEVIEW.md §2 |
| `0x60327cfd` | MVR_IMG | func | V | CPU2 tasks 0x2005/0x2007/0x200a entry, prio 25 | Shared entry for MVR_IMG1/IMG2/IMG_POST | docs/RE_LIVEVIEW.md §1 |
| `0x603291af` | MVR_MAIN | func | V | CPU2 task 0x2002 entry, prio 25, stack 0x2800 | Waits flag (0x60041076) at 0x6032920e; bit 0x4 -> mbx 0x2001, 0x8 -> mbx 0x2002 (0x6032560b), others -> 0x6032a07d. Runs the LV job state machine | docs/RE_LIVEVIEW.md §1-2 |
| `0x6032936a` | lv_apply | func | V |  | Current record 0x60309eb9, 0x6031b09f, 0x6032f37a/0x6032f5e0, 0x6032a1d6 (-> comparator / act 0x6032a706) | docs/RE_LIVEVIEW.md §2 |
| `0x60329479` | lv_msg_to_event | func | V | d0 mbx, d1 code, a0 &event | mbx 0x2001: 1->0, 2->1, 16->2, 26->3, 17->4, 23->5, 18->6; mbx 0x2002 via jtab 0x604e3f00: 1->11, 5->12, 2->13, 3->14, 4->15, 6->16, 7->17, 8->18, 10->19, 33..36->24..27 | docs/RE_LIVEVIEW.md §2 |
| `0x60329646` | lv_msg_handler | func | V | a0 msg {u16 mbx, u32 code, +8, +12 state*, +16 ctx} | Mailbox 0x2001/2 handler: 0x60329479 maps code -> event, then 0x6032967e | docs/RE_LIVEVIEW.md §2 |
| `0x6032967e` | lv_state_dispatch | func | V | d0 event (<28), a0 state*, a1 ctx | entry = 0x604e315c + 0xE0*state + 8*event; action(state, entry, ctx, &out) then post(state); errors 0x9d05/0x9d06. Callers 0x60329670, 0x6032a19e, 0x6032cb75 | docs/RE_LIVEVIEW.md §2 |
| `0x6032a07d` | lv_flag_to_event | func | V | a0 ctx, a1 &flag bits | 0x1 -> event 7 (after 0x6032c82d, 0x60305edd, 0x60305e3b, 0x6031a8a0, 0x6032c703); 0x2/0x400 -> 8 dmy_cap; 0x10 -> 9 rec_err; 0x20..0x100 -> 10 allow_rec_end; 0x200 post_through_end_timeout | docs/RE_LIVEVIEW.md §2 |
| `0x6032caec` | lv_jobend_to_event | func | V |  | Job-end word: 0x4000 -> 23, 0x800 -> 20, 0x1000 -> 21, 0x2000 -> 22 | docs/RE_LIVEVIEW.md §2 |
| `0x6032cba8` | lv_s_reader | func | V |  | -> 0x6030ba2b: only LV reader chain of effective S (0xF6EA via 0x6030bd54) | docs/LV_BUNDLES.md |
| `0x6032dd61` | lv_ev7_action | func | V | state action | Event 7 family (also 0x6032ddb2, 0x6032de23, 0x6032de8e, 0x6032dee6): 0x6032cba8 re-read, 0x60309d90, 0x6030a801, 0x6032936a | docs/RE_LIVEVIEW.md §2 |
| `0x603f26a1` | REC_VIEW | func | V | task 108, prio 26 |  | this atlas (descriptor) |
| `0x604e2f64` | mvr_handler_table | table | V | u32[7] handler | 0x60329646 LV state machine, 0x6032819d, 0x603301cc, 0x603252a9, 0x60325ed9, 0x60332acc, 0x603324fc (Rec View) | docs/RE_LIVEVIEW.md §1 |
| `0x604e315c` | lv_state_table | table | V | 13 states x 28 events x 8 B {u32 action, u32 post}; row 0xE0 | Event 7 (param update) in every state: actions 0x6032dd61/0x6032ddb2/0x6032de23/0x6032de8e/0x6032dee6/0x6032f09e, post 0x6032e074. LV_ART_PREVIEW §7 read it 4 B off (0x604e3190) and called event 7 "event 0" | docs/RE_LIVEVIEW.md §2 |
| `0x605540e6` | takemov_drain | func | V |  | TAKE_MOV loop body: arg 0 -> 0x60554173 (multi-step, progress word 0x6223cd18) -> 0x605542ba -> 0x60303ad3; arg != 0 -> 0x605542b0 -> 0x60303e7f | docs/RE_LIVEVIEW.md §1 |
| `0x60882ec4` | getOutputSizeForFineZoom | func | V |  | JT 0x60b01e74; getTakeAreaSize 0x608833ae | docs/ASPECT.md |
| `0x62236dbd` | through_update_gate | data | I | u8 | Non-zero = TAKE_MOV through path live [I] | docs/RE_LIVEVIEW.md §1 |
| `0x6223cbbc` | takemov_queue | data | V | ptr to queue object | Dequeued by 0x60554128 (cpu_lock); enqueue 0x6020b998 | docs/RE_LIVEVIEW.md §1 |
| `0x6266a354` | recview_developing | data | V | u8 | Set 0x60332799 (Rec View developing) | docs/ISSUES_19_20.md |

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

| Address | Name | Kind | Tag | Signature / layout | Notes | Source |
|---|---|---|---|---|---|---|
| `0x60040a20` | recview_sem_id | data | V | u16 = 22 | REC_VIEW holds it per request; REC_IMAGE briefly | docs/RE_CAPTURE.md §1 |
| `0x60040c90` | rec_main_flag_id | data | V | u16 = 203 | Bits 0x1 mbx 75, 0x2 local, 0x4/0x8 CPU2 slot 0/1 | docs/RE_CAPTURE.md §1 |
| `0x60040d6e` | rec_mbx_ids | data | V | u16 73..79 | 73 REC_FILE, 74 REC_IMAGE, 75 REC_MAIN, 76/77 REC_PREPRO, 78 REC_SOUND, 79 REC_VIEW; 0x60040e32 171 PRE_V1, 0x60040e34 172 PRE_I1, 0x60040e1a 159 REC_EXT | docs/RE_CAPTURE.md §1 |
| `0x602325b4` | rap_block_names | table | V | char* x 26 | RAP_* / VDC_* debug names; RAP_SHADING_SETTING and RAP_CIRCLE_SHD_SETTING (and _2) are front-end blocks | docs/VIGNETTE_FIX.md |
| `0x602a529f` | cap_still_cmd_build | func | V | capture command builder | Calls 0x6055545e, stores cap+0x1326 / +0x13b0 / +0x15f0 / +0x1650 / +0x384a / +0x13b8 / +0x5da0 pointers at cmd+0x1bc..0x1d8 | docs/VIGNETTE_FIX.md |
| `0x602a79ef` | lens_shading_fetch | func | V | a0 desc (bit 0 -> 0x2000) | Reached from R3/R4 when key 0x8c21 == 1. Front-end command with outputs cap+0x1326 (64 u16), cap+0x13b0, +0x15f0, +0x1650, +0x384a, +0x5da0 | docs/VIGNETTE_FIX.md |
| `0x602a7eda` | cap_sharp_read | func | C | call 0x6005e971 key 0x8119 -> cap+24010 | Sharpness read (hook sh_get at rel32 +1) | docs/SHARPENING_OFF.md |
| `0x602a8095` | cap_nr_read | func | C | key sid 143 | Noise Filter capture read (also MakerNote 0x6028d08a) | docs/CODE_SPACE_MAP.md |
| `0x602a8372` | cap_me_fields | func | V |  | Copies keys 0x1851 (Auto Gain), 0x1841 (frames) into capture (0x602a8385) | docs/LIVE_ND.md |
| `0x602a857e` | capture_populate | func | V |  | Settings -> capture record: pm read 0x602a8577 (cap+24053), F6B1 0x602a85b7 (if pm 11, cap+24083), S x12 cap+24058.., mono +24084..86 | docs/PROFILE_INDEX_WB.md, docs/AP_CUSTOM.md |
| `0x602ab42d` | cap_still_cmd_shading_b | func | V | same contract as 0x6055545e | R2 of VIDEO_HIDDEN §5 (call 0x602ab488); +0x10000 always | docs/VIGNETTE_FIX.md |
| `0x603017f3` | capture_setup | func | C | (8,sp) = cap | EXIF-facing capture fields; copyright-enable getter 0x6030288d | patches/exif_name/ex.s.in |
| `0x60302c0f` | wb_resolve | func | V |  | Segment to 0x60302fc9: category cap+24006 (prop 33057), preset cap+24002 (33073); 10 rel32 WB getter sites | docs/WB_AND_MONO.md, docs/WB_PATCH.md |
| `0x6030e9d1` | params_builder_2 | func | V |  | Second params builder (<- 0x60329080); WB reads 0x6030eb61/77 | docs/WB_PATCH.md |
| `0x603b5769` | wb_gain_calc | func | V | d0/d1 = params+5520/5521 | Called twice: params+4466 -> job+11322, +4474 -> job+11330 | docs/WB_PATCH.md |
| `0x603df803` | REC_MAIN | func | V | task 32, prio 54 |  | this atlas (descriptor bytes) |
| `0x603df97d` | rec_reply | func | V | d0 status, a0 msg | 12-B reply to mailbox at msg+32 | docs/RE_CAPTURE.md §1 |
| `0x603df9f1` | rec_msg_recv | func | V | d0 mbx, a0 msg (300 B); timeout -1 | Sets +192 = 0x1f01 when abort word 0xa26a0a94 set and +280 == 3 | docs/RE_CAPTURE.md §1 |
| `0x603dfa41` | rec_msg_send | func | V | d0 mbx, a0 msg (300 B); timeout -1 |  | docs/RE_CAPTURE.md §1 |
| `0x603dfb10` | rec_main_drain | func | V | a0 msg buf | Counts mbx 75, receives each, routes by +52 via jtab 0x6053adbc (28): mbx 76/77, 159, 78, or CPU2 slot + flag 0x60041090 | docs/RE_CAPTURE.md §1 |
| `0x603e14ca` | rec_image_prep | func | V |  | Called by REC_IMAGE before cap_type_switch; holds sem 22 (0x60040a20) only around 0x603e1fe1 (shot settings copy) | docs/RE_CAPTURE.md §1 |
| `0x603e1a40` | wb_bracket | func | V |  | BKT step -> cap+3028/3030 | docs/WB_PATCH.md |
| `0x603e28c6` | REC_MAIN_CPU2 | func | V | CPU2 task 0x2012, prio 55 | Waits CPU2 flag 0x60041090; -> mbx 0x600410c2 | docs/RE_CAPTURE.md §1 |
| `0x603e2c0d` | rec_trace | func | V | (mode\|code, file/line, ...) | "%s(%s):%d mode[%04x] TID:%d" trace (83 callers); sibling 0x603e2b2f | docs/RE_CAPTURE.md §1 |
| `0x603e4e82` | rec_history_add | func | V | d0 stage, d1 cmd | Per-CPU ring 0xa26a0aa0 + 0x448*cpu | docs/RE_CAPTURE.md §1 |
| `0x603e5d57` | REC_IMAGE | func | V | task 31, prio 54, stack 0x3700 | Capture task; runs work list 0x60354214 from 0x603e624d. (HALATION_RED calls this REC_MAIN: wrong, REC_MAIN = 0x603df803) | this atlas (descriptor bytes) |
| `0x603e5fce` | cap_type_switch | func | V | table 0x6053dac0 | Job-type switch (types 4098..) -> combine loop 0x603edcca | docs/LIVE_ND.md |
| `0x603e62d1` | conv_still | func | V | (20,sp) capture, d3 params | Capture -> job params (params = job+36); shared by 4 still builders. Mode-12 gate 0x603e66ab | docs/FIRMWARE_GUIDE.md §6 |
| `0x603e8af1` | conv_cpu2 | func | V |  | CPU2 path converter | docs/FIRMWARE_GUIDE.md §6 |
| `0x603e91e4` | conv_rec | func | V |  | Recording path converter; gate 0x603e91f2. Others 0x603ec1b9, 0x603f1ab2 | docs/FIRMWARE_GUIDE.md §6 |
| `0x603ea909` | job_type_map | func | V |  | Job type from source request (0x110, 0x120, 0x1000, 0) | docs/GRAIN_PORT.md |
| `0x603eab39` | art_effect_to_flags | func | V |  | Art Effect id -> job flags (jtab 0x6053dd00); from 0x603e615c/0x603e8abd; key-11 test 0x603eaa04 | docs/BLOOM_HALATION.md |
| `0x603eca94` | rec_mem_get | func | V |  | Allocates the 0x4da7d47-B REC working block (0xa26a1ca8) under sem 94; "rec_mem.c" | docs/RE_CAPTURE.md §2 |
| `0x603ecd3b` | rec_mem_config | func | V |  | Picks memory mode 0/1/2 from settings, frees the working block. Entry 0x603ec9f3 (callers 0x602ed2ec, 0x6031fa5d, 0x60c7347a) | docs/RE_CAPTURE.md §2 |
| `0x603eec2e` | rec_wai_flg | func | V | d0 flag, d1 pattern | Logs 0x1e040002 line 219 on failure | docs/RE_CAPTURE.md §1 |
| `0x603ef3d3` | xcpu_slot_find | func | V |  | 2-slot cross-CPU ring (index 0xa27409e8); both busy -> 0x1e040002 line 0x202 | docs/RE_CAPTURE.md §1 |
| `0x603ef606` | xcpu_slot_take | func | V |  | Copies slot record 0xa27409fc + 300*slot, calls its handler | docs/RE_CAPTURE.md §1 |
| `0x603f07b9` | REC_PRE_V1_CPU2 | func | V | CPU2 task 0x2013, prio 26 | -> mbx 0x600410c4 | docs/RE_CAPTURE.md §1 |
| `0x603f2b1f` | REC_VIEW_CPU2 | func | V | CPU2 task 0x2014, prio 25 | Results back to CPU0 flag 203 + slot | docs/RE_CAPTURE.md §1 |
| `0x6053adbc` | rec_main_route_jtab | table | V | 28 x u32 | Route code (+52) -> handler | docs/RE_CAPTURE.md §1 |
| `0x6053da74` | rec_image_cmd_jtab | table | V | 19 x u32 (cmd 0x1001..0x1013) | REC_IMAGE per-command tail | docs/RE_CAPTURE.md §1 |
| `0x6055545e` | cap_still_cmd_shading | func | V | d0 capture-mode id, a0 cmd; 5 callers | Fifth 0x8c21 reader (call 0x605554bc). Record bit 3 && key == 1 -> cmd+4 \|= 0x2000. Twin of 0x602ab42d. v0.25 sc_get covers it | docs/VIGNETTE_FIX.md |
| `0x60555739` | cap_mode_record | func | V | d0 id -> a0 record or 0 | 45 x 48-B records at 0x6055ca20; +4 bit 3 = shading allowed (still ids 0x1xxxx yes, LV 0x2xxxx and 0x90000 sensor-check no) | docs/VIGNETTE_FIX.md |
| `0x6055ca20` | cap_mode_records | table | V | 45 x 48 B {u32 id, u16 flags, ...} | Id 0x10000/0x110000/0x210000/0x50000/0x1000e/0x10019 ... have flags 0x000b (bit 3) | docs/VIGNETTE_FIX.md |
| `0xa26a0aa0` | rec_history | data | V | +0 tail, +2 head, +8 256 x {u8 task letter, u8 stage, u16 cmd} | No timestamps; .bss. Stages 60/62 begin/end, 91/93 view, 101 REC_MAIN | docs/RE_CAPTURE.md §1 |
| `0xa27409e8` | xcpu_slot_ring | data | V | u8 index, busy bytes +1.., keys 0xa27409ec+8n, records 0xa27409fc+300n | CPU0 <-> CPU2 REC messages | docs/RE_CAPTURE.md §1 |

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

| Address | Name | Kind | Tag | Signature / layout | Notes | Source |
|---|---|---|---|---|---|---|
| `0x601de740` | st_w | func | V | d0 = P+1020, a0 = P | Ours (split_tone v0.32a .sti): EP7X (no LOOKS.BIN, or fm_load still reading) -> capture mallocs at once, live view counts 240 split passes in P+848 (tag 0x5354xxxx) first; fm_load not run -> no split | patches/split_tone |
| `0x60210e90` | st_h | func | V | jmp from st_c; (4,sp) P, (24,sp) kind | Ours (split_tone v0.32a .sth): no S at P+848 -> with LOOKS.BIN (P+1020 EP7F, L valid) S = L+2688 in the unused tail of the LOOKS block, no malloc; else jmp st_w | patches/split_tone |
| `0x603397e0` | dev_stage_list | func | V | a0 ctx | Stage builder; 0x60339b8e gates the lens shading stage 0x6039d19a -> 0x6039e54e | docs/VIGNETTE_FIX.md |
| `0x60339b8e` | gate_lens_shading | func | V | a0 ctx -> d0 | On when ctx+0xc4 == 0 and 0x603b54b0(request) != 0 and byte 1 != 0xff | docs/VIGNETTE_FIX.md |
| `0x6034667e` | isp_desc_write | func | V |  | Copies output words verbatim to hardware descriptors | docs/FINDINGS.md |
| `0x60346e37` | gamma_lut_upload | func | V | a? window (u32 words), ctx (+12 O, +0x38 owner, +0x6c dirty bits) | R==G==B: window+0x000; else R +0x400, G +0x800, B +0xC00 (bytes), O+2608 -> +0x1000; skipped unless owner changed (0xa27360ec[2]) or ctx+108 bit0. Callers 0x60345f9b, 0x60345fbd (in 0x60345ebe) | docs/RE_LIVEVIEW.md §4 |
| `0x60346eb4` | gamma_reg_writer | func | V | (4,sp) = O+2596, (16,sp) = stage context | Skips if R slot 0, or if no context change and C+108 bit 0 clear (btst 1 at 0x60346ed0); R = G = B path and a distinct-RGB path, both CPU copies (no DMA). The only consumer of split_tone curves | docs/GRAIN_HANG.md |
| `0x6034fcd2` | tone_ctrl_scale | func | V | (R+1512, C+64) | Raw -7..7 tone values scaled; spline bend 0x6034ff93 | docs/TONE_ENDS.md |
| `0x60350334` | pool_first_fit | func | V |  | Free list pool+0x2c; nodes 0x603503ca (<=125 x 16 B) | docs/RE_CAPTURE.md §2 |
| `0x603504a0` | buf_alloc_core | func | V | size, flags, job, desc -> slot or 48 | 48 records at job+0x19c0; flag 0x20000 pool (0x10000 selects job+0x2ab0 else job+0x2a5c), else 0x6034442b | docs/RE_CAPTURE.md §2 |
| `0x60350560` | buf_alloc | func | V |  | Job buffer pool (40 MB full size); >=48 -> error 0x9ec3/0x9ece; free 0x60350843 | docs/GRAIN_PORT.md |
| `0x60350843` | buf_free | func | V | d0 slot (<48), a? job |  | docs/RE_CAPTURE.md §2 |
| `0x60350975` | buf_lookup | func | V | job, id -> 88-B record | job+6592: 48 records: +0 bus, +8 fmt, +10 stride px, +12 w, +14 h, +16/18 active, +20/22 x/y, +72 size | docs/FIRMWARE_GUIDE.md §7 |
| `0x603510af` | job_req_slot_get | func | V |  | 3 x 0x1058 B at job+0x968; none free -> 0x9ece | docs/RE_CAPTURE.md §2 |
| `0x603537eb` | job_ctor | func | C |  | Job constructor (stills, LV, movie). Size 15488 at 0x603537f0 (Caduceus 15512), tail memset 0x6035390c. Pre-dispatch 0x60353c70 -> 0x60354709 -> work list | docs/FIRMWARE_GUIDE.md §6 |
| `0x60353b15` | job_flag_strip | func | V |  | Type &0xf0==0x40 or &0xf00==0x100: clears 0x40/0x80/0x300/0x4000/0x40000/0x100000 (art keys only) | docs/BLOOM_HALATION.md |
| `0x60353bcf` | job_color_shading | func | V |  | Keys 9/11 always get 0x80000 (creative shading 0x6035b03a) | docs/GRAIN_PORT.md |
| `0x60353d02` | pack_mono_filter | func | V |  | Mono-filter merge (key-12 test 0x60353db9) | docs/MONO_COLOUR.md |
| `0x60354214` | worklist_run | func | V |  | Runs entries synchronously (`calls (a1)` at 0x6035428e) in REC_IMAGE | docs/GRAIN_PORT.md |
| `0x60354930` | request_wait | func | V |  | Wait for producing request before CPU reads | docs/FIRMWARE_GUIDE.md §7 |
| `0x60354ce4` | request_pack | func | V |  | Clears request (job+11364, 1884 B) and fills from params | docs/FIRMWARE_GUIDE.md §6 |
| `0x60355409` | request_pack_movie | func | V |  | Same S path (request+1816) | docs/MOVIE_COLOUR.md |
| `0x60355ebe` | job_pre_pass_cb | func | V | job+0x2c20 callback | Set for every key but 12 and 0x01010068/0x01020068 (worklist_build). Returns 0x603a2ec6(...) unless params+5555 | docs/VIGNETTE_FIX.md |
| `0x60355fd4` | job_callback | func | V |  |  | docs/HSL_PORT.md |
| `0x603573d3` | worklist_mod_slot | func | V |  | Development entry modifier slot; final add 0x6035739e | docs/GRAIN_PORT.md |
| `0x60357415` | worklist_build | func | V |  | Dispatch on key (hash 0x6052200c, (key-11)&31); post-handler flag tests 0x603578bd.. | docs/FIRMWARE_GUIDE.md §6 |
| `0x6035749f` | worklist_default | func | V |  | Keys < 12 | docs/GRAIN_PORT.md |
| `0x603574e3` | worklist_gf | func | V |  | Grainy Film I/II handler | docs/OM3_NOTES.md |
| `0x6035778b` | worklist_key12 | func | V |  | MONO: job+11320==0 -> mask pass 0x60359bc8 (stage 0x0900) + grain pass 0x60359cd8 (0x0901) | docs/GRAIN_PORT.md |
| `0x6035b03a` | creative_shading_mod | func | V | effect 0x0c00 | Fallback 0x6035b529 / 0x6035b517 | docs/GRAIN_PORT.md |
| `0x6035b03f` | creative_shading_mod_body | func | V | job, request | Level job+0x15d4: 0 -> effect 0, gain 0x400 (emulated bank == no mask); 1..5 / -1..-5 -> effect 0x0c00, gain 0x100000/tbl 0x604ec0d8. Copies the mask desc *(job+0x37a0)+0xc -> request+0x214 | docs/VIGNETTE_FIX.md |
| `0x6035b105` | mask_mod_10000 | func | V | job, request | Job flag 0x10000 modifier: mask desc job+0x11c8/+0x1208, effect 0xfe00, gain job+0x1248. 0x10000 is cleared for stills in art_effect_to_flags (0x603eabd0) and never set there | docs/VIGNETTE_FIX.md |
| `0x6035ca31` | sf_blend | func | V |  | 0x1000 + 0x1061 -> new 0x1000; returns with buffer complete | docs/FIRMWARE_GUIDE.md §6 |
| `0x6035cc1b` | softfocus_pending | func | V | cb 0x6035cd94 | Classes 5-8 single pass; classes 0-3 reduce 0x6035cee6 -> upscale 0x6035cfe9 -> blend 0x6035ca31 | docs/BLOOM_HALATION.md |
| `0x6035cee6` | sf_reduce | func | V |  | 0x1000 -> 0x1060 (160x120 / 144x108 / 144x80, fmt 0x0305, 4 B/px); sizes 0x60348ce2, table 0x604eb450 | docs/BLOOM_HALATION.md |
| `0x6035cfe9` | sf_upscale | func | V | kind 3, stage 0xf005, effect 0x0401 | 0x1060 -> 0x1061 (fmt 0x0302) | docs/BLOOM_HALATION.md |
| `0x6035d0f4` | dramatic_pass | func | V | effect 0x0100 -> 0x6035d253 (0x0101) | Highlight finding unresolved (0x6035d4ae?) | docs/BLOOM_HALATION.md |
| `0x6035d6ef` | starlight_pass | func | V | kind 3, effect 0x0106 -> combiner 136 | Star layer 0x1083 | docs/BLOOM_HALATION.md |
| `0x60366f21` | dev_default | func | V | default dev entry body (from 0x60356d7b) | request+0x668 is set (1 / 0x10101 / 0x20201 / 0x30101 / 0x40201) only when job+0x2c4a != 0 (multi-pass branch); else stays 0 | docs/VIGNETTE_FIX.md |
| `0x6036b564` | mask_cache_96 | func | V | 2 x 92-B objects | Key 0x01010076 only: 4 planes 96 x 96 from fixed ROM tables 0x604eb85c.. (0x6036ce3d -> 0x603389c8) | docs/VIGNETTE_FIX.md |
| `0x6036b635` | mask_cache | func | V | 4 x 100-B objects at 0xa27364e8 | Shading/vignette mask; descriptor by 0x6036cec0 (128x128 u16 Q10, fmt 0x080C); pixels 0x603390a4 -> 0x60338d49 (radial 0x604ebf1c) | docs/HALATION_RED.md §10c, docs/VIGNETTE.md |
| `0x6039e54e` | stage_lens_shading | func | V | a0 ctx (+4 request, +0x14 bank) | Kind 0: request+0x6fc on -> 64-entry radial gain from request+0x67c into bank+0x404/+0x484, bit 4 of bank+0xc; off -> flat 0x2000. Kind 5: off. Runs only if request+0x668 != 0 | docs/VIGNETTE_FIX.md |
| `0x6039fe58` | combiner_5 | func | V |  | Water Color I affine; table 0x605244f4; default chroma 0x6039fdf0 | docs/BLOOM_HALATION.md |
| `0x6039fee8` | sf_weight_get | func | C |  | Soft Focus weight table 0x604ec02e by level | docs/BLOOM_HALATION.md |
| `0x603a013b` | combiner_config | func | V |  | Hash 0x60524508; bank = base+7364 | docs/GRAIN_PORT.md |
| `0x603a049e` | combiner_11 | func | C |  | Linear mix w / 1024-w, diagonal YCbCr; w from 0x6039fee8. w > 1024 = unsharp (Clarity) | docs/CLARITY.md |
| `0x603a05b3` | combiner_31 | func | V |  | Grain; gains 0x604ec0ce (110/300/600) | docs/GRAIN_PORT.md |
| `0x603a065b` | combiner_32 | func | V |  | Grain; gains 0x604ec0d4 (50/75/100); counter 0xa27393f8 | docs/GRAIN_PORT.md |
| `0x603a06f8` | combiner_33 | func | V | mode 0x1002 | Lerp to constant colour through mask (vignette/shading) | docs/VIGNETTE.md |
| `0x603a2ec6` | pre_pass_select | func | V | d0 0, type, key*, ISO, ... | ISO bucket tables 0x60505280 (on from bucket 5) / 0x6050528c (all on); key only matters for art 0x0101006d and 0x0200008f/0x020003e8 | docs/VIGNETTE_FIX.md |
| `0x603aaced` | stage_dispatch | func | V |  | Request kinds 0/16 -> 0x603b17e6/0x603b1819; callers 0x60339870, 0x603399d7 | docs/LV_BUNDLES.md |
| `0x603ac0c1` | sharpen_gain | func | C |  | One byte from Sharpness (0 at -5 on key 11) | docs/SHARPENING_OFF.md |
| `0x603acfe4` | mono_selector | func | V |  |  | docs/MONO_COLOUR.md |
| `0x603ae2fd` | gamma_row_pick | func | V | a0 row, d0 variant, d1 type (R+14) -> a0 curve | Column: type hi 0x40 -> +16; 0x30 + lo 2..5 -> +8 else +24; other + lo 2..5 -> +8 else +0; variant -> +4 | docs/RE_LIVEVIEW.md §4 |
| `0x603ae354` | gamma_select | func | C |  | RGB gamma selection; movie log path | docs/VIDEO_LOG.md |
| `0x603ae7d3` | rgb_gamma_set | func | V | three curve pointers | Per-channel R/G/B gamma setter (split-tone lead) | docs/FUJI_GAPS.md, docs/SPLIT_TONE.md |
| `0x603ae80d` | gamma_stage | func | V | a0 stage ctx (+4 request, +12 output O); `call ..,[d2,d3,a2,a3],16` | From dev_stage_list 0x603b14a6 (2nd stage). gamma_select -> cache check -> rgb_gamma_set 0x603ae995 -> cache store. Split-tone hook G1 at 0x603ae830 (5 B f8923c 5c24) | docs/RE_LIVEVIEW.md §4-5 |
| `0x603ae830` | gamma_stage_after_select | site | V | 5 B `movbu d0,(60,sp); mov (36,sp),a0`; frame add -260,sp | (40,sp) request R, (36,sp) output O, (56,sp) ctx, (60,sp) select result, (68/72/76,sp) R/G/B curve pointers; stage returns by ret (MDR dead) | docs/SPLIT_TONE_G1.md §1.2 |
| `0x603ae861` | gamma_change_cache_ptr | code | V | d3 = (R+1484) + 5736 when (R+1484) != 0 | Cache {R*, G*, B*, 12 B, u8 +20}; all three equal and 0x603b5ddc == 4 -> setter skipped (0x603ae8c1..8f0) | docs/SPLIT_TONE_G1.md §1.2 |
| `0x603ae9cf` | gamma_skip_clear | site | V | mov (56,sp),a0; add 108,a0; and -2 | gamma_stage skip path (slots unchanged): clears C+108 bit 0. Not a wait flag | docs/GRAIN_HANG.md |
| `0x603aeacd` | gamma_stage_art_reads_g_slot | code | V | mov (2600,O),a1 -> 0x60335323 | Only O-slot read in the gamma stage; in the art-key branch (keys 0x01010064..0x01030069) after its own setter | docs/SPLIT_TONE.md |
| `0x603af871` | mono_color_route | func | V |  | Key 12: hash 0x60532510 miss -> desc 0x60530eb8 (table 0x605120ec, ctrl 0xb8f) or 0x60530eec (0x60512cc0, 0x3cf) | docs/WB_AND_MONO.md |
| `0x603afb94` | color_builder_art | func | V |  | Art tables; bypasses H/L hook | docs/HSL_PORT.md |
| `0x603afd26` | color_builder_general | func | V |  | Non-11 keys when flagged | docs/MOVIE_COLOUR.md |
| `0x603b0068` | color_builder | func | C | `call ..,[d2,d3,a2,a3],96`; ret at 0x603b0244 | 12 records at +688 stride 24 (hue +18, sat +20, L +22) from 0x6051de2c and request+1816. Ends 0x603b0246 (0x603b0247 is a separate leaf) | docs/HSL_PORT.md, docs/REVIEW_fixed_hl.md |
| `0x603b0252` | color_selector | func | C |  | Key 11 test 0x603b02c1 -> builder call 0x603b02d9 (H/L hook); request+1524 -> art builder 0x603afb94 at 0x603b027c | docs/FIRMWARE_GUIDE.md §6 |
| `0x603b039b` | tone_select | func | V |  | ROM LUT by contrast (R+1796) via 0x603b092f | docs/TONE_ENDS.md |
| `0x603b04fa` | tone_select_mask | func | V |  | Key 12 stage 0x0900 -> 0x60532738 | docs/GRAIN_PORT.md |
| `0x603b0a70` | tone_lut_build | func | C |  | 256 x u16 luminance LUT (10-bit), tone control bend into O+2612 | docs/TONE_ENDS.md |
| `0x603b132a` | chroma_stage | func | C |  | Output+76 {enable, Cb, Cr} via 0x603b11fb (hook 0x603b134e); makes MONO grey | docs/WB_AND_MONO.md |
| `0x603b1466` | dev_stage_list | func | C |  | Development stages: colour (0x603b14f3 -> selector), tone 0x603b0a70 (hook after 0x603b14ff), chroma 0x603b132a (0x603b1508) | docs/FIRMWARE_GUIDE.md §6 |
| `0x603b1517` | stage_list_alt | func | V |  | From 0x603b1843/0x603b18b5; colour step 0x603b0345 | docs/LV_BUNDLES.md |
| `0x603b18cd` | stage_kind4_lv | func | V |  | Kind 4 defaults, chroma off (0x603b1904) | docs/WB_AND_MONO.md |
| `0x603b5200` | combiner_select | func | V | (key, stage, effect) | Key 12: 0x0901 -> 31, 0x0902 -> 32 (0x603b531a); default path 0x603b539f hash 0x60532e98 (0x0402 -> 11, 0x0403 -> 12); grain hook 0x603b5249 | docs/GRAIN_PORT.md |
| `0x603b54b0` | req_pre_pass_cfg | func | V | a0 request -> d0 | Kind 0/16: request+0x668, kind 4: +0x108, kind 5: +0xd8 | docs/VIGNETTE_FIX.md |
| `0x603b5ddc` | gamma_cache_cmp | func | I | a0, a1 -> d0 (4 = same) | Second half of the gamma-stage cache check (after pointer compare) | docs/RE_LIVEVIEW.md §4 |
| `0x603b5e8c` | gamma_curve_analyse | func | I | a0, a1 curve, d0 out | Run per distinct curve when gamma_select returns 1; outputs to stage frame +44..+64 (meaning unknown) | docs/RE_LIVEVIEW.md §4 |
| `0x604eb450` | sf_reduce_sizes | table | V |  | Global; changing it changes stock Soft Focus | docs/BLOOM_HALATION.md |
| `0x604ec02e` | sf_weight_table | table | V |  | By level (request+1832/+708) | docs/BLOOM_HALATION.md |
| `0x604edc78` | rgb_gamma_tables | table | V | ~97 x 256 u16 (0..4095) to 0x604f9c78 | Slot 0 identity | docs/VIDEO_LOG.md |
| `0x604eee78` | gamma_crossproc1_r | table | V | 256 u16 (0..4095) | Cross Process I R; G 0x604ef078, B 0x604ef278 | docs/RE_LIVEVIEW.md §4 |
| `0x604f0a78` | gamma_vintage1_r | table | V | 256 u16 | Vintage I R; G 0x604f0c78, B 0x604f0e78 (B 1283..3818: stock split tone) | docs/RE_LIVEVIEW.md §4 |
| `0x604f4278` | gamma_flat | table | C | 256 u16 | Effect id 2000 (Flat) | docs/VIDEO_LOG.md |
| `0x604f4478` | gamma_log | table | C | 256 u16 | Effect id 2001 (log) | docs/VIDEO_LOG.md |
| `0x604f9e82` | luma_tone_tables | table | V | ~50 x 256 u16 (0..1023) to 0x60500fb6 | Contrast 0 0x604fa082, +2 0x604fb482 | docs/VIDEO_LOG.md |
| `0x605003aa` | grain_mask_weight | table | I |  | Chroma-preserving weighting mask lead | docs/FUJI_GAPS.md |
| `0x6050f06e` | mono_tone_vectors | table | V | 5 x 5 B {1, Cb, Cr, Cb2, Cr2} | N/Sepia/Blue/Purple/Green | docs/MONO_COLOUR.md |
| `0x6051d258` | art_color_table | table | V |  | Art (0x0101007c, key 2818); centres 5461 apart. Also 0x605167e4 (0x0101006c) | docs/V02_BUNDLES.md |
| `0x6051de2c` | color_table | table | C | 12 sector records | COLOR mode table; gains 0x60531810 | docs/FINDINGS.md |
| `0x60521a54` | filter_key_flag_hash | table | V |  | Filter key -> flag (at 0x603539d7): Soft Focus 0x01010065 -> 0x80 | docs/BLOOM_HALATION.md |
| `0x60530b6c` | gamma_ptr_table | table | V | 25 rows x 8 u32 (4 cols x {normal, variant}) | Row 0 base 0x604ede78; 5-7 Cross Process I R/G/B; 9-11 CP II; 12-14 Vintage I; 15-17 Vintage II; 18-20 Vintage III; 21-23 Bleach Bypass II; 24 used when R+1838 == 257 | docs/RE_LIVEVIEW.md §4 |
| `0x60532110` | gamma_effect_hash | table | V | 16 x {u32 id-1999, u32 handler} | id 2000 Flat, 2001 log, 0x0101006b/0x0102006b/0x01010079/0x01020079/0x01030079/0x0102007b three-curve, others single | docs/RE_LIVEVIEW.md §4 |
| `0x60532738` | mask_tone_lut | table | V |  | Key 12 stage 0x0900 tone | docs/GRAIN_PORT.md |

## 9. JPEG and EXIF

The EXIF **writer** itself is not located; what is known is the tag table (rows point at capture-record offsets) and the
capture-setup code that fills those fields. Quantisation is scaled at run time from Q50 tables.

| Address | Name | Kind | Tag | Signature / layout | Notes | Source |
|---|---|---|---|---|---|---|
| `0x6028d08a` | makernote_nr_read | func | V | sid 143 | MakerNote Noise Filter read | docs/CODE_SPACE_MAP.md |
| `0x602a9691` | cap_orientation_latch | func | V |  | Stills latch orientation into cap+24168 (also 0x602a9d33); copied to +18 at 0x603029b7..cd | docs/VIDEO_ROTATION.md |
| `0x60301252` | usercomment_fill | func | V |  | Fills cap+1668..1784 with spaces | patches/exif_name/ex.s.in |
| `0x6030288d` | cap_copyright_get | func | C | call 0x6005e971,[d2,d3],12 key 0x5ef1 | Once per capture setup; Caduceus EXIF hook | patches/exif_name/build.py |
| `0x60302898` | artist_copyright_write | func | V |  | 0x60302898..0x603028b3 write cap+1384/+1554 | docs/FEATURE_GAPS.md |
| `0x603032f2` | maker_string_write | func | V |  | Key 0x8f11 -> cap+2172 ("OLYMPUS DIGITAL CAMERA"); rel16 callers 0x60301348, 0x603018cd | docs/FEATURE_GAPS.md |
| `0x603b6120` | jpeg_q_scale | func | V | Sf (halfword from param block) | q = max(1,min(255,(base*Sf+128)>>8)) [clamp outside?]; engine regs 0x99901xxx; last Sf cache 0xa27393fc; shift at 0x603b619c | docs/JPEG_QUALITY.md |
| `0x603ee48c` | variant_exif_copy | func | V |  | Copies Artist/Copyright to variant jobs (not +1448) | docs/FEATURE_GAPS.md |
| `0x604dadf0` | exif_tag_table | table | C | rows {tag, type, count, cap offset} | 0x10E ImageDescription cap+1448 (32 B), 0x9286 UserComment cap+1660 (125), Artist cap+1384, Copyright cap+1554, Orientation row 0x604dae20 (cap+18) | patches/exif_name/ex.s.in, docs/FEATURE_GAPS.md |
| `0x604ddeb4` | exif_software_tmpl | data | V | "Version x.x" | Digits stored at +8/+10 by 0x60301243..0x6030124e | docs/FEATURE_GAPS.md |
| `0x60533048` | jpeg_q_ptrs | table | V |  | Luma 0x60533058, chroma 0x60533098 (Annex K Q50), then Huffman; used at 0x603b6186 | docs/JPEG_QUALITY.md |
| `0x613e8627` | jpeg_param_dump | func | V | +0x10 ulJpegCodeSize, +0x14 usJpegSf, +0x16 usJpegType, +0x18 usCtrlThAB | Debug print (also 0x613f121b) | docs/JPEG_QUALITY.md |
| `0x613f9322` | cap_profile_dbg | func | V |  | Debug printf of cap+24083, not EXIF | docs/PROFILE_INDEX_WB.md |

## 10. SD and file I/O

fileif API in section 4. From an ordinary CPU0 task each call is a synchronous RPC to FILECLBK (no timeout). Paths
`C:\…`. Caduceus reads/writes `EP7MOD\*.BIN` from HLS_EVENT on half-press ([FIRMWARE_GUIDE.md](FIRMWARE_GUIDE.md) §8).

| Address | Name | Kind | Tag | Signature / layout | Notes | Source |
|---|---|---|---|---|---|---|
| `0x6005a509` | linux_from_sd | func | V |  | Stock fopen/ftell/fseek/fread/fclose precedent | docs/SD_BUNDLES.md |
| `0x605b771f` | sd_lo_slot62 | data | V | sd_lo[62..63] (sd_lo 0x605b76e1, sd_span 0x605b7721) | Loader v3 range check is (s8 byte - s8 lo) <= span unsigned (0x605b75e8..) | docs/SPLIT_TONE.md |
| `0x60613000` | fs_library | data | V | 0x60613000-0x60650000 | FS library (no calls into section 5) | docs/SD_BUNDLES.md |
| `0x60618b53` | card_mount_dcf_init | func | V |  | Card mount sequence (dcfnum.c); last step card_param_csv_load 0x6061907a | docs/RE_SETTINGS.md §6 |
| `0x6062fc44` | FILECLBK | func | V | task 16, prio 55, stack 0x1000 | Dispatch by class: 0x0000xxxx low-level (unmount 18, mount 97, sector read 83, table 0x6070a410), 0x0001xxxx fileif | docs/SD_BUNDLES.md |
| `0x60634a81` | FILEFGND | func | V | task 17 | Driver completions; never block here | this atlas (descriptor), docs/SD_BUNDLES.md |
| `0x60634fbc` | fopen | func | C | a0 path (C:\..), a1 mode -> a0 handle/0; `[],4` | Impl 0x60636358, msg 0x10001 | docs/SD_BUNDLES.md |
| `0x60634fc5` | fclose | func | C | a0 handle; `[d2,a2,a3],16` | msg 0x10002 | docs/SD_BUNDLES.md |
| `0x60635041` | fwrite | func | C | as fread |  | docs/LOOK_EDITOR.md §6 |
| `0x6063514b` | fread | func | C | a0 buf, d0 size, d1 count, a1 handle -> d0; `[d2,d3,a2,a3],24` | msg 0x10005 | docs/SD_BUNDLES.md |
| `0x606351d9` | ftell | func | C | a0 -> d0 (-1 fail); `[d2,a2,a3],16` | msg 0x10007 | docs/SD_BUNDLES.md |
| `0x60635243` | fseek | func | C | a0, d0 off, d1 whence (2 SET, 0 CUR, 1 END); `[d2,d3,a2,a3],20` | Impl 0x6064610d; size handle+268, pos +308 | docs/SD_BUNDLES.md |
| `0x60643765` | fileif_classify | func | V | -> 0 direct / 1 RPC / 2 other CPU | Direct in FILECLBK and task listed at 0xa2786068 | docs/SD_BUNDLES.md |
| `0x60646851` | drive_letter | func | V |  | Drive 0 = C: (adds 67) | docs/SD_BUNDLES.md |
| `0x60765cc8` | fopen_w_precedent | func | V |  | Section-5 app code opens with "w" | docs/LOOK_PICKER.md |
| `0x6077d590` | media_status_set | func | V | d0 media type, d1 status (0xF000 MOUNT OK); ret [d2],20 | Called by 0x60863da7 (0x60863e90, dead for our use) | docs/SD_BUNDLES.md, docs/REVIEW_v04.md |
| `0x607d5510` | ls_chk | func | V | jmp from 0x6143a4ed; a3 = L, d3 = size, a2 = P | Ours (looks_split, sec-5 dead sdk-api claim 0x607d5500..0x607d5900): ls_sc, then call fm_check, jmp 0x6143a4f2 | patches/looks_split |
| `0x607d5521` | ls_sc | func | V | [d2,d3,a2,a3],20 | Ours: CRC first; each record +61/+62 = 0, or +60 = 0 and both split bytes in range; then stash L+2568+2j, zero them in the record, rewrite CRC +16, L+2564 = P, L+2560 EP7W last. Any miss: file untouched (fm_check rejects split bytes after the name NUL) | patches/looks_split |
| `0x6143a410` | fm_load | func | V | CALLS, a2 = P | Ours (film_menu_v2 fm_core, sec 9): once per power-on LOOKS.BIN -> L (malloc 2640 from v0.32, was 2560), fm_check, slot resume by name, publish P+1016 / P+1020 EP7F. v0.32: its fm_check call goes through ls_chk (split stash) | patches/looks_split |
| `0x6143a4ed` | fm_load_call_fm_check | site | V | 5 B `call fm_check,[d2,d3,a2,a3],20` (cd b9 00 f0 14) | Ours (film_menu_v2 fm_core). After it: cmp 0,d0 at 0x6143a4f2; size test and 63 / cmp 128 / cmp 2113 at 0x6143a49e..a4b5; malloc 2560 at 0x6143a439 | docs/SPLIT_TONE_G1.md §1.2 |
| `0x6143a5a6` | fm_check | func | V | a3 = L (file), d3 = size -> d0 0 valid; [d2,d3,a2,a3],20 | Ours (fm_core): header template, CRC (bytes 0..15, 20..end), per-record range table 0..44, class/mask, tint, name rule (NUL tail to +63). Unchanged in v0.32: ls_sc hands it a file whose +61/+62 are already 0 | patches/looks_split |
| `0x6143a688` | fm_crc | func | V | d0 running CRC, a0 data, d1 length > 0 -> d0; [d2,d3],8; keeps a1 | Ours (fm_core): bitwise CRC-32 (0xedb88320), no table. Also called by ls_sc and plugin_loader | patches/looks_split |
| `0x61fa8fb8` | media_status_words | data | V | +0/+8/+10/+18 | Mount status per medium | docs/SD_BUNDLES_V2.md |

## 11. Movie

Picture mode reaches movies through the settings message and record +294; log/Flat via the hidden byte +925 →
effect ids 2001/2000. The colour route of the recording stream (0x6039a97b) is only partly traced.
Detail: [MOVIE_COLOUR.md](MOVIE_COLOUR.md), [VIDEO_LOG.md](VIDEO_LOG.md), [VIDEO_HIDDEN.md](VIDEO_HIDDEN.md),
[VIDEO_ROTATION.md](VIDEO_ROTATION.md).

| Address | Name | Kind | Tag | Signature / layout | Notes | Source |
|---|---|---|---|---|---|---|
| `0x6006d157` | orientation_get | func | V |  | Setting 0x6203c89c / table 0x61b21858[state]; PER_ROTATE task 0x6006d180 stores 0x6203c8a0 | docs/VIDEO_ROTATION.md |
| `0x6030d93e` | mv_settings_msg | func | C |  | A+354 = pm (store 0x6030d969); +925 (log byte) at 0x6030df3d; record copy 0x6030c452 (A+352 -> rec+292) | docs/MOVIE_COLOUR.md, docs/VIDEO_LOG.md |
| `0x60316bc7` | mv_key_map | func | C |  | -> 0x60324d6b -> 0x60349297: rec+294/+925 -> job key (art 0x0101_00yy.., COLOR 11, MONO 12, Flat 2000, log 2001) | docs/MOVIE_COLOUR.md |
| `0x60319139` | rec_limit | func | C |  | `mov 1740,d0` at 0x60319156 (imm at 0x60319157), `mov 7200,d0` 0x6031915b (imm 0x6031915c) | docs/FEATURE_GAPS.md, docs/V02_BUNDLES.md |
| `0x603263d5` | mv_pm_in | func | V |  | Reads 0x9481 into rec68+29 (ptr 0xa27354a0) | docs/MOVIE_COLOUR.md |
| `0x6039a97b` | mv_stream_table | func | I |  | Movie stream job table fetch (<- 0x6035169b <- 0x60351174); colour route not traced | docs/VIDEO_LOG.md |
| `0x603d4027` | rec_start_dispatch | func | C | call 0x603d421e | REC_START (log string 0x60538585) | docs/VIDEO_ROTATION.md |
| `0x603d4053` | rec_free_dispatch | func | C | call 0x603d43af | REC_FREE (log 0x605385a4) | docs/VIDEO_ROTATION.md |
| `0x603f332a` | EXP_MOVIE | func | V | task 96 | Movie exposure [I role] | this atlas (descriptor) |
| `0x6076b856` | second_display | func | V | (which, map) | Mask 0x602cce6a(3); HDMI planes 0x60a36d21 | docs/VIDEO_HIDDEN.md |
| `0x60c8a30f` | MOVP_MAIN | func | V | task 78 | Movie player (also MOVE_* 81-83 for movie edit) [I roles] | this atlas (descriptor) |

## 12. Lens, AE and sequencer

| Address | Name | Kind | Tag | Signature / layout | Notes | Source |
|---|---|---|---|---|---|---|
| `0x601f2761` | lens_dev_get | func | V | d0 0 -> a0 device 0xa271ca70 or 0 | device+0x440 L_REF_M, +1092 L_ID[]; predicate 0x601f46dc (Panasonic) | docs/APERTURE_RING.md |
| `0x601f5ed7` | lens_status_parse | func | V |  | DIS_FCENC store; second parser 0x601f6322 | docs/APERTURE_RING.md |
| `0x601f9df3` | lens_req_dispatch | func | V |  | Every lens request from power-on | docs/APERTURE_RING.md |
| `0x6020d024` | ae_prop_handles_init | func | V | d0 on | on == 1: ~200 x prop_handle(key) -> 0x622a09a4..0x622a0bfc (e.g. 0x6020d7a6 key 0x949a -> 0x622a0b40, 0x6020da40 0x8eb9 -> 0x622a0bd8, 0x6020d393 0x30ea -> 0x622a0a60); else zero them. Callers 0x6020d011, 0x60421338. No value cache | docs/RE_AE.md §0 |
| `0x6028e684` | exp_change_notify | func | V |  | Optional post (mbx 0x600410a6, code 6), then take_expose_calculate. From 0x602e87e1 (sid 86 / sid 6 descriptor callbacks and others) | docs/RE_AE.md §1 |
| `0x603b6fb7` | ae_override_rec | func | V | -> a0 = 0xa27396d8 + 24*(0xa2739720) | Source of AE values when sid 382 == 1 and sid 323[1] == 0 | docs/RE_AE.md §2 |
| `0x603edcca` | me_combine_loop | func | V |  | Two-input Bayer request 0x603523db (cb 0x603e7b83); gain 0x603ee3d8 | docs/LIVE_ND.md |
| `0x603f38f8` | ae_program | func | V | a0 param block {A, B, photometry, ., stab, ., result, aux} | Trampoline to 0x603fbe7a: per-mode program via hash 0x60542558 (key mode-2), else limits 0x603fc6ba -> ae_program_line 0x603fce91 | docs/RE_AE.md §3 |
| `0x603fc5d3` | ae_slow_limit_rule | func | C |  | Hand-holding rule; Lowest S/S uses 0x6020cf8a(+30, step); predicate 0x603fe925 (P/A) | docs/MIN_SHUTTER.md |
| `0x603fcaf1` | ae_sv_resolve | func | V | d0 table Sv code -> Sv | ISO Auto: 0x9f00 -> A+24 (or 0xd00), 0xa000 -> A+26 (or floor), 0xa100 -> same +256 if 0x603fe960, 0xa200 -> floor; manual -> B+2. Clamp [floor 0x500/0x600 (0x603fe808), 0xd00] unless key 0xc222 == 2 | docs/RE_AE.md §3 |
| `0x603fce91` | ae_program_line | func | I |  | Tv/Av/Sv split; applies B+14 (sid 86, program shift [I]) in program modes; snaps to EV step B+12 | docs/RE_AE.md §3 |
| `0x603fe925` | ae_minss_pred | func | V | -> d0 bool | Lowest S/S active: mode in {3,4,36,37}, A+30 != 0x7eee, 0x60420199(A+38, A+46) == 0 (MIN_SHUTTER) | docs/RE_AE.md §3 |
| `0x60421540` | TAKE_EXPOSE | func | V | task 111 |  | this atlas (descriptor) |
| `0x6042661b` | ae_detect_build | func | V | a0 DP (124 B); `call ..,[d2,d3,a2,a3],36` | DP: +18 gradation, +32/+34 Auto ISO upper/default, +46 ISO, +48 Av, +50 exp comp, +56/58/60 exposure shift | docs/RE_AE.md §2 |
| `0x60426e30` | ae_frame_cb | func | V | a0 frame status | Detection-result callback: status 0 and mode != 7 -> publish 0x60425ba3 + te_calc_core every call; else once per 250-tick timer (0x6006b003, cb 0x60425e05 clears 0x622a0641) | docs/RE_AE.md §1 |
| `0x60426f83` | ae_detect_prefetch_cb | func | V | a0 {buf*, ...} | Fills the 124-B DP: mode 7 -> rebuild at most every 100000 counter ticks; else rebuild only when DP+62 == 0x60555c80(), otherwise copy cache 0x622a084c | docs/RE_AE.md §0, §1 |
| `0x6042754a` | take_expose_calculate | func | V | `call ..,[],4` | Log "[TEXP]take_expose_calculate"; sem 0x60040a36 around te_calc_core(0). Callers 0x6028e6a8, 0x604259cb, 0x60425a64 | docs/RE_AE.md §1 |
| `0x604275b3` | take_expose_calculate_internal | func | V | `call ..,[],4` | Same with the _internal string; 38 TAKE_EXPOSE handler callers | docs/RE_AE.md §1 |
| `0x6042760c` | te_calc_core | func | V | d0 flag; `call ..,[d2,d3,a2,a3],16`; 760-B frame | ae_record_build(A sp+36, B sp+120) every call (no cache) -> 0x60427dac -> 0x603f3956 -> ae_program 0x603f38f8 -> 0x6042805e -> 0x6042857f -> copy 76 B to 0x622a0714 | docs/RE_AE.md §1 |
| `0x6042777c` | ae_record_build | func | V | 84-B record (from 0x60427689) | Min shutter builder 0x604279c9 reads key 0x536a | docs/MIN_SHUTTER.md |
| `0x60427ae7` | ae_aperture_snapshot | func | V | call 0x60429548 (InfoGet 0x80ca) | Every LV AE frame | docs/APERTURE_RING.md |
| `0x6042805e` | ae_result_publish | func | V | a0 result 76 B, a1 A, d0 B | Writes AE results to properties (prop_set; keys 0xd0ca, 0xa07a, 0xa02a, 0xa04a, 0xc55a ...) | docs/RE_AE.md §1 |
| `0x604290a4` | ae_shift_meta | func | I |  | Picks exposure shift by EXIF-style metering code (5 ESP 0x30ea, 2 CW 0x30fa, 3 spot 0x310a), stores x100/256 at a2+2564 with /100 | docs/RE_AE.md §4 |
| `0x60429519` | ae_iso_get | func | V | -> d0 Sv (0 = Auto) | key 0x810a (sid 6); Auto with 0x622a076a == 1 -> 1536 (0x603f3968). -> B+2, DP+46 | docs/RE_AE.md §2 |
| `0x60429629` | ae_gradation_get | func | V | `call ..,[],24` -> d0 s8 | key 0x8eb9 (sid 105) via prop_get at 0x6042965b (hook G1); 0x603042a9 branch dead (stub returns 0). Callers 0x6042681a (DP+18), 0x60427876 (A+14) | docs/RE_AE.md §2, §5 |
| `0x604297db` | ae_expcomp_get | func | V | -> d0 (+-1280) | key 0x80ba (sid 2) via prop_get at 0x60429824 (EI hook E1); override struct 0x603b6fb7+16 when sid 382 == 1 and sid 323[1] == 0. Callers 0x604269f6 (DP+50), 0x60427af1 (B+6) | docs/RE_AE.md §2, §5 |
| `0x60541326` | ae_program_table | table | V | 70-B rows, mode u16 at +0x44 (lookup 0x603fca0a) | Per-mode Av/Tv/Sv bounds; Sv entries may be sentinels 0x9f00/0xa000/0xa100/0xa200 resolved by ae_sv_resolve | docs/RE_AE.md §3 |
| `0x6054aa50` | take_expose_msg_table | table | V | 64 x {u32 id+1, u32 handler}, linear probe | TAKE_EXPOSE message dispatch (ids 0x000..0xd03); loop 0x60421540 queue (0x60040d9a) | docs/RE_AE.md §1 |
| `0x6069166d` | fcs_limit_calc_fl | func | V |  | AF Limiter: reads keys 0x5391 (sid 1149 on/off), 0x53a1 (1150 preset), 0x53b2/0x53c2 (near/far x3), 0x5651 (1274) | docs/RE_SETTINGS.md §7 |
| `0x60691b0e` | fcs_limit_drive_exec | func | V |  | AF Limiter drive; reads 0x5642 (sid 1273), 0x5651 (1274); log "focus_limit.ldp_far" | docs/RE_SETTINGS.md §7 |
| `0x609352c9` | seq_focus_bkt | func | V |  | Sequencer: sid 605==1 and (860==1 or 24 in {207,216}); pixshift 0x6093531d, silent 0x6093536a, zero lag 0x609353c2 | docs/UNLOCK_LEADS.md |
| `0x6096b73c` | sendTakePictureContinue | func | C |  | ME parts; entryTAKE_PICTURE_CONT 0x6096a1c7; frame array malloc(20) 0x6091b038 (5-frame hard limit) | docs/LIVE_ND.md |
| `0x60c7a697` | EFFECT | func | V | task 59 | Role unknown (playback/art?) [I] | this atlas (descriptor) |
| `0x61facd8c` | shutter_key_state | data | V | 4 = full press | Kind handlers 0x6095ab89.. | docs/LIVE_ND.md |
| `0x622a0b40` | ae_h_iso_auto_upper | data | V | ptr (handle for key 0x949a, sid 112) | Siblings: 0x622a0b44 0x9a9a, 0x622a0a60/5c/64 0x30ea/0x30fa/0x310a, 0x622a0bd8 0x8eb9, 0x622a0b00 0x80ba | docs/RE_AE.md §0 |

## 13. Updater and container

Container: 32-B header `OE`, model `14 20`, +12 size, +20 kind; payload; 32-B trailer (repeats header 0–27, +28
checksum; word sum over header + decoded payload + trailer = 0). Scramble = invert + 16-byte lane permutation.
FIRMUP_CLI picks `DCOLYMP\E142????BIN` with the largest hex suffix > 0; components written main last; no rollback.
Detail: [FIRMWARE_GUIDE.md](FIRMWARE_GUIDE.md) §1, [SD_UPDATE.md](SD_UPDATE.md), [SD_REJECT.md](SD_REJECT.md).

| Address | Name | Kind | Tag | Signature / layout | Notes | Source |
|---|---|---|---|---|---|---|
| `0x600c4f35` | flash_write | func | V | mode | -> 0x600c5016 -> 0x60021621 -> erase 0x600218a9 -> 0x60021137 | docs/SD_REJECT.md |
| `0x601e7094` | fw_report_ok | func | V | (3,2) | "UPDATE SUCCESS"; fail 0x601e71b6(3,3); none found 0x601e7186(3) | docs/SD_UPDATE.md |
| `0x601e748a` | FIRMUP_LED | func | C | task 116 | Steady = working, ~2 Hz = success | docs/SD_REJECT.md |
| `0x60c95bab` | FIRMUP_CLI | func | V | task 88, prio 45 | Walks pattern table 0x60f2cbf0 in DCOLYMP (cmp 0x60c95ed6, hex suffix 0x60c95fd8); reads into 0xa43a3ec0; posts to FIRMUP_SRV. No static activation found | docs/SD_UPDATE.md |
| `0x60c96030` | FIRMUP_SRV | func | V | task 18 | Started only by USRSTART5 (0x601922f0); kind 1 via 0x60f2d878 -> 0x60c96100 | docs/SD_UPDATE.md |
| `0x60c964c1` | fw_validate | func | V |  | Header, model 0x1420 (0x60c965c7), every checksum; no version check | docs/SD_UPDATE.md |
| `0x60c971e5` | boot_compare_skip | func | V |  | BOOT kind only: read flash, memcmp 0x60022f89, skip if equal | docs/SD_UPDATE.md |
| `0x60c974c0` | fw_ctrl_cmd | func | V |  | Writes 0x98e0008c, cmd 0x20041001 via 0x600219ab | docs/SD_UPDATE.md |

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
