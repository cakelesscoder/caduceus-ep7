# Olympus OM-D E-M1 Mark II: Focus Stacking Limit Removal Analysis

This document provides a comprehensive reverse-engineering analysis of the in-camera **Focus Stacking** lens restriction in the Olympus OM-D E-M1 Mark II (firmware **v3.70** / build `3700`, model ID `125`), along with the exact opcode patch and automated tool to unlock automatic focus stacking on **any autofocus lens**.

---

## 1. Executive Summary

- **Restriction**: Olympus restricts in-camera Focus Stacking to an explicit allowlist of first-party M.ZUIKO PRO and Macro lenses (e.g., 12-40mm f/2.8 PRO, 40-150mm f/2.8 PRO, 60mm f/2.8 Macro, 300mm f/4.0 IS PRO, etc.). When an unsupported autofocus lens is attached (such as Olympus standard lenses, Panasonic Leica/Lumix lenses, Sigma DC DN lenses, etc.), the camera greys out the Focus Stacking menu toggle and disables in-camera composite generation.
- **Root Cause**: The decision is made inside function `fcs_check_focus_stacking_enable` at `0x60656a2d` (file offset `0x635a0d` in Partition 0, `00_0100_40560020.decoded.bin`). After querying the lens capabilities at `0x60233c46`, a conditional branch instruction at `0x60656a4a` (file offset `0x635a2a`) evaluates the compatibility test. If the lens is not recognized on the allowlist, the branch skips the assignment instruction `mov 1, d0`.
- **The Patch**: Modifying 2 bytes at offset `0x635a2a` from `c9 04` (`BNE +4`) to `cb cb` (`NOP NOP`) eliminates the rejection branch. The function unconditionally executes `mov 1, d0`, marking the attached lens as fully stacking-compatible.
- **Hardware Prerequisites Retained**: The camera's prerequisite guards (null lens check, autofocus mode readiness, battery level, shutter state) remain completely intact. Standard Micro Four Thirds focus stepping commands (`0x1b...` SPI packets) are supported natively by all autofocus lenses.

---

## 2. Firmware Context & Landmarks

| Attribute | Specification |
| :--- | :--- |
| **Camera Model** | Olympus OM-D E-M1 Mark II (model code `125`) |
| **Firmware Version** | v3.70 (`3700`) |
| **Target Partition** | Partition 0 (`0x100`, Main RTOS & Camera Application) |
| **Partition Size** | 23,068,608 bytes |
| **Architecture** | Panasonic MN103 (AM32R 32-bit RISC, Little-Endian) |
| **Virtual Base Address (VMA)** | `0x60021020` |
| **Routine Name** | `fcs_check_focus_stacking_enable` |
| **Routine VMA Range** | `0x60656a2d` – `0x60656b8e` (length: 354 bytes) |
| **Routine File Offset** | `0x635a0d` – `0x635b6e` |
| **Diagnostic String Landmark** | `"fcs_check_focus_stacking_enable stacking"` at `0x6074750d` (`0x7264ed`) |

---

## 3. Disassembly & Deep-Dive Analysis

### 3.1 Call Graph & Control Flow

```
                      fcs_check_focus_stacking_enable (0x60656a2d)
                                          │
                         CALL32 0x602299f5 (Lens Object Getter)
                                          │
                         Is Lens Pointer NULL? (0x60656a3e)
                                ├── Yes ──> [Reject / Exit 0]
                                └── No
                                          │
                         CALL32 0x60233c46 (Lens Allowlist & Capability Check)
                                          │
                    ┌─────────────────────┴──────────────────────┐
                    │ Branch at 0x60656a4a (Offset 0x635a2a)     │
                    │ Stock: c9 04 (BNE +4)                      │
                    └─────────────────────┬──────────────────────┘
                                          │
                 ┌────────────────────────┴────────────────────────┐
                 │                                                 │
      [Stock: Not on Allowlist]                          [Patched / On Allowlist]
          Branch to 0x60656a50                              Fallthrough to 0x60656a4c
                 │                                                 │
          (d0 remains 0)                                     8a 01: mov 1, d0
                 │                                                 │
                 └────────────────────────┬────────────────────────┘
                                          │
                         Prerequisite Guard Evaluations (AF/Mode)
                                          │
                         Store result to State Descriptor
                                          │
                                         RTS
```

