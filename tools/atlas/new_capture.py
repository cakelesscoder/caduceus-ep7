# New atlas entries from docs/RE_CAPTURE.md (capture task chain, burst limits, crash/exception handling).
# Same structure as atlas_data.py: E(addr, name, kind, subsystem, conf, sig, notes, source).
# Merge by exec'ing after atlas_data.py (E and S come from there).
# Not repeated (already in the atlas): nmi_handler 0x60059a9d, task_REC_* entries, REC_VIEW 0x603f26a1, cap_type_switch
# 0x603e5fce, buf_alloc 0x60350560, wdt_on 0x6005b232, cpu2_task_desc_table 0x6003d344.
# CORRECTION for the lead: atlas 'wdt_expiry_handler' 0x60059c20 is mid-instruction (inside `mov imm32,a0` at 0x60059c1b,
# within nmi_handler 0x60059a9d). The watchdog case is the (0x8900) bit-0x2 branch at 0x60059c63, added below as
# 'nmi_wdt_branch'. Please fix or drop the 0x60059c20 entry in atlas_data.py.
c = 'capture'
r = 'rtos'
p = 'pipeline'
SRC = 'docs/RE_CAPTURE.md'

# ---- exceptions, watchdog, loggers ----
E(0x60059c63, 'nmi_wdt_branch', 'code', r, 'V', 'btst 2,(0x8900)', 'WATCHDOG_TIMEROVER case inside nmi_handler 0x60059a9d (replaces mis-addressed wdt_expiry_handler 0x60059c20)', SRC + ' §4')
E(0x60059aab, 'nmi_hook_site', 'code', r, 'V', '6 B fc dc ec 74 07 60 (mov 0x600774ec,a0)', 'After wdt_hw_set(1) at 0x60059aa4 (reset ~1 s later). No branch target in span. Crash-log hook C1 candidate', SRC + ' §4.1')
E(0x60030000, 'vec_base_cpu0', 'table', r, 'V', '+0x08 NMI -> 0x60055250, +0x20 IRQ entry -> 0x600386f8', 'CPU1 base 0x60050000 (NMI 0x600552c0), CPU2 0x600d0000 (NMI 0x60055330)', SRC + ' §4')
E(0x60055250, 'nmi_stub_cpu0', 'func', r, 'V', 'saves regs to frame, calls 0x60059a9d, rti', 'CPU1 0x600552c0, CPU2 0x60055330', SRC + ' §4')
E(0x600386f8, 'irq_entry', 'func', r, 'V', 'movm [a2,a3,other]', 'Kernel interrupt entry; saves MDR/LIR/LAR. Vector stubs also write PSW/PC/SP to the NMI frame on every IRQ', SRC + ' §4')
E(0x62ae8000, 'nmi_frame', 'data', r, 'V', '3 x 0x40 B per CPU: +0 tid, +4 SP, +8 PSW, +0xc PC, +0x10 busmon, +0x20..+0x3c d0..a3', 'Outside .bss; not cleared at boot [V scan]; survival through WDT reset unknown', SRC + ' §4')
E(0x62ae8100, 'crashlog_area_cand', 'data', r, 'I', '~2.5 KB in 0x62ae80c0..0x62de0000', 'Only static users: ICTLOG debug init/t_init fill (0x613ff19e/0x613ff1c9). Proposed crash record R', SRC + ' §4.1')
E(0x60056138, 'addec_irq_handler', 'func', r, 'V', '', 'ADDEC (bus/address decode) error: prints ADDR/RDATA/WDATA/STATUS from 0x9a000000+0x100*cpu, clears, returns. Registered by 0x600560a9 via 0x6006aa25', SRC + ' §4')
E(0x600219e3, 'sysreg_bit10_get', 'func', r, 'V', '-> d0 = (0x98e00000) bit 10', 'Read by dbg init 0x600617c1; set only via debug shell 0x613c4d91 [meaning I]', SRC + ' §4')
E(0x60066d2d, 'bootmode_byte_take', 'func', r, 'V', '-> d0 top byte of 0x98e00000, then cleared', 'Persistent system register (RTC domain I); setter 0x60066d14 (from 0x60192936). Not for our use', SRC + ' §4')
E(0x60061808, 'dbg_put', 'func', r, 'V', 'd0 code, d1 kind, ...; 1900 callers', 'Central error logger. Kind 1: first-error record 0xa2715d28 + ICTLOG item 119; reboot hooks 0x60054a1d/20/23 are empty retf', SRC + ' §4')
E(0xa2682c34, 'dbg_put_state', 'data', r, 'V', 'u32: off/put/sd/serial/sd-serial/reboot', 'Boot sets 1 (put) at 0x60061797', SRC + ' §4')
E(0xa2715d28, 'dbg_first_error', 'data', r, 'V', '64 B record', 'Ver (prop 0xc082 or 0x1100), RTC time, code, args. .bss, lost on reset', SRC + ' §4')
E(0x613e63e3, 'mod_err_log', 'func', r, 'V', '(level, code, line, ...)', 'REC/module error wrapper -> dbg_put; codes 0x1e0xxxxx in REC code', SRC + ' §1')
E(0x603e2c0d, 'rec_trace', 'func', c, 'V', '(mode|code, file/line, ...)', '"%s(%s):%d mode[%04x] TID:%d" trace (83 callers); sibling 0x603e2b2f', SRC + ' §1')
E(0x600224ff, 'dbg_printf', 'func', r, 'V', 'a0 fmt', 'Console print -> 0x6002247c -> DBG_OUT queue (0x60040fdc) + tee into the console ring', SRC + ' §4')
E(0x6002245c, 'dbgring_mode_set', 'func', r, 'V', 'd0 0/1/2', 'Sets 0xa2728c98; boot passes prop 0xf981 (0x6005d661)', SRC + ' §4')
E(0xa2726c90, 'dbgring_buf', 'data', r, 'V', '8 KB; head 0xa2728c90, tail 0xa2728c94, mode 0xa2728c98', 'Console tail ring (.bss)', SRC + ' §4')
E(0x600fa223, 'dbgring_save_card', 'func', r, 'V', '', 'Writes ring to C:\\dbgterm\\<time>.txt; only caller power-off 0x6006109f', SRC + ' §4')
E(0x6006109f, 'power_off_seq', 'func', r, 'V', 'd0 kind, d1 ms', 'Shutdown tail: dbgring save, ... ends in boot-ROM 0x47000b0a. Callers 0x601e729e, 0x602f7729, 0x613cae2a', SRC + ' §4')
E(0x60cc0e4a, 'ictlog_boot_load', 'func', r, 'V', '', 'From USRSTART5 0x60191bd5: flash 0x47b00000 (1 MB) -> RAM 0x62de0000; header "log" + checksum, else reinit 0x60023c61', SRC + ' §4')
E(0x62de0000, 'ictlog_mirror', 'data', r, 'V', '1 MB: +0 checksum, +4 u16 1, +0x400 "log", items from +0x440', '120 item descriptors at 0x61fb035c (12 B)', SRC + ' §4')
E(0x600239b4, 'ictlog_flash_save', 'func', r, 'V', '', 'Checksum + 0x6005bc79 write to 0x47b00000. Only via 0x602f8a63 from OlyHfwPower::startShutDown 0x607a9c2e', SRC + ' §4')
E(0x60023863, 'ictlog_add', 'func', r, 'V', 'd0 item, d1 len, a0 data', 'Needs state 8 (0x6233b790). dbg_put uses item 119, 60 B (0x60061c4f)', SRC + ' §4')

# ---- kernel calls (names from strings) ----
E(0x60051143, 'wai_flg', 'func', r, 'V', '"OlyEvWt"', '72 callers', SRC + ' §1')
E(0x6005168d, 'wai_sem', 'func', r, 'V', '"OlySmWt"', '', SRC + ' §1')
E(0x60051762, 'sig_sem', 'func', r, 'V', '"OlySmSi"', '', SRC + ' §1')
E(0x6003483e, 'ref_mbx_count', 'func', r, 'I', 'd0 mbx, a0 &info -> count at info+4', 'Used by REC_MAIN drain 0x603dfb10', SRC + ' §1')

# ---- REC task chain ----
E(0x603df9f1, 'rec_msg_recv', 'func', c, 'V', 'd0 mbx, a0 msg (300 B); timeout -1', 'Sets +192 = 0x1f01 when abort word 0xa26a0a94 set and +280 == 3', SRC + ' §1')
E(0x603dfa41, 'rec_msg_send', 'func', c, 'V', 'd0 mbx, a0 msg (300 B); timeout -1', '', SRC + ' §1')
E(0x603df97d, 'rec_reply', 'func', c, 'V', 'd0 status, a0 msg', '12-B reply to mailbox at msg+32', SRC + ' §1')
E(0x603eec2e, 'rec_wai_flg', 'func', c, 'V', 'd0 flag, d1 pattern', 'Logs 0x1e040002 line 219 on failure', SRC + ' §1')
E(0x603dfb10, 'rec_main_drain', 'func', c, 'V', 'a0 msg buf', 'Counts mbx 75, receives each, routes by +52 via jtab 0x6053adbc (28): mbx 76/77, 159, 78, or CPU2 slot + flag 0x60041090', SRC + ' §1')
E(0x6053adbc, 'rec_main_route_jtab', 'table', c, 'V', '28 x u32', 'Route code (+52) -> handler', SRC + ' §1')
E(0x603ef3d3, 'xcpu_slot_find', 'func', c, 'V', '', '2-slot cross-CPU ring (index 0xa27409e8); both busy -> 0x1e040002 line 0x202', SRC + ' §1')
E(0x603ef606, 'xcpu_slot_take', 'func', c, 'V', '', 'Copies slot record 0xa27409fc + 300*slot, calls its handler', SRC + ' §1')
E(0xa27409e8, 'xcpu_slot_ring', 'data', c, 'V', 'u8 index, busy bytes +1.., keys 0xa27409ec+8n, records 0xa27409fc+300n', 'CPU0 <-> CPU2 REC messages', SRC + ' §1')
E(0x603e14ca, 'rec_image_prep', 'func', c, 'V', '', 'Called by REC_IMAGE before cap_type_switch; holds sem 22 (0x60040a20) only around 0x603e1fe1 (shot settings copy)', SRC + ' §1')
E(0x6053da74, 'rec_image_cmd_jtab', 'table', c, 'V', '19 x u32 (cmd 0x1001..0x1013)', 'REC_IMAGE per-command tail', SRC + ' §1')
E(0x603e4e82, 'rec_history_add', 'func', c, 'V', 'd0 stage, d1 cmd', 'Per-CPU ring 0xa26a0aa0 + 0x448*cpu', SRC + ' §1')
E(0xa26a0aa0, 'rec_history', 'data', c, 'V', '+0 tail, +2 head, +8 256 x {u8 task letter, u8 stage, u16 cmd}', 'No timestamps; .bss. Stages 60/62 begin/end, 91/93 view, 101 REC_MAIN', SRC + ' §1')
E(0x603e28c6, 'REC_MAIN_CPU2', 'func', c, 'V', 'CPU2 task 0x2012, prio 55', 'Waits CPU2 flag 0x60041090; -> mbx 0x600410c2', SRC + ' §1')
E(0x603f07b9, 'REC_PRE_V1_CPU2', 'func', c, 'V', 'CPU2 task 0x2013, prio 26', '-> mbx 0x600410c4', SRC + ' §1')
E(0x603f2b1f, 'REC_VIEW_CPU2', 'func', c, 'V', 'CPU2 task 0x2014, prio 25', 'Results back to CPU0 flag 203 + slot', SRC + ' §1')
E(0x60040c90, 'rec_main_flag_id', 'data', c, 'V', 'u16 = 203', 'Bits 0x1 mbx 75, 0x2 local, 0x4/0x8 CPU2 slot 0/1', SRC + ' §1')
E(0x60040d6e, 'rec_mbx_ids', 'data', c, 'V', 'u16 73..79', '73 REC_FILE, 74 REC_IMAGE, 75 REC_MAIN, 76/77 REC_PREPRO, 78 REC_SOUND, 79 REC_VIEW; 0x60040e32 171 PRE_V1, 0x60040e34 172 PRE_I1, 0x60040e1a 159 REC_EXT', SRC + ' §1')
E(0x60040a20, 'recview_sem_id', 'data', c, 'V', 'u16 = 22', 'REC_VIEW holds it per request; REC_IMAGE briefly', SRC + ' §1')

