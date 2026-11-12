# New atlas entries from docs/RE_SETTINGS.md (settings store: sid ranges, property registry, banks, persistence).
# Same structure as atlas_data.py: E(addr, name, kind, subsystem, conf, sig, notes, source).
# Merge by exec'ing after atlas_data.py (E and S come from there).
# DANGER entries write the camera's flash (settings, factory data) or erase it. Never hook, call or patch them
# without a camera-tested plan: a bad write there is a settings loss at best, a factory-data loss at worst.
# Not repeated (already in the atlas or new_ae.py): prop_lookup 0x6005d924, prop_handle 0x6005e947, prop_get 0x6005e971,
# prop_set 0x6005ea22, prop_read_width 0x6005efbd, prop_init_table 0x600973dc, wdt_flashop 0x6005bcb5 (inside
# prm_flash_op), flash_write 0x600c4f35, sid_get 0x602cbc0a, sid_active_get 0x602cc0a7, sid_read_raw 0x602cc0fc,
# sid_set_raw 0x602cc122, reset_to_default 0x602b972b, val_default 0x602b9bad, validator_hash_init 0x602ba4cc,
# sid_key_table 0x604d6c14, validator_table 0x604cc98c, set_desc_registry 0x604317ac, reset_gate 0x62257b04.
s = 'settings'
p = 'settings'  # persistence entries render in ATLAS §3; flash writers carry DANGER in notes
SRC = 'docs/RE_SETTINGS.md'

# ---- sid ranges and sid-level helpers ----
E(0x602cbd3b, 'sid_to_key', 'func', s, 'V', 'd0 sid, a0 &handle -> d0 key (0 = none)', 'Ranges 0-1768 (0x604d6c14), 3000-3021, 4000-4022, 4500-4521, 10000-10110, 15000-15273; caches prop_handle per sid in RAM (0xa2699cb4.. for 0-1768). Sid 6000 is a RAM word, not a property', SRC + ' §1')
E(0x602cbf8b, 'sid_to_index', 'func', s, 'V', 'd0 sid -> d0 index', '4000/4500 ranges have no index (0)', SRC + ' §1')
E(0x602cbc13, 'sid_get_core', 'func', s, 'V', 'd0 sid -> d0', 'sid_to_key + sid_to_index + prop_get. Body of sid_get', SRC + ' §1')
E(0x602cbc5d, 'sid_set', 'func', s, 'V', 'd0 sid, d1 value', 'Skipped while reset_gate == 1; else sid_set_core 0x602cbc74 (prop_set). 86 callers', SRC + ' §1')
E(0x602cbcbf, 'sid_prop_reset', 'func', s, 'V', 'd0 sid', 'Property back to its ROM default (prop_set_default)', SRC + ' §3')
E(0x602cbcfd, 'sid_prop_default', 'func', s, 'V', 'd0 sid -> d0', 'ROM default of the sid property (prop_get_default)', SRC + ' §3')
E(0x604d87b8, 'sid_key_3000', 'table', s, 'V', '22 x {u16 key, u16 index}', 'Sids 3000-3021. Followed by 0x604d8810 (4500-4521, u16 key), 0x604d883c (4000-4022, u16 key), 0x604d886a (10000-10110, {key, index}), 0x604d8a26 (15000-15273, {key, index})', SRC + ' §1')
E(0x604a8774, 'sid_default_table', 'table', s, 'V', 's32 x 1769 (sid 0-1768)', 'Read by val_default; then 0x604aa318 (10000-10110), 0x604aa4d4 (15000-15273). Other ranges default 0', SRC + ' §1')
E(0x604ad20c, 'sid_default_region', 'table', s, 'V', '12 B {u16 region, u16 n, u32 sids, u32 values}, 0-terminated', 'val_default override keyed by sid 4508. One row: region 1 -> sid 3010 = 0, 3009 = 1', SRC + ' §1')
E(0x602ba523, 'validator_lookup', 'func', s, 'V', 'd0 sid -> a0 record (0 = none)', 'Hash bucket sid & 127 (0x62248528); first record for the sid. 0x602ba54d also matches attr', SRC + ' §1')
E(0x602ba146, 'val_step_core', 'func', s, 'V', 'd0 type, ...', 'Next/previous value by validator type: 1 u8, 2 s8, 3 s16 nearest, 4 s16, 5 u16, 6 blob (elem bytes)', SRC + ' §1')
E(0x602b174c, 'desc_lookup', 'func', s, 'V', 'd0 sid -> a0 descriptor', 'Hash sid & 63 at 0x62247d48 (built by 0x602b16f7 over the 439 records)', SRC + ' §1')
E(0x60ef98a4, 'opc_prop_table', 'table', s, 'V', '24 B {char* name, u32 sid, get, set, list, 0}', 'Wi-Fi remote property names: takemode, drivemode 3281, focalvalue 3, expcomp 2, shutspeedvalue 4, isospeedvalue 6, wbvalue 9, artfilter 280, colorphase 665 ...', SRC + ' §2')

