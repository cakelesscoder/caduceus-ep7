# New atlas entries from the crash record layer (patches/crash_log, docs/CRASH_LOG.md). E-P7 1.1.
# Same structure as atlas_data.py: E(addr, name, kind, subsystem, conf, sig, notes, source). Merged by gen.py.
# Not repeated: nmi_handler 0x60059a9d, nmi_hook_site 0x60059aab (with the layer: `jmp cl_nmi; nop`), nmi_frame 0x62ae8000,
# crashlog_area_cand 0x62ae8100 (the record: crash_record below, on the uncached alias), rec_history 0xa26a0aa0, wdt_hw_set
# 0x600219ab, addec_irq_handler 0x60056138, window_mode_array 0xa2716034, malloc / free, fopen / fwrite / fclose.
r = 'rtos'
SRC = 'docs/CRASH_LOG.md'

# ---- stock ----
E(0x600589d9, 'sys_down_request', 'func', r, 'V', 'd0 = code; retf [],0', 'Stores the code at 0x8ff000b0 and writes 1 to 0x99200400 (an interrupt for CPU0). The NMI handler calls it on CPU1 (code 1) and CPU2 (code 4), so CPU0 stops too', SRC)
E(0x600589f3, 'sys_down_irq', 'func', r, 'V', '', 'CPU0 side of sys_down_request: by the code at 0x8ff000b0, 1 / 4 spin at once (0x60058b8b); 3 "Heap Destroy", 2 / 5 "CPUn ADDEC", 0x10 "ARM" (+ its registers from 0x8ff00b80..), 0x30 SCPU, 0x20 COMMON, 0x50 WiFi, 0x60 BLE print, then wdt_hw_set(1) and spin. This path never enters nmi_handler', SRC)
E(0x8ff000b0, 'sys_down_code', 'data', r, 'V', 'u32', 'Why CPU0 was told to stop (sys_down_request). 0x8ff00000.. is RAM shared by the CPUs (lock words 0x8ff00040, 0x8ff006fc)', SRC)
E(0x621a630c, 'cur_tcb_cpu0', 'data', r, 'V', 'pointer; task id = s16 at +16', 'Current TCB of CPU0, as nmi_handler and addec_irq_handler read it. A negative id: no task', SRC)
E(0x626616c4, 'cur_tcb_cpu1', 'data', r, 'V', 'pointer; task id = s16 at +16', 'Current TCB of CPU1', SRC)
E(0x6267c09c, 'cur_tcb_cpu2', 'data', r, 'V', 'pointer; task id = s16 at +16', 'Current TCB of CPU2', SRC)
E(0xa1bce7c0, 'heap_pool_class0', 'data', r, 'V', '0xa1bce7c0..0xa1bd6d40', 'malloc <= 128 B (bounds in free 0x600227b6 / 0x600227be). Our 128-B grain record lives here', SRC)
E(0x9a000008, 'addec_regs', 'data', r, 'V', 'u32 ADDR, R DATA, W DATA, STATUS at +8..+0x14; + 0x100 per CPU', 'Address-decode error registers; plain reads. The handler clears through the word at +0 (or 4, then and ~2). An error taken with interrupts masked stays here', SRC)
E(0x613ff19e, 'ictlog_dbg_init', 'func', r, 'V', 'debug shell `init`; `t_init` 0x613ff1c9', 'memset(0x62ae80c0, 0x99, 0x2f7f40): everything between the NMI frames and the ICTLOG mirror 0x62de0000; mode byte 0x6233b791 = 1 (t_init: 2); then ictlog_boot_load, which touches the mirror only. The one stock user of that RAM by address', SRC)
E(0x605b748f, 'sd_go_load_call', 'site', 'fileio', 'V', 'call sd_load,[d2,d3,a2,a3],36 (cd 08 00 f0 24), then sd_gout: ret [d2,d3,a2,a3],36', 'Ours (card loader v3, sec 3): the one load attempt of a power-on (state word 0x622cbcc2 spent just before; ap_boot re-arms a failed one up to 4 times). crash_log: `jmp cl_first`', SRC)

# ---- ours ----
E(0x601e01ec, 'cl_nmi', 'func', r, 'V', 'jmp from nmi_hook_site; ends `mov 0x600774ec,a0; jmp 0x60059ab1`', 'Ours (crash_log, sec 1, in r2\'s unused gc_grain body 0x601e01eb..0x601e0560): the fault record into this CPU\'s slot of crash_record. No call; 28 B of stack; every register, MDR, LIR, LAR and the flags as the stock handler has them at 0x60059ab1', SRC)
E(0x601e045d, 'cl_first', 'func', 'fileio', 'V', 'jmp from sd_go_load_call, on sd_gate\'s frame; ends ret [d2,d3,a2,a3],36', 'Ours (crash_log): `call sd_load`, then with a card table and a marked slot: class-2 heap copy, marks cleared, C:\\EP7MOD\\CRASH.BIN written (fopen w / fwrite / fclose), free. sd_load\'s d0 / d1 / a0 / a1 given back', SRC)
E(0xa2ae8100, 'crash_record', 'data', r, 'V', '3 slots x 0xc3c B (one per CPU), format tools/ep7_crash.py', 'Ours: +0 mark (CRSH complete, BRSH busy), +4 sum, +8 later NMI entries, +0x18 header, +0x6c NMI frames, +0x12c CPU0 ring, +0x574 own ring, +0x9bc grain record, +0xa3c stack. Uncached; whether it survives the watchdog reset is not proven', SRC)
