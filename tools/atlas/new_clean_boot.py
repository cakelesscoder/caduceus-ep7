# New atlas entries from the clean restart layer (patches/clean_boot, docs/GRAIN_HANG.md "Clean restart"). E-P7 1.1.
# Same structure as atlas_data.py: E(addr, name, kind, subsystem, conf, sig, notes, source). Merged by gen.py.
# Not repeated: malloc 0x60022782, alloc_phys_impl 0x60022a61, phys_pool_base / _stride 0x60026df4 / 0x60026e34 (class 1:
# 21 blocks of 0x840 B at 0xa1f8d800, so a malloc(1024) block is 4-aligned and holds 1024 B), sd_go_load_call 0x605b748f,
# cl_first 0x601e045d, fm_load 0x6143a410, ap_P 0x601df03c, hl_run 0x601de917 (with halation h6: `jmp h6_run`).
SRC = 'docs/GRAIN_HANG.md'
f = 'fileio'

# ---- ours ----
E(0x605b7497, 'sd_load', 'func', f, 'V', 'call from sd_go (crash_log: from cl_first); ret [d2,d3,a2,a3],36', 'Ours (card loader v3, sec 3): P = malloc(1024), BUNDLES.BIN read into it (fopen, fseek END, ftell, fseek SET, fread, fclose), sd_check, names, then the handle into the state word 0x622cbcc2, last. Any miss frees the block. The loader writes P+0..+815 only; what the other layers keep above that (editor +680.., split tone +848, movie +960.., AP +984.., grain record +1000, mono +1004.., LOOKS +1016 / +1020) was whatever the block held', SRC)
E(0x605b74a1, 'sd_load_block_site', 'site', f, 'V', '5 B `mov a0,a2; cmp 0,a2; bne +5` (92 ba 00 c9 05), then `jmp sd_out` and `mov sd_path,a0; mov sd_mode,a1; call fopen`', 'Ours (card loader v3): right after `mov 1024,d0; call malloc,[],4`. The block is private here: nothing is in it yet and the state word still says 0xFFFF. clean_boot: `jmp cb_zero`', SRC)
E(0x605b7780, 'cb_zero', 'func', f, 'V', 'jmp from sd_load_block_site, a0 = block or 0; ends `jmp 0x605b74a9` (a block) or `jmp 0x605b74a6` (none)', 'Ours (clean_boot, sec 3, 33 B in place of halation h2\'s hl_pc, which h6 left unused): replays the three displaced instructions and clears the block\'s 1024 B with byte stores, so no mark or pointer of an earlier session (DRAM keeps its contents through a crash-restart) is ever read from P. No call, no stack; every register but a1 (loaded two instructions on) and the flags are as without it', SRC)
