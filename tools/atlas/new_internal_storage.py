# New atlas entries from docs/INTERNAL_STORAGE.md (looks in the camera's settings memory: research and design). E-P7 1.1.
# Same structure as atlas_data.py: E(addr, name, kind, subsystem, conf, sig, notes, source). Merged by gen.py.
# DANGER entries write or erase the camera's flash. Never hook, call or patch them.
# Not repeated: prm_flash_op 0x6005bc79, prm_bank_save 0x6005c5be, prm_bank_load 0x6005c524, prm_bank_check 0x6005c78a,
# prm_bank_cksum 0x6005c7f3, prm_bank_gen_inc 0x6005c811, prm_bank_fill_defaults 0x6005e309, prm_clear 0x6005dfc3,
# prm_ctl 0x6005f099, prm_load_all 0x6005f341, prm_banks_init 0x6005daeb, settings_save 0x602cc6dd, prop_set 0x6005ea22,
# flash_write 0x600c4f35, mode_bank_rom 0x60096f90, mode_bank_ram 0x624ea400, prm_banks 0xa26ff940, reset_pick 0x602b0560,
# reset_to_default_cache 0x602b9778, boot_tail_resets 0x60192961, fw_report_ok 0x601e7094, to_cached / to_uncached,
# cpu_lock / cpu_unlock / cache_flush.
s = 'settings'
SRC = 'docs/INTERNAL_STORAGE.md'

# ---- settings store: what the tail design depends on ----
E(0x6005c4b2, 'prm_bank_next_copy', 'func', s, 'V', 'a0 bank -> d0 copy', 'Copy index for the next save. With the one shadow each bank has it stays 0; the two flash slots are below this layer (fmem_mode_write_alt)', SRC + ' §2.4')
E(0x6005c854, 'prm_copy_words', 'func', s, 'V', 'd0 words, a0 src, a1 dst', 'Word copy of prm_bank_load (whole image, size / 4) and the CPRAM refill', SRC + ' §2.6')
E(0x6005eadf, 'prop_store_both', 'func', s, 'V', 'd0 key, d1 index, a0 storage (cached), a1 value', 'The store behind prop_set on CPU0: writes the value at the cached address, then at its uncached alias (width from the key). Other CPUs reach it through 0x6005e6e9', SRC + ' §2.5')
E(0x6005f089, 'prm_mode_load_failed_take', 'func', s, 'V', '-> d0 flag; clears it', 'Reads and clears mode_load_failed. 0x6005f079 the same for EEROM (0xa2715cb6), 0x6005f069 for BKRAM (0xa2715cb4)', SRC + ' §2.6')
E(0xa2715cb8, 'mode_load_failed', 'data', s, 'V', 'u16', 'Set to 1 by prm_load_all when the MODE image was refused and the bank was rebuilt from ROM', SRC + ' §2.6')
E(0xa2715ab8, 'mode_bank_end_cursor', 'data', s, 'V', 'u32', 'First free address after the packed MODE records, stored by prm_bank_fill_defaults (0x6250f9b0). 0xa2715abc EEROM, 0xa2715ac0 BKRAM. Read only by the debug shell `size`; a normal load does not write it', SRC + ' §2.8')
E(0x6005e57b, 'prm_dbg_mode_used', 'func', s, 'V', '-> d0 used bytes', 'Debug shell `size` only. DANGER: it rebuilds the MODE defaults in RAM to measure them. 0x6005e551 EEROM, 0x6005e5ab BKRAM', SRC + ' §2.8')
E(0x624ea404, 'mode_bank_gen', 'data', s, 'V', 'u32', 'Generation of the MODE image in RAM (image +4). prm_bank_save adds 1 before the checksum; equal to the shadow\'s (0xa2a78004) except while a save is in flight', SRC + ' §3.4')
E(0x6250f9b0, 'mode_bank_tail', 'data', s, 'V', 'image offset 0x255b0; free to 0x6252a3fc (109,132 B)', 'First byte after the last MODE record (key 0xfa64). No record, no absolute reference and no decompiled function names anything from here to the end of the image; loaded, summed, compared and saved with the image (emulated). Run-time use through computed pointers not excluded [I]', SRC + ' §2.2, §2.8')
E(0x62524400, 'mode_tail_block_cand', 'data', s, 'I', 'image offset 0x3A000, 4 KB reserve; uncached 0xa2524400', 'Ours, proposed, nothing built: the block that would hold BUNDLES / LOOKS / MOVIE / AP images (EP7I, 3,080 B). Not camera-proven', SRC + ' §3.1')
E(0xa2a78000, 'mode_bank_shadow', 'data', s, 'V', '0x40000 B; cached alias 0x62a78000', 'RAM mirror of the saved MODE image: filled at boot from the newer valid flash slot (fmem_param_mount), read back after every save. prm_bank_save compares the RAM image with it', SRC + ' §2.4')
E(0x602b039a, 'settings_boot_init', 'func', s, 'V', '', 'From boot_tail_resets (0x6019296e). If the MODE image was refused (settings_mode_load_failed): settings_factory_init, then settings_save at once', SRC + ' §2.6')
E(0x602b962f, 'settings_factory_init', 'func', s, 'V', '', 'Every sid 0..1768, 10000.., 15000.. := its sid default (property, raw plane, both active parts), then snapshot_store for slots 0..8. Sid-level: never touches bytes outside the records. Callers: boot (refused image), factory-setting reset, self-adjust, ADJ task', SRC + ' §2.6')
E(0x602cc7ec, 'settings_mode_load_failed', 'func', s, 'V', '-> d0', 'Wrapper (id 0xf0020) of prm_mode_load_failed_take', SRC + ' §2.6')
E(0x602cb832, 'settings_cmd_dispatch', 'func', s, 'V', 'd0 command id 0x60001..0x60020, a0 args', 'Jump table 0x604d6b40: sid get / set / reset, settings_save, settings_save_bkram, settings_mode_load_failed. Reached from the script reader 0x60ba7eec through 0x602cb779, not from the menus', SRC + ' §2.5')
E(0x602b3a60, 'settings_reset_list_626', 'func', s, 'V', 'd0, d1', 'List reset over 626 sids (0x604ab744) through reset_to_default_cache. Which menu Reset this is [I]', SRC + ' §2.6')
E(0x602b3a8c, 'settings_reset_list_1785', 'func', s, 'V', 'd0, d1', 'List reset over 1,785 sids (0x604aa952); with sid 41 set it first reloads snapshot 0. Which menu Reset this is [I]', SRC + ' §2.6')
E(0x607ac5eb, 'factory_setting_reset', 'func', s, 'V', '', 'OlyHfwResetFactorySetting.cpp: keeps sid 23, settings_factory_init, settings_save, EEROM save 0x602d2f75. Service path', SRC + ' §2.5')
E(0x604057e3, 'fatal_save_hang', 'func', s, 'V', '', 'Error code 15235, prm_ctl save {mode}, cpu_lock, endless loop. From the 120 s wait 0x60404fba', SRC + ' §2.5')
E(0x60022f89, 'memcmp', 'func', 'rtos', 'V', 'd0 length, a0, a1 -> d0 (0 = equal); retf [d2,d3],8', 'Byte compare; prm_bank_save calls it with size - 12 from image + 8', SRC + ' §2.5')

# ---- flash layer under the banks: two slots per bank ----
E(0x6005b6cc, 'fmem_param_mount', 'func', 'boot', 'V', 'called from 0x600521b9', 'Boot: reads the first 512 B of both MODE slots, compares the generations (wrap-aware); the slot one ahead is read in full and its 16-bit sum checked (fmem_sum_check); a wrong sum loads the other slot; neither ahead: both erased. Sets fmem_mode_slot. Then the same for EEROM', SRC + ' §2.4')
E(0x6005b634, 'fmem_param_class', 'func', 'boot', 'V', 'a0 address -> d0', '1 = EEROM (shadow 0xa2ab8000, flash 0x402c0000 / 0x402e0000), 2 = MODE (shadow 0xa2a78000, flash 0x40240000 / 0x40280000), 0 = other. flash_write picks the slot writer by it', SRC + ' §2.4')
E(0x6005bc0f, 'fmem_sum_check', 'func', 'boot', 'V', 'd0 size, a0 image -> d0 0 = sum is 0', 'Cache flush, then the 16-bit sum of size / 2 halfwords', SRC + ' §2.4')
E(0x600216fd, 'fmem_mode_write_alt', 'func', 'boot', 'V', 'd0 size, a1 source', 'DANGER: flash write. Flips fmem_mode_slot, erases and programs that slot (flash_erase_program), reads it back into the shadow (flash_read_pages)', SRC + ' §2.4')
E(0x6002166f, 'fmem_eerom_write_alt', 'func', 'boot', 'V', 'd0 size, a1 source', 'DANGER: flash write. The same for the EEROM slots (slot byte 0x61b213a0)', SRC + ' §2.4')
E(0x60021621, 'flash_erase_program', 'func', 'boot', 'V', 'd0 size, a0 flash, a1 source', 'DANGER: erase 0x600218a9, then program 0x6002173b', SRC + ' §2.4')
E(0x6002144e, 'flash_read_pages', 'func', 'boot', 'V', 'd0 size, a0 flash, a1 RAM', 'Page reads (0x800) from logical flash into RAM. Read only. Also the boot loads at 0x600201fe', SRC + ' §2.4')
E(0x61b21368, 'fmem_mode_slots', 'data', 'boot', 'V', '2 x 28 B {u32 size 0x40000, u32 shadow 0xa2a78000, u32 flash, ..}', 'Slot 0 flash 0x40240000, slot 1 0x40280000. EEROM table 0x61b21340 (0x402c0000, 0x402e0000). Filled from ROM 0x6002e3a8 by the data copy at 0x60020117 (0x6002e020..0x6002e8e8 -> 0x61b20fe0)', SRC + ' §2.4')
E(0x61b213a1, 'fmem_mode_slot', 'data', 'boot', 'V', 'u8 0 / 1', 'Slot the MODE shadow was loaded from; flipped before each save, so saves alternate. EEROM: 0x61b213a0', SRC + ' §2.4')
E(0x601e729e, 'fw_power_off_reboot', 'func', 'updater', 'V', '', '"Power OFF" / "Power Reboot" after an update: prm_ctl save {mode} from RAM, then the power request. From fw_report_ok and the fail report 0x601e71b6, and 0x602ca7ac', SRC + ' §2.7')
