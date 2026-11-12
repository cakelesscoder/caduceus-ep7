# New atlas entries from docs/RE_LIVEVIEW.md (live-view lifecycle, stills RGB gamma).
# Same structure as atlas_data.py: E(addr, name, kind, subsystem, conf, sig, notes, source).
# Merge by exec'ing after atlas_data.py (E and S come from there).
l = 'liveview'
r = 'rtos'
p = 'pipeline'
SRC = 'docs/RE_LIVEVIEW.md'

# ---- CPU2 tasks / MVR framework ----
E(0x6003d344, 'cpu2_task_desc_table', 'table', r, 'V', '28 x 28 B {u32 id, u32 attr, u32 0, u32 entry, u32 prio, u32 stack, u32 0}', 'Ids 0x2001..0x201c; names in 0x61400b18 (n = id & 0xff) [I pairing]', SRC + ' §1')
E(0x61400b18, 'cpu2_task_name_table', 'table', r, 'V', '26 B {char name[24], u16 n}', 'BOOT_CPU2 1, MVR_MAIN 2, MVR_MOVIE 3, MVR_IMG1 5, MVR_CALC 6, MVR_IMG2 7, MVR_ENC 8, MVR_RECVIEW 0xc, REC_MAIN_CPU2 0x12, REC_VIEW_CPU2 0x14, MVR_EXEC 0x17 ... 0x1c', SRC + ' §1')
E(0x6140033a, 'cpu1_task_name_table', 'table', r, 'V', '26 B {char name[24], u16 n}', 'BOOT_CPU1 1 .. S_SHELL_CPU1 0x29 (wifi, AVM, C3D, FCS_IMG_2NDCPU_MAIN)', SRC + ' §1')
E(0x603291af, 'MVR_MAIN', 'func', l, 'V', 'CPU2 task 0x2002 entry, prio 25, stack 0x2800', 'Waits flag (0x60041076) at 0x6032920e; bit 0x4 -> mbx 0x2001, 0x8 -> mbx 0x2002 (0x6032560b), others -> 0x6032a07d. Runs the LV job state machine', SRC + ' §1-2')
E(0x60327cfd, 'MVR_IMG', 'func', l, 'V', 'CPU2 tasks 0x2005/0x2007/0x200a entry, prio 25', 'Shared entry for MVR_IMG1/IMG2/IMG_POST', SRC + ' §1')
E(0x6032560b, 'mvr_service_loop', 'func', l, 'V', 'd0 mailbox id, a0 ctx', 'Receive 0x6031d88c, then handler slot from 0x604e2f64 by mailbox (0x2001/2 -> 0, 0x200a/c/f -> 1, 0x2003/4 -> 2, 0x200b -> 3, 0x200e -> 4, 0x2010 -> 5, 0x2011 -> 6)', SRC + ' §1')
E(0x604e2f64, 'mvr_handler_table', 'table', l, 'V', 'u32[7] handler', '0x60329646 LV state machine, 0x6032819d, 0x603301cc, 0x603252a9, 0x60325ed9, 0x60332acc, 0x603324fc (Rec View)', SRC + ' §1')
E(0x6004109e, 'mvr_mbx_id_words', 'data', r, 'V', 'u16[] = 0x2001, 0x2002, 0x2003, 0x2004 ..; 0x600410be = 0x2011', 'MVR mailbox ids (CPU2 id space)', SRC + ' §1')
E(0x60041076, 'mvr_main_flag_id', 'data', r, 'V', 'u16 flag id', 'MVR_MAIN event flag; bit 0x1 = LV param event 7', SRC + ' §1-2')
E(0x600510e8, 'set_flg', 'func', r, 'V', 'd0 flag id, d1 bits', 'Event flag set; used by 0x6031daaa/0x6031dafa/0x6031db4b, TAKE_MOV post 0x6020c15c path', SRC + ' §1')
E(0x6031da00, 'mvr_flag_post_deferred', 'func', l, 'V', 'a0 req {u16 flag, u32 bits, u32 delay, u8 mode}', 'Bits 1 -> setter 0x6031daaa, 2/0x400 -> 0x6031dafa, 0x4000 -> 0x6031db4b; armed via 0x6005633f (alarm/timer [I]). Stock: delay 0, mode 2', SRC + ' §1')
E(0x6005633f, 'alarm_start', 'func', r, 'I', 'a0 callback, a1 delay, d0 mode', 'Deferred callback (cyclic/alarm handler [I]); ~30 callers', SRC + ' §1')

