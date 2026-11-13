# New atlas entries from docs/EXTRAS_OVERLAY.md (Extras text-overlay probe, E-P7 1.1 stock main). Not merged.
# Same structure as atlas_data.py: E(addr, name, kind, subsystem, conf, sig, notes, source).
# Merge by exec'ing after atlas_data.py (E and S come from there).
p = 'ui'
SRC = 'docs/EXTRAS_OVERLAY.md'

# ---- GE text / graphics-context draw path (the recipe the overlay uses) ----
E(0x60d075a7, 'ge_draw_text', 'func', p, 'V', 'd0 style*, d1 wchar*, a0 gc, a1 rect{x0,y0,x1,y1 s16}; frame [d2,d3,a2,a3],252',
  'High-level string drawer: per-glyph through DC +28 / drawFont. Returns early if string 0 or gc+0x4c 0. Style 24 B (PLUGINS §11): +0 text colour (applied with 0x60d0fc05, overrides any gc colour; saved/restored), +4 / +8 colours (gc+0x28c/+0x290), +12 h-align, +13 v-align, +14 x off, +16 right inset, +18 y off, +20 bottom inset. Callers 0x60d0758f/0x60d455bf/0x60d4728a/0x60d473db', SRC)
E(0x60d0fc05, 'gc_set_colour', 'func', p, 'V', 'd0 colour, a0 gc; retf [d2,d3,a2,a3],16',
  'Writes gc+0x24 and gc+0x280; if gc+0x294/295 set, remaps the colour through gc+0x296..298 shifts and gc+0x274/278/27c masks. ge_draw_text overwrites it from style +0, so set the colour in the style (PLUGINS §11). 8-bit palette index; 0 = transparent', SRC)
E(0x60d0fce0, 'gc_set_font', 'func', p, 'V', 'd0 text-style id, a0 gc; ret [a2],8 -> a0 font or 0', 'Text-style id (74-B record at *(0x61fc15bc+4*bank)+74*id), not a font index; sets gc+0x4c via 0x60d0fd74. Stock calls it before every text draw (PLUGINS §11)', SRC)
E(0x60d0fd83, 'gc_set_mode', 'func', p, 'V', 'd0 value, a0 gc; retf [],0', 'Writes gc+0x34. Stock sets it to 2 before a list text draw', SRC)
E(0x60d15503, 'gpi_platform_fn', 'func', p, 'V', 'd0 id (0xc..0x89) -> a0 fn', 'Platform function lookup (open hash 0x60f96578, 32 slots). Registered by 0x60d0eec0 into DAT_61fb2588.. (font metric 0x34, draw 0x8a, etc.)', SRC)

# ---- GE screen paint and the empty post-paint hook slot ----
E(0x60d00506, 'ge_window_paint', 'func', p, 'V', 'a0 window, a1 painter; ret [d2,d3,a2,a3],32',
  'Window paint: draws the child widgets (0x60d0f3aa / 0x60d06530 / 0x60d0642a), then vtbl +164 (0xa4) then +160 (0xa0), then ge_paint_end (present). *(window+72) and a1 are the painter; gc = *(painter+8) (0x60d060e3, PLUGINS §11)', SRC)
E(0x60cfe263, 'ge_window_postpaint', 'func', p, 'V', 'retf [],0', 'The empty vtable +164 method, shared by both window classes (words 0x60f94820, 0x60fac3f0). overlay_probe re-points these to ov_post', SRC)
E(0x60f94820, 'win_vtbl_a_164', 'data', p, 'V', 'u32 = 0x60cfe263', 'Window class A vtable +164 (base 0x60f9477c). overlay_probe -> ov_post', SRC)
E(0x60fac3f0, 'win_vtbl_b_164', 'data', p, 'V', 'u32 = 0x60cfe263', 'Window class B vtable +164 (base 0x60fac34c). overlay_probe -> ov_post', SRC)

# ---- Colour Profile editor view (open/close signal for the overlay) ----
E(0x61155e14, 'colprof_view_vtbl', 'data', p, 'V', 'Colour Profile editor view vtable; +0 update 0x60dec790, +4 0x60dec697',
  'overlay_probe re-points +0 (update) to ov_upd, which sets the overlay flag each time the editor paints', SRC)
E(0x60dec790, 'colprof_view_update', 'func', p, 'V', 'a0 view; movm [d2,d3,a2,a3]; add -12; ... ret [d2,d3,a2,a3],28',
  'Rebuilds the view state (GUI data 175) via the facade; reads ALL state 0x61fc3804, picture mode 111, cursor settings 1091/1096/1097/1686', SRC)

# ---- our code (built) ----
E(0x607b8430, 'ov_upd', 'func', p, 'I', 'overlay_probe: view +0 wrapper', 'Runs 0x60dec790, then sets the .bss overlay flag (0x622ab792 = 1). Same frame/return as the body', SRC)
E(0x607b8450, 'ov_post', 'func', p, 'I', 'overlay_probe: window +164', 'Post-paint. Flag 0 -> stock retf. Flag 1 and editor on the Extras page (P valid, EP7E, axis 4) -> draws four text rows via ge_draw_text into the window gc, clears the flag', SRC)
E(0x622ab792, 'ov_flag', 'data', p, 'V', '.bss u8 (uncached 0xa22ab792)', 'overlay_probe: set by ov_upd, cleared by ov_post each frame (self-clear on editor close)', SRC)
E(0x622ab793, 'ov_counter', 'data', p, 'V', '.bss u8 (uncached 0xa22ab793)', 'overlay_probe: ghosting counter, incremented each draw, shown as 2 hex digits in row D', SRC)
