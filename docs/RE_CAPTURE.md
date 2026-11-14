# Capture tasks, crash handling and the v0.31a crash (E-P7 1.1)

Round R2b. Static analysis only: `tools/dis.sh`, `tools/ep7_xref.py`, byte reads and the private decompile corpus.
No build, emulator run or camera test. Answers atlas unknown #4. Tags: **[V]** read from bytes or disassembly,
**[I]** inference. Raw listings are in `~/ep7fw-private/decomp/capture/` (private). New symbols:
`tools/atlas/new_capture.py`. Ids below are resolved through the constant u16 id tables (tasks `0x600408d8`,
semaphores from `0x600409f4`, flags from `0x60040afa`, mailboxes `0x60040cdc`; value n at base + 2n) [V bytes].

## 0. Short answers

1. **The stills pipeline is a chain of mailbox tasks, one message (300 B) per stage** [V]:
   TAKE side → REC_MAIN (router) → REC_PREPRO → REC_PRE_I1 → **REC_IMAGE (job + work list, our CPU passes)** →
   REC_FILE. Rec View leaves REC_PREPRO for REC_PRE_V1 → REC_VIEW, or crosses to CPU2 (REC_MAIN_CPU2 →
   REC_PRE_V1_CPU2 → REC_VIEW_CPU2). Every receive and send blocks forever (timeout −1). The only stage that runs a
   long job is REC_IMAGE (prio 54). While a CPU pass runs there, **every CPU0 task at prio ≥ 54 is starved**: REC_MAIN,
   REC_FILE, HLS_EVENT (54), REC_PREPRO, REC_PRE_I1, SYS_WDT, FILECLBK (55). REC_VIEW (26) and REC_PRE_V1 (46) are
   not, but a Rec View request still has to pass REC_MAIN and REC_PREPRO first [V priorities and routing; I timing].
2. **Nothing is persisted on a crash** [V code]. Every fatal exception and the watchdog arrive at the NMI handler
   `0x60059a9d`. It **sets the hardware watchdog to 1 s first**, prints registers to the debug console and spins, so
   the camera resets about 1 s after any fault. The stock logs that do reach flash or the card do so **only at an
   orderly shutdown**: ICTLOG (1 MB at flash 0x47b00000) and the `dbgterm` console ring (8 KB, card, off by default).
   **A crash log is feasible without flash:** a hook in the NMI handler copies the fault frame and the stock capture
   history into RAM that boot does not clear. The next half-press writes it to the card. It works only if DRAM keeps
   its contents through the watchdog reset, which needs one camera probe (§4).
3. **v0.31a:** the crash timing (≈2 s) fits "fault ≈1 s after the shot, then the handler's 1 s watchdog" [V handler,
   I timing]. The likely cause is that its yields let starved CPU0 tasks run in the middle of a job. Ranked in §5,
   with the checks that separate them.

## 1. Tasks, ids and the message path

| Task | CPU / id | Entry | Prio | Waits on (all −1 = forever) | Sends to | Tag |
|---|---|---|---:|---|---|---|
| REC_MAIN | 0 / 32 | `0x603df803` | 54 | flag 203 (word `0x60040c90`), pattern 0x1f | see router | V |
| REC_PREPRO | 0 / 33 | `0x603ef892` | 55 | polls mbx 76, 77 (timeout 0), else flag 58 (`0x60040b6e`) | route code 19 → mbx 171 (PRE_V1), else mbx 172 (PRE_I1) | V |
| REC_PRE_I1 | 0 / 77 | `0x603ef9bb` | 55 | mbx 172 (`0x60040e34`) | mbx 74 (REC_IMAGE) | V |
| REC_IMAGE | 0 / 31 | `0x603e5d57` | 54 | mbx 74 (`0x60040d70`); sem 22 briefly | mbx 73 (REC_FILE) | V |
| REC_FILE | 0 / 30 | `0x603e4236` | 54 | mbx 73 (`0x60040d6e`) | reply | V (file I/O via FILECLBK: I) |
| REC_PRE_V1 | 0 / 87 | `0x603ef94a` | 46 | mbx 171 (`0x60040e32`) | mbx 79 (REC_VIEW) | V |
| REC_VIEW | 0 / 108 | `0x603f26a1` | 26 | mbx 79 (`0x60040d7a`), then **sem 22** (`0x60040a20`) for the whole request | reply | V |
| REC_SOUND / REC_EXT / REC_PROGRESS | 0 / 34, 117, 129 | atlas | 55 / 26 / 55 | mbx 78 / 159 / 206 | – | V |
| REC_MAIN_CPU2 | 2 / 0x2012 | `0x603e28c6` | 55 | CPU2 flag `0x60041090` | mbx `0x600410c2` (0x2013) | V |
| REC_PRE_V1_CPU2 | 2 / 0x2013 | `0x603f07b9` | 26 | mbx `0x600410c2` | mbx `0x600410c4` (0x2014) | V |
| REC_VIEW_CPU2 | 2 / 0x2014 | `0x603f2b1f` | 25 | mbx `0x600410c4` | CPU0 flag 203 + shared slot | V |

