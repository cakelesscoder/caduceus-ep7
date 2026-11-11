# C Source File Inventory: Block 0 (`00_0100_40560020.decoded.bin`)

**Total Embedded Source Filenames**: 248 occurrences (244 unique `.c` files)  
**Compilation Paradigm**: GCC for MN103 / AM32R with embedded source file tracking (`__FILE__` strings).  

---

## 1. Operating System & Kernel (`boot/sys`)

| Source File | Functionality |
| :--- | :--- |
| `albm_os.c` | Album filesystem thread synchronization and OS wrappers. |
| `api_system.c` | High-level system state management (power on, sleep, battery cut). |
| `dosfat.c` | FAT32 file allocation table driver. |
| `dosfile.c` | File read, write, seek, and close abstractions. |
| `dospath.c` | Path normalization and 8.3 filename parsing. |
| `dospath_lfn.c` | Long File Name (LFN) Unicode support. |
| `move_util_system.c` | Video recording system utilities. |
| `movp_util_system.c` | Video playback system utilities. |
| `osddraw.c` | On-Screen Display vector drawing and font rasterizer. |
| `pos_debug.c` | Positional debugger and trace log manager. |
| `pos_main.c` | Positioning main loop (GPS / OI.Share location sync). |
| `rec_os.c` | Recording operating system task dispatcher. |

---

## 2. Firmware Update & ROM Access (`firmup/update`)

| Source File | Functionality |
| :--- | :--- |
| `api_firmup.c` | Main firmware update API, SD `DCOLYMP` search, preflight verification. |
| `play_rom.c` | Internal ROM asset reader, background music (`\BGM\*.WAV`) loader. |
| `stb_ext_firmup.c` | Hot-shoe accessory and flash unit firmware update protocol. |
| `stb_seq_flash.c` | Strobe sequence flash controller and flash parameter calculator. |

---

## 3. Camera Core, Autofocus & Image Processing (`image/lens`)

| Source File | Functionality |
| :--- | :--- |
| `Batpc_rawedit.c` | In-camera RAW image editor and development processor. |
| `api_disp.c` | Display mode switcher (EVF, rear LCD, HDMI output). |
| `cam_aedrv.c` | Automatic Exposure (AE) driver and metering calculation. |
| `cam_afdrv.c` | Autofocus (AF) motor driver and contrast-detection loop. |
| `cam_imgdev.c` | Image sensor device controller (Live MOS sensor timing). |
| `cam_imgdev_driver.c` | Sensor communication bus and register programming. |
| `cam_imgdev_sensor.c` | Sensor readout mode switching (mechanical shutter vs. electronic shutter). |
| `cam_imgdev_serial.c` | Sensor SPI control channel. |
| `cam_lens.c` | Digital lens mount communication protocol (focus-by-wire, aperture, OIS). |
| `fcs_img_Debug_AllScan.c` | Focus sensor diagnostic scan worker. |
| `fcs_img_Debug_Flag.c` | Focus debug flags. |
| `fcs_img_Debug_StackTrace.c`| Focus stack trace logger. |

---

## 4. Storage, DCF & Peripherals (`usb/sd`)

| Source File | Functionality |
| :--- | :--- |
| `dcfscan.c` | DCF directory scan and folder enumeration (`100OLYMP`, etc.). |
| `dcfsearch.c` | DCF image sequence search and next image number allocator. |
| `sd_asic.c` | Custom Olympus SD card controller ASIC interface. |
| `sd_mount.c` | SD card mount, partition table read, and speed negotiation (UHS-II). |
| `sdmem.c` | SD memory block read/write DMA engine. |
| `sdmem_format.c` | In-camera SD card formatting routine. |
| `sdphy.c` | Physical layer PHY tuning and clock frequency switcher. |

---

## 5. Network, Wi-Fi & Communications (`wifi/comm`)

| Source File | Functionality |
| :--- | :--- |
| `httpd_cgi.c` | Embedded HTTP web server for OI.Share smartphone app. |
| `movp_if_wifi.c` | Live-view video stream over Wi-Fi interface. |
| `olnet_proxy_isc_cli.c` | Olympus Network Proxy for remote shutter control. |
| `api_wifi.c` | Wi-Fi AP / Station mode switcher and WPA2 security manager. |
