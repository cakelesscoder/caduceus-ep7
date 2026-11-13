/* E-M1 Mark II aspect: 65:24 (id 6) / 21:9 (id 7) in the AF / AE display lookups that only know 1,3,2,4,9,10.
 * Port of the E-P7 aspect_fix t1 policy (camera-proven in E-P7 v0.29; caduceus-ep7 docs/ASPECT.md §1i): ids 6/7
 * behave as 16:9 (id 3) in the local copy only. 65:24 and 21:9 are centred full-width crops like 16:9.
 *   sv  <- 0x60ea25e2 (6)  shooting-screen selected-point validity maps, key (4,a1)   (E-P7 0x60e3bde8)
 *   ag1 <- 0x60e5f5d7 (6)  AF frame display geometry lists, key (248,a3)              (E-P7 0x60df798a)
 *   ag2 <- 0x60e5f823 (6)  same, second function                                      (E-P7 0x60df7b55)
 *   mt  <- 0x60e99d28 (5)  metering display geometry, key (40,sp)                     (E-P7 0x60e32899)
 *   ch1 <- 0x60e3be27 (6)  AF_Target_Actuator cursor-layout chain, key (56,sp) (default was 4:3)
 *   ch2 <- 0x60e3c9d7 (6)  same, second chain, key (52,sp)
 *   gt  <- 0x60d76dc9 (6)  bitmap getter &table[id] (the only reader of the table pointer 0x61fbc3e0): ids 6668 /
 *                          7086 return entry words in main-image free space (E_6668 / E_7086 -> descriptors there), so
 *                          the icons don't depend on OSD (0x101) edits (v0.4c9); 6669 / 7087 = SCP tile labels (v0.4c11)
 * No stores at all; registers only. Jump targets are --defsym symbols T_<addr>; E_<id> entry addresses likewise.
 */
 .am33_2
 .text
 .global _start
_start:

 .macro IDD r
 cmp 6,\r
 beq 91f
 cmp 7,\r
 bne 92f
91:
 mov 3,\r
92:
 .endm

sv:
 mov (8,sp),a1
 clr d1
 mov (4,a1),d2
 IDD d2
 jmp T_60ea25e8
ag1:
 clr d1
 clr d2
 mov (248,a3),d3
 IDD d3
 jmp T_60e5f5dd
ag2:
 clr d1
 clr d2
 mov (248,a3),d3
 IDD d3
 jmp T_60e5f829
mt:
 mov 0,a1
 clr d2
 mov (40,sp),d0
 IDD d0
 jmp T_60e99d2d
ch1:
 mov (56,sp),d0
 IDD d0
 cmp 9,d0
 beq 1f
 jmp T_60e3be77
1:
 jmp T_60e3be2d
ch2:
 mov (52,sp),d0
 IDD d0
 cmp 9,d0
 beq 2f
 jmp T_60e3ca27
2:
 jmp T_60e3c9dd
gt:
 mov d0,d1
 exthu d1
 cmp 6668,d1
 beq 3f
 cmp 7086,d1
 beq 4f
 cmp 6669,d1
 beq 6f
 cmp 7087,d1
 beq 7f
 cmp 0,d1
 bne 5f
 jmp T_60d76dcf
5:
 jmp T_60d76dd3
3:
 mov E_6668,a0
 retf [],0
4:
 mov E_7086,a0
 retf [],0
6:
 mov E_6669,a0
 retf [],0
7:
 mov E_7087,a0
 retf [],0
af_end:
