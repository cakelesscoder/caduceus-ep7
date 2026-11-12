# Settings store: catalogue, banks, persistence (E-P7 1.1)

Static analysis only: `tools/dis.sh`, byte reads of the decoded main, the private decompiler corpus, the English OSD
string table. No build, emulator run or camera test. Tags: **[V]** read from bytes or disassembly, **[I]** inference.
Private material (decompiler output, bank-setup listing, generator scripts): `~/ep7fw-private/decomp/settings/`.
Catalogue: [settings_catalogue.json](settings_catalogue.json). New symbols: `tools/atlas/new_settings.py`.

## 0. Short answers

1. **Catalogue.** 2221 sids in six ranges, 2216 with a property key. Every key resolves to exactly one registry slot
   (no duplicates) [V]. 1282 sids have validator records, 414 an on-change callback [V]. **481 are named (21.7 %)**:
   333 from menu records, 5 from the Wi-Fi remote name table, 95 from repo docs, 48 copied within a key group [V
   names; confidence per entry].
2. **Persistence.** Properties live in nine registered banks. 2160 of the sids sit in one flash bank, **MODE (id 7,
   flash 0x40240000, 256 KB)**, which also holds the Myset/snapshot arrays [V]. Banks are written only by `prm_ctl`
   (`0x6005f099`) save, called at **power-off, sleep and a few system events, never per setting change** [V callers].
   Each flash bank image is `{u16 id, u16 checksum, u32 generation, values}` with a zero halfword sum. A bad image
   loads ROM defaults for that bank instead of bricking [V code].
3. **Leads.** The strongest: a stock **card-file property overlay** (`PARAMDT/CP??????.CSV`, loaded on card mount, RAM
   only), the **AF Limiter** feature with its full settings and menu records, and about 216 persisted key groups with
   validators but no menu (§7).

## 1. Sid space [V]

| Range | Key table | Entry | Notes |
|---|---|---|---|
| 0–1768 | `0x604d6c14` | `{u16 key, u16 index}` | handle cache per sid at `0xa2699cb4` |
| 3000–3021 | `0x604d87b8` | `{u16 key, u16 index}` | |
| 4500–4521 | `0x604d8810` | `u16 key` | index 0 |
| 4000–4022 | `0x604d883c` | `u16 key` | index 0 |
| 10000–10110 | `0x604d886a` | `{u16 key, u16 index}` | |
| 15000–15273 | `0x604d8a26` | `{u16 key, u16 index}` | |
| 6000 | – | RAM halfword | not a property (`sid_get_core 0x602cbc13`) |

- Mapping: `sid_to_key 0x602cbd3b`, `sid_to_index 0x602cbf8b` [V]. Other ids (3281 drive, 3431, 3568…) appear only in
  validator/rule tables, not in the sid space [V].
- **Key** = `id<<4 | type`. Width = `type & 3`, with 0 meaning 4 bytes (`0x6005c743`). Bit 3 = signed [V].
- **Validators** `0x604cc98c` (1333 × 20 B). The `type` byte at +17 selects the walk in `val_step_core 0x602ba146`:
  1 u8 list, 2 s8 list, 3 s16 nearest-match list, 4 s16 list, 5 u16 list, 6 blob of `elem` bytes. Count = bytes/elem [V].
  Some sids have several records that differ in `attr` (looked up by `0x602ba54d`) [V].
- **Descriptors** `0x604317ac` (439 × 60 B): `u32 sid` + 14 function words. +24 is the on-change callback [V]. They are
  hashed by `sid & 63` at `0x62247d48` (`desc_lookup 0x602b174c`) [V]. A second run of 60-B records follows at
  `0x60437ecc`; it is not in that hash [V] and has no direct reference [V scan].
- **Two kinds of default** [V]:
  - `prop_default`: the initial value in the bank's ROM image. A bank reset restores it.
  - `sid_default`: from `val_default 0x602b9bad`, tables `0x604a8774` (0–1768), `0x604aa318` (10000+) and `0x604aa4d4`
    (15000+), overridden per region (sid 4508) by `0x604ad20c`. Settings-level resets write this one.
  - They differ. For example sid 1147 Lowest S/S has a prop default of 0 and a sid default of 2048 (1/250 s).

## 2. Names [V method, confidence per entry]

| Source | How | Count | Conf |
|---|---|---|---|
| `menu_item` | 36-B records `{u16 id, u16 n, u32, label name, label help, opts, u32, opts2}` (two copies, text bases `0x611799dc`, `0x6115d8b8`) | 81 | high |
| `menu_page` | main-menu pages `0x6117b1b4` (7 × 28 B), 12-B items `{u32 id, label}` | 24 | high |
| `menu_custom` | 36-B records `{u32 id, label, opts, n, 0, label2, opts2, n2}` (three copies at `0x611b…`, `0x611c…`, `0x611d…`); runs of ≥ 3 real sids | 228 | medium |
| `opc` | Wi-Fi remote table `0x60ef98a4` (24 B `{char* name, u32 sid, get, set, list}`) | 5 (+ alt) | medium |
| `docs` | repo docs (RE_AE, ATLAS §3, MIN_SHUTTER, BUTTONS, LIVE_ND, UNLOCK_LEADS …) | 95 | by doc tag |
| `key_group` | name of a sibling sid on the same key + index | 48 | low |

- Labels are kind-4 string ids into the English table (`generated/osd/strings_en.json`). `@A0xx@` icon tokens are stripped [V].
- Option lists (`[value, label]`) are attached for 289 sids. LC strips `0x61176e70`, editor child lists `0x61186ba4`,
  grey-out ids `0x60adf518` and rule-DB sids `0x6045e5fc` are recorded as `ui` evidence [V].
- **Limits.** The root menu is multi-model (LOOK_MENUS §1 row 9), so a named sid may still be hidden on the E-P7 [V].
  About 1740 sids have no name: internal state, per-mode copies and editor-only values [I]. Help texts were read but
  are not published.

## 3. Property registry and banks [V]

`prm_registry_build 0x6005d6aa` clears the 4096-slot registry `0xa26ffa88` (8 B `{u16 key, u16 count, u32 data}`,
slot = key>>4). It then registers each source with `prm_reg_add_records 0x6005d987`. Records are `{u16 key, u16 count,
data…}` padded to 4 bytes. Storage is either inline (the registry points into the record) or packed into a RAM area,
aligned to the width. `prm_device_of 0x6005e852` classifies a key by its storage address.

| Device (clear id) | Keys | ROM image | RAM | Persisted in | Size |
|---|---|---|---|---|---|
| CONST (5) | 449 | `0x60078e2c` | inline in ROM | – (read-only) | – |
| CPRAM (2) | 522 | `0x6008e9d0` | `0x624b6400`, inline | nowhere: ROM → RAM every boot (`0x6005e111`) | 0x932 words |
| FLASH (4), id 18 | 113 | `0x60090e98` | `0x624ba400`, inline | flash `0x40060000` (shadow `0xa2898000`) | 0x20000 |
| BKRAM (3), id 10 | 14 | `0x60078db0` | `0x6252a400`, packed | backup registers `0x98e00008` (14 words) | 56 |
| EEROM (6), id 67 | 125 | `0x600921d4` | `0x624da400`, packed | flash `0x402c0000` (shadow `0xa2ab8000`) | 0x10000 |
| **MODE (7), id 7** | **1084** | `0x60096f90` | `0x624ea400`, packed | **flash `0x40240000`** (shadow `0xa2a78000`) | 0x40000 |
| DEVICE (9) | 32 | `0x60096f04` (key list) | none (count 0) | – | – |
| FLASHD1 (10), id 2 | 5 | `0x600be00c` (key list) | `0x628b8000` | flash `0x40080000` | 0x60000 |
| FLASHD2 (11), id 1 | 12 | `0x600be02c` (key list) | `0x62918000` | flash `0x400e0000` | 0x160000 |
| CSV overlay (1) | file | card | `0x62496400` → registry `0xa2707a88` | – (RAM) | ≤ 0x1fffc |

- Bank objects: 7 × 28 B at `0xa26ff940`, set up by `prm_banks_init 0x6005daeb`. That code is not a Ghidra function
  [V]. Layout: `+0 id, +2 current copy, +4/+8 shadow copies (only copy 0 used), +12 ROM default, +16 RAM, +20 size`.
- Shadow → flash mapping: `fmem_shadow_to_flash 0x600c508d`, table `0x60078620` [V]. The flash device is the one the
  main image lives on: the container's main starts at `0x406a0020` [V manifest].
- Sid share: MODE 2160, CPRAM 44, EEROM 5, CONST 3, FLASH 3, BKRAM 1 [V].
- Storage addresses in the catalogue are computed by re-running the registration rules on the ROM lists [V code].
  For packed flash banks the flash address = bank flash base + (RAM − RAM base), because the whole RAM image is
  written [V]. FLASH-bank addresses are tagged [I], because the load merge can reorder records.
- FLASHD1/D2 hold large arrays (`0x7144` 52000 words, `0x7a64` 30000, `0x7044` 9200 …) [V]. They are factory
  calibration, not user settings [I].

## 4. Persistence path [V unless tagged]

**Image format** (FLASH/EEROM/MODE in flash, BKRAM in registers): `+0 u16 id` (must equal the ROM header id),
`+2 u16 checksum` (two's complement of the halfword sum of the rest, so the whole image sums to 0, `prm_bank_cksum
0x6005c7f3`), `+4 u32 generation` (+1 per save), `+8` values (packed or inline records). Check: `prm_bank_check
0x6005c78a`. With two valid copies the newer generation wins, wrap-aware (`0x6005c3bb`). The E-P7 sets only one copy
per bank, so there is no A/B redundancy.

**Boot.** `prm_banks_init` → `prm_ctl {op 0, bkram 1, flash 1, eerom 1, mode 1}` → `prm_load_all 0x6005f341`:
- FLASH: stored records whose key and count match the ROM list are kept, and the rest get ROM defaults
  (`prm_flash_bank_merge 0x6005e129`). This is the stock migration rule for firmware updates.
- BKRAM, EEROM, MODE: the shadow is checked and copied to RAM. **On a bad image the bank's ROM defaults are loaded**
  (`prm_clear`) and flags `0xa2715cb4/6/8` are set. No write-back happens at this point.
- `prm_registry_build`.

**Save** `prm_ctl` op 1 (`{op, bkram, flash, eerom, mode}`):
- FLASH/EEROM/MODE: `prm_bank_save 0x6005c5be` compares RAM with the shadow and writes only if they differ. It then
  does gen++ and the checksum, flushes the cache, and calls `prm_flash_op(size, 0, RAM, shadow)`.
- The `flash` flag also rewrites **FLASHD1 and FLASHD2** unconditionally (`0x6005c64c`, `0x6005c69b`).
- BKRAM: gen++ and checksum, then 14 register writes (`prm_bkram_save 0x6005c583`).
- `prm_flash_op 0x6005bc79`: semaphore `0x60040af0`, WDT off around the write/erase, then `flash_write 0x600c4f35`
  (mode 0), `fmem_read 0x600c4e80` (0x100) or `fmem_erase 0x600c4edc` (0x200).

**Who saves** (21 `prm_ctl` call sites):

| Entry | Flags | Callers |
|---|---|---|
| `settings_save 0x602cc6dd` | eerom + mode | `OlyHfwPower::startShutDown 0x607a957a`, sleep (`0x607aa1d6`, "SLEEP WAKEUP"), `0x607a93ed/943e/c5eb` (power code range [I]), firmware-update check `0x609a6c4b`, life tests (`OlyHfwOpeLifTstSequence`, 8 sites) |
| `settings_save_bkram 0x602cc767` | bkram | `0x60795b78`, power `0x607a93ed/943e`, sleep, Wi-Fi `0x6080be0e`, system events `0x6082546d`, `CmpCst_Function 0x6097cad5` |
| `flash_prop_save 0x602ccc3c` | flash (+ FLASHD1/D2) | `0x60827377`. Writes one of keys `0x0db1`, `0xbac1`, `0xbbc1` first |
| direct `prm_ctl` | various | power off/reboot `0x601e729e`, card CSV `0x6061907a`, updater/PTP `0x60c49587`, `0x60c49ac1`, Wi-Fi `0x60bdf7ff`, `0x60bdf96b`, `0x60be09ab`, others [V sites; roles I] |

- A setting change only updates RAM (`set_value` → store → post-set → descriptor callback). Nothing reaches flash
  until one of the saves above [V: no prm_ctl on the set path]. So a crash or battery pull loses changes made since the
  last save [I].

**DANGER** (also marked in `new_settings.py`): `prm_flash_op 0x6005bc79`, `prm_bank_save 0x6005c5be`,
`prm_fd1_save 0x6005c64c`, `prm_fd2_save 0x6005c69b`, `prm_bank_erase 0x6005c6ea`, `fmem_erase 0x600c4edc`,
`flash_write 0x600c4f35`, `prm_ctl 0x6005f099` (ops 1 and 3), `settings_save 0x602cc6dd`, `flash_prop_save 0x602ccc3c`.
- Never hook, call or patch any of them.
- Never trigger a save with the `flash` flag: it rewrites the factory data banks.
- Hooks on settings must stay in RAM (`prop_get` call sites, RE_AE §5). The flash image is whatever the RAM bank holds at
  shutdown, so a hook that writes a property persists its value [I]. Prefer read-side hooks.

## 5. Reset and snapshots

- **Per property:** `prop_set_default 0x6005ef24` copies the ROM default back, and `prop_get_default 0x6005eeab` reads
  it [V]. Per sid: `sid_prop_reset 0x602cbcbf` / `sid_prop_default 0x602cbcfd` [V].
- **Per bank:** `prm_clear 0x6005dfc3(device)` restores ROM defaults in RAM and re-registers. It persists only at the
  next save [V].
- **Settings-level:**
  - `reset_to_default 0x602b972b(count, ids)` writes `sid_default` to the property, the raw plane (`0x8b54`) and both
    parts of the active bank (`0x8b64`) [V]. `0x602b9778` does the same into the RAM sid caches [V].
  - The id lists (`0x6049b31c` 27, `0x6049c144` 626, `0x6049b352` 1785, `0x6049c628` 2, `0x6049c62c` 6) are windows into
    a `{u16 sid, u16 0/1}` pair table. Each u16 is reset as an id, so sids 0/1 are also re-defaulted [V bytes; I intent].
  - `reset_pick 0x602b0560`: if sid 10049 == 0, list 27; otherwise list 626 plus `snapshot_store(0)` [V]. That 10049
    selects Basic vs Full reset is [I].
- **Snapshots / Myset** (all three keys are in the MODE bank, so they persist with it) [V layout; I slot meaning]:

  | Key | Count | Role |
  |---|---|---|
  | `0x8b54` | 1780 | raw per-sid plane (`sid_read_raw`/`sid_set_raw`) |
  | `0x8b64` | 3560 | active bank: 2 parts × 1769 (`sid_active_get/set`) |
  | `0x85d4` | 32040 | 9 slots × 3538 words: `snapshot_load 0x602cbffe(slot)`, `snapshot_store 0x602cc03a(slot)`, `snapshot_get 0x602cc076` |

  Slot 0 is written by the reset path. Slots 1–4 = Myset1–4 (strings 357–360, "Reset/Myset") is [I]. The two parts
  are not identified [I: stills/movie or per-mode]. Mode planes (`mode_planes 0x604a8420`) restore from the active
  bank on mode entry (`0x602b97c5`) [V].

## 6. Card CSV property overlay (lead) [V path; I format]

- On every card mount, `0x60618b53` (dcfnum.c) calls `card_param_csv_load 0x6061907a`. If special folder 2 exists as a
  directory (`PARAMDT`) and holds a file matching `CP??????.CSV`, it calls `prm_clear(1)` and then `prm_ctl` op 2 [V].
- `prm_csv_load 0x6005c8e2` reads the file into `0x62496400` (≤ 0x1fffc B; "DBG_PRM_CSV_SIZE_OVER"). The parser splits
  on `,`, skips `//` comments and blanks, upper-cases, and reads decimal, `0X` hex or `-` negative values [V helpers
  `0x6005cbfb..0x6005cc6b`]. The record layout it emits is inline `{key, count, data}` [V consumer]. The column order
  is unconfirmed, likely "TagID, values" after the `prmdbg setval <(cnt<<16)|TagID>` help text [I].
