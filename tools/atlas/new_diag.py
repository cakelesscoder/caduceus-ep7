# New atlas entries from docs/PLUGINS.md §10 (camera diagnosis, E-P7 1.1 stock main + v0.32 diag layer). Not merged.
# Same structure as atlas_data.py: E(addr, name, kind, subsystem, conf, sig, notes, source).
p = 'ui'
SRC = 'docs/PLUGINS.md §10'

# ---- stock ----
E(0x60027068, 'section_table', 'table', 'boot', 'V', '9 x {start, flash source, destination}', 'Entry 5 = {0x6075a800, 0x40dda800, 0x6075a800}: sec 5 is copied 1:1 (flash = image addr - 0x60020020 + 0x406a0020)', SRC)
E(0x60045786, 'section_end', 'func', 'boot', 'V', 'd0 id 1..9 -> d0 end (jump table 0x60046780 of mov imm32 stubs)', 'Sec 5 end 0x60b9e000 (stub 0x600457b4); sec 8 empty (0x613bd000)', SRC)
E(0x60022782, 'malloc', 'func', 'mem', 'V', 'd0 size -> a0; [],4', 'Class by size: <=128 -> 0, <=2048 -> 1, <=16384 -> 2 (0x60022a61); larger: error log 0x60022694, a0 = 0. Class 2 = 43 blocks of 0x4040 B at 0xa1dd8d40', SRC)
E(0x60d00506, 'ge_paint_window', 'func', p, 'V', 'a0 window, a1 gc or 0 (then window+72); frame [d2,d3,a2,a3],32', 'One caller 0x60d3907e. Early out if u16 window+1372 == 0. Calls vtable +708, +680, then +164 (0x60d005ef) and +160, then paint end 0x60d0658a / 0x60d06468', SRC)
E(0x60d005ef, 'ge_paint_post164_site', 'site', p, 'V', 'mov (164,a2),a2; calls (a2) (6 B); a0 window, a1 = (4,sp) gc', 'The only +164 call. a0/a1/a2 reloaded at 0x60d005f5; nothing branches into +1..+5. v0.32 diag: jmp dg_paint + nop', SRC)
E(0x60cfe263, 'win_empty_method', 'func', p, 'V', 'retf [],0', '+164 word of about 400 window vtables (0x60f94628 .. 0x611104b8); re-pointing one vtable covers one class only', SRC)
E(0x60f9477c, 'ge_window_vtable', 'table', p, 'V', '>= 712 B vtable', 'Base window class, stored by ctor 0x60cff51e (one caller, 0x60d43e80). +164 at 0x60f94820', SRC)
E(0x60fac34c, 'ge_window_sub_vtable', 'table', p, 'V', '>= 712 B vtable', 'Subclass, ctor 0x60d43e80, made only at 0x60d39f41. +164 at 0x60fac3f0', SRC)
E(0x60dec4d4, 'profile_view_new', 'func', p, 'V', 'a0 parent -> new 148 B view (0x60a4ec03), ctor 0x60dec4f4 [d2,d3,a2,a3],88', 'Ctor stores vtable 0x61155e14 and registers listener 111 through 0x607f9062 -> +8', SRC)
E(0x60dec697, 'profile_view_dtor', 'func', p, 'V', 'vtable +4; movm [a2,a3] prologue; a0 view', 'Restores vtable 0x61155e14, unregisters listener 111. v0.32 diag: word 0x61155e18 -> dg_dtor', SRC)
E(0x601df6e5, 'ap_post', 'func', 'card', 'V', 'tail-jmp wrapper, event at (32,sp)', 'Half-press 0x02000100, ap_P, P+980 EP7T, P+992 != EP7U -> EP7U, P+984 = 0, call pl_ap (0x601df730); then jmp 0x605b7340', SRC)

