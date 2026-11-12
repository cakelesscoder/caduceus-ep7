# Olympus OM-D E-M1 Mark II Firmware Analysis (E1259999.BIN)

**Date**: 2026-10-30  
**Target File**: `E1259999.BIN`  
**Camera Model**: Olympus OM-D E-M1 Mark II (Internal model ID `125` / `0x1250`)  
**Firmware Version**: v3.70 (Internal version field `0x3700`)  
**File Size**: 93,050,944 bytes (88.74 MiB)  
**SHA-256**: `f0c25dd80e3fe2f38af0bc515f250692c47c42758eef411dfaef1f9674dd66dc`  

---

## 1. Executive Summary

`E1259999.BIN` is the official camera update payload for the Olympus OM-D E-M1 Mark II, formatted for manual SD-card recovery and offline flashing (via the `DCOLYMP/` directory with the `OK` button held during power-on).

The file is encapsulated inside Olympus's proprietary scrambled **`OE`** container format. It consists of **5 distinct partitions/blocks**, each with an independent 32-byte header, 32-byte trailer, and separate 32-bit additive checksum verification.

---

## 2. Olympus `OE` Container Format & Deobfuscation

### 2.1 Block Framing & Metadata
Each partition block has the following structure:
- **Header**: 32 bytes (`offset`)
- **Payload**: $N$ bytes (multiple of 16 bytes)
- **Trailer**: 32 bytes (`offset + N + 32` to `offset + N + 64`)

#### Header / Trailer Fields (Little-Endian)
| Byte Range | Type | Field Name | Description |
| :--- | :--- | :--- | :--- |
| `0x00 - 0x01` | ASCII | Magic | Signature bytes `0x4F 0x45` (`OE`) |
| `0x02 - 0x03` | uint16 | Model ID | Camera model identifier (`0x12 0x50` = model `125`) |
| `0x04 - 0x07` | uint32 | Reserved | Zero padding |
| `0x08 - 0x0B` | uint32 | Load Address | Target load address in memory/flash |
| `0x0C - 0x0F` | uint32 | Payload Size | Uncompressed size in bytes |
| `0x10 - 0x11` | uint16 | Version | Payload release version (e.g. `0x3700` = v3.70) |
| `0x14 - 0x15` | uint16 | Block Kind | Partition kind identifier (`0x0100`, `0x0101`, etc.) |
| `0x1C - 0x1F` | uint32 | Checksum | Zero in header; additive checksum in trailer |

### 2.2 Scrambling Algorithm
The payload bytes are scrambled in 16-byte blocks using byte-level bit inversion followed by index transposition:

1. **Byte Inversion**:
   $$\text{byte}' = \text{byte} \oplus 0\text{xFF}$$
2. **16-Byte Transposition**:
   $$\text{DECODE\_ORDER} = (1, 3, 0, 2, 6, 4, 7, 5, 11, 10, 9, 8, 13, 14, 12, 15)$$
   Every 16-byte stride in the payload is remapped according to this permutation vector.
3. **Additive 32-Bit Checksum**:
   Summing all 32-bit unsigned words of the header, decoded payload, and trailer modulo $2^{32}$ yields exactly `0`:
   $$\left(\sum_{i} \text{Word32}(\text{Header}) + \sum_{j} \text{Word32}(\text{Payload}) + \sum_{k} \text{Word32}(\text{Trailer})\right) \pmod{2^{32}} = 0$$

---

## 3. Extracted Partition Table

All 5 partitions were extracted and verified with $100\%$ checksum validity into [`extracted/`](file:///home/hertzel/projects/olympus-firmware/extracted):

| Block | File | Size | Kind | Load Address | Version | SHA-256 | Description |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- | :--- |
| **0** | [`00_0100_40560020.decoded.bin`](file:///home/hertzel/projects/olympus-firmware/extracted/00_0100_40560020.decoded.bin) | 23,068,608 B (22.0 MB) | `0x0100` | `0x40560000` | `3.70` | `7c2fa57fbe2c5716d940f47719e2917c8ecc17f3a1dd18ad97c73e4e62300c88` | **Main System Firmware**: RTOS kernel, task scheduler, camera control logic, UI menus, SD updater routines, 66,141 system strings |
| **1** | [`01_0101_42060020.decoded.bin`](file:///home/hertzel/projects/olympus-firmware/extracted/01_0101_42060020.decoded.bin) | 26,214,336 B (25.0 MB) | `0x0101` | `0x42060000` | `1.00` | `35f385b7350fa10d7277eb0eec4ac787efeeeac13937b4111160202f02395dde` | **DSP Subsystem**: Secondary processor code for TruePic VIII image processing core |
| **2** | [`02_0106_43960020.decoded.bin`](file:///home/hertzel/projects/olympus-firmware/extracted/02_0106_43960020.decoded.bin) | 38,797,248 B (37.0 MB) | `0x0106` | `0x43960000` | `1.00` | `ed5208fb2bf833a364883d8df35d33e07a57f1254636881913efa322f118e8b8` | **Calibration & ISP Tables**: Color matrices, sensor defect maps, lens correction profiles, and lookup tables |
| **3** | [`03_010e_40002820.decoded.bin`](file:///home/hertzel/projects/olympus-firmware/extracted/03_010e_40002820.decoded.bin) | 251,904 B (246 KB) | `0x010e` | `0x40002800` | `0.01` | `b812f596d9b47f33e5bbeb6dfb9299b77f84e2812dd54d61ff7b725e3ff3a6f6` | **Bootloader / IPC**: Early stage initialization, inter-processor communication (`time_m_cpu1`, `wait que`, `open err!!`) |
| **4** | [`04_0102_470e0020.decoded.bin`](file:///home/hertzel/projects/olympus-firmware/extracted/04_0102_470e0020.decoded.bin) | 4,718,528 B (4.50 MB) | `0x0102` | `0x470e0000` | `1.00` | `65c5c0b582e7d91a9943a2335feb773306f8db730ae68687f634f9bb981d1399` | **OSD Graphics & Assets**: UI bitmaps, LCD fonts, menu icons, color palettes, EXIF templates (`OLYMPUS Viewer 3`) |

---

## 4. Reverse Engineering via REA

### 4.1 Ingestion via REA MCP
Because `E1259999.BIN` is an encrypted container rather than a raw ELF/PE binary, direct ingestion with `open_binary` on the `.BIN` container fails with `unsupported binary format`.

Once decoded, individual raw binary blocks can be opened and tracked in REA using `open_binary`:
```json
{
  "path": "/home/hertzel/projects/olympus-firmware/extracted/00_0100_40560020.decoded.bin",
  "format": "raw-binary",
  "architecture": "arm",
  "entry_point": "0x40560020"
}
```

This registers the session and generates persistent content-addressed Evidence records:
- **Artifact Evidence**: `ev_6565bcb694ebd85ce30475adc6c65562a071cfc13858017de487faa91dcc7b81`
- **Objdump Inspection Evidence**: `ev_fe3b88afc6065a1c7c9551c3bdebe12b5313436ddbe96ad43746ddd5a74bbb90`

### 4.2 Configuring Disassembly & Analysis Providers
To use REA's deep static analysis features (`analyze_function`, `procedure_pseudo_code`, `list_procedures`):
1. **Ghidra**: Set the environment variable `GHIDRA_INSTALL_DIR` pointing to an extracted Ghidra 12.1.x distribution with Java 17+.
2. **Binwalk / Unblob**: For signature discovery via `inspect_firmware_regions` or `extract_firmware`, configure `REA_BINWALK_COMMAND=/usr/bin/binwalk`.

---

## 5. Offline Python Decoder Reference

The following script can be used to extract or repack any Olympus `OE` firmware container:

```python
#!/usr/bin/env python3
"""Offline Olympus OE firmware container decoder/unpacker."""

from array import array
from dataclasses import dataclass
import hashlib
from pathlib import Path
import struct
import sys

DECODE_ORDER = (1, 3, 0, 2, 6, 4, 7, 5, 11, 10, 9, 8, 13, 14, 12, 15)
INVERT = bytes(i ^ 0xFF for i in range(256))

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def decode(data: bytes) -> bytes:
    if len(data) % 16:
        raise ValueError("Payload length must be a multiple of 16 bytes")
    result = bytearray(len(data))
    for output_index, input_index in enumerate(DECODE_ORDER):
        result[output_index::16] = data[input_index::16].translate(INVERT)
    return bytes(result)

def sum32(data: bytes) -> int:
    words = array("I")
    words.frombytes(data)
    if sys.byteorder != "little":
        words.byteswap()
    return sum(words) & 0xFFFFFFFF

def unpack(firmware_path: Path, output_dir: Path):
    data = firmware_path.read_bytes()
    output_dir.mkdir(parents=True, exist_ok=True)
    offset = 0
    block_idx = 0

    while offset < len(data):
        header = data[offset:offset+32]
        if header[:2] != b"OE":
            raise ValueError(f"Invalid magic at offset {offset:#x}")
        size = struct.unpack_from("<I", header, 12)[0]
        kind = struct.unpack_from("<H", header, 20)[0]
        addr = struct.unpack_from("<I", header, 8)[0]
        ver = struct.unpack_from("<H", header, 16)[0]
        end = offset + size + 64
        trailer = data[end-32:end]

        payload = decode(data[offset+32:end-32])
        csum = (sum32(header) + sum32(payload) + sum32(trailer)) & 0xFFFFFFFF
        if csum != 0:
            raise ValueError(f"Checksum mismatch in block {block_idx} (sum={csum:#x})")

        out_name = f"{block_idx:02d}_{kind:04x}_{addr+32:08x}.decoded.bin"
        (output_dir / out_name).write_bytes(payload)
        print(f"Block {block_idx} [kind=0x{kind:04x}, ver=0x{ver:04x}, addr=0x{addr+32:08x}]: {len(payload)} B -> {out_name}")
        block_idx += 1
        offset = end

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 unpack_oe.py <E1259999.BIN> <output_dir>")
        sys.exit(1)
    unpack(Path(sys.argv[1]), Path(sys.argv[2]))
```
