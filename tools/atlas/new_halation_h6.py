# New atlas entries from the halation h6 layer (patches/halation_h6, docs/HALATION_RED.md "h6"). E-P7 1.1.
# Same structure as atlas_data.py: E(addr, name, kind, subsystem, conf, sig, notes, source). Merged by gen.py.
# Not repeated: cpu_lock / cpu_unlock 0x6006a922 / 0x6006a96b, cache_flush 0x60066fc0, window_map 0x60067146, window_mode_get /
# _set 0x600672ee / 0x600672fe, malloc 0x60022782, free 0x600227b4, alloc_phys_impl 0x60022a61, phys_pool_base / _count /
# _stride 0x60026df4 / e04 / e34, ap_P 0x601df03c, gc_grain 0x601e01e5 (already in the atlas).
# Read while placing the grid in the LOOKS.BIN block (docs/GRAIN_HANG.md "The LOOKS.BIN block's tail"): alloc_phys_impl
# returns pool base + index * stride and writes nothing into the block (its bookkeeping is the counters at 0xa2728f28.. and
# the bitmaps below), so the 64 B a block has past its class size are never touched by the allocator.
SRC = 'patches/halation_h6'
p = 'pipeline'

# ---- stock: the fixed-block pools
E(0x60022d9f, 'pool_bit_set', 'func', 'rtos', 'V', 'a0 = bitmap, d0 = block index; retf [d2],4', 'alloc_phys_impl marks a block taken: word index >> 5, bit index & 31 (bitmaps 0xa27291f4 / 0xa272920c / 0xa2729210 for classes 0 / 1 / 2, table 0x60026e24)', SRC)
E(0x60022db5, 'pool_bit_clear', 'func', 'rtos', 'V', 'a0 = bitmap, d0 = block index; retf [d2],4', 'The same for a freed block', SRC)
E(0x60022b23, 'free_phys_impl', 'func', 'rtos', 'V', 'd0 = class, a0 = block; [d2,d3,a2,a3],40', 'free 0x600227b4 picks the class from the block\'s address range and comes here; takes cpu_lock, per-CPU tables by (0x8050)', SRC)

# ---- ours: grain_cpu r2 and halation h2 pieces that h6 uses or replaces
E(0x601e018a, 'gc_open', 'func', p, 'V', 'd0 = bus address -> a0 = CPU address or 0, d0 = lock token, d1 = window mode to restore or -1; [d2,d3,a2,a3],32',
  'Ours (grain_cpu r2): cpu_lock, then direct (0xa0000000..0xafffffff), this CPU\'s window if its mode already fits (gc_btab / gc_mtab by 128 MB slice), or window_map. Add -0x40000000 for the cached alias. Used by grain g2 and halation h6', SRC)
E(0x601de880, 'hl_lvl', 'func', p, 'V', 'a0 = job -> d0 = grain level 1..3, 4 = halation only, 0 = stock; [d2,d3],16', 'Ours (halation h2): replaces gc_gs\'s call gc_lvl; leaves tint << 4 | stage at grain record +96. Unchanged by h6', SRC)
E(0x601de8e6, 'hl_grain', 'func', p, 'V', 'a0 = 0x1000 buffer record, d0 = level 1..4; on gc_grain\'s 144 frame', 'Ours (halation h2): replaces gc_gs\'s call gc_grain: call hl_run,[d2,d3,a2,a3],96 when record +96 is set, then jmp gc_grain for levels 1..3. Unchanged by h6', SRC)
E(0x601de917, 'hl_run', 'site', p, 'V', 'a0 = buffer record, d0 = tint << 4 | stage; frame [d2,d3,a2,a3],96 (locals 4..76)', 'Ours (halation h2): the three passes. h6: its first 5 B are `jmp h6_run`; the rest, hl_pa 0x601e3ae4, hl_pb 0x601e0850, hl_box, hl_li, hl_gpb, hl_row, hl_seg, hl_pc 0x605b7780, hl_x98 and the tables hl_tint / hl_gm stay in place, unused (docs/CODE_SPACE_MAP.md "halation h6")', SRC)

# ---- ours: h6 (sec-5 dead sdk-api claim 0x607c6420..0x607c8420, code 0x607c6430..0x607c6fc0)
E(0x607c6430, 'h6_run', 'func', p, 'V', 'jmp from hl_run; a0 = buffer record, d0 = tint << 4 | stage; ret [d2,d3,a2,a3],96',
  'Ours (halation h6): h2\'s record checks, gmax / tint row, then the cell grid: L+5824 of the LOOKS.BIN block when P (ap_P) has EP7F, L is 4-aligned in the class-2 pool with EP7L and the back pointer, and the grid fits 10560 B; else one malloc. Then h6_pa', SRC)
E(0x607c6585, 'h6_pa', 'site', p, 'V', 'context = hl_run\'s frame', 'Ours: pass A driver. Bound of one row (8,sp) = W / 2 * 10 + 120; rows 2, 6, 10.. through h6_rows (4 rows a lock at 5184 wide)', SRC)
E(0x607c65c0, 'h6_pb', 'site', p, 'V', '', 'Ours: pass B. h6_box on every grid row, then every column; u = min(255, 21 v >> 3), g = (u (511 - u) >> 8) gmax >> 8; no cell or more than a third of the cells at g >= 16: exit (h2\'s cap)', SRC)
E(0x607c663b, 'h6_pc', 'site', p, 'V', '', 'Ours: pass C driver. Band j = rows 32 + 64 j .. 95 + 64 j (from 0 for j = 0) on cell rows j and min(j + 1, GH - 1): the columns with glow give the first / last strip (72) / (76) and the bound of one row; a band without glow is skipped (h6_band 0x607c6644, h6_next 0x607c66e7)', SRC)
E(0x607c66ef, 'h6_exit', 'site', p, 'V', '', 'Ours: frees the grid if it was a malloc ((40,sp)), ret [d2,d3,a2,a3],96 (h6_ret 0x607c66fc)', SRC)
E(0x607c66ff, 'h6_box', 'func', p, 'V', 'a0 = u8 line, d0 = n, d1 = stride; [d2,d3,a2,a3],24', 'Ours: two [1 2 1] / 4 passes in place (the value before is kept in a register): h2\'s hl_box without its u16 temp buffer', SRC)
E(0x607c672d, 'h6_rows', 'func', p, 'V', 'a1 = context, d0 = first row, d1 = rows at most -> d0 = 0, d1 = rows done; d0 = 1: window refused; [d2,d3,a2,a3],64',
  'Ours: one gc_open / flush or mode restore / cpu_unlock around several rows. A further row joins while it lies in the same 128 MB slice and work done + the bound of a row (8,a1) <= HL_CAP - 300 (120000); pass A counts a row as its bound, pass C what h6_crow reports. A first row across a slice edge goes alone in two pieces', SRC)
E(0x607c68cf, 'h6_wk', 'func', p, 'V', 'a0 = address of pair d1, a1 = context, d0 = row, d1 .. d2 = pairs; [d2,d3,a2,a3],84', 'Ours: under the lock: h6_arow for pass A ((60,a1) = 0), else h6_crow', SRC)
E(0x607c68d9, 'h6_arow', 'site', p, 'V', 'as h6_wk', 'Ours: pass A, one piece of a row. Per 64-px cell (32 samples): a cell at 248 is skipped; else four groups of eight Y bytes OR-ed, one compare against T + 4 = 228 (below: none adds); a group over it sample by sample, cell += (Y - 224) >> 2, saturating at 248. Cells cut by the piece go one sample at a time', SRC)
E(0x607c6a54, 'h6_crow', 'site', p, 'V', 'as h6_wk -> d0 = bound of the work done (pairs run * 41 + strips walked * 30 + 130)',
  'Ours: pass C, one piece of a row, strip by strip (h6_seg 0x607c6ad4): a = lv(k - 1), b = lv(k), lv(c) = (64 r0[c] + (r1[c] - r0[c]) t) >> 6. a = 0 and b <= 1: skipped. Whole strip with a, b >= 1: h6_nz 0x607c6b29 straight into h6_p8. Else h6_nc 0x607c6b5f: the pairs with g >= 1 by h6_z, clipped to the piece', SRC)
E(0x607c6bed, 'h6_p8', 'site', p, 'V', 'a0 = pixel pair, a3 = end - 28, a1 = v, a2 = step', 'Ours: eight pairs a turn (36 instructions a pair): g = v >> 6, g dY once for both Y bytes, w0 g for the two chroma bytes, one compare per chroma clamp. h6_p1 0x607c6f02 takes the pairs left over', SRC)
E(0x607c6f6c, 'h6_tint', 'data', p, 'V', 's32[4][3]: dY, dC0, dC1 for red, amber, warm, cool', 'Ours: h2\'s tint rows (4-aligned); then h6_gm 0x607c6f9c u8[3] gmax 112 / 176 / 240 and h6_z 0x607c6f9f u8[33], h6_z[x] = ceil(32 / x)', SRC)