# ---- v0.32 diag layer (our code, sec 5) ----
E(0x607b8700, 'dg_ap', 'func', 'card', 'V', 'jmp from pl_ap, frame [d2,d3,a2,a3],24, a2 = P', 'Plugin loader with stage marks L (0x6203c8bb bits 1-3); clears P+852 first', SRC)
E(0x607b88bc, 'dg_fw', 'func', p, 'V', 'call entry [d2,d3,a2,a3],88: a0 widget, a1 value', 'Firmware Body value "L/OK" (K from the keyhook Fn stage byte 0x6203bcb2, PLUGINS §11/§12); empty value -> fw_val', SRC)
E(0x607b898b, 'dg_paint', 'func', p, 'V', 'jmp from 0x60d005ef', 'Stock +164 call, then O2, PT log and dg_draw (current window only) while the profile view is alive (0x622ab792 bit 0)', SRC)

# ---- §11: why the overlay text was invisible (docs/PLUGINS.md §11) ----
SRC11 = 'docs/PLUGINS.md §11'
E(0x60d4c434, 'label_widget_draw', 'func', p, 'V', 'widget draw method, frame [d2,d3,a2,a3]; gc (24,sp), rect (28,sp); ref 0x60faeeb4',
  'Stock text-label draw: 0x60d0fce0(gc, widget+128 text style), 0x60d0fd83(gc, 2), then inline text (widget+174 == 1) -> 0x60d075a7(style = widget+132); no gc colour call', SRC11)
E(0x60d0758f, 'ge_draw_text_res', 'func', p, 'V', 'd0 resource string id, d1 style*, a0 gc, a1 rect; [d2,a2,a3],16', 'String id -> 0x60d10bf2, then ge_draw_text', SRC11)
E(0x60d0fb5d, 'gc_set_colour2', 'func', p, 'V', 'd0 colour, a0 gc; ret [a2],8', 'gc+0x28c (converted if gc+0x294/295 == 1). ge_draw_text calls it with style +4', SRC11)
E(0x60d0fb40, 'gc_set_colour3', 'func', p, 'V', 'd0 colour, a0 gc; ret [a2],8', 'gc+0x290. ge_draw_text calls it with style +8', SRC11)
E(0x60d0642a, 'ge_paint_begin', 'func', p, 'V', 'a0 gc, a1 window+1200, d0 window+1392; [d2,d3,a2,a3],20', 'DC clip from window+1200 (0x60d0f8e3), gc+12 = window+1200, update region (36 B) -> gc+168', SRC11)
E(0x60d06468, 'ge_paint_end_single', 'func', p, 'V', 'a0 gc; [d2,d3,a2,a3],48', 'ge_present(gc+8), then each gc+168 rect -> 0x60d0ed81 (sync front -> back through DC +8)', SRC11)
E(0x60d0ed79, 'ge_present', 'func', p, 'V', '[],4', '-> 0x60d125af: if 0x61fb2939 set, gpiUpdateDisplay(0) (whole-buffer flip), 0x61fb2938 ^= 1, clear 0x61fb2939', SRC11)
E(0x60d0f530, 'region_count', 'func', p, 'V', 'a0 region -> d0 (24,a0)', 'Update region: 36 B, rects at +0 (8 B each), count +24; 0x60d0f529 clears the count, 0x60d0f539 copies 36 B', SRC11)
E(0x607b8a58, 'dg_draw', 'func', p, 'V', 'call from dg_pnt [d2,d3,a2,a3],108; a1 = gc = *(painter+8), d3 window',
  'Four probe rows on the Extras page: style colour 1/2/4/6; always selects the window default text style (+488 -> 0x60d0fce0), gc+0x34 = 2, draws, releases the font (0x60d10708), restores gc+0x4c / +0x34 (PLUGINS §13); none -> O4', SRC11)
E(0x60d060e3, 'painter_gc', 'func', p, 'V', 'a0 painter -> a0 gc = *(painter+8); [],0', 'The +164 argument and *(window+72) are the painter; the drawer needs this gc (PLUGINS §11)', SRC11)
E(0x60d3379b, 'ge_current_window', 'func', p, 'V', '-> a0 = *(0x61fb3138); retf', 'Set by 0x60d337a4 from the window ctor 0x60cff51e and 0x60cfd455. 893 callers', SRC11)
E(0x60d00f90, 'win_default_text_style', 'func', p, 'V', 'window vtable +488; a0 window -> d0 u16 window+108', 'Both window classes. Ctor sets 0. Used by the generic GE text draw 0x60d06bb7 before 0x60d0fce0', SRC11)
E(0x60d0695c, 'ge_draw_label_generic', 'func', p, 'V', 'GE text draw (caller 0x60d0691b)', 'Colour = window +504, text style = window +488 -> 0x60d0fce0 (skips if a0 0), 0x60d0fd83(2), 0x60d0758f', SRC11)
E(0x61fb3138, 'ge_current_window_ptr', 'data', p, 'V', 'u32 window*', 'Current (last constructed) window', SRC11)

