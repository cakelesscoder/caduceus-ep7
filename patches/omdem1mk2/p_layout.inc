/* Caduceus E-M1 Mark II shared state block "P" (included by sd_loader and color_creator_wheel).
 *
 * P is one heap block from the UNCACHED allocator (malloc 0x6002329a / free 0x600232d9), 128-byte aligned
 * inside a P_ALLOC-byte allocation. Uncached because the image pipeline reads it (E-P7 rule: all cores
 * see the same bytes without cache maintenance).
 * Its u16 handle lives at P_HANDLE_ADDR; P = P_BASE + (handle << 7). sd_loader's p_get validates
 * (magic + handle copy) and returns 0 if the handle is missing or clobbered; p_ensure creates P.
 *
 * P_HANDLE_ADDR 0x621e24ae: alignment padding between the byte 0x621e24ac (24 direct byte
 * accesses) and the word 0x621e24b0 in a cluster of one module's scalars; the only array base
 * nearby, 0x621e2488, is a 2-word array indexed by 0x621e2480 (ends 0x621e2490). No instruction
 * or data word references 0x621e24ad..0x621e24af. [V static 2026-11-10; camera unproven]
 * Every handle value maps into 0xa1b00000..0xa22fff80 (uncached alias of heap pools + .bss = RAM), so a
 * stray handle is read safely and rejected by the magic check. Uncached pools: 0xa1bb0fc0..0xa1bb9540,
 * 0xa1dbb540..0xa1e68000, 0xa1f80800..0xa1f8b540 (free 0x600232d9).
 */
.equ P_HANDLE_ADDR, 0x621e24ae
.equ P_BASE,        0xa1b00000
.equ P_HMAX_BYTES,  0x00800000      /* 0x10000 << 7 */
.equ P_MAGIC,       0x50314d45      /* 'EM1P' little-endian */
.equ P_ALLOC,       384             /* malloc class <= 2048 */
.equ P_SIZE,        256             /* bytes zeroed and owned (P_ALLOC - 127 >= P_SIZE) */

/* layout */
.equ P_MAGIC_OFF,   0               /* u32 'EM1P' */
.equ P_HCOPY,       4               /* u16 copy of the handle */
.equ P_SD_STATE,    6               /* u16 0 = not tried, 1 = LOOKS.BIN loaded, 0xFFFF = failed */
.equ P_BUF,         8               /* u32 LOOKS.BIN buffer (2,080 B) */
.equ P_RAW,         12              /* u32 raw malloc pointer of P */
.equ P_LOOK,        16              /* u16 active look index 0..15 */
.equ P_PAGE,        18              /* u16 editor page 0..3 */
.equ P_INIT,        20              /* u16 1 once a look was applied this session */
.equ P_HL,          22              /* s8 highlights */
.equ P_MID,         23              /* s8 midtones */
.equ P_SH,          24              /* s8 shadows */
.equ P_CHR,         25              /* s8 chroma page offset */
.equ P_DIAL,        26              /* u8 1 while a stock dial loop runs (cc_dial1/2) */
.equ P_DIAG,        27              /* u8 low byte of the last failing SetValue(617/618) */
.equ P_NLOOKS,      28              /* u16 looks in the loaded LOOKS.BIN (1..32) */
.equ P_ACTIVE,      30              /* u8 1 = a colour look drives the COLOR engine (pipeline gate) */
.equ P_HLON,        31              /* u8 1 = the look has per-sector hue/light (flags bit1) */
.equ P_CCMODE,      32              /* u32 raw property 0x9481 recorded when the Color Creator editor opens */
.equ P_KEY,         36              /* u32 last colour-stage key seen by the selector hook (diagnostic) */
.equ P_HITS,        40              /* u32 colour-stage runs the look was applied to (diagnostic) */
.equ P_SAT,         44              /* s8[12] saturation, UI sector order (-5..5) -> request+1816 */
.equ P_HUE,         56              /* s8[12] hue, UI order (-15..15) */
.equ P_LIGHT,       68              /* s8[12] light, UI order (-15..15) */
.equ P_TMP,         81              /* u8 scratch (look_fill multiplier) */
.equ P_SDTRY,       82              /* u8 LOOKS.BIN open attempts this power-on (v0.4c14; banner " C0.n") */
.equ P_STR,         80              /* u8 look strength 0..3 = x1, x1.5, x2, x3 (S up to +-10, H/L up to +-15) */
/* debug_log (v0.4b1). Patch state never goes in the loaded image (FIRMWARE_GUIDE §10 lesson 2). */
.equ P_LGON,        96              /* u8 0 = DEBUG.TXT not looked for yet, 1 = found, 2 = absent (stop looking) */
.equ P_LGSLOT,      97              /* u8 card with DEBUG.TXT: 0 = C: (slot 1), 1 = D: (slot 2) */
.equ P_LGN,         100             /* u32 reports written this power-on */
