# Olympus OM-D E-M1 Mark II Firmware Function & Table Reference (v3.70)

**Target Firmware**: Olympus OM-D E-M1 Mark II, Version 3.70 (Build 3700, Model ID `0x1250`)  
**Target CPU**: Panasonic MN10300 (AM33-2) 32-bit RISC Core  
**Decoded Binary**: `em1mk2/extracted/00_0100_40560020.decoded.bin` (23,068,608 bytes)  
**Execution Base VMA**: `0x60021020`  
**Disassembly Ground Truth**: Verified via GNU Binutils (`mn10300-elf-objdump -m am33-2`)

---

## 1. Settings Subsystem & GUI Facade (`OlyApiSettingController`)

### `0x608362c5` — `OlyApiSettingController::GetInstance`
* **Role**: Singleton accessor for the GUI Settings Controller facade (`OlyApiSettingController`).
* **Calling Convention**: `call 0x608362c5, [], 4` $\to$ returns `a0 = facade` (`0x61f9e48c`).
* **Vtable (`0x60afb400`)**:
  * `+0x00` (`0x60837170`): `SetValue(a0 = facade, d0 = setting_id, d1 = op, a1 = value)`. With `op = 0` it calls `0x60863a8a(sid, value)`; `op = 1/2/3` call `0x60863b69` / `0x60863b2e` / `0x60863af3`. Returns `0` on success, `0xF0000058` while global camera-state bits (`0x607abb14`) say busy (applies to every sid except 285/42/29), `0xF0000016` when the value is rejected. **It does not filter by sid or picture mode** (corrected 2026-11-10; the old note said it did). The stock Color Creator commit `0x60e4c0a7` writes 617/618 with this call. The "writes / refreshes ISP / notifies" chain below `0x60863a8a` is not re-verified.
  * `+0x08` (`0x60836747`): `GetValue(a0 = facade, d0 = setting_id, a1 = &out_val)`.
  * `+0x18` (`0x60836769`): `GetCount(a0 = facade, d0 = setting_id)` $\to$ `0x608632dc`.
  * `+0x1c` (`0x60836991`): `GetValueByIndex(a0 = facade, d0 = setting_id, d1 = index, a1 = &out)` $\to$ `0x608632e8`.
  * `+0x24` (`0x60836357`): `IsValueAvailable(a0 = facade, d0 = setting_id, d1 = value)` $\to$ delegates to `0x608632ba` [not re-verified].

### Direct Setting Accessors
| Function | VMA | Signature | Description |
| :--- | :---: | :--- | :--- |
| **sid getter** | `0x602da802`, `0x602da602` | `d0 = sid` $\to$ `d0 = value` | Both call `0x602db73f` (used by SetValue with sid 478) [V]. |
| `0x602da5f9` | `0x602da5f9` | `d0 = sid` | Calls `0x602db6e0`, **not** the sid getter. v0.1 used it as `em1_get_setting`; role not traced. |
| **set_setting_active** | `0x602da60b` | `d0 = sid, d1 = value` | Calls `0x602db7c0`; runs observers synchronously (calling it during editor init froze the camera in v0.1). Not used. |
| `0x602da6b9` | `0x602da6b9` | `void` | Calls `0x602df633`. v0.1 called it "commit_tone_curve" without tracing it; dropped in v0.2b1. |
| `(0x61fbfc94)` vtable `+76` | – | – | Called by v0.1 as "ISP refresh", never traced; dropped in v0.2b1. |
| **property getter** | `0x6005e6cf` | `d0 = key, d1 = index, a0 = 0` $\to$ `d0` | Raw property read used by the request builder (E-P7 `0x6005e971`) [V]. |

### Sid Table (`0x604f808c`)
Sid `0..1624` → `{u16 property key, u16 index}`, same format as the E-P7's `0x604d6c14`; lookup `0x602fb97c`. Key = `id << 4 | type`. See `ARCHITECTURE_AND_MEMORY_MAP.md` §7.3 for the colour and tone sids.

### Validator Table (`0x604ee648`)
* **Bounds**: `0x604ee648` to `0x604f4544` (1,215 entries $\times$ 20 bytes), **not sorted by sid**.
* **Entry Layout** (20 bytes): `{u16 sid, u16 attr, u32 list, u32 alt, u16 bytes, u16 elem, u8 sub, u8 type}` (E-P7 `0x604cc98c` layout). Values = `bytes / elem` signed entries of size `elem` at `list`.
* **Colour and tone entries** [V 2026-11-10; the old `val_arr` addresses in this section pointed at unrelated data and are removed]:
  * `449` (`0x604f13fc`) / `450` (`0x604f13e8`): byte, `-7..+7`. Keys `0xD7EA` / `0xD7F9`; role not traced.
  * `617` (`0x604f199c`): byte list `0x604edb95`, `0..29` (Color Creator hue).
  * `618` (`0x604f19b0`): byte list `0x604edbb3`, `-4..+3` (Color Creator vividness).
  * `889 / 890 / 891`: half, `-7..+7` (ordinary-mode tone, keys `0xF609/F619/F629`).
  * `383 / 384 / 692`: half, `-7..+7` (tone mirrors read by the request builder).
  * `925..960`: half, `-5..+5` (per-profile saturation `0xF6FA`, COLOR1..3 × 12).
  * `961..969`: half, `-7..+7` (COLOR1..3 tone, keys `0xF709/F719/F729` [set]).
  * `913..924` (effective saturation `0xF6EA`) and `978 / 988 / 992`: **no record** (derived).