# ---- property registry and banks ----
E(0x6005d6aa, 'prm_registry_build', 'func', p, 'V', '', 'Clears 4096-slot registry 0xa26ffa88 ({u16 key, u16 count, u32 data}), registers CONST, FLASH, BKRAM, EEROM, MODE, CPRAM records, the DEVICE key list, then FLASHD1/D2 if present', SRC + ' §3')
E(0x6005d987, 'prm_reg_add_records', 'func', p, 'V', 'd0 registry, a0 records, a1 storage (0 = inline)', 'Records {u16 key, u16 count, data, pad 4}. Storage inline, or packed into a1 (aligned to width = key & 3, 0 -> 4). Duplicate key -> error 0x1c005001', SRC + ' §3')
E(0x6005da25, 'prm_reg_add_keylist', 'func', p, 'V', 'd0 registry, a0 {u16 key, u16 count} list, a1 storage', 'Used for FLASHD1/D2', SRC + ' §3')
E(0x6005daeb, 'prm_banks_init', 'func', p, 'V', '', 'Not a Ghidra function. Sets the bank objects (id, shadow, ROM default, RAM, size), clears headers, refills CPRAM, then prm_ctl load {0,1,1,1,1}. FLASHD1/D2 init at 0x6005dd7d / 0x6005de81', SRC + ' §3')
E(0x6005c2f1, 'prm_bank_new', 'func', p, 'V', '-> a0 bank', '7 bank objects at 0xa26ff940, 28 B: +0 id, +2 current copy, +4/+8 shadow copies, +12 ROM default, +16 RAM, +20 size, +24 in use', SRC + ' §3')
E(0x6005c3bb, 'prm_bank_pick_copy', 'func', p, 'V', 'a0 bank -> d0 copy (0/1, 0xfe none valid)', 'Checks each shadow copy (prm_bank_check); with two valid copies picks the newer generation (+4, wraps)', SRC + ' §4')
E(0x6005c524, 'prm_bank_load', 'func', p, 'V', 'a0 bank -> d0 1 = failed', 'Valid shadow copy -> RAM (size/4 words)', SRC + ' §4')
E(0x6005c78a, 'prm_bank_check', 'func', p, 'V', 'd0 size, d1 id, a0 image -> d0 0 = ok', 'Valid when image+0 == bank id and the u16 sum of size/2 halfwords is 0', SRC + ' §4')
E(0x6005c7f3, 'prm_bank_cksum', 'func', p, 'V', 'd0 size, a0 image -> d0', 'Negated u16 sum of the image after the checksum word; stored at +2 by 0x6005c7e7', SRC + ' §4')
E(0x6005c811, 'prm_bank_gen_inc', 'func', p, 'V', 'a0 image', 'Generation counter at image+4 += 1', SRC + ' §4')
E(0x6005c5be, 'prm_bank_save', 'func', p, 'V', 'a0 bank -> d0 status', 'DANGER: flash write. memcmp RAM vs shadow; if different: next copy, gen++, checksum, cache flush, prm_flash_op(size, 0, RAM, shadow). Used for FLASH, EEROM, MODE', SRC + ' §4')
E(0x6005c64c, 'prm_fd1_save', 'func', p, 'V', 'a0 bank', 'DANGER: writes FLASHD1 (0x60000 B) to flash 0x40080000. Factory data. Runs whenever prm_ctl save has the flash flag', SRC + ' §4')
E(0x6005c69b, 'prm_fd2_save', 'func', p, 'V', 'a0 bank', 'DANGER: writes FLASHD2 (0x160000 B) to flash 0x400e0000. Factory data', SRC + ' §4')
E(0x6005c6ea, 'prm_bank_erase', 'func', p, 'V', 'a0 bank', 'DANGER: flash erase (prm_flash_op mode 0x200) of both shadow copies', SRC + ' §4')
E(0x6005c583, 'prm_bkram_save', 'func', p, 'V', 'a0 bank', 'Gen++, checksum, RAM -> backup registers 0x98e00008 (14 words, 0x60066e14). Not flash', SRC + ' §4')
E(0x6005c559, 'prm_bkram_load', 'func', p, 'V', 'a0 bank -> d0 1 = failed', 'Backup registers -> 0xa26ffa04, check, -> RAM', SRC + ' §4')
E(0x6005bc79, 'prm_flash_op', 'func', p, 'V', 'd0 size, d1 mode (0 write, 0x10, 0x100 read, 0x200 erase), a0 src, a1 dst', 'DANGER: the only flash entry of the settings store. Sem 0x60040af0, WDT off around write/erase (wdt_flashop 0x6005bcb5 is inside), -> flash_write / 0x600c4e80 / fmem_erase', SRC + ' §4')
E(0x600c508d, 'fmem_shadow_to_flash', 'func', p, 'V', 'a0 addr -> a0 flash addr', 'Maps a bank shadow to its flash address via table 0x60078620: 0xa2ab8000 -> 0x802c0000 (EEROM), 0xa2a78000 -> 0x80240000 (MODE), 0xa2898000 -> 0x80060000 (FLASH)', SRC + ' §4')
E(0x600c4edc, 'fmem_erase', 'func', p, 'V', 'd0 size, a0 addr', 'DANGER: flash erase via 0x600218a9', SRC + ' §4')
E(0x600c4e80, 'fmem_read', 'func', p, 'V', 'd0 size, d1 mode 0x100-0x102, a0 dst, a1 flash src', 'Read only', SRC + ' §4')
E(0x6005f099, 'prm_ctl', 'func', p, 'V', 'a0 -> {u16 op, u16 bkram, u16 flash, u16 eerom, u16 mode}', 'DANGER for op 1/3. op 0 load (prm_load_all), 1 save (flash flag also writes FLASHD1/D2), 2 card CSV overlay, 3 erase. 21 call sites', SRC + ' §4')
E(0x6005f341, 'prm_load_all', 'func', p, 'V', 'a0 cmd', 'FLASH (merge), BKRAM, EEROM, MODE; a failed check logs, sets 0xa2715cb4/6/8 and restores that bank from ROM (prm_clear), then prm_registry_build', SRC + ' §4')
E(0x6005dfc3, 'prm_clear', 'func', p, 'V', 'd0 device (1 CSV, 2 CPRAM, 3 BKRAM, 4 FLASH, 6 EEROM, 7 MODE, 10/11 FLASHD1/D2)', 'RAM only: device back to ROM defaults, then prm_registry_build. Not persisted until a save', SRC + ' §5')
E(0x6005e129, 'prm_flash_bank_merge', 'func', p, 'V', 'a0 stored image (0 = none)', 'Rebuilds FLASH bank RAM: stored records whose key and count match the ROM list first, then ROM defaults for the rest', SRC + ' §4')
E(0x6005e309, 'prm_bank_fill_defaults', 'func', p, 'V', 'd0 size, a0 RAM, a1 ROM records', 'Packed defaults for BKRAM/EEROM/MODE', SRC + ' §5')
E(0x6005e852, 'prm_device_of', 'func', p, 'V', 'd0 key -> d0 device id', 'By storage address: 1 CSV, 2 CPRAM, 3 BKRAM, 4 FLASH, 6 EEROM, 7 MODE, 10/11 FLASHD1/D2, 9 DEVICE, 5 ROM', SRC + ' §3')
E(0x6005eeab, 'prop_get_default', 'func', p, 'V', 'd0 key, d1 index -> d0', 'ROM default via 0x6005f005 (record lookup in the owning bank ROM image)', SRC + ' §5')
E(0x6005ef24, 'prop_set_default', 'func', p, 'V', 'd0 key', 'Copies the ROM default over the property (core 0; wrapper 0x6005eefb forwards from core 1)', SRC + ' §5')
E(0x6005c8e2, 'prm_csv_load', 'func', p, 'V', 'a0 cmd {.., +20 drive, +24 dir, +28 name}', 'Reads a card file into 0x62496400 (max 0x1fffc B), then prm_csv_overlay_build', SRC + ' §6')
E(0x6005d8e3, 'prm_csv_overlay_build', 'func', p, 'V', '', 'Builds overlay registry 0xa2707a88 from 0x62496400 and sets 0xa26ffa84 = 1; prop_lookup then prefers the overlay', SRC + ' §6')
E(0x6061907a, 'card_param_csv_load', 'func', p, 'V', '', 'On card mount (dcfnum.c, 0x60618b53): finds PARAMDT/CP??????.CSV, then prm_clear(1) + prm_ctl op 2', SRC + ' §6')