# ---- CPU0 TAKE_MOV side ----
E(0x60296ec8, 'through_update_post', 'func', l, 'V', '`call ..,[],12`', 'Enqueue {1,0} on (0x6223cbbc) and set TAKE_MOV flag (0x60040c2e) bit 1. Only caller 0x6029413f', SRC + ' §1')
E(0x6029413f, 'through_update_req', 'func', l, 'V', 'calls; add -4,sp / ret [],4', 'Gate (0x62236dbd) != 0 -> 0x60296ec8. Ops-struct slot (word 0x6054cb98, built at 0x6054cb48..); indirect caller unknown. Candidate LV refresh trigger L1', SRC + ' §1, §5')
E(0x62236dbd, 'through_update_gate', 'data', l, 'I', 'u8', 'Non-zero = TAKE_MOV through path live [I]', SRC + ' §1')
E(0x6223cbbc, 'takemov_queue', 'data', l, 'V', 'ptr to queue object', 'Dequeued by 0x60554128 (cpu_lock); enqueue 0x6020b998', SRC + ' §1')
E(0x605540e6, 'takemov_drain', 'func', l, 'V', '', 'TAKE_MOV loop body: arg 0 -> 0x60554173 (multi-step, progress word 0x6223cd18) -> 0x605542ba -> 0x60303ad3; arg != 0 -> 0x605542b0 -> 0x60303e7f', SRC + ' §1')
E(0x60303ad3, 'through_update', 'func', l, 'V', 'a0 msg', '"TH" tag. 0x6030ddc7()==2 -> 0x60327b93, else 0x60327b3c. Callers 0x6055439b (TAKE_MOV), 0x60303e2e', SRC + ' §2')
E(0x60327b3c, 'through_record_post', 'func', l, 'V', 'a0 msg, a1 0x62039f24', '0x60308de5, 0x6030b3b9, 0x60309805(rec,0) record build, then 0x6031da00 {flag 0x60041076, bits 1, delay 0, mode 2} -> event 7', SRC + ' §2')

# ---- LV state machine ----
E(0x604e315c, 'lv_state_table', 'table', l, 'V', '13 states x 28 events x 8 B {u32 action, u32 post}; row 0xE0', 'Event 7 (param update) in every state: actions 0x6032dd61/0x6032ddb2/0x6032de23/0x6032de8e/0x6032dee6/0x6032f09e, post 0x6032e074. LV_ART_PREVIEW §7 read it 4 B off (0x604e3190) and called event 7 "event 0"', SRC + ' §2')
E(0x6032967e, 'lv_state_dispatch', 'func', l, 'V', 'd0 event (<28), a0 state*, a1 ctx', 'entry = 0x604e315c + 0xE0*state + 8*event; action(state, entry, ctx, &out) then post(state); errors 0x9d05/0x9d06. Callers 0x60329670, 0x6032a19e, 0x6032cb75', SRC + ' §2')
E(0x60329646, 'lv_msg_handler', 'func', l, 'V', 'a0 msg {u16 mbx, u32 code, +8, +12 state*, +16 ctx}', 'Mailbox 0x2001/2 handler: 0x60329479 maps code -> event, then 0x6032967e', SRC + ' §2')
E(0x60329479, 'lv_msg_to_event', 'func', l, 'V', 'd0 mbx, d1 code, a0 &event', 'mbx 0x2001: 1->0, 2->1, 16->2, 26->3, 17->4, 23->5, 18->6; mbx 0x2002 via jtab 0x604e3f00: 1->11, 5->12, 2->13, 3->14, 4->15, 6->16, 7->17, 8->18, 10->19, 33..36->24..27', SRC + ' §2')
E(0x6032a07d, 'lv_flag_to_event', 'func', l, 'V', 'a0 ctx, a1 &flag bits', '0x1 -> event 7 (after 0x6032c82d, 0x60305edd, 0x60305e3b, 0x6031a8a0, 0x6032c703); 0x2/0x400 -> 8 dmy_cap; 0x10 -> 9 rec_err; 0x20..0x100 -> 10 allow_rec_end; 0x200 post_through_end_timeout', SRC + ' §2')
E(0x6032caec, 'lv_jobend_to_event', 'func', l, 'V', '', 'Job-end word: 0x4000 -> 23, 0x800 -> 20, 0x1000 -> 21, 0x2000 -> 22', SRC + ' §2')
E(0x6032dd61, 'lv_ev7_action', 'func', l, 'V', 'state action', 'Event 7 family (also 0x6032ddb2, 0x6032de23, 0x6032de8e, 0x6032dee6): 0x6032cba8 re-read, 0x60309d90, 0x6030a801, 0x6032936a', SRC + ' §2')
E(0x6032936a, 'lv_apply', 'func', l, 'V', '', 'Current record 0x60309eb9, 0x6031b09f, 0x6032f37a/0x6032f5e0, 0x6032a1d6 (-> comparator / act 0x6032a706)', SRC + ' §2')
E(0x60311440, 'lv_job_delete', 'func', l, 'V', '', 'Called by act 0x6032a706 at 0x6032a7df before rebuild 0x603114e0', SRC + ' §2')
E(0x6030bb2d, 'lv_wb_fill', 'func', l, 'V', '', 'Compact WB fill (prop_get at 0x6030bb5b/6e, key 0x84f9..); from 0x6030ba2b on every event 7', SRC + ' §2')

# ---- stills / LV RGB gamma ----
E(0x603ae80d, 'gamma_stage', 'func', p, 'V', 'a0 stage ctx (+4 request, +12 output O); `call ..,[d2,d3,a2,a3],16`', 'From dev_stage_list 0x603b14a6 (2nd stage). gamma_select -> cache check -> rgb_gamma_set 0x603ae995 -> cache store. Split-tone hook G1 at 0x603ae830 (5 B f8923c 5c24)', SRC + ' §4-5')
E(0x603ae2fd, 'gamma_row_pick', 'func', p, 'V', 'a0 row, d0 variant, d1 type (R+14) -> a0 curve', 'Column: type hi 0x40 -> +16; 0x30 + lo 2..5 -> +8 else +24; other + lo 2..5 -> +8 else +0; variant -> +4', SRC + ' §4')
E(0x60530b6c, 'gamma_ptr_table', 'table', p, 'V', '25 rows x 8 u32 (4 cols x {normal, variant})', 'Row 0 base 0x604ede78; 5-7 Cross Process I R/G/B; 9-11 CP II; 12-14 Vintage I; 15-17 Vintage II; 18-20 Vintage III; 21-23 Bleach Bypass II; 24 used when R+1838 == 257', SRC + ' §4')
E(0x60532110, 'gamma_effect_hash', 'table', p, 'V', '16 x {u32 id-1999, u32 handler}', 'id 2000 Flat, 2001 log, 0x0101006b/0x0102006b/0x01010079/0x01020079/0x01030079/0x0102007b three-curve, others single', SRC + ' §4')
E(0x60346e37, 'gamma_lut_upload', 'func', p, 'V', 'a? window (u32 words), ctx (+12 O, +0x38 owner, +0x6c dirty bits)', 'R==G==B: window+0x000; else R +0x400, G +0x800, B +0xC00 (bytes), O+2608 -> +0x1000; skipped unless owner changed (0xa27360ec[2]) or ctx+108 bit0. Callers 0x60345f9b, 0x60345fbd (in 0x60345ebe)', SRC + ' §4')
E(0x603b5ddc, 'gamma_cache_cmp', 'func', p, 'I', 'a0, a1 -> d0 (4 = same)', 'Second half of the gamma-stage cache check (after pointer compare)', SRC + ' §4')
E(0x603b5e8c, 'gamma_curve_analyse', 'func', p, 'I', 'a0, a1 curve, d0 out', 'Run per distinct curve when gamma_select returns 1; outputs to stage frame +44..+64 (meaning unknown)', SRC + ' §4')
E(0x604eee78, 'gamma_crossproc1_r', 'table', p, 'V', '256 u16 (0..4095)', 'Cross Process I R; G 0x604ef078, B 0x604ef278', SRC + ' §4')
E(0x604f0a78, 'gamma_vintage1_r', 'table', p, 'V', '256 u16', 'Vintage I R; G 0x604f0c78, B 0x604f0e78 (B 1283..3818: stock split tone)', SRC + ' §4')