**Message** (300 B) [V offsets, I meanings]: +52 u32 route code (0..27), +192 u16 status (0x1f01 = cancelled, set by
the receive wrapper when the abort word `0xa26a0a94` is set and +280 == 3), +194 u16 command (REC_IMAGE 0x1001..0x1013,
REC_VIEW 0x2002/0x2005/0x2006/0x2008), +206 u16 sub-mode, +280 u8 kind. Loops exit on an internal state 0x1f80..0x1fff
(8064..8191), for example 0x1fbc when a receive fails.

**Wrappers** [V]: `rec_msg_recv 0x603df9f1` and `rec_msg_send 0x603dfa41` (300 B, timeout −1) sit on
`0x603eeb57` / `0x603eeba4` (queue_recv / queue_send with trace calls). `rec_reply 0x603df97d` sends 12 B to the
reply mailbox at msg+32. `rec_wai_flg 0x603eec2e` logs 0x1e040002 on failure. Kernel names from their strings:
`wai_flg 0x60051143` ("OlyEvWt"), `wai_sem 0x6005168d` ("OlySmWt"), `sig_sem 0x60051762` ("OlySmSi").

**REC_MAIN as router** [V]:
- Flag bit 0x1 → `0x603dfb10`. It counts the messages in mbx 75 (`0x6003483e`, ref_mbx-like), receives each one
  (`0x603dfc7a`) and jumps on route code +52 through `0x6053adbc` (28 entries): to mbx 77 or 76 (REC_PREPRO), mbx 159
  (REC_EXT) or mbx 78 (REC_SOUND), or to CPU2. CPU2 is taken when +194 == 0x2008 and +206 == 2: the message is put in a
  shared slot (`0x603eee25`) and the CPU2 flag `0x60041090` bit 1 is set. Other codes are handled in place or get
  reply 0x1f10.
- Bits 0x4 / 0x8 → results from CPU2 in **shared slot 0 / 1**. The ring: index `0xa27409e8`, busy bytes
  `0xa27409e9..`, keys at `0xa27409ec` + 8·slot, records at `0xa27409fc` + 300·slot. Read by `0x603ef606`.
- **Only two cross-CPU slots.** When both are busy, `0x603ef3d3` logs 0x1e040002 at line 0x202 [V]. That limits
  bursts that use the CPU2 path [I].
- Senders into mbx 75: TAKE/API code at `0x602ac457`, `0x602ac864`, `0x602ad582`, `0x602ea5e2`.., and playback
  `0x60c73665`.. [V xrefs].

**REC_IMAGE body** [V]: receive → stage 60 → `0x603e137c` → `0x603e14ca` (holds **sem 22 only around**
`0x603e1fe1`, a copy of per-slot shot settings into the capture record) → `cap_type_switch 0x603e5fce` → work list
(synchronous; ISP waits `0x6035486d`; our CPU passes) → per-command tail through jump table `0x6053da74` (19 entries)
→ send to REC_FILE. So **REC_IMAGE and REC_VIEW exclude each other only for that short copy**. REC_VIEW holds sem 22
for its whole request, so a long Rec View request delays the *start* of the next job [V], not a running one.

