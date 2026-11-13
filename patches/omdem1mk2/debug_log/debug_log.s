/* Caduceus OM-D E-M1 Mark II debug log (idea from caduceus-om3 debug-log).
 *
 * Switch: C:\EM1MOD\DEBUG.TXT or D:\EM1MOD\DEBUG.TXT on the card (contents ignored).
 * Output: EM1MOD\CADLOG.TXT on the same card, rewritten at each shutter TRIG event, fixed LG_SIZE bytes
 *         (space padded, CRLF at the end), because the firmware's fopen "w" is not assumed to truncate.
 *
 * v0.4b1 rewrite of the v0.4 logger, which restarted the camera at the first half-press:
 *   - every call now uses the same [regs],frame as the callee's ret (v0.4: do_debug_log entered with
 *     [d2,d3,a2,a3],36 but left with ret [],4; the string helpers entered with [],0, left with ret [],4);
 *   - no stores into the loaded image (v0.4 kept lg_on/lg_n/lg_slot/lg_buf_ptr inside this cave, the
 *     FIRMWARE_GUIDE §10 lesson-2 crash). State lives in heap P (P_LGON/P_LGSLOT/P_LGN), locals on the stack;
 *   - (0,sp) is kept free as the call slot (a nested call stores its return address there);
 *   - card-mount gate as sd_loader's sd_gate: nothing is opened before a card is mounted, and "DEBUG.TXT absent"
 *     is remembered only once a card was mounted (v0.4 could give up for the whole session at a press before mount).
 *
 * Without P (sd_loader never created it) the logger still works: it looks for DEBUG.TXT at every event and
 * reports "P: NULL". Every miss path returns to the stock instructions with stock registers.
 *
 * Runs from the Section 4 FF tail (0x6078e8c0..0x6078f000). Hook 0x6023d10a (Section 1) runs only at shutter
 * TRIG events, after boot has loaded every section.
 */

.am33_2
.text
.global _start
.global debug_log_entry

.include "p_layout.inc"

.equ LG_SIZE, 1024

_start:
debug_log_entry:
    /* (0,sp) stays free: the call below stores its return address there. */
    add -36,sp
    mov d0,(4,sp)
    mov d1,(8,sp)
    mov d2,(12,sp)
    mov d3,(16,sp)
    mov a0,(20,sp)
    mov a1,(24,sp)
    mov a2,(28,sp)
    mov a3,(32,sp)

    call do_debug_log,[d2,d3,a2,a3],36

    mov (4,sp),d0
    mov (8,sp),d1
    mov (12,sp),d2
    mov (16,sp),d3
    mov (20,sp),a0
    mov (24,sp),a1
    mov (28,sp),a2
    mov (32,sp),a3
    add 36,sp

    /* Displaced stock instructions at 0x6023d10a: movhu (0x60040d2e),d0; exth d0. The next stock instruction
     * is a call, so PSW is dead at the resume point. */
    movhu (0x60040d2e),d0
    exth d0
    jmp em1_trig_ret

/* =========================================================================
 * do_debug_log: entered as call do_debug_log,[d2,d3,a2,a3],36.
 * After add -28,sp the locals are:
 *   (0,sp) call slot   (4,sp) file handle   (8,sp) report buffer   (12,sp) card slot 0/1
 *   (16,sp) P or 0     (20,sp),(24,sp) first 8 bytes of LOOKS.BIN
 * a3 = report write cursor (the helpers advance it).
 * ========================================================================= */
do_debug_log:
    add -28,sp

    /* Card mounted? Same test as sd_loader's sd_gate. Not yet: retry at the next event. */
    mov (0x61f9deec),d0
    cmp 0,d0
    bne lg_mounted
    mov (0x61f9def0),d0
    cmp 0,d0
    bne lg_mounted
    mov (0x61f9dec4),d0
    cmp 0xf000,d0
    beq lg_mounted
    mov (0x61f9dedc),d0
    cmp 0xf000,d0
    beq lg_mounted
    jmp lg_done

lg_mounted:
    /* P = validated block or 0 (same checks as sd_loader's p_get) */
    mov 0,a2
    movhu (P_HANDLE_ADDR),d0
    cmp 0,d0
    beq lg_have_p
    mov d0,d1
    asl 7,d0
    add P_BASE,d0
    mov d0,a0
    mov (P_MAGIC_OFF,a0),d0
    cmp P_MAGIC,d0
    bne lg_have_p
    movhu (P_HCOPY,a0),d0
    cmp d1,d0
    bne lg_have_p
    mov a0,a2
lg_have_p:
    mov a2,(16,sp)
    cmp 0,a2
    beq lg_probe
    movbu (P_LGON,a2),d0
    cmp 2,d0
    beq lg_done_near
    cmp 1,d0
    bne lg_probe
    movbu (P_LGSLOT,a2),d0
    mov d0,(12,sp)
    jmp lg_run

lg_done_near:
    jmp lg_done

lg_probe:
    mov path_c_dbg,a0
    mov mode_r,a1
    call em1_fopen,[],4
    clr d1
    cmp 0,a0
    bne lg_found
    mov path_d_dbg,a0
    mov mode_r,a1
    call em1_fopen,[],4
    mov 1,d1
    cmp 0,a0
    bne lg_found

    /* No DEBUG.TXT on a mounted card: stop looking for this power-on (needs P to remember) */
    mov (16,sp),a2
    cmp 0,a2
    beq lg_done_near
    mov 2,d0
    movbu d0,(P_LGON,a2)
    jmp lg_done

lg_found:
    mov d1,(12,sp)              /* before fclose: d1 is scratch */
    call em1_fclose,[d2,a2,a3],16
    mov (16,sp),a2
    cmp 0,a2
    beq lg_run
    mov 1,d0
    movbu d0,(P_LGON,a2)
    mov (12,sp),d0
    movbu d0,(P_LGSLOT,a2)

lg_run:
    mov (16,sp),a2
    cmp 0,a2
    beq 1f
    mov (P_LGN,a2),d0
    inc d0
    mov d0,(P_LGN,a2)
1:
    mov LG_SIZE,d0
    call em1_malloc,[],4
    cmp 0,a0
    beq lg_done_near
    mov a0,(8,sp)
    mov a0,a3

    /* ---- Line 1: banner + build ---- */
    mov str_banner,a0
    call lg_puts,[],4
    mov lg_ver,a0
    call lg_puts,[],4
    call lg_crlf,[],4

    /* ---- Line 2: report number + card ---- */
    mov str_ev,a0
    call lg_puts,[],4
    clr d0
    mov (16,sp),a2
    cmp 0,a2
    beq 1f
    mov (P_LGN,a2),d0
1:
    call lg_putd,[d2,d3],12
    mov str_sl,a0
    call lg_puts,[],4
    mov (12,sp),d0
    cmp 0,d0
    bne 1f
    mov str_c,a0
    bra 2f
1:
    mov str_d,a0
2:
    call lg_puts,[],4
    call lg_crlf,[],4

    /* ---- Lines 3-4: shared state P ---- */
    mov (16,sp),a2
    cmp 0,a2
    bne p_ok
    movhu (P_HANDLE_ADDR),d0
    cmp 0,d0
    bne p_bad
    mov str_p_null,a0
    call lg_puts,[],4
    call lg_crlf,[],4
    jmp p_done
p_bad:
    mov str_p_bad,a0
    call lg_puts,[],4
    movhu (P_HANDLE_ADDR),d0
    call lg_puth4,[],4
    mov str_rpar,a0
    call lg_puts,[],4
    call lg_crlf,[],4
    jmp p_done

p_ok:
    mov str_p1,a0
    call lg_puts,[],4
    mov a2,d0
    call lg_puth8,[],4
    mov str_p_h,a0
    call lg_puts,[],4
    movhu (P_HCOPY,a2),d0
    call lg_puth4,[],4
    mov str_p_st,a0
    call lg_puts,[],4
    movhu (P_SD_STATE,a2),d0
    call lg_putd,[d2,d3],12
    mov str_p_buf,a0
    call lg_puts,[],4
    mov (P_BUF,a2),d0
    call lg_puth8,[],4
    mov str_p_nl,a0
    call lg_puts,[],4
    movhu (P_NLOOKS,a2),d0
    call lg_putd,[d2,d3],12
    call lg_crlf,[],4

    mov str_p2,a0
    call lg_puts,[],4
    movhu (P_LOOK,a2),d0
    call lg_putd,[d2,d3],12
    mov str_p_pg,a0
    call lg_puts,[],4
    movhu (P_PAGE,a2),d0
    call lg_putd,[d2,d3],12
    mov str_p_str,a0
    call lg_puts,[],4
    movbu (P_STR,a2),d0
    call lg_putd,[d2,d3],12
    mov str_p_act,a0
    call lg_puts,[],4
    movbu (P_ACTIVE,a2),d0
    call lg_putd,[d2,d3],12
    mov str_p_hits,a0
    call lg_puts,[],4
    mov (P_HITS,a2),d0
    call lg_putd,[d2,d3],12
    mov str_p_diag,a0
    call lg_puts,[],4
    movbu (P_DIAG,a2),d0
    call lg_putd,[d2,d3],12
    call lg_crlf,[],4

p_done:
    /* ---- Line 5: LOOKS.BIN on the same card: first 8 bytes ---- */
    clr d0
    mov d0,(20,sp)
    mov d0,(24,sp)
    mov (12,sp),d0
    cmp 0,d0
    bne 1f
    mov path_c_looks,a0
    bra 2f
1:
    mov path_d_looks,a0
2:
    mov mode_r,a1
    call em1_fopen,[],4
    cmp 0,a0
    beq looks_missing

    mov a0,(4,sp)
    mov sp,a0
    add 20,a0                   /* buffer (20,sp), 8 bytes: clear of the (0,sp) call slot */
    mov 1,d0
    mov 8,d1
    mov (4,sp),a1
    call em1_fread,[d2,d3,a2,a3],24
    mov (4,sp),a0
    call em1_fclose,[d2,a2,a3],16

    mov str_looks_ok,a0
    call lg_puts,[],4
    mov (20,sp),d0
    call lg_puth8,[],4
    mov str_spc,a0
    call lg_puts,[],4
    mov (24,sp),d0
    call lg_puth8,[],4
    call lg_crlf,[],4
    bra sd_done

looks_missing:
    mov str_looks_missing,a0
    call lg_puts,[],4
    call lg_crlf,[],4

sd_done:
    /* ---- Pad to LG_SIZE: spaces, then CRLF in the last two bytes ---- */
    mov (8,sp),a0
    add LG_SIZE-2,a0
pad_loop:
    cmp a0,a3
    bcc pad_end
    mov 32,d0
    movbu d0,(a3)
    inc a3
    bra pad_loop
pad_end:
    mov 13,d0
    movbu d0,(a3)
    inc a3
    mov 10,d0
    movbu d0,(a3)

    /* ---- Write CADLOG.TXT ---- */
    mov (12,sp),d0
    cmp 0,d0
    bne 1f
    mov path_c_log,a0
    bra 2f
1:
    mov path_d_log,a0
2:
    mov mode_w,a1
    call em1_fopen,[],4
    cmp 0,a0
    beq lg_free

    mov a0,(4,sp)
    mov (8,sp),a0
    mov 1,d0
    mov LG_SIZE,d1
    mov (4,sp),a1
    call em1_fwrite,[d2,d3,a2,a3],24
    mov (4,sp),a0
    call em1_fclose,[d2,a2,a3],16

lg_free:
    mov (8,sp),a0
    call em1_free,[],4

lg_done:
    add 28,sp
    ret [d2,d3,a2,a3],36

/* =========================================================================
 * Helpers. a3 = write cursor (advanced). Report text is < 400 bytes, LG_SIZE is 1024.
 * lg_puts/lg_crlf/lg_puth8/lg_puth4: call ...,[],4 / ret [],4. Clobber d0, d1, a0.
 * lg_putd: call lg_putd,[d2,d3],12 / ret [d2,d3],12. Clobbers d0, d1, a0.
 * ========================================================================= */

lg_puts:
    movbu (a0),d0
    cmp 0,d0
    beq 9f
    movbu d0,(a3)
    inc a0
    inc a3
    bra lg_puts
9:
    ret [],4

lg_crlf:
    mov 13,d0
    movbu d0,(a3)
    inc a3
    mov 10,d0
    movbu d0,(a3)
    inc a3
    ret [],4

lg_puth8:
    mov 8,a0
1:
    mov d0,d1
    lsr 28,d1
    cmp 10,d1
    bcs 2f
    add 7,d1
2:
    add 48,d1
    movbu d1,(a3)
    inc a3
    asl 4,d0
    add -1,a0
    cmp 0,a0
    bne 1b
    ret [],4

lg_puth4:
    asl 16,d0
    mov 4,a0
1:
    mov d0,d1
    lsr 28,d1
    cmp 10,d1
    bcs 2f
    add 7,d1
2:
    add 48,d1
    movbu d1,(a3)
    inc a3
    asl 4,d0
    add -1,a0
    cmp 0,a0
    bne 1b
    ret [],4

/* unsigned decimal, no leading zeros, by repeated subtraction (no mul/div) */
lg_putd:
    mov lg_p10,a0
    clr d3                  /* non-zero once a digit was printed */
1:
    mov (a0),d1
    clr d2
2:
    cmp d1,d0
    bcs 3f
    sub d1,d0
    inc d2
    bra 2b
3:
    or d2,d3
    cmp 1,d1
    beq 4f
    cmp 0,d3
    beq 5f
4:
    add 48,d2
    movbu d2,(a3)
    inc a3
5:
    inc4 a0
    cmp 1,d1
    bne 1b
    ret [d2,d3],12

/* =========================================================================
 * Read-only data (nothing below is ever written)
 * ========================================================================= */

.balign 4
lg_p10:
    .long 1000000000, 100000000, 10000000, 1000000, 100000, 10000, 1000, 100, 10, 1

path_c_dbg:
    .asciz "C:\\EM1MOD\\DEBUG.TXT"
path_d_dbg:
    .asciz "D:\\EM1MOD\\DEBUG.TXT"
path_c_log:
    .asciz "C:\\EM1MOD\\CADLOG.TXT"
path_d_log:
    .asciz "D:\\EM1MOD\\CADLOG.TXT"
path_c_looks:
    .asciz "C:\\EM1MOD\\LOOKS.BIN"
path_d_looks:
    .asciz "D:\\EM1MOD\\LOOKS.BIN"
mode_r:
    .asciz "r"
mode_w:
    .asciz "w"

.include "lgver.inc"

str_banner:
    .asciz "=== Caduceus E-M1 Mark II log | build "
str_ev:
    .asciz "Report #"
str_sl:
    .asciz " | card "
str_c:
    .asciz "C: (slot 1)"
str_d:
    .asciz "D: (slot 2)"

str_p1:
    .asciz "P: 0x"
str_p_h:
    .asciz " H: 0x"
str_p_st:
    .asciz " SD_ST: "
str_p_buf:
    .asciz " BUF: 0x"
str_p_nl:
    .asciz " NLOOKS: "

str_p2:
    .asciz "LK: #"
str_p_pg:
    .asciz " PG: "
str_p_str:
    .asciz " STR: "
str_p_act:
    .asciz " ACT: "
str_p_hits:
    .asciz " HITS: "
str_p_diag:
    .asciz " DIAG: "

str_p_null:
    .asciz "P: NULL (no handle)"
str_p_bad:
    .asciz "P: INVALID (handle 0x"
str_rpar:
    .asciz ")"

str_looks_ok:
    .asciz "LOOKS.BIN: found | header 0x"
str_spc:
    .asciz " 0x"
str_looks_missing:
    .asciz "LOOKS.BIN: NOT FOUND"