- `prm_csv_overlay_build 0x6005d8e3` registers it as a second registry `0xa2707a88` and sets `0xa26ffa84 = 1`.
  `prop_lookup` then serves overlay keys first [V].
- **Why it matters:** any property can be overridden at boot from the card with no firmware patch. It is RAM-only:
  saves write the bank RAM, not the overlay [V], and the next mount clears it (`prm_clear(1)`) [V].
- **Risks:**
  - A count larger than the real property makes readers index past the data [I]. Keep counts equal.
  - Do not override keys that the descriptor callbacks write back, or the overridden value might reach a bank through
    them [I].
  - Camera probe first: one harmless key, for example a CPRAM display flag.

## 7. Hidden and unused sids (unlock leads)

The catalogue marks 513 sids (216 key groups) as `lead`: MODE-persisted, validator with ≥ 2 values, no
menu/editor/LC/remote/grey-out reference found. Many are per-mode copies or editor-only values that this scan misses
[I]. Top picks:

| Lead | Sids / keys | Evidence | Next step |
|---|---|---|---|
| **AF Limiter** | 1149 `0x5391` On/Off, 1150 `0x53a1` preset 0–2, 1151/1153/1155 `0x53b2[0..2]` near (defaults 50/100/500), 1152/1154/1156 `0x53c2[0..2]` far (9999). Also 1273 `0x5642`, 1274 `0x5651` | Full menu records (`0x6117d9f8` "AF Limiter", strings 2952/2953/2970/3146) and focus code that reads all these keys (`fcs_limit_calc_fl 0x6069166d`, `drive(LIMIT)` `0x606d4fe9`, TAKE_FOCUS `0x606bc087`; 1273/1274 also `fcs_limit_drive_exec 0x60691b0e`) [V] | Camera: look for it in Custom Menu A. If hidden, find the model filter (LOOK_MENUS §1 row 9) [I] |
| **Card CSV overlay** | any key | §6 [V] | One-key probe on camera |
| Focus-stack flag | 1333 `0x9331` {0, 1} | read in `fcs_calc_focus_bracket_info` / `stacking_clip` (`0x6065ff16`) [V] | The backend is absent (UNLOCK_LEADS §2); low value |
| Kelvin pair | 520/521 `0xdfc2[0..1]`, 2000–14000, default 5400 | one reader `0x60c67b49` (playback/RAW edit range) [V] | Probably RAW-edit WB K [I] |
| AF-frame offsets | 1175/1176 `0xef09` ±20, 1177/1178 `0xef19` ±13 | 20 key reads, AE detect, LV frame code (`frame_rect`) [V] | Meaning untraced [I] |
| Unknown with callbacks | 263 `0x9132` 80–10000 (default 90, cb `0x602b60c9`, capture readers), 686 `0xeee1` {0, 1} (cb `0x602b648e`, 16 reads incl. rec_mem.c, AE detect), 1440 `0x4a21` 1–6 / 1443 `0x4b71` {1, 2, 4, 8} (cb `0x602b259f`) | [V] | Trace the readers |
| WB-group selector | 335 `0x72c2`: values are sids 324/325/326/329/330/3459 | readers in `res_read`/`res_clear` (`0x6015afd0`) [V] | Ties to the WB fine-tune leads (PROFILE_INDEX_WB §2) [I] |
| Exp-comp memories | 224–228 `0x9e4a..0x9e7a` ±1280 (228: 0..1792) | no immediate key reads [V] | Likely per-mode memories [I] |

- Values beyond the menu: only sid 845 (BGM) has a validator value (2) that no option offers [V]. Validator-list
  widening (aspect, buttons) remains the known route (FIRMWARE_GUIDE §3).
- Pro Capture / High Res gates 758/764/1158/1493 are MODE properties with no validator [V]. That confirms
  UNLOCK_LEADS: the gate is not the problem.

## 8. Open

- Slot numbers of `0x85d4` against Myset1–4, and the two parts of `0x8b64`: one camera read of `snapshot_get` before
  and after "Assign to Myset1".
- Who calls `reset_pick` (indirect), and the All Reset (string 54) path: is it `prm_clear(7)` + save?
- CSV column format: needs one sample file. Stock has no writer; the debug `prmdbg` shell uses the same TagID syntax.
- Descriptor slots other than +24 (+4/+8 get/set for 3/4/17, +16, +20 `0x602b0781`, +40, +44 `0x602b0790`, +48)
  are unnamed.
- The second 60-B descriptor run at `0x60437ecc`.
