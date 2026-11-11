/* Olympus OM-D E-M1 Mark II Firmware 3.70 - Color Creator Caduceus Look Selector
 *
 * Implements pure Caduceus Live View Color Creator architecture (matching E-P7 ed_ui / ed_view):
 *   - Hooks the Live View Color Creator 56-byte editor parent controller record at 0x61259c40 (key 0x13a9):
 *       +04 (0x61259c44): cc_init  (stock 0x60e8b9bd) — initializes children, sets page=0 (Film), applies look
 *       +12 (0x61259c4c): cc_up    (stock 0x60e8bda4) — Up arrow & Rear Dial (+) per-click
 *       +16 (0x61259c50): cc_down  (stock 0x60e8bedf) — Down arrow & Rear Dial (-) per-click
 *       +20 (0x61259c54): cc_left  (stock 0x60e8c0f5) — Left arrow & Front Dial (+) per-click
 *       +24 (0x61259c58): cc_right (stock 0x60e8c46a) — Right arrow & Front Dial (-) per-click
 *       +28 (0x61259c5c): cc_dial1 (stock 0x60e8c786) — Rear Dial wrapper (sets dial_active flag around stock loop)
 *       +32 (0x61259c60): cc_dial2 (stock 0x60e8c9d3) — Front Dial wrapper (sets dial_active flag around stock loop)
 *       +36 (0x61259c64): cc_page  (stock 0x60e8cc69) — intercepts TRASH (0x9016) to cycle pages
 *       +44 (0x61259c6c): cc_info  (stock 0x60e8d038) — intercepts INFO (0x9014) to cycle pages
 *   - Hooks the Color Creator View Part Table Guide Label writer in .data init at 0x60297fb4:
 *       cc_guide (stock 0x60e543d6) — writes kind-5 inline UTF-16LE text to (40, view) / (48, view)
 *       displaying the active look name (Page 0) or live page values (Chroma, Luminance, Midtones).
 *
 * Pages (P_PAGE in the shared state block P, see ../p_layout.inc), INFO / TRASH cycle 0..2:
 *   - Page 0 (Film): arrows step the look; the look drives the E-P7 COLOR engine (sd_loader cc_sel/cc_hl:
 *       12-sector S, per-sector H/L) plus tone 384/692/383 (HL/MID/SH, read by the image request); colour looks reset Color Creator
 *       vividness (618) to 0, mono looks set -4. Dials: stock wheel (vividness 618 / hue 617).
 *       Banner: name, " Exx" (failed 617/618 write), " C<card state>", " K<key>" and "+" once applied.
 *   - Page 1 (Chroma): offset on all 12 sectors of the look's S (-5..+5).
 *   - Page 2 (Luminance): Front Dial & Left/Right = Highlights (384), Rear Dial & Up/Down = Shadows (383).
 *   Page 3 (Strength): x1 / x1.5 / x2 / x3 on the look's S, hue and light. Midtone comes from the look only.
 *
 * Cave location: 0x612e6900, Section 6 FF tail 0x612e68c4..0x612e7000 (Section 6 ends at 0x612e7000;
 *   nothing past it is loaded). Built-in looks are in the Section 5 tail (build.py BUILTIN_ADDR).
 *
 * State: heap block P (../p_layout.inc), owned by sd_loader (p_get / p_ensure).
 *   v0.1 and v0.2b1 used 0x621e2f76..0x621e2f87, which turned out to be inside a stock 32-entry
 *   callback ring (0x621e2f74..0x621e3073): stock overwrote the state (garbage names, looks not
 *   sticking) and the state overwrote queued callbacks.
 */

/* E-M1 II setting ids (sid table 0x604f808c, validator table 0x604ee648 (unsorted); see
 * em1mk2/docs/ARCHITECTURE_AND_MEMORY_MAP.md §7.3). This body's ids are the E-P7's minus 2. */
.equ SID_CC_HUE,   617      /* 0xE8F1, 0..29  -> request +24206 */
.equ SID_CC_VIVID, 618      /* 0xE909, -4..+3 -> request +24207 */
/* Tone = the properties the image request reads directly (request builder 0x602d243d/2453/2466 ->
 * request +24937..+24939; same keys and mapping as the E-P7: TONE_ENDS.md §1.3 "384 HL / 694 MID / 383 SH").
 * On the E-P7 they are refreshed from the per-mode 891..893; the E-M1 II has that storage (889..891) but no
 * code using it, so v0.3b5 writes the request-side values. Half-word, validator -7..+7.
 * History: 889..891 (v0.2b1-v0.3b2) dead, no readers; 449/450 (v0.3b3-b4) stored with callbacks, but no
 * visible effect in live view or JPEG in Color Creator (camera, 2026-11-11). */
.equ SID_TONE_HL,  384      /* 0x3739 Highlights */
.equ SID_TONE_MID, 692      /* 0xEFC9 Midtones (no stock UI on this body, but the request reads it) */
.equ SID_TONE_SH,  383      /* 0x3719 Shadows */
.equ N_PAGES,      4        /* Film, Chroma, Luminance, Strength */
.equ VIVID_MIN,    -4       /* lowest valid 618 value; there is no monochrome in Color Creator */

.include "p_layout.inc"

.am33_2
.text
.global _start
.global cc_init
.global cc_up
.global cc_down
.global cc_left
.global cc_right
.global cc_dial1
.global cc_dial2
.global cc_page
.global cc_info
.global cc_guide
.global scp_cc_label

_start:

/* State lives in the heap block P (../p_layout.inc), created and validated by sd_loader's
 * p_ensure / p_get (Section 2; Section 6 may call it, load order 1,7,2,3,4,5,6).
 *   call p_get,[d2,d3],12             -> a0 = P or 0; preserves d0, d1, a1
 *   call p_ensure,[d2,d3,a2,a3],20    -> a0 = P (created if needed) or 0
 * Convention: handlers keep P in a2; helpers entered by `call X,[d2,d3,a2,a3],N` read it from a2.
 * Without P every handler behaves as stock. v0.1/v0.2b1 kept this state at 0x621e2f76.., inside
 * the stock callback ring 0x621e2f74..0x621e3073 (garbage names, looks not sticking). */

/* =========================================================================
 * 1. cc_init: Controller Record +4 (Create, stock 0x60e8b9bd)
 * CALLS entry: a0 = parent, d0 = key (0x13a9)
 * ========================================================================= */
cc_init:
    movm [d2,d3,a2,a3],(sp)
    add -16,sp
    mov a0,a3

    /* Stock init first so Child 0 (124,a3) & Child 1 (128,a3) exist */
    calls em1_cc_init
    mov d0,d3

    call p_ensure,[d2,d3,a2,a3],20
    cmp 0,a0
    beq 9f
    mov a0,a2

    /* Record the raw picture-mode property while the Color Creator editor is open: the colour-stage
     * hook applies looks only while 0x9481 still has this value (sd_loader cc_sel). */
    mov 0x9481,d0
    clr d1
    mov 0,a0
    call em1_getter,[d2,d3],12
    mov d0,(P_CCMODE,a2)

    /* Always start on Page 0 (Film) with dial_active = 0 */
    clr d0
    movhu d0,(P_PAGE,a2)
    movbu d0,(P_DIAL,a2)

    /* First entry this session: apply look 0 */
    movhu (P_INIT,a2),d0
    cmp 0,d0
    bne 1f
    mov 1,d0
    movhu d0,(P_INIT,a2)
    clr d0
    movhu d0,(P_LOOK,a2)
    call apply_active_look,[d2,d3,a2,a3],20
    bra 2f
1:
    /* Later entries: pick up the current Highlight/Shadow settings 449/450 */
    mov SID_TONE_HL,d0
    call get_setting_facade,[d2,d3,a2,a3],24
    movbu d0,(P_HL,a2)
    mov SID_TONE_SH,d0
    call get_setting_facade,[d2,d3,a2,a3],24
    movbu d0,(P_SH,a2)
2:
    call sync_children_and_view,[d2,d3,a2,a3],20
9:
    mov d3,d0
    ret [d2,d3,a2,a3],32


/* =========================================================================
 * 2. cc_dial1 / cc_dial2: Rear Dial (+28) & Front Dial (+32) Wrappers
 * Set P_DIAL = 1 while the stock dial loop calls cc_up/down/left/right once per detent.
 * Frame 16: (0,sp) call slot, 12 B saved d2/d3/a2. a2 = parent, d2 = P (or 0).
 * ========================================================================= */
cc_dial1:
    movm [d2,d3,a2],(sp)
    add -4,sp
    mov a0,a2
    call p_get,[d2,d3],12
    mov a0,d2
    cmp 0,d2
    beq 1f
    mov 1,d3
    movbu d3,(P_DIAL,a0)
1:
    mov a2,a0
    calls em1_cc_dial1
    cmp 0,d2
    beq 2f
    mov d2,a0
    clr d3
    movbu d3,(P_DIAL,a0)
2:
    ret [d2,d3,a2],16

cc_dial2:
    movm [d2,d3,a2],(sp)
    add -4,sp
    mov a0,a2
    call p_get,[d2,d3],12
    mov a0,d2
    cmp 0,d2
    beq 1f
    mov 1,d3
    movbu d3,(P_DIAL,a0)
1:
    mov a2,a0
    calls em1_cc_dial2
    cmp 0,d2
    beq 2f
    mov d2,a0
    clr d3
    movbu d3,(P_DIAL,a0)
2:
    ret [d2,d3,a2],16


/* =========================================================================
 * 3. cc_info & cc_page: Cycle Pages on INFO (0x9014) or TRASH (0x9016)
 * CALLS entry: a0 = parent, d0 = event, d1 = arg
 * ========================================================================= */
cc_page:
    cmp 0x9016,d0
    beq cc_info
    jmp em1_cc_page

cc_info:
    movm [d2,d3,a2,a3],(sp)
    add -12,sp
    mov a0,a3
    call p_get,[d2,d3],12
    cmp 0,a0
    bne 2f
    /* No P: stock behaviour */
    mov a3,a0
    cmp 0x9016,d0
    beq 1f
    calls em1_cc_info
    ret [d2,d3,a2,a3],28
1:
    calls em1_cc_page
    ret [d2,d3,a2,a3],28
2:
    mov a0,a2
    /* Cycle page: 0 -> 1 -> 2 -> 3 -> 0 */
    movhu (P_PAGE,a2),d0
    inc d0
    cmp N_PAGES,d0
    bcs 3f
    clr d0
3:
    movhu d0,(P_PAGE,a2)
    bra cc_poke_child


/* =========================================================================
 * 4. cc_up / cc_down / cc_left / cc_right: arrows, and dials via the stock dial loop
 * CALLS entry: a0 = parent, d0 = event, d1 = arg
 * Registers are saved FIRST: the stock dial loop (0x60e8c786 / 0x60e8c9d3) keeps its detent
 * counter in d2 and count in d3 (v0.1 overwrote both). Frame 28: (0,sp) call slot,
 * (4,sp) incoming d0, (8,sp) incoming d1, 16 B saved regs. a3 = parent, a2 = P, d3 = direction.
 * ========================================================================= */
cc_up:
    movm [d2,d3,a2,a3],(sp)
    add -12,sp
    mov a0,a3
    mov d0,(4,sp)
    mov d1,(8,sp)
    mov 1,d3
    bra cc_up_down_common

cc_down:
    movm [d2,d3,a2,a3],(sp)
    add -12,sp
    mov a0,a3
    mov d0,(4,sp)
    mov d1,(8,sp)
    mov -1,d3

cc_up_down_common:
    call p_get,[d2,d3],12
    cmp 0,a0
    beq cc_ud_stock
    mov a0,a2
    movhu (P_PAGE,a2),d2
    cmp 0,d2
    beq cc_ud_p0
    cmp 2,d2
    beq cc_ud_lum
    bra cc_ud_stock

cc_ud_p0:
    /* Page 0: dial = stock Vividness; Up/Down arrows step the look */
    movbu (P_DIAL,a2),d2
    cmp 0,d2
    bne cc_ud_stock
    mov d3,d2
    call step_film_profile,[d2,d3,a2,a3],20
    bra cc_poke_child

cc_ud_lum:
    mov d3,d2
    call step_shadows,[d2,d3,a2,a3],20
    bra cc_poke_child

cc_ud_stock:
    mov a3,a0
    mov (4,sp),d0
    mov (8,sp),d1
    cmp 0,d3
    bgt 1f
    calls em1_cc_down
    ret [d2,d3,a2,a3],28
1:
    calls em1_cc_up
    ret [d2,d3,a2,a3],28

cc_left:
    movm [d2,d3,a2,a3],(sp)
    add -12,sp
    mov a0,a3
    mov d0,(4,sp)
    mov d1,(8,sp)
    mov -1,d3
    bra cc_left_right_common

cc_right:
    movm [d2,d3,a2,a3],(sp)
    add -12,sp
    mov a0,a3
    mov d0,(4,sp)
    mov d1,(8,sp)
    mov 1,d3

cc_left_right_common:
    call p_get,[d2,d3],12
    cmp 0,a0
    beq cc_lr_stock
    mov a0,a2
    movhu (P_PAGE,a2),d2
    cmp 0,d2
    beq cc_lr_p0
    cmp 1,d2
    beq cc_lr_chr
    cmp 2,d2
    beq cc_lr_lum
    /* Page 3 (Strength) */
    mov d3,d2
    call step_strength,[d2,d3,a2,a3],20
    bra cc_poke_child

cc_lr_p0:
    /* Page 0: dial = stock Hue; Left/Right arrows step the look */
    movbu (P_DIAL,a2),d2
    cmp 0,d2
    bne cc_lr_stock
    mov d3,d2
    call step_film_profile,[d2,d3,a2,a3],20
    bra cc_poke_child

cc_lr_chr:
    mov d3,d2
    call step_chroma,[d2,d3,a2,a3],20
    bra cc_poke_child

cc_lr_lum:
    mov d3,d2
    call step_highlights,[d2,d3,a2,a3],20
    bra cc_poke_child

cc_lr_stock:
    /* stock left = 0x60e8c0f5, right = 0x60e8c46a (record +20 / +24) */
    mov a3,a0
    mov (4,sp),d0
    mov (8,sp),d1
    cmp 0,d3
    bgt 1f
    calls em1_cc_left
    ret [d2,d3,a2,a3],28
1:
    calls em1_cc_right
    ret [d2,d3,a2,a3],28


/* =========================================================================
 * 5. cc_poke_child & sync_children_and_view (a3 = parent):
 * Re-read Child 0 (Hue, parent+124) & Child 1 (Vivid, parent+128) from the settings and send
 * 0x900c so each commits and redraws (stock commit 0x60e4c0a7, sync 0x60e4a59c).
 * ========================================================================= */
cc_poke_child:
    call sync_children_and_view,[d2,d3,a2,a3],20
    mov 1,d0
    ret [d2,d3,a2,a3],28

sync_children_and_view:
    mov (124,a3),a0
    cmp 0,a0
    beq 1f
    call em1_child_sync,[d2,d3,a2,a3],76
    mov (124,a3),a0
    mov 36876,d0
    clr d1
    mov (a0),a1
    mov (a1),a1
    calls (a1)
1:
    mov (128,a3),a0
    cmp 0,a0
    beq 2f
    call em1_child_sync,[d2,d3,a2,a3],76
    mov (128,a3),a0
    mov 36876,d0
    clr d1
    mov (a0),a1
    mov (a1),a1
    calls (a1)
2:
    ret [d2,d3,a2,a3],20


/* =========================================================================
 * 6. cc_guide: Color Creator View Part 3 Guide Label Writer
 * Hooked at .data init 0x60297fb4 (stock 0x60e543d6). CALLS entry: a0 = view.
 * Frame 32: (0,sp) call slot, (8,sp) stock result, (12,sp) P, 16 B saved regs.
 * Without P the stock label stays.
 * ========================================================================= */
cc_guide:
    movm [d2,d3,a2,a3],(sp)
    add -16,sp
    mov a0,a3

    calls em1_cc_guide
    mov d0,(8,sp)

    call p_get,[d2,d3],12
    cmp 0,a0
    bne 0f
    jmp guide_done
0:
    mov a0,(12,sp)

    /* Label kind = 5 (inline UTF-16LE text) at (40, view); clear 33 u16 units at view+48 */
    mov 5,d0
    movhu d0,(40,a3)
    mov 2,d0
    movhu d0,(46,a3)
    mov a3,a0
    add 48,a0
    mov 33,d3
    clr d0
1:
    movhu d0,(a0)
    add 2,a0
    add -1,d3
    bne 1b

    /* a2 = destination (view + 48) */
    mov a3,a2
    add 48,a2

    mov (12,sp),a0
    movhu (P_PAGE,a0),d1
    cmp 0,d1
    beq guide_page_film
    cmp 1,d1
    beq guide_page_chroma
    cmp 2,d1
    beq guide_page_lum

    cmp 3,d1
    beq guide_page_str

guide_page_str:
    /* Page 3: "Strength x1.5" */
    mov str_strength,a1
    call copy_ascii_to_u16,[],4
    mov (12,sp),a0
    movbu (P_STR,a0),d0
    and 3,d0
    asl 2,d0
    mov str_str_vals,a1
    add d0,a1
    call copy_ascii_to_u16,[],4
    jmp guide_done

guide_page_chroma:
    /* Page 1: "Chroma: +0" */
    mov str_chroma,a1
    call copy_ascii_to_u16,[],4
    mov (12,sp),a0
    movbu (P_CHR,a0),d0
    extb d0
    call append_signed_num,[],4
    bra guide_done

guide_page_lum:
    /* Page 2: "Lum H:+0 S:+0", read back from the settings */
    mov str_lum_h,a1
    call copy_ascii_to_u16,[],4
    mov SID_TONE_HL,d0
    call get_setting_facade,[d2,d3,a2,a3],24
    call append_signed_num,[],4
    mov str_lum_s,a1
    call copy_ascii_to_u16,[],4
    mov SID_TONE_SH,d0
    call get_setting_facade,[d2,d3,a2,a3],24
    call append_signed_num,[],4
    bra guide_done

guide_page_film:
    mov (12,sp),a0
    call look_name_ptr,[],4        /* a1 = ASCII name of the active look */
    call copy_ascii_to_u16,[],4

    /* Diagnostic: " E58" (camera busy) / " E16" (rejected) when a 617/618 write failed during
     * the last look apply. Names are capped at 16 characters, so this fits the buffer. */
    mov (12,sp),a0
    movbu (P_DIAG,a0),d0
    cmp 0,d0
    beq guide_card
    mov 0x20,d1
    movhu d1,(a2)
    mov 0x45,d1
    movhu d1,(2,a2)
    add 4,a2
    mov d0,d1
    lsr 4,d1
    call put_hex_digit,[],4
    mov d0,d1
    and 15,d1
    call put_hex_digit,[],4

guide_card:
    /* Card state: " C1" LOOKS.BIN loaded, " C0" not tried yet, " CF" tried and failed/absent */
    mov (12,sp),a0
    movhu (P_SD_STATE,a0),d0
    mov 0x20,d1
    movhu d1,(a2)
    mov 0x43,d1
    movhu d1,(2,a2)
    add 4,a2
    mov d0,d1
    and 15,d1
    call put_hex_digit,[],4

    /* Pipeline diagnostic: " K" + low 16 bits of the last colour-stage key (hex), "+" once the look
     * was applied to a frame (P_HITS). No key yet = the selector hook has not run. */
    mov (12,sp),a0
    mov (P_KEY,a0),d0
    cmp 0,d0
    beq guide_done
    mov 0x20,d1
    movhu d1,(a2)
    mov 0x4b,d1
    movhu d1,(2,a2)
    add 4,a2
    mov d0,d1
    lsr 12,d1
    call put_hex_digit,[],4
    mov d0,d1
    lsr 8,d1
    call put_hex_digit,[],4
    mov d0,d1
    lsr 4,d1
    call put_hex_digit,[],4
    mov d0,d1
    call put_hex_digit,[],4
    mov (12,sp),a0
    mov (P_HITS,a0),d0
    cmp 0,d0
    beq guide_done
    mov 0x2b,d1
    movhu d1,(a2)
    add 2,a2

guide_done:
    mov (8,sp),d0
    ret [d2,d3,a2,a3],32

/* Helper: look_name_ptr (a0 = P) -> a1 = name of the active look (record +48). Uses d0, d1.
 * Falls back to the built-in record when the name does not start with a printable character. */
look_name_ptr:
    movhu (P_LOOK,a0),d0
    call look_rec,[],4             /* a1 = record */
    add 48,a1
    movbu (a1),d1
    cmp 0x20,d1
    bcs 1f
    cmp 0x7f,d1
    bcs 2f
1:
    movhu (P_LOOK,a0),d0
    and 15,d0
    asl 6,d0
    mov builtin_looks+48,a1
    add d0,a1
2:
    ret [],4

/* Helper: look_rec (a0 = P, d0 = look index) -> a1 = 64-byte look record. Uses d0, d1.
 * Card (E-P7 LOOKS.BIN, records at buf + 64 + 64 i) when loaded and i < n, else built-in i mod 16. */
look_rec:
    movhu (P_SD_STATE,a0),d1
    cmp 1,d1
    bne 1f
    mov (P_BUF,a0),a1
    cmp 0,a1
    beq 1f
    movhu (P_NLOOKS,a0),d1
    cmp d1,d0
    bcc 1f
    asl 6,d0
    add 64,d0
    add d0,a1
    ret [],4
1:
    and 15,d0
    asl 6,d0
    mov builtin_looks,a1
    add d0,a1
    ret [],4

/* Helper: copy_ascii_to_u16
 * Copies up to 16 printable ASCII chars from a1 into UTF-16LE at a2 (advancing a2); stops at
 * NUL or any byte outside 0x20..0x7e. Uses d0, d3. */
copy_ascii_to_u16:
    mov 16,d3
1:
    cmp 0,d3
    beq 2f
    movbu (a1),d0
    cmp 0x20,d0
    bcs 2f
    cmp 0x7f,d0
    bcc 2f
    movhu d0,(a2)
    inc a1
    add 2,a2
    add -1,d3
    bra 1b
2:
    ret [],4

/* Helper: put_hex_digit
 * Writes hex digit d1 (0..15) as UTF-16LE at a2 (advancing a2). Leaves d0 alone. */
put_hex_digit:
    and 15,d1
    cmp 10,d1
    bcs 1f
    add 7,d1            /* 'A' - '0' - 10 */
1:
    add 0x30,d1
    movhu d1,(a2)
    add 2,a2
    ret [],4

/* Helper: append_signed_num
 * Writes signed integer d0 (-9..+9) as '+N', '-N', or ' 0' into UTF-16LE at a2 (advancing a2).
 * Out-of-range values print as '?'. Uses d0, d1, d2. */
append_signed_num:
    mov 0x2b,d1         /* '+' */
    cmp 0,d0
    bgt 1f
    mov 0x20,d1         /* ' ' */
    beq 1f
    mov 0x2d,d1         /* '-' */
    clr d2
    sub d0,d2
    mov d2,d0
1:
    movhu d1,(a2)
    add 2,a2
    cmp 9,d0
    bls 2f
    mov 0x3f-0x30,d0    /* '?' */
2:
    add 0x30,d0
    movhu d0,(a2)
    add 2,a2
    ret [],4


/* =========================================================================
 * 7. SUBROUTINES: set/get through the facade, step_*, apply_active_look (a2 = P)
 * ========================================================================= */

/* set_setting_facade: SetValue(d0 = sid, 0, d1 = value) via facade vtable[0] 0x60837170.
 * Returns d0 = 0 OK, 0xF0000058 camera busy, 0xF0000016 value/sid rejected. */
set_setting_facade:
    mov d0,d2
    mov d1,d3
    call em1_get_facade,[],4
    mov (a0),a2
    mov (a2),a2
    mov d2,d0
    exthu d0
    clr d1
    mov d3,a1
    calls (a2)
    ret [d2,d3,a2,a3],20

/* set_cc_param: set_setting_facade for 617/618; a failing return's low byte goes to P_DIAG
 * (shown as " Exx" after the look name). Stock commit 0x60e4c0a7 uses the same SetValue. */
set_cc_param:
    call set_setting_facade,[d2,d3,a2,a3],20
    cmp 0,d0
    beq 1f
    movbu d0,(P_DIAG,a2)
1:
    ret [d2,d3,a2,a3],20

/* get_setting_facade: d0 = sid -> d0 = value via facade vtable +8 GetValue(sid, &out)
 * (0x60836747). Frame 24: (0,sp) call slot, (4,sp) out, 16 B regs. */
get_setting_facade:
    mov d0,d2
    clr d0
    mov d0,(4,sp)
    call em1_get_facade,[],4
    mov (a0),a2
    mov (8,a2),a2
    mov d2,d0
    exthu d0
    mov sp,a1
    inc4 a1
    calls (a2)
    mov (4,sp),d0
    ret [d2,d3,a2,a3],24

/* step_tone: d2 = delta, d0 = P offset of the cached value, d1 = sid. Clamp -7..+7. */
step_tone:
    mov d1,d3                     /* sid */
    mov a2,a0
    add d0,a0                     /* a0 = &P[off] */
    movbu (a0),d0
    extb d0
    add d2,d0
    cmp 7,d0
    ble 1f
    mov 7,d0
1:
    cmp -7,d0
    bge 2f
    mov -7,d0
2:
    movbu d0,(a0)
    mov d0,d1
    mov d3,d0
    call set_setting_facade,[d2,d3,a2,a3],20
    call lv_refresh,[d2,d3,a2,a3],20
    ret [d2,d3,a2,a3],20

step_highlights:
    mov P_HL,d0
    mov SID_TONE_HL,d1
    call step_tone,[d2,d3,a2,a3],20
    ret [d2,d3,a2,a3],20

