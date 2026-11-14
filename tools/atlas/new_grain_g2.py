# New atlas entries from the grain g2 layer (patches/grain_g2, docs/GRAIN_PORT.md "g2"). E-P7 1.1.
# Same structure as atlas_data.py: E(addr, name, kind, subsystem, conf, sig, notes, source). Merged by gen.py.
# Not repeated: cpu_lock / cpu_unlock 0x6006a922 / 0x6006a96b, psw_mask 0x60054d9f, cache_flush 0x60066fc0, window_map
# 0x60067146, window_mode_get / _set 0x600672ee / 0x600672fe (atlas_data.py).
# 0x607b6430 is also kh_ret0 in new_keyhook.py: that is the shelved plugin build; plugins=False builds have g2_grain there.
SRC = 'patches/grain_g2'

E(0x60054dc0, 'psw_restore', 'func', 'rtos', 'V', 'd0 = PSW; retf [],0', 'mov d0,psw + 2 nop: cpu_unlock gives back the PSW that psw_mask returned. Between the two leaves this CPU takes no maskable interrupt (IM = 0 for cpu_lock(0))', SRC)
E(0x601e01e5, 'gc_grain', 'site', 'pipeline', 'V', 'a0 = buffer record, d0 = level 1..3; frame [d2,d3,a2,a3],144', 'Ours (grain_cpu r2): the CPU grain pass, called by gc_ob and reached by jmp from halation hl_grain. g2: its first 6 B are `jmp g2_grain; nop`; the body to gc_cls 0x601e0572, gc_fill 0x601e05c3, gc_next 0x601e060d, gc_p2 0x601e0640, gc_cach 0x601e0669, gc_tbl 0x601e0686, gc_stab 0x601e06ce and gc_G 0x601e074d stay in place, unused', SRC)
E(0x607b6430, 'g2_grain', 'func', 'pipeline', 'V', 'a0 = buffer record, d0 = level 1..3; on gc_grain\'s frame, ret [d2,d3,a2,a3],144', 'Ours (grain_g2, sec-5 dead sdk-api claim 0x607b6420..0x607c6420): r2\'s guards (+ 0x33 level), record fields, stage marks, lock / window / flush protocol, K rows per lock (build constant), slice-edge split. Noise from g2_tile, tables from g2_T, 176 B more stack, no malloc / free', SRC)
E(0x607b678f, 'g2_offs', 'func', 'pipeline', 'V', 'calls, shares the frame: blocks (80,sp), r (48,sp)', 'Ours: one block row\'s offsets. Per block tx then ty = ((r >> 8) & 0xffff) * 65 >> 16 from the photo\'s xorshift32; off[b] = ty * 128 + tx, u16 at (128 + 2b, sp). Runs outside the lock, every 64 rows', SRC)
E(0x607b67f6, 'g2_row', 'func', 'pipeline', 'V', 'calls, shares the frame: pointer (52,sp), pixels (56), x (76), tile row (84), T (8)', 'Ours: one row piece from any x. Whole 64-px blocks through g2_blk; the pixels before a block edge or after the last whole block one at a time', SRC)
E(0x607b6834, 'g2_blk', 'site', 'pipeline', 'V', 'a0 image, a2 off[b], d2 tile row, d3 blocks, a3 T', 'Ours: the block loop, 392 instructions for 64 px: a1 = tile row + off[b], then per pixel n = (k,a1), Y = (2k,a0), T[(Y << 5) + n] back to (2k,a0)', SRC)
E(0x607b7420, 'g2_tile', 'data', 'pipeline', 'V', 'u8[128][128], values 0..30', 'Ours: the noise tile (model.py tile(), xorshift seed 4880): r2\'s ring statistics in two dimensions. A block reads the 64 x 64 window at (tx, ty), 0..64', SRC)
E(0x607bb420, 'g2_T', 'data', 'pipeline', 'V', 'u8[3][256][32]: level, Y, n', 'Ours: the Low / Med / High tables, the bytes r2\'s gc_tbl builds for strengths 23 / 55 / 91, centre 991 (verify T)', SRC)
