# Firmware Update Mechanism (`api_firmup.c` & SD Flasher)

**Target Image**: `00_0100_40560020.decoded.bin`  
**Key Modules**: `api_firmup.c` (at `0x604f7ef4`), `stb_ext_firmup.c` (at `0x601fb6ae`), `play_rom.c` (at `0x6101451e`)  

---

## 1. Overview

The Olympus firmware update mechanism handles three categories of firmware updates:
1. **Camera Body Firmware** (flashed via SD card recovery mode or OM Workspace USB protocol).
2. **Four Thirds / Micro Four Thirds Lens Firmware** (flashed across the digital lens mount).
3. **External Accessories & Strobe (STB)** (flashed through the hot-shoe communication interface, e.g. external flashes, clip-on flash units, microphones).

---

## 2. SD Card Update Path (`DCOLYMP/`)

### 2.1 File Search Specifications
When booting with the `OK` button held down, the camera mounts the SD card using `sd_mount.c` and scans for firmware updates in the `DCOLYMP` folder.

#### Path Structure & Filename Patterns
| Pattern / Path | Address in ROM | Usage |
| :--- | :--- | :--- |
| `DCOLYMP    ` | `0x604f7f01` | Root folder on FAT32 filesystem (8.3 space-padded name: `DCOLYMP`). |
| `F???????BIN` | `0x604f7f0d` | Body firmware search pattern (e.g. `E1259999.BIN` or `F1250000.BIN`). |
| `L???????BIN` | `0x604f7f19` | Lens firmware search pattern (e.g. `L0019999.BIN`). |
| `%04x%04xBIN` | `0x604f7ee8` | Format template used for model ID + version matching. |

### 2.2 Scanning Logic (`0x602f9c10 - 0x602f9d10`)
1. **Mount Verification**: The SD physical layer checks card status via `sdmem_format.c` and `dosfat.c`.
2. **Directory Traverse**: Searches `\DCOLYMP\` on drive `0:` or `1:` (dual SD card slots).
3. **Pattern Matching**:
   - Compares candidate files against `F???????BIN` and `L???????BIN`.
   - File length and header signature `OE` (`0x4F45`) are read and validated.
   - Model ID field (`0x1250` for E-M1 Mark II) must match the hardware ID reported by the bootloader.
4. **Checksum Preflight**:
   - The camera calculates the 32-bit additive checksum of each partition block:
     $$\sum \text{Words}_{32}(\text{Header}) + \sum \text{Words}_{32}(\text{Payload}) + \sum \text{Words}_{32}(\text{Trailer}) \equiv 0 \pmod{2^{32}}$$
   - If any partition checksum fails, the update halts and the orange LED blinks an error code.

---

## 3. Accessory & Hot-Shoe Firmware Updates (`stb_ext_firmup.c`)

External accessories attached to the Olympus hot shoe are updated using the `stb_ext_firmup` subsystem (offset `0x1da68e`, address `0x601fb6ae`):

### Protocol Handshake & Fields
```
STB FIRM UP fw_type
STB FIRM UP id
STB FIRM UP hw_ver
STB FIRM UP STB_FIRMUP_FW_VER
STB FIRM UP major
STB FIRM UP minor
STB FIRM UP fw_extention
STB FIRM UP serial_number
STB FIRM UP START !!
STB FIRM UP header_maker       
STB FIRM UP header_fw          
STB FIRM UP header_id          
STB FIRM UP header_hw          
STB FIRM UP header_minor       
STB FIRM UP header_major       
STB FIRM UP header_extension   
STB FIRM UP header_start_adrs  
STB FIRM UP header_size        
STB FIRM UP STB_FIRMUP_START
STB FIRM UP STB_FIRMUP_START TRANSMIT
STB FIRM UP STB_FIRMUP_END
STB FIRM UP STB_FIRMUP_ABORT
STB FIRM UP ALL END !! status
```

1. **Identification**: Query accessory maker ID, hardware version, and current firmware version.
2. **Transfer**: Streams binary packets over the SPI/UART hot-shoe interface using `STB_FIRMUP_START TRANSMIT`.
3. **Verification**: Accessory reports `STB FIRM UP STB_FIRMUP_END` upon verifying internal checksums before committing to its local SPI flash.

---

## 4. Lens Firmware Updates (`cam_lens.c`)

Lenses mounted via Micro Four Thirds or Four Thirds adapters communicate over the bayonet interface:

- `LensFirmwareVersion[0]`: Current lens main firmware version (offset `0x19eb98`, address `0x601bfbb8`).
- `LensAdapterFirmwareVersion1[0]`: Adapter firmware version (offset `0x19ecd0`, address `0x601bfcf0`).
- Update images matching `L???????BIN` are transmitted using synchronous SPI bursts during the update state.
