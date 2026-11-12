# New atlas entries from docs/RE_AE.md (AE cadence, records, Auto ISO / shift / gradation hooks).
# Same structure as atlas_data.py: E(addr, name, kind, subsystem, conf, sig, notes, source).
# Merge by exec'ing after atlas_data.py (E and S come from there).
# Not repeated (already in the atlas): ae_record_build 0x6042777c, ae_aperture_snapshot 0x60427ae7, TAKE_EXPOSE
# 0x60421540, ae_slow_limit_rule 0x603fc5d3, prop_get 0x6005e971, prop_lookup 0x6005d924, sid_get 0x602cbc0a.
a = 'lens_ae'
s = 'settings'
SRC = 'docs/RE_AE.md'

# ---- property access ----
E(0x6005e947, 'prop_handle', 'func', s, 'V', 'd0 key -> a0 storage ptr (0 if unknown)', 'prop_lookup + per-core translate 0x6005c8cf. Result is the a0 handle prop_get/prop_set accept: skips the lookup, value still read live', SRC + ' §0')
E(0x6005efbd, 'prop_read_width', 'func', s, 'V', 'd0 key, d1 index, a0 storage', 'Reads u8/s8/u16/s16/u32 by key type nibble (bit 3 = signed, low 3 bits = width)', SRC + ' §0')
E(0x6005ea22, 'prop_set', 'func', s, 'V', 'd0 key, d1 index, a0 handle (0 = lookup), a1 value; `call ..,[d2,d3,a2,a3],40`', 'Used by the AE publish 0x6042805e and the bracket step', SRC + ' §1')
E(0x6020d024, 'ae_prop_handles_init', 'func', a, 'V', 'd0 on', 'on == 1: ~200 x prop_handle(key) -> 0x622a09a4..0x622a0bfc (e.g. 0x6020d7a6 key 0x949a -> 0x622a0b40, 0x6020da40 0x8eb9 -> 0x622a0bd8, 0x6020d393 0x30ea -> 0x622a0a60); else zero them. Callers 0x6020d011, 0x60421338. No value cache', SRC + ' §0')
E(0x622a0b40, 'ae_h_iso_auto_upper', 'data', a, 'V', 'ptr (handle for key 0x949a, sid 112)', 'Siblings: 0x622a0b44 0x9a9a, 0x622a0a60/5c/64 0x30ea/0x30fa/0x310a, 0x622a0bd8 0x8eb9, 0x622a0b00 0x80ba', SRC + ' §0')

# ---- task / entry points ----
E(0x6054aa50, 'take_expose_msg_table', 'table', a, 'V', '64 x {u32 id+1, u32 handler}, linear probe', 'TAKE_EXPOSE message dispatch (ids 0x000..0xd03); loop 0x60421540 queue (0x60040d9a)', SRC + ' §1')
E(0x6042754a, 'take_expose_calculate', 'func', a, 'V', '`call ..,[],4`', 'Log "[TEXP]take_expose_calculate"; sem 0x60040a36 around te_calc_core(0). Callers 0x6028e6a8, 0x604259cb, 0x60425a64', SRC + ' §1')
E(0x604275b3, 'take_expose_calculate_internal', 'func', a, 'V', '`call ..,[],4`', 'Same with the _internal string; 38 TAKE_EXPOSE handler callers', SRC + ' §1')
E(0x6042760c, 'te_calc_core', 'func', a, 'V', 'd0 flag; `call ..,[d2,d3,a2,a3],16`; 760-B frame', 'ae_record_build(A sp+36, B sp+120) every call (no cache) -> 0x60427dac -> 0x603f3956 -> ae_program 0x603f38f8 -> 0x6042805e -> 0x6042857f -> copy 76 B to 0x622a0714', SRC + ' §1')
E(0x60426e30, 'ae_frame_cb', 'func', a, 'V', 'a0 frame status', 'Detection-result callback: status 0 and mode != 7 -> publish 0x60425ba3 + te_calc_core every call; else once per 250-tick timer (0x6006b003, cb 0x60425e05 clears 0x622a0641)', SRC + ' §1')
E(0x60426f83, 'ae_detect_prefetch_cb', 'func', a, 'V', 'a0 {buf*, ...}', 'Fills the 124-B DP: mode 7 -> rebuild at most every 100000 counter ticks; else rebuild only when DP+62 == 0x60555c80(), otherwise copy cache 0x622a084c', SRC + ' §0, §1')
E(0x6042661b, 'ae_detect_build', 'func', a, 'V', 'a0 DP (124 B); `call ..,[d2,d3,a2,a3],36`', 'DP: +18 gradation, +32/+34 Auto ISO upper/default, +46 ISO, +48 Av, +50 exp comp, +56/58/60 exposure shift', SRC + ' §2')
E(0x6028e684, 'exp_change_notify', 'func', a, 'V', '', 'Optional post (mbx 0x600410a6, code 6), then take_expose_calculate. From 0x602e87e1 (sid 86 / sid 6 descriptor callbacks and others)', SRC + ' §1')

# ---- getters feeding the records ----
E(0x60429519, 'ae_iso_get', 'func', a, 'V', '-> d0 Sv (0 = Auto)', 'key 0x810a (sid 6); Auto with 0x622a076a == 1 -> 1536 (0x603f3968). -> B+2, DP+46', SRC + ' §2')
E(0x604297db, 'ae_expcomp_get', 'func', a, 'V', '-> d0 (+-1280)', 'key 0x80ba (sid 2) via prop_get at 0x60429824 (EI hook E1); override struct 0x603b6fb7+16 when sid 382 == 1 and sid 323[1] == 0. Callers 0x604269f6 (DP+50), 0x60427af1 (B+6)', SRC + ' §2, §5')
E(0x60429629, 'ae_gradation_get', 'func', a, 'V', '`call ..,[],24` -> d0 s8', 'key 0x8eb9 (sid 105) via prop_get at 0x6042965b (hook G1); 0x603042a9 branch dead (stub returns 0). Callers 0x6042681a (DP+18), 0x60427876 (A+14)', SRC + ' §2, §5')
E(0x603b6fb7, 'ae_override_rec', 'func', a, 'V', '-> a0 = 0xa27396d8 + 24*(0xa2739720)', 'Source of AE values when sid 382 == 1 and sid 323[1] == 0', SRC + ' §2')
E(0x604290a4, 'ae_shift_meta', 'func', a, 'I', '', 'Picks exposure shift by EXIF-style metering code (5 ESP 0x30ea, 2 CW 0x30fa, 3 spot 0x310a), stores x100/256 at a2+2564 with /100', SRC + ' §4')

# ---- AE program ----
E(0x603f38f8, 'ae_program', 'func', a, 'V', 'a0 param block {A, B, photometry, ., stab, ., result, aux}', 'Trampoline to 0x603fbe7a: per-mode program via hash 0x60542558 (key mode-2), else limits 0x603fc6ba -> ae_program_line 0x603fce91', SRC + ' §3')
E(0x60541326, 'ae_program_table', 'table', a, 'V', '70-B rows, mode u16 at +0x44 (lookup 0x603fca0a)', 'Per-mode Av/Tv/Sv bounds; Sv entries may be sentinels 0x9f00/0xa000/0xa100/0xa200 resolved by ae_sv_resolve', SRC + ' §3')
E(0x603fcaf1, 'ae_sv_resolve', 'func', a, 'V', 'd0 table Sv code -> Sv', 'ISO Auto: 0x9f00 -> A+24 (or 0xd00), 0xa000 -> A+26 (or floor), 0xa100 -> same +256 if 0x603fe960, 0xa200 -> floor; manual -> B+2. Clamp [floor 0x500/0x600 (0x603fe808), 0xd00] unless key 0xc222 == 2', SRC + ' §3')
E(0x603fce91, 'ae_program_line', 'func', a, 'I', '', 'Tv/Av/Sv split; applies B+14 (sid 86, program shift [I]) in program modes; snaps to EV step B+12', SRC + ' §3')
E(0x603fe925, 'ae_minss_pred', 'func', a, 'V', '-> d0 bool', 'Lowest S/S active: mode in {3,4,36,37}, A+30 != 0x7eee, 0x60420199(A+38, A+46) == 0 (MIN_SHUTTER)', SRC + ' §3')
E(0x6042805e, 'ae_result_publish', 'func', a, 'V', 'a0 result 76 B, a1 A, d0 B', 'Writes AE results to properties (prop_set; keys 0xd0ca, 0xa07a, 0xa02a, 0xa04a, 0xc55a ...)', SRC + ' §1')