# ---- §13: TRACE ring log + overlay side-effect fix (docs/PLUGINS.md §13) ----
SRC13 = 'docs/PLUGINS.md §13'
E(0x60d10708, 'gc_font_release', 'func', p, 'V', 'a0 font (from 0x60d0fce0); [],4',
  'calls (0x61fb2614)(font) if both non-zero. Every stock 0x60d0fce0 user calls it after its draw (0x60d4c638, 0x60d457a5, 0x60d0695c); the gc+0x4c it leaves behind is a released font', SRC13)
E(0x60d0fd83, 'gc_set_mode34', 'func', p, 'V', 'a0 gc, d0 -> u16 gc+0x34; retf', 'All three stock callers pass 2 right before a text draw', SRC13)
E(0x60ce017e, 'ca_key_generic_twin', 'func', 'ui', 'V', 'frame [d2,d3,a2,a3],44; a0 CA, a1 record; same 24-B copy loop',
  'Unhooked twin of 0x60ce0108 (CA state 0x5704). kmap call 0x60ce0190 (7 B), resume 0x60ce0197; nothing branches into +1..+6. v0.32 diag: jmp dg_twin', SRC13)
E(0x601df6fa, 'ap_post_halfpress_block', 'site', 'card', 'V', 'movm [d2,d3,a2,a3],(sp); add -4,sp (5 B)',
  'First instruction after the half-press test; d0/d1/a0/a1 are reloaded from (0..12,sp) at 0x601df73a. v0.32 diag: jmp dg_half', SRC13)
E(0x60635041, 'fwrite', 'func', 'card', 'I', 'a0 buf, d0 1, d1 len, a1 handle; [d2,d3,a2,a3],24', 'Used by the diag TRACE.TXT dump (fopen "w" mode string 0x60a65d37, as stock 0x60765cc8)', SRC13)
E(0x6203bcb3, 'dg_logon', 'data', 'card', 'V', 'u8, boot-cleared .bss pad', 'v0.32 diag: 1 = this power-on\'s 16 KB log block is in P+860 (set by dg_ap only); no stock reference', SRC13)
E(0x607b8cb0, 'dg_logw', 'func', 'card', 'V', 'call [d2,d3,a2,a3],40: d0 tag, d1 w1, a0 w2, a1 w3', 'Ring-log writer: 0x6203bcb3 == 1, ap_P, P+860 inside the class-2 pool -> 16 B at base + (P+864 & 0x3ff0), P+864 += 16', SRC13)
E(0x607b8d09, 'dg_key0', 'func', 'ui', 'V', 'jmp from 0x60ce011a', 'Log K0 (event, record+196 state, record+4), kh_chk; handled -> log D0, ret [d2,a2,a3],40; else kh_miss', SRC13)
E(0x607b8d3a, 'dg_key1', 'func', 'ui', 'V', 'jmp from 0x60cebc9a', 'As dg_key0 with kh_chk2 / kh2_miss, ret [d2,d3,a2],48', SRC13)
E(0x607b8d6b, 'dg_twin', 'func', 'ui', 'V', 'jmp from 0x60ce0190', 'Log KT, rebuild the copy-loop registers, replay call 0x60cc9a05,[d2],4, jmp 0x60ce0197', SRC13)
E(0x607b8d8f, 'dg_half', 'func', 'card', 'V', 'jmp from 0x601df6fa', 'Below-the-frame call of dg_hc (dump if P+864 != 0; reset only if written), then the relocated prologue', SRC13)
E(0x607b8de9, 'dg_dump', 'func', 'card', 'V', 'call [d2,d3,a2,a3],56; a2 = P -> d0 1 written / 0 fopen failed', 'EP7MOD/TRACE.TXT: title, header (-1, build id, L/flag/kstage, entries), ring oldest first as hex lines', SRC13)
