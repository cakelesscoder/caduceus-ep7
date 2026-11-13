# New atlas entries verified while preparing v0.32 (docs/SPLIT_TONE_G1.md). Same structure as atlas_data.py:
# E(addr, name, kind, subsystem, conf, sig, notes, source). Merge by exec'ing after atlas_data.py (E comes from there).
# Not repeated: gamma stage 0x603ae80d / gamma_select 0x603ae354 / rgb_gamma_set 0x603ae7d3 (new_liveview.py),
# card_mount_dcf_init 0x60618b53 / card_param_csv_load 0x6061907a (RE_SETTINGS).
p = 'pipeline'
u = 'ui'
f = 'fileio'
SRC = 'docs/SPLIT_TONE_G1.md'

E(0x603ae830, 'gamma_stage_after_select', 'site', p, 'V', '5 B `movbu d0,(60,sp); mov (36,sp),a0`; frame add -260,sp',
  '(40,sp) request R, (36,sp) output O, (56,sp) ctx, (60,sp) select result, (68/72/76,sp) R/G/B curve pointers; stage returns by ret (MDR dead)', SRC + ' §1.2')
E(0x603ae861, 'gamma_change_cache_ptr', 'code', p, 'V', 'd3 = (R+1484) + 5736 when (R+1484) != 0',
  'Cache {R*, G*, B*, 12 B, u8 +20}; all three equal and 0x603b5ddc == 4 -> setter skipped (0x603ae8c1..8f0)', SRC + ' §1.2')
E(0x6118cc00, 'lv_grid_aspect_table_a', 'table', u, 'V', '6 x {u32 aspect, u32 list, u32 count}; aspects 1,2,3,4,9,10',
  'LV grid selector 0x60e32406 (count `mov 6,a0` at 0x60e326c3). Siblings 0x6118cc48 (state (1020,this) == 1), 0x6118cc90. Row 5 (aspect 10, 17:9) is dead in this function: aspect is 1/3 in movie or GetValue(270), never 10', SRC + ' §2')
E(0x6118c818, 'lv_grid_value_lists', 'table', u, 'V', '18 x 5 x {u32 value, u32 bitmap}, 40 B each',
  'Values 8 diagonal, 6 golden, 5 grid, 7 cross, 1 thirds; bitmaps 5996-6126, index 124, 2-px lines (6018: 708x399 thirds)', SRC + ' §2')
E(0x6018e1b3, 'sec4_ctor_list_runner', 'code', 'boot', 'V', 'd2 = byte count, a2 = list (0x60747f1c), calls each word',
  'Section-4 ctor list has count 0, so 0x60747f1c is only a label; the sec-4 FF tail 0x60747f20..0x60748000 has no other live ref', SRC + ' §1.3')
E(0x6143a4ed, 'fm_load_call_fm_check', 'site', f, 'V', '5 B `call fm_check,[d2,d3,a2,a3],20` (cd b9 00 f0 14)',
  'Ours (film_menu_v2 fm_core). After it: cmp 0,d0 at 0x6143a4f2; size test and 63 / cmp 128 / cmp 2113 at 0x6143a49e..a4b5; malloc 2560 at 0x6143a439', SRC + ' §1.2')
E(0x601df03c, 'ap_P', 'func', 'ui', 'V', '`call ..,[d2],8` -> d0 1, a0 = the unswapped P (also while P2/P3 is in the state word)',
  'Ours (ap_custom). Reads the state word 0x622cbcc2; with movie +960 VM and +964 back-pointer it follows +968 to P', SRC + ' / docs/SPLIT_TONE.md')
E(0x603aeacd, 'gamma_stage_art_reads_g_slot', 'code', p, 'V', 'mov (2600,O),a1 -> 0x60335323',
  'Only O-slot read in the gamma stage; in the art-key branch (keys 0x01010064..0x01030069) after its own setter', 'docs/SPLIT_TONE.md')
E(0x605b771f, 'sd_lo_slot62', 'data', f, 'V', 'sd_lo[62..63] (sd_lo 0x605b76e1, sd_span 0x605b7721)',
  'Loader v3 range check is (s8 byte - s8 lo) <= span unsigned (0x605b75e8..)', 'docs/SPLIT_TONE.md')
E(0x6118c8e0, 'lv_grid_list_179', 'table', u, 'V', '5 x {value, bitmap}: 6001 6007 6766 6015 6021',
  'Aspect-10 (17:9) lists of the three classes: 0x6118c8e0 / c9d0 / cb10. 6001/6007/6087/6099/6105/6031 are referenced in main only by these lists', SRC + ' §2')
