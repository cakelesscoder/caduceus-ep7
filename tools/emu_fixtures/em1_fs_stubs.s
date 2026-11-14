/* Emulator-only stand-ins for the E-M1 II file / heap calls used by sd_loader (never part of a build).
 * Same frames as the loader's calls. Control block CTL (--defsym): +0 first fopen call that succeeds (1-based; 0 = never),
 * +4 fopen calls so far, +8 file size, +12 file data address, +16 bump-heap pointer, +20 seek position. */
 .am33_2
 .text
 .global _start
_start:
s_fopen:                     /* call ..,[],4 : a0 path, a1 mode -> a0 handle or 0 */
 mov CTL,a1
 mov (4,a1),d0
 inc d0
 mov d0,(4,a1)
 mov (0,a1),d1
 cmp 0,d1
 beq 1f
 cmp d1,d0
 bcs 1f
 mov 0x9e7f0000,a0
 ret [],4
1:
 mov 0,a0
 ret [],4
s_fseek:                     /* call ..,[d2,d3,a2,a3],20 : a0 h, d0 off, d1 whence (1 END, 2 SET) -> d0 0 */
 mov CTL,a1
 cmp 1,d1
 bne 2f
 mov (8,a1),d0
2:
 mov d0,(20,a1)
 clr d0
 ret [d2,d3,a2,a3],20
s_ftell:                     /* call ..,[d2,a2,a3],16 : a0 h -> d0 pos */
 mov CTL,a1
 mov (20,a1),d0
 ret [d2,a2,a3],16
s_fread:                     /* call ..,[d2,d3,a2,a3],24 : a0 buf, d0 size 1, d1 n, a1 h -> d0 n */
 mov CTL,a2
 mov (12,a2),a3
 mov d1,d3
 mov d1,d2
3:
 cmp 0,d2
 beq 4f
 movbu (a3),d0
 movbu d0,(a0)
 inc a3
 inc a0
 add -1,d2
 bra 3b
4:
 mov d3,d0
 ret [d2,d3,a2,a3],24
s_fclose:                    /* call ..,[d2,a2,a3],16 */
 clr d0
 ret [d2,a2,a3],16
s_malloc:                    /* call ..,[],4 : d0 n -> a0 */
 mov CTL,a1
 mov (16,a1),a0
 mov a0,d1
 add 64,d0
 add d0,d1
 mov d1,(16,a1)
 ret [],4
s_free:                      /* call ..,[],4 */
 ret [],4
