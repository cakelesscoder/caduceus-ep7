# New atlas entries from the v0.32 grain-hang investigation (docs/GRAIN_HANG.md). E-P7 1.1 stock main.
# Same structure as atlas_data.py: E(addr, name, kind, subsystem, conf, sig, notes, source). Merged by gen.py.
# Not repeated: malloc 0x60022782 (new_diag.py), free 0x600227b4, cpu_lock / cpu_unlock 0x6006a922 / 0x6006a96b,
# dev_stage_list 0x603b1466, gamma_stage 0x603ae80d, prop_get 0x6005e971.
SRC = 'docs/GRAIN_HANG.md'



E(0x60022a61, 'alloc_phys_impl', 'func', 'mem', 'V', 'd0 class 0..3 -> a0 block or 0', 'Fixed-block pools: cpu_lock, ssc_lock(0xa09000a, spin), bump index then free stack, bitmap set; on failure "no more heap" log + heap_fail_dump 0x60022dcd, returns 0. Pools shared by all CPUs', SRC)
E(0x60022cc5, 'free_phys_impl', 'func', 'mem', 'V', 'd0 class, a0 block', 'Index = (a0 - base) / stride; bad or unallocated pointer logs and dumps; else bitmap clear + push on the free stack', SRC)
E(0x60022dcd, 'heap_fail_dump', 'func', 'mem', 'V', '', 'Called on alloc/free failure: task id, log line, dump 0x60022e34. Not fatal: the caller still gets 0', SRC)
E(0x60026df4, 'phys_pool_base', 'table', 'mem', 'V', 'u32[4] by class', 'Class bases 0xa1bce7c0 / 0xa1f8d800 / 0xa1dd8d40 / 0xa27f3500 (3 = scheap_sharealloc)', SRC)
E(0x60026e04, 'phys_pool_count', 'table', 'mem', 'V', 'u32[4] by class', 'Blocks per class: 178 / 21 / 43 / 100', SRC)
E(0x60026e14, 'phys_pool_freestk', 'table', 'mem', 'V', 'u32[4] by class', 'u16 free-stack arrays 0xa2728f48 / 0xa27290ac / 0xa27290d6 / 0xa272912c', SRC)
E(0x60026e24, 'phys_pool_bitmap', 'table', 'mem', 'V', 'u32[4] by class', 'Allocated bitmaps 0xa27291f4 / 0xa272920c / 0xa2729210 / 0xa2729218', SRC)
E(0x60026e34, 'phys_pool_stride', 'table', 'mem', 'V', 'u32[4] by class', 'Block strides 0xc0 / 0x840 / 0x4040 / 0xc0: one allocation takes a whole block whatever its size', SRC)
E(0xa2728f28, 'phys_pool_bump', 'data', 'mem', 'V', 'u32[4] by class', 'Next never-used block index per class; 0xa2728f38 u32[4] = free-stack depth', SRC)
E(0x60059fdd, 'ssc_lock', 'func', 'rtos', 'V', 'd0 id (group = bits 3..5, bit = bits 0..2), d1 0 try / 0xff spin / ms -> d0', 'Hardware semaphore bset on 0x8fe00000 + 8*group; spin logs every 0x800000 tries. Used by the phys heap with id 0xa09000a', SRC)
E(0x60059fcd, 'ssc_try', 'func', 'rtos', 'V', 'd0 bit mask, d1 register -> d0 1 got', 'bset d0,(a0): Z set = was free', SRC)
E(0x6005a126, 'ssc_unlock', 'func', 'rtos', 'V', 'd0 id', 'bclr on the group register', SRC)
E(0x8fe00000, 'ssc_regs', 'mmio', 'rtos', 'V', '8 groups x 8 B', 'Cross-CPU hardware semaphores (ssc_lock / ssc_unlock)', SRC)
E(0x60346eb4, 'gamma_reg_writer', 'func', 'pipeline', 'V', '(4,sp) = O+2596, (16,sp) = stage context', 'Skips if R slot 0, or if no context change and C+108 bit 0 clear (btst 1 at 0x60346ed0); R = G = B path and a distinct-RGB path, both CPU copies (no DMA). The only consumer of split_tone curves', SRC)
E(0x603ae9cf, 'gamma_skip_clear', 'site', 'pipeline', 'V', 'mov (56,sp),a0; add 108,a0; and -2', 'gamma_stage skip path (slots unchanged): clears C+108 bit 0. Not a wait flag', SRC)

# ---- v0.32a split_tone placement (ours) ----
E(0x60210e90, 'st_h', 'func', 'pipeline', 'V', 'jmp from st_c; (4,sp) P, (24,sp) kind', 'Ours (split_tone v0.32a .sth): no S at P+848 -> with LOOKS.BIN (P+1020 EP7F, L valid) S = L+2688 in the unused tail of the LOOKS block, no malloc; else jmp st_w', 'patches/split_tone')
E(0x601de740, 'st_w', 'func', 'pipeline', 'V', 'd0 = P+1020, a0 = P', 'Ours (split_tone v0.32a .sti): EP7X (no LOOKS.BIN, or fm_load still reading) -> capture mallocs at once, live view counts 240 split passes in P+848 (tag 0x5354xxxx) first; fm_load not run -> no split', 'patches/split_tone')