# ---- burst limits ----
E(0x603504a0, 'buf_alloc_core', 'func', p, 'V', 'size, flags, job, desc -> slot or 48', '48 records at job+0x19c0; flag 0x20000 pool (0x10000 selects job+0x2ab0 else job+0x2a5c), else 0x6034442b', SRC + ' §2')
E(0x60350334, 'pool_first_fit', 'func', p, 'V', '', 'Free list pool+0x2c; nodes 0x603503ca (<=125 x 16 B)', SRC + ' §2')
E(0x60350843, 'buf_free', 'func', p, 'V', 'd0 slot (<48), a? job', '', SRC + ' §2')
E(0x603510af, 'job_req_slot_get', 'func', p, 'V', '', '3 x 0x1058 B at job+0x968; none free -> 0x9ece', SRC + ' §2')
E(0x603eca94, 'rec_mem_get', 'func', c, 'V', '', 'Allocates the 0x4da7d47-B REC working block (0xa26a1ca8) under sem 94; "rec_mem.c"', SRC + ' §2')
E(0x603ecd3b, 'rec_mem_config', 'func', c, 'V', '', 'Picks memory mode 0/1/2 from settings, frees the working block. Entry 0x603ec9f3 (callers 0x602ed2ec, 0x6031fa5d, 0x60c7347a)', SRC + ' §2')