# ---- settings-side save / snapshot / reset ----
E(0x602cc6dd, 'settings_save', 'func', p, 'V', '', 'DANGER: prm_ctl save {bkram 0, flash 0, eerom 1, mode 1}. Callers: OlyHfwPower::startShutDown, sleep, firmware-update check, life tests', SRC + ' §4')
E(0x602cc767, 'settings_save_bkram', 'func', p, 'V', '', 'prm_ctl save {bkram 1}. Backup registers only', SRC + ' §4')
E(0x602ccc3c, 'flash_prop_save', 'func', p, 'V', 'd0 key, d1 value -> d0 1 = failed', 'DANGER: sets one FLASH-bank key (0x0db1, 0xbac1, 0xbbc1) and saves with the flash flag, which also rewrites FLASHD1/D2. Caller 0x60827377', SRC + ' §4')
E(0x602cbffe, 'snapshot_load', 'func', s, 'I', 'd0 slot', 'Copies key 0x85d4[slot*3538 + i] -> active key 0x8b64[i], i < 3538 (2 parts x 1769 sids). Slot meaning (Myset n) [I]', SRC + ' §5')
E(0x602cc03a, 'snapshot_store', 'func', s, 'I', 'd0 slot', 'Active 0x8b64 -> 0x85d4 slot. 0x85d4 has 32040 words = 9 slots, all in the MODE bank', SRC + ' §5')
E(0x602cc076, 'snapshot_get', 'func', s, 'V', 'd0 sid, d1 slot, a0 part -> d0', '0x85d4[sid + part*1769 + slot*3538]', SRC + ' §5')
E(0x602cc0d0, 'sid_active_set', 'func', s, 'V', 'd0 sid, d1 part, a0 value', 'Writes 0x8b64[sid + part*1769]; pair of sid_active_get', SRC + ' §5')
E(0x602cc631, 'sid_cache_all', 'func', s, 'V', '', 'Reads every sid of the 0, 3000, 4000, 4500, 15000 ranges into RAM 0x6225359c..', SRC + ' §5')
E(0x602b9778, 'reset_to_default_cache', 'func', s, 'V', 'd0 count, a0 u16 id list', 'Like reset_to_default but writes the RAM sid caches (0x602cc1f2/0x602cc345) instead of the properties', SRC + ' §5')
E(0x602b0560, 'reset_pick', 'func', s, 'V', '', 'sid 10049 == 0 -> reset list 0x6049b31c (27); else list 0x6049c144 (626) and snapshot_store(0)', SRC + ' §5')