---

## 2. Live View Editor Parent & Child Widget Subsystem (`0x60e8b6be` / `0x60e4a59c`)

### Editor Parent Controller Table (`0x61258af8`)
* **Bounds**: 92 entries $\times$ 56 bytes (`0x38`), searched by `0x60e8b6be` and copied into `parent+32..+84` by `0x60e8b9bd`.
* **Entry 79 (`0x61259c40`, Key `0x13a9` = 5033 — Live View Color Creator)**:
  * `+04` (`0x61259c44`, `(36, parent)`): Create (`0x60e8b9bd` $\to$ `cc_init`)
  * `+08` (`0x61259c48`, `(40, parent)`): Destroy (`0x60e8bafc`)
  * `+12` (`0x61259c4c`, `(44, parent)`): Up (`0x60e8bda4` $\to$ `cc_up`, called by `0x60e8bb39`)
  * `+16` (`0x61259c50`, `(48, parent)`): Down (`0x60e8bedf` $\to$ `cc_down`, called by `0x60e8bb61`)
  * `+20` (`0x61259c54`, `(52, parent)`): Left (`0x60e8c0f5` $\to$ `cc_left`, called by `0x60e8bb89`)
  * `+24` (`0x61259c58`, `(56, parent)`): Right (`0x60e8c46a` $\to$ `cc_right`, called by `0x60e8bbb1`)
  * `+28` (`0x61259c5c`, `(60, parent)`): Dial 1 / Rear Dial (`0x60e8c786` $\to$ `cc_dial1`, called by `0x60e8bbd9`)
  * `+32` (`0x61259c60`, `(64, parent)`): Dial 2 / Front Dial (`0x60e8c9d3` $\to$ `cc_dial2`, called by `0x60e8bc0f`)
  * `+36` (`0x61259c64`, `(68, parent)`): Event (`0x60e8cc69` $\to$ `cc_page`, called by `0x60e8bc97`)
  * `+40` (`0x61259c68`, `(72, parent)`): OK (`0x60e8d1ea`, called on `0x9015`)
  * `+44` (`0x61259c6c`, `(76, parent)`): INFO (`0x60e8d038` $\to$ `cc_info`, called on `0x9014` by `0x60e8bc45`)

### Child Setting Widget (`0x60e4a59c` / `0x60e4e3ae`)
* **Parent Pointers**:
  * `(124, parent)`: Child 0 (`setting_id = 617`, Hue `0..29`)
  * `(128, parent)`: Child 1 (`setting_id = 618`, Vividness `-4..+3`)
* **`0x60e4a59c` (`em1_child_sync`)**:
  * Queries `facade->GetCount(setting_id)`, `facade->GetValue(setting_id, &cur_val)`, and `facade->GetValueByIndex(setting_id, idx)`, updating `(92, child)` (count), `(94, child)` (matching index for `cur_val`), and `(104, child)` (allocated value array).
* **`0x60e4e3ae` / `0x60e4e6e7` (Child Event Handler for `0x900c` = `36876`)**:
  * Reads `idx = (94, child)` and `val = ((104, child))[idx]`, calls `facade->SetValue((80, child), 0, val)`, and notifies the Color Creator View (`0x60e542a2`) to redraw the Color Wheel cursor and bottom guide banner.

### Color Creator View Part Table (`0x60297fac` $\to$ `.data` `0x61fbd4ec`)
* **View Constructor / Updater**: `0x60e540f4` / `0x60e542a2`
* **Part Table**: 5 function pointers copied at boot from ROM `0x60297fac` to `.data` `0x61fbd4ec`:
  * `0x60297fac` (`0x61fbd4ec`): Part 1 (`0x60e542ff`)
  * `0x60297fb0` (`0x61fbd4f0`): Part 2 (`0x60e5435f`)
  * `0x60297fb4` (`0x61fbd4f4`): Part 3 (`0x60e543d6` $\to$ `cc_guide` — Guide Label writer at `view+40..+114`)
  * `0x60297fb8` (`0x61fbd4f8`): Part 4 (`0x60e54463`)
  * `0x60297fbc` (`0x61fbd4fc`): Part 5 (`0x60e548a8`)

---

## 3. Native RTOS Memory, Filesystem & Trigger Subsystems

