/* Caduceus plugin "shortcut_cycle" (E-P7 1.1, plugin ABI 1.1 = API version 1 with >= 7 words). Our own code.
 * docs/PLUGINS.md §7-§9, §12.
 *
 * The Shortcut (Fn) button, sid 47, keycode 15, in a still mode (not movie, not AP). Cycle (state byte ST in B):
 *   press 1 (shooting, site 0): stock, Fn's assigned function (Multi Function -> the colour profile popup, select
 *           mode 49 in state 0x5800). ST 1.
 *   press 2 (popup open, site 1, ST 1, open mode != 50, key-held flag 0):
 *           API >= 8 words + feature bit 2: ka_rep = the stock "other key" exit, which replays this Fn press after
 *           the popup closes; the replay reaches site 0 with ST 2 -> aspect in the same press. ST 2. Handled.
 *           Older API: stock exit only (request 158 at record+32); the next Fn press opens aspect. ST 2. Handled.
 *   site 0 with ST 2 (the replay, or press 3 on the older API): aspect popup, select mode 50 via ka_sel. ST 3. Handled.
 *   Fn in the aspect popup (site 1, ST 3, open mode 50): stock exit. ST 0. Handled.
 * Resets: any other key at site 0 -> ST 0; a Fn press at site 0 with ST 1 or 3 means the popup was closed some other
 * way (OK, half-press, timeout) -> press 1 again. Site 1 with any other state or mode, key-held flag (selw+8) set
 * (stock ignores keys then), record+4 == 152, movie
 * (sid 44 == 1) and AP (sid 24 in 14, 209..216): stock, ST 0. Setup > Firmware shows "0.32S" while loaded.
 *
 * init (calls): a0 = API, d0 = B (uncached). Declines (d0 1) unless API version 1 with >= 7 words and feature bits 0, 1.
 * REP = 1 when the API has >= 8 words and feature bit 2 (ka_rep at +32).
 * hook (calls, from the resident key hook): d0 event, d1 B (uncached), d2 site (0 shooting, 1 select state),
 * a0 CA module (site 0) or 0, a1 event record -> d0 1 handled.
 * Position independent; data through B only. d2, d3, a2, a3 and the stack kept (movm frame).
 */
 .am33_2
 .text
 .global _start
_start:
hdr:
 .space 32

init:
 movhu (a0),d1
 cmp 1,d1
 bne no
 movhu (2,a0),d1
 cmp 7,d1
 bcs no
 mov (24,a0),d1
 and 3,d1
 cmp 3,d1
 bne no
 mov d0,a1                        /* a1 = B */
 mov a0,(API,a1)
 clr d1
 movbu d1,(ST,a1)
 movhu (2,a0),d0                  /* REP: ka_rep available */
 cmp 8,d0
 bcs 3f
 mov (24,a0),d0
 and 4,d0
 beq 3f
 mov 1,d1
3:
 movbu d1,(REP,a1)
 mov a1,d1                        /* key hook word B+24 = hook in the cached alias (read only once the loader */
 add hook - 0x40000000,d1         /* has published "ready", after init returns) */
 mov d1,(24,a1)
 mov a1,d1                        /* Firmware text, as hello: version string + SUFFIX at B + buf, B+28 -> it */
 add buf,d1
 mov d1,(28,a1)
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

/* hook: d0 event, d1 B, d2 site, a0 CA or 0, a1 record */
hook:
 movm [d2,d3,a2,a3],(sp)
 add -8,sp                        /* frame 24: (0,sp) return slot of our calls */
 mov d2,d3                        /* d3 = site */
 mov a0,d2                        /* d2 = CA (0 at site 1) */
 mov d1,a2                        /* a2 = B */
 mov a1,a3                        /* a3 = record */
 cmp EV_FN,d0
 beq 1f
 cmp 0,d3
 bne pass                         /* site 1, other event: stock, state kept */
 bra reset                        /* site 0, other key: reset */
1:
 mov (API,a2),a0
 mov (20,a0),a1                   /* ka_get */
 mov K44,d0
 clr d1
 calls (a1)
 cmp 1,d0
 beq reset                        /* movie */
 mov (API,a2),a0
 mov (20,a0),a1
 mov K24,d0
 clr d1
 calls (a1)
 cmp 14,d0
 beq reset                        /* AP */
 add -209,d0
 cmp 8,d0
 bcs reset                        /* AP 209..216 */
 movbu (ST,a2),d1
 cmp 0,d3
 bne sel
 mov (4,a3),d0                    /* site 0: shooting */
 cmp 152,d0
 beq reset
 cmp 2,d1
 beq 2f
 mov 1,d0                         /* press 1: stock */
 movbu d0,(ST,a2)
 bra pass
2:
 mov 3,d0                         /* press 3: aspect */
 movbu d0,(ST,a2)
 mov (API,a2),a0
 mov (16,a0),a2                   /* ka_sel (B no longer needed) */
 mov d2,a0                        /* CA */
 mov a3,a1                        /* record */
 mov MODE,d0
 calls (a2)
 bra done
sel:                              /* site 1: a select mode is open */
 mov (API,a2),a0
 mov (28,a0),a0
 mov (8,a0),d0                    /* key-held flag: stock ignores keys while it is set */
 cmp 0,d0
 bne reset
 mov (a0),d0                      /* its action */
 cmp 1,d1
 bne 3f
 cmp MODE,d0
 beq reset
 mov 2,d1                         /* press 2: exit, arm aspect */
 movbu d1,(ST,a2)
 movbu (REP,a2),d0
 cmp 0,d0
 beq 5f
 mov (API,a2),a0
 mov (32,a0),a0                   /* ka_rep: stock exit + replay of this press (request 158 included) */
 mov a3,a1
 calls (a0)
 bra done
5:
 mov 158,d0
 mov d0,(32,a3)
 bra done
3:
 cmp 3,d1
 bne reset
 cmp MODE,d0
 bne reset
 clr d1                           /* press 4: stock exit of aspect */
4:
 movbu d1,(ST,a2)
 mov 158,d0
 mov d0,(32,a3)
done:
 mov 1,d0
 ret [d2,d3,a2,a3],24
reset:
 clr d0
 movbu d0,(ST,a2)
pass:
 clr d0
 ret [d2,d3,a2,a3],24

 .balign 4
API = . - _start
 .long 0
ST = . - _start
 .byte 0
REP = . - _start
 .byte 0
 .balign 2
buf:
 .space 2 * (MAXC + 2)
end:
