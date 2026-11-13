# New atlas entries from docs/VIGNETTE_FIX.md (lens shading correction vs COLOR profiles, E-P7 1.1 stock main). Not merged.
# Same structure as atlas_data.py: E(addr, name, kind, subsystem, conf, sig, notes, source).
p = 'pipeline'
SRC = 'docs/VIGNETTE_FIX.md'

# ---- capture side: Shading Comp. (key 0x8c21) readers ----
E(0x6055545e, 'cap_still_cmd_shading', 'func', 'capture', 'V', 'd0 capture-mode id, a0 cmd; 5 callers', 'Fifth 0x8c21 reader (call 0x605554bc). Record bit 3 && key == 1 -> cmd+4 |= 0x2000. Twin of 0x602ab42d. v0.25 sc_get covers it', SRC)
E(0x602ab42d, 'cap_still_cmd_shading_b', 'func', 'capture', 'V', 'same contract as 0x6055545e', 'R2 of VIDEO_HIDDEN §5 (call 0x602ab488); +0x10000 always', SRC)
E(0x60555739, 'cap_mode_record', 'func', 'capture', 'V', 'd0 id -> a0 record or 0', '45 x 48-B records at 0x6055ca20; +4 bit 3 = shading allowed (still ids 0x1xxxx yes, LV 0x2xxxx and 0x90000 sensor-check no)', SRC)
E(0x6055ca20, 'cap_mode_records', 'table', 'capture', 'V', '45 x 48 B {u32 id, u16 flags, ...}', 'Id 0x10000/0x110000/0x210000/0x50000/0x1000e/0x10019 ... have flags 0x000b (bit 3)', SRC)
E(0x602a79ef, 'lens_shading_fetch', 'func', 'capture', 'V', 'a0 desc (bit 0 -> 0x2000)', 'Reached from R3/R4 when key 0x8c21 == 1. Front-end command with outputs cap+0x1326 (64 u16), cap+0x13b0, +0x15f0, +0x1650, +0x384a, +0x5da0', SRC)
E(0x602a529f, 'cap_still_cmd_build', 'func', 'capture', 'V', 'capture command builder', 'Calls 0x6055545e, stores cap+0x1326 / +0x13b0 / +0x15f0 / +0x1650 / +0x384a / +0x13b8 / +0x5da0 pointers at cmd+0x1bc..0x1d8', SRC)
E(0x602325b4, 'rap_block_names', 'table', 'capture', 'V', 'char* x 26', 'RAP_* / VDC_* debug names; RAP_SHADING_SETTING and RAP_CIRCLE_SHD_SETTING (and _2) are front-end blocks', SRC)

# ---- development side ----
E(0x6039e54e, 'stage_lens_shading', 'func', p, 'V', 'a0 ctx (+4 request, +0x14 bank)', 'Kind 0: request+0x6fc on -> 64-entry radial gain from request+0x67c into bank+0x404/+0x484, bit 4 of bank+0xc; off -> flat 0x2000. Kind 5: off. Runs only if request+0x668 != 0', SRC)
E(0x603397e0, 'dev_stage_list', 'func', p, 'V', 'a0 ctx', 'Stage builder; 0x60339b8e gates the lens shading stage 0x6039d19a -> 0x6039e54e', SRC)
E(0x60339b8e, 'gate_lens_shading', 'func', p, 'V', 'a0 ctx -> d0', 'On when ctx+0xc4 == 0 and 0x603b54b0(request) != 0 and byte 1 != 0xff', SRC)
E(0x603b54b0, 'req_pre_pass_cfg', 'func', p, 'V', 'a0 request -> d0', 'Kind 0/16: request+0x668, kind 4: +0x108, kind 5: +0xd8', SRC)
E(0x60366f21, 'dev_default', 'func', p, 'V', 'default dev entry body (from 0x60356d7b)', 'request+0x668 is set (1 / 0x10101 / 0x20201 / 0x30101 / 0x40201) only when job+0x2c4a != 0 (multi-pass branch); else stays 0', SRC)
E(0x60355ebe, 'job_pre_pass_cb', 'func', p, 'V', 'job+0x2c20 callback', 'Set for every key but 12 and 0x01010068/0x01020068 (worklist_build). Returns 0x603a2ec6(...) unless params+5555', SRC)
E(0x603a2ec6, 'pre_pass_select', 'func', p, 'V', 'd0 0, type, key*, ISO, ...', 'ISO bucket tables 0x60505280 (on from bucket 5) / 0x6050528c (all on); key only matters for art 0x0101006d and 0x0200008f/0x020003e8', SRC)
E(0x6035b03f, 'creative_shading_mod_body', 'func', p, 'V', 'job, request', 'Level job+0x15d4: 0 -> effect 0, gain 0x400 (emulated bank == no mask); 1..5 / -1..-5 -> effect 0x0c00, gain 0x100000/tbl 0x604ec0d8. Copies the mask desc *(job+0x37a0)+0xc -> request+0x214', SRC)
E(0x6035b105, 'mask_mod_10000', 'func', p, 'V', 'job, request', 'Job flag 0x10000 modifier: mask desc job+0x11c8/+0x1208, effect 0xfe00, gain job+0x1248. 0x10000 is cleared for stills in art_effect_to_flags (0x603eabd0) and never set there', SRC)
E(0x6036b564, 'mask_cache_96', 'func', p, 'V', '2 x 92-B objects', 'Key 0x01010076 only: 4 planes 96 x 96 from fixed ROM tables 0x604eb85c.. (0x6036ce3d -> 0x603389c8)', SRC)