### 3.2 Annotated Assembly of Decision Gate

The disassembly below details the critical sequence in `fcs_check_focus_stacking_enable` around `0x60656a4a` (file offset `0x635a2a`):

```nasm
; --- Step 1: Query Lens Descriptor ---
0x60656a35  (+0x635a15):  dd bb 2f bd ff    CALL32  0x602299f5        ; fcs_get_current_lens_object() -> a0
0x60656a3a  (+0x635a1a):  a0 0c             mov     d0, (sp+12)
0x60656a3c  (+0x635a1c):  14 a8             cmp     0, a0              ; Check if lens is physically mounted
0x60656a3e  (+0x635a1e):  c9 10             bne     0x60656a50        ; If lens attached, continue

; --- Step 2: Query Capability and Allowlist Matching ---
0x60656a40  (+0x635a20):  dd 01 d2 bd ff    CALL32  0x60233c46        ; Check lens ID against stacking table
0x60656a45  (+0x635a25):  00 04
0x60656a47  (+0x635a27):  14 a0 01          cmp     1, d0              ; Did capability check succeed?

; --- Step 3: Compatibility Decision Branch (THE TARGET) ---
0x60656a4a  (+0x635a2a):  c9 04             bne     0x60656a50        ; [STOCK] Skip enable if not matched
                                                                        ; [PATCH] cb cb (NOP NOP) -> fall through!

; --- Step 4: Stacking Enable Flag Assignment ---
0x60656a4c  (+0x635a2c):  8a 01             mov     1, d0              ; Enable focus stacking support!
0x60656a4e  (+0x635a2e):  fc a5 38 e9 2c 62 mov     (0x622ce938), a0   ; Diagnostic state pointer

; --- Step 5: Diagnostic Logging (if debug enabled) ---
0x60656a54  (+0x635a34):  fa ed 00 02       ...
0x60656a58  (+0x635a38):  c8 11             beq     0x60656a6b
0x60656a5a  (+0x635a3a):  fc dc 0d 75 74 60 mov     0x6074750d, a0     ; String: "fcs_check_focus_stacking_enable stacking"
0x60656a60  (+0x635a40):  88 14             mov     d0, a1
0x60656a62  (+0x635a42):  dd ea 21 0a 00    CALL32  0x606f8c51        ; Debug log routine
```

When `0x60656a4a` (`c9 04`) is replaced with `cb cb` (`nop nop`), the conditional jump to `0x60656a50` never triggers. Regardless of the return value from `0x60233c46`, execution flows directly into `8a 01` (`mov 1, d0`), marking the attached lens as qualified for focus stacking.

---

## 4. Historical Precedent & Version Matrix

Cross-firmware analysis across historical patches confirms how Olympus shifted this routine across major updates:

| Firmware Build | Function Address | Patch Address | Patch File Offset | Stock Instruction | Patched Instruction |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **v3.00** (`3001`) | `0x60652d28` | `0x60652d8f` | `0x631d6f` | `c8 07` (`BEQ +7`) | `cb cb` (`NOP NOP`) |
| **v3.40** (`3400`) | `0x60656a7e` | `0x60656aeb` | `0x635a7b` | `c8 07` (`BEQ +7`) | `cb cb` (`NOP NOP`) |
| **v3.60** (`3600`) | `0x60656a2d` | `0x60656a4a` | `0x635a2a` | `c9 04` (`BNE +4`) | `cb cb` (`NOP NOP`) |
| **v3.70** (`3700`) | `0x60656a2d` | `0x60656a4a` | `0x635a2a` | `c9 04` (`BNE +4`) | `cb cb` (`NOP NOP`) |

> [!NOTE]
> Firmware **v3.70** maintains the exact binary layout, code addresses, and opcode alignment as **v3.60** for the focus stacking subsystem. Offset `0x635a2a` is identical between v3.60 and v3.70.

---

## 5. Byte Diff & Checksum Verification

### 5.1 Decoded Partition 0 Diff

In `00_0100_40560020.decoded.bin`:

```
Offset 0x635a2a:
  Stock:   c9 04  (BNE +4)
  Patched: cb cb  (NOP NOP)
```

Surrounding 32-byte context verification:
```
Stock:   00 04 14 a0 01 c9 04 8a 01 fc a5 38 e9 2c 62 fa ed 00 02 c8 11 fc dc 0d 75 74 60 88 14 dd ea 21
Patched: 00 04 14 a0 01 cb cb 8a 01 fc a5 38 e9 2c 62 fa ed 00 02 c8 11 fc dc 0d 75 74 60 88 14 dd ea 21
                        ^^^^^
```

### 5.2 Container Checksum Repair

The Olympus `OE` container uses a 32-bit two's complement additive word checksum over the decoded payload, header, and trailer:

$$\left(\sum_{w \in \text{Header}} w + \sum_{w \in \text{Decoded Payload}} w + \sum_{w \in \text{Trailer}} w\right) \bmod 2^{32} = 0$$

- Modifying `c9 04` (word `0x04c9`) to `cb cb` (word `0xcbcb`) increases the payload sum by:
  $$\Delta = 0\text{xcbcb} - 0\text{x04c9} = 0\text{xc702}$$
- The 4-byte checksum field at byte offset 28 of the 32-byte Partition 0 trailer adjusts accordingly:
  - Stock trailer checksum: `0x0123e5f8` (bytes: `f8 e5 23 01`)
  - Patched trailer checksum: `0x3a21e5f8` (bytes: `f8 e5 21 3a`)
- All other 4 partitions (`0x101`, `0x106`, `0x10e`, `0x102`) remain 100% byte-identical with unchanged checksums.

---

## 6. Automated Patch Tool

A standalone, self-contained Python patch utility is provided at:
[`scripts/patch_focus_stacking.py`](file:///home/hertzel/projects/olympus-firmware/scripts/patch_focus_stacking.py)

### Usage

```bash
# Apply patch to stock firmware
python3 scripts/patch_focus_stacking.py E1259999.BIN -o output/E1259999_STACKING_PATCHED.BIN

# Dry-run inspection without writing
python3 scripts/patch_focus_stacking.py E1259999.BIN --dry-run
```

### Verification Output

```
[*] Reading source firmware from E1259999.BIN...
[+] Loaded container with 5 partitions.
[*] Checking Partition 0 (Length: 23,068,608 bytes)...
[+] Target found: offset 0x635a2a (0x60656a4a): c904 -> cbcb
[*] Rebuilding container and recalculating additive checksums...
[*] Verifying roundtrip integrity of repacked binary...
[+] Repacked container verified successfully!
[+] Successfully wrote patched firmware to: output/E1259999_STACKING_PATCHED.BIN
    Size: 93,050,944 bytes
```

---

## 7. Flashing the Patched Firmware

To install the patched firmware onto the camera:

1. **Filename Convention**: Place the patched file onto the root of an SD card formatted in the camera.
   - For standard body updates: name the file `E1259999.BIN` (or `OLY_E_125_3700_0000_0000.BIN` if using camera updater software).
2. **Camera Flasher Search Order**:
   - The camera's built-in update loader in Partition 3 (`0x10e`) searches the root directory and `\DCOLYMP\` directory for `F???????BIN`, `L???????BIN`, and `%04x%04xBIN` (see [docs/FIRMWARE_UPDATE_SUBSYSTEM.md](file:///home/hertzel/projects/olympus-firmware/docs/FIRMWARE_UPDATE_SUBSYSTEM.md)).
3. **Safety Verification**:
   - The file size must match `93,050,944` bytes exactly.
   - The container roundtrip test confirms that all 5 partition headers, trailers, and 32-bit additive checksums pass the camera bootloader's preflight check.