**Stock capture history ring** `0x603e4e82(d0 stage, d1 code)` [V]: per CPU at `0xa26a0aa0` + 0x448·cpu
(uncached, in .bss). 256 entries of 4 B at +8, `{u8 task letter, u8 stage, u16 command}`, tail +0 / head +2,
plus a 16-entry overflow ring at +0x408 when re-entered. Letters by task id: F REC_FILE, I REC_IMAGE, M REC_MAIN,
P REC_PREPRO, S REC_SOUND, V REC_VIEW, E REC_EXT, v REC_PRE_V1, i REC_PRE_I1, p IMG_PRECON, B REC_PROGRESS,
m / z / x the three CPU2 REC tasks, ? any other. Stages seen: 60 / 62 (I, i, F begin/end), 91 / 93 (v, V), 101
(M dispatch), 40–45, 112, 123, 125. **No timestamps**: it gives order, not time. It is ideal crash context (§4).

## 2. Burst limits (job buffer pool)

| Limit | Where | On failure | Tag |
|---|---|---|---|
| 48 buffer records per job (88 B at job+6592) | slot finder `0x60350b05` in `0x603504a0` | returns 48; caller → **0x9ec3** | V |
| Pool heap: first-fit free list at pool+0x2c, ≤ 125 nodes of 16 B (pool+0x30..+0x800, `0x603503ca`) | `0x60350334` | 0 → 48 → 0x9ec3 | V |
| Pool must be registered: job+0x2a8c == 0x5000 (pool job+0x2a5c) or, with flag 0x10000, job+0x2ae0 == 0x15001 (pool job+0x2ab0) | `0x60350999` | 48 → 0x9ec3 | V |
| Non-pool buffers (flag 0x20000 clear) | `0x6034442b(0x13, …)` | job+0x2c36 = 1, 48 → 0x9ec3 | V |
| Job constructor malloc | `0x60353807` | 0x9ec3 | V |
| 3 request slots per job (0x1058 B at job+0x968, checked against job+0x3c38/3c3c/3c40) | `0x603510af` | **0x9ece** | V |
| 16-entry table | `0x60354b8c` (from `0x60354bb0`) | 0x9ece | V |
| REC working block 0x4da7d47 B (≈ 77.7 MiB), allocated once under sem 94 | `rec_mem_get 0x603eca94` ("rec_mem.c" line 0x1a1) | logs 0x1e00b002 | V |
| REC memory mode 0/1/2 chosen from settings (picture mode 0x9481, keys 0x810a, 0x949a, 0x9dd1, …); frees the working block | `rec_mem_config 0x603ecd3b`, entry `0x603ec9f3` (callers `0x602ed2ec`, MVR `0x6031fa5d`, playback `0x60c7347a`/`a2`) | – | V |

- **0x9ec3 means out of buffer memory or records. 0x9ece means no free request slot** [V sites; names I].
- A full-size 0x0302 buffer is 40,310,784 B (GRAIN_PORT), so the 77.7 MiB block holds about **two** at once [I that
  the job pools live in it].
- A forced Soft Focus job needs dev, 0x1061 and a new 0x1000. It fits only because stock frees the sources right
  after the blend wait [I].
- **Burst rule [I]:** the TAKE side (prio 25) can expose while REC_IMAGE is busy, but the REC queue behind it only
  drains one job at a time. A CPU pass in REC_IMAGE also starves REC_MAIN/REC_PREPRO/REC_PRE_I1 (next shot's routing
  and pre-processing) and FILECLBK (card writes of earlier frames). So the burst depth is set by the REC working
  memory, and stalls show as 0x9ec3 in the next job's allocations.

## 3. Where a CPU pass can run

| Option | Rec View | Next shot | Notes | Tag |
|---|---|---|---|---|
| **In REC_IMAGE's work list (today)** | Delayed only if its request is still queued in REC_MAIN/REC_PREPRO when the pass starts; REC_VIEW itself pre-empts | Routing and pre-processing of the next shot stall for the whole pass; exposure doesn't | The only point where the buffer is complete and JPEG not yet encoded (GRAIN_PORT) | V prio, I timing |
| Pass in REC_IMAGE, **yielding with dly_tsk** (v0.31a) | Rec View path can progress mid-pass | Next-shot routing can progress | Crashed on camera (§5). Don't, until §5 is answered | V camera |
| **Offload rows to another CPU, REC_IMAGE blocks on a semaphore** | as stock ISP waits | as stock ISP waits | Same shape as a stock ISP wait (`0x6035486d`): REC_IMAGE blocked, not busy. SYS_WDT runs, so no watchdog change is needed. CPU1 hosts FCS_IMG_2NDCPU_MAIN-type tasks. **Same exposure as v0.31a's yields:** other CPU0 tasks run mid-job. Settle §5 first | I |
| After REC_IMAGE (REC_FILE) | – | – | Too late: the output pass already encoded the JPEG | V (GRAIN_PORT) |

