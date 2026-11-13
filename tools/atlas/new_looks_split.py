# New atlas entries from the v0.32 looks_split layer (patches/looks_split, docs/PACKS.md "Split tone on the E-P7").
# Same structure as atlas_data.py: E(addr, name, kind, subsystem, conf, sig, notes, source). Merged by gen.py.
# Not repeated: fm_load_call_fm_check 0x6143a4ed, the fm_load malloc 0x6143a439, ap_P 0x601df03c (new_build032.py).
SRC = 'patches/looks_split'
f = 'fileio'
u = 'ui'

E(0x6143a410, 'fm_load', 'func', f, 'V', 'CALLS, a2 = P', 'Ours (film_menu_v2 fm_core, sec 9): once per power-on LOOKS.BIN -> L (malloc 2640 from v0.32, was 2560), fm_check, slot resume by name, publish P+1016 / P+1020 EP7F. v0.32: its fm_check call goes through ls_chk (split stash)', SRC)
E(0x6143a5a6, 'fm_check', 'func', f, 'V', 'a3 = L (file), d3 = size -> d0 0 valid; [d2,d3,a2,a3],20', 'Ours (fm_core): header template, CRC (bytes 0..15, 20..end), per-record range table 0..44, class/mask, tint, name rule (NUL tail to +63). Unchanged in v0.32: ls_sc hands it a file whose +61/+62 are already 0', SRC)
E(0x6143a688, 'fm_crc', 'func', f, 'V', 'd0 running CRC, a0 data, d1 length > 0 -> d0; [d2,d3],8; keeps a1', 'Ours (fm_core): bitwise CRC-32 (0xedb88320), no table. Also called by ls_sc and plugin_loader', SRC)
E(0x601e2e28, 'u_apply', 'func', u, 'V', 'a0 = L, a2 = P, d3 = k; T = L+2456 (entry 64 + name 16)', 'Ours (film_menu_v2 fm_ui): staging T -> slot k bytes 0..49 only (v0.25 bound 0x601e2e46; +50..63 untouched, so split +62/+63 survives the copy), flags byte last, name P+544+16k, dirty; then jmp lt_post 0x601e233c -> sl_pick', SRC)
E(0x601e39aa, 'sl_pick', 'func', u, 'V', 'a2 = P, d3 = k, a3 = parent', 'Ours (v0.25 shade): Film-pick tail, library look sets slot +49 (Shading). Its tail jmp 0x601e3a16 -> ls_pick from v0.32 (was fm_post 0x601e37b4)', SRC)
E(0x601e3a16, 'sl_pick_tail_jmp', 'site', u, 'V', '5 B jmp rel32 (dc ..)', 'Ours: v0.32 -> ls_pick (slot +62/+63 from the LOOKS.BIN stash or the Own snapshot), which ends jmp fm_post 0x601e37b4', SRC)
E(0x601e37b4, 'fm_post', 'func', u, 'V', 'a2 = P, d3 = k, a3 = parent', 'Ours (lv_art_refresh): after a Film pick, LV art refresh then ed_poke', SRC)
E(0x607d5510, 'ls_chk', 'func', f, 'V', 'jmp from 0x6143a4ed; a3 = L, d3 = size, a2 = P', 'Ours (looks_split, sec-5 dead sdk-api claim 0x607d5500..0x607d5900): ls_sc, then call fm_check, jmp 0x6143a4f2', SRC)
E(0x607d5521, 'ls_sc', 'func', f, 'V', '[d2,d3,a2,a3],20', 'Ours: CRC first; each record +61/+62 = 0, or +60 = 0 and both split bytes in range; then stash L+2568+2j, zero them in the record, rewrite CRC +16, L+2564 = P, L+2560 EP7W last. Any miss: file untouched (fm_check rejects split bytes after the name NUL)', SRC)
E(0x607d55ef, 'ls_pick', 'func', u, 'V', 'jmp from 0x601e3a16; a2 = P, d3 = k', 'Ours: call ls_pk, jmp fm_post', SRC)
E(0x607d55f9, 'ls_pk', 'func', u, 'V', '[d2,d3,a2,a3],20', 'Ours: real P (ap_P) + L + EP7W tag: library pos -> stash to slot +62/+63 (0 clears); Own / Stock -> snapshot L+2132+80k +62/+63; else nothing', SRC)
