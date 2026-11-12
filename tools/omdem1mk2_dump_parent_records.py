import struct
from pathlib import Path

bin_path = Path("/home/hertzel/projects/olympus-firmware/caduceus-ep7/em1mk2/extracted/00_0100_40560020.decoded.bin")
data = bin_path.read_bytes()
BASE_VMA = 0x60021020

# Dump 56-byte records starting before 0x61259c40 to after
for addr in range(0x61259b00, 0x61259d80, 56):
    off = addr - BASE_VMA
    key = struct.unpack_from("<H", data, off)[0]
    init = struct.unpack_from("<I", data, off + 4)[0]
    info = struct.unpack_from("<I", data, off + 44)[0]
    print(f"Record at {hex(addr)}: key={hex(key)} ({key}), init={hex(init)}, info={hex(info)}")
