# Crash record (`EP7MOD/CRASH.BIN`)

Layer `patches/crash_log` (`cl.s.in`, `build.py`, `verify.py`), decoder `tools/ep7_crash.py`. Design: [RE_CAPTURE.md](RE_CAPTURE.md) §4
and §4.1. Reliability tooling: it changes nothing a photo or a menu can show. Built and emulator-verified; released in v0.33; normal shooting camera-tested, the crash / restart path itself not yet seen on a camera.
[V] = read in code or shown in the emulator. [I] = inference.

**What it is for.** Stock firmware keeps nothing when it faults: the NMI handler prints to a console nobody sees, and the camera
resets about 1 s later. With this layer the fault leaves a record in RAM, and the first half-press after the restart writes it to the
card. **The owner does nothing**: keep using the camera, then copy `EP7MOD/CRASH.BIN` off the card.

## When

| Step | Where | When it runs |
|---|---|---|
| **C1** `cl_nmi` | `jmp` at `0x60059aab` in the NMI handler `0x60059a9d`, right after its `wdt_hw_set(1)` | Only inside a fault (fatal exception, watchdog, external NMI). 9,300 instructions on CPU0, 9,900 on CPU1 / CPU2 [V emulator]: a small part of the 1 s before the reset [I timing]. A later entry on a CPU that already has a record: 36 |
| **C2** `cl_first` | `jmp` at the card loader's `call sd_load` (`sd_go`, `0x605b748f`) | Once per power-on: the half-press on which `BUNDLES.BIN` loads. No card or no `EP7MOD` folder: never. No record: three RAM reads, then nothing |

Nothing runs at boot, and nothing runs in the capture path.

## What is saved

One slot of 3,132 B per CPU (the file is the three slots, 9,396 B; a slot without a record is zeros). A CPU writes only its own slot,
so NMIs on several CPUs can't overwrite each other. Layout: the constants at the top of `tools/ep7_crash.py`.

| Part | Bytes | Content |
|---|---:|---|
| Marks | 8 | `CRSH` = complete (written last), `BRSH` = started and not finished; the sum of the body |
| Later entries | 16 | NMI entries on this CPU while the record waited: count, and the last one's cause and PC. **The first fault is kept** (see below) |
| Header | 84 | Version, CPU, flags; NMIINTREG `(0x8900)` and SYSERRREG `(0x8044)`; task id and TCB pointer; sections loaded; card-table handle, P and the word at P+1000; REC abort word and working-block pointer; the three bus-window modes; this CPU's address-decode error registers (ADDR, R DATA, W DATA, STATUS); the system-down code `(0x8ff000b0)`; a tag of the firmware build |
| NMI frames | 192 | All three 0x40-B frames at `0x62ae8000`: SP, PSW, PC, bus-monitor word, d0–d3, a0–a3. The faulting CPU's is exact; the others are what that CPU could read [I: other CPUs' caches] |
| History ring, CPU0 | 1,096 | The stock capture ring at `0xa26a0aa0`: 256 × {task letter, stage, command} |
| History ring, own | 1,096 | The faulting CPU's ring when it isn't CPU0, else zeros |
| Grain record | 128 | Ours (pointer at heap P+1000): stage, guard, level, rows done, buffer and window fields. Zeros when a pointer in the chain fails its check |
| Stack | 512 | From the frame's SP: the return addresses of the interrupted task |