| Function Name | VMA | Calling Convention / Registers | Description |
| :--- | :--- | :--- | :--- |
| **`malloc`** | `0x6002329a` | `call 0x6002329a, [], 4`<br>`d0 = size` $\to$ `a0 = ptr` | Allocates memory from the class-1 uncached heap pool `[0xa1f80800, 0xa1f8b540)`. |
| **`free`** | `0x600232d9` | `call 0x600232d9, [], 4`<br>`a0 = ptr` | Deallocates heap memory back to the class-1 pool. |
| **`fopen`** | `0x6063bbbd` | `call 0x6063bbbd, [], 4`<br>`a0 = path_ptr`, `a1 = mode_ptr` $\to$ `a0 = FILE *` | Olympus FAT32 file open wrapper (`C:\` = Slot 1, `D:\` = Slot 2). |
| **`fclose`** | `0x6063c1b2` | `call 0x6063c1b2, [d2, a2, a3], 16`<br>`a0 = FILE *` $\to$ `d0 = status` | Closes file handle and releases OS file descriptor. |
| **`fseek`** | `0x6063c840` | `call 0x6063c840, [d2, d3, a2, a3], 20`<br>`a0 = FILE *`, `d0 = offset`, `d1 = whence` | Repositions file offset (`1 = SEEK_END`, `2 = SEEK_SET`). |
| **`ftell`** | `0x6063ce15` | `call 0x6063ce15, [d2, a2, a3], 16`<br>`a0 = FILE *` $\to$ `d0 = position` | Returns current file offset in bytes. |
| **`fread`** | `0x6063cf0d` | `call 0x6063cf0d, [d2, d3, a2, a3], 24`<br>`a0 = dest`, `d0 = size`, `d1 = count`, `a1 = FILE *` | Reads data blocks from file into destination memory. |
| **`trig1_hook`** | `0x6023d0db` | `call 0x6023cf7c, [], 4` $\to$ `call 0x60580200, [], 4` | Shutter half-press (`TRIG1`) classifier in `HLS_EVENT` task; calls `sd_loader` gate once per boot. |

---

## 4. Focus Stacking & Video Recording Subsystems

### `0x60656a2d` — `fcs_check_focus_stacking_enable`
* **Hook Site (`0x60656a4a`)**: `c9 04` (`bne 0x60656a50`) $\to$ `cb cb` (`nop; nop`), unlocking in-camera focus stacking for all autofocus lenses.

### `0x603549b9` — `video_recording_duration_limit_eval`
* **Hook Sites (`0x603549d7`, `0x603549dc`)**: `cc 06` (`1740s` = 29 min) and `20 1c` (`7200s` = 2 hr) $\to$ `90 7e` (`32400s` = 9 hr).

---

## 5. TruePic VIII ISP Pipeline & Color / Tone Generation

### `0x603ed86c` — `isp_execute_stages`
* **Role**: Sequential execution loop iterating through TruePic VIII ISP hardware/software stages.
* **Stage Function (`0x603ec82c`)**: Invoked when processing stage record for Picture Mode / Color Control.
  * Stock behavior: Tests `d1 == 11` (COLOR Profile Control). If `d1 != 11` (e.g. Color Creator mode `d1 == 10`), it branches to `0x603ec8d3` and skips matrix generation entirely.
* **Release Status**: Kept 100% stock. Hooking this early ISP stage from Section 2 into later-loaded sections caused watchdog boot loops due to the TruePic VIII section load order (`1, 7, 2, 3, 4, 5, 6, 8, 9`). Colour and tone control go through the GUI Settings Controller facade (`0x60837170`) in Section 6. v0.1 wrote sids `915..926` and `449, 450, 963..965`, which are the wrong ids on this body; v0.2b1 writes `617/618` and tone `889/890/891` (see `ARCHITECTURE_AND_MEMORY_MAP.md` §7.3).

### `0x603ec642` — `isp_calc_12sector_matrix`
* **Role**: Computes TruePic VIII 12-sector matrix transformation and loads color coefficients.
* **Arguments**:
  * `a0`: ISP context record (`sp+4` in stage caller).
  * `a1`: Pointer to array of 12 signed 16-bit halfword saturation values (`s16 sat[12]`, 24 bytes total).
  * `a2`: Input picture mode record (`R`).
  * `a3`: Output hardware register target block (`O`).

### `0x603ecf7e` — `isp_build_luminance_tone_curve`
* **Role**: Computes the 256-word luminance curve for hardware tone mapping.
* **Stock Behavior**: Calls `0x6038b2ce` to test `*(R + 1512)`. If unpopulated, bypasses curve bending.
* **Release Status**: Kept 100% stock. v0.1 also called `0x602da6b9` (`-> 0x602df633`) and `0x61fbfc94` vtable+76 after tone writes; neither was traced, and v0.2b1 drops both.

### `0x6038b379` — `isp_populate_spline_knot_deltas`
* **Role**: Scales 5 signed halfwords (`blacks, whites, highlights, midtones, shadows`) by `4096 / 7` and populates the 8 spline knot deltas at `C + 64` via `0x6038afd5`.
* **Arguments**:
  * `a0`: Pointer to 5 signed 16-bit halfwords on stack (`sp+4`).
  * `a1`: Destination knot delta buffer (`C + 64` = `(52, sp) + 64`).

### `0x6038b63a` — `isp_generate_spline_curve_256`
* **Role**: Bends the monotonic 256-word luminance transfer function according to the 8 spline knot deltas at `C + 64`.