**Practical rule now [I]:** keep the pass inside the work list with no sleeps (v0.31b). Order the Rec View before the
pass: check with the history ring (§4) whether 'v'/'V' entries precede the shot's 'I' stage 60. If Rec View has to
wait for the pass, the only stock-safe fix is shortening the pass.

## 4. Crash and exception handling

**Vectors** [V]: per-CPU bases `0x60030000` (CPU0), `0x60050000` (CPU1), `0x600d0000` (CPU2).
- +0x08 is the NMI entry. It jumps to `0x60055250` / `0x600552c0` / `0x60055330`. Each stub saves d0–a3, SP, the
  stacked PSW and PC, and bus-monitor word (0x99700000+40), clearing 0x99700000, into a **0x40-B frame at
  `0x62ae8000` + 0x40·cpu**: +0 tid, +4 SP, +8 PSW, +0xc PC, +0x10 busmon, +0x20..+0x3c d0 d1 d2 d3 a0 a1 a2 a3.
  Then it calls `0x60059a9d`. +0x14..+0x1c are unused.
- +0x20 is the interrupt entry. It saves PSW/PC/SP to the same frame (+8/+c/+4) on **every interrupt**, then
  `0x600386f8` saves `[a2,a3,other]` (MDR/LIR/LAR included).
- The frames lie outside .bss (0x621caf00–0x62796888) and are not in the flash-shadow table of the `fmem` debug command (`0x60078620`: RAM 0x62898000, 0x62a78000,
  0x62ab8000) [V]. No stock code clears them at boot [V abs scan]. Whether DRAM keeps them through a watchdog reset is
  unknown [I].

**NMI handler `0x60059a9d`** [V]:
1. `wdt_hw_set(1)` at `0x60059aa4`: the reset now comes about 1 s later, whatever happens next.
2. It prints the CPU ("Genba Ha CPUn"), stores the current tid (TCB pointers `0x621a630c` / `0x626616c4` /
   `0x6267c09c`, +16) into frame +0, and prints the frame, NMIINTREG `(0x8900)` and SYSERRREG `(0x8044)`.
3. Cause branches: 0x8900 bit 0x1 EXT_NMI_INT, **bit 0x2 WATCHDOG_TIMEROVER** (`0x60059c63`), bit 0x4
   FATAL_SYSTEM_ERROR with 0x8044 bit 0x4 MISSA, 0x8 UNIMP, 0x20 MEM, 0x200 UNIMPEX.
4. It spins at `bra .` (`0x60059cec`).
- **Correction:** atlas `wdt_expiry_handler 0x60059c20` is mid-instruction (inside `mov imm32,a0` at `0x60059c1b`).
  The watchdog case is the 0x8900 bit-0x2 branch inside `0x60059a9d`. MISSA as "misaligned access" is [I] (name only).

**Bus-error interrupt `0x60056138`** ("ADDEC ERROR Hassei", registered by `0x600560a9` via `0x6006aa25`) [V]: prints
ADDR / R DATA / W DATA / STATUS from `0x9a000000` + 0x100·cpu, stores the tid in the frame, clears the status and
**returns**. Execution continues after a bad access [V]; a later fault is likely [I].

**Error logger `dbg_put 0x60061808`** (1900 callers; module wrapper `0x613e63e3(level, code, line, …)`, REC trace
`0x603e2c0d` / `0x603e2b2f`) [V]:
- State `0xa2682c34` (debug shell: off / put / sd / serial / sd-serial / reboot); boot sets 1 (put).
- Kind 1 errors: the first one fills a 64-B record at `0xa2715d28` (version from prop 0xc082 or 0x1100, RTC
  timestamp `0x600fb44e`/`0x600fb6bd`, code, args) and adds it to ICTLOG item 119 (`0x60061c4f` → `0x60023863`).
- Its reboot hooks `0x60054a1d` / `0x60054a20` / `0x60054a23` are empty (`retf`) in this build.

**What persists, and when** [V code; I for hardware behaviour]:

| Store | RAM | Persisted to | When | On a crash |
|---|---|---|---|---|
| NMI frames | `0x62ae8000`..`+0xc0` | nothing | – | RAM only; survival unknown |
| dbg_put first-error record | `0xa2715d28` (.bss) | via ICTLOG | – | lost (.bss zeroed at boot) |
| ICTLOG (120 items, 12-B descriptors at `0x61fb035c`; item 119 = dbg_put) | mirror `0x62de0000`, 1 MB, header "log" + checksum | **flash 0x47b00000** | only at `OlyHfwPower::startShutDown` (`0x607a9c2e` → `0x602f8a63` → `0x600239b4` → `0x6005bc79`) | not saved; boot reloads the mirror from flash (`0x60cc0e4a`, USRSTART5 `0x60191bd5`) and overwrites RAM |
| Console ring (8 KB) | `0xa2726c90`, head `0xa2728c90`, tail `…94`, mode `0xa2728c98` (1 linear, 2 wrap; set at boot from prop 0xf981 via `0x6002245c`) | card `C:\dbgterm\*.txt` (`0x600fa223`) | only in the power-off routine `0x6006109f`, and only if the mode ≠ 0 | lost |
| Boot-mode byte, flags | system register `0x98e00000` (bits 2..7 RTC-valid 42, bit 9, bit 10, top byte read-and-clear at boot `0x60066d2d`) | survives power-off [I] | stock shutdown / debug shell | **not ours to use** |

So **no stock path records a fatal fault anywhere that survives** [V]. ICTLOG item 119 from earlier, cleanly
shut-down sessions can be read from the RAM mirror at run time (read-only), but it holds software errors only, never
the NMI faults.

### 4.1 Crash-log design (built: `patches/crash_log`, see "As built" below)

**Goal:** on the next boot, the card holds the fault CPU, task, PC, cause and the last REC pipeline stages. No flash
writes, and no new code that runs before the fault except a few RAM stores.

**C1, fault-time hook at `0x60059aab`** (6 B `fc dc ec 74 07 60` = `mov 0x600774ec,a0`) [V bytes; no branch target
in `0x60059aab..0x60059ab0`, short and long scan]:
- It runs after `wdt_hw_set(1)`, so a bug in the stub can delay the reset by at most about 1 s. The reset still happens.
- Stub, with interrupts already masked, no calls and no locks, using d0, d1, a0, a1 only (scratch at this point):
  1. cpu = `(0x8050)`.
  2. Copy frame `0x62ae8000 + 0x40·cpu` (cached read on the same CPU is coherent), `(0x8900)`, `(0x8044)`.
  3. Copy CPU0's capture-history ring (0x448 B at `0xa26a0aa0`) and, if cpu ≠ 0, that CPU's ring too.
  4. Optional: copy our breadcrumb words from heap P, only if P lies inside the class-1 heap range.
  5. Write everything through the **uncached** alias to record R, then a checksum, then the magic last.
  6. Replay `mov 0x600774ec,a0`, then `jmp 0x60059ab1`.
- The stub must live in the base image or section 1, so an NMI during boot doesn't jump into an unloaded section.
- R: about 2.5 KB at `0xa2ae8100` (cached `0x62ae8100`), inside 0x62ae80c0..0x62de0000. The only static users of that
  range are the ICTLOG debug-shell commands `init` / `t_init` (`0x613ff19e` / `0x613ff1c9`), which fill it with 0x99
  [V abs scan]. Stock may still use it through base + offset, which a scan can't see [I].

**C2, next-boot writer:** in the existing half-press card hook in HLS_EVENT (the `GRAIND.BIN` / `MOVIE.BIN` path
through `ed_wfile`, camera-proven):
1. If R's magic and checksum are valid, write `EP7MOD/CRASH.BIN` (header, frame, registers, rings).
2. Then clear only the magic word.
Stock never reads R, so a stale record does no harm; the magic plus checksum rules out power-on garbage.

**Probe first (P-R, one flash, harmless):**
1. At the first half-press, write R's current magic and a counter to a card file, then set magic and counter + 1.
2. Power off and on normally: this shows whether DRAM survives a power cycle (expected: no).
3. Only a real fault shows survival through a watchdog reset. Without one, C1 + C2 can still ship:
   - if RAM isn't retained, they write nothing;
   - if it is, the next crash produces the file.

| Risk | Level | Mitigation |
|---|---|---|
| R used by stock code: our fault-time stores land on its data | Low | Happens only during a fault, right before the reset |
| The same, but our boot-time clear corrupts stock data | Very low | Clear only after magic + checksum matched |
| DRAM not retained through the watchdog reset | Unknown | Design degrades to "no file"; P-R shows it |
| Stub faults inside the NMI handler (bad P pointer) | Low | Range-check P; the 1 s watchdog is already armed |
| NMI before the stub's section is loaded | Low | Put the stub in base or section 1 |
| D-cache loses the record at reset | Low | Write R uncached only; history rings are already uncached |
| Card write blocks the UI | Low | Same path and size class as GRAIND.BIN; half-press only, never during capture |
| Flash writes | None | None are made; `0x98e00000` and ICTLOG are left alone |

**As built** (2026-11-14, `patches/crash_log`, [CRASH_LOG.md](CRASH_LOG.md); emulator-verified; released in v0.33; normal shooting camera-tested, the crash / restart path itself not yet seen on a camera). C1 and C2 as
designed, the probe P-R not built. What differs from the design above, and why:
- **One slot per CPU** (3 × 3,132 B at `0xa2ae8100`–`0xa2aea5b4`, not one record of 2.5 KB). Each CPU has its own NMI vector and
  frame, so NMIs can arrive on several CPUs; a CPU now writes only its own slot.
- **The first fault is kept.** The handler arms 1 s and spins, and the handler has a WATCHDOG_TIMEROVER branch, so the watchdog's
  own NMI can follow the real fault on the same CPU [I]. A slot that holds a record only counts later entries (count, cause, PC).
- **A busy mark before the copy** (`BRSH`, then `CRSH` last). A fault inside the stub re-enters the handler, which calls
  `wdt_hw_set(1)` again; without the mark the stub would run again and the reset could be pushed back each time [I]. With it, the
  second entry skips the stub.
- **C2's gate is the mark alone; the decoder checks the sum.** A record whose sum fails, or that is still marked busy, is written
  and labelled. With the sum as a gate those cases would give no file, the same as "RAM not kept".
- **The frame's tid (+0) is stale at the site** (the handler stores it after its first print), so the stub reads the TCB word
  itself, as the handler does next (`0x621a630c` / `0x626616c4` / `0x6267c09c`, +16) [V].
- **No register had to be scratch.** d0 / d1 / a1 are saved on the stack (28 B, less than the 32 B the handler's next call writes
  there) and given back; a0 comes from the replayed instruction; the flags from repeating `wdt_hw_set`'s final `cmp 0,d0`.
- **More context than listed**, all from constant addresses or checked pointers: 512 B of the interrupted stack, the TCB pointer,
  the bus-window modes, this CPU's address-decode error registers, the REC abort word and working-block pointer, the system-down
  code, a build tag.
- **C2 hooks `sd_go`'s `call sd_load`** (`0x605b748f`), not `sd_back`: that call runs once per power-on by construction (the state
  word is spent just before it), so no latch is needed, and "card table loaded" stands for "the `EP7MOD` folder exists".
- **New in §4:** software system-down requests (`0x600589d9` → `0x600589f3`: Heap Destroy, another CPU's ADDEC error, ARM / SCPU /
  WiFi / BLE reboots) arm the 1 s watchdog and spin on CPU0 **without** entering `0x60059a9d` [V]. The line "every fatal exception
  and the watchdog arrive at the NMI handler" holds for CPU exceptions and the watchdog, not for these. And the debug-shell fill
  covers exactly `0x62ae80c0`–`0x62de0000` (`memset(…, 0x99, 0x2f7f40)`), then reloads only the mirror at `0x62de0000` [V].

## 5. The v0.31a crash (bright daylight, ≈2 s after the shot)

**Facts:**
- v0.31a = v0.31 + `dly_tsk(1)` after every 32nd unlock in halation and grain + the BUNDLES loader retry.
- v0.31b removed the yields, kept the retry and raised the watchdog to 30 s; on the same scene, no crash
  (WORKLOG, camera) [V].
- A 10 s watchdog can't fire at 2 s. The NMI handler arms a 1 s reset (§4), so the fault happened ≈1 s after the shot
  [V handler, I timing].
- Yields are the only new way for CPU0 tasks at prio ≥ 54 to run mid-job. Stock ISP waits let them run too, but only
  while the hardware owns the buffers [I].
- Bright frames start long halation row passes about 1 s after the shot, so they yield early. Dark frames yield
  mainly later, in grain [I, from HALATION_RED §20 costs].

Ruled out:
- **Window/cache state:** every halation segment maps, flushes, restores the mode and unlocks before `hl_unl` yields
  (`hl_seg`) [V our code].
- **Loop registers:** no `setlb` in our code; the kernel entry saves MDR/LIR/LAR [V].
- **SYS_WDT running:** it only kicks [V].

| Rank | Hypothesis | Confidence | Why |
|---:|---|---|---|
| 1 | **Our shared grain record is changed under a running pass.** Another job's capture-chain hooks (flag hook, `gc_gs` / `hl_lvl` writing +95/+96, counters at +100) run in a task released by the yield: a Rec View or next-shot job routed through REC_MAIN/REC_PREPRO | Medium | Those jobs can only reach our hooks mid-pass if REC_MAIN (54) / REC_PREPRO (55) run, i.e. only with yields |
| 2 | **Stock REC state changed mid-job** by REC_MAIN handling a queued message (CPU2 Rec View result slots, end of Rec View, return to LV), up to `rec_mem_config` freeing the REC working block while our buffers live in it | Medium-low | Same release mechanism; use-after-free gives MEM / bus errors |
| 3 | **HLS_EVENT (54) work at a yield:** loader retry, half-press hooks, card I/O through FILECLBK, heap free/malloc of P blocks | Low-medium | New in v0.31a too, but needs a half-press |
| 4 | **REC_IMAGE stack (0x3700) overflow** with the dly_tsk dispatch frame at the deepest point | Low | Interrupts already nest there without crashing |
| 5 | Window/cache changed by another task during a yield | Low | Ruled out for halation; check gc_grain's three sites the same way |

**Checks that discriminate:**

| Check | Kind | Separates |
|---|---|---|
| Field audit: which grain-record fields our per-job hooks write vs. which `gc_grain` / `hl_run` read after the first `hl_unl` (pointers, lengths, state) | static, cheap | 1 yes/no |
| Emulator: v0.31a pass with a `dly_tsk` stub that, on call N, runs a second (Rec View-sized) job through the real blend hook; compare the record and the pass result | emulator | 1 |
| Emulator: minimum SP over the work list + our frames + one dispatch frame, against the 0x3700 stack | emulator | 4 |
| Camera, v0.31a: bright scene with Rec View Off | camera | 1/2 (gone) vs 3/4 |
| Camera, v0.31a: 2 s self-timer, hands off (no half-press after the shot) | camera | 3 |
| Camera, v0.31a with yields in grain only | camera | early-yield timing (1, 2) vs any yield |
| Crash log (§4.1) on v0.31a: fault CPU, tid, PC, cause (MISSA / MEM / bus) and the history ring between yields (letters M, P, i, v, V, F) | camera | which task faulted and which REC tasks ran: 1 vs 2 vs 3 |

## 6. Open items

- Whether DRAM, in particular R and the NMI frames, survives a watchdog reset (probe P-R; then the next real fault).
- Whether 0x62ae80c0..0x62de0000 has runtime users reached through base + offset (watch R for changes in a debug
  build, or emulate a full boot).
- Order of the Rec View ('v', 'V') entries against the shot's REC_IMAGE stage 60, from a history-ring dump on a normal
  shot (no crash needed).
- Sizes of the job pools inside the REC working block (who registers pool ids 0x5000 / 0x15001).
- REC_FILE's file calls (assumed FILECLBK RPC, not traced).
- Which CPU each static task runs on (CPU0 assumed for table `0x600389d0`).
- Meanings of `0x98e00000` bit 10 (read by dbg init `0x600617c1`, set only by a debug command) and of history stages
  40–45, 112, 123, 125.
