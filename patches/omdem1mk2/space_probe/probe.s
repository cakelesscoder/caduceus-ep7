/* E-M1 Mark II code-space probe (sp1): is RAM 0x612e7000..0x61300000 loaded and left alone once section 5's loaded-end
 * word (0x60042b6d) is raised from 0x612e7000 to 0x61300000? The region holds a magic word + a fixed pseudo-random
 * pattern; this check sums it on every banner draw of the look editor and appends " S+" (loaded, intact), " S!" (loaded,
 * changed since boot) or " S0" (not loaded) to the banner text. Called as `call SPROBE,[],4` with a2 = text pointer
 * (UTF-16LE), advances a2; uses d0, d1, a0, a1 only. The code is NOT in the probed region, so a bad region can't crash.
 * --defsym REGION, REGION_END, MAGIC, EXPECT. */
 .am33_2
 .text
 .global _start
_start:
sprobe:
 mov 0x20,d1
 movhu d1,(a2)
 mov 0x53,d1
 movhu d1,(2,a2)
 add 4,a2
 mov REGION,a0
 mov (a0),d0
 cmp MAGIC,d0
 bne 3f
 clr d0
 mov REGION_END,a1
1:
 mov (a0),d1
 add d1,d0
 add 4,a0
 cmp a1,a0
 bcs 1b
 cmp EXPECT,d0
 bne 2f
 mov 0x2b,d1
 bra 4f
2:
 mov 0x21,d1
 bra 4f
3:
 mov 0x30,d1
4:
 movhu d1,(a2)
 add 2,a2
 ret [],4
