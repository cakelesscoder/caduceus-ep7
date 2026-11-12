import struct
from pathlib import Path

bin_path = Path("/home/hertzel/projects/olympus-firmware/caduceus-ep7/em1mk2/extracted/00_0100_40560020.decoded.bin")
data = bin_path.read_bytes()
BASE_VMA = 0x60021020

# Search for references to the table around 0x61259c40 or 0x61259b00
for test_addr in range(0x61259000, 0x6125a000, 4):
    target = struct.pack("<I", test_addr)
    idx = 0
    found = []
    while True:
        pos = data.find(target, idx)
        if pos == -1: break
        found.append(hex(BASE_VMA + pos))
        idx = pos + 1
    if found:
        print(f"Table candidate {hex(test_addr)}: referenced at {found}")
