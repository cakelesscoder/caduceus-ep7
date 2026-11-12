import struct
from pathlib import Path

bin_path = Path("/home/hertzel/projects/olympus-firmware/caduceus-ep7/em1mk2/extracted/00_0100_40560020.decoded.bin")
data = bin_path.read_bytes()
BASE_VMA = 0x60021020

target = struct.pack("<I", 0x61259c40)
idx = 0
while True:
    pos = data.find(target, idx)
    if pos == -1: break
    print(f"0x61259c40 referenced at {hex(BASE_VMA + pos)}")
    idx = pos + 1