step_shadows:
    mov P_SH,d0
    mov SID_TONE_SH,d1
    call step_tone,[d2,d3,a2,a3],20
    ret [d2,d3,a2,a3],20

step_chroma:
    movbu (P_CHR,a2),d0
    extb d0
    add d2,d0
    cmp 5,d0
    ble 1f
    mov 5,d0
1:
    cmp -5,d0
    bge 2f
    mov -5,d0
2:
    movbu d0,(P_CHR,a2)
    /* Chroma = offset on all 12 sectors of the look's saturation (pipeline reads P_SAT) */
    call refill_look,[d2,d3,a2,a3],20
    call lv_refresh,[d2,d3,a2,a3],20
    ret [d2,d3,a2,a3],20

/* step_strength (a2 = P, d2 = +-1): look strength 0..3 = x1, x1.5, x2, x3 (sd_loader look_fill). */
step_strength:
    movbu (P_STR,a2),d0
    add d2,d0
    cmp 3,d0
    ble 1f
    mov 3,d0
1:
    cmp 0,d0
    bge 2f
    clr d0
2:
    movbu d0,(P_STR,a2)
    call refill_look,[d2,d3,a2,a3],20
    call lv_refresh,[d2,d3,a2,a3],20
    ret [d2,d3,a2,a3],20

/* refill_look (a2 = P): recompute P_SAT/P_HUE/P_LIGHT from the active look (colour looks only). */
refill_look:
    movhu (P_LOOK,a2),d0
    mov a2,a0
    call look_rec,[],4
    mov a1,a3
    movbu (45,a3),d0
    cmp 1,d0
    beq 1f
    call look_fill,[d2,d3,a2,a3],20
1:
    ret [d2,d3,a2,a3],20

/* lv_refresh: re-write Color Creator vividness (618) with its current value. The setter has no
 * unchanged-value skip (0x60863a8a always stores, runs 0x608647c0 and the listeners), and a 618 write is
 * what makes live view re-run the colour stage (look changes show; Chroma/Luminance alone did not, v0.3b3). */
lv_refresh:
    mov SID_CC_VIVID,d0
    call get_setting_facade,[d2,d3,a2,a3],24
    mov d0,d1
    mov SID_CC_VIVID,d0
    call set_setting_facade,[d2,d3,a2,a3],20
    ret [d2,d3,a2,a3],20

step_film_profile:
    movhu (P_LOOK,a2),d0
    add d2,d0
    /* number of looks: card n when loaded, else 16 */
    mov 16,d1
    movhu (P_SD_STATE,a2),d3
    cmp 1,d3
    bne 1f
    mov (P_BUF,a2),a0
    cmp 0,a0
    beq 1f
    movhu (P_NLOOKS,a2),d1
    cmp 0,d1
    bne 1f
    mov 16,d1
1:
    cmp 0,d0
    bge 2f
    mov d1,d0
    add -1,d0
    bra 3f
2:
    cmp d1,d0
    bcs 3f
    clr d0
3:
    movhu d0,(P_LOOK,a2)
    call apply_active_look,[d2,d3,a2,a3],20
    ret [d2,d3,a2,a3],20


/* apply_active_look (a2 = P). a3 = the look's 64-byte E-P7 record (webapp/src/format.ts lookRecord):
 *   +0..11 hue[12], +12..23 light[12] (UI order, -15..15), +31 flags (bit1 = H/L),
 *   +32 tone flag: 1 -> +35 HL, +36 MID, +37 SH and S nibbles +38..43 when +44 == 1;
 *                  0 -> raw S[12] at +33..44, no tone
 *   +45 class (0 colour, 1 mono), +48 name.
 * Colour: P_SAT/P_HUE/P_LIGHT for the colour-stage hooks (sd_loader cc_sel / cc_hl), P_ACTIVE = 1.
 * Mono: Color Creator cannot render B&W through the COLOR engine; P_ACTIVE = 0, vividness -4. */
apply_active_look:
    clr d0
    movbu d0,(P_DIAG,a2)
    movbu d0,(P_ACTIVE,a2)
    movbu d0,(P_CHR,a2)
    movhu (P_LOOK,a2),d0
    mov a2,a0
    call look_rec,[],4
    mov a1,a3

    /* tone */
    clr d3
    clr d2
    clr d0
    movbu (32,a3),d1
    cmp 1,d1
    bne 1f
    movbu (35,a3),d3
    movbu (36,a3),d2
    movbu (37,a3),d0
1:
    call apply_hms_common,[d2,d3,a2,a3],20

    movbu (45,a3),d0
    cmp 1,d0
    bne 2f
    /* mono */
    mov SID_CC_VIVID,d0
    mov VIVID_MIN,d1
    call set_cc_param,[d2,d3,a2,a3],20
    ret [d2,d3,a2,a3],20
2:
    /* S (+ chroma), hue, light, all x strength, and P_HLON: sd_loader look_fill (Section 2) */
    call look_fill,[d2,d3,a2,a3],20
    mov 1,d0
    movbu d0,(P_ACTIVE,a2)
    /* Color Creator's own processing still runs (its hue control acts on the image), so reset its
     * vividness to neutral 0: otherwise a mono look's -4 stays and every later look renders B&W. */
    mov SID_CC_VIVID,d0
    clr d1
    call set_cc_param,[d2,d3,a2,a3],20
    ret [d2,d3,a2,a3],20

/* Helper: apply_hms_common (d3 = hl, d2 = mid, d0 = sh) -> P cache + request tone 384 / 692 / 383. */
apply_hms_common:
    mov d0,a3
    extb d3
    movbu d3,(P_HL,a2)
    mov d3,d1
    mov SID_TONE_HL,d0
    call set_setting_facade,[d2,d3,a2,a3],20

    extb d2
    movbu d2,(P_MID,a2)
    mov d2,d1
    mov SID_TONE_MID,d0
    call set_setting_facade,[d2,d3,a2,a3],20

    mov a3,d3
    extb d3
    movbu d3,(P_SH,a2)
    mov d3,d1
    mov SID_TONE_SH,d0
    call set_setting_facade,[d2,d3,a2,a3],20
    ret [d2,d3,a2,a3],20


/* =========================================================================
 * 8. scp_cc_label: Super Control Panel Color Creator cell text
 * Hooked at 0x60e25ec8 (stock 0x60ee8cd1), entered with its own 136-byte frame:
 * (0,sp) call slot, (16,sp) a1, (20,sp) view25, (24,sp) P, (40..,sp) UTF-16 text, regs at top.
 * a0 = value record, a1 = &{view24, view25}. Without P the stock text stays.
 * ========================================================================= */
scp_cc_label:
    mov a1,(16,sp)
    call em1_scp_stock_format,[d2,d3,a2,a3],136
    mov (16,sp),a1

    mov (4,a1),a0
    cmp 0,a0
    beq scp_skip
    mov a0,(20,sp)

    call p_get,[d2,d3],12
    cmp 0,a0
    beq scp_skip
    mov a0,(24,sp)

    movhu (P_PAGE,a0),d0
    cmp 0,d0
    bne scp_page_mode

    /* Page 0: active look name */
    call look_name_ptr,[],4
    mov sp,a3
    add 40,a3
    mov a3,a2
    call copy_ascii_to_u16,[],4
    clr d0
    movhu d0,(a2)
    mov a3,a1
    bra scp_set_text

scp_page_mode:
    and 3,d0
    asl 2,d0
    mov scp_page_ptrs,a1
    add d0,a1
    mov (a1),a1

scp_set_text:
    mov (20,sp),a0
    call em1_scp_text,[d2,d3,a2,a3],24

scp_skip:
    ret [d2,d3,a2,a3],136


/* =========================================================================
 * 10. DATA TABLES: Page Labels, Built-in Preset Names, and Preset Values
 * ========================================================================= */
.balign 4
scp_page_ptrs:
    .long u16_page0
    .long u16_page1
    .long u16_page2
    .long u16_page3

u16_page0:
    .hword 'F','i','l','m',' ','L','o','o','k',0
u16_page1:
    .hword 'C','h','r','o','m','a',0
u16_page2:
    .hword 'L','u','m','i','n','a','n','c','e',0
u16_page3:
    .hword 'S','t','r','e','n','g','t','h',0

.balign 4
str_chroma:
    .asciz "Chroma: "
str_lum_h:
    .asciz "Lum H:"
str_lum_s:
    .asciz " S:"
str_strength:
    .asciz "Strength x"
str_str_vals:
    .ascii "1\0\0\0" "1.5\0" "2\0\0\0" "3\0\0\0"

/* builtin_looks (16 x 64-byte records) lives in the Section 5 FF tail (build.py BUILTIN_ADDR): Section 6
 * loads only up to 0x612e7000, which this cave nearly fills. */
