/* Olympus OM-D E-M1 Mark II Firmware 3.70 - SD Custom Looks Loader
 * Based on Caduceus v3 event-gated RTOS architecture.
 *
 * Cave location: 0x60580200 (in 71 KB clean 0xFF cave 0x6058018c..0x60591800)
 * Hook site:     0x6023d0db (TRIG1 shutter half-press classifier)
 * Continuation:  0x6023d104
 *
 * State: one heap block "P" shared with color_creator_wheel (layout in p_layout.inc).
 *   P's u16 handle lives in the halfword 0x621e24ae: compiler padding between the byte 0x621e24ac
 *   and the word 0x621e24b0 of one module's scalars (em1mk2/docs/ARCHITECTURE_AND_MEMORY_MAP.md §6).
 *   P = 0x61b00000 + (handle << 7); valid only if P+0 == 'EM1P' and P+4 == handle.
 *   v0.1 / v0.2b1 kept state at 0x621e2f76.. which is inside a stock 32-entry callback ring
 *   (0x621e2f74..0x621e3073), so stock overwrote it and it overwrote queued callbacks.
 *
 * Media status / ready registers:
 *   0x61f9deec: u32 sd1_ready (non-zero when Card 1 ready)
 *   0x61f9def0: u32 sd2_ready (non-zero when Card 2 ready)
 *   0x61f9dec4: u32 sd1_mount_status (0xf000 when Card 1 mounted)
 *   0x61f9dedc: u32 sd2_mount_status (0xf000 when Card 2 mounted)
 */

.include "p_layout.inc"

.equ LB_MAGIC, 0x42375045   /* 'EP7B' little-endian */
.equ LB_HDR,   64
.equ LB_MIN,   128          /* header + 1 look */
.equ LB_MAX,   2112         /* header + 32 looks */

.am33_2
.text
.global _start
.global sd_gate_entry
.global p_get
.global p_ensure
.global cc_sel
.global cc_hl
.global look_fill

_start:
    bra sd_hook
    nop
    nop
.balign 4
sd_gate_entry:
    bra sd_gate
    nop
    nop
.balign 4
sd_hook:
    /* Replay displaced instructions from 0x6023d0db:
     * clr d0; movhu d0,(0x621e2f6e)
     */
    clr d0
    movhu d0,(0x621e2f6e)

    /* Call gate / loader with callee-save frame */
    call sd_gate,[d2,d3,a2,a3],36

sd_back:
    clr d0
    jmp em1_trig1_ret

sd_gate:
    /* Get (or create) P; no P = do nothing this time */
    call p_ensure,[d2,d3,a2,a3],20
    cmp 0,a0
    beq sd_gate_ret
    mov a0,a3

    /* Check if already attempted this power-on */
    movhu (P_SD_STATE,a3),d0
    cmp 0,d0
    bne sd_gate_ret

    /* Check if either SD slot is ready or reported mounted (0xf000) */
    mov (0x61f9deec),d0
    cmp 0,d0
    bne sd_go
    mov (0x61f9def0),d0
    cmp 0,d0
    bne sd_go
    mov (0x61f9dec4),d0
    cmp 0xf000,d0
    beq sd_go
    mov (0x61f9dedc),d0
    cmp 0xf000,d0
    beq sd_go

    /* Neither card is ready/mounted yet.
     * Leave sd_state == 0 so we retry on the next call.
     */
sd_gate_ret:
    ret [d2,d3,a2,a3],36

sd_go:
    /* Mark attempted (0xffff = failed/no file) until proven loaded */
    mov 0xffff,d0
    movhu d0,(P_SD_STATE,a3)
    mov a3,a0
    call sd_load,[d2,d3,a2,a3],36
    ret [d2,d3,a2,a3],36

sd_load:
    /* a0 = P, kept at (16,sp): frame 36 = 20 B locals (0,sp = call slot) + 16 B saved regs.
     * LOOKS.BIN is the E-P7 v3 file (tools/ep7_looks_bin.py, webapp encodeLooksBin): 64-byte header +
     * n x 64-byte records, n = 1..32, so 128..2112 bytes. One buffer of the maximum size. */
    mov a0,(16,sp)
    mov LB_MAX,d0
    call em1_malloc,[],4
    mov a0,a2              /* a2 = buffer */
    cmp 0,a2
    beq sd_load_exit

    /* Try Card Slot 1 first: C:\EM1MOD\LOOKS.BIN */
    mov path_c,a0
    mov mode_r,a1
    call em1_fopen,[],4
    mov a0,a3              /* a3 = file handle */
    cmp 0,a3
    bne sd_have_file

    /* Try Card Slot 2 next: D:\EM1MOD\LOOKS.BIN */
    mov path_d,a0
    mov mode_r,a1
    call em1_fopen,[],4
    mov a0,a3
    cmp 0,a3
    beq sd_free            /* File not found on either card */

sd_have_file:
    /* File size with fseek(END) / ftell */
    mov a3,a0
    clr d0
    mov 1,d1               /* whence 1 = END (as stock 0x6040cb2e) */
    call em1_fseek,[d2,d3,a2,a3],20
    cmp 0,d0
    bne sd_close

    mov a3,a0
    call em1_ftell,[d2,a2,a3],16
    mov d0,d3              /* d3 = file size */
    cmp LB_MIN,d3
    bcs sd_close
    cmp LB_MAX+1,d3
    bcc sd_close
    mov d3,d0
    and 63,d0
    bne sd_close           /* 64 + 64 n */

    /* Rewind: fseek(SET, 0) */
    mov a3,a0
    clr d0
    mov 2,d1               /* whence 2 = SET */
    call em1_fseek,[d2,d3,a2,a3],20
    cmp 0,d0
    bne sd_close

    /* Read the whole file */
    mov a2,a0
    mov 1,d0
    mov d3,d1
    mov a3,a1
    call em1_fread,[d2,d3,a2,a3],24
    mov d0,d2              /* d2 = bytes read */

    mov a3,a0
    call em1_fclose,[d2,a2,a3],16
    clr a3

    cmp d3,d2
    bne sd_free            /* Short read */

    /* Validate header and CRC-32 (a0 = buffer, d0 = size) */
    mov a2,a0
    mov d3,d0
    call sd_check,[d2,d3,a2,a3],20   /* 20: sd_check calls sd_crc, so it needs the (0,sp) call slot */
    cmp 0,d0
    bne sd_free

    /* Publish: buffer, look count, loaded. Kept for the session. */
    mov (16,sp),a0
    mov a2,(P_BUF,a0)
    mov d3,d0
    add -LB_HDR,d0
    lsr 6,d0
    movhu d0,(P_NLOOKS,a0)
    mov 1,d0
    movhu d0,(P_SD_STATE,a0)
    bra sd_load_exit

sd_close:
    mov a3,a0
    call em1_fclose,[d2,a2,a3],16
sd_free:
    mov a2,a0
    call em1_free,[],4
sd_load_exit:
    ret [d2,d3,a2,a3],36

/* sd_check: E-P7 LOOKS.BIN v3 header + CRC. a0 = buffer, d0 = file size (validated 128..2112, 64-aligned).
 * Checks 'EP7B', version 3, header length 64, payload == size - 64, n == payload / 64, record length 64,
 * CRC-32 (zlib) over bytes 0..15 and 20..size-1. The E-P7-specific fields (firmware build +8, main SHA
 * prefix +20, layout CRC +28) are not checked, so one file serves both cameras.
 * Returns d0 = 0 valid, 1 invalid. */
sd_check:
    mov a0,a2
    mov d0,d3              /* d3 = size */
    mov (0,a2),d0
    cmp LB_MAGIC,d0
    bne sd_check_bad
    movhu (4,a2),d0
    cmp 3,d0
    bne sd_check_bad
    movhu (6,a2),d0
    cmp LB_HDR,d0
    bne sd_check_bad
    mov (12,a2),d0
    mov d3,d1
    add -LB_HDR,d1
    cmp d1,d0
    bne sd_check_bad
    lsr 6,d1               /* n */
    movhu (24,a2),d0
    cmp d1,d0
    bne sd_check_bad
    movhu (26,a2),d0
    cmp 64,d0
    bne sd_check_bad

    /* CRC part 1: bytes 0..15 */
    mov -1,d0
    mov a2,a0
    mov 16,d1
    call sd_crc,[d2,d3],12
    /* part 2: bytes 20..size-1 */
    mov a2,a0
    add 20,a0
    mov d3,d1
    add -20,d1
    call sd_crc,[d2,d3],12
    not d0
    mov (16,a2),d1
    cmp d1,d0
    bne sd_check_bad
    clr d0
    ret [d2,d3,a2,a3],20

sd_check_bad:
    mov 1,d0
    ret [d2,d3,a2,a3],20

/* Standard IEEE 802.3 CRC-32 routine (polynomial 0xEDB88320)
 * d0 = running CRC, a0 = data pointer, d1 = byte count (> 0)
 * Returns updated d0
 */
sd_crc:
    movbu (a0),d2
    xor d2,d0
    mov 8,d3
sd_b1:
    btst 1,d0
    beq sd_b0
    lsr 1,d0
    xor 0xedb88320,d0
    bra sd_b2
sd_b0:
    lsr 1,d0
sd_b2:
    add -1,d3
    bne sd_b1
    inc a0
    add -1,d1
    bne sd_crc
    ret [d2,d3],12

/* =========================================================================
 * p_get: a0 = P if the handle at P_HANDLE_ADDR names a valid block, else 0.
 * Entered as `call p_get,[d2,d3],12`; preserves d0, d1, a1.
 * Any handle value maps into 0x61b00000..0x622fff80 (RAM), so a clobbered handle
 * is read safely and then rejected by the magic / handle-copy check.
 * ========================================================================= */
p_get:
    movhu (P_HANDLE_ADDR),d2
    cmp 0,d2
    beq 9f
    mov d2,d3
    asl 7,d2
    add P_BASE,d2
    mov d2,a0
    mov (P_MAGIC_OFF,a0),d2
    cmp P_MAGIC,d2
    bne 9f
    movhu (P_HCOPY,a0),d2
    cmp d3,d2
    bne 9f
    ret [d2,d3],12
9:
    mov 0,a0
    ret [d2,d3],12

/* =========================================================================
 * p_ensure: a0 = P, creating it on first use (or after the handle was lost).
 * Entered as `call p_ensure,[d2,d3,a2,a3],20`. Returns a0 = 0 if malloc fails.
 * ========================================================================= */
p_ensure:
    call p_get,[d2,d3],12
    cmp 0,a0
    bne 8f
    mov P_ALLOC,d0
    call em1_malloc_unc,[],4
    cmp 0,a0
    beq 8f
    mov a0,a2              /* a2 = raw block */
    mov a0,d2
    add 127,d2
    and 0xffffff80,d2      /* 128-aligned P inside the block */
    mov d2,d3
    sub P_BASE,d3
    cmp P_HMAX_BYTES,d3    /* (P - base) >> 7 must fit 16 bits and be non-zero */
    bcc 7f
    cmp 0,d3
    beq 7f
    lsr 7,d3               /* d3 = handle */
    mov d2,a0
    /* zero P_SIZE bytes */
    mov P_SIZE,d0
    clr d1
    mov a0,a1
5:
    mov d1,(a1)
    inc4 a1
    add -4,d0
    bne 5b
    mov P_MAGIC,d0
    mov d0,(P_MAGIC_OFF,a0)
    movhu d3,(P_HCOPY,a0)
    mov a2,(P_RAW,a0)
    movhu d3,(P_HANDLE_ADDR)
8:
    ret [d2,d3,a2,a3],20
7:
    /* aligned block outside the handle range: give it back */
    mov a2,a0
    call em1_free_unc,[],4
    mov 0,a0
    ret [d2,d3,a2,a3],20

/* =========================================================================
 * Colour-stage hooks (E-P7 COLOR engine, docs ARCHITECTURE_AND_MEMORY_MAP.md §7.6).
 * The selector 0x603ec82c and builder 0x603ec642 are the E-P7's 0x603b0252 / 0x603b0068 byte for
 * byte (addresses aside). Stock runs the COLOR builder only for key 11. While a colour look is active
 * and the live picture mode (property 0x9481) equals the value recorded when the Color Creator editor
 * opened (P_CCMODE), cc_sel copies the look's 12 S bytes to request+1816 and takes the COLOR branch;
 * cc_hl then writes per-sector hue/light into the builder's 12 output records exactly like the E-P7
 * `lv` hook (patches/lv_bundles). No look / no P / other modes: stock.
 * ========================================================================= */

/* cc_sel <- jmp at 0x603ec89b (replaces cmp 11,d1; bne 0x603ec8d3; mov (12,a2),d1).
 * In: d1 = key, a2 = context, a3 = request, d3 = request+12 (live on the stock non-11 path).
 * May change d0, d2, a0, a1 (reloaded or dead on both stock paths); keeps d3, a2, a3, MDR. */
cc_sel:
    cmp 11,d1
    beq sel_color
    add -20,sp             /* (0) call slot, (4) key, (8) MDR, (12) P */
    mov d1,(4,sp)
    mov mdr,d0
    mov d0,(8,sp)
    call p_get,[d2,d3],12
    cmp 0,a0
    beq sel_stock
    mov a0,(12,sp)
    mov (4,sp),d1
    mov d1,(P_KEY,a0)
    movbu (P_ACTIVE,a0),d0
    cmp 0,d0
    beq sel_stock
    mov (P_CCMODE,a0),d0
    cmp 0,d0
    beq sel_stock
    mov 0x9481,d0          /* live picture mode (sid 111), raw */
    clr d1
    mov 0,a0
    call em1_getter,[d2,d3],12
    mov (12,sp),a0
    mov (P_CCMODE,a0),d1
    cmp d1,d0
    bne sel_stock
    mov (P_HITS,a0),d0
    inc d0
    mov d0,(P_HITS,a0)
    mov a0,a1
    add P_SAT,a1
    mov a3,a0
    add 1816,a0
    mov 12,d0
1:
    movbu (a1),d1
    movbu d1,(a0)
    inc a1
    inc a0
    add -1,d0
    bne 1b
    mov (8,sp),d0
    mov d0,mdr
    add 20,sp
sel_color:
    mov (12,a2),d1         /* displaced */
    jmp em1_sel_color      /* 0x603ec8a2: add 1816,a3; ... call builder */
sel_stock:
    mov (8,sp),d0
    mov d0,mdr
    add 20,sp
    jmp em1_sel_other      /* 0x603ec8d3: stock non-11 path */

/* cc_hl <- jmp at 0x603ec8b8, right after the builder (replaces mov (60,a2),d0; btst 2,d0).
 * a2 = context, a3 = request+1816. The builder is reached with key != 11 only through cc_sel. */
cc_hl:
    add -32,sp
    mov d1,(4,sp)
    mov d2,(8,sp)
    mov d3,(12,sp)
    mov a0,(16,sp)
    mov a1,(20,sp)
    mov a3,(24,sp)
    mov mdr,d0
    mov d0,(28,sp)
    movbu (-1808,a3),d1    /* request key (request+8..11), as the selector builds it */
    movbu (-1807,a3),d0
    movhu (-1806,a3),d2
    asl 24,d1
    asl 16,d0
    or d0,d1
    or d2,d1
    cmp 11,d1
    beq hl_out
    call p_get,[d2,d3],12
    cmp 0,a0
    beq hl_out
    movbu (P_ACTIVE,a0),d0
    cmp 0,d0
    beq hl_out
    movbu (P_HLON,a0),d0
    cmp 0,d0
    beq hl_out
    mov (12,a2),a3         /* context+12 -> colour output */
    add 688+18,a3          /* record 0 hue (E-P7 OUT_RECORDS + 18) */
    clr d2                 /* physical record r */
2:
    mov hl_perm,a1
    movbu (d2,a1),d1       /* UI index w = 2*(r%6)+r/6 */
    mov a0,a1
    add d1,a1
    movbu (P_HUE,a1),d0
    extb d0
    add 15,d0
    add d0,d0
    mov hl_hue_lut,a1
    movhu (d0,a1),d3
    movhu d3,(a3)
    mov a0,a1
    add d1,a1
    movbu (P_LIGHT,a1),d0
    extb d0
    add 15,d0
    add d0,d0
    mov hl_light_lut,a1
    movhu (d0,a1),d3
    movhu d3,(4,a3)        /* L at hue+4 */
    add 24,a3
    inc d2
    cmp 12,d2
    bne 2b
hl_out:
    mov (28,sp),d0
    mov d0,mdr
    mov (4,sp),d1
    mov (8,sp),d2
    mov (12,sp),d3
    mov (16,sp),a0
    mov (20,sp),a1
    mov (24,sp),a3
    add 32,sp
    mov (60,a2),d0         /* displaced 0x603ec8b8 */
    btst 2,d0              /* displaced 0x603ec8bb */
    jmp em1_hl_resume      /* 0x603ec8be: beq ... */

.include "hl_luts.inc"     /* hl_hue_lut, hl_light_lut (31 x s16, UI -15..15), hl_perm (12 B); build.py */

.balign 4
path_c:
    .asciz "C:\\EM1MOD\\LOOKS.BIN"
path_d:
    .asciz "D:\\EM1MOD\\LOOKS.BIN"
mode_r:
    .asciz "r"

.balign 2
/* =========================================================================
 * look_fill (GUI side, called by color_creator_wheel; lives here for space: Section 6 is full).
 * Entered as `call look_fill,[d2,d3,a2,a3],20` with a2 = P, a3 = 64-byte look record.
 * P_SAT[k]  = clamp(scale(S[k]) + P_CHR, -10, 10)  S from nibbles +38..43 (tone record, +44 == 1),
 *                                                raw +33..44 (no-tone record), else 0
 * P_HUE[k]  = clamp(scale(hue[k]), -15, 15), P_LIGHT[k] = clamp(scale(light[k]), -15, 15)
 * P_HLON    = flags +31 bit1.   scale(v) = v * m / 2, m = 2/3/4/6 for P_STR 0..3 (x1, x1.5, x2, x3).
 * No mul/div: repeated add. Stores: P only.
 * ========================================================================= */
look_fill:
    movbu (P_STR,a2),d0
    and 3,d0
    mov lf_mult,a0
    movbu (d0,a0),d0
    movbu d0,(P_TMP,a2)            /* m */
    clr d2                         /* k */
1:
    /* --- saturation --- */
    clr d0
    movbu (32,a3),d1
    cmp 1,d1
    bne 3f
    movbu (44,a3),d1
    cmp 1,d1
    bne 4f
    mov d2,d1
    lsr 1,d1
    add 38,d1
    movbu (d1,a3),d0
    btst 1,d2
    beq 2f
    lsr 4,d0
2:
    and 15,d0
    asl 28,d0
    asr 28,d0
    bra 4f
3:
    mov d2,d1
    add 33,d1
    movbu (d1,a3),d0
    extb d0
4:
    call lf_scale,[],4
    movbu (P_CHR,a2),d1
    extb d1
    add d1,d0
    mov 10,d1
    call lf_clamp,[],4
    mov a2,a0
    add d2,a0
    movbu d0,(P_SAT,a0)
    /* --- hue --- */
    movbu (d2,a3),d0
    extb d0
    call lf_scale,[],4
    mov 15,d1
    call lf_clamp,[],4
    mov a2,a0
    add d2,a0
    movbu d0,(P_HUE,a0)
    /* --- light --- */
    mov d2,d1
    add 12,d1
    movbu (d1,a3),d0
    extb d0
    call lf_scale,[],4
    mov 15,d1
    call lf_clamp,[],4
    mov a2,a0
    add d2,a0
    movbu d0,(P_LIGHT,a0)
    inc d2
    cmp 12,d2
    bne 1b
    movbu (31,a3),d0
    and 2,d0
    lsr 1,d0
    movbu d0,(P_HLON,a2)
    ret [d2,d3,a2,a3],20

/* lf_scale: d0 = d0 * m / 2 (m = P_TMP of a2). Uses d1, d3. Leaf. */
lf_scale:
    movbu (P_TMP,a2),d3
    clr d1
5:
    add d0,d1
    add -1,d3
    bne 5b
    mov d1,d0
    asr 1,d0
    ret [],4

/* lf_clamp: d0 = clamp(d0, -d1, d1). Uses d3. Leaf. */
lf_clamp:
    cmp d1,d0
    ble 6f
    mov d1,d0
6:
    clr d3
    sub d1,d3
    cmp d3,d0
    bge 7f
    mov d3,d0
7:
    ret [],4

lf_mult:
    .byte 2,3,4,6

