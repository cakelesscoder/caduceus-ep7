# New atlas entries from docs/PLUGINS.md (SD plugin layer v1, v0.32; patches/plugin_loader).
# Same structure as atlas_data.py: E(addr, name, kind, subsystem, conf, sig, notes, source).
# Merge by exec'ing after atlas_data.py (E and S come from there).
# Our code (v0.32 image only; addresses move if the layer is rebuilt). Stock services it calls are already in the atlas:
# malloc 0x60022782, free 0x600227b4, fopen 0x60634fbc, fread 0x6063514b, text setter 0x60d4c9df, prop_get 0x6005e971.
p = 'plugins'
SRC = 'docs/PLUGINS.md'

# ---- loader (half-press chain, once per power-on) ----
E(0x601df730, 'pl_ap_site', 'hook', p, 'V', '`call d16,[d2,d3,a2,a3],24` (5 B)', "ap_post's only call to ap_load 0x601df7cd, retargeted to pl_ap. Reached once per power-on behind P+992 'EP7U'", SRC + ' §1')
E(0x601e1c68, 'pl_ap', 'func', p, 'V', 'frame of ap_post\'s ap_load call; a2 = real P', 'ap_load, then malloc 16384 -> B, fopen C:\\EP7MOD\\PLUGIN.BIN "r", fseek END / ftell (34..16384), fseek SET, fread == size, fclose -> pl_chk; any miss frees B', SRC + ' §1')
E(0x601e1a8c, 'pl_chk', 'func', p, 'V', 'a2 P, a3 B, d2 size; tail of pl_ap\'s frame', "Header: 'EP7P', u16 ABI 1 + u16 flags 0, firmware id 5dd9af16, size == file size, CRC-32 of 8..size-1 (fm_crc); then init(a0 pl_api, d0 B) at B - 0x40000000 + 32. d0 0 -> P+856 = B, P+852 = 'EP7K'. B never freed after init", SRC + ' §1, §2')
E(0x601e1d00, 'pl_api', 'table', p, 'V', 'u16 ABI 1, u16 n 3, then n words', '+4 wide version string (fw_val\'s L"0.32"), +8 prop_get 0x6005e971, +12 text setter 0x60d4c9df. Read-only', SRC + ' §3')
E(0x601e1d10, 'pl_path', 'data', p, 'V', 'ASCII', 'C:\\EP7MOD\\PLUGIN.BIN', SRC + ' §1')

# ---- Firmware screen hook ----
E(0x601e1af7, 'pl_fw', 'func', p, 'V', 'frame of `call fw_val,[d2,d3,a2,a3],88`; a0 widget, a1 value', "Non-empty value, ap_P real P with P+852 'EP7K' and hook word B+28 != 0 -> setter(widget, B+28 string); else jmp fw_val with registers as found. Sites 0x60d7f271 / 0x60d7f2cd", SRC + ' §3')
E(0x601e1c40, 'fw_val', 'func', p, 'V', 'same frame (88)', 'fw_version: non-empty Body value -> L"0.32" (string 0x601e1c5a, ends 0x601e1c64); empty passes through', 'docs/CODE_SPACE_MAP.md')

# Heap P+852 ('EP7K' ready) / P+856 (block B) are offsets in the handle-based P, not fixed addresses: docs/CODE_SPACE_MAP.md.