**First fault wins.** A slot that already holds a record is not rewritten. The handler arms a 1 s watchdog and spins, so a second NMI
(the watchdog's own) can follow the real fault on the same CPU; it must not replace the record of the fault that matters. It is
counted instead.

**A fault inside the stub can't loop.** The slot is marked `BRSH` before anything is copied. A second entry on that CPU sees the
mark and goes straight on to the stock handler.

**Every pointer the stub follows is checked first** (the camera faults on a misaligned access, and a fault here would cost the
record): the card-table handle against the class-1 pool as `gc_pp` does, the grain-record pointer against the class-0 pool
(`0xa1bce7c0`–`0xa1bd6d40`, 128 B inside, 4-aligned), the TCB pointer and the SP for alignment and for lying in the first 128 MB of
RAM. The TCB read is the one the stock handler makes itself a few instructions later.

## Reading it

```
.venv/bin/python -I tools/ep7_crash.py CRASH.BIN --spec generated/crash_log/edits.json
```

`--spec` is the `edits.json` of the build that was on the camera. With it the decoder names our own code (`g2_blk+0x5c`) and checks
the build tag; without it, it still says whether an address is in one of our claims ([CODE_SPACE_MAP.md](CODE_SPACE_MAP.md)) or in
stock code, with the nearest symbol of [atlas.json](atlas.json).

- **cause**: `EXT_NMI`, `WATCHDOG_TIMEROVER`, or `FATAL_SYSTEM_ERROR` with `MISSA` / `UNIMP` / `MEM` / `UNIMPEX`.
- **task**: id and name on that CPU (`31 REC_IMAGE`). A negative id means no task (boot, idle or an interrupt).
- **PC / SP / PSW / registers**, and for a0–a3 where they point when that is code.
- **stack**: words that are code addresses, with their symbols: the call chain, innermost first.
- **history**: the last 40 ring entries, oldest first. Letters as RE_CAPTURE §1 (`I` REC_IMAGE, `F` REC_FILE, `M` REC_MAIN, `v` / `V`
  the Rec View tasks, …). `I 60` without a later `I 62` means the shot was still in REC_IMAGE.
- **grain record** by field, with one line of verdict: before the pass, inside it (rows done of rows), or finished.
- Three states of a slot:
  - `complete, checksum ok`;
  - `CHECKSUM MISMATCH`: the mark survived but some bytes changed between the fault and the write. The fields are printed
    anyway; treat single values with care;
  - `INCOMPLETE`: the stub started and did not finish. That points at the stub itself, or at a second fault inside it.

A watchdog record has the PC where that CPU was stuck. A record with `EXT_NMI` after pulling the battery with the camera on would be
expected [I: what drives the external NMI isn't known].

## What is not known

- **Does RAM survive the watchdog reset?** Not proven. The record is at `0xa2ae8100` (uncached), outside .bss and outside every
  region boot is known to clear [V scan, RE_CAPTURE §4]. Indirect evidence that heap RAM outlives a restart: the stale-marks bug of
  0.30b9 ([AP_CUSTOM.md](AP_CUSTOM.md)) [I]. **If RAM is not kept, no file appears and nothing else changes.**
- **Does stock use this RAM?** The only code that names `0x62ae80c0`–`0x62de0000` is the ICTLOG debug-shell `init` / `t_init`, which
  fills exactly that range with 0x99 and reloads the log mirror at `0x62de0000` [V]. A user through base + offset can't be ruled
  out [I]. Its effect would be a `CHECKSUM MISMATCH` record, which is why such a record is written and not dropped.
- **Faults that don't reach the NMI handler.** Software "system down" requests (`0x600589d9` → CPU0 handler `0x600589f3`: Heap
  Destroy, another CPU's ADDEC error, …) arm the same 1 s watchdog and spin without passing `0x60059a9d` [V]. They leave a record
  only if the watchdog's expiry is delivered as an NMI before the reset [I]; the header's system-down code then says which it was.
- **A fault before section 1 is loaded** jumps into RAM that doesn't hold the stub yet. Stock firmware would have to fault during
  the first moments of boot for that [I].
- **Other CPUs:** P's handle and the other CPUs' frames are read through this CPU's cache, so on CPU1 / CPU2 they can be stale. The
  flags in the header say what was read.

## As built

- **Code:** `cl_nmi` (625 B) and `cl_first` (228 B) + the path string, 875 B at `0x601e01ec` in section 1: the body of r2's
  `gc_grain`, unused since grain_g2 ([CODE_SPACE_MAP.md](CODE_SPACE_MAP.md)). The NMI can come before later sections load, so C1
  can't live anywhere else; C2 sits beside it.
- **C1 is transparent to the handler [V emulator]:** no call, no lock, no `mul` / `div` / `setlb`; 28 B of stack below the
  handler's sp (its own next call writes 32 B there). At `0x60059ab1` all eight registers, MDR, LIR, LAR and the PSW equal the stock
  handler's. No register needed to be scratch: d0, d1 and a1 are saved and given back, a0 is set by the replayed instruction, and
  the flags are restored by repeating `wdt_hw_set`'s last `cmp 0,d0`.
- **C2:** runs the displaced `call sd_load` on `sd_gate`'s frame, then checks for a card table and a mark. With a record: a
  class-2 heap copy (slots without a record zeroed), **each mark cleared in RAM, then** `fopen("C:\EP7MOD\CRASH.BIN", "w")`,
  one `fwrite`, `fclose`, `free`. A failure in the writer can't repeat on the next boot. The latest record replaces the file.
  `sd_load`'s d0 / d1 / a0 / a1 are given back, so the hooks after it see what they saw before.
- **The gate is the mark, not the sum.** The design asked for mark and sum; the sum is checked by the decoder instead, so a
  damaged or unfinished record reaches the card with a label. With mark and sum as the gate, those two cases would look the same
  as "RAM not kept": no file.
- **Build checks:** stock bytes of the handler, of `wdt_hw_set`'s tail, the three TCB words, the frame layout, the ring, the two
  pools, the file calls' `ret` forms; the handler decodes linearly with the site as whole instructions and no branch into it; the
  hole holds r2's bytes (hash) and no reference into the claim (abs32 on four aliases, call / calls / jmp encodings; four pinned
  false positives).
- **Verifier** (`patches/crash_log/verify.py BASE NEW PKGDIR`, BASE = the chain without the layer): C1 36 cases, C2 10, the
  decoder 12, 7,575 word / halfword accesses of our code all aligned, P (package == the emulated image, restore == stock, only our
  three sites differ from BASE): all pass. The cases are listed in its docstring.
- **Build:** `patches/v032/build.py releases/v0.31d/edits.json --out generated/crash_log/edits.json --version 0.33 --extra
  grain_g2=patches/grain_g2/build.py --extra crash_log=patches/crash_log/build.py`; package `generated/crash_log/rel/patched.pkg.bin`
  `4e50cdf4…6528`, restore `963f4dfe…2327`.

**Camera check:** none beyond "the camera behaves as before". The next unplanned restart is the test.
