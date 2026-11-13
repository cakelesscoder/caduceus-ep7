# New atlas entries from docs/I18N_ZH.md (menu language, string / font lookup, E-P7 1.1 stock main). Not merged.
# Same structure as atlas_data.py: E(addr, name, kind, subsystem, conf, sig, notes, source).
SRC = 'docs/I18N_ZH.md'
u = 'ui'

E(0x60d10bf2, 'osd_string_get', 'func', u, 'V', 'd0 string id -> a0 wchar*; [d2],8', 'a0 = (*(0x61fc1530 + 4*bank))[id]; bank = 0x60d10c09. Behind ge_draw_text_res 0x60d0758f and 9 other callers', SRC)
E(0x60d10c09, 'osd_lang_bank', 'func', u, 'V', '-> d0 = (u8)(0x61fb2818); retf', 'Index into the per-bank string-table and text-style pointer arrays 0x61fc1530 / 0x61fc15bc', SRC)
E(0x60d10b88, 'osd_text_style', 'func', u, 'V', 'd0 style id -> d0 74-B record', '(0x61fc15bc)[bank] + 74*id: the text-style records gc_set_font 0x60d0fce0 reads', SRC)
E(0x61fc1530, 'osd_string_tables', 'data', u, 'V', 'u32[bank] -> u32 string pointer table', 'Bank 0 = *res (p0 of the loaded string resource), written by 0x60eac6f2', SRC)
E(0x61fc15bc, 'osd_style_tables', 'data', u, 'V', 'u32[bank]', 'Bank 0 = res[1] of the loaded string resource (text styles / pFontsList)', SRC)
E(0x60eac6f2, 'gui_load_language', 'func', u, 'V', 'd0 mode (0/1 load strings, 0 also res type 1)', 'Reads sid 3009 (facade +8 0xbc1), maps it through 0x60eac8a3 / 0x60eac851, loads font (type 0), strings (type 2) and type 1 via facade +0x34; strings "MODE_LANGUAGE", "loadLanguageData", "pFontsList"', SRC)
E(0x60eac851, 'lang_to_string_res', 'func', u, 'V', 'd0 language value -> (a3) u16 resource', 'Table 0x611f0c5c {u32 lang, u16 res}, -0x10000 end: 5 -> 2 (Simplified Chinese), 6 -> 3 (Traditional), 1 -> 8 (English)', SRC)
E(0x60eac8a3, 'lang_to_font_res', 'func', u, 'V', 'd0 language value, d1 1 -> u16 resource', 'Table 0x611f0d7c {u32 lang, u16 1, u16 res}: font = string res + 34 (5 -> 36, 6 -> 37)', SRC)
E(0x611f0c5c, 'lang_string_res_tab', 'table', u, 'V', '34 x {u32 lang, u16 res, u16 pad}', 'Language value (sid 3009) -> OSD string resource 1..34', SRC)
E(0x611f0d7c, 'lang_font_res_tab', 'table', u, 'V', '34 x {u32 lang, u16 1, u16 res}', 'Language value -> OSD font resource 35..68', SRC)
E(0x62509d7c, 'sid3009_language', 'data', 'settings', 'V', 'u8, MODE bank (key 0x85e1)', 'Menu language value; 5 = Simplified Chinese, 6 = Traditional Chinese, 1 = English', SRC)
E(0xa400bac0, 'zh_font_cmap', 'data', u, 'I', 'u32[256] page dir -> {u16 w, u16 h, u32 glyph}[256]', 'Font res 36 +0x54580: 636 CJK glyphs (37 px). Second dir +0x54980: 133 Latin / full-width (40 px). tools/zh_glyphs.py. Runtime address via the inferred font base 0xa3fb7540; the structure is verified in flash', SRC)