# ---- ROM images and RAM ----
E(0x60078e2c, 'prop_const_records', 'table', p, 'V', 'records {u16 key, u16 count, data}', 'CONST: 449 read-only keys, storage inline in ROM', SRC + ' §3')
E(0x6008e9d0, 'cpram_rom', 'table', p, 'V', 'records, 0x932 words', 'CPRAM image, 522 keys, copied to RAM 0x624b6400 every boot (0x6005e111)', SRC + ' §3')
E(0x60090e98, 'flash_bank_rom', 'table', p, 'V', '{u16 id 18, u16 cksum, u32 gen}, records', 'FLASH bank defaults, 113 keys; RAM 0x624ba400 (inline), shadow 0xa2898000, flash 0x40060000, 0x20000 B', SRC + ' §3')
E(0x60078db0, 'bkram_rom', 'table', p, 'V', '{id 10, cksum, gen}, records', 'BKRAM defaults, 14 keys; RAM 0x6252a400 (packed, 56 B), backup registers 0x98e00008', SRC + ' §3')
E(0x600921d4, 'eerom_rom', 'table', p, 'V', '{id 67, cksum, gen}, records', 'EEROM defaults, 125 keys; RAM 0x624da400 (packed), shadow 0xa2ab8000, flash 0x402c0000, 0x10000 B', SRC + ' §3')
E(0x60096f90, 'mode_bank_rom', 'table', p, 'V', '{id 7, cksum, gen}, records (to 0x600be008)', 'MODE defaults, 1084 keys incl. snapshots 0x85d4/0x8b64/0x8b54; RAM 0x624ea400 (packed), shadow 0xa2a78000, flash 0x40240000, 0x40000 B. prop_init_table 0x600973dc lies inside', SRC + ' §3')
E(0x60096f04, 'device_keylist', 'table', p, 'V', '{id 0, cksum, gen}, {u16 key, u16 count}', '32 DEVICE keys, registered with count 0 (no storage)', SRC + ' §3')
E(0x600be00c, 'fd1_keylist', 'table', p, 'V', '{id 2, ..}, {u16 key, u16 count}', 'FLASHD1: 5 keys (0x7044 9200 words ...); RAM 0x628b8000, flash 0x40080000', SRC + ' §3')
E(0x600be02c, 'fd2_keylist', 'table', p, 'V', '{id 1, ..}, {u16 key, u16 count}', 'FLASHD2: 12 keys (0x7144 52000 words ...); RAM 0x62918000, flash 0x400e0000', SRC + ' §3')
E(0x60078620, 'fmem_xchg_table', 'table', p, 'V', '3 x {u32 uncached shadow, u32 cached shadow, u32 flash}', 'Read by fmem_shadow_to_flash', SRC + ' §4')
E(0xa26ff940, 'prm_banks', 'data', p, 'V', '7 x 28 B bank objects', 'Pointers: 0xa2711a88 CONST records, 0xa2711a8c CPRAM ROM, 0xa2711a90 FLASH, 0xa2711a94 BKRAM, 0xa2711a98 EEROM, 0xa2711a9c MODE, 0xa2711aa0 DEVICE, 0xa2711aa4 FLASHD1, 0xa2711aa8 FLASHD2', SRC + ' §3')
E(0xa2707a88, 'prop_overlay_registry', 'table', p, 'V', '4096 x 8 B', 'CSV overlay; active when 0xa26ffa84 != 0 (prop_lookup checks it first)', SRC + ' §6')
E(0x624ea400, 'mode_bank_ram', 'data', p, 'V', '0x40000 B: {u16 id, u16 cksum, u32 gen}, packed values', 'User settings working copy. Storage of each key: docs/settings_catalogue.json', SRC + ' §3')
E(0x98e00008, 'bk_regs', 'data', p, 'V', 'u32 x 14', 'Battery-backed registers for the BKRAM bank (0x60066e14 write, 0x60066e29 read)', SRC + ' §4')

# ---- unlock leads (§6, §7) ----
E(0x60618b53, 'card_mount_dcf_init', 'func', 'fileio', 'V', '', 'Card mount sequence (dcfnum.c); last step card_param_csv_load 0x6061907a', SRC + ' §6')
E(0x6069166d, 'fcs_limit_calc_fl', 'func', 'lens_ae', 'V', '', 'AF Limiter: reads keys 0x5391 (sid 1149 on/off), 0x53a1 (1150 preset), 0x53b2/0x53c2 (near/far x3), 0x5651 (1274)', SRC + ' §7')
E(0x60691b0e, 'fcs_limit_drive_exec', 'func', 'lens_ae', 'V', '', 'AF Limiter drive; reads 0x5642 (sid 1273), 0x5651 (1274); log "focus_limit.ldp_far"', SRC + ' §7')
