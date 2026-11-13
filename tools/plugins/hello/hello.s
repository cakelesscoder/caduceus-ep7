/* Caduceus plugin "hello" (E-P7 1.1, plugin ABI v1). Our own code. docs/PLUGINS.md.
 *
 * Visible effect: Setup > Firmware shows "Caduceus: 0.32P" instead of "Caduceus: 0.32" once the plugin has loaded
 * (first half-press after power-on). It copies the resident version string (API +4) into its own block, appends the
 * suffix and points hook word B+28 at the copy. Nothing else: no stock state, no file, no settings.
 *
 * Linked at 0 = file offset 0; bytes 0..31 are the header (filled by build.py), init is at 32.
 * init: entered by `calls`, a0 = API table, d0 = B (the block, uncached alias). Returns d0 0 (accept) or 1 (decline)
 * with `rets`. Uses d0, d1, a0, a1 only; d2, d3, a2, a3 and the stack are untouched.
 */
 .am33_2
 .text
 .global _start
_start:
hdr:
 .space 32

init:
 movhu (a0),d1                    /* ABI 1 */
 cmp 1,d1
 bne no
 movhu (2,a0),d1                  /* the table has fw_text (+4) */
 cmp 1,d1
 bcs no
 mov d0,a1                        /* a1 = B */
 mov a1,d1
 add buf,d1                       /* d1 = B + buf (position independent: buf is a file offset) */
 mov d1,(28,a1)                   /* hook word: read only after the loader publishes "ready" */
 mov d1,a1                        /* a1 = dst */
 mov (4,a0),a0                    /* a0 = L"0.32" */
 mov MAXC,d1
1:
 movhu (a0),d0
 cmp 0,d0
 beq 2f
 movhu d0,(a1)
 add 2,a0
 add 2,a1
 add -1,d1
 bne 1b
2:
 mov SUFFIX,d0
 movhu d0,(a1)
 clr d0
 movhu d0,(2,a1)
 rets                             /* d0 = 0: accept */
no:
 mov 1,d0
 rets

 .balign 2
buf:
 .space 2 * (MAXC + 2)
end:
